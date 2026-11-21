#!/usr/bin/env python3
"""Preregistered D-b cluster bootstrap and paired tests for FHAM 1quater."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

import run_step1quater as q4

OUT = q4.OUT
N_BOOT = 10_000
N_PERM = 100_000


def candidate_first_cover(message_id: str, attempt: int, cover_ids: list[str]) -> str:
    rng = np.random.Generator(np.random.PCG64(
        q4.seed_for("A4/candidate_draws", message_id, str(attempt))))
    return str(rng.permutation(cover_ids)[0])


def add_first_candidate(df: pd.DataFrame, cover_ids: list[str]):
    return df.assign(first_candidate=[candidate_first_cover(mid, int(a), cover_ids)
                                      for mid, a in zip(df.message_id, df.attempt)])


def paired_cover_signflip(base: pd.DataFrame, alt: pd.DataFrame, outcome: str,
                          cover_ids: list[str], test_name: str, seed: int):
    cols = ["message_id", "attempt", outcome]
    left = add_first_candidate(base[cols].copy(), cover_ids)
    right = alt[cols].copy()
    paired = left.merge(right, on=["message_id", "attempt"], suffixes=("_base", "_alt"), validate="one_to_one")
    paired["delta"] = paired[f"{outcome}_alt"] - paired[f"{outcome}_base"]
    cluster = paired.groupby("first_candidate").delta.mean().reindex(cover_ids)
    values = cluster.to_numpy(dtype=np.float64)
    if not np.isfinite(values).all() or len(values) != 100:
        raise RuntimeError(f"Invalid paired cover-cluster data for {test_name}")
    observed = float(values.mean())
    rng = np.random.Generator(np.random.PCG64(seed))
    exceed = 0
    batch = 1000
    for start in range(0, N_PERM, batch):
        n = min(batch, N_PERM - start)
        signs = rng.integers(0, 2, size=(n, len(values)), dtype=np.int8) * 2 - 1
        stats = (signs * values[None, :]).mean(axis=1)
        exceed += int(np.count_nonzero(np.abs(stats) >= abs(observed) - 1e-15))
    pvalue = (1 + exceed) / (N_PERM + 1)
    return {"hypothesis": test_name, "paired_outcome": outcome,
            "mean_cluster_difference": observed, "clusters": len(values),
            "permutations": N_PERM, "p_raw_two_sided": pvalue}


def bootstrap_selected():
    selected = json.loads((OUT / "selected_configuration.json").read_text(encoding="utf-8"))["selected"]
    p, q, m, bound = (int(selected[k]) for k in ("p", "q", "m", "B"))
    covers = pd.read_csv(q4.INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    cover_ids = [str(r.source_id) for r in covers.itertuples(index=False)]
    cover_rows = {str(r.source_id): r for r in covers.itertuples(index=False)}
    messages = {k: v for k, v in q4.compressed_messages().items() if len(v[2]) == 100}
    mids = list(messages)
    outcomes = {mid: {"feasible": np.zeros(100, dtype=np.int8),
                      "jpeg": np.zeros(100, dtype=np.int8), "noise": np.zeros(100, dtype=np.int8),
                      "b_assign": np.full(100, np.nan),
                      "b_total_by_gallery_index": np.full((100, m), np.nan)} for mid in mids}
    t0 = time.perf_counter()
    for mi, mid in enumerate(mids):
        _family, _index, source, compressed = messages[mid]
        for ci, cid in enumerate(cover_ids):
            locs, hashes, cw, blocks, assn, attacks = q4.solve_cell_assignment(
                cid, mid, source, compressed, p, q, bound, cover_rows[cid])
            if not assn["parity_ok"]:
                continue
            outcomes[mid]["feasible"][ci] = 1
            outcomes[mid]["jpeg"][ci] = int(q4.recover_message(
                source, compressed, cw, blocks, assn, hashes, attacks["jpeg"], locs, p)[0])
            outcomes[mid]["noise"][ci] = int(q4.recover_message(
                source, compressed, cw, blocks, assn, hashes, attacks["noise"], locs, p)[0])
            fixed = math.ceil(math.log2(1764)) + math.ceil(math.log2(2 * bound + 1))
            outcomes[mid]["b_assign"][ci] = (assn["n_placed"] * fixed + len(cw)) / len(source)
            # Reconstruct selected config id from its frozen lexicographic order.
            config_id = selected["config_id"]
            for gallery_id in range(m):
                body = q4.serialize_1quater_body(source, cw, assn, locs, config_id, m, gallery_id, p)
                outcomes[mid]["b_total_by_gallery_index"][ci, gallery_id] = (
                    8 * (41 + len(__import__("zlib").compress(body, 9))) / len(source))
        print(f"BOOTSTRAP INPUT {mi+1}/12 {mid}: feasible={outcomes[mid]['feasible'].mean():.3f}", flush=True)

    rng = np.random.Generator(np.random.PCG64(
        q4.seed_for("bootstrap/cluster", "selected_config", str(selected["config_id"]), str(N_BOOT))))
    reps = []
    ncover = len(cover_ids)
    for rep in range(N_BOOT):
        pool = rng.integers(0, ncover, size=ncover)
        msg_stats = []
        for mid in mids:
            # Draw m distinct gallery entries from each bootstrap pool for every
            # attempt; source covers can repeat in the bootstrapped pool.
            slots = np.empty((100, m), dtype=np.int16)
            for k in range(m):
                ranks = rng.integers(0, ncover - k, size=100)
                if k:
                    previous = np.sort(slots[:, :k], axis=1)
                    for j in range(k):
                        ranks += ranks >= previous[:, j]
                slots[:, k] = ranks
            candidate_indices = pool[slots]
            feas = outcomes[mid]["feasible"][candidate_indices]
            any_feas = feas.any(axis=1)
            first = feas.argmax(axis=1)
            chosen = candidate_indices[np.arange(100), first]
            values = {name: arr[chosen] for name, arr in outcomes[mid].items()
                      if name != "b_total_by_gallery_index"}
            chosen_btotal = outcomes[mid]["b_total_by_gallery_index"][chosen, first]
            msg_stats.append({
                "feasibility": float(any_feas.mean()),
                "jpeg": float((any_feas * values["jpeg"]).mean()),
                "noise": float((any_feas * values["noise"]).mean()),
                "b_assign": float(np.nanmean(np.where(any_feas, values["b_assign"], np.nan))),
                "b_total": float(np.nanmean(np.where(any_feas, chosen_btotal, np.nan))),
            })
        reps.append({"replicate": rep,
                     **{k: float(np.mean([x[k] for x in msg_stats]))
                        for k in ("feasibility", "jpeg", "noise", "b_assign", "b_total")}})
        if (rep + 1) % 2000 == 0:
            print(f"BOOTSTRAP {rep+1}/{N_BOOT} elapsed {time.perf_counter()-t0:.1f}s", flush=True)
    frame = pd.DataFrame(reps)
    frame.to_csv(OUT / "selected_config_cluster_bootstrap_10000.csv.gz", index=False, compression="gzip")
    summary = []
    for key in ("feasibility", "jpeg", "noise", "b_assign", "b_total"):
        summary.append({"metric": key, "mean": float(frame[key].mean()),
                        "ci95_low": float(frame[key].quantile(.025)),
                        "ci95_high": float(frame[key].quantile(.975)), "bootstrap_replicates": N_BOOT,
                        "cluster_unit": "D-b cover pool; m candidates redrawn without replacement per attempt"})
    pd.DataFrame(summary).to_csv(OUT / "selected_config_cluster_bootstrap_summary.csv", index=False)


def hypothesis_tests():
    d = pd.read_csv(OUT / "grid_trials_12x100.csv.gz", low_memory=False)
    covers = pd.read_csv(q4.INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    cover_ids = [str(r.source_id) for r in covers.itertuples(index=False)]
    configs = {(int(r.p), int(r.q), int(r.m), int(r.B)): int(r.config_id)
               for r in d[["p", "q", "m", "B", "config_id"]].drop_duplicates().itertuples(index=False)}

    def cell(p, q, m, b):
        return d[d.config_id.eq(configs[(p, q, m, b)])].copy()

    # H12: RS at 40% versus no parity, q=0,m=1,B=8; exact recovery on both
    # preregistered channels is the binary paired outcome.
    h12_base, h12_alt = cell(0, 0, 1, 8), cell(40, 0, 1, 8)
    h12_base["both"] = h12_base.success_jpeg * h12_base.success_noise
    h12_alt["both"] = h12_alt.success_jpeg * h12_alt.success_noise
    tests = [paired_cover_signflip(h12_base, h12_alt, "both", cover_ids, "H12_RS40_vs_noRS", q4.seed_for("permutation/sign_flip", "H12"))]
    # H13: q=5% versus robust-only q=0, no parity and one cover, B=8.
    tests.append(paired_cover_signflip(cell(0, 0, 1, 8), cell(0, 5, 1, 8), "feasible", cover_ids,
                                       "H13_q5_vs_q0_feasibility", q4.seed_for("permutation/sign_flip", "H13")))
    # H14: m=3 versus m=1, isolated A4 branch, B=8.
    tests.append(paired_cover_signflip(cell(0, 0, 1, 8), cell(0, 0, 3, 8), "feasible", cover_ids,
                                       "H14_m3_vs_m1_feasibility", q4.seed_for("permutation/sign_flip", "H14")))
    ordered = sorted(tests, key=lambda x: x["p_raw_two_sided"])
    running = 0.0
    for rank, item in enumerate(ordered):
        adj = min(1.0, (len(ordered) - rank) * item["p_raw_two_sided"])
        running = max(running, adj)
        item["p_holm"] = running
    pd.DataFrame(tests).to_csv(OUT / "H12_H14_paired_permutation.csv", index=False)

    # Report the prespecified H12/H13 branches and H14 independence diagnostic.
    rows = []
    for name, p, q, m, b in (("H12_A2_only",40,0,1,8), ("H13_A3_q5",0,5,1,8),
                             ("H14_A4_m3",0,0,3,8), ("H14_A4_m1",0,0,1,8)):
        x = cell(p,q,m,b)
        good = x.feasible.eq(1)
        placed = x.loc[good,"N_placed"].sum()
        rows.append({"branch":name,"p":p,"q":q,"m":m,"B":b,
                     "feasibility":x.feasible.mean(),"success_jpeg":x.success_jpeg.mean(),
                     "success_noise":x.success_noise.mean(),
                     "conditional_accuracy_jpeg":1-x.loc[good,"errors_jpeg"].sum()/placed if placed else np.nan,
                     "conditional_accuracy_noise":1-x.loc[good,"errors_noise"].sum()/placed if placed else np.nan,
                     "b_assign_conditional":x.b_assign.mean(),"b_total_conditional":x.b_total.mean()})
    descriptive = pd.DataFrame(rows)
    descriptive.to_csv(OUT / "H12_H14_descriptive.csv", index=False)
    h14_m1 = cell(0,0,1,8).groupby("message_id").feasible.mean()
    h14_m3 = cell(0,0,3,8).groupby("message_id").feasible.mean()
    expected = float((1 - (1 - h14_m1) ** 3).mean())
    observed = float(h14_m3.mean())
    (OUT / "H14_independence_diagnostic.json").write_text(json.dumps({
        "branch": "p=0,q=0,B=8", "single_cover_feasibility_macro12": float(h14_m1.mean()),
        "expected_if_independent_m3_macro12": expected, "observed_m3_feasibility_macro12": observed,
        "ratio_observed_to_independence_expectation": observed / expected if expected else None,
        "interpretation": "diagnostic comparison; independence is not assumed as a guarantee"
    }, indent=2) + "\n", encoding="utf-8")


def main():
    bootstrap_csv = OUT / "selected_config_cluster_bootstrap_10000.csv.gz"
    bootstrap_summary = OUT / "selected_config_cluster_bootstrap_summary.csv"
    if not (bootstrap_csv.exists() and bootstrap_summary.exists()):
        bootstrap_selected()
    else:
        print("Reusing completed 10,000-replicate bootstrap outputs", flush=True)
    hypothesis_tests()
    print("BOOTSTRAP and H12-H14 analyses complete", flush=True)


if __name__ == "__main__":
    main()
