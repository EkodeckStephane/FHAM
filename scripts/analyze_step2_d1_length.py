#!/usr/bin/env python3
"""D-1 grouped length leakage analysis for the frozen 8,000 D-msg records."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/step2/detection"
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")
N_BOOT = 10000
SEED = 20261121


def _mi_from_table(table):
    pxy = table / table.sum()
    px = pxy.sum(axis=0)
    py = pxy.sum(axis=1)
    denom = py[:, None] * px[None, :]
    valid = pxy > 0
    return float(np.sum(pxy[valid] * np.log2(pxy[valid] / denom[valid])))


def _cluster_bootstrap(data, length_column):
    grouped = data.groupby(["family", "sha256", length_column], as_index=False).size()
    length_values = sorted(grouped[length_column].unique().tolist())
    value_index = {value: i for i, value in enumerate(length_values)}
    tables = {}
    for family in FAMILIES:
        rows = grouped[grouped.family == family]
        tables[family] = (rows[length_column].map(value_index).to_numpy(),
                          rows["size"].to_numpy(dtype=np.int64))
    rng = np.random.default_rng(SEED)
    mi_samples = np.empty(N_BOOT)
    acc_samples = np.empty(N_BOOT)
    for replicate in range(N_BOOT):
        contingency = np.zeros((len(FAMILIES), len(length_values)), dtype=np.float64)
        for family_index, family in enumerate(FAMILIES):
            indices, sizes = tables[family]
            chosen = rng.integers(0, len(indices), len(indices))
            np.add.at(contingency[family_index], indices[chosen], sizes[chosen])
        # Keep the four family priors balanced as in the experiment.
        normalized = contingency / contingency.sum(axis=1, keepdims=True) / len(FAMILIES)
        mi_samples[replicate] = _mi_from_table(normalized)
        acc_samples[replicate] = np.max(normalized, axis=0).sum()
    return {
        "mutual_information_bits": _mi_from_table(
            _balanced_contingency(data, length_column, length_values)),
        "mutual_information_cluster_bootstrap_95": [
            float(np.quantile(mi_samples, .025)), float(np.quantile(mi_samples, .975))],
        "length_only_accuracy_cluster_bootstrap_95": [
            float(np.quantile(acc_samples, .025)), float(np.quantile(acc_samples, .975))],
    }


def _balanced_contingency(data, length_column, length_values):
    table = np.zeros((len(FAMILIES), len(length_values)), dtype=np.float64)
    idx = {v: i for i, v in enumerate(length_values)}
    for fi, family in enumerate(FAMILIES):
        subset = data[data.family == family]
        counts = subset[length_column].value_counts()
        table[fi] = [counts.get(v, 0) / len(subset) / len(FAMILIES)
                     for v in length_values]
    return table


def evaluate(data, mode):
    length_column = f"{mode}_framed_bytes"
    labels = data.family.to_numpy()
    groups = data.sha256.to_numpy()
    features = data[[length_column]].to_numpy(dtype=float)
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    predictions = np.empty(len(data), dtype=object)
    fold_rows = []
    for fold, (train_index, test_index) in enumerate(splitter.split(features, labels, groups), 1):
        model = LogisticRegression(max_iter=2000, class_weight=None, random_state=SEED)
        model.fit(features[train_index], labels[train_index])
        predictions[test_index] = model.predict(features[test_index])
        fold_rows.append({"mode": mode, "fold": fold,
                          "train_records": len(train_index), "test_records": len(test_index),
                          "accuracy": accuracy_score(labels[test_index], predictions[test_index]),
                          "test_unique_hashes": len(set(groups[test_index]))})
    result = {"mode": mode, "records": len(data),
              "accuracy_grouped_5fold": accuracy_score(labels, predictions),
              "chance_accuracy": .25,
              **_cluster_bootstrap(data, length_column)}
    return result, fold_rows


def main():
    data = pd.read_csv(OUT / "dmsg_selected_2000_per_family.csv.gz")
    if len(data) != 8000 or not data.groupby("family").size().eq(2000).all():
        raise RuntimeError("D-1 requires exactly 2,000 retained messages in each family")
    summaries, folds = [], []
    for mode in ("R0", "R1"):
        summary, fold_rows = evaluate(data, mode)
        summaries.append(summary)
        folds.extend(fold_rows)
    pd.DataFrame(summaries).to_csv(OUT / "d1_length_summary.csv", index=False)
    pd.DataFrame(folds).to_csv(OUT / "d1_length_grouped_folds.csv", index=False)
    metadata = {"records_per_family": 2000, "total_records": len(data),
                "grouping": "SHA-256 identical messages stay in one CV fold and bootstrap cluster",
                "seed": SEED, "bootstrap_replicates": N_BOOT,
                "families": list(FAMILIES),
                "R0_length_column": "R0_framed_bytes",
                "R1_length_column": "R1_framed_bytes"}
    (OUT / "d1_length_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    main()
