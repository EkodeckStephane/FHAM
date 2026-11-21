#!/usr/bin/env python3
"""Cover-pool bootstrap for the single-pass frozen E validation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_step1quater as q4

OUT = q4.OUT / "E_validation"
N_BOOT = 10_000


def main():
    lock = json.loads((q4.OUT / "GQ2_configuration_freeze.json").read_text(encoding="utf-8"))
    if lock["selected_configuration"]["config_id"] != 50:
        raise RuntimeError("E bootstrap requires the already frozen config_id=50")
    if not (OUT / "E_validation_provenance.json").is_file():
        raise RuntimeError("E validation has not completed")
    data = pd.read_csv(OUT / "E_cover_message_outcomes.csv.gz", low_memory=False)
    messages = list(data.message_id.drop_duplicates())
    covers = list(data.cover_id.drop_duplicates())
    if len(messages) != 12 or len(covers) != 200 or len(data) != 2400:
        raise RuntimeError("E cover-message table must contain 200 × 12 outcomes")
    index = {cid: i for i, cid in enumerate(covers)}
    metrics = {mid: {} for mid in messages}
    for mid in messages:
        d = data[data.message_id.eq(mid)].set_index("cover_id").loc[covers]
        metrics[mid] = {key: d[key].to_numpy(dtype=np.int8)
                        for key in ("feasible", "success_jpeg", "success_noise")}
    seed = q4.seed_for("bootstrap/cluster", "E", "config_50", str(N_BOOT))
    rng = np.random.Generator(np.random.PCG64(seed))
    n = len(covers); m = 2; reps = []
    for rep in range(N_BOOT):
        pool = rng.integers(0, n, size=n)
        per_message = []
        for mid in messages:
            slots = np.empty((n, m), dtype=np.int16)
            for k in range(m):
                ranks = rng.integers(0, n-k, size=n)
                if k:
                    previous = np.sort(slots[:, :k], axis=1)
                    for j in range(k):
                        ranks += ranks >= previous[:, j]
                slots[:, k] = ranks
            candidate = pool[slots]
            feasible = metrics[mid]["feasible"][candidate]
            any_feasible = feasible.any(axis=1)
            first = feasible.argmax(axis=1)
            chosen = candidate[np.arange(n), first]
            per_message.append({
                "feasibility": float(any_feasible.mean()),
                "jpeg": float((any_feasible * metrics[mid]["success_jpeg"][chosen]).mean()),
                "noise": float((any_feasible * metrics[mid]["success_noise"][chosen]).mean()),
            })
        reps.append({"replicate": rep, **{
            k: float(np.mean([x[k] for x in per_message]))
            for k in ("feasibility", "jpeg", "noise")}})
        if (rep + 1) % 2000 == 0:
            print(f"E cluster bootstrap {rep+1}/{N_BOOT}", flush=True)
    frame = pd.DataFrame(reps)
    frame.to_csv(OUT / "E_cluster_bootstrap_10000.csv.gz", index=False, compression="gzip")
    summary = []
    for name in ("feasibility", "jpeg", "noise"):
        summary.append({"metric": name, "mean": float(frame[name].mean()),
                        "ci95_low": float(frame[name].quantile(.025)),
                        "ci95_high": float(frame[name].quantile(.975)),
                        "bootstrap_replicates": N_BOOT,
                        "cluster_unit": "E cover pool; two gallery candidates redrawn without replacement per attempt"})
    pd.DataFrame(summary).to_csv(OUT / "E_cluster_bootstrap_summary.csv", index=False)
    gate_path = OUT / "GQ3_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["cluster_bootstrap_10000"] = {
        name: {"ci95_low": float(frame[name].quantile(.025)),
               "ci95_high": float(frame[name].quantile(.975))}
        for name in ("feasibility", "jpeg", "noise")}
    gate["cluster_bootstrap_success_lower_ge_0_92"] = bool(
        frame.jpeg.quantile(.025) >= .92 and frame.noise.quantile(.025) >= .92)
    gate["G_Q3_all_frozen_checks_pass"] = bool(
        gate["G_Q3_point_estimate_pass"] and gate["G_Q3_N200_macro_wilson_pass"] and
        gate["cluster_bootstrap_success_lower_ge_0_92"])
    gate_path.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate["cluster_bootstrap_10000"], indent=2), flush=True)
    print("G_Q3_all_frozen_checks_pass=" + str(gate["G_Q3_all_frozen_checks_pass"]), flush=True)


if __name__ == "__main__":
    main()
