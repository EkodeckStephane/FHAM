from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import heapq
from itertools import count
import random

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class AggregatedSolution:
    flows: dict[tuple[int, int], int]
    cost: int
    feasible: bool


def symbol_counts(message: bytes | str) -> Counter[int]:
    if isinstance(message, str):
        values = message.encode("latin-1")
    else:
        values = message
    return Counter(values)


def codebook_counts(values: list[int] | np.ndarray) -> Counter[int]:
    return Counter(int(value) for value in values)


def aggregated_min_cost_assignment(
    demands: Counter[int], capacities: Counter[int], bound: int | None = None
) -> AggregatedSolution:
    source = "s"
    sink = "t"
    graph: dict[object, list[list[object]]] = defaultdict(list)

    def add_edge(left, right, capacity, cost):
        graph[left].append([right, capacity, cost, len(graph[right])])
        graph[right].append([left, 0, -cost, len(graph[left]) - 1])

    total = sum(demands.values())
    for value, demand in demands.items():
        add_edge(source, ("d", value), demand, 0)
    for value, capacity in capacities.items():
        add_edge(("c", value), sink, capacity, 0)
    for demand_value in demands:
        for cover_value in capacities:
            cost = abs(demand_value - cover_value)
            if bound is None or cost <= bound:
                add_edge(("d", demand_value), ("c", cover_value), demands[demand_value], cost)

    flow, cost = _min_cost_flow(graph, source, sink, total)
    if flow != total:
        return AggregatedSolution({}, cost, False)

    flows: dict[tuple[int, int], int] = {}
    for demand_value in demands:
        node = ("d", demand_value)
        for edge in graph[node]:
            target, remaining, edge_cost, reverse_index = edge
            if not (isinstance(target, tuple) and target[0] == "c"):
                continue
            reverse = graph[target][reverse_index]
            used = int(reverse[1])
            if used:
                flows[(demand_value, int(target[1]))] = used
    return AggregatedSolution(flows, cost, True)


def _min_cost_flow(graph, source, sink, target_flow):
    flow = 0
    cost = 0
    potentials = defaultdict(int)
    while flow < target_flow:
        distances = defaultdict(lambda: float("inf"))
        previous = {}
        distances[source] = 0
        tie = count()
        queue = [(0, next(tie), source)]
        while queue:
            distance, _, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for index, edge in enumerate(graph[node]):
                next_node, capacity, edge_cost, _ = edge
                if capacity <= 0:
                    continue
                reduced = edge_cost + potentials[node] - potentials[next_node]
                candidate = distance + reduced
                if candidate < distances[next_node]:
                    distances[next_node] = candidate
                    previous[next_node] = (node, index)
                    heapq.heappush(queue, (candidate, next(tie), next_node))
        if sink not in previous:
            break
        for node, distance in distances.items():
            if distance < float("inf"):
                potentials[node] += distance
        pushed = target_flow - flow
        node = sink
        while node != source:
            prev_node, edge_index = previous[node]
            pushed = min(pushed, graph[prev_node][edge_index][1])
            node = prev_node
        node = sink
        while node != source:
            prev_node, edge_index = previous[node]
            edge = graph[prev_node][edge_index]
            edge[1] -= pushed
            graph[node][edge[3]][1] += pushed
            cost += pushed * edge[2]
            node = prev_node
        flow += pushed
    return flow, cost


def dense_min_cost(targets: list[int], hashes: list[int], bound: int | None = None) -> int | None:
    if len(targets) > len(hashes):
        return None
    costs = np.abs(
        np.asarray(targets, dtype=np.int16)[:, None]
        - np.asarray(hashes, dtype=np.int16)[None, :]
    ).astype(np.float64)
    if bound is not None:
        costs[costs > bound] = np.inf
    try:
        rows, columns = linear_sum_assignment(costs)
    except ValueError:
        return None
    if not np.isfinite(costs[rows, columns]).all():
        return None
    return int(costs[rows, columns].sum())


def bottleneck_radius(demands: Counter[int], capacities: Counter[int]) -> int | None:
    if sum(demands.values()) > sum(capacities.values()):
        return None
    low, high = 0, 255
    answer = None
    while low <= high:
        mid = (low + high) // 2
        if aggregated_min_cost_assignment(demands, capacities, mid).feasible:
            answer = mid
            high = mid - 1
        else:
            low = mid + 1
    return answer


def random_feasible_assignment(targets: list[int], hashes: list[int], bound: int, seed: int) -> list[int] | None:
    rng = random.Random(seed)
    available = list(range(len(hashes)))
    result = []
    for target in targets:
        candidates = [index for index in available if abs(target - hashes[index]) <= bound]
        if not candidates:
            return None
        chosen = rng.choice(candidates)
        available.remove(chosen)
        result.append(chosen)
    return result


def stability_aware_cost(target: int, cover_hash: int, stability: float, lam: float) -> float:
    residual = abs(target - cover_hash) / 255.0
    return lam * residual + (1.0 - lam) * (1.0 - stability)


def stability_aware_columns(
    targets: list[int],
    hashes: list[int],
    stabilities: list[float],
    bound: int,
    lam: float,
) -> list[int] | None:
    if len(targets) > len(hashes):
        return None
    costs = np.empty((len(targets), len(hashes)), dtype=np.float64)
    for row, target in enumerate(targets):
        for column, cover_hash in enumerate(hashes):
            residual = abs(target - cover_hash)
            costs[row, column] = (
                stability_aware_cost(target, cover_hash, stabilities[column], lam)
                if residual <= bound
                else np.inf
            )
    try:
        rows, columns = linear_sum_assignment(costs)
    except ValueError:
        return None
    if not np.isfinite(costs[rows, columns]).all():
        return None
    return [int(column) for _, column in sorted(zip(rows, columns))]
