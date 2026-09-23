"""Typed topology-free assembly placement increments."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional


ASSEMBLY_PLACEMENT_POLICY_V1_CONTRACT = "spike/assembly-placement-policy/v1"


@dataclass(frozen=True)
class AssemblyPlacementPolicy:
    contract: str = ASSEMBLY_PLACEMENT_POLICY_V1_CONTRACT
    translation_snap_mm: Optional[float] = None
    rotation_snap_deg: Optional[float] = None

    def __post_init__(self) -> None:
        if self.contract != ASSEMBLY_PLACEMENT_POLICY_V1_CONTRACT:
            raise ValueError(f"Unsupported assembly placement policy contract: {self.contract}")
        for value, label, maximum in (
            (self.translation_snap_mm, "translation_snap_mm", None),
            (self.rotation_snap_deg, "rotation_snap_deg", 180.0),
        ):
            if value is None:
                continue
            if isinstance(value, bool):
                raise ValueError(f"Assembly placement policy {label} must be a finite positive number or null.")
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Assembly placement policy {label} must be a finite positive number or null.") from exc
            if not math.isfinite(numeric) or numeric <= 0 or (maximum is not None and numeric > maximum):
                bound = f" at most {maximum:g}" if maximum is not None else ""
                raise ValueError(f"Assembly placement policy {label} must be finite, positive, and{bound}.")
            object.__setattr__(self, label, numeric)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AssemblyPlacementPolicy":
        if not isinstance(raw, Mapping):
            raise ValueError("Assembly placement policy must be an object.")
        required = {"contract", "translation_snap_mm", "rotation_snap_deg"}
        if set(raw) != required:
            raise ValueError("Assembly placement policy must contain exactly contract, translation_snap_mm, and rotation_snap_deg.")
        return cls(**dict(raw))
