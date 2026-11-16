"""Add ORB/RANSAC success and cluster intervals to Step 1 validation outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stability_step1"
SEED = 20261116
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fham.config import DATASET_DIR  # noqa: E402
from stability_step1_estimate import split_names  # noqa: E402
from stability_step1_pilot import SEED as ATTACK_SEED, _register, transform  # noqa: E402


def main():
    chunks = OUT / "validation_chunks_p2resize"
    files = sorted(chunks.glob("*_recovery.csv.gz"))
    raw_frames = [pd.read_csv(path) for path in files if path.stat().st_size >= 100]
    raw = pd.concat(raw_frames, ignore_index=True)
    keys = ["cover", "config", "transform", "path"]
    registration = raw.groupby(keys, dropna=False, as_index=False).agg(
        registration_success_rate=("registration_success", "mean"),
        mean_keypoint_matches=("keypoint_matches", "mean"),
        mean_ransac_inliers=("ransac_inliers", "mean"),
    )
    summary_path = OUT / "validation_recovery_summary_p2resize.csv"
    summary = pd.read_csv(summary_path)
    summary = summary.drop(columns=[
        "registration_success_rate", "mean_keypoint_matches", "mean_ransac_inliers"
    ], errors="ignore")
    summary = summary.merge(registration, on=keys, how="left")
    summary.to_csv(summary_path, index=False)

    _dev_names, val_names = split_names()
    registration_rows = []
    for image_index, name in enumerate(val_names):
        image = np.asarray(Image.open(DATASET_DIR / "stress" / f"{name}.png").convert("L"))
        for i, transform_name in enumerate(("rotate1", "crop5", "resize0.8")):
            data = transform(image, transform_name,
                             ATTACK_SEED + image_index * 101 + (2, 3, 4)[i], "bicubic")
            attacked = data[0] if isinstance(data, tuple) else data
            aligned, matches, inliers = _register(image, attacked)
            registration_rows.append({
                "cover": name, "transform": transform_name,
                "registration_success": int(aligned is not None),
                "keypoint_matches": matches, "ransac_inliers": inliers,
            })
    registration_by_cover = pd.DataFrame(registration_rows)
    by_transform = registration_by_cover.groupby("transform", as_index=False).agg(
        covers=("cover", "nunique"),
        registration_successes=("registration_success", "sum"),
        registration_success_rate=("registration_success", "mean"),
        mean_keypoint_matches=("keypoint_matches", "mean"),
        mean_ransac_inliers=("ransac_inliers", "mean"),
    )
    p2 = summary[(summary.path == "P2") &
                 (summary.config == "S3:lambda=0.5:tau=None")]
    accuracy = p2.groupby("transform", as_index=False).agg(
        mean_accuracy_conditional=("accuracy_conditional", "mean"),
        mean_accuracy_unconditional=("accuracy_unconditional", "mean"),
        exact_messages=("exact_messages", "sum"),
    )
    by_transform = by_transform.merge(accuracy, on="transform", how="left")
    by_transform.to_csv(OUT / "validation_registration_summary.csv", index=False)

    selected = summary[
        (summary.config == "S3:lambda=0.5:tau=None")
        & (summary.transform != "identity")
    ].copy()
    rng = np.random.default_rng(SEED)
    ci_rows = []
    for (transform_name, path), group in selected.groupby(["transform", "path"]):
        group = group.sort_values("cover")
        values = group["accuracy_conditional"].to_numpy(dtype=float)
        bootstrap_indices = rng.integers(0, len(values), size=(10000, len(values)))
        means = np.nanmean(values[bootstrap_indices], axis=1)
        ci_rows.append({
            "method": "S3", "lambda": 0.5,
            "transform": transform_name, "path": path,
            "mean_accuracy_conditional": float(np.nanmean(values)),
            "ci95_low": float(np.nanpercentile(means, 2.5)),
            "ci95_high": float(np.nanpercentile(means, 97.5)),
            "covers": int(group.cover.nunique()),
            "bootstrap_draws": 10000,
        })
    pd.DataFrame(ci_rows).to_csv(OUT / "validation_selected_accuracy_ci.csv", index=False)
    print(by_transform.to_string(index=False))
    print(json.dumps({
        "p2_geometric_registration": by_transform[
            by_transform["transform"].isin(["rotate1", "crop5", "resize0.8"])
        ].to_dict(orient="records"),
        "selected_accuracy_ci": ci_rows,
    }, indent=2))


if __name__ == "__main__":
    main()
