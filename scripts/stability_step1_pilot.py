"""Preregistered 20-cover geometric stability pilot (Step 1, D0)."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image
from skimage.feature import ORB, match_descriptors
from skimage.measure import ransac
from skimage.transform import ProjectiveTransform, warp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fham.config import DATASET_DIR  # noqa: E402
from fham.descriptors import descriptor_hashes  # noqa: E402
from fham.experiments import _attack, _message  # noqa: E402
from fham.methods import OptimalAssignmentMethod, StabilityAwareAssignmentMethod  # noqa: E402
from fham.stability import estimate_position_stability  # noqa: E402

SEED = 20261116
BLOCK_SIZE = 12
BOUND = 2


def _cv_interpolation(name):
    return cv2.INTER_CUBIC if name == "bicubic" else cv2.INTER_LINEAR


def transform(image, name, seed, interpolation="bicubic"):
    h, w = image.shape
    interp = _cv_interpolation(interpolation)
    if name.startswith("jpeg"):
        quality = int(name[4:])
        buf = io.BytesIO()
        Image.fromarray(image).save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        return np.asarray(Image.open(buf).convert("L"))
    if name.startswith("noise"):
        sigma = float(name[5:])
        rng = np.random.default_rng(seed)
        return np.clip(image.astype(np.float64) + rng.normal(0, sigma, image.shape),
                       0, 255).astype(np.uint8)
    if name.startswith("rotate"):
        degrees = float(name[6:])
        matrix = cv2.getRotationMatrix2D(((w - 1) / 2, (h - 1) / 2), degrees, 1)
        attacked = cv2.warpAffine(image, matrix, (w, h), flags=interp,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        return attacked, matrix
    if name.startswith("crop"):
        percent = float(name[4:]) / 100
        margin_y, margin_x = round(h * percent), round(w * percent)
        cropped = image[margin_y:h - margin_y, margin_x:w - margin_x]
        attacked = cv2.resize(cropped, (w, h), interpolation=interp)
        scale_x = w / cropped.shape[1]
        scale_y = h / cropped.shape[0]
        matrix = np.array([
            [scale_x, 0, (0.5 - margin_x) * scale_x - 0.5],
            [0, scale_y, (0.5 - margin_y) * scale_y - 0.5],
        ], dtype=np.float64)
        return attacked, matrix
    if name.startswith("resize"):
        scale = float(name[6:])
        reduced = cv2.resize(image, (round(w * scale), round(h * scale)),
                             interpolation=interp)
        return cv2.resize(reduced, (w, h), interpolation=interp)
    if name == "combo_rotate1_jpeg75":
        rotated = transform(image, "rotate1", seed, interpolation)[0]
        return transform(rotated, "jpeg75", seed, interpolation)
    raise ValueError(name)


def _register(reference, attacked):
    def features(image):
        extractor = ORB(n_keypoints=600, fast_threshold=0.04)
        try:
            extractor.detect_and_extract(image.astype(np.float32) / 255)
            return extractor
        except RuntimeError:
            return None

    ref, atk = features(reference), features(attacked)
    if ref is None or atk is None or len(ref.descriptors) < 4 or len(atk.descriptors) < 4:
        return None, 0, 0
    pairs = match_descriptors(ref.descriptors, atk.descriptors,
                              cross_check=True, max_ratio=0.8)
    if len(pairs) < 4:
        return None, len(pairs), 0
    source = ref.keypoints[pairs[:, 0]][:, ::-1]
    destination = atk.keypoints[pairs[:, 1]][:, ::-1]
    model, inliers = ransac(
        (source, destination), ProjectiveTransform, min_samples=4,
        residual_threshold=3, max_trials=1000,
        rng=np.random.default_rng(20261110),
    )
    if model is None or inliers is None or int(inliers.sum()) < 4:
        return None, len(pairs), 0
    inverse = model.params.astype(np.float64)
    aligned = cv2.warpPerspective(
        attacked, inverse, (reference.shape[1], reference.shape[0]),
        flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    return aligned, len(pairs), int(inliers.sum())


def main():
    face_rows = pd.read_csv(DATASET_DIR / "stress" / "manifest.csv")
    faces = face_rows[face_rows.content_type.str.lower().str.contains("face")]
    face_names = sorted(faces.name.astype(str).tolist())
    # A stable digest ordering makes the pilot reproducible and fixes its 20 covers.
    pilot_names = sorted(face_names, key=lambda x: hashlib.sha256(
        f"{SEED}:{x}".encode()).hexdigest())[:20]
    rows = []
    margin_rows = []
    for image_index, name in enumerate(pilot_names):
        image_path = DATASET_DIR / "stress" / f"{name}.png"
        image = np.asarray(Image.open(image_path).convert("L"))
        lookup = OptimalAssignmentMethod(BLOCK_SIZE, "spectral")
        lookup.build_lookup_table(image)
        locations = [loc for candidates in lookup.lookup_table.values() for loc in candidates]

        # S1 uses the submitted three-transform development set; identity and
        # validation transformations remain excluded from this estimate.
        dev = [
            _attack(image, attack, SEED + image_index * 31 + index)
            for index, attack in enumerate(("jpeg90", "resize90", "noise1"))
        ]
        empirical, _continuous, margin_data = estimate_position_stability(
            image, locations, BLOCK_SIZE, "spectral", dev
        )
        margin_rows.extend({"image": name, **row} for row in margin_data)
        method = StabilityAwareAssignmentMethod(
            BOUND, 0.75, BLOCK_SIZE, "spectral", residual_scale=BOUND
        )
        method.lookup_table, method.image_shape = lookup.lookup_table, lookup.image_shape
        method.stabilities = empirical
        source = _message(40, name, 0).encode("latin-1")
        coded = zlib.compress(source, level=9)
        payload = coded.decode("latin-1")
        assignment = method.embed(payload, image)
        if assignment is None:
            for transform_name in ("jpeg75", "noise2", "rotate1", "crop5", "resize08"):
                for path in ("P0", "P1", "P2", "P3"):
                    rows.append({"image": name, "transform": transform_name,
                                 "path": path, "feasible": 0})
            continue
        expected = payload
        validation = {
            "jpeg75": transform(image, "jpeg75", SEED + image_index),
            "noise2": transform(image, "noise2", SEED + image_index + 1),
            "rotate1": transform(image, "rotate1", SEED + image_index + 2)[0],
            "crop5": transform(image, "crop5", SEED + image_index + 3)[0],
            "resize08": transform(image, "resize0.8", SEED + image_index + 4),
        }
        for transform_name, attacked in validation.items():
            decoded_fixed = method.extract(assignment, attacked)
            p2_matches = p2_inliers = 0
            p2 = attacked
            if transform_name in ("rotate1", "crop5", "resize08"):
                p2, p2_matches, p2_inliers = _register(image, attacked)
                p2_success = int(p2 is not None)
            else:
                p2_success = 1
            p3 = attacked
            oracle_matrix = None
            if transform_name == "rotate1":
                _attacked, oracle_matrix = transform(image, "rotate1", SEED + image_index + 2)
                p3 = cv2.warpAffine(
                    attacked, oracle_matrix, (image.shape[1], image.shape[0]),
                    flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0,
                )
            elif transform_name == "crop5":
                _attacked, oracle_matrix = transform(image, "crop5", SEED + image_index + 3)
                p3 = cv2.warpAffine(
                    attacked, oracle_matrix, (image.shape[1], image.shape[0]),
                    flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0,
                )
            elif transform_name == "resize08":
                # Downscale-restore already returns to the original grid;
                # the exact geometric inverse is identity (P3 = P1).
                p3 = attacked
            recovered = {
                "P0": method.extract(assignment, image),
                "P1": decoded_fixed,
                "P2": (method.extract(assignment, p2) if p2 is not None else None),
                "P3": method.extract(assignment, p3),
            }
            for path, output in recovered.items():
                n_correct = (sum(a == b for a, b in zip(expected, output))
                             if output is not None else 0)
                rows.append({
                    "image": name,
                    "transform": transform_name,
                    "path": path,
                    "feasible": 1,
                    "matches": p2_matches if path == "P2" else np.nan,
                    "inliers": p2_inliers if path == "P2" else np.nan,
                    "registration_success": p2_success if path == "P2" else 1,
                    "symbols": len(expected),
                    "correct": n_correct,
                    "accuracy": n_correct / len(expected),
                    "exact": int(output == expected) if output is not None else 0,
                })
        print(f"[{image_index + 1}/20] {name} complete", flush=True)

    raw = pd.DataFrame(rows)
    out = ROOT / "results" / "stability_step1"
    out.mkdir(parents=True, exist_ok=True)
    raw.to_csv(out / "pilot_d0_raw.csv", index=False)
    pd.DataFrame(margin_rows).to_csv(
        out / "pilot_d0_position_margins.csv.gz", index=False, compression="gzip"
    )
    summary = raw.groupby(["transform", "path"], as_index=False).agg(
        covers=("image", "nunique"),
        feasible=("feasible", "mean"),
        accuracy=("accuracy", "mean"),
        exact=("exact", "mean"),
        matches=("matches", "mean"),
        inliers=("inliers", "mean"),
    )
    summary.to_csv(out / "pilot_d0_summary.csv", index=False)
    provenance = {
        "seed": SEED,
        "pilot_names": pilot_names,
        "image_sha256": {
            name: hashlib.sha256((DATASET_DIR / "stress" / f"{name}.png").read_bytes()).hexdigest()
            for name in pilot_names
        },
        "block_size": BLOCK_SIZE,
        "bound": BOUND,
        "residual_scale": "B",
        "payload": "zlib-9; one deterministic 40-byte message per cover",
        "S1_development": ["jpeg90", "resize90", "noise1"],
                "validation": ["jpeg75", "noise2", "rotate1", "crop5", "resize0.8"],
        "registration": "skimage ORB, cross-check, ratio=0.8, >=4, RANSAC threshold=3, seed=20261110",
        "oracle": "known CV2 affine mapping, bilinear inverse warp",
    }
    (out / "pilot_d0_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
