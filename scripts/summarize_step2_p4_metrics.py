#!/usr/bin/env python3
"""Expand Step-2 P4 outputs into message-, segment-, and symbol-level metrics."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/step2/geometry"
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")
CHAINS = ("P1", "P2", "P3", "P4")
TRANSFORMS = ("rotation", "crop_restore", "resize_restore")


def _summarize(dataset: str):
    segment_path = OUT / f"p4_{dataset}_segment_trials.csv.gz"
    message_path = OUT / f"p4_{dataset}_message_trials.csv"
    summary_path = OUT / f"p4_{dataset}_summary.csv"
    segments = pd.read_csv(segment_path, compression="gzip")
    messages = pd.read_csv(message_path)
    if messages.groupby("family").attempt.nunique().to_dict() != {f: 100 for f in FAMILIES}:
        raise RuntimeError(f"{dataset}: expected exactly 100 trials per family")
    key = ["family", "message_id", "attempt", "transform", "chain"]
    if messages.duplicated(key).any():
        raise RuntimeError(f"{dataset}: duplicate message result rows")
    if len(messages) != 4 * 100 * len(TRANSFORMS) * len(CHAINS):
        raise RuntimeError(f"{dataset}: incomplete message result matrix: {len(messages)}")

    metric_rows = []
    specs = {
        "P1": ("P1_exact_segment", "P1_erasures", "P1_symbol_errors"),
        "P2": ("P2_exact_segment", "P2_erasures", "P2_symbol_errors"),
        "P3": ("P3_exact_segment", "P3_erasures", "P3_symbol_errors"),
        "P4": ("P4_exact_segment", "P4_erasures", "P4_symbol_errors"),
    }
    groups = [*((fam, tr, chain, group) for (fam, tr, chain), group
                in messages.groupby(["family", "transform", "chain"])),
              *(("ALL", tr, chain, group) for (tr, chain), group
                in messages.groupby(["transform", "chain"]))]
    for family, transform, chain, msg_group in groups:
        seg_group = segments[(segments["transform"] == transform) & (segments["family"] == family)] if family != "ALL" else segments[segments["transform"] == transform]
        exact_col, erase_col, error_col = specs[chain]
        total_slots = int(seg_group.symbols_total.sum())
        assigned = int(seg_group.symbols_assigned.sum())
        observed_errors = int(seg_group[error_col].sum())
        erasures = int(seg_group[erase_col].sum())
        n_messages = len(msg_group)
        metric_rows.append({
            "dataset": dataset, "family": family, "transform": transform, "chain": chain,
            "message_attempts": n_messages,
            "assignment_feasible_rate": float(msg_group.assignment_feasible.mean()),
            "exact_message_rate": float(msg_group.exact_message.mean()),
            "feasible_segment_count": int(len(seg_group)),
            "exact_segment_rate": float(seg_group[exact_col].mean()) if len(seg_group) else float("nan"),
            "registration_success_rate": float(seg_group.registration_success.mean()) if len(seg_group) else float("nan"),
            "codeword_slots": total_slots,
            "assigned_symbols": assigned,
            "erasures": erasures,
            "erasure_rate_per_codeword_slot": erasures / total_slots if total_slots else float("nan"),
            "observed_symbol_errors": observed_errors,
            "assigned_symbol_accuracy_before_RS": 1.0 - observed_errors / assigned if assigned else float("nan"),
            "symbol_metric_scope": "assigned symbols before Reed-Solomon; P4 uses its winning candidate on exact recovery, otherwise its last candidate before the CPU budget ended",
            "p4_candidates_per_message": float(msg_group.p4_candidates_total.mean()) if chain == "P4" else 0.0,
            "p4_cpu_seconds_per_message": float(msg_group.p4_cpu_seconds.mean()) if chain == "P4" else 0.0,
            "p4_wall_seconds_per_message": float(msg_group.p4_wall_seconds.mean()) if chain == "P4" else 0.0,
        })
    metrics = pd.DataFrame(metric_rows)
    message_summary = pd.read_csv(summary_path)
    metrics = metrics.merge(message_summary[["family", "transform", "chain",
                                             "cluster_bootstrap_low", "cluster_bootstrap_high"]],
                            on=["family", "transform", "chain"], how="left", validate="one_to_one")
    metrics.to_csv(OUT / f"p4_{dataset}_complete_metrics.csv", index=False)
    print(metrics[metrics.family == "ALL"].to_string(index=False))
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=("D_b_posthoc", "E_geo", "C_geo", "F_geo"), required=True)
    args = parser.parse_args()
    _summarize(args.dataset)


if __name__ == "__main__":
    main()
