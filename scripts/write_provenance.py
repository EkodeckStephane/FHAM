from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path.cwd()
    raw = root / "results" / "raw" / run_id
    processed = root / "results" / "processed" / run_id
    provenance = root / "results" / "provenance" / run_id
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    provenance.mkdir(parents=True, exist_ok=True)

    for csv_path in (root / "results").glob("*.csv"):
        target = raw / csv_path.name if csv_path.name.endswith("_raw.csv") else processed / csv_path.name
        shutil.copy2(csv_path, target)

    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    (provenance / "environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (provenance / "package_versions.txt").open("w", encoding="utf-8") as handle:
        subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=handle, check=False)
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    (provenance / "git_commit.txt").write_text(git.stdout.strip() or "NO_GIT_REPOSITORY", encoding="utf-8")
    (provenance / "command.txt").write_text("python run_pipeline.py --profile full --strict\n", encoding="utf-8")
    if (root / "config" / "experiments.yaml").exists():
        shutil.copy2(root / "config" / "experiments.yaml", provenance / "config_snapshot.yaml")
    dataset_hashes = []
    for manifest in (root / "dataset").glob("**/manifest*.csv"):
        dataset_hashes.append({"path": str(manifest), "sha256": file_hash(manifest)})
    for manifest in (root / "dataset" / "manifests").glob("*.csv"):
        dataset_hashes.append({"path": str(manifest), "sha256": file_hash(manifest)})
    (provenance / "dataset_hashes.csv").write_text(
        "path,sha256\n" + "".join(f"{row['path']},{row['sha256']}\n" for row in dataset_hashes),
        encoding="utf-8",
    )
    (provenance / "start_time_utc.txt").write_text(run_id + "\n", encoding="utf-8")
    (provenance / "end_time_utc.txt").write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")
    paper_run = {
        "run_id": run_id,
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "results": sorted(path.name for path in processed.glob("*.csv")),
        "config_hash": file_hash(root / "config" / "experiments.yaml") if (root / "config" / "experiments.yaml").exists() else None,
        "justification": "latest strict pipeline run",
    }
    (root / "results" / "processed" / "paper_run.json").write_text(
        json.dumps(paper_run, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"wrote provenance run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
