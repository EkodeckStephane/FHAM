"""Cluster-bootstrap receiver-side erasure and registration results."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stability_step1"
SEED = 20261116
DRAWS = 10000


def pooled_rmax(frame: pd.DataFrame) -> float:
    denominator = frame["symbols"].sum()
    if denominator == 0:
        return float("nan")
    f = frame["flagged"].sum() / denominator
    s = frame["silent_errors"].sum() / denominator
    return float(1 - f - 2 * s)


def main():
    raw = pd.read_csv(OUT / "receiver_validation_raw.csv.gz")
    raw["class"] = np.where(
        raw["transform"].isin(["rotate1", "crop5", "resize0.8"]),
        "geometric", "photometric",
    )
    keys = ["cover", "z_flag", "class", "transform", "path"]
    cover = raw.groupby(keys, as_index=False, dropna=False).agg(
        symbols=("symbols", "sum"),
        correct=("correct", "sum"),
        flagged=("flagged", "sum"),
        flagged_wrong=("flagged_wrong", "sum"),
        silent_errors=("silent_errors", "sum"),
        exact_messages=("exact", "sum"),
        source_exact_messages=("source_exact", "sum"),
        registration_success_rate=("registration_success", "mean"),
    )
    cover["accuracy"] = cover["correct"] / cover["symbols"].replace(0, np.nan)
    rng = np.random.default_rng(SEED)
    summaries = []
    cis = []
    group_keys = ["z_flag", "class", "transform", "path"]
    for group_key, frame in cover.groupby(group_keys, dropna=False):
        symbols = frame["symbols"].sum()
        row = dict(zip(group_keys, group_key))
        row.update({
            "covers": int(frame.cover.nunique()),
            "symbols": int(symbols),
            "correct": int(frame.correct.sum()),
            "flagged": int(frame.flagged.sum()),
            "flagged_wrong": int(frame.flagged_wrong.sum()),
            "silent_errors": int(frame.silent_errors.sum()),
            "exact_messages": int(frame.exact_messages.sum()),
            "source_exact_messages": int(frame.source_exact_messages.sum()),
            "registration_success_rate": float(frame.registration_success_rate.mean()),
            "accuracy": float(frame.correct.sum() / symbols) if symbols else float("nan"),
            "f": float(frame.flagged.sum() / symbols) if symbols else float("nan"),
            "s": float(frame.silent_errors.sum() / symbols) if symbols else float("nan"),
            "R_max": pooled_rmax(frame),
        })
        summaries.append(row)
        indices = rng.integers(0, len(frame), size=(DRAWS, len(frame)))
        arr = frame[["symbols", "flagged", "silent_errors"]].to_numpy(dtype=np.float64)
        sampled = arr[indices].sum(axis=1)
        den = sampled[:, 0]
        values = np.where(den > 0, 1 - sampled[:, 1] / den - 2 * sampled[:, 2] / den,
                          np.nan)
        cis.append({
            **dict(zip(group_keys, group_key)),
            "R_max": row["R_max"],
            "ci95_low": float(np.nanpercentile(values, 2.5)),
            "ci95_high": float(np.nanpercentile(values, 97.5)),
            "bootstrap_draws": DRAWS,
            "unit": "cover cluster",
        })
    summary = pd.DataFrame(summaries)
    ci = pd.DataFrame(cis)
    summary.to_csv(OUT / "receiver_validation_detailed_summary.csv", index=False)
    ci.to_csv(OUT / "receiver_validation_rmax_cluster_ci.csv", index=False)
    chosen = float(json.loads((OUT / "receiver_validation_selection.json").read_text(
        encoding="utf-8"))["chosen_z_flag"])
    chosen_rows = summary[summary.z_flag == chosen]
    print(f"selected z_flag={chosen:g}")
    print(chosen_rows[["class", "transform", "path", "accuracy", "f", "s",
                       "R_max", "registration_success_rate"]].to_string(index=False))
    print(ci[ci.z_flag == chosen][["class", "transform", "path", "ci95_low",
                                  "ci95_high"]].to_string(index=False))


if __name__ == "__main__":
    main()
