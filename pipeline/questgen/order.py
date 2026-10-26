"""Ordering: the order the stops are visited in, as a walk (open path) or a loop back to the start.

Nearest neighbour from the start, then 2-opt until no reversal shortens the path. With a start point, the path
begins there (the start is not a stop); without one, every stop is tried as the first and the shortest path wins.
Deterministic: ties go to the lower index.
"""
import numpy as np

from .registry import ORDERS


def length(D, tour, closed):
    L = sum(D[a, b] for a, b in zip(tour, tour[1:]))
    return L + (D[tour[-1], tour[0]] if closed else 0.0)


def nearest(D, first):
    tour, left = [first], set(range(len(D))) - {first}
    while left:
        here = tour[-1]
        nxt = min(left, key=lambda j: (D[here, j], j))
        tour.append(nxt)
        left.remove(nxt)
    return tour


def two_opt(D, tour, closed):
    """Reverse stretches of the tour (never its first node) while that shortens it."""
    tour, best = list(tour), length(D, tour, closed)
    better = True
    while better:
        better = False
        for i in range(1, len(tour) - 1):
            for k in range(i + 1, len(tour)):
                t = tour[:i] + tour[i:k + 1][::-1] + tour[k + 1:]
                L = length(D, t, closed)
                if L < best - 1e-9:
                    tour, best, better = t, L, True
    return tour, best


def plan(xz, start, closed):
    xz = np.asarray(xz, dtype=float)
    if start is not None:
        P = np.vstack([np.asarray(start, dtype=float)[None, :], xz])
        D = np.hypot(*(P[:, None, :] - P[None, :, :]).transpose(2, 0, 1))
        tour, _ = two_opt(D, nearest(D, 0), closed)
        return [i - 1 for i in tour[1:]]
    D = np.hypot(*(xz[:, None, :] - xz[None, :, :]).transpose(2, 0, 1))
    best = None
    for first in range(len(xz)):
        tour, L = two_opt(D, nearest(D, first), closed)
        if best is None or L < best[0] - 1e-9:
            best = (L, tour)
    return best[1]


@ORDERS.register("walk")
def walk(xz, start=None):
    """The shortest open path through the stops (from the start, if given)."""
    return plan(xz, start, closed=False)


@ORDERS.register("loop")
def loop(xz, start=None):
    """The shortest round trip: back to the start (or the first stop) at the end."""
    return plan(xz, start, closed=True)
