"""Run the preregistered 20-cover Step 1bis sample-size pilot on BOWS2-A."""

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

from fham.methods import OptimalAssignmentMethod, StabilityAwareAssignmentMethod
from fham.stability import estimate_position_stability
from stability_step1_estimate import EXTENDED_DEVELOPMENT
from stability_step1_pilot import transform

SEED = 20261116
BLOCK_SIZE = 12
BOUND = 2
VALIDATION = ("jpeg75", "noise2", "rotate1", "crop5", "resize0.8")
FAMILIES = ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated")
LENGTHS = (100, 200)


def gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"))


def fixed_messages() -> dict[tuple[str, int], bytes]:
    root = ROOT / "dataset" / "messages"
    messages = {}
    for family in FAMILIES:
        for length in LENGTHS:
            path = root / family / f"{family}_{length}_00.bin"
            source = path.read_bytes()
            if len(source) != length:
                raise RuntimeError(f"Wrong source length for {path}: {len(source)}")
            messages[(family, length)] = source
    return messages


def methods(image: np.ndarray, block_size: int):
    lookup = OptimalAssignmentMethod(block_size, "spectral")
    lookup.build_lookup_table(image)
    locations = [location for group in lookup.lookup_table.values() for location in group]
    return lookup, locations


def make_method(lookup, locations, stabilities, lam):
    method = StabilityAwareAssignmentMethod(
        BOUND, lam, BLOCK_SIZE, "spectral", residual_scale=BOUND, sparse_solver=True
    )
    method.lookup_table = lookup.lookup_table
    method.image_shape = lookup.image_shape
    method.stabilities = {location: stabilities.get(location, 1.0) for location in locations}
    return method


def oracle_image(image, transform_name, attacked, matrix):
    if transform_name in ("rotate1", "crop5"):
        return cv2.warpAffine(
            attacked, matrix, (image.shape[1], image.shape[0]),
            flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
    return attacked


def main() -> None:
    out = ROOT / "results" / "stability_step1" / "step1bis" / "pilot"
    out.mkdir(parents=True, exist_ok=True)
    split = pd.read_csv(ROOT / "results" / "stability_step1" / "step1bis" / "manifest" / "split_manifest.csv")
    a_names = split[split.split.eq("A")].sort_values("selection_rank").source_id.astype(str).tolist()
    if len(a_names) != 200:
        raise RuntimeError(f"Expected 200 BOWS2-A covers, found {len(a_names)}")
    names = a_names[:20]
    messages = fixed_messages()
    score_rows = []
    started = time.perf_counter()

    for cover_index, name in enumerate(names):
        image_path = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover") / name
        image = gray(image_path)
        if image.shape != (256, 256):
            raise RuntimeError(f"Unexpected BOWS2 image shape for {name}: {image.shape}")
        lookup, locations = methods(image, BLOCK_SIZE)
        development = [
            transform(image, transform_name,
                      SEED + 50000 + cover_index * 101 + index, "bilinear")
            for index, transform_name in enumerate(EXTENDED_DEVELOPMENT)
        ]
        development = [value[0] if isinstance(value, tuple) else value for value in development]
        _empirical, continuous, _margin_rows = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", development
        )
        s0 = make_method(lookup, locations, {}, 1.0)
        s3 = make_method(lookup, locations, continuous, 0.5)

        attacked = {}
        for transform_index, transform_name in enumerate(VALIDATION):
            value = transform(image, transform_name,
                              SEED + cover_index * 101 + transform_index, "bicubic")
            if isinstance(value, tuple):
                transformed, matrix = value
            else:
                transformed, matrix = value, None
            attacked[transform_name] = oracle_image(
                image, transform_name, transformed, matrix
            )

        for (family, length), source in messages.items():
            payload_bytes = zlib.compress(source, level=9)
            payload = payload_bytes.decode("latin-1")
            for method_name, method in (("S0", s0), ("S3", s3)):
                tic = time.perf_counter()
                assignment = method.embed(payload, image)
                solve_ms = (time.perf_counter() - tic) * 1000
                for transform_name, received in (("identity", image), *attacked.items()):
                    recovered = method.extract(assignment, received) if assignment else None
                    correct = (
                        sum(left == right for left, right in zip(payload, recovered))
                        if recovered is not None else 0
                    )
                    score_rows.append({
                        "cover": name,
                        "cover_rank_A": cover_index + 1,
                        "cover_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                        "family": family,
                        "source_length": length,
                        "message_file": f"{family}_{length}_00.bin",
                        "message_sha256": hashlib.sha256(source).hexdigest(),
                        "compressed_length": len(payload_bytes),
                        "profile": BLOCK_SIZE,
                        "method": method_name,
                        "lambda": 1.0 if method_name == "S0" else 0.5,
                        "transform": transform_name,
                        "path": "P3",
                        "feasible": int(assignment is not None),
                        "symbols": len(payload),
                        "correct_symbols": correct,
                        "accuracy_unconditional": correct / len(payload),
                        "exact_recovery": int(recovered == payload) if recovered is not None else 0,
                        "mean_abs_displacement": (
                            float(np.mean(np.abs(assignment.displacements))) if assignment else np.nan
                        ),
                        "solve_ms": solve_ms,
                    })
        print(f"[{cover_index + 1}/20] {name} complete", flush=True)

    raw = pd.DataFrame(score_rows)
    raw.to_csv(out / "paired_scores.csv", index=False)
    per_cover = raw.groupby(
        ["cover", "method", "transform"], as_index=False
    ).agg(accuracy=("accuracy_unconditional", "mean"), feasible=("feasible", "mean"))
    wide = per_cover.pivot(index=["cover", "transform"], columns="method", values="accuracy").reset_index()
    wide["delta_S3_minus_S0"] = wide["S3"] - wide["S0"]
    wide.to_csv(out / "per_cover_deltas.csv", index=False)
    delta_sd = (
        wide[wide["transform"].isin(VALIDATION)]
        .groupby("transform").delta_S3_minus_S0.std(ddof=1)
    )
    sd_delta = float(delta_sd.max())
    n_delta = int(np.ceil((1.96 * sd_delta / 0.03) ** 2))
    n_q = int(np.ceil((1.96 * 0.5 / 0.03) ** 2))
    sample_n = max(200, n_delta, n_q)
    summary = raw.groupby(["method", "transform"], as_index=False).agg(
        covers=("cover", "nunique"),
        feasibility=("feasible", "mean"),
        accuracy=("accuracy_unconditional", "mean"),
        exact_recovery=("exact_recovery", "mean"),
        mean_abs_displacement=("mean_abs_displacement", "mean"),
        mean_solve_ms=("solve_ms", "mean"),
    )
    summary.to_csv(out / "pilot_summary.csv", index=False)
    provenance = {
        "seed_root": SEED,
        "covers": names,
        "cover_selection": "first 20 from frozen BOWS2-A, ordered by selection_rank",
        "profile": "spectral, L=12, B=2, BOWS2 native grayscale 256x256",
        "methods": "S0 and S3 lambda=0.5, stability estimated on the ten frozen development transforms",
        "messages": "four families x source lengths 100/200, fixed index 00, zlib level 9",
        "validation": "JPEG75, noise sigma 2, rotation +1 degree, crop 5 percent, resize 0.8; P3 oracle for geometry",
        "sd_delta": sd_delta,
        "sd_delta_by_transform": {str(key): float(value) for key, value in delta_sd.items()},
        "sd_q_conservative": 0.5,
        "n_delta": n_delta,
        "n_q": n_q,
        "sealed_sample_n": sample_n,
        "eligible_BOWS2_C": 7525,
        "phase_b_author_go_received": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    (out / "pilot_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance, indent=2), flush=True)
    print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
