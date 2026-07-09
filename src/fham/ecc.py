from __future__ import annotations


def repetition_encode(message: str, repeat: int) -> str:
    """Expands each character of ``message`` into ``repeat`` consecutive
    copies. Combined with ``repetition_decode``, this is a message-layer
    repetition code: it targets the value-domain transformation sensitivity
    of the assignment channel (JPEG, additive noise, filtering, resizing,
    photometric change) documented in the extended robustness study, by
    adding redundancy rather than by changing the descriptor or the
    Location model. It does not address geometric misalignment (crop,
    rotation): those transforms decorrelate the recomputed descriptor from
    its embed-time value at a given location, and majority vote over
    decorrelated copies stays decorrelated."""
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    return "".join(character * repeat for character in message)


def repetition_decode(expanded: str, length: int, repeat: int) -> str:
    """Inverse of ``repetition_encode``: splits ``expanded`` into ``length``
    groups of ``repeat`` characters and decodes each group by majority
    vote, breaking ties by the lexicographically smallest character."""
    if len(expanded) != length * repeat:
        raise ValueError("expanded length does not match length * repeat")
    decoded = []
    for index in range(length):
        group = expanded[index * repeat:(index + 1) * repeat]
        counts: dict[str, int] = {}
        for character in group:
            counts[character] = counts.get(character, 0) + 1
        best = max(counts.items(), key=lambda item: (item[1], -ord(item[0])))
        decoded.append(best[0])
    return "".join(decoded)
