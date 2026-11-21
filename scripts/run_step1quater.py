#!/usr/bin/env python3
"""Run the preregistered FHAM 1quater analyses on frozen D-b only.

Stages are resumable: robustness, A1, or all. Results are written exclusively
under results/stability_step1/step1quater/run/.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching, min_weight_full_bipartite_matching
from reedsolo import RSCodec

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fham.descriptors import _ordinal_arrangements
from fham.methods import Location, OptimalAssignmentMethod
from run_step1ter_descriptor_screen import batch_hash_map, locations_and_hashes
from stability_step1_pilot import transform

INPUT = ROOT / "results/stability_step1/step1quater/manifest"
OUT = ROOT / "results/stability_step1/step1quater/run"
IMAGE_ROOT = Path(r"C:\Users\User\Downloads\Compressed\BOWS2_extracted\cover")
PROTOCOL = ROOT / "protocols/FHAM_etape_1quater_preregistre.md"
MASTER = 20261120
BLOCK = 12
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")
INDICES = ("00", "01", "02")
LENGTHS = (25, 50, 100, 200)
BOUNDS = (4, 8)
CODEBOOK_CACHE = {}
IMAGE_CACHE = {}
ATTACK_CACHE = {}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def seed_for(stream: str, *ids: str) -> int:
    payload = "FHAM-1quater-v1|" + str(MASTER) + "|" + stream + "|" + "|".join(ids)
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def draw_development_attacks(image: np.ndarray, image_sha: str):
    result = {"jpeg": [], "noise": []}
    for family, stream in (("jpeg", "robustness/jpeg"), ("noise", "robustness/noise")):
        rng = np.random.Generator(np.random.PCG64(seed_for(stream, image_sha, "robustness")))
        for rep in range(50):
            if family == "jpeg":
                q = int(rng.integers(70, 91))
                while 74 <= q <= 76:
                    q = int(rng.integers(70, 91))
                atk = transform(image, f"jpeg{q}", seed_for(stream, image_sha, "robustness", family, str(rep)), "bilinear")
                result[family].append((atk, q, None))
            else:
                sigma = float(rng.uniform(1.0, 2.4))
                while 1.9 <= sigma <= 2.1:
                    sigma = float(rng.uniform(1.0, 2.4))
                atk = transform(image, f"noise{sigma:.12f}", seed_for(stream, image_sha, "robustness", family, str(rep)), "bilinear")
                result[family].append((atk, None, sigma))
    return result


def run_robustness(limit: int = 100):
    OUT.mkdir(parents=True, exist_ok=True)
    covers = pd.read_csv(INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    if len(covers) != 100:
        raise RuntimeError(f"Frozen D-b manifest has {len(covers)} rows, expected 100")
    provenance_path = OUT / "robustness_provenance.json"
    provenance = {
        "protocol": "FHAM-1quater-v1", "stage": "D-b robustness", "covers": limit,
        "timing_pilot": limit == 5,
        "block_size": BLOCK, "descriptor": "mean_ordinal", "K_per_family": 50,
        "attack_sampling": "uniform JPEG integer 70..90 excluding 74..76; uniform sigma [1,2.4) excluding [1.9,2.1], exact rejection resampling",
        "seed_derivation": "SHA256 UTF-8 FHAM-1quater-v1|20261120|stream|image_sha256|robustness|family|replicate; first 64 bits big endian",
        "input_manifest_sha256": digest(INPUT / "D_b_images_sha256.csv"),
        "protocol_sha256": digest(PROTOCOL), "script_sha256": digest(Path(__file__)),
        "opened": {"D_b": True, "E": False, "C": False, "F": False},
    }
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    summary_path = OUT / "robustness_summary.csv"
    complete = set()
    if summary_path.exists():
        complete = set(pd.read_csv(summary_path).cover_id.astype(str))
    summaries = []
    if summary_path.exists():
        summaries = pd.read_csv(summary_path).to_dict("records")
    detail_root = OUT / "robustness_positions"
    detail_root.mkdir(exist_ok=True)
    for ix, row in covers.head(limit).iterrows():
        cover_id = str(row.source_id)
        if cover_id in complete:
            continue
        image_path = IMAGE_ROOT / str(row.relative_path)
        if digest(image_path) != str(row.sha256):
            raise RuntimeError(f"D-b source hash mismatch: {image_path}")
        image = np.asarray(Image.open(image_path).convert("L"), dtype=np.uint8)
        if image.shape != (256, 256):
            raise RuntimeError(f"D-b expected native 256x256 image: {cover_id}, got {image.shape}")
        profile, locations, _lookup, base = locations_and_hashes(image, "mean_ordinal")
        if profile != BLOCK or len(locations) != 1764:
            raise RuntimeError(f"Unexpected C-mean codebook for {cover_id}: L={profile}, M={len(locations)}")
        flips = {family: np.zeros(len(locations), dtype=np.uint16) for family in ("jpeg", "noise")}
        loc_index = {loc: i for i, loc in enumerate(locations)}
        attacks = draw_development_attacks(image, str(row.sha256))
        t0 = time.perf_counter()
        for family, variants in attacks.items():
            for attacked, _q, _sigma in variants:
                current = batch_hash_map(attacked, "mean_ordinal", BLOCK, locations)
                flips[family] += np.fromiter((current[loc] != base[loc] for loc in locations), dtype=np.uint16, count=len(locations))
        robust_mask = (flips["jpeg"] == 0) & (flips["noise"] == 0)
        f = flips["jpeg"] + flips["noise"]
        stability = np.where(robust_mask, 1.0, (101.0 - f) / 102.0)
        details = pd.DataFrame({
            "position_index": np.arange(len(locations), dtype=np.int32),
            "x": [x.x for x in locations], "y": [x.y for x in locations],
            "arrangement": [x.arrangement for x in locations],
            "hash_value": [base[x] for x in locations],
            "jpeg_flips": flips["jpeg"], "noise_flips": flips["noise"],
            "robust": robust_mask.astype(np.uint8), "s_hat": stability,
        })
        details.to_csv(detail_root / f"{Path(cover_id).stem}.csv.gz", index=False, compression="gzip")
        summaries.append({
            "cover_id": cover_id, "sha256": row.sha256, "height": 256, "width": 256,
            "block_size": BLOCK, "positions": len(locations), "robust_positions": int(robust_mask.sum()),
            "robust_fraction": float(robust_mask.mean()), "mean_s_hat": float(stability.mean()),
            "elapsed_seconds": time.perf_counter() - t0,
        })
        pd.DataFrame(summaries).to_csv(summary_path, index=False)
        print(f"ROBUST {ix+1}/{limit} {cover_id}: {int(robust_mask.sum())}/{len(locations)} ({time.perf_counter()-t0:.2f}s)", flush=True)
    return summaries


def load_codebook(cover_id: str):
    if cover_id in CODEBOOK_CACHE:
        return CODEBOOK_CACHE[cover_id]
    df = pd.read_csv(OUT / "robustness_positions" / f"{Path(cover_id).stem}.csv.gz")
    locs = [Location(int(r.x), int(r.y), int(r.arrangement)) for r in df.itertuples(index=False)]
    hashes = df.hash_value.to_numpy(dtype=np.int16)
    robust = df.robust.to_numpy(dtype=bool)
    s_hat = df.s_hat.to_numpy(dtype=np.float64)
    CODEBOOK_CACHE[cover_id] = (locs, hashes, robust, s_hat)
    return CODEBOOK_CACHE[cover_id]


def compressed_messages():
    rows = pd.read_csv(INPUT / "messages_sha256.csv", keep_default_na=False)
    messages = {}
    for r in rows.itertuples(index=False):
        raw = (ROOT / r.path).read_bytes()
        if digest(ROOT / r.path) != r.sha256 or len(raw) != int(r.L_src):
            raise RuntimeError(f"Frozen message mismatch: {r.message_id}")
        messages[r.message_id] = (r.family, r.index, raw, zlib.compress(raw, 9))
    return messages


def edge_graph(targets: np.ndarray, hashes: np.ndarray, available: np.ndarray, bound: int):
    cols = np.flatnonzero(available)
    rows, local_cols = [], []
    for i, target in enumerate(targets):
        hits = np.flatnonzero(np.abs(hashes[cols] - int(target)) <= bound)
        rows.extend([i] * len(hits))
        local_cols.extend(hits.tolist())
    graph = csr_matrix((np.ones(len(rows), dtype=np.int8), (rows, local_cols)), shape=(len(targets), len(cols)))
    return graph, cols


def max_match(targets: bytes, hashes: np.ndarray, available: np.ndarray, bound: int):
    graph, cols = edge_graph(np.frombuffer(targets, dtype=np.uint8), hashes, available, bound)
    matching = maximum_bipartite_matching(graph, perm_type="column")
    matched_rows = np.flatnonzero(matching >= 0)
    matched_positions = cols[matching[matched_rows]]
    residuals = np.frombuffer(targets, dtype=np.uint8)[matched_rows].astype(np.int16) - hashes[matched_positions]
    return matched_rows, matched_positions, residuals


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054):
    if n <= 0:
        return (float("nan"), float("nan"))
    p = successes / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return center - half, center + half


def run_a1():
    if not (OUT / "robustness_summary.csv").exists() or len(pd.read_csv(OUT / "robustness_summary.csv")) != 100:
        raise RuntimeError("A1 requires complete D-b robustness output")
    covers = pd.read_csv(INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    messages = compressed_messages()
    results = []
    out_path = OUT / "A1_by_cover_message.csv"
    done = set()
    if out_path.exists():
        old = pd.read_csv(out_path)
        results = old.to_dict("records")
        done = set(zip(old.cover_id.astype(str), old.message_id.astype(str), old.B.astype(int)))
    total = len(covers) * len(messages) * len(BOUNDS)
    start = time.perf_counter()
    for ci, cover in covers.iterrows():
        cover_id = str(cover.source_id)
        _locs, hashes, robust, _s = load_codebook(cover_id)
        for message_id, (family, index, raw, compressed) in messages.items():
            for bound in BOUNDS:
                key = (cover_id, message_id, bound)
                if key in done:
                    continue
                targets = np.frombuffer(compressed, dtype=np.uint8)
                rr, pp, dd = max_match(compressed, hashes, robust, bound)
                deficit = len(compressed) - len(rr)
                no_candidate = int(sum(not np.any(robust & (np.abs(hashes.astype(np.int16) - int(t)) <= bound)) for t in targets))
                results.append({
                    "cover_id": cover_id, "family": family, "index": index, "message_id": message_id,
                    "L_src": len(raw), "L_c": len(compressed), "B": bound,
                    "robust_positions": int(robust.sum()), "max_matching": len(rr),
                    "feasible": int(deficit == 0), "deficit": deficit,
                    "symbols_without_candidate": no_candidate,
                    "d_hall": max(0, deficit - no_candidate),
                    "mean_abs_residual": float(np.abs(dd).mean()) if len(dd) else None,
                })
                done.add(key)
        if (ci + 1) % 5 == 0 or ci == len(covers) - 1:
            pd.DataFrame(results).to_csv(out_path, index=False)
            print(f"A1 {ci+1}/100 covers; {len(results)}/{total} rows; elapsed {time.perf_counter()-start:.1f}s", flush=True)
    summary = pd.DataFrame(results)
    per_message = summary.groupby(["L_src", "B", "family", "message_id"], as_index=False).agg(
        feasibility=("feasible", "mean"), mean_capacity=("max_matching", "mean"),
        median_capacity=("max_matching", "median"), mean_deficit=("deficit", "mean"),
    )
    per_message[["wilson_low", "wilson_high"]] = pd.DataFrame(
        per_message.feasibility.map(lambda p: wilson_interval(round(float(p) * 100), 100)).tolist(),
        index=per_message.index, columns=["wilson_low", "wilson_high"])
    per_message.to_csv(OUT / "A1_by_message_summary.csv", index=False)
    cover_joint = summary.groupby(["cover_id", "L_src", "B"], as_index=False).agg(
        n_messages=("message_id", "nunique"), all_12_feasible=("feasible", "min"),
        mean_message_capacity=("max_matching", "mean"),
    )
    if not cover_joint.n_messages.eq(12).all():
        raise RuntimeError("A1 joint feasibility requires all 12 messages per cover/length/B")
    joint = cover_joint.groupby(["L_src", "B"], as_index=False).agg(
        joint_feasibility=("all_12_feasible", "mean"), mean_message_capacity=("mean_message_capacity", "mean"),
    )
    joint[["wilson_low", "wilson_high"]] = pd.DataFrame(
        joint.joint_feasibility.map(lambda p: wilson_interval(round(float(p) * 100), 100)).tolist(),
        index=joint.index, columns=["wilson_low", "wilson_high"])
    joint.to_csv(OUT / "A1_joint_summary.csv", index=False)
    cover_joint.to_csv(OUT / "A1_joint_by_cover.csv", index=False)
    return summary


def balanced_blocks(length: int, max_source: int = 128):
    count = max(1, math.ceil(length / max_source))
    base, extra = divmod(length, count)
    result, cursor = [], 0
    for i in range(count):
        size = base + (1 if i < extra else 0)
        result.append((cursor, size))
        cursor += size
    return result


def rs_encode(compressed: bytes, p: int):
    blocks, codewords = [], []
    for source_start, source_len in balanced_blocks(len(compressed)):
        data = compressed[source_start:source_start + source_len]
        parity = math.ceil((p / 100) * source_len) if p else 0
        if parity:
            codec = RSCodec(parity, nsize=255, fcr=0, generator=2, prim=0x11D, c_exp=8)
            cw = bytes(codec.encode(data))
        else:
            cw = data
        blocks.append({"src_start": source_start, "src_len": source_len,
                       "cw_start": sum(len(x) for x in codewords), "cw_len": len(cw),
                       "parity": parity})
        codewords.append(cw)
    return b"".join(codewords), blocks


def assignment_graph(targets: bytes, hashes: np.ndarray, s_hat: np.ndarray,
                     robust: np.ndarray, allowed: np.ndarray, bound: int,
                     blocks: list[dict], p: int, q: int):
    """Minimum-cost maximum placement with block-limited erasure slots.

    The objective is lexicographic: robust placements first for q>0, then
    total placements, then minimum L1 residual, then maximum sum log(s_hat).
    """
    t = np.frombuffer(targets, dtype=np.uint8).astype(np.int16)
    pos = np.flatnonzero(allowed)
    n = len(t)
    # Dummy columns are grouped by RS block, so each block's erasure count is
    # visible and checked against its frozen parity allowance after matching.
    dummy_base = len(pos)
    dummy_ranges = []
    for b in blocks:
        dummy_ranges.append((b["cw_start"], b["cw_start"] + b["cw_len"], dummy_base,
                             dummy_base + b["parity"]))
        dummy_base += b["parity"]
    scale = n * math.log(102.0) + 1.0
    residual_max = bound * scale + math.log(102.0) + 1.0
    placement_weight = n * residual_max + 1.0
    robust_weight = n * (placement_weight + residual_max) + 1.0
    rr, cc, vv = [], [], []
    for i, target in enumerate(t):
        hit = np.flatnonzero(np.abs(hashes[pos] - target) <= bound)
        for loc in hit:
            j = int(pos[loc])
            residual = abs(int(target) - int(hashes[j]))
            cost = residual * scale - math.log(float(s_hat[j]))
            if q > 0 and not robust[j]:
                cost += robust_weight
            rr.append(i); cc.append(int(loc)); vv.append(cost + 1e-9)
        for start, end, dbeg, dend in dummy_ranges:
            if start <= i < end:
                for dcol in range(dbeg, dend):
                    # Each block has exactly its parity allowance in erasure slots.
                    rr.append(i); cc.append(dcol); vv.append(robust_weight + placement_weight + 1e-9)
                break
    graph = csr_matrix((np.asarray(vv, dtype=np.float64),
                        (np.asarray(rr, dtype=np.int32), np.asarray(cc, dtype=np.int32))),
                       shape=(n, dummy_base))
    try:
        rows, cols = min_weight_full_bipartite_matching(graph)
    except ValueError:
        # No assignment satisfies the RS erasure budget. Retain the maximum
        # partial matching for descriptive payload-cost accounting; this trial
        # remains infeasible and cannot count as successful communication.
        graph_real = graph[:, :len(pos)]
        match = maximum_bipartite_matching(graph_real, perm_type="column")
        rows = np.flatnonzero(match >= 0)
        cols = match[rows]
    by_row = np.full(n, -1, dtype=np.int32)
    real = cols < len(pos)
    by_row[rows[real]] = pos[cols[real]]
    erasures = by_row < 0
    block_erasures = []
    for b in blocks:
        e = int(erasures[b["cw_start"]:b["cw_start"] + b["cw_len"]].sum())
        block_erasures.append(e)
    parity_ok = len(rows) == n and all(e <= b["parity"] for e, b in zip(block_erasures, blocks))
    displacements = np.zeros(n, dtype=np.int16)
    for i in np.flatnonzero(~erasures):
        displacements[i] = int(t[i]) - int(hashes[by_row[i]])
    return {"positions": by_row, "erasures": erasures, "displacements": displacements,
            "block_erasures": block_erasures, "parity_ok": parity_ok,
            "n_placed": int((~erasures).sum()), "residual_sum": int(np.abs(displacements[~erasures]).sum())}


def validation_hashes(image: np.ndarray, locations: list[Location], cover_sha: str, message_id: str):
    key = (cover_sha, message_id)
    if key in ATTACK_CACHE:
        return ATTACK_CACHE[key]
    outputs = {}
    for family, attack_name, stream in (("jpeg", "jpeg75", "attacks/jpeg"),
                                        ("noise", "noise2.00000000", "attacks/noise")):
        seed = seed_for(stream, cover_sha, message_id, family, "0")
        attacked = transform(image, attack_name, seed, "bilinear")
        outputs[family] = batch_hash_map(attacked, "mean_ordinal", BLOCK, locations)
    ATTACK_CACHE[key] = outputs
    return outputs


def recover_message(source: bytes, compressed: bytes, codeword: bytes, blocks: list[dict],
                    assignment: dict, hashes: np.ndarray, transformed: dict,
                    locations: list[Location], p: int):
    positions = assignment["positions"]
    recv = np.zeros(len(codeword), dtype=np.uint8)
    actual = np.frombuffer(codeword, dtype=np.uint8)
    errors = 0
    for i, j in enumerate(positions):
        if j < 0:
            continue
        loc = locations[int(j)]
        val = int(transformed[loc]) + int(assignment["displacements"][i])
        val = min(255, max(0, val))
        recv[i] = val
        errors += int(val != int(actual[i]))
    recovered_compressed = bytearray()
    total_e = 0
    try:
        for b in blocks:
            a, z = b["cw_start"], b["cw_start"] + b["cw_len"]
            erasures = np.flatnonzero(positions[a:z] < 0).tolist()
            total_e += len(erasures)
            if len(erasures) > b["parity"]:
                return False, total_e, errors
            chunk = bytes(recv[a:z])
            if b["parity"]:
                codec = RSCodec(b["parity"], nsize=255, fcr=0, generator=2, prim=0x11D, c_exp=8)
                decoded = bytes(codec.decode(chunk, erase_pos=erasures)[0])
            else:
                if erasures:
                    return False, total_e, errors
                decoded = chunk
            recovered_compressed.extend(decoded)
        rebuilt = zlib.decompress(bytes(recovered_compressed))
        return rebuilt == source, total_e, errors
    except Exception:
        return False, total_e, errors


def serialize_1quater_body(source: bytes, codeword: bytes, assignment: dict,
                           locations: list[Location], config_id: int, m: int,
                           selected_cover_id: int, p: int):
    nplaced = assignment["n_placed"]
    header = struct.pack(">4sBHHHI", b"FHQ1", 1, 256, 256, BLOCK, nplaced)
    code_source_len = len(zlib.compress(source, 9))
    crc = struct.pack(">I", zlib.crc32(source) & 0xffffffff)
    cover_bits = math.ceil(math.log2(m)) if m > 1 else 0
    bitstring = format(selected_cover_id, f"0{cover_bits}b") if cover_bits else ""
    directory = bytes([len(source)]) + struct.pack(">HH", code_source_len, len(codeword))
    directory += int(bitstring + "0" * ((8 - len(bitstring) % 8) % 8), 2).to_bytes((len(bitstring) + 7) // 8, "big") if bitstring else b""
    descriptor = directory
    # One segment, consistent with the full-message grid.
    fixed = struct.pack(">HHHH", config_id, len(source), code_source_len, len(codeword)) + struct.pack(">H", 1)
    erasure_bits = np.packbits(assignment["erasures"].astype(np.uint8), bitorder="big").tobytes()
    records = bytearray()
    for i, j in enumerate(assignment["positions"]):
        if j < 0:
            continue
        loc = locations[int(j)]
        block_index = (loc.y // BLOCK) * (256 // BLOCK) + loc.x // BLOCK
        token = block_index * 4 + loc.arrangement
        records.extend(struct.pack(">Hh", token, int(assignment["displacements"][i])))
    return header + fixed + crc + descriptor + erasure_bits + bytes(records)


def solve_cell_assignment(cover_id: str, message_id: str, source: bytes, compressed: bytes,
                          p: int, q: int, bound: int, cover_row):
    locations, hashes, robust, s_hat = load_codebook(cover_id)
    codeword, blocks = rs_encode(compressed, p)
    allowed = robust.copy()
    if q:
        cap = math.floor((q / 100) * len(codeword))
        unstable = np.flatnonzero(~robust)
        order = sorted(unstable.tolist(), key=lambda j: (-float(s_hat[j]), j))
        if cap:
            allowed[np.asarray(order[:cap], dtype=np.int32)] = True
    cover_id = str(cover_row.source_id)
    if cover_id not in IMAGE_CACHE:
        image_path = IMAGE_ROOT / str(cover_row.relative_path)
        if digest(image_path) != str(cover_row.sha256):
            raise RuntimeError(f"D-b SHA-256 mismatch before validation attack: {cover_id}")
        IMAGE_CACHE[cover_id] = np.asarray(Image.open(image_path).convert("L"), dtype=np.uint8)
    image = IMAGE_CACHE[cover_id]
    attacks = validation_hashes(image, locations, str(cover_row.sha256), message_id)
    assignment = assignment_graph(codeword, hashes, s_hat, robust, allowed, bound, blocks, p, q)
    return locations, hashes, codeword, blocks, assignment, attacks


def run_grid():
    if len(pd.read_csv(OUT / "robustness_summary.csv")) != 100:
        raise RuntimeError("Grid requires complete D-b robustness output")
    covers = pd.read_csv(INPUT / "D_b_images_sha256.csv", keep_default_na=False)
    messages = {k: v for k, v in compressed_messages().items() if len(v[2]) == 100}
    if len(messages) != 12:
        raise RuntimeError(f"Grid expects the 12 frozen 100-byte messages, found {len(messages)}")
    cover_by_id = {str(r.source_id): r for r in covers.itertuples(index=False)}
    cover_ids = [str(r.source_id) for r in covers.itertuples(index=False)]
    params = [(p, q, m, b) for p in (0, 10, 20, 30, 40)
              for q in (0, 2, 5, 10) for m in (1, 2, 3, 5) for b in BOUNDS]
    output = OUT / "grid_trials_12x100.csv.gz"
    done = set()
    if output.exists():
        existing = pd.read_csv(output, usecols=["config_id", "message_id"])
        counts = existing.groupby(["config_id", "message_id"]).size()
        done = {key for key, count in counts.items() if count == 100}
    # Cache assignment/validation data by (cover,message,p,q,B), then reuse over m.
    cache = {}
    by_msg = defaultdict(list)
    for mid, value in messages.items():
        by_msg[mid] = value
    trial_rows = []
    t0 = time.perf_counter()
    for mid, (family, index, source, compressed) in by_msg.items():
        # Same random permutation is reused across all grid cells for this trial.
        candidate_orders = []
        for attempt in range(100):
            rng = np.random.Generator(np.random.PCG64(seed_for("A4/candidate_draws", mid, str(attempt))))
            candidate_orders.append(rng.permutation(cover_ids).tolist())
        for p in (0, 10, 20, 30, 40):
            codewords = {cid: rs_encode(compressed, p)[0] for cid in cover_ids}
            for q in (0, 2, 5, 10):
                for bound in BOUNDS:
                    m_config_ids = {params.index((p, q, m, bound)) for m in (1, 2, 3, 5)}
                    if all((config_id, mid) in done for config_id in m_config_ids):
                        continue
                    solved = {}
                    for ci, cid in enumerate(cover_ids):
                        solved[cid] = solve_cell_assignment(cid, mid, source, compressed, p, q, bound, cover_by_id[cid])
                    for m in (1, 2, 3, 5):
                        config_id = params.index((p, q, m, bound))
                        if (config_id, mid) in done:
                            continue
                        for attempt, order in enumerate(candidate_orders):
                            selected = None
                            for gallery_index, cid in enumerate(order[:m]):
                                if solved[cid][4]["parity_ok"]:
                                    selected = (cid, gallery_index, solved[cid])
                                    break
                            if selected is None:
                                trial_rows.append({"config_id": config_id, "p": p, "q": q, "m": m, "B": bound,
                                                   "message_id": mid, "family": family, "index": index,
                                                   "attempt": attempt, "selected_cover": "", "feasible": 0,
                                                   "success_jpeg": 0, "success_noise": 0, "N_placed": 0,
                                                   "L_src": len(source), "L_c": len(compressed), "L_cw": 0,
                                                   "b_assign": np.nan, "b_total": np.nan, "erasures": np.nan,
                                                   "errors_jpeg": np.nan, "errors_noise": np.nan})
                                continue
                            cid, gallery_index, data = selected
                            locs, hashes, cw, blocks, assn, attacks = data
                            ok_j, e_j, t_j = recover_message(source, compressed, cw, blocks, assn, hashes, attacks["jpeg"], locs, p)
                            ok_n, e_n, t_n = recover_message(source, compressed, cw, blocks, assn, hashes, attacks["noise"], locs, p)
                            fixed_bits = math.ceil(math.log2(1764)) + math.ceil(math.log2(2 * bound + 1))
                            b_assign = (assn["n_placed"] * fixed_bits + len(cw)) / len(source)
                            body = serialize_1quater_body(source, cw, assn, locs, config_id, m, gallery_index, p)
                            b_total = 8 * (41 + len(zlib.compress(body, 9))) / len(source)
                            trial_rows.append({"config_id": config_id, "p": p, "q": q, "m": m, "B": bound,
                                               "message_id": mid, "family": family, "index": index,
                                               "attempt": attempt, "selected_cover": cid, "feasible": 1,
                                               "success_jpeg": int(ok_j), "success_noise": int(ok_n),
                                               "N_placed": assn["n_placed"], "L_src": len(source),
                                               "L_c": len(compressed), "L_cw": len(cw),
                                               "b_assign": b_assign, "b_total": b_total,
                                               "erasures": int(assn["erasures"].sum()),
                                               "errors_jpeg": t_j, "errors_noise": t_n,
                                               "crc32_source": zlib.crc32(source) & 0xffffffff,
                                               "block_erasures": json.dumps(assn["block_erasures"]),
                                               "parity_ok": int(assn["parity_ok"])})
                    # Persist after each (message,p,q,B), so interruption is visible
                    # and does not silently restart from an incomplete matrix.
                    if len(trial_rows) >= 1000:
                        pd.DataFrame(trial_rows).to_csv(output, index=False, compression="gzip", mode="a" if output.exists() else "w", header=not output.exists())
                        trial_rows.clear()
                        print(f"GRID {mid} p={p} q={q} B={bound}: elapsed {time.perf_counter()-t0:.1f}s", flush=True)
    if trial_rows:
        pd.DataFrame(trial_rows).to_csv(output, index=False, compression="gzip", mode="a" if output.exists() else "w", header=not output.exists())
    data = pd.read_csv(output)
    summary = data.groupby(["config_id", "p", "q", "m", "B", "family"], as_index=False).agg(
        communication_success_jpeg=("success_jpeg", "mean"), communication_success_noise=("success_noise", "mean"),
        b_assign=("b_assign", "mean"), b_total=("b_total", "mean"),
        feasibility=("feasible", "mean"), mean_erasures=("erasures", "mean"),
    )
    summary.to_csv(OUT / "grid_summary_by_family.csv", index=False)
    cell = data.groupby(["config_id", "p", "q", "m", "B"], as_index=False).agg(
        success_jpeg=("success_jpeg", "mean"), success_noise=("success_noise", "mean"),
        b_assign=("b_assign", "mean"), b_total=("b_total", "mean"), feasibility=("feasible", "mean"),
    )
    cell["success_combined"] = cell[["success_jpeg", "success_noise"]].min(axis=1)
    cell.to_csv(OUT / "grid_summary.csv", index=False)
    return cell


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("robustness", "A1", "grid", "all"))
    parser.add_argument("--limit", type=int, choices=(5, 100), default=100)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage in ("robustness", "all"):
        run_robustness(args.limit)
    if args.stage in ("A1", "all"):
        run_a1()
    if args.stage in ("grid", "all"):
        run_grid()


if __name__ == "__main__":
    main()
