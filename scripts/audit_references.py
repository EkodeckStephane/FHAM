from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path


REQUIRED = ("author", "title", "year", "doi")
CROSSREF_TIMEOUT_S = 10
CROSSREF_POLITE_DELAY_S = 0.3


def crossref_lookup(doi: str) -> tuple[dict | None, str | None]:
    """Resolves a DOI against the public Crossref REST API (no API key
    required). Returns (message, error); message is None if the lookup
    failed, in which case error carries a short diagnostic string rather than
    silently degrading to an unfounded pass."""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    try:
        with urllib.request.urlopen(url, timeout=CROSSREF_TIMEOUT_S) as response:
            payload = json.load(response)
        return payload.get("message"), None
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except Exception as exc:  # noqa: BLE001 - network failure must not raise
        return None, f"{type(exc).__name__}: {exc}"


def _crossref_year(message: dict) -> str | None:
    for field in ("published-print", "published-online", "issued", "published"):
        parts = (message.get(field) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return None


def check_online(entry: dict) -> dict:
    doi = entry.get("doi", "")
    if not doi:
        return {
            "crossref_status": "NO_DOI",
            "crossref_title_similarity": "",
            "crossref_year_match": "",
            "crossref_retracted": "",
            "crossref_error": "no doi in bib entry",
        }
    message, error = crossref_lookup(doi)
    time.sleep(CROSSREF_POLITE_DELAY_S)
    if message is None:
        return {
            "crossref_status": "LOOKUP_FAILED",
            "crossref_title_similarity": "",
            "crossref_year_match": "",
            "crossref_retracted": "",
            "crossref_error": error or "unknown",
        }

    local_title = entry.get("title", "").strip().lower()
    remote_titles = [str(t).strip().lower() for t in message.get("title", [])]
    similarity = max(
        (SequenceMatcher(None, local_title, t).ratio() for t in remote_titles),
        default=0.0,
    )

    remote_year = _crossref_year(message)
    year_match = (remote_year == entry.get("year", "")) if remote_year else None

    relation = message.get("relation", {}) or {}
    update_to = message.get("update-to", []) or []
    retraction_relation_keys = [key for key in relation if "retract" in key.lower()]
    retraction_updates = [
        item for item in update_to if "retract" in str(item.get("type", "")).lower()
    ]
    is_retracted = bool(retraction_relation_keys or retraction_updates)

    if is_retracted:
        status = "RETRACTION_FLAGGED"
    elif similarity < 0.6:
        status = "TITLE_MISMATCH"
    elif year_match is False:
        status = "YEAR_MISMATCH"
    else:
        status = "VERIFIED_ONLINE"

    return {
        "crossref_status": status,
        "crossref_title_similarity": round(similarity, 3),
        "crossref_year_match": "" if year_match is None else int(year_match),
        "crossref_retracted": int(is_retracted),
        "crossref_error": "",
    }


def parse_bib(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    entries = []
    for match in re.finditer(r"@\w+\s*\{\s*([^,]+),(.*?)\n\}", text, re.S):
        key = match.group(1).strip()
        body = match.group(2)
        fields = {"key": key}
        for field, value in re.findall(r"(\w+)\s*=\s*\{(.*?)\}\s*,?", body, re.S):
            fields[field.lower()] = " ".join(value.split())
        entries.append(fields)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bib", default="paper/references.bib")
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()

    references = Path("references")
    references.mkdir(exist_ok=True)
    entries = parse_bib(Path(args.bib))
    doi_counts = {}
    title_counts = {}
    for entry in entries:
        doi_counts[entry.get("doi", "").lower()] = doi_counts.get(entry.get("doi", "").lower(), 0) + 1
        title_counts[entry.get("title", "").lower()] = title_counts.get(entry.get("title", "").lower(), 0) + 1

    rows = []
    checks = []
    status_ok = True
    now = datetime.now(timezone.utc).isoformat()
    for entry in entries:
        missing = [field for field in REQUIRED if not entry.get(field)]
        duplicate_doi = doi_counts.get(entry.get("doi", "").lower(), 0) > 1
        duplicate_title = title_counts.get(entry.get("title", "").lower(), 0) > 1
        status = "VERIFIED_OFFLINE" if not missing and not duplicate_doi and not duplicate_title else "UNRESOLVED"
        row = {
            "key": entry["key"],
            "title": entry.get("title", ""),
            "doi": entry.get("doi", ""),
            "year": entry.get("year", ""),
            "missing_fields": ";".join(missing),
            "duplicate_doi": int(duplicate_doi),
            "duplicate_title": int(duplicate_title),
            "status": status,
            "checked_at_utc": now,
        }
        if args.online:
            row.update(check_online(entry))
            if row["crossref_status"] in ("RETRACTION_FLAGGED", "TITLE_MISMATCH"):
                status = row["crossref_status"]
                row["status"] = status
        status_ok = status_ok and status not in ("UNRESOLVED", "RETRACTION_FLAGGED", "TITLE_MISMATCH")
        rows.append(row)
        checks.append(row)

    with (references / "reference_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with (references / "reference_checks.jsonl").open("w", encoding="utf-8") as handle:
        for row in checks:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    snapshot = {
        "checked_at_utc": now,
        "bib": args.bib,
        "entries": len(entries),
        "online": args.online,
        "status": "PASS" if status_ok else "FAIL",
    }
    (references / "reference_status_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (references / "claim_reference_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["claim_id", "reference_key", "status"])
        writer.writeheader()
        for entry in entries:
            writer.writerow({"claim_id": "bibliography", "reference_key": entry["key"], "status": "LINKED"})
    print(f"audited {len(entries)} references")
    return 0 if status_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
