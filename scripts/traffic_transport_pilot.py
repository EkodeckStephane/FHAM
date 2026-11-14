"""Generate FHAM-positive TCP/TLS traces and compare them with NonVPN captures.

This is a controlled wire-format pilot, not a covert-channel protocol claim.
It writes small synthetic positive PCAPs and aggregate flow statistics only;
the external ISCXVPN2016 captures are read in place and never modified.
"""

from __future__ import annotations

import csv
import os
import ssl
import struct
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from PIL import Image

from analyze_nonvpn_traces import parse_pcap, parse_pcapng
from fham.channel import AuxiliaryChannel, ReplayGuard
from fham.config import DATASET_DIR, RESULTS_DIR
from fham.experiments import _message
from fham.methods import BoundedAssignmentMethod


CAPTURE_DIR = RESULTS_DIR / "traffic_transport_pcaps"
FRAME_HEADER = struct.Struct("!4sBBI")
FRAME_MAGIC = b"FHAM"
FRAME_VERSION = 1
FRAME_OFFER = 1
FRAME_RECORD = 2
FRAME_ACK = 3
MSS = 1200
STREAM_MARKERS = (
    b"FHAM", b"FHAM\x01", b"FHMS\x01", b"FHME\x01", b"FHMT\x01"
)


def pack_frame(kind: int, payload: bytes) -> bytes:
    return FRAME_HEADER.pack(FRAME_MAGIC, FRAME_VERSION, kind, len(payload)) + payload


def unpack_frames(data: bytes) -> list[tuple[int, bytes]]:
    frames = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < FRAME_HEADER.size:
            raise ValueError("truncated FHAM application frame")
        magic, version, kind, length = FRAME_HEADER.unpack_from(data, offset)
        offset += FRAME_HEADER.size
        if magic != FRAME_MAGIC or version != FRAME_VERSION or offset + length > len(data):
            raise ValueError("invalid FHAM application frame")
        frames.append((kind, data[offset:offset + length]))
        offset += length
    return frames


def generate_tls_certificate(directory: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fham-pilot.local")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("fham-pilot.local")]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "fham-pilot-cert.pem"
    key_path = directory / "fham-pilot-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    return cert_path, key_path


def make_tls_contexts(cert_path: Path, key_path: Path):
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_3
    server_context.maximum_version = ssl.TLSVersion.TLSv1_3
    server_context.load_cert_chain(str(cert_path), str(key_path))

    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.minimum_version = ssl.TLSVersion.TLSv1_3
    client_context.maximum_version = ssl.TLSVersion.TLSv1_3
    client_context.check_hostname = True
    client_context.verify_mode = ssl.CERT_REQUIRED
    client_context.load_verify_locations(cafile=str(cert_path))
    return client_context, server_context


def make_application_exchange(image: np.ndarray, message: str, trial: int,
                              method: BoundedAssignmentMethod | None = None):
    """Build and verify one signed FHAM session over its application frames."""
    if method is None:
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
    assignment = method.embed(message, image)
    if assignment is None:
        raise ValueError(f"B=2 assignment infeasible for positive trial {trial}")

    sender_identity = ed25519.Ed25519PrivateKey.generate()
    receiver_identity = ed25519.Ed25519PrivateKey.generate()
    sender_id = sender_identity.public_key().public_bytes_raw()
    receiver_id = receiver_identity.public_key().public_bytes_raw()
    sender_ephemeral = X25519PrivateKey.generate()
    receiver_ephemeral = X25519PrivateKey.generate()
    session_id = os.urandom(16)
    sender_offer, sender_signature = AuxiliaryChannel.sign_ephemeral(
        sender_identity, sender_ephemeral, receiver_id, session_id
    )
    receiver_offer, receiver_signature = AuxiliaryChannel.sign_ephemeral(
        receiver_identity, receiver_ephemeral, sender_id, session_id
    )
    AuxiliaryChannel.verify_ephemeral(
        sender_id, receiver_id, sender_offer, sender_signature, session_id
    )
    AuxiliaryChannel.verify_ephemeral(
        receiver_id, sender_id, receiver_offer, receiver_signature, session_id
    )
    sender_key = AuxiliaryChannel.derive_session_key(
        sender_ephemeral, receiver_offer, session_id
    )
    receiver_key = AuxiliaryChannel.derive_session_key(
        receiver_ephemeral, sender_offer, session_id
    )
    if sender_key != receiver_key:
        raise AssertionError("session-key agreement failed")

    envelope = AuxiliaryChannel.protect_session(
        assignment, sender_key, image, session_id, 0, record_capacity=len(message)
    )
    sender_payload = session_id + sender_offer + sender_signature
    receiver_payload = session_id + receiver_offer + receiver_signature
    request = pack_frame(FRAME_OFFER, sender_payload) + pack_frame(FRAME_RECORD, envelope)
    reply = pack_frame(FRAME_OFFER, receiver_payload) + pack_frame(
        FRAME_ACK, session_id + b"\x00"
    )

    request_frames = unpack_frames(request)
    response_frames = unpack_frames(reply)
    received_offer = request_frames[0][1]
    if len(received_offer) != 112:
        raise AssertionError("unexpected signed-offer size")
    AuxiliaryChannel.verify_ephemeral(
        sender_id, receiver_id, received_offer[16:48], received_offer[48:112],
        received_offer[:16],
    )
    if len(request_frames) != 2 or request_frames[0][1] != sender_payload:
        raise AssertionError("serialized sender offer differs from signed offer")
    received_server_offer = response_frames[0][1]
    AuxiliaryChannel.verify_ephemeral(
        receiver_id, sender_id, received_server_offer[16:48],
        received_server_offer[48:112], received_server_offer[:16],
    )
    if len(response_frames) != 2 or response_frames[1][1] != session_id + b"\x00":
        raise AssertionError("invalid application acknowledgement")

    guard = ReplayGuard()
    guard.register_session(session_id)
    recovered = AuxiliaryChannel.recover_session(envelope, receiver_key, image, guard)
    recovered_message = method.extract(recovered, image)
    if recovered_message != message:
        raise AssertionError("positive FHAM session did not recover exactly")
    return request, reply, {
        "trial": trial,
        "message_length": len(message),
        "frame_request_bytes": len(request),
        "frame_reply_bytes": len(reply),
        "envelope_bytes": len(envelope),
        "exact_recovery": 1,
        "key_agreement": 1,
        "offer_authentication": 1,
        "cover_binding": 1,
        "replay_state_acceptance": 1,
    }


def drain_bio(bio: ssl.MemoryBIO) -> bytes:
    chunks = []
    while bio.pending:
        chunks.append(bio.read())
    return b"".join(chunks)


def tls13_exchange(request: bytes, expected_reply: bytes, client_context, server_context):
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(client_in, client_out, server_side=False,
                                     server_hostname="fham-pilot.local")
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    events: list[tuple[float, int, bytes]] = []
    tick = 0.0
    client_done = server_done = False

    def move(source, destination, direction):
        nonlocal tick
        data = drain_bio(source)
        if data:
            events.append((tick, direction, data))
            tick += 0.001
            destination.write(data)
            return True
        return False

    for _ in range(100):
        progress = False
        if not client_done:
            try:
                client.do_handshake()
                client_done = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            progress |= move(client_out, server_in, 0)
        if not server_done:
            try:
                server.do_handshake()
                server_done = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            progress |= move(server_out, client_in, 1)
        if client_done and server_done:
            break
        if not progress and not client_out.pending and not server_out.pending:
            raise RuntimeError("TLS 1.3 handshake made no progress")
    else:
        raise RuntimeError("TLS 1.3 handshake did not complete")

    if client.write(request) != len(request):
        raise RuntimeError("TLS client did not accept the full FHAM request")
    progress = move(client_out, server_in, 0)
    received = server.read(1_000_000)
    if received != request:
        raise AssertionError("TLS server received different FHAM application bytes")
    if not progress:
        raise RuntimeError("TLS application request generated no wire bytes")

    if server.write(expected_reply) != len(expected_reply):
        raise RuntimeError("TLS server did not accept the full FHAM reply")
    if not move(server_out, client_in, 1):
        raise RuntimeError("TLS application reply generated no wire bytes")
    if client.read(1_000_000) != expected_reply:
        raise AssertionError("TLS client received different FHAM reply bytes")
    return events


def raw_exchange(request: bytes, reply: bytes):
    return [(0.003, 0, request), (0.050, 1, reply)]


def checksum(data: bytes) -> int:
    if len(data) & 1:
        data += b"\x00"
    words = struct.unpack("!" + "H" * (len(data) // 2), data)
    total = sum(words)
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


class PcapWriter:
    def __init__(self, path: Path):
        self.stream = path.open("wb")
        self.stream.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))

    def packet(self, timestamp: float, frame: bytes):
        sec = int(timestamp)
        usec = int((timestamp - sec) * 1_000_000)
        self.stream.write(struct.pack("<IIII", sec, usec, len(frame), len(frame)))
        self.stream.write(frame)

    def close(self):
        self.stream.close()


class TcpFlowPcapBuilder:
    def __init__(self, writer: PcapWriter, flow_index: int, mode: str):
        self.writer = writer
        self.flow_index = flow_index
        self.mode = mode
        self.client_ip = bytes((192, 0, 2, 10))
        self.server_ip = bytes((198, 51, 100, 20))
        self.client_mac = bytes.fromhex("020000000001")
        self.server_mac = bytes.fromhex("020000000002")
        self.client_port = 40000 + flow_index
        self.server_port = 443
        self.client_seq = 1_000_000 + flow_index * 100_000
        self.server_seq = 2_000_000 + flow_index * 100_000
        self.client_next = self.client_seq
        self.server_next = self.server_seq
        self.packet_id = (flow_index * 31) & 0xFFFF
        self.base_time = 1_700_000_000 + flow_index * 15

    def _emit(self, timestamp, direction, payload=b"", flags=0x10):
        if direction == 0:
            src_ip, dst_ip = self.client_ip, self.server_ip
            src_mac, dst_mac = self.client_mac, self.server_mac
            sport, dport = self.client_port, self.server_port
            seq, ack = self.client_next, self.server_next
        else:
            src_ip, dst_ip = self.server_ip, self.client_ip
            src_mac, dst_mac = self.server_mac, self.client_mac
            sport, dport = self.server_port, self.client_port
            seq, ack = self.server_next, self.client_next

        tcp_wo_sum = struct.pack("!HHIIHHHH", sport, dport, seq, ack,
                                 (5 << 12) | flags, 64240, 0, 0) + payload
        pseudo = src_ip + dst_ip + b"\x00\x06" + struct.pack("!H", len(tcp_wo_sum))
        tcp_sum = checksum(pseudo + tcp_wo_sum)
        tcp = struct.pack("!HHIIHHHH", sport, dport, seq, ack,
                          (5 << 12) | flags, 64240, tcp_sum, 0) + payload
        total_len = 20 + len(tcp)
        ip_wo_sum = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total_len,
                                self.packet_id, 0x4000, 64, 6, 0, src_ip, dst_ip)
        ip_sum = checksum(ip_wo_sum)
        ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total_len,
                          self.packet_id, 0x4000, 64, 6, ip_sum, src_ip, dst_ip)
        self.packet_id = (self.packet_id + 1) & 0xFFFF
        eth = dst_mac + src_mac + b"\x08\x00"
        self.writer.packet(timestamp, eth + ip + tcp)
        if flags & 0x02:
            if direction == 0:
                self.client_next += 1
            else:
                self.server_next += 1
        if payload:
            if direction == 0:
                self.client_next += len(payload)
            else:
                self.server_next += len(payload)
        if flags & 0x01:
            if direction == 0:
                self.client_next += 1
            else:
                self.server_next += 1

    def write(self, events):
        t = self.base_time
        self._emit(t, 0, flags=0x02)
        self._emit(t + 0.001, 1, flags=0x12)
        self._emit(t + 0.002, 0, flags=0x10)
        t += 0.004
        for offset, direction, data in events:
            for start in range(0, len(data), MSS):
                segment = data[start:start + MSS]
                self._emit(t + offset, direction, segment, flags=0x18)
                t += 0.0001
        self._emit(t + 0.010, 0, flags=0x11)
        self._emit(t + 0.011, 1, flags=0x11)
        self._emit(t + 0.012, 0, flags=0x10)


def decode_tcp(packet: bytes, linktype: int):
    """Decode TCP header and payload from common Ethernet/raw IP captures."""
    offset = 0
    if linktype == 1:
        if len(packet) < 14:
            return None
        ethertype = int.from_bytes(packet[12:14], "big")
        offset = 14
        while ethertype in (0x8100, 0x88A8, 0x9100):
            if len(packet) < offset + 4:
                return None
            ethertype = int.from_bytes(packet[offset + 2:offset + 4], "big")
            offset += 4
    elif linktype in (101, 228, 229):
        if not packet:
            return None
        ethertype = 0x0800 if packet[0] >> 4 == 4 else 0x86DD
    else:
        return None

    if ethertype == 0x0800:
        if len(packet) < offset + 20 or packet[offset] >> 4 != 4:
            return None
        ihl = (packet[offset] & 0x0F) * 4
        total = int.from_bytes(packet[offset + 2:offset + 4], "big")
        proto = packet[offset + 9]
        fragment = int.from_bytes(packet[offset + 6:offset + 8], "big") & 0x1FFF
        if ihl < 20 or proto != 6 or fragment:
            return None
        src, dst = packet[offset + 12:offset + 16], packet[offset + 16:offset + 20]
        transport = offset + ihl
        end = min(len(packet), offset + total)
        version = 4
    elif ethertype == 0x86DD:
        if len(packet) < offset + 40 or packet[offset] >> 4 != 6:
            return None
        proto = packet[offset + 6]
        src, dst = packet[offset + 8:offset + 24], packet[offset + 24:offset + 40]
        transport = offset + 40
        end = min(len(packet), transport + int.from_bytes(packet[offset + 4:offset + 6], "big"))
        while proto in (0, 43, 44, 51, 60):
            if len(packet) < transport + 2:
                return None
            next_proto = packet[transport]
            ext_len = (packet[transport + 1] + 2) * 4 if proto == 51 else (packet[transport + 1] + 1) * 8
            if proto == 44 and int.from_bytes(packet[transport + 2:transport + 4], "big") & 0xFFF8:
                return None
            transport += ext_len
            proto = next_proto
        if proto != 6:
            return None
        version = 6
    else:
        return None

    if end < transport + 20:
        return None
    sport, dport, seq, ack = struct.unpack_from("!HHII", packet, transport)
    tcp_len = (packet[transport + 12] >> 4) * 4
    flags = packet[transport + 13]
    if tcp_len < 20 or end < transport + tcp_len:
        return None
    payload = packet[transport + tcp_len:end]
    return version, src, dst, sport, dport, seq, ack, flags, len(packet) - offset, payload


class TcpStreamScanner:
    def __init__(self):
        self.next_seq = None
        self.pending = {}
        self.pending_bytes = 0
        self.tail = b""
        self.markers = set()
        self.gaps = 0

    def _consume(self, data):
        window = self.tail + data
        for marker in STREAM_MARKERS:
            if marker in window:
                self.markers.add(marker)
        self.tail = window[-(max(map(len, STREAM_MARKERS)) - 1):]
        self.next_seq = (self.next_seq + len(data)) & 0xFFFFFFFF

    def feed(self, seq, flags, payload):
        data_seq = (seq + (1 if flags & 0x02 else 0)) & 0xFFFFFFFF
        if self.next_seq is None:
            self.next_seq = data_seq
        if not payload:
            return
        delta = (data_seq - self.next_seq) & 0xFFFFFFFF
        if delta == 0:
            self._consume(payload)
        elif delta < 0x80000000:
            if self.pending_bytes + len(payload) <= 1_000_000:
                self.pending.setdefault(data_seq, payload)
                self.pending_bytes += len(payload)
            else:
                self.pending.clear()
                self.pending_bytes = 0
                self.gaps += 1
                self.next_seq = data_seq
                self._consume(payload)
        else:
            overlap = (self.next_seq - data_seq) & 0xFFFFFFFF
            if overlap < len(payload):
                self._consume(payload[overlap:])
        while self.next_seq in self.pending:
            chunk = self.pending.pop(self.next_seq)
            self.pending_bytes -= len(chunk)
            self._consume(chunk)


class FlowAccumulator:
    def __init__(self, capture, key, first_direction, timestamp):
        self.capture = capture
        self.key = key
        self.first_direction = first_direction
        self.first_ts = timestamp
        self.last_ts = timestamp
        self.packets = [0, 0]
        self.ip_bytes = [0, 0]
        self.payload_bytes = [0, 0]
        self.first_sizes = []
        self.streams = [TcpStreamScanner(), TcpStreamScanner()]

    def add(self, timestamp, direction, seq, flags, ip_bytes, payload):
        self.last_ts = max(self.last_ts, timestamp)
        self.packets[direction] += 1
        self.ip_bytes[direction] += ip_bytes
        self.payload_bytes[direction] += len(payload)
        if len(self.first_sizes) < 20:
            self.first_sizes.append((direction, ip_bytes))
        self.streams[direction].feed(seq, flags, payload)

    def row(self):
        markers = set().union(*(state.markers for state in self.streams))
        cdir = self.first_direction
        sdir = 1 - cdir
        return {
            "capture": self.capture,
            "packets": sum(self.packets),
            "ip_bytes": sum(self.ip_bytes),
            "tcp_payload_bytes": sum(self.payload_bytes),
            "client_to_server_bytes": self.ip_bytes[cdir],
            "server_to_client_bytes": self.ip_bytes[sdir],
            "duration_seconds": max(0.0, self.last_ts - self.first_ts),
            "first20_ip_packet_sizes": ";".join(f"{d}:{n}" for d, n in self.first_sizes),
            "stream_FHAM": int(b"FHAM" in markers),
            "stream_FHAM_version1": int(b"FHAM\x01" in markers),
            "stream_FHMS_version1": int(b"FHMS\x01" in markers),
            "stream_FHME_version1": int(b"FHME\x01" in markers),
            "stream_FHMT_version1": int(b"FHMT\x01" in markers),
            "reassembly_gap_events": sum(state.gaps for state in self.streams),
        }


def extract_tcp_flows(path: Path):
    flows = {}
    counts = Counter()

    def consume(timestamp, caplen, origlen, linktype, packet):
        if timestamp is None:
            timestamp = 0.0
        decoded = decode_tcp(packet, linktype)
        if decoded is None:
            return
        version, src, dst, sport, dport, seq, ack, flags, ip_bytes, payload = decoded
        counts["tcp_packets"] += 1
        a, b = (src, sport), (dst, dport)
        if a <= b:
            key, direction = (version, a, b), 0
        else:
            key, direction = (version, b, a), 1
        flow = flows.get(key)
        if flow is None:
            first_dir = direction
            flow = FlowAccumulator(path.name, key, first_dir, timestamp)
            flows[key] = flow
        flow.add(timestamp, direction, seq, flags, ip_bytes, payload)

    if path.suffix.lower() == ".pcapng":
        parse_pcapng(path, consume)
    else:
        parse_pcap(path, consume)
    return [dict(flow.row(), flow_index=i) for i, flow in enumerate(flows.values())], counts


def make_ipv4_pcap(message_lengths=(40,), trials_per_image=5):
    trials = []
    records = []
    image_paths = sorted((DATASET_DIR / "controlled").glob("*.png"))
    codebooks = {}
    for image_path in image_paths:
        image = np.asarray(Image.open(image_path).convert("L"))
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        codebooks[image_path.stem] = (image, method)
    with tempfile.TemporaryDirectory(prefix="fham-tls-pilot-") as temp:
        cert_path, key_path = generate_tls_certificate(Path(temp))
        tls_contexts = make_tls_contexts(cert_path, key_path)
        for length in message_lengths:
            for image_path in image_paths:
                image, method = codebooks[image_path.stem]
                for trial_index in range(trials_per_image):
                    label = len(trials)
                    message = _message(length, image_path.stem, trial_index)
                    request, reply, measured = make_application_exchange(
                        image, message, label, method
                    )
                    tls_events = tls13_exchange(request, reply, *tls_contexts)
                    trials.append({"request": request, "reply": reply, "tls_events": tls_events})
                    records.append({**measured, "image": image_path.stem})

        # Build the two synthetic positive captures from the verified exchanges.
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for mode in ("raw_tcp", "tls13_tcp"):
            capture = CAPTURE_DIR / f"fham_{mode}.pcap"
            writer = PcapWriter(capture)
            for index, trial in enumerate(trials):
                events = raw_exchange(trial["request"], trial["reply"]) if mode == "raw_tcp" else trial["tls_events"]
                TcpFlowPcapBuilder(writer, index, mode).write(events)
            writer.close()
            outputs[mode] = capture
    return outputs, records


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", type=Path, default=Path(r"D:\dataset"))
    parser.add_argument("--lengths", type=int, nargs="+", default=[40, 200])
    parser.add_argument("--trials-per-image", type=int, default=5)
    parser.add_argument("--reuse-positive-captures", action="store_true",
                        help="reuse generated PCAPs and protocol checks; scan the background only")
    args = parser.parse_args()

    if args.reuse_positive_captures:
        captures = {mode: CAPTURE_DIR / f"fham_{mode}.pcap" for mode in ("raw_tcp", "tls13_tcp")}
        with (RESULTS_DIR / "traffic_transport_protocol_checks.csv").open(
            "r", newline="", encoding="utf-8"
        ) as stream:
            protocol_rows = list(csv.DictReader(stream))
        for capture in captures.values():
            if not capture.exists():
                raise FileNotFoundError(capture)
    else:
        captures, protocol_rows = make_ipv4_pcap(tuple(args.lengths), args.trials_per_image)
    features = []
    for mode, path in captures.items():
        rows, _ = extract_tcp_flows(path)
        for row in rows:
            row["transport_mode"] = mode
            metadata = protocol_rows[row["flow_index"]]
            row["image"] = metadata["image"]
            row["message_length"] = int(metadata["message_length"])
            features.append(row)
    write_csv(RESULTS_DIR / "traffic_transport_positive_flows.csv", features)
    write_csv(RESULTS_DIR / "traffic_transport_protocol_checks.csv", protocol_rows)

    background_files = sorted(
        p for p in args.background.rglob("*")
        if p.is_file() and p.suffix.lower() in (".pcap", ".pcapng")
    )
    benign = []
    capture_rows = []
    for index, path in enumerate(background_files, 1):
        rows, _ = extract_tcp_flows(path)
        benign.extend(rows)
        capture_rows.append({"capture": path.name, "scenario": path.parent.name,
                             "tcp_flows": len(rows),
                             "marker_flows": sum(r["stream_FHAM"] for r in rows),
                             "versioned_FHAM_flows": sum(r["stream_FHAM_version1"] for r in rows),
                             "versioned_FHMS_flows": sum(r["stream_FHMS_version1"] for r in rows),
                             "reassembly_gap_events": sum(r["reassembly_gap_events"] for r in rows)})
        print(f"[{index}/{len(background_files)}] {path.name}: {len(rows)} TCP flows", flush=True)

    write_csv(RESULTS_DIR / "nonvpn_tcp_capture_flows.csv", capture_rows)
    if not benign:
        raise RuntimeError("no TCP flows decoded from the selected background captures")
    benign_marker = sum(row["stream_FHAM"] for row in benign)
    benign_versioned_fham = sum(row["stream_FHAM_version1"] for row in benign)
    benign_versioned = sum(row["stream_FHMS_version1"] for row in benign)
    benign_bytes = np.asarray([row["ip_bytes"] for row in benign], dtype=float)
    benign_packets = np.asarray([row["packets"] for row in benign], dtype=float)
    summary = []
    for mode in ("raw_tcp", "tls13_tcp"):
        for message_length in args.lengths:
            group = [r for r in features if r["transport_mode"] == mode and r["message_length"] == message_length]
            sizes = np.asarray([r["ip_bytes"] for r in group], dtype=float)
            packets = np.asarray([r["packets"] for r in group], dtype=float)
            summary.append({
                "mode": mode,
                "message_length": message_length,
                "positive_flows": len(group),
                "positive_FHAM_marker_flows": sum(r["stream_FHAM"] for r in group),
                "positive_FHAM_version1_flows": sum(r["stream_FHAM_version1"] for r in group),
                "positive_FHMS_version1_flows": sum(r["stream_FHMS_version1"] for r in group),
                "positive_exact_recovery_trials": sum(int(r["exact_recovery"]) for r in protocol_rows if int(r["message_length"]) == message_length),
                "median_flow_packets": float(np.median(packets)),
                "median_flow_ip_bytes": float(np.median(sizes)),
                "median_flow_payload_bytes": float(np.median([r["tcp_payload_bytes"] for r in group])),
                "positive_size_within_benign_10_90pct": float(np.mean((sizes >= np.percentile(benign_bytes, 10)) & (sizes <= np.percentile(benign_bytes, 90)))),
                "positive_packets_within_benign_10_90pct": float(np.mean((packets >= np.percentile(benign_packets, 10)) & (packets <= np.percentile(benign_packets, 90)))),
            })
    write_csv(RESULTS_DIR / "traffic_transport_pilot.csv", summary)
    print({
        "background_files": len(background_files),
        "background_tcp_flows": len(benign),
        "background_stream_FHAM_flows": benign_marker,
        "background_stream_FHAM_version1_flows": benign_versioned_fham,
        "background_stream_FHMS_version1_flows": benign_versioned,
        "generated_captures": {k: str(v) for k, v in captures.items()},
        "summary": summary,
    })


if __name__ == "__main__":
    main()
