"""Repeat the robust-position ceiling for the two frozen Step 4b winners."""
from __future__ import annotations

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
from fham.methods import BoundedAssignmentMethod, Location
from fham.stability import _block_payloads
from stability_step1_pilot import transform

SOURCE = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
MANIFEST = ROOT / "results/stability_step1/step1ter/manifest/bows2_D_E_C_manifest.csv"
SCREEN = ROOT / "results/stability_step1/step1ter/step4b_screen"
SELECTED = ROOT / "results/stability_step1/step1ter/step4b_decision/selected_descriptors.json"
OUT = ROOT / "results/stability_step1/step1ter/step4b_ceiling"
FAMILIES = ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated")
BOUNDS = (2, 4, 8)
SEED = 20261118


def read_image(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L"))


def messages(length: int):
    for family in FAMILIES:
        for idx in range(3):
            source = (ROOT / "dataset/messages" / family / f"{family}_{length}_{idx:02d}.bin").read_bytes()
            coded = zlib.compress(source, 9)
            yield family, idx, source, coded


def decode_from_cache(assignment, received_cache, descriptor: str) -> bytes:
    hashes = []
    for location, delta in zip(assignment.locations, assignment.displacements):
        value = received_cache[(location.x, location.y)][location.arrangement]
        hashes.append(max(0, min(255, int(value) + int(delta))))
    return bytes(hashes)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    selected = json.loads(SELECTED.read_text(encoding="utf-8"))["selected_top_two"]
    if len(selected) != 2:
        raise RuntimeError("Expected exactly two frozen descriptors")
    manifest = pd.read_csv(MANIFEST, keep_default_na=False)
    d = manifest.loc[manifest.split.eq("D")].sort_values("selection_rank_1ter").head(100)
    if len(d) != 100:
        raise RuntimeError("Expected 100 BOWS2-D covers")
    provenance = {"step": "4b C3 robust-position ceiling rerun", "selected_descriptors": selected,
                  "selection_sha256": hashlib.sha256(SELECTED.read_bytes()).hexdigest(),
                  "D_images": d.source_id.tolist(), "D_sha256": dict(zip(d.source_id, d.sha256)),
                  "B": BOUNDS, "source_lengths": [100, 200], "K_per_family": 50,
                  "robust_rule": "zero hash flips in each of K=50 JPEG and K=50 noise samples",
                  "validation_attacks": {"jpeg_quality": 75, "noise_sigma": 2},
                  "E_C_F_evaluation_pixels_opened": False,
                  "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "python": sys.version, "numpy": np.__version__}
    (OUT / "run_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    for cover_index, row in enumerate(d.itertuples(index=False)):
        stem = Path(row.source_id).stem
        marker = OUT / f"{stem}_ceiling.csv"
        if marker.exists():
            continue
        image = read_image(SOURCE / row.relative_path)
        cover_rows = []
        for descriptor in selected:
            pos = pd.read_csv(SCREEN / f"{stem}_positions.csv.gz")
            pos = pos.loc[pos.descriptor.eq(descriptor)]
            profile = int(pos.block_size.iloc[0])
            locations = [Location(int(r.x), int(r.y), int(r.arrangement))
                         for r in pos.itertuples(index=False)]
            hash_by_location = {loc: int(value) for loc, value in zip(locations, pos.hash_value)}
            robust_locs = {loc for loc, flag in zip(locations, pos.robust) if int(flag) == 1}
            filtered = defaultdict(list)
            for loc in robust_locs:
                filtered[hash_by_location[loc]].append(loc)
            lookup = {v: ls for v, ls in filtered.items() if ls} or {-1: []}
            coordinates = sorted({(loc.x, loc.y) for loc in robust_locs})
            attacks = {
                "jpeg75": transform(image, "jpeg75", SEED + cover_index * 11 + 1, "bicubic"),
                "noise2": transform(image, "noise2", SEED + cover_index * 11 + 2, "bicubic"),
            }
            received = {name: _block_payloads(im, coordinates, profile, descriptor)
                        for name, im in attacks.items()}
            for bound in BOUNDS:
                method = BoundedAssignmentMethod(bound, profile, descriptor)
                method.lookup_table = lookup
                method.image_shape = image.shape
                all_success = True
                for source_length in (100, 200):
                    all_success = True
                    for family, idx, source, coded in messages(source_length):
                        payload = coded.decode("latin-1")
                        start = time.perf_counter()
                        assignment = method.embed(payload, image)
                        solve_ms = (time.perf_counter() - start) * 1000
                        feasible = assignment is not None
                        all_success &= feasible
                        if feasible:
                            # Identity reconstruction is a required implementation invariant.
                            original_bytes = bytes(max(0, min(255,
                                int(hash_by_location[loc]) + int(delta)))
                                for loc, delta in zip(assignment.locations, assignment.displacements))
                            if original_bytes != coded:
                                raise RuntimeError(f"Identity mismatch {row.source_id}/{descriptor}/{family}/{source_length}")
                            d1 = int(sum(abs(int(v)) for v in assignment.displacements))
                            for attack_name, cache in received.items():
                                decoded = decode_from_cache(assignment, cache, descriptor)
                                correct = sum(a == b for a, b in zip(coded, decoded))
                                try:
                                    source_exact = int(zlib.decompress(decoded) == source)
                                except zlib.error:
                                    source_exact = 0
                                cover_rows.append({"cover": row.source_id, "profile": profile,
                                    "descriptor": descriptor, "bound": bound,
                                    "source_length": source_length, "compressed_length": len(coded),
                                    "family": family, "index": idx, "attack": attack_name,
                                    "feasible": 1, "D1": d1, "accuracy": correct/len(coded),
                                    "exact_compressed": int(decoded == coded), "exact_source": source_exact,
                                    "robust_positions": len(robust_locs), "position_count": len(locations),
                                    "token_bits": math.ceil(math.log2(len(locations))),
                                    "residual_bits": math.ceil(math.log2(2*bound+1)),
                                    "fixed_bits_per_symbol": math.ceil(math.log2(len(locations))) + math.ceil(math.log2(2*bound+1)),
                                    "solve_ms": solve_ms})
                        else:
                            cover_rows.append({"cover": row.source_id, "profile": profile,
                                "descriptor": descriptor, "bound": bound,
                                "source_length": source_length, "compressed_length": len(coded),
                                "family": family, "index": idx, "attack": "none",
                                "feasible": 0, "D1": np.nan, "accuracy": np.nan,
                                "exact_compressed": 0, "exact_source": 0,
                                "robust_positions": len(robust_locs), "position_count": len(locations),
                                "token_bits": math.ceil(math.log2(len(locations))),
                                "residual_bits": math.ceil(math.log2(2*bound+1)),
                                "fixed_bits_per_symbol": math.ceil(math.log2(len(locations))) + math.ceil(math.log2(2*bound+1)),
                                "solve_ms": solve_ms})
                    cover_rows.append({"cover": row.source_id, "profile": profile,
                        "descriptor": descriptor, "bound": bound, "source_length": source_length,
                        "compressed_length": np.nan, "family": "ALL12", "index": -1,
                        "attack": "feasibility_12_all", "feasible": int(all_success),
                        "D1": np.nan, "accuracy": np.nan, "exact_compressed": np.nan,
                        "exact_source": np.nan, "robust_positions": len(robust_locs),
                        "position_count": len(locations), "token_bits": math.ceil(math.log2(len(locations))),
                        "residual_bits": math.ceil(math.log2(2*bound+1)),
                        "fixed_bits_per_symbol": math.ceil(math.log2(len(locations))) + math.ceil(math.log2(2*bound+1)),
                        "solve_ms": np.nan})
        pd.DataFrame(cover_rows).to_csv(marker, index=False)
        print(f"[{cover_index+1}/100] {row.source_id} finished", flush=True)


if __name__ == "__main__":
    main()
