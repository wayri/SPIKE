# SPDX-License-Identifier: Apache-2.0
"""Named, bounded internal-engine parameter perturbations.

Mechanisms describe the intent of a circuit approximation, not validated
damage physics. Shunts must already exist in the compiled circuit.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol


class FaultSession(Protocol):
    def set_resistance(self, element_id: str, resistance_ohm: float) -> None: ...
    def set_mosfet_threshold(self, element_id: str, threshold_voltage_v: float) -> None: ...


@dataclass(frozen=True)
class FaultSite:
    name: str
    element_id: str
    parameter: str
    healthy_value: float
    minimum: float
    maximum: float
    mechanism: str

    def __post_init__(self) -> None:
        for label in ("name", "element_id", "mechanism"):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise ValueError(f"fault {label} must be nonempty text without NUL")
        bounds = {"resistance_ohm": (1e-6, 1e15), "threshold_voltage_v": (-100.0, 100.0)}
        if self.parameter not in bounds:
            raise ValueError("unsupported fault parameter")
        low, high = bounds[self.parameter]
        values = (self.minimum, self.healthy_value, self.maximum)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                   for v in values):
            raise ValueError("fault bounds and healthy value must be finite numbers")
        if not low <= self.minimum <= self.healthy_value <= self.maximum <= high:
            raise ValueError("fault bounds must contain healthy value and obey native limits")

    def validate(self, value: float) -> float:
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not self.minimum <= value <= self.maximum):
            raise ValueError(f"fault {self.name} value must be within [{self.minimum}, {self.maximum}]")
        return float(value)


def apply_fault(session: FaultSession, site: FaultSite, value: float) -> None:
    """Validate a named site's bounds before changing its native parameter."""
    number = site.validate(value)
    if site.parameter == "resistance_ohm":
        session.set_resistance(site.element_id, number)
    else:
        session.set_mosfet_threshold(site.element_id, number)


def reset_fault(session: FaultSession, site: FaultSite) -> None:
    """Restore the immutable declared healthy parameter, retaining circuit time."""
    apply_fault(session, site, site.healthy_value)
