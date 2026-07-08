from __future__ import annotations

import subprocess
import sys
from pathlib import Path


COMMANDS = [
    [sys.executable, "scripts/generate_messages.py"],
    [sys.executable, "scripts/prepare_datasets.py", "--download-missing", "--strict"],
    [sys.executable, "-m", "pytest", "-q"],
    [sys.executable, "scripts/evaluate_benchmarks.py"],
    [sys.executable, "run_pipeline.py"],
    [sys.executable, "scripts/write_provenance.py"],
    [sys.executable, "scripts/audit_references.py"],
    [sys.executable, "scripts/build_experiment_registry.py"],
    [sys.executable, "scripts/compile_paper.py", "--strict"],
    [sys.executable, "scripts/acceptance_gate.py"],
]

# Not included above because they are slow (minutes to about an hour) and are
# not required by the acceptance gate; run them explicitly before a final
# submission pass:
#   python scripts/select_descriptor.py             (~2 minutes)
#   python scripts/run_stratified_robustness.py      (~1 hour; 2000 images per corpus)
#   python scripts/audit_references.py --online      (~10 seconds; requires network)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    status = 0
    for command in COMMANDS:
        print("running:", " ".join(command))
        result = subprocess.run(command, cwd=root)
        if result.returncode:
            status = result.returncode
            break
    return status


if __name__ == "__main__":
    raise SystemExit(main())
