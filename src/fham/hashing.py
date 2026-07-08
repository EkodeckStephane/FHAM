import numpy as np


def largest_eigenvalue(block):
    matrix = np.asarray(block, dtype=np.float64)
    matrix -= matrix.mean()
    try:
        return float(np.linalg.eigvalsh(matrix @ matrix.T).max())
    except np.linalg.LinAlgError:
        return float(np.abs(matrix).max())


def hash_block_arrangements(block):
    side = block.shape[0]
    sub_side = side // 3
    sub_blocks = [
        block[row * sub_side:(row + 1) * sub_side,
              col * sub_side:(col + 1) * sub_side]
        for row in range(3)
        for col in range(3)
    ]
    values = [largest_eigenvalue(sub_block) for sub_block in sub_blocks]
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
        sum((values[4] <= values[index]) << bit
            for bit, index in zip(range(7, -1, -1), (0, 1, 2, 3, 5, 6, 7, 8)))
    )
    return hashes
