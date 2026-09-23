"""Bounded, versioned data contracts for SPIKES virtual instruments.

The reference instruments only make physical measurements from acquisitions
whose scale and timebase have explicit, verified calibration provenance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


CALIBRATION_CONTRACT = "spikes/instrument-calibration/v1"
WAVEFORM_CONTRACT = "spikes/sampled-waveform/v1"
FREQUENCY_RESPONSE_CONTRACT = "spikes/frequency-response/v1"
SCOPE_CAPTURE_CONTRACT = "spikes/scope-capture/v1"
SPECTRUM_TRACE_CONTRACT = "spikes/spectrum-trace/v1"
MEASUREMENT_CONTRACT = "spikes/instrument-measurement/v1"
SMITH_POINT_CONTRACT = "spikes/smith-point/v1"

MAX_WAVEFORM_SAMPLES = 1_048_576
MAX_RESPONSE_POINTS = 65_536
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]*$", re.ASCII)


def finite(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}.")
    return result


def finite_complex(value: Any, label: str) -> complex:
    try:
        result = complex(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be complex numeric.") from exc
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{label} must have finite real and imaginary parts.")
    return result


def _identifier(value: Any, label: str) -> str:
    normalized = str(value).strip()
    if _IDENTIFIER_RE.fullmatch(normalized) is None:
        raise ValueError(f"{label} must be a stable identifier.")
    return normalized


def _unit(value: Any) -> str:
    unit = str(value).strip()
    if not unit or len(unit) > 32 or any(ord(character) < 32 for character in unit):
        raise ValueError("A non-empty SI unit symbol is required.")
    return unit


class AcquisitionStatus(str, Enum):
    VALID = "valid"
    CLIPPED = "clipped"
    OVERRANGE = "overrange"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class CalibrationState(str, Enum):
    VERIFIED = "verified"
    UNCALIBRATED = "uncalibrated"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class CalibrationRecord:
    calibration_id: str
    source: str
    state: CalibrationState
    scale_verified: bool
    timebase_verified: bool
    uncertainty_fraction: float = 0.0
    notes: str = ""
    contract: str = CALIBRATION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != CALIBRATION_CONTRACT:
            raise ValueError(f"Expected calibration contract {CALIBRATION_CONTRACT}.")
        object.__setattr__(self, "calibration_id", _identifier(self.calibration_id, "calibration id"))
        if not str(self.source).strip():
            raise ValueError("Calibration source/provenance is required.")
        try:
            state = CalibrationState(self.state)
        except ValueError as exc:
            raise ValueError("Unsupported calibration state.") from exc
        object.__setattr__(self, "state", state)
        if not isinstance(self.scale_verified, bool) or not isinstance(self.timebase_verified, bool):
            raise ValueError("Calibration verification flags must be boolean.")
        uncertainty = finite(self.uncertainty_fraction, "calibration uncertainty")
        if not 0.0 <= uncertainty <= 1.0:
            raise ValueError("Calibration uncertainty must be between zero and one.")
        object.__setattr__(self, "uncertainty_fraction", uncertainty)

    def require_physical_claim(self, *, timebase: bool = False) -> None:
        if self.state is not CalibrationState.VERIFIED or not self.scale_verified:
            raise ValueError("Physical measurement requires verified scale calibration.")
        if timebase and not self.timebase_verified:
            raise ValueError("This measurement requires verified timebase calibration.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "calibration_id": self.calibration_id,
            "source": self.source,
            "state": self.state.value,
            "scale_verified": self.scale_verified,
            "timebase_verified": self.timebase_verified,
            "uncertainty_fraction": self.uncertainty_fraction,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class SampledWaveform:
    channel: str
    unit: str
    sample_rate_hz: float
    samples: tuple[float, ...]
    calibration: CalibrationRecord
    provenance: tuple[str, ...]
    status: AcquisitionStatus = AcquisitionStatus.VALID
    t0_s: float = 0.0
    contract: str = WAVEFORM_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != WAVEFORM_CONTRACT:
            raise ValueError(f"Expected waveform contract {WAVEFORM_CONTRACT}.")
        object.__setattr__(self, "channel", _identifier(self.channel, "channel"))
        object.__setattr__(self, "unit", _unit(self.unit))
        object.__setattr__(self, "sample_rate_hz", finite(self.sample_rate_hz, "sample rate", positive=True))
        object.__setattr__(self, "t0_s", finite(self.t0_s, "waveform start time"))
        values = tuple(finite(item, f"sample {index}") for index, item in enumerate(self.samples))
        if not values or len(values) > MAX_WAVEFORM_SAMPLES:
            raise ValueError(f"Waveform must contain 1..{MAX_WAVEFORM_SAMPLES} samples.")
        object.__setattr__(self, "samples", values)
        if not isinstance(self.calibration, CalibrationRecord):
            raise ValueError("Waveform requires a CalibrationRecord.")
        provenance = tuple(str(item).strip() for item in self.provenance)
        if not provenance or any(not item for item in provenance):
            raise ValueError("Waveform provenance must contain non-empty references.")
        object.__setattr__(self, "provenance", provenance)
        try:
            object.__setattr__(self, "status", AcquisitionStatus(self.status))
        except ValueError as exc:
            raise ValueError("Unsupported waveform acquisition status.") from exc

    def require_valid(self, *, timebase: bool = False) -> None:
        if self.status is not AcquisitionStatus.VALID:
            raise ValueError(f"Physical measurement rejected acquisition status {self.status.value}.")
        self.calibration.require_physical_claim(timebase=timebase)

    @property
    def sample_interval_s(self) -> float:
        """Exact nominal interval; acquisitions never consult a wall clock."""

        return 1.0 / self.sample_rate_hz

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "channel": self.channel,
            "unit": self.unit,
            "sample_rate_hz": self.sample_rate_hz,
            "sample_interval_s": self.sample_interval_s,
            "t0_s": self.t0_s,
            "samples": list(self.samples),
            "calibration": self.calibration.to_dict(),
            "provenance": list(self.provenance),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class FrequencyResponse:
    name: str
    quantity: str
    unit: str
    frequency_hz: tuple[float, ...]
    values: tuple[complex, ...]
    reference_impedance_ohm: float
    calibration: CalibrationRecord
    provenance: tuple[str, ...]
    status: AcquisitionStatus = AcquisitionStatus.VALID
    contract: str = FREQUENCY_RESPONSE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != FREQUENCY_RESPONSE_CONTRACT:
            raise ValueError(f"Expected response contract {FREQUENCY_RESPONSE_CONTRACT}.")
        object.__setattr__(self, "name", _identifier(self.name, "response name"))
        quantity = str(self.quantity).upper().strip()
        if quantity not in {"S11", "Z", "Y", "TRANSFER"}:
            raise ValueError("Response quantity must be S11, Z, Y, or TRANSFER.")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "unit", _unit(self.unit))
        expected_units = {"S11": "1", "Z": "ohm", "Y": "S"}
        if quantity in expected_units and self.unit != expected_units[quantity]:
            raise ValueError(f"{quantity} responses require unit {expected_units[quantity]}.")
        frequencies = tuple(finite(item, f"frequency {index}", positive=True) for index, item in enumerate(self.frequency_hz))
        values = tuple(finite_complex(item, f"response value {index}") for index, item in enumerate(self.values))
        if not frequencies or len(frequencies) != len(values) or len(values) > MAX_RESPONSE_POINTS:
            raise ValueError(f"Frequency response requires 1..{MAX_RESPONSE_POINTS} matched points.")
        if any(right <= left for left, right in zip(frequencies, frequencies[1:])):
            raise ValueError("Frequencies must be strictly increasing.")
        object.__setattr__(self, "frequency_hz", frequencies)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "reference_impedance_ohm", finite(self.reference_impedance_ohm, "reference impedance", positive=True))
        if not isinstance(self.calibration, CalibrationRecord):
            raise ValueError("Frequency response requires a CalibrationRecord.")
        provenance = tuple(str(item).strip() for item in self.provenance)
        if not provenance or any(not item for item in provenance):
            raise ValueError("Response provenance must contain non-empty references.")
        object.__setattr__(self, "provenance", provenance)
        try:
            object.__setattr__(self, "status", AcquisitionStatus(self.status))
        except ValueError as exc:
            raise ValueError("Unsupported response acquisition status.") from exc

    def require_valid(self) -> None:
        if self.status is not AcquisitionStatus.VALID:
            raise ValueError(f"Physical measurement rejected acquisition status {self.status.value}.")
        self.calibration.require_physical_claim(timebase=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "name": self.name,
            "quantity": self.quantity,
            "unit": self.unit,
            "frequency_hz": list(self.frequency_hz),
            "values": [{"real": item.real, "imag": item.imag} for item in self.values],
            "reference_impedance_ohm": self.reference_impedance_ohm,
            "calibration": self.calibration.to_dict(),
            "provenance": list(self.provenance),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class ScopeCapture:
    waveform: SampledWaveform
    trigger_index: int
    trigger_time_s: float
    pretrigger_samples: int
    contract: str = SCOPE_CAPTURE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != SCOPE_CAPTURE_CONTRACT:
            raise ValueError(f"Expected scope capture contract {SCOPE_CAPTURE_CONTRACT}.")
        if not isinstance(self.waveform, SampledWaveform):
            raise ValueError("Scope capture requires a SampledWaveform.")
        if not 0 <= self.trigger_index < len(self.waveform.samples):
            raise ValueError("Trigger index is outside the captured waveform.")
        if not 0 <= self.pretrigger_samples <= self.trigger_index:
            raise ValueError("Pretrigger sample count is invalid.")
        object.__setattr__(self, "trigger_time_s", finite(self.trigger_time_s, "trigger time"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "waveform": self.waveform.to_dict(),
            "trigger_index": self.trigger_index,
            "trigger_time_s": self.trigger_time_s,
            "pretrigger_samples": self.pretrigger_samples,
        }


@dataclass(frozen=True, slots=True)
class SpectrumTrace:
    source_channel: str
    amplitude_unit: str
    frequency_hz: tuple[float, ...]
    complex_amplitude: tuple[complex, ...]
    window: str
    sample_count: int
    provenance: tuple[str, ...]
    contract: str = SPECTRUM_TRACE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != SPECTRUM_TRACE_CONTRACT:
            raise ValueError(f"Expected spectrum contract {SPECTRUM_TRACE_CONTRACT}.")
        object.__setattr__(self, "source_channel", _identifier(self.source_channel, "source channel"))
        object.__setattr__(self, "amplitude_unit", _unit(self.amplitude_unit))
        window = str(self.window).lower().strip()
        if window not in {"rect", "rectangular", "none", "hann", "hamming", "blackman"}:
            raise ValueError("Spectrum window is unsupported.")
        object.__setattr__(self, "window", window)
        if not self.frequency_hz or len(self.frequency_hz) != len(self.complex_amplitude):
            raise ValueError("Spectrum axes must be non-empty and matched.")
        frequencies = tuple(finite(item, f"spectrum frequency {index}") for index, item in enumerate(self.frequency_hz))
        values = tuple(finite_complex(item, f"spectrum bin {index}") for index, item in enumerate(self.complex_amplitude))
        if any(right <= left for left, right in zip(frequencies, frequencies[1:])):
            raise ValueError("Spectrum frequencies must be strictly increasing.")
        object.__setattr__(self, "frequency_hz", frequencies)
        object.__setattr__(self, "complex_amplitude", values)
        if isinstance(self.sample_count, bool) or int(self.sample_count) != self.sample_count:
            raise ValueError("Spectrum sample count must be an integer.")
        object.__setattr__(self, "sample_count", int(self.sample_count))
        if self.sample_count < 2 or self.sample_count > MAX_WAVEFORM_SAMPLES:
            raise ValueError("Spectrum sample count is invalid.")
        provenance = tuple(str(item).strip() for item in self.provenance)
        if not provenance or any(not item for item in provenance):
            raise ValueError("Spectrum provenance is required.")
        object.__setattr__(self, "provenance", provenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "source_channel": self.source_channel,
            "amplitude_unit": self.amplitude_unit,
            "frequency_hz": list(self.frequency_hz),
            "complex_amplitude": [
                {"real": item.real, "imag": item.imag} for item in self.complex_amplitude
            ],
            "window": self.window,
            "sample_count": self.sample_count,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True, slots=True)
class Measurement:
    kind: str
    value: float
    unit: str
    source: str
    uncertainty_fraction: float
    provenance: tuple[str, ...]
    contract: str = MEASUREMENT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != MEASUREMENT_CONTRACT:
            raise ValueError(f"Expected measurement contract {MEASUREMENT_CONTRACT}.")
        object.__setattr__(self, "kind", _identifier(self.kind, "measurement kind"))
        object.__setattr__(self, "source", _identifier(self.source, "measurement source"))
        object.__setattr__(self, "unit", _unit(self.unit))
        object.__setattr__(self, "value", finite(self.value, "measurement value"))
        uncertainty = finite(self.uncertainty_fraction, "measurement uncertainty")
        if not 0.0 <= uncertainty <= 1.0:
            raise ValueError("Measurement uncertainty must be between zero and one.")
        object.__setattr__(self, "uncertainty_fraction", uncertainty)
        provenance = tuple(str(item).strip() for item in self.provenance)
        if not provenance or any(not item for item in provenance):
            raise ValueError("Measurement provenance is required.")
        object.__setattr__(self, "provenance", provenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "kind": self.kind,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "uncertainty_fraction": self.uncertainty_fraction,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True, slots=True)
class SmithPoint:
    frequency_hz: float
    reflection: complex
    normalized_resistance: float
    normalized_reactance: float
    contract: str = SMITH_POINT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != SMITH_POINT_CONTRACT:
            raise ValueError(f"Expected Smith point contract {SMITH_POINT_CONTRACT}.")
        object.__setattr__(self, "frequency_hz", finite(self.frequency_hz, "frequency", positive=True))
        object.__setattr__(self, "reflection", finite_complex(self.reflection, "reflection"))
        object.__setattr__(self, "normalized_resistance", finite(self.normalized_resistance, "normalized resistance"))
        object.__setattr__(self, "normalized_reactance", finite(self.normalized_reactance, "normalized reactance"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "frequency_hz": self.frequency_hz,
            "reflection": {"real": self.reflection.real, "imag": self.reflection.imag},
            "smith_x": self.reflection.real,
            "smith_y": self.reflection.imag,
            "normalized_resistance": self.normalized_resistance,
            "normalized_reactance": self.normalized_reactance,
        }
