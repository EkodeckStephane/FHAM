#!/usr/bin/env python3
"""Protocol Step 2 G development on the already-open D-b set only."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from skimage.feature import ORB, match_descriptors
from skimage.measure import ransac
from skimage.transform import SimilarityTransform, warp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_step1quater as q4
from run_step1ter_descriptor_screen import batch_hash_map

MANIFEST = ROOT / "results/stability_step1/step1quater/manifest/D_b_images_sha256.csv"
TRIALS = ROOT / "results/stability_step1/step1quater/run/A4_segmented_trials.csv.gz"
OUT = ROOT / "results/step2/geometry"
CONFIG_ID = 210
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")


def _feature(image):
    detector = ORB(n_keypoints=800, fast_threshold=0.04)
    try:
        detector.detect_and_extract(image.astype(np.float32) / 255.0)
        return detector
    except RuntimeError:
        return None


def _estimate(reference, attacked):
    a, b = _feature(reference), _feature(attacked)
    if a is None or b is None or len(a.descriptors) < 4 or len(b.descriptors) < 4:
        return None, 0, 0
    pairs = match_descriptors(a.descriptors, b.descriptors,
                              cross_check=True, max_ratio=0.8)
    if len(pairs) < 4:
        return None, len(pairs), 0
    source = a.keypoints[pairs[:, 0]][:, ::-1]
    destination = b.keypoints[pairs[:, 1]][:, ::-1]
    model, inliers = ransac(
        (source, destination), SimilarityTransform, min_samples=4,
        residual_threshold=2.5, max_trials=1000,
        rng=np.random.default_rng(20261121),
    )
    if model is None or inliers is None or int(inliers.sum()) < 4:
        return None, len(pairs), 0
    restored = warp(attacked, inverse_map=model, output_shape=reference.shape,
                    order=1, mode="constant", cval=0, preserve_range=True)
    return np.clip(np.rint(restored), 0, 255).astype(np.uint8), len(pairs), int(inliers.sum())


def _transforms(image, identity, attempt):
    side = image.shape[0]
    seed_base = hashlib.sha256(f"FHAM-G2|{identity}|{attempt}".encode()).digest()
    rng = np.random.default_rng(int.from_bytes(seed_base[:8], "big"))
    angle = float(rng.uniform(-2.0, 2.0))
    scale = float(rng.uniform(0.82, 0.95))
    margin_pct = float(rng.uniform(0.02, 0.08))
    margin = max(1, round(side * margin_pct))
    crop_scale = side / (side - 2 * margin)
    transforms = {
        "rotation": SimilarityTransform(rotation=np.deg2rad(angle),
                                        translation=(side * 0.5, side * 0.5))
                    + SimilarityTransform(translation=(-side * 0.5, -side * 0.5)),
        "crop_restore": SimilarityTransform(scale=crop_scale,
                                             translation=(side / 2 * (1 - crop_scale),
                                                          side / 2 * (1 - crop_scale))),
        "resize_restore": SimilarityTransform(),
    }
    outputs = {}
    for name, transform in transforms.items():
        if name == "resize_restore":
            reduced = Image.fromarray(image).resize((round(side * scale), round(side * scale)),
                                                     Image.Resampling.LANCZOS)
            attacked = np.asarray(reduced.resize((side, side), Image.Resampling.LANCZOS))
            oracle_model = SimilarityTransform()
        else:
            attacked = warp(image, inverse_map=transform.inverse, output_shape=image.shape,
                            order=1, mode="constant", cval=0, preserve_range=True)
            attacked = np.clip(np.rint(attacked), 0, 255).astype(np.uint8)
            oracle_model = transform
        outputs[name] = (attacked, oracle_model, angle if name == "rotation" else
                         (margin_pct if name == "crop_restore" else scale))
    return outputs


def _solve_segment(message_id, source, compressed, cover_id):
    locations, hashes, robust, stability = q4.load_codebook(cover_id)
    codeword, blocks = q4.rs_encode(compressed, 10)
    allowed = robust.copy()
    cap = int(np.floor(0.05 * len(codeword)))
    unstable = np.flatnonzero(~robust)
    order = sorted(unstable.tolist(), key=lambda j: (-float(stability[j]), j))
    if cap:
        allowed[np.asarray(order[:cap], dtype=np.int32)] = True
    assignment = q4.assignment_graph(codeword, hashes, stability, robust,
                                     allowed, 4, blocks, 10, 5)
    if not assignment["parity_ok"]:
        return None
    return {"locations": locations, "hashes": hashes, "robust": robust,
            "stability": stability, "source": source, "compressed": compressed,
            "codeword": codeword, "blocks": blocks, "assignment": assignment}


def _decode_segment(segment, image, cover_id, p=10):
    transformed = batch_hash_map(image, "mean_ordinal", 12, segment["locations"])
    ok, erasures, errors = q4.recover_message(
        segment["source"], segment["compressed"], segment["codeword"],
        segment["blocks"], segment["assignment"], segment["hashes"],
        transformed, segment["locations"], p,
    )
    return ok, erasures, errors


def _measure_segment_chains(segment, cover_id, original, variants, attempt,
                           message_id, family, segment_index):
    rows = []
    for transform_name, (attacked, true_model, severity) in variants.items():
        estim = time.perf_counter()
        aligned, matches, inliers = _estimate(original, attacked)
        estimate_seconds = time.perf_counter() - estim
        oracle = warp(attacked, inverse_map=true_model, output_shape=original.shape,
                      order=1, mode="constant", cval=0, preserve_range=True)
        oracle = np.clip(np.rint(oracle), 0, 255).astype(np.uint8)
        chains = {"P1_fixed": attacked, "P2_ORB_RANSAC": aligned,
                  "P3_inverse_oracle": oracle}
        for chain, image in chains.items():
            if image is None:
                exact, erasures, errors = False, len(segment["codeword"]), len(segment["codeword"])
            else:
                exact, erasures, errors = _decode_segment(segment, image, cover_id)
            rows.append({"cover_id": cover_id, "attempt": attempt, "message_id": message_id,
                         "message_family": family, "segment_index": segment_index,
                         "transform": transform_name, "severity": severity, "chain": chain,
                         "exact_segment": int(exact),
                         "erasures": erasures, "symbol_errors": errors,
                         "orb_matches": matches, "ransac_inliers": inliers,
                         "registration_success": int(aligned is not None),
                         "registration_seconds": estimate_seconds})
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(MANIFEST, keep_default_na=False)
    if len(manifest) != 100:
        raise RuntimeError("D-b must contain exactly 100 frozen covers")
    by_id = {str(r.source_id): r for r in manifest.itertuples(index=False)}
    trials = pd.read_csv(TRIALS, compression="gzip", low_memory=False)
    trials = trials[(trials.config_id == CONFIG_ID) & (trials.feasible == 1)
                    & (trials["index"] == 0)]
    if set(trials.family.unique()) != set(FAMILIES):
        raise RuntimeError("the four frozen geometry messages are not present")
    messages = q4.compressed_messages()
    rows = []
    started = time.perf_counter()
    run_started = started
    transform_cache = {}
    cover_cache = {}
    for trial in trials.sort_values(["family", "attempt"]).itertuples(index=False):
        message_id = trial.message_id
        family, _, source, _ = messages[message_id]
        selected = str(trial.selected_covers).split(";")
        if len(selected) != 2 or any(cid not in by_id for cid in selected):
            raise RuntimeError(f"selected covers are outside D-b: {message_id}/{trial.attempt}")
        source_segments = (source[:50], source[50:])
        compressed_segments = tuple(q4.zlib.compress(x, 9) for x in source_segments)
        segment_results = []
        for segment_index, (raw, compressed, cover_id) in enumerate(
            zip(source_segments, compressed_segments, selected)
        ):
            key = (cover_id, message_id)
            segment = _solve_segment(message_id, raw, compressed, cover_id)
            if segment is None:
                raise RuntimeError(f"A4 feasible row not reproducible: {message_id}/{cover_id}")
            segment_results.append(segment)
            image_path = q4.IMAGE_ROOT / by_id[cover_id].relative_path
            if cover_id not in cover_cache:
                if q4.digest(image_path) != by_id[cover_id].sha256:
                    raise RuntimeError(f"D-b hash mismatch: {image_path.name}")
                cover_cache[cover_id] = np.asarray(Image.open(image_path).convert("L"), dtype=np.uint8)
            original = cover_cache[cover_id]
            cache_key = (cover_id, int(trial.attempt))
            if cache_key not in transform_cache:
                transform_cache[cache_key] = _transforms(original, by_id[cover_id].sha256,
                                                         int(trial.attempt))
            outputs = transform_cache[cache_key]
            rows.extend(_measure_segment_chains(segment, cover_id, original, outputs,
                                                int(trial.attempt), message_id, family,
                                                segment_index))
        # A message is exact only when both independently assigned 50-byte blocks recover.
        # Segment rows are retained; aggregation joins by message and attempt below.
        if len(rows) % 2:
            raise AssertionError("two segments per message invariant failed")
        if len(rows) % 6:
            raise AssertionError("three transform families x three chains per segment")
        if len(rows) and len(rows) % 18:
            raise AssertionError("each A4 row must yield 18 segment-chain observations")
        if time.perf_counter() - started > 1:
            print(f"G2 processed {len(rows)//18} message-attempts / {len(trials)}", flush=True)
            started = time.perf_counter()
    data = pd.DataFrame(rows)
    data.to_csv(OUT / "g2_d_b_segment_trials.csv.gz", index=False, compression="gzip")
    # Both segments must decode exactly; bootstrap unit remains the source image.
    cell = data.groupby(["message_id", "message_family", "attempt", "transform", "chain"], as_index=False).agg(
        exact_segments=("exact_segment", "sum"), segment_count=("exact_segment", "count"),
        mean_errors=("symbol_errors", "mean"), mean_erasures=("erasures", "mean"),
        orb_matches=("orb_matches", "mean"), ransac_inliers=("ransac_inliers", "mean"),
        registration_success=("registration_success", "min"),
        mean_registration_seconds=("registration_seconds", "mean"),
    )
    pair = (data.pivot_table(index=["message_id", "message_family", "attempt", "transform", "chain"],
                             columns="segment_index", values="cover_id", aggfunc="first")
            .rename(columns={0: "cover0", 1: "cover1"}).reset_index())
    cell = cell.merge(pair, on=["message_id", "message_family", "attempt", "transform", "chain"],
                      validate="one_to_one")
    cell["exact_message"] = (cell.exact_segments == cell.segment_count).astype(int)
    cell.to_csv(OUT / "g2_d_b_message_trials.csv", index=False)
    summary = cell.groupby(["transform", "chain"], as_index=False).agg(
        messages=("exact_message", "count"), exact_rate=("exact_message", "mean"),
        segment_rate=("exact_segments", "sum"), total_segments=("segment_count", "sum"),
        mean_orb_matches=("orb_matches", "mean"), mean_ransac_inliers=("ransac_inliers", "mean"),
        registration_rate=("registration_success", "mean"),
        mean_registration_seconds=("mean_registration_seconds", "mean"),
    )
    # Two-way cover-cluster bootstrap: each message uses one cover per segment.
    rng = np.random.default_rng(20261121)
    cover_ids = sorted(set(cell.cover0.astype(str)) | set(cell.cover1.astype(str)))
    cover_index = {cover: index for index, cover in enumerate(cover_ids)}
    clustered_ci = []
    for (transform_name, chain), group in cell.groupby(["transform", "chain"]):
        left = group.cover0.astype(str).map(cover_index).to_numpy()
        right = group.cover1.astype(str).map(cover_index).to_numpy()
        outcomes = group.exact_message.to_numpy(dtype=float)
        boot = np.empty(10_000, dtype=float)
        for b in range(len(boot)):
            counts = np.bincount(rng.integers(0, len(cover_ids), len(cover_ids)),
                                 minlength=len(cover_ids))
            weights = counts[left] * counts[right]
            boot[b] = np.average(outcomes, weights=weights) if weights.sum() else outcomes.mean()
        clustered_ci.append({"transform": transform_name, "chain": chain,
                             "cover_clusters": len(cover_ids),
                             "cluster_bootstrap_low": float(np.quantile(boot, .025)),
                             "cluster_bootstrap_high": float(np.quantile(boot, .975))})
    summary = summary.merge(pd.DataFrame(clustered_ci), on=["transform", "chain"],
                            validate="one_to_one")
    summary.to_csv(OUT / "g2_d_b_summary.csv", index=False)
    metadata = {"scope": "G development D-b only; E/C/F remain unopened",
                "D_b_manifest_sha256": q4.digest(MANIFEST), "config_id": CONFIG_ID,
                "message_ids": sorted(trials.message_id.unique().tolist()),
                "trial_rows": int(len(trials)), "segment_chain_rows": int(len(data)),
                "G0": "G-ref; receiver has the canonical pre-shared catalogue",
                "unique_selected_covers": len(cover_ids),
                "bootstrap_replicates": 10000,
                "total_wall_seconds": time.perf_counter() - run_started}
    (OUT / "g2_d_b_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
