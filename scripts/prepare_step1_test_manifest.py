"""Hash-only inventory and deterministic selection of sealed Step 1 candidates.

This script never decodes image pixels. It records file hashes and source IDs so
eligibility and the final sample can be frozen before pixel-level evaluation.
"""

from __future__ import annotations

import csv
import hashlib
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DERIVED = Path(r"C:\Users\User\Documents\Articles\Baleba\data\derived\multicorpus_v2_1000eval_512")
DEFAULT_SOURCE_MANIFEST = Path(r"C:\Users\User\Documents\Articles\Mama Assandje\Curvature Fragile Authentication\.project\multicorpus_v2_1000eval_512_manifest.csv")
SEED = "FHAM-Step1-test-20261116"
SAMPLE_SIZE = 201


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_sources(source_manifest: Path) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    with source_manifest.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            name = Path(row["derived_relative_path"]).stem
            corpus = {"bossbase_1_01": "BOSSBase", "ms_coco_val2017": "COCO"}.get(
                row["subcorpus"], row["subcorpus"]
            )
            mapping[name] = {
                "dataset": corpus,
                "source_id": row["source_relative_path"],
                "source_sha256": row["source_sha256"],
                "derived_sha256": row["derived_sha256"],
                "source_root_name": row["source_root_name"],
                "split": row["split"],
            }
    return mapping


def prior_used_sources() -> dict[str, set[str]]:
    names = {"BOSSBase": set(), "COCO": set()}
    raw_files = [
        (ROOT / "results" / "raw" / "stratified_robustness" / "stratified_robustness_raw.csv", {
            "bossbase": "BOSSBase", "coco2017_val": "COCO"
        }),
        (ROOT / "results" / "raw" / "benchmark_smoke" / "benchmark_assignment_raw.csv", {
            "bossbase": "BOSSBase", "coco2017_val": "COCO"
        }),
    ]
    for path, aliases in raw_files:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                corpus = aliases.get(row.get("dataset", ""))
                if corpus:
                    names[corpus].add(Path(row.get("image", "")).name)

    descriptor_raw = ROOT / "results" / "descriptor_selection_validation_raw.csv"
    if descriptor_raw.exists():
        with descriptor_raw.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                names["BOSSBase"].add(Path(row.get("image", "").removeprefix("bossbase_val_")).name)

    hashes = {"BOSSBase": set(), "COCO": set()}
    manifest_paths = {
        "BOSSBase": ROOT / "dataset" / "manifests" / "bossbase.csv",
        "COCO": ROOT / "dataset" / "manifests" / "coco2017_val.csv",
    }
    for corpus, path in manifest_paths.items():
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if Path(row["relative_path"]).name in names[corpus]:
                    hashes[corpus].add(row["sha256"])
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--derived-root", type=Path, default=DEFAULT_DERIVED)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    args = parser.parse_args()
    source_map = candidate_sources(args.source_manifest)
    previously_used = prior_used_sources()
    records = []
    selected = []
    for folder, corpus in (("bossbase_1_01", "BOSSBase"),
                           ("ms_coco_val2017", "COCO")):
        paths = sorted((args.derived_root / folder).glob("*.png"))
        corpus_rows = []
        for path in paths:
            source = source_map.get(path.stem, {})
            if source.get("dataset") != corpus:
                source = {"dataset": corpus, "source_id": "UNMAPPED:" + path.stem}
            record = {
                "corpus": corpus,
                "filename": path.name,
                "source_id": source.get("source_id"),
                "source_sha256": source.get("source_sha256", ""),
                "derived_sha256_manifest": source.get("derived_sha256", ""),
                "source_root_name": source.get("source_root_name", ""),
                "source_split": source.get("split", ""),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
                "previously_used_in_fham": source.get("source_sha256", "") in previously_used[corpus],
                "eligible": False,
                "selection_rank": "",
                "selected_for_sealed_test": False,
                "selection_seed": SEED,
                "pixels_opened": False,
            }
            corpus_rows.append(record)
        eligible = [row for row in corpus_rows if not row["previously_used_in_fham"]]
        if len(eligible) < SAMPLE_SIZE:
            raise RuntimeError(
                f"{corpus}: only {len(eligible)} eligible candidates after excluding prior FHAM samples"
            )
        ranked = sorted(eligible, key=lambda row: hashlib.sha256(
            f"{SEED}:{corpus}:{row['source_id']}".encode()).hexdigest())
        for row in ranked:
            row["eligible"] = True
        for rank, row in enumerate(ranked, 1):
            row["selection_rank"] = rank
            row["selected_for_sealed_test"] = rank <= SAMPLE_SIZE
            row["selection_seed"] = SEED
        records.extend(corpus_rows)
        selected.extend(row for row in ranked[:SAMPLE_SIZE])

    out = ROOT / "results" / "stability_step1"
    out.mkdir(parents=True, exist_ok=True)
    fields = ["corpus", "filename", "source_id", "source_sha256",
              "derived_sha256_manifest", "source_root_name", "source_split", "sha256",
              "size_bytes", "previously_used_in_fham", "eligible", "selection_rank", "selected_for_sealed_test",
              "selection_seed", "pixels_opened"]
    for filename, rows in (("sealed_candidate_manifest.csv", records),
                           ("sealed_test_selection.csv", selected)):
        with (out / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    summary = {
        "seed": SEED,
        "selection_size_per_corpus": SAMPLE_SIZE,
        "candidate_counts": {
            corpus: sum(row["corpus"] == corpus for row in records)
            for corpus in ("BOSSBase", "COCO")
        },
        "mapped_source_count": {
            corpus: sum(row["corpus"] == corpus and not row["source_id"].startswith("UNMAPPED:")
                        for row in records)
            for corpus in ("BOSSBase", "COCO")
        },
        "previously_used_counts_excluded": {
            corpus: sum(row["corpus"] == corpus and row["previously_used_in_fham"]
                        for row in records)
            for corpus in ("BOSSBase", "COCO")
        },
        "eligible_counts": {
            corpus: sum(row["corpus"] == corpus and row["eligible"] for row in records)
            for corpus in ("BOSSBase", "COCO")
        },
        "pixel_evaluation_performed": False,
        "source_manifest_sha256": sha256(args.source_manifest),
        "selection_status": "deterministically selected after overlap audit and LFW-val freeze; pixel evaluation awaits the pre-test commit",
    }
    (out / "sealed_test_manifest_provenance.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
