"""Parallel-diode electrothermal sharing reference and qualification model.

This module is deliberately independent of SPIKES' production MNA/DAE engine.  It
is a small, deterministic reference model for qualification cases involving
parallel diode mismatch, mutual thermal coupling, current hogging, and thermal
runaway.  It must not be advertised as general circuit-solver integration.

The electrical solve enforces a common terminal voltage and a specified total
forward current.  Each diode keeps its own temperature-dependent Shockley law
and series resistance.  A backward-Euler thermal RC step uses the electrical
losses from the start of the step.  This split is intentionally simple and
auditable; production coupled solves belong in the native MNA/DAE engine.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Sequence


_BOLTZMANN_EV_PER_K = 8.617333262145e-5
_BOLTZMANN_J_PER_K = 1.380649e-23
_ELEMENTARY_CHARGE_C = 1.602176634e-19


class ElectrothermalInputError(ValueError):
    """Raised before execution when a reference scenario is not physical."""


@dataclass(frozen=True, slots=True)
class DiodeParameters:
    """Electrical parameters at ``reference_temperature_k``."""

    name: str
    saturation_current_a: float = 1.0e-12
    ideality_factor: float = 1.8
    series_resistance_ohm: float = 0.02
    reference_temperature_k: float = 300.15
    bandgap_ev: float = 1.11
    saturation_temperature_exponent: float = 3.0


@dataclass(frozen=True, slots=True)
class ThermalParameters:
    """One junction-to-ambient compact thermal RC branch."""

    resistance_k_per_w: float = 20.0
    capacitance_j_per_k: float = 0.25
    initial_temperature_k: float = 300.15


@dataclass(frozen=True, slots=True)
class DiodeInstance:
    electrical: DiodeParameters
    thermal: ThermalParameters = ThermalParameters()


@dataclass(frozen=True, slots=True)
class MismatchSpec:
    """Independent, positive log-normal one-sigma mismatch fractions."""

    saturation_current_sigma_fraction: float = 0.0
    ideality_sigma_fraction: float = 0.0
    series_resistance_sigma_fraction: float = 0.0


@dataclass(frozen=True, slots=True)
class RunawayLimits:
    warning_temperature_k: float = 398.15
    trip_temperature_k: float = 423.15
    warning_current_share: float = 0.70
    trip_current_share: float = 0.90
    warn_on_positive_runaway_margin: bool = True


@dataclass(frozen=True, slots=True)
class ParallelDiodeScenario:
    instances: tuple[DiodeInstance, ...]
    total_current_a: float
    duration_s: float
    time_step_s: float
    ambient_temperature_k: float = 300.15
    # Symmetric off-diagonal conductances.  Entry [i][j] transfers heat from i
    # to j in W/K.  The diagonal must be zero.
    mutual_thermal_conductance_w_per_k: tuple[tuple[float, ...], ...] = ()
    limits: RunawayLimits = RunawayLimits()
    stop_on_trip: bool = True


@dataclass(frozen=True, slots=True)
class SharingEvent:
    time_s: float
    severity: str
    kind: str
    instance: str
    value: float
    limit: float
    message: str


@dataclass(frozen=True, slots=True)
class SharingSample:
    time_s: float
    terminal_voltage_v: float
    currents_a: tuple[float, ...]
    powers_w: tuple[float, ...]
    temperatures_k: tuple[float, ...]
    current_shares: tuple[float, ...]
    runaway_margins_w_per_k: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SharingResult:
    """Trace from the qualification-only electrothermal reference."""

    model_status: str
    termination: str
    samples: tuple[SharingSample, ...]
    events: tuple[SharingEvent, ...]
    seed: int | None = None

    @property
    def final(self) -> SharingSample:
        return self.samples[-1]


def _finite(value: float, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ElectrothermalInputError(f"{label} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ElectrothermalInputError(f"{label} must be a finite number.")
    return result


def _require_positive(value: float, label: str, *, allow_zero: bool = False) -> float:
    result = _finite(value, label)
    invalid = result < 0.0 if allow_zero else result <= 0.0
    if invalid:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ElectrothermalInputError(f"{label} must be {qualifier}.")
    return result


def _validate_instance(instance: DiodeInstance, index: int) -> None:
    electrical = instance.electrical
    thermal = instance.thermal
    if not isinstance(electrical.name, str) or not electrical.name.strip():
        raise ElectrothermalInputError(f"instances[{index}].electrical.name must not be blank.")
    _require_positive(electrical.saturation_current_a, f"{electrical.name}.saturation_current_a")
    ideality = _require_positive(electrical.ideality_factor, f"{electrical.name}.ideality_factor")
    if not 0.5 <= ideality <= 10.0:
        raise ElectrothermalInputError(f"{electrical.name}.ideality_factor must be between 0.5 and 10.")
    _require_positive(electrical.series_resistance_ohm, f"{electrical.name}.series_resistance_ohm", allow_zero=True)
    _require_positive(electrical.reference_temperature_k, f"{electrical.name}.reference_temperature_k")
    _require_positive(electrical.bandgap_ev, f"{electrical.name}.bandgap_ev")
    _finite(electrical.saturation_temperature_exponent, f"{electrical.name}.saturation_temperature_exponent")
    _require_positive(thermal.resistance_k_per_w, f"{electrical.name}.resistance_k_per_w")
    _require_positive(thermal.capacitance_j_per_k, f"{electrical.name}.capacitance_j_per_k")
    _require_positive(thermal.initial_temperature_k, f"{electrical.name}.initial_temperature_k")


def validate_scenario(scenario: ParallelDiodeScenario) -> None:
    """Validate all inputs, blocking ambiguous or non-physical execution."""

    if len(scenario.instances) < 2:
        raise ElectrothermalInputError("A parallel-sharing scenario requires at least two diode instances.")
    for index, instance in enumerate(scenario.instances):
        _validate_instance(instance, index)
    names = [instance.electrical.name for instance in scenario.instances]
    if len(names) != len(set(names)):
        raise ElectrothermalInputError("Diode instance names must be unique.")
    _require_positive(scenario.total_current_a, "total_current_a")
    _require_positive(scenario.duration_s, "duration_s")
    _require_positive(scenario.time_step_s, "time_step_s")
    _require_positive(scenario.ambient_temperature_k, "ambient_temperature_k")

    limits = scenario.limits
    warning_temperature = _require_positive(limits.warning_temperature_k, "warning_temperature_k")
    trip_temperature = _require_positive(limits.trip_temperature_k, "trip_temperature_k")
    if warning_temperature >= trip_temperature:
        raise ElectrothermalInputError("warning_temperature_k must be below trip_temperature_k.")
    warning_share = _finite(limits.warning_current_share, "warning_current_share")
    trip_share = _finite(limits.trip_current_share, "trip_current_share")
    equal_share = 1.0 / len(scenario.instances)
    if not equal_share < warning_share < trip_share <= 1.0:
        raise ElectrothermalInputError(
            "Current-share limits must satisfy equal share < warning < trip <= 1."
        )

    matrix = scenario.mutual_thermal_conductance_w_per_k
    if not matrix:
        return
    count = len(scenario.instances)
    if len(matrix) != count or any(len(row) != count for row in matrix):
        raise ElectrothermalInputError("Mutual thermal conductance must be an N by N matrix.")
    for i in range(count):
        for j in range(count):
            conductance = _require_positive(
                matrix[i][j], f"mutual_thermal_conductance_w_per_k[{i}][{j}]", allow_zero=True
            )
            if i == j and conductance != 0.0:
                raise ElectrothermalInputError("Mutual thermal conductance diagonal entries must be zero.")
            if not math.isclose(conductance, float(matrix[j][i]), rel_tol=1.0e-12, abs_tol=1.0e-15):
                raise ElectrothermalInputError("Mutual thermal conductance matrix must be symmetric.")


def _lognormal_multiplier(rng: random.Random, sigma_fraction: float) -> float:
    sigma_fraction = _require_positive(sigma_fraction, "mismatch sigma", allow_zero=True)
    if sigma_fraction == 0.0:
        return 1.0
    # Convert coefficient of variation to log-space and retain a mean of one.
    sigma_log = math.sqrt(math.log1p(sigma_fraction * sigma_fraction))
    return math.exp(rng.gauss(-0.5 * sigma_log * sigma_log, sigma_log))


def sample_diode_instances(
    base: DiodeInstance,
    count: int,
    *,
    seed: int,
    mismatch: MismatchSpec = MismatchSpec(),
    exact_matched: bool = False,
    name_prefix: str = "D",
) -> tuple[DiodeInstance, ...]:
    """Create reproducible independent instances or an exactly matched set.

    No random mismatch is ever applied by :func:`simulate_parallel_diodes`; it
    must be requested explicitly through this helper.
    """

    if not isinstance(count, int) or count < 2:
        raise ElectrothermalInputError("count must be an integer of at least two.")
    if not isinstance(seed, int):
        raise ElectrothermalInputError("seed must be an integer.")
    if not isinstance(name_prefix, str) or not name_prefix.strip():
        raise ElectrothermalInputError("name_prefix must not be blank.")
    _validate_instance(base, 0)
    for label, sigma in (
        ("saturation_current_sigma_fraction", mismatch.saturation_current_sigma_fraction),
        ("ideality_sigma_fraction", mismatch.ideality_sigma_fraction),
        ("series_resistance_sigma_fraction", mismatch.series_resistance_sigma_fraction),
    ):
        _require_positive(sigma, label, allow_zero=True)

    rng = random.Random(seed)
    result: list[DiodeInstance] = []
    for index in range(count):
        electrical = base.electrical
        if not exact_matched:
            electrical = DiodeParameters(
                name=electrical.name,
                saturation_current_a=electrical.saturation_current_a
                * _lognormal_multiplier(rng, mismatch.saturation_current_sigma_fraction),
                ideality_factor=electrical.ideality_factor
                * _lognormal_multiplier(rng, mismatch.ideality_sigma_fraction),
                series_resistance_ohm=electrical.series_resistance_ohm
                * _lognormal_multiplier(rng, mismatch.series_resistance_sigma_fraction),
                reference_temperature_k=electrical.reference_temperature_k,
                bandgap_ev=electrical.bandgap_ev,
                saturation_temperature_exponent=electrical.saturation_temperature_exponent,
            )
        result.append(
            DiodeInstance(
                electrical=DiodeParameters(
                    name=f"{name_prefix}{index + 1}",
                    saturation_current_a=electrical.saturation_current_a,
                    ideality_factor=electrical.ideality_factor,
                    series_resistance_ohm=electrical.series_resistance_ohm,
                    reference_temperature_k=electrical.reference_temperature_k,
                    bandgap_ev=electrical.bandgap_ev,
                    saturation_temperature_exponent=electrical.saturation_temperature_exponent,
                ),
                thermal=base.thermal,
            )
        )
    return tuple(result)


def _saturation_current(parameters: DiodeParameters, temperature_k: float) -> float:
    ratio = temperature_k / parameters.reference_temperature_k
    exponent = (parameters.bandgap_ev / _BOLTZMANN_EV_PER_K) * (
        1.0 / parameters.reference_temperature_k - 1.0 / temperature_k
    )
    return parameters.saturation_current_a * ratio ** parameters.saturation_temperature_exponent * math.exp(
        min(700.0, max(-700.0, exponent))
    )


def _voltage_for_current(parameters: DiodeParameters, temperature_k: float, current_a: float) -> float:
    saturation_current = _saturation_current(parameters, temperature_k)
    thermal_voltage = _BOLTZMANN_J_PER_K * temperature_k / _ELEMENTARY_CHARGE_C
    return (
        parameters.ideality_factor * thermal_voltage * math.log1p(current_a / saturation_current)
        + current_a * parameters.series_resistance_ohm
    )


def _current_at_voltage(
    parameters: DiodeParameters, temperature_k: float, voltage_v: float, upper_current_a: float
) -> float:
    low = 0.0
    high = upper_current_a
    for _ in range(64):
        midpoint = 0.5 * (low + high)
        if _voltage_for_current(parameters, temperature_k, midpoint) < voltage_v:
            low = midpoint
        else:
            high = midpoint
    return 0.5 * (low + high)


def _solve_electrical(
    instances: Sequence[DiodeInstance], temperatures_k: Sequence[float], total_current_a: float
) -> tuple[float, tuple[float, ...], tuple[float, ...]]:
    high_voltage = max(
        _voltage_for_current(instance.electrical, temperature, total_current_a)
        for instance, temperature in zip(instances, temperatures_k)
    )
    low_voltage = 0.0
    currents: tuple[float, ...] = ()
    for _ in range(72):
        voltage = 0.5 * (low_voltage + high_voltage)
        currents = tuple(
            _current_at_voltage(instance.electrical, temperature, voltage, total_current_a)
            for instance, temperature in zip(instances, temperatures_k)
        )
        if sum(currents) < total_current_a:
            low_voltage = voltage
        else:
            high_voltage = voltage
    voltage = 0.5 * (low_voltage + high_voltage)
    currents = tuple(
        _current_at_voltage(instance.electrical, temperature, voltage, total_current_a)
        for instance, temperature in zip(instances, temperatures_k)
    )
    correction = total_current_a / sum(currents)
    currents = tuple(current * correction for current in currents)
    return voltage, currents, tuple(voltage * current for current in currents)


def _mutual_matrix(scenario: ParallelDiodeScenario) -> tuple[tuple[float, ...], ...]:
    if scenario.mutual_thermal_conductance_w_per_k:
        return scenario.mutual_thermal_conductance_w_per_k
    count = len(scenario.instances)
    return tuple(tuple(0.0 for _ in range(count)) for _ in range(count))


def _solve_linear(matrix: list[list[float]], vector: list[float]) -> tuple[float, ...]:
    """Small dense Gaussian elimination used only by this reference model."""

    count = len(vector)
    for column in range(count):
        pivot = max(range(column, count), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1.0e-18:
            raise ArithmeticError("Singular thermal reference matrix.")
        if pivot != column:
            matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
            vector[column], vector[pivot] = vector[pivot], vector[column]
        scale = matrix[column][column]
        for row in range(column + 1, count):
            factor = matrix[row][column] / scale
            if factor == 0.0:
                continue
            for entry in range(column, count):
                matrix[row][entry] -= factor * matrix[column][entry]
            vector[row] -= factor * vector[column]
    solution = [0.0] * count
    for row in range(count - 1, -1, -1):
        remainder = vector[row] - sum(matrix[row][column] * solution[column] for column in range(row + 1, count))
        solution[row] = remainder / matrix[row][row]
    return tuple(solution)


def _advance_thermal(
    scenario: ParallelDiodeScenario,
    temperatures_k: Sequence[float],
    powers_w: Sequence[float],
    time_step_s: float,
) -> tuple[float, ...]:
    count = len(scenario.instances)
    mutual = _mutual_matrix(scenario)
    matrix = [[0.0] * count for _ in range(count)]
    vector = [0.0] * count
    for i, instance in enumerate(scenario.instances):
        capacitance = instance.thermal.capacitance_j_per_k
        ambient_conductance = 1.0 / instance.thermal.resistance_k_per_w
        mutual_total = sum(mutual[i])
        matrix[i][i] = capacitance / time_step_s + ambient_conductance + mutual_total
        vector[i] = (
            capacitance / time_step_s * temperatures_k[i]
            + ambient_conductance * scenario.ambient_temperature_k
            + powers_w[i]
        )
        for j in range(count):
            if i != j:
                matrix[i][j] = -mutual[i][j]
    return _solve_linear(matrix, vector)


def _runaway_margins(
    scenario: ParallelDiodeScenario, temperatures_k: Sequence[float], powers_w: Sequence[float]
) -> tuple[float, ...]:
    mutual = _mutual_matrix(scenario)
    margins: list[float] = []
    for index, temperature in enumerate(temperatures_k):
        delta = max(1.0e-3, temperature * 1.0e-5)
        perturbed = list(temperatures_k)
        perturbed[index] += delta
        _, _, perturbed_powers = _solve_electrical(
            scenario.instances, perturbed, scenario.total_current_a
        )
        generated_slope = (perturbed_powers[index] - powers_w[index]) / delta
        cooling_slope = 1.0 / scenario.instances[index].thermal.resistance_k_per_w + sum(mutual[index])
        margins.append(generated_slope - cooling_slope)
    return tuple(margins)


def _sample(scenario: ParallelDiodeScenario, time_s: float, temperatures_k: Sequence[float]) -> SharingSample:
    voltage, currents, powers = _solve_electrical(
        scenario.instances, temperatures_k, scenario.total_current_a
    )
    return SharingSample(
        time_s=time_s,
        terminal_voltage_v=voltage,
        currents_a=currents,
        powers_w=powers,
        temperatures_k=tuple(temperatures_k),
        current_shares=tuple(current / scenario.total_current_a for current in currents),
        runaway_margins_w_per_k=_runaway_margins(scenario, temperatures_k, powers),
    )


def _threshold_time(previous: SharingSample, current: SharingSample, old: float, new: float, limit: float) -> float:
    if new == old:
        return current.time_s
    fraction = min(1.0, max(0.0, (limit - old) / (new - old)))
    return previous.time_s + fraction * (current.time_s - previous.time_s)


def _new_events(
    scenario: ParallelDiodeScenario,
    previous: SharingSample,
    current: SharingSample,
    emitted: set[tuple[str, int]],
) -> list[SharingEvent]:
    result: list[SharingEvent] = []
    limits = scenario.limits
    checks = (
        ("temperature_warning", "warning", previous.temperatures_k, current.temperatures_k, limits.warning_temperature_k),
        ("temperature_trip", "trip", previous.temperatures_k, current.temperatures_k, limits.trip_temperature_k),
        ("current_share_warning", "warning", previous.current_shares, current.current_shares, limits.warning_current_share),
        ("current_share_trip", "trip", previous.current_shares, current.current_shares, limits.trip_current_share),
    )
    for kind, severity, old_values, new_values, limit in checks:
        unit = "K" if kind.startswith("temperature") else "fraction"
        for index, (old, new) in enumerate(zip(old_values, new_values)):
            key = (kind, index)
            if key not in emitted and old < limit <= new:
                emitted.add(key)
                name = scenario.instances[index].electrical.name
                result.append(
                    SharingEvent(
                        time_s=_threshold_time(previous, current, old, new, limit),
                        severity=severity,
                        kind=kind,
                        instance=name,
                        value=new,
                        limit=limit,
                        message=f"{name} crossed {kind.replace('_', ' ')} at {new:.6g} {unit}.",
                    )
                )
    if limits.warn_on_positive_runaway_margin:
        for index, (old, new) in enumerate(
            zip(previous.runaway_margins_w_per_k, current.runaway_margins_w_per_k)
        ):
            key = ("positive_runaway_margin", index)
            if key not in emitted and old <= 0.0 < new:
                emitted.add(key)
                name = scenario.instances[index].electrical.name
                result.append(
                    SharingEvent(
                        time_s=_threshold_time(previous, current, old, new, 0.0),
                        severity="warning",
                        kind="positive_runaway_margin",
                        instance=name,
                        value=new,
                        limit=0.0,
                        message=f"{name} generated-heat slope exceeded its local cooling slope.",
                    )
                )
    return result


def _initial_events(
    scenario: ParallelDiodeScenario,
    sample: SharingSample,
    emitted: set[tuple[str, int]],
) -> list[SharingEvent]:
    """Report limits already exceeded at t=0 instead of hiding the condition."""

    limits = scenario.limits
    result: list[SharingEvent] = []
    checks = (
        ("temperature_warning", "warning", sample.temperatures_k, limits.warning_temperature_k),
        ("temperature_trip", "trip", sample.temperatures_k, limits.trip_temperature_k),
        ("current_share_warning", "warning", sample.current_shares, limits.warning_current_share),
        ("current_share_trip", "trip", sample.current_shares, limits.trip_current_share),
    )
    for kind, severity, values, limit in checks:
        unit = "K" if kind.startswith("temperature") else "fraction"
        for index, value in enumerate(values):
            if value < limit:
                continue
            emitted.add((kind, index))
            name = scenario.instances[index].electrical.name
            result.append(
                SharingEvent(
                    time_s=0.0,
                    severity=severity,
                    kind=kind,
                    instance=name,
                    value=value,
                    limit=limit,
                    message=f"{name} started beyond {kind.replace('_', ' ')} at {value:.6g} {unit}.",
                )
            )
    if limits.warn_on_positive_runaway_margin:
        for index, margin in enumerate(sample.runaway_margins_w_per_k):
            if margin <= 0.0:
                continue
            emitted.add(("positive_runaway_margin", index))
            name = scenario.instances[index].electrical.name
            result.append(
                SharingEvent(
                    time_s=0.0,
                    severity="warning",
                    kind="positive_runaway_margin",
                    instance=name,
                    value=margin,
                    limit=0.0,
                    message=f"{name} started with generated-heat slope above its local cooling slope.",
                )
            )
    return result


def simulate_parallel_diodes(scenario: ParallelDiodeScenario, *, seed: int | None = None) -> SharingResult:
    """Run a validated deterministic electrothermal qualification trace.

    ``seed`` is provenance only.  Sampling is explicit in
    :func:`sample_diode_instances`, preventing hidden variation in nominal runs.
    """

    validate_scenario(scenario)
    if seed is not None and not isinstance(seed, int):
        raise ElectrothermalInputError("seed must be an integer or None.")

    temperatures = tuple(instance.thermal.initial_temperature_k for instance in scenario.instances)
    samples = [_sample(scenario, 0.0, temperatures)]
    emitted: set[tuple[str, int]] = set()
    events = _initial_events(scenario, samples[0], emitted)
    termination = "completed"
    if scenario.stop_on_trip and any(event.severity == "trip" for event in events):
        termination = "tripped"
    time_s = 0.0
    while termination != "tripped" and time_s < scenario.duration_s:
        step = min(scenario.time_step_s, scenario.duration_s - time_s)
        previous = samples[-1]
        temperatures = _advance_thermal(scenario, temperatures, previous.powers_w, step)
        if any(not math.isfinite(value) or value <= 0.0 for value in temperatures):
            raise ArithmeticError("The thermal reference produced a non-physical temperature.")
        time_s += step
        current = _sample(scenario, time_s, temperatures)
        samples.append(current)
        step_events = _new_events(scenario, previous, current, emitted)
        events.extend(step_events)
        if scenario.stop_on_trip and any(event.severity == "trip" for event in step_events):
            termination = "tripped"
            break

    return SharingResult(
        model_status="reference_qualification_only",
        termination=termination,
        samples=tuple(samples),
        events=tuple(events),
        seed=seed,
    )


__all__ = [
    "DiodeInstance",
    "DiodeParameters",
    "ElectrothermalInputError",
    "MismatchSpec",
    "ParallelDiodeScenario",
    "RunawayLimits",
    "SharingEvent",
    "SharingResult",
    "SharingSample",
    "ThermalParameters",
    "sample_diode_instances",
    "simulate_parallel_diodes",
    "validate_scenario",
]
