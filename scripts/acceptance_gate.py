from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


CHECKS = [
    ("bossbase_manifest", Path("dataset/manifests/bossbase.csv"), 10000),
    ("bows2_manifest", Path("dataset/manifests/bows2.csv"), 10000),
    ("coco2017_val_manifest", Path("dataset/manifests/coco2017_val.csv"), 5000),
    ("messages", Path("dataset/message_manifests/message_seeds.csv"), 160),
    ("reference_audit", Path("references/reference_audit.csv"), 14),
    ("supplement_pdf", Path("paper/build/supplement_fham.pdf"), None),
    ("article_pdf", Path("paper/build/article_fham.pdf"), None),
]


def count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    failures = []
    passes = []
    for name, path, expected_rows in CHECKS:
        if expected_rows is None:
            ok = path.exists()
            observed = None
        else:
            observed = count_rows(path)
            ok = observed == expected_rows
        record = {"condition": name, "path": str(path), "observed_rows": observed}
        if ok:
            passes.append(record)
        else:
            record["corrective_action"] = "create or regenerate this artefact with the strict reproduction pipeline"
            failures.append(record)

    claim_path = Path("results/acceptance/claim_evidence_matrix.csv")
    unresolved = []
    if claim_path.exists():
        with claim_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("status", "").upper() == "UNRESOLVED":
                    unresolved.append(row.get("claim_id", "unknown"))
    else:
        unresolved.append("missing_claim_matrix")
    if unresolved:
        failures.append(
            {
                "condition": "claim_matrix",
                "path": str(claim_path),
                "observed_rows": len(unresolved),
                "unresolved_or_weakened_claims": unresolved,
                "corrective_action": "resolve, weaken in manuscript, or remove these claims before strict acceptance",
            }
        )
    else:
        passes.append({"condition": "claim_matrix", "path": str(claim_path), "observed_rows": count_rows(claim_path)})

    verdict = "MANUSCRIT PRET POUR SOUMISSION" if not failures else "MANUSCRIT NON PRET POUR SOUMISSION"
    data = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "verdict": verdict,
        "passed_checks": passes,
        "failures": failures,
    }
    output_dir = Path("results/acceptance")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "acceptance_gate.json").write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )
    reports = Path("reports")
    reports.mkdir(exist_ok=True)
    lines = ["# Acceptance Gate", "", f"## Verdict", "", verdict, ""]
    if failures:
        lines.extend(["## Failures", ""])
        for failure in failures:
            lines.append(f"- {failure['condition']}: {failure['path']} observed={failure['observed_rows']}")
    (reports / "acceptance_gate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(verdict)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
