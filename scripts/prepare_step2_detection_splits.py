#!/usr/bin/env python3
"""Group identical D-msg contents and freeze the 400/200/1000 session split."""
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/step2/detection"
FAMILIES = ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes")
SPLIT_COUNTS = {"train": 500, "validation": 250, "test": 1250}  # messages per family


def _subset(items, target):
    reachable = {0: []}
    for group_index, size in enumerate(items):
        for current in sorted(list(reachable), reverse=True):
            nxt = current + size
            if nxt <= target and nxt not in reachable:
                reachable[nxt] = reachable[current] + [group_index]
        if target in reachable:
            return reachable[target]
    return None


def _stable_groups(frame):
    grouped = frame.groupby("sha256").agg(
        n=("candidate_id", "count"), ids=("candidate_id", lambda x: list(x)),
    ).reset_index()
    grouped["order_key"] = grouped.sha256.map(
        lambda value: hashlib.sha256(b"FHAM-D-SPLIT-v1" + bytes.fromhex(value)).hexdigest())
    return grouped.sort_values("order_key").reset_index(drop=True)


def main():
    data = pd.read_csv(OUT / "dmsg_selected_2000_per_family.csv.gz")
    if len(data) != 8000 or not data.groupby("family").size().eq(2000).all():
        raise RuntimeError("expected 2,000 feasible retained messages per family")
    split_by_hash = {}
    feasibility = {}
    for family in FAMILIES:
        groups = _stable_groups(data[data.family == family])
        remaining = list(range(len(groups)))
        for split in ("train", "validation"):
            goal = SPLIT_COUNTS[split]
            sizes = [int(groups.iloc[i].n) for i in remaining]
            selected_local = _subset(sizes, goal)
            if selected_local is None:
                raise RuntimeError(f"exact grouped {split} quota cannot be met for {family}")
            selected_indices = [remaining[i] for i in selected_local]
            for index in selected_indices:
                split_by_hash[str(groups.iloc[index].sha256)] = split
            selected_set = set(selected_indices)
            remaining = [i for i in remaining if i not in selected_set]
        if sum(int(groups.iloc[i].n) for i in remaining) != SPLIT_COUNTS["test"]:
            raise RuntimeError(f"grouped test quota cannot be met for {family}")
        for index in remaining:
            split_by_hash[str(groups.iloc[index].sha256)] = "test"
        feasibility[family] = {"unique_hashes": len(groups),
                               "messages_per_split": SPLIT_COUNTS}
    data["split"] = data.sha256.astype(str).map(split_by_hash)
    if data.split.isna().any():
        raise RuntimeError("some message content was not assigned to a split")
    if data.groupby(["sha256", "split"]).size().groupby(level=0).size().gt(1).any():
        raise RuntimeError("identical content crosses partitions")
    if set(data.groupby(["family", "split"]).size().tolist()) != {500, 250, 1250}:
        raise RuntimeError("per-family split quotas do not match the protocol")
    # FHAM and control sessions use the same five source messages and cadence.
    sessions = []
    session_ids = {"train": 0, "validation": 0, "test": 0}
    for split, n_sessions in (("train", 400), ("validation", 200), ("test", 1000)):
        per_family = {family: data[(data.split == split) & (data.family == family)]
                      .sort_values("candidate_id").to_dict(orient="records") for family in FAMILIES}
        if any(len(per_family[f]) != 5 * n_sessions // 4 for f in FAMILIES):
            raise RuntimeError(f"unexpected per-family allocation in {split}")
        cursors = {family: 0 for family in FAMILIES}
        for local_session in range(n_sessions):
            extra_family = FAMILIES[local_session % len(FAMILIES)]
            chosen = []
            for family in FAMILIES:
                chosen.append((family, per_family[family][cursors[family]]))
                cursors[family] += 1
            chosen.append((extra_family, per_family[extra_family][cursors[extra_family]]))
            cursors[extra_family] += 1
            sid = f"{split}_{local_session:04d}"
            for position, (family, row) in enumerate(chosen):
                sessions.append({"split": split, "session_id": sid,
                                 "record_index": position, "family": family,
                                 "candidate_id": row["candidate_id"],
                                 "message_sha256": row["sha256"],
                                 "source_path": row["path"]})
    session_data = pd.DataFrame(sessions)
    counts = session_data.groupby(["split", "session_id"]).size()
    if not counts.eq(5).all() or session_data.message_sha256.isna().any():
        raise RuntimeError("each frozen session must contain five messages")
    data.to_csv(OUT / "dmsg_grouped_partitions.csv.gz", index=False, compression="gzip")
    session_data.to_csv(OUT / "dmsg_sessions.csv", index=False)
    metadata = {"grouping_key": "message SHA-256", "counts_per_split": {
                    "train_sessions": 400, "validation_sessions": 200, "test_sessions": 1000,
                    "records_per_session": 5},
                "records_per_family_split": SPLIT_COUNTS,
                "content_groups_cross_split": False,
                "sessions_per_condition": 1600,
                "total_source_records_per_condition": 8000,
                "family_group_details": feasibility,
                "candidate_manifest_sha256": hashlib.sha256(
                    (OUT / "dmsg_candidates.csv").read_bytes()).hexdigest()}
    (OUT / "dmsg_session_split_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(session_data.groupby("split").session_id.nunique().to_string())
    print(session_data.groupby(["split", "family"]).candidate_id.count().to_string())
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
