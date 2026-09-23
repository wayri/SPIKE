"""Versioned, JSON-compatible contracts for persistent SPIKES sessions.

These contracts describe a soft-real-time orchestration layer.  They are not a
hard-real-time or HIL qualification contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


COMPILED_BLOCK_CONTRACT = "spikes/compiled-block/v1"
SESSION_CHECKPOINT_CONTRACT = "spikes/session-checkpoint/v1"
SESSION_EVENT_CONTRACT = "spikes/session-event/v1"
SESSION_STATS_CONTRACT = "spikes/session-stats/v1"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$:/-]*$", flags=re.ASCII)


def _identifier(value: Any, label: str) -> str:
    normalized = str(value).strip()
    if not normalized or _IDENTIFIER_RE.fullmatch(normalized) is None:
        raise ValueError(f"{label} is not a valid stable identifier.")
    return normalized


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}.")
    return number


class ControlType(str, Enum):
    MOMENTARY = "momentary"
    TOGGLE = "toggle"
    PULSE = "pulse"
    SET = "set"
    INCREMENT = "increment"
    ANALOG_RAMP = "analog_ramp"


@dataclass(frozen=True, slots=True)
class SignalDescriptor:
    """One observable with an immutable integer ID in a compiled block."""

    id: int
    name: str
    unit: str = ""
    initial_value: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.id, bool) or int(self.id) != self.id or self.id < 0:
            raise ValueError("signal id must be a non-negative integer.")
        object.__setattr__(self, "id", int(self.id))
        object.__setattr__(self, "name", _identifier(self.name, "signal name"))
        object.__setattr__(self, "unit", str(self.unit).strip())
        object.__setattr__(self, "initial_value", _finite(self.initial_value, "signal initial value"))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "unit": self.unit, "initial_value": self.initial_value}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SignalDescriptor":
        return cls(
            id=value.get("id", -1),
            name=value.get("name", ""),
            unit=value.get("unit", ""),
            initial_value=value.get("initial_value", 0.0),
        )


@dataclass(frozen=True, slots=True)
class InputDescriptor:
    """One typed, bounded control with a stable integer ID."""

    id: int
    name: str
    control_type: ControlType
    unit: str = ""
    default_value: float = 0.0
    minimum: float = 0.0
    maximum: float = 1.0
    active_value: float = 1.0
    safe_value: float = 0.0
    pulse_duration_s: float = 0.001
    ramp_rate_per_s: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.id, bool) or int(self.id) != self.id or self.id < 0:
            raise ValueError("input id must be a non-negative integer.")
        object.__setattr__(self, "id", int(self.id))
        object.__setattr__(self, "name", _identifier(self.name, "input name"))
        try:
            kind = ControlType(self.control_type)
        except ValueError as exc:
            raise ValueError("input control_type is unsupported.") from exc
        object.__setattr__(self, "control_type", kind)
        object.__setattr__(self, "unit", str(self.unit).strip())
        minimum = _finite(self.minimum, "input minimum")
        maximum = _finite(self.maximum, "input maximum")
        if minimum > maximum:
            raise ValueError("input minimum cannot exceed maximum.")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        for name in ("default_value", "active_value", "safe_value"):
            value = _finite(getattr(self, name), f"input {name}")
            if not minimum <= value <= maximum:
                raise ValueError(f"input {name} must be inside its bounds.")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self, "pulse_duration_s", _finite(self.pulse_duration_s, "pulse duration", positive=True)
        )
        object.__setattr__(
            self, "ramp_rate_per_s", _finite(self.ramp_rate_per_s, "ramp rate", positive=True)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "control_type": self.control_type.value,
            "unit": self.unit,
            "default_value": self.default_value,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "active_value": self.active_value,
            "safe_value": self.safe_value,
            "pulse_duration_s": self.pulse_duration_s,
            "ramp_rate_per_s": self.ramp_rate_per_s,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InputDescriptor":
        return cls(
            id=value.get("id", -1),
            name=value.get("name", ""),
            control_type=value.get("control_type", ""),
            unit=value.get("unit", ""),
            default_value=value.get("default_value", 0.0),
            minimum=value.get("minimum", 0.0),
            maximum=value.get("maximum", 1.0),
            active_value=value.get("active_value", 1.0),
            safe_value=value.get("safe_value", 0.0),
            pulse_duration_s=value.get("pulse_duration_s", 0.001),
            ramp_rate_per_s=value.get("ramp_rate_per_s", 1.0),
        )


@dataclass(frozen=True, slots=True)
class CompiledBlock:
    """Immutable public metadata for a reusable compiled simulation block."""

    name: str
    signals: tuple[SignalDescriptor, ...]
    inputs: tuple[InputDescriptor, ...]
    nominal_step_s: float
    content_sha256: str
    metadata: tuple[tuple[str, str], ...] = ()
    contract: str = COMPILED_BLOCK_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != COMPILED_BLOCK_CONTRACT:
            raise ValueError(f"Expected compiled block contract {COMPILED_BLOCK_CONTRACT}.")
        object.__setattr__(self, "name", _identifier(self.name, "block name"))
        object.__setattr__(self, "nominal_step_s", _finite(self.nominal_step_s, "nominal step", positive=True))
        if not self.signals:
            raise ValueError("compiled block must expose at least one signal.")
        self._validate_descriptors(self.signals, "signal")
        self._validate_descriptors(self.inputs, "input")
        digest = str(self.content_sha256).lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("content_sha256 must contain 64 lowercase hexadecimal characters.")
        object.__setattr__(self, "content_sha256", digest)
        normalized_metadata = tuple(sorted((str(key), str(value)) for key, value in self.metadata))
        if len({key for key, _ in normalized_metadata}) != len(normalized_metadata):
            raise ValueError("compiled block metadata keys must be unique.")
        object.__setattr__(self, "metadata", normalized_metadata)

    @staticmethod
    def _validate_descriptors(items: Sequence[Any], label: str) -> None:
        ids = [item.id for item in items]
        names = [item.name for item in items]
        if ids != list(range(len(items))):
            raise ValueError(f"{label} ids must be contiguous and declaration ordered from zero.")
        if len(set(names)) != len(names):
            raise ValueError(f"{label} names must be unique.")

    @classmethod
    def build(
        cls,
        name: str,
        signals: Sequence[SignalDescriptor],
        inputs: Sequence[InputDescriptor] = (),
        *,
        nominal_step_s: float,
        metadata: Mapping[str, Any] | None = None,
        implementation_fingerprint: str = "",
    ) -> "CompiledBlock":
        signal_tuple = tuple(signals)
        input_tuple = tuple(inputs)
        metadata_tuple = tuple(sorted((str(key), str(value)) for key, value in (metadata or {}).items()))
        identity = {
            "contract": COMPILED_BLOCK_CONTRACT,
            "name": str(name),
            "signals": [item.to_dict() for item in signal_tuple],
            "inputs": [item.to_dict() for item in input_tuple],
            "nominal_step_s": float(nominal_step_s),
            "metadata": dict(metadata_tuple),
            "implementation_fingerprint": str(implementation_fingerprint),
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        return cls(
            name=name,
            signals=signal_tuple,
            inputs=input_tuple,
            nominal_step_s=nominal_step_s,
            content_sha256=digest,
            metadata=metadata_tuple,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "name": self.name,
            "signals": [item.to_dict() for item in self.signals],
            "inputs": [item.to_dict() for item in self.inputs],
            "nominal_step_s": self.nominal_step_s,
            "content_sha256": self.content_sha256,
            "metadata": dict(self.metadata),
            "capabilities": {"hard_realtime_qualified": False, "execution_class": "soft_realtime"},
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CompiledBlock":
        raw_signals = value.get("signals", ())
        raw_inputs = value.get("inputs", ())
        raw_metadata = value.get("metadata", {})
        if not isinstance(raw_signals, (list, tuple)) or not isinstance(raw_inputs, (list, tuple)):
            raise ValueError("compiled block signals and inputs must be arrays.")
        if not isinstance(raw_metadata, Mapping):
            raise ValueError("compiled block metadata must be an object.")
        return cls(
            contract=value.get("contract", ""),
            name=value.get("name", ""),
            signals=tuple(SignalDescriptor.from_dict(item) for item in raw_signals),
            inputs=tuple(InputDescriptor.from_dict(item) for item in raw_inputs),
            nominal_step_s=value.get("nominal_step_s"),
            content_sha256=value.get("content_sha256", ""),
            metadata=tuple((str(key), str(item)) for key, item in raw_metadata.items()),
        )


@dataclass(frozen=True, slots=True)
class SessionEvent:
    sequence: int
    step_index: int
    simulation_time_s: float
    kind: str
    severity: str
    message: str
    details: tuple[tuple[str, Any], ...] = ()
    contract: str = SESSION_EVENT_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "sequence": self.sequence,
            "step_index": self.step_index,
            "simulation_time_s": self.simulation_time_s,
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class SessionStats:
    steps: int = 0
    measured_compute_ns: int = 0
    maximum_compute_ns: int = 0
    deadline_overruns: int = 0
    consecutive_overruns: int = 0
    maximum_lateness_ns: int = 0
    dropped_events: int = 0
    contract: str = SESSION_STATS_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "steps": self.steps,
            "measured_compute_ns": self.measured_compute_ns,
            "maximum_compute_ns": self.maximum_compute_ns,
            "deadline_overruns": self.deadline_overruns,
            "consecutive_overruns": self.consecutive_overruns,
            "maximum_lateness_ns": self.maximum_lateness_ns,
            "dropped_events": self.dropped_events,
            "hard_realtime_qualified": False,
        }


@dataclass(frozen=True, slots=True)
class SessionCheckpoint:
    block_sha256: str
    simulation_time_s: float
    step_index: int
    lifecycle: str
    inputs: tuple[float, ...]
    signals: tuple[float, ...]
    control_state: Mapping[str, Any] = field(default_factory=dict)
    plant_state: Any = None
    contract: str = SESSION_CHECKPOINT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != SESSION_CHECKPOINT_CONTRACT:
            raise ValueError(f"Expected checkpoint contract {SESSION_CHECKPOINT_CONTRACT}.")
        digest = str(self.block_sha256).lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("checkpoint block_sha256 is invalid.")
        object.__setattr__(self, "block_sha256", digest)
        simulation_time = _finite(self.simulation_time_s, "checkpoint simulation time")
        if simulation_time < 0.0:
            raise ValueError("checkpoint simulation time cannot be negative.")
        object.__setattr__(self, "simulation_time_s", simulation_time)
        if isinstance(self.step_index, bool) or int(self.step_index) != self.step_index or self.step_index < 0:
            raise ValueError("checkpoint step_index must be a non-negative integer.")
        object.__setattr__(self, "step_index", int(self.step_index))
        object.__setattr__(self, "lifecycle", str(self.lifecycle))
        object.__setattr__(self, "inputs", tuple(_finite(item, "checkpoint input") for item in self.inputs))
        object.__setattr__(self, "signals", tuple(_finite(item, "checkpoint signal") for item in self.signals))

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "contract": self.contract,
            "block_sha256": self.block_sha256,
            "simulation_time_s": self.simulation_time_s,
            "step_index": self.step_index,
            "lifecycle": self.lifecycle,
            "inputs": list(self.inputs),
            "signals": list(self.signals),
            "control_state": dict(self.control_state),
            "plant_state": self.plant_state,
        }
        json.dumps(payload, allow_nan=False)
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SessionCheckpoint":
        control_state = value.get("control_state", {})
        if not isinstance(control_state, Mapping):
            raise ValueError("checkpoint control_state must be an object.")
        inputs = value.get("inputs", ())
        signals = value.get("signals", ())
        if not isinstance(inputs, (list, tuple)) or not isinstance(signals, (list, tuple)):
            raise ValueError("checkpoint inputs and signals must be arrays.")
        return cls(
            contract=value.get("contract", ""),
            block_sha256=value.get("block_sha256", ""),
            simulation_time_s=value.get("simulation_time_s"),
            step_index=value.get("step_index", -1),
            lifecycle=value.get("lifecycle", ""),
            inputs=tuple(inputs),
            signals=tuple(signals),
            control_state=dict(control_state),
            plant_state=value.get("plant_state"),
        )


__all__ = [
    "COMPILED_BLOCK_CONTRACT",
    "SESSION_CHECKPOINT_CONTRACT",
    "SESSION_EVENT_CONTRACT",
    "SESSION_STATS_CONTRACT",
    "CompiledBlock",
    "ControlType",
    "InputDescriptor",
    "SessionCheckpoint",
    "SessionEvent",
    "SessionStats",
    "SignalDescriptor",
]
