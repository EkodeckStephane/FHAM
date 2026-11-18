"""Aggregate frozen Step 1ter D outputs and apply G-T1 exactly as registered."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results/stability_step1/step1ter/step2_3"
OUT = ROOT / "results/stability_step1/step1ter/summary"
Z = 1.959963984540054


def wilson(k: int, n: int) -> tuple[float, float]:
    p = k / n
    den = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / den
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return max(0.0, center - half), min(1.0, center + half)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ceiling_files = sorted(DATA.glob("*_ceiling.csv"))
    if len(ceiling_files) != 100:
        raise RuntimeError(f"Expected 100 completed D covers, found {len(ceiling_files)}")
    ceiling = pd.concat([pd.read_csv(p) for p in ceiling_files], ignore_index=True)
    all12 = ceiling.loc[ceiling.attack.eq("feasibility_12_all") & ceiling.source_length.eq(100)]
    if all12.groupby(["profile", "bound"]).cover.nunique().ne(100).any():
        raise RuntimeError("Each G-T1 cell must contain exactly 100 covers")
    rows = []
    for (profile, bound), group in all12.groupby(["profile", "bound"], sort=True):
        k, n = int(group.feasible.sum()), len(group)
        lo, hi = wilson(k, n)
        point = k / n
        status = "green" if lo >= .90 else "orange" if point >= .70 else "red"
        rows.append({"profile": profile, "B": bound, "successes": k, "covers": n,
                     "point_estimate": point, "wilson95_low": lo, "wilson95_high": hi,
                     "G_T1": status})
    gate = pd.DataFrame(rows)
    gate.to_csv(OUT / "G_T1_by_profile_bound.csv", index=False)

    msg = ceiling.loc[~ceiling.attack.eq("feasibility_12_all")]
    feasibility = msg.groupby(["profile", "bound", "source_length", "family"], as_index=False).agg(
        message_trials=("feasible", "size"), feasible_messages=("feasible", "sum"),
        mean_feasibility=("feasible", "mean"), median_compressed_length=("compressed_length", "median"))
    feasibility.to_csv(OUT / "message_feasibility.csv", index=False)
    robust = ceiling.loc[ceiling.attack.eq("feasibility_12_all")].groupby(
        ["profile", "source_length"], as_index=False).agg(
            median_robust_positions=("robust_positions", "median"),
            p10_robust_positions=("robust_positions", lambda x: x.quantile(.1)),
            p90_robust_positions=("robust_positions", lambda x: x.quantile(.9)),
            mean_total_positions=("total_positions", "mean"))
    robust.to_csv(OUT / "robust_position_summary.csv", index=False)

    bit_files = sorted(DATA.glob("*_bits.csv"))
    bits = pd.concat([pd.read_csv(p) for p in bit_files], ignore_index=True)
    bits["bit_msb_index"] = 7 - bits.bit_lsb_index
    bit_summary = bits.groupby(["profile", "family", "arrangement", "bit_msb_index"], as_index=False).agg(
        flips=("flips", "sum"), comparisons=("comparisons", "sum"))
    bit_summary["flip_rate"] = bit_summary.flips / bit_summary.comparisons
    bit_summary.to_csv(OUT / "step2_bit_flip_summary.csv", index=False)

    margin_files = sorted(DATA.glob("*_margins.csv"))
    margins = pd.concat([pd.read_csv(p) for p in margin_files], ignore_index=True)
    margins["bit_msb_index"] = 7 - margins.bit_lsb_index
    margin_summary = margins.groupby(["profile", "arrangement", "bit_msb_index"], as_index=False).agg(
        median_abs_margin_across_covers=("median_abs_margin", "median"),
        mean_cover_p05_margin=("p05_abs_margin", "mean"),
        mean_cover_p95_margin=("p95_abs_margin", "mean"))
    margin_summary.to_csv(OUT / "step2_margin_summary.csv", index=False)

    position_files = sorted(DATA.glob("*_positions.csv.gz"))
    score_rows = []
    value_rows = []
    for path in position_files:
        pos = pd.read_csv(path)
        k = 100
        pos["s_jpeg_smoothed"] = (k * pos.s_jpeg + 1) / (k + 2)
        pos["s_noise_smoothed"] = (k * pos.s_noise + 1) / (k + 2)
        pos["s_min_smoothed"] = pos[["s_jpeg_smoothed", "s_noise_smoothed"]].min(axis=1)
        pos.to_csv(path, index=False, compression="gzip")
        for (cover, profile), group in pos.groupby(["cover", "profile"]):
            value_rows.append({"cover": cover, "profile": profile,
                               "robust_distinct_hash_values": group.loc[group.robust.eq(1), "hash_value"].nunique(),
                               "all_distinct_hash_values": group.hash_value.nunique(),
                               "robust_positions": int(group.robust.sum()),
                               "position_count": len(group)})
    values = pd.DataFrame(value_rows)
    values.to_csv(OUT / "robust_hash_value_coverage.csv", index=False)

    statuses = set(gate.G_T1)
    overall = "green" if "green" in statuses else "orange" if "orange" in statuses else "red"
    report = {"D_covers": 100, "profiles": sorted(gate.profile.unique().tolist()),
              "G_T1_overall": overall,
              "eligible_green_cells": gate.loc[gate.G_T1.eq("green"), ["profile", "B"]].to_dict("records"),
              "best_point_cell": gate.sort_values("point_estimate", ascending=False).iloc[0].to_dict(),
              "C_F_E_evaluation_pixels_opened": False,
              "notes": ["E is reserved for the Step 5 held-out validation; C/F remain reserved for Step 6.",
                        "Smoothed per-family scores are derived from the saved empirical stability counts."]}
    (OUT / "decision_G_T1.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
