#!/usr/bin/env python3
"""Generate real V1 TCP/TLS 1.3 sessions for the frozen D-2/D-3 design.

PktMon capture is started and stopped outside this process so the capture
driver's required privilege is explicit. Use --pilot for implementation checks;
only --full outputs are eligible for the protocol's classifier analysis.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import random
import socket
import sqlite3
import ssl
import struct
import sys
import tempfile
import threading
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.x509.oid import NameOID
from reedsolo import RSCodec

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_step1quater as q4
from fham.v1 import (
    FRAME, FRAME_CONFIRM, FRAME_OFFER, FRAME_RECORD, RECORD_R0, RECORD_R1,
    R1_CAPACITY, V1RecordSender, V1ReplayGuard, accept_v1_record,
    build_inner_header, catalogue_digest, create_offer, derive_v1_keys,
    encode_params, frame, key_confirmation, pack_slot, transcript_hash,
    unpack_record, unpack_slot, unframe, verify_key_confirmation, verify_offer,
)

OUT = ROOT / "results/step2/detection"
SESSIONS = OUT / "dmsg_sessions.csv"
ASSIGNMENTS = OUT / "dmsg_selected_2000_per_family.csv.gz"
COVER_MANIFEST = ROOT / "results/stability_step1/step1quater/manifest/D_b_images_sha256.csv"
# One dedicated local port is reused sequentially so the OS capture filter
# remains narrowly scoped to this experiment.
PORTS = {("TCP", RECORD_R0): 45511, ("TCP", RECORD_R1): 45511,
         ("TLS13", RECORD_R0): 45511, ("TLS13", RECORD_R1): 45511}
MAX_FRAME = 2**20
INTERVAL_SECONDS = 0.002
COVER_IDS = []


def _read_exact(sock, length):
    chunks, remaining = [], length
    while remaining:
        block = sock.recv(remaining)
        if not block:
            raise EOFError("socket closed before the protocol frame completed")
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def _read_frame(sock):
    head = _read_exact(sock, FRAME.size)
    magic, version, kind, length = FRAME.unpack(head)
    if magic != b"FHAM" or version != 2 or length > MAX_FRAME:
        raise ValueError("invalid application frame in local receiver")
    return head + _read_exact(sock, length)


class TrackedStream:
    """Real TCP stream with optional TLS 1.3 and endpoint-visible wire metrics.

    On this Windows host PktMon exposes no loopback component. This records
    actual socket writes/reads and, for TLS, exact TLS record sizes from the
    TLS 1.3 MemoryBIO byte streams; it does not claim TCP packet boundaries.
    """

    def __init__(self, raw, transport, context=None, server_side=False):
        self.raw = raw
        self.transport = transport
        self.tls = transport == "TLS13"
        self.tx_calls, self.rx_calls = [], []
        self.tx_records, self.rx_records = [], []
        self.tx_wire = bytearray()
        self.rx_wire = bytearray()
        self.tx_plain_bytes = 0
        self.rx_plain_bytes = 0
        self._inbio = ssl.MemoryBIO() if self.tls else None
        self._outbio = ssl.MemoryBIO() if self.tls else None
        self._tls_input = bytearray()
        self._sslobj = context.wrap_bio(
            self._inbio, self._outbio, server_side=server_side,
            server_hostname=None if server_side else "127.0.0.1") if self.tls else None
        if self.tls:
            self._handshake()

    @staticmethod
    def _extract_records(buffer):
        result = []
        while len(buffer) >= 5:
            size = 5 + int.from_bytes(buffer[3:5], "big")
            if len(buffer) < size:
                break
            result.append({"content_type": int(buffer[0]),
                           "legacy_version": buffer[1:3].hex(), "record_bytes": size})
            del buffer[:size]
        return result

    def _flush_tls(self):
        while self._outbio.pending:
            data = self._outbio.read()
            self.tx_records.extend(self._extract_records(bytearray(data)))
            self.tx_wire.extend(data)
            self.tx_calls.append({"bytes": len(data), "time_ns": time.perf_counter_ns()})
            self.raw.sendall(data)

    def _feed_tls(self):
        data = self.raw.recv(65536)
        if not data:
            self._inbio.write_eof()
            raise EOFError("TCP closed during TLS 1.3 read")
        self.rx_calls.append({"bytes": len(data), "time_ns": time.perf_counter_ns()})
        self.rx_wire.extend(data)
        self._tls_input.extend(data)
        self.rx_records.extend(self._extract_records(self._tls_input))
        self._inbio.write(data)

    def _handshake(self):
        while True:
            try:
                self._sslobj.do_handshake()
                self._flush_tls()
                return
            except ssl.SSLWantReadError:
                self._flush_tls()
                self._feed_tls()
            except ssl.SSLWantWriteError:
                self._flush_tls()

    def sendall(self, data):
        data = bytes(data)
        self.tx_plain_bytes += len(data)
        if not self.tls:
            self.tx_calls.append({"bytes": len(data), "time_ns": time.perf_counter_ns()})
            self.tx_wire.extend(data)
            return self.raw.sendall(data)
        offset = 0
        while offset < len(data):
            try:
                offset += self._sslobj.write(data[offset:])
                self._flush_tls()
            except ssl.SSLWantWriteError:
                self._flush_tls()
            except ssl.SSLWantReadError:
                self._flush_tls()
                self._feed_tls()

    def recv(self, length):
        if not self.tls:
            data = self.raw.recv(length)
            self.rx_calls.append({"bytes": len(data), "time_ns": time.perf_counter_ns()})
            self.rx_wire.extend(data)
            self.rx_plain_bytes += len(data)
            return data
        while True:
            try:
                data = self._sslobj.read(length)
                self._flush_tls()
                self.rx_plain_bytes += len(data)
                return data
            except ssl.SSLWantReadError:
                self._flush_tls()
                self._feed_tls()
            except ssl.SSLWantWriteError:
                self._flush_tls()

    def shutdown(self, how):
        return self.raw.shutdown(how)

    def close(self):
        return self.raw.close()

    def metrics(self):
        return {
            "client_or_peer_tx_calls": self.tx_calls,
            "client_or_peer_rx_calls": self.rx_calls,
            "tls_tx_records": self.tx_records,
            "tls_rx_records": self.rx_records,
            "tx_wire_bytes": len(self.tx_wire),
            "rx_wire_bytes": len(self.rx_wire),
            "tx_plain_bytes": self.tx_plain_bytes,
            "rx_plain_bytes": self.rx_plain_bytes,
            "marker_FHAM_tx": int(b"FHAM" in self.tx_wire),
            "marker_FHAM_rx": int(b"FHAM" in self.rx_wire),
            "marker_FHQ2_tx": int(b"FHQ2" in self.tx_wire),
            "marker_FHQ2_rx": int(b"FHQ2" in self.rx_wire),
        }


def _load_catalogue():
    global COVER_IDS
    manifest = pd.read_csv(COVER_MANIFEST, keep_default_na=False)
    images = []
    id_to_index = {}
    for index, row in enumerate(manifest.itertuples(index=False)):
        path = q4.IMAGE_ROOT / row.relative_path
        if q4.digest(path) != row.sha256:
            raise RuntimeError(f"D-b image manifest mismatch: {path.name}")
        images.append(np.asarray(Image.open(path).convert("L"), dtype=np.uint8))
        id_to_index[str(row.source_id)] = index
        COVER_IDS.append(str(row.source_id))
    return images, id_to_index, catalogue_digest(images)


def _make_inner(row, mode, id_to_index):
    compressed = (base64.b64decode(row.segment0_compressed_b64),
                  base64.b64decode(row.segment1_compressed_b64))
    codewords = (base64.b64decode(row.segment0_codeword_b64),
                 base64.b64decode(row.segment1_codeword_b64))
    slots = json.loads(row.segment0_slots) + json.loads(row.segment1_slots)
    cover_ids = (str(row.cover0_id), str(row.cover1_id))
    selected = (str(row.selected_cover_segment0), str(row.selected_cover_segment1))
    pairs = []
    for chosen_id in selected:
        pairs.append((id_to_index[cover_ids[0]], id_to_index[cover_ids[1]],
                      0 if chosen_id == cover_ids[0] else 1))
    digest = hashlib.sha256(b"".join(compressed)).digest()[:16]
    placed = sum((int(slot) >> 15) == 0 for slot in slots)
    inner = build_inner_header(
        mode=mode, height=256, width=256, m=2, p=10, q=5, bound=4,
        block_size=12, descriptor_id=1, integrity_id=1, source_len=100,
        compressed_segments=compressed, codeword_segments=codewords,
        gallery_pairs=tuple(pairs), placed_count=placed,
        integrity_digest=digest,
    )
    params = encode_params(mode=mode, capacity=0 if mode == RECORD_R0 else R1_CAPACITY,
                           m=2, p=10, q=5, bound=4, block_size=12,
                           descriptor_id=1, integrity_id=1)
    return inner, slots, params, compressed


def _decode_assignment(header, slots, catalogue):
    recovered_segments = []
    cursor = 0
    for segment in header.segments:
        segment_slots = slots[cursor:cursor + segment.codeword_len]
        cursor += segment.codeword_len
        cover_index = segment.cover0 if segment.chosen == 0 else segment.cover1
        cover_id = COVER_IDS[cover_index]
        locations, hashes, _, _ = q4.load_codebook(cover_id)
        codebook = {location: int(value) for location, value in zip(locations, hashes)}
        received = bytearray(segment.codeword_len)
        erasures = []
        for index, slot in enumerate(segment_slots):
            erased, token, delta = unpack_slot(int(slot))
            if erased:
                erasures.append(index)
                continue
            block, arrangement = divmod(token, 4)
            location = q4.Location((block % (256 // q4.BLOCK)) * q4.BLOCK,
                                   (block // (256 // q4.BLOCK)) * q4.BLOCK,
                                   arrangement)
            value = codebook[location] + int(delta)
            received[index] = min(255, max(0, value))
        parity = int(np.ceil(0.10 * segment.compressed_len))
        codec = RSCodec(parity, nsize=255, fcr=0, generator=2,
                        prim=0x11D, c_exp=8)
        if len(erasures) > parity:
            raise ValueError("received V1 segment exceeds its Reed-Solomon erasure budget")
        decoded = bytes(codec.decode(bytes(received), erase_pos=erasures)[0])
        recovered_segments.append(decoded)
    if cursor != len(slots):
        raise ValueError("V1 slot directory was not fully consumed")
    return tuple(recovered_segments)


def _create_tls_cert(directory):
    private = generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FHAM local test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(private.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(private, hashes.SHA256()))
    key_path = Path(directory) / "local_tls_key.pem"
    cert_path = Path(directory) / "local_tls_cert.pem"
    key_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def _tls_contexts(cert_path, key_path):
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = server.maximum_version = ssl.TLSVersion.TLSv1_3
    server.options |= ssl.OP_NO_TICKET
    server.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    client.minimum_version = client.maximum_version = ssl.TLSVersion.TLSv1_3
    client.options |= ssl.OP_NO_TICKET
    client.load_verify_locations(cafile=str(cert_path))
    return server, client


def _serve_condition(server_socket, transport, mode, stop_count, cert_context,
                     catalogue, cat_hash, identities, replay_db, message_payloads,
                     flow_registry, registry_condition, outcomes, error_box):
    epoch = [1]
    guard = V1ReplayGuard(replay_db, lambda: epoch[0])
    try:
        for _ in range(stop_count):
            conn, address = server_socket.accept()
            client_port = int(address[1])
            with registry_condition:
                if not registry_condition.wait_for(lambda: client_port in flow_registry, timeout=30):
                    raise TimeoutError("client did not register its flow label")
                flow = flow_registry[client_port]
            conn.settimeout(30)
            if transport == "TLS13":
                conn = TrackedStream(conn, "TLS13", cert_context, server_side=True)
            else:
                conn = TrackedStream(conn, "TCP")
            label = flow["label"]
            try:
                if label == "positive":
                    first = _read_frame(conn)
                    kind, payload = unframe(first)
                    if kind != FRAME_OFFER:
                        raise ValueError("positive flow does not start with a V1 offer")
                    if len(payload) != 117:
                        raise ValueError("invalid role-0 offer length")
                    sid = payload[1:17]
                    epoch_value = struct.unpack("!I", payload[49:53])[0]
                    peer_eph = verify_offer(
                        payload, sender_identity=identities[0].public_key(),
                        recipient_identity=identities[1].public_key(), expected_role=0,
                        expected_session_id=sid, expected_epoch=epoch_value)
                    eph_local = X25519PrivateKey.generate()
                    offer1 = create_offer(
                        identity_private=identities[1], ephemeral_private=eph_local,
                        peer_identity=identities[0].public_key(), role=1,
                        session_id=sid, epoch=epoch_value)
                    conn.sendall(frame(FRAME_OFFER, offer1))
                    pub1 = verify_offer(
                        offer1, sender_identity=identities[1].public_key(),
                        recipient_identity=identities[0].public_key(), expected_role=1,
                        expected_session_id=sid, expected_epoch=epoch_value)
                    mode_params = encode_params(mode=mode,
                        capacity=0 if mode == RECORD_R0 else R1_CAPACITY,
                        m=2, p=10, q=5, bound=4, block_size=12, descriptor_id=1)
                    transcript = transcript_hash(payload, offer1, catalog_hash=cat_hash,
                                                 epoch=epoch_value, params=mode_params)
                    keys = derive_v1_keys(eph_local, peer_eph, sid, transcript)
                    confirm0 = unframe(_read_frame(conn))[1]
                    verify_key_confirmation(keys, 0, transcript, confirm0)
                    conn.sendall(frame(FRAME_CONFIRM, key_confirmation(keys, 1, transcript)))
                    guard.register_session(sid, epoch_value)
                    for sequence in range(5):
                        wire = _read_frame(conn)
                        frame_kind, record = unframe(wire)
                        if frame_kind != FRAME_RECORD:
                            raise ValueError("positive flow contains a non-record application frame")
                        peek = unpack_record(
                            record, key=keys.aead_role0, expected_session_id=sid,
                            expected_sequence=sequence, expected_epoch=epoch_value,
                            catalog_hash=cat_hash,
                            params=encode_params(mode=mode,
                                capacity=0 if mode == RECORD_R0 else R1_CAPACITY,
                                m=2, p=10, q=5, bound=4, block_size=12,
                                descriptor_id=1))
                        compressed = _decode_assignment(peek[0], peek[1], catalogue)
                        selected_covers = [catalogue[s.cover0 if s.chosen == 0 else s.cover1]
                                           for s in peek[0].segments]
                        # Pinned catalogue and I1 are checked before replay state advances.
                        _, _, rebuilt = accept_v1_record(
                            record=record, key=keys.aead_role0, expected_session_id=sid,
                            expected_sequence=sequence, expected_epoch=epoch_value,
                            catalog_hash=cat_hash, params=encode_params(mode=mode,
                                capacity=0 if mode == RECORD_R0 else R1_CAPACITY,
                                m=2, p=10, q=5, bound=4, block_size=12,
                                descriptor_id=1), catalogue=catalogue,
                            received_covers=selected_covers,
                            decoded_compressed_segments=compressed,
                            replay_guard=guard)
                        expected_ids = flow["candidate_ids"]
                        candidate_id = expected_ids[sequence]
                        expected = message_payloads[candidate_id]
                        reconstructed = b"".join(zlib.decompress(part) for part in compressed)
                        if reconstructed != expected:
                            raise ValueError("end-to-end reconstructed source differs")
                    outcomes.append({"client_port": client_port, "label": label,
                                     "accepted_records": 5, "receiver_exact": 1})
                else:
                    for _record in range(5):
                        payload = _read_exact(conn, 100)
                        if len(payload) != 100:
                            raise ValueError("ordinary control record is not 100 source bytes")
                    outcomes.append({"client_port": client_port, "label": label,
                                     "accepted_records": 5, "receiver_exact": 1})
            except Exception as exc:
                error_box.append(f"server port {server_socket.getsockname()[1]}, client {client_port}: {type(exc).__name__}: {exc}")
                raise
            finally:
                server_metrics = conn.metrics()
                for outcome in reversed(outcomes):
                    if outcome.get("client_port") == client_port:
                        outcome["server_endpoint_metrics"] = server_metrics
                        break
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()
    except Exception as exc:
        if not error_box:
            error_box.append(f"server: {type(exc).__name__}: {exc}")
    finally:
        server_socket.close()


def _positive_client(sock, transport, mode, session_key, identity0, identity1,
                     cat_hash, catalogue_index, session_records, assignment_map,
                     message_payloads):
    sid = os.urandom(16)
    epoch = 1
    eph0 = X25519PrivateKey.generate()
    offer0 = create_offer(identity_private=identity0, ephemeral_private=eph0,
                          peer_identity=identity1.public_key(), role=0,
                          session_id=sid, epoch=epoch)
    sock.sendall(frame(FRAME_OFFER, offer0))
    kind, offer1 = unframe(_read_frame(sock))
    if kind != FRAME_OFFER:
        raise ValueError("server did not return a signed offer")
    peer_eph = verify_offer(offer1, sender_identity=identity1.public_key(),
                            recipient_identity=identity0.public_key(), expected_role=1,
                            expected_session_id=sid, expected_epoch=epoch)
    params = encode_params(mode=mode,
                           capacity=0 if mode == RECORD_R0 else R1_CAPACITY,
                           m=2, p=10, q=5, bound=4, block_size=12,
                           descriptor_id=1)
    transcript = transcript_hash(offer0, offer1, catalog_hash=cat_hash,
                                 epoch=epoch, params=params)
    keys = derive_v1_keys(eph0, peer_eph, sid, transcript)
    sock.sendall(frame(FRAME_CONFIRM, key_confirmation(keys, 0, transcript)))
    kind, confirm1 = unframe(_read_frame(sock))
    if kind != FRAME_CONFIRM:
        raise ValueError("server did not return a key confirmation")
    verify_key_confirmation(keys, 1, transcript, confirm1)
    sender = V1RecordSender(key=keys.aead_role0, session_id=sid, mode=mode,
                            epoch=epoch, catalog_hash=cat_hash, params=params)
    time.sleep(0.02)
    candidate_ids = []
    for sequence, candidate_id in enumerate(session_records):
        inner, slots, _params, _compressed = _make_inner(
            assignment_map[candidate_id], mode, catalogue_index)
        record = sender.seal(inner_header=inner, slots=slots)
        sock.sendall(frame(FRAME_RECORD, record))
        candidate_ids.append(candidate_id)
        time.sleep(INTERVAL_SECONDS)
    return sid.hex(), candidate_ids


def _control_client(sock, session_records, message_payloads):
    time.sleep(0.02)
    for candidate_id in session_records:
        payload = message_payloads[candidate_id]
        if len(payload) != 100:
            raise ValueError("control message must contain 100 bytes")
        sock.sendall(payload)
        time.sleep(INTERVAL_SECONDS)
    return "", list(session_records)


def _make_tls_context(directory):
    cert_path, key_path = _create_tls_cert(directory)
    return _tls_contexts(cert_path, key_path)


def run_condition(transport, mode, split_filter, per_split, tls_contexts,
                  catalogue, cat_hash, catalogue_index, identities,
                  assignments, payloads, out_rows, outcome_rows, error_box,
                  db_path, pilot=False):
    port = PORTS[(transport, mode)]
    outcome_start = len(outcome_rows)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", port))
    server_socket.listen(128)
    server_context = tls_contexts[0] if transport == "TLS13" else None
    client_context = tls_contexts[1] if transport == "TLS13" else None
    split_sessions = []
    manifest = pd.read_csv(SESSIONS)
    for split in split_filter:
        subset = manifest[manifest.split == split]
        grouped = [(sid, group.sort_values("record_index").candidate_id.tolist())
                   for sid, group in subset.groupby("session_id", sort=True)]
        if pilot:
            grouped = grouped[:per_split[split]]
        elif len(grouped) != per_split[split]:
            raise RuntimeError(f"{split} expected {per_split[split]} sessions, observed {len(grouped)}")
        split_sessions.extend((split, sid, ids) for sid, ids in grouped)
    plans = []
    for split, base_id, ids in split_sessions:
        plans.append({"split": split, "base_id": base_id, "label": "positive", "ids": ids})
        plans.append({"split": split, "base_id": base_id, "label": "control", "ids": ids})
    random.Random(20261121 + port).shuffle(plans)
    errors_server = []
    flow_registry = {}
    registry_condition = threading.Condition()
    server_thread = threading.Thread(
        target=_serve_condition,
        args=(server_socket, transport, mode, len(plans), server_context,
              catalogue, cat_hash, identities, db_path, payloads,
              flow_registry, registry_condition, outcome_rows, errors_server), daemon=True)
    server_thread.start()
    for index, plan in enumerate(plans):
        sock = socket.create_connection(("127.0.0.1", port), timeout=30)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(30)
        local_port = int(sock.getsockname()[1])
        with registry_condition:
            flow_registry[local_port] = {"label": plan["label"],
                                         "candidate_ids": plan["ids"]}
            registry_condition.notify_all()
        if transport == "TLS13":
            sock = TrackedStream(sock, "TLS13", client_context)
        else:
            sock = TrackedStream(sock, "TCP")
        start = time.perf_counter()
        if plan["label"] == "positive":
            session_id, record_ids = _positive_client(
                sock, transport, mode, None, identities[0], identities[1],
                cat_hash, catalogue_index, plan["ids"], assignments, payloads)
        else:
            session_id, record_ids = _control_client(sock, plan["ids"], payloads)
        end = time.perf_counter()
        client_metrics = sock.metrics()
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        sock.close()
        out_rows.append({"condition": f"{transport}_R{mode}", "transport": transport,
                         "mode": f"R{mode}", "split": plan["split"],
                         "base_session_id": plan["base_id"], "label": plan["label"],
                         "client_port": local_port, "server_port": port,
                         "session_id": session_id, "record_ids": ";".join(record_ids),
                         "client_endpoint_metrics": json.dumps(client_metrics),
                         "client_start_monotonic": start, "client_end_monotonic": end,
                         "client_duration_seconds": end - start})
        if (index + 1) % 100 == 0:
            print(f"{transport} R{mode}: {index+1}/{len(plans)} sessions", flush=True)
    server_thread.join(timeout=60)
    if server_thread.is_alive():
        raise RuntimeError("receiver server did not finish the condition")
    if errors_server:
        raise RuntimeError(errors_server[0])
    new_outcomes = outcome_rows[outcome_start:]
    if len(new_outcomes) != len(plans) or any(x["receiver_exact"] != 1 for x in new_outcomes):
        raise RuntimeError("receiver did not validate every generated session")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true", help="one train session per split, implementation only")
    parser.add_argument("--full", action="store_true", help="run the frozen 1,600 sessions per condition")
    args = parser.parse_args()
    if args.pilot == args.full:
        parser.error("choose exactly one of --pilot or --full")
    if not SESSIONS.exists() or not ASSIGNMENTS.exists():
        raise RuntimeError("D-msg selection and grouped session split must be complete")
    OUT.mkdir(parents=True, exist_ok=True)
    selected = pd.read_csv(ASSIGNMENTS, compression="gzip", keep_default_na=False)
    assignments = {str(row.candidate_id): row for row in selected.itertuples(index=False)}
    payloads = {candidate_id: (ROOT / row.path).read_bytes()
                for candidate_id, row in assignments.items()}
    if any(len(value) != 100 for value in payloads.values()):
        raise RuntimeError("all D-msg payloads must contain exactly 100 bytes")
    catalogue, catalogue_index, cat_hash = _load_catalogue()
    identities = (Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
    capture_root = OUT / ("pilot_capture" if args.pilot else "full_capture")
    capture_root.mkdir(parents=True, exist_ok=True)
    outcomes, flow_rows, errors = [], [], []
    with tempfile.TemporaryDirectory(prefix="fham_step2_tls_") as temp:
        tls_contexts = _make_tls_context(temp)
        split_filter = ("train",) if args.pilot else ("train", "validation", "test")
        per_split = {"train": 2} if args.pilot else {
            "train": 400, "validation": 200, "test": 1000}
        for transport in ("TCP", "TLS13"):
            for mode in (RECORD_R0, RECORD_R1):
                db_path = capture_root / f"replay_{transport}_R{mode}.sqlite"
                if db_path.exists():
                    db_path.unlink()
                run_condition(transport, mode, split_filter, per_split, tls_contexts,
                              catalogue, cat_hash, catalogue_index, identities,
                              assignments, payloads, flow_rows, outcomes, errors,
                              db_path, pilot=args.pilot)
                print(f"completed {transport} R{mode}: {len(flow_rows)} total flows", flush=True)
    flows = pd.DataFrame(flow_rows)
    flows.to_csv(capture_root / "session_flow_manifest.csv", index=False)
    pd.DataFrame(outcomes).to_csv(capture_root / "receiver_acceptance.csv", index=False)
    result = {"scope": "pilot only" if args.pilot else "frozen D test and train/validation capture",
              "pilot_not_for_classifier": bool(args.pilot),
              "flows": len(flows), "positive": int((flows.label == "positive").sum()),
              "controls": int((flows.label == "control").sum()),
              "receiver_validated_sessions": len(outcomes),
              "receiver_exact_failures": int(sum(x["receiver_exact"] != 1 for x in outcomes)),
              "protocol_ports": {f"{k[0]}_R{k[1]}": v for k, v in PORTS.items()},
              "catalogue_sha256": cat_hash.hex(), "source_records_per_session": 5,
              "interval_seconds": INTERVAL_SECONDS,
              "tls_version": ssl.OPENSSL_VERSION,
              "observation_method": "endpoint-visible TCP socket writes/reads and TLS 1.3 record lengths; not packet capture",
              "packet_capture": "unavailable for Windows loopback with current PktMon adapter set; no pcap claim"}
    (capture_root / "capture_metadata.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
