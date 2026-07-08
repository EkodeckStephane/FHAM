from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fham.assignment import bottleneck_radius, codebook_counts, symbol_counts
from fham.methods import BoundedAssignmentMethod


def load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L").resize((512, 512), Image.Resampling.LANCZOS))


def messages(message_manifest: Path, limit: int) -> list[tuple[str, str, bytes]]:
    by_family: dict[str, list[tuple[str, bytes]]] = {}
    with message_manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["length_bytes"] not in {"50", "100", "200"}:
                continue
            by_family.setdefault(row["family"], []).append(
                (row["message_id"], Path(row["path"]).read_bytes())
            )
    families = sorted(by_family)
    rows = []
    index = 0
    while len(rows) < limit and any(by_family[family] for family in families):
        family = families[index % len(families)]
        if by_family[family]:
            message_id, payload = by_family[family].pop(0)
            rows.append((family, message_id, payload))
        index += 1
    return rows


def evaluate_manifest(dataset: str, manifest: Path, image_limit: int, message_limit: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not manifest.exists():
        return pd.DataFrame(), pd.DataFrame()
    with manifest.open(newline="", encoding="utf-8") as handle:
        image_rows = list(csv.DictReader(handle))[:image_limit]
    msg_rows = messages(Path("dataset/message_manifests/message_seeds.csv"), message_limit)
    raw_rows = []
    for image_row in image_rows:
        root = Path(image_row["source_root"])
        image_path = root / image_row["relative_path"]
        image = load_gray(image_path)
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        hashes = [value for value, locations in method.lookup_table.items() for _ in locations]
        for family, message_id, payload in msg_rows:
            text = payload.decode("latin-1")
            assignment = method.embed(text, image)
            raw_rows.append(
                {
                    "dataset": dataset,
                    "image": image_row["relative_path"],
                    "message_id": message_id,
                    "family": family,
                    "message_bytes": len(payload),
                    "descriptor": "spectral",
                    "bound": 2,
                    "success": int(assignment is not None),
                    "b_star": bottleneck_radius(symbol_counts(payload), codebook_counts(hashes)),
                }
            )
    raw = pd.DataFrame(raw_rows)
    if raw.empty:
        return pd.DataFrame(), raw
    summary = raw.groupby(["dataset", "family", "message_bytes"], as_index=False).agg(
        images=("image", "nunique"),
        trials=("success", "size"),
        success=("success", "mean"),
        b_star_median=("b_star", "median"),
        b_star_max=("b_star", "max"),
    )
    return summary, raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-limit", type=int, default=60)
    parser.add_argument("--message-limit", type=int, default=24)
    args = parser.parse_args()

    output = Path("results/processed/benchmark_smoke")
    raw_output = Path("results/raw/benchmark_smoke")
    output.mkdir(parents=True, exist_ok=True)
    raw_output.mkdir(parents=True, exist_ok=True)
    summaries = []
    raws = []
    for dataset in ("bossbase", "bows2", "coco2017_val"):
        summary, raw = evaluate_manifest(
            dataset,
            Path("dataset/manifests") / f"{dataset}.csv",
            args.image_limit,
            args.message_limit,
        )
        if not summary.empty:
            summaries.append(summary)
        if not raw.empty:
            raws.append(raw)
    if summaries:
        pd.concat(summaries, ignore_index=True).to_csv(output / "benchmark_assignment.csv", index=False)
    if raws:
        pd.concat(raws, ignore_index=True).to_csv(raw_output / "benchmark_assignment_raw.csv", index=False)
    print(f"evaluated {len(raws)} dataset groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
