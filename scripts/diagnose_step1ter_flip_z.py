"""Post-run completion of Step 2: normalized z values at spectral bit flips."""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fham.methods import OptimalAssignmentMethod
from fham.stability import _block_payloads, estimate_position_stability
from stability_step1_pilot import transform

SOURCE = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
MANIFEST = ROOT / "results/stability_step1/step1ter/manifest/bows2_D_E_C_manifest.csv"
OUT = ROOT / "results/stability_step1/step1ter/step2_z_at_flip"
SEED = 20261118
PROFILES = (12, 24)
K = 100


def sample_attacks(image, cover_index, profile):
    rng = np.random.default_rng(SEED + cover_index * 997 + profile * 17)
    jpeg, noise = [], []
    for k in range(K):
        q = int(rng.integers(70, 91))
        if 74 <= q <= 76:
            q = 73 if k % 2 == 0 else 77
        sigma = float(rng.uniform(1.0, 2.4))
        if 1.9 <= sigma <= 2.1:
            sigma = 1.89 if k % 2 == 0 else 2.11
        jpeg.append(transform(image, f"jpeg{q}", SEED + cover_index * 2000 + profile * 100 + k, "bilinear"))
        noise.append(transform(image, f"noise{sigma:.8f}", SEED + cover_index * 2000 + profile * 100 + 1000 + k, "bilinear"))
    return {"jpeg": jpeg, "noise": noise}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(MANIFEST, keep_default_na=False)
    d = manifest.loc[manifest.split.eq("D")].sort_values("selection_rank_1ter").head(100)
    provenance = {"phase": "supplemental completion of frozen Step 2 diagnostic",
                  "reason": "initial runner stored flip counts and baseline margins but omitted normalized z at the flipped comparisons",
                  "D_images": d.source_id.tolist(), "K_per_family": K, "profiles": PROFILES,
                  "seed": SEED,
                  "z_definition": "absolute baseline comparison margin divided by per-comparison sample SD of development margin perturbations, using the frozen estimator's per-cover 5th-percentile sigma floor",
                  "E_C_F_evaluation_pixels_opened": False,
                  "script_sha256": __import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    for cover_index, row in enumerate(d.itertuples(index=False)):
        output = OUT / f"{Path(row.source_id).stem}_flip_z.csv"
        if output.exists():
            continue
        with Image.open(SOURCE / row.relative_path) as im:
            image = np.asarray(im.convert("L"))
        entries = []
        for profile in PROFILES:
            lookup = OptimalAssignmentMethod(profile, "spectral")
            lookup.build_lookup_table(image)
            locations = [loc for group in lookup.lookup_table.values() for loc in group]
            coordinates = sorted({(loc.x, loc.y) for loc in locations})
            base = {loc: value for value, group in lookup.lookup_table.items() for loc in group}
            variants = sample_attacks(image, cover_index, profile)
            for family, attacked_images in variants.items():
                _empirical, _continuous, margin_rows = estimate_position_stability(
                    image, locations, profile, "spectral", attacked_images)
                z_by_location = {
                    (int(r["x"]), int(r["y"]), int(r["arrangement"])): np.asarray(r["z"], dtype=float)
                    for r in margin_rows
                }
                flips = defaultdict(int)
                z_flips = defaultdict(list)
                for attacked in attacked_images:
                    blocks = _block_payloads(attacked, coordinates, profile, "spectral")
                    for loc in locations:
                        value = int(blocks[(loc.x, loc.y)][0][loc.arrangement])
                        xor = int(base[loc]) ^ value
                        z_vector = z_by_location[(loc.x, loc.y, loc.arrangement)]
                        for bit_lsb in range(8):
                            key = (loc.arrangement, 7 - bit_lsb)
                            if (xor >> bit_lsb) & 1:
                                flips[key] += 1
                                z_flips[key].append(float(z_vector[7 - bit_lsb]))
                for arrangement in range(4):
                    arrangement_positions = sum(loc.arrangement == arrangement for loc in locations)
                    for bit_msb in range(8):
                        key = (arrangement, bit_msb)
                        samples = np.asarray(z_flips[key], dtype=float)
                        entries.append({"cover": row.source_id, "profile": profile,
                            "family": family, "arrangement": arrangement,
                            "bit_msb_index": bit_msb, "comparisons": K * arrangement_positions,
                            "flips": int(flips[key]), "flip_rate": flips[key] / (K * arrangement_positions),
                            "n_flips_with_z": len(samples),
                            "z_flip_mean": float(samples.mean()) if len(samples) else np.nan,
                            "z_flip_median": float(np.median(samples)) if len(samples) else np.nan,
                            "z_flip_p05": float(np.quantile(samples, .05)) if len(samples) else np.nan,
                            "z_flip_p95": float(np.quantile(samples, .95)) if len(samples) else np.nan})
        pd.DataFrame(entries).to_csv(output, index=False)
        if (cover_index + 1) % 10 == 0:
            print(f"z-at-flip {cover_index+1}/100", flush=True)
    chunks = [pd.read_csv(p) for p in sorted(OUT.glob("*_flip_z.csv"))]
    data = pd.concat(chunks, ignore_index=True)
    summary = data.groupby(["profile", "family", "arrangement", "bit_msb_index"], as_index=False).agg(
        covers=("cover", "nunique"), flips=("flips", "sum"), comparisons=("comparisons", "sum"),
        median_cover_z_flip=("z_flip_median", "median"),
        mean_cover_z_flip=("z_flip_mean", "mean"),
        p05_cover_z_flip=("z_flip_p05", "median"),
        p95_cover_z_flip=("z_flip_p95", "median"))
    summary["flip_rate"] = summary.flips / summary.comparisons
    summary.to_csv(OUT / "z_at_flip_summary.csv", index=False)
    print(f"Saved normalized z-at-flip summary: {OUT / 'z_at_flip_summary.csv'}", flush=True)


if __name__ == "__main__":
    main()
