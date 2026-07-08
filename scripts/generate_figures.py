from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fham.visualization import bounded_plot, capacity_plot, channel_plot, robustness_plot

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUTPUT_DIR = ROOT / "paper" / "figures" / "generated"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


FIGURES = [
    ("fig_capacity.png", "capacity.csv", capacity_plot),
    ("fig_auxiliary_channel.png", "auxiliary_channel.csv", channel_plot),
    ("fig_bounded_assignment.png", "bounded_assignment.csv", bounded_plot),
    ("fig_robustness.png", "robustness.csv", robustness_plot),
]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    commit = git_commit()
    now = datetime.now(timezone.utc).isoformat()
    for figure_name, csv_name, plot_fn in FIGURES:
        csv_path = RESULTS / csv_name
        data = pd.read_csv(csv_path)
        output_path = OUTPUT_DIR / figure_name
        plot_fn(data, output_path)
        provenance = {
            "script": "scripts/generate_figures.py",
            "command": f"python scripts/generate_figures.py",
            "git_commit": commit,
            "input_files": [str(csv_path.relative_to(ROOT))],
            "input_sha256": {str(csv_path.relative_to(ROOT)): sha256(csv_path)},
            "generated_at_utc": now,
            "output_file": str(output_path.relative_to(ROOT)),
            "output_sha256": sha256(output_path),
        }
        provenance_path = output_path.with_suffix(".provenance.json")
        provenance_path.write_text(
            json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"wrote {output_path.relative_to(ROOT)} + provenance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
