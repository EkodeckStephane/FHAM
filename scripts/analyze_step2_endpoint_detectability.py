#!/usr/bin/env python3
"""Secondary endpoint-visible detectability analysis for Step 2.

This is explicitly not packet-capture analysis: it uses measured TCP socket
write/read chunks and TLS record lengths at the communicating endpoints.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "results/step2/detection/full_capture"
OUT = ROOT / "results/step2/detection"


def _features(row):
    m = json.loads(row.client_endpoint_metrics)
    tx = m["client_or_peer_tx_calls"]
    rx = m["client_or_peer_rx_calls"]
    tx_sizes = [int(x["bytes"]) for x in tx]
    rx_sizes = [int(x["bytes"]) for x in rx]
    tx_times = [int(x["time_ns"]) for x in tx]
    rx_times = [int(x["time_ns"]) for x in rx]
    tls_tx = [int(x["record_bytes"]) for x in m["tls_tx_records"]]
    tls_rx = [int(x["record_bytes"]) for x in m["tls_rx_records"]]
    tls_tx_ct = [int(x["content_type"]) for x in m["tls_tx_records"]]
    tls_rx_ct = [int(x["content_type"]) for x in m["tls_rx_records"]]
    values = {
        "tx_bytes": m["tx_wire_bytes"], "rx_bytes": m["rx_wire_bytes"],
        "total_bytes": m["tx_wire_bytes"] + m["rx_wire_bytes"],
        "tx_plain_bytes": m["tx_plain_bytes"], "rx_plain_bytes": m["rx_plain_bytes"],
        "tx_calls": len(tx), "rx_calls": len(rx),
        "tx_call_mean": float(np.mean(tx_sizes)) if tx_sizes else 0.0,
        "tx_call_std": float(np.std(tx_sizes)) if tx_sizes else 0.0,
        "rx_call_mean": float(np.mean(rx_sizes)) if rx_sizes else 0.0,
        "rx_call_std": float(np.std(rx_sizes)) if rx_sizes else 0.0,
        "tx_iat_mean_ms": float(np.mean(np.diff(tx_times)) / 1e6) if len(tx_times) > 1 else 0.0,
        "rx_iat_mean_ms": float(np.mean(np.diff(rx_times)) / 1e6) if len(rx_times) > 1 else 0.0,
        "tls_tx_count": len(tls_tx), "tls_rx_count": len(tls_rx),
        "tls_tx_ct22": sum(x == 22 for x in tls_tx_ct),
        "tls_tx_ct23": sum(x == 23 for x in tls_tx_ct),
        "tls_rx_ct22": sum(x == 22 for x in tls_rx_ct),
        "tls_rx_ct23": sum(x == 23 for x in tls_rx_ct),
        "marker_FHAM_tx": int(m["marker_FHAM_tx"]),
    }
    for direction, sizes in (("tx_call", tx_sizes), ("rx_call", rx_sizes),
                             ("tls_tx", tls_tx), ("tls_rx", tls_rx)):
        for i in range(10):
            values[f"{direction}_{i}"] = sizes[i] if i < len(sizes) else 0
    return values


def main():
    flows = pd.read_csv(CAPTURE / "session_flow_manifest.csv", keep_default_na=False)
    flows["features"] = flows.apply(_features, axis=1)
    feature_names = list(flows.features.iloc[0])
    feature_frame = pd.DataFrame(flows.features.tolist(), columns=feature_names)
    flows = pd.concat([flows.drop(columns="features"), feature_frame], axis=1)
    models = {
        "volume_only": None,
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=20261121)),
        "random_forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                                class_weight="balanced", random_state=20261121,
                                                n_jobs=1),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08,
                                                                 max_leaf_nodes=15, l2_regularization=1.0,
                                                                 random_state=20261121),
    }
    rows, predictions = [], []
    for condition, frame in flows.groupby("condition", sort=True):
        frame = frame.reset_index(drop=True)
        y = (frame.label == "positive").astype(int).to_numpy()
        splits = frame.split.to_numpy()
        # Only expose features observable on the wire. Raw TCP exposes the
        # application magic and directional byte totals. TLS uses record
        # lengths/counts and directional totals; socket syscall chunking and
        # endpoint timings are excluded because they are not packet features.
        if frame.transport.iloc[0] == "TCP":
            used_features = ["marker_FHAM_tx", "tx_bytes", "rx_bytes"]
        else:
            used_features = ["tx_bytes", "rx_bytes", "tls_tx_count", "tls_rx_count",
                             "tls_tx_ct22", "tls_tx_ct23", "tls_rx_ct22", "tls_rx_ct23"]
            used_features += [f"tls_tx_{i}" for i in range(10)]
            used_features += [f"tls_rx_{i}" for i in range(10)]
        x = frame[used_features].to_numpy(dtype=float)
        idx = {s: np.flatnonzero(splits == s) for s in ("train", "validation", "test")}
        aucs = {}
        fitted = {}
        for name, model in models.items():
            if model is None:
                score = frame.total_bytes.to_numpy(dtype=float)
                # The sign is oriented using train only.
                train_idx = idx["train"]
                if np.mean(score[train_idx][y[train_idx] == 1]) < np.mean(score[train_idx][y[train_idx] == 0]):
                    score = -score
                aucs[name] = roc_auc_score(y[idx["validation"]], score[idx["validation"]])
                fitted[name] = (None, score)
            else:
                model.fit(x[idx["train"]], y[idx["train"]])
                score = model.predict_proba(x)[:, 1]
                aucs[name] = roc_auc_score(y[idx["validation"]], score[idx["validation"]])
                fitted[name] = (model, score)
        chosen = max(aucs, key=aucs.get)
        model, score = fitted[chosen]
        test = idx["test"]
        auc = float(roc_auc_score(y[test], score[test]))
        val_fpr, val_tpr, val_thresholds = roc_curve(y[idx["validation"]], score[idx["validation"]])
        threshold_index = int(np.argmax(val_tpr - val_fpr))
        threshold = float(val_thresholds[threshold_index])
        bal_acc = float(balanced_accuracy_score(y[test], score[test] >= threshold))
        fpr, tpr, _ = roc_curve(y[test], score[test])
        eligible = np.flatnonzero(fpr <= 0.01)
        tpr_at_1 = float(tpr[eligible[-1]]) if len(eligible) else 0.0
        # Cluster bootstrap by base session (positive/control pair), sampled within test.
        test_groups = frame.iloc[test].base_session_id.to_numpy()
        uniq = np.unique(test_groups)
        rng = np.random.default_rng(20261121)
        boot = np.empty(10_000)
        for b in range(len(boot)):
            sampled = rng.choice(uniq, len(uniq), replace=True)
            counts = pd.Series(sampled).value_counts().to_dict()
            weights = np.array([counts.get(g, 0) for g in test_groups])
            boot[b] = roc_auc_score(y[test], score[test], sample_weight=weights)
        rows.append({"condition": condition, "observation_scope": "wire-visible application marker and byte totals" if frame.transport.iloc[0] == "TCP" else "wire-visible TLS 1.3 record lengths and byte totals",
                     "features_used": ";".join(used_features),
                     "train_sessions": len(idx["train"]) // 2,
                     "validation_sessions": len(idx["validation"]) // 2,
                     "test_sessions": len(idx["test"]) // 2,
                     "selected_model": chosen,
                     "validation_auc_selected": float(aucs[chosen]),
                     "test_auc": auc, "test_auc_cluster_ci_low": float(np.quantile(boot, .025)),
                     "test_auc_cluster_ci_high": float(np.quantile(boot, .975)),
                     "decision_threshold_from_validation": threshold,
                     "test_balanced_accuracy_at_validation_threshold": bal_acc,
                     "test_tpr_at_fpr_1pct": tpr_at_1,
                     "validation_auc_by_model": json.dumps(aucs, sort_keys=True)})
        per = frame.iloc[test][["condition", "base_session_id", "label", "split"]].copy()
        per["score"] = score[test]
        predictions.append(per)
    pd.DataFrame(rows).to_csv(OUT / "endpoint_detectability_summary.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_csv(OUT / "endpoint_detectability_test_predictions.csv", index=False)
    metadata = {"scope": "supplementary endpoint-visible analysis, not pcap/network packet capture",
                "source": str(CAPTURE / "session_flow_manifest.csv"),
                "features_parsed_at_endpoints": feature_names,
                "classifier_feature_policy": "TCP: visible FHAM frame marker and directional byte counts. TLS 1.3: record lengths/counts and byte totals only; endpoint syscall chunking/timing excluded.",
                "split": "frozen grouped train/validation/test sessions; model selected on validation, evaluated once on test",
                "bootstrap": "10,000 pair-cluster resamples on held-out test sessions, seed 20261121"}
    (OUT / "endpoint_detectability_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
