"""Bounded deterministic parameter-sweep orchestration for linear SPIKES decks."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .contracts import CircuitElement, CircuitProject
from .runner import run_project


TEMPERATURE_SWEEP_CONTRACT = "spikes/temperature-sweep-result/v1"
MONTE_CARLO_CONTRACT = "spikes/monte-carlo-result/v1"
CORNER_SWEEP_CONTRACT = "spikes/corner-sweep-result/v1"
MAX_CASES = 256
MAX_TOTAL_SOLVE_POINTS = 250_000
MAX_VARIATIONS = 16


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


@dataclass(frozen=True, slots=True)
class TemperatureCoefficient:
    element: str
    linear_per_c: float
    quadratic_per_c2: float = 0.0

    def __post_init__(self) -> None:
        name = str(self.element).strip().upper()
        if not name:
            raise ValueError("Temperature coefficient requires an element ID.")
        object.__setattr__(self, "element", name)
        object.__setattr__(self, "linear_per_c", _finite(self.linear_per_c, "linear temperature coefficient"))
        object.__setattr__(self, "quadratic_per_c2", _finite(self.quadratic_per_c2, "quadratic temperature coefficient"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "element": self.element,
            "linear_per_c": self.linear_per_c,
            "quadratic_per_c2": self.quadratic_per_c2,
        }


@dataclass(frozen=True, slots=True)
class RelativeVariation:
    element: str
    tolerance: float

    def __post_init__(self) -> None:
        name = str(self.element).strip().upper()
        tolerance = _finite(self.tolerance, "relative tolerance")
        if not name or not 0.0 < tolerance < 1.0:
            raise ValueError("Variation requires an element ID and tolerance in (0, 1).")
        object.__setattr__(self, "element", name)
        object.__setattr__(self, "tolerance", tolerance)

    def to_dict(self) -> dict[str, Any]:
        return {"element": self.element, "tolerance": self.tolerance}


def _linear_elements(project: CircuitProject) -> dict[str, CircuitElement]:
    unsupported = [
        element.name for element in project.elements
        if element.kind not in {"resistor", "capacitor", "inductor", "voltage_source", "current_source"}
    ]
    if unsupported:
        raise ValueError(
            "Sweep orchestration supports only linear R/L/C/V/I elements; unsupported: "
            + ", ".join(unsupported)
            + "."
        )
    return {element.name: element for element in project.elements}


def _validate_targets(elements: Mapping[str, CircuitElement], targets: Sequence[str]) -> None:
    if len(targets) > MAX_VARIATIONS or len(targets) != len(set(targets)):
        raise ValueError(f"Variation targets must be unique and contain at most {MAX_VARIATIONS} elements.")
    missing = [target for target in targets if target not in elements]
    if missing:
        raise ValueError("Unknown variation element(s): " + ", ".join(missing) + ".")
    zero = [target for target in targets if elements[target].value == 0.0]
    if zero:
        raise ValueError("Relative variation requires nonzero nominal values: " + ", ".join(zero) + ".")


def _analysis_points(project: CircuitProject) -> int:
    analysis = project.analysis
    if analysis.mode == "operating_point":
        return 1
    if analysis.mode == "transient":
        assert analysis.time_step_s is not None and analysis.stop_time_s is not None
        return int(math.floor(analysis.stop_time_s / analysis.time_step_s + 1.0e-12)) + 1
    assert analysis.start is not None and analysis.stop is not None and analysis.step is not None
    return int(math.floor(abs((analysis.stop - analysis.start) / analysis.step) + 1.0e-12)) + 1


def _admit_work(project: CircuitProject, cases: int) -> None:
    if not 1 <= cases <= MAX_CASES:
        raise ValueError(f"Sweep case count must be between 1 and {MAX_CASES}.")
    solve_points = _analysis_points(project) * cases
    if solve_points > MAX_TOTAL_SOLVE_POINTS:
        raise ValueError(
            f"Sweep would execute {solve_points} solve points; limit is {MAX_TOTAL_SOLVE_POINTS}."
        )


def _with_values(project: CircuitProject, values: Mapping[str, float]) -> CircuitProject:
    elements = tuple(
        replace(element, value=values.get(element.name, element.value))
        for element in project.elements
    )
    return replace(project, elements=elements)


def _envelope(contract: str, project: CircuitProject, analysis: Mapping[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    completed = all(case["result"]["status"] == "completed" for case in cases)
    return {
        "contract": contract,
        "status": "completed" if completed else "failed",
        "model_status": "experimental",
        "analysis": dict(analysis),
        "cases": cases,
        "diagnostics": {
            "case_count": len(cases),
            "solve_points": len(cases) * _analysis_points(project),
        },
        "issues": [],
        "provenance": {
            "orchestrator": "python.spikes.sweeps",
            "source_sha256": project.source_sha256,
            "execution": "independent_reference_runner_cases",
            "nonlinear_temperature_physics": False,
            "self_heating": False,
            "deck_directive_parsing": False,
        },
    }


def _temperature_values(start_c: float, stop_c: float, step_c: float) -> list[float]:
    start = _finite(start_c, "temperature start")
    stop = _finite(stop_c, "temperature stop")
    step = _finite(step_c, "temperature step")
    if step == 0.0 or (stop - start) * step < 0.0:
        raise ValueError("Temperature step must be nonzero and point toward the stop temperature.")
    count = int(math.floor(abs((stop - start) / step) + 1.0e-12)) + 1
    values = [start + index * step for index in range(count)]
    tolerance = max(abs(start), abs(stop), 1.0) * 1.0e-12
    if values and abs(values[-1] - stop) <= tolerance:
        values[-1] = stop
    return values


def run_temperature_sweep(
    project: CircuitProject,
    start_c: float,
    stop_c: float,
    step_c: float,
    coefficients: Sequence[TemperatureCoefficient],
    *,
    reference_c: float = 27.0,
) -> dict[str, Any]:
    """Apply explicit polynomial value coefficients and run independent cases."""

    elements = _linear_elements(project)
    normalized_step = _finite(step_c, "temperature step")
    temperatures = _temperature_values(start_c, stop_c, normalized_step)
    _admit_work(project, len(temperatures))
    reference = _finite(reference_c, "reference temperature")
    targets = [item.element for item in coefficients]
    _validate_targets(elements, targets)
    if not coefficients:
        raise ValueError("Temperature sweep requires at least one explicit R/L/C coefficient.")
    invalid_kinds = [target for target in targets if elements[target].kind not in {"resistor", "capacitor", "inductor"}]
    if invalid_kinds:
        raise ValueError("Temperature coefficients are limited to R/L/C values: " + ", ".join(invalid_kinds) + ".")
    cases: list[dict[str, Any]] = []
    for index, temperature in enumerate(temperatures):
        delta = temperature - reference
        values: dict[str, float] = {}
        factors: dict[str, float] = {}
        for coefficient in coefficients:
            factor = 1.0 + coefficient.linear_per_c * delta + coefficient.quadratic_per_c2 * delta * delta
            value = elements[coefficient.element].value * factor
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"Temperature case {temperature:g} C makes {coefficient.element} nonpositive or nonfinite.")
            values[coefficient.element] = value
            factors[coefficient.element] = factor
        result = run_project(_with_values(project, values)).to_dict()
        cases.append({
            "index": index,
            "temperature_c": temperature,
            "value_factors": factors,
            "result": result,
        })
    return _envelope(
        TEMPERATURE_SWEEP_CONTRACT,
        project,
        {
            "mode": "temperature_sweep",
            "start_c": temperatures[0],
            "stop_c": temperatures[-1],
            "step_c": normalized_step,
            "reference_c": reference,
            "coefficients": [item.to_dict() for item in coefficients],
        },
        cases,
    )


def _uniform(seed: int, sample: int, element: str, lane: int = 0) -> float:
    digest = hashlib.sha256(f"spikes-mc-v1:{seed}:{sample}:{element}:{lane}".encode("utf-8")).digest()
    integer = int.from_bytes(digest[:8], "big")
    return (integer + 0.5) / float(1 << 64)


def _deviation(seed: int, sample: int, variation: RelativeVariation, distribution: str) -> float:
    if distribution == "uniform":
        normalized = 2.0 * _uniform(seed, sample, variation.element) - 1.0
    else:
        u1 = _uniform(seed, sample, variation.element, 0)
        u2 = _uniform(seed, sample, variation.element, 1)
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        normalized = max(-1.0, min(1.0, z / 3.0))
    return normalized * variation.tolerance


def run_monte_carlo(
    project: CircuitProject,
    variations: Sequence[RelativeVariation],
    *,
    samples: int,
    seed: int,
    distribution: str = "uniform",
) -> dict[str, Any]:
    """Run digest-derived reproducible independent relative-value samples."""

    elements = _linear_elements(project)
    if isinstance(samples, bool) or int(samples) != samples:
        raise ValueError("Monte Carlo sample count must be an integer.")
    sample_count = int(samples)
    _admit_work(project, sample_count)
    if isinstance(seed, bool) or int(seed) != seed or not 0 <= int(seed) <= (1 << 63) - 1:
        raise ValueError("Monte Carlo seed must be an integer from 0 through 2^63-1.")
    normalized_distribution = str(distribution).strip().lower()
    if normalized_distribution not in {"uniform", "normal_3sigma_clipped"}:
        raise ValueError("Monte Carlo distribution must be uniform or normal_3sigma_clipped.")
    targets = [item.element for item in variations]
    _validate_targets(elements, targets)
    if not variations:
        raise ValueError("Monte Carlo requires at least one variation.")
    cases: list[dict[str, Any]] = []
    for sample in range(sample_count):
        deviations = {
            item.element: _deviation(int(seed), sample, item, normalized_distribution)
            for item in variations
        }
        values = {
            target: elements[target].value * (1.0 + deviation)
            for target, deviation in deviations.items()
        }
        result = run_project(_with_values(project, values)).to_dict()
        cases.append({"index": sample, "relative_deviations": deviations, "result": result})
    return _envelope(
        MONTE_CARLO_CONTRACT,
        project,
        {
            "mode": "monte_carlo",
            "samples": sample_count,
            "seed": int(seed),
            "distribution": normalized_distribution,
            "variations": [item.to_dict() for item in variations],
            "random_mapping": (
                "sha256-counter-uniform/v1"
                if normalized_distribution == "uniform"
                else "sha256-counter-box-muller-clipped/v1"
            ),
        },
        cases,
    )


def run_corner_sweep(project: CircuitProject, variations: Sequence[RelativeVariation]) -> dict[str, Any]:
    """Run every deterministic low/high Cartesian corner."""

    elements = _linear_elements(project)
    targets = [item.element for item in variations]
    _validate_targets(elements, targets)
    if not variations:
        raise ValueError("Corner sweep requires at least one variation.")
    case_count = 1 << len(variations)
    _admit_work(project, case_count)
    cases: list[dict[str, Any]] = []
    for case_index in range(case_count):
        labels: dict[str, str] = {}
        deviations: dict[str, float] = {}
        for index, variation in enumerate(variations):
            high = bool(case_index & (1 << index))
            labels[variation.element] = "high" if high else "low"
            deviations[variation.element] = variation.tolerance if high else -variation.tolerance
        values = {
            target: elements[target].value * (1.0 + deviation)
            for target, deviation in deviations.items()
        }
        result = run_project(_with_values(project, values)).to_dict()
        cases.append({
            "index": case_index,
            "corner": labels,
            "relative_deviations": deviations,
            "result": result,
        })
    return _envelope(
        CORNER_SWEEP_CONTRACT,
        project,
        {
            "mode": "corner_sweep",
            "variations": [item.to_dict() for item in variations],
            "ordering": "input-order-bitmask-low-before-high",
        },
        cases,
    )


__all__ = [
    "CORNER_SWEEP_CONTRACT",
    "MONTE_CARLO_CONTRACT",
    "TEMPERATURE_SWEEP_CONTRACT",
    "RelativeVariation",
    "TemperatureCoefficient",
    "run_corner_sweep",
    "run_monte_carlo",
    "run_temperature_sweep",
]
