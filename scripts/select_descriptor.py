from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fham.experiments import descriptor_comparison_experiment

SAMPLE_SIZE = 100
LENGTH_BYTES = 200
TRIALS = 5
BOUND = 2
MANIFEST = Path("dataset/manifests/bossbase.csv")


def load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(
            image.convert("L").resize((512, 512), Image.Resampling.LANCZOS)
        )


def load_validation_sample(manifest: Path, sample_size: int) -> dict[str, np.ndarray]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["split"] == "validation"]
    rows.sort(key=lambda row: row["relative_path"])
    images = {}
    for row in rows[:sample_size]:
        root = Path(row["source_root"])
        images[f"bossbase_val_{row['relative_path']}"] = load_gray(
            root / row["relative_path"]
        )
    return images


def main() -> int:
    images = load_validation_sample(MANIFEST, SAMPLE_SIZE)
    if not images:
        print("no BOSSBase validation images found; cannot select descriptor")
        return 1

    summary, raw = descriptor_comparison_experiment(
        images, lengths=(LENGTH_BYTES,), trials=TRIALS, bound=BOUND
    )
    Path("results/descriptor_selection_validation.csv").parent.mkdir(
        parents=True, exist_ok=True
    )
    summary.to_csv("results/descriptor_selection_validation.csv", index=False)
    raw.to_csv("results/descriptor_selection_validation_raw.csv", index=False)

    d0_time = float(summary.loc[summary["descriptor"] == "spectral", "mean_build_ms"].iloc[0])
    candidates = []
    for _, row in summary.iterrows():
        candidates.append(
            {
                "descriptor": row["descriptor"],
                "success": float(row["success"]),
                "b_star_median": (
                    None if pd_isna(row["b_star_median"]) else float(row["b_star_median"])
                ),
                "mean_build_ms": float(row["mean_build_ms"]),
                "mean_displacement": float(row["mean_displacement"]),
                "meets_success_threshold": bool(row["success"] >= 0.99),
                "meets_radius_threshold": bool(
                    row["b_star_median"] is not None and row["b_star_median"] <= 2
                ),
                "meets_time_threshold": bool(row["mean_build_ms"] <= 2 * d0_time),
            }
        )

    eligible = [
        c
        for c in candidates
        if c["meets_success_threshold"]
        and c["meets_radius_threshold"]
        and c["meets_time_threshold"]
    ]
    pool = eligible if eligible else candidates
    pool = sorted(
        pool,
        key=lambda c: (-c["success"], c["b_star_median"] or 999, c["mean_build_ms"]),
    )
    selected = pool[0]

    decision = {
        "selected_descriptor": selected["descriptor"],
        "selection_rule": (
            "Eligibility: clean assignment success >= 99% at 200 bytes AND "
            "median B* <= 2 AND mean codebook-construction time <= 2x the "
            "spectral (D0) time, all measured on this validation sample only. "
            "Among eligible descriptors, ties broken by highest success, then "
            "lowest median B*, then lowest construction time. If no descriptor "
            "is eligible, the same ranking is applied to all three so a "
            "decision is still recorded, and this fallback is reported "
            "explicitly rather than silently defaulting to D0."
        ),
        "used_fallback_no_eligible_descriptor": not eligible,
        "sample": "BOSSBase 1.01 validation split (dataset/manifests/bossbase.csv, split=validation)",
        "sample_size": len(images),
        "length_bytes": LENGTH_BYTES,
        "bound": BOUND,
        "candidates": candidates,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": (
            "This selection is frozen before any use of the BOSSBase test_internal "
            "split, BOWS2, or COCO 2017; it is independent of, and does not "
            "retroactively change, the spectral descriptor used as the default "
            "throughout the rest of this study."
        ),
    }
    Path("results/acceptance/frozen_descriptor.json").write_text(
        json.dumps(decision, indent=2, sort_keys=False), encoding="utf-8"
    )
    print(f"selected descriptor: {selected['descriptor']} (fallback used: {not eligible})")
    return 0


def pd_isna(value) -> bool:
    return value != value  # NaN != NaN


if __name__ == "__main__":
    raise SystemExit(main())
