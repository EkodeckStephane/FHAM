"""Evaluate the stability-cost lambda sweep on images outside the tuning set."""

from __future__ import annotations

import hashlib
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fham.experiments import _attack, _location_stabilities  # noqa: E402
from fham.methods import OptimalAssignmentMethod, StabilityAwareAssignmentMethod  # noqa: E402


def main() -> None:
    manifest = pd.read_csv(ROOT / "dataset" / "stress" / "manifest.csv")
    controlled = set(pd.read_csv(ROOT / "dataset" / "controlled" / "manifest.csv")["name"])
    # Keep stress images that are disjoint from both the controlled corpus
    # and the LFW face set used for the parameter-selection ablation.
    holdout = manifest[
        ~manifest["name"].isin(controlled)
        & ~manifest["content_type"].str.lower().str.contains("face")
    ]
    message_paths = sorted((ROOT / "dataset" / "messages" / "natural_text").glob("natural_text_200_*.bin"))[:3]
    lambdas = (0.0, 0.25, 0.5, 0.75, 1.0)
    development_attacks = ("jpeg90", "resize90", "noise1")
    evaluation_attacks = ("jpeg75", "rotate1", "noise2")
    rows = []
    for image_index, item in enumerate(holdout.itertuples(index=False), start=1):
        image_path = ROOT / "dataset" / "stress" / item.file
        image = np.asarray(Image.open(image_path).convert("L"))
        lookup = OptimalAssignmentMethod(block_size=12, descriptor="spectral")
        lookup.build_lookup_table(image)
        stability = _location_stabilities(lookup, image, development_attacks, item.name)
        for trial, message_path in enumerate(message_paths):
            original = message_path.read_bytes()
            coded = zlib.compress(original, level=9)
            coded_text = coded.decode("latin-1")
            for lam in lambdas:
                method = StabilityAwareAssignmentMethod(
                    max_displacement=2,
                    lam=lam,
                    block_size=12,
                    descriptor="spectral",
                )
                method.lookup_table = lookup.lookup_table
                method.image_shape = lookup.image_shape
                method.stabilities = stability
                assignment = method.embed(coded_text, image)
                base = {
                    "image": item.name,
                    "content_type": item.content_type,
                    "trial": trial,
                    "message_file": message_path.name,
                    "input_bytes": len(original),
                    "coded_bytes": len(coded),
                    "lambda": lam,
                    "block_size": 12,
                    "descriptor": "spectral",
                    "bound": 2,
                    "assignment_success": int(assignment is not None),
                    "identity_exact": 0,
                    "identity_byte_accuracy": 0.0,
                    "total_displacement": np.nan,
                }
                if assignment is None:
                    for attack_name in evaluation_attacks:
                        rows.append({**base, "transform": attack_name, "exact_coded_recovery": 0, "source_recovery": 0, "byte_accuracy": 0.0})
                    continue
                recovered = method.extract(assignment, image).encode("latin-1")
                if recovered != coded:
                    raise ValueError("identity round-trip failed for the coded message")
                try:
                    identity_source_recovery = int(zlib.decompress(recovered) == original)
                except zlib.error:
                    identity_source_recovery = 0
                base["identity_exact"] = 1
                base["identity_byte_accuracy"] = 1.0
                base["total_displacement"] = sum(abs(value) for value in assignment.displacements)
                for attack_index, attack_name in enumerate(evaluation_attacks):
                    attacked = _attack(image, attack_name, 20261114 + attack_index + trial + image_index * 37)
                    received = method.extract(assignment, attacked).encode("latin-1")
                    exact = int(received == coded)
                    accuracy = sum(a == b for a, b in zip(received, coded)) / len(coded)
                    try:
                        source_recovery = int(zlib.decompress(received) == original)
                    except zlib.error:
                        source_recovery = 0
                    rows.append({
                        **base,
                        "identity_source_recovery": identity_source_recovery,
                        "transform": attack_name,
                        "exact_coded_recovery": exact,
                        "source_recovery": source_recovery,
                        "byte_accuracy": accuracy,
                    })
        print(f"[{image_index}/{len(holdout)}] {item.name} complete", flush=True)

    raw = pd.DataFrame(rows)
    summary = raw.groupby(["lambda", "transform"], as_index=False).agg(
        trials=("source_recovery", "size"),
        assignment_success=("assignment_success", "mean"),
        exact_coded_recovery=("exact_coded_recovery", "mean"),
        source_recovery=("source_recovery", "mean"),
        mean_byte_accuracy=("byte_accuracy", "mean"),
        mean_total_displacement=("total_displacement", "mean"),
    )
    out = ROOT / "results" / "revision_ablation"
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "lambda_transfer_scene_holdout_raw.csv"
    summary_path = out / "lambda_transfer_scene_holdout.csv"
    raw.to_csv(raw_path, index=False)
    summary.to_csv(summary_path, index=False)
    provenance = {
        "images": list(holdout["name"]),
        "image_count": len(holdout),
        "image_sha256": {
            name: hashlib.sha256((ROOT / "dataset" / "stress" / f"{name}.png").read_bytes()).hexdigest()
            for name in holdout["name"]
        },
        "message_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in message_paths},
        "block_size": 12,
        "descriptor": "spectral",
        "bound": 2,
        "lambda_values": lambdas,
        "development_attacks": development_attacks,
        "evaluation_attacks": evaluation_attacks,
        "raw_rows": len(raw),
        "identity_round_trip": "exact coded bytes and decompressed source checked before evaluation transforms",
        "seed_rule": "20261114 + transform_index + trial + 37 * image_index",
    }
    (out / "lambda_transfer_scene_holdout_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
