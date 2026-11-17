"""Verify the focused S3/lambda=0.5 regression against the same 20 LFW covers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


CONFIG = "S3:lambda=0.5:tau=None"
KEY = ["transform", "path"]


def read_cover_summaries(folder: Path, names: list[str]) -> pd.DataFrame:
    frames = []
    for name in names:
        path = folder / f"{name}_cover_recovery_summary.csv.gz"
        frame = pd.read_csv(path)
        frame = frame.loc[frame["config"].eq(CONFIG)].copy()
        frame["cover"] = name
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reproduction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    names = sorted(
        path.name.removesuffix("_cover_recovery_summary.csv.gz")
        for path in args.reproduction.glob("*_cover_recovery_summary.csv.gz")
    )
    if len(names) != 20:
        raise RuntimeError(f"Expected 20 reproduced covers; found {len(names)}")

    reference = read_cover_summaries(args.reference, names)
    reproduction = read_cover_summaries(args.reproduction, names)
    keys = ["cover", *KEY]
    columns = [*keys, "correct_symbols", "expected_symbols"]
    reference = reference[columns].rename(
        columns={"correct_symbols": "reference_correct", "expected_symbols": "reference_expected"}
    )
    reproduction = reproduction[columns].rename(
        columns={"correct_symbols": "reproduced_correct", "expected_symbols": "reproduced_expected"}
    )
    paired = reference.merge(reproduction, on=keys, validate="one_to_one")
    if len(paired) != 280:
        raise RuntimeError(f"Expected 280 paired cover/condition rows; found {len(paired)}")

    paired["reference_accuracy"] = paired.reference_correct / paired.reference_expected
    paired["reproduced_accuracy"] = paired.reproduced_correct / paired.reproduced_expected
    paired["delta_percentage_points"] = (
        paired.reproduced_accuracy - paired.reference_accuracy
    ) * 100
    summary = paired.groupby(KEY, as_index=False).agg(
        covers=("cover", "nunique"),
        reference_accuracy=("reference_accuracy", "mean"),
        reproduced_accuracy=("reproduced_accuracy", "mean"),
        delta_percentage_points=("delta_percentage_points", "mean"),
    )
    max_abs_delta = float(summary.delta_percentage_points.abs().max())
    gate = {
        "configuration": CONFIG,
        "covers": len(names),
        "cover_condition_pairs": len(paired),
        "reference_cover_set_matches_reproduction": True,
        "maximum_absolute_difference_percentage_points": max_abs_delta,
        "tolerance_percentage_points": 0.05,
        "passed": max_abs_delta <= 0.05,
        "cover_ids": names,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    paired.to_csv(args.output / "paired_cover_conditions.csv", index=False)
    summary.to_csv(args.output / "condition_summary.csv", index=False)
    (args.output / "gate.json").write_text(json.dumps(gate, indent=2), encoding="utf-8")
    print(json.dumps(gate, indent=2))
    if not gate["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
