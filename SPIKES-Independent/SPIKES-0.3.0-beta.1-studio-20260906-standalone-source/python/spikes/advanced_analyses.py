"""Executable, bounded linear noise, sensitivity, and pole-zero analyses.

These routines intentionally share the validated linear MNA formulation used by
``spikes.analyses``.  They do not claim semiconductor noise, nonlinear bias
linearization, Volterra distortion, or full SPICE3 analysis compatibility.
"""

from __future__ import annotations

import copy
import math
from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.linalg import eig

try:
    from python.spike_core.native_mna import _assemble, run_native_mna
except ModuleNotFoundError as exc:
    if exc.name != "python":
        raise
    from spike_core.native_mna import _assemble, run_native_mna  # type: ignore[no-redef]

from .analyses import AcExcitation, AcSweep, run_ac_analysis
from .contracts import CircuitProject, ProbeDescriptor
from .runner import native_request


NOISE_RESULT_CONTRACT = "spikes/linear-noise-result/v1"
SENSITIVITY_RESULT_CONTRACT = "spikes/ac-sensitivity-result/v1"
POLE_ZERO_RESULT_CONTRACT = "spikes/pole-zero-result/v1"

BOLTZMANN_J_K = 1.380649e-23
MAX_NOISE_SOURCE_POINTS = 2_000_000
MAX_SENSITIVITY_SOLVES = 512
MAX_POLE_ZERO_UNKNOWNS = 2048


def _require_linear(project: CircuitProject) -> None:
    unsupported = [
        element.name for element in project.elements
        if element.kind not in {
            "resistor", "capacitor", "inductor", "voltage_source", "current_source",
            "vcvs", "vccs", "cccs", "ccvs",
        }
    ]
    if unsupported:
        raise ValueError(
            "This analysis requires the linear R/L/C/source subset; unsupported: "
            + ", ".join(unsupported)
        )


def _complex_values(series: Mapping[str, Any]) -> list[complex]:
    real, imaginary = series.get("real"), series.get("imaginary")
    if not isinstance(real, Sequence) or not isinstance(imaginary, Sequence):
        raise ValueError("Expected a complex series with real and imaginary arrays.")
    if len(real) != len(imaginary):
        raise ValueError("Complex series arrays have different lengths.")
    return [complex(float(a), float(b)) for a, b in zip(real, imaginary)]


def _complex_series(values: Sequence[complex]) -> dict[str, list[float]]:
    return {
        "real": [float(value.real) for value in values],
        "imaginary": [float(value.imag) for value in values],
        "magnitude": [float(abs(value)) for value in values],
        "phase_deg": [float(math.degrees(math.atan2(value.imag, value.real))) for value in values],
    }


def _probe_voltage(data: Mapping[str, Any], probe: ProbeDescriptor) -> list[complex]:
    if probe.quantity != "node_voltage":
        raise ValueError("This bounded analysis currently requires a node-voltage output probe.")
    raw_nodes = data.get("node_voltage_v")
    if not isinstance(raw_nodes, Mapping):
        raise ValueError("MNA output is missing node voltages.")

    def values(node: str) -> list[complex]:
        if node == "0":
            first = next(iter(raw_nodes.values()), {"real": []})
            count = len(first.get("real", ())) if isinstance(first, Mapping) else 0
            return [0j] * count
        raw = raw_nodes.get(node)
        if not isinstance(raw, Mapping):
            raise ValueError(f"MNA output is missing node {node}.")
        return _complex_values(raw)

    positive = values(probe.targets[0])
    if len(probe.targets) == 1:
        return positive
    negative = values(probe.targets[1])
    return [left - right for left, right in zip(positive, negative)]


def run_linear_noise_analysis(
    project: CircuitProject,
    sweep: AcSweep,
    output_probe: ProbeDescriptor,
    *,
    temperature_k: float = 300.15,
) -> dict[str, Any]:
    """Compute uncorrelated resistor Johnson noise at one voltage output.

    Each resistor is represented by its Norton density ``sqrt(4 k T / R)`` and
    propagated through the exact linear AC MNA system.  PSDs, not amplitudes,
    are summed.
    """

    _require_linear(project)
    temperature = float(temperature_k)
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("Noise temperature must be finite and positive.")
    resistors = [element for element in project.elements if element.kind == "resistor"]
    if not resistors:
        raise ValueError("Linear noise analysis requires at least one resistor.")
    if sweep.points * len(resistors) > MAX_NOISE_SOURCE_POINTS:
        raise ValueError(f"Noise source-by-frequency work exceeds {MAX_NOISE_SOURCE_POINTS}.")
    if output_probe.quantity != "node_voltage":
        raise ValueError("Linear noise output must be a node-voltage probe.")

    base = native_request(project)
    base["analysis"] = {
        "mode": "ac", "start_hz": sweep.start_hz, "stop_hz": sweep.stop_hz,
        "points": sweep.points, "scale": sweep.scale,
    }
    for element in base["elements"]:
        if element["type"] in {"voltage_source", "current_source"}:
            element["ac_magnitude"] = 0.0
            element["ac_phase_deg"] = 0.0

    total_psd = np.zeros(sweep.points, dtype=float)
    contributions: dict[str, dict[str, list[float]]] = {}
    frequencies: list[float] | None = None
    for resistor in resistors:
        request = copy.deepcopy(base)
        density = math.sqrt(4.0 * BOLTZMANN_J_K * temperature / resistor.value)
        request["elements"].append({
            "id": f"__NOISE_{resistor.name}", "type": "current_source",
            "positive_node": resistor.positive_node, "negative_node": resistor.negative_node,
            "dc_value": 0.0, "ac_magnitude": density, "ac_phase_deg": 0.0,
        })
        result = run_native_mna(request)
        if result.get("status") != "completed":
            raise ValueError(f"Noise solve for {resistor.name} failed validation or convergence.")
        if frequencies is None:
            frequencies = [float(value) for value in result["data"]["frequency_hz"]]
        output = _probe_voltage(result["data"], output_probe)
        psd = np.asarray([abs(value) ** 2 for value in output], dtype=float)
        total_psd += psd
        contributions[resistor.name] = {"output_psd_v2_hz": psd.tolist()}

    assert frequencies is not None
    frequency_array = np.asarray(frequencies, dtype=float)
    cumulative = np.zeros_like(total_psd)
    if len(total_psd) > 1:
        cumulative[1:] = np.cumsum(
            0.5 * (total_psd[1:] + total_psd[:-1]) * np.diff(frequency_array)
        )
    return {
        "contract": NOISE_RESULT_CONTRACT,
        "status": "completed",
        "model_status": "qualified_linear_thermal_noise",
        "analysis": {**sweep.to_dict(), "temperature_k": temperature},
        "output_probe": output_probe.to_dict(),
        "data": {
            "frequency_hz": frequencies,
            "output_noise_psd_v2_hz": total_psd.tolist(),
            "output_noise_density_v_sqrt_hz": np.sqrt(total_psd).tolist(),
            "cumulative_output_noise_v_rms": np.sqrt(cumulative).tolist(),
            "integrated_output_noise_v_rms": float(math.sqrt(cumulative[-1])),
            "contributions": contributions,
        },
        "issues": [],
        "provenance": {
            "implementation": "python.spikes.advanced_analyses.linear_resistor_noise",
            "source_model": "uncorrelated_resistor_johnson_nyquist_norton",
            "boltzmann_constant_j_k": BOLTZMANN_J_K,
            "omissions": [
                "semiconductor shot and flicker noise", "correlated noise",
                "device noise parameters", "nonlinear operating-point linearization",
            ],
        },
    }


def run_ac_sensitivity(
    project: CircuitProject,
    sweep: AcSweep,
    excitation: AcExcitation,
    output_probe: ProbeDescriptor,
    element_names: Iterable[str],
    *,
    relative_step: float = 1.0e-5,
) -> dict[str, Any]:
    """Central-difference complex AC sensitivity to positive R/L/C values."""

    _require_linear(project)
    step = float(relative_step)
    if not math.isfinite(step) or not 1.0e-8 <= step <= 1.0e-2:
        raise ValueError("Sensitivity relative_step must be from 1e-8 to 1e-2.")
    requested = tuple(str(name).strip().upper() for name in element_names)
    if not requested or len(requested) > MAX_SENSITIVITY_SOLVES // 2:
        raise ValueError("Sensitivity requires 1 to 256 unique element names.")
    if len(set(requested)) != len(requested):
        raise ValueError("Sensitivity element names must be unique.")
    by_name = {element.name: element for element in project.elements}
    invalid = [name for name in requested if name not in by_name or by_name[name].kind not in {"resistor", "capacitor", "inductor"}]
    if invalid:
        raise ValueError("Sensitivity supports existing R/L/C elements only: " + ", ".join(invalid))

    baseline = run_ac_analysis(project, sweep, excitation)
    if baseline.get("status") != "completed":
        raise ValueError("Baseline AC sensitivity solve did not complete.")
    if output_probe.name not in baseline["probes"]:
        raise ValueError("Sensitivity output probe must be present in the project.")
    base_values = _complex_values(baseline["probes"][output_probe.name]["values"])
    results: dict[str, Any] = {}
    for name in requested:
        nominal = by_name[name].value
        delta = nominal * step

        def perturbed(value: float) -> CircuitProject:
            return replace(project, elements=tuple(
                replace(element, value=value) if element.name == name else element
                for element in project.elements
            ))

        plus = run_ac_analysis(perturbed(nominal + delta), sweep, excitation)
        minus = run_ac_analysis(perturbed(nominal - delta), sweep, excitation)
        if plus.get("status") != "completed" or minus.get("status") != "completed":
            raise ValueError(f"Sensitivity perturbation solve failed for {name}.")
        plus_values = _complex_values(plus["probes"][output_probe.name]["values"])
        minus_values = _complex_values(minus["probes"][output_probe.name]["values"])
        derivative = [(high - low) / (2.0 * delta) for high, low in zip(plus_values, minus_values)]
        if any(abs(base_value) <= 1.0e-300 for base_value in base_values):
            raise ValueError(
                "Normalized logarithmic sensitivity is undefined where the baseline output is zero."
            )
        normalized = [
            nominal * derivative_value / base_value
            for derivative_value, base_value in zip(derivative, base_values)
        ]
        results[name] = {
            "nominal_value": nominal,
            "absolute_derivative": _complex_series(derivative),
            "normalized_log_sensitivity": _complex_series(normalized),
        }
    return {
        "contract": SENSITIVITY_RESULT_CONTRACT,
        "status": "completed",
        "model_status": "qualified_linear_central_difference",
        "analysis": baseline["analysis"],
        "output_probe": output_probe.to_dict(),
        "data": {
            "frequency_hz": baseline["data"]["frequency_hz"],
            "baseline": _complex_series(base_values),
            "elements": results,
        },
        "issues": [],
        "provenance": {
            "implementation": "python.spikes.advanced_analyses.central_difference_ac",
            "relative_step": step,
            "solves": 1 + 2 * len(requested),
            "omissions": ["adjoint sensitivity", "nonlinear bias sensitivity", "statistical covariance"],
        },
    }


def _finite_eigenvalues(values: np.ndarray) -> list[complex]:
    finite = [complex(value) for value in values if np.isfinite(value.real) and np.isfinite(value.imag)]
    finite.sort(key=lambda value: (value.real, value.imag))
    return finite


def run_linear_pole_zero(
    project: CircuitProject,
    excitation: AcExcitation,
    output_probe: ProbeDescriptor,
) -> dict[str, Any]:
    """Solve descriptor-system poles and SISO transmission zeros.

    The descriptor matrices are recovered from the exact MNA pencil
    ``G + s C``. Infinite descriptor eigenvalues are omitted and counted.
    """

    _require_linear(project)
    if output_probe.quantity != "node_voltage":
        raise ValueError("Pole-zero output must be a node-voltage probe.")
    request = native_request(project)
    request["analysis"] = {"mode": "ac", "start_hz": 1.0, "stop_hz": 1.0, "points": 1, "scale": "linear"}
    source_found = False
    for element in request["elements"]:
        if element["type"] in {"voltage_source", "current_source"}:
            selected = str(element["id"]).upper() == excitation.source
            element["ac_magnitude"] = 1.0 if selected else 0.0
            element["ac_phase_deg"] = 0.0
            source_found = source_found or selected
    if not source_found:
        raise ValueError(f"Pole-zero excitation source {excitation.source} does not exist.")
    g_raw, b, node_indices, _branch_indices, _nodes = _assemble(request, mode="ac", frequency_hz=0.0)
    at_one, _rhs, *_ = _assemble(request, mode="ac", frequency_hz=1.0 / (2.0 * math.pi))
    g = np.asarray(g_raw.toarray() if hasattr(g_raw, "toarray") else g_raw, dtype=complex)
    pencil = np.asarray(at_one.toarray() if hasattr(at_one, "toarray") else at_one, dtype=complex)
    c_matrix = (pencil - g) / 1j
    unknowns = g.shape[0]
    if unknowns > MAX_POLE_ZERO_UNKNOWNS:
        raise ValueError(f"Pole-zero analysis is limited to {MAX_POLE_ZERO_UNKNOWNS} MNA unknowns.")
    output = np.zeros((1, unknowns), dtype=complex)
    positive = node_indices.get(output_probe.targets[0])
    negative = node_indices.get(output_probe.targets[1]) if len(output_probe.targets) == 2 else None
    if positive is not None:
        output[0, positive] += 1.0
    if negative is not None:
        output[0, negative] -= 1.0
    if not np.any(output):
        raise ValueError("Pole-zero output cannot be ground-to-ground.")

    raw_poles = eig(-g, c_matrix, right=False)
    poles = _finite_eigenvalues(raw_poles)
    augmented_a = np.block([[-g, b.reshape(-1, 1)], [output, np.zeros((1, 1), dtype=complex)]])
    augmented_e = np.block([
        [c_matrix, np.zeros((unknowns, 1), dtype=complex)],
        [np.zeros((1, unknowns + 1), dtype=complex)],
    ])
    raw_zeros = eig(augmented_a, augmented_e, right=False)
    zeros = _finite_eigenvalues(raw_zeros)
    return {
        "contract": POLE_ZERO_RESULT_CONTRACT,
        "status": "completed",
        "model_status": "experimental_linear_descriptor",
        "analysis": {"mode": "pole_zero", "excitation": excitation.to_dict()},
        "output_probe": output_probe.to_dict(),
        "data": {
            "poles_rad_s": _complex_series(poles),
            "zeros_rad_s": _complex_series(zeros),
            "pole_count": len(poles), "zero_count": len(zeros),
            "infinite_pole_count": int(len(raw_poles) - len(poles)),
            "infinite_zero_count": int(len(raw_zeros) - len(zeros)),
        },
        "issues": [],
        "provenance": {
            "implementation": "python.spikes.advanced_analyses.generalized_mna_eigenproblem",
            "formulation": "det(G+sC)=0 and augmented_siso_system_pencil",
            "omissions": ["pole-zero cancellation reduction", "nonlinear operating-point linearization", "multi-input multi-output zeros"],
        },
    }


__all__ = [
    "NOISE_RESULT_CONTRACT", "SENSITIVITY_RESULT_CONTRACT", "POLE_ZERO_RESULT_CONTRACT",
    "run_linear_noise_analysis", "run_ac_sensitivity", "run_linear_pole_zero",
]
