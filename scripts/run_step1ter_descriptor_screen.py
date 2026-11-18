"""Frozen Step 4b screen of spectral, mean, DCT-sumabs, and Arr.4 descriptors."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.fft import dctn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fham.abdulsattar import AbdulsattarMethod
from fham.descriptors import _ordinal_arrangements
from fham.methods import Location, OptimalAssignmentMethod
from fham.stability import _block_payloads
from stability_step1_pilot import transform

SOURCE = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
MANIFEST = ROOT / "results/stability_step1/step1ter/manifest/bows2_D_E_C_manifest.csv"
OUT = ROOT / "results/stability_step1/step1ter/step4b_screen"
SEED = 20261118
K = 50
DESCRIPTORS = ("spectral", "mean_ordinal", "dct_sumabs", "abdulsattar_arr4")


def read_image(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L"))


def attacks(image: np.ndarray, cover_index: int, profile: int):
    rng = np.random.default_rng(SEED + cover_index * 997 + profile * 17 + 900000)
    result = {"jpeg": [], "noise": []}
    for k in range(K):
        q = int(rng.integers(70, 91))
        if 74 <= q <= 76:
            q = 73 if k % 2 == 0 else 77
        sigma = float(rng.uniform(1.0, 2.4))
        if 1.9 <= sigma <= 2.1:
            sigma = 1.89 if k % 2 == 0 else 2.11
        result["jpeg"].append(transform(image, f"jpeg{q}", SEED + cover_index * 2000 + 400000 + k, "bilinear"))
        result["noise"].append(transform(image, f"noise{sigma:.8f}", SEED + cover_index * 2000 + 401000 + k, "bilinear"))
    return result


def locations_and_hashes(image: np.ndarray, descriptor: str):
    if descriptor == "abdulsattar_arr4":
        values = AbdulsattarMethod._arrangement_four_hashes(image, 6)
        locs, lookup = [], defaultdict(list)
        for row, col in np.ndindex(values.shape):
            loc = Location(col * 6, row * 6, 0)
            value = int(values[row, col])
            locs.append(loc)
            lookup[value].append(loc)
        return 18, locs, dict(lookup), {loc: int(values[loc.y // 6, loc.x // 6]) for loc in locs}

    profile = 12
    method = OptimalAssignmentMethod(profile, descriptor)
    method.build_lookup_table(image)
    locs = [loc for values in method.lookup_table.values() for loc in values]
    return profile, locs, method.lookup_table, {loc: value for value, values in method.lookup_table.items() for loc in values}


def batch_hash_map(image: np.ndarray, descriptor: str, profile: int,
                   locations: list[Location]) -> dict[Location, int]:
    if descriptor == "spectral":
        blocks = _block_payloads(image, sorted({(l.x, l.y) for l in locations}), profile, "spectral")
        return {loc: int(blocks[(loc.x, loc.y)][0][loc.arrangement]) for loc in locations}
    if descriptor == "abdulsattar_arr4":
        values = AbdulsattarMethod._arrangement_four_hashes(image, 6)
        return {loc: int(values[loc.y // 6, loc.x // 6]) for loc in locations}

    sub = profile // 3
    coordinates = sorted({(loc.x, loc.y) for loc in locations})
    blocks = np.stack([image[y:y+profile, x:x+profile] for x, y in coordinates]).astype(np.float64)
    cells = blocks.reshape(len(blocks), 3, sub, 3, sub).transpose(0, 1, 3, 2, 4).reshape(-1, sub, sub)
    if descriptor == "mean_ordinal":
        scores = cells.mean(axis=(-2, -1)).reshape(len(blocks), 9)
    elif descriptor == "dct_sumabs":
        coeff = dctn(cells, type=2, norm="ortho", axes=(-2, -1))
        scores = (np.abs(coeff[:, 0, 0]) + np.abs(coeff[:, 0, 1]) + np.abs(coeff[:, 1, 0])).reshape(len(blocks), 9)
    else:
        raise ValueError(descriptor)
    all_hashes = np.asarray([_ordinal_arrangements(v.tolist()) for v in scores], dtype=np.uint8)
    by_xy = {xy: all_hashes[i] for i, xy in enumerate(coordinates)}
    return {loc: int(by_xy[(loc.x, loc.y)][loc.arrangement]) for loc in locations}


def run_cover(row, cover_index: int):
    image = read_image(SOURCE / row.relative_path)
    if image.shape != (256, 256):
        raise RuntimeError(f"Unexpected shape {row.source_id}: {image.shape}")
    attacked = attacks(image, cover_index, 12)
    screen, detail = [], []
    for descriptor in DESCRIPTORS:
        t0 = time.perf_counter()
        profile, locs, _lookup, base = locations_and_hashes(image, descriptor)
        family_flip = {family: Counter() for family in ("jpeg", "noise")}
        for family, variants in attacked.items():
            for variant in variants:
                current = batch_hash_map(variant, descriptor, profile, locs)
                for loc in locs:
                    family_flip[family][loc] += int(current[loc] != base[loc])
        robust = [loc for loc in locs if family_flip["jpeg"][loc] == 0 and family_flip["noise"][loc] == 0]
        values = {base[loc] for loc in locs}
        robust_values = {base[loc] for loc in robust}
        screen.append({"cover": row.source_id, "cover_sha256": row.sha256,
                       "descriptor": descriptor, "block_size": profile,
                       "positions": len(locs), "robust_positions": len(robust),
                       "robust_fraction": len(robust) / len(locs),
                       "distinct_hash_values": len(values),
                       "robust_distinct_hash_values": len(robust_values),
                       "elapsed_seconds": time.perf_counter() - t0})
        for loc in locs:
            detail.append({"cover": row.source_id, "descriptor": descriptor,
                           "x": loc.x, "y": loc.y, "arrangement": loc.arrangement,
                           "hash_value": base[loc], "jpeg_flips": family_flip["jpeg"][loc],
                           "noise_flips": family_flip["noise"][loc],
                           "robust": int(family_flip["jpeg"][loc] == 0 and family_flip["noise"][loc] == 0)})
        print(f"{row.source_id} {descriptor}: rho={len(robust)/len(locs):.3f}, n={len(robust)}/{len(locs)}", flush=True)
    return screen, detail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, choices=(5, 100))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(MANIFEST, keep_default_na=False)
    d = manifest.loc[manifest.split.eq("D")].sort_values("selection_rank_1ter").head(args.limit)
    provenance = {"step": "4b descriptor screen", "limit": args.limit,
                  "D_covers": d.source_id.tolist(), "D_sha256": dict(zip(d.source_id, d.sha256)),
                  "descriptors": DESCRIPTORS, "K_per_family": K,
                  "seed": SEED, "attack_ranges": "JPEG U[70,90] excluding 74..76; noise sigma U[1,2.4] excluding 1.9..2.1",
                  "protocol_amendment": "FHAM_etape_1ter_amendement_4b.md",
                  "E_C_F_evaluation_pixels_opened": False,
                  "python": sys.version, "numpy": np.__version__,
                  "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT / ("pilot_provenance.json" if args.limit == 5 else "run_provenance.json")).write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    for i, row in enumerate(d.itertuples(index=False)):
        stem = Path(row.source_id).stem
        marker = OUT / f"{stem}_summary.csv"
        if marker.exists():
            continue
        summary, detail = run_cover(row, i)
        pd.DataFrame(summary).to_csv(marker, index=False)
        pd.DataFrame(detail).to_csv(OUT / f"{stem}_positions.csv.gz", index=False, compression="gzip")


if __name__ == "__main__":
    main()
