"""Calibrate receiver-only R-a erasure flags on the selected LFW-val method."""

from __future__ import annotations

import hashlib
import json
import sys
import time
import zlib
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.config import DATASET_DIR  # noqa: E402
from fham.experiments import _attack  # noqa: E402
from fham.methods import OptimalAssignmentMethod, StabilityAwareAssignmentMethod  # noqa: E402
from fham.stability import estimate_position_stability, receiver_reliability_flags  # noqa: E402
from parameter_ablation_revision import load_messages  # noqa: E402
from stability_step1_estimate import EXTENDED_DEVELOPMENT, OLD_DEVELOPMENT, split_names  # noqa: E402
from stability_step1_pilot import SEED, _register, transform  # noqa: E402

BLOCK_SIZE = 12
BOUND = 2
Z_FLAGS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
TRANSFORMS = ("jpeg75", "noise2", "rotate1", "crop5", "resize0.8")


def jitter_images(received, seed):
    h, w = received.shape
    result = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        matrix = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
        result.append(cv2.warpAffine(
            received, matrix, (w, h), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        ))
    for i in range(4):
        rng = np.random.default_rng(seed + i)
        result.append(np.clip(
            received.astype(np.float64) + rng.normal(0, 1.0, received.shape),
            0, 255,
        ).astype(np.uint8))
    return result


def make_attacks(image, image_index):
    result = {}
    for i, name in enumerate(TRANSFORMS):
        data = transform(image, name, SEED + image_index * 101 + i, "bicubic")
        matrix = None
        attacked = data
        if isinstance(data, tuple):
            attacked, matrix = data
        if name in ("rotate1", "crop5", "resize0.8"):
            aligned, matches, inliers = _register(image, attacked)
            oracle = (cv2.warpAffine(
                attacked, matrix, (image.shape[1], image.shape[0]),
                flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0,
            ) if matrix is not None else attacked)
            result[name] = {
                "P1": attacked,
                "P2": aligned,
                "P3": oracle,
                "matches": matches,
                "inliers": inliers,
            }
        else:
            result[name] = {"P1": attacked, "P2": attacked, "P3": attacked}
    return result


def main():
    selection = json.loads(
        (ROOT / "results" / "stability_step1" / "validation_config_selection.json")
        .read_text(encoding="utf-8")
    )["selection"]
    if selection is None:
        raise RuntimeError("No eligible configuration was selected on validation")
    if selection["method"] != "S3":
        raise NotImplementedError("R-a validation currently wires the selected S3 method")
    _, val_names = split_names()
    messages = {length: load_messages(length, 3) for length in (100, 200)}
    chunks = ROOT / "results" / "stability_step1" / "receiver_validation_chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    for image_index, name in enumerate(val_names):
        raw_path = chunks / f"{name}.csv.gz"
        if raw_path.exists():
            print(f"[{image_index + 1}/100] {name}: completed, reusing", flush=True)
            continue
        image_path = DATASET_DIR / "stress" / f"{name}.png"
        image = np.asarray(Image.open(image_path).convert("L"))
        lookup = OptimalAssignmentMethod(BLOCK_SIZE, "spectral")
        lookup.build_lookup_table(image)
        locations = [loc for vals in lookup.lookup_table.values() for loc in vals]
        old_images = [
            _attack(image, attack, SEED + 10000 + image_index * 101 + i)
            for i, attack in enumerate(OLD_DEVELOPMENT)
        ]
        extended_images = []
        for i, attack in enumerate(EXTENDED_DEVELOPMENT):
            data = transform(image, attack, SEED + 20000 + image_index * 101 + i,
                             "bilinear")
            extended_images.append(data[0] if isinstance(data, tuple) else data)
        _s1, s3, _margin_rows = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", extended_images
        )
        method = StabilityAwareAssignmentMethod(
            BOUND, float(selection["lambda"]), BLOCK_SIZE, "spectral",
            residual_scale=BOUND, sparse_solver=True,
        )
        method.lookup_table, method.image_shape = lookup.lookup_table, lookup.image_shape
        method.stabilities = s3
        attacks = make_attacks(image, image_index)

        reliability = {}
        for transform_name, data in attacks.items():
            paths = ("P1", "P2", "P3") if transform_name in ("rotate1", "crop5", "resize0.8") else ("P1",)
            for path in paths:
                received = data[path]
                if received is None:
                    reliability[(transform_name, path)] = None
                    continue
                _flags, rows = receiver_reliability_flags(
                    received, locations, BLOCK_SIZE, "spectral",
                    jitter_images(received, SEED + image_index * 1009
                                  + TRANSFORMS.index(transform_name) * 31
                                  + paths.index(path) * 13),
                    z_flag=-1,
                )
                reliability[(transform_name, path)] = {
                    (int(row["x"]), int(row["y"]), int(row["arrangement"])):
                    (bool(row["any_jitter_hash_flip"]), float(row["min_margin_z"]))
                    for row in rows
                }

        rows = []
        for length in (100, 200):
            for family, sources in messages[length].items():
                for trial, source in enumerate(sources):
                    coded = zlib.compress(source, level=9)
                    payload = coded.decode("latin-1")
                    assignment = method.embed(payload, image)
                    for transform_name, data in attacks.items():
                        primary_path = "P2" if transform_name in ("rotate1", "crop5", "resize0.8") else "P1"
                        if assignment is None:
                            for z_flag in Z_FLAGS:
                                rows.append({
                                    "cover": name, "family": family, "length": length,
                                    "trial": trial, "transform": transform_name,
                                    "path": primary_path, "z_flag": z_flag,
                                    "feasible": 0, "symbols": 0, "correct": 0,
                                    "flagged": 0, "flagged_wrong": 0,
                                    "silent_errors": 0, "exact": 0,
                                    "source_exact": 0,
                                    "registration_success": int(data.get("P2") is not None),
                                })
                            continue
                        received = data[primary_path]
                        map_features = reliability[(transform_name, primary_path)]
                        if received is None or map_features is None:
                            recovered = bytes(len(coded))
                            correct = np.zeros(len(coded), dtype=bool)
                            feature_values = [(False, 0.0)] * len(assignment.locations)
                            registration_success = 0
                        else:
                            decoded = method.extract(assignment, received).encode("latin-1")
                            recovered = decoded
                            correct = np.asarray([
                                a == b for a, b in zip(coded, decoded)
                            ], dtype=bool)
                            feature_values = [
                                map_features[(loc.x, loc.y, loc.arrangement)]
                                for loc in assignment.locations
                            ]
                            registration_success = 1
                        try:
                            source_exact = int(zlib.decompress(recovered) == source)
                        except zlib.error:
                            source_exact = 0
                        flips = np.asarray([item[0] for item in feature_values], dtype=bool)
                        min_z = np.asarray([item[1] for item in feature_values], dtype=float)
                        errors = ~correct
                        for z_flag in Z_FLAGS:
                            flagged = flips | (min_z < z_flag)
                            rows.append({
                                "cover": name, "family": family, "length": length,
                                "trial": trial, "transform": transform_name,
                                "path": primary_path, "z_flag": z_flag,
                                "feasible": 1, "symbols": len(coded),
                                "correct": int(correct.sum()),
                                "flagged": int(flagged.sum()),
                                "flagged_wrong": int((flagged & errors).sum()),
                                "silent_errors": int((~flagged & errors).sum()),
                                "exact": int(recovered == coded),
                                "source_exact": source_exact,
                                "registration_success": registration_success,
                            })
        pd.DataFrame(rows).to_csv(raw_path, index=False, compression="gzip")
        print(f"[{image_index + 1}/100] {name}: receiver flags complete; "
              f"{time.perf_counter() - started:.1f}s", flush=True)

    raw = pd.concat([pd.read_csv(path) for path in sorted(chunks.glob("*.csv.gz"))],
                    ignore_index=True)
    raw.to_csv(ROOT / "results" / "stability_step1" / "receiver_validation_raw.csv.gz",
               index=False, compression="gzip")
    raw["class"] = np.where(raw["transform"].isin(["rotate1", "crop5", "resize0.8"]),
                            "geometric", "photometric")
    summary = raw.groupby(["z_flag", "class", "transform", "path"],
                         as_index=False).agg(
        assignments=("feasible", "size"),
        feasibility=("feasible", "mean"),
        symbols=("symbols", "sum"),
        correct=("correct", "sum"),
        flagged=("flagged", "sum"),
        flagged_wrong=("flagged_wrong", "sum"),
        silent_errors=("silent_errors", "sum"),
        exact_messages=("exact", "sum"),
        source_exact_messages=("source_exact", "sum"),
    )
    summary["accuracy"] = summary["correct"] / summary["symbols"].replace(0, np.nan)
    summary["f_flagged_fraction"] = summary["flagged"] / summary["symbols"].replace(0, np.nan)
    summary["s_silent_error_fraction"] = summary["silent_errors"] / summary["symbols"].replace(0, np.nan)
    summary["R_max"] = 1 - summary["f_flagged_fraction"] - 2 * summary["s_silent_error_fraction"]
    summary["flag_precision"] = summary["flagged_wrong"] / summary["flagged"].replace(0, np.nan)
    error_count = summary["symbols"] - summary["correct"]
    summary["flag_recall"] = summary["flagged_wrong"] / error_count.replace(0, np.nan)
    summary.to_csv(ROOT / "results" / "stability_step1" / "receiver_validation_summary.csv",
                   index=False)
    aggregate = raw.groupby(["z_flag", "class"], as_index=False).agg(
        symbols=("symbols", "sum"),
        correct=("correct", "sum"),
        flagged=("flagged", "sum"),
        flagged_wrong=("flagged_wrong", "sum"),
        silent_errors=("silent_errors", "sum"),
        exact_messages=("exact", "sum"),
        source_exact_messages=("source_exact", "sum"),
    )
    aggregate["accuracy"] = aggregate["correct"] / aggregate["symbols"].replace(0, np.nan)
    aggregate["f"] = aggregate["flagged"] / aggregate["symbols"].replace(0, np.nan)
    aggregate["s"] = aggregate["silent_errors"] / aggregate["symbols"].replace(0, np.nan)
    aggregate["R_max"] = 1 - aggregate["f"] - 2 * aggregate["s"]
    overall = raw.groupby("z_flag", as_index=False).agg(
        symbols=("symbols", "sum"), flagged=("flagged", "sum"),
        silent_errors=("silent_errors", "sum"),
    )
    overall["f"] = overall["flagged"] / overall["symbols"].replace(0, np.nan)
    overall["s"] = overall["silent_errors"] / overall["symbols"].replace(0, np.nan)
    overall["R_max"] = 1 - overall.f - 2 * overall.s
    best = overall.sort_values(["R_max", "f", "z_flag"],
                               ascending=[False, True, False]).iloc[0]
    result = {
        "selected_configuration": selection,
        "z_flag_grid": list(Z_FLAGS),
        "chosen_z_flag": float(best.z_flag),
        "overall_R_max": float(best.R_max),
        "overall_flagged_fraction": float(best.f),
        "overall_silent_error_fraction": float(best.s),
        "class_summary": aggregate.to_dict(orient="records"),
        "test_remains_sealed": True,
        "elapsed_seconds": time.perf_counter() - started,
    }
    (ROOT / "results" / "stability_step1" / "receiver_validation_selection.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(aggregate.to_string(index=False), flush=True)
    print(json.dumps({k: result[k] for k in (
        "chosen_z_flag", "overall_R_max", "overall_flagged_fraction",
        "overall_silent_error_fraction", "elapsed_seconds"
    )}, indent=2), flush=True)


if __name__ == "__main__":
    main()
