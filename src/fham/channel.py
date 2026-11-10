import os
import struct
import zlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .methods import Assignment, Location


class AuxiliaryChannel:
    SERIAL_HEADER = struct.Struct(">4sBHHHI")
    RECORD = struct.Struct(">Hh")
    ENVELOPE_HEADER = struct.Struct(">4sBII")
    SHAPED_ENVELOPE_HEADER = struct.Struct(">4sBI")
    SERIAL_MAGIC = b"FHMS"
    ENVELOPE_MAGIC = b"FHME"
    SHAPED_ENVELOPE_MAGIC = b"FHMT"
    VERSION = 1
    AAD = b"FHAM-AUXILIARY"
    SHAPED_AAD = b"FHAM-AUXILIARY-SHAPED"

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
