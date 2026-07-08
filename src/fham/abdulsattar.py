from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class AbdulsattarLocation:
    x: int
    y: int


@dataclass
class AbdulsattarAssignment:
    image_shape: tuple[int, int]
    block_size: int
    locations: list[AbdulsattarLocation]


class AbdulsattarMethod:
    """Arr.4 exact ASCII mapping from Abdulsattar (2021)."""

    def __init__(self, overlapping=True):
        self.block_size = 18
        self.stride = 6 if overlapping else 18
        self.lookup_table = {}
        self.image_shape = None

    @staticmethod
    def _arrangement_four_hashes(image, stride):
        blocks = np.lib.stride_tricks.sliding_window_view(image, (18, 18))
        blocks = blocks[::stride, ::stride]
        values = []
        for row in range(3):
            for column in range(3):
                subblocks = blocks[
                    ...,
                    row * 6:(row + 1) * 6,
                    column * 6:(column + 1) * 6,
                ].astype(np.float64)
                subblocks -= subblocks.mean(axis=(-2, -1), keepdims=True)
                gram = subblocks @ np.swapaxes(subblocks, -1, -2)
                values.append(np.linalg.eigvalsh(gram)[..., -1])

        order = (0, 3, 6, 7, 8, 5, 2, 1, 4)
        hashes = np.zeros(blocks.shape[:2], dtype=np.uint8)
        for bit, (left, right) in enumerate(zip(order, order[1:])):
            hashes |= (
                (values[left] >= values[right]).astype(np.uint8) << (7 - bit)
            )
        return hashes

    def build_lookup_table(self, image):
        self.image_shape = tuple(image.shape)
        self.lookup_table = {}
        hashes = self._arrangement_four_hashes(image, self.stride)
        for row, column in np.ndindex(hashes.shape):
            value = int(hashes[row, column])
            self.lookup_table.setdefault(value, []).append(
                AbdulsattarLocation(column * self.stride, row * self.stride)
            )
        return self.capacity

    @property
    def capacity(self):
        return sum(len(locations) for locations in self.lookup_table.values())

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
        return AbdulsattarAssignment(self.image_shape, self.block_size, selected)

    def extract(self, assignment, image):
        if tuple(image.shape) != assignment.image_shape:
            image = np.asarray(
                Image.fromarray(image).resize(
                    (assignment.image_shape[1], assignment.image_shape[0]),
                    Image.Resampling.LANCZOS,
                )
            )
        characters = []
        for location in assignment.locations:
            block = image[
                location.y:location.y + assignment.block_size,
                location.x:location.x + assignment.block_size,
            ]
            value = int(self._arrangement_four_hashes(block, 18)[0, 0])
            characters.append(chr(value))
        return "".join(characters)
