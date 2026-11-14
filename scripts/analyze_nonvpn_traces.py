"""Summarize non-VPN PCAP/PCAPNG traces and scan transport payloads for FHAM markers.

The input traces remain on the data volume. The script writes only a compact CSV
summary into the repository results directory. Marker scanning is packet-local;
it is a baseline signature check, not a full stream-reassembly or classifier.
"""

from __future__ import annotations

import argparse
import csv
import struct
from collections import Counter
from pathlib import Path


MARKERS = (b"FHMS", b"FHME", b"FHMT")


def ethernet_ip(packet: bytes, linktype: int):
    """Return (IP version, protocol, transport payload) when decodable."""
    offset = 0
    ethertype = None
    if linktype == 1:  # Ethernet
        if len(packet) < 14:
            return None
        ethertype = int.from_bytes(packet[12:14], "big")
        offset = 14
        while ethertype in (0x8100, 0x88A8, 0x9100):
            if len(packet) < offset + 4:
                return None
            ethertype = int.from_bytes(packet[offset + 2:offset + 4], "big")
            offset += 4
    elif linktype == 113:  # Linux cooked capture v1
        if len(packet) < 16:
            return None
        ethertype = int.from_bytes(packet[14:16], "big")
        offset = 16
    elif linktype == 276:  # Linux cooked capture v2
        if len(packet) < 20:
            return None
        ethertype = int.from_bytes(packet[0:2], "big")
        offset = 20
    elif linktype in (101, 228, 229):  # raw IP, IPv4, IPv6
        if not packet:
            return None
        version = packet[0] >> 4
        ethertype = {4: 0x0800, 6: 0x86DD}.get(version)
    elif linktype in (0, 108):  # BSD loopback / loopback with network byte order
        if len(packet) < 4:
            return None
        family = int.from_bytes(packet[:4], "little" if linktype == 0 else "big")
        ethertype = 0x0800 if family in (2, 24,  AF_INET) else (0x86DD if family in (10, 23,  AF_INET6) else None)
        offset = 4
    else:
        return None

    if ethertype == 0x0800:
        if len(packet) < offset + 20 or packet[offset] >> 4 != 4:
            return None
        ihl = (packet[offset] & 0x0F) * 4
        total_len = int.from_bytes(packet[offset + 2:offset + 4], "big")
        if ihl < 20 or len(packet) < offset + ihl:
            return None
        proto = packet[offset + 9]
        fragment = int.from_bytes(packet[offset + 6:offset + 8], "big") & 0x1FFF
        l4 = offset + ihl
        end = min(len(packet), offset + total_len) if total_len else len(packet)
        if fragment:
            return (4, proto, b"")
    elif ethertype == 0x86DD:
        if len(packet) < offset + 40 or packet[offset] >> 4 != 6:
            return None
        payload_len = int.from_bytes(packet[offset + 4:offset + 6], "big")
        proto = packet[offset + 6]
        l4 = offset + 40
        end = min(len(packet), l4 + payload_len)
        # Walk common IPv6 extension headers to the transport protocol.
        while proto in (0, 43, 44, 51, 60):
            if len(packet) < l4 + 2:
                return (6, proto, b"")
            next_proto = packet[l4]
            ext_len = (packet[l4 + 1] + 2) * 4 if proto == 51 else (packet[l4 + 1] + 1) * 8
            if len(packet) < l4 + ext_len:
                return (6, proto, b"")
            l4 += ext_len
            proto = next_proto
    else:
        return None

    if proto == 6 and end >= l4 + 20:
        header_len = (packet[l4 + 12] >> 4) * 4
        if header_len < 20 or end < l4 + header_len:
            return (4 if ethertype == 0x0800 else 6, proto, b"")
        payload = packet[l4 + header_len:end]
    elif proto == 17 and end >= l4 + 8:
        udp_len = int.from_bytes(packet[l4 + 4:l4 + 6], "big")
        payload = packet[l4 + 8:min(end, l4 + udp_len)]
    else:
        payload = b""
    return (4 if ethertype == 0x0800 else 6, proto, payload)


# BSD address-family values vary across platforms; these are the common values.
AF_INET = 2
AF_INET6 = 24


def parse_pcap(path: Path, consume):
    with path.open("rb") as stream:
        magic = stream.read(4)
        formats = {
            b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
            b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
            b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
            b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
        }
        if magic not in formats:
            raise ValueError(f"unsupported classic PCAP magic in {path}")
        endian, resolution = formats[magic]
        header = stream.read(20)
        if len(header) != 20:
            raise ValueError(f"truncated PCAP global header in {path}")
        _major, _minor, _zone, _sigfigs, _snaplen, linktype = struct.unpack(endian + "HHIIII", header)
        while True:
            record = stream.read(16)
            if not record:
                break
            if len(record) != 16:
                raise ValueError(f"truncated PCAP record header in {path}")
            sec, fraction, caplen, origlen = struct.unpack(endian + "IIII", record)
            packet = stream.read(caplen)
            if len(packet) != caplen:
                raise ValueError(f"truncated PCAP packet in {path}")
            consume((sec + fraction / resolution), caplen, origlen, linktype, packet)


def parse_pcapng(path: Path, consume):
    endian = None
    interfaces: list[tuple[int, float, int]] = []
    with path.open("rb") as stream:
        while True:
            first = stream.read(12)
            if not first:
                break
            if len(first) < 12:
                raise ValueError(f"truncated PCAPNG block in {path}")
            block_type_raw = first[:4]
            if block_type_raw == b"\x0a\x0d\x0d\x0a":
                bom = first[8:12]
                endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else (">" if bom == b"\x1a\x2b\x3c\x4d" else None)
                if endian is None:
                    raise ValueError(f"invalid PCAPNG byte-order magic in {path}")
                block_type = 0x0A0D0D0A
                total_len = struct.unpack(endian + "I", first[4:8])[0]
                interfaces = []
            else:
                if endian is None:
                    raise ValueError(f"PCAPNG section header missing in {path}")
                block_type, total_len = struct.unpack(endian + "II", first[:8])
            if total_len < 12 or total_len % 4:
                raise ValueError(f"invalid PCAPNG block size {total_len} in {path}")
            rest = stream.read(total_len - 12)
            if len(rest) != total_len - 12:
                raise ValueError(f"truncated PCAPNG block body in {path}")
            body = first[8:] + rest[:-4]
            if block_type == 1 and len(body) >= 8:  # Interface Description Block
                linktype = struct.unpack(endian + "H", body[:2])[0]
                resolution = 1e-6  # PCAPNG default: microsecond timestamps
                offset = 0
                option_offset = 8
                while option_offset + 4 <= len(body):
                    code, option_length = struct.unpack_from(endian + "HH", body, option_offset)
                    option_offset += 4
                    if code == 0:
                        break
                    option = body[option_offset:option_offset + option_length]
                    if code == 9 and option_length == 1:  # if_tsresol
                        value = option[0]
                        resolution = (2.0 ** -(value & 0x7F) if value & 0x80 else 10.0 ** -value)
                    elif code == 14 and option_length == 8:  # if_tsoffset
                        offset = struct.unpack(endian + "q", option)[0]
                    option_offset += (option_length + 3) & ~3
                interfaces.append((linktype, resolution, offset))
            elif block_type == 6 and len(body) >= 20:  # Enhanced Packet Block
                interface_id, ts_hi, ts_lo, caplen, origlen = struct.unpack(endian + "IIIII", body[:20])
                packet = body[20:20 + caplen]
                if len(packet) == caplen and interface_id < len(interfaces):
                    linktype, resolution, offset = interfaces[interface_id]
                    consume(((ts_hi << 32) | ts_lo) * resolution + offset, caplen, origlen, linktype, packet)
            elif block_type == 2 and len(body) >= 20:  # obsolete Packet Block
                interface_id, _drops, ts_hi, ts_lo, caplen, origlen = struct.unpack(endian + "HHIIII", body[:20])
                packet = body[20:20 + caplen]
                if len(packet) == caplen and interface_id < len(interfaces):
                    linktype, resolution, offset = interfaces[interface_id]
                    consume(((ts_hi << 32) | ts_lo) * resolution + offset, caplen, origlen, linktype, packet)
            elif block_type == 3 and len(body) >= 4:  # Simple Packet Block (no timestamp)
                origlen = struct.unpack(endian + "I", body[:4])[0]
                if interfaces:
                    caplen = min(origlen, len(body) - 4)
                    consume(None, caplen, origlen, interfaces[0][0], body[4:4 + caplen])


def summarize(path: Path) -> dict:
    stats = Counter()
    first_ts = None
    last_ts = None
    markers = Counter()
    packet_markers = Counter()

    def consume(timestamp, caplen, origlen, linktype, packet):
        nonlocal first_ts, last_ts
        stats["packets"] += 1
        stats["captured_bytes"] += caplen
        stats["wire_bytes"] += origlen
        stats[f"linktype_{linktype}"] += 1
        if timestamp is not None:
            first_ts = timestamp if first_ts is None else min(first_ts, timestamp)
            last_ts = timestamp if last_ts is None else max(last_ts, timestamp)
        decoded = ethernet_ip(packet, linktype)
        if decoded is None:
            stats["undecoded_link_packets"] += 1
            return
        version, proto, payload = decoded
        stats[f"ipv{version}_packets"] += 1
        if proto == 6:
            stats["tcp_packets"] += 1
        elif proto == 17:
            stats["udp_packets"] += 1
        if proto in (6, 17):
            stats["transport_payload_bytes"] += len(payload)
            stats["transport_payload_packets"] += bool(payload)
            for marker in MARKERS:
                if marker in payload:
                    markers[marker.decode()] += 1
                    packet_markers[marker.decode()] += 1

    if path.suffix.lower() == ".pcapng":
        parse_pcapng(path, consume)
    else:
        parse_pcap(path, consume)

    row = {
        "file": path.name,
        "scenario": path.parent.name,
        "file_bytes": path.stat().st_size,
        **stats,
        "duration_seconds": (last_ts - first_ts) if first_ts is not None and last_ts is not None else "",
        "FHMS_payload_packets": packet_markers["FHMS"],
        "FHME_payload_packets": packet_markers["FHME"],
        "FHMT_payload_packets": packet_markers["FHMT"],
    }
    return row


def inspect_markers(path: Path) -> list[dict]:
    """Record packet-local byte context for each clear marker occurrence."""
    rows = []
    packet_index = 0

    def consume(timestamp, caplen, origlen, linktype, packet):
        nonlocal packet_index
        packet_index += 1
        decoded = ethernet_ip(packet, linktype)
        if decoded is None:
            return
        _version, proto, payload = decoded
        if proto not in (6, 17):
            return
        for marker in MARKERS:
            start = 0
            while True:
                offset = payload.find(marker, start)
                if offset < 0:
                    break
                rows.append({
                    "file": path.name,
                    "packet_index": packet_index,
                    "timestamp_seconds": "" if timestamp is None else f"{timestamp:.6f}",
                    "transport": "TCP" if proto == 6 else "UDP",
                    "marker": marker.decode("ascii"),
                    "payload_offset": offset,
                    "payload_bytes": len(payload),
                    "marker_following_byte_hex": payload[offset + len(marker):offset + len(marker) + 1].hex(),
                    "at_payload_start": int(offset == 0),
                })
                start = offset + 1

    if path.suffix.lower() == ".pcapng":
        parse_pcapng(path, consume)
    else:
        parse_pcap(path, consume)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="directory containing extracted PCAP/PCAPNG files")
    parser.add_argument("--output", type=Path, default=Path("results/nonvpn_trace_baseline.csv"))
    parser.add_argument("--inspect-summary", type=Path, help="re-scan only files with markers in an earlier summary")
    parser.add_argument("--marker-details", type=Path, default=Path("results/nonvpn_marker_occurrences.csv"))
    args = parser.parse_args()
    if args.inspect_summary:
        with args.inspect_summary.open("r", newline="", encoding="utf-8") as stream:
            summary_rows = list(csv.DictReader(stream))
        selected = [row for row in summary_rows if any(int(row.get(f"{marker}_payload_packets") or 0) for marker in ("FHMS", "FHME", "FHMT"))]
        details = []
        for index, row in enumerate(selected, 1):
            path = args.input / row["scenario"] / row["file"]
            print(f"[inspect {index}/{len(selected)}] {path.name}", flush=True)
            details.extend(inspect_markers(path))
        args.marker_details.parent.mkdir(parents=True, exist_ok=True)
        fields = ["file", "packet_index", "timestamp_seconds", "transport", "marker", "payload_offset", "payload_bytes", "marker_following_byte_hex", "at_payload_start"]
        with args.marker_details.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(details)
        print(f"marker_occurrences={len(details)} details={args.marker_details}")
        return
    files = sorted(p for p in args.input.rglob("*") if p.is_file() and p.suffix.lower() in (".pcap", ".pcapng"))
    if not files:
        raise SystemExit(f"no PCAP/PCAPNG files found under {args.input}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, path in enumerate(files, 1):
        row = summarize(path)
        rows.append(row)
        print(f"[{index}/{len(files)}] {path.name}: {row.get('packets', 0)} packets")
    fields = sorted({key for row in rows for key in row})
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    total_packets = sum(row.get("packets", 0) for row in rows)
    total_bytes = sum(row.get("wire_bytes", 0) for row in rows)
    marker_totals = {marker: sum(row.get(f"{marker}_payload_packets", 0) for row in rows) for marker in ("FHMS", "FHME", "FHMT")}
    print(f"captures={len(rows)} packets={total_packets} wire_bytes={total_bytes} markers={marker_totals}")
    print(f"summary={args.output}")


if __name__ == "__main__":
    main()
