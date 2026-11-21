#!/usr/bin/env python3
"""Create the immutable G-Q2 selection lock before any E pixels are read."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stability_step1/step1quater/run"
MANIFEST = ROOT / "results/stability_step1/step1quater/manifest"


def sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    selected = json.loads((OUT / "selected_configuration.json").read_text(encoding="utf-8"))
    if selected.get("G_Q2") != "green" or selected.get("selected") is None:
        raise RuntimeError("G-Q2 is not green; no E validation lock may be created")
    checks = json.loads((OUT / "quality_checks_and_GQ2.json").read_text(encoding="utf-8"))
    if checks["grid_rows"] != 192000 or checks["grid_cells"] != 160 or checks["grid_message_count"] != 12:
        raise RuntimeError("The complete primary grid has not passed the row-count checks")
    expected_files = [
        OUT / "robustness_summary.csv", OUT / "A1_by_cover_message.csv",
        OUT / "A1_joint_summary.csv", OUT / "A1_Lsrc_star.csv",
        OUT / "grid_trials_12x100.csv.gz", OUT / "grid_summary.csv",
        OUT / "A4_segmented_trials.csv.gz", OUT / "A4_segmented_summary.csv",
        OUT / "selected_config_cluster_bootstrap_10000.csv.gz",
        OUT / "selected_config_cluster_bootstrap_summary.csv",
        OUT / "H12_H14_paired_permutation.csv", OUT / "H12_H14_descriptive.csv",
        OUT / "H14_independence_diagnostic.json",
    ]
    for path in expected_files:
        if not path.is_file():
            raise RuntimeError(f"Required pre-E artifact missing: {path.name}")
    lock_path = OUT / "GQ2_configuration_freeze.json"
    if lock_path.exists():
        raise RuntimeError("G-Q2 lock already exists; refusing to overwrite it")
    lock = {
        "protocol": "FHAM-1quater-v1",
        "stage": "D-b G-Q2 selected configuration frozen before E pixel access",
        "branch": git("branch", "--show-current"),
        "source_commit": git("rev-parse", "HEAD"),
        "source_commit_is_clean": not bool(git("status", "--porcelain")),
        "selected_configuration": selected["selected"],
        "selection_rule": selected["selection_rule"],
        "G_Q2": selected["G_Q2"],
        "eligible_cells": selected["eligible_cells"],
        "D_b_image_manifest_sha256": sha(MANIFEST / "D_b_images_sha256.csv"),
        "message_manifest_sha256": sha(MANIFEST / "messages_sha256.csv"),
        "seed_schedule_sha256": sha(MANIFEST / "seed_schedule.json"),
        "protocol_sha256": sha(ROOT / "protocols/FHAM_etape_1quater_preregistre.md"),
        "artifacts_sha256": {p.name: sha(p) for p in expected_files},
        "analysis_code_sha256": {
            name: sha(ROOT / "scripts" / name) for name in (
                "run_step1quater.py", "run_step1quater_segmented.py",
                "summarize_step1quater.py", "analyze_step1quater_stats.py")
        },
        "E_pixels_opened": False,
        "C_pixels_opened": False,
        "F_pixels_opened": False,
        "G_Q3_authorized_by_frozen_protocol": True,
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"lock": str(lock_path.relative_to(ROOT)),
                      "source_commit": lock["source_commit"],
                      "config": lock["selected_configuration"],
                      "E_pixels_opened": False}, indent=2))


if __name__ == "__main__":
    main()
