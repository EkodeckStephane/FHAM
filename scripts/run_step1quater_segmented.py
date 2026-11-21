#!/usr/bin/env python3
"""Run the preregistered A4 source-segmentation variant on D-b."""
from __future__ import annotations

import json
import math
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_step1quater as q4

OUT = q4.OUT
COLUMNS = ["config_id", "p", "q", "m", "B", "message_id", "family", "index", "attempt",
           "feasible", "success_jpeg", "success_noise", "covers_used", "selected_covers",
           "b_assign", "b_total", "N_placed", "L_src", "L_c", "L_cw", "erasures",
           "errors_jpeg", "errors_noise"]


def packed_bits(bits: str) -> bytes:
    if not bits:
        return b""
    bits += "0" * ((8 - len(bits) % 8) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


def serialize_segmented(source: bytes, segments: list[dict], config_id: int, m: int) -> bytes:
    nplaced = sum(s["assignment"]["n_placed"] for s in segments)
    lc = sum(len(s["compressed"]) for s in segments)
    lcw = sum(len(s["codeword"]) for s in segments)
    header = struct.pack(">4sBHHHI", b"FHQ1", 1, 256, 256, q4.BLOCK, nplaced)
    fixed = struct.pack(">HHHHH", config_id, len(source), lc, lcw, len(segments))
    directory_bits = ""
    cover_bits = math.ceil(math.log2(m)) if m > 1 else 0
    for seg in segments:
        directory_bits += format(len(seg["source"]), "08b")
        directory_bits += format(len(seg["compressed"]), "016b")
        directory_bits += format(len(seg["codeword"]), "016b")
        if cover_bits:
            directory_bits += format(seg["cover_id"], f"0{cover_bits}b")
    directory = packed_bits(directory_bits)
    crc = struct.pack(">I", zlib.crc32(source) & 0xffffffff)
    erasures = np.concatenate([s["assignment"]["erasures"] for s in segments]).astype(np.uint8)
    bitmap = np.packbits(erasures, bitorder="big").tobytes()
    records = bytearray()
    for seg in segments:
        assn, locs = seg["assignment"], seg["locations"]
        for i, j in enumerate(assn["positions"]):
            if j < 0:
                continue
            loc = locs[int(j)]
            block_idx = (loc.y // q4.BLOCK) * (256 // q4.BLOCK) + loc.x // q4.BLOCK
            token = block_idx * 4 + loc.arrangement
            records.extend(struct.pack(">Hh", token, int(assn["displacements"][i])))
    return header + fixed + crc + directory + bitmap + bytes(records)


def run():
    covers = pd.read_csv(q4.INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    if len(covers) != 100 or len(pd.read_csv(OUT / "robustness_summary.csv")) != 100:
        raise RuntimeError("Segmented A4 requires the frozen 100-cover D-b robustness output")
    messages = {k: v for k, v in q4.compressed_messages().items() if len(v[2]) == 100}
    if len(messages) != 12:
        raise RuntimeError("Segmented A4 must use exactly the 12 frozen 100-byte messages")
    cover_rows = {str(r.source_id): r for r in covers.itertuples(index=False)}
    cover_ids = list(cover_rows)
    params = [(p, q, m, b) for p in (0, 10, 20, 30, 40)
              for q in (0, 2, 5, 10) for m in (1, 2, 3, 5) for b in q4.BOUNDS]
    output = OUT / "A4_segmented_trials.csv.gz"
    done = set()
    if output.exists():
        prior = pd.read_csv(output, usecols=["config_id", "message_id"])
        counts = prior.groupby(["config_id", "message_id"]).size()
        if not counts.eq(100).all():
            raise RuntimeError("Existing segmented output contains a partial cell; preserve and audit before resuming")
        done = set(counts.index.tolist())
    rows_out = []
    started = time.perf_counter()
    for mid, (family, index, source, _whole_compressed) in messages.items():
        if all((160 + cid, mid) in done for cid in range(160)):
            continue
        raw_segments = [source[i:i + 50] for i in range(0, len(source), 50)]
        segments = [(raw, zlib.compress(raw, 9)) for raw in raw_segments]
        draw_orders = []
        for si in range(len(segments)):
            orders = []
            for attempt in range(100):
                rng = np.random.Generator(np.random.PCG64(
                    q4.seed_for("A4/candidate_draws", mid, "segment", str(si), str(attempt))))
                orders.append(rng.permutation(cover_ids).tolist())
            draw_orders.append(orders)
        for p in (0, 10, 20, 30, 40):
            for q in (0, 2, 5, 10):
                for bound in q4.BOUNDS:
                    base_ids = {160 + params.index((p, q, m, bound)) for m in (1, 2, 3, 5)}
                    if all((cid, mid) in done for cid in base_ids):
                        continue
                    solutions = []
                    for si, (seg_source, seg_comp) in enumerate(segments):
                        per_cover = {}
                        for cid in cover_ids:
                            per_cover[cid] = q4.solve_cell_assignment(
                                cid, mid, seg_source, seg_comp, p, q, bound, cover_rows[cid])
                        solutions.append(per_cover)
                    for m in (1, 2, 3, 5):
                        base_config = params.index((p, q, m, bound))
                        config_id = 160 + base_config
                        if (config_id, mid) in done:
                            continue
                        for attempt in range(100):
                            selected_segments = []
                            viable = True
                            for si, per_cover in enumerate(solutions):
                                selected = None
                                for gallery_index, cid in enumerate(draw_orders[si][attempt][:m]):
                                    data = per_cover[cid]
                                    if data[4]["parity_ok"]:
                                        selected = (cid, gallery_index, data)
                                        break
                                if selected is None:
                                    viable = False
                                    break
                                cid, gallery_index, data = selected
                                locs, hashes, cw, blocks, assn, attacks = data
                                selected_segments.append({
                                    "source": segments[si][0], "compressed": segments[si][1],
                                    "codeword": cw, "blocks": blocks, "assignment": assn,
                                    "locations": locs, "hashes": hashes, "attacks": attacks,
                                    "cover": cid, "cover_id": gallery_index,
                                })
                            if not viable:
                                rows_out.append({"config_id": config_id, "p": p, "q": q, "m": m, "B": bound,
                                    "message_id": mid, "family": family, "index": index, "attempt": attempt,
                                    "feasible": 0, "success_jpeg": 0, "success_noise": 0,
                                    "covers_used": 0, "selected_covers": "", "b_assign": np.nan,
                                    "b_total": np.nan, "N_placed": 0, "L_src": len(source),
                                    "L_c": sum(len(x[1]) for x in segments), "L_cw": 0,
                                    "erasures": np.nan, "errors_jpeg": np.nan, "errors_noise": np.nan})
                                continue
                            ok_j, ok_n, errors_j, errors_n, e_total = True, True, 0, 0, 0
                            for seg in selected_segments:
                                oj, ej, tj = q4.recover_message(
                                    seg["source"], seg["compressed"], seg["codeword"], seg["blocks"],
                                    seg["assignment"], seg["hashes"], seg["attacks"]["jpeg"],
                                    seg["locations"], p)
                                on, en, tn = q4.recover_message(
                                    seg["source"], seg["compressed"], seg["codeword"], seg["blocks"],
                                    seg["assignment"], seg["hashes"], seg["attacks"]["noise"],
                                    seg["locations"], p)
                                ok_j &= oj; ok_n &= on
                                errors_j += tj; errors_n += tn; e_total += ej
                            nplaced = sum(s["assignment"]["n_placed"] for s in selected_segments)
                            lcw = sum(len(s["codeword"]) for s in selected_segments)
                            fixed_bits = math.ceil(math.log2(1764)) + math.ceil(math.log2(2 * bound + 1))
                            b_assign = (nplaced * fixed_bits + lcw) / len(source)
                            body = serialize_segmented(source, selected_segments, config_id, m)
                            b_total = 8 * (41 + len(zlib.compress(body, 9))) / len(source)
                            rows_out.append({"config_id": config_id, "p": p, "q": q, "m": m, "B": bound,
                                "message_id": mid, "family": family, "index": index, "attempt": attempt,
                                "feasible": 1, "success_jpeg": int(ok_j), "success_noise": int(ok_n),
                                "covers_used": len({s["cover"] for s in selected_segments}),
                                "selected_covers": ";".join(s["cover"] for s in selected_segments),
                                "b_assign": b_assign, "b_total": b_total, "N_placed": nplaced,
                                "L_src": len(source), "L_c": sum(len(s["compressed"]) for s in selected_segments),
                                "L_cw": lcw, "erasures": sum(s["assignment"]["erasures"].sum() for s in selected_segments),
                                "errors_jpeg": errors_j, "errors_noise": errors_n})
                    if len(rows_out) >= 800:
                        pd.DataFrame(rows_out).reindex(columns=COLUMNS).to_csv(output, index=False,
                            compression="gzip", mode="a" if output.exists() else "w", header=not output.exists())
                        rows_out.clear()
                        print(f"SEG {mid} p={p} q={q} B={bound}; {time.perf_counter()-started:.1f}s", flush=True)
    if rows_out:
        pd.DataFrame(rows_out).reindex(columns=COLUMNS).to_csv(output, index=False,
            compression="gzip", mode="a" if output.exists() else "w", header=not output.exists())
    data = pd.read_csv(output, low_memory=False)
    expected_rows = 160 * 12 * 100
    counts = data.groupby(["config_id", "message_id"]).size()
    if len(data) != expected_rows or data.config_id.nunique() != 160 or not counts.eq(100).all():
        raise RuntimeError(f"Segmented result shape mismatch: rows={len(data)}, cells={data.config_id.nunique()}")
    placed_rows = data.feasible.eq(1)
    if not data.loc[placed_rows, "N_placed"].add(data.loc[placed_rows, "erasures"]).eq(
            data.loc[placed_rows, "L_cw"]).all():
        raise RuntimeError("Segmented record invariant N_placed + erasures = L_cw failed")
    expected_b = (data.loc[placed_rows, "N_placed"] *
                  (math.ceil(math.log2(1764)) + data.loc[placed_rows, "B"].map(
                      lambda b: math.ceil(math.log2(2 * int(b) + 1)))) +
                  data.loc[placed_rows, "L_cw"]) / data.loc[placed_rows, "L_src"]
    if not np.allclose(data.loc[placed_rows, "b_assign"], expected_b, atol=1e-10):
        raise RuntimeError("Segmented b_assign does not match the frozen formula")
    summary = data.groupby(["config_id", "p", "q", "m", "B", "family"], as_index=False).agg(
        success_jpeg=("success_jpeg", "mean"), success_noise=("success_noise", "mean"),
        feasibility=("feasible", "mean"), b_assign=("b_assign", "mean"), b_total=("b_total", "mean"),
        mean_covers_used=("covers_used", "mean"))
    summary.to_csv(OUT / "A4_segmented_summary_by_family.csv", index=False)
    cell = data.groupby(["config_id", "p", "q", "m", "B"], as_index=False).agg(
        success_jpeg=("success_jpeg", "mean"), success_noise=("success_noise", "mean"),
        feasibility=("feasible", "mean"), b_assign=("b_assign", "mean"), b_total=("b_total", "mean"),
        mean_covers_used=("covers_used", "mean"))
    cell["success_combined"] = cell[["success_jpeg", "success_noise"]].min(axis=1)
    cell.to_csv(OUT / "A4_segmented_summary.csv", index=False)
    print(f"SEGMENTED COMPLETE rows={len(data)} cells={data.config_id.nunique()} elapsed={time.perf_counter()-started:.1f}s", flush=True)


if __name__ == "__main__":
    run()
