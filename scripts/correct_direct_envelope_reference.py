"""Correct direct AES-GCM byte counts that included the FHAM record header."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
ARCHIVE = RESULTS / "revision_step0" / "legacy_direct_header_13"
OLD_HEADER_BYTES = 13
DIRECT_FORMAT_BYTES = 1
REMOVED_BYTES = OLD_HEADER_BYTES - DIRECT_FORMAT_BYTES


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archived_source(path: Path) -> Path:
    relative = path.relative_to(ROOT)
    archive_path = ARCHIVE / relative
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        shutil.copy2(path, archive_path)
    return archive_path


def correct_raw_file(path: Path, column: str) -> pd.DataFrame:
    original = archived_source(path)
    frame = pd.read_csv(original)
    if column not in frame:
        raise KeyError(f"{column} not found in {path.relative_to(ROOT)}")
    frame[column] = frame[column] - REMOVED_BYTES
    if column == "direct_encrypted_bytes":
        if "encrypted_bytes" in frame:
            frame["fham_to_direct_ratio"] = frame["encrypted_bytes"] / frame[column]
        if "shaped_encrypted_bytes" in frame:
            frame["shaped_to_direct_ratio"] = frame["shaped_encrypted_bytes"] / frame[column]
        if "compact_envelope_bytes" in frame:
            frame["envelope_to_direct_ratio"] = frame["compact_envelope_bytes"] / frame[column]
    frame.to_csv(path, index=False, float_format="%.12g")
    return frame


def auxiliary_summary(raw: pd.DataFrame) -> pd.DataFrame:
    return raw.groupby("length", as_index=False).agg(
        raw_bytes=("raw_bytes", "mean"),
        compressed_bytes=("compressed_bytes", "mean"),
        encrypted_bytes=("encrypted_bytes", "mean"),
        direct_encrypted_bytes=("direct_encrypted_bytes", "mean"),
        fham_to_direct_ratio=("fham_to_direct_ratio", "mean"),
        shaped_record_capacity=("shaped_record_capacity", "first"),
        shaped_encrypted_bytes=("shaped_encrypted_bytes", "mean"),
        shaped_to_direct_ratio=("shaped_to_direct_ratio", "mean"),
        shaped_to_compact_ratio=("shaped_to_compact_ratio", "mean"),
        encrypted_to_message_ratio=("encrypted_to_message_ratio", "mean"),
        shaped_to_message_ratio=("shaped_to_message_ratio", "mean"),
        encrypted_to_cover_ratio=("encrypted_to_cover_ratio", "mean"),
        shaped_to_cover_ratio=("shaped_to_cover_ratio", "mean"),
        encrypt_ms=("encrypt_ms", "mean"),
        decrypt_ms=("decrypt_ms", "mean"),
        shaped_encrypt_ms=("shaped_encrypt_ms", "mean"),
        shaped_decrypt_ms=("shaped_decrypt_ms", "mean"),
        encrypt_peak_kib=("encrypt_peak_kib", "mean"),
        decrypt_peak_kib=("decrypt_peak_kib", "mean"),
        shaped_encrypt_peak_kib=("shaped_encrypt_peak_kib", "mean"),
        shaped_decrypt_peak_kib=("shaped_decrypt_peak_kib", "mean"),
    )


def bounded_summary(raw: pd.DataFrame) -> pd.DataFrame:
    feasible = raw[raw["success"] == 1]
    return pd.DataFrame([{
        "bound": 2,
        "length": 200,
        "trials": len(raw),
        "feasible_trials": len(feasible),
        "assignment_success_rate": len(feasible) / len(raw),
        "mean_raw_record_bytes": feasible["raw_record_bytes"].mean(),
        "mean_compact_envelope_bytes": feasible["compact_envelope_bytes"].mean(),
        "mean_direct_encrypted_bytes": feasible["direct_encrypted_bytes"].mean(),
        "mean_envelope_to_direct_ratio": feasible["envelope_to_direct_ratio"].mean(),
    }])


def write_preprocessed_table(path: Path) -> None:
    raw = pd.read_csv(path)
    rows = raw[(raw["bound"] == 2) & (raw["compression"] == "zlib9")]
    grouped = rows.groupby("message_family").agg(
        coded=("coded_length", "mean"),
        compact=("compact_bytes", "mean"),
        packed=("packed_compact_bytes", "mean"),
        direct=("direct_bytes", "mean"),
    )
    labels = {
        "adversarial_repeated": "Repeated byte",
        "natural_text": "Templated text",
        "printable_ascii": "Printable ASCII",
        "uniform_bytes": "Uniform bytes",
    }
    lines = [
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"""\textbf{Message family} & \textbf{Coded bytes} & \textbf{Compact FHAM} & \textbf{Packed FHAM prototype} & \textbf{Direct AES-GCM} & \textbf{Packed/direct} \\""",
        r"\midrule",
    ]
    for family in ("adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes"):
        row = grouped.loc[family]
        ratio = row["packed"] / row["direct"]
        lines.append(
            f"{labels[family]} & {row['coded']:.0f} & {row['compact']:.2f} & "
            f"{row['packed']:.2f} & {row['direct']:.2f} & {ratio:.2f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    target = RESULTS / "revision_step0" / "tab_preprocessed_metadata_direct29.tex"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # This table is the active result consumed by the SPIC manuscript.
    for venue_source in (
        ROOT / "FHAM_Elsevier_SPIC" / "01_MAIN_MANUSCRIPT" / "source" / "tab_preprocessed_metadata.tex",
        ROOT / "FHAM_Elsevier_SPIC" / "01_MAIN_MANUSCRIPT" / "02_REVISION_SOURCE" / "tab_preprocessed_metadata.tex",
    ):
        venue_source.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    source_files = []
    for path in (RESULTS / "auxiliary_channel_raw.csv", RESULTS / "auxiliary_channel_b2_200_raw.csv"):
        source_files.append((path, "direct_encrypted_bytes"))
    for path in sorted((RESULTS / "revision_ablation").glob("*_channel*_raw.csv")):
        header = pd.read_csv(path, nrows=0).columns
        if "direct_bytes" in header:
            source_files.append((path, "direct_bytes"))

    original_hashes = {}
    for path, column in source_files:
        old_path = archived_source(path)
        original_hashes[str(path.relative_to(ROOT))] = sha256(old_path)
        correct_raw_file(path, column)

    channel_raw = pd.read_csv(RESULTS / "auxiliary_channel_raw.csv")
    auxiliary_summary(channel_raw).to_csv(RESULTS / "auxiliary_channel.csv", index=False, float_format="%.12g")
    b2_raw = pd.read_csv(RESULTS / "auxiliary_channel_b2_200_raw.csv")
    bounded_summary(b2_raw).to_csv(RESULTS / "auxiliary_channel_b2_200.csv", index=False, float_format="%.12g")

    packed_raw = RESULTS / "revision_ablation" / "controlled_parameters_dspectral_b12_n200_t3_iall_channel_channel_raw.csv"
    write_preprocessed_table(packed_raw)

    # Rebuild the two envelope-size tables from the corrected active summaries.
    sys.path.insert(0, str(ROOT / "scripts"))
    import generate_tables
    commit = generate_tables.git_commit()
    generate_tables.table_channel_real(commit)
    generate_tables.table_channel_bounded(commit)
    for table_name in ("tab_channel_real", "tab_channel_bounded"):
        generated = ROOT / "paper" / "tables" / "generated" / f"{table_name}.tex"
        for venue_source in (
            ROOT / "FHAM_Elsevier_SPIC" / "01_MAIN_MANUSCRIPT" / "source" / f"{table_name}.tex",
            ROOT / "FHAM_Elsevier_SPIC" / "01_MAIN_MANUSCRIPT" / "02_REVISION_SOURCE" / f"{table_name}.tex",
        ):
            shutil.copy2(generated, venue_source)

    provenance = {
        "purpose": "correct direct AES-GCM size reference",
        "legacy_direct_header_bytes": OLD_HEADER_BYTES,
        "direct_format_version_bytes": DIRECT_FORMAT_BYTES,
        "direct_nonce_bytes": 12,
        "aes_gcm_tag_bytes": 16,
        "corrected_fixed_overhead_bytes": DIRECT_FORMAT_BYTES + 12 + 16,
        "removed_fham_specific_bytes": REMOVED_BYTES,
        "method": "Preserve historical inputs, subtract the 12-byte FHAM envelope-header excess, and recompute ratios from raw rows.",
        "source_sha256": original_hashes,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    out = RESULTS / "revision_step0" / "direct_baseline_provenance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8")
    print(f"corrected direct baseline: {DIRECT_FORMAT_BYTES}+12+16 = {DIRECT_FORMAT_BYTES + 12 + 16} fixed bytes")
    print(f"provenance: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
