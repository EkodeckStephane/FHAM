"""Summarize already-frozen Step 1ter ceiling and robust-hash outputs.

This is a read-only audit utility: it does not open source image pixels or
launch additional experiments.
"""
from __future__ import annotations

import csv
import gzip
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1ter"
OUT = BASE / "audit_diagnostics"
OUT.mkdir(parents=True, exist_ok=True)


def rows_in(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        yield from csv.DictReader(stream)


# The assignment result is duplicated for the two channel attacks. Count each
# cover/message once, then report feasibility by individual message.
message_cover = {}
joint_inputs: dict[tuple, set] = defaultdict(set)
joint_rows = {}
for path in sorted((BASE / "step4b_ceiling").glob("*_ceiling.csv")):
    for row in rows_in(path):
        key = (row["cover"], row["descriptor"], int(row["bound"]),
               int(row["source_length"]), row["family"], int(row["index"]))
        feasible = int(float(row["feasible"]))
        message_cover[key] = feasible
        if key[4] == "ALL12":
            joint_rows[(key[1], key[2], key[3], key[0])] = feasible

msg_groups: dict[tuple, list] = defaultdict(list)
for (cover, desc, bound, source_n, family, index), feasible in message_cover.items():
    if family == "ALL12":
        continue
    msg_groups[(desc, bound, source_n, family, index)].append(feasible)
with (OUT / "per_message_feasibility.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["descriptor", "B", "source_bytes", "family", "message_index", "feasible_covers", "covers", "rate"])
    for key, vals in sorted(msg_groups.items()):
        w.writerow([*key, sum(vals), len(vals), f"{sum(vals)/len(vals):.6f}"])

# Capacity is only summarized at the already measured source lengths (100 and
# 200); no interpolation or new message generation is performed.
caps: dict[tuple, list] = defaultdict(list)
for (desc, bound, source_n, cover), feasible in joint_rows.items():
    caps[(desc, bound, source_n)].append(feasible)
with (OUT / "joint_12_feasibility.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["descriptor", "B", "source_bytes", "covers_feasible_all_12", "covers", "rate"])
    for desc, bound, source_n in sorted({k[:3] for k in caps}):
        vals = caps[(desc, bound, source_n)]
        w.writerow([desc, bound, source_n, sum(vals), len(vals), f"{sum(vals)/len(vals):.6f}"])

# Robust hash-value histogram and target-byte neighborhood coverage. The latter
# is a diagnostic, not a substitute for Hall's condition or message assignment.
hist: dict[tuple, Counter] = defaultdict(Counter)
cover_hist: dict[tuple, Counter] = defaultdict(Counter)
for path in sorted((BASE / "step4b_screen").glob("*_positions.csv.gz")):
    with gzip.open(path, "rt", newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if int(row["robust"]):
                key = (row["descriptor"], path.stem.split("_")[0])
                hv = int(row["hash_value"])
                cover_hist[key][hv] += 1
                hist[(row["descriptor"],)][hv] += 1

with (OUT / "robust_hash_histogram.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["descriptor", "hash_value", "robust_positions_total", "cover_count", "mean_positions_per_cover"])
    for (desc,), counts in sorted(hist.items()):
        by_value = Counter()
        desc_covers = {cover for (d, cover) in cover_hist if d == desc}
        n_covers = len(desc_covers)
        for (d, _cover), c in cover_hist.items():
            if d == desc:
                by_value.update(c)
        for value in range(256):
            count = by_value[value]
            w.writerow([desc, value, count, sum(1 for (d, _), c in cover_hist.items() if d == desc and c[value]),
                        f"{count/n_covers:.6f}"])

with (OUT / "robust_hash_neighborhood_coverage.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["descriptor", "B", "target_byte", "covers_with_no_robust_candidate", "covers", "mean_candidate_positions"])
    for (desc,), counts in sorted(hist.items()):
        by_cover = {cover: c for (d, cover), c in cover_hist.items() if d == desc}
        for bound in (2, 4, 8):
            for target in range(256):
                candidates = [sum(c[v] for v in range(max(0, target-bound), min(255, target+bound)+1)) for c in by_cover.values()]
                w.writerow([desc, bound, target, sum(x == 0 for x in candidates), len(candidates),
                            f"{sum(candidates)/len(candidates):.6f}"])

with (OUT / "fixed_bits_by_profile.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["corpus", "resolution", "L", "positions_M", "B", "token_bits", "residual_bits", "fixed_bits_per_symbol"])
    for corpus, side, block_sizes in (("BOWS2_native_256", 256, (12, 24)), ("BOSSBase_native_512", 512, (12, 24, 36, 48))):
        for L in block_sizes:
            M = 4 * (((side-L)//L)+1)**2
            for B in (2, 4, 8):
                token = math.ceil(math.log2(M))
                residual = math.ceil(math.log2(2*B+1))
                w.writerow([corpus, f"{side}x{side}", L, M, B, token, residual, token+residual])

print(f"Wrote audit tables to {OUT}")
print(f"Unique cover/message feasibility rows: {len(message_cover)}")
print(f"Descriptors in robust-position exports: {len(hist)}")
