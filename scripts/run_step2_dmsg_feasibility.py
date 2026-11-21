#!/usr/bin/env python3
"""Exact D-msg feasibility and V1 record-size study on frozen D-b pairs."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import math
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_step1quater as q4
from fham.v1 import (RECORD_R0, RECORD_R1, R1_CAPACITY, build_inner_header,
                     encode_params, pack_record, pack_slot)

OUT = ROOT / "results/step2/detection"
CANDIDATES = OUT / "dmsg_candidates.csv"
COVERS = ROOT / "results/stability_step1/step1quater/manifest/D_b_images_sha256.csv"
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")
SEED = 20261121


def solve(message_hash, part_index, source, cover_id, cache):
    cache_key = (message_hash, part_index, cover_id)
    if cache_key in cache:
        return cache[cache_key]
    compressed = zlib.compress(source, 9)
    codeword, blocks = q4.rs_encode(compressed, 10)
    locations, hashes, robust, stability = q4.load_codebook(cover_id)
    allowed = robust.copy()
    cap = math.floor(0.05 * len(codeword))
    unstable = np.flatnonzero(~robust)
    order = sorted(unstable.tolist(), key=lambda j: (-float(stability[j]), j))
    if cap:
        allowed[np.asarray(order[:cap], dtype=np.int32)] = True
    assignment = q4.assignment_graph(codeword, hashes, stability, robust,
                                    allowed, 4, blocks, 10, 5)
    if not assignment["parity_ok"]:
        result = None
    else:
        slots = []
        for symbol_index, position_index in enumerate(assignment["positions"]):
            if position_index < 0:
                slots.append(pack_slot(erasure=True))
                continue
            loc = locations[int(position_index)]
            token = ((loc.y // q4.BLOCK) * (256 // q4.BLOCK)
                     + loc.x // q4.BLOCK) * 4 + loc.arrangement
            slots.append(pack_slot(token=token,
                                   delta=int(assignment["displacements"][symbol_index])))
        result = {"cover_id": cover_id, "compressed": compressed,
                  "codeword": codeword, "slots": slots,
                  "placed": assignment["n_placed"],
                  "erasures": int(assignment["erasures"].sum()),
                  "residual_sum": assignment["residual_sum"]}
    cache[cache_key] = result
    return result


def serialize_selected(row, parts, segments, catalogue_digest_bytes, message_no):
    compressed = tuple(zlib.compress(part, 9) for part in parts)
    codewords = tuple(segment["codeword"] for segment in segments)
    slots = [slot for segment in segments for slot in segment["slots"]]
    pairs = []
    for part_index, segment in enumerate(segments):
        pairs.append((int(row.cover0_index), int(row.cover1_index),
                      0 if segment["cover_id"] == row.cover0_id else 1))
    digest = hashlib.sha256(b"".join(compressed)).digest()[:16]
    header = dict(height=256, width=256, m=2, p=10, q=5, bound=4,
                  block_size=12, descriptor_id=1, integrity_id=1, source_len=100,
                  compressed_segments=compressed, codeword_segments=codewords,
                  gallery_pairs=tuple(pairs),
                  placed_count=sum(s["placed"] for s in segments),
                  integrity_digest=digest)
    key = hashlib.sha256(f"FHAM-DMSG-KEY:{SEED}:{message_no}".encode()).digest()
    sid = hashlib.sha256(f"FHAM-DMSG-SID:{SEED}:{message_no}".encode()).digest()[:16]
    sizes = {}
    for mode in (RECORD_R0, RECORD_R1):
        capacity = 0 if mode == RECORD_R0 else R1_CAPACITY
        inner = build_inner_header(mode=mode, **header)
        params = encode_params(mode=mode, capacity=capacity, m=2, p=10, q=5,
                               bound=4, block_size=12, descriptor_id=1,
                               integrity_id=1)
        record = pack_record(inner_header=inner, slots=slots, key=key,
                             session_id=sid, sequence=0, mode=mode, epoch=1,
                             catalog_hash=catalogue_digest_bytes, params=params,
                             nonce=hashlib.sha256(f"{message_no}:{mode}".encode()).digest()[:12])
        sizes[f"R{mode}_record_bytes"] = len(record)
        sizes[f"R{mode}_framed_bytes"] = len(record) + 10
    raw = parts[0] + parts[1]
    raw_envelope_bytes = 12 + len(raw) + 16
    compressed_source = zlib.compress(raw, 9)
    compressed_envelope_bytes = 12 + len(compressed_source) + 16
    return {**sizes, "AES_raw_bytes": raw_envelope_bytes,
            "AES_zlib9_bytes": compressed_envelope_bytes,
            "AES_raw_ratio_R0": sizes["R0_framed_bytes"] / raw_envelope_bytes,
            "AES_zlib9_ratio_R0": sizes["R0_framed_bytes"] / compressed_envelope_bytes,
            "AES_raw_ratio_R1": sizes["R1_framed_bytes"] / raw_envelope_bytes,
            "AES_zlib9_ratio_R1": sizes["R1_framed_bytes"] / compressed_envelope_bytes}


def main():
    candidates = pd.read_csv(CANDIDATES, keep_default_na=False)
    catalogue = pd.read_csv(COVERS, keep_default_na=False)
    catalogue_hash = hashlib.sha256(b"").digest()
    from fham.v1 import catalogue_digest
    from PIL import Image
    images = []
    for row in catalogue.itertuples(index=False):
        image_path = q4.IMAGE_ROOT / row.relative_path
        if q4.digest(image_path) != row.sha256:
            raise RuntimeError(f"D-b cover SHA-256 mismatch: {image_path.name}")
        images.append(np.asarray(Image.open(image_path).convert("L"), dtype=np.uint8))
    catalogue_hash = catalogue_digest(images)
    cover_by_index = {int(i): str(r.source_id)
                      for i, r in enumerate(catalogue.itertuples(index=False))}
    assignment_cache = {}
    result_rows = []
    feasible_payloads = []
    selected_count = {family: 0 for family in FAMILIES}
    started = time.perf_counter()
    for candidate in candidates.itertuples(index=False):
        source = (ROOT / candidate.path).read_bytes()
        if hashlib.sha256(source).hexdigest() != candidate.sha256:
            raise RuntimeError(f"D-msg SHA-256 mismatch: {candidate.candidate_id}")
        pair = (str(candidate.cover0_id), str(candidate.cover1_id))
        if pair != (cover_by_index[int(candidate.cover0_index)],
                    cover_by_index[int(candidate.cover1_index)]):
            raise RuntimeError("DPAIR index and canonical D-b cover ID disagree")
        parts = (source[:50], source[50:])
        selected = []
        for part_index, part in enumerate(parts):
            chosen = None
            for cover_id in pair:
                chosen = solve(candidate.sha256, part_index, part, cover_id, assignment_cache)
                if chosen is not None:
                    break
            if chosen is None:
                selected = []
                break
            selected.append(chosen)
        feasible = int(len(selected) == 2)
        record_sizes = {}
        retained = 0
        if feasible:
            record_sizes = serialize_selected(candidate, parts, selected,
                                              catalogue_hash, candidate.candidate_id)
            if selected_count[candidate.family] < 2000:
                selected_count[candidate.family] += 1
                retained = 1
                row = {**candidate._asdict(), "feasible": 1,
                       "selected_cover_segment0": selected[0]["cover_id"],
                       "selected_cover_segment1": selected[1]["cover_id"],
                       "segment0_slots": json.dumps(selected[0]["slots"], separators=(",", ":")),
                       "segment1_slots": json.dumps(selected[1]["slots"], separators=(",", ":")),
                       "segment0_codeword_b64": base64.b64encode(selected[0]["codeword"]).decode("ascii"),
                       "segment1_codeword_b64": base64.b64encode(selected[1]["codeword"]).decode("ascii"),
                       "segment0_compressed_b64": base64.b64encode(selected[0]["compressed"]).decode("ascii"),
                       "segment1_compressed_b64": base64.b64encode(selected[1]["compressed"]).decode("ascii"),
                       **record_sizes}
                feasible_payloads.append(row)
        result_rows.append({"candidate_id": candidate.candidate_id, "family": candidate.family,
                            "sha256": candidate.sha256, "feasible": feasible,
                            "retained_for_D": retained,
                            **record_sizes})
        if len(result_rows) % 100 == 0:
            print(f"D-msg {len(result_rows)}/10000; feasible retained {selected_count}; "
                  f"unique assignment solves {len(assignment_cache)}; "
                  f"elapsed {time.perf_counter()-started:.1f}s", flush=True)
    data = pd.DataFrame(result_rows)
    data.to_csv(OUT / "dmsg_feasibility_all.csv", index=False)
    selected = pd.DataFrame(feasible_payloads)
    selected.to_csv(OUT / "dmsg_selected_2000_per_family.csv.gz", index=False, compression="gzip")
    summary = data.groupby("family", as_index=False).agg(
        candidates=("candidate_id", "count"), feasible=("feasible", "sum"),
        feasibility_rate=("feasible", "mean"), unique_contents=("sha256", "nunique"))
    summary["retained_for_D"] = summary.family.map(selected_count)
    summary.to_csv(OUT / "dmsg_feasibility_summary.csv", index=False)
    metadata = {"candidate_manifest_sha256": hashlib.sha256(CANDIDATES.read_bytes()).hexdigest(),
                "catalogue_digest": catalogue_hash.hex(), "assignment_solves_cached": len(assignment_cache),
                "selected_per_family": selected_count,
                "D_gate": "pass" if all(x == 2000 for x in selected_count.values()) else "stop: fewer than 2000 feasible in at least one family",
                "elapsed_seconds": time.perf_counter() - started}
    (OUT / "dmsg_feasibility_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    print(json.dumps(metadata, indent=2))
    if not all(x == 2000 for x in selected_count.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
