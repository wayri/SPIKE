# SPDX-License-Identifier: Apache-2.0
"""Original bounded AABB hierarchy; emits all positive box-overlap pairs.

Median center splits bound tree depth even for coincident boxes. Traversal
uses a depth-first stack and bounded leaf products, never a global pair array.
The caller owns the exact intersection test and the candidate budget.
"""
import numpy as np


def overlapping_pairs(lows, highs, max_visits, reject):
    centers = (lows + highs) / 2
    nodes = []

    def build(ids):
        index = len(nodes)
        lo, hi = lows[ids].min(0), highs[ids].max(0)
        nodes.append(None)
        if len(ids) <= 8:
            nodes[index] = (lo, hi, ids, None)
        else:
            axis = int(np.argmax(np.ptp(centers[ids], axis=0)))
            middle = len(ids) // 2
            ids = ids[np.argpartition(centers[ids, axis], middle)]
            children = (build(ids[:middle]), build(ids[middle:]))
            nodes[index] = (lo, hi, None, children)
        return index

    build(np.arange(len(lows)))
    pending, visits = [(0, 0)], 0
    while pending:
        a, b = pending.pop()
        visits += 1
        reject(visits <= max_visits, "Geometry hierarchy traversal budget exceeded.")
        al, ah, ai, ac = nodes[a]
        bl, bh, bi, bc = nodes[b]
        if np.any(np.minimum(ah, bh) <= np.maximum(al, bl)):
            continue
        if a == b and ac is not None:
            pending.extend(((ac[0], ac[0]), (ac[0], ac[1]), (ac[1], ac[1])))
        elif ac is not None:
            pending.extend(((ac[0], b), (ac[1], b)))
        elif bc is not None:
            pending.extend(((a, bc[0]), (a, bc[1])))
        else:
            mask = np.all(np.minimum(highs[ai, None], highs[bi]) >
                          np.maximum(lows[ai, None], lows[bi]), axis=2)
            for x, y in zip(*np.nonzero(mask)):
                i, j = int(ai[x]), int(bi[y])
                if a != b or i < j:
                    yield i, j
