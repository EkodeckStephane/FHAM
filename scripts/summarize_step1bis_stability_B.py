"""Summarize frozen Step 1bis F2 B results and evaluate G-A1/G-A2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1bis" / "stability_F2"
TRANSFORMS = ("jpeg75", "noise2", "rotate1", "crop5", "resize0.8")
BOOTSTRAPS = 10000
SEED = 20261117


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def boot_ci(values, rng):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    picks = rng.integers(0, len(x), size=(BOOTSTRAPS, len(x)))
    means = x[picks].mean(axis=1)
    return float(x.mean()), float(np.quantile(means, .025)), float(np.quantile(means, .975))


def main():
    bdir = BASE / "B"
    assignment_files = sorted(bdir.glob("*_assignments.csv.gz"))
    recovery_files = sorted(bdir.glob("*_recovery.csv.gz"))
    feasibility_files = sorted(bdir.glob("*_feasibility.csv.gz"))
    if not (len(assignment_files) == len(recovery_files) == len(feasibility_files) == 200):
        raise RuntimeError(f"Expected 200 complete B covers, got {len(assignment_files)}, "
                           f"{len(recovery_files)}, {len(feasibility_files)}")
    assignments = pd.concat((pd.read_csv(p) for p in assignment_files), ignore_index=True)
    recovery = pd.concat((pd.read_csv(p) for p in recovery_files), ignore_index=True)
    feasibility = pd.concat((pd.read_csv(p) for p in feasibility_files), ignore_index=True)
    assignments.to_csv(BASE / "B_raw_assignments.csv.gz", index=False, compression="gzip")
    recovery.to_csv(BASE / "B_raw_recovery.csv.gz", index=False, compression="gzip")
    feasibility.to_csv(BASE / "B_raw_feasibility.csv.gz", index=False, compression="gzip")
    keys = ["cover", "method", "lambda", "filter_q"]
    p3 = recovery[(recovery["path"] == "P3") & recovery["transform"].isin(TRANSFORMS)]
    cover_transform = p3.groupby(keys + ["transform"], dropna=False, as_index=False).accuracy.mean()
    cover_scores = cover_transform.groupby(keys, dropna=False, as_index=False).accuracy.mean()
    cover_scores = cover_scores.rename(columns={"accuracy": "p3_macro_accuracy"})
    feas100 = (feasibility[feasibility.source_length.eq(100)]
               .groupby(keys, dropna=False, as_index=False).feasible.mean()
               .rename(columns={"feasible": "feasibility_100"}))
    d1 = assignments.groupby(keys, dropna=False, as_index=False).D1.mean()
    metrics = cover_scores.merge(feas100, on=keys).merge(d1, on=keys)

    rng = np.random.default_rng(SEED)
    rows = []
    for (method, lam, q, transform), group in cover_transform.groupby(
            ["method", "lambda", "filter_q", "transform"], dropna=False):
        mean, low, high = boot_ci(group.accuracy, rng)
        rows.append({"method": method, "lambda": lam, "filter_q": q,
                     "transform": transform, "covers": group.cover.nunique(),
                     "mean_p3_accuracy": mean, "ci95_low": low, "ci95_high": high})
    transform_summary = pd.DataFrame(rows)
    summary = metrics.groupby(["method", "lambda", "filter_q"], dropna=False).agg(
        covers=("cover", "nunique"), p3_macro_mean=("p3_macro_accuracy", "mean"),
        p3_macro_sd=("p3_macro_accuracy", "std"), feasibility_100=("feasibility_100", "mean"),
        mean_D1=("D1", "mean")).reset_index()
    summary["p3_se"] = summary.p3_macro_sd / np.sqrt(summary.covers)
    summary.to_csv(BASE / "B_configuration_summary.csv", index=False)
    transform_summary.to_csv(BASE / "B_transform_summary.csv", index=False)
    metrics.to_csv(BASE / "B_cover_configuration_metrics.csv", index=False)
    cover_transform.to_csv(BASE / "B_cover_transform_metrics.csv", index=False)
    all_paths = recovery.groupby(["method", "lambda", "filter_q", "cover", "transform", "path"], dropna=False,
                                as_index=False).agg(
        accuracy=("accuracy", "mean"), exact_rate=("exact", "mean"))
    path_summary = all_paths.groupby(["method", "lambda", "filter_q", "transform", "path"],
                                     dropna=False, as_index=False).agg(
        covers=("cover", "nunique"), mean_accuracy=("accuracy", "mean"),
        mean_exact_rate=("exact_rate", "mean"))
    path_summary.to_csv(BASE / "B_all_path_summary.csv", index=False)
    family_summary = recovery.groupby(["method", "lambda", "filter_q", "cover", "family", "source_length",
                                       "transform", "path"], dropna=False,
                                     as_index=False).agg(
        accuracy=("accuracy", "mean"), exact_rate=("exact", "mean"))
    family_summary = family_summary.groupby(["method", "lambda", "filter_q", "family",
                                              "source_length", "transform", "path"],
                                             dropna=False, as_index=False).agg(
        covers=("cover", "nunique"), mean_accuracy=("accuracy", "mean"),
        mean_exact_rate=("exact_rate", "mean"))
    family_summary.to_csv(BASE / "B_family_path_summary.csv", index=False)

    # G-A1 uses image-cover clusters, 100-byte source feasibility, and oracle P3.
    gate_rows = []
    for (method, lam, q), cfg in metrics.groupby(["method", "lambda", "filter_q"], dropna=False):
        for attack in ("jpeg75", "noise2"):
            vals = cover_transform[(cover_transform.method == method)
                                   & (cover_transform["lambda"].fillna(-9) == (-9 if pd.isna(lam) else lam))
                                   & (cover_transform.filter_q.fillna(-9) == (-9 if pd.isna(q) else q))
                                   & (cover_transform["transform"] == attack)].set_index("cover").accuracy
            mean, low, high = boot_ci(vals, rng)
            feasible = float(cfg.feasibility_100.mean())
            gate_rows.append({"method": method, "lambda": lam, "filter_q": q,
                              "transform": attack, "a_P3": mean, "ci95_low": low,
                              "ci95_high": high, "feasibility_100": feasible,
                              "G_A1_cell_green": bool(mean >= .95 and low >= .92 and feasible >= .95)})
    gate = pd.DataFrame(gate_rows)
    gate.to_csv(BASE / "B_G_A1_cells.csv", index=False)
    complete = gate.groupby(["method", "lambda", "filter_q"], dropna=False).agg(
        both_attack_means=("a_P3", "min"),
        both_attack_lower_ci=("ci95_low", "min"),
        feasibility_100=("feasibility_100", "first"),
        both_attack_cells_green=("G_A1_cell_green", "all")).reset_index()
    complete.to_csv(BASE / "B_G_A1_configurations.csv", index=False)
    g1 = bool(complete.both_attack_cells_green.any())

    # Paired B-minus-S0 cluster bootstrap for every F2 method under rotation/crop.
    s0 = cover_transform[cover_transform.method.eq("S0")].pivot(
        index="cover", columns="transform", values="accuracy")
    delta_rows = []
    for (method, lam, q), group in cover_transform[~cover_transform.method.eq("S0")].groupby(
            ["method", "lambda", "filter_q"], dropna=False):
        mat = group.pivot(index="cover", columns="transform", values="accuracy")
        common = mat.index.intersection(s0.index)
        for attack in ("rotate1", "crop5"):
            delta = mat.loc[common, attack] - s0.loc[common, attack]
            mean, low, high = boot_ci(delta, rng)
            delta_rows.append({"method": method, "lambda": lam, "filter_q": q,
                               "transform": attack, "covers": len(common),
                               "delta_vs_S0": mean, "ci95_low": low, "ci95_high": high,
                               "positive_strict_ci": bool(low > 0)})
    delta = pd.DataFrame(delta_rows)
    delta.to_csv(BASE / "B_G_A2_paired_deltas.csv", index=False)
    g2 = bool(delta.positive_strict_ci.any())

    g1_verdict = "green" if g1 else (
        "orange" if complete.both_attack_means.max() >= .90 else "red")
    provenance = {
        "stage": "BOWS2-B frozen F2 reevaluation", "covers": 200,
        "configurations": json.loads((BASE / "frozen_selection_A.json").read_text(encoding="utf-8"))["stage_B_configurations"],
        "cluster_unit": "cover", "bootstrap_replicates": BOOTSTRAPS,
        "bootstrap_seed": SEED, "p3_transforms": TRANSFORMS,
        "G_A1": {"verdict": g1_verdict, "green": g1,
                 "criterion": "same frozen configuration has a_P3>=0.95 and lower cluster-bootstrap 95% CI>=0.92 for both JPEG75 and noise2, with feasibility>=0.95 at 100-byte source"},
        "G_A2": {"positive_rotation_or_crop_delta_with_strict_95pct_CI": g2,
                 "criterion": "paired cover-level P3 accuracy difference from S0 has a strictly positive 95% bootstrap CI under rotation or crop"},
        "BOWS2_C_pixels_opened": False,
        "raw_assignment_files_sha256": {p.name: sha(p) for p in assignment_files},
        "raw_recovery_files_sha256": {p.name: sha(p) for p in recovery_files},
        "raw_feasibility_files_sha256": {p.name: sha(p) for p in feasibility_files},
    }
    (BASE / "B_gate_verdict.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print("G-A1 cell estimates:")
    print(gate.to_string(index=False))
    print("\nG-A1 configuration verdicts:")
    print(complete.to_string(index=False))
    print(f"\nG-A1={g1_verdict}; G-A2 positive under rotation/crop={g2}")
    print("\nPaired deltas:")
    print(delta.to_string(index=False))


if __name__ == "__main__":
    main()
