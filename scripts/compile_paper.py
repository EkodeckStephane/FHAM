from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    paper = Path("paper")
    build = paper / "build"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    required = [
        paper / "fig_capacity.png",
        paper / "fig_bounded_assignment.png",
        paper / "fig_auxiliary_channel.png",
        paper / "fig_robustness.png",
        Path("references/reference_audit.csv"),
        Path("results/acceptance/claim_evidence_matrix.csv"),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing and args.strict:
        print("missing required compile inputs:", "; ".join(missing))
        return 1
    for tex in ("article_fham.tex", "supplement_fham.tex", "cover_letter_fham.tex"):
        if not (paper / tex).exists():
            if args.strict:
                print(f"missing {paper / tex}")
                return 1
            continue
        run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex], paper)
        run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex], paper)
        pdf = paper / tex.replace(".tex", ".pdf")
        if pdf.exists():
            shutil.copy2(pdf, build / pdf.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
