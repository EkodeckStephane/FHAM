#!/usr/bin/env python3
"""Execute the frozen Step 2 security checks on real D-b FHAM assignments."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import struct
import shutil
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from PIL import Image
from reedsolo import RSCodec

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_step1quater as q4
from fham.channel import AuxiliaryChannel, ReplayGuard
from fham.methods import OptimalAssignmentMethod
from fham.v1 import (
    FRAME_CONFIRM,
    FRAME_OFFER,
    FRAME_RECORD,
    RECORD_R0,
    RECORD_R1,
    R1_CAPACITY,
    V1ReplayGuard,
    build_inner_header,
    catalogue_digest,
    create_offer,
    derive_v1_keys,
    encode_params,
    frame,
    pack_record,
    pack_slot,
    parse_inner_header,
    transcript_hash,
    unpack_record,
    unframe,
    validate_cover_binding,
    verify_key_confirmation,
    verify_offer,
    key_confirmation,
    verify_integrity,
)


SEED = 20261121
N_MUTATIONS = 1000
SEGMENTED_CONFIG_ID = 210  # 1quater config 50 offset by the frozen 160-cell A4 grid
OUT = ROOT / "results/step2/security"
INPUT = ROOT / "results/stability_step1/step1quater/manifest"
IMAGE_ROOT = q4.IMAGE_ROOT
TRIALS = q4.OUT / "A4_segmented_trials.csv.gz"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalogue():
    manifest_path = INPUT / "D_b_images_sha256.csv"
    manifest = pd.read_csv(manifest_path, keep_default_na=False)
    if len(manifest) != 100:
        raise RuntimeError("V1 security fixture requires the frozen 100-image D-b catalogue")
    images, id_to_index = [], {}
    for index, row in enumerate(manifest.itertuples(index=False)):
        path = IMAGE_ROOT / row.relative_path
        if sha(path) != row.sha256:
            raise RuntimeError(f"D-b image hash mismatch: {path.name}")
        images.append(np.asarray(Image.open(path).convert("L"), dtype=np.uint8))
        id_to_index[str(row.source_id)] = index
    return manifest, images, id_to_index, sha(manifest_path)


def solve_existing_assignment(message_id, segment_source, segment_compressed, cover_id, cover_row):
    locations, hashes, robust, s_hat = q4.load_codebook(cover_id)
    codeword, blocks = q4.rs_encode(segment_compressed, 10)
    allowed = robust.copy()
    cap = int(np.floor(0.05 * len(codeword)))
    unstable = np.flatnonzero(~robust)
    order = sorted(unstable.tolist(), key=lambda j: (-float(s_hat[j]), j))
    if cap:
        allowed[np.asarray(order[:cap], dtype=np.int32)] = True
    assignment = q4.assignment_graph(
        codeword, hashes, s_hat, robust, allowed, 4, blocks, 10, 5
    )
    if not assignment["parity_ok"]:
        raise RuntimeError(f"selected 1quater location is not feasible: {message_id}/{cover_id}")
    return locations, codeword, assignment


def deterministic_secret(seed: int, label: str, n: int) -> bytes:
    return hashlib.sha256(f"FHAM-step2-test:{seed}:{label}".encode()).digest()[:n]


def build_v1_fixtures():
    manifest, catalogue, id_to_index, manifest_hash = load_catalogue()
    table = pd.read_csv(TRIALS, compression="gzip", low_memory=False)
    table = table[(table.config_id == SEGMENTED_CONFIG_ID) & (table.feasible == 1)]
    rows = {}
    for row in table.itertuples(index=False):
        rows.setdefault(row.message_id, row)
    messages = {k: v for k, v in q4.compressed_messages().items() if len(v[2]) == 100}
    if len(rows) < 10 or len(messages) != 12:
        raise RuntimeError("existing 1quater segmented D-b records are incomplete")
    cat_hash = catalogue_digest(catalogue)
    fixtures = []
    message_ids = sorted(set(rows) & set(messages))
    for index in range(10):
        message_id = message_ids[index % len(message_ids)]
        family, msg_index, source, _ = messages[message_id]
        saved = rows[message_id]
        chosen_ids = str(saved.selected_covers).split(";")
        if len(chosen_ids) != 2:
            raise RuntimeError(f"bad saved segment cover selection for {message_id}")
        cover_indices = [id_to_index[x] for x in chosen_ids]
        source_segments = (source[:50], source[50:])
        compressed_segments = tuple(zlib.compress(part, level=9) for part in source_segments)
        codeword_segments, slots, pairs, placements = [], [], [], []
        for segment_index, (part, compressed, cover_index) in enumerate(
            zip(source_segments, compressed_segments, cover_indices)
        ):
            cover_id = str(manifest.iloc[cover_index].source_id)
            cover_row = next(r for r in manifest.itertuples(index=False)
                             if str(r.source_id) == cover_id)
            locations, codeword, assignment = solve_existing_assignment(
                message_id, part, compressed, cover_id, cover_row
            )
            if sum(assignment["erasures"]) > sum(b["parity"] for b in q4.rs_encode(compressed, 10)[1]):
                raise RuntimeError("invalid RS erasure count in security fixture")
            codeword_segments.append(codeword)
            placements.append(int(assignment["n_placed"]))
            for symbol_index, position_index in enumerate(assignment["positions"]):
                if position_index < 0:
                    slots.append(pack_slot(erasure=True))
                    continue
                location = locations[int(position_index)]
                token = ((location.y // q4.BLOCK) * (256 // q4.BLOCK)
                         + location.x // q4.BLOCK) * 4 + location.arrangement
                slots.append(pack_slot(
                    token=token,
                    delta=int(assignment["displacements"][symbol_index]),
                ))
            # The second catalogue ID is a fixed, non-selected member of the
            # pre-shared catalogue; it is not used to make a new success claim.
            decoy = (cover_index + 1) % len(catalogue)
            pairs.append((cover_index, decoy, 0))
        digest = hashlib.sha256(b"".join(compressed_segments)).digest()[:16]
        header_values = dict(
            height=256, width=256, m=2, p=10, q=5, bound=4, block_size=12,
            descriptor_id=1, integrity_id=1, source_len=100,
            compressed_segments=compressed_segments,
            codeword_segments=tuple(codeword_segments), gallery_pairs=tuple(pairs),
            placed_count=sum(placements), integrity_digest=digest,
        )
        for mode in (RECORD_R0, RECORD_R1):
            capacity = 0 if mode == RECORD_R0 else R1_CAPACITY
            inner = build_inner_header(mode=mode, **header_values)
            params = encode_params(
                mode=mode, capacity=capacity, m=2, p=10, q=5, bound=4,
                block_size=12, descriptor_id=1, integrity_id=1,
            )
            record_no = len(fixtures)
            key = deterministic_secret(SEED, f"key-{record_no}", 32)
            session_id = deterministic_secret(SEED, f"sid-{record_no}", 16)
            nonce = deterministic_secret(SEED, f"nonce-{record_no}", 12)
            record = pack_record(
                inner_header=inner, slots=slots, key=key, session_id=session_id,
                sequence=record_no, mode=mode, epoch=1, catalog_hash=cat_hash,
                params=params, nonce=nonce,
            )
            frame_bytes = frame(FRAME_RECORD, record)
            fixtures.append({
                "record": record, "frame": frame_bytes, "key": key,
                "session_id": session_id, "sequence": record_no,
                "epoch": 1, "catalogue_hash": cat_hash, "params": params,
                "inner": inner, "header": parse_inner_header(inner),
                "slots": list(slots),
                "message_id": message_id, "family": family,
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "cover_indices": cover_indices, "cover_ids": chosen_ids,
                "header_values": header_values,
                "compressed_segments": compressed_segments,
                "codeword_segments": tuple(codeword_segments),
                "mode": mode,
            })
    manifest_rows = []
    for i, fixture in enumerate(fixtures):
        manifest_rows.append({
            "record_index": i, "message_id": fixture["message_id"],
            "family": fixture["family"], "mode": fixture["mode"],
            "source_sha256": fixture["source_sha256"],
            "selected_cover_ids": ";".join(fixture["cover_ids"]),
            "record_bytes": len(fixture["record"]),
            "frame_bytes": len(fixture["frame"]),
            "record_sha256": hashlib.sha256(fixture["record"]).hexdigest(),
        })
    pd.DataFrame(manifest_rows).to_csv(OUT / "v1_record_manifest.csv", index=False)
    return fixtures, catalogue, manifest_hash


def expect_rejection(operation):
    try:
        operation()
        return False, "accepted"
    except Exception as exc:  # precisely record the implementation's rejection path
        return True, type(exc).__name__ + ": " + str(exc)


def mark_expected_mechanism(data, mapping):
    allowed = {name: set(kinds) for name, kinds in mapping.items()}
    data["exception_type"] = data["reason"].map(lambda value: value.split(":", 1)[0])
    data["mechanism_match"] = data.apply(
        lambda row: int(row["exception_type"] in allowed.get(row["class"], set())), axis=1
    )
    return data


def run_v1_mutation_suite(fixtures, catalogue):
    rng = random.Random(SEED)
    rows = []
    catalog_count = len(catalogue)
    wrong_catalogue_hash = catalogue_digest(list(reversed(catalogue)))
    wrong_params = encode_params(
        mode=RECORD_R1, capacity=R1_CAPACITY, m=2, p=10, q=5,
        bound=4, block_size=12, descriptor_id=2,
    )
    id0 = Ed25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "id0", 32))
    id1 = Ed25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "id1", 32))
    eph0 = X25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "eph0", 32))
    sid = deterministic_secret(SEED, "offer-sid", 16)
    valid_offer = create_offer(identity_private=id0, ephemeral_private=eph0,
                               peer_identity=id1.public_key(), role=0,
                               session_id=sid, epoch=1)
    cover0 = catalogue[0].copy()
    cover1 = catalogue[1].copy()
    cover1[0, 0] ^= 1

    classes = ("frame_header", "header", "nonce", "ciphertext", "tag", "truncation", "extension",
               "session", "sequence", "catalogue", "parameters", "offer_signature",
               "selected_cover")
    for mutation_class in classes:
        for trial in range(N_MUTATIONS):
            fixture = fixtures[trial % len(fixtures)]
            record = fixture["record"]
            context = dict(
                key=fixture["key"], expected_session_id=fixture["session_id"],
                expected_sequence=fixture["sequence"], expected_epoch=fixture["epoch"],
                catalog_hash=fixture["catalogue_hash"], params=fixture["params"],
            )
            payload_context = context.copy()
            if mutation_class == "frame_header":
                wire = bytearray(fixture["frame"])
                bit = rng.randrange(10 * 8)
                wire[bit // 8] ^= 1 << (bit % 8)
                operation = lambda wire=bytes(wire), c=context: _decode_wire(wire, c)
            elif mutation_class in ("header", "nonce", "ciphertext", "tag", "truncation", "extension",
                                  "session", "sequence"):
                mutable = bytearray(record)
                if mutation_class == "header":
                    bit = rng.choice(list(range(0, 48)) + list(range(42 * 8, 44 * 8)))
                    mutable[bit // 8] ^= 1 << (bit % 8)
                elif mutation_class == "nonce":
                    bit = rng.randrange(30 * 8, 42 * 8)
                    mutable[bit // 8] ^= 1 << (bit % 8)
                elif mutation_class == "ciphertext":
                    bit = rng.randrange(44 * 8, (len(record) - 16) * 8)
                    mutable[bit // 8] ^= 1 << (bit % 8)
                elif mutation_class == "tag":
                    bit = rng.randrange((len(record) - 16) * 8, len(record) * 8)
                    mutable[bit // 8] ^= 1 << (bit % 8)
                elif mutation_class == "truncation":
                    mutable = mutable[:-rng.randint(1, 8)]
                elif mutation_class == "extension":
                    mutable.extend(rng.randbytes(rng.randint(1, 8)))
                elif mutation_class == "session":
                    bit = rng.randrange(6 * 8, 22 * 8)
                    mutable[bit // 8] ^= 1 << (bit % 8)
                elif mutation_class == "sequence":
                    bit = rng.randrange(22 * 8, 30 * 8)
                    mutable[bit // 8] ^= 1 << (bit % 8)
                target = bytes(mutable)
                operation = lambda target=target, context=context: unpack_record(target, **context)
            elif mutation_class == "catalogue":
                payload_context["catalog_hash"] = wrong_catalogue_hash
                operation = lambda record=record, c=payload_context: unpack_record(record, **c)
            elif mutation_class == "parameters":
                payload_context["params"] = wrong_params
                operation = lambda record=record, c=payload_context: unpack_record(record, **c)
            elif mutation_class == "offer_signature":
                altered = bytearray(valid_offer)
                bit = rng.randrange(53 * 8, 117 * 8)
                altered[bit // 8] ^= 1 << (bit % 8)
                operation = lambda altered=bytes(altered): verify_offer(
                    altered, sender_identity=id0.public_key(),
                    recipient_identity=id1.public_key(), expected_role=0,
                    expected_session_id=sid, expected_epoch=1,
                )
            else:
                cover = cover1.copy()
                cover[rng.randrange(cover.shape[0]), rng.randrange(cover.shape[1])] ^= 1
                selected = fixture["header"].segments[0]
                selected_image = catalogue[selected.cover0 if selected.chosen == 0 else selected.cover1]
                # Ensure a changed pixel is used even if the sampled pixel happens to
                # be restored to the same value by uint8 wraparound.
                cover = selected_image.copy()
                cover[0, 0] ^= 1
                operation = lambda f=fixture, c=cover: validate_cover_binding(
                    f["header"], catalogue, [c, catalogue[
                        f["header"].segments[1].cover0 if f["header"].segments[1].chosen == 0
                        else f["header"].segments[1].cover1]],
                )
            rejected, reason = expect_rejection(operation)
            rows.append({"format": "V1", "class": mutation_class,
                         "trial": trial, "rejected": int(rejected), "reason": reason})

    # State/replay classes are exercised against persistent SQLite state.
    for mutation_class in ("duplicate_replay", "out_of_order", "sequence_skip", "unknown_session", "stale_epoch"):
        for trial in range(N_MUTATIONS):
            with tempfile.TemporaryDirectory() as temp:
                epoch = [1]
                guard = V1ReplayGuard(Path(temp) / "rx.sqlite", lambda: epoch[0])
                session = hashlib.sha256(f"{SEED}:{mutation_class}:{trial}".encode()).digest()[:16]
                guard.register_session(session, 1)
                if mutation_class == "duplicate_replay":
                    guard.accept(session, 0, 1)
                    operation = lambda g=guard, s=session: g.accept(s, 0, 1)
                elif mutation_class == "out_of_order":
                    operation = lambda g=guard, s=session: g.accept(s, 1, 1)
                elif mutation_class == "sequence_skip":
                    operation = lambda g=guard, s=session: g.accept(s, 2, 1)
                elif mutation_class == "unknown_session":
                    operation = lambda g=guard, s=session: g.accept(bytes(16), 0, 1)
                else:
                    epoch[0] = 2
                    operation = lambda g=guard, s=session: g.accept(s, 0, 1)
                rejected, reason = expect_rejection(operation)
                rows.append({"format": "V1", "class": mutation_class,
                             "trial": trial, "rejected": int(rejected), "reason": reason})
    result = mark_expected_mechanism(pd.DataFrame(rows), {
        "frame_header": ("ValueError",),
        "header": ("ValueError", "InvalidTag"),
        "nonce": ("InvalidTag",), "ciphertext": ("InvalidTag",),
        "tag": ("InvalidTag",), "truncation": ("ValueError", "InvalidTag"),
        "extension": ("ValueError", "InvalidTag"), "session": ("ValueError",),
        "sequence": ("ValueError",), "catalogue": ("InvalidTag",),
        "parameters": ("InvalidTag",), "offer_signature": ("ValueError",),
        "selected_cover": ("ValueError",), "duplicate_replay": ("ValueError",),
        "out_of_order": ("ValueError",), "sequence_skip": ("ValueError",),
        "unknown_session": ("ValueError",), "stale_epoch": ("ValueError",),
    })
    result.to_csv(OUT / "v1_mutation_trials.csv", index=False)
    summary = result.groupby(["format", "class"], as_index=False).agg(
        trials=("trial", "count"), accepted=("rejected", lambda x: int((x == 0).sum())),
        rejected=("rejected", "sum"), mechanism_mismatches=("mechanism_match", lambda x: int((x == 0).sum())),
    )
    summary.to_csv(OUT / "v1_mutation_summary.csv", index=False)
    return summary


def _decode_wire(wire, context):
    kind, payload = unframe(wire)
    if kind != FRAME_RECORD:
        raise ValueError("wrong V1 application frame type")
    return unpack_record(payload, **context)


def run_exhaustive_bit_sweep(fixtures):
    rows = []
    total = rejected = 0
    for index, fixture in enumerate(fixtures):
        record = fixture["record"]
        context = dict(
            key=fixture["key"], expected_session_id=fixture["session_id"],
            expected_sequence=fixture["sequence"], expected_epoch=fixture["epoch"],
            catalog_hash=fixture["catalogue_hash"], params=fixture["params"],
        )
        accepted = 0
        wire = fixture["frame"]
        for bit in range(len(wire) * 8):
            mutated = bytearray(wire)
            mutated[bit // 8] ^= 1 << (bit % 8)
            did_reject, _ = expect_rejection(
                lambda value=bytes(mutated), ctx=context: _decode_wire(value, ctx)
            )
            accepted += int(not did_reject)
        count = len(wire) * 8
        total += count
        rejected += count - accepted
        rows.append({"record_index": index, "mode": fixture["mode"],
                     "record_bytes": len(record), "bits_tested": count,
                     "accepted_mutations": accepted,
                     "rejected_mutations": count - accepted})
    pd.DataFrame(rows).to_csv(OUT / "v1_exhaustive_bit_sweep.csv", index=False)
    return {"records": len(fixtures), "bits_tested": total,
            "rejected_mutations": rejected, "accepted_mutations": total - rejected}


def run_integrity_size_comparison(fixtures):
    rows = []
    for index, fixture in enumerate(fixtures):
        h = dict(fixture["header_values"])
        compressed = b"".join(fixture["compressed_segments"])
        i0_digest = (zlib.crc32(compressed) & 0xFFFFFFFF).to_bytes(4, "big") + bytes(12)
        h["integrity_id"] = 0
        h["integrity_digest"] = i0_digest
        inner_i0 = build_inner_header(mode=fixture["mode"], **h)
        inner_i1 = fixture["inner"]
        slots = fixture["slots"]
        slot_bytes = struct.pack(f"!{len(slots)}H", *slots)
        if fixture["mode"] == RECORD_R0:
            payload_i0 = zlib.compress(inner_i0 + slot_bytes, level=9)
            payload_i1 = zlib.compress(inner_i1 + slot_bytes, level=9)
        else:
            fill = [(1 << 15)] * (R1_CAPACITY - len(slots))
            fixed = slot_bytes + struct.pack(f"!{len(fill)}H", *fill)
            payload_i0 = inner_i0 + fixed
            payload_i1 = inner_i1 + fixed
        record_i0 = 44 + len(payload_i0) + 16
        record_i1 = 44 + len(payload_i1) + 16
        rows.append({
            "record_index": index, "mode": fixture["mode"],
            "message_id": fixture["message_id"],
            "i0_body_bytes": len(payload_i0), "i1_body_bytes": len(payload_i1),
            "i0_record_bytes": record_i0, "i1_record_bytes": record_i1,
            "i0_framed_bytes": record_i0 + 10, "i1_framed_bytes": record_i1 + 10,
            "i0_minus_i1_record_bytes": record_i0 - record_i1,
            "crc32": f"{int.from_bytes(i0_digest[:4], 'big'):08x}",
            "sha256_128": inner_i1[-16:].hex(),
        })
    data = pd.DataFrame(rows)
    data.to_csv(OUT / "v1_i0_i1_size_comparison.csv", index=False)
    summary = data.groupby("mode", as_index=False).agg(
        records=("record_index", "count"),
        mean_i0_record_bytes=("i0_record_bytes", "mean"),
        mean_i1_record_bytes=("i1_record_bytes", "mean"),
        mean_i0_minus_i1=("i0_minus_i1_record_bytes", "mean"),
        max_abs_delta=("i0_minus_i1_record_bytes", lambda x: int(x.abs().max())),
    )
    summary.to_csv(OUT / "v1_i0_i1_size_summary.csv", index=False)
    return {
        "by_mode": summary.to_dict(orient="records"),
        "I1_false_accept_upper_bound_K_2000": 2000 / (2**128),
        "I0_random_collision_upper_bound_K_54043": 54043 / (2**32),
        "I0_warning": "CRC-32 is not adversarial message authentication",
    }


def run_message_integrity_trials(fixtures):
    rng = random.Random(SEED + 113)
    rows = []
    for fixture in fixtures:
        original = fixture["compressed_segments"]
        expected = fixture["header"].integrity_digest
        for trial in range(N_MUTATIONS):
            part = rng.randrange(2)
            altered_part = bytearray(original[part])
            altered_part[rng.randrange(len(altered_part))] ^= 1 << rng.randrange(8)
            altered = list(original)
            altered[part] = bytes(altered_part)
            rejected = False
            try:
                verify_integrity(tuple(altered), expected)
            except ValueError:
                rejected = True
            rows.append({"record_index": fixture["sequence"], "mode": fixture["mode"],
                         "trial": trial, "rejected": int(rejected)})
    data = pd.DataFrame(rows)
    data.to_csv(OUT / "v1_message_integrity_trials.csv", index=False)
    summary = data.groupby("mode", as_index=False).agg(
        trials=("trial", "count"), rejected=("rejected", "sum"),
        accepted=("rejected", lambda x: int((x == 0).sum())),
    )
    summary.to_csv(OUT / "v1_message_integrity_summary.csv", index=False)
    return summary


def run_v0_comparator(catalogue):
    """Replay legacy V0 checks only for fields it actually represents."""
    image = catalogue[0]
    method = OptimalAssignmentMethod(block_size=12)
    method.build_lookup_table(image)
    symbols = sorted(value for value in method.lookup_table if 32 <= value <= 126)
    if not symbols:
        raise RuntimeError("could not build one-symbol legacy V0 assignment")
    assignment = method.embed(chr(symbols[0]), image)
    if assignment is None:
        raise RuntimeError("legacy V0 one-symbol assignment failed")
    key = deterministic_secret(SEED, "v0-key", 32)
    session_id = deterministic_secret(SEED, "v0-session", 16)
    base = AuxiliaryChannel.protect_session(
        assignment, key, image, session_id, sequence=0, record_capacity=1
    )
    rng = random.Random(SEED + 100)
    classes = ("header", "nonce", "ciphertext", "tag", "truncation", "extension",
               "session", "sequence", "cover_substitution", "replay", "offer_signature")
    rows = []
    header_n = AuxiliaryChannel.SESSION_ENVELOPE_HEADER.size
    for cls in classes:
        for trial in range(N_MUTATIONS):
            guard = ReplayGuard()
            guard.register_session(session_id)
            envelope = base
            cover = image
            if cls == "replay":
                AuxiliaryChannel.recover_session(base, key, image, guard)
                operation = lambda g=guard: AuxiliaryChannel.recover_session(base, key, image, g)
            elif cls == "cover_substitution":
                cover = catalogue[1]
                operation = lambda c=cover, g=guard: AuxiliaryChannel.recover_session(base, key, c, g)
            elif cls == "offer_signature":
                identity_a = Ed25519PrivateKey.from_private_bytes(
                    deterministic_secret(SEED, "v0-id-a", 32))
                identity_b = Ed25519PrivateKey.from_private_bytes(
                    deterministic_secret(SEED, "v0-id-b", 32))
                ephemeral = X25519PrivateKey.from_private_bytes(
                    deterministic_secret(SEED, "v0-eph", 32))
                offer, signature = AuxiliaryChannel.sign_ephemeral(
                    identity_a, ephemeral, identity_b.public_key(), session_id
                )
                signature = bytearray(signature)
                signature[rng.randrange(len(signature))] ^= 1
                operation = lambda o=offer, s=bytes(signature): AuxiliaryChannel.verify_ephemeral(
                    identity_a.public_key(), identity_b.public_key(), o, s, session_id
                )
            else:
                changed = bytearray(base)
                if cls == "header":
                    bit = rng.choice(list(range(0, 40)) + list(range(41 * 8, header_n * 8)))
                    changed[bit // 8] ^= 1 << (bit % 8)
                elif cls == "nonce":
                    bit = rng.randrange(29 * 8, 41 * 8)
                    changed[bit // 8] ^= 1 << (bit % 8)
                elif cls == "ciphertext":
                    bit = rng.randrange(header_n * 8, (len(base) - 16) * 8)
                    changed[bit // 8] ^= 1 << (bit % 8)
                elif cls == "tag":
                    bit = rng.randrange((len(base) - 16) * 8, len(base) * 8)
                    changed[bit // 8] ^= 1 << (bit % 8)
                elif cls == "truncation":
                    changed = changed[:-rng.randint(1, 8)]
                elif cls == "extension":
                    changed.extend(rng.randbytes(rng.randint(1, 8)))
                elif cls == "session":
                    bit = rng.randrange(5 * 8, 21 * 8)
                    changed[bit // 8] ^= 1 << (bit % 8)
                elif cls == "sequence":
                    bit = rng.randrange(21 * 8, 29 * 8)
                    changed[bit // 8] ^= 1 << (bit % 8)
                envelope = bytes(changed)
                operation = lambda e=envelope, g=guard: AuxiliaryChannel.recover_session(
                    e, key, image, g
                )
            rejected, reason = expect_rejection(operation)
            rows.append({"format": "V0", "class": cls, "trial": trial,
                         "rejected": int(rejected), "reason": reason})
    result = mark_expected_mechanism(pd.DataFrame(rows), {
        "header": ("ValueError", "InvalidTag"), "nonce": ("InvalidTag",),
        "ciphertext": ("InvalidTag",), "tag": ("InvalidTag",),
        "truncation": ("ValueError", "InvalidTag"), "extension": ("ValueError", "InvalidTag"),
        "session": ("InvalidTag", "ValueError"), "sequence": ("InvalidTag", "ValueError"),
        "cover_substitution": ("InvalidTag",), "replay": ("ValueError",),
        "offer_signature": ("ValueError",),
    })
    result.to_csv(OUT / "v0_mutation_trials.csv", index=False)
    summary = result.groupby(["format", "class"], as_index=False).agg(
        trials=("trial", "count"), accepted=("rejected", lambda x: int((x == 0).sum())),
        rejected=("rejected", "sum"), mechanism_mismatches=("mechanism_match", lambda x: int((x == 0).sum())),
    )
    summary.to_csv(OUT / "v0_mutation_summary.csv", index=False)
    return summary


def run_handshake_and_compromise(fixtures):
    sid = deterministic_secret(SEED, "handshake-sid", 16)
    epoch = 1
    id0 = Ed25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "handshake-id0", 32))
    id1 = Ed25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "handshake-id1", 32))
    eph0 = X25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "handshake-eph0", 32))
    eph1 = X25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "handshake-eph1", 32))
    offer0 = create_offer(identity_private=id0, ephemeral_private=eph0,
                          peer_identity=id1.public_key(), role=0,
                          session_id=sid, epoch=epoch)
    offer1 = create_offer(identity_private=id1, ephemeral_private=eph1,
                          peer_identity=id0.public_key(), role=1,
                          session_id=sid, epoch=epoch)
    pub0 = verify_offer(offer0, sender_identity=id0.public_key(),
                        recipient_identity=id1.public_key(), expected_role=0,
                        expected_session_id=sid, expected_epoch=epoch)
    pub1 = verify_offer(offer1, sender_identity=id1.public_key(),
                        recipient_identity=id0.public_key(), expected_role=1,
                        expected_session_id=sid, expected_epoch=epoch)
    catalog_hash = hashlib.sha256(b"test ordered catalogue").digest()
    params = encode_params(mode=RECORD_R1, capacity=R1_CAPACITY, m=2, p=10,
                           q=5, bound=4, block_size=12, descriptor_id=1)
    transcript = transcript_hash(offer0, offer1, catalog_hash=catalog_hash,
                                 epoch=epoch, params=params)
    keys0 = derive_v1_keys(eph0, pub1, sid, transcript)
    keys1 = derive_v1_keys(eph1, pub0, sid, transcript)
    if keys0 != keys1:
        raise RuntimeError("honest session key agreement failed")
    verify_key_confirmation(keys0, 0, transcript, key_confirmation(keys1, 0, transcript))
    verify_key_confirmation(keys0, 1, transcript, key_confirmation(keys1, 1, transcript))
    offer_frames = (frame(FRAME_OFFER, offer0), frame(FRAME_OFFER, offer1))
    confirm_frames = (
        frame(FRAME_CONFIRM, key_confirmation(keys0, 0, transcript)),
        frame(FRAME_CONFIRM, key_confirmation(keys0, 1, transcript)),
    )
    handshake_bytes = sum(map(len, offer_frames + confirm_frames))
    offer_tamper = bytearray(offer0)
    offer_tamper[59] ^= 1
    signature_rejected = False
    try:
        verify_offer(bytes(offer_tamper), sender_identity=id0.public_key(),
                     recipient_identity=id1.public_key(), expected_role=0,
                     expected_session_id=sid, expected_epoch=epoch)
    except ValueError:
        signature_rejected = True
    # An attacker with both long-term identity keys but without either ephemeral
    # private value derives a different shared secret and cannot open a record.
    attacker_eph = X25519PrivateKey.from_private_bytes(deterministic_secret(SEED, "attacker-eph", 32))
    attacker_keys = derive_v1_keys(attacker_eph, pub1, sid, transcript)
    fixture = fixtures[0]
    captured = pack_record(
        inner_header=fixture["inner"], slots=fixture["slots"],
        key=keys0.aead_role0, session_id=sid, sequence=0,
        mode=fixture["mode"], epoch=epoch,
        catalog_hash=fixture["catalogue_hash"], params=fixture["params"],
        nonce=deterministic_secret(SEED, "pfs-record-nonce", 12),
    )
    identity_leak_decryption_rejected = False
    try:
        unpack_record(
            captured, key=attacker_keys.aead_role0, expected_session_id=sid,
            expected_sequence=0, expected_epoch=epoch,
            catalog_hash=fixture["catalogue_hash"], params=fixture["params"],
        )
    except Exception:
        identity_leak_decryption_rejected = True
    sid2 = deterministic_secret(SEED, "handshake-sid-two", 16)
    transcript2 = hashlib.sha256(transcript + b"second independent session").digest()
    keys_second_session = derive_v1_keys(eph0, pub1, sid2, transcript2)
    session_independent = keys0.aead_role0 != keys_second_session.aead_role0
    # The stolen A identity can authenticate as A, but cannot sign as pinned B.
    forged_as_b = create_offer(identity_private=id0, ephemeral_private=attacker_eph,
                               peer_identity=id0.public_key(), role=1,
                               session_id=sid, epoch=epoch)
    impersonation_rejected = False
    try:
        verify_offer(forged_as_b, sender_identity=id1.public_key(),
                     recipient_identity=id0.public_key(), expected_role=1,
                     expected_session_id=sid, expected_epoch=epoch)
    except ValueError:
        impersonation_rejected = True
    return {
        "honest_key_agreement": keys0 == keys1,
        "directional_keys_distinct": len({keys0.aead_role0, keys0.aead_role1,
                                            keys0.confirm_role0, keys0.confirm_role1}) == 4,
        "both_key_confirmations_pass": True,
        "altered_offer_signature_rejected": signature_rejected,
        "identity_key_leak_does_not_decrypt_captured_record": identity_leak_decryption_rejected,
        "session_keys_are_context_bound": session_independent,
        "stolen_A_cannot_impersonate_pinned_B": impersonation_rejected,
        "offer_frame_bytes": [len(x) for x in offer_frames],
        "confirmation_frame_bytes": [len(x) for x in confirm_frames],
        "handshake_framed_bytes": handshake_bytes,
        "ephemeral_memory_zeroization": "not claimed; Python cannot guarantee physical erasure",
    }


def run_persistent_replay_restart_and_rollback_trials():
    rows = []
    for trial in range(N_MUTATIONS):
        with tempfile.TemporaryDirectory() as temp:
            epoch = [1]
            path = Path(temp) / "receiver.sqlite"
            sid = hashlib.sha256(f"restart:{SEED}:{trial}".encode()).digest()[:16]
            guard = V1ReplayGuard(path, lambda: epoch[0])
            guard.register_session(sid, 1)
            guard.accept(sid, 0, 1)
            snapshot = Path(temp) / "snapshot.sqlite"
            shutil.copy2(path, snapshot)
            reopened = V1ReplayGuard(path, lambda: epoch[0])
            accepted_next_after_restart = True
            try:
                reopened.accept(sid, 1, 1)
            except ValueError:
                accepted_next_after_restart = False
            epoch[0] = 2
            restored = V1ReplayGuard(snapshot, lambda: epoch[0])
            rollback_rejected, reason = expect_rejection(lambda: restored.accept(sid, 1, 1))
            rows.append({"trial": trial,
                         "restart_next_sequence_accepted": int(accepted_next_after_restart),
                         "restored_old_snapshot_rejected": int(rollback_rejected),
                         "rollback_reason": reason})
    data = pd.DataFrame(rows)
    data.to_csv(OUT / "v1_replay_restart_rollback.csv", index=False)
    return {
        "trials": N_MUTATIONS,
        "restart_sequence_continuity_failures": int((data.restart_next_sequence_accepted == 0).sum()),
        "old_snapshot_acceptances": int((data.restored_old_snapshot_rejected == 0).sum()),
        "trusted_epoch_provider": "external monotone test state; SQLite rollback alone is not prevented",
    }


def main():
    global N_MUTATIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutations", type=int, default=N_MUTATIONS)
    parser.add_argument("--skip-v0", action="store_true")
    args = parser.parse_args()
    N_MUTATIONS = args.mutations
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures, catalogue, image_manifest_sha = build_v1_fixtures()
    mutation_summary = run_v1_mutation_suite(fixtures, catalogue)
    bit_sweep = run_exhaustive_bit_sweep(fixtures)
    integrity_size = run_integrity_size_comparison(fixtures)
    message_integrity = run_message_integrity_trials(fixtures)
    v0_summary = run_v0_comparator(catalogue)
    key_results = run_handshake_and_compromise(fixtures)
    replay_persistence = run_persistent_replay_restart_and_rollback_trials()
    output = {
        "protocol_commit": "a4775ee",
        "seed": SEED,
        "mutations_per_class": N_MUTATIONS,
        "format": "FHAM V1, R0/R1, D-b 1quater assignment fixtures",
        "D_b_image_manifest_sha256": image_manifest_sha,
        "D_b_catalogue_sha256": fixtures[0]["catalogue_hash"].hex(),
        "mutation_summary": mutation_summary.to_dict(orient="records"),
        "V0_mutation_summary": v0_summary.to_dict(orient="records"),
        "exhaustive_bit_sweep": bit_sweep,
        "I0_I1_size_comparison": integrity_size,
        "message_integrity_trials": message_integrity.to_dict(orient="records"),
        "handshake_and_compromise": key_results,
        "replay_restart_and_rollback": replay_persistence,
        "V0_comparison": "completed for legacy-compatible checks; gallery-order and V1-parameter checks are not applicable to V0",
    }
    (OUT / "security_summary.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
