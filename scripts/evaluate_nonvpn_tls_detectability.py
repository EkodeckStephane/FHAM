"""Compare live-socket FHAM TLS streams with TLS flows in the NonVPN PCAPs.

The classifier uses only TLS record lengths and direction. Negative folds are
grouped by source capture; FHAM folds are held out by independent socket run.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.config import RESULTS_DIR
from traffic_transport_pilot import decode_tcp
from analyze_nonvpn_traces import parse_pcap, parse_pcapng


MAX_STREAM_BYTES = 256_000
TLS_CONTENT_TYPES = {20, 21, 22, 23, 24}


class TCPStream:
    def __init__(self):
        self.next_seq = None
        self.pending = {}
        self.pending_bytes = 0
        self.data = bytearray()
        self.gaps = 0

    def _consume(self, data):
        room = MAX_STREAM_BYTES - len(self.data)
        if room > 0:
            self.data.extend(data[:room])
        if self.next_seq is not None:
            self.next_seq = (self.next_seq + len(data)) & 0xFFFFFFFF

    def feed(self, seq, flags, payload):
        data_seq = (seq + (1 if flags & 0x02 else 0)) & 0xFFFFFFFF
        if self.next_seq is None:
            self.next_seq = data_seq
        if not payload:
            return
        delta = (data_seq - self.next_seq) & 0xFFFFFFFF
        if delta == 0:
            self._consume(payload)
            while self.next_seq in self.pending:
                data = self.pending.pop(self.next_seq)
                self.pending_bytes -= len(data)
                self._consume(data)
        elif delta < 0x80000000:
            if self.pending_bytes + len(payload) <= 1_000_000:
                if data_seq not in self.pending:
                    self.pending[data_seq] = payload
                    self.pending_bytes += len(payload)
            else:
                self.gaps += 1


class TCPFlow:
    def __init__(self, first_direction, timestamp):
        self.first_direction = first_direction
        self.first_ts = timestamp
        self.last_ts = timestamp
        self.packets = [0, 0]
        self.wire_bytes = [0, 0]
        self.streams = [TCPStream(), TCPStream()]
        self.client_direction = first_direction

    def add(self, timestamp, direction, sport, dport, seq, flags, ip_bytes, payload):
        self.last_ts = max(self.last_ts, timestamp)
        self.packets[direction] += 1
        self.wire_bytes[direction] += ip_bytes
        if flags & 0x02 and not (flags & 0x10):
            self.client_direction = direction
        elif dport in (80, 443) and sport not in (80, 443):
            self.client_direction = direction
        self.streams[direction].feed(seq, flags, payload)


def parse_tls_records(stream):
    """Find a coherent run of TLS records, allowing midstream capture offsets."""
    end_scan = min(64, max(0, len(stream) - 5))
    best = []
    for offset in range(end_scan + 1):
        records = []
        cursor = offset
        while cursor + 5 <= len(stream):
            content_type = stream[cursor]
            major = stream[cursor + 1]
            minor = stream[cursor + 2]
            size = int.from_bytes(stream[cursor + 3:cursor + 5], "big")
            if content_type not in TLS_CONTENT_TYPES or major != 3 or minor > 4 or size > 18432:
                break
            next_cursor = cursor + 5 + size
            if next_cursor > len(stream):
                break
            records.append((5 + size, content_type, major * 256 + minor))
            cursor = next_cursor
        if len(records) > len(best):
            best = records
    return best if len(best) >= 2 else []


def extract_tls_flows(capture_root: Path):
    captures = sorted(
        path for path in capture_root.rglob("*")
        if path.is_file() and path.suffix.lower() in (".pcap", ".pcapng")
    )
    rows = []
    for capture_index, path in enumerate(captures, 1):
        flows = {}

        def consume(timestamp, caplen, origlen, linktype, packet):
            if timestamp is None:
                timestamp = 0.0
            decoded = decode_tcp(packet, linktype)
            if decoded is None:
                return
            version, src, dst, sport, dport, seq, ack, flags, ip_bytes, payload = decoded
            left, right = (src, sport), (dst, dport)
            if left <= right:
                key, direction = (version, left, right), 0
            else:
                key, direction = (version, right, left), 1
            flow = flows.get(key)
            if flow is None:
                flow = TCPFlow(direction, timestamp)
                flows[key] = flow
            flow.add(timestamp, direction, sport, dport, seq, flags, ip_bytes, payload)

        if path.suffix.lower() == ".pcapng":
            parse_pcapng(path, consume)
        else:
            parse_pcap(path, consume)

        for flow_index, flow in enumerate(flows.values()):
            client_dir = flow.client_direction
            server_dir = 1 - client_dir
            client_records = parse_tls_records(flow.streams[client_dir].data)
            server_records = parse_tls_records(flow.streams[server_dir].data)
            if len(client_records) + len(server_records) < 3:
                continue
            row = {
                "capture": path.name,
                "capture_group": path.name,
                "scenario": path.parent.name,
                "flow_index": flow_index,
                "tcp_packets": sum(flow.packets),
                "tcp_ip_bytes": sum(flow.wire_bytes),
                "duration_seconds": max(0.0, flow.last_ts - flow.first_ts),
                "client_tls_record_count": len(client_records),
                "server_tls_record_count": len(server_records),
                "client_tls_record_lengths": ";".join(str(x[0]) for x in client_records),
                "server_tls_record_lengths": ";".join(str(x[0]) for x in server_records),
                "client_tls_versions": ";".join(f"{x[2]:04x}" for x in client_records[:3]),
                "server_tls_versions": ";".join(f"{x[2]:04x}" for x in server_records[:3]),
                "reassembly_gap_events": flow.streams[client_dir].gaps + flow.streams[server_dir].gaps,
            }
            rows.append(row)
        print(f"[{capture_index}/{len(captures)}] {path.name}: {len(flows)} TCP flows, "
              f"{sum(1 for row in rows if row['capture'] == path.name)} TLS flows", flush=True)
    return rows


def feature_names():
    return [
        "client_tls_record_count", "server_tls_record_count",
        "client_tls_total_bytes", "server_tls_total_bytes",
    ] + [
        f"{direction}_record_len_{index}"
        for direction in ("client", "server") for index in range(16)
    ]


FEATURE_SETS = {
    "directional_volume": [
        "client_tls_record_count", "server_tls_record_count",
        "client_tls_total_bytes", "server_tls_total_bytes",
    ],
    "first_record_lengths": [
        "client_record_len_0", "server_record_len_0",
    ],
    "first_four_record_lengths": [
        f"{direction}_record_len_{index}"
        for direction in ("client", "server") for index in range(4)
    ],
    "volume_plus_sixteen_record_lengths": feature_names(),
}


def add_record_features(row, client_lengths, server_lengths):
    row["client_tls_record_count"] = len(client_lengths)
    row["server_tls_record_count"] = len(server_lengths)
    row["client_tls_total_bytes"] = sum(client_lengths)
    row["server_tls_total_bytes"] = sum(server_lengths)
    for direction, values in (("client", client_lengths), ("server", server_lengths)):
        for index in range(16):
            row[f"{direction}_record_len_{index}"] = values[index] if index < len(values) else 0
    return row


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_grouped_cv(background_rows):
    positive_rows = []
    for run_id in ("rep1", "rep2", "rep3"):
        with (RESULTS_DIR / f"socket_tls_detectability_flows_{run_id}.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            for source in csv.DictReader(stream):
                if source["transport_mode"] != "tls13_tcp" or source["label"] != "fham":
                    continue
                client_lengths = [int(x) for x in source["client_record_lengths"].split(";") if x]
                server_lengths = [int(x) for x in source["server_record_lengths"].split(";") if x]
                row = {
                    "label_fham": 1,
                    "group": f"positive_{run_id}",
                    "message_length": source["message_length"],
                }
                positive_rows.append(add_record_features(row, client_lengths, server_lengths))

    negative_rows = []
    for source in background_rows:
        client_lengths = [int(x) for x in source["client_tls_record_lengths"].split(";") if x]
        server_lengths = [int(x) for x in source["server_tls_record_lengths"].split(";") if x]
        row = {"label_fham": 0, "group": f"background_{source['capture_group']}"}
        negative_rows.append(add_record_features(row, client_lengths, server_lengths))

    rows = positive_rows + negative_rows
    results = []
    background_groups = sorted({row["group"] for row in negative_rows})
    for run_id in ("rep1", "rep2", "rep3"):
        heldout_background = {
            group for index, group in enumerate(background_groups) if index % 3 == (int(run_id[-1]) - 1)
        }
        test = [row for row in rows if row["group"] == f"positive_{run_id}" or row["group"] in heldout_background]
        train = [row for row in rows if row["group"] != f"positive_{run_id}"
                 and row["group"] not in heldout_background]
        y_train = np.asarray([int(row["label_fham"]) for row in train])
        y_test = np.asarray([int(row["label_fham"]) for row in test])
        for feature_set, features in FEATURE_SETS.items():
            x_train = np.asarray([[float(row[key]) for key in features] for row in train])
            x_test = np.asarray([[float(row[key]) for key in features] for row in test])
            model = make_pipeline(
                StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced")
            )
            model.fit(x_train, y_train)
            scores = model.predict_proba(x_test)[:, 1]
            predictions = (scores >= 0.5).astype(int)
            results.append({
                "heldout_positive_run": run_id,
                "feature_set": feature_set,
                "training_positive_runs": ";".join(x for x in ("rep1", "rep2", "rep3") if x != run_id),
                "heldout_background_captures": len(heldout_background),
                "heldout_background_tls_flows": sum(row["label_fham"] == 0 for row in test),
                "heldout_fham_tls_flows": sum(row["label_fham"] == 1 for row in test),
                "auc_fham_positive_orientation": float(roc_auc_score(y_test, scores)),
                "balanced_accuracy_at_0_5": float(balanced_accuracy_score(y_test, predictions)),
            })
    return positive_rows, negative_rows, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", type=Path, default=Path(r"D:\dataset"))
    parser.add_argument(
        "--reuse-extracted", action="store_true",
        help="reuse results/nonvpn_tls_flow_features.csv instead of scanning PCAP files",
    )
    args = parser.parse_args()
    if args.reuse_extracted:
        with (RESULTS_DIR / "nonvpn_tls_flow_features.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            background_rows = list(csv.DictReader(stream))
    else:
        background_rows = extract_tls_flows(args.background)
    positive_rows, negative_rows, cv_rows = run_grouped_cv(background_rows)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(RESULTS_DIR / "nonvpn_tls_flow_features.csv", background_rows)
    with (RESULTS_DIR / "nonvpn_tls_detectability_cv.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cv_rows[0]))
        writer.writeheader()
        writer.writerows(cv_rows)
    print({
        "background_captures": len({row["capture_group"] for row in background_rows}),
        "background_tls_flows": len(background_rows),
        "fham_tls_flows": len(positive_rows),
        "heldout_results": cv_rows,
    })


if __name__ == "__main__":
    main()
