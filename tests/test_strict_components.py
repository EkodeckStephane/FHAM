from collections import Counter

import numpy as np

from fham.assignment import (
    aggregated_min_cost_assignment,
    bottleneck_radius,
    codebook_counts,
    dense_min_cost,
    random_feasible_assignment,
    stability_aware_columns,
    symbol_counts,
)
from fham.descriptors import DESCRIPTORS, descriptor_hashes
from fham.methods import (
    BottleneckAssignmentMethod,
    BoundedAssignmentMethod,
    OptimalAssignmentMethod,
    RandomFeasibleAssignmentMethod,
    StabilityAwareAssignmentMethod,
)


def test_all_descriptor_families_produce_four_8bit_hashes():
    image = np.arange(24 * 24, dtype=np.uint16).reshape(24, 24).astype(np.uint8)
    for descriptor in DESCRIPTORS:
        values = descriptor_hashes(image, descriptor)
        assert len(values) == 4
        assert all(0 <= value <= 255 for value in values)


def test_methods_accept_descriptor_selection():
    image = np.arange(24 * 24 * 4, dtype=np.uint16).reshape(48, 48).astype(np.uint8)
    method = OptimalAssignmentMethod(block_size=24, descriptor="dct_ordinal")
    assignment = method.embed("abc", image)
    assert assignment is not None
    assert method.extract(assignment, image) == "abc"


def test_aggregated_assignment_matches_dense_cost():
    message = b"\x00\x01\x01\x04"
    hashes = [0, 1, 2, 5, 255]
    aggregated = aggregated_min_cost_assignment(
        symbol_counts(message), codebook_counts(hashes), bound=2
    )
    assert aggregated.feasible
    assert aggregated.cost == dense_min_cost(list(message), hashes, bound=2)


def test_bottleneck_radius_is_exact():
    demands = Counter({10: 2, 20: 1})
    capacities = Counter({9: 1, 12: 1, 25: 1})
    assert bottleneck_radius(demands, capacities) == 5
    assert not aggregated_min_cost_assignment(demands, capacities, bound=4).feasible
    assert aggregated_min_cost_assignment(demands, capacities, bound=5).feasible


def test_random_and_stability_aware_assignments_respect_bounds():
    targets = [10, 11, 12]
    hashes = [9, 13, 12]
    random_columns = random_feasible_assignment(targets, hashes, bound=2, seed=7)
    assert random_columns is not None
    assert len(set(random_columns)) == len(targets)
    assert all(abs(targets[row] - hashes[col]) <= 2 for row, col in enumerate(random_columns))

    stable_columns = stability_aware_columns(
        targets, hashes, stabilities=[0.1, 0.5, 1.0], bound=2, lam=0.5
    )
    assert stable_columns is not None
    assert len(set(stable_columns)) == len(targets)


def test_bounded_descriptor_round_trip():
    image = np.arange(24 * 24 * 4, dtype=np.uint16).reshape(48, 48).astype(np.uint8)
    method = BoundedAssignmentMethod(255, block_size=24, descriptor="wavelet_gradient")
    assignment = method.embed("xy", image)
    assert assignment is not None
    assert method.extract(assignment, image) == "xy"


def test_bottleneck_method_minimizes_max_displacement_and_round_trips():
    image = np.arange(24 * 24 * 4, dtype=np.uint16).reshape(48, 48).astype(np.uint8)
    method = BottleneckAssignmentMethod(255, block_size=24)
    assignment = method.embed("abcd", image)
    assert assignment is not None
    assert max(map(abs, assignment.displacements)) <= 255
    assert method.extract(assignment, image) == "abcd"


def test_random_feasible_method_respects_bound_and_round_trips():
    image = np.arange(24 * 24 * 4, dtype=np.uint16).reshape(48, 48).astype(np.uint8)
    method = RandomFeasibleAssignmentMethod(255, seed=3, block_size=24)
    assignment = method.embed("abc", image)
    assert assignment is not None
    assert all(abs(d) <= 255 for d in assignment.displacements)
    assert method.extract(assignment, image) == "abc"


def test_stability_aware_method_uses_stabilities_and_round_trips():
    image = np.arange(24 * 24 * 4, dtype=np.uint16).reshape(48, 48).astype(np.uint8)
    lookup = OptimalAssignmentMethod(block_size=24)
    lookup.build_lookup_table(image)
    method = StabilityAwareAssignmentMethod(255, lam=0.5, block_size=24)
    method.lookup_table = lookup.lookup_table
    method.image_shape = lookup.image_shape
    method.stabilities = {
        location: 0.5
        for locations in lookup.lookup_table.values()
        for location in locations
    }
    assignment = method.embed("ab", image)
    assert assignment is not None
    assert method.extract(assignment, image) == "ab"
