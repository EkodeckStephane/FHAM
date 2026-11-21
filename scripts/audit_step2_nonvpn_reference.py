#!/usr/bin/env python3
"""Freeze archive-to-feature provenance for the secondary NonVPN reference."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(r"D:\dataset")
OUT = ROOT / "results/step2/detection"
FEATURES = ROOT / "results/nonvpn_tls_flow_features.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def main():
    archives = sorted(DATA.glob("NonVPN-PCAPs-*.zip"))
    if len(archives) != 3:
        raise RuntimeError(f"expected 3 NonVPN archives, found {len(archives)}")
    member_map = {}
    archive_rows = []
    for archive in archives:
        with zipfile.ZipFile(archive) as zf:
            members = [x for x in zf.infolist()
                       if x.filename.lower().endswith((".pcap", ".pcapng"))]
            archive_rows.append({"archive": archive.name, "pcap_members": len(members),
                                 "compressed_bytes": archive.stat().st_size,
                                 "sha256": sha256(archive)})
            for item in members:
                member_map.setdefault(Path(item.filename).name, []).append(
                    {"archive": archive.name, "member": item.filename,
                     "uncompressed_bytes": item.file_size,
                     "zip_crc32": f"{item.CRC:08x}"})
    source = pd.read_csv(FEATURES, keep_default_na=False)
    used_captures = sorted(source.capture.unique())
    rows = []
    for capture in used_captures:
        matches = member_map.get(capture, [])
        if len(matches) != 1:
            raise RuntimeError(f"capture {capture!r} has {len(matches)} archive matches")
        rows.append({"capture": capture, **matches[0],
                     "flows_in_feature_table": int((source.capture == capture).sum())})
    capture_df = pd.DataFrame(rows)
    capture_df.to_csv(OUT / "nonvpn_reference_capture_manifest.csv", index=False)
    scripts = [ROOT / "scripts/evaluate_nonvpn_tls_detectability.py",
               ROOT / "scripts/analyze_nonvpn_traces.py",
               ROOT / "scripts/traffic_transport_pilot.py"]
    result_files = [FEATURES, ROOT / "results/nonvpn_tls_detectability_cv.csv"]
    metadata = {
        "archives": archive_rows,
        "archive_pcap_member_count": sum(row["pcap_members"] for row in archive_rows),
        "mapped_feature_captures": len(capture_df),
        "mapped_tls_flows": len(source),
        "feature_table_sha256": sha256(FEATURES),
        "script_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in scripts},
        "result_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in result_files if p.exists()},
        "mapping": "each feature capture basename maps uniquely to a PCAP/PCAPNG member in the three source ZIP archives; ZIP member CRC32 and uncompressed size recorded",
        "content_validation_limit": "the 91 mapped PCAP members were not decompressed and reparsed in this audit; archive SHA-256 anchors the source archives and prior extraction script/result hashes anchor the feature artifact",
        "data_writes": "none to D:\\dataset; archives read in place",
    }
    (OUT / "nonvpn_reference_provenance.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"archives": [{"archive": x["archive"], "sha256": x["sha256"]} for x in archive_rows],
                      "members": metadata["archive_pcap_member_count"],
                      "mapped_captures": len(capture_df), "tls_flows": len(source)}, indent=2))


if __name__ == "__main__":
    main()
