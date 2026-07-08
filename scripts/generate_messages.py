from __future__ import annotations

import argparse
import csv
import hashlib
import random
from pathlib import Path


LENGTHS = (10, 50, 100, 200, 400, 800, 1200, 1600)
FAMILIES = (
    "uniform_bytes",
    "printable_ascii",
    "natural_text",
    "adversarial_repeated",
)
TEXT = (
    "This deterministic public-domain-style test sentence is used only to "
    "exercise byte generation for the FHAM reproducibility harness. "
)


def generate(family: str, length: int, seed: int) -> bytes:
    rng = random.Random(seed)
    if family == "uniform_bytes":
        return bytes(rng.randrange(256) for _ in range(length))
    if family == "printable_ascii":
        return bytes(rng.randrange(32, 127) for _ in range(length))
    if family == "natural_text":
        source = (TEXT * ((length // len(TEXT)) + 2)).encode("ascii")
        offset = rng.randrange(len(TEXT))
        return (source[offset:] + source[:offset])[:length]
    if family == "adversarial_repeated":
        value = rng.choice((0, 1, 2, 253, 254, 255))
        return bytes([value]) * length
    raise ValueError(f"unknown message family: {family}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="dataset/messages")
    parser.add_argument("--manifest", default="dataset/message_manifests/message_seeds.csv")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    output_root = Path(args.output_root)
    manifest = Path(args.manifest)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for family in FAMILIES:
        family_dir = output_root / family
        family_dir.mkdir(parents=True, exist_ok=True)
        for length in LENGTHS:
            for repetition in range(args.repetitions):
                seed = args.seed + length * 1009 + repetition * 9173 + sum(family.encode("ascii"))
                payload = generate(family, length, seed)
                message_id = f"{family}_{length}_{repetition:02d}"
                path = family_dir / f"{message_id}.bin"
                path.write_bytes(payload)
                rows.append(
                    {
                        "message_id": message_id,
                        "family": family,
                        "length_bytes": length,
                        "seed": seed,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "path": path.as_posix(),
                        "generation_rule": family,
                    }
                )

    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} messages to {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
