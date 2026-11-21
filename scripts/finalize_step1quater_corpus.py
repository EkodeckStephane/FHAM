#!/usr/bin/env python3
"""Record provenance for a completed single-pass C/F artifact set."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/stability_step1/step1quater/run"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(corpus: str):
    out = RUN / f"{corpus}_final"
    manifest = RUN / "final_freeze" / f"{corpus}_final_manifest_hash_only.csv"
    gate = out / f"{corpus}_provisional_gate.json"
    trials = out / f"{corpus}_validation_trials.csv.gz"
    outcomes = out / f"{corpus}_cover_message_outcomes.csv.gz"
    robust = out / f"{corpus}_robustness_summary.csv"
    if not all(p.is_file() for p in (manifest, gate, trials, outcomes, robust)):
        raise RuntimeError(f"Incomplete {corpus} result set")
    if (out / f"{corpus}_validation_provenance.json").exists():
        raise RuntimeError("Provenance already exists")
    n = len(pd.read_csv(manifest))
    frame = pd.read_csv(trials)
    provenance = {
        "protocol": "FHAM-1quater-v1 + pre-open clarification 2026-11-21",
        "corpus": corpus, "N": n,
        "manifest_sha256": sha(manifest),
        "preopen_lock_sha256": sha(RUN / "final_freeze/preopen_sizing_and_manifest_lock.json"),
        "GQ2_lock_sha256": sha(RUN / "GQ2_configuration_freeze.json"),
        "E_gate_sha256": sha(RUN / "E_validation/GQ3_gate.json"),
        "config": {"config_id": 50, "p": 10, "q": 5, "m": 2, "B": 4},
        "images": n, "messages": int(frame.message_id.nunique()), "attempts": len(frame),
        "pixels_opened": {"C": corpus == "C", "F": corpus == "F"},
        "result_sha256": {p.name: sha(p) for p in (gate, trials, outcomes, robust)},
        "state": "single-pass outcomes complete; cluster bootstrap pending",
    }
    (out / f"{corpus}_validation_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("corpus", choices=("C", "F"))
    main(p.parse_args().corpus)
