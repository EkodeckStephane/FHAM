"""Small exact maximum-cardinality bipartite matching utility for FHAM audits."""
from __future__ import annotations

from collections import deque


def max_matching(adjacency: list[list[int]], n_right: int) -> int:
    """Hopcroft–Karp cardinality for a bipartite graph (symbols -> positions)."""
    n_left = len(adjacency)
    left_match = [-1] * n_left
    right_match = [-1] * n_right
    distance = [0] * n_left
    inf = n_left + 1
    shortest = inf

    def bfs() -> bool:
        nonlocal shortest
        q = deque()
        for u in range(n_left):
            if left_match[u] < 0:
                distance[u] = 0
                q.append(u)
            else:
                distance[u] = inf
        shortest = inf
        while q:
            u = q.popleft()
            if distance[u] >= shortest:
                continue
            for v in adjacency[u]:
                mate = right_match[v]
                if mate < 0:
                    shortest = distance[u] + 1
                elif distance[mate] == inf:
                    distance[mate] = distance[u] + 1
                    q.append(mate)
        return shortest != inf

    def dfs(u: int) -> bool:
        for v in adjacency[u]:
            mate = right_match[v]
            if ((mate < 0 and distance[u] + 1 == shortest)
                    or (mate >= 0 and distance[mate] == distance[u] + 1 and dfs(mate))):
                left_match[u] = v
                right_match[v] = u
                return True
        distance[u] = inf
        return False

    cardinality = 0
    while bfs():
        for u in range(n_left):
            if left_match[u] < 0 and dfs(u):
                cardinality += 1
    return cardinality
