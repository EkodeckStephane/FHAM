#!/usr/bin/env python3
"""Add cover-pair clustered intervals to the completed D-b G2 results."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/step2/geometry"
raw = pd.read_csv(OUT / "g2_d_b_segment_trials.csv.gz")
cell = raw.groupby(["message_id", "message_family", "attempt", "transform", "chain"],
                   as_index=False).agg(
    exact_segments=("exact_segment", "sum"), segment_count=("exact_segment", "count"),
    mean_errors=("symbol_errors", "mean"), mean_erasures=("erasures", "mean"),
    orb_matches=("orb_matches", "mean"), ransac_inliers=("ransac_inliers", "mean"),
    registration_success=("registration_success", "min"),
    mean_registration_seconds=("registration_seconds", "mean"))
pair = raw.pivot_table(
    index=["message_id", "message_family", "attempt", "transform", "chain"],
    columns="segment_index", values="cover_id", aggfunc="first")
pair = pair.rename(columns={0: "cover0", 1: "cover1"}).reset_index()
cell = cell.merge(pair, on=["message_id", "message_family", "attempt", "transform", "chain"],
                  validate="one_to_one")
cell["exact_message"] = (cell.exact_segments == cell.segment_count).astype(int)
cell.to_csv(OUT / "g2_d_b_message_trials.csv", index=False)

rng = np.random.default_rng(20261121)
cover_ids = sorted(set(cell.cover0.astype(str)) | set(cell.cover1.astype(str)))
cover_map = {x: i for i, x in enumerate(cover_ids)}
summary = cell.groupby(["transform", "chain"], as_index=False).agg(
    n_message_attempts=("exact_message", "count"), exact_rate=("exact_message", "mean"),
    exact_segments=("exact_segments", "sum"), total_segments=("segment_count", "sum"),
    mean_orb_matches=("orb_matches", "mean"), mean_ransac_inliers=("ransac_inliers", "mean"),
    registration_rate=("registration_success", "mean"),
    mean_registration_seconds=("mean_registration_seconds", "mean"))
intervals = []
for (transform, chain), group in cell.groupby(["transform", "chain"]):
    left = group.cover0.astype(str).map(cover_map).to_numpy()
    right = group.cover1.astype(str).map(cover_map).to_numpy()
    outcome = group.exact_message.to_numpy(dtype=float)
    draws = np.empty(10000, dtype=float)
    for i in range(len(draws)):
        counts = np.bincount(rng.integers(0, len(cover_ids), len(cover_ids)),
                             minlength=len(cover_ids))
        weights = counts[left] * counts[right]
        draws[i] = np.average(outcome, weights=weights) if weights.sum() else outcome.mean()
    intervals.append({"transform": transform, "chain": chain,
                      "cover_clusters": len(cover_ids),
                      "cluster_bootstrap_low": np.quantile(draws, .025),
                      "cluster_bootstrap_high": np.quantile(draws, .975)})
summary = summary.merge(pd.DataFrame(intervals), on=["transform", "chain"], validate="one_to_one")
summary.to_csv(OUT / "g2_d_b_summary.csv", index=False)
metadata_path = OUT / "g2_d_b_metadata.json"
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata.pop("created_seconds", None)
metadata["unique_selected_covers"] = len(cover_ids)
metadata["bootstrap_replicates"] = 10000
metadata["runtime_seconds"] = None
metadata["runtime_note"] = "total wall time was not recorded by the first runner; per-registration runtime is recorded in the trial data"
metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print(summary.to_string(index=False))
print(f"unique selected catalogue images: {len(cover_ids)}; raw segment-chain observations: {len(raw)}")
