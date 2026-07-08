from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment

from .assignment import random_feasible_assignment, stability_aware_columns
from .config import BLOCK_SIZE
from .descriptors import descriptor_hashes


@dataclass(frozen=True)
class Location:
    x: int
    y: int
    arrangement: int


@dataclass
class Assignment:
    image_shape: tuple[int, int]
    block_size: int
    locations: list[Location]
    displacements: list[int]


class BaseMethod:
    def __init__(self, block_size=BLOCK_SIZE, descriptor="spectral"):
        self.block_size = block_size
        self.descriptor = descriptor
        self.lookup_table = {}
        self.image_shape = None

    def build_lookup_table(self, image):
        self.image_shape = tuple(image.shape)
        self.lookup_table = {}
        height, width = image.shape
        for y in range(0, height - self.block_size + 1, self.block_size):
            for x in range(0, width - self.block_size + 1, self.block_size):
                block = image[y:y + self.block_size, x:x + self.block_size]
                for arrangement, hash_value in enumerate(
                    descriptor_hashes(block, self.descriptor)
                ):
                    self.lookup_table.setdefault(hash_value, []).append(
                        Location(x, y, arrangement)
                    )
        return self.capacity

    @property
    def capacity(self):
        return sum(len(locations) for locations in self.lookup_table.values())

    def extract(self, assignment, image):
        if tuple(image.shape) != assignment.image_shape:
            image = np.asarray(
                Image.fromarray(image).resize(
                    (assignment.image_shape[1], assignment.image_shape[0]),
                    Image.Resampling.LANCZOS,
                )
            )
        characters = []
        for location, displacement in zip(
            assignment.locations, assignment.displacements
        ):
            block = image[
                location.y:location.y + assignment.block_size,
                location.x:location.x + assignment.block_size,
            ]
            value = descriptor_hashes(block, self.descriptor)[location.arrangement]
            characters.append(chr(max(0, min(255, value + displacement))))
        return "".join(characters)


class ExactMatchMethod(BaseMethod):
    def embed(self, message, image):
        if not self.lookup_table:
            self.build_lookup_table(image)
        remaining = {
            value: list(locations) for value, locations in self.lookup_table.items()
        }
        selected = []
        for character in message:
            value = ord(character)
            if not remaining.get(value):
                return None
            selected.append(remaining[value].pop())
        return Assignment(self.image_shape, self.block_size, selected, [0] * len(message))


class GreedyAssignmentMethod(BaseMethod):
    def embed(self, message, image):
        if not self.lookup_table:
            self.build_lookup_table(image)
        if len(message) > self.capacity:
            return None
        remaining = {
            value: list(locations) for value, locations in self.lookup_table.items()
        }
        locations = []
        displacements = []
        for character in message:
            target = ord(character)
            value = min(
                (candidate for candidate, entries in remaining.items() if entries),
                key=lambda candidate: (abs(candidate - target), candidate),
            )
            locations.append(remaining[value].pop())
            displacements.append(target - value)
        return Assignment(
            self.image_shape, self.block_size, locations, displacements
        )


class OptimalAssignmentMethod(BaseMethod):
    def embed(self, message, image):
        if not self.lookup_table:
            self.build_lookup_table(image)
        if len(message) > self.capacity:
            return None
        records = [
            (value, location)
            for value in sorted(self.lookup_table)
            for location in self.lookup_table[value]
        ]
        targets = np.fromiter((ord(character) for character in message), dtype=np.int16)
        hashes = np.fromiter((value for value, _ in records), dtype=np.int16)
        rows, columns = linear_sum_assignment(
            np.abs(targets[:, None] - hashes[None, :])
        )
        ordered_columns = columns[np.argsort(rows)]
        locations = [records[index][1] for index in ordered_columns]
        displacements = [
            int(target - records[index][0])
            for target, index in zip(targets, ordered_columns)
        ]
        return Assignment(
            self.image_shape, self.block_size, locations, displacements
        )


class BottleneckAssignmentMethod(BaseMethod):
    """Minimizes the maximum |displacement| (A4) instead of the L1 sum, via
    binary search on the threshold followed by a feasibility check with the
    Jonker-Volgenant solver used by ``scipy.optimize.linear_sum_assignment``."""

    def __init__(self, max_displacement, block_size=BLOCK_SIZE, descriptor="spectral"):
        super().__init__(block_size, descriptor)
        self.max_displacement = max_displacement

    def embed(self, message, image):
        if not self.lookup_table:
            self.build_lookup_table(image)
        if len(message) > self.capacity:
            return None
        records = [
            (value, location)
            for value in sorted(self.lookup_table)
            for location in self.lookup_table[value]
        ]
        targets = np.fromiter((ord(character) for character in message), dtype=np.int16)
        hashes = np.fromiter((value for value, _ in records), dtype=np.int16)
        base_costs = np.abs(targets[:, None] - hashes[None, :]).astype(np.float64)
        low, high = 0, int(self.max_displacement)
        best = None
        while low <= high:
            mid = (low + high) // 2
            costs = base_costs.copy()
            costs[costs > mid] = np.inf
            try:
                rows, columns = linear_sum_assignment(costs)
            except ValueError:
                rows = None
            if (
                rows is not None
                and len(rows) == len(message)
                and np.isfinite(costs[rows, columns]).all()
            ):
                best = (rows, columns)
                high = mid - 1
            else:
                low = mid + 1
        if best is None:
            return None
        rows, columns = best
        ordered_columns = columns[np.argsort(rows)]
        locations = [records[index][1] for index in ordered_columns]
        displacements = [
            int(target - records[index][0])
            for target, index in zip(targets, ordered_columns)
        ]
        return Assignment(
            self.image_shape, self.block_size, locations, displacements
        )


class RandomFeasibleAssignmentMethod(BaseMethod):
    """Wraps ``assignment.random_feasible_assignment`` (A6): a randomized
    feasible assignment used only as a lower-anchor baseline, not a proposed
    contribution."""

    def __init__(self, max_displacement, seed=0, block_size=BLOCK_SIZE, descriptor="spectral"):
        super().__init__(block_size, descriptor)
        self.max_displacement = max_displacement
        self.seed = seed

    def embed(self, message, image):
        if not self.lookup_table:
            self.build_lookup_table(image)
        if len(message) > self.capacity:
            return None
        records = [
            (value, location)
            for value in sorted(self.lookup_table)
            for location in self.lookup_table[value]
        ]
        targets = [ord(character) for character in message]
        hashes = [value for value, _ in records]
        indices = random_feasible_assignment(
            targets, hashes, self.max_displacement, self.seed
        )
        if indices is None:
            return None
        locations = [records[index][1] for index in indices]
        displacements = [
            target - records[index][0] for target, index in zip(targets, indices)
        ]
        return Assignment(
            self.image_shape, self.block_size, locations, displacements
        )


class StabilityAwareAssignmentMethod(BaseMethod):
    """Assignment using the composite cost
    ``c = lam * normalized_residual + (1 - lam) * (1 - stability)``.

    ``stabilities`` maps a ``Location`` to an empirically estimated
    probability that its descriptor hash is unchanged under a development
    subset of the transformation channel; unseen locations default to 1.0
    (assumed stable)."""

    def __init__(
        self, max_displacement, lam, block_size=BLOCK_SIZE, descriptor="spectral"
    ):
        super().__init__(block_size, descriptor)
        self.max_displacement = max_displacement
        self.lam = lam
        self.stabilities: dict[Location, float] = {}

    def embed(self, message, image):
        if not self.lookup_table:
            self.build_lookup_table(image)
        if len(message) > self.capacity:
            return None
        records = [
            (value, location)
            for value in sorted(self.lookup_table)
            for location in self.lookup_table[value]
        ]
        targets = [ord(character) for character in message]
        hashes = [value for value, _ in records]
        stabilities = [
            self.stabilities.get(location, 1.0) for _, location in records
        ]
        columns = stability_aware_columns(
            targets, hashes, stabilities, self.max_displacement, self.lam
        )
        if columns is None:
            return None
        locations = [records[index][1] for index in columns]
        displacements = [
            target - records[index][0] for target, index in zip(targets, columns)
        ]
        return Assignment(
            self.image_shape, self.block_size, locations, displacements
        )


class BoundedAssignmentMethod(OptimalAssignmentMethod):
    def __init__(self, max_displacement, block_size=BLOCK_SIZE, descriptor="spectral"):
        super().__init__(block_size, descriptor)
        self.max_displacement = max_displacement

    def embed(self, message, image):
        if not self.lookup_table:
            self.build_lookup_table(image)
        if len(message) > self.capacity:
            return None
        records = [
            (value, location)
            for value in sorted(self.lookup_table)
            for location in self.lookup_table[value]
        ]
        targets = np.fromiter((ord(character) for character in message), dtype=np.int16)
        hashes = np.fromiter((value for value, _ in records), dtype=np.int16)
        costs = np.abs(targets[:, None] - hashes[None, :]).astype(np.float64)
        costs[costs > self.max_displacement] = np.inf
        try:
            rows, columns = linear_sum_assignment(costs)
        except ValueError:
            return None
        if not np.isfinite(costs[rows, columns]).all():
            return None
        ordered_columns = columns[np.argsort(rows)]
        locations = [records[index][1] for index in ordered_columns]
        displacements = [
            int(target - records[index][0])
            for target, index in zip(targets, ordered_columns)
        ]
        return Assignment(
            self.image_shape, self.block_size, locations, displacements
        )
