"""Reproduce the S3/0.5 1bis bridge on 20 BOWS2-A and 20 BOWS2-B covers."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import run_step1bis_profiles as ref

SPLIT = ROOT / "results/stability_step1/step1bis/manifest/split_manifest.csv"
OUT = ROOT / "results/stability_step1/step1ter/G_T0"
BASE = ROOT / "results/stability_step1/step1bis/profile_stage"
ARCHIVE_PROVENANCE = BASE / "summaries/summary_provenance.json"
CONFIG = ("S3", 0.5)
KEYS = ["cover", "family", "source_length", "message_index", "transform", "path"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    split = pd.read_csv(SPLIT).sort_values("selection_rank")
    archived_covers = json.loads(ARCHIVE_PROVENANCE.read_text(encoding="utf-8"))["covers_by_group"]
    messages = ref.fixed_messages((0,))  # 4 families × 2 source lengths = 8
    rows = []
    started = time.perf_counter()
    for group in ("A", "B"):
        group_rows = split.loc[split.split.eq(group)].reset_index(drop=True)
        names = archived_covers["A_profile_screen" if group == "A" else "B_q0_bridge"][:20]
        selected = group_rows.loc[group_rows.source_id.isin(names)].copy()
        selected["original_index"] = selected.source_id.map(
            {source_id: i for i, source_id in enumerate(group_rows.source_id)})
        selected = selected.set_index("source_id").loc[names].reset_index()
        if len(selected) != 20:
            raise RuntimeError(f"Expected 20 existing {group} covers")
        output = BASE / ("A_profile_screen" if group == "A" else "B_q0_bridge")
        for row in selected.itertuples(index=False):
            record = ref.make_record(ref.BOWS2_ROOT / row.relative_path,
                                     "BOWS2", group, row.source_id, int(row.original_index))
            _, recovery, _ = ref.process_cover(record, (12,), messages, q0_only=True)
            frame = recovery.loc[(recovery.method.eq(CONFIG[0]))
                                 & (recovery["lambda"].eq(CONFIG[1]))].copy()
            archived = pd.concat([
                pd.read_csv(output / f"{row.source_id}_recovery.csv.gz")
                for _ in [0]
            ], ignore_index=True)
            archived = archived.loc[(archived.method.eq(CONFIG[0]))
                                     & (archived["lambda"].eq(CONFIG[1]))]
            merged = frame.merge(archived, on=KEYS, suffixes=("_new", "_old"),
                                 validate="one_to_one")
            if len(merged) != len(frame) or len(frame) != 8 * 14:
                raise RuntimeError(f"Unexpected paired rows for {group}/{row.source_id}: {len(merged)}")
            # Compare primary recovery counts exactly; the tolerance is applied
            # to aggregate percentage-point accuracy as frozen in the protocol.
            for col in ("n_correct", "n_symbols", "exact"):
                if not (merged[f"{col}_new"] == merged[f"{col}_old"]).all():
                    raise RuntimeError(f"Raw regression mismatch {group}/{row.source_id}/{col}")
            merged["group"] = group
            merged["cover_sha256"] = row.sha256
            rows.append(merged[KEYS + ["group", "cover_sha256", "n_correct_new", "n_symbols_new"]])
            print(f"G-T0 {group} {index+1}/20 {row.source_id}: exact", flush=True)
    paired = pd.concat(rows, ignore_index=True)
    paired["accuracy"] = paired.n_correct_new / paired.n_symbols_new
    agg = paired.groupby(["group", "transform", "path"], as_index=False).agg(
        mean_accuracy=("accuracy", "mean"), covers=("cover", "nunique"))
    provenance = {"configuration": "S3 lambda=0.5, B=2, L=12, zlib-9",
                  "covers_per_group": 20, "messages_per_cover": 8,
                  "paired_rows": len(paired), "raw_metric_match": "exact",
                  "maximum_absolute_percentage_point_difference": 0.0,
                  "tolerance_percentage_points": 0.05,
                  "passed": True,
                  "elapsed_seconds": time.perf_counter()-started}
    paired.to_csv(OUT / "paired_rows.csv", index=False)
    agg.to_csv(OUT / "aggregate.csv", index=False)
    (OUT / "gate.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance, indent=2), flush=True)


if __name__ == "__main__":
    main()
