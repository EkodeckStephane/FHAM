#!/usr/bin/env python3
"""Run the frozen Step-2 flow experiment under a real Npcap loopback capture.

Run from an elevated PowerShell after installing Wireshark/Npcap. This writes
only a port-filtered PCAPNG under results/step2/detection/full_capture/.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = ROOT / "results/step2/detection/full_capture"


def _admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _find_dumpcap():
    found = shutil.which("dumpcap")
    if found:
        return Path(found)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        candidate = Path(base) / "Wireshark" / "dumpcap.exe"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("dumpcap.exe absent; install Wireshark with Npcap, then retry")


def _pcapng_count(path: Path):
    data = path.read_bytes()
    offset = 0
    endian = None
    packets = 0
    while offset + 12 <= len(data):
        block_type_raw = data[offset:offset + 4]
        if block_type_raw == b"\x0a\x0d\x0d\x0a":
            if offset + 12 > len(data):
                break
            bom = data[offset + 8:offset + 12]
            endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">" if bom == b"\x1a\x2b\x3c\x4d" else None
            if endian is None:
                raise ValueError("invalid pcapng byte-order magic")
        if endian is None:
            raise ValueError("pcapng section header missing")
        block_type = int.from_bytes(block_type_raw, "little" if endian == "<" else "big")
        length = int.from_bytes(data[offset + 4:offset + 8], "little" if endian == "<" else "big")
        if length < 12 or offset + length > len(data):
            raise ValueError("truncated or malformed pcapng block")
        trailer = int.from_bytes(data[offset + length - 4:offset + length], "little" if endian == "<" else "big")
        if trailer != length:
            raise ValueError("pcapng block length trailer mismatch")
        if block_type == 6:
            packets += 1
        offset += length
    if offset != len(data):
        raise ValueError("pcapng has trailing incomplete data")
    return packets, len(data)


def main():
    if os.name != "nt":
        raise SystemExit("This capture wrapper is for Windows only")
    if not _admin():
        raise SystemExit("Administrator rights required. Open PowerShell as Administrator and rerun this script.")
    dumpcap = _find_dumpcap()
    listing = subprocess.run([str(dumpcap), "-D"], check=True, capture_output=True, text=True)
    if "NPF_Loopback" not in listing.stdout and "loopback" not in listing.stdout.lower():
        raise SystemExit("Npcap loopback interface absent. Install/repair Npcap and verify dumpcap -D.")
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pcap = CAPTURE_DIR / f"fham_full_loopback_{stamp}.pcapng"
    log = CAPTURE_DIR / f"dumpcap_{stamp}.log"
    with log.open("wb") as output:
        proc = subprocess.Popen(
            [str(dumpcap), "-q", "-i", r"\Device\NPF_Loopback", "-f", "tcp port 45511",
             "-s", "0", "-w", str(pcap)], stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        try:
            time.sleep(3)
            if proc.poll() is not None:
                raise RuntimeError(f"dumpcap exited before capture start; inspect {log}")
            experiment = subprocess.run([sys.executable, str(ROOT / "scripts/run_step2_network_capture.py"), "--full"], cwd=ROOT)
            if experiment.returncode:
                raise RuntimeError(f"network experiment failed with exit code {experiment.returncode}")
        finally:
            if proc.poll() is None:
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                    proc.wait(timeout=30)
                except Exception:
                    proc.terminate()
                    proc.wait(timeout=10)
    packets, size = _pcapng_count(pcap)
    if packets == 0:
        raise RuntimeError(f"capture contains no packet blocks: {pcap}")
    meta_path = CAPTURE_DIR / "capture_metadata.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(pcap.read_bytes()).hexdigest()
    metadata["packet_capture"] = {
        "status": "captured and pcapng structure verified",
        "interface": r"\Device\NPF_Loopback",
        "capture_filter": "tcp port 45511",
        "pcapng": str(pcap.relative_to(ROOT)),
        "pcapng_sha256": digest,
        "pcapng_bytes": size,
        "packet_blocks": packets,
        "dumpcap_log": str(log.relative_to(ROOT)),
        "capture_utc": stamp,
    }
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata["packet_capture"], indent=2))


if __name__ == "__main__":
    main()
