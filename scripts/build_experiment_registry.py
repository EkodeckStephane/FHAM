from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

RAW_GLOBS = [
    Path("results").glob("*_raw.csv"),
    Path("results/processed/benchmark_smoke").glob("*_raw.csv"),
]

CANDIDATE_KEY_COLUMNS = [
    "image",
    "descriptor",
    "method",
    "family",
    "length",
    "message_bytes",
    "bound",
    "lambda",
    "attack",
]


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize(path: Path) -> dict:
    rows = load_rows(path)
    summary = {
        "file": path.as_posix(),
        "trials": len(rows),
    }
    if not rows:
        return summary
    columns = rows[0].keys()
    for column in CANDIDATE_KEY_COLUMNS:
        if column in columns:
            values = sorted({row[column] for row in rows if row.get(column) not in (None, "")})
            summary[f"distinct_{column}"] = len(values)
            summary[f"values_{column}"] = values
    return summary


def coverage(declared: list, observed_by_file: dict[str, set[str]], label: str) -> list[dict]:
    rows = []
    for value in declared:
        exercised_in = [
            name for name, values in observed_by_file.items() if str(value) in values
        ]
        rows.append(
            {
                "parameter": label,
                "declared_value": value,
                "exercised": bool(exercised_in),
                "exercised_in_files": "; ".join(sorted(exercised_in)),
            }
        )
    return rows


def main() -> int:
    config = yaml.safe_load(Path("config/experiments.yaml").read_text(encoding="utf-8"))
    files = sorted(
        {path for pattern in RAW_GLOBS for path in pattern}, key=lambda p: p.as_posix()
    )
    summaries = [summarize(path) for path in files]

    observed = {
        "descriptor": {},
        "method": {},
        "family": {},
        "length": {},
        "message_bytes": {},
        "bound": {},
        "lambda": {},
        "attack": {},
    }
    for path in files:
        rows = load_rows(path)
        if not rows:
            continue
        columns = rows[0].keys()
        for key in observed:
            if key in columns:
                observed[key][path.as_posix()] = {
                    row[key] for row in rows if row.get(key) not in (None, "")
                }

    coverage_rows = []
    coverage_rows += coverage(config.get("descriptors", []), observed["descriptor"], "descriptor")
    coverage_rows += coverage(
        config.get("assignment_methods", []), observed["method"], "assignment_method"
    )
    coverage_rows += coverage(
        config.get("message_families", []), observed["family"], "message_family"
    )
    length_observed = {
        name: values | observed["message_bytes"].get(name, set())
        for name, values in observed["length"].items()
    }
    for name, values in observed["message_bytes"].items():
        length_observed.setdefault(name, set()).update(values)
    coverage_rows += coverage(
        config.get("message_lengths_bytes", []), length_observed, "message_length_bytes"
    )
    coverage_rows += coverage(config.get("bounds", []), observed["bound"], "bound")
    coverage_rows += coverage(config.get("lambdas", []), observed["lambda"], "lambda")
    coverage_rows += coverage(config.get("transforms", []), observed["attack"], "transform")

    registry_path = Path("results/acceptance/experiment_registry.csv")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["file", "trials"] + [
            f"distinct_{column}" for column in CANDIDATE_KEY_COLUMNS
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summaries)

    coverage_path = Path("results/acceptance/parameter_coverage.csv")
    with coverage_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["parameter", "declared_value", "exercised", "exercised_in_files"],
        )
        writer.writeheader()
        writer.writerows(coverage_rows)

    total_trials = sum(item["trials"] for item in summaries)
    unexercised = [row for row in coverage_rows if not row["exercised"]]

    lines = [
        "# Experiment Inventory",
        "",
        f"Total raw-result files: {len(summaries)}",
        f"Total logged trials across all raw files: {total_trials}",
        f"Declared parameter values never exercised in any raw file: {len(unexercised)}",
        "",
        "## Raw Result Files",
        "",
        "| File | Trials | Distinct images | Distinct lengths | Distinct methods/descriptors |",
        "|---|---|---|---|---|",
    ]
    for item in summaries:
        lines.append(
            "| {file} | {trials} | {images} | {lengths} | {methods} |".format(
                file=item["file"],
                trials=item["trials"],
                images=item.get("distinct_image", "-"),
                lengths=item.get("distinct_length", item.get("distinct_message_bytes", "-")),
                methods=item.get("distinct_method", item.get("distinct_descriptor", "-")),
            )
        )
    lines += [
        "",
        "## Declared-Parameter Coverage (config/experiments.yaml)",
        "",
        "Parameters declared in the central experiment registry but never observed",
        "in any raw result file are listed below; they are declared for future",
        "extension and are not claimed as executed in the current manuscript.",
        "",
        "| Parameter | Value | Exercised |",
        "|---|---|---|",
    ]
    for row in coverage_rows:
        lines.append(
            f"| {row['parameter']} | {row['declared_value']} | {'yes' if row['exercised'] else 'NO'} |"
        )

    Path("reports/experiment_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"raw files: {len(summaries)}, total trials: {total_trials}, unexercised declared values: {len(unexercised)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
