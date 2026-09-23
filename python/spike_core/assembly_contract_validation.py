"""Shared scalar validation for typed AssemblyIR records."""

from __future__ import annotations

import math
from typing import Optional


def validate_optional_physical(
    value: Optional[float], label: str, *, strictly_positive: bool = False,
) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"AssemblyIR {label} must be numeric when supplied.") from exc
    if not math.isfinite(numeric) or numeric < 0 or (strictly_positive and numeric == 0):
        qualifier = "positive" if strictly_positive else "finite and non-negative"
        raise ValueError(f"AssemblyIR {label} must be {qualifier} when supplied.")
    return numeric
