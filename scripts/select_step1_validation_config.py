"""Apply the preregistered LFW-val rule and produce confidence intervals."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "stability_step1"
SEED = 20261116


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials <= 0:
        return float("nan"), float("nan")
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    margin = z * np.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return float(center - margin), float(center + margin)


def main():
    run_suffix = "p2resize"
    assignment = pd.read_csv(RESULTS / f"validation_assignment_summary_{run_suffix}.csv")
    recovery = pd.read_csv(RESULTS / f"validation_recovery_summary_{run_suffix}.csv")
    primary = recovery[
        ((recovery["transform"] != "identity")
         & (((recovery["transform"].isin(["rotate1", "crop5", "resize0.8"])) & (recovery["path"] == "P2"))
            | (~recovery["transform"].isin(["rotate1", "crop5", "resize0.8"]) & (recovery["path"] == "P1"))))
    ].copy()
    primary_by_cover = primary.groupby(
        ["cover", "method", "lambda", "tau", "config"], dropna=False,
        as_index=False,
    ).agg(
        correct=("correct_symbols", "sum"),
        feasible_symbols=("feasible_symbols", "sum"),
        expected_symbols=("expected_symbols", "sum"),
        feasible_messages=("feasible_messages", "sum"),
        n_messages=("n_messages", "sum"),
        exact_messages=("exact_messages", "sum"),
    )
    primary_by_cover["a_conditional"] = (
        primary_by_cover["correct"]
        / primary_by_cover["feasible_symbols"].replace(0, np.nan)
    )
    primary_by_cover["a_unconditional"] = (
        primary_by_cover["correct"] / primary_by_cover["expected_symbols"]
    )
    primary_by_cover["exact_rate_unconditional"] = (
        primary_by_cover["exact_messages"] / primary_by_cover["n_messages"]
    )

    assignment_group = assignment.groupby(
        ["method", "lambda_value", "tau", "config"], dropna=False,
        as_index=False,
    ).agg(
        mean_feasibility=("feasibility", "mean"),
        feasible_trials=("feasible_messages", "sum"),
        total_trials=("assignment_trials", "sum"),
        mean_D1=("mean_D1", "mean"),
        mean_solve_ms=("mean_solve_ms", "mean"),
    )
    baseline_D1 = float(
        assignment_group.loc[assignment_group.method == "S0", "mean_D1"].iloc[0]
    )
    assignment_group["mean_D1_ratio"] = (
        assignment_group["mean_D1"] / baseline_D1
    )
    cover_counts = primary_by_cover.groupby("config").agg(
        covers=("cover", "nunique"),
        mean_a_conditional=("a_conditional", "mean"),
        sd_a_conditional=("a_conditional", "std"),
        mean_a_unconditional=("a_unconditional", "mean"),
        mean_exact_unconditional=("exact_rate_unconditional", "mean"),
    ).reset_index()
    ranking = assignment_group.merge(cover_counts, on="config", how="left")
    ranking["se_a"] = ranking["sd_a_conditional"] / np.sqrt(ranking["covers"])
    intervals = [wilson_interval(int(r.feasible_trials), int(r.total_trials))
                 for r in ranking.itertuples()]
    ranking["feasibility_wilson95_low"] = [x[0] for x in intervals]
    ranking["feasibility_wilson95_high"] = [x[1] for x in intervals]
    ranking["eligible"] = (
        (ranking.mean_feasibility >= 0.95)
        & (ranking.mean_D1_ratio <= 5.0)
    )

    rng = np.random.default_rng(SEED)
    n_covers = len(primary_by_cover.cover.unique())
    bootstrap_indices = rng.integers(0, n_covers, size=(10000, n_covers))
    ci_rows = []
    for config, group in primary_by_cover.groupby("config"):
        group = group.sort_values("cover")
        for metric in ("a_conditional", "a_unconditional", "exact_rate_unconditional"):
            values = group[metric].to_numpy(dtype=float)
            if np.isnan(values).all():
                mean = low = high = float("nan")
            else:
                means = np.nanmean(values[bootstrap_indices], axis=1)
                mean = float(np.nanmean(values))
                low = float(np.nanpercentile(means, 2.5))
                high = float(np.nanpercentile(means, 97.5))
            ci_rows.append({
                "config": config,
                "metric": metric,
                "mean": mean,
                "ci95_low": low,
                "ci95_high": high,
                "bootstrap_draws": 10000,
                "unit": "cover cluster",
            })
    cis = pd.DataFrame(ci_rows)
    ranking.to_csv(RESULTS / "validation_config_ranking.csv", index=False)
    cis.to_csv(RESULTS / "validation_config_cluster_ci.csv", index=False)

    eligible = ranking[ranking.eligible].copy()
    chosen = None
    within_one_se = []
    if not eligible.empty:
        best = eligible.loc[eligible.mean_a_conditional.idxmax()]
        threshold = best.mean_a_conditional - best.se_a
        within = eligible[eligible.mean_a_conditional >= threshold]
        selected = within.sort_values(
            ["mean_D1", "mean_a_conditional"], ascending=[True, False]
        ).iloc[0]
        chosen = {
            "method": selected.method,
            "lambda": (None if pd.isna(selected.lambda_value)
                       else float(selected.lambda_value)),
            "tau": (None if pd.isna(selected.tau) else float(selected.tau)),
            "config": selected.config,
            "selection_metric": "primary conditional per-symbol accuracy: P1 for photometric transforms; P2 for rotation, crop, and resize geometric transforms",
            "best_mean_accuracy": float(best.mean_a_conditional),
            "one_se_threshold": float(threshold),
            "selected_mean_accuracy": float(selected.mean_a_conditional),
            "selected_mean_unconditional_accuracy": float(selected.mean_a_unconditional),
            "selected_feasibility": float(selected.mean_feasibility),
            "selected_mean_D1": float(selected.mean_D1),
            "selected_D1_ratio_to_S0": float(selected.mean_D1_ratio),
            "within_one_se_configs": within.config.tolist(),
        }
        within_one_se = within.config.tolist()
    decision = {
        "eligible_configuration_count": int(len(eligible)),
        "total_configuration_count": int(len(ranking)),
        "selection": chosen,
        "no_eligible_configuration": chosen is None,
        "selection_rule": "feasibility >= 0.95 and mean D1 <= 5x S0; maximize validation accuracy; among configurations within one standard error of best choose lowest D1.",
        "test_remains_sealed": True,
    }
    (RESULTS / "validation_config_selection.json").write_text(
        json.dumps(decision, indent=2), encoding="utf-8"
    )
    print(ranking.sort_values("mean_a_conditional", ascending=False).to_string(index=False))
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
