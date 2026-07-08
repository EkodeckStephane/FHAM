from __future__ import annotations

import numpy as np
from scipy.fft import dctn

from .hashing import hash_block_arrangements


def _as_gray_uint8(block: np.ndarray) -> np.ndarray:
    array = np.asarray(block)
    if array.ndim == 3:
        array = (
            0.299 * array[..., 0] + 0.587 * array[..., 1] + 0.114 * array[..., 2]
        )
    if array.dtype == bool:
        array = array.astype(np.uint8) * 255
    elif np.issubdtype(array.dtype, np.floating):
        scale = 255 if array.max(initial=0) <= 1 else 1
        array = np.clip(array * scale, 0, 255)
    return array.astype(np.uint8, copy=False)


def spectral_hashes(block: np.ndarray) -> list[int]:
    return hash_block_arrangements(_as_gray_uint8(block))


def dct_ordinal_hashes(block: np.ndarray) -> list[int]:
    gray = _as_gray_uint8(block).astype(np.float64)
    side = gray.shape[0]
    sub_side = side // 3
    values = []
    coords = ((0, 1), (1, 0), (1, 1), (0, 2), (2, 0), (1, 2), (2, 1), (2, 2), (0, 3))
    for row in range(3):
        for col in range(3):
            sub = gray[row * sub_side:(row + 1) * sub_side, col * sub_side:(col + 1) * sub_side]
            coeff = dctn(sub, type=2, norm="ortho")
            values.append(float(sum(coeff[r, c] for r, c in coords if r < coeff.shape[0] and c < coeff.shape[1])))
    return _ordinal_arrangements(values)


def wavelet_gradient_hashes(block: np.ndarray) -> list[int]:
    gray = _as_gray_uint8(block).astype(np.float64)
    side = gray.shape[0]
    sub_side = side // 3
    values = []
    for row in range(3):
        for col in range(3):
            sub = gray[row * sub_side:(row + 1) * sub_side, col * sub_side:(col + 1) * sub_side]
            even_rows = sub[0::2, :]
            odd_rows = sub[1::2, :]
            ll = (even_rows[:, 0::2] + even_rows[:, 1::2] + odd_rows[:, 0::2] + odd_rows[:, 1::2]) / 4
            lh = (even_rows[:, 0::2] - even_rows[:, 1::2] + odd_rows[:, 0::2] - odd_rows[:, 1::2]) / 4
            hl = (even_rows[:, 0::2] + even_rows[:, 1::2] - odd_rows[:, 0::2] - odd_rows[:, 1::2]) / 4
            gy, gx = np.gradient(sub)
            values.append(float(ll.mean() + lh.std() + hl.std() + np.hypot(gx, gy).mean()))
    return _ordinal_arrangements(values)


def _ordinal_arrangements(values: list[float]) -> list[int]:
    orders = (
        (0, 1, 2, 5, 8, 7, 6, 3, 4),
        tuple(range(9)),
        (0, 3, 6, 7, 8, 5, 2, 1, 4),
    )
    hashes = [
        sum(
            (values[order[index]] >= values[order[index + 1]]) << (7 - index)
            for index in range(8)
        )
        for order in orders
    ]
    hashes.append(
        sum(
            (values[4] <= values[index]) << bit
            for bit, index in zip(range(7, -1, -1), (0, 1, 2, 3, 5, 6, 7, 8))
        )
    )
    return hashes


DESCRIPTORS = {
    "spectral": spectral_hashes,
    "dct_ordinal": dct_ordinal_hashes,
    "wavelet_gradient": wavelet_gradient_hashes,
}


def descriptor_hashes(block: np.ndarray, descriptor: str = "spectral") -> list[int]:
    try:
        return DESCRIPTORS[descriptor](block)
    except KeyError as exc:
        raise ValueError(f"unknown descriptor: {descriptor}") from exc
