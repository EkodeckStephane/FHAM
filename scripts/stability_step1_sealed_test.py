"""One-shot, locked LFW-selected Step 1 evaluation on sealed BOSSBase/COCO."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
import zlib
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = Path(r"C:\Users\User\Documents\Articles\Baleba\data\derived\multicorpus_v2_1000eval_512")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fham.config import DATASET_DIR  # noqa: E402
from fham.methods import OptimalAssignmentMethod, StabilityAwareAssignmentMethod  # noqa: E402
from fham.stability import estimate_position_stability, receiver_reliability_flags  # noqa: E402
from parameter_ablation_revision import load_messages  # noqa: E402
from stability_step1_estimate import EXTENDED_DEVELOPMENT  # noqa: E402
from stability_step1_pilot import SEED, _register, transform  # noqa: E402
from stability_step1_receiver_validation import jitter_images  # noqa: E402

OUT = ROOT / "results" / "stability_step1"
BLOCK_SIZE = 12
BOUND = 2
TEST_TRANSFORMS = (
    "jpeg60", "noise3", "rotate_neg1.5", "crop10", "resize0.7",
    "combo_rotate1_jpeg75",
)
GEOMETRIC = {"rotate_neg1.5", "crop10", "resize0.7", "combo_rotate1_jpeg75"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_frozen_commit(expected: str) -> None:
    git_safe = f"safe.directory={ROOT.as_posix()}"
    current = subprocess.run(["git", "-c", git_safe, "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
    if current != expected:
        raise RuntimeError(f"HEAD {current} differs from frozen commit {expected}")
    protected = [
        "scripts/stability_step1_sealed_test.py",
        "scripts/stability_step1_validation.py",
        "scripts/stability_step1_receiver_validation.py",
        "results/stability_step1/validation_config_selection.json",
        "results/stability_step1/receiver_validation_selection.json",
        "results/stability_step1/sealed_test_selection.csv",
    ]
    result = subprocess.run(["git", "-c", git_safe, "diff", "--quiet", expected,
                             "--", *protected],
                            cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError("A frozen Step 1 code/configuration file changed after commit")


def attack_set(image: np.ndarray, image_index: int) -> dict[str, dict]:
    result = {}
    for i, name in enumerate(TEST_TRANSFORMS):
        seed = SEED + 30000 + image_index * 101 + i
        matrix = None
        if name == "combo_rotate1_jpeg75":
            rotated, matrix = transform(image, "rotate1", seed, "bicubic")
            attacked = transform(rotated, "jpeg75", seed + 1, "bicubic")
        else:
            transform_name = {
                "rotate_neg1.5": "rotate-1.5",
                "crop10": "crop10",
                "resize0.7": "resize0.7",
                "jpeg60": "jpeg60",
                "noise3": "noise3",
            }[name]
            generated = transform(image, transform_name, seed, "bicubic")
            if isinstance(generated, tuple):
                attacked, matrix = generated
            else:
                attacked = generated
        paths = {"P1": attacked}
        if name in GEOMETRIC:
            aligned, matches, inliers = _register(image, attacked)
            paths["P2"] = aligned
            paths["matches"] = matches
            paths["inliers"] = inliers
            if matrix is None:
                paths["P3"] = attacked
            else:
                paths["P3"] = cv2.warpAffine(
                    attacked, matrix, (image.shape[1], image.shape[0]),
                    flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0,
                )
        else:
            paths["P3"] = attacked
        result[name] = paths
    return result


def load_gray_512(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L").resize(
            (512, 512), Image.Resampling.LANCZOS
        ))


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials <= 0:
        return float("nan"), float("nan")
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    margin = z * np.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return float(center - margin), float(center + margin)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-commit", required=True,
                        help="Git commit containing the frozen method, parameters, and test manifest")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT,
                        help="Root containing the hashed BOSSBase and COCO PNG candidates")
    args = parser.parse_args()
    require_frozen_commit(args.frozen_commit)

    selection = json.loads((OUT / "validation_config_selection.json").read_text(encoding="utf-8"))["selection"]
    receiver = json.loads((OUT / "receiver_validation_selection.json").read_text(encoding="utf-8"))
    if selection is None or selection["method"] != "S3":
        raise RuntimeError("The frozen validation selection must be the supported S3 method")
    z_flag = float(receiver["chosen_z_flag"])
    with (OUT / "sealed_test_selection.csv").open(encoding="utf-8", newline="") as stream:
        selected = list(csv.DictReader(stream))
    counts = {name: sum(row["corpus"] == name for row in selected)
              for name in ("BOSSBase", "COCO")}
    if counts != {"BOSSBase": 201, "COCO": 201}:
        raise RuntimeError(f"Expected 201 sealed test images per corpus; found {counts}")

    config_digest = hashlib.sha256(
        (OUT / "validation_config_selection.json").read_bytes()
        + (OUT / "receiver_validation_selection.json").read_bytes()
        + (OUT / "sealed_test_selection.csv").read_bytes()
    ).hexdigest()
    chunks = OUT / "sealed_test_chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    messages = {length: load_messages(length, 3) for length in (100, 200)}
    started = time.perf_counter()
    run_started_epoch = time.time()
    all_names = sorted(selected, key=lambda row: (row["corpus"], int(row["selection_rank"])))

    for image_index, record in enumerate(all_names):
        chunk = chunks / f"{record['corpus']}_{record['filename']}.csv.gz"
        if chunk.exists():
            print(f"[{image_index + 1}/{len(all_names)}] {record['corpus']}/{record['filename']}: resumed",
                  flush=True)
            continue
        path = args.data_root / (
            "bossbase_1_01" if record["corpus"] == "BOSSBase" else "ms_coco_val2017"
        ) / record["filename"]
        if sha256(path) != record["sha256"]:
            raise RuntimeError(f"Sealed image hash changed: {record['filename']}")
        image = load_gray_512(path)
        lookup = OptimalAssignmentMethod(BLOCK_SIZE, "spectral")
        lookup.build_lookup_table(image)
        locations = [loc for candidates in lookup.lookup_table.values() for loc in candidates]
        development = []
        for i, attack in enumerate(EXTENDED_DEVELOPMENT):
            attacked = transform(image, attack,
                                 SEED + 20000 + image_index * 101 + i, "bilinear")
            development.append(attacked[0] if isinstance(attacked, tuple) else attacked)
        _s2, s3, _margin_rows = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", development
        )
        method = StabilityAwareAssignmentMethod(
            BOUND, float(selection["lambda"]), BLOCK_SIZE, "spectral",
            residual_scale=BOUND, sparse_solver=True,
        )
        method.lookup_table, method.image_shape = lookup.lookup_table, lookup.image_shape
        method.stabilities = s3
        attacks = attack_set(image, image_index)

        primary = {name: ("P2" if name in GEOMETRIC else "P1")
                   for name in TEST_TRANSFORMS}
        reliable = {}
        for name, path_name in primary.items():
            received = attacks[name][path_name]
            if received is None:
                reliable[name] = None
                continue
            seed = SEED + 40000 + image_index * 1009 + TEST_TRANSFORMS.index(name) * 31
            _flags, reliability_rows = receiver_reliability_flags(
                received, locations, BLOCK_SIZE, "spectral",
                jitter_images(received, seed), z_flag=z_flag,
            )
            reliable[name] = {
                (int(row["x"]), int(row["y"]), int(row["arrangement"])):
                (bool(row["any_jitter_hash_flip"]), float(row["min_margin_z"]))
                for row in reliability_rows
            }

        rows = []
        for length in (100, 200):
            for family, sources in messages[length].items():
                for trial, source in enumerate(sources):
                    coded = zlib.compress(source, level=9)
                    assignment = method.embed(coded.decode("latin-1"), image)
                    paths_to_decode = [("identity", "P0", image)] + [
                        (name, path_name, attacks[name][path_name])
                        for name in TEST_TRANSFORMS
                        for path_name in (("P1", "P2", "P3") if name in GEOMETRIC else ("P1", "P3"))
                    ]
                    for transform_name, path_name, received in paths_to_decode:
                        if assignment is None:
                            recovered = b""
                            correct = np.zeros(len(coded), dtype=bool)
                            flags = np.zeros(len(coded), dtype=bool)
                        elif received is None:
                            recovered = b""
                            correct = np.zeros(len(coded), dtype=bool)
                            flags = np.ones(len(coded), dtype=bool)
                        else:
                            recovered = method.extract(assignment, received).encode("latin-1")
                            correct = np.zeros(len(coded), dtype=bool)
                            width = min(len(coded), len(recovered))
                            correct[:width] = np.fromiter(
                                (coded[i] == recovered[i] for i in range(width)),
                                dtype=bool, count=width,
                            )
                            flags = np.zeros(len(coded), dtype=bool)
                            if transform_name != "identity" and path_name == primary.get(transform_name):
                                mapping = reliable[transform_name]
                                if mapping is not None:
                                    features = [mapping[(loc.x, loc.y, loc.arrangement)]
                                                for loc in assignment.locations]
                                    flips = np.asarray([item[0] for item in features], dtype=bool)
                                    z = np.asarray([item[1] for item in features], dtype=float)
                                    flags[:min(len(flags), len(flips))] = (
                                        flips | (z < z_flag)
                                    )[:min(len(flags), len(flips))]
                                elif path_name == "P2":
                                    flags[:] = True
                        errors = ~correct
                        if assignment is None:
                            flagged_wrong = silent_errors = 0
                        else:
                            flagged_wrong = int((flags & errors).sum())
                            silent_errors = int((~flags & errors).sum())
                        try:
                            source_exact = int(zlib.decompress(recovered) == source)
                        except zlib.error:
                            source_exact = 0
                        primary_path = (transform_name != "identity"
                                        and path_name == primary.get(transform_name))
                        rows.append({
                            "frozen_commit": args.frozen_commit,
                            "config_sha256": config_digest,
                            "cover": record["filename"], "corpus": record["corpus"],
                            "selection_rank": int(record["selection_rank"]),
                            "family": family, "length": length, "trial": trial,
                            "transform": transform_name, "path": path_name,
                            "primary_path": int(primary_path),
                            "feasible": int(assignment is not None),
                            "symbols": len(coded) if assignment is not None else 0,
                            "expected_symbols": len(coded),
                            "correct": int(correct.sum()),
                            "exact": int(recovered == coded),
                            "source_exact": source_exact,
                            "flagged": int(flags.sum()) if primary_path else np.nan,
                            "flagged_wrong": flagged_wrong if primary_path else np.nan,
                            "silent_errors": silent_errors if primary_path else np.nan,
                            "registration_success": int(received is not None)
                            if path_name == "P2" else np.nan,
                            "keypoint_matches": attacks.get(transform_name, {}).get("matches", np.nan)
                            if path_name == "P2" else np.nan,
                            "ransac_inliers": attacks.get(transform_name, {}).get("inliers", np.nan)
                            if path_name == "P2" else np.nan,
                        })
        pd.DataFrame(rows).to_csv(chunk, index=False, compression="gzip")
        print(f"[{image_index + 1}/{len(all_names)}] {record['corpus']}/{record['filename']} complete; "
              f"elapsed {time.perf_counter() - started:.1f}s", flush=True)

    raw = pd.concat((pd.read_csv(path) for path in sorted(chunks.glob("*.csv.gz"))),
                    ignore_index=True)
    raw.to_csv(OUT / "sealed_test_raw.csv.gz", index=False, compression="gzip")
    summary_rows = []
    boot_rng = np.random.default_rng(SEED)
    for (corpus, transform_name, path_name), group in raw.groupby(
            ["corpus", "transform", "path"], dropna=False):
        per_cover = group.groupby("cover", as_index=False).agg(
            feasible=("feasible", "mean"), symbols=("symbols", "sum"),
            expected_symbols=("expected_symbols", "sum"),
            correct=("correct", "sum"), exact=("exact", "sum"),
            source_exact=("source_exact", "sum"), flagged=("flagged", "sum"),
            flagged_wrong=("flagged_wrong", "sum"), silent_errors=("silent_errors", "sum"),
            registration_success=("registration_success", "mean"),
        )
        denominator = group["symbols"].sum()
        expected_denominator = group["expected_symbols"].sum()
        correct_total = group["correct"].sum()
        primary_path = bool(group["primary_path"].fillna(0).max())
        f = group["flagged"].sum() / denominator if primary_path and denominator else np.nan
        s = group["silent_errors"].sum() / denominator if primary_path and denominator else np.nan
        rmax = 1 - f - 2 * s if primary_path else np.nan
        acc_per_cover = (per_cover.correct / per_cover.symbols.replace(0, np.nan)).to_numpy()
        indices = boot_rng.integers(0, len(per_cover), size=(10000, len(per_cover)))
        boot_acc = np.nanmean(acc_per_cover[indices], axis=1)
        if primary_path:
            vals = per_cover[["symbols", "flagged", "silent_errors"]].to_numpy(dtype=float)[indices].sum(axis=1)
            boot_r = 1 - vals[:, 1] / vals[:, 0] - 2 * vals[:, 2] / vals[:, 0]
            r_lo, r_hi = np.nanpercentile(boot_r, [2.5, 97.5])
        else:
            r_lo = r_hi = np.nan
        summary_rows.append({
            "corpus": corpus, "transform": transform_name, "path": path_name,
            "covers": int(per_cover.cover.nunique()),
            "assignments": int(len(group)),
            "feasible_assignments": int(group.feasible.sum()),
            "assignment_feasibility": float(group.feasible.mean()),
            "feasibility_wilson95_low": wilson_interval(
                int(group.feasible.sum()), len(group)
            )[0],
            "feasibility_wilson95_high": wilson_interval(
                int(group.feasible.sum()), len(group)
            )[1],
            "accuracy": float(correct_total / denominator) if denominator else np.nan,
            "accuracy_unconditional": float(correct_total / expected_denominator)
            if expected_denominator else np.nan,
            "accuracy_ci95_low": float(np.nanpercentile(boot_acc, 2.5)),
            "accuracy_ci95_high": float(np.nanpercentile(boot_acc, 97.5)),
            "exact_messages": int(group.exact.sum()),
            "source_exact_messages": int(group.source_exact.sum()),
            "exact_rate": float(group.exact.mean()),
            "source_exact_rate": float(group.source_exact.mean()),
            "registration_success_rate": float(group.registration_success.mean()),
            "mean_keypoint_matches": float(group.keypoint_matches.mean()),
            "mean_ransac_inliers": float(group.ransac_inliers.mean()),
            "f_flagged_fraction": f, "s_silent_error_fraction": s,
            "R_max": rmax, "R_max_ci95_low": r_lo, "R_max_ci95_high": r_hi,
            "primary_path": int(primary_path),
            "cluster_bootstrap_draws": 10000,
        })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "sealed_test_summary.csv", index=False)
    provenance = {
        "frozen_commit": args.frozen_commit,
        "configuration": selection,
        "receiver_z_flag": z_flag,
        "configuration_and_manifest_sha256": config_digest,
        "sample_counts": counts,
        "data_root_name": args.data_root.name,
        "transformations": TEST_TRANSFORMS,
        "paths": "P1 fixed coordinates; P2 ORB/RANSAC; P3 known geometric inverse",
        "preprocessing": "grayscale then Lanczos resize to 512x512",
        "seed_root": SEED,
        "cluster_bootstrap_draws": 10000,
        "started_epoch_seconds": run_started_epoch,
        "elapsed_seconds": time.perf_counter() - started,
        "selection_test_split_sha256": sha256(OUT / "sealed_test_selection.csv"),
        "candidate_manifest_sha256": sha256(OUT / "sealed_candidate_manifest.csv"),
        "protocol_sha256": sha256(Path(r"C:\Users\User\Downloads\FHAM — Protocole de l'étape 1 stabilité par position sous transformations.md")),
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": importlib.metadata.version("scipy"),
            "opencv": cv2.__version__,
            "Pillow": Image.__version__,
            "scikit_image": importlib.metadata.version("scikit-image"),
        },
        "scripts_sha256": {
            name: sha256(ROOT / "scripts" / name)
            for name in (
                "stability_step1_sealed_test.py",
                "stability_step1_validation.py",
                "stability_step1_receiver_validation.py",
                "stability_step1_pilot.py",
                "stability_step1_estimate.py",
            )
        },
        "raw_sha256": sha256(OUT / "sealed_test_raw.csv.gz"),
    }
    (OUT / "sealed_test_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
