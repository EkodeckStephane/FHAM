"""Summarize F2 A and freeze the preregistered configuration selection for B."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1bis" / "stability_F2"
TRANSFORMS = ("jpeg75", "noise2", "rotate1", "crop5", "resize0.8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    a_dir = BASE / "A"
    assignment_files = sorted(a_dir.glob("*_assignments.csv.gz"))
    recovery_files = sorted(a_dir.glob("*_recovery.csv.gz"))
    feasibility_files = sorted(a_dir.glob("*_feasibility.csv.gz"))
    if not (len(assignment_files) == len(recovery_files) == len(feasibility_files) == 100):
        raise RuntimeError(f"Expected 100 complete A covers; found {len(assignment_files)} assignments, "
                           f"{len(recovery_files)} recovery, {len(feasibility_files)} feasibility")
    assignments = pd.concat((pd.read_csv(p) for p in assignment_files), ignore_index=True)
    recovery = pd.concat((pd.read_csv(p) for p in recovery_files), ignore_index=True)
    feasibility = pd.concat((pd.read_csv(p) for p in feasibility_files), ignore_index=True)

    p3 = recovery[(recovery["path"] == "P3") & recovery["transform"].isin(TRANSFORMS)].copy()
    cover_transform = p3.groupby(["cover", "method", "lambda", "filter_q", "transform"],
                                 dropna=False, as_index=False).accuracy.mean()
    scores = cover_transform.groupby(["cover", "method", "lambda", "filter_q"],
                                     dropna=False, as_index=False).accuracy.mean()
    scores = scores.rename(columns={"accuracy": "p3_macro_accuracy"})
    feas100 = (feasibility[feasibility.source_length.eq(100)]
               .groupby(["cover", "method", "lambda", "filter_q"], dropna=False,
                        as_index=False).feasible.mean()
               .rename(columns={"feasible": "feasibility_100"}))
    d1 = (assignments.groupby(["cover", "method", "lambda", "filter_q"], dropna=False,
                              as_index=False).D1.mean())
    metrics = scores.merge(feas100, on=["cover", "method", "lambda", "filter_q"])
    metrics = metrics.merge(d1, on=["cover", "method", "lambda", "filter_q"])
    summary = metrics.groupby(["method", "lambda", "filter_q"], dropna=False).agg(
        covers=("cover", "nunique"), p3_macro_mean=("p3_macro_accuracy", "mean"),
        p3_macro_sd=("p3_macro_accuracy", "std"),
        feasibility_100=("feasibility_100", "mean"), mean_D1=("D1", "mean")
    ).reset_index()
    summary["p3_se"] = summary.p3_macro_sd / np.sqrt(summary.covers)
    s0 = summary[summary.method.eq("S0")].iloc[0]
    summary["D1_ratio_to_S0"] = summary.mean_D1 / s0.mean_D1
    summary["eligible"] = (summary.feasibility_100.ge(.95)
                           & summary.D1_ratio_to_S0.le(5.0))
    summary = summary.sort_values("p3_macro_mean", ascending=False)
    summary.to_csv(BASE / "A_configuration_summary.csv", index=False)
    metrics.to_csv(BASE / "A_cover_configuration_metrics.csv", index=False)
    cover_transform.to_csv(BASE / "A_cover_transform_metrics.csv", index=False)

    eligible = summary[summary.eligible].copy()
    if len(eligible) == 0:
        raise RuntimeError("No eligible F2 configuration on A; protocol selection rule yields no B run")
    best = eligible.iloc[0]
    within = eligible[eligible.p3_macro_mean.ge(best.p3_macro_mean - best.p3_se)].copy()
    within = within.sort_values(["mean_D1", "p3_macro_mean"], ascending=[True, False])
    remaining = eligible[~eligible.index.isin(within.index)].sort_values("p3_macro_mean", ascending=False)
    ordered = pd.concat([within, remaining], ignore_index=True).head(3)
    selected = []
    for _, item in ordered.iterrows():
        selected.append({"method": item["method"],
                         "lambda": None if pd.isna(item["lambda"]) else float(item["lambda"]),
                         "filter_q": None if pd.isna(item["filter_q"]) else float(item["filter_q"]),
                         "A_p3_macro_mean": float(item["p3_macro_mean"]),
                         "A_feasibility_100": float(item["feasibility_100"]),
                         "A_D1": float(item["mean_D1"]),
                         "A_D1_ratio_to_S0": float(item["D1_ratio_to_S0"])})
    if not any(item["method"] == "S0" for item in selected):
        selected.append({"method": "S0", "lambda": 1.0, "filter_q": None,
                         "added_as_control": True})
    provenance = {
        "selection_source": "BOWS2-A exploratory only",
        "profile": 12, "bound": 2, "covers": 100,
        "configurations_ranked": len(summary),
        "rule": "eligibility feasibility>=0.95 at 100-byte source and mean D1<=5x S0; rank by cover-macro mean P3 over five validation transforms; among candidates within one cover-level SE of the best, prioritize lower D1; retain three; add S0 on B if absent",
        "stage_B_configurations": selected,
        "stage_B_includes_S0": any(item["method"] == "S0" for item in selected),
        "A_assignments_sha256": {p.name: sha(p) for p in assignment_files},
        "A_recovery_sha256": {p.name: sha(p) for p in recovery_files},
        "A_feasibility_sha256": {p.name: sha(p) for p in feasibility_files},
        "summary_sha256": sha(BASE / "A_configuration_summary.csv"),
        "selection_script_sha256": sha(Path(__file__)),
        "frozen_utc_note": "selection frozen after A and before B; local timestamp recorded by git commit",
        "BOWS2_C_pixels_opened": False,
    }
    (BASE / "frozen_selection_A.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(summary[["method", "lambda", "filter_q", "p3_macro_mean", "p3_se",
                   "feasibility_100", "mean_D1", "D1_ratio_to_S0", "eligible"]].to_string(index=False))
    print("\nFrozen B configurations:")
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()
