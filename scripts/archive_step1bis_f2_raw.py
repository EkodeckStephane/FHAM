"""Pack per-cover Step 1bis F2 CSV chunks into stage-level gzip artifacts."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "stability_step1" / "step1bis" / "stability_F2"

for stage in ("A", "B"):
    folder = BASE / stage
    expected = 100 if stage == "A" else 200
    for kind in ("assignments", "recovery", "feasibility"):
        chunks = sorted(folder.glob(f"*_{kind}.csv.gz"))
        if len(chunks) != expected:
            raise RuntimeError(f"{stage}/{kind}: expected {expected} chunks, found {len(chunks)}")
        frame = pd.concat((pd.read_csv(path) for path in chunks), ignore_index=True)
        target = BASE / f"{stage}_raw_{kind}.csv.gz"
        frame.to_csv(target, index=False, compression="gzip")
        print(f"{target.name}: {len(frame)} rows from {len(chunks)} covers")
