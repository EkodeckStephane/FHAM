#!/usr/bin/env python3
"""Compare real Step-2 TLS 1.3 FHAM flows with the archived NonVPN TLS corpus.

Uses only externally observable directional TLS record lengths/counts and total
bytes. The reference corpus is capture-group split; this remains secondary
because the archive and FHAM runs differ in capture era and environment.
"""
from __future__ import annotations

import hashlib
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
BACKGROUND = ROOT / "results/nonvpn_tls_flow_features.csv"
OUT = ROOT / "results/step2/detection"
SEED = 20261121


def _lengths(value):
    if value is None or (isinstance(value, float) and np.isnan(value)) or value == "":
        return []
    return [int(v) for v in str(value).split(";") if v]


def _feature_row(tx, rx):
    row = {"tx_count": len(tx), "rx_count": len(rx),
           "tx_total": sum(tx), "rx_total": sum(rx)}
    for direction, values in (("tx", tx), ("rx", rx)):
        for i in range(16):
            row[f"{direction}_record_{i}"] = values[i] if i < len(values) else 0
    return row


def _model_candidates():
    return {
        "volume_only": None,
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=SEED)),
        "random_forest": RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                                                class_weight="balanced", random_state=SEED, n_jobs=1),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08,
                                                                 max_leaf_nodes=15, l2_regularization=1.0,
                                                                 random_state=SEED),
    }


def _bootstrap_auc(y, score, pos_groups, neg_groups, reps=10_000):
    rng = np.random.default_rng(SEED)
    positive = np.flatnonzero(y == 1)
    negative = np.flatnonzero(y == 0)
    p_groups = np.unique(pos_groups[positive])
    n_groups = np.unique(neg_groups[negative])
    output = np.empty(reps)
    for b in range(reps):
        pg = rng.choice(p_groups, len(p_groups), replace=True)
        ng = rng.choice(n_groups, len(n_groups), replace=True)
        pc = pd.Series(pg).value_counts().to_dict()
        nc = pd.Series(ng).value_counts().to_dict()
        weights = np.zeros(len(y), dtype=float)
        for i in positive:
            weights[i] = pc.get(pos_groups[i], 0)
        for i in negative:
            weights[i] = nc.get(neg_groups[i], 0)
        output[b] = roc_auc_score(y, score, sample_weight=weights)
    return float(np.quantile(output, .025)), float(np.quantile(output, .975))


def main():
    background = pd.read_csv(BACKGROUND, keep_default_na=False)
    # Split reference captures deterministically before looking at labels/features.
    captures = sorted(background.capture_group.unique(),
                      key=lambda name: hashlib.sha256(("FHAM-step2-ref|" + name).encode()).hexdigest())
    n = len(captures)
    cut_train, cut_val = int(np.floor(.70*n)), int(np.floor(.85*n))
    group_split = {name: ("train" if i < cut_train else "validation" if i < cut_val else "test")
                   for i, name in enumerate(captures)}
    bg_rows = []
    for r in background.itertuples(index=False):
        features = _feature_row(_lengths(r.client_tls_record_lengths),
                                _lengths(r.server_tls_record_lengths))
        bg_rows.append({**features, "label": 0, "split": group_split[r.capture_group],
                        "cluster": "ref:" + str(r.capture_group), "source": "NonVPN-PCAP",
                        "capture_group": r.capture_group})

    fham = pd.read_csv(CAPTURE / "session_flow_manifest.csv", keep_default_na=False)
    fham = fham[(fham.transport == "TLS13") & (fham.label == "positive")].copy()
    fham_rows = []
    for r in fham.itertuples(index=False):
        metrics = json.loads(r.client_endpoint_metrics)
        tx = [int(x["record_bytes"]) for x in metrics["tls_tx_records"]]
        rx = [int(x["record_bytes"]) for x in metrics["tls_rx_records"]]
        features = _feature_row(tx, rx)
        fham_rows.append({**features, "label": 1, "split": r.split,
                          "cluster": "fham:" + str(r.base_session_id), "source": "FHAM-V1",
                          "capture_group": "FHAM-V1"})

    data = pd.DataFrame(bg_rows + fham_rows)
    feature_names = ["tx_count", "rx_count", "tx_total", "rx_total"] + [
        f"{d}_record_{i}" for d in ("tx", "rx") for i in range(16)]
    models = _model_candidates()
    results, predictions = [], []
    for mode in ("R0", "R1"):
        fham_condition = fham[fham["mode"] == mode].copy().reset_index(drop=True)
        pos = []
        for r in fham_condition.itertuples(index=False):
            m = json.loads(r.client_endpoint_metrics)
            pos.append(_feature_row([int(x["record_bytes"]) for x in m["tls_tx_records"]],
                                    [int(x["record_bytes"]) for x in m["tls_rx_records"]]))
        pos = pd.DataFrame(pos)
        pos["label"] = 1
        pos["split"] = fham_condition.split.to_numpy()
        pos["cluster"] = ["fham:" + str(x) for x in fham_condition.base_session_id]
        pos["capture_group"] = "FHAM-V1"
        neg = data[(data.label == 0)].copy()
        frame = pd.concat([pos, neg], ignore_index=True)
        y = frame.label.to_numpy(dtype=int)
        split = frame.split.to_numpy()
        x = frame[feature_names].to_numpy(dtype=float)
        ix = {s: np.flatnonzero(split == s) for s in ("train", "validation", "test")}
        val_auc = {}
        fitted = {}
        for name, model in models.items():
            if model is None:
                score = frame.tx_total.to_numpy(dtype=float) + frame.rx_total.to_numpy(dtype=float)
                ti = ix["train"]
                if np.mean(score[ti][y[ti] == 1]) < np.mean(score[ti][y[ti] == 0]):
                    score = -score
                val_auc[name] = roc_auc_score(y[ix["validation"]], score[ix["validation"]])
                fitted[name] = (None, score)
            else:
                model.fit(x[ix["train"]], y[ix["train"]])
                score = model.predict_proba(x)[:, 1]
                val_auc[name] = roc_auc_score(y[ix["validation"]], score[ix["validation"]])
                fitted[name] = (model, score)
        chosen = max(val_auc, key=val_auc.get)
        score = fitted[chosen][1]
        ti = ix["test"]
        y_test, score_test = y[ti], score[ti]
        low, high = _bootstrap_auc(y_test, score_test,
                                   frame.cluster.to_numpy()[ti], frame.cluster.to_numpy()[ti])
        val_fpr, val_tpr, val_thresholds = roc_curve(y[ix["validation"]], score[ix["validation"]])
        threshold_index = int(np.argmax(val_tpr - val_fpr))
        threshold = float(val_thresholds[threshold_index])
        fpr, tpr, _ = roc_curve(y_test, score_test)
        allowed = np.flatnonzero(fpr <= .01)
        results.append({"mode": mode, "reference_flows": int((neg.split == "test").sum()),
                        "reference_capture_groups": len(set(neg.loc[neg.split == "test", "capture_group"])),
                        "fham_train": int((pos.split == "train").sum()),
                        "fham_validation": int((pos.split == "validation").sum()),
                        "fham_test": int((pos.split == "test").sum()),
                        "selected_model": chosen, "validation_auc": float(val_auc[chosen]),
                        "test_auc": float(roc_auc_score(y_test, score_test)),
                        "test_auc_cluster_bootstrap_low": low,
                        "test_auc_cluster_bootstrap_high": high,
                        "decision_threshold_from_validation": threshold,
                        "test_balanced_accuracy_at_validation_threshold": float(balanced_accuracy_score(y_test, score_test >= threshold)),
                        "test_tpr_at_fpr_le_1pct": float(tpr[allowed[-1]]) if len(allowed) else 0.0,
                        "validation_auc_by_model": json.dumps(val_auc, sort_keys=True)})
        selected = frame.iloc[ti][["label", "split", "cluster", "capture_group"]].copy()
        selected["mode"] = mode
        selected["score"] = score_test
        predictions.append(selected)
    pd.DataFrame(results).to_csv(OUT / "tls_reference_detectability_summary.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_csv(OUT / "tls_reference_detectability_test_predictions.csv", index=False)
    metadata = {"scope": "external NonVPN reference; distinct from paired synthetic controls",
                "background_features_csv_sha256": hashlib.sha256(BACKGROUND.read_bytes()).hexdigest(),
                "background_rows": len(background), "background_captures": len(captures),
                "capture_group_split_counts": {s: int(sum(v == s for v in group_split.values()))
                                               for s in ("train", "validation", "test")},
                "split_rule": "capture names ordered by SHA256('FHAM-step2-ref|'+name); 70/15/15 capture groups",
                "fham_source": str(CAPTURE / "session_flow_manifest.csv"),
                "features": feature_names,
                "limitations": ["reference capture era and traffic applications differ from the local FHAM run",
                                "background metadata are an existing extraction; archive mapping audited separately",
                                "no live packet capture of the FHAM loopback flows was available"]}
    (OUT / "tls_reference_detectability_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(pd.DataFrame(results).to_string(index=False))


if __name__ == "__main__":
    main()
