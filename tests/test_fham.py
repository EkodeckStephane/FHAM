import os

import numpy as np
import pytest
from cryptography.exceptions import InvalidTag

from fham.channel import AuxiliaryChannel
from fham.abdulsattar import AbdulsattarMethod
from fham.methods import (
    BoundedAssignmentMethod,
    GreedyAssignmentMethod,
    OptimalAssignmentMethod,
)
from fham.wysawis import WysawisMethod


def test_optimal_round_trip_and_unique_locations():
    image = np.arange(144, dtype=np.uint8).reshape(12, 12)
    method = OptimalAssignmentMethod(block_size=6)
    assignment = method.embed("GLOBAL", image)
    assert len(set(assignment.locations)) == 6
    assert method.extract(assignment, image) == "GLOBAL"


def test_optimal_cost_is_not_worse_than_greedy():
    image = np.arange(144, dtype=np.uint8).reshape(12, 12)
    message = "Assignment"
    greedy = GreedyAssignmentMethod(block_size=6)
    optimal = OptimalAssignmentMethod(block_size=6)
    greedy_assignment = greedy.embed(message, image)
    optimal_assignment = optimal.embed(message, image)
    greedy_cost = sum(map(abs, greedy_assignment.displacements))
    optimal_cost = sum(map(abs, optimal_assignment.displacements))
    assert optimal_cost <= greedy_cost


def test_bounded_assignment_enforces_radius():
    image = np.arange(144, dtype=np.uint8).reshape(12, 12)
    method = BoundedAssignmentMethod(max_displacement=255, block_size=6)
    assignment = method.embed("BOUND", image)
    assert assignment is not None
    assert max(map(abs, assignment.displacements)) <= 255


def test_zero_bound_matches_only_exact_hashes():
    image = np.arange(144, dtype=np.uint8).reshape(12, 12)
    method = BoundedAssignmentMethod(max_displacement=0, block_size=6)
    method.build_lookup_table(image)
    assignment = method.embed(chr(next(iter(method.lookup_table))), image)
    assert assignment is not None
    assert set(assignment.displacements) == {0}


def test_encrypted_channel_round_trip():
    image = np.arange(144, dtype=np.uint8).reshape(12, 12)
    method = OptimalAssignmentMethod(block_size=6)
    assignment = method.embed("FHAM", image)
    key = os.urandom(32)
    envelope = AuxiliaryChannel.protect(assignment, key)
    recovered = AuxiliaryChannel.recover(envelope, key)
    assert recovered == assignment
    assert len(AuxiliaryChannel.serialize(assignment)) == 15 + 4 * len("FHAM")
    assert method.extract(recovered, image) == "FHAM"


def test_encrypted_channel_rejects_tampering():
    image = np.arange(144, dtype=np.uint8).reshape(12, 12)
    assignment = OptimalAssignmentMethod(block_size=6).embed("FHAM", image)
    key = os.urandom(32)
    envelope = bytearray(AuxiliaryChannel.protect(assignment, key))
    envelope[-1] ^= 1
    with pytest.raises(InvalidTag):
        AuxiliaryChannel.recover(bytes(envelope), key)


def _wysawis_adequate_image():
    image = np.zeros((16, 16), dtype=np.uint8)
    for zero_count in range(16):
        bits = [0] * zero_count + [1] * (15 - zero_count)
        values = [128]
        for bit in bits:
            values.append(values[-1] - 1 if bit else values[-1] + 1)
        row, column = divmod(zero_count, 4)
        image[row * 4:(row + 1) * 4, column * 4:(column + 1) * 4] = (
            np.asarray(values, dtype=np.uint8).reshape(4, 4)
        )
    return image


def test_wysawis_round_trip_and_categories():
    image = _wysawis_adequate_image()
    method = WysawisMethod()
    assert method.build_index(image)
    assignment = method.embed("WYSAWIS", image)
    assert assignment is not None
    assert method.extract(assignment, image) == "WYSAWIS"
    assert WysawisMethod.cloud_records(assignment) == 5


def test_abdulsattar_capacity_and_round_trip():
    rng = np.random.default_rng(17)
    image = rng.integers(0, 256, size=(512, 512), dtype=np.uint8)
    method = AbdulsattarMethod(overlapping=True)
    assert method.build_lookup_table(image) == 6889
    available = "".join(chr(value) for value in sorted(method.lookup_table)[:20])
    assignment = method.embed(available, image)
    assert assignment is not None
    assert len(set(assignment.locations)) == len(available)
    assert method.extract(assignment, image) == available


def test_abdulsattar_published_nominal_capacities():
    image = np.zeros((512, 512), dtype=np.uint8)
    assert AbdulsattarMethod(overlapping=False).build_lookup_table(image) * 8 == 6272
    assert AbdulsattarMethod(overlapping=True).build_lookup_table(image) * 8 == 55112
