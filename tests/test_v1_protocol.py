import hashlib
import shutil
import zlib

import numpy as np
import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from reedsolo import RSCodec

from fham.v1 import (
    FRAME_RECORD,
    INNER_BYTES,
    AAD_DOMAIN,
    OUTER,
    RECORD_R0,
    RECORD_R1,
    R1_CAPACITY,
    V1ReplayGuard,
    V1RecordSender,
    accept_v1_record,
    build_inner_header,
    catalogue_digest,
    create_offer,
    derive_v1_keys,
    encode_params,
    frame,
    key_confirmation,
    pack_record,
    pack_slot,
    parse_inner_header,
    transcript_hash,
    unframe,
    unpack_record,
    validate_cover_binding,
    verify_key_confirmation,
    verify_integrity,
    verify_offer,
)


def record_fixture(mode):
    source = bytes(range(100))
    source_parts = (source[:50], source[50:])
    compressed = tuple(zlib.compress(part, level=9) for part in source_parts)
    codewords = []
    for part in compressed:
        parity = (len(part) + 9) // 10
        codec = RSCodec(parity, nsize=255, fcr=0, generator=2, prim=0x11D, c_exp=8)
        codewords.append(bytes(codec.encode(part)))
    codewords = tuple(codewords)
    codeword_len = sum(map(len, codewords))
    slots = [pack_slot(token=i, delta=(i % 9) - 4) for i in range(codeword_len)]
    # Two known erasures remain within the RS parity allowance in each block.
    slots[0] = pack_slot(erasure=True)
    slots[len(codewords[0])] = pack_slot(erasure=True)
    placed = codeword_len - 2
    digest = hashlib.sha256(b"".join(compressed)).digest()[:16]
    inner = build_inner_header(
        mode=mode, height=256, width=256, m=2, p=10, q=5, bound=4,
        block_size=12, descriptor_id=1, integrity_id=1, source_len=100,
        compressed_segments=compressed, codeword_segments=codewords,
        gallery_pairs=((0, 1, 0), (2, 3, 1)), placed_count=placed,
        integrity_digest=digest,
    )
    capacity = 0 if mode == RECORD_R0 else R1_CAPACITY
    params = encode_params(
        mode=mode, capacity=capacity, m=2, p=10, q=5, bound=4,
        block_size=12, descriptor_id=1, integrity_id=1,
    )
    catalogue = [np.arange(64, dtype=np.uint8).reshape(8, 8) + i for i in range(4)]
    cat_hash = catalogue_digest(catalogue)
    key = bytes(range(32))
    session_id = bytes(range(16))
    record = pack_record(
        inner_header=inner, slots=slots, key=key, session_id=session_id,
        sequence=0, mode=mode, epoch=7, catalog_hash=cat_hash, params=params,
        nonce=bytes(range(12)),
    )
    return record, slots, key, session_id, cat_hash, params, inner


@pytest.mark.parametrize("mode", [RECORD_R0, RECORD_R1])
def test_v1_record_round_trip_and_frozen_lengths(mode):
    record, slots, key, sid, cat_hash, params, inner = record_fixture(mode)
    decoded_header, decoded_slots = unpack_record(
        record, key=key, expected_session_id=sid, expected_sequence=0,
        expected_epoch=7, catalog_hash=cat_hash, params=params,
    )
    assert decoded_header == parse_inner_header(inner)
    assert decoded_slots == slots
    if mode == RECORD_R1:
        assert len(record) == 396
        frame_bytes = frame(FRAME_RECORD, record)
        assert len(frame_bytes) == 406
        assert unframe(frame_bytes) == (FRAME_RECORD, record)
    else:
        assert len(record) < 396


def test_v1_rejects_wrong_catalogue_epoch_parameters_and_session():
    record, _, key, sid, cat_hash, params, _ = record_fixture(RECORD_R1)
    contexts = [
        dict(expected_session_id=sid, expected_epoch=7, catalog_hash=bytes(32), params=params),
        dict(expected_session_id=sid, expected_epoch=8, catalog_hash=cat_hash, params=params),
        dict(expected_session_id=sid, expected_epoch=7, catalog_hash=cat_hash,
             params=encode_params(mode=RECORD_R1, capacity=R1_CAPACITY, m=2, p=10,
                                  q=5, bound=4, block_size=12, descriptor_id=2)),
        dict(expected_session_id=bytes([1]) * 16, expected_epoch=7,
             catalog_hash=cat_hash, params=params),
    ]
    for context in contexts:
        with pytest.raises((ValueError, InvalidTag)):
            unpack_record(record, key=key, expected_sequence=0, **context)


def test_v1_exhaustive_single_bit_mutation_of_record_is_rejected():
    record, _, key, sid, cat_hash, params, _ = record_fixture(RECORD_R1)
    for bit in range(len(record) * 8):
        mutated = bytearray(record)
        mutated[bit // 8] ^= 1 << (bit % 8)
        with pytest.raises((ValueError, InvalidTag, zlib.error)):
            unpack_record(
                bytes(mutated), key=key, expected_session_id=sid,
                expected_sequence=0, expected_epoch=7,
                catalog_hash=cat_hash, params=params,
            )


def test_v1_signed_ephemeral_exchange_confirms_directional_keys():
    sid = bytes(range(16))
    epoch = 3
    identity0, identity1 = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    eph0, eph1 = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    offer0 = create_offer(identity_private=identity0, ephemeral_private=eph0,
                          peer_identity=identity1.public_key(), role=0,
                          session_id=sid, epoch=epoch)
    offer1 = create_offer(identity_private=identity1, ephemeral_private=eph1,
                          peer_identity=identity0.public_key(), role=1,
                          session_id=sid, epoch=epoch)
    pub1 = verify_offer(offer1, sender_identity=identity1.public_key(),
                        recipient_identity=identity0.public_key(), expected_role=1,
                        expected_session_id=sid, expected_epoch=epoch)
    pub0 = verify_offer(offer0, sender_identity=identity0.public_key(),
                        recipient_identity=identity1.public_key(), expected_role=0,
                        expected_session_id=sid, expected_epoch=epoch)
    catalog = catalogue_digest([np.arange(64, dtype=np.uint8).reshape(8, 8)])
    params = encode_params(mode=RECORD_R1, capacity=R1_CAPACITY, m=2, p=10,
                           q=5, bound=4, block_size=12, descriptor_id=1)
    transcript = transcript_hash(offer0, offer1, catalog_hash=catalog,
                                 epoch=epoch, params=params)
    keys0 = derive_v1_keys(eph0, pub1, sid, transcript)
    keys1 = derive_v1_keys(eph1, pub0, sid, transcript)
    assert keys0 == keys1
    assert len({keys0.aead_role0, keys0.aead_role1,
                keys0.confirm_role0, keys0.confirm_role1}) == 4
    verify_key_confirmation(keys0, 0, transcript, key_confirmation(keys1, 0, transcript))
    tampered = bytearray(offer1)
    tampered[20] ^= 1
    with pytest.raises(ValueError):
        verify_offer(bytes(tampered), sender_identity=identity1.public_key(),
                     recipient_identity=identity0.public_key(), expected_role=1,
                     expected_session_id=sid, expected_epoch=epoch)


def test_v1_replay_guard_survives_restart_and_rejects_old_epoch(tmp_path):
    current_epoch = [4]
    path = tmp_path / "receiver.sqlite"
    guard = V1ReplayGuard(path, lambda: current_epoch[0])
    sid = bytes(range(16))
    guard.register_session(sid, 4)
    guard.accept(sid, 0, 4)
    with pytest.raises(ValueError):
        guard.accept(sid, 0, 4)
    guard = V1ReplayGuard(path, lambda: current_epoch[0])
    guard.accept(sid, 1, 4)
    backup = tmp_path / "old-snapshot.sqlite"
    shutil.copy2(path, backup)
    current_epoch[0] = 5
    rollback_guard = V1ReplayGuard(backup, lambda: current_epoch[0])
    with pytest.raises(ValueError):
        rollback_guard.accept(sid, 1, 4)


def test_v1_cover_binding_and_message_digest_are_checked():
    record, _, key, sid, cat_hash, params, _ = record_fixture(RECORD_R1)
    header, _ = unpack_record(
        record, key=key, expected_session_id=sid, expected_sequence=0,
        expected_epoch=7, catalog_hash=cat_hash, params=params,
    )
    catalogue = [np.arange(64, dtype=np.uint8).reshape(8, 8) + i for i in range(4)]
    validate_cover_binding(header, catalogue, [catalogue[0], catalogue[3]])
    altered = catalogue[0].copy()
    altered[0, 0] ^= 1
    with pytest.raises(ValueError):
        validate_cover_binding(header, catalogue, [altered, catalogue[3]])
    compressed = (zlib.compress(bytes(range(50)), 9),
                  zlib.compress(bytes(range(50, 100)), 9))
    good = hashlib.sha256(b"".join(compressed)).digest()[:16]
    assert verify_integrity(compressed, good) == b"".join(compressed)
    with pytest.raises(ValueError):
        verify_integrity(compressed, bytes(16))


def test_stateful_sender_rejects_nonce_reuse_and_advances_sequence():
    record, slots, key, sid, cat_hash, params, inner = record_fixture(RECORD_R1)
    sender = V1RecordSender(key=key, session_id=sid, mode=RECORD_R1,
                            epoch=7, catalog_hash=cat_hash, params=params)
    nonce = bytes(range(12))
    sealed = sender.seal(inner_header=inner, slots=slots, nonce=nonce)
    assert OUTER.unpack_from(sealed)[4] == 0
    with pytest.raises(ValueError, match="reused"):
        sender.seal(inner_header=inner, slots=slots, nonce=nonce)
    next_record = sender.seal(inner_header=inner, slots=slots)
    assert OUTER.unpack_from(next_record)[4] == 1


def test_receiver_commits_replay_state_only_after_cover_and_i1_checks(tmp_path):
    record, _, key, sid, cat_hash, params, _ = record_fixture(RECORD_R1)
    catalogue = [np.arange(64, dtype=np.uint8).reshape(8, 8) + i for i in range(4)]
    compressed = (zlib.compress(bytes(range(50)), 9),
                  zlib.compress(bytes(range(50, 100)), 9))
    guard = V1ReplayGuard(tmp_path / "receiver.sqlite", lambda: 7)
    guard.register_session(sid, 7)
    args = dict(record=record, key=key, expected_session_id=sid,
                expected_sequence=0, expected_epoch=7, catalog_hash=cat_hash,
                params=params, catalogue=catalogue,
                decoded_compressed_segments=compressed, replay_guard=guard)
    with pytest.raises(ValueError, match="does not match"):
        accept_v1_record(**args, received_covers=[catalogue[1], catalogue[2]])
    # The invalid cover did not consume sequence zero; the correct selected covers do.
    result = accept_v1_record(**args, received_covers=[catalogue[0], catalogue[3]])
    assert result[2] == b"".join(compressed)
    with pytest.raises(ValueError, match="duplicate"):
        accept_v1_record(**args, received_covers=[catalogue[0], catalogue[3]])


def test_v1_r0_decompression_is_bounded_even_for_authenticated_input():
    key = bytes(range(32))
    sid = bytes(range(16))
    nonce = bytes(range(12))
    epoch = 7
    catalog = [np.arange(64, dtype=np.uint8).reshape(8, 8)]
    cat_hash = catalogue_digest(catalog)
    params = encode_params(mode=RECORD_R0, capacity=0, m=2, p=10, q=5,
                           bound=4, block_size=12, descriptor_id=1)
    header = OUTER.pack(b"FHQ2", 2, RECORD_R0, sid, 0, nonce, 0)
    aad = AAD_DOMAIN + header + cat_hash + epoch.to_bytes(4, "big") + params
    compressed_bomb = zlib.compress(b"A" * 1_000_000, level=9)
    ciphertext = AESGCM(key).encrypt(nonce, compressed_bomb, aad)
    with pytest.raises(ValueError):
        unpack_record(header + ciphertext, key=key, expected_session_id=sid,
                      expected_sequence=0, expected_epoch=epoch,
                      catalog_hash=cat_hash, params=params)
