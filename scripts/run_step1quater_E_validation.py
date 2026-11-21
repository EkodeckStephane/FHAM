#!/usr/bin/env python3
"""Single-pass E validation of the frozen G-Q2 configuration."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_step1quater as q4

OUT = q4.OUT / "E_validation"
SOURCE_MANIFEST = ROOT / "results/stability_step1/step1ter/manifest/bows2_D_E_C_manifest.csv"


def sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson(success: int, n: int, z: float = 1.959963984540054):
    p = success / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main():
    lock_path = q4.OUT / "GQ2_configuration_freeze.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock["G_Q2"] != "green" or lock["E_pixels_opened"]:
        raise RuntimeError("E run requires a frozen green G-Q2 configuration and unopened E pixels")
    frozen = lock["selected_configuration"]
    p, q, m, bound = (int(frozen[k]) for k in ("p", "q", "m", "B"))
    config_id = int(frozen["config_id"])
    if (p, q, m, bound, config_id) != (10, 5, 2, 4, 50):
        raise RuntimeError("Unexpected selected configuration; refusing an unregistered E evaluation")
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "E_validation_trials.csv.gz").exists():
        raise RuntimeError("E validation output already exists; refusing to repeat the single validation pass")
    all_rows = pd.read_csv(SOURCE_MANIFEST, keep_default_na=False)
    e_rows = all_rows.loc[all_rows.split.eq("E")].sort_values("selection_rank_1ter").copy()
    if len(e_rows) != 200:
        raise RuntimeError(f"Frozen E manifest should contain 200 rows; found {len(e_rows)}")
    d_b = pd.read_csv(q4.INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    if set(e_rows.source_id.astype(str)) & set(d_b.source_id.astype(str)):
        raise RuntimeError("E overlaps with D-b")
    e_manifest = OUT / "E_validation_manifest_sha256.csv"
    e_rows[["source_id", "relative_path", "sha256", "selection_rank_1ter"]].to_csv(e_manifest, index=False)
    image_root = q4.IMAGE_ROOT
    # Make the frozen E codebooks addressable through the shared 1quater solver.
    q4.OUT = OUT
    q4.CODEBOOK_CACHE.clear(); q4.IMAGE_CACHE.clear(); q4.ATTACK_CACHE.clear()
    robustness_root = OUT / "robustness_positions"
    robustness_root.mkdir(parents=True, exist_ok=True)
    summary = []
    begin = time.perf_counter()
    for ix, row in enumerate(e_rows.itertuples(index=False), 1):
        image_path = image_root / str(row.relative_path)
        if sha(image_path) != str(row.sha256):
            raise RuntimeError(f"E source SHA-256 mismatch: {row.source_id}")
        image = np.asarray(Image.open(image_path).convert("L"), dtype=np.uint8)
        if image.shape != (256, 256):
            raise RuntimeError(f"E expected native 256x256 image: {row.source_id}, got {image.shape}")
        profile, locations, _lookup, base = q4.locations_and_hashes(image, "mean_ordinal")
        if profile != 12 or len(locations) != 1764:
            raise RuntimeError(f"Unexpected E codebook: {row.source_id}, M={len(locations)}")
        flips = {name: np.zeros(len(locations), dtype=np.uint16) for name in ("jpeg", "noise")}
        attacks = q4.draw_development_attacks(image, str(row.sha256))
        t0 = time.perf_counter()
        for family, variants in attacks.items():
            for attacked, _q, _sigma in variants:
                current = q4.batch_hash_map(attacked, "mean_ordinal", 12, locations)
                flips[family] += np.fromiter((current[loc] != base[loc] for loc in locations),
                                             dtype=np.uint16, count=len(locations))
        robust = (flips["jpeg"] == 0) & (flips["noise"] == 0)
        total_flips = flips["jpeg"] + flips["noise"]
        stability = np.where(robust, 1.0, (101.0 - total_flips) / 102.0)
        pd.DataFrame({
            "position_index": np.arange(len(locations)), "x": [l.x for l in locations],
            "y": [l.y for l in locations], "arrangement": [l.arrangement for l in locations],
            "hash_value": [base[l] for l in locations], "jpeg_flips": flips["jpeg"],
            "noise_flips": flips["noise"], "robust": robust.astype(np.uint8), "s_hat": stability,
        }).to_csv(robustness_root / f"{Path(str(row.source_id)).stem}.csv.gz", index=False, compression="gzip")
        summary.append({"cover_id": row.source_id, "sha256": row.sha256,
                        "robust_positions": int(robust.sum()), "robust_fraction": float(robust.mean()),
                        "elapsed_seconds": time.perf_counter() - t0})
        pd.DataFrame(summary).to_csv(OUT / "E_robustness_summary.csv", index=False)
        if ix % 10 == 0:
            print(f"E ROBUST {ix}/200 elapsed={time.perf_counter()-begin:.1f}s", flush=True)
    covers = e_rows.reset_index(drop=True)
    cover_ids = [str(r.source_id) for r in covers.itertuples(index=False)]
    cover_rows = {str(r.source_id): r for r in covers.itertuples(index=False)}
    messages = {k: v for k, v in q4.compressed_messages().items() if len(v[2]) == 100}
    if len(messages) != 12:
        raise RuntimeError("E validation must use the same 12 100-byte messages")
    trials = []
    cover_message_results = []
    for mi, (mid, (family, index, source, compressed)) in enumerate(messages.items(), 1):
        solved = {}
        for ci, cid in enumerate(cover_ids):
            solved[cid] = q4.solve_cell_assignment(cid, mid, source, compressed,
                                                    p, q, bound, cover_rows[cid])
            locs, hashes, cw, blocks, assn, attacks = solved[cid]
            feasible = int(assn["parity_ok"])
            if feasible:
                okj, ej, tj = q4.recover_message(source, compressed, cw, blocks, assn,
                                                   hashes, attacks["jpeg"], locs, p)
                okn, en, tn = q4.recover_message(source, compressed, cw, blocks, assn,
                                                   hashes, attacks["noise"], locs, p)
                fixed_bits = math.ceil(math.log2(1764)) + math.ceil(math.log2(2 * bound + 1))
                ba = (assn["n_placed"] * fixed_bits + len(cw)) / len(source)
                body = q4.serialize_1quater_body(source, cw, assn, locs, config_id, m, 0, p)
                bt = 8 * (41 + len(zlib.compress(body, 9))) / len(source)
            else:
                okj = okn = 0; ej = en = tj = tn = 0; ba = bt = np.nan
            cover_message_results.append({"cover_id": cid, "message_id": mid, "family": family,
                "feasible": feasible, "success_jpeg": int(okj), "success_noise": int(okn),
                "b_assign": ba, "b_total_gallery0": bt,
                "N_placed": assn["n_placed"], "L_cw": len(cw),
                "erasures": int(assn["erasures"].sum()), "errors_jpeg": tj, "errors_noise": tn})
        orders = []
        for attempt in range(200):
            rng = np.random.Generator(np.random.PCG64(q4.seed_for(
                "A4/candidate_draws", "E", mid, str(attempt))))
            orders.append(rng.permutation(cover_ids).tolist())
        for attempt, order in enumerate(orders):
            selected = None
            for gallery_index, cid in enumerate(order[:m]):
                if solved[cid][4]["parity_ok"]:
                    selected = (cid, gallery_index, solved[cid])
                    break
            if selected is None:
                trials.append({"config_id": config_id, "p": p, "q": q, "m": m, "B": bound,
                    "message_id": mid, "family": family, "index": index, "attempt": attempt,
                    "selected_cover": "", "feasible": 0, "success_jpeg": 0, "success_noise": 0,
                    "b_assign": np.nan, "b_total": np.nan, "N_placed": 0,
                    "L_src": len(source), "L_c": len(compressed), "L_cw": len(compressed),
                    "erasures": np.nan, "errors_jpeg": np.nan, "errors_noise": np.nan})
                continue
            cid, gallery_index, data = selected
            locs, hashes, cw, blocks, assn, attacks = data
            okj, ej, tj = q4.recover_message(source, compressed, cw, blocks, assn,
                                               hashes, attacks["jpeg"], locs, p)
            okn, en, tn = q4.recover_message(source, compressed, cw, blocks, assn,
                                               hashes, attacks["noise"], locs, p)
            fixed_bits = math.ceil(math.log2(1764)) + math.ceil(math.log2(2 * bound + 1))
            ba = (assn["n_placed"] * fixed_bits + len(cw)) / len(source)
            body = q4.serialize_1quater_body(source, cw, assn, locs, config_id, m, gallery_index, p)
            bt = 8 * (41 + len(zlib.compress(body, 9))) / len(source)
            trials.append({"config_id": config_id, "p": p, "q": q, "m": m, "B": bound,
                "message_id": mid, "family": family, "index": index, "attempt": attempt,
                "selected_cover": cid, "feasible": 1, "success_jpeg": int(okj),
                "success_noise": int(okn), "b_assign": ba, "b_total": bt,
                "N_placed": assn["n_placed"], "L_src": len(source), "L_c": len(compressed),
                "L_cw": len(cw), "erasures": int(assn["erasures"].sum()),
                "errors_jpeg": tj, "errors_noise": tn, "gallery_index": gallery_index,
                "block_erasures": json.dumps(assn["block_erasures"])})
        print(f"E MESSAGE {mi}/12 {mid}: attempts=200", flush=True)
    cover_df = pd.DataFrame(cover_message_results)
    trial_df = pd.DataFrame(trials)
    if len(trial_df) != 2400 or trial_df.groupby("message_id").size().ne(200).any():
        raise RuntimeError("E trial count does not equal 12 messages × 200 attempts")
    if not trial_df.loc[trial_df.feasible.eq(1), "N_placed"].add(
            trial_df.loc[trial_df.feasible.eq(1), "erasures"]).eq(
            trial_df.loc[trial_df.feasible.eq(1), "L_cw"]).all():
        raise RuntimeError("E placement/erasure invariant failed")
    cover_df.to_csv(OUT / "E_cover_message_outcomes.csv.gz", index=False, compression="gzip")
    trial_df.to_csv(OUT / "E_validation_trials.csv.gz", index=False, compression="gzip")
    per_msg = trial_df.groupby(["message_id", "family"], as_index=False).agg(
        feasibility=("feasible", "mean"), success_jpeg=("success_jpeg", "mean"),
        success_noise=("success_noise", "mean"), b_assign=("b_assign", "mean"), b_total=("b_total", "mean"))
    per_msg[["wilson_jpeg_low", "wilson_jpeg_high", "wilson_noise_low", "wilson_noise_high"]] = np.nan
    for i, r in per_msg.iterrows():
        sj, sn = int(round(r.success_jpeg * 200)), int(round(r.success_noise * 200))
        per_msg.loc[i, ["wilson_jpeg_low", "wilson_jpeg_high"]] = wilson(sj, 200)
        per_msg.loc[i, ["wilson_noise_low", "wilson_noise_high"]] = wilson(sn, 200)
    per_msg.to_csv(OUT / "E_validation_by_message.csv", index=False)
    macro_jpeg = float(per_msg.success_jpeg.mean())
    macro_noise = float(per_msg.success_noise.mean())
    pooled_j = int(trial_df.success_jpeg.sum()); pooled_n = int(trial_df.success_noise.sum())
    gate = {
        "selected_configuration": frozen,
        "E_images": len(e_rows), "messages": len(messages), "attempts": len(trial_df),
        "macro_success_jpeg": macro_jpeg, "macro_success_noise": macro_noise,
        "per_message_min_jpeg": float(per_msg.success_jpeg.min()),
        "per_message_min_noise": float(per_msg.success_noise.min()),
        "pooled_wilson_2400_jpeg": wilson(pooled_j, len(trial_df)),
        "pooled_wilson_2400_noise": wilson(pooled_n, len(trial_df)),
        "N200_macro_wilson_jpeg": wilson(round(200 * macro_jpeg), 200),
        "N200_macro_wilson_noise": wilson(round(200 * macro_noise), 200),
        "G_Q3_point_estimate_pass": bool(macro_jpeg >= .96 and macro_noise >= .96),
        "G_Q3_N200_macro_wilson_pass": bool(wilson(round(200 * macro_jpeg), 200)[0] >= .92 and
                                             wilson(round(200 * macro_noise), 200)[0] >= .92),
        "per_message_wilson_reported_separately": True,
        "E_pixels_opened": True, "C_pixels_opened": False, "F_pixels_opened": False,
    }
    (OUT / "GQ3_gate.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "protocol": "FHAM-1quater-v1", "stage": "single-pass E validation",
        "frozen_GQ2_lock_sha256": sha(lock_path), "selected_configuration": frozen,
        "E_manifest_sha256": sha(e_manifest), "source_partition_manifest_sha256": sha(SOURCE_MANIFEST),
        "E_images": 200, "messages": 12, "attempts": 2400,
        "pixels_opened": {"D_b": "previously analyzed", "E": True, "C": False, "F": False},
        "opened_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "script_sha256": sha(Path(__file__)), "run_seconds": time.perf_counter() - begin,
    }
    (OUT / "E_validation_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2), flush=True)


if __name__ == "__main__":
    main()
