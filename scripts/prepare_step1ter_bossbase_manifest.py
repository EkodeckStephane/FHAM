"""Hash-only reservation of BOSSBase-F; performs no FHAM evaluation."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.fft import dctn

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Users\User\Downloads\Compressed\cpu_stego_experiments\datasets\BOSSbase")
OLD = ROOT / "results/stability_step1/sealed_candidate_manifest.csv"
OUT = ROOT / "results/stability_step1/step1ter/manifest"
SEED = "FHAM-1ter-20261118"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def phash(path: Path) -> int:
    with Image.open(path) as im:
        image = im.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    coefficients = dctn(np.asarray(image, dtype=np.float64), type=2, norm="ortho")[:8, :8]
    threshold = float(np.median(coefficients.reshape(-1)[1:]))
    result = 0
    for value in coefficients.reshape(-1):
        result = (result << 1) | int(value > threshold)
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(OLD, keep_default_na=False)
    old = old.loc[old.corpus.eq("BOSSBase")]
    if len(old) != 400:
        raise RuntimeError(f"Expected 400 prior BOSSBase candidates, found {len(old)}")
    old_ids = set(old.source_id.astype(str))
    old_hashes = set(old.source_sha256.astype(str))
    files = sorted(SOURCE.glob("*.pgm"), key=lambda p: p.name)
    if len(files) != 10000:
        raise RuntimeError(f"Expected 10,000 BOSSBase PGM files, found {len(files)}")
    references = {p.name: phash(SOURCE / p.name) for p in files if p.name in old_ids}
    rows = []
    for n, path in enumerate(files, 1):
        sha = digest(path)
        value = phash(path)
        near = [name for name, ref in references.items()
                if name != path.name and (value ^ ref).bit_count() <= 4]
        rows.append({"source_id": path.name, "sha256": sha,
                     "phash": f"{value:016x}", "prior_candidate_id": path.name in old_ids,
                     "prior_candidate_hash": sha in old_hashes,
                     "near_prior_candidate_ids": ";".join(sorted(near)),
                     "evaluation_pixels_opened": False})
        if n % 1000 == 0:
            print(f"hash-only inventory {n}/10000", flush=True)
    frame = pd.DataFrame(rows)
    excluded_prior = frame.prior_candidate_id | frame.prior_candidate_hash | frame.near_prior_candidate_ids.ne("")
    eligible = frame.loc[~excluded_prior].copy()
    # Exclude both members of any candidate-to-candidate near-duplicate pair.
    values = {r.source_id: int(r.phash, 16) for r in eligible.itertuples(index=False)}
    ids = sorted(values)
    duplicate_ids = set()
    band_index: dict[tuple[int, int], set[str]] = defaultdict(set)
    for source_id in ids:
        value = values[source_id]
        candidates = set()
        for band, shift in enumerate((48, 32, 16, 0)):
            candidates.update(band_index.get((band, (value >> shift) & 0xFFFF), set()))
        for other in candidates:
            if (value ^ values[other]).bit_count() <= 4:
                duplicate_ids.update((source_id, other))
        for band, shift in enumerate((48, 32, 16, 0)):
            band_index[(band, (value >> shift) & 0xFFFF)].add(source_id)
    frame["intra_candidate_duplicate"] = frame.source_id.isin(duplicate_ids)
    eligible = frame.loc[~excluded_prior & ~frame.intra_candidate_duplicate].copy()
    eligible["selection_key"] = eligible.sha256.map(
        lambda value: hashlib.sha256(f"{SEED}:{value}".encode("ascii")).hexdigest())
    eligible = eligible.sort_values(["selection_key", "source_id"], kind="stable")
    if len(eligible) < 200:
        raise RuntimeError(f"Only {len(eligible)} BOSSBase-F candidates remain")
    selected = set(eligible.head(200).source_id)
    frame["split"] = "excluded"
    frame.loc[frame.source_id.isin(selected), "split"] = "F"
    frame["exclude_reason"] = "prior/near duplicate or not selected"
    frame.loc[frame.split.eq("F"), "exclude_reason"] = ""
    frame["partition_seed"] = SEED
    frame.to_csv(OUT / "bossbase_F_hash_only_manifest.csv", index=False)
    summary = {"phase": "step0 hash-only reservation; no FHAM metrics",
               "seed": SEED, "source_root": str(SOURCE), "source_count": len(files),
               "prior_candidates_excluded": len(old_ids),
               "prior_sha256_excluded": len(old_hashes),
               "intra_candidate_near_duplicates_excluded": len(duplicate_ids),
               "eligible_after_exclusions": len(eligible), "F_count": len(selected),
               "manifest_sha256": digest(OUT / "bossbase_F_hash_only_manifest.csv"),
               "evaluation_pixels_opened": False, "evaluation_metrics_run": False,
               "pHash": "Pillow grayscale 32x32 LANCZOS; SciPy DCT-II orthonormal; low-frequency 8x8; median AC; MSB-first"}
    (OUT / "bossbase_F_provenance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
