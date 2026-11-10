import hashlib
import os
import sqlite3
import struct
import threading
import zlib
from contextlib import closing

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .methods import Assignment, Location


class AuxiliaryChannel:
    SERIAL_HEADER = struct.Struct(">4sBHHHI")
    RECORD = struct.Struct(">Hh")
    ENVELOPE_HEADER = struct.Struct(">4sBII")
    SHAPED_ENVELOPE_HEADER = struct.Struct(">4sBI")
    SESSION_ENVELOPE_HEADER = struct.Struct(">4sB16sQ12sI")
    SERIAL_MAGIC = b"FHMS"
    ENVELOPE_MAGIC = b"FHME"
    SHAPED_ENVELOPE_MAGIC = b"FHMT"
    VERSION = 1
    AAD = b"FHAM-AUXILIARY"
    SHAPED_AAD = b"FHAM-AUXILIARY-SHAPED"
    SESSION_MAGIC = b"FHMS"
    SESSION_AAD = b"FHAM-AUXILIARY-SESSION-v1"

    @classmethod
    def serialize(cls, assignment):
        count = len(assignment.locations)
        if count != len(assignment.displacements):
            raise ValueError("location and displacement counts differ")
        payload = bytearray(
            cls.SERIAL_HEADER.pack(
                cls.SERIAL_MAGIC,
                cls.VERSION,
                assignment.image_shape[0],
                assignment.image_shape[1],
                assignment.block_size,
                count,
            )
        )
        for location, displacement in zip(
            assignment.locations, assignment.displacements
        ):
            blocks_per_row = assignment.image_shape[1] // assignment.block_size
            block_index = (
                location.y // assignment.block_size
            ) * blocks_per_row + location.x // assignment.block_size
            token = block_index * 4 + location.arrangement
            payload.extend(
                cls.RECORD.pack(
                    token,
                    displacement,
                )
            )
        return bytes(payload)

    @classmethod
    def deserialize(cls, payload):
        header_size = cls.SERIAL_HEADER.size
        magic, version, height, width, block_size, count = cls.SERIAL_HEADER.unpack(
            payload[:header_size]
        )
        if magic != cls.SERIAL_MAGIC or version != cls.VERSION:
            raise ValueError("unsupported auxiliary payload")
        expected = header_size + count * cls.RECORD.size
        if len(payload) != expected:
            raise ValueError("invalid auxiliary payload length")
        locations = []
        displacements = []
        offset = header_size
        blocks_per_row = width // block_size
        for _ in range(count):
            token, displacement = cls.RECORD.unpack_from(payload, offset)
            block_index, arrangement = divmod(token, 4)
            y, block_column = divmod(block_index, blocks_per_row)
            x = block_column * block_size
            y *= block_size
            locations.append(Location(x, y, arrangement))
            displacements.append(displacement)
            offset += cls.RECORD.size
        return Assignment(
            (height, width), block_size, locations, displacements
        )

    @classmethod
    def serialized_length(cls, payload):
        header_size = cls.SERIAL_HEADER.size
        if len(payload) < header_size:
            raise ValueError("auxiliary payload too short")
        magic, version, _height, _width, _block_size, count = cls.SERIAL_HEADER.unpack(
            payload[:header_size]
        )
        if magic != cls.SERIAL_MAGIC or version != cls.VERSION:
            raise ValueError("unsupported auxiliary payload")
        return header_size + count * cls.RECORD.size

    @classmethod
    def protect(cls, assignment, key):
        raw = cls.serialize(assignment)
        compressed = zlib.compress(raw, level=9)
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, compressed, cls.AAD)
        envelope = cls.ENVELOPE_HEADER.pack(
            cls.ENVELOPE_MAGIC, cls.VERSION, len(raw), len(compressed)
        )
        return envelope + nonce + ciphertext

    @classmethod
    def recover(cls, envelope, key):
        header_size = cls.ENVELOPE_HEADER.size
        magic, version, raw_size, compressed_size = cls.ENVELOPE_HEADER.unpack(
            envelope[:header_size]
        )
        if magic != cls.ENVELOPE_MAGIC or version != cls.VERSION:
            raise ValueError("unsupported encrypted envelope")
        nonce = envelope[header_size:header_size + 12]
        ciphertext = envelope[header_size + 12:]
        compressed = AESGCM(key).decrypt(nonce, ciphertext, cls.AAD)
        if len(compressed) != compressed_size:
            raise ValueError("compressed length mismatch")
        raw = zlib.decompress(compressed)
        if len(raw) != raw_size:
            raise ValueError("raw length mismatch")
        return cls.deserialize(raw)

    @classmethod
    def protect_shaped(cls, assignment, key, record_capacity):
        """Protect an assignment with fixed-size, traffic-shaped records.

        The compact envelope above optimizes byte cost by compressing the
        serialized assignment, but its ciphertext size tracks both message
        length and residual structure. This variant pads the serialized record
        array to a public record capacity and encrypts the padded plaintext
        without compression. The true record count remains inside the encrypted
        serialized header.
        """
        raw = cls.serialize(assignment)
        count = len(assignment.locations)
        if count > record_capacity:
            raise ValueError("assignment exceeds shaped record capacity")
        padded_size = cls.SERIAL_HEADER.size + record_capacity * cls.RECORD.size
        padding_size = padded_size - len(raw)
        padded = raw + os.urandom(padding_size)
        nonce = os.urandom(12)
        public_header = cls.SHAPED_ENVELOPE_HEADER.pack(
            cls.SHAPED_ENVELOPE_MAGIC, cls.VERSION, record_capacity
        )
        ciphertext = AESGCM(key).encrypt(nonce, padded, cls.SHAPED_AAD + public_header)
        return public_header + nonce + ciphertext

    @classmethod
    def recover_shaped(cls, envelope, key):
        header_size = cls.SHAPED_ENVELOPE_HEADER.size
        magic, version, record_capacity = cls.SHAPED_ENVELOPE_HEADER.unpack(
            envelope[:header_size]
        )
        if magic != cls.SHAPED_ENVELOPE_MAGIC or version != cls.VERSION:
            raise ValueError("unsupported shaped envelope")
        public_header = envelope[:header_size]
        nonce = envelope[header_size:header_size + 12]
        ciphertext = envelope[header_size + 12:]
        padded = AESGCM(key).decrypt(nonce, ciphertext, cls.SHAPED_AAD + public_header)
        expected = cls.SERIAL_HEADER.size + record_capacity * cls.RECORD.size
        if len(padded) != expected:
            raise ValueError("shaped payload length mismatch")
        raw_length = cls.serialized_length(padded)
        if raw_length > expected:
            raise ValueError("serialized payload exceeds shaped capacity")
        return cls.deserialize(padded[:raw_length])

    @staticmethod
    def derive_session_key(local_private_key, peer_public_key, session_id):
        """Derive a directional-session key from an X25519 exchange.

        The caller must authenticate the peer public key (for example, by
        checking a pinned identity key or a signature over the handshake).
        X25519 alone does not prevent a man-in-the-middle attack.
        """
        if len(session_id) != 16:
            raise ValueError("session_id must contain exactly 16 bytes")
        if not isinstance(local_private_key, X25519PrivateKey):
            raise TypeError("local_private_key must be an X25519PrivateKey")
        peer = (
            peer_public_key
            if isinstance(peer_public_key, X25519PublicKey)
            else X25519PublicKey.from_public_bytes(peer_public_key)
        )
        shared_secret = local_private_key.exchange(peer)
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=session_id,
            info=b"FHAM-AUXILIARY-SESSION-KEY-v1",
        ).derive(shared_secret)

    @staticmethod
    def sign_ephemeral(identity_private_key, ephemeral_private_key, peer_identity_public_key,
                       session_id):
        """Sign an ephemeral X25519 public key for an authenticated handshake.

        Both parties must pin or otherwise authenticate the peer's Ed25519
        identity key. The signature binds the offer to the intended peer and
        session identifier.
        """
        if len(session_id) != 16:
            raise ValueError("session_id must contain exactly 16 bytes")
        if not isinstance(identity_private_key, Ed25519PrivateKey):
            raise TypeError("identity_private_key must be an Ed25519PrivateKey")
        if not isinstance(ephemeral_private_key, X25519PrivateKey):
            raise TypeError("ephemeral_private_key must be an X25519PrivateKey")
        peer_identity = (
            peer_identity_public_key
            if isinstance(peer_identity_public_key, Ed25519PublicKey)
            else Ed25519PublicKey.from_public_bytes(peer_identity_public_key)
        )
        own_identity = identity_private_key.public_key().public_bytes_raw()
        peer_identity_bytes = peer_identity.public_bytes_raw()
        ephemeral_bytes = ephemeral_private_key.public_key().public_bytes_raw()
        signed = (
            b"FHAM-X25519-OFFER-v1"
            + session_id
            + own_identity
            + peer_identity_bytes
            + ephemeral_bytes
        )
        return ephemeral_bytes, identity_private_key.sign(signed)

    @staticmethod
    def verify_ephemeral(sender_identity_public_key, recipient_identity_public_key,
                         ephemeral_public_key, signature, session_id):
        """Verify a signed key offer using an authenticated identity key."""
        sender = (
            sender_identity_public_key
            if isinstance(sender_identity_public_key, Ed25519PublicKey)
            else Ed25519PublicKey.from_public_bytes(sender_identity_public_key)
        )
        recipient = (
            recipient_identity_public_key
            if isinstance(recipient_identity_public_key, Ed25519PublicKey)
            else Ed25519PublicKey.from_public_bytes(recipient_identity_public_key)
        )
        sender_bytes = sender.public_bytes_raw()
        recipient_bytes = recipient.public_bytes_raw()
        signed = (
            b"FHAM-X25519-OFFER-v1"
            + session_id
            + sender_bytes
            + recipient_bytes
            + ephemeral_public_key
        )
        try:
            sender.verify(signature, signed)
        except InvalidSignature as exc:
            raise ValueError("unauthenticated or altered key offer") from exc

    @staticmethod
    def reference_digest(reference_image):
        """Hash the canonical 2-D uint8 reference used to build the codebook."""
        import numpy as np

        image = np.asarray(reference_image)
        if image.ndim != 2 or image.dtype != np.uint8:
            raise ValueError("reference image must be a two-dimensional uint8 array")
        image = np.ascontiguousarray(image)
        digest_input = (
            b"FHAM-CANONICAL-REFERENCE-v1"
            + struct.pack(">II", image.shape[0], image.shape[1])
            + image.tobytes(order="C")
        )
        return hashlib.sha256(digest_input).digest()

    @classmethod
    def protect_session(cls, assignment, session_key, reference_image, session_id,
                        sequence, record_capacity):
        """Protect a fixed-capacity record bound to a cover and session.

        The public record capacity fixes ciphertext size for a session. The
        caller should choose it from a public communication profile.
        """
        import numpy as np

        reference_image = np.asarray(reference_image)
        if len(session_key) != 32:
            raise ValueError("session_key must contain exactly 32 bytes")
        if len(session_id) != 16:
            raise ValueError("session_id must contain exactly 16 bytes")
        if not 0 <= sequence < 2**64:
            raise ValueError("sequence must be an unsigned 64-bit integer")
        if record_capacity < len(assignment.locations):
            raise ValueError("assignment exceeds session record capacity")
        reference_digest = cls.reference_digest(reference_image)
        if tuple(reference_image.shape) != tuple(assignment.image_shape):
            raise ValueError("reference image shape differs from assignment")
        raw = cls.serialize(assignment)
        padded_size = cls.SERIAL_HEADER.size + record_capacity * cls.RECORD.size
        padded = raw + os.urandom(padded_size - len(raw))
        nonce = os.urandom(12)
        header = cls.SESSION_ENVELOPE_HEADER.pack(
            cls.SESSION_MAGIC,
            cls.VERSION,
            session_id,
            sequence,
            nonce,
            record_capacity,
        )
        ciphertext = AESGCM(session_key).encrypt(
            nonce, padded, cls.SESSION_AAD + header + reference_digest
        )
        return header + ciphertext

    @classmethod
    def recover_session(cls, envelope, session_key, reference_image, replay_guard):
        """Authenticate cover/session/sequence, then atomically reject replays.

        ``replay_guard`` must be durable and shared across receiver processes
        in deployments that require replay protection across restarts.
        """
        import numpy as np

        reference_image = np.asarray(reference_image)
        header_size = cls.SESSION_ENVELOPE_HEADER.size
        if len(envelope) < header_size + 16:
            raise ValueError("session envelope is truncated")
        (magic, version, session_id, sequence, nonce,
         record_capacity) = cls.SESSION_ENVELOPE_HEADER.unpack(
            envelope[:header_size]
        )
        if magic != cls.SESSION_MAGIC or version != cls.VERSION:
            raise ValueError("unsupported session envelope")
        reference_digest = cls.reference_digest(reference_image)
        header = envelope[:header_size]
        padded = AESGCM(session_key).decrypt(
            nonce, envelope[header_size:], cls.SESSION_AAD + header + reference_digest
        )
        expected_size = cls.SERIAL_HEADER.size + record_capacity * cls.RECORD.size
        if len(padded) != expected_size:
            raise ValueError("session record length mismatch")
        raw_size = cls.serialized_length(padded)
        raw = padded[:raw_size]
        assignment = cls.deserialize(raw)
        if tuple(reference_image.shape) != tuple(assignment.image_shape):
            raise ValueError("reference image shape differs from assignment")
        replay_guard.accept(session_id, sequence)
        return assignment


class ReplayGuard:
    """In-memory strict sequence guard for single-process experiments."""

    def __init__(self):
        self._next_sequence = {}
        self._lock = threading.Lock()

    def register_session(self, session_id):
        if len(session_id) != 16:
            raise ValueError("session_id must contain exactly 16 bytes")
        with self._lock:
            if session_id in self._next_sequence:
                raise ValueError("session is already registered")
            self._next_sequence[session_id] = 0

    def accept(self, session_id, sequence):
        with self._lock:
            if session_id not in self._next_sequence:
                raise ValueError("unregistered session")
            expected = self._next_sequence[session_id]
            if sequence != expected:
                raise ValueError(
                    f"unexpected session sequence {sequence}; expected {expected}"
                )
            self._next_sequence[session_id] = expected + 1


class SQLiteReplayGuard:
    """Durable, atomic replay state for a receiver deployment."""

    def __init__(self, database_path):
        self.database_path = str(database_path)
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS fham_sessions "
                "(session_id BLOB PRIMARY KEY, next_sequence INTEGER NOT NULL)"
            )
            connection.commit()

    def register_session(self, session_id):
        if len(session_id) != 16:
            raise ValueError("session_id must contain exactly 16 bytes")
        try:
            with closing(sqlite3.connect(self.database_path, timeout=30)) as connection:
                connection.execute(
                    "INSERT INTO fham_sessions (session_id, next_sequence) "
                    "VALUES (?, 0)",
                    (session_id,),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("session is already registered") from exc

    def accept(self, session_id, sequence):
        with closing(sqlite3.connect(self.database_path, timeout=30)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT next_sequence FROM fham_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("unregistered session")
                expected = row[0]
                if sequence != expected:
                    raise ValueError(
                        f"unexpected session sequence {sequence}; expected {expected}"
                    )
                connection.execute(
                    "UPDATE fham_sessions SET next_sequence = ? WHERE session_id = ?",
                    (expected + 1, session_id),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
