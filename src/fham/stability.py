"""Position-level stability estimates used in the preregistered Step 1 study."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from scipy.special import ndtr

from .descriptors import descriptor_hashes
from .hashing import spectral_comparison_margins


def _location_hash_and_margins(image, location, block_size, descriptor):
    block = image[
        location.y:location.y + block_size,
        location.x:location.x + block_size,
    ]
    hashes = descriptor_hashes(block, descriptor)
    if descriptor != "spectral":
        raise ValueError("continuous comparison margins are defined for spectral only")
    margins = spectral_comparison_margins(block)[location.arrangement]
    return hashes[location.arrangement], margins


def _block_payload(image, x, y, block_size, descriptor):
    block = image[y:y + block_size, x:x + block_size]
    hashes = descriptor_hashes(block, descriptor)
    margins = (spectral_comparison_margins(block)
               if descriptor == "spectral" else None)
    return hashes, margins


def _block_payloads(image, coordinates, block_size, descriptor):
    """Vectorized codebook evaluation for all grid positions in one image."""
    coordinates = list(coordinates)
    if descriptor != "spectral":
        return {
            xy: _block_payload(image, *xy, block_size, descriptor)
            for xy in coordinates
        }
    sub_side = block_size // 3
    blocks = np.stack([
        image[y:y + block_size, x:x + block_size] for x, y in coordinates
    ]).astype(np.float64)
    subblocks = blocks.reshape(
        len(blocks), 3, sub_side, 3, sub_side
    ).transpose(0, 1, 3, 2, 4).reshape(-1, sub_side, sub_side)
    centered = subblocks - subblocks.mean(axis=(-2, -1), keepdims=True)
    gram = centered @ np.swapaxes(centered, -1, -2)
    values = np.linalg.eigvalsh(gram)[..., -1].reshape(len(blocks), 3, 3)
    flat = values.reshape(len(blocks), 9)
    orders = (
        (0, 1, 2, 5, 8, 7, 6, 3, 4),
        tuple(range(9)),
        (0, 3, 6, 7, 8, 5, 2, 1, 4),
    )
    hashes = []
    margins = []
    for order in orders:
        diffs = np.stack([
            flat[:, order[i]] - flat[:, order[i + 1]] for i in range(8)
        ], axis=1)
        margins.append(diffs)
        hashes.append(np.sum(
            (diffs >= 0).astype(np.uint16)
            * (2 ** np.arange(7, -1, -1, dtype=np.uint16)), axis=1
        ))
    comparison_indices = (0, 1, 2, 3, 5, 6, 7, 8)
    final_diffs = np.stack([
        flat[:, idx] - flat[:, 4] for idx in comparison_indices
    ], axis=1)
    margins.append(final_diffs)
    hashes.append(np.sum(
        (final_diffs >= 0).astype(np.uint16)
        * (2 ** np.arange(7, -1, -1, dtype=np.uint16)), axis=1
    ))
    hash_values = np.stack(hashes, axis=1).astype(np.int16)
    margin_values = np.stack(margins, axis=1)
    return {
        xy: (hash_values[i].tolist(), margin_values[i])
        for i, xy in enumerate(coordinates)
    }


def estimate_position_stability(image, locations, block_size, descriptor,
                                development_images: Iterable[np.ndarray]):
    """Estimate empirical unchanged-hash and continuous-margin scores.

    Returns ``(empirical, continuous, rows)`` keyed by assignment Location.
    The per-comparison development standard deviation is estimated across
    paired identity/development margins, then floored at its fifth percentile
    within the cover, as specified in the Step 1 protocol.
    """
    development_images = list(development_images)
    if not development_images:
        raise ValueError("at least one development transform is required")
    coordinates = sorted({(loc.x, loc.y) for loc in locations})
    base = {}
    base_margins = {}
    attacked_margins = {loc: [] for loc in locations}
    unchanged = {loc: 0 for loc in locations}
    base_blocks = _block_payloads(image, coordinates, block_size, descriptor)
    for location in locations:
        hashes, margins = base_blocks[(location.x, location.y)]
        base[location] = hashes[location.arrangement]
        base_margins[location] = margins[location.arrangement]
    for transformed in development_images:
        transformed_blocks = _block_payloads(
            transformed, coordinates, block_size, descriptor
        )
        for location in locations:
            hashes, margins = transformed_blocks[(location.x, location.y)]
            value = hashes[location.arrangement]
            margins = margins[location.arrangement]
            unchanged[location] += int(value == base[location])
            attacked_margins[location].append(margins)
    empirical = {
        loc: unchanged[loc] / len(development_images) for loc in locations
    }
    if descriptor != "spectral":
        return empirical, {}, []

    deviations = {
        loc: np.std(
            np.stack(attacked_margins[loc], axis=0) - base_margins[loc],
            axis=0,
            ddof=1 if len(development_images) > 1 else 0,
        )
        for loc in locations
    }
    all_sigmas = np.concatenate([v.ravel() for v in deviations.values()])
    floor = max(float(np.percentile(all_sigmas, 5)), np.finfo(float).eps)
    continuous = {}
    rows = []
    for loc in locations:
        sigma = np.maximum(deviations[loc], floor)
        z = np.abs(base_margins[loc]) / sigma
        continuous[loc] = float(np.prod(ndtr(z)))
        rows.append({
            "x": loc.x,
            "y": loc.y,
            "arrangement": loc.arrangement,
            "hash": base[loc],
            "empirical_stability": empirical[loc],
            "continuous_stability": continuous[loc],
            "sigma_floor": floor,
            "margins": base_margins[loc].tolist(),
            "sigma": sigma.tolist(),
            "z": z.tolist(),
        })
    return empirical, continuous, rows


def receiver_reliability_flags(received, locations, block_size, descriptor,
                               jitter_images, z_flag):
    """Return per-location R-a flags and receiver-only reliability features."""
    jitter_images = list(jitter_images)
    if len(jitter_images) != 8:
        raise ValueError("R-a requires exactly eight receiver-side perturbations")
    flagged = {}
    rows = []
    coordinates = {(loc.x, loc.y) for loc in locations}
    jitter_blocks = [
        _block_payloads(x, coordinates, block_size, descriptor)
        for x in jitter_images
    ]
    received_blocks = _block_payloads(
        received, coordinates, block_size, descriptor
    )
    if descriptor != "spectral":
        raise ValueError("R-a margin flagging currently supports spectral only")
    per_location = {}
    all_sigmas = []
    for location in locations:
        xy = (location.x, location.y)
        base_hash = received_blocks[xy][0][location.arrangement]
        base_margin = received_blocks[xy][1][location.arrangement]
        jitter = [
            (block[xy][0][location.arrangement],
             block[xy][1][location.arrangement])
            for block in jitter_blocks
        ]
        hashes = [item[0] for item in jitter]
        sigma = np.std(
            np.stack([item[1] for item in jitter]) - base_margin,
            axis=0,
            ddof=1,
        )
        per_location[location] = (base_hash, base_margin, hashes, sigma)
        all_sigmas.extend(sigma.tolist())
    cover_floor = max(float(np.percentile(all_sigmas, 5)), np.finfo(float).eps)
    for location in locations:
        base_hash, base_margin, hashes, sigma = per_location[location]
        z = np.abs(base_margin) / np.maximum(sigma, cover_floor)
        any_flip = any(value != base_hash for value in hashes)
        flagged[location] = bool(any_flip or float(z.min()) < z_flag)
        rows.append({
            "x": location.x,
            "y": location.y,
            "arrangement": location.arrangement,
            "received_hash": base_hash,
            "any_jitter_hash_flip": int(any_flip),
            "min_margin_z": float(z.min()),
            "sigma_floor": cover_floor,
            "flagged": int(flagged[location]),
        })
    return flagged, rows
