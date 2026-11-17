"""Aggregate Step 1bis profile/Q0 outputs by cover and apply the frozen rule."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1bis" / "profile_stage"
OUT = BASE / "summaries"
BOOTSTRAPS = 10000
SEED = 20261116
VALIDATION = ("jpeg75", "noise2", "rotate1", "crop5", "resize0.8")


def load_group(name: str, suffix: str) -> pd.DataFrame:
    folder = BASE / name
    files = sorted(folder.glob(f"*_{suffix}.csv.gz"))
    if not files:
        raise FileNotFoundError(f"No {suffix} chunks in {folder}")
    frames = [pd.read_csv(path) for path in files]
    result = pd.concat(frames, ignore_index=True)
    if result.cover.nunique() != len(files):
        raise RuntimeError(f"Duplicate or missing cover chunks for {name}/{suffix}")
    return result


def cluster_summary(rows: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    per_cover = rows.groupby(
        [*group_columns, "cover"], as_index=False, dropna=False
    ).agg(
        accuracy=("accuracy", "mean"),
        exact_rate=("exact", "mean"),
        source_exact_rate=("source_exact", "mean"),
        feasibility=("feasible", "mean"),
        conditional_accuracy=("accuracy", lambda value: float(value.mean())),
    )
    # Conditional accuracy is computed from feasible messages only.
    feasible_by_cover = rows.loc[rows.feasible.eq(1)].groupby(
        [*group_columns, "cover"], as_index=False, dropna=False
    ).accuracy.mean().rename(columns={"accuracy": "conditional_accuracy"})
    per_cover = per_cover.drop(columns="conditional_accuracy").merge(
        feasible_by_cover, on=[*group_columns, "cover"], how="left", validate="one_to_one"
    )
    per_cover["conditional_accuracy"] = per_cover.conditional_accuracy.fillna(0.0)

    value_columns = ("accuracy", "conditional_accuracy", "exact_rate", "source_exact_rate", "feasibility")
    rng = np.random.default_rng(SEED)
    output = []
    for keys, group in per_cover.groupby(group_columns, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        result = dict(zip(group_columns, keys))
        result["covers"] = int(group.cover.nunique())
        n = len(group)
        for metric in value_columns:
            values = group[metric].to_numpy(dtype=float)
            boot = np.empty(BOOTSTRAPS, dtype=float)
            for start in range(0, BOOTSTRAPS, 250):
                count = min(250, BOOTSTRAPS - start)
                indices = rng.integers(0, n, size=(count, n))
                boot[start:start + count] = values[indices].mean(axis=1)
            result[f"mean_{metric}"] = float(values.mean())
            result[f"{metric}_ci_low"] = float(np.quantile(boot, 0.025))
            result[f"{metric}_ci_high"] = float(np.quantile(boot, 0.975))
        output.append(result)
    return pd.DataFrame(output), per_cover


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assignment_frames = []
    recovery_frames = []
    feasibility_frames = []
    groups = ("A_profile_screen", "B_q0_bridge", "LFW_q0_bridge")
    for group_name in groups:
        assignment_frames.append(load_group(group_name, "assignments"))
        recovery_frames.append(load_group(group_name, "recovery"))
        feasibility_frames.append(load_group(group_name, "feasibility"))
    assignments = pd.concat(assignment_frames, ignore_index=True)
    recoveries = pd.concat(recovery_frames, ignore_index=True)
    feasibilities = pd.concat(feasibility_frames, ignore_index=True)

    recovery_summary, per_cover_recovery = cluster_summary(
        recoveries,
        ["corpus", "split", "profile", "method", "transform", "path"],
    )
    recovery_summary.to_csv(OUT / "recovery_summary_clustered.csv", index=False)
    per_cover_recovery.to_csv(OUT / "recovery_per_cover.csv.gz", index=False, compression="gzip")

    feasibility_summary = feasibilities.groupby(
        ["corpus", "split", "profile", "method", "source_length"], as_index=False
    ).agg(covers=("cover", "nunique"), cases=("feasible", "size"), feasibility=("feasible", "mean"))
    feasibility_summary.to_csv(OUT / "feasibility_by_length.csv", index=False)

    assignment_summary = assignments.groupby(
        ["corpus", "split", "profile", "method", "source_length"], as_index=False
    ).agg(
        covers=("cover", "nunique"),
        assignments=("feasible", "size"),
        feasibility=("feasible", "mean"),
        mean_D1=("D1", "mean"),
        mean_max_abs_delta=("max_abs_delta", "mean"),
        mean_solve_ms=("solve_ms", "mean"),
    )
    assignment_summary.to_csv(OUT / "assignment_summary.csv", index=False)

    # Frozen profile screening rule: eligibility at source length 100; rank by
    # cover-macro mean P3 accuracy, averaging methods and five attacks equally.
    a_feas = feasibility_summary[
        (feasibility_summary.corpus == "BOWS2")
        & (feasibility_summary.split == "A")
        & (feasibility_summary.source_length == 100)
    ]
    a_d1 = assignment_summary[
        (assignment_summary.corpus == "BOWS2")
        & (assignment_summary.split == "A")
        & (assignment_summary.source_length == 100)
    ]
    d1_s0 = a_d1[a_d1.method.eq("S0")].set_index("profile").mean_D1
    eligibility = []
    for profile in (12, 24, 36, 48):
        methods_ok = []
        d1_values = []
        for method in ("S0", "S3"):
            f = a_feas[(a_feas.profile == profile) & (a_feas.method == method)]
            d = a_d1[(a_d1.profile == profile) & (a_d1.method == method)]
            feasible_rate = float(f.feasibility.iloc[0]) if len(f) else 0.0
            d1_mean = float(d.mean_D1.iloc[0]) if len(d) else float("inf")
            baseline = float(d1_s0.get(profile, np.nan))
            ratio = d1_mean / baseline if baseline > 0 else (1.0 if d1_mean == 0 else float("inf"))
            d1_values.append(d1_mean)
            methods_ok.append(feasible_rate >= 0.95 and ratio <= 5.0)
        eligibility.append({
            "profile": profile,
            "eligible": any(methods_ok),
            "S0_feasibility": float(a_feas[(a_feas.profile == profile) & a_feas.method.eq("S0")].feasibility.iloc[0]),
            "S3_feasibility": float(a_feas[(a_feas.profile == profile) & a_feas.method.eq("S3")].feasibility.iloc[0]),
            "mean_D1_best_method": min(d1_values),
        })

    p3 = per_cover_recovery[
        (per_cover_recovery.corpus == "BOWS2")
        & (per_cover_recovery.split == "A")
        & (per_cover_recovery.path == "P3")
        & (per_cover_recovery["transform"].isin(VALIDATION))
    ]
    profile_cover = p3.groupby(["profile", "cover"], as_index=False).accuracy.mean()
    eligibility_frame = pd.DataFrame(eligibility)
    eligibility_frame = eligibility_frame.merge(
        profile_cover.groupby("profile", as_index=False).accuracy.agg(["mean", "std"]).reset_index(),
        on="profile", how="left",
    )
    eligibility_frame["standard_error"] = eligibility_frame["std"] / np.sqrt(100)
    eligible = eligibility_frame[eligibility_frame.eligible].copy()
    eligible = eligible.sort_values(["mean", "mean_D1_best_method"], ascending=[False, True])
    selected_profiles = []
    if len(eligible):
        best_mean = float(eligible.iloc[0]["mean"])
        best_se = float(eligible.iloc[0]["standard_error"])
        within_se = eligible[eligible["mean"] >= best_mean - best_se]
        preferred = within_se.sort_values("mean_D1_best_method").profile.astype(int).tolist()
        remaining = eligible.loc[~eligible.profile.isin(preferred)].profile.astype(int).tolist()
        selected_profiles = (preferred + remaining)[:2]
    decision = {
        "profile_selection_rule": "eligible when at least one method has feasibility >=0.95 at source length 100 and D1 <=5x S0; rank by equal-transform/method cover-macro P3 accuracy",
        "eligible_profiles": eligibility_frame.loc[eligibility_frame.eligible, "profile"].astype(int).tolist(),
        "profile_scores": eligibility_frame.to_dict("records"),
        "selected_profiles_for_F2": selected_profiles,
        "selection_stage": "exploratory A only; validation and confirmatory interpretation remain separate",
        "profile_stage_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUT / "profile_selection.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")
    (OUT / "summary_provenance.json").write_text(json.dumps({
        "cluster_unit": "cover",
        "bootstrap_draws": BOOTSTRAPS,
        "bootstrap_seed": SEED,
        "source_groups": list(groups),
        "covers_by_group": {
            group: sorted(pd.concat([assignment_frames[groups.index(group)]], ignore_index=True).cover.unique().astype(str).tolist())
            for group in groups
        },
        "profiles": [12, 24, 36, 48],
        "phase_b_author_go_received": False,
    }, indent=2), encoding="utf-8")
    print("Profile selection:")
    print(json.dumps(decision, indent=2), flush=True)
    print("BOWS2-A feasibility by profile/length:")
    print(feasibility_summary[feasibility_summary.split.eq("A")].to_string(index=False), flush=True)
    print("BOWS2-A P3 accuracy:")
    print(recovery_summary[(recovery_summary.split == "A") & (recovery_summary.path == "P3")].to_string(index=False), flush=True)
    print("Q0 bridge:")
    print(recovery_summary[(recovery_summary.transform.isin(VALIDATION)) & (recovery_summary.path == "P3") & (recovery_summary.profile == 12)].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
