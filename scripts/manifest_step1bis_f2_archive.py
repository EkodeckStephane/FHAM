"""Write SHA-256 manifest for the consolidated Step 1bis F2 archive."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1bis" / "stability_F2"
files = [
    "A_raw_assignments.csv.gz", "A_raw_recovery.csv.gz", "A_raw_feasibility.csv.gz",
    "A_configuration_summary.csv", "A_cover_configuration_metrics.csv",
    "A_cover_transform_metrics.csv", "A_run.json", "frozen_selection_A.json",
    "B_raw_assignments.csv.gz", "B_raw_recovery.csv.gz", "B_raw_feasibility.csv.gz",
    "B_configuration_summary.csv", "B_transform_summary.csv", "B_all_path_summary.csv",
    "B_family_path_summary.csv", "B_cover_configuration_metrics.csv",
    "B_cover_transform_metrics.csv", "B_G_A1_cells.csv", "B_G_A1_configurations.csv",
    "B_G_A2_paired_deltas.csv", "B_gate_verdict.json", "B_run.json",
    "rapport_F2_1bis.md",
]
manifest = {"description": "Consolidated results and provenance for Step 1bis F2; per-cover working CSV chunks remain locally available and are covered in the stage provenance.",
            "files": {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest()
                      for name in files}}
(BASE / "archive_sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"Wrote checksum manifest for {len(files)} artifacts")
