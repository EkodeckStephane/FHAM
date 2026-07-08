from __future__ import annotations

import csv
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fham.config import RANDOM_SEED
from fham.experiments import _extended_attack, _message
from fham.methods import BoundedAssignmentMethod

TARGET_IMAGES_PER_CORPUS = 2000
LENGTH_BYTES = 100
BOUND = 2
TRANSFORMS = (
    "identity",
    "jpeg90",
    "jpeg75",
    "resize090",
    "rotate_pos1",
    "gnoise_sigma1",
    "gfilter_k3",
    "medfilter_k3",
)
MANIFESTS = {
    "bossbase": Path("dataset/manifests/bossbase.csv"),
    "bows2": Path("dataset/manifests/bows2.csv"),
    "coco2017_val": Path("dataset/manifests/coco2017_val.csv"),
}


def load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(
            image.convert("L").resize((512, 512), Image.Resampling.LANCZOS)
        )


def stratified_sample(rows: list[dict], target: int) -> list[dict]:
    rows = sorted(rows, key=lambda row: row["relative_path"])
    if len(rows) <= target:
        return rows
    indices = sorted(set(np.linspace(0, len(rows) - 1, target).round().astype(int).tolist()))
    return [rows[i] for i in indices]


def run_corpus(dataset: str, manifest: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    sample = stratified_sample(rows, TARGET_IMAGES_PER_CORPUS)
    raw_rows = []
    t0 = time.time()
    for index, row in enumerate(sample):
        root = Path(row["source_root"])
        image = load_gray(root / row["relative_path"])
        method = BoundedAssignmentMethod(BOUND)
        method.build_lookup_table(image)
        message = _message(LENGTH_BYTES, row["relative_path"], 0)
        assignment = method.embed(message, image)
        if assignment is None:
            continue
        for transform_name in TRANSFORMS:
            seed = RANDOM_SEED + zlib.crc32(
                f"{row['relative_path']}:{transform_name}".encode()
            )
            attacked = (
                image
                if transform_name == "identity"
                else _extended_attack(image, transform_name, seed)
            )
            recovered = method.extract(assignment, attacked)
            correct = sum(a == b for a, b in zip(message, recovered))
            raw_rows.append(
                {
                    "dataset": dataset,
                    "image": row["relative_path"],
                    "transform": transform_name,
                    "exact_recovery": int(recovered == message),
                    "character_accuracy": correct / LENGTH_BYTES,
                }
            )
        if (index + 1) % 200 == 0:
            elapsed = time.time() - t0
            print(f"{dataset}: {index + 1}/{len(sample)} images, {elapsed:.0f}s elapsed")
    raw = pd.DataFrame(raw_rows)
    if raw.empty:
        return pd.DataFrame(), raw
    summary = raw.groupby(["dataset", "transform"], as_index=False).agg(
        images=("image", "nunique"),
        trials=("exact_recovery", "size"),
        exact_recovery=("exact_recovery", "mean"),
        character_accuracy=("character_accuracy", "mean"),
    )
    return summary, raw


def main() -> int:
    summaries = []
    raws = []
    for dataset, manifest in MANIFESTS.items():
        if not manifest.exists():
            print(f"{dataset}: manifest missing, skipping")
            continue
        summary, raw = run_corpus(dataset, manifest)
        if not summary.empty:
            summaries.append(summary)
            raws.append(raw)
        print(f"{dataset}: {len(raw)} raw trials")

    output_dir = Path("results/processed/stratified_robustness")
    raw_dir = Path("results/raw/stratified_robustness")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    if summaries:
        pd.concat(summaries, ignore_index=True).to_csv(
            output_dir / "stratified_robustness.csv", index=False
        )
    if raws:
        pd.concat(raws, ignore_index=True).to_csv(
            raw_dir / "stratified_robustness_raw.csv", index=False
        )
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
