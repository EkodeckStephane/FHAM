"""Rank the frozen Step 4b descriptor screen on D and freeze the top two."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results/stability_step1/step1ter/step4b_screen"
OUT = ROOT / "results/stability_step1/step1ter/step4b_decision"
DESCRIPTORS = ("spectral", "mean_ordinal", "dct_sumabs", "abdulsattar_arr4")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA.glob("*_summary.csv"))
    if len(files) != 100:
        raise RuntimeError(f"Expected 100 descriptor-screen covers, found {len(files)}")
    data = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if set(data.descriptor.unique()) != set(DESCRIPTORS) or data.cover.nunique() != 100:
        raise RuntimeError("Descriptor or cover count mismatch")
    ranking = data.groupby("descriptor", as_index=False).agg(
        covers=("cover", "nunique"), mean_robust_fraction=("robust_fraction", "mean"),
        median_robust_fraction=("robust_fraction", "median"),
        mean_robust_positions=("robust_positions", "mean"),
        median_robust_positions=("robust_positions", "median"),
        mean_distinct_hash_values=("distinct_hash_values", "mean"),
        mean_robust_distinct_hash_values=("robust_distinct_hash_values", "mean"),
        mean_position_count=("positions", "mean"),
        mean_seconds=("elapsed_seconds", "mean"))
    ranking["rank_score_6dp"] = ranking.mean_robust_fraction.round(6)
    # Frozen rule: highest mean robust fraction; tie-break by number of covers
    # meeting G-T1 on the subsequent D C3 run, then descriptor name.
    # No six-decimal tie occurred in the observed screen; this is verified below.
    if ranking.rank_score_6dp.duplicated().any():
        raise RuntimeError("A six-decimal ranking tie requires the preregistered G-T1 tie-break run")
    ranking = ranking.sort_values(["rank_score_6dp", "descriptor"],
                                  ascending=[False, True]).reset_index(drop=True)
    ranking["rank"] = range(1, len(ranking) + 1)
    ranking.to_csv(OUT / "descriptor_ranking.csv", index=False)
    top_two = ranking.head(2).descriptor.tolist()
    selected = {"selected_top_two": top_two,
                "ranking_rule": "mean robust fraction across 100 D covers, rounded to six decimals; no tie occurred",
                "screen_count": 100, "K_per_family": 50,
                "descriptor_ranking_sha256": hashlib.sha256((OUT / "descriptor_ranking.csv").read_bytes()).hexdigest(),
                "E_C_F_evaluation_pixels_opened": False,
                "status": "exploratory selection for C3 ceiling rerun on D"}
    (OUT / "selected_descriptors.json").write_text(json.dumps(selected, indent=2), encoding="utf-8")
    print(json.dumps({"ranking": ranking.to_dict("records"), **selected}, indent=2))


if __name__ == "__main__":
    main()
