# SPDX-License-Identifier: Apache-2.0
"""Build a DC load RHS using voltage deviations at clamped boundaries."""

from __future__ import annotations

from math import fsum
from typing import Any, Dict, List, Sequence

import numpy as np


def shifted_dc_rhs(
    edges: Sequence[Dict[str, Any]],
    rhs: np.ndarray,
    unknown: np.ndarray,
    known_mask: np.ndarray,
    voltage_offset: np.ndarray,
) -> np.ndarray:
    """Stamp known-node voltage offsets without subtracting large G*V terms."""

    reduced_rhs = rhs[unknown].copy()
    unknown_lookup = np.full(rhs.size, -1, dtype=np.int64)
    unknown_lookup[unknown] = np.arange(unknown.size)
    boundary_terms: Dict[int, List[float]] = {}
    for edge in edges:
        a, b = edge["a"], edge["b"]
        if known_mask[a] == known_mask[b]:
            continue
        free, clamped = (b, a) if known_mask[a] else (a, b)
        offset = voltage_offset[clamped]
        if offset:
            boundary_terms.setdefault(free, []).append(offset / edge["resistance_ohm"])
    for node, terms in boundary_terms.items():
        reduced_rhs[unknown_lookup[node]] += fsum(terms)
    return reduced_rhs
