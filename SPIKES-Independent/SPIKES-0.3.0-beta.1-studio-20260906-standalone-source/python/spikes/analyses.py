"""Bounded executable frequency-domain analyses for the SPIKES CLI.

AC execution deliberately targets the existing linear native-MNA reference
engine.  Transfer function and Fourier outputs are reductions of executable
results; they are not parsers for SPICE ``.tf`` or ``.four`` directives.
"""

from __future__ import annotations

import cmath
import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

try:
    from python.spike_core.native_mna import run_native_mna
except ModuleNotFoundError as exc:
    if exc.name != "python":
        raise
    from spike_core.native_mna import run_native_mna  # type: ignore[no-redef]

from .contracts import CircuitProject, ProbeDescriptor, RESULT_CONTRACT
from .runner import native_request


AC_REQUEST_CONTRACT = "spikes/ac-analysis-request/v1"
AC_RESULT_CONTRACT = "spikes/ac-analysis-result/v1"
TRANSFER_RESULT_CONTRACT = "spikes/transfer-function-result/v1"
FOURIER_RESULT_CONTRACT = "spikes/fourier-reduction-result/v1"

MAX_AC_POINTS = 65_536
MAX_AC_COMPLEX_VALUES = 1_000_000
MAX_FOURIER_SAMPLES = 1_000_001
MAX_FOURIER_HARMONICS = 128
MAX_FOURIER_WORK = 8_000_000
MAX_FOURIER_RESULT_BYTES = 64 * 1024 * 1024


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}.")
    return number


@dataclass(frozen=True, slots=True)
class AcSweep:
    """Explicit bounded sweep independent of unsupported ``.ac`` syntax."""

    start_hz: float
    stop_hz: float
    points: int
    scale: str = "log"
    contract: str = AC_REQUEST_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != AC_REQUEST_CONTRACT:
            raise ValueError(f"Expected AC request contract {AC_REQUEST_CONTRACT}.")
        start = _finite(self.start_hz, "AC start frequency", positive=True)
        stop = _finite(self.stop_hz, "AC stop frequency", positive=True)
        if stop < start:
            raise ValueError("AC stop frequency must not be below the start frequency.")
        if isinstance(self.points, bool) or int(self.points) != self.points:
            raise ValueError("AC point count must be an integer.")
        points = int(self.points)
        if not 1 <= points <= MAX_AC_POINTS:
            raise ValueError(f"AC point count must be between 1 and {MAX_AC_POINTS}.")
        scale = str(self.scale).strip().lower()
        if scale not in {"linear", "log"}:
            raise ValueError("AC scale must be linear or log.")
        object.__setattr__(self, "start_hz", start)
        object.__setattr__(self, "stop_hz", stop)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "scale", scale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "mode": "ac",
            "start_hz": self.start_hz,
            "stop_hz": self.stop_hz,
            "points": self.points,
            "scale": self.scale,
        }


@dataclass(frozen=True, slots=True)
class AcExcitation:
    """One independent source selected as the AC phasor excitation."""

    source: str
    magnitude: float = 1.0
    phase_deg: float = 0.0

    def __post_init__(self) -> None:
        source = str(self.source).strip().upper()
        if not source or not source.rsplit(":", 1)[-1].startswith(("V", "I")):
            raise ValueError("AC source must name an independent V or I source.")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "magnitude", _finite(self.magnitude, "AC magnitude", positive=True))
        object.__setattr__(self, "phase_deg", _finite(self.phase_deg, "AC phase"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "magnitude": self.magnitude,
            "phase_deg": self.phase_deg,
        }


def _complex_values(series: Mapping[str, Any]) -> list[complex]:
    real = series.get("real")
    imaginary = series.get("imaginary")
    if not isinstance(real, Sequence) or isinstance(real, (str, bytes)):
        raise ValueError("Complex series is missing its real array.")
    if not isinstance(imaginary, Sequence) or isinstance(imaginary, (str, bytes)):
        raise ValueError("Complex series is missing its imaginary array.")
    if len(real) != len(imaginary):
        raise ValueError("Complex series arrays have different lengths.")
    return [complex(float(a), float(b)) for a, b in zip(real, imaginary)]


def _complex_series(values: Sequence[complex]) -> dict[str, list[float]]:
    return {
        "real": [float(value.real) for value in values],
        "imaginary": [float(value.imag) for value in values],
        "magnitude": [float(abs(value)) for value in values],
        "phase_deg": [float(math.degrees(cmath.phase(value))) for value in values],
    }


def _probe_series(probe: ProbeDescriptor, data: Mapping[str, Any], count: int) -> dict[str, list[float]]:
    if probe.quantity == "node_voltage":
        raw_nodes = data.get("node_voltage_v")
        if not isinstance(raw_nodes, Mapping):
            raise ValueError("AC result is missing node voltages.")

        def voltage(node: str) -> list[complex]:
            if node == "0":
                return [0j] * count
            raw = raw_nodes.get(node)
            if not isinstance(raw, Mapping):
                raise ValueError(f"AC result is missing node {node}.")
            return _complex_values(raw)

        values = voltage(probe.targets[0])
        if len(probe.targets) == 2:
            negative = voltage(probe.targets[1])
            values = [positive - reference for positive, reference in zip(values, negative)]
    else:
        key = "element_current_a" if probe.quantity == "element_current" else "element_complex_power_va"
        raw_elements = data.get(key)
        raw = raw_elements.get(probe.targets[0]) if isinstance(raw_elements, Mapping) else None
        if not isinstance(raw, Mapping):
            raise ValueError(f"AC result is missing {probe.targets[0]} {probe.quantity}.")
        values = _complex_values(raw)
    if len(values) != count:
        raise ValueError("AC probe series length does not match the frequency axis.")
    return _complex_series(values)


def _blocked_ac(project: CircuitProject, sweep: AcSweep, excitation: AcExcitation, native: Mapping[str, Any]) -> dict[str, Any]:
    validation = native.get("validation", {})
    issues = list(native.get("issues", ()))
    if not issues and isinstance(validation, Mapping):
        issues = list(validation.get("issues", ()))
    return {
        "contract": AC_RESULT_CONTRACT,
        "status": str(native.get("status", "failed")),
        "model_status": str(native.get("model_status", "unsupported")),
        "analysis": {**sweep.to_dict(), "excitation": excitation.to_dict()},
        "data": {},
        "probes": {},
        "diagnostics": dict(native.get("diagnostics", {})),
        "issues": issues,
        "provenance": {
            "adapter": "python.spikes.analyses",
            "source_sha256": project.source_sha256,
            "owned_cpp_ac": False,
        },
    }


def run_ac_analysis(project: CircuitProject, sweep: AcSweep, excitation: AcExcitation) -> dict[str, Any]:
    """Execute a linear phasor sweep with one explicitly selected source."""

    unsupported = [element.name for element in project.elements if element.kind not in {
        "resistor", "capacitor", "inductor", "voltage_source", "current_source",
        "vcvs", "vccs", "cccs", "ccvs",
    }]
    if unsupported:
        raise ValueError(f"AC analysis currently supports only linear R/L/C and independent/dependent sources; unsupported: {', '.join(unsupported)}.")
    if any(element.waveform is not None for element in project.elements):
        raise ValueError("AC analysis requires constant independent sources in this slice.")
    nodes = {
        node
        for element in project.elements
        for node in (element.positive_node, element.negative_node)
        if node != "0"
    }
    branch_count = sum(
        element.kind in {"inductor", "voltage_source", "vcvs", "ccvs"}
        for element in project.elements
    )
    series_count = len(nodes) + branch_count + 2 * len(project.elements) + len(project.probes)
    if sweep.points * series_count > MAX_AC_COMPLEX_VALUES:
        raise ValueError(
            f"AC output would exceed {MAX_AC_COMPLEX_VALUES} complex series values; reduce points or circuit size."
        )
    sources = {element.name: element for element in project.elements if element.kind in {"voltage_source", "current_source"}}
    if excitation.source not in sources:
        raise ValueError(f"AC source {excitation.source} does not exist or is not independent.")

    request = copy.deepcopy(native_request(project))
    request["request_id"] = f"spikes-ac-{project.source_sha256[:16] or 'memory'}"
    request["analysis"] = {
        "mode": "ac",
        "start_hz": sweep.start_hz,
        "stop_hz": sweep.stop_hz,
        "points": sweep.points,
        "scale": sweep.scale,
    }
    for element in request["elements"]:
        if element["type"] in {"voltage_source", "current_source"}:
            selected = str(element["id"]).upper() == excitation.source
            element["ac_magnitude"] = excitation.magnitude if selected else 0.0
            element["ac_phase_deg"] = excitation.phase_deg if selected else 0.0

    native = run_native_mna(request)
    if native.get("status") != "completed":
        return _blocked_ac(project, sweep, excitation, native)
    data = dict(native["data"])
    frequency = list(data.get("frequency_hz", ()))
    probes = {
        probe.name: {
            "descriptor": probe.to_dict(),
            "values": _probe_series(probe, data, len(frequency)),
            **({"ac_unit": "VA"} if probe.quantity == "element_power" else {}),
        }
        for probe in project.probes
    }
    return {
        "contract": AC_RESULT_CONTRACT,
        "status": "completed",
        "model_status": str(native.get("model_status", "experimental")),
        "analysis": {**sweep.to_dict(), "excitation": excitation.to_dict()},
        "data": data,
        "probes": probes,
        "diagnostics": dict(native.get("diagnostics", {})),
        "issues": list(native.get("issues", ())),
        "provenance": {
            "adapter": "python.spikes.analyses",
            "source_sha256": project.source_sha256,
            "ac_engine": {
                "implementation": "python.spike_core.native_mna",
                "formulation": "linear_complex_modified_nodal_analysis",
                "owned_cpp_ac": False,
                "nonlinear_bias_linearization": False,
            },
            "native": dict(native.get("provenance", {})),
        },
    }


def run_transfer_function(
    project: CircuitProject,
    sweep: AcSweep,
    excitation: AcExcitation,
    output_probe: ProbeDescriptor,
) -> dict[str, Any]:
    """Execute AC and divide one output phasor by the selected source phasor."""

    if output_probe.quantity == "element_power":
        raise ValueError("Transfer output must be a voltage or current probe; complex power is not linear in excitation amplitude.")
    if output_probe.name not in {probe.name for probe in project.probes}:
        raise ValueError("Transfer output probe must be present in the circuit project.")
    ac = run_ac_analysis(project, sweep, excitation)
    if ac["status"] != "completed":
        return {**ac, "contract": TRANSFER_RESULT_CONTRACT}
    raw_output = ac["probes"][output_probe.name]["values"]
    output = _complex_values(raw_output)
    input_phasor = cmath.rect(excitation.magnitude, math.radians(excitation.phase_deg))
    transfer = [value / input_phasor for value in output]
    input_unit = "V" if excitation.source.rsplit(":", 1)[-1].startswith("V") else "A"
    output_unit = "VA" if output_probe.quantity == "element_power" else output_probe.unit
    return {
        "contract": TRANSFER_RESULT_CONTRACT,
        "status": "completed",
        "model_status": ac["model_status"],
        "analysis": ac["analysis"],
        "output_probe": output_probe.to_dict(),
        "data": {
            "frequency_hz": ac["data"]["frequency_hz"],
            "transfer": _complex_series(transfer),
            "unit": f"{output_unit}/{input_unit}",
        },
        "diagnostics": ac["diagnostics"],
        "issues": ac["issues"],
        "provenance": {
            **ac["provenance"],
            "reduction": "output_phasor_divided_by_selected_source_phasor",
        },
    }


def reduce_fourier_result(
    transient_result: Mapping[str, Any],
    probe_name: str,
    fundamental_hz: float,
    harmonics: int,
) -> dict[str, Any]:
    """Reduce a completed uniform transient probe over integral full cycles."""

    fundamental = _finite(fundamental_hz, "Fourier fundamental", positive=True)
    if isinstance(harmonics, bool) or int(harmonics) != harmonics:
        raise ValueError("Fourier harmonic count must be an integer.")
    harmonic_count = int(harmonics)
    if not 1 <= harmonic_count <= MAX_FOURIER_HARMONICS:
        raise ValueError(f"Fourier harmonic count must be between 1 and {MAX_FOURIER_HARMONICS}.")
    if transient_result.get("contract") != RESULT_CONTRACT or transient_result.get("status") != "completed":
        raise ValueError("Fourier input must be a completed SPIKES circuit result.")
    analysis = transient_result.get("analysis")
    if not isinstance(analysis, Mapping) or analysis.get("mode") != "transient":
        raise ValueError("Fourier input must contain transient analysis data.")
    data = transient_result.get("data")
    probes = transient_result.get("probes")
    if not isinstance(data, Mapping) or not isinstance(probes, Mapping):
        raise ValueError("Fourier input is missing transient data or probes.")
    times = data.get("time_s")
    probe = probes.get(str(probe_name))
    samples = probe.get("values") if isinstance(probe, Mapping) else None
    if not isinstance(times, Sequence) or isinstance(times, (str, bytes)):
        raise ValueError("Fourier input is missing its time axis.")
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise ValueError(f"Fourier input is missing probe {probe_name}.")
    if len(times) != len(samples) or not 3 <= len(times) <= MAX_FOURIER_SAMPLES:
        raise ValueError(f"Fourier time and sample arrays must match and contain 3 to {MAX_FOURIER_SAMPLES} points.")
    numeric_times = [_finite(value, "Fourier time") for value in times]
    numeric_samples = [_finite(value, "Fourier sample") for value in samples]
    step = numeric_times[1] - numeric_times[0]
    if step <= 0.0:
        raise ValueError("Fourier time axis must be strictly increasing.")
    time_scale = max(abs(numeric_times[0]), abs(numeric_times[-1]), abs(step), 1.0e-300)
    tolerance = max(abs(step) * 1.0e-9, math.ulp(time_scale) * 16.0)
    deltas = [numeric_times[index] - numeric_times[index - 1] for index in range(2, len(numeric_times))]
    if any(delta <= 0.0 or abs(delta - step) > tolerance for delta in deltas):
        raise ValueError("Fourier reduction requires a uniform time axis.")
    cycles = (numeric_times[-1] - numeric_times[0]) * fundamental
    rounded_cycles = round(cycles)
    if rounded_cycles < 1 or abs(cycles - rounded_cycles) > 1e-7 * max(1.0, cycles):
        raise ValueError("Fourier capture must span an integral positive number of fundamental cycles.")
    interval_count = len(numeric_samples) - 1
    if interval_count * harmonic_count > MAX_FOURIER_WORK:
        raise ValueError(f"Fourier sample-by-harmonic work must not exceed {MAX_FOURIER_WORK}.")
    sample_rate = 1.0 / step
    if harmonic_count * fundamental > sample_rate / 2.0 * (1.0 + 1e-12):
        raise ValueError("Requested Fourier harmonic exceeds the Nyquist frequency.")

    selected = numeric_samples[:-1]  # final sample duplicates the start phase
    dc = math.fsum(selected) / interval_count
    components: list[dict[str, float | int]] = []
    amplitudes: list[float] = []
    for order in range(1, harmonic_count + 1):
        angular_step = 2.0 * math.pi * order * fundamental * step
        coefficient = (2.0 / interval_count) * sum(
            value * cmath.exp(-1j * angular_step * index)
            for index, value in enumerate(selected)
        )
        amplitude = float(abs(coefficient))
        amplitudes.append(amplitude)
        components.append({
            "order": order,
            "frequency_hz": order * fundamental,
            "real": float(coefficient.real),
            "imaginary": float(coefficient.imag),
            "amplitude": amplitude,
            "phase_deg": float(math.degrees(cmath.phase(coefficient))),
        })
    thd = None if amplitudes[0] == 0.0 else math.sqrt(math.fsum(value * value for value in amplitudes[1:])) / amplitudes[0]
    canonical = json.dumps(transient_result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {
        "contract": FOURIER_RESULT_CONTRACT,
        "status": "completed",
        "source": {
            "contract": RESULT_CONTRACT,
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "probe": str(probe_name),
        },
        "analysis": {
            "fundamental_hz": fundamental,
            "harmonics": harmonic_count,
            "cycles": int(rounded_cycles),
            "sample_count": interval_count,
            "sample_rate_hz": sample_rate,
        },
        "data": {"dc": dc, "components": components, "thd": thd},
        "issues": [],
        "provenance": {
            "implementation": "python.spikes.analyses.direct_uniform_dft",
            "endpoint_policy": "exclude_repeated_final_phase_sample",
            "requires_integral_cycles": True,
        },
    }


__all__ = [
    "AC_REQUEST_CONTRACT",
    "AC_RESULT_CONTRACT",
    "FOURIER_RESULT_CONTRACT",
    "TRANSFER_RESULT_CONTRACT",
    "AcExcitation",
    "AcSweep",
    "reduce_fourier_result",
    "run_ac_analysis",
    "run_transfer_function",
]
