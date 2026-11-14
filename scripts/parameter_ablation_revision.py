"""Reproducible revision ablation for FHAM payload and codebook parameters.

The first stage isolates descriptor, block-size, displacement-bound, message
family, and optional pre-assignment compression effects on the controlled
corpus. A second invocation can use --corpus stress for out-of-domain checks.
Raw trial rows and a grouped summary are written under results/revision_ablation.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import json
import platform
import random
import struct
import sys
import time
import zlib
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fham.descriptors import DESCRIPTORS  # noqa: E402
from fham.methods import BoundedAssignmentMethod  # noqa: E402


DESCRIPTORS_TO_TEST = ("spectral", "dct_ordinal", "wavelet_gradient")
BLOCK_SIZES = (12, 18, 24, 30, 36, 48)
BOUNDS = (1, 2, 4, 8)
FAMILIES = ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated")
LENGTHS = (100, 200)


def load_messages(length: int, trials: int) -> dict[str, list[bytes]]:
    messages: dict[str, list[bytes]] = {}
    for family in FAMILIES:
        paths = sorted((ROOT / "dataset" / "messages" / family).glob(f"{family}_{length}_*.bin"))
        if not paths:
            raise FileNotFoundError(f"No prepared messages for {family}, length={length}")
        messages[family] = [path.read_bytes() for path in paths[:trials]]
    return messages


def codebook_counts(image: np.ndarray, descriptor: str, block_size: int) -> Counter[int]:
    count: Counter[int] = Counter()
    height, width = image.shape[:2]
    fn = DESCRIPTORS[descriptor]
    for y in range(0, height - block_size + 1, block_size):
        for x in range(0, width - block_size + 1, block_size):
            count.update(fn(image[y:y + block_size, x:x + block_size]))
    return count


def minimum_bound(demands: Counter[int], capacities: Counter[int]) -> int | None:
    if sum(demands.values()) > sum(capacities.values()):
        return None

    def interval_feasible(bound: int) -> bool:
        """Exact capacitated matching for the model's 1-D interval graph.

        Each demanded value v can use exactly the codebook values in
        [v-bound, v+bound]. Processing demand values in increasing order and
        consuming the smallest available eligible codebook value is the
        earliest-deadline interval-matching greedy; its exchange argument
        preserves a feasible matching whenever one exists.
        """
        values = sorted(capacities)
        remaining = [capacities[value] for value in values]
        cursor = 0
        for target, quantity in sorted(demands.items()):
            cursor = max(cursor, bisect_left(values, target - bound, cursor))
            need = quantity
            while need:
                if cursor == len(values) or values[cursor] > target + bound:
                    return False
                used = min(need, remaining[cursor])
                need -= used
                remaining[cursor] -= used
                if remaining[cursor] == 0:
                    cursor += 1
        return True

    low, high = 0, 255
    while low < high:
        mid = (low + high) // 2
        if interval_feasible(mid):
            high = mid
        else:
            low = mid + 1
    return low if interval_feasible(low) else None


def make_candidate(payload: bytes, compression: str) -> bytes:
    if compression == "none":
        return payload
    if compression == "zlib9":
        return zlib.compress(payload, level=9)
    raise ValueError(compression)


def packed_assignment_payload(assignment, bound: int) -> bytes:
    """Prototype a fixed-width lossless code for selected location/residual pairs."""
    blocks_per_row = assignment.image_shape[1] // assignment.block_size
    block_rows = assignment.image_shape[0] // assignment.block_size
    token_count = blocks_per_row * block_rows * 4
    token_bits = (token_count - 1).bit_length()
    residual_bits = (2 * bound).bit_length()
    header = struct.pack(
        ">4sBHHHI", b"FHMP", 1, assignment.image_shape[0],
        assignment.image_shape[1], assignment.block_size,
        len(assignment.locations),
    )
    stream = 0
    width = 0
    for location, residual in zip(assignment.locations, assignment.displacements):
        block_index = (location.y // assignment.block_size) * blocks_per_row + location.x // assignment.block_size
        token = block_index * 4 + location.arrangement
        residual_code = residual + bound
        if not 0 <= residual_code <= 2 * bound:
            raise ValueError("residual falls outside the selected bound")
        stream = (stream << token_bits) | token
        width += token_bits
        stream = (stream << residual_bits) | residual_code
        width += residual_bits
    packed = stream.to_bytes((width + 7) // 8, "big")
    return header + packed


def unpacked_pairs(payload: bytes, bound: int) -> tuple[list[int], list[int]]:
    magic, version, height, width, block_size, count = struct.unpack_from(">4sBHHHI", payload)
    if magic != b"FHMP" or version != 1:
        raise ValueError("unsupported packed assignment")
    blocks_per_row = width // block_size
    token_count = (height // block_size) * blocks_per_row * 4
    token_bits = (token_count - 1).bit_length()
    residual_bits = (2 * bound).bit_length()
    total_bits = count * (token_bits + residual_bits)
    value = int.from_bytes(payload[15:], "big")
    cursor = len(payload[15:]) * 8 - total_bits
    tokens, residuals = [], []
    for _ in range(count):
        cursor += token_bits
        tokens.append((value >> (len(payload[15:]) * 8 - cursor)) & ((1 << token_bits) - 1))
        cursor += residual_bits
        residuals.append(((value >> (len(payload[15:]) * 8 - cursor)) & ((1 << residual_bits) - 1)) - bound)
    return tokens, residuals


def assignment_channel_sizes(
    image: np.ndarray, config: dict, payload: bytes, direct_payload: bytes
) -> dict[str, int | float | None]:
    method = BoundedAssignmentMethod(
        int(config["bound"]), block_size=int(config["block_size"]), descriptor=str(config["descriptor"])
    )
    method.lookup_table = config["lookup_table"]
    method.image_shape = tuple(image.shape)
    message = payload.decode("latin-1")
    assignment = method.embed(message, image)
    if assignment is None:
        return {"feasible": 0, "record_bytes": None, "compact_bytes": None, "direct_bytes": None}
    recovered_coded = method.extract(assignment, image).encode("latin-1")
    if recovered_coded != payload:
        raise ValueError("identity-channel FHAM round-trip mismatch")
    recovered_plain = zlib.decompress(recovered_coded) if recovered_coded != direct_payload else recovered_coded
    if recovered_plain != direct_payload:
        raise ValueError("preprocessed FHAM payload does not decode to its source message")
    from fham.channel import AuxiliaryChannel

    raw = AuxiliaryChannel.serialize(assignment)
    compressed = AuxiliaryChannel.protect(assignment, b"\x11" * 32)
    packed = packed_assignment_payload(assignment, int(config["bound"]))
    expected_tokens = []
    blocks_per_row = assignment.image_shape[1] // assignment.block_size
    for location in assignment.locations:
        block_index = (location.y // assignment.block_size) * blocks_per_row + location.x // assignment.block_size
        expected_tokens.append(block_index * 4 + location.arrangement)
    packed_tokens, packed_residuals = unpacked_pairs(packed, int(config["bound"]))
    if packed_tokens != expected_tokens or packed_residuals != assignment.displacements:
        raise ValueError("packed assignment round-trip mismatch")
    packed_compressed = zlib.compress(packed, level=9)
    packed_header = struct.pack(">4sBII", b"FHMP", 1, len(packed), len(packed_compressed))
    nonce = b"\x22" * 12
    aad = b"FHAM-PACKED-ASSIGNMENT-v1" + packed_header
    packed_ciphertext = AESGCM(b"\x33" * 32).encrypt(nonce, packed_compressed, aad)
    packed_envelope = packed_header + nonce + packed_ciphertext
    recovered_compressed = AESGCM(b"\x33" * 32).decrypt(
        nonce, packed_envelope[len(packed_header) + len(nonce):], aad
    )
    recovered_packed = zlib.decompress(recovered_compressed)
    if recovered_packed != packed:
        raise ValueError("packed AES-GCM envelope round-trip mismatch")
    packed_compact_bytes = len(packed_envelope)
    # Fixed framing: 13-byte direct envelope header + nonce + AES-GCM tag.
    direct_compressed = zlib.compress(direct_payload, level=9)
    direct_bytes = 13 + 12 + len(direct_compressed) + 16
    return {
        "feasible": 1,
        "fham_recovery_exact": 1,
        "record_bytes": len(raw),
        "compact_bytes": len(compressed),
        "packed_record_bytes": len(packed),
        "packed_compact_bytes": packed_compact_bytes,
        "packed_roundtrip": 1,
        "direct_bytes": direct_bytes,
    }


def run(
    corpus: str,
    image_limit: int | None,
    trials: int,
    include_channel: bool,
    descriptors: tuple[str, ...],
    block_sizes: tuple[int, ...],
    lengths: tuple[int, ...],
    families: tuple[str, ...],
    faces_only: bool,
    nonface_holdout: bool,
):
    image_dir = ROOT / "dataset" / corpus
    image_paths = sorted(image_dir.glob("*.png"))
    content_types = {}
    manifest = image_dir / "manifest.csv"
    if manifest.exists():
        manifest_df = pd.read_csv(manifest)
        content_types = dict(zip(manifest_df["name"], manifest_df["content_type"]))
    if faces_only:
        image_paths = [path for path in image_paths if "face" in content_types.get(path.stem, "").lower()]
    if nonface_holdout:
        controlled_manifest = pd.read_csv(ROOT / "dataset" / "controlled" / "manifest.csv")
        controlled_names = set(controlled_manifest["name"])
        image_paths = [
            path for path in image_paths
            if "face" not in content_types.get(path.stem, "").lower()
            and path.stem not in controlled_names
        ]
    if image_limit:
        image_paths = image_paths[:image_limit]
    if not image_paths:
        raise FileNotFoundError(f"No PNG images in {image_dir}")
    all_rows = []
    channel_rows = []
    started = time.time()
    for image_index, image_path in enumerate(image_paths, start=1):
        image = np.asarray(Image.open(image_path).convert("L"))
        for descriptor in descriptors:
            for block_size in block_sizes:
                build_start = time.perf_counter()
                capacities = codebook_counts(image, descriptor, block_size)
                build_ms = (time.perf_counter() - build_start) * 1000
                config = {"descriptor": descriptor, "block_size": block_size}
                channel_lookup = None
                if include_channel and 200 in lengths:
                    channel_builder = BoundedAssignmentMethod(0, block_size=block_size, descriptor=descriptor)
                    channel_builder.build_lookup_table(image)
                    channel_lookup = channel_builder.lookup_table
                for length in lengths:
                    for family, payloads in load_messages(length, trials).items():
                        if family not in families:
                            continue
                        for trial, original in enumerate(payloads):
                            for compression in ("none", "zlib9"):
                                encoded = make_candidate(original, compression)
                                required = Counter(encoded)
                                solve_start = time.perf_counter()
                                b_star = minimum_bound(required, capacities)
                                solve_ms = (time.perf_counter() - solve_start) * 1000
                                row = {
                                    "corpus": corpus,
                                    "image": image_path.stem,
                                    "content_type": content_types.get(image_path.stem, "unknown"),
                                    "descriptor": descriptor,
                                    "block_size": block_size,
                                    "bound": 2,
                                    "message_family": family,
                                    "input_length": len(original),
                                    "compression": compression,
                                    "coded_length": len(encoded),
                                    "trial": trial,
                                    "b_star": b_star,
                                    "feasible_b2": int(b_star is not None and b_star <= 2),
                                    **{
                                        f"feasible_b{bound}": int(b_star is not None and b_star <= bound)
                                        for bound in BOUNDS
                                    },
                                    "codebook_positions": sum(capacities.values()),
                                    "distinct_hashes": len(capacities),
                                    "codebook_build_ms": build_ms,
                                    "feasibility_ms": solve_ms,
                                    "message_sha256": hashlib.sha256(original).hexdigest(),
                                }
                                all_rows.append(row)
                                # Full assignment serialization is measured on each requested
                                # codebook configuration and the same source message.
                                if include_channel and length == 200:
                                    for bound in (2, 4, 8):
                                        channel_config = {
                                            **config,
                                            "bound": bound,
                                            "lookup_table": channel_lookup,
                                        }
                                        sizes = assignment_channel_sizes(
                                            image, channel_config, encoded, original
                                        )
                                        channel_rows.append({**row, "bound": bound, **sizes})
        elapsed = time.time() - started
        print(f"[{image_index}/{len(image_paths)}] {image_path.name} done; elapsed={elapsed:.1f}s", flush=True)
    raw = pd.DataFrame(all_rows)
    summary = raw.groupby(
        ["corpus", "descriptor", "block_size", "bound", "message_family", "input_length", "compression"],
        dropna=False,
        as_index=False,
    ).agg(
        trials=("feasible_b2", "size"),
        mean_coded_length=("coded_length", "mean"),
        **{f"feasible_b{bound}": (f"feasible_b{bound}", "mean") for bound in BOUNDS},
        b_star_median=("b_star", "median"),
        mean_codebook_positions=("codebook_positions", "mean"),
        mean_distinct_hashes=("distinct_hashes", "mean"),
        mean_build_ms=("codebook_build_ms", "mean"),
        mean_feasibility_ms=("feasibility_ms", "mean"),
    )
    return raw, summary, pd.DataFrame(channel_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", choices=("controlled", "stress"), default="controlled")
    parser.add_argument("--image-limit", type=int)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--include-channel", action="store_true")
    parser.add_argument("--descriptors", nargs="+", choices=DESCRIPTORS_TO_TEST, default=DESCRIPTORS_TO_TEST)
    parser.add_argument("--block-sizes", nargs="+", type=int, choices=BLOCK_SIZES, default=BLOCK_SIZES)
    parser.add_argument("--lengths", nargs="+", type=int, choices=LENGTHS, default=LENGTHS)
    parser.add_argument("--families", nargs="+", choices=FAMILIES, default=FAMILIES)
    parser.add_argument("--faces-only", action="store_true")
    parser.add_argument("--nonface-holdout", action="store_true")
    args = parser.parse_args()
    raw, summary, channel = run(
        args.corpus,
        args.image_limit,
        args.trials,
        args.include_channel,
        tuple(args.descriptors),
        tuple(args.block_sizes),
        tuple(args.lengths),
        tuple(args.families),
        args.faces_only,
        args.nonface_holdout,
    )
    out = ROOT / "results" / "revision_ablation"
    out.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{args.corpus}_{'faces_' if args.faces_only else 'nonface_holdout_' if args.nonface_holdout else ''}parameters"
        f"_d{'-'.join(args.descriptors)}_b{'-'.join(map(str, args.block_sizes))}"
        f"_n{'-'.join(map(str, args.lengths))}_t{args.trials}"
        f"_i{args.image_limit or 'all'}{'_channel' if args.include_channel else ''}"
    )
    raw.to_csv(out / f"{stem}_raw.csv", index=False)
    summary.to_csv(out / f"{stem}.csv", index=False)
    if not channel.empty:
        channel.to_csv(out / f"{stem}_channel_raw.csv", index=False)
    metadata = {
        "corpus": args.corpus,
        "image_limit": args.image_limit,
        "faces_only": args.faces_only,
        "nonface_holdout": args.nonface_holdout,
        "trials_per_message_family_length": args.trials,
        "descriptors": args.descriptors,
        "block_sizes": args.block_sizes,
        "bounds_reported": BOUNDS,
        "message_families": args.families,
        "lengths": args.lengths,
        "compression": ["none", "zlib9"],
        "seed_message_files": "dataset/message_manifests/message_seeds.csv",
        "command": " ".join(sys.argv),
        "raw_rows": len(raw),
        "channel_rows": len(channel),
        "python_version": platform.python_version(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_image_sha256": {
            name: hashlib.sha256((ROOT / "dataset" / args.corpus / f"{name}.png").read_bytes()).hexdigest()
            for name in sorted(raw["image"].unique())
        },
        "input_message_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for length in args.lengths
            for family in args.families
            for path in sorted((ROOT / "dataset" / "messages" / family).glob(f"{family}_{length}_*.bin"))[: args.trials]
        },
        "message_manifest_sha256": hashlib.sha256(
            (ROOT / "dataset" / "message_manifests" / "message_seeds.csv").read_bytes()
        ).hexdigest(),
    }
    (out / f"{stem}_provenance.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    print(f"Wrote raw data and summaries to {out}")


if __name__ == "__main__":
    main()
