"""Create hash-only BOWS2 deduplication audit and frozen Step 1bis splits.

This utility decodes images only for SHA-256 and the preregistered pHash. It
does not render previews, create transformed images, calculate FHAM features,
or run evaluation metrics. In particular, BOWS2-C remains evaluation-closed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.fft import dctn

ROOT = Path(__file__).resolve().parents[1]
BOWS2_ROOT = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
DERIVED_ROOT = Path(r"C:\Users\User\Documents\Articles\Baleba\data\derived\multicorpus_v2_1000eval_512")
OUT = ROOT / "results" / "stability_step1" / "step1bis" / "manifest"
HISTORICAL_RAW = (
    ROOT / "results" / "raw" / "stratified_robustness" / "stratified_robustness_raw.csv",
    ROOT / "results" / "raw" / "benchmark_smoke" / "benchmark_assignment_raw.csv",
)
HISTORICAL_COLUMNS = {
    "stratified_robustness_raw.csv": ("dataset", "image", {"bows2": "BOWS2"}),
    "benchmark_assignment_raw.csv": ("dataset", "image", {"bows2": "BOWS2"}),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def phash64(path: Path) -> int:
    with Image.open(path) as source:
        image = source.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    coefficients = dctn(np.asarray(image, dtype=np.float64), type=2, norm="ortho")[:8, :8]
    threshold = float(np.median(coefficients.reshape(-1)[1:]))
    value = 0
    for coefficient in coefficients.reshape(-1):
        value = (value << 1) | int(coefficient > threshold)
    return value


def bands(value: int) -> tuple[int, int, int, int]:
    return tuple((value >> shift) & 0xFFFF for shift in (48, 32, 16, 0))


def near_reference(candidate_hash: int, reference_index: dict[int, set[int]],
                   references: list[dict]) -> list[tuple[int, int]]:
    possible: set[int] = set()
    for band_id, band_value in enumerate(bands(candidate_hash)):
        possible.update(reference_index.get((band_id << 16) | band_value, set()))
    return [(reference_id, distance)
            for reference_id in possible
            if (distance := (candidate_hash ^ references[reference_id]["phash_int"]).bit_count()) <= 4]


def build_reference_index(references: list[dict]) -> dict[int, set[int]]:
    index: dict[int, set[int]] = defaultdict(set)
    for reference_id, row in enumerate(references):
        for band_id, band_value in enumerate(bands(row["phash_int"])):
            index[(band_id << 16) | band_value].add(reference_id)
    return index


def add_reference(references: list[dict], path: Path, dataset: str, source_id: str,
                  expected_sha256: str | None = None) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = file_sha256(path)
    if expected_sha256 and digest != expected_sha256:
        raise RuntimeError(f"SHA-256 mismatch for reference {dataset}:{source_id}")
    references.append({
        "dataset": dataset,
        "source_id": source_id,
        "sha256": digest,
        "phash_int": phash64(path),
    })


def historical_bows2_ids() -> set[str]:
    used: set[str] = set()
    for raw_path in HISTORICAL_RAW:
        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)
        dataset_col, image_col, aliases = HISTORICAL_COLUMNS[raw_path.name]
        frame = pd.read_csv(raw_path, usecols=[dataset_col, image_col])
        matches = frame[dataset_col].astype(str).str.lower().eq("bows2")
        # Some raw files use a corpus label without a normalized spelling.
        if not matches.any():
            matches = frame[dataset_col].astype(str).str.lower().isin(aliases)
        used.update(Path(value).name for value in frame.loc[matches, image_col].astype(str))
    if len(used) != 2046:
        raise RuntimeError(f"Expected 2,046 historical BOWS2 identifiers; found {len(used)}")
    return used


def load_cross_corpus_references(historical: set[str], bows_manifest: dict[str, dict]) -> list[dict]:
    references: list[dict] = []

    for manifest_name, folder in (("stress", ROOT / "dataset" / "stress"),
                                  ("controlled", ROOT / "dataset" / "controlled")):
        manifest = pd.read_csv(folder / "manifest.csv")
        for row in manifest.to_dict("records"):
            add_reference(references, folder / row["file"], manifest_name, row["file"])

    # Audit every candidate used to create the prior 402-image sealed sample
    # and the 240 candidates marked as previously used, not only selected files.
    candidate_path = ROOT / "results" / "stability_step1" / "sealed_candidate_manifest.csv"
    candidate_frame = pd.read_csv(candidate_path, keep_default_na=False)
    if len(candidate_frame) != 800:
        raise RuntimeError(f"Expected 800 prior BOSSBase/COCO candidates; found {len(candidate_frame)}")
    for row in candidate_frame.to_dict("records"):
        folder = "bossbase_1_01" if row["corpus"] == "BOSSBase" else "ms_coco_val2017"
        path = DERIVED_ROOT / folder / row["filename"]
        add_reference(references, path, row["corpus"], row["filename"], row["sha256"])

    # Prior BOWS2 images are excluded by ID and also provide a perceptual
    # reference, so renamed near-duplicates cannot enter the new split.
    for name in sorted(historical):
        row = bows_manifest.get(name)
        if row is None:
            raise RuntimeError(f"Historical BOWS2 ID absent from manifest: {name}")
        add_reference(references, BOWS2_ROOT / row["relative_path"], "BOWS2_history", name,
                      row["sha256"])
    return references


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bows_frame = pd.read_csv(ROOT / "dataset" / "manifests" / "bows2.csv", keep_default_na=False)
    if len(bows_frame) != 10000 or not (bows_frame.width.eq(256) & bows_frame.height.eq(256)).all():
        raise RuntimeError("BOWS2 manifest is not the expected 10,000 native 256x256 images")
    bows_rows = {row["relative_path"]: row for row in bows_frame.to_dict("records")}
    by_name = {Path(name).name: row for name, row in bows_rows.items()}
    historical = historical_bows2_ids()
    references = load_cross_corpus_references(historical, by_name)
    reference_index = build_reference_index(references)
    reference_sha_index: dict[str, list[int]] = defaultdict(list)
    for reference_id, reference in enumerate(references):
        reference_sha_index[reference["sha256"]].append(reference_id)
    pd.DataFrame([{
        "reference_dataset": row["dataset"],
        "reference_id": row["source_id"],
        "sha256": row["sha256"],
        "phash": f"{row['phash_int']:016x}",
    } for row in references]).to_csv(OUT / "dedup_reference_hashes.csv", index=False)

    rows = []
    for relative_path, source_row in sorted(bows_rows.items()):
        path = BOWS2_ROOT / relative_path
        digest = file_sha256(path)
        if digest != source_row["sha256"]:
            raise RuntimeError(f"BOWS2 manifest SHA-256 mismatch: {relative_path}")
        rows.append({
            "source_id": Path(relative_path).name,
            "relative_path": relative_path,
            "sha256": digest,
            "phash_int": phash64(path),
            "historically_used": Path(relative_path).name in historical,
            "cross_corpus_matches": [],
            "intra_bows2_duplicate": False,
        })

    matches = []
    for row in rows:
        cross = near_reference(row["phash_int"], reference_index, references)
        # Exact byte matches are detected independently of perceptual hash.
        exact = reference_sha_index.get(row["sha256"], [])
        match_ids = set(i for i, _ in cross) | set(exact)
        row["cross_corpus_matches"] = sorted(match_ids)
        for reference_id in sorted(match_ids):
            ref = references[reference_id]
            distance = (row["phash_int"] ^ ref["phash_int"]).bit_count()
            matches.append({
                "bows2_id": row["source_id"],
                "reference_dataset": ref["dataset"],
                "reference_id": ref["source_id"],
                "sha256_exact": row["sha256"] == ref["sha256"],
                "phash_hamming": distance,
            })

    candidate_indices = [i for i, row in enumerate(rows) if not row["historically_used"]]
    local_index: dict[int, set[int]] = defaultdict(set)
    local_pairs = set()
    for i in candidate_indices:
        value = rows[i]["phash_int"]
        possible: set[int] = set()
        for band_id, band_value in enumerate(bands(value)):
            possible.update(local_index.get((band_id << 16) | band_value, set()))
        for j in possible:
            if (value ^ rows[j]["phash_int"]).bit_count() <= 4:
                local_pairs.add((j, i))
        for band_id, band_value in enumerate(bands(value)):
            local_index[(band_id << 16) | band_value].add(i)

    intra_excluded = set()
    for left, right in sorted(local_pairs):
        rows[left]["intra_bows2_duplicate"] = True
        rows[right]["intra_bows2_duplicate"] = True
        intra_excluded.update((left, right))
        matches.append({
            "bows2_id": rows[right]["source_id"],
            "reference_dataset": "BOWS2_candidate",
            "reference_id": rows[left]["source_id"],
            "sha256_exact": rows[right]["sha256"] == rows[left]["sha256"],
            "phash_hamming": (rows[right]["phash_int"] ^ rows[left]["phash_int"]).bit_count(),
        })

    cross_excluded = {i for i, row in enumerate(rows) if row["cross_corpus_matches"]}
    eligible = [i for i in candidate_indices if i not in cross_excluded and i not in intra_excluded]
    eligible.sort(key=lambda i: rows[i]["sha256"])
    if len(eligible) < 600:
        raise RuntimeError(f"Need at least 600 eligible images for A/B/C; found {len(eligible)}")

    for row in rows:
        row["phash"] = f"{row['phash_int']:016x}"
        row["cross_corpus_match_count"] = len(row.pop("cross_corpus_matches"))
        row.pop("phash_int")
        row["split"] = "excluded"
        row["exclude_reason"] = "historical BOWS2 use" if row["historically_used"] else "duplicate audit"
        row["dedup_hash_only"] = True
        row["evaluation_pixels_opened"] = False
    for rank, index in enumerate(eligible):
        row = rows[index]
        row["exclude_reason"] = ""
        row["selection_rank"] = rank + 1
        row["split"] = "A" if rank < 200 else "B" if rank < 400 else "C"

    columns = ["source_id", "relative_path", "sha256", "phash", "historically_used",
               "intra_bows2_duplicate", "cross_corpus_match_count", "split", "selection_rank",
               "exclude_reason", "dedup_hash_only", "evaluation_pixels_opened"]
    pd.DataFrame(rows)[columns].to_csv(OUT / "bows2_hash_only_manifest.csv", index=False)
    pd.DataFrame(matches, columns=["bows2_id", "reference_dataset", "reference_id",
                                   "sha256_exact", "phash_hamming"]).to_csv(
        OUT / "dedup_matches.csv", index=False)
    pd.DataFrame([row for row in rows if row["split"] != "excluded"])[columns].to_csv(
        OUT / "split_manifest.csv", index=False)

    split_counts = pd.Series([row["split"] for row in rows]).value_counts().to_dict()
    summary = {
        "method": "SHA-256 plus preregistered 64-bit pHash; exact Hamming audit at threshold 4",
        "pHash": "Pillow L grayscale; 32x32 LANCZOS; scipy.fft.dctn type II, norm=ortho; row-major 8x8 low-frequency coefficients; median of 63 AC coefficients; strict greater-than threshold; MSB first",
        "phash_band_audit": "four contiguous 16-bit bands; every pair with Hamming distance <=4 shares at least one band",
        "bows2_source_manifest_sha256": file_sha256(ROOT / "dataset" / "manifests" / "bows2.csv"),
        "historical_bows2_identifiers": len(historical),
        "cross_corpus_reference_images": len(references),
        "dedicated_scenes11_source_available": False,
        "scenes11_scope_note": "No standalone Scenes-11 image bundle is present in the repository or declared local manifests; all 219 local stress images and eight controlled images are included in the hash-only audit.",
        "bows2_native_images_hashed": len(rows),
        "all_bows2_ids_matching_a_dedup_reference": len(cross_excluded),
        "nonhistorical_candidates_matching_a_reference": sum(
            bool(row["cross_corpus_match_count"])
            for row in rows if not row["historically_used"]
        ),
        "intra_bows2_matched_pairs": len(local_pairs),
        "intra_bows2_excluded_images": len(intra_excluded),
        "eligible_after_all_exclusions": len(eligible),
        "split_counts_including_excluded": split_counts,
        "pixels_used_only_for_hash_deduplication": True,
        "evaluation_pixels_opened": {"A": False, "B": False, "C": False},
        "phase_b_author_go_received": False,
        "dedup_script_sha256": file_sha256(Path(__file__)),
        "environment_record_sha256": file_sha256(
            ROOT / "results" / "stability_step1" / "step1bis_environment.json"
        ),
    }
    (OUT / "dedup_provenance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
