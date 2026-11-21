#!/usr/bin/env python3
"""Generate and hash-freeze the 10,000 protocol D-msg candidates."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_messages import generate

OUT = ROOT / "results/step2/detection"
SEED = 20261121
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")
COVERS = ROOT / "results/stability_step1/step1quater/manifest/D_b_images_sha256.csv"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cover_manifest = pd.read_csv(COVERS, keep_default_na=False)
    if len(cover_manifest) != 100:
        raise RuntimeError("protocol requires the frozen 100-cover D-b catalogue")
    cover_ids = cover_manifest.source_id.astype(str).tolist()
    existing = pd.read_csv(ROOT / "results/stability_step1/step1quater/manifest/messages_sha256.csv")
    old = set(existing.loc[existing.L_src == 100, "sha256"].astype(str))
    data_root = OUT / "messages"
    rows = []
    for family_index, family in enumerate(FAMILIES):
        family_dir = data_root / family
        family_dir.mkdir(parents=True, exist_ok=True)
        for candidate in range(2500):
            seed = SEED + family_index * 1_000_003 + candidate * 9173
            generation_seed = seed
            if family == "adversarial_repeated":
                rng = random.Random(seed)
                value = rng.randrange(256)
                payload = bytes([value]) * 100
                while hashlib.sha256(payload).hexdigest() in old:
                    value = (value + 1) % 256
                    payload = bytes([value]) * 100
            else:
                # Deterministically redraw only if the content duplicates a
                # frozen 1quater message; the candidate ID and first seed remain recorded.
                attempt_seed = seed
                while True:
                    payload = generate(family, 100, attempt_seed)
                    if hashlib.sha256(payload).hexdigest() not in old:
                        generation_seed = attempt_seed
                        break
                    attempt_seed += 1
            digest = hashlib.sha256(payload).hexdigest()
            path = family_dir / f"{family}_{candidate:05d}.bin"
            path.write_bytes(payload)
            pair_rank = sorted(
                range(len(cover_ids)),
                key=lambda cover_index: hashlib.sha256(
                    b"FHAM-DPAIR-v1" + bytes.fromhex(digest)
                    + cover_index.to_bytes(1, "big")
                ).digest(),
            )[:2]
            rows.append({"candidate_id": f"{family}_{candidate:05d}",
                         "family": family, "candidate_index": candidate,
                         "seed": seed, "generation_seed": generation_seed,
                         "source_bytes": len(payload),
                         "sha256": digest, "path": path.relative_to(ROOT).as_posix(),
                         "cover0_index": pair_rank[0], "cover1_index": pair_rank[1],
                         "cover0_id": cover_ids[pair_rank[0]],
                         "cover1_id": cover_ids[pair_rank[1]]})
    manifest = pd.DataFrame(rows)
    manifest.to_csv(OUT / "dmsg_candidates.csv", index=False)
    overlap = sorted(set(manifest.sha256.astype(str)) & old)
    if overlap:
        raise RuntimeError(f"D-msg overlaps the frozen 1quater source set ({len(overlap)} hashes)")
    unique = manifest.groupby("family").agg(
        candidates=("candidate_id", "count"), unique_contents=("sha256", "nunique"))
    unique.to_csv(OUT / "dmsg_candidate_content_counts.csv")
    metadata = {
        "seed": SEED, "families": list(FAMILIES), "candidates_per_family": 2500,
        "total_candidates": len(manifest), "source_bytes": 100,
        "cover_manifest_sha256": hashlib.sha256(COVERS.read_bytes()).hexdigest(),
        "candidate_manifest_sha256": hashlib.sha256((OUT / "dmsg_candidates.csv").read_bytes()).hexdigest(),
        "legacy_1quater_hash_overlaps": len(overlap),
        "generation": "seeded generate_messages for natural/ASCII/uniform; all-byte uniform repeated values, deterministic redraw on frozen-hash collision",
    }
    (OUT / "dmsg_candidates_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(unique.to_string())
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
