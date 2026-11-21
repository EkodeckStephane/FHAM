#!/usr/bin/env python3
"""Hash-only manifest freeze for post-hoc E/C/F geometry extension."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/step2/geometry/manifests"
BOWS_SOURCE = ROOT / "results/stability_step1/step1bis/manifest/split_manifest.csv"
BOWS_USED_C = ROOT / "results/stability_step1/step1quater/run/final_freeze/C_final_manifest_hash_only.csv"
BOSS_SOURCE = ROOT / "results/stability_step1/step1ter/manifest/bossbase_F_hash_only_manifest.csv"
BOSS_USED_F = ROOT / "results/stability_step1/step1quater/run/final_freeze/F_final_manifest_hash_only.csv"
BOWS_ROOT = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
BOSS_ROOT = Path(r"C:\Users\User\Downloads\Compressed\cpu_stego_experiments\datasets\BOSSbase")


def rank(seed: str, sha: str) -> str:
    return hashlib.sha256(f"{seed}|{sha}".encode("ascii")).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bows = pd.read_csv(BOWS_SOURCE, keep_default_na=False)
    used_c = pd.read_csv(BOWS_USED_C, keep_default_na=False)
    if len(used_c) != 200:
        raise RuntimeError("expected the 200 previously used 1quater C images")
    used_ids, used_hashes = set(used_c.source_id.astype(str)), set(used_c.sha256.astype(str))
    c = bows[(bows.split == "C") & (~bows.historically_used.astype(bool))
             & (~bows.intra_bows2_duplicate.astype(bool))
             & (bows.cross_corpus_match_count.astype(int) == 0)].copy()
    c = c[~c.source_id.astype(str).isin(used_ids) & ~c.sha256.astype(str).isin(used_hashes)]
    if len(c) < 400:
        raise RuntimeError(f"only {len(c)} eligible unused BOWS2-C images remain")
    c["selection_rank"] = c.sha256.map(lambda s: rank("FHAM-step2-Egeo-posthoc-20261121", s))
    e = c.sort_values(["selection_rank", "source_id"], kind="stable").head(200).copy()
    e_ids, e_hashes = set(e.source_id.astype(str)), set(e.sha256.astype(str))
    c = c[~c.source_id.astype(str).isin(e_ids) & ~c.sha256.astype(str).isin(e_hashes)].copy()
    c["selection_rank"] = c.sha256.map(lambda s: rank("FHAM-step2-Cgeo-posthoc-20261121", s))
    c = c.sort_values(["selection_rank", "source_id"], kind="stable").head(200).copy()

    boss = pd.read_csv(BOSS_SOURCE, keep_default_na=False)
    used_f = pd.read_csv(BOSS_USED_F, keep_default_na=False)
    if len(used_f) != 200:
        raise RuntimeError("expected the 200 previously used 1quater F images")
    used_f_ids, used_f_hashes = set(used_f.source_id.astype(str)), set(used_f.sha256.astype(str))
    eligible = boss[(~boss.prior_candidate_id.astype(bool))
                    & (~boss.prior_candidate_hash.astype(bool))
                    & (boss.near_prior_candidate_ids.astype(str) == "")
                    & (~boss.intra_candidate_duplicate.astype(bool))
                    & (boss.sha256.astype(str).map(lambda x: len(x) == 64))].copy()
    eligible = eligible[~eligible.source_id.astype(str).isin(used_f_ids)
                        & ~eligible.sha256.astype(str).isin(used_f_hashes)]
    if len(eligible) < 200:
        raise RuntimeError(f"only {len(eligible)} eligible unused BOSSBase images remain")
    eligible["selection_rank"] = eligible.sha256.map(
        lambda s: rank("FHAM-step2-Fgeo-posthoc-20261121", s))
    f = eligible.sort_values(["selection_rank", "source_id"], kind="stable").head(200).copy()

    manifests = {}
    for name, frame, image_root, corpus in (("E_geo", e, BOWS_ROOT, "BOWS2-C"),
                                             ("C_geo", c, BOWS_ROOT, "BOWS2-C"),
                                             ("F_geo", f, BOSS_ROOT, "BOSSBase")):
        rows = []
        for row in frame.itertuples(index=False):
            rel = str(row.source_id)
            rows.append({"corpus": corpus, "source_id": rel,
                         "relative_path": rel,
                         "absolute_path": str(image_root / rel),
                         "sha256": str(row.sha256),
                         "selection_rank": str(row.selection_rank),
                         "pixels_opened": False})
        output = pd.DataFrame(rows).sort_values(["selection_rank", "source_id"], kind="stable")
        path = OUT / f"{name}_manifest_hash_only.csv"
        output.to_csv(path, index=False)
        manifests[name] = {"count": len(output), "manifest_sha256": file_sha(path),
                           "ids": output.source_id.tolist()}

    meta = {"status": "hash-only manifests frozen; no selected image pixels read",
            "selection_date": "2026-11-21", "extension": "post hoc at author direction after initial G-2 stop",
            "source_manifests": {str(p.relative_to(ROOT)): file_sha(p)
                                 for p in (BOWS_SOURCE, BOWS_USED_C, BOSS_SOURCE, BOSS_USED_F)},
            "manifests": {k: {"count": v["count"], "sha256": v["manifest_sha256"]}
                          for k, v in manifests.items()},
            "exclusions": {"E_C": "previous 1quater C images, historically used images, within-BOWS2 near-duplicates and cross-corpus matches",
                           "C_geo": "all E_geo exclusions plus all E_geo images",
                           "F_geo": "prior 1ter candidates/hashes/near duplicates, intra-candidate duplicates, prior 1quater F images"},
            "p4_grid": "625 local candidates per segment; full ranges and order in the committed post-hoc extension protocol",
            "sealed_labels": "the sets are post-hoc exploratory due to the initial G-G2 stop; each is still opened once after P4 freeze"}
    (OUT / "posthoc_manifest_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: {"count": v["count"], "sha256": v["manifest_sha256"]}
                      for k, v in manifests.items()}, indent=2))


if __name__ == "__main__":
    main()
