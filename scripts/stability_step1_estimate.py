"""Estimate S1/S2/S3 position scores on the frozen 100-cover LFW-dev split."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import PIL
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.config import DATASET_DIR  # noqa: E402
from fham.experiments import _attack  # noqa: E402
from fham.methods import OptimalAssignmentMethod  # noqa: E402
from fham.stability import estimate_position_stability  # noqa: E402
from stability_step1_pilot import transform  # noqa: E402

SEED = 20261116
BLOCK_SIZE = 12
OLD_DEVELOPMENT = ("jpeg90", "resize90", "noise1")
EXTENDED_DEVELOPMENT = (
    "jpeg90", "jpeg85", "noise1", "noise1.5",
    "rotate-0.5", "rotate0.5", "rotate2",
    "crop3", "crop7", "resize0.9",
)


def split_names():
    manifest = pd.read_csv(DATASET_DIR / "stress" / "manifest.csv")
    faces = manifest[manifest.content_type.str.lower().str.contains("face")]
    ordered = sorted(
        faces.name.astype(str).tolist(),
        key=lambda name: hashlib.sha256(f"{SEED}:{name}".encode()).hexdigest(),
    )
    if len(ordered) < 200:
        raise RuntimeError(f"Expected 200 LFW images, found {len(ordered)}")
    return ordered[:100], ordered[100:200]


def main():
    dev_names, val_names = split_names()
    out = ROOT / "results" / "stability_step1"
    out.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    score_empirical_old = []
    score_empirical_extended = []
    score_continuous = []
    margin_arrays = []
    location_arrays = []
    started = time.perf_counter()

    for image_index, name in enumerate(dev_names):
        image_path = DATASET_DIR / "stress" / f"{name}.png"
        image = np.asarray(Image.open(image_path).convert("L"))
        if image.shape != (512, 512):
            raise ValueError(f"{name} has unexpected shape {image.shape}")
        lookup = OptimalAssignmentMethod(BLOCK_SIZE, "spectral")
        lookup.build_lookup_table(image)
        locations = [
            loc for candidates in lookup.lookup_table.values() for loc in candidates
        ]
        old_images = [
            _attack(image, attack, SEED + image_index * 101 + i)
            for i, attack in enumerate(OLD_DEVELOPMENT)
        ]
        old_scores, _, _ = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", old_images
        )

        extended_images = []
        for i, attack in enumerate(EXTENDED_DEVELOPMENT):
            if attack.startswith("jpeg"):
                attacked = transform(image, attack, SEED + image_index * 101 + i,
                                     "bilinear")
            elif attack.startswith("noise"):
                attacked = transform(image, attack, SEED + image_index * 101 + i,
                                     "bilinear")
            elif attack.startswith("rotate") or attack.startswith("crop") or attack.startswith("resize"):
                attacked = transform(image, attack, SEED + image_index * 101 + i,
                                     "bilinear")
            else:
                raise ValueError(attack)
            if isinstance(attacked, tuple):
                attacked = attacked[0]
            extended_images.append(attacked)
        extended_scores, continuous_scores, margin_rows = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", extended_images
        )
        score_empirical_old.append([old_scores[loc] for loc in locations])
        score_empirical_extended.append([extended_scores[loc] for loc in locations])
        score_continuous.append([continuous_scores[loc] for loc in locations])
        location_arrays.append([
            [loc.x, loc.y, loc.arrangement]
            for loc in locations
        ])
        margin_arrays.append(np.asarray([
            [row["margins"], row["sigma"]] for row in margin_rows
        ], dtype=np.float32))
        summary_rows.append({
            "image": name,
            "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "positions": len(locations),
            "S1_mean_stability": float(np.mean(score_empirical_old[-1])),
            "S2_mean_stability": float(np.mean(score_empirical_extended[-1])),
            "S3_mean_stability": float(np.mean(score_continuous[-1])),
            "S3_sigma_floor": float(margin_rows[0]["sigma_floor"]),
            "elapsed_seconds": time.perf_counter() - started,
        })
        if (image_index + 1) % 10 == 0:
            print(f"[{image_index + 1}/100] covers; elapsed "
                  f"{time.perf_counter() - started:.1f}s", flush=True)

    max_positions = max(len(x) for x in score_empirical_old)
    if any(len(x) != max_positions for x in score_empirical_old):
        raise RuntimeError("Position counts differ across LFW-dev covers")
    np.savez_compressed(
        out / "dev_position_scores.npz",
        image_names=np.asarray(dev_names),
        locations=np.asarray(location_arrays, dtype=np.int16),
        S1=np.asarray(score_empirical_old, dtype=np.float32),
        S2=np.asarray(score_empirical_extended, dtype=np.float32),
        S3=np.asarray(score_continuous, dtype=np.float32),
        margins_sigma=np.asarray(margin_arrays, dtype=np.float32),
    )
    pd.DataFrame(summary_rows).to_csv(out / "dev_stability_summary.csv", index=False)
    split_manifest = {
        "seed": SEED,
        "ordering": "ascending SHA256(f'{seed}:{image_name}')",
        "dev_names": dev_names,
        "val_names": val_names,
        "dev_sha256": {r["image"]: r["sha256"] for r in summary_rows},
        "val_sha256": {
            name: hashlib.sha256(
                (DATASET_DIR / "stress" / f"{name}.png").read_bytes()
            ).hexdigest()
            for name in val_names
        },
        "validation_history": "Same 200-image LFW stress corpus was used in prior FHAM capacity studies; split is held out only for this new stability-transform analysis.",
        "block_size": BLOCK_SIZE,
        "descriptor": "spectral",
        "development_original": list(OLD_DEVELOPMENT),
        "development_extended": list(EXTENDED_DEVELOPMENT),
        "seed_rule": "image order ascending SHA256(f'{20261116}:{image_name}'); first 100 dev, next 100 validation; first 20 dev used for D0 pilot.",
        "geometry_interpolation": "OpenCV INTER_LINEAR",
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pillow": PIL.__version__,
        },
        "stability_definition": "empirical unchanged hash and product of eight normal CDFs of absolute margins divided by per-comparison empirical sigma; sigma floor is the 5th percentile within cover.",
    }
    (out / "dev_split_and_provenance.json").write_text(
        json.dumps(split_manifest, indent=2), encoding="utf-8"
    )
    print(pd.DataFrame(summary_rows)[[
        "S1_mean_stability", "S2_mean_stability", "S3_mean_stability"
    ]].mean().to_string(), flush=True)
    print(f"wrote {out / 'dev_position_scores.npz'}; elapsed "
          f"{time.perf_counter() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
