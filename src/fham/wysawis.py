from dataclasses import dataclass
from functools import lru_cache
from math import ceil, comb, log2

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class WysawisLocation:
    block_index: int
    zero_count: int
    sequence_rank: int


@dataclass
class WysawisAssignment:
    image_shape: tuple[int, int]
    bit_length: int
    locations: list[WysawisLocation]


@lru_cache(maxsize=1)
def _sequences_by_zero_count():
    groups = {zero_count: [] for zero_count in range(16)}
    for value in range(1 << 15):
        zero_count = 15 - value.bit_count()
        groups[zero_count].append(value)
    return {zero_count: tuple(values) for zero_count, values in groups.items()}


@lru_cache(maxsize=1)
def _sequence_ranks():
    return {
        zero_count: {value: rank for rank, value in enumerate(values)}
        for zero_count, values in _sequences_by_zero_count().items()
    }


def _hash_block(block):
    pixels = block.reshape(-1)[:16]
    value = 0
    for left, right in zip(pixels[:-1], pixels[1:]):
        value = (value << 1) | int(left >= right)
    return value


class WysawisMethod:
    """Core block/category mapping described in the WYSAWIS paper."""

    block_size = 4
    sequence_bits = 15
    published_min_capacity_bits = 491_520
    minimum_cloud_files = 16 * 6_435

    def __init__(self):
        self.image_shape = None
        self.useful_blocks = {}

    def build_index(self, image):
        self.image_shape = tuple(image.shape)
        self.useful_blocks = {}
        height, width = image.shape
        blocks_per_row = width // self.block_size
        for y in range(0, height - self.block_size + 1, self.block_size):
            for x in range(0, width - self.block_size + 1, self.block_size):
                block = image[y:y + self.block_size, x:x + self.block_size]
                value = _hash_block(block)
                zero_count = self.sequence_bits - value.bit_count()
                block_index = (y // self.block_size) * blocks_per_row
                block_index += x // self.block_size
                self.useful_blocks.setdefault(zero_count, block_index)
                if len(self.useful_blocks) == self.sequence_bits + 1:
                    return True
        return False

    @property
    def adequate(self):
        return len(self.useful_blocks) == self.sequence_bits + 1

    def embed(self, message, image):
        if self.image_shape != tuple(image.shape) or not self.useful_blocks:
            self.build_index(image)
        if not self.adequate:
            return None
        payload = message.encode("utf-8")
        bit_length = len(payload) * 8
        bits = "".join(f"{byte:08b}" for byte in payload)
        padding = (-len(bits)) % self.sequence_bits
        bits += "0" * padding
        ranks = _sequence_ranks()
        locations = []
        for start in range(0, len(bits), self.sequence_bits):
            value = int(bits[start:start + self.sequence_bits], 2)
            zero_count = self.sequence_bits - value.bit_count()
            locations.append(
                WysawisLocation(
                    self.useful_blocks[zero_count],
                    zero_count,
                    ranks[zero_count][value],
                )
            )
        return WysawisAssignment(self.image_shape, bit_length, locations)

    def extract_bits(self, assignment, image):
        if tuple(image.shape) != assignment.image_shape:
            image = np.asarray(
                Image.fromarray(image).resize(
                    (assignment.image_shape[1], assignment.image_shape[0]),
                    Image.Resampling.LANCZOS,
                )
            )
        blocks_per_row = assignment.image_shape[1] // self.block_size
        groups = _sequences_by_zero_count()
        recovered = []
        valid = []
        for location in assignment.locations:
            block_y, block_x = divmod(location.block_index, blocks_per_row)
            y = block_y * self.block_size
            x = block_x * self.block_size
            value = _hash_block(
                image[y:y + self.block_size, x:x + self.block_size]
            )
            zero_count = self.sequence_bits - value.bit_count()
            sequences = groups[zero_count]
            if location.sequence_rank >= len(sequences):
                recovered.extend([0] * self.sequence_bits)
                valid.extend([False] * self.sequence_bits)
                continue
            segment = sequences[location.sequence_rank]
            recovered.extend(
                (segment >> shift) & 1
                for shift in range(self.sequence_bits - 1, -1, -1)
            )
            valid.extend([True] * self.sequence_bits)
        return (
            recovered[:assignment.bit_length],
            valid[:assignment.bit_length],
        )

    def extract(self, assignment, image):
        bits, valid = self.extract_bits(assignment, image)
        if not all(valid):
            return None
        payload = bytearray()
        for start in range(0, assignment.bit_length, 8):
            value = 0
            for bit in bits[start:start + 8]:
                value = (value << 1) | bit
            payload.append(value)
        return payload.decode("utf-8", errors="replace")

    @staticmethod
    def cloud_records(assignment):
        return len(assignment.locations) + 1

    @staticmethod
    def location_information_lower_bound(assignment):
        bits = 0
        for location in assignment.locations:
            bits += 4 + ceil(log2(comb(15, location.zero_count)))
        bits += ceil(log2(max(2, assignment.bit_length + 1)))
        return bits
