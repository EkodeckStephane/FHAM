"""Post-hoc D6/D7 diagnostics on saved 1ter D outputs only.

No images are opened and no new perturbations are generated. D6 reports both
the protocol's random-parity surrogate and exact parity from reedsolo (the
surrogate is not treated as a bound on the actual RS code). D7 analyzes saved
hash histograms and per-byte Hall-window overloads.
"""
from __future__ import annotations

import csv
import gzip
import math
import zlib
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

import numpy as np
from reedsolo import RSCodec

from fham_matching import max_matching

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1ter"
GQ0 = BASE / "audit_diagnostics" / "GQ0_posthoc"
OUT = GQ0
DESCRIPTOR = "mean_ordinal"
BOUNDS = (4, 8)
PERCENTAGES = (0, 10, 20, 30, 40)
PARITY_SEED = 20261120


def rows_in(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


# Gather saved position hashes for both all positions and the exact robust set.
all_hashes: dict[str, list[int]] = defaultdict(list)
robust_hashes: dict[str, list[int]] = defaultdict(list)
for path in sorted((BASE / "step4b_screen").glob("*_positions.csv.gz")):
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["descriptor"] == DESCRIPTOR:
                cover = row["cover"]
                value = int(row["hash_value"])
                all_hashes[cover].append(value)
                if int(row["robust"]):
                    robust_hashes[cover].append(value)
if len(robust_hashes) != 100:
    raise RuntimeError(f"Expected 100 already-open D covers; found {len(robust_hashes)}")

messages = []
for family in ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated"):
    for index in range(3):
        raw = (ROOT / "dataset" / "messages" / family / f"{family}_100_{index:02d}.bin").read_bytes()
        payload = zlib.compress(raw, 9)
        messages.append((family, index, len(raw), payload))


def make_codeword(payload: bytes, pct: int, mode: str, family: str, index: int) -> tuple[bytes, int]:
    if pct == 0:
        return payload, 0
    parity = math.ceil(pct * len(payload) / 100)
    if mode == "random_surrogate":
        # Fixed, message-specific parity stream shared across covers.
        seed = PARITY_SEED + pct * 1009 + index * 97 + sum(family.encode("ascii"))
        tail = np.random.default_rng(seed).integers(0, 256, size=parity, dtype=np.uint8).tobytes()
        return payload + tail, parity
    if mode == "reedsolo_exact":
        codec = RSCodec(nsym=parity, nsize=255, fcr=0, generator=2, prim=0x11D, c_exp=8)
        encoded = bytes(codec.encode(payload))
        if len(encoded) != len(payload) + parity:
            raise RuntimeError("Unexpected RS codeword length")
        return encoded, parity
    raise ValueError(mode)


# D6: calculate maximum matching deficiency on the extended word. For exact RS,
# d<=P is a necessary erasure-capacity condition on a perfect channel. For the
# random surrogate, the same test is only a sensitivity scenario.
d6_rows = []
for mode in ("random_surrogate", "reedsolo_exact"):
    words = {}
    for family, index, source_n, payload in messages:
        for pct in PERCENTAGES:
            words[(family, index, pct)] = make_codeword(payload, pct, mode, family, index)
    for cover, hashes in sorted(robust_hashes.items()):
        for bound in BOUNDS:
            candidate_by_byte = [
                [j for j, h in enumerate(hashes) if abs(h - target) <= bound]
                for target in range(256)
            ]
            for family, index, source_n, payload in messages:
                for pct in PERCENTAGES:
                    word, parity = words[(family, index, pct)]
                    adjacency = [candidate_by_byte[symbol] for symbol in word]
                    matched = max_matching(adjacency, len(hashes))
                    deficit = len(word) - matched
                    d6_rows.append({
                        "cover": cover, "descriptor": DESCRIPTOR, "B": bound,
                        "family": family, "message_index": index,
                        "source_bytes": source_n, "compressed_symbols_Lc": len(payload),
                        "parity_pct": pct, "parity_symbols_P": parity,
                        "codeword_symbols_Lcw": len(word), "parity_mode": mode,
                        "deficit_d": deficit, "d_le_P_perfect_channel_necessary": int(deficit <= parity),
                    })

with (OUT / "D6_codeword_deficit.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(d6_rows[0]))
    w.writeheader()
    w.writerows(d6_rows)

# D6 at p=0 must reproduce the already-audited G-Q0 feasibility labels exactly.
gq0_map = {
    (r["cover"], int(r["B"]), r["family"], int(r["message_index"])): int(r["feasible"])
    for r in rows_in(GQ0 / "message_deficits.csv")
    if r["descriptor"] == DESCRIPTOR and int(r["B"]) in BOUNDS
}
for row in d6_rows:
    if row["parity_pct"] == 0:
        key = (row["cover"], row["B"], row["family"], row["message_index"])
        if row["d_le_P_perfect_channel_necessary"] != gq0_map[key]:
            raise RuntimeError(f"D6 p=0 did not reproduce G-Q0 for {key}")

d6_summary = []
groups: dict[tuple, list[dict]] = defaultdict(list)
for row in d6_rows:
    groups[(row["parity_mode"], row["B"], row["parity_pct"])].append(row)
for (mode, bound, pct), rows in sorted(groups.items()):
    deficits = np.asarray([r["deficit_d"] for r in rows], dtype=float)
    d6_summary.append({
        "parity_mode": mode, "B": bound, "parity_pct": pct,
        "cover_message_cases": len(rows),
        "mean_Lc": float(np.mean([r["compressed_symbols_Lc"] for r in rows])),
        "mean_P": float(np.mean([r["parity_symbols_P"] for r in rows])),
        "mean_Lcw": float(np.mean([r["codeword_symbols_Lcw"] for r in rows])),
        "median_deficit_d": float(np.median(deficits)),
        "q90_deficit_d": float(np.quantile(deficits, .90)),
        "q99_deficit_d": float(np.quantile(deficits, .99)),
        "max_deficit_d": int(np.max(deficits)),
        "fraction_d_le_P": float(np.mean([r["d_le_P_perfect_channel_necessary"] for r in rows])),
    })
with (OUT / "D6_summary.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(d6_summary[0]))
    w.writeheader()
    w.writerows(d6_summary)

# D7: quantify concentration of robust hash values versus all positions.
hist_rows = []
concentration_rows = []
def entropy_counts(counts: Counter, total: int) -> float:
    if total == 0:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts.values() if n)

for cover in sorted(robust_hashes):
    for label, values in (("all", all_hashes[cover]), ("robust", robust_hashes[cover])):
        counts = Counter(values)
        total = len(values)
        entropy = entropy_counts(counts, total)
        ordered = sorted(counts.values(), reverse=True)
        concentration_rows.append({
            "cover": cover, "pool": label, "positions": total,
            "distinct_values": len(counts), "entropy_bits": entropy,
            "effective_support_2H": 2 ** entropy,
            "top1_fraction": ordered[0] / total if total else 0,
            "top10_fraction": sum(ordered[:10]) / total if total else 0,
        })
        for value in range(256):
            hist_rows.append({"cover": cover, "pool": label, "hash_value": value,
                              "position_count": counts[value]})
with (OUT / "D7_hash_histogram_by_cover.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(hist_rows[0]))
    w.writeheader()
    w.writerows(hist_rows)
with (OUT / "D7_concentration_by_cover.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(concentration_rows[0]))
    w.writeheader()
    w.writerows(concentration_rows)

# Per-symbol-value neighborhood overload. A target byte is saturated when its
# multiplicity in the message exceeds all robust positions in its +/-B window.
# This is a singleton Hall violation; absence of such a violation does not rule
# out a multi-value Hall violation caused by overlapping windows.
window_rows = []
message_window_rows = []
for cover, hashes in sorted(robust_hashes.items()):
    for bound in BOUNDS:
        candidate_counts = [sum(abs(h - target) <= bound for h in hashes) for target in range(256)]
        for family, index, _source_n, payload in messages:
            demand = Counter(payload)
            overloaded = []
            total_shortage = 0
            for value, load in sorted(demand.items()):
                capacity = candidate_counts[value]
                if load > capacity:
                    shortage = load - capacity
                    total_shortage += shortage
                    overloaded.append(value)
                    window_rows.append({
                        "cover": cover, "B": bound, "family": family,
                        "message_index": index, "target_byte": value,
                        "symbol_demand": load, "robust_candidates_in_window": capacity,
                        "singleton_hall_shortage": shortage,
                    })
            message_window_rows.append({
                "cover": cover, "B": bound, "family": family, "message_index": index,
                "compressed_symbols": len(payload), "distinct_target_bytes": len(demand),
                "saturated_target_byte_values": len(overloaded),
                "total_singleton_shortage": total_shortage,
            })
with (OUT / "D7_saturated_windows.csv").open("w", newline="", encoding="utf-8") as f:
    fields = ["cover", "B", "family", "message_index", "target_byte", "symbol_demand",
              "robust_candidates_in_window", "singleton_hall_shortage"]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(window_rows)
with (OUT / "D7_message_window_summary.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(message_window_rows[0]))
    w.writeheader()
    w.writerows(message_window_rows)

# Relate singleton-window overloads to the already computed Hall residual.
gq0_rows = list(rows_in(GQ0 / "message_deficits.csv"))
window_lookup = {(r["cover"], int(r["B"]), r["family"], int(r["message_index"])): r
                 for r in message_window_rows}
hall_compare = []
for row in gq0_rows:
    if row["descriptor"] != DESCRIPTOR or int(row["B"]) not in BOUNDS:
        continue
    w = window_lookup[(row["cover"], int(row["B"]), row["family"], int(row["message_index"]))]
    hall_compare.append({
        "cover": row["cover"], "B": row["B"], "family": row["family"],
        "message_index": row["message_index"], "deficit_d": row["deficit_d"],
        "d_empty": row["d_empty"], "d_Hall": row["d_Hall"], "feasible": row["feasible"],
        "saturated_target_byte_values": w["saturated_target_byte_values"],
        "total_singleton_shortage": w["total_singleton_shortage"],
    })
with (OUT / "D7_hall_vs_singleton_windows.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(hall_compare[0]))
    w.writeheader()
    w.writerows(hall_compare)

print(f"D6/D7 complete; D6 rows={len(d6_rows)}, Reed-Solomon library={version('reedsolo')}")
print(f"Outputs: {OUT}")
