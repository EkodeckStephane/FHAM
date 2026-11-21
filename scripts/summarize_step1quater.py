#!/usr/bin/env python3
"""Validate and summarize frozen D-b 1quater outputs, then freeze G-Q2 choice."""
from __future__ import annotations

import hashlib
import json
import math
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_step1quater as q4

OUT = q4.OUT


def sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    a1 = pd.read_csv(OUT / "A1_by_cover_message.csv")
    if len(a1) != 100 * 48 * 2 or a1.cover_id.nunique() != 100:
        raise RuntimeError("A1 row/cover count mismatch")
    cap = a1.groupby(["L_src", "B", "cover_id"], as_index=False).agg(
        max_symbol_capacity=("max_matching", "max"),
        mean_symbol_capacity=("max_matching", "mean"),
        messages_feasible=("feasible", "sum"),
    )
    cap.to_csv(OUT / "A1_capacity_by_cover.csv", index=False)
    cap_summary = cap.groupby(["L_src", "B"], as_index=False).agg(
        mean_max_capacity=("max_symbol_capacity", "mean"),
        median_max_capacity=("max_symbol_capacity", "median"),
        q10_max_capacity=("max_symbol_capacity", lambda x: x.quantile(.10)),
        q90_max_capacity=("max_symbol_capacity", lambda x: x.quantile(.90)),
        mean_messages_feasible=("messages_feasible", "mean"),
    )
    cap_summary.to_csv(OUT / "A1_capacity_summary.csv", index=False)
    permsg = pd.read_csv(OUT / "A1_by_message_summary.csv")
    nstar = []
    for (bound, message_id), rows in permsg.groupby(["B", "message_id"]):
        rows = rows.sort_values("L_src")
        passing = rows.loc[rows.wilson_low >= .90, "L_src"].tolist()
        nstar.append({"B": int(bound), "message_id": message_id,
                      "L_src_star": max(passing) if passing else "non atteint"})
    joint = pd.read_csv(OUT / "A1_joint_summary.csv")
    for bound, rows in joint.groupby("B"):
        passing = rows.loc[rows.wilson_low >= .90, "L_src"].tolist()
        nstar.append({"B": int(bound), "message_id": "joint_all_12",
                      "L_src_star": max(passing) if passing else "non atteint"})
    pd.DataFrame(nstar).to_csv(OUT / "A1_Lsrc_star.csv", index=False)

    trials_path = OUT / "grid_trials_12x100.csv.gz"
    data = pd.read_csv(trials_path, low_memory=False)
    expected_configs = [(p, q, m, b) for p in (0, 10, 20, 30, 40)
                        for q in (0, 2, 5, 10) for m in (1, 2, 3, 5) for b in (4, 8)]
    expected_ids = {cfg: i for i, cfg in enumerate(expected_configs)}
    if (len(data) != 160 * 12 * 100 or data.config_id.nunique() != 160 or
            data.message_id.nunique() != 12 or not data.groupby(["config_id", "message_id"]).size().eq(100).all()):
        raise RuntimeError("Primary grid is incomplete: expected 192000 rows, 160 cells, 12 messages × 100 trials")
    if set(data.L_src.astype(int)) != {100}:
        raise RuntimeError("Primary grid contains a source length other than 100 bytes")
    if ((data.success_jpeg > data.feasible) | (data.success_noise > data.feasible)).any():
        raise RuntimeError("An infeasible trial was counted as a successful communication")
    placed = data.feasible.eq(1)
    if not data.loc[placed, "N_placed"].add(data.loc[placed, "erasures"]).eq(data.loc[placed, "L_cw"]).all():
        raise RuntimeError("N_placed + erasures != L_cw on feasible trials")
    expected_b = (data.loc[placed, "N_placed"] *
                  (math.ceil(math.log2(1764)) + data.loc[placed, "B"].map(
                      lambda b: math.ceil(math.log2(2 * int(b) + 1)))) +
                  data.loc[placed, "L_cw"]) / data.loc[placed, "L_src"]
    if not np.allclose(data.loc[placed, "b_assign"], expected_b, atol=1e-10):
        raise RuntimeError("b_assign formula mismatch")
    for cfg, cid in expected_ids.items():
        rows = data[data.config_id.eq(cid)]
        if len(rows) != 1200 or tuple(int(rows[c].iloc[0]) for c in ("p", "q", "m", "B")) != cfg:
            raise RuntimeError(f"Grid cell mapping/count mismatch: {cfg}, id={cid}")
        for raw in rows.loc[placed.loc[rows.index], "block_erasures"]:
            if not isinstance(raw, str) or not raw.startswith("["):
                raise RuntimeError(f"Malformed block erasure list in config {cid}")

    # Metrics are first averaged within each frozen message, then equally over
    # the 12 messages; cost is conditional on a record actually being sent.
    by_msg = data.groupby(["config_id", "p", "q", "m", "B", "message_id", "family"], as_index=False).agg(
        success_jpeg=("success_jpeg", "mean"), success_noise=("success_noise", "mean"),
        feasibility=("feasible", "mean"), b_assign_conditional=("b_assign", "mean"),
        b_total_conditional=("b_total", "mean"), mean_erasures=("erasures", "mean"),
    )
    by_msg.to_csv(OUT / "grid_summary_by_message.csv", index=False)
    cells = by_msg.groupby(["config_id", "p", "q", "m", "B"], as_index=False).agg(
        success_jpeg=("success_jpeg", "mean"), success_noise=("success_noise", "mean"),
        feasibility=("feasibility", "mean"), b_assign=("b_assign_conditional", "mean"),
        b_total=("b_total_conditional", "mean"),
        messages_with_cost=("b_assign_conditional", "count"),
        mean_erasures=("mean_erasures", "mean"),
    )
    cells["success_combined"] = cells[["success_jpeg", "success_noise"]].min(axis=1)
    cells.to_csv(OUT / "grid_summary.csv", index=False)
    fam = by_msg.groupby(["config_id", "p", "q", "m", "B", "family"], as_index=False).agg(
        success_jpeg=("success_jpeg", "mean"), success_noise=("success_noise", "mean"),
        feasibility=("feasibility", "mean"), b_assign=("b_assign_conditional", "mean"),
        b_total=("b_total_conditional", "mean"), mean_erasures=("mean_erasures", "mean"),
    )
    fam.to_csv(OUT / "grid_summary_by_family.csv", index=False)

    eligible = cells[(cells.success_jpeg >= .95) & (cells.success_noise >= .95) &
                     (cells.b_assign <= 24) & (cells.messages_with_cost == 12)].copy()
    if eligible.empty:
        decision = {"G_Q2": "red_or_orange", "selected": None}
    else:
        eligible = eligible.sort_values(["b_assign", "p", "q", "m", "B"], kind="mergesort")
        winner = eligible.iloc[0]
        decision = {
            "G_Q2": "green",
            "selection_rule": "both channel estimates >=0.95; equal-message mean b_assign <=24; choose lowest b_assign then p,q,m,B ascending",
            "selected": {k: (int(winner[k]) if k in ("config_id", "p", "q", "m", "B") else float(winner[k]))
                         for k in ("config_id", "p", "q", "m", "B", "success_jpeg", "success_noise",
                                   "success_combined", "feasibility", "b_assign", "b_total")},
            "eligible_cells": int(len(eligible)),
            "b_assign_interpretation": "equal-weight mean of the 12 within-message means, conditional on a feasible transmitted record",
            "b_total_interpretation": "same aggregation; complete 1quater body zlib-9 plus measured F=41-byte envelope overhead",
            "E_authorized_by_frozen_protocol": True,
        }
        (OUT / "selected_configuration.json").write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    checks = {
        "protocol_sha256": sha(q4.PROTOCOL), "D_b_manifest_sha256": sha(q4.INPUT / "D_b_images_sha256.csv"),
        "message_manifest_sha256": sha(q4.INPUT / "messages_sha256.csv"),
        "robustness_positions_sha256": sha(OUT / "robustness_summary.csv"),
        "A1_rows": int(len(a1)), "grid_rows": int(len(data)), "grid_cells": int(data.config_id.nunique()),
        "grid_trials_per_cell_message": 100, "grid_message_count": int(data.message_id.nunique()),
        "failed_attempts": int((data.feasible == 0).sum()),
        "successful_exact_jpeg": int(data.success_jpeg.sum()), "successful_exact_noise": int(data.success_noise.sum()),
        "A4_grid_selection": decision,
        "aborted_scope_run": "grid_trials_ABORTED_incorrect_48_message_scope.csv.gz",
        "E_C_F_pixels_opened": False,
    }
    (OUT / "quality_checks_and_GQ2.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2))
    print(f"validated: A1={len(a1)} rows; primary grid={len(data)} rows; output={OUT}")


if __name__ == "__main__":
    main()
