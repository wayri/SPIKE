"""Small normalization helpers for the DesignIR v1 migration adapter."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def pad_drill_size(raw: Mapping[str, Any]) -> tuple[float, float]:
    value = raw.get("drill_size", raw.get("drill_size_mm", raw.get("drill", 0.0)))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = list(value)
        if len(values) >= 2:
            return (float(values[0] or 0.0), float(values[1] or 0.0))
        if len(values) == 1:
            diameter = float(values[0] or 0.0)
            return (diameter, diameter)
    diameter = float(value or 0.0)
    return (diameter, diameter)


def normalize_boolean(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1", "plated"}:
            return True
        if normalized in {"false", "no", "off", "0", "unplated"}:
            return False
    return default
