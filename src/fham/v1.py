"""Frozen FHAM V1 record and authenticated ephemeral session primitives.

This module implements the wire profile in
``protocols/FHAM_etape_2_addendum_gel_2026-11-21.md``. It is an experimental
record layer; it does not implement a general-purpose TLS stack.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import struct
import threading
import zlib
from contextlib import closing
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


FRAME = struct.Struct("!4sBBI")
FRAME_MAGIC = b"FHAM"
FRAME_VERSION = 2
FRAME_OFFER = 1
FRAME_CONFIRM = 2
FRAME_RECORD = 3

OUTER = struct.Struct("!4sBB16sQ12sH")
OUTER_MAGIC = b"FHQ2"
RECORD_VERSION = 2
RECORD_R0 = 0
RECORD_R1 = 1
R1_CAPACITY = 140
GCM_TAG_BYTES = 16

INNER_PREFIX = struct.Struct("!2sBBHH7B4HB")
INNER_SEGMENT = struct.Struct("!BHHBBB")
INNER_MAGIC = b"FH"
INNER_VERSION = 2
INNER_BYTES = INNER_PREFIX.size + 2 * INNER_SEGMENT.size + 16
assert INNER_PREFIX.size == 24
assert INNER_SEGMENT.size == 8
assert INNER_BYTES == 56

AAD_DOMAIN = b"FHAM-1quater-V1-AAD"
GALLERY_DOMAIN = b"FHAM-CATALOG-v1"
OFFER_DOMAIN = b"FHAM-X25519-OFFER-v2"
HKDF_DOMAIN = b"FHAM-V1-HKDF"
MAX_CATALOGUE = 256
MAX_CODEWORD = 140
MAX_INNER_PLAINTEXT = INNER_BYTES + 2 * MAX_CODEWORD
MAX_R0_COMPRESSED = MAX_INNER_PLAINTEXT + (MAX_INNER_PLAINTEXT >> 12) + 13
MAX_FRAME_PAYLOAD = OUTER.size + GCM_TAG_BYTES + MAX_R0_COMPRESSED


@dataclass(frozen=True)
class SegmentInfo:
    source_len: int
    compressed_len: int
    codeword_len: int
    cover0: int
    cover1: int
    chosen: int


@dataclass(frozen=True)
class InnerHeader:
    mode: int
    height: int
    width: int
    m: int
    p: int
    q: int
    bound: int
    block_size: int
    descriptor_id: int
    integrity_id: int
    source_len: int
    compressed_len: int
    codeword_len: int
    placed_count: int
    segments: tuple[SegmentInfo, SegmentInfo]
    integrity_digest: bytes


@dataclass(frozen=True)
class V1Keys:
    aead_role0: bytes
    aead_role1: bytes
    confirm_role0: bytes
    confirm_role1: bytes


def frame(kind: int, payload: bytes) -> bytes:
    if kind not in (FRAME_OFFER, FRAME_CONFIRM, FRAME_RECORD):
        raise ValueError("unknown V1 frame type")
    if len(payload) > MAX_FRAME_PAYLOAD:
        raise ValueError("frame payload exceeds the frozen V1 maximum")
    return FRAME.pack(FRAME_MAGIC, FRAME_VERSION, kind, len(payload)) + payload


def unframe(data: bytes) -> tuple[int, bytes]:
    if len(data) < FRAME.size:
        raise ValueError("truncated V1 frame header")
    magic, version, kind, length = FRAME.unpack_from(data)
    if magic != FRAME_MAGIC or version != FRAME_VERSION:
        raise ValueError("unsupported V1 frame")
    if kind not in (FRAME_OFFER, FRAME_CONFIRM, FRAME_RECORD):
        raise ValueError("unknown V1 frame type")
    if length > MAX_FRAME_PAYLOAD or len(data) != FRAME.size + length:
        raise ValueError("V1 frame length mismatch")
    return kind, data[FRAME.size:]


def _uint(value: int, bits: int, name: str) -> int:
    if not isinstance(value, int) or not 0 <= value < 2**bits:
        raise ValueError(f"{name} must fit uint{bits}")
    return value


def canonical_cover_digest(image) -> bytes:
    """Digest canonical grayscale uint8 image using the repository definition."""
    import numpy as np

    array = np.asarray(image)
    if array.ndim != 2 or array.dtype != np.uint8:
        raise ValueError("cover must be a two-dimensional grayscale uint8 array")
    array = np.ascontiguousarray(array)
    return hashlib.sha256(
        b"FHAM-CANONICAL-REFERENCE-v1"
        + struct.pack(">II", array.shape[0], array.shape[1])
        + array.tobytes(order="C")
    ).digest()


def catalogue_digest(images) -> bytes:
    if not 1 <= len(images) <= MAX_CATALOGUE:
        raise ValueError("catalogue must contain between 1 and 256 covers")
    digests = b"".join(canonical_cover_digest(image) for image in images)
    return hashlib.sha256(GALLERY_DOMAIN + struct.pack(">H", len(images)) + digests).digest()


def encode_params(*, mode: int, capacity: int, m: int, p: int, q: int,
                  bound: int, block_size: int, descriptor_id: int,
                  integrity_id: int = 1) -> bytes:
    values = (RECORD_VERSION, m, p, q, bound, block_size, descriptor_id, mode)
    for name, value in zip(
        ("version", "m", "p", "q", "B", "L", "descriptor_id", "mode"), values
    ):
        _uint(value, 8, name)
    _uint(capacity, 16, "capacity")
    _uint(integrity_id, 8, "integrity_id")
    return struct.pack("!8BH B", *values, capacity, integrity_id)


def build_inner_header(
    *, mode: int, height: int, width: int, m: int, p: int, q: int,
    bound: int, block_size: int, descriptor_id: int, integrity_id: int,
    source_len: int, compressed_segments: tuple[bytes, bytes],
    codeword_segments: tuple[bytes, bytes],
    gallery_pairs: tuple[tuple[int, int, int], tuple[int, int, int]],
    placed_count: int, integrity_digest: bytes,
) -> bytes:
    if mode not in (RECORD_R0, RECORD_R1):
        raise ValueError("mode must be R0 or R1")
    if len(compressed_segments) != 2 or len(codeword_segments) != 2:
        raise ValueError("V1 profile requires exactly two 50-byte source segments")
    if sum(len(x) for x in codeword_segments) > MAX_CODEWORD:
        raise ValueError("codeword exceeds the frozen 140-slot capacity")
    if len(integrity_digest) != 16:
        raise ValueError("I1 digest must contain exactly 16 bytes")
    if source_len != sum((50, 50)):
        raise ValueError("frozen V1 profile requires 100 source bytes in two 50-byte segments")
    for pair in gallery_pairs:
        c0, c1, chosen = pair
        _uint(c0, 8, "cover0")
        _uint(c1, 8, "cover1")
        if c0 == c1 or chosen not in (0, 1):
            raise ValueError("each segment requires two distinct covers and choice 0 or 1")
    comp_lens = tuple(len(x) for x in compressed_segments)
    cw_lens = tuple(len(x) for x in codeword_segments)
    if any(x > 0xFFFF for x in comp_lens + cw_lens):
        raise ValueError("segment length exceeds uint16")
    total_comp, total_cw = sum(comp_lens), sum(cw_lens)
    if total_cw > MAX_CODEWORD:
        raise ValueError("codeword exceeds the frozen 140-slot capacity")
    prefix = INNER_PREFIX.pack(
        INNER_MAGIC, INNER_VERSION, mode, _uint(height, 16, "height"),
        _uint(width, 16, "width"), _uint(m, 8, "m"), _uint(p, 8, "p"),
        _uint(q, 8, "q"), _uint(bound, 8, "B"), _uint(block_size, 8, "L"),
        _uint(descriptor_id, 8, "descriptor_id"), _uint(integrity_id, 8, "integrity_id"),
        _uint(source_len, 16, "source_len"), _uint(total_comp, 16, "compressed_len"),
        _uint(total_cw, 16, "codeword_len"), _uint(placed_count, 16, "placed_count"), 2,
    )
    entries = b"".join(
        INNER_SEGMENT.pack(50, comp_len, cw_len, *pair)
        for comp_len, cw_len, pair in zip(comp_lens, cw_lens, gallery_pairs)
    )
    result = prefix + entries + integrity_digest
    if len(result) != INNER_BYTES:
        raise AssertionError("internal V1 header length invariant failed")
    return result


def parse_inner_header(data: bytes) -> InnerHeader:
    if len(data) != INNER_BYTES:
        raise ValueError("V1 inner header must be exactly 56 bytes")
    values = INNER_PREFIX.unpack_from(data)
    (magic, version, mode, height, width, m, p, q, bound, block_size,
     descriptor_id, integrity_id, source_len, compressed_len, codeword_len,
     placed_count, segment_count) = values
    if magic != INNER_MAGIC or version != INNER_VERSION:
        raise ValueError("unsupported V1 inner header")
    if mode not in (RECORD_R0, RECORD_R1) or segment_count != 2:
        raise ValueError("invalid V1 mode or segment count")
    offset = INNER_PREFIX.size
    segments = []
    for _ in range(2):
        source_n, comp_n, cw_n, cover0, cover1, chosen = INNER_SEGMENT.unpack_from(data, offset)
        offset += INNER_SEGMENT.size
        if source_n != 50 or cover0 == cover1 or chosen not in (0, 1):
            raise ValueError("invalid V1 segment directory")
        segments.append(SegmentInfo(source_n, comp_n, cw_n, cover0, cover1, chosen))
    digest = data[offset:offset + 16]
    if sum(x.source_len for x in segments) != source_len:
        raise ValueError("source-length directory mismatch")
    if sum(x.compressed_len for x in segments) != compressed_len:
        raise ValueError("compressed-length directory mismatch")
    if sum(x.codeword_len for x in segments) != codeword_len or codeword_len > MAX_CODEWORD:
        raise ValueError("codeword-length directory mismatch")
    if placed_count > codeword_len:
        raise ValueError("placed count exceeds codeword length")
    return InnerHeader(
        mode, height, width, m, p, q, bound, block_size, descriptor_id,
        integrity_id, source_len, compressed_len, codeword_len, placed_count,
        (segments[0], segments[1]), digest,
    )


def validate_cover_binding(header: InnerHeader, catalogue, received_covers) -> None:
    """Require each untransformed received cover to match its selected entry."""
    if len(catalogue) > MAX_CATALOGUE or len(received_covers) != len(header.segments):
        raise ValueError("invalid catalogue or received-cover count")
    for segment, received in zip(header.segments, received_covers):
        for cover_id in (segment.cover0, segment.cover1):
            if cover_id >= len(catalogue):
                raise ValueError("segment references an unknown catalogue entry")
        chosen_id = segment.cover0 if segment.chosen == 0 else segment.cover1
        if canonical_cover_digest(received) != canonical_cover_digest(catalogue[chosen_id]):
            raise ValueError("received cover does not match the authenticated selection")


def verify_integrity(compressed_segments, expected_digest: bytes) -> bytes:
    """Verify I1 after RS decoding and return the concatenated compressed bytes."""
    if len(compressed_segments) != 2 or len(expected_digest) != 16:
        raise ValueError("invalid V1 integrity input")
    compressed = b"".join(compressed_segments)
    if not hmac.compare_digest(hashlib.sha256(compressed).digest()[:16], expected_digest):
        raise ValueError("V1 reconstructed-message integrity check failed")
    return compressed


class V1RecordSender:
    """Stateful sender enforcing unique nonces for one session direction/key."""

    def __init__(self, *, key: bytes, session_id: bytes, mode: int, epoch: int,
                 catalog_hash: bytes, params: bytes, first_sequence: int = 0):
        if len(key) != 32 or len(session_id) != 16 or len(catalog_hash) != 32:
            raise ValueError("invalid V1 sender context")
        if not 0 <= first_sequence < 2**64:
            raise ValueError("invalid first sequence")
        self._key, self._session_id = bytes(key), bytes(session_id)
        self._mode, self._epoch = mode, epoch
        self._catalog_hash, self._params = bytes(catalog_hash), bytes(params)
        self._next_sequence = first_sequence
        self._nonces: set[bytes] = set()

    def seal(self, *, inner_header: bytes, slots: list[int], nonce: bytes | None = None) -> bytes:
        if len(self._nonces) >= 2**32:
            raise ValueError("V1 sender nonce budget exhausted")
        nonce = os.urandom(12) if nonce is None else bytes(nonce)
        if len(nonce) != 12 or nonce in self._nonces:
            raise ValueError("invalid or reused V1 AES-GCM nonce")
        record = pack_record(
            inner_header=inner_header, slots=slots, key=self._key,
            session_id=self._session_id, sequence=self._next_sequence,
            mode=self._mode, epoch=self._epoch,
            catalog_hash=self._catalog_hash, params=self._params, nonce=nonce,
        )
        self._nonces.add(nonce)
        self._next_sequence += 1
        return record


def accept_v1_record(*, record: bytes, key: bytes, expected_session_id: bytes,
                     expected_sequence: int, expected_epoch: int,
                     catalog_hash: bytes, params: bytes, catalogue,
                     received_covers, decoded_compressed_segments,
                     replay_guard: "V1ReplayGuard"):
    """Validate AEAD, cover selection and I1 before atomically advancing replay state."""
    header, slots = unpack_record(
        record, key=key, expected_session_id=expected_session_id,
        expected_sequence=expected_sequence, expected_epoch=expected_epoch,
        catalog_hash=catalog_hash, params=params,
    )
    validate_cover_binding(header, catalogue, received_covers)
    message = verify_integrity(decoded_compressed_segments, header.integrity_digest)
    replay_guard.accept(expected_session_id, expected_sequence, expected_epoch)
    return header, slots, message


def pack_slot(*, erasure: bool = False, token: int = 0, delta: int = 0) -> int:
    if erasure:
        if token != 0 or delta != 0:
            raise ValueError("erasure slots must have zero token and residual")
        return 1 << 15
    if not 0 <= token < 2**11:
        raise ValueError("token must fit uint11")
    if not -4 <= delta <= 4:
        raise ValueError("residual is outside B=4")
    return (token << 4) | (delta + 4)


def unpack_slot(value: int) -> tuple[bool, int, int | None]:
    if not 0 <= value < 2**16:
        raise ValueError("slot must fit uint16")
    erasure = bool(value >> 15)
    token = (value >> 4) & 0x7FF
    residue = value & 0xF
    if erasure:
        if token or residue:
            raise ValueError("non-canonical erasure/fill slot")
        return True, 0, None
    if residue > 8:
        raise ValueError("invalid B=4 residual encoding")
    return False, token, residue - 4


def pack_record(*, inner_header: bytes, slots: list[int], key: bytes,
                session_id: bytes, sequence: int, mode: int, epoch: int,
                catalog_hash: bytes, params: bytes, nonce: bytes | None = None) -> bytes:
    if len(key) != 32 or len(session_id) != 16 or len(catalog_hash) != 32:
        raise ValueError("invalid V1 key, session id, or catalogue digest length")
    if len(params) != 11 or len(inner_header) != INNER_BYTES:
        raise ValueError("invalid V1 parameter or inner-header length")
    if not 0 <= sequence < 2**64 or not 0 <= epoch < 2**32:
        raise ValueError("sequence or epoch out of range")
    parsed = parse_inner_header(inner_header)
    if parsed.mode != mode:
        raise ValueError("record mode differs from inner header")
    capacity_value = 0 if mode == RECORD_R0 else R1_CAPACITY
    expected_params = encode_params(
        mode=mode, capacity=capacity_value, m=parsed.m, p=parsed.p, q=parsed.q,
        bound=parsed.bound, block_size=parsed.block_size,
        descriptor_id=parsed.descriptor_id, integrity_id=parsed.integrity_id,
    )
    if params != expected_params:
        raise ValueError("AAD parameters differ from the encrypted inner header")
    if mode == RECORD_R0:
        if len(slots) != parsed.codeword_len:
            raise ValueError("R0 slot count must equal codeword length")
        capacity = 0
        plaintext = inner_header + struct.pack(f"!{len(slots)}H", *slots)
        plaintext = zlib.compress(plaintext, level=9)
    elif mode == RECORD_R1:
        if len(slots) != parsed.codeword_len:
            raise ValueError("R1 supplied slots must equal codeword length")
        if len(slots) > R1_CAPACITY:
            raise ValueError("R1 codeword exceeds 140 slots")
        fixed_slots = list(slots) + [(1 << 15)] * (R1_CAPACITY - len(slots))
        capacity = R1_CAPACITY
        plaintext = inner_header + struct.pack(f"!{R1_CAPACITY}H", *fixed_slots)
    else:
        raise ValueError("unknown V1 record mode")
    nonce = os.urandom(12) if nonce is None else nonce
    if len(nonce) != 12:
        raise ValueError("AES-GCM nonce must be 12 bytes")
    header = OUTER.pack(OUTER_MAGIC, RECORD_VERSION, mode, session_id,
                        sequence, nonce, capacity)
    aad = AAD_DOMAIN + header + catalog_hash + struct.pack("!I", epoch) + params
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return header + ciphertext


def unpack_record(record: bytes, *, key: bytes, expected_session_id: bytes,
                  expected_sequence: int, expected_epoch: int,
                  catalog_hash: bytes, params: bytes) -> tuple[InnerHeader, list[int]]:
    if len(record) < OUTER.size + GCM_TAG_BYTES:
        raise ValueError("truncated V1 record")
    if len(record) > OUTER.size + GCM_TAG_BYTES + MAX_R0_COMPRESSED:
        raise ValueError("V1 record exceeds the maximum frozen record size")
    magic, version, mode, session_id, sequence, nonce, capacity = OUTER.unpack_from(record)
    if magic != OUTER_MAGIC or version != RECORD_VERSION or mode not in (RECORD_R0, RECORD_R1):
        raise ValueError("unsupported V1 record header")
    if session_id != expected_session_id or sequence != expected_sequence:
        raise ValueError("unexpected V1 session or sequence")
    if capacity != (0 if mode == RECORD_R0 else R1_CAPACITY):
        raise ValueError("invalid V1 public capacity")
    if len(key) != 32 or len(catalog_hash) != 32 or len(params) != 11:
        raise ValueError("invalid V1 decryption context")
    header = record[:OUTER.size]
    aad = AAD_DOMAIN + header + catalog_hash + struct.pack("!I", expected_epoch) + params
    plaintext = AESGCM(key).decrypt(nonce, record[OUTER.size:], aad)
    if mode == RECORD_R0:
        inflater = zlib.decompressobj()
        plaintext = inflater.decompress(plaintext, MAX_INNER_PLAINTEXT + 1)
        if len(plaintext) > MAX_INNER_PLAINTEXT or inflater.unconsumed_tail:
            raise ValueError("R0 plaintext exceeds the frozen maximum")
        plaintext += inflater.flush(MAX_INNER_PLAINTEXT + 1 - len(plaintext))
        if (len(plaintext) > MAX_INNER_PLAINTEXT or not inflater.eof
                or inflater.unused_data):
            raise ValueError("invalid or oversized R0 compressed plaintext")
        if len(plaintext) < INNER_BYTES or (len(plaintext) - INNER_BYTES) % 2:
            raise ValueError("invalid R0 plaintext length")
        inner = plaintext[:INNER_BYTES]
        slots = list(struct.unpack(f"!{(len(plaintext)-INNER_BYTES)//2}H",
                                   plaintext[INNER_BYTES:]))
    else:
        if len(plaintext) != INNER_BYTES + 2 * R1_CAPACITY:
            raise ValueError("invalid R1 plaintext length")
        inner = plaintext[:INNER_BYTES]
        slots = list(struct.unpack(f"!{R1_CAPACITY}H", plaintext[INNER_BYTES:]))
    parsed = parse_inner_header(inner)
    if parsed.mode != mode or len(slots) < parsed.codeword_len:
        raise ValueError("inner and outer V1 record disagree")
    expected_params = encode_params(
        mode=mode, capacity=capacity, m=parsed.m, p=parsed.p, q=parsed.q,
        bound=parsed.bound, block_size=parsed.block_size,
        descriptor_id=parsed.descriptor_id, integrity_id=parsed.integrity_id,
    )
    if params != expected_params:
        raise ValueError("AAD parameters differ from the decrypted inner header")
    if mode == RECORD_R0 and len(slots) != parsed.codeword_len:
        raise ValueError("R0 codeword length mismatch")
    if mode == RECORD_R1:
        if any(slot != 1 << 15 for slot in slots[parsed.codeword_len:]):
            raise ValueError("R1 fill slots are not canonical")
        slots = slots[:parsed.codeword_len]
    return parsed, slots


def create_offer(*, identity_private: Ed25519PrivateKey,
                 ephemeral_private: X25519PrivateKey, peer_identity: Ed25519PublicKey,
                 role: int, session_id: bytes, epoch: int) -> bytes:
    if role not in (0, 1) or len(session_id) != 16:
        raise ValueError("invalid handshake role or session id")
    _uint(epoch, 32, "epoch")
    sender_id = identity_private.public_key().public_bytes_raw()
    peer_id = peer_identity.public_bytes_raw()
    ephemeral = ephemeral_private.public_key().public_bytes_raw()
    body = struct.pack("!B", role) + session_id + ephemeral + struct.pack("!I", epoch)
    signature = identity_private.sign(OFFER_DOMAIN + body + sender_id + peer_id)
    return body + signature


def verify_offer(payload: bytes, *, sender_identity: Ed25519PublicKey,
                 recipient_identity: Ed25519PublicKey, expected_role: int,
                 expected_session_id: bytes, expected_epoch: int) -> bytes:
    if len(payload) != 117:
        raise ValueError("V1 offer must be exactly 117 bytes")
    role = payload[0]
    session_id = payload[1:17]
    ephemeral = payload[17:49]
    epoch = struct.unpack("!I", payload[49:53])[0]
    signature = payload[53:]
    if role != expected_role or session_id != expected_session_id or epoch != expected_epoch:
        raise ValueError("V1 offer context mismatch")
    signed = OFFER_DOMAIN + payload[:53] + sender_identity.public_bytes_raw() + recipient_identity.public_bytes_raw()
    try:
        sender_identity.verify(signature, signed)
    except InvalidSignature as exc:
        raise ValueError("invalid V1 offer signature") from exc
    X25519PublicKey.from_public_bytes(ephemeral)
    return ephemeral


def transcript_hash(offer_role0: bytes, offer_role1: bytes, *,
                    catalog_hash: bytes, epoch: int, params: bytes) -> bytes:
    for payload in (offer_role0, offer_role1):
        if len(payload) != 117:
            raise ValueError("invalid V1 offer in transcript")
    if offer_role0[0] != 0 or offer_role1[0] != 1:
        raise ValueError("V1 transcript offers are not in canonical role order")
    if len(catalog_hash) != 32 or len(params) != 11:
        raise ValueError("invalid V1 transcript context")
    return hashlib.sha256(
        b"FHAM-V1-TRANSCRIPT" + offer_role0 + offer_role1 + catalog_hash
        + struct.pack("!I", epoch) + params
    ).digest()


def derive_v1_keys(local_ephemeral: X25519PrivateKey, peer_ephemeral: bytes,
                   session_id: bytes, transcript: bytes) -> V1Keys:
    if len(session_id) != 16 or len(transcript) != 32:
        raise ValueError("invalid V1 key-schedule context")
    peer = X25519PublicKey.from_public_bytes(peer_ephemeral)
    shared = local_ephemeral.exchange(peer)

    def expand(label: bytes) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(), length=32, salt=session_id,
            info=HKDF_DOMAIN + b"/" + label + b"/" + transcript,
        ).derive(shared)

    return V1Keys(
        expand(b"aead-role0"), expand(b"aead-role1"),
        expand(b"confirm-role0"), expand(b"confirm-role1"),
    )


def key_confirmation(keys: V1Keys, role: int, transcript: bytes) -> bytes:
    if role not in (0, 1) or len(transcript) != 32:
        raise ValueError("invalid V1 key confirmation context")
    key = keys.confirm_role0 if role == 0 else keys.confirm_role1
    return hmac.new(key, transcript + bytes([role]), hashlib.sha256).digest()


def verify_key_confirmation(keys: V1Keys, sender_role: int, transcript: bytes,
                            confirmation: bytes) -> None:
    expected = key_confirmation(keys, sender_role, transcript)
    if not hmac.compare_digest(expected, confirmation):
        raise ValueError("V1 key confirmation failed")


class V1ReplayGuard:
    """Atomic sequence/replay table checked against an external monotone epoch.

    ``trusted_epoch`` must come from state that cannot be rolled back with the
    SQLite database. The class deliberately does not pretend SQLite provides
    that property on its own.
    """

    def __init__(self, database_path, trusted_epoch_provider):
        self.database_path = str(database_path)
        self.trusted_epoch_provider = trusted_epoch_provider
        self._lock = threading.Lock()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS fham_v1_sessions "
                "(session_id BLOB PRIMARY KEY, epoch INTEGER NOT NULL, "
                "next_sequence INTEGER NOT NULL)"
            )
            connection.commit()

    def register_session(self, session_id: bytes, epoch: int) -> None:
        if len(session_id) != 16 or epoch != self.trusted_epoch_provider():
            raise ValueError("session epoch is not the trusted current epoch")
        try:
            with closing(sqlite3.connect(self.database_path, timeout=30)) as connection:
                connection.execute(
                    "INSERT INTO fham_v1_sessions(session_id,epoch,next_sequence) "
                    "VALUES(?,?,0)", (session_id, epoch)
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("V1 session is already registered") from exc

    def accept(self, session_id: bytes, sequence: int, epoch: int) -> None:
        trusted_epoch = self.trusted_epoch_provider()
        if epoch != trusted_epoch:
            raise ValueError("record belongs to a stale or future receiver epoch")
        with closing(sqlite3.connect(self.database_path, timeout=30)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT epoch,next_sequence FROM fham_v1_sessions "
                    "WHERE session_id=?", (session_id,)
                ).fetchone()
                if row is None or row[0] != trusted_epoch:
                    raise ValueError("unknown or stale V1 session")
                if sequence != row[1]:
                    raise ValueError("duplicate, reordered, or skipped V1 sequence")
                connection.execute(
                    "UPDATE fham_v1_sessions SET next_sequence=? WHERE session_id=?",
                    (sequence + 1, session_id),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise


__all__ = [
    "FRAME", "FRAME_CONFIRM", "FRAME_OFFER", "FRAME_RECORD", "INNER_BYTES",
    "InnerHeader", "RECORD_R0", "RECORD_R1", "R1_CAPACITY", "SegmentInfo",
    "V1Keys", "V1RecordSender", "accept_v1_record", "build_inner_header", "canonical_cover_digest", "catalogue_digest",
    "create_offer", "derive_v1_keys", "encode_params", "frame", "key_confirmation",
    "pack_record", "pack_slot", "parse_inner_header", "transcript_hash", "unframe",
    "unpack_record", "unpack_slot", "validate_cover_binding", "verify_integrity",
    "verify_key_confirmation", "verify_offer", "V1ReplayGuard",
]
