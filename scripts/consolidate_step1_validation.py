"""Consolidate resumable cover chunks into the row-level Step 1 datasets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stability_step1"


def concatenate(files: list[Path], destination: Path) -> int:
    frames = []
    for path in files:
        if path.stat().st_size < 100:
            continue
        frames.append(pd.read_csv(path))
    if not frames:
        raise RuntimeError(f"No usable rows found for {destination.name}")
    frame = pd.concat(frames, ignore_index=True)
    frame.to_csv(destination, index=False, compression="gzip")
    return len(frame)


def main() -> None:
    chunks = OUT / "validation_chunks_p2resize"
    n_assignment = concatenate(
        sorted(chunks.glob("*_assignments.csv.gz")),
        OUT / "validation_assignment_raw_p2resize.csv.gz",
    )
    n_recovery = concatenate(
        sorted(chunks.glob("*_recovery.csv.gz")),
        OUT / "validation_recovery_raw_p2resize.csv.gz",
    )
    receiver_chunks = OUT / "receiver_validation_chunks"
    n_receiver = concatenate(
        sorted(receiver_chunks.glob("*.csv.gz")),
        OUT / "receiver_validation_raw.csv.gz",
    )
    print({"assignment_rows": n_assignment,
           "recovery_rows": n_recovery,
           "receiver_rows": n_receiver})


if __name__ == "__main__":
    main()
