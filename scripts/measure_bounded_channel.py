"""Measure auxiliary-channel size for the controlled B=2 cohort at 200 chars."""

from pathlib import Path
import os
import zlib

import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import numpy as np
from PIL import Image

from fham.channel import AuxiliaryChannel
from fham.config import DATASET_DIR, RESULTS_DIR
from fham.experiments import _message
from fham.methods import BoundedAssignmentMethod


def main():
    key = os.urandom(32)
    rows = []
    for image_path in sorted((DATASET_DIR / "controlled").glob("*.png")):
        image_name = image_path.stem
        image = np.asarray(Image.open(image_path).convert("L"))
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        for trial in range(10):
            message = _message(200, image_name, trial)
            assignment = method.embed(message, image)
            if assignment is None:
                rows.append({"image": image_name, "trial": trial, "success": 0})
                continue
            compact = AuxiliaryChannel.protect(assignment, key)
            direct_payload = zlib.compress(message.encode("ascii"), level=9)
            nonce = os.urandom(12)
            ciphertext = AESGCM(key).encrypt(nonce, direct_payload, b"FHAM-DIRECT-BASELINE")
            direct_bytes = 13 + len(nonce) + len(ciphertext)
            raw = AuxiliaryChannel.serialize(assignment)
            rows.append({
                "image": image_name,
                "trial": trial,
                "success": 1,
                "message_bytes": len(message.encode("ascii")),
                "raw_record_bytes": len(raw),
                "compact_envelope_bytes": len(compact),
                "direct_encrypted_bytes": direct_bytes,
                "envelope_to_direct_ratio": len(compact) / direct_bytes,
            })
    raw = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / "auxiliary_channel_b2_200_raw.csv"
    summary_path = RESULTS_DIR / "auxiliary_channel_b2_200.csv"
    raw.to_csv(raw_path, index=False)
    successful = raw[raw.success == 1]
    summary = pd.DataFrame([{
        "bound": 2,
        "length": 200,
        "trials": len(raw),
        "feasible_trials": len(successful),
        "assignment_success_rate": len(successful) / len(raw),
        "mean_raw_record_bytes": successful.raw_record_bytes.mean(),
        "mean_compact_envelope_bytes": successful.compact_envelope_bytes.mean(),
        "mean_direct_encrypted_bytes": successful.direct_encrypted_bytes.mean(),
        "mean_envelope_to_direct_ratio": successful.envelope_to_direct_ratio.mean(),
    }])
    summary.to_csv(summary_path, index=False)
    print(summary.to_string(index=False))
    print(f"raw: {raw_path}")
    print(f"summary: {summary_path}")


if __name__ == "__main__":
    main()
