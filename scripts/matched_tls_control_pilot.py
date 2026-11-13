"""Compare FHAM and length-matched HTTP controls at the TLS 1.3 record layer.

This memory-BIO experiment does not open network sockets or capture packets.
It isolates application-content leakage from record-size leakage under the
same local OpenSSL TLS configuration.
"""

from __future__ import annotations

import csv
import random
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.config import DATASET_DIR, RESULTS_DIR
from fham.methods import BoundedAssignmentMethod
from traffic_transport_pilot import (
    generate_tls_certificate,
    make_application_exchange,
    make_tls_contexts,
    tls13_exchange,
)
from fham.experiments import _message


ALPHABET = b"abcdefghijklmnopqrstuvwxyz0123456789"


def http_message(target_length: int, *, response: bool, seed: int) -> bytes:
    """Create a valid HTTP/1.1 JSON message with exactly target_length bytes."""
    rng = random.Random(seed)
    body_prefix = b'{"payload":"'
    body_suffix = b'"}'
    filler = bytes(rng.choice(ALPHABET) for _ in range(target_length))
    for body_length in range(max(0, target_length - 512), target_length):
        body = body_prefix + filler[:body_length] + body_suffix
        if response:
            header = (
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Connection: keep-alive\r\n\r\n"
            )
        else:
            header = (
                b"POST /api/v1/messages HTTP/1.1\r\n"
                b"Host: fham-pilot.local\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Connection: keep-alive\r\n\r\n"
            )
        message = header + body
        if len(message) == target_length:
            return message
    raise ValueError(f"cannot fit valid HTTP message in {target_length} bytes")


def tls_records(events):
    """Return direction, content type, and wire length for each TLS record."""
    records = []
    for _tick, direction, chunk in events:
        offset = 0
        while offset < len(chunk):
            if len(chunk) - offset < 5:
                raise ValueError("truncated TLS record header")
            content_type = chunk[offset]
            length = int.from_bytes(chunk[offset + 3:offset + 5], "big")
            end = offset + 5 + length
            if end > len(chunk):
                raise ValueError("truncated TLS record payload")
            records.append((direction, content_type, length + 5))
            offset = end
    return records


def write_csv(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    images = {}
    for path in sorted((DATASET_DIR / "controlled").glob("*.png")):
        images[path.stem] = np.asarray(Image.open(path).convert("L"))

    codebooks = {}
    for name, image in images.items():
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        codebooks[name] = method

    rows = []
    with tempfile.TemporaryDirectory(prefix="fham-matched-tls-") as temp:
        cert_path, key_path = generate_tls_certificate(Path(temp))
        client_context, server_context = make_tls_contexts(cert_path, key_path)
        for message_length in (40, 200):
            for image_name, image in images.items():
                method = codebooks[image_name]
                for trial in range(5):
                    pair_id = f"{message_length}-{image_name}-{trial}"
                    message = _message(message_length, image_name, trial)
                    request, reply, _checks = make_application_exchange(
                        image, message, trial, method
                    )
                    control_request = http_message(
                        len(request), response=False, seed=trial + 101
                    )
                    control_reply = http_message(
                        len(reply), response=True, seed=trial + 809
                    )

                    fham_events = tls13_exchange(
                        request, reply, client_context, server_context
                    )
                    control_events = tls13_exchange(
                        control_request, control_reply,
                        client_context, server_context,
                    )
                    fham_records = tls_records(fham_events)
                    control_records = tls_records(control_events)
                    fham_direction_lengths = [
                        tuple(row[2] for row in fham_records if row[0] == direction)
                        for direction in (0, 1)
                    ]
                    control_direction_lengths = [
                        tuple(row[2] for row in control_records if row[0] == direction)
                        for direction in (0, 1)
                    ]
                    fham_wire = [
                        sum(row[2] for row in fham_records if row[0] == direction)
                        for direction in (0, 1)
                    ]
                    control_wire = [
                        sum(row[2] for row in control_records if row[0] == direction)
                        for direction in (0, 1)
                    ]
                    fham_ciphertext = [b"".join(event[2] for event in fham_events if event[1] == d) for d in (0, 1)]
                    control_ciphertext = [b"".join(event[2] for event in control_events if event[1] == d) for d in (0, 1)]
                    rows.append({
                        "pair_id": pair_id,
                        "message_length": message_length,
                        "image": image_name,
                        "fham_plaintext_request_bytes": len(request),
                        "http_plaintext_request_bytes": len(control_request),
                        "fham_plaintext_reply_bytes": len(reply),
                        "http_plaintext_reply_bytes": len(control_reply),
                        "fham_tls_record_count": len(fham_records),
                        "http_tls_record_count": len(control_records),
                        "fham_client_tls_bytes": fham_wire[0],
                        "http_client_tls_bytes": control_wire[0],
                        "fham_server_tls_bytes": fham_wire[1],
                        "http_server_tls_bytes": control_wire[1],
                        "client_record_lengths_equal": int(
                            fham_direction_lengths[0] == control_direction_lengths[0]
                        ),
                        "server_record_lengths_equal": int(
                            fham_direction_lengths[1] == control_direction_lengths[1]
                        ),
                        "fham_marker_in_tls_bytes": int(
                            b"FHAM\x01" in fham_ciphertext[0] + fham_ciphertext[1]
                        ),
                        "http_marker_in_tls_bytes": int(
                            b"FHAM\x01" in control_ciphertext[0] + control_ciphertext[1]
                        ),
                    })

    output = RESULTS_DIR / "matched_tls_control_pilot.csv"
    write_csv(rows, output)
    count = len(rows)
    print({
        "pairs": count,
        "exact_plaintext_length_match": all(
            int(row["fham_plaintext_request_bytes"]) == int(row["http_plaintext_request_bytes"])
            and int(row["fham_plaintext_reply_bytes"]) == int(row["http_plaintext_reply_bytes"])
            for row in rows
        ),
        "client_record_length_matches": sum(int(r["client_record_lengths_equal"]) for r in rows),
        "server_record_length_matches": sum(int(r["server_record_lengths_equal"]) for r in rows),
        "fham_markers_in_tls_records": sum(int(r["fham_marker_in_tls_bytes"]) for r in rows),
        "control_markers_in_tls_records": sum(int(r["http_marker_in_tls_bytes"]) for r in rows),
        "output": str(output),
    })


if __name__ == "__main__":
    main()
