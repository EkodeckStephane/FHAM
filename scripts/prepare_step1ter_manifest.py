"""Freeze the hash-only 1ter BOWS2 split before any 1ter image metrics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/stability_step1/step1bis/manifest/split_manifest.csv"
OUT = ROOT / "results/stability_step1/step1ter/manifest"
SEED = "FHAM-1ter-20261118"


def rank_key(row: pd.Series) -> tuple[str, str]:
    value = hashlib.sha256(f"{SEED}:{row.sha256}".encode("ascii")).hexdigest()
    return value, str(row.source_id)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(SOURCE, keep_default_na=False)
    if frame.split.value_counts().to_dict() != {"C": 7525, "A": 200, "B": 200}:
        raise RuntimeError("1bis split is not the frozen 200/200/7525 allocation")
    if frame.evaluation_pixels_opened.astype(str).str.lower().eq("true").any():
        raise RuntimeError("Source split contains evaluation-opened images")
    c = frame.loc[frame.split.eq("C")].copy()
    keys = c.apply(rank_key, axis=1)
    c["amendment_rank_hash"] = [key[0] for key in keys]
    c["amendment_rank_tiebreak"] = [key[1] for key in keys]
    c = c.sort_values(["amendment_rank_hash", "amendment_rank_tiebreak"], kind="stable")
    c.loc[:, "split"] = "C"
    c.iloc[:200, c.columns.get_loc("split")] = "D"
    c.iloc[200:400, c.columns.get_loc("split")] = "E"
    c["selection_rank_1ter"] = range(1, len(c) + 1)
    c["evaluation_pixels_opened"] = False
    c["partition_seed"] = SEED
    c["partition_method"] = "ascending SHA256(seed + ':' + source_sha256), source_id tie-break"
    ab = frame.loc[frame.split.isin(["A", "B"])].copy()
    ab["selection_rank_1ter"] = pd.NA
    ab["partition_seed"] = "inherited frozen 1bis"
    ab["partition_method"] = "unchanged from committed 1bis manifest"
    result = pd.concat([ab, c], ignore_index=True)
    result.to_csv(OUT / "bows2_D_E_C_manifest.csv", index=False)
    counts = result.groupby("split").size().to_dict()
    if counts != {"A": 200, "B": 200, "C": 7125, "D": 200, "E": 200}:
        raise RuntimeError(f"Unexpected partition sizes: {counts}")
    if result.loc[result.split.eq("C"), "evaluation_pixels_opened"].astype(str).str.lower().eq("true").any():
        raise RuntimeError("C must remain unopened")
    sha = hashlib.sha256((OUT / "bows2_D_E_C_manifest.csv").read_bytes()).hexdigest()
    provenance = {
        "phase": "step0 hash-only partition freeze",
        "seed": SEED,
        "input_manifest": str(SOURCE.relative_to(ROOT)),
        "input_manifest_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "output_manifest": "bows2_D_E_C_manifest.csv",
        "output_manifest_sha256": sha,
        "counts": counts,
        "ordering": "ascending SHA256(seed + ':' + source_sha256), source_id tie-break, applied only to the prior C rows",
        "evaluation_pixels_opened": {"D": False, "E": False, "C": False},
        "evaluation_metrics_run": False,
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
