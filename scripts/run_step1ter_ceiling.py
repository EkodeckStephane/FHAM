"""Run 1ter Steps 2–3 on BOWS2-D (exploratory; C and F remain closed)."""
from __future__ import annotations

import hashlib
import io
import json
import argparse
import math
import sys
import time
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fham.hashing import spectral_comparison_margins
from fham.methods import BoundedAssignmentMethod, OptimalAssignmentMethod
from fham.stability import _block_payloads, estimate_position_stability
from stability_step1_pilot import transform

SOURCE = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
MANIFEST = ROOT / "results/stability_step1/step1ter/manifest/bows2_D_E_C_manifest.csv"
OUT = ROOT / "results/stability_step1/step1ter/step2_3"
SEED = 20261118
FAMILIES = ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated")
BOUNDS = (2, 4, 8)
PROFILES = (12, 24)


def read_image(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L"))


def dev_images(image: np.ndarray, cover_idx: int, profile: int):
    jpeg, noise = [], []
    rng = np.random.default_rng(SEED + cover_idx * 997 + profile * 17)
    for k in range(100):
        q = int(rng.integers(70, 91))
        if 74 <= q <= 76:
            q = 73 if (k % 2 == 0) else 77
        s = float(rng.uniform(1.0, 2.4))
        if 1.9 <= s <= 2.1:
            s = 1.89 if (k % 2 == 0) else 2.11
        jpeg.append(transform(image, f"jpeg{q}", SEED + cover_idx * 2000 + profile * 100 + k, "bilinear"))
        noise.append(transform(image, f"noise{s:.8f}", SEED + cover_idx * 2000 + profile * 100 + 1000 + k, "bilinear"))
    return jpeg, noise


def messages(length: int):
    out = []
    for family in FAMILIES:
        for idx in range(3):
            raw = (ROOT / "dataset/messages" / family / f"{family}_{length}_{idx:02d}.bin").read_bytes()
            compressed = zlib.compress(raw, 9)
            out.append((family, idx, len(raw), compressed, compressed.decode("latin-1")))
    return out


def score_and_diagnostics(image, profile, cover_idx):
    lookup = OptimalAssignmentMethod(profile, "spectral")
    lookup.build_lookup_table(image)
    locations = [loc for entries in lookup.lookup_table.values() for loc in entries]
    jpeg, noise = dev_images(image, cover_idx, profile)
    s_jpeg, _, _ = estimate_position_stability(image, locations, profile, "spectral", jpeg)
    s_noise, _, _ = estimate_position_stability(image, locations, profile, "spectral", noise)
    base_by_xy = {}
    for value, entries in lookup.lookup_table.items():
        for loc in entries:
            base_by_xy[(loc.x, loc.y, loc.arrangement)] = value
    bit_flips = Counter()
    margin_rows = []
    # Step-2 bit-flip and baseline-margin diagnostics on the 100 D covers.
    for fam, attacked_images in (("jpeg", jpeg), ("noise", noise)):
        for sample, attacked in enumerate(attacked_images):
            attacked_blocks = _block_payloads(
                attacked, sorted({(loc.x, loc.y) for loc in locations}), profile, "spectral")
            for loc in locations:
                old = base_by_xy[(loc.x, loc.y, loc.arrangement)]
                new = attacked_blocks[(loc.x, loc.y)][0][loc.arrangement]
                xor = old ^ new
                for bit in range(8):
                    if (xor >> bit) & 1:
                        bit_flips[(fam, loc.arrangement, bit)] += 1
            if sample == 0:
                pass
    # Recompute family-specific survival counts from each family independently.
    # The combined `counts` above is intentionally not used for selection.
    family_scores = {"jpeg": s_jpeg, "noise": s_noise}
    robust = {loc for loc in locations if s_jpeg[loc] == 1.0 and s_noise[loc] == 1.0}
    margin_by_arr = defaultdict(list)
    for y in range(0, image.shape[0] - profile + 1, profile):
        for x in range(0, image.shape[1] - profile + 1, profile):
            margins = spectral_comparison_margins(image[y:y+profile, x:x+profile])
            for arrangement in range(4):
                for bit, value in enumerate(margins[arrangement]):
                    margin_by_arr[(arrangement, bit)].append(float(abs(value)))
    diag = []
    for (fam, arrangement, bit), flip_count in sorted(bit_flips.items()):
        diag.append({"family": fam, "arrangement": arrangement, "bit_lsb_index": bit,
                     "flips": flip_count, "comparisons": 100 * len(locations),
                     "flip_rate": flip_count / (100 * len(locations))})
    margins = [{"arrangement": a, "bit_lsb_index": b,
                "median_abs_margin": float(np.median(vals)),
                "p05_abs_margin": float(np.quantile(vals, .05)),
                "p95_abs_margin": float(np.quantile(vals, .95))}
               for (a, b), vals in sorted(margin_by_arr.items())]
    return lookup, locations, family_scores, robust, diag, margins


def evaluate_cover(row, cover_idx):
    image_path = SOURCE / str(row.relative_path)
    image = read_image(image_path)
    if image.shape != (256, 256):
        raise RuntimeError(f"Unexpected BOWS2 shape for {row.source_id}: {image.shape}")
    all_summary, all_diag, all_margins, all_location_scores = [], [], [], []
    for profile in PROFILES:
        t0 = time.perf_counter()
        lookup, locations, fam_scores, robust, diag, margins = score_and_diagnostics(image, profile, cover_idx)
        all_diag.extend({"cover": row.source_id, "profile": profile, **d} for d in diag)
        all_margins.extend({"cover": row.source_id, "profile": profile, **d} for d in margins)
        hash_by_location = {loc: value for value, entries in lookup.lookup_table.items() for loc in entries}
        all_location_scores.extend({
            "cover": row.source_id, "profile": profile, "x": loc.x, "y": loc.y,
            "arrangement": loc.arrangement, "hash_value": hash_by_location[loc],
            "s_jpeg": fam_scores["jpeg"][loc], "s_noise": fam_scores["noise"][loc],
            "robust": int(loc in robust),
        } for loc in locations)
        robust_lookup = defaultdict(list)
        for value, entries in lookup.lookup_table.items():
            robust_lookup[value] = [loc for loc in entries if loc in robust]
        for bound in BOUNDS:
            for source_length in (100, 200):
                feasible_cover = True
                for family, idx, raw_length, coded, payload in messages(source_length):
                    method = BoundedAssignmentMethod(bound, profile, "spectral")
                    method.lookup_table = {v: ls for v, ls in robust_lookup.items() if ls}
                    if not method.lookup_table:
                        method.lookup_table = {-1: []}
                    method.image_shape = image.shape
                    assignment = method.embed(payload, image)
                    feasible = assignment is not None
                    if source_length == 100:
                        feasible_cover &= feasible
                    acc = exact = None
                    if feasible:
                        for attack_name, attack in (
                            ("jpeg75", transform(image, "jpeg75", SEED + cover_idx * 11 + 1, "bicubic")),
                            ("noise2", transform(image, "noise2", SEED + cover_idx * 11 + 2, "bicubic")),
                        ):
                            recovered = method.extract(assignment, attack).encode("latin-1")
                            acc = sum(a == b for a, b in zip(coded, recovered)) / len(coded)
                            exact = int(recovered == coded)
                            all_summary.append({"cover": row.source_id, "profile": profile,
                                "bound": bound, "source_length": source_length,
                                "compressed_length": len(coded), "family": family, "index": idx,
                                "attack": attack_name, "feasible": 1,
                                "D1": sum(abs(x) for x in assignment.displacements),
                                "accuracy": acc, "exact": exact,
                                "robust_positions": len(robust), "total_positions": len(locations),
                                "elapsed_cover_seconds": time.perf_counter()-t0})
                    if not feasible:
                        all_summary.append({"cover": row.source_id, "profile": profile,
                            "bound": bound, "source_length": source_length,
                            "compressed_length": len(coded), "family": family, "index": idx,
                            "attack": "none", "feasible": 0, "D1": None,
                            "accuracy": None, "exact": 0,
                            "robust_positions": len(robust), "total_positions": len(locations),
                            "elapsed_cover_seconds": time.perf_counter()-t0})
                all_summary.append({"cover": row.source_id, "profile": profile,
                    "bound": bound, "source_length": source_length,
                    "compressed_length": None, "family": "ALL12", "index": -1,
                    "attack": "feasibility_12_all", "feasible": int(feasible_cover),
                    "D1": None, "accuracy": None, "exact": None,
                    "robust_positions": len(robust), "total_positions": len(locations),
                    "elapsed_cover_seconds": time.perf_counter()-t0})
        print(f"[D {cover_idx+1}/100] {row.source_id} L={profile} robust={len(robust)}/{len(locations)} elapsed={time.perf_counter()-t0:.1f}s", flush=True)
    return all_summary, all_diag, all_margins, all_location_scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100,
                        help="Use 5 for the frozen timing pilot; 100 for the full D evaluation.")
    args = parser.parse_args()
    if args.limit not in (5, 100):
        raise ValueError("The preregistered run permits only --limit 5 or --limit 100")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(MANIFEST, keep_default_na=False)
    d = manifest.loc[manifest.split.eq("D")].sort_values("selection_rank_1ter").head(args.limit)
    if len(d) != args.limit:
        raise RuntimeError(f"Need {args.limit} hash-frozen BOWS2-D images")
    provenance = {"seed": SEED, "protocol_commit_expected": "cf655f8",
                  "D_images": d.source_id.tolist(), "D_sha256": dict(zip(d.source_id, d.sha256)),
                  "run_limit": args.limit,
                  "profiles": PROFILES, "bounds": BOUNDS, "K_per_family": 100,
                  "development": "JPEG Q~U[70,90] excluding 74..76; Gaussian sigma~U[1,2.4] excluding 1.9..2.1",
                  "validation": {"JPEG": 75, "noise_sigma": 2},
                  "messages": "4 families x indices 00..02; zlib level 9; source lengths 100 and 200",
                  "python": sys.version, "numpy": np.__version__, "scipy": __import__("scipy").__version__,
                  "opencv": cv2.__version__, "evaluation_pixels_opened": {"D": True, "E": False, "C": False, "F": False}}
    provenance_name = "pilot_run_provenance.json" if args.limit == 5 else "run_provenance.json"
    (OUT / provenance_name).write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    for i, row in enumerate(d.itertuples(index=False)):
        marker = OUT / f"{Path(row.source_id).stem}_ceiling.csv"
        if marker.exists():
            continue
        t0 = time.perf_counter()
        summary, diag, margins, locscores = evaluate_cover(row, i)
        pd.DataFrame(summary).to_csv(marker, index=False)
        pd.DataFrame(diag).to_csv(OUT / f"{Path(row.source_id).stem}_bits.csv", index=False)
        pd.DataFrame(margins).to_csv(OUT / f"{Path(row.source_id).stem}_margins.csv", index=False)
        pd.DataFrame(locscores).to_csv(OUT / f"{Path(row.source_id).stem}_positions.csv.gz", index=False, compression="gzip")
        print(f"saved {row.source_id}; {time.perf_counter()-t0:.1f}s", flush=True)
    print(f"Step 2–3 cover outputs saved under {OUT}", flush=True)


if __name__ == "__main__":
    main()
