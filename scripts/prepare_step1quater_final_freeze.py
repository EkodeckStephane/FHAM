#!/usr/bin/env python3
"""Pre-open sizing clarification and hash-only C/F manifests for 1quater."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/stability_step1/step1quater/run"
OUT = RUN / "final_freeze"
PARTITIONS = ROOT / "results/stability_step1/step1ter/manifest/bows2_D_E_C_manifest.csv"
F_MANIFEST = ROOT / "results/stability_step1/step1ter/manifest/bossbase_F_hash_only_manifest.csv"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trials_path = RUN / "grid_trials_12x100.csv.gz"
    lock_path = RUN / "GQ2_configuration_freeze.json"
    gate_path = RUN / "E_validation/GQ3_gate.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate["G_Q3_all_frozen_checks_pass"] or gate["C_pixels_opened"] or gate["F_pixels_opened"]:
        raise RuntimeError("G-Q3 must be green and C/F pixels unopened")
    trials = pd.read_csv(trials_path)
    d = trials[(trials.config_id == 50) & (trials.feasible == 1)]
    # Each selected source cover is a cluster; channel success is averaged over
    # the frozen 12 messages/attempts assigned to that cover in D-b.
    per_cover = d.groupby("selected_cover")[["success_jpeg", "success_noise"]].mean()
    sd = per_cover.std(ddof=1)
    n_by_channel = {k: max(200, math.ceil((1.96 * float(v) / 0.03) ** 2)) for k, v in sd.items()}
    n_c = max(n_by_channel.values())
    if n_c > 7125:
        raise RuntimeError(f"Computed C sample size {n_c} exceeds the frozen C pool")

    # The previous protocol did not define Δ. This amendment operationalizes
    # it as the per-cover channel success rate, choosing the larger channel SD.
    # Selection uses only the existing D-b outcome table and frozen C metadata.
    partitions = pd.read_csv(PARTITIONS, keep_default_na=False)
    c = partitions.loc[partitions.split.eq("C")].copy()
    c["_rank"] = c.apply(lambda r: hashlib.sha256(
        ("FHAM-1quater-C-final-20261121|" + str(r.source_id) + "|" + str(r.sha256)).encode()
    ).hexdigest(), axis=1)
    c = c.sort_values(["_rank", "source_id"]).head(n_c)
    c["absolute_path"] = c.relative_path.map(lambda x: str(Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover") / x))
    c[["source_id", "relative_path", "absolute_path", "sha256", "split", "selection_rank_1ter", "_rank"]].rename(
        columns={"_rank": "selection_sha256"}).to_csv(OUT / "C_final_manifest_hash_only.csv", index=False)

    f = pd.read_csv(F_MANIFEST, keep_default_na=False)
    f = f.loc[f.split.eq("F")].copy()
    f["absolute_path"] = f.source_id.map(lambda x: str(Path(r"C:\Users\User\Downloads\Compressed\cpu_stego_experiments\datasets\BOSSbase") / x))
    if len(f) != 200:
        raise RuntimeError(f"Frozen F hash-only manifest should contain 200 rows; got {len(f)}")
    f[["source_id", "absolute_path", "sha256", "phash", "split", "partition_seed"]].to_csv(
        OUT / "F_final_manifest_hash_only.csv", index=False)

    summary = {
        "protocol": "FHAM-1quater-v1 + pre-open clarification dated 2026-11-21",
        "GQ2_lock_sha256": sha(lock_path), "E_gate_sha256": sha(gate_path),
        "D_b_trials_sha256": sha(trials_path), "C_source_partition_sha256": sha(PARTITIONS),
        "F_hash_only_manifest_sha256": sha(F_MANIFEST),
        "delta_operational_definition": "Per-source-cover success rate for each frozen channel, averaged over the 12 frozen 100-byte messages and the available D-b gallery attempts; sample SD across source-cover clusters; take the larger channel SD.",
        "channel_sd_D_b": {k: float(v) for k, v in sd.items()},
        "N_C_by_channel": n_by_channel, "N_C_frozen": n_c,
        "N_F_frozen": len(f),
        "C_selection": "Deterministic SHA-256 ranking of the frozen C partition rows using seed FHAM-1quater-C-final-20261121; first N_C rows.",
        "F_selection": "The 200-item hash-only F split reserved in 1ter; no reselection.",
        "pixel_state_at_freeze": {"C": False, "F": False},
        "C_manifest_sha256": sha(OUT / "C_final_manifest_hash_only.csv"),
        "F_manifest_sha256": sha(OUT / "F_final_manifest_hash_only.csv"),
        "GQ2_configuration": lock["selected_configuration"],
    }
    path = OUT / "preopen_sizing_and_manifest_lock.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lock_sha = sha(path)
    (OUT / "preopen_sizing_and_manifest_lock.sha256").write_text(
        f"{lock_sha}  {path.name}\n", encoding="ascii")
    summary["selection_lock_sha256"] = lock_sha
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
