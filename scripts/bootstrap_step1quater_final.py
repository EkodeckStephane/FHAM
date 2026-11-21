#!/usr/bin/env python3
"""Cluster bootstrap C/F and independent corpus contrast for G-Q4."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_step1quater as q4

RUN = q4.OUT
N_BOOT = 10_000


def bootstrap(corpus: str):
    out = RUN / f"{corpus}_final"
    data = pd.read_csv(out / f"{corpus}_cover_message_outcomes.csv.gz", low_memory=False)
    messages = list(data.message_id.drop_duplicates())
    covers = list(data.cover_id.drop_duplicates())
    if len(messages) != 12 or len(covers) != 200 or len(data) != 2400:
        raise RuntimeError(f"{corpus}: expected 200 covers × 12 messages")
    metrics = {}
    for mid in messages:
        d = data[data.message_id.eq(mid)].set_index("cover_id").loc[covers]
        metrics[mid] = {k: d[k].to_numpy(dtype=np.int8)
                        for k in ("feasible", "success_jpeg", "success_noise")}
    seed = q4.seed_for("bootstrap/cluster", corpus, "config_50", str(N_BOOT))
    rng = np.random.Generator(np.random.PCG64(seed))
    reps = np.empty((N_BOOT, 3), dtype=np.float64)
    n = len(covers)
    for rep in range(N_BOOT):
        pool = rng.integers(0, n, size=n)
        channel_metrics = {"feasibility": [], "jpeg": [], "noise": []}
        for mid in messages:
            slots = np.empty((n, 2), dtype=np.int16)
            slots[:, 0] = rng.integers(0, n, size=n)
            ranks = rng.integers(0, n - 1, size=n)
            slots[:, 1] = ranks + (ranks >= slots[:, 0])
            candidate = pool[slots]
            feasible = metrics[mid]["feasible"][candidate]
            any_feasible = feasible.any(axis=1)
            first = feasible.argmax(axis=1)
            chosen = candidate[np.arange(n), first]
            channel_metrics["feasibility"].append(float(any_feasible.mean()))
            channel_metrics["jpeg"].append(float((any_feasible * metrics[mid]["success_jpeg"][chosen]).mean()))
            channel_metrics["noise"].append(float((any_feasible * metrics[mid]["success_noise"][chosen]).mean()))
        reps[rep] = [np.mean(channel_metrics[k]) for k in ("feasibility", "jpeg", "noise")]
    frame = pd.DataFrame(reps, columns=("feasibility", "jpeg", "noise"))
    frame.to_csv(out / f"{corpus}_cluster_bootstrap_10000.csv.gz", index=False, compression="gzip")
    summaries = []
    for metric in frame.columns:
        summaries.append({"metric": metric, "mean": float(frame[metric].mean()),
                          "ci95_low": float(frame[metric].quantile(.025)),
                          "ci95_high": float(frame[metric].quantile(.975)),
                          "replicates": N_BOOT, "cluster_unit": "source cover; m=2 candidates redrawn"})
    pd.DataFrame(summaries).to_csv(out / f"{corpus}_cluster_bootstrap_summary.csv", index=False)
    return frame


def main():
    c = bootstrap("C")
    f = bootstrap("F")
    rng = np.random.Generator(np.random.PCG64(q4.seed_for("bootstrap/corpus_contrast", "C_F", str(N_BOOT))))
    diff_j = f.jpeg.to_numpy() - c.jpeg.to_numpy()
    diff_n = f.noise.to_numpy() - c.noise.to_numpy()
    contrast = {
        "F_minus_C_jpeg": {"mean": float(diff_j.mean()), "ci95": [float(np.quantile(diff_j, .025)), float(np.quantile(diff_j, .975))]},
        "F_minus_C_noise": {"mean": float(diff_n.mean()), "ci95": [float(np.quantile(diff_n, .025)), float(np.quantile(diff_n, .975))]},
        "point_gap_jpeg": float(json.loads((RUN / "F_final/F_provisional_gate.json").read_text())["macro_success_jpeg"] -
                                 json.loads((RUN / "C_final/C_provisional_gate.json").read_text())["macro_success_jpeg"]),
        "point_gap_noise": float(json.loads((RUN / "F_final/F_provisional_gate.json").read_text())["macro_success_noise"] -
                                  json.loads((RUN / "C_final/C_provisional_gate.json").read_text())["macro_success_noise"]),
        "interpretation": "Independent cluster bootstrap on each corpus; paired replicate indices are not observations paired across corpora.",
        "replicates": N_BOOT,
    }
    path = RUN / "GQ4_cluster_bootstrap_contrast.json"
    path.write_text(json.dumps(contrast, indent=2) + "\n", encoding="utf-8")
    for corpus in ("C", "F"):
        out = RUN / f"{corpus}_final"
        gate_path = out / f"{corpus}_provisional_gate.json"
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        summary = pd.read_csv(out / f"{corpus}_cluster_bootstrap_summary.csv")
        gate["cluster_bootstrap_10000"] = {
            r.metric: {"ci95_low": float(r.ci95_low), "ci95_high": float(r.ci95_high)}
            for r in summary.itertuples(index=False)}
        gate["GQ4_green_by_N200_macro_Wilson_diagnostic"] = bool(
            gate["N200_macro_wilson_jpeg"][0] >= .92 and gate["N200_macro_wilson_noise"][0] >= .92)
        gate["GQ4_green_by_preregistered_cover_cluster_bootstrap"] = bool(
            gate["cluster_bootstrap_10000"]["jpeg"]["ci95_low"] >= .92 and
            gate["cluster_bootstrap_10000"]["noise"]["ci95_low"] >= .92)
        gate_path.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    c_gate = json.loads((RUN / "C_final/C_provisional_gate.json").read_text())
    f_gate = json.loads((RUN / "F_final/F_provisional_gate.json").read_text())
    decision = {
        "protocol": "FHAM-1quater-v1 + pre-open clarification 2026-11-21",
        "primary_uncertainty_method": "10,000-replicate percentile bootstrap resampling source covers; section 7 specifies cover as the statistical unit.",
        "GQ4_C_green": c_gate["GQ4_green_by_preregistered_cover_cluster_bootstrap"],
        "GQ4_F_green": f_gate["GQ4_green_by_preregistered_cover_cluster_bootstrap"],
        "point_gap_C_F_jpeg": contrast["point_gap_jpeg"],
        "point_gap_C_F_noise": contrast["point_gap_noise"],
        "point_gap_threshold": 0.05,
        "both_corpora_lower_bound_ge_0_92": bool(
            c_gate["GQ4_green_by_preregistered_cover_cluster_bootstrap"] and
            f_gate["GQ4_green_by_preregistered_cover_cluster_bootstrap"]),
        "point_gaps_below_0_05": bool(contrast["point_gap_jpeg"] <= .05 and contrast["point_gap_noise"] <= .05),
        "GQ4_status": "green" if (c_gate["GQ4_green_by_preregistered_cover_cluster_bootstrap"] and
                                    f_gate["GQ4_green_by_preregistered_cover_cluster_bootstrap"] and
                                    contrast["point_gap_jpeg"] <= .05 and contrast["point_gap_noise"] <= .05)
                      else "orange",
        "N200_macro_Wilson_diagnostic": {
            "C_jpeg_lower": c_gate["N200_macro_wilson_jpeg"][0],
            "C_noise_lower": c_gate["N200_macro_wilson_noise"][0],
            "F_jpeg_lower": f_gate["N200_macro_wilson_jpeg"][0],
            "F_noise_lower": f_gate["N200_macro_wilson_noise"][0],
            "note": "This message-averaged Wilson diagnostic treats a rounded mean as a binomial count; it is not the cover-cluster interval used for the primary G-Q4 decision."
        },
        "contrast_uncertainty": contrast,
        "limitations": [
            "C clustered lower bounds pass narrowly; individual message success varies, with minima 0.855 (JPEG) and 0.820 (noise).",
            "Independent-corpus bootstrap intervals for F−C include differences above 0.05 even though point gaps are below 0.05.",
            "The result applies to the frozen BOWS2-C and BOSSBase-F samples and selected configuration; it does not establish transfer to other datasets or parameter settings."
        ]
    }
    (RUN / "GQ4_decision.json").write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(contrast, indent=2))
    print(pd.read_csv(RUN / "C_final/C_cluster_bootstrap_summary.csv").to_string(index=False))
    print(pd.read_csv(RUN / "F_final/F_cluster_bootstrap_summary.csv").to_string(index=False))


if __name__ == "__main__":
    main()
