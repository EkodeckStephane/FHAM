"""Run Step 1bis profile screening on BOWS2-A and the preregistered Q0 bridge.

BOWS2-C is never read by this script. Each input image is opened only for the
profile, assignment, and recovery metrics described in the frozen protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fham.methods import OptimalAssignmentMethod
from fham.stability import estimate_position_stability
import stability_step1_estimate as estimate
import stability_step1_pilot as pilot
import stability_step1_validation as validation

SEED = 20261116
PROFILES = (12, 24, 36, 48)
FAMILIES = ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated")
PERFORMANCE_LENGTHS = (100, 200)
FEASIBILITY_LENGTHS = (50, 100, 200)
METHODS = ("S0", "S3")
LAMBDA_S3 = 0.5
DEVELOPMENT = estimate.EXTENDED_DEVELOPMENT
TRANSFORMS = validation.TRANSFORMS
BOWS2_ROOT = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
OUT = ROOT / "results" / "stability_step1" / "step1bis" / "profile_stage"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"))


def fixed_messages(indices: tuple[int, ...]) -> dict[tuple[str, int, int], bytes]:
    messages = {}
    root = ROOT / "dataset" / "messages"
    for family in FAMILIES:
        for length in PERFORMANCE_LENGTHS:
            for index in indices:
                path = root / family / f"{family}_{length}_{index:02d}.bin"
                data = path.read_bytes()
                if len(data) != length:
                    raise RuntimeError(f"Unexpected length in {path}: {len(data)}")
                messages[(family, length, index)] = data
    return messages


def development_images(image: np.ndarray, image_index: int) -> list[np.ndarray]:
    transformed = []
    for index, name in enumerate(DEVELOPMENT):
        result = pilot.transform(
            image, name, SEED + 50000 + image_index * 101 + index, "bilinear"
        )
        transformed.append(result[0] if isinstance(result, tuple) else result)
    return transformed


def build_configurations(image: np.ndarray, profile: int, image_index: int):
    validation.BLOCK_SIZE = profile
    lookup = OptimalAssignmentMethod(profile, "spectral")
    lookup.build_lookup_table(image)
    locations = [location for group in lookup.lookup_table.values() for location in group]
    dev = development_images(image, image_index)
    empirical, continuous, _ = estimate_position_stability(
        image, locations, profile, "spectral", dev
    )
    configurations = validation._configs(lookup, empirical, empirical, continuous)
    selected = {}
    for name, lam, _tau, method in configurations:
        if name == "S0":
            selected["S0"] = method
        elif name == "S3" and lam == LAMBDA_S3:
            selected["S3"] = method
    if set(selected) != set(METHODS):
        raise RuntimeError(f"S0/S3 configuration missing at profile {profile}")
    return lookup, locations, selected


def make_record(image_path: Path, corpus: str, split: str, source_id: str, index: int):
    image = image_gray(image_path)
    if corpus == "BOWS2" and image.shape != (256, 256):
        raise RuntimeError(f"BOWS2 shape mismatch for {source_id}: {image.shape}")
    return {
        "path": image_path,
        "corpus": corpus,
        "split": split,
        "source_id": source_id,
        "index": index,
        "image": image,
        "sha256": sha256(image_path),
    }


def process_cover(record: dict, profiles: tuple[int, ...], messages: dict,
                  q0_only: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    image = record["image"]
    methods_by_profile = {}
    for profile in profiles:
        methods_by_profile[profile] = build_configurations(
            image, profile, record["index"]
        )
    attacked_by_transform = validation._cover_transforms(image, record["index"])
    assignment_rows = []
    recovery_rows = []
    feasibility_rows = []

    for profile in profiles:
        _lookup, _locations, selected = methods_by_profile[profile]
        for (family, source_length, message_index), source in messages.items():
            compressed = zlib.compress(source, level=9)
            payload = compressed.decode("latin-1")
            for method_name, method in selected.items():
                started = time.perf_counter()
                assignment = method.embed(payload, image)
                solve_ms = (time.perf_counter() - started) * 1000
                assignment_rows.append({
                    "cover": record["source_id"],
                    "cover_sha256": record["sha256"],
                    "corpus": record["corpus"],
                    "split": record["split"],
                    "profile": profile,
                    "n_locations": (image.shape[0] // profile) * (image.shape[1] // profile) * 4,
                    "token_bits": int(np.ceil(np.log2((image.shape[0] // profile) * (image.shape[1] // profile) * 4))),
                    "bound": 2,
                    "family": family,
                    "source_length": source_length,
                    "message_index": message_index,
                    "message_sha256": hashlib.sha256(source).hexdigest(),
                    "compressed_length": len(compressed),
                    "method": method_name,
                    "lambda": 1.0 if method_name == "S0" else LAMBDA_S3,
                    "feasible": int(assignment is not None),
                    "D1": float(np.mean(np.abs(assignment.displacements))) if assignment else np.nan,
                    "max_abs_delta": int(np.max(np.abs(assignment.displacements))) if assignment else np.nan,
                    "n_symbols": len(payload),
                    "solve_ms": solve_ms,
                })

                conditions = [("identity", "P0", image, None, None, None)]
                for transform_name, paths in attacked_by_transform.items():
                    for path_name in (("P1", "P3") if transform_name not in ("rotate1", "crop5", "resize0.8")
                                      else ("P1", "P2", "P3")):
                        conditions.append((
                            transform_name, path_name, paths.get(path_name),
                            paths.get("matches"), paths.get("inliers"),
                            int(paths.get(path_name) is not None) if path_name == "P2" else 1,
                        ))
                for transform_name, path_name, received, matches, inliers, registration_ok in conditions:
                    if assignment is None or received is None:
                        recovered = None
                    else:
                        recovered = method.extract(assignment, received).encode("latin-1")
                    correct = (
                        sum(left == right for left, right in zip(compressed, recovered))
                        if recovered is not None else 0
                    )
                    try:
                        source_exact = int(zlib.decompress(recovered) == source) if recovered is not None else 0
                    except zlib.error:
                        source_exact = 0
                    recovery_rows.append({
                        "cover": record["source_id"],
                        "cover_sha256": record["sha256"],
                        "corpus": record["corpus"],
                        "split": record["split"],
                        "profile": profile,
                        "family": family,
                        "source_length": source_length,
                        "message_index": message_index,
                        "method": method_name,
                        "lambda": 1.0 if method_name == "S0" else LAMBDA_S3,
                        "transform": transform_name,
                        "path": path_name,
                        "feasible": int(assignment is not None),
                        "registration_success": registration_ok,
                        "keypoint_matches": matches if path_name == "P2" else np.nan,
                        "ransac_inliers": inliers if path_name == "P2" else np.nan,
                        "n_symbols": len(compressed),
                        "n_correct": correct,
                        "accuracy": correct / len(compressed),
                        "exact": int(recovered == compressed) if recovered is not None else 0,
                        "source_exact": source_exact,
                        "solve_ms": solve_ms,
                    })

        # Feasibility-only lengths include 50; robustness uses 100/200 above.
        for method_name, method in selected.items():
            for family in FAMILIES:
                for source_length in FEASIBILITY_LENGTHS:
                    path = ROOT / "dataset" / "messages" / family / f"{family}_{source_length}_00.bin"
                    source = path.read_bytes()
                    if len(source) != source_length:
                        raise RuntimeError(f"Unexpected length in {path}")
                    compressed = zlib.compress(source, level=9).decode("latin-1")
                    feasible = method.embed(compressed, image) is not None
                    feasibility_rows.append({
                        "cover": record["source_id"],
                        "corpus": record["corpus"],
                        "split": record["split"],
                        "profile": profile,
                        "method": method_name,
                        "family": family,
                        "source_length": source_length,
                        "compressed_length": len(compressed),
                        "n_locations": (image.shape[0] // profile) * (image.shape[1] // profile) * 4,
                        "feasible": int(feasible),
                    })
    return pd.DataFrame(assignment_rows), pd.DataFrame(recovery_rows), pd.DataFrame(feasibility_rows)


def run_group(records: list[dict], profiles: tuple[int, ...], messages: dict, group_name: str):
    group_dir = OUT / group_name
    group_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for index, record in enumerate(records):
        assignments, recoveries, feasibility = process_cover(record, profiles, messages)
        assignments.to_csv(group_dir / f"{record['source_id']}_assignments.csv.gz", index=False, compression="gzip")
        recoveries.to_csv(group_dir / f"{record['source_id']}_recovery.csv.gz", index=False, compression="gzip")
        feasibility.to_csv(group_dir / f"{record['source_id']}_feasibility.csv.gz", index=False, compression="gzip")
        print(f"[{group_name} {index + 1}/{len(records)}] {record['source_id']} complete", flush=True)
    elapsed = time.perf_counter() - started
    (group_dir / "run.json").write_text(json.dumps({
        "group": group_name,
        "covers": [record["source_id"] for record in records],
        "cover_sha256": {record["source_id"]: record["sha256"] for record in records},
        "profiles": list(profiles),
        "messages": [
            {"family": family, "source_length": length, "index": index,
             "sha256": hashlib.sha256(data).hexdigest()}
            for (family, length, index), data in messages.items()
        ],
        "seed_root": SEED,
        "development_transforms": list(DEVELOPMENT),
        "validation_transforms": list(TRANSFORMS),
        "method_configurations": ["S0", "S3 lambda=0.5"],
        "runtime_seconds": elapsed,
        "step1bis_author_go_for_phase_b": False,
        "script_sha256": sha256(Path(__file__)),
        "environment_sha256": sha256(ROOT / "results" / "stability_step1" / "step1bis_environment.json"),
    }, indent=2), encoding="utf-8")
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=("profile", "q0", "all"), default="all")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    split_path = ROOT / "results" / "stability_step1" / "step1bis" / "manifest" / "split_manifest.csv"
    split = pd.read_csv(split_path)
    source_order = split.sort_values("selection_rank")
    a_rows = source_order[source_order.split.eq("A")].head(100)
    b_rows = source_order[source_order.split.eq("B")].head(100)
    a_records = [make_record(BOWS2_ROOT / row.relative_path, "BOWS2", "A", row.source_id, i)
                 for i, row in enumerate(a_rows.itertuples(index=False))]
    b_records = [make_record(BOWS2_ROOT / row.relative_path, "BOWS2", "B", row.source_id, i)
                 for i, row in enumerate(b_rows.itertuples(index=False))]
    _, lfw_names = estimate.split_names()
    lfw_records = [make_record(ROOT / "dataset" / "stress" / f"{name}.png", "LFW", "validation", name, i)
                   for i, name in enumerate(lfw_names)]

    elapsed = {}
    if args.group in ("profile", "all"):
        elapsed["profile_A"] = run_group(a_records, PROFILES, fixed_messages((0,)), "A_profile_screen")
    if args.group in ("q0", "all"):
        elapsed["q0_B"] = run_group(b_records, (12,), fixed_messages((0,)), "B_q0_bridge")
        elapsed["q0_LFW"] = run_group(lfw_records, (12,), fixed_messages((0,)), "LFW_q0_bridge")
    print(json.dumps(elapsed, indent=2), flush=True)


if __name__ == "__main__":
    main()
