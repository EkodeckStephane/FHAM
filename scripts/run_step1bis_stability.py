"""Run preregistered Step 1bis F2 stability grid on BOWS2 A or B."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fham.methods import OptimalAssignmentMethod, StabilityAwareAssignmentMethod
from fham.stability import estimate_position_stability
import stability_step1_estimate as estimate
import stability_step1_pilot as pilot
import stability_step1_validation as validation

SEED = 20261116
PROFILE = 12  # sole retained profile under the frozen profile-screen rule
BOUND = 2
LAMBDAS = (0.25, 0.5, 0.75, 0.9)
QUANTILES = (0.5, 0.3, 0.1)
FAMILIES = ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated")
ROOT_IMAGES = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
OUT = ROOT / "results" / "stability_step1" / "step1bis" / "stability_F2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_gray(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L"))


def messages(indices: tuple[int, ...]) -> dict[tuple[str, int, int], bytes]:
    result = {}
    root = ROOT / "dataset" / "messages"
    for family in FAMILIES:
        for length in (100, 200):
            for index in indices:
                path = root / family / f"{family}_{length}_{index:02d}.bin"
                value = path.read_bytes()
                if len(value) != length:
                    raise ValueError(f"Unexpected source size: {path}")
                result[(family, length, index)] = value
    return result


def dev_images(image: np.ndarray, cover_index: int, attacks: tuple[str, ...]):
    result = []
    for j, name in enumerate(attacks):
        value = pilot.transform(image, name, SEED + 50000 + cover_index * 101 + j, "bilinear")
        result.append(value[0] if isinstance(value, tuple) else value)
    return result


def method_for(lookup, scores, lam):
    method = validation._new_method(lookup, scores, lam)
    return method


def build_methods(image: np.ndarray, cover_index: int):
    validation.BLOCK_SIZE = PROFILE
    lookup = OptimalAssignmentMethod(PROFILE, "spectral")
    lookup.build_lookup_table(image)
    locations = [loc for group in lookup.lookup_table.values() for loc in group]
    old = dev_images(image, cover_index, estimate.OLD_DEVELOPMENT)
    extended = dev_images(image, cover_index, estimate.EXTENDED_DEVELOPMENT)
    s1, _, _ = estimate_position_stability(image, locations, PROFILE, "spectral", old)
    s2, s3, _ = estimate_position_stability(image, locations, PROFILE, "spectral", extended)
    all_one = {loc: 1.0 for loc in locations}
    methods = [("S0", 1.0, None, method_for(lookup, all_one, 1.0))]
    for name, scores in (("S1", s1), ("S2", s2), ("S3", s3)):
        for lam in LAMBDAS:
            methods.append((name, lam, None, method_for(lookup, scores, lam)))
    ordered = sorted(locations, key=lambda loc: (-s3[loc], loc.x, loc.y, loc.arrangement))
    for q in QUANTILES:
        keep = set(ordered[:math.ceil(q * len(ordered))])
        filtered = defaultdict(list)
        for value, locs in lookup.lookup_table.items():
            for loc in locs:
                if loc in keep:
                    filtered[value].append(loc)
        method = method_for(lookup, {}, 1.0)
        method.lookup_table = dict(filtered) if filtered else {-1: []}
        methods.append(("S4q", None, q, method))
    return lookup, locations, methods


def feasibility_for(method, image, index):
    rows = []
    for family in FAMILIES:
        for length in (50, 100, 200):
            path = ROOT / "dataset" / "messages" / family / f"{family}_{length}_00.bin"
            source = path.read_bytes()
            coded = zlib.compress(source, 9).decode("latin-1")
            rows.append({"family": family, "source_length": length,
                         "compressed_length": len(coded),
                         "feasible": int(method.embed(coded, image) is not None)})
    return rows


def process(path: Path, row, index: int, msg_map):
    image = read_gray(path)
    if image.shape != (256, 256):
        raise ValueError(f"Expected 256x256 BOWS2 image: {row.source_id} {image.shape}")
    lookup, locations, configs = build_methods(image, index)
    attacked = validation._cover_transforms(image, index)
    assignments, recoveries, feasibilities = [], [], []
    for name, lam, q, method in configs:
        params = {"cover": row.source_id, "cover_sha256": row.sha256,
                  "corpus": "BOWS2", "split": row.split, "profile": PROFILE,
                  "method": name, "lambda": lam, "filter_q": q}
        for frow in feasibility_for(method, image, index):
            feasibilities.append({**params, **frow})
        for (family, length, msg_index), source in msg_map.items():
            compressed = zlib.compress(source, 9)
            payload = compressed.decode("latin-1")
            start = time.perf_counter()
            assignment = method.embed(payload, image)
            elapsed = (time.perf_counter() - start) * 1000
            d1 = float(np.mean(np.abs(assignment.displacements))) if assignment else np.nan
            assignments.append({**params, "family": family, "source_length": length,
                                "message_index": msg_index, "compressed_length": len(compressed),
                                "feasible": int(assignment is not None), "D1": d1,
                                "solve_ms": elapsed, "n_locations": len(locations),
                                "retained_locations": method.capacity})
            if assignment is None:
                continue
            conditions = [("identity", "P0", image)]
            for tname, paths in attacked.items():
                ps = ("P1", "P2", "P3") if tname in ("rotate1", "crop5", "resize0.8") else ("P1", "P3")
                for p in ps:
                    conditions.append((tname, p, paths.get(p)))
            for tname, pname, received in conditions:
                recovered = method.extract(assignment, received).encode("latin-1") if received is not None else b""
                ncorrect = sum(a == b for a, b in zip(compressed, recovered))
                recoveries.append({**params, "family": family, "source_length": length,
                                   "message_index": msg_index, "transform": tname,
                                   "path": pname, "n_symbols": len(compressed),
                                   "n_correct": ncorrect, "accuracy": ncorrect / len(compressed),
                                   "exact": int(recovered == compressed)})
    return pd.DataFrame(assignments), pd.DataFrame(recoveries), pd.DataFrame(feasibilities)


def run(stage: str, limit: int | None):
    split_path = ROOT / "results" / "stability_step1" / "step1bis" / "manifest" / "split_manifest.csv"
    split = pd.read_csv(split_path).sort_values("selection_rank")
    rows = split[split.split.eq(stage)].head(limit or (100 if stage == "A" else 200))
    indices = (0,) if stage == "A" else (0, 1, 2)
    msg_map = messages(indices)
    out = OUT / stage
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for i, row in enumerate(rows.itertuples(index=False)):
        stem = Path(row.relative_path).stem
        marker = out / f"{stem}_assignments.csv.gz"
        if marker.exists():
            print(f"[{stage} {i+1}/{len(rows)}] {stem} already complete; skip", flush=True)
            continue
        result = process(ROOT_IMAGES / row.relative_path, row, i, msg_map)
        for df, suffix in zip(result, ("assignments", "recovery", "feasibility")):
            df.to_csv(out / f"{stem}_{suffix}.csv.gz", index=False, compression="gzip")
        print(f"[{stage} {i+1}/{len(rows)}] {stem} complete; elapsed={time.perf_counter()-started:.1f}s", flush=True)
    provenance = {"stage": stage, "profile": PROFILE, "bound": BOUND,
                  "lambda_grid": LAMBDAS, "S4q": QUANTILES, "message_indices": indices,
                  "covers": rows.source_id.tolist(), "validation_transforms": validation.TRANSFORMS,
                  "development_old": estimate.OLD_DEVELOPMENT,
                  "development_extended": estimate.EXTENDED_DEVELOPMENT,
                  "opencv": __import__("cv2").__version__, "python": sys.version,
                  "elapsed_seconds": time.perf_counter()-started,
                  "script_sha256": sha(Path(__file__))}
    (out / "run.json").write_text(json.dumps(provenance, indent=2, default=list), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("A", "B"), required=True)
    parser.add_argument("--limit", type=int, help="diagnostic subset; preregistered run uses full split")
    args = parser.parse_args()
    run(args.stage, args.limit)


if __name__ == "__main__":
    main()
