"""Post-hoc G-Q0 deficit audit using only the already-open 1ter D outputs.

No source images are read and no perturbations or new assignments are run.
The graph is reconstructed from 1ter's saved robust positions and its fixed
zlib-9 messages, then compared against the archived 1ter feasibility labels.
"""
from __future__ import annotations

import csv
import gzip
import math
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
from fham_matching import max_matching

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1ter"
OUT = BASE / "audit_diagnostics" / "GQ0_posthoc"
OUT.mkdir(parents=True, exist_ok=True)
DESCRIPTORS = ("mean_ordinal", "dct_sumabs")
BOUNDS = (2, 4, 8)
BOOTSTRAP_SEED = 20261119
BOOTSTRAP_REPS = 10_000


def csv_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


# Saved robust positions from 1ter Step 4b, indexed once per cover/descriptor.
positions: dict[tuple[str, str], list[int]] = defaultdict(list)
position_files = sorted((BASE / "step4b_screen").glob("*_positions.csv.gz"))
for path in position_files:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["descriptor"] in DESCRIPTORS and int(row["robust"]):
                positions[(row["cover"], row["descriptor"])].append(int(row["hash_value"]))

if len({cover for cover, desc in positions if desc == "mean_ordinal"}) != 100:
    raise RuntimeError("Expected exactly 100 D covers in saved robust-position outputs")

# Load the 12 fixed source messages, then use the exact zlib-9 representation
# that the 1ter ceiling calculation used.
messages = []
for family in ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated"):
    for index in range(3):
        raw = (ROOT / "dataset" / "messages" / family / f"{family}_100_{index:02d}.bin").read_bytes()
        payload = zlib.compress(raw, 9)
        messages.append((family, index, len(raw), payload))

# Reconstruct and compare feasibility for each (cover,message) with archived
# Step 4b assignments. The attack rows duplicate the assignment; keep one.
archived = {}
for path in sorted((BASE / "step4b_ceiling").glob("*_ceiling.csv")):
    for row in csv_rows(path):
        if (row["descriptor"] in DESCRIPTORS and int(row["source_length"]) == 100
                and row["family"] != "ALL12"):
            key = (row["cover"], row["descriptor"], int(row["bound"]), row["family"], int(row["index"]))
            archived[key] = int(float(row["feasible"]))

detail_rows = []
per_message: dict[tuple, dict[str, int]] = defaultdict(dict)
empty_values_by_cover: dict[tuple[str, str, int], int] = {}
for (cover, descriptor), hash_values in sorted(positions.items()):
    if descriptor not in DESCRIPTORS:
        continue
    for bound in BOUNDS:
        # Count missing target byte values for this cover and radius.
        value_candidate_counts = [sum(abs(h - target) <= bound for h in hash_values) for target in range(256)]
        empty_values_by_cover[(cover, descriptor, bound)] = sum(c == 0 for c in value_candidate_counts)
        for family, index, source_n, payload in messages:
            adjacency = []
            for symbol in payload:
                target = symbol
                adjacency.append([j for j, h in enumerate(hash_values) if abs(h - target) <= bound])
            n = len(payload)
            no_candidate = sum(not neighbors for neighbors in adjacency)
            matched = max_matching(adjacency, len(hash_values))
            deficit = n - matched
            hall_deficit = deficit - no_candidate
            if hall_deficit < 0:
                raise AssertionError("Hall residual cannot be negative")
            key = (cover, descriptor, bound, family, index)
            archived_value = archived.get(key)
            if archived_value is None:
                raise RuntimeError(f"Missing archived feasibility row for {key}")
            reproduced = int(deficit == 0)
            if reproduced != archived_value:
                raise RuntimeError(f"Feasibility mismatch for {key}: reconstructed={reproduced}, archived={archived_value}")
            rec = {
                "cover": cover, "descriptor": descriptor, "B": bound,
                "family": family, "message_index": index, "source_bytes": source_n,
                "compressed_symbols_n": n, "matched_symbols": matched,
                "deficit_d": deficit, "d_empty": no_candidate,
                "d_Hall": hall_deficit, "feasible": reproduced,
                "target_values_without_candidate_on_cover": empty_values_by_cover[(cover, descriptor, bound)],
            }
            detail_rows.append(rec)
            per_message[(descriptor, bound, family, index)][cover] = reproduced

with (OUT / "message_deficits.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(detail_rows[0]))
    w.writeheader()
    w.writerows(detail_rows)

# Descriptive summaries are over infeasible messages only, as specified by H11.
groups: dict[tuple, list[dict]] = defaultdict(list)
for row in detail_rows:
    groups[(row["descriptor"], row["B"])].append(row)
summary_rows = []
for (descriptor, bound), rows in sorted(groups.items()):
    failed = [r for r in rows if not r["feasible"]]
    ds = np.asarray([r["deficit_d"] for r in failed], dtype=float)
    ratio = np.asarray([r["deficit_d"] / r["compressed_symbols_n"] for r in failed], dtype=float)
    summary_rows.append({
        "descriptor": descriptor, "B": bound, "messages_total": len(rows),
        "messages_infeasible": len(failed), "infeasible_rate": len(failed) / len(rows),
        "median_d_infeasible": float(np.median(ds)) if len(ds) else 0,
        "q90_d_infeasible": float(np.quantile(ds, .90)) if len(ds) else 0,
        "q99_d_infeasible": float(np.quantile(ds, .99)) if len(ds) else 0,
        "max_d_infeasible": int(np.max(ds)) if len(ds) else 0,
        "median_d_over_n_infeasible": float(np.median(ratio)) if len(ratio) else 0,
        "mean_d_empty_infeasible": float(np.mean([r["d_empty"] for r in failed])) if failed else 0,
        "mean_d_Hall_infeasible": float(np.mean([r["d_Hall"] for r in failed])) if failed else 0,
        "failed_with_d_Hall_zero": sum(r["d_Hall"] == 0 for r in failed),
        "failed_count": len(failed),
    })
with (OUT / "deficit_summary.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(summary_rows[0]))
    w.writeheader()
    w.writerows(summary_rows)

# Per-cover histogram of the number of byte values with no robust candidate.
with (OUT / "empty_target_values_by_cover.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["cover", "descriptor", "B", "target_byte_values_without_candidate"])
    for (cover, descriptor, bound), count in sorted(empty_values_by_cover.items()):
        w.writerow([cover, descriptor, bound, count])

# Cover-cluster bootstrap CIs for the per-message feasibility proportions.
rng = np.random.default_rng(BOOTSTRAP_SEED)
boot_rows = []
for (descriptor, bound, family, index), covers in sorted(per_message.items()):
    values = np.asarray(list(covers.values()), dtype=np.int8)
    samples = rng.integers(0, len(values), size=(BOOTSTRAP_REPS, len(values)))
    estimates = values[samples].mean(axis=1)
    boot_rows.append({
        "descriptor": descriptor, "B": bound, "family": family, "message_index": index,
        "feasible_covers": int(values.sum()), "covers": len(values), "rate": float(values.mean()),
        "cluster_bootstrap_low_95": float(np.quantile(estimates, .025)),
        "cluster_bootstrap_high_95": float(np.quantile(estimates, .975)),
        "bootstrap_reps": BOOTSTRAP_REPS, "seed": BOOTSTRAP_SEED,
    })
with (OUT / "per_message_feasibility_bootstrap.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(boot_rows[0]))
    w.writeheader()
    w.writerows(boot_rows)

# Verify archived labels are complete and exact for the evaluated subset.
if len(detail_rows) != len(archived):
    raise RuntimeError(f"Row-count mismatch: reconstructed={len(detail_rows)}, archived={len(archived)}")
print(f"Post-hoc G-Q0 complete: {len(detail_rows)} cover/message/configuration rows")
print(f"Exact feasibility agreement with 1ter: {sum(r['feasible'] == archived[(r['cover'], r['descriptor'], r['B'], r['family'], r['message_index'])] for r in detail_rows)}/{len(detail_rows)}")
print(f"Outputs: {OUT}")
