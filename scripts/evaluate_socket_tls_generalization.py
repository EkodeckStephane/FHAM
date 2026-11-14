"""Evaluate held-out-run generalization for the local socket detectability pilot."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fham.config import RESULTS_DIR


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def features_for(rows, feature_names):
    return np.asarray([[float(row[name]) for name in feature_names] for row in rows])


def paired_bootstrap_auc(rows, scores, repetitions=2000):
    labels = np.asarray([int(row["label_fham"]) for row in rows])
    groups = np.asarray([row["pair_id"] for row in rows])
    unique = np.unique(groups)
    index_map = {group: np.flatnonzero(groups == group) for group in unique}
    rng = np.random.default_rng(20261113)
    draws = []
    for _ in range(repetitions):
        picked = rng.choice(unique, size=len(unique), replace=True)
        ix = np.concatenate([index_map[group] for group in picked])
        draws.append(roc_auc_score(labels[ix], scores[ix]))
    low, high = np.percentile(draws, (2.5, 97.5))
    return float(low), float(high)


def main():
    run_ids = ("rep1", "rep2", "rep3")
    rows = []
    for run_id in run_ids:
        batch = read_csv(RESULTS_DIR / f"socket_tls_detectability_flows_{run_id}.csv")
        for row in batch:
            row["run_id"] = run_id
        rows.extend(batch)

    size_features = [
        "client_wire_bytes", "server_wire_bytes", "client_record_count",
        "server_record_count",
    ] + [
        f"{direction}_record_len_{index}"
        for direction in ("client", "server") for index in range(12)
    ]
    relay_features = size_features + [
        "relay_duration_ms", "relay_event_count", "client_read_count",
        "server_read_count", "client_read_max", "server_read_max",
        "client_iat_mean_ms", "client_iat_max_ms",
        "server_iat_mean_ms", "server_iat_max_ms",
    ] + [
        f"{direction}_read_size_{index}"
        for direction in ("client", "server") for index in range(12)
    ]

    output = []
    for mode in ("raw_tcp", "tls13_tcp"):
        mode_rows = [row for row in rows if row["transport_mode"] == mode]
        for heldout in run_ids:
            train = [row for row in mode_rows if row["run_id"] != heldout]
            test = [row for row in mode_rows if row["run_id"] == heldout]
            for feature_set, feature_names in (
                ("sizes_and_records", size_features),
                ("relay_timing_and_chunks", relay_features),
            ):
                model = make_pipeline(
                    StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")
                )
                model.fit(features_for(train, feature_names),
                          np.asarray([int(row["label_fham"]) for row in train]))
                scores = model.predict_proba(features_for(test, feature_names))[:, 1]
                labels = np.asarray([int(row["label_fham"]) for row in test])
                raw_auc = float(roc_auc_score(labels, scores))
                low, high = paired_bootstrap_auc(test, scores)
                output.append({
                    "transport_mode": mode,
                    "feature_set": feature_set,
                    "heldout_run": heldout,
                    "training_runs": ";".join(run for run in run_ids if run != heldout),
                    "test_pairs": len({row["pair_id"] for row in test}),
                    "auc_raw_positive_orientation": raw_auc,
                    "paired_bootstrap_95_low": low,
                    "paired_bootstrap_95_high": high,
                })

    write_csv(RESULTS_DIR / "socket_tls_generalization.csv", output)
    for mode in ("raw_tcp", "tls13_tcp"):
        for feature_set in ("sizes_and_records", "relay_timing_and_chunks"):
            subset = [r for r in output if r["transport_mode"] == mode and r["feature_set"] == feature_set]
            vals = [float(r["auc_raw_positive_orientation"]) for r in subset]
            print(mode, feature_set, "held-out AUCs", [round(v, 3) for v in vals],
                  "mean", round(float(np.mean(vals)), 3))


if __name__ == "__main__":
    main()
