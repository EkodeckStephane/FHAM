"""Measure FHAM and matched HTTP flows using a Windows Schannel TLS client.

The server and transparent relay are local. The client uses .NET SslStream on
Windows with TLS 1.2, while the application bytes and server implementation
match the existing socket-level pilot. Only aggregate flow features are saved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import random
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.config import DATASET_DIR, RESULTS_DIR
from fham.experiments import _message
from fham.methods import BoundedAssignmentMethod
from matched_tls_control_pilot import http_message
from socket_tls_detectability_pilot import socket_exchange, summarize_events, write_rows
from traffic_transport_pilot import (
    FRAME_HEADER,
    FRAME_ACK,
    FRAME_OFFER,
    FRAME_RECORD,
    generate_tls_certificate,
    make_application_exchange,
    pack_frame,
    unpack_frames,
)


TLS12_APP_OVERHEAD = 29
TLS12_RESUMED_CLIENT_HANDSHAKE_BYTES = 399
TLS12_RESUMED_SERVER_HANDSHAKE_BYTES = 109
RESUMED_HANDSHAKE_RECORDS_PER_DIRECTION = 3
FRAME_PADDING = 4
MAX_TLS_PLAINTEXT = 16_384


def make_server_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return context


def make_schannel_runner(request_path: Path):
    script_path = ROOT / "scripts" / "schannel_tls_client.ps1"
    process = subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(script_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )

    def run(address, request: bytes, reply: bytes, server_name: str,
            write_chunks=None):
        host, port = address
        request_path.write_bytes(request)
        if process.poll() is not None:
            raise RuntimeError("Persistent Schannel client exited unexpectedly")
        chunk_field = ",".join(str(value) for value in write_chunks) if write_chunks else "-"
        process.stdin.write(
            f"{server_name}|{host}|{port}|{request_path}|{len(reply)}|{chunk_field}\n"
        )
        process.stdin.flush()
        response = process.stdout.readline().strip()
        if response != "OK":
            detail = process.stderr.readline().strip()
            raise RuntimeError(f"Schannel client failed: {detail or response}")

    def close():
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)

    run.close = close

    return run


def load_shape_templates():
    path = RESULTS_DIR / "nonvpn_tls_flow_features.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    groups = sorted({row["capture_group"] for row in rows})
    template_groups = {group for index, group in enumerate(groups) if index % 3 == 0}
    template_rows = [row for row in rows if row["capture_group"] in template_groups]
    evaluation_rows = [row for row in rows if row["capture_group"] not in template_groups]
    write_rows(RESULTS_DIR / "nonvpn_tls_flow_features_eval.csv", evaluation_rows)
    with (RESULTS_DIR / "nonvpn_tls_shape_template_groups.txt").open(
        "w", encoding="utf-8"
    ) as stream:
        stream.write("\n".join(sorted(template_groups)) + "\n")
    return template_rows, evaluation_rows, template_groups


def parse_lengths(value: str) -> list[int]:
    return [int(item) for item in value.split(";") if item]


def allocate_chunks(total: int, count: int,
                    template_lengths: list[int]) -> list[int]:
    if count < 1 or len(template_lengths) < count:
        raise ValueError("target TLS record profile cannot carry the framed application data")
    chunks = [value - TLS12_APP_OVERHEAD for value in template_lengths[:count]]
    chunks[-1] += total - sum(chunks)
    if any(size < 1 or size > MAX_TLS_PLAINTEXT for size in chunks):
        raise ValueError("sampled target cannot be represented by TLS application records")
    return chunks


def make_padded_frame(base: bytes, total_plaintext: int, chunk_count: int,
                      template_lengths: list[int]):
    padding_bytes = total_plaintext - len(base) - FRAME_HEADER.size
    if padding_bytes < 0:
        raise ValueError("background TLS target is smaller than the original FHAM frame")
    padding_frame = pack_frame(FRAME_PADDING, os.urandom(padding_bytes))
    padded = base + padding_frame
    chunks = allocate_chunks(len(padded), chunk_count, template_lengths)
    parsed_base = unpack_frames(base)
    parsed_padded = unpack_frames(padded)
    if parsed_padded[:-1] != parsed_base or parsed_padded[-1][0] != FRAME_PADDING:
        raise AssertionError("padding frame changed the original application frames")
    return padded, chunks, padding_bytes


def choose_shape_target(template_rows, request_size, reply_size, rng):
    feasible = []
    for row in template_rows:
        client_lengths = parse_lengths(row["client_tls_record_lengths"])
        server_lengths = parse_lengths(row["server_tls_record_lengths"])
        client_chunks = len(client_lengths) - RESUMED_HANDSHAKE_RECORDS_PER_DIRECTION
        server_chunks = len(server_lengths) - RESUMED_HANDSHAKE_RECORDS_PER_DIRECTION
        if not (2 <= client_chunks <= 9 and 6 <= server_chunks <= 11):
            continue
        client_app_template = client_lengths[RESUMED_HANDSHAKE_RECORDS_PER_DIRECTION:]
        server_app_template = server_lengths[RESUMED_HANDSHAKE_RECORDS_PER_DIRECTION:]
        if min(client_app_template, default=0) < 30 or min(server_app_template, default=0) < 30:
            continue
        if (max(client_app_template, default=0) > MAX_TLS_PLAINTEXT + TLS12_APP_OVERHEAD
                or max(server_app_template, default=0) > MAX_TLS_PLAINTEXT + TLS12_APP_OVERHEAD):
            continue
        client_plaintext = (
            sum(client_lengths) - TLS12_RESUMED_CLIENT_HANDSHAKE_BYTES
            - TLS12_APP_OVERHEAD * client_chunks
        )
        server_plaintext = (
            sum(server_lengths) - TLS12_RESUMED_SERVER_HANDSHAKE_BYTES
            - TLS12_APP_OVERHEAD * server_chunks
        )
        if (client_plaintext >= request_size + FRAME_HEADER.size
                and server_plaintext >= reply_size + FRAME_HEADER.size
                and client_plaintext <= MAX_TLS_PLAINTEXT * client_chunks
                and server_plaintext <= MAX_TLS_PLAINTEXT * server_chunks
                and 1 <= client_app_template[-1] - TLS12_APP_OVERHEAD
                + client_plaintext - sum(value - TLS12_APP_OVERHEAD for value in client_app_template)
                <= MAX_TLS_PLAINTEXT
                and 1 <= server_app_template[-1] - TLS12_APP_OVERHEAD
                + server_plaintext - sum(value - TLS12_APP_OVERHEAD for value in server_app_template)
                <= MAX_TLS_PLAINTEXT):
            feasible.append((row, client_lengths, server_lengths,
                             client_chunks, server_chunks,
                             client_plaintext, server_plaintext))
    if not feasible:
        raise RuntimeError(
            f"no training-capture shape can carry {request_size}/{reply_size} application bytes"
        )
    return rng.choice(feasible)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", choices=("rep1", "rep2", "rep3"), required=True)
    parser.add_argument("--limit-pairs", type=int, default=0,
                        help="optional smoke-run limit; zero evaluates all 80 pairs")
    parser.add_argument(
        "--shape-to-background", action="store_true",
        help="add a padding frame and fragment app data to training-capture TLS sizes/counts",
    )
    args = parser.parse_args()
    run_salt = int.from_bytes(hashlib.sha256(args.run_id.encode()).digest()[:4], "big")
    template_rows = evaluation_rows = template_groups = []
    if args.shape_to_background:
        template_rows, evaluation_rows, template_groups = load_shape_templates()
    images = {
        path.stem: np.asarray(Image.open(path).convert("L"))
        for path in sorted((DATASET_DIR / "controlled").glob("*.png"))
    }
    methods = {}
    for name, image in images.items():
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        methods[name] = method

    rows = []
    pair_index = 0
    with tempfile.TemporaryDirectory(prefix="fham-schannel-pilot-") as temp:
        temporary = Path(temp)
        cert_path, key_path = generate_tls_certificate(temporary)
        server_context = make_server_context(cert_path, key_path)
        client_runner = make_schannel_runner(temporary / "request.bin")
        try:
            for length in (40, 200):
                for image_name, image in images.items():
                    for trial in range(5):
                        message = _message(length, image_name, trial + run_salt)
                        request, reply, checks = make_application_exchange(
                            image, message, pair_index, methods[image_name]
                        )
                        shape = None
                        if args.shape_to_background:
                            rng = random.Random(run_salt + pair_index * 1009)
                            shape = choose_shape_target(
                                template_rows, len(request), len(reply), rng
                            )
                            template, target_client, target_server, client_app_count, server_app_count, client_plain, server_plain = shape
                            padded_request, client_chunks, request_pad_bytes = make_padded_frame(
                                request, client_plain, client_app_count,
                                target_client[RESUMED_HANDSHAKE_RECORDS_PER_DIRECTION:],
                            )
                            padded_reply, server_chunks, reply_pad_bytes = make_padded_frame(
                                reply, server_plain, server_app_count,
                                target_server[RESUMED_HANDSHAKE_RECORDS_PER_DIRECTION:],
                            )
                            control_request = http_message(
                                len(padded_request), response=False,
                                seed=pair_index + run_salt + 101,
                            )
                            control_reply = http_message(
                                len(padded_reply), response=True,
                                seed=pair_index + run_salt + 809,
                            )
                            target_totals = (sum(target_client), sum(target_server))
                            target_counts = (len(target_client), len(target_server))
                        else:
                            padded_request, padded_reply = request, reply
                            client_chunks = server_chunks = None
                            request_pad_bytes = reply_pad_bytes = 0
                            target_totals = target_counts = None
                            control_request = http_message(
                                len(request), response=False,
                                seed=pair_index + run_salt + 101,
                            )
                            control_reply = http_message(
                                len(reply), response=True,
                                seed=pair_index + run_salt + 809,
                            )
                        exchanges = [
                            ("fham", padded_request, padded_reply),
                            ("http_control", control_request, control_reply),
                        ]
                        if (pair_index + int(args.run_id[-1])) % 2:
                            exchanges.reverse()
                        server_name = "fham-pilot.local"
                        socket_exchange(
                            None, server_context, b"", b"", tls=True,
                            client_runner=client_runner, tls_server_name=server_name,
                        )
                        for label, client_request, server_reply in exchanges:
                            events = socket_exchange(
                                None, server_context, client_request, server_reply,
                                tls=True, client_runner=client_runner,
                                tls_server_name=server_name,
                                client_write_chunks=client_chunks,
                                server_write_chunks=server_chunks,
                            )
                            features = summarize_events(events, tls=True)
                            if shape is not None and label == "fham":
                                observed_totals = (
                                    int(features["client_wire_bytes"]),
                                    int(features["server_wire_bytes"]),
                                )
                                observed_counts = (
                                    int(features["client_record_count"]),
                                    int(features["server_record_count"]),
                                )
                                if observed_totals != target_totals or observed_counts != target_counts:
                                    raise AssertionError(
                                        f"shaped TLS flow differs from target {target_totals}/{target_counts}: "
                                        f"{observed_totals}/{observed_counts}"
                                    )
                            rows.append({
                                "pair_id": f"schannel_tls12{'_shaped' if shape is not None else ''}-{args.run_id}-{length}-{image_name}-{trial}",
                                "transport_mode": "schannel_tls12_shaped" if shape is not None else "schannel_tls12",
                                "label": label,
                                "label_fham": int(label == "fham"),
                                "message_length": length,
                                "image": image_name,
                                "request_plaintext_bytes": len(client_request),
                                "reply_plaintext_bytes": len(server_reply),
                                "exact_recovery_verified_before_transport": int(
                                    label != "fham" or checks["exact_recovery"]
                                ),
                                "padding_request_bytes": request_pad_bytes if label == "fham" else 0,
                                "padding_reply_bytes": reply_pad_bytes if label == "fham" else 0,
                                "shape_template_capture": template["capture"] if shape is not None else "",
                                **features,
                            })
                        pair_index += 1
                        if args.limit_pairs and pair_index >= args.limit_pairs:
                            break
                    if args.limit_pairs and pair_index >= args.limit_pairs:
                        break
                if args.limit_pairs and pair_index >= args.limit_pairs:
                    break
        finally:
            client_runner.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_prefix = "schannel_shaped_tls_flows" if args.shape_to_background else "schannel_tls_flows"
    flows_path = RESULTS_DIR / f"{output_prefix}_{args.run_id}.csv"
    write_rows(flows_path, rows)

    pairs = {}
    for row in rows:
        pairs.setdefault(row["pair_id"], {})[row["label"]] = row
    complete_pairs = [pair for pair in pairs.values() if len(pair) == 2]
    matched_lengths = sum(
        int(pair["fham"]["client_wire_bytes"] == pair["http_control"]["client_wire_bytes"]
            and pair["fham"]["server_wire_bytes"] == pair["http_control"]["server_wire_bytes"])
        for pair in complete_pairs
    )
    matched_records = sum(
        int(pair["fham"]["client_record_lengths"] == pair["http_control"]["client_record_lengths"]
            and pair["fham"]["server_record_lengths"] == pair["http_control"]["server_record_lengths"])
        for pair in complete_pairs
    )
    print({
        "run": args.run_id,
        "pairs": len(complete_pairs),
        "sessions": len(rows),
        "directional_byte_totals_matched": matched_lengths,
        "directional_record_sequences_matched": matched_records,
        "padding_profile": args.shape_to_background,
        "template_capture_groups": len(template_groups),
        "evaluation_capture_groups": len({row["capture_group"] for row in evaluation_rows})
        if args.shape_to_background else 0,
        "all_fham_recoveries_verified": all(
            row["exact_recovery_verified_before_transport"]
            for row in rows if row["label"] == "fham"
        ),
        "flows_csv": str(flows_path),
    })


if __name__ == "__main__":
    main()
