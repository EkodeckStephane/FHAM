#!/usr/bin/env python3
"""Post-hoc P4 local-transform search; preserves the frozen Step-2 outputs."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import subprocess
import time
import zlib
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
import run_step2_geometry_development as g2
from run_step1ter_descriptor_screen import batch_hash_map, locations_and_hashes

OUT = ROOT / "results/step2/geometry"
MANIFESTS = OUT / "manifests"
CODEBOOKS = OUT / "codebooks"
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")
TRANSFORMS = ("rotation", "crop_restore", "resize_restore")
ANGLE_OFFSETS = (-0.50, -0.25, 0.0, 0.25, 0.50)
SCALE_OFFSETS = (0.90, 0.95, 1.0, 1.05, 1.10)
SHIFT_BASE = (-4, -2, 0, 2, 4)
FROZEN_MANIFEST_SHA256 = {
    "E_geo": "f932eccd1dbef7cb4290891e3b7ea9b80d0eccb50c0d96cb12d5b93c22ef48aa",
    "C_geo": "02920231b222ec61b192d364c308af37f87fd19e92eb8159e8b3bca212e04fbe",
    "F_geo": "3ef18386b490c570f23ec37de8d6bdb4a36c4a8bea9cfb0fe3ee818311131034",
}
P4_GRID = sorted(itertools.product(ANGLE_OFFSETS, SCALE_OFFSETS,
                                  SHIFT_BASE, SHIFT_BASE),
                 key=lambda x: ((x[0] / .5) ** 2 + ((x[1] - 1) / .1) ** 2
                                + (x[2] / 6) ** 2 + (x[3] / 6) ** 2, x))
P4_GRID = [(a, s, x, y) for a, s, x, y in P4_GRID]
MESSAGE_CACHE = None
CODEBOOK_CACHE = {}
CODEBOOKS_ACTIVE = [None]


def _feature(image):
    detector = ORB(n_keypoints=800, fast_threshold=0.04)
    try:
        detector.detect_and_extract(image.astype(np.float32) / 255.0)
        return detector
    except RuntimeError:
        return None


def _estimate_model(reference, attacked):
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
    return model, len(pairs), int(inliers.sum())


def _aligned(attacked, model):
    image = warp(attacked, inverse_map=model, output_shape=attacked.shape,
                 order=1, mode="constant", cval=0, preserve_range=True)
    return np.clip(np.rint(image), 0, 255).astype(np.uint8)


def _transform_for_offset(base, offset, side):
    angle, scale, dx, dy = offset
    delta = SimilarityTransform(scale=scale, rotation=np.deg2rad(angle),
                                translation=(dx * side / 256, dy * side / 256))
    return SimilarityTransform(matrix=base.params @ delta.params)


def _robust_codebook(image, cover_id, image_sha):
    cached = CODEBOOK_CACHE.get(cover_id)
    if cached is not None:
        return cached
    path = CODEBOOKS / str(CODEBOOKS_ACTIVE[0]) / f"{Path(cover_id).stem}.csv.gz"
    if path.exists():
        df = pd.read_csv(path)
        if "source_sha256" not in df or (image_sha is not None and not df.source_sha256.eq(str(image_sha)).all()):
            raise RuntimeError(f"existing codebook provenance mismatch: {path}")
        locations = [q4.Location(int(r.x), int(r.y), int(r.arrangement))
                     for r in df.itertuples(index=False)]
        data = (locations, df.hash_value.to_numpy(dtype=np.int16),
                df.robust.to_numpy(dtype=bool), df.s_hat.to_numpy(dtype=np.float64))
        CODEBOOK_CACHE[cover_id] = data
        return data

    profile, locations, _lookup, base = locations_and_hashes(image, "mean_ordinal")
    expected_positions = 1764 if image.shape[0] == 256 else 7056 if image.shape[0] == 512 else None
    if profile != 12 or expected_positions is None or len(locations) != expected_positions:
        raise RuntimeError(f"unexpected codebook geometry for {cover_id}: {profile}, {len(locations)}")
    flips = {family: np.zeros(len(locations), dtype=np.uint16) for family in ("jpeg", "noise")}
    attacks = q4.draw_development_attacks(image, image_sha)
    for family, variants in attacks.items():
        for attacked, _q, _sigma in variants:
            current = batch_hash_map(attacked, "mean_ordinal", 12, locations)
            flips[family] += np.fromiter((current[loc] != base[loc] for loc in locations),
                                         dtype=np.uint16, count=len(locations))
    robust = (flips["jpeg"] == 0) & (flips["noise"] == 0)
    total_flips = flips["jpeg"] + flips["noise"]
    s_hat = np.where(robust, 1.0, (101.0 - total_flips) / 102.0)
    hashes = np.fromiter((base[loc] for loc in locations), dtype=np.int16, count=len(locations))
    df = pd.DataFrame({"position_index": np.arange(len(locations), dtype=np.int32),
                       "x": [p.x for p in locations], "y": [p.y for p in locations],
                       "arrangement": [p.arrangement for p in locations],
                       "hash_value": hashes, "jpeg_flips": flips["jpeg"],
                       "noise_flips": flips["noise"], "robust": robust.astype(np.uint8),
                       "s_hat": s_hat, "source_sha256": str(image_sha)})
    CODEBOOKS.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, compression="gzip")
    data = (locations, hashes, robust, s_hat.astype(np.float64))
    CODEBOOK_CACHE[cover_id] = data
    return data


def _segment_assignment(cover_id, codebook, source):
    locations, hashes, robust, stability = codebook
    compressed = zlib.compress(source, 9)
    codeword, blocks = q4.rs_encode(compressed, 10)
    allowed = robust.copy()
    cap = int(np.floor(.05 * len(codeword)))
    unstable = np.flatnonzero(~robust)
    order = sorted(unstable.tolist(), key=lambda j: (-float(stability[j]), j))
    if cap:
        allowed[np.asarray(order[:cap], dtype=np.int32)] = True
    assignment = q4.assignment_graph(codeword, hashes, stability, robust,
                                     allowed, 4, blocks, 10, 5)
    return {"cover_id": cover_id, "locations": locations, "hashes": hashes,
            "robust": robust, "stability": stability, "source": source,
            "compressed": compressed, "codeword": codeword, "blocks": blocks,
            "assignment": assignment}


def _decode(segment, image):
    positions = segment["assignment"]["positions"]
    used = np.unique(positions[positions >= 0]).astype(np.int32)
    active_locations = [segment["locations"][int(j)] for j in used]
    transformed = batch_hash_map(image, "mean_ordinal", 12, active_locations)
    recv = np.zeros(len(segment["codeword"]), dtype=np.uint8)
    actual = np.frombuffer(segment["codeword"], dtype=np.uint8)
    errors = 0
    for i, j in enumerate(positions):
        if j < 0:
            continue
        loc = segment["locations"][int(j)]
        value = int(transformed[loc]) + int(segment["assignment"]["displacements"][i])
        value = min(255, max(0, value))
        recv[i] = value
        errors += int(value != int(actual[i]))
    rebuilt = bytearray()
    total_erasures = 0
    try:
        for block in segment["blocks"]:
            start, end = block["cw_start"], block["cw_start"] + block["cw_len"]
            erasures = np.flatnonzero(positions[start:end] < 0).tolist()
            total_erasures += len(erasures)
            if len(erasures) > block["parity"]:
                return False, total_erasures, errors, None
            chunk = bytes(recv[start:end])
            if block["parity"]:
                codec = q4.RSCodec(block["parity"], nsize=255, fcr=0,
                                   generator=2, prim=0x11D, c_exp=8)
                decoded = bytes(codec.decode(chunk, erase_pos=erasures)[0])
            elif erasures:
                return False, total_erasures, errors, None
            else:
                decoded = chunk
            rebuilt.extend(decoded)
        recovered = zlib.decompress(bytes(rebuilt))
        return recovered == segment["source"], total_erasures, errors, recovered
    except Exception:
        return False, total_erasures, errors, None


def _p4(segment, attacked, model, side, deadline=None):
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    last = (False, len(segment["codeword"]), len(segment["codeword"]), None)
    if model is None:
        return {"exact": 0, "erasures": last[1], "symbol_errors": last[2],
                "candidates_tested": 0, "cpu_seconds": time.process_time() - cpu_start,
                "wall_seconds": time.perf_counter() - wall_start,
                "recovered": None, "winning_angle_offset": None, "winning_scale_factor": None,
                "winning_dx": None, "winning_dy": None}
    tested = 0
    for rank, offset in enumerate(P4_GRID, 1):
        if deadline is not None and time.process_time() >= deadline:
            break
        candidate = _transform_for_offset(model, offset, side)
        aligned = _aligned(attacked, candidate)
        last = _decode(segment, aligned)
        tested = rank
        if last[0]:
            return {"exact": 1, "erasures": int(last[1]), "symbol_errors": int(last[2]),
                    "candidates_tested": rank, "cpu_seconds": time.process_time() - cpu_start,
                    "wall_seconds": time.perf_counter() - wall_start,
                    "recovered": last[3],
                    "winning_angle_offset": offset[0], "winning_scale_factor": offset[1],
                    "winning_dx": offset[2] * side / 256, "winning_dy": offset[3] * side / 256}
    return {"exact": 0, "erasures": int(last[1]), "symbol_errors": int(last[2]),
            "candidates_tested": tested, "cpu_seconds": time.process_time() - cpu_start,
            "wall_seconds": time.perf_counter() - wall_start,
            "recovered": last[3],
            "winning_angle_offset": None, "winning_scale_factor": None,
            "winning_dx": None, "winning_dy": None}


def _variants(image, cover_sha, attempt):
    return g2._transforms(image, cover_sha, attempt)


def _image_from_manifest(row):
    path = Path(row.absolute_path) if hasattr(row, "absolute_path") else q4.IMAGE_ROOT / str(row.relative_path)
    if q4.digest(path) != str(row.sha256):
        raise RuntimeError(f"image SHA-256 mismatch: {path}")
    return np.asarray(Image.open(path).convert("L"), dtype=np.uint8)


def _messages():
    global MESSAGE_CACHE
    if MESSAGE_CACHE is None:
        MESSAGE_CACHE = q4.compressed_messages()
    return MESSAGE_CACHE


def _run_d_b(attempts_per_message: int):
    manifest = pd.read_csv(q4.INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    by_id = {str(r.source_id): r for r in manifest.itertuples(index=False)}
    trial_path = q4.OUT / "A4_segmented_trials.csv.gz"
    trials = pd.read_csv(trial_path, compression="gzip", low_memory=False)
    trials = trials[(trials.config_id == 210) & (trials["index"] == 0)]
    chosen = []
    for family in FAMILIES:
        subset = trials[trials.family == family].sort_values("attempt")
        chosen.extend(subset.head(attempts_per_message).to_dict("records"))
    return _run_trials("D_b_posthoc", chosen, by_id, read_new_codebooks=False)


def _save_new_assignments(dataset, message_id, per_segment):
    # Assignment payloads are serialized as JSON/arrays in a compressed NPZ for resumption.
    path = CODEBOOKS / "assignments" / dataset
    path.mkdir(parents=True, exist_ok=True)
    out = path / f"{message_id}.npz"
    arrays = {}
    for si, solutions in enumerate(per_segment):
        for ci, (cover_id, segment) in enumerate(solutions.items()):
            prefix = f"s{si}_c{ci}_"
            arrays[prefix + "cover_id"] = np.asarray(cover_id)
            arrays[prefix + "source"] = np.frombuffer(segment["source"], dtype=np.uint8)
            arrays[prefix + "compressed"] = np.frombuffer(segment["compressed"], dtype=np.uint8)
            arrays[prefix + "codeword"] = np.frombuffer(segment["codeword"], dtype=np.uint8)
            arrays[prefix + "positions"] = segment["assignment"]["positions"]
            arrays[prefix + "displacements"] = segment["assignment"]["displacements"]
            arrays[prefix + "erasures"] = segment["assignment"]["erasures"].astype(np.uint8)
            arrays[prefix + "blocks"] = np.asarray([[b["cw_start"], b["cw_len"], b["parity"]]
                                                     for b in segment["blocks"]], dtype=np.int16)
    np.savez_compressed(out, **arrays)


def _load_saved_assignment(dataset, message_id, segment_index, cover_id):
    path = CODEBOOKS / "assignments" / dataset / f"{message_id}.npz"
    archive = np.load(path, allow_pickle=False)
    prefixes = [k[:-8] for k in archive.files if k.startswith(f"s{segment_index}_c") and k.endswith("cover_id")]
    for prefix in prefixes:
        if str(archive[prefix + "cover_id"].item()) != cover_id:
            continue
        CODEBOOKS_ACTIVE[0] = dataset
        locations, hashes, robust, stability = _robust_codebook(None, cover_id, None)
        blocks_arr = archive[prefix + "blocks"]
        blocks = [{"cw_start": int(a), "cw_len": int(b), "parity": int(c)} for a, b, c in blocks_arr]
        codeword = archive[prefix + "codeword"].tobytes()
        positions = archive[prefix + "positions"]
        assignment = {"positions": positions,
                      "displacements": archive[prefix + "displacements"],
                      "erasures": archive[prefix + "erasures"].astype(bool),
                      "parity_ok": True}
        return {"cover_id": cover_id, "locations": locations, "hashes": hashes,
                "robust": robust, "stability": stability,
                "source": archive[prefix + "source"].tobytes(),
                "compressed": archive[prefix + "compressed"].tobytes(),
                "codeword": codeword, "blocks": blocks, "assignment": assignment}
    raise KeyError(f"saved segment assignment unavailable: {dataset}/{message_id}/{segment_index}/{cover_id}")


def _run_trials(dataset, trial_rows, by_id, read_new_codebooks):
    messages = _messages()
    trial_rows = sorted(trial_rows, key=lambda r: (r["family"], int(r["attempt"])))
    segment_path = OUT / f"p4_{dataset}_segment_trials.csv.gz"
    message_path = OUT / f"p4_{dataset}_message_trials.csv"
    rows = pd.read_csv(segment_path, compression="gzip").to_dict("records") if segment_path.exists() else []
    message_rows = pd.read_csv(message_path).to_dict("records") if message_path.exists() else []
    completed_counts = {}
    for row in message_rows:
        key = (str(row["message_id"]), int(row["attempt"]))
        completed_counts[key] = completed_counts.get(key, 0) + 1
    completed = {key for key, count in completed_counts.items() if count == len(TRANSFORMS) * 4}
    trial_rows = [r for r in trial_rows if (str(r["message_id"]), int(r["attempt"])) not in completed]
    image_cache = {}
    for n, trial in enumerate(trial_rows, 1):
        message_id = trial["message_id"]
        family = trial["family"]
        source = messages[message_id][2]
        if not int(trial["feasible"]):
            for transform_name in TRANSFORMS:
                for chain in ("P1", "P2", "P3", "P4"):
                    message_rows.append({"dataset": dataset, "message_id": message_id,
                                         "family": family, "attempt": int(trial["attempt"]),
                                         "transform": transform_name, "chain": chain,
                                         "assignment_feasible": 0, "exact_message": 0,
                                         "cover0": "", "cover1": "",
                                         "p4_candidates_total": 0, "p4_cpu_seconds": 0.0,
                                         "p4_wall_seconds": 0.0})
            if n % 5 == 0:
                _persist_trials(dataset, rows, message_rows)
            continue
        selected = str(trial["selected_covers"]).split(";")
        if len(selected) != 2:
            raise RuntimeError(f"expected two selected covers: {dataset}/{message_id}/{trial['attempt']}")
        segments = []
        for si, (cover_id, raw) in enumerate(zip(selected, (source[:50], source[50:]))):
            row = by_id[cover_id]
            if cover_id not in image_cache:
                image_cache[cover_id] = _image_from_manifest(row)
            if read_new_codebooks:
                segment = _load_saved_assignment(dataset, message_id, si, cover_id)
            else:
                codebook = q4.load_codebook(cover_id)
                segment = _segment_assignment(cover_id, codebook, raw)
            if not segment["assignment"]["parity_ok"]:
                raise RuntimeError(f"selected segment assignment is not feasible: {dataset}/{message_id}/{cover_id}")
            segments.append(segment)
        segment_results = []
        for transform_name in TRANSFORMS:
            p4_deadline = time.process_time() + 60.0
            transform_data = []
            for si, segment in enumerate(segments):
                cover_id = segment["cover_id"]
                original = image_cache[cover_id]
                image_sha = str(by_id[cover_id].sha256)
                variants = _variants(original, image_sha, int(trial["attempt"]))
                attacked, true_model, severity = variants[transform_name]
                registration_wall_started = time.perf_counter()
                registration_cpu_started = time.process_time()
                model, matches, inliers = _estimate_model(original, attacked)
                registration_wall_seconds = time.perf_counter() - registration_wall_started
                registration_cpu_seconds = time.process_time() - registration_cpu_started
                transform_data.append((si, segment, cover_id, original, attacked,
                                       true_model, severity, model, matches, inliers,
                                       registration_cpu_seconds, registration_wall_seconds))
            for (si, segment, cover_id, original, attacked, true_model, severity,
                 model, matches, inliers, registration_cpu_seconds,
                 registration_wall_seconds) in transform_data:
                p4 = _p4(segment, attacked, model, original.shape[0], p4_deadline)
                p4["cpu_seconds"] += registration_cpu_seconds
                p4["wall_seconds"] += registration_wall_seconds
                p1 = _decode(segment, attacked)
                p2 = _decode(segment, _aligned(attacked, model)) if model is not None else (False, len(segment["codeword"]), len(segment["codeword"]), None)
                oracle = warp(attacked, inverse_map=true_model, output_shape=original.shape,
                              order=1, mode="constant", cval=0, preserve_range=True)
                oracle = np.clip(np.rint(oracle), 0, 255).astype(np.uint8)
                p3 = _decode(segment, oracle)
                row = {"dataset": dataset, "message_id": message_id, "family": family,
                       "attempt": int(trial["attempt"]), "segment_index": si,
                       "cover_id": cover_id, "transform": transform_name,
                       "severity": severity, "orb_matches": matches,
                       "ransac_inliers": inliers, "registration_success": int(model is not None),
                       "P1_exact_segment": int(p1[0]), "P1_erasures": int(p1[1]),
                       "P1_symbol_errors": int(p1[2]),
                       "P2_exact_segment": int(p2[0]), "P2_erasures": int(p2[1]),
                       "P2_symbol_errors": int(p2[2]),
                       "P3_exact_segment": int(p3[0]), "P3_erasures": int(p3[1]),
                       "P3_symbol_errors": int(p3[2]),
                       "P4_exact_segment": int(p4["exact"]), "P4_erasures": p4["erasures"],
                       "P4_symbol_errors": p4["symbol_errors"],
                       "P4_candidates_tested": p4["candidates_tested"],
                       "P4_cpu_seconds": p4["cpu_seconds"],
                       "P4_wall_seconds": p4["wall_seconds"],
                       "P4_angle_offset": p4["winning_angle_offset"],
                       "P4_scale_factor": p4["winning_scale_factor"],
                       "P4_dx": p4["winning_dx"], "P4_dy": p4["winning_dy"],
                       "symbols_total": len(segment["codeword"]),
                       "symbols_assigned": int(np.count_nonzero(segment["assignment"]["positions"] >= 0)),
                       "registration_cpu_seconds": registration_cpu_seconds,
                       "registration_wall_seconds": registration_wall_seconds}
                row["_p1_recovered"] = p1[3]
                row["_p2_recovered"] = p2[3]
                row["_p3_recovered"] = p3[3]
                row["_p4_recovered"] = p4["recovered"]
                rows.append(row)
                segment_results.append(row)
        # The message is exact only if both source segments are recovered.
        for name in ("P1", "P2", "P3", "P4"):
            for transform_name in TRANSFORMS:
                cell = [r for r in segment_results if r["transform"] == transform_name]
                exact = int(len(cell) == 2 and all(r[f"{name}_exact_segment"] for r in cell))
                recovered = b"".join(r[f"_{name.lower()}_recovered"] or b"" for r in sorted(cell, key=lambda x: x["segment_index"]))
                expected_i1 = hashlib.sha256(source).digest()[:16]
                i1_valid = len(recovered) == len(source) and hashlib.sha256(recovered).digest()[:16] == expected_i1
                exact = int(exact and i1_valid)
                message_rows.append({"dataset": dataset, "message_id": message_id,
                                     "family": family, "attempt": int(trial["attempt"]),
                                     "transform": transform_name,
                                     "chain": name, "assignment_feasible": 1,
                                     "exact_message": exact,
                                     "cover0": selected[0], "cover1": selected[1],
                                     "p4_candidates_total": sum(r["P4_candidates_tested"] for r in cell) if name == "P4" else 0,
                                     "p4_cpu_seconds": sum(r["P4_cpu_seconds"] for r in cell) if name == "P4" else 0.0,
                                     "p4_wall_seconds": sum(r["P4_wall_seconds"] for r in cell) if name == "P4" else 0.0})
        if n % 5 == 0:
            _persist_trials(dataset, rows, message_rows)
            print(f"{dataset}: {n}/{len(trial_rows)} gallery trials complete", flush=True)
    _persist_trials(dataset, rows, message_rows)
    return rows, message_rows


def _new_dataset_trials(dataset, attempts_per_message):
    manifest_path = MANIFESTS / f"{dataset}_manifest_hash_only.csv"
    manifest_sha = q4.digest(manifest_path)
    if manifest_sha != FROZEN_MANIFEST_SHA256[dataset]:
        raise RuntimeError(f"frozen {dataset} manifest SHA-256 mismatch: {manifest_sha}")
    CODEBOOKS_ACTIVE[0] = dataset
    manifest = pd.read_csv(manifest_path, keep_default_na=False)
    if len(manifest) != 200 or not manifest.pixels_opened.astype(str).str.lower().eq("false").all():
        raise RuntimeError(f"{dataset} manifest is incomplete or was previously opened")
    if attempts_per_message != 100:
        raise RuntimeError("sealed E/C/F evaluation is frozen at exactly 100 gallery trials per message")
    run_state = OUT / f"p4_{dataset}_metadata.json"
    if run_state.exists():
        prior = json.loads(run_state.read_text(encoding="utf-8"))
        if prior.get("status") == "completed":
            raise RuntimeError(f"{dataset} has already been opened and completed; refusing a second evaluation")
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
    run_state.write_text(json.dumps({
        "status": "running", "dataset": dataset,
        "scope": "post-hoc exploratory; sealed set opened once after P4 freeze",
        "manifest_sha256": manifest_sha, "runner_sha256": q4.digest(Path(__file__)),
        "git_commit": git_commit, "pixels_opened": True,
        "pixels_opened_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "attempts_per_message": attempts_per_message,
    }, indent=2) + "\n", encoding="utf-8")
    by_id = {str(r.source_id): r for r in manifest.itertuples(index=False)}
    cover_ids = sorted(by_id)
    result = []
    messages = _messages()
    for message_id, (family, index, source, _compressed) in messages.items():
        if family not in FAMILIES or str(index) != "00" or len(source) != 100:
            continue
        orders = []
        for segment in range(2):
            segment_orders = []
            for attempt in range(attempts_per_message):
                material = f"FHAM-step2-P4-posthoc|20261121|{dataset}|{message_id}|{segment}|{attempt}"
                seed = int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")
                segment_orders.append(np.random.Generator(np.random.PCG64(seed)).permutation(cover_ids).tolist())
            orders.append(segment_orders)
        per_segment = []
        for si, raw in enumerate((source[:50], source[50:])):
            solutions = {}
            for idx_cover, (cover_id, row) in enumerate(by_id.items(), 1):
                codebook_path = CODEBOOKS / dataset / f"{Path(cover_id).stem}.csv.gz"
                if codebook_path.exists():
                    codebook = _robust_codebook(None, cover_id, str(row.sha256))
                else:
                    path = Path(row.absolute_path)
                    if q4.digest(path) != str(row.sha256):
                        raise RuntimeError(f"sealed image mismatch before evaluation: {path}")
                    image = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
                    if image.shape not in ((256, 256), (512, 512)):
                        raise RuntimeError(f"unexpected native resolution: {cover_id} {image.shape}")
                    codebook = _robust_codebook(image, cover_id, str(row.sha256))
                    del image
                solutions[cover_id] = _segment_assignment(cover_id, codebook, raw)
                if idx_cover % 25 == 0:
                    print(f"{dataset}/{message_id}/seg{si} codebook+assignment {idx_cover}/200", flush=True)
            per_segment.append(solutions)
        _save_new_assignments(dataset, message_id, per_segment)
        for attempt in range(attempts_per_message):
            selected = []
            feasible = 1
            for si in range(2):
                pair = orders[si][attempt][:2]
                selected_cover = next((cid for cid in pair if per_segment[si][cid]["assignment"]["parity_ok"]), "")
                if not selected_cover:
                    feasible = 0
                selected.append(selected_cover)
            result.append({"dataset": dataset, "message_id": message_id,
                           "family": family, "attempt": attempt,
                           "feasible": feasible, "selected_covers": ";".join(selected)})
        print(f"{dataset}/{message_id}: feasibility trials ready", flush=True)
    pd.DataFrame(result).to_csv(OUT / f"p4_{dataset}_gallery_trials.csv", index=False)
    return _run_trials(dataset, result, by_id, read_new_codebooks=True)


def _summarize(dataset):
    messages = pd.read_csv(OUT / f"p4_{dataset}_message_trials.csv")
    summary = messages.groupby(["family", "transform", "chain"], as_index=False).agg(
        attempts=("exact_message", "count"), exact_rate=("exact_message", "mean"),
        feasible_rate=("assignment_feasible", "mean"),
        mean_p4_candidates=("p4_candidates_total", "mean"),
        mean_p4_cpu_seconds=("p4_cpu_seconds", "mean"),
        mean_p4_wall_seconds=("p4_wall_seconds", "mean"))
    overall = messages.groupby(["transform", "chain"], as_index=False).agg(
        attempts=("exact_message", "count"), exact_rate=("exact_message", "mean"),
        feasible_rate=("assignment_feasible", "mean"),
        mean_p4_candidates=("p4_candidates_total", "mean"),
        mean_p4_cpu_seconds=("p4_cpu_seconds", "mean"),
        mean_p4_wall_seconds=("p4_wall_seconds", "mean"))
    overall["family"] = "ALL"
    summary = pd.concat([summary, overall], ignore_index=True)
    rng = np.random.default_rng(20261121)
    cis = []
    bootstrap_groups = [*((family, transform, chain, group) for (family, transform, chain), group
                          in messages.groupby(["family", "transform", "chain"])),
                        *(('ALL', transform, chain, group) for (transform, chain), group
                          in messages.groupby(["transform", "chain"]))]
    for family, transform, chain, group in bootstrap_groups:
        values = group.exact_message.to_numpy(dtype=float)
        c0 = group.cover0.fillna("").astype(str).to_numpy()
        c1 = group.cover1.fillna("").astype(str).to_numpy()
        # Resample selected source covers as clusters; infeasible trials remain
        # in the denominator and receive their own zero-outcome cluster.
        labels = sorted(set(c0[c0 != ""]) | set(c1[c1 != ""]))
        if labels:
            idx = {v: i for i, v in enumerate(labels)}
            missing = (c0 == "") | (c1 == "")
            missing_cluster = len(labels) + np.cumsum(missing, dtype=np.int32) - 1
            left = np.asarray([idx[x] if x else missing_cluster[i] for i, x in enumerate(c0)])
            right = np.asarray([idx[x] if x else missing_cluster[i] for i, x in enumerate(c1)])
            left[missing] = missing_cluster[missing]
            right[missing] = missing_cluster[missing]
            cluster_count = len(labels) + int(missing.sum())
            draws = np.empty(10000, dtype=float)
            for b in range(len(draws)):
                sampled = rng.integers(0, cluster_count, cluster_count)
                counts = np.bincount(sampled, minlength=cluster_count)
                weights = counts[left] * counts[right]
                draws[b] = np.average(values, weights=weights) if weights.sum() else values.mean()
            low, high = np.quantile(draws, [.025, .975])
        else:
            low, high = 0.0, 0.0
        cis.append({"family": family, "transform": transform, "chain": chain,
                    "cluster_bootstrap_low": float(low), "cluster_bootstrap_high": float(high)})
    ci_df = pd.DataFrame(cis)
    summary = summary.merge(ci_df, on=["family", "transform", "chain"], how="left")
    summary.to_csv(OUT / f"p4_{dataset}_summary.csv", index=False)
    return summary


def _persist_trials(dataset, rows, message_rows):
    private = [c for c in ("_p1_recovered", "_p2_recovered", "_p3_recovered", "_p4_recovered")
               if c in pd.DataFrame(rows).columns]
    pd.DataFrame(rows).drop(columns=private, errors="ignore").to_csv(
        OUT / f"p4_{dataset}_segment_trials.csv.gz", index=False, compression="gzip")
    pd.DataFrame(message_rows).to_csv(OUT / f"p4_{dataset}_message_trials.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=("D_b_posthoc", "E_geo", "C_geo", "F_geo"), required=True)
    parser.add_argument("--attempts-per-message", type=int, default=100)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.dataset == "D_b_posthoc":
        trials = q4.OUT / "A4_segmented_trials.csv.gz"
        if not trials.exists():
            raise RuntimeError("D-b A4 assignments are missing")
        rows, _ = _run_d_b(args.attempts_per_message)
    else:
        rows, _ = _new_dataset_trials(args.dataset, args.attempts_per_message)
    _summarize(args.dataset)
    metadata = {"scope": "post-hoc P4 extension; exploratory, not confirmatory",
                "protocol": "protocols/FHAM_etape_2_extension_posthoc_P4_sealed_2026-11-21.md",
                "dataset": args.dataset, "attempts_per_message": args.attempts_per_message,
                "timing_definition": {
                    "p4_budget": "60 seconds active process CPU time per message-transformation cell, shared across both segments; ORB/RANSAC included",
                    "reported": "P4 CPU seconds and wall-clock seconds, separately",
                },
                "p4_grid_candidates_per_segment": len(P4_GRID),
                "p4_max_candidates_per_message": 2 * len(P4_GRID),
                "p4_grid": {"angle_deg": list(ANGLE_OFFSETS), "relative_scale": list(SCALE_OFFSETS),
                            "dx_base_px": list(SHIFT_BASE), "dy_base_px": list(SHIFT_BASE)},
                "D_b_manifest_sha256": q4.digest(q4.INPUT / "D_b_images_sha256.csv") if args.dataset == "D_b_posthoc" else None,
                "sealed_manifest_sha256": FROZEN_MANIFEST_SHA256.get(args.dataset),
                "sealed_pixels_opened": args.dataset in FROZEN_MANIFEST_SHA256,
                "runner_sha256": q4.digest(Path(__file__)),
                "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                             check=True, capture_output=True, text=True).stdout.strip(),
                "grid_unique_candidates": len(set(P4_GRID)),
                "seed": 20261121,
                "status": "completed"}
    (OUT / f"p4_{args.dataset}_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(_summarize(args.dataset).to_string(index=False))


if __name__ == "__main__":
    main()
