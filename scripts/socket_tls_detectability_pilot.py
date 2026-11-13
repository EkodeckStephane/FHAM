"""Capture TLS byte streams from real local TCP sockets through a relay.

Positive FHAM exchanges are paired with same-length HTTP/1.1 controls and use
the same local TLS 1.3/OpenSSL endpoint configuration. The relay records only
numeric flow/record features; it does not save application or ciphertext bytes.
"""

from __future__ import annotations

import csv
import argparse
import select
import hashlib
import socket
import ssl
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.config import DATASET_DIR, RESULTS_DIR
from fham.experiments import _message
from fham.methods import BoundedAssignmentMethod
from matched_tls_control_pilot import http_message, tls_records
from traffic_transport_pilot import (
    generate_tls_certificate,
    make_application_exchange,
    make_tls_contexts,
)


def recv_exact(sock, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise ConnectionError(f"peer closed after {len(data)} of {count} bytes")
        data.extend(part)
    return bytes(data)


def socket_exchange(client_context, server_context, request, reply, *, tls: bool):
    """Relay one raw-TCP or TLS exchange over real loopback TCP sockets."""
    events = []
    errors = []
    server_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_listener.bind(("127.0.0.1", 0))
    server_listener.listen(1)
    server_listener.settimeout(10)

    relay_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    relay_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    relay_listener.bind(("127.0.0.1", 0))
    relay_listener.listen(1)
    relay_listener.settimeout(10)

    def server_worker():
        try:
            raw, _ = server_listener.accept()
            def respond(channel):
                received = recv_exact(channel, len(request))
                if received != request:
                    raise AssertionError("server received different application bytes")
                channel.sendall(reply)
            if tls:
                with server_context.wrap_socket(raw, server_side=True) as channel:
                    respond(channel)
            else:
                with raw:
                    respond(raw)
        except Exception as exc:  # captured and re-raised in the caller
            errors.append(exc)

    def relay_worker():
        upstream = None
        downstream = None
        try:
            downstream, _ = relay_listener.accept()
            upstream = socket.create_connection(server_listener.getsockname(), timeout=10)
            downstream.settimeout(None)
            upstream.settimeout(None)
            peers = {downstream: (upstream, 0), upstream: (downstream, 1)}
            open_sides = set(peers)
            deadline = time.monotonic() + 15
            while open_sides:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("TCP relay exceeded 15 seconds")
                readable, _, _ = select.select(list(open_sides), [], [], min(remaining, 1))
                if not readable:
                    continue
                for source in readable:
                    target, direction = peers[source]
                    chunk = source.recv(65536)
                    if not chunk:
                        open_sides.remove(source)
                        try:
                            target.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
                        continue
                    target.sendall(chunk)
                    events.append((time.perf_counter_ns(), direction, chunk))
        except Exception as exc:
            errors.append(exc)
        finally:
            for sock in (downstream, upstream):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass

    server_thread = threading.Thread(target=server_worker, daemon=True)
    relay_thread = threading.Thread(target=relay_worker, daemon=True)
    server_thread.start()
    relay_thread.start()
    client_raw = socket.create_connection(relay_listener.getsockname(), timeout=10)
    try:
        client_raw.settimeout(10)
        def exchange(channel):
            channel.sendall(request)
            received = recv_exact(channel, len(reply))
            if received != reply:
                raise AssertionError("client received different application bytes")
        if tls:
            with client_context.wrap_socket(client_raw, server_hostname="fham-pilot.local") as channel:
                exchange(channel)
        else:
            with client_raw:
                exchange(client_raw)
    finally:
        server_thread.join(timeout=15)
        relay_thread.join(timeout=15)
        server_listener.close()
        relay_listener.close()
    if server_thread.is_alive() or relay_thread.is_alive():
        raise TimeoutError("TCP socket worker did not stop")
    if errors:
        raise errors[0]
    return events


def summarize_events(events, *, tls: bool):
    streams = [bytearray(), bytearray()]
    chunks = [[], []]
    times = [[], []]
    for timestamp, direction, data in events:
        streams[direction].extend(data)
        chunks[direction].append(len(data))
        times[direction].append(timestamp)
    records = (
        [tls_records([(0, d, bytes(streams[d]))]) for d in (0, 1)]
        if tls else [[], []]
    )
    result = {
        "relay_duration_ms": (
            (max(t for t, _, _ in events) - min(t for t, _, _ in events)) / 1e6
            if events else 0.0
        ),
        "relay_event_count": len(events),
    }
    for direction, name in enumerate(("client", "server")):
        lengths = [row[2] for row in records[direction]]
        result[f"{name}_wire_bytes"] = len(streams[direction])
        result[f"{name}_record_count"] = len(lengths)
        result[f"{name}_record_lengths"] = ";".join(map(str, lengths))
        result[f"{name}_read_count"] = len(chunks[direction])
        result[f"{name}_read_sizes"] = ";".join(map(str, chunks[direction][:12]))
        result[f"{name}_read_max"] = max(chunks[direction], default=0)
        for index in range(12):
            result[f"{name}_record_len_{index}"] = lengths[index] if index < len(lengths) else 0
            result[f"{name}_read_size_{index}"] = chunks[direction][index] if index < len(chunks[direction]) else 0
        intervals_ms = np.diff(times[direction]) / 1e6
        result[f"{name}_iat_mean_ms"] = float(np.mean(intervals_ms)) if len(intervals_ms) else 0.0
        result[f"{name}_iat_max_ms"] = float(np.max(intervals_ms)) if len(intervals_ms) else 0.0
    result["fham_marker_in_stream"] = int(
        b"FHAM\x01" in streams[0] + streams[1]
    )
    return result


def write_rows(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def classifier_auc(rows, feature_names):
    x = np.asarray([[float(row[key]) for key in feature_names] for row in rows])
    y = np.asarray([int(row["label_fham"]) for row in rows])
    groups = np.asarray([row["pair_id"] for row in rows])
    predictions = np.zeros(len(rows), dtype=float)
    splitter = GroupKFold(n_splits=5)
    fold_ids = np.full(len(rows), -1, dtype=int)
    for fold_id, (train, test) in enumerate(splitter.split(x, y, groups)):
        model = make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")
        )
        model.fit(x[train], y[train])
        predictions[test] = model.predict_proba(x[test])[:, 1]
        fold_ids[test] = fold_id
    fold_aucs = [
        roc_auc_score(y[fold_ids == fold_id], predictions[fold_ids == fold_id])
        for fold_id in range(5)
    ]
    auc = float(np.mean(fold_aucs))
    unique_groups = np.unique(groups)
    indices_by_group = {group: np.flatnonzero(groups == group) for group in unique_groups}
    rng = np.random.default_rng(20261113)
    bootstrapped = []
    for _ in range(1000):
        resampled_fold_aucs = []
        for fold_id in range(5):
            fold_groups = np.unique(groups[fold_ids == fold_id])
            sampled_groups = rng.choice(fold_groups, size=len(fold_groups), replace=True)
            indices = np.concatenate([indices_by_group[group] for group in sampled_groups])
            resampled_fold_aucs.append(roc_auc_score(y[indices], predictions[indices]))
        sampled_auc = float(np.mean(resampled_fold_aucs))
        bootstrapped.append(max(sampled_auc, 1.0 - sampled_auc))
    low, high = np.percentile(bootstrapped, (2.5, 97.5))
    return auc, max(auc, 1.0 - auc), float(low), float(high)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="latest", help="identifier for repeated socket-capture runs")
    run_id = parser.parse_args().run_id
    run_salt = int.from_bytes(hashlib.sha256(run_id.encode("utf-8")).digest()[:4], "big")
    images = {
        path.stem: np.asarray(Image.open(path).convert("L"))
        for path in sorted((DATASET_DIR / "controlled").glob("*.png"))
    }
    methods = {}
    for name, image in images.items():
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        methods[name] = method

    flows = []
    with tempfile.TemporaryDirectory(prefix="fham-socket-detectability-") as temp:
        cert, key = generate_tls_certificate(Path(temp))
        client_context, server_context = make_tls_contexts(cert, key)
        pair_index = 0
        for length in (40, 200):
            for image_name, image in images.items():
                for trial in range(5):
                    pair_id_base = f"{length}-{image_name}-{trial}"
                    message = _message(length, image_name, trial + run_salt)
                    fham_request, fham_reply, _ = make_application_exchange(
                        image, message, pair_index, methods[image_name]
                    )
                    http_request = http_message(
                        len(fham_request), response=False, seed=pair_index + run_salt + 101
                    )
                    http_reply = http_message(
                        len(fham_reply), response=True, seed=pair_index + run_salt + 809
                    )
                    for mode in ("raw_tcp", "tls13_tcp"):
                        pair_id = f"{mode}-{pair_id_base}"
                        exchanges = [
                            ("fham", fham_request, fham_reply),
                            ("http_control", http_request, http_reply),
                        ]
                        if (pair_index + int(mode == "tls13_tcp")) % 2:
                            exchanges.reverse()
                        for label, request, reply in exchanges:
                            use_tls = mode == "tls13_tcp"
                            events = socket_exchange(
                                client_context if use_tls else None,
                                server_context if use_tls else None,
                                request, reply, tls=use_tls,
                            )
                            flows.append({
                                "pair_id": pair_id,
                                "transport_mode": mode,
                                "label": label,
                                "label_fham": int(label == "fham"),
                                "message_length": length,
                                "image": image_name,
                                "request_plaintext_bytes": len(request),
                                "reply_plaintext_bytes": len(reply),
                                **summarize_events(events, tls=use_tls),
                            })
                    pair_index += 1

    size_features = [
        "client_wire_bytes", "server_wire_bytes", "client_record_count",
        "server_record_count",
    ] + [
        f"{direction}_record_len_{index}"
        for direction in ("client", "server") for index in range(12)
    ]
    observer_features = size_features + [
        "relay_duration_ms", "relay_event_count", "client_read_count",
        "server_read_count", "client_read_max", "server_read_max",
        "client_iat_mean_ms", "client_iat_max_ms",
        "server_iat_mean_ms", "server_iat_max_ms",
    ] + [
        f"{direction}_read_size_{index}"
        for direction in ("client", "server") for index in range(12)
    ]

    summary = []
    for mode in ("raw_tcp", "tls13_tcp"):
        mode_flows = [row for row in flows if row["transport_mode"] == mode]
        groups = {}
        for row in mode_flows:
            groups.setdefault(row["pair_id"], {})[row["label"]] = row
        wire_match_count = sum(
            int(group["fham"]["client_wire_bytes"] == group["http_control"]["client_wire_bytes"]
                and group["fham"]["server_wire_bytes"] == group["http_control"]["server_wire_bytes"])
            for group in groups.values()
        )
        record_match_count = sum(
            int(group["fham"]["client_record_lengths"] == group["http_control"]["client_record_lengths"]
                and group["fham"]["server_record_lengths"] == group["http_control"]["server_record_lengths"])
            for group in groups.values()
        )
        positives = [row for row in mode_flows if row["label"] == "fham"]
        controls = [row for row in mode_flows if row["label"] == "http_control"]
        auc_size = classifier_auc(mode_flows, size_features)
        auc_observer = classifier_auc(mode_flows, observer_features)
        summary.append({
            "run_id": run_id,
            "transport_mode": mode,
            "matched_pairs": len(groups),
            "flows": len(mode_flows),
            "fham_marker_positive_hits": sum(int(row["fham_marker_in_stream"]) for row in positives),
            "http_control_marker_hits": sum(int(row["fham_marker_in_stream"]) for row in controls),
            "pairs_with_equal_directional_wire_bytes": wire_match_count,
            "pairs_with_equal_tls_record_length_sequences": record_match_count if mode == "tls13_tcp" else "NA",
            "grouped_5fold_auc_size_records_raw_orientation": auc_size[0],
            "grouped_5fold_auc_size_records_separability": auc_size[1],
            "size_record_separability_ci95_low": auc_size[2],
            "size_record_separability_ci95_high": auc_size[3],
            "grouped_5fold_auc_all_relay_raw_orientation": auc_observer[0],
            "grouped_5fold_auc_all_relay_separability": auc_observer[1],
            "all_relay_separability_ci95_low": auc_observer[2],
            "all_relay_separability_ci95_high": auc_observer[3],
        })
    write_rows(RESULTS_DIR / f"socket_tls_detectability_flows_{run_id}.csv", flows)
    write_rows(RESULTS_DIR / f"socket_tls_detectability_summary_{run_id}.csv", summary)
    print(summary)


if __name__ == "__main__":
    main()
