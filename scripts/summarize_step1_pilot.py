"""Summarize preregistered geometric pilot contrasts and precision target."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "stability_step1"
TARGET_HALF_WIDTH = 0.03
Z = 1.96


def main():
    raw = pd.read_csv(RESULTS / "pilot_d0_raw.csv")
    raw = raw[raw["path"].isin(["P1", "P2"]) & raw["transform"].isin(
        ["rotate1", "crop5", "resize08"]
    )]
    wide = raw.pivot(index="image", columns=["transform", "path"], values="accuracy")
    rows = []
    for transform in ("rotate1", "crop5", "resize08"):
        delta = wide[(transform, "P2")] - wide[(transform, "P1")]
        sd = float(delta.std(ddof=1))
        required = math.ceil((Z * sd / TARGET_HALF_WIDTH) ** 2)
        rows.append({
            "transformation": transform,
            "paired_contrast": "P2 minus P1 per-cover character accuracy",
            "n_covers": int(delta.notna().sum()),
            "mean_delta": float(delta.mean()),
            "sd_delta": sd,
            "required_n_for_3pp_half_width": required,
        })
    selected_n = max(100, max(r["required_n_for_3pp_half_width"] for r in rows))
    result = {
        "formula": "ceil((1.96*sd_delta/0.03)^2)",
        "source": "20-cover D0 pilot; paired P2-P1 contrasts for all geometric validation transformations",
        "selected_n": selected_n,
        "rule": "retain preregistered 100-image LFW-val split when the maximum pilot estimate is <=100; otherwise expand before validation",
        "results": rows,
    }
    (RESULTS / "pilot_sample_size.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
