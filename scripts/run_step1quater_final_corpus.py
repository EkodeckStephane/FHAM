#!/usr/bin/env python3
"""Single-pass G-Q4 evaluation on the pre-frozen C or F corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_step1quater as q4

FINAL = q4.OUT / "final_freeze"
RUN_ROOT = q4.OUT
LOCK_PATH = FINAL / "preopen_sizing_and_manifest_lock.json"
CONFIG = {"config_id": 50, "p": 10, "q": 5, "m": 2, "B": 4}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def wilson(k: int, n: int, z: float = 1.959963984540054):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def body_record(source: bytes, codeword: bytes, assignment: dict,
                locations: list, selected_cover_id: int, width: int, height: int):
    nplaced = assignment["n_placed"]
    header = struct.pack(">4sBHHHI", b"FHQ1", 1, width, height, q4.BLOCK, nplaced)
    code_source_len = len(zlib.compress(source, 9))
    crc = struct.pack(">I", zlib.crc32(source) & 0xffffffff)
    bits = format(selected_cover_id, "01b")
    directory = bytes([len(source)]) + struct.pack(">HH", code_source_len, len(codeword))
    directory += int(bits + "0" * 7, 2).to_bytes(1, "big")
    fixed = struct.pack(">HHHHH", 50, len(source), code_source_len, len(codeword), 1)
    erasures = np.packbits(assignment["erasures"].astype(np.uint8), bitorder="big").tobytes()
    records = bytearray()
    nblocks_x = width // q4.BLOCK
    for i, j in enumerate(assignment["positions"]):
        if j < 0:
            continue
        loc = locations[int(j)]
        block_index = (loc.y // q4.BLOCK) * nblocks_x + loc.x // q4.BLOCK
        token = block_index * 4 + loc.arrangement
        records.extend(struct.pack(">Hh", token, int(assignment["displacements"][i])))
    return header + fixed + crc + directory + erasures + bytes(records)


def run(corpus: str):
    if corpus not in {"C", "F"}:
        raise ValueError(corpus)
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    gate = json.loads((RUN_ROOT / "E_validation/GQ3_gate.json").read_text(encoding="utf-8"))
    if not gate["G_Q3_all_frozen_checks_pass"]:
        raise RuntimeError("G-Q3 is not green")
    if lock["pixel_state_at_freeze"] != {"C": False, "F": False}:
        raise RuntimeError("C/F pixels were already opened before the final freeze")
    n = int(lock["N_C_frozen"] if corpus == "C" else lock["N_F_frozen"])
    manifest_path = FINAL / f"{corpus}_final_manifest_hash_only.csv"
    if not manifest_path.is_file():
        raise RuntimeError(f"Missing frozen {corpus} manifest")
    out = q4.OUT / f"{corpus}_final"
    out.mkdir(parents=True, exist_ok=True)
    if (out / f"{corpus}_validation_provenance.json").exists():
        raise RuntimeError(f"{corpus} already has a provenance record; single-pass stop")

    manifest = pd.read_csv(manifest_path, keep_default_na=False)
    if len(manifest) != n:
        raise RuntimeError(f"{corpus} frozen manifest size mismatch: {len(manifest)} != {n}")
    root = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover" if corpus == "C"
                else r"C:\Users\User\Downloads\Compressed\cpu_stego_experiments\datasets\BOSSbase")
    width = height = 256 if corpus == "C" else 512
    expected_positions = 1764 if corpus == "C" else 7056
    manifest["relative_path"] = manifest.source_id
    if corpus == "C":
        manifest["relative_path"] = manifest.relative_path
    q4.IMAGE_ROOT = root
    q4.OUT = out
    q4.CODEBOOK_CACHE.clear(); q4.IMAGE_CACHE.clear(); q4.ATTACK_CACHE.clear()
    positions_root = out / "robustness_positions"
    positions_root.mkdir(exist_ok=True)
    robustness = []
    start = time.perf_counter()
    for ix, row in enumerate(manifest.itertuples(index=False), 1):
        path = root / str(row.relative_path)
        if sha(path) != str(row.sha256):
            raise RuntimeError(f"{corpus} SHA-256 mismatch for {row.source_id}: {path}")
        image = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
        if image.shape != (height, width):
            raise RuntimeError(f"{corpus} shape mismatch {row.source_id}: {image.shape}")
        profile, locs, _lookup, base = q4.locations_and_hashes(image, "mean_ordinal")
        if profile != 12 or len(locs) != expected_positions:
            raise RuntimeError(f"{corpus} codebook mismatch {row.source_id}: L={profile}, M={len(locs)}")
        flips = {name: np.zeros(len(locs), dtype=np.uint16) for name in ("jpeg", "noise")}
        attacks = q4.draw_development_attacks(image, str(row.sha256))
        for family, variants in attacks.items():
            for attacked, _q, _sigma in variants:
                current = q4.batch_hash_map(attacked, "mean_ordinal", 12, locs)
                flips[family] += np.fromiter((current[x] != base[x] for x in locs), dtype=np.uint16,
                                              count=len(locs))
        robust = (flips["jpeg"] == 0) & (flips["noise"] == 0)
        total = flips["jpeg"] + flips["noise"]
        shat = np.where(robust, 1.0, (101.0 - total) / 102.0)
        pd.DataFrame({"position_index": np.arange(len(locs)), "x": [x.x for x in locs],
                      "y": [x.y for x in locs], "arrangement": [x.arrangement for x in locs],
                      "hash_value": [base[x] for x in locs], "jpeg_flips": flips["jpeg"],
                      "noise_flips": flips["noise"], "robust": robust.astype(np.uint8),
                      "s_hat": shat}).to_csv(positions_root / f"{Path(str(row.source_id)).stem}.csv.gz",
                                              index=False, compression="gzip")
        robustness.append({"cover_id": row.source_id, "sha256": row.sha256,
                           "robust_positions": int(robust.sum()),
                           "robust_fraction": float(robust.mean())})
        if ix % 20 == 0:
            print(f"{corpus} ROBUST {ix}/{n}; elapsed={time.perf_counter()-start:.1f}s", flush=True)
    pd.DataFrame(robustness).to_csv(out / f"{corpus}_robustness_summary.csv", index=False)

    messages = {k: v for k, v in q4.compressed_messages().items() if len(v[2]) == 100}
    if len(messages) != 12:
        raise RuntimeError("Expected the same 12 frozen 100-byte messages")
    cover_ids = manifest.source_id.astype(str).tolist()
    cover_rows = {str(r.source_id): r for r in manifest.itertuples(index=False)}
    solved = {}
    outcomes = []
    for mid, (family, index, source, compressed) in messages.items():
        solved[mid] = {}
        for cid in cover_ids:
            result = q4.solve_cell_assignment(cid, mid, source, compressed, 10, 5, 4, cover_rows[cid])
            solved[mid][cid] = result
            locs, hashes, cw, blocks, assn, attacks = result
            feasible = int(assn["parity_ok"])
            if feasible:
                okj, _ej, tj = q4.recover_message(source, compressed, cw, blocks, assn,
                                                   hashes, attacks["jpeg"], locs, 10)
                okn, _en, tn = q4.recover_message(source, compressed, cw, blocks, assn,
                                                   hashes, attacks["noise"], locs, 10)
            else:
                okj = okn = False; tj = tn = 0
            outcomes.append({"cover_id": cid, "message_id": mid, "family": family,
                             "feasible": feasible, "success_jpeg": int(okj), "success_noise": int(okn),
                             "errors_jpeg": tj, "errors_noise": tn,
                             "N_placed": assn["n_placed"], "L_cw": len(cw),
                             "erasures": int(assn["erasures"].sum())})

    trials = []
    for mid, (family, index, source, compressed) in messages.items():
        for attempt in range(200):
            rng = np.random.Generator(np.random.PCG64(q4.seed_for(
                "A4/candidate_draws", corpus, mid, str(attempt))))
            order = rng.permutation(cover_ids).tolist()
            selected = None
            for gallery_index, cid in enumerate(order[:2]):
                if solved[mid][cid][4]["parity_ok"]:
                    selected = (cid, gallery_index, solved[mid][cid]); break
            if selected is None:
                trials.append({"message_id": mid, "family": family, "attempt": attempt,
                               "selected_cover": "", "feasible": 0, "success_jpeg": 0,
                               "success_noise": 0, "b_assign": np.nan, "b_total": np.nan})
                continue
            cid, gallery_index, data = selected
            locs, hashes, cw, blocks, assn, attacks = data
            okj, _ej, tj = q4.recover_message(source, compressed, cw, blocks, assn,
                                               hashes, attacks["jpeg"], locs, 10)
            okn, _en, tn = q4.recover_message(source, compressed, cw, blocks, assn,
                                               hashes, attacks["noise"], locs, 10)
            fixed_bits = math.ceil(math.log2(expected_positions)) + math.ceil(math.log2(9))
            b_assign = (assn["n_placed"] * fixed_bits + len(cw)) / len(source)
            body = body_record(source, cw, assn, locs, gallery_index, width, height)
            b_total = 8 * (41 + len(zlib.compress(body, 9))) / len(source)
            trials.append({"message_id": mid, "family": family, "attempt": attempt,
                           "selected_cover": cid, "feasible": 1, "success_jpeg": int(okj),
                           "success_noise": int(okn), "b_assign": b_assign, "b_total": b_total,
                           "N_placed": assn["n_placed"], "L_c": len(compressed), "L_cw": len(cw),
                           "erasures": int(assn["erasures"].sum()), "errors_jpeg": tj, "errors_noise": tn,
                           "gallery_index": gallery_index})
    outcome_df = pd.DataFrame(outcomes)
    trial_df = pd.DataFrame(trials)
    outcome_df.to_csv(out / f"{corpus}_cover_message_outcomes.csv.gz", index=False, compression="gzip")
    trial_df.to_csv(out / f"{corpus}_validation_trials.csv.gz", index=False, compression="gzip")
    per_msg = trial_df.groupby(["message_id", "family"], as_index=False).agg(
        feasibility=("feasible", "mean"), success_jpeg=("success_jpeg", "mean"),
        success_noise=("success_noise", "mean"), b_assign=("b_assign", "mean"), b_total=("b_total", "mean"))
    per_msg.to_csv(out / f"{corpus}_validation_by_message.csv", index=False)
    macro_j = float(per_msg.success_jpeg.mean()); macro_n = float(per_msg.success_noise.mean())
    gate = {"corpus": corpus, "images": n, "messages": len(messages), "attempts": len(trial_df),
            "macro_success_jpeg": macro_j, "macro_success_noise": macro_n,
            "per_message_min_jpeg": float(per_msg.success_jpeg.min()),
            "per_message_min_noise": float(per_msg.success_noise.min()),
            "pooled_wilson_jpeg": wilson(int(trial_df.success_jpeg.sum()), len(trial_df)),
            "pooled_wilson_noise": wilson(int(trial_df.success_noise.sum()), len(trial_df)),
            "N200_macro_wilson_jpeg": wilson(round(200 * macro_j), 200),
            "N200_macro_wilson_noise": wilson(round(200 * macro_n), 200),
            "all_checks": bool(macro_j >= .96 and macro_n >= .96 and
                               wilson(round(200 * macro_j), 200)[0] >= .92 and
                               wilson(round(200 * macro_n), 200)[0] >= .92),
            "config": CONFIG, "pixel_opened": True}
    (out / f"{corpus}_provisional_gate.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    provenance = {"protocol": "FHAM-1quater-v1 + pre-open clarification 2026-11-21",
                  "corpus": corpus, "N": n, "manifest_sha256": sha(manifest_path),
                  "freeze_sha256": sha(LOCK_PATH), "GQ2_lock_sha256": sha(RUN_ROOT / "GQ2_configuration_freeze.json"),
                  "config": CONFIG, "images": n, "messages": len(messages), "attempts": len(trial_df),
                  "pixels_opened": {"C": corpus == "C", "F": corpus == "F"},
                  "opened_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "elapsed_seconds": time.perf_counter() - start}
    (out / f"{corpus}_validation_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n",
                                                                encoding="utf-8")
    print(json.dumps(gate, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", choices=("C", "F"))
    run(parser.parse_args().corpus)
