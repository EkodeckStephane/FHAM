#!/usr/bin/env python3
"""Add final bootstrap/gate hashes to C/F provenance after their single pass."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/stability_step1/step1quater/run"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


for corpus in ("C", "F"):
    out = RUN / f"{corpus}_final"
    path = out / f"{corpus}_validation_provenance.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    gate = out / f"{corpus}_provisional_gate.json"
    files = [gate, out / f"{corpus}_validation_trials.csv.gz",
             out / f"{corpus}_cover_message_outcomes.csv.gz",
             out / f"{corpus}_robustness_summary.csv",
             out / f"{corpus}_cluster_bootstrap_10000.csv.gz",
             out / f"{corpus}_cluster_bootstrap_summary.csv"]
    data["state"] = "single-pass outcomes and 10,000-replicate cover-cluster bootstrap complete"
    data["result_sha256"] = {p.name: sha(p) for p in files}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(corpus, sha(path))
