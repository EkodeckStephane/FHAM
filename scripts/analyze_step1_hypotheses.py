"""Paired cover-cluster analysis of the preregistered H1/H2 contrasts."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stability_step1"
SEED = 20261116
DRAWS = 10000
PERMUTATIONS = 100000


def holm(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p_values) - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def sealed_geometry_diagnostics(rng: np.random.Generator) -> list[dict]:
    raw = pd.read_csv(OUT / "sealed_test_raw.csv.gz")
    geometry = ["rotate_neg1.5", "crop10", "resize0.7",
                "combo_rotate1_jpeg75"]
    grouped = raw[raw["transform"].isin(geometry)].groupby(
        ["corpus", "cover", "transform", "path"], as_index=False
    ).agg(correct=("correct", "sum"), symbols=("symbols", "sum"))
    grouped["accuracy"] = grouped.correct / grouped.symbols
    wide = grouped.pivot(
        index=["corpus", "cover", "transform"], columns="path",
        values="accuracy",
    ).reset_index()
    identity = raw[raw["transform"] == "identity"].groupby(
        ["corpus", "cover"], as_index=False
    ).agg(correct=("correct", "sum"), symbols=("symbols", "sum"))
    identity["P0"] = identity.correct / identity.symbols
    wide = wide.merge(identity[["corpus", "cover", "P0"]],
                      on=["corpus", "cover"], validate="many_to_one")
    rows = []
    for (corpus, transform), group in wide.groupby(["corpus", "transform"]):
        group = group.sort_values("cover")
        for label, left, right in (
            ("P3_minus_P2_recalibration_cost", "P3", "P2"),
            ("P0_minus_P3_transform_loss", "P0", "P3"),
        ):
            delta = (group[left] - group[right]).to_numpy(dtype=float)
            n = len(delta)
            idx = rng.integers(0, n, size=(DRAWS, n))
            boot = delta[idx].mean(axis=1)
            ci = np.quantile(boot, [0.025, 0.975])
            rows.append({
                "corpus": corpus,
                "transform": transform,
                "contrast": label,
                "covers": n,
                "mean_delta": float(delta.mean()),
                "bootstrap_ci95_low": float(ci[0]),
                "bootstrap_ci95_high": float(ci[1]),
                "bootstrap_draws": DRAWS,
                "unit": "cover cluster",
            })
    return rows


def main() -> None:
    recovery = pd.read_csv(OUT / "validation_recovery_raw_p2resize.csv.gz")
    assignment = pd.read_csv(OUT / "validation_assignment_summary_p2resize.csv")
    recovery = recovery[
        recovery["method"].isin(["S1", "S2", "S3"])
        & (recovery["lambda"] == 0.5)
        & recovery["transform"].isin(["rotate1", "crop5"])
        & (recovery["path"] == "P2")
    ]
    rec = recovery.groupby(
        ["cover", "transform", "method"], as_index=False
    ).agg(correct=("n_correct", "sum"), feasible_symbols=("n_symbols", "sum"))
    rec["a_conditional"] = rec.correct / rec.feasible_symbols
    rec = rec.pivot(
        index=["cover", "transform"], columns="method", values="a_conditional"
    ).dropna()
    complete_covers = len(rec.index.get_level_values("cover").unique())
    if complete_covers != 99:
        raise RuntimeError(
            f"Expected 99 feasible LFW-val cover clusters, found {complete_covers}"
        )

    assignment = assignment[
        assignment["method"].isin(["S1", "S2", "S3"])
        & (assignment["lambda_value"] == 0.5)
    ]
    feasibility = assignment.groupby(
        ["cover", "method"], as_index=False
    ).agg(feasible=("feasible_messages", "sum"),
          total=("assignment_trials", "sum"))
    feasibility["feasibility"] = feasibility.feasible / feasibility.total
    feasibility = feasibility.pivot(index="cover", columns="method",
                                    values="feasibility")

    rng = np.random.default_rng(SEED)
    rows = []
    for family, method_a, method_b in (
        ("H1_S2_minus_S1", "S2", "S1"),
        ("H2_S3_minus_S2", "S3", "S2"),
    ):
        raw_p = []
        family_rows = []
        for transform in ("rotate1", "crop5"):
            block = rec.xs(transform, level="transform")
            paired = block[[method_a, method_b]].dropna()
            delta = (paired[method_a] - paired[method_b]).to_numpy()
            n = len(delta)
            boot_idx = rng.integers(0, n, size=(DRAWS, n))
            boot = delta[boot_idx].mean(axis=1)
            observed = float(delta.mean())
            signs = rng.choice(np.array([-1.0, 1.0]),
                               size=(PERMUTATIONS, n))
            null = (signs * delta).mean(axis=1)
            p = float((1 + np.count_nonzero(np.abs(null) >= abs(observed)))
                      / (PERMUTATIONS + 1))
            ci = np.quantile(boot, [0.025, 0.975])
            feas = feasibility.loc[paired.index]
            record = {
                "hypothesis": family,
                "transform": transform,
                "metric": "conditional per-symbol accuracy",
                "method_a": method_a,
                "method_b": method_b,
                "covers": n,
                "mean_a": float(paired[method_a].mean()),
                "mean_b": float(paired[method_b].mean()),
                "mean_delta": observed,
                "bootstrap_ci95_low": float(ci[0]),
                "bootstrap_ci95_high": float(ci[1]),
                "sign_flip_p_raw": p,
                "feasibility_a": float(feas[method_a].mean()),
                "feasibility_b": float(feas[method_b].mean()),
                "bootstrap_draws": DRAWS,
                "sign_flip_permutations": PERMUTATIONS,
                "unit": "cover cluster",
            }
            raw_p.append(p)
            family_rows.append(record)
        for record, adjusted in zip(family_rows, holm(raw_p)):
            record["sign_flip_p_holm"] = adjusted
            record["supported_by_accuracy"] = (
                record["mean_delta"] > 0
                and record["bootstrap_ci95_low"] > 0
                and adjusted < 0.05
            )
            rows.append(record)
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "validation_hypothesis_contrasts.csv", index=False)
    geometry_rows = sealed_geometry_diagnostics(rng)
    pd.DataFrame(geometry_rows).to_csv(
        OUT / "sealed_geometry_diagnostics.csv", index=False
    )
    metadata = {
        "source": "validation_recovery_raw_p2resize.csv.gz",
        "configuration": "lambda=0.5; S1/S2/S3; P2; rotation +1 degree and crop 5 percent",
        "conditional_analysis_covers": complete_covers,
        "all_infeasible_covers": 100 - complete_covers,
        "method": "paired cover-cluster percentile bootstrap and two-sided sign-flip randomization; Holm adjustment within each two-transform hypothesis family",
        "seed": SEED,
        "bootstrap_draws": DRAWS,
        "sign_flip_permutations": PERMUTATIONS,
        "analysis_script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "results": rows,
        "note": "H2 also requires a valid out-of-sample Brier comparison; these accuracy contrasts alone do not establish calibration.",
        "sealed_geometry_diagnostics": geometry_rows,
    }
    (OUT / "validation_hypothesis_contrasts.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
