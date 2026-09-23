"""Versioned contracts for SPIKES built-in circuit archetypes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


LIBRARY_CONTRACT = "spikes/archetype-library/v1"
ARCHETYPE_CONTRACT = "spikes/archetype/v1"
ELABORATION_CONTRACT = "spikes/archetype-elaboration/v1"
LIBRARY_VALIDATION_CONTRACT = "spikes/archetype-library-validation/v1"

_ARCHETYPE_ID_RE = re.compile(
    r"^spikes\.(?:ideal|generic|power|electromechanical|core):[a-z][a-z0-9_.-]*@[1-9][0-9]*$",
    flags=re.ASCII,
)
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_.-]*$", flags=re.ASCII)
_PIN_RE = re.compile(r"^[a-z][a-z0-9_]*$", flags=re.ASCII)


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number, not a boolean.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """One numeric engineering parameter with a bounded validity domain."""

    name: str
    unit: str
    default: float
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if _TOKEN_RE.fullmatch(self.name) is None:
            raise ValueError("Parameter names must be lowercase ASCII identifiers.")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError(f"Parameter {self.name} requires an explicit unit or '1'.")
        default = _finite(self.default, f"default for {self.name}")
        minimum = None if self.minimum is None else _finite(self.minimum, f"minimum for {self.name}")
        maximum = None if self.maximum is None else _finite(self.maximum, f"maximum for {self.name}")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"Parameter {self.name} minimum exceeds its maximum.")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "default", self.validate(default))

    def validate(self, value: Any) -> float:
        number = _finite(value, self.name)
        if self.minimum is not None and number < self.minimum:
            raise ValueError(f"{self.name} must be at least {self.minimum:g} {self.unit}.")
        if self.maximum is not None and number > self.maximum:
            raise ValueError(f"{self.name} must be at most {self.maximum:g} {self.unit}.")
        return number

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ArchetypePreset:
    """A named deterministic parameter overlay."""

    preset_id: str
    title: str
    values: Mapping[str, float]
    description: str = ""

    def __post_init__(self) -> None:
        if _TOKEN_RE.fullmatch(self.preset_id) is None:
            raise ValueError("Preset IDs must be lowercase ASCII identifiers.")
        if not self.title.strip():
            raise ValueError("Preset title is required.")
        if not isinstance(self.values, Mapping):
            raise ValueError("Preset values must be a mapping.")
        normalized = {str(name): _finite(value, f"preset {self.preset_id}.{name}") for name, value in self.values.items()}
        object.__setattr__(self, "values", MappingProxyType(dict(sorted(normalized.items()))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.preset_id,
            "title": self.title,
            "values": dict(self.values),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ArchetypeDescriptor:
    """Discoverable metadata for a runnable or explicitly unavailable part."""

    archetype_id: str
    title: str
    family: str
    summary: str
    status: str
    fidelity: str
    pins: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...] = ()
    presets: tuple[ArchetypePreset, ...] = ()
    tags: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    elaborator: str = ""
    unavailable_reason: str = ""
    limitations: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    contract: str = ARCHETYPE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ARCHETYPE_CONTRACT:
            raise ValueError(f"Expected archetype contract {ARCHETYPE_CONTRACT}.")
        if _ARCHETYPE_ID_RE.fullmatch(self.archetype_id) is None:
            raise ValueError(f"Invalid archetype ID: {self.archetype_id}.")
        if not all((self.title.strip(), self.family.strip(), self.summary.strip(), self.fidelity.strip())):
            raise ValueError(f"Archetype {self.archetype_id} has incomplete descriptive metadata.")
        if self.status not in {"runnable", "unavailable"}:
            raise ValueError("Archetype status must be runnable or unavailable.")
        if not self.pins or any(_PIN_RE.fullmatch(pin) is None for pin in self.pins):
            raise ValueError(f"Archetype {self.archetype_id} requires valid pins.")
        if len(self.pins) != len(set(self.pins)):
            raise ValueError(f"Archetype {self.archetype_id} has duplicate pins.")
        parameter_names = [parameter.name for parameter in self.parameters]
        preset_ids = [preset.preset_id for preset in self.presets]
        if len(parameter_names) != len(set(parameter_names)) or len(preset_ids) != len(set(preset_ids)):
            raise ValueError(f"Archetype {self.archetype_id} has duplicate parameters or presets.")
        parameter_map = {parameter.name: parameter for parameter in self.parameters}
        for preset in self.presets:
            unknown = set(preset.values) - set(parameter_map)
            if unknown:
                raise ValueError(f"Preset {preset.preset_id} contains unknown parameters: {sorted(unknown)}.")
            for name, value in preset.values.items():
                parameter_map[name].validate(value)
        if self.status == "runnable":
            if not self.elaborator or self.unavailable_reason:
                raise ValueError("Runnable archetypes require an elaborator and no unavailable reason.")
        elif self.elaborator or not self.unavailable_reason.strip():
            raise ValueError("Unavailable archetypes require a reason and cannot declare an elaborator.")
        if not isinstance(self.provenance, Mapping):
            raise ValueError("Archetype provenance must be a mapping.")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    @property
    def available(self) -> bool:
        return self.status == "runnable"

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "id": self.archetype_id,
            "title": self.title,
            "family": self.family,
            "summary": self.summary,
            "status": self.status,
            "available": self.available,
            "fidelity": self.fidelity,
            "tags": list(self.tags),
            "unavailable_reason": self.unavailable_reason,
        }

    def to_dict(self) -> dict[str, Any]:
        result = self.to_summary_dict()
        result.update({
            "pins": list(self.pins),
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "presets": [preset.to_dict() for preset in self.presets],
            "required_capabilities": list(self.required_capabilities),
            "limitations": list(self.limitations),
            "provenance": dict(self.provenance),
        })
        return result


__all__ = [
    "ARCHETYPE_CONTRACT",
    "ELABORATION_CONTRACT",
    "LIBRARY_CONTRACT",
    "LIBRARY_VALIDATION_CONTRACT",
    "ArchetypeDescriptor",
    "ArchetypePreset",
    "ParameterSpec",
]
