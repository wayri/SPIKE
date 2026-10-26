# SPDX-License-Identifier: Apache-2.0
"""Explicit board/part ownership for reduced assembly thermal nodes."""
from __future__ import annotations

import json
from typing import Any, Mapping


def thermal_node_id(kind: str, owner: str, node: str) -> str:
    """Preserve existing board IDs while keeping part IDs in a distinct namespace."""
    values = [owner, node] if kind == "board_id" else ["part", owner, node]
    return json.dumps(values, separators=(",", ":"), ensure_ascii=True)


def thermal_endpoint(endpoint: Mapping[str, Any]) -> tuple[str, str, str]:
    scopes = set(endpoint) & {"board_id", "part_id"}
    if len(scopes) != 1:
        raise ValueError("Thermal endpoints require exactly one of board_id or part_id.")
    kind = next(iter(scopes))
    owner, node = endpoint[kind], endpoint.get("node")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 256 for value in (owner, node)):
        raise ValueError("Thermal endpoint owner and node require nonempty strings of at most 256 characters.")
    return kind, owner, node
