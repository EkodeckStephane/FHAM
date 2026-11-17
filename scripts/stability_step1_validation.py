"""Evaluate the frozen S0-S4 configuration grid on LFW-val (no sealed test)."""

from __future__ import annotations

import hashlib
import argparse
import json
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.config import DATASET_DIR  # noqa: E402
from fham.experiments import _attack  # noqa: E402
from fham.methods import OptimalAssignmentMethod, StabilityAwareAssignmentMethod  # noqa: E402
from fham.stability import estimate_position_stability  # noqa: E402
from parameter_ablation_revision import load_messages  # noqa: E402
from stability_step1_estimate import EXTENDED_DEVELOPMENT, OLD_DEVELOPMENT, split_names  # noqa: E402
from stability_step1_pilot import SEED, _register, transform  # noqa: E402

BLOCK_SIZE = 12
BOUND = 2
LAMBDAS = (0.5, 0.75, 0.9, 0.95, 1.0)
TAUS = (0.5, 0.8, 0.9, 0.95, 0.99)
TRANSFORMS = ("jpeg75", "noise2", "rotate1", "crop5", "resize0.8")


def _oracle_restore(attacked, matrix, shape):
    import cv2
    return cv2.warpAffine(
        attacked, matrix, (shape[1], shape[0]),
        flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )


def _new_method(lookup, scores, lam):
    method = StabilityAwareAssignmentMethod(
        BOUND, lam, BLOCK_SIZE, "spectral", residual_scale=BOUND,
        sparse_solver=True,
    )
    method.lookup_table = lookup.lookup_table
    method.image_shape = lookup.image_shape
    method.stabilities = scores
    return method


def _configs(lookup, s1, s2, s3):
    all_stable = {loc: 1.0 for values in lookup.lookup_table.values()
                  for loc in values}
    result = [("S0", None, None, _new_method(lookup, all_stable, 1.0))]
    for name, scores in (("S1", s1), ("S2", s2), ("S3", s3)):
        for lam in LAMBDAS:
            result.append((name, lam, None, _new_method(lookup, scores, lam)))
    for tau in TAUS:
        filtered = defaultdict(list)
        for value, locations in lookup.lookup_table.items():
            for location in locations:
                if s3[location] >= tau:
                    filtered[value].append(location)
        method = _new_method(lookup, {}, 1.0)
        method.lookup_table = dict(filtered) or {-1: []}
        result.append(("S4", None, tau, method))
    return result


def _cover_transforms(image, image_index):
    result = {}
    for i, name in enumerate(TRANSFORMS):
        data = transform(image, name, SEED + image_index * 101 + i, "bicubic")
        matrix = None
        attacked = data
        if isinstance(data, tuple):
            attacked, matrix = data
        result[name] = {"P1": attacked}
        if name in ("rotate1", "crop5", "resize0.8"):
            aligned, matches, inliers = _register(image, attacked)
            result[name]["P2"] = aligned
            result[name]["matches"] = matches
            result[name]["inliers"] = inliers
            result[name]["P3"] = (_oracle_restore(attacked, matrix, image.shape)
                                  if matrix is not None else attacked)
        else:
            result[name]["P3"] = attacked
            result[name]["matches"] = np.nan
            result[name]["inliers"] = np.nan
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100,
                        help="diagnostic cover limit; use default 100 for the preregistered run")
    parser.add_argument("--resume", action="store_true",
                        help="reuse covers with completed per-cover summaries")
    parser.add_argument("--step1bis-regression", action="store_true",
                        help="run only the preregistered S3, lambda=0.5 regression configuration")
    args = parser.parse_args()
    dev_names, val_names = split_names()
    val_names = val_names[:args.limit]
    messages = {
        length: load_messages(length, 3)
        for length in (100, 200)
    }
    out = ROOT / "results" / "stability_step1"
    run_suffix = "p2resize"
    chunks = out / (f"validation_chunks_{run_suffix}" if args.limit == 100
                    else f"validation_chunks_probe_{args.limit}_{run_suffix}")
    chunks.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    for image_index, name in enumerate(val_names):
        if args.resume and all((chunks / f"{name}_{suffix}.csv.gz").exists()
                               for suffix in ("cover_assignment_summary",
                                              "cover_recovery_summary")):
            print(f"[{image_index + 1}/{len(val_names)}] {name}: completed, reusing summaries",
                  flush=True)
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
            transformed = transform(image, attack, SEED + 20000 + image_index * 101 + i,
                                    "bilinear")
            extended_images.append(transformed[0] if isinstance(transformed, tuple)
                                   else transformed)
        s1, _, _ = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", old_images
        )
        s2, s3, _margin_rows = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", extended_images
        )
        attacked = _cover_transforms(image, image_index)
        configs = _configs(lookup, s1, s2, s3)
        if args.step1bis_regression:
            configs = [config for config in configs
                       if config[0] == "S3" and config[1] == 0.5]
        local_assignments, local_recovery = [], []

        for family, length, trial, source in (
            (family, length, trial, source)
            for length in (100, 200)
            for family, trials in messages[length].items()
            for trial, source in enumerate(trials)
        ):
            coded = zlib.compress(source, level=9)
            payload = coded.decode("latin-1")
            for method_name, lam, tau, method in configs:
                t0 = time.perf_counter()
                assignment = method.embed(payload, image)
                solve_ms = (time.perf_counter() - t0) * 1000
                config = f"{method_name}:lambda={lam}:tau={tau}"
                assign_row = {
                    "cover": name,
                    "corpus": "LFW",
                    "split": "validation",
                    "family": family,
                    "length": length,
                    "trial": trial,
                    "method": method_name,
                    "lambda": lam,
                    "tau": tau,
                    "config": config,
                    "feasible": int(assignment is not None),
                    "D1": (sum(abs(x) for x in assignment.displacements)
                           if assignment else np.nan),
                    "max_abs_delta": (max(map(abs, assignment.displacements))
                                      if assignment else np.nan),
                    "symbols": len(coded),
                    "solve_ms": solve_ms,
                }
                local_assignments.append(assign_row)
                if assignment is None:
                    continue
                identity = method.extract(assignment, image).encode("latin-1")
                if identity != coded:
                    raise RuntimeError(f"identity round trip failed for {name}/{config}")
                try:
                    identity_source = int(zlib.decompress(identity) == source)
                except zlib.error:
                    identity_source = 0
                local_recovery.append({
                    **assign_row, "transform": "identity", "path": "P0",
                    "n_correct": len(coded), "n_symbols": len(coded),
                    "accuracy": 1.0, "exact": 1,
                    "source_exact": identity_source,
                })
                for transform_name, paths in attacked.items():
                    path_names = ("P1", "P3") if transform_name not in ("rotate1", "crop5", "resize0.8") else ("P1", "P2", "P3")
                    for path in path_names:
                        received = paths[path]
                        if received is None:
                            local_recovery.append({
                                **assign_row, "transform": transform_name,
                                "path": path, "n_correct": 0,
                                "n_symbols": len(coded), "accuracy": 0.0,
                                "exact": 0, "source_exact": 0,
                                "registration_success": 0,
                                "keypoint_matches": paths.get("matches"),
                                "ransac_inliers": paths.get("inliers"),
                            })
                            continue
                        recovered = method.extract(assignment, received).encode("latin-1")
                        n_correct = sum(a == b for a, b in zip(coded, recovered))
                        try:
                            source_exact = int(zlib.decompress(recovered) == source)
                        except zlib.error:
                            source_exact = 0
                        local_recovery.append({
                            **assign_row,
                            "transform": transform_name,
                            "path": path,
                            "n_correct": n_correct,
                            "n_symbols": len(coded),
                            "accuracy": n_correct / len(coded),
                            "exact": int(recovered == coded),
                            "source_exact": source_exact,
                            "registration_success": int(
                                path != "P2" or paths.get("P2") is not None
                            ),
                            "keypoint_matches": paths.get("matches"),
                            "ransac_inliers": paths.get("inliers"),
                        })

        pd.DataFrame(local_assignments).to_csv(
            chunks / f"{name}_assignments.csv.gz", index=False,
            compression="gzip",
        )
        pd.DataFrame(local_recovery).to_csv(
            chunks / f"{name}_recovery.csv.gz", index=False,
            compression="gzip",
        )
        assign_frame = pd.DataFrame(local_assignments)
        recovery_frame = pd.DataFrame(local_recovery)
        if recovery_frame.empty:
            recovery_frame = pd.DataFrame(columns=[
                "config", "transform", "path", "n_correct", "exact", "source_exact"
            ])
        assign_by_config = {
            config: group for config, group in assign_frame.groupby("config")
        }
        recovery_cover_rows = []
        for config, assignment_group in assign_by_config.items():
            feasible_rows = assignment_group[assignment_group["feasible"] == 1]
            feasible_symbols = int(feasible_rows["symbols"].sum())
            expected_symbols = int(assignment_group["symbols"].sum())
            n_messages = len(assignment_group)
            for transform_name, path in (
                [("identity", "P0")]
                + [(t, p) for t in TRANSFORMS
                   for p in (("P1", "P3") if t not in ("rotate1", "crop5", "resize0.8")
                             else ("P1", "P2", "P3"))]
            ):
                rows = recovery_frame[
                    (recovery_frame["config"] == config)
                    & (recovery_frame["transform"] == transform_name)
                    & (recovery_frame["path"] == path)
                ]
                recovery_cover_rows.append({
                    "cover": name,
                    "method": assignment_group["method"].iloc[0],
                    "lambda": assignment_group["lambda"].iloc[0],
                    "tau": assignment_group["tau"].iloc[0],
                    "config": config,
                    "transform": transform_name,
                    "path": path,
                    "n_messages": n_messages,
                    "feasible_messages": int(assignment_group["feasible"].sum()),
                    "feasibility": float(assignment_group["feasible"].mean()),
                    "feasible_symbols": feasible_symbols,
                    "expected_symbols": expected_symbols,
                    "correct_symbols": int(rows["n_correct"].sum()) if len(rows) else 0,
                    "exact_messages": int(rows["exact"].sum()) if len(rows) else 0,
                    "source_exact_messages": int(rows["source_exact"].sum()) if len(rows) else 0,
                })
        pd.DataFrame(recovery_cover_rows).to_csv(
            chunks / f"{name}_cover_recovery_summary.csv.gz", index=False,
            compression="gzip",
        )
        assign_frame.groupby("config", as_index=False, dropna=False).agg(
            method=("method", "first"),
            lambda_value=("lambda", "first"),
            tau=("tau", "first"),
            assignment_trials=("feasible", "size"),
            feasible_messages=("feasible", "sum"),
            feasibility=("feasible", "mean"),
            mean_D1=("D1", "mean"),
            mean_solve_ms=("solve_ms", "mean"),
            expected_symbols=("symbols", "sum"),
        ).assign(cover=name).to_csv(
            chunks / f"{name}_cover_assignment_summary.csv.gz", index=False,
            compression="gzip",
        )
        print(f"[{image_index + 1}/100] {name}: "
              f"{len(local_assignments)} assignments; "
              f"{time.perf_counter() - started:.1f}s", flush=True)

    assignment_chunks = sorted(chunks.glob("*_cover_assignment_summary.csv.gz"))
    recovery_chunks = sorted(chunks.glob("*_cover_recovery_summary.csv.gz"))
    assignment_summary = pd.concat(
        [pd.read_csv(path) for path in assignment_chunks], ignore_index=True
    )
    recovery_summary = pd.concat(
        [pd.read_csv(path) for path in recovery_chunks], ignore_index=True
    )
    recovery_summary["accuracy_conditional"] = (
        recovery_summary["correct_symbols"]
        / recovery_summary["feasible_symbols"].replace(0, np.nan)
    )
    recovery_summary["accuracy_unconditional"] = (
        recovery_summary["correct_symbols"] / recovery_summary["expected_symbols"]
    )
    recovery_summary["exact_rate_unconditional"] = (
        recovery_summary["exact_messages"] / recovery_summary["n_messages"]
    )
    assignment_summary.to_csv(out / f"validation_assignment_summary_{run_suffix}.csv", index=False)
    recovery_summary.to_csv(out / f"validation_recovery_summary_{run_suffix}.csv", index=False)
    metadata = {
        "seed": SEED,
        "validation_names": val_names,
        "validation_cover_count": len(val_names),
        "validation_sha256": {
            name: hashlib.sha256((DATASET_DIR / "stress" / f"{name}.png").read_bytes()).hexdigest()
            for name in val_names
        },
        "profile": "spectral 12x12, B=2, zlib-9 before assignment",
        "methods": ["S0", "S1", "S2", "S3", "S4"],
        "lambda_grid": LAMBDAS,
        "tau_grid": TAUS,
        "messages_per_cover_family_length": 3,
        "source_lengths": [100, 200],
        "transforms": TRANSFORMS,
        "geometry_paths": "P1 fixed coordinates; P2 ORB/RANSAC estimate; P3 known affine oracle",
        "solver": "SciPy sparse min-weight full bipartite matching; exact objective",
        "elapsed_seconds": time.perf_counter() - started,
    }
    (out / f"validation_provenance_{run_suffix}.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    aggregate = recovery_summary.groupby(
        ["method", "lambda", "tau", "config", "transform", "path"],
        dropna=False, as_index=False,
    ).agg(
        covers=("cover", "nunique"),
        mean_feasibility=("feasibility", "mean"),
        mean_conditional_accuracy=("accuracy_conditional", "mean"),
        mean_unconditional_accuracy=("accuracy_unconditional", "mean"),
        mean_exact_rate=("exact_rate_unconditional", "mean"),
    )
    aggregate.to_csv(out / f"validation_recovery_aggregate_{run_suffix}.csv", index=False)
    print("assignment summary:")
    print(assignment_summary.groupby(
        ["method", "lambda_value", "tau"], dropna=False
    ).agg(feasibility=("feasibility", "mean"), mean_D1=("mean_D1", "mean"),
          mean_solve_ms=("mean_solve_ms", "mean")).to_string(), flush=True)
    print(f"validation sweep elapsed {metadata['elapsed_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
