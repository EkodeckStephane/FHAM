#!/usr/bin/env python3
"""Freeze 1quater D-b/message inputs and measure existing envelope overhead.

This preflight does not read image pixels and does not run A1-A5.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import platform
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stability_step1/step1quater/manifest"
MESSAGE_ROOT = ROOT / "dataset/messages"
SEED_CSV = ROOT / "dataset/message_manifests/message_seeds.csv"
D_MANIFEST = ROOT / "results/stability_step1/step1ter/manifest/bows2_D_E_C_manifest.csv"
DA_PROVENANCE = ROOT / "results/stability_step1/step1ter/step2_3/run_provenance.json"
PROTOCOL = ROOT / "protocols/FHAM_etape_1quater_preregistre.md"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with D_MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    d_rows = [row for row in rows if row["split"] == "D"]
    if len(d_rows) != 200:
        raise RuntimeError(f"Expected 200 D images, found {len(d_rows)}")

    da = json.loads(DA_PROVENANCE.read_text(encoding="utf-8"))
    da_ids = set(da["D_images"])
    if len(da_ids) != 100:
        raise RuntimeError(f"Expected 100 D-a IDs, found {len(da_ids)}")
    d_by_id = {row["source_id"]: row for row in d_rows}
    if not da_ids.issubset(d_by_id):
        missing = sorted(da_ids - set(d_by_id))
        raise RuntimeError(f"D-a IDs absent from frozen D split: {missing[:5]}")
    for source_id, digest in da["D_sha256"].items():
        if d_by_id[source_id]["sha256"] != digest:
            raise RuntimeError(f"D-a hash mismatch: {source_id}")

    db_rows = [row for row in d_rows if row["source_id"] not in da_ids]
    if len(db_rows) != 100:
        raise RuntimeError(f"Expected 100 D-b images, found {len(db_rows)}")
    db_stems = {Path(row["source_id"]).stem for row in db_rows}
    step1ter_root = ROOT / "results/stability_step1/step1ter"
    named_output_hits = [
        str(path.relative_to(ROOT).as_posix())
        for path in step1ter_root.rglob("*")
        if path.is_file() and path.stem.split(".")[0] in db_stems
    ]
    if named_output_hits:
        raise RuntimeError(
            "D-b source IDs already occur as named 1ter outputs: "
            + ", ".join(named_output_hits[:10])
        )
    db_rows.sort(key=lambda row: (int(row["selection_rank_1ter"] or 10**9), row["source_id"]))
    d_b_path = OUT / "D_b_images_sha256.csv"
    with d_b_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["position", "source_id", "relative_path", "sha256", "selection_rank_1ter"],
        )
        writer.writeheader()
        for pos, row in enumerate(db_rows, 1):
            writer.writerow({
                "position": pos,
                "source_id": row["source_id"],
                "relative_path": row["relative_path"],
                "sha256": row["sha256"],
                "selection_rank_1ter": row["selection_rank_1ter"],
            })

    with SEED_CSV.open(encoding="utf-8-sig", newline="") as stream:
        seed_rows = list(csv.DictReader(stream))
    seed_by_id = {row["message_id"]: row for row in seed_rows}
    families = ["adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes"]
    indices = ["00", "01", "02"]
    message_rows: list[dict[str, object]] = []
    for family in families:
        for index in indices:
            for length in (25, 50, 100, 200):
                message_id = f"{family}_{length}_{index}"
                path = MESSAGE_ROOT / family / f"{message_id}.bin"
                derivation = "source artifact"
                seed_id = message_id
                if length == 25:
                    seed_id = f"{family}_50_{index}"
                    seed_row = seed_by_id.get(seed_id)
                    if seed_row is None:
                        raise RuntimeError(f"Missing seed row for {seed_id}")
                    source_path = ROOT / seed_row["path"]
                    source = source_path.read_bytes()
                    if len(source) != 50 or sha256_bytes(source) != seed_row["sha256"]:
                        raise RuntimeError(f"Frozen 50-byte source mismatch: {seed_id}")
                    payload = source[:25]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                    derivation = f"first 25 bytes of {seed_row['path']}"
                else:
                    seed_row = seed_by_id.get(message_id)
                    if seed_row is None:
                        raise RuntimeError(f"Missing seed row for {message_id}")
                    if seed_row["path"] != path.relative_to(ROOT).as_posix():
                        raise RuntimeError(f"Message path mismatch: {message_id}")
                    payload = path.read_bytes()
                    if len(payload) != length or sha256_bytes(payload) != seed_row["sha256"]:
                        raise RuntimeError(f"Message artifact mismatch: {message_id}")
                message_rows.append({
                    "message_id": message_id,
                    "family": family,
                    "index": index,
                    "L_src": length,
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": sha256_bytes(payload),
                    "seed": seed_row["seed"],
                    "seed_inherited_from": seed_id if length == 25 else "",
                    "derivation": derivation,
                })

    if len(message_rows) != 48:
        raise RuntimeError(f"Expected 48 message artifacts, found {len(message_rows)}")
    msg_path = OUT / "messages_sha256.csv"
    with msg_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(message_rows[0]))
        writer.writeheader()
        writer.writerows(message_rows)

    root_seed = 20261120
    streams = [
        "robustness/jpeg",
        "robustness/noise",
        "attacks/jpeg",
        "attacks/noise",
        "A4/candidate_draws",
        "RS/parity_sensitivity",
        "bootstrap/cluster",
        "permutation/sign_flip",
    ]
    seed_schedule = {
        "protocol": "FHAM-1quater-v1",
        "master_seed": root_seed,
        "bit_generator": "numpy.random.PCG64",
        "derivation": "first 64 bits (big-endian) of SHA-256(UTF-8('FHAM-1quater-v1|20261120|<stream>|<stable identifiers>'))",
        "stable_identifiers": ["D-b image sha256", "message_id", "attack family", "replicate index"],
        "named_streams": {
            name: int.from_bytes(hashlib.sha256(
                f"FHAM-1quater-v1|{root_seed}|{name}|global".encode("utf-8")
            ).digest()[:8], "big")
            for name in streams
        },
        "message_seeds_source": "dataset/message_manifests/message_seeds.csv",
        "reedsolo": {
            "version": "1.7.0",
            "field": "GF(256)",
            "nsize": 255,
            "fcr": 0,
            "generator": 2,
            "prim": "0x11D",
            "c_exp": 8,
        },
        "note": "Seeds are frozen for reproducibility; no A1-A5 measurements are run by this preflight.",
    }
    seed_path = OUT / "seed_schedule.json"
    seed_path.write_text(json.dumps(seed_schedule, indent=2) + "\n", encoding="utf-8")

    sys.path.insert(0, str(ROOT / "src"))
    from fham.channel import AuxiliaryChannel
    from fham.methods import Assignment

    empty = Assignment((256, 256), 12, [], [])
    raw = AuxiliaryChannel.serialize(empty)
    compressed = zlib.compress(raw, level=9)
    key = bytes(range(32))
    envelope = AuxiliaryChannel.protect(empty, key)
    direct = AuxiliaryChannel.protect_direct(b"", key, nonce=bytes(range(12)))
    fixed_fham = (
        AuxiliaryChannel.ENVELOPE_HEADER.size + 12 + 16
    )
    fixed_direct = AuxiliaryChannel.DIRECT_ENVELOPE_HEADER.size + 12 + 16
    if (len(raw), len(compressed), len(envelope), fixed_fham, len(direct), fixed_direct) != (15, 21, 62, 41, 29, 29):
        raise RuntimeError("Serializer overhead did not match the expected measured byte counts")
    serializer = {
        "implementation": "src/fham/channel.py::AuxiliaryChannel",
        "implementation_sha256": sha256_file(ROOT / "src/fham/channel.py"),
        "serialization_header_bytes": AuxiliaryChannel.SERIAL_HEADER.size,
        "compressed_empty_serialized_payload_bytes": len(compressed),
        "compact_public_header_bytes": AuxiliaryChannel.ENVELOPE_HEADER.size,
        "nonce_bytes": 12,
        "gcm_tag_bytes": 16,
        "fham_fixed_envelope_overhead_bytes": fixed_fham,
        "direct_public_header_bytes": AuxiliaryChannel.DIRECT_ENVELOPE_HEADER.size,
        "direct_fixed_envelope_overhead_bytes": fixed_direct,
        "empty_fham_envelope_total_bytes": len(envelope),
        "direct_empty_envelope_total_bytes": len(direct),
        "measurement_method": "serialize empty Assignment; zlib level 9; protect with AES-GCM; subtract compressed plaintext length from envelope length; deterministic direct nonce for byte-count reproducibility",
        "note": "The current Assignment serializer does not yet encode the 1quater CRC, erasure bitmap, or gallery identifiers. Its F=41 envelope overhead is measured; full 1quater Z9/b_total requires the versioned 1quater body serializer before reporting.",
    }
    serializer_path = OUT / "serializer_overhead.json"
    serializer_path.write_text(json.dumps(serializer, indent=2) + "\n", encoding="utf-8")

    versions = {}
    for package in ["numpy", "scipy", "Pillow", "opencv-python", "cryptography", "reedsolo"]:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    try:
        import cv2
        versions["cv2_runtime"] = cv2.__version__
    except ImportError:
        versions["cv2_runtime"] = None
    prior_metadata_path = OUT / "freeze_metadata.json"
    prior_metadata = (
        json.loads(prior_metadata_path.read_text(encoding="utf-8"))
        if prior_metadata_path.exists()
        else {}
    )
    metadata = {
        "protocol": "FHAM 1quater preregistration",
        "branch": git("branch", "--show-current"),
        "base_commit_before_freeze": git("rev-parse", "HEAD"),
        "input_freeze_commit": prior_metadata.get("input_freeze_commit"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "libraries": versions,
        "reedsolo_required": "1.7.0",
        "D_a_source": "results/stability_step1/step1ter/step2_3/run_provenance.json",
        "D_a_count": len(da_ids),
        "D_b_count": len(db_rows),
        "D_b_named_output_files_in_step1ter": len(named_output_hits),
        "D_b_sha256_csv": sha256_file(d_b_path),
        "message_count": len(message_rows),
        "message_manifest_sha256": sha256_file(msg_path),
        "source_seed_csv_sha256": sha256_file(SEED_CSV),
        "seed_schedule_sha256": sha256_file(seed_path),
        "serializer_measurement_sha256": sha256_file(serializer_path),
        "protocol_sha256": sha256_file(PROTOCOL),
        "source_partition_manifest_sha256": sha256_file(D_MANIFEST),
        "D_a_provenance_sha256": sha256_file(DA_PROVENANCE),
        "opened_pixel_data": {"D_a": "previously analyzed", "D_b": False, "E": False, "C": False, "F": False},
        "A1_A5_executed": False,
    }
    meta_path = OUT / "freeze_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "D_b_images": len(db_rows),
        "messages": len(message_rows),
        "25_byte_prefixes_created": sum(row["L_src"] == 25 for row in message_rows),
        "reedsolo": versions.get("reedsolo"),
        "F_fham": fixed_fham,
        "F_direct": fixed_direct,
        "empty_payload_zlib9": len(compressed),
        "empty_fham_envelope": len(envelope),
        "A1_A5_executed": False,
        "freeze_metadata": str(meta_path.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
