"""Bounded nonlinear operating-point, linearization, noise and distortion tools."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .analyses import AcExcitation
from .behavioral import CompiledBehavioralExpression, compile_behavioral_expression
from .contracts import CircuitElement, CircuitProject, ProbeDescriptor


NONLINEAR_OP_CONTRACT = "spikes/nonlinear-operating-point-result/v1"
NONLINEAR_SMALL_SIGNAL_CONTRACT = "spikes/nonlinear-small-signal-result/v1"
BIASED_NOISE_CONTRACT = "spikes/biased-noise-result/v1"
ADJOINT_SENSITIVITY_CONTRACT = "spikes/nonlinear-adjoint-sensitivity-result/v1"
LOCAL_DISTORTION_CONTRACT = "spikes/local-distortion-result/v1"
TWO_TONE_DISTORTION_CONTRACT = "spikes/two-tone-distortion-result/v1"
FREQUENCY_VOLTERRA_CONTRACT = "spikes/frequency-volterra-result/v1"
MULTITONE_VOLTERRA_CONTRACT = "spikes/multitone-volterra-result/v1"

ELEMENTARY_CHARGE_C = 1.602176634e-19
BOLTZMANN_J_K = 1.380649e-23
MAX_NONLINEAR_UNKNOWNS = 4096
MAX_NEWTON_ITERATIONS = 100
MAX_VOLTERRA_TONES = 4
MAX_VOLTERRA_MIXING_TERMS = 4096


@dataclass(slots=True)
class _OperatingPoint:
    x: np.ndarray
    residual: np.ndarray
    jacobian: np.ndarray
    iterations: int
    node_indices: dict[str, int]
    branch_indices: dict[str, int]
    diode_currents: dict[str, float]


@dataclass(frozen=True, slots=True)
class NoiseCorrelation:
    """Complex correlation coefficient between two native noise sources.

    ``coefficient`` may be one value for the whole sweep or one value per
    requested frequency.  The assembled correlation matrix is required to be
    Hermitian positive semidefinite, so inconsistent multi-source covariance
    requests fail closed instead of producing negative noise power.
    """

    first_source: str
    second_source: str
    coefficient: complex | Sequence[complex]

    def __post_init__(self) -> None:
        first, second = str(self.first_source).upper(), str(self.second_source).upper()
        if not first or not second or first == second:
            raise ValueError("Noise correlation requires two distinct source names.")
        object.__setattr__(self, "first_source", first)
        object.__setattr__(self, "second_source", second)

    def coefficients(self, count: int) -> tuple[complex, ...]:
        raw = self.coefficient
        if isinstance(raw, (complex, float, int)) and not isinstance(raw, bool):
            values = (complex(raw),) * count
        else:
            values = tuple(complex(value) for value in raw)
            if len(values) != count:
                raise ValueError(
                    "Frequency-dependent noise correlation count does not match the sweep."
                )
        if any(
            not math.isfinite(value.real) or not math.isfinite(value.imag)
            or abs(value) > 1.0 + 1.0e-12
            for value in values
        ):
            raise ValueError("Noise correlation coefficients must be finite with magnitude <= 1.")
        return values


@dataclass(frozen=True, slots=True)
class VolterraTone:
    """One real sinusoidal excitation used by the multi-tone Volterra solver."""

    source: str
    frequency_hz: float
    amplitude: float
    phase_deg: float = 0.0

    def __post_init__(self) -> None:
        source = str(self.source).strip().upper()
        frequency = float(self.frequency_hz)
        amplitude = float(self.amplitude)
        phase = float(self.phase_deg)
        if not source:
            raise ValueError("Volterra tone source must not be empty.")
        if not math.isfinite(frequency) or frequency <= 0.0:
            raise ValueError("Volterra tone frequency must be finite and positive.")
        if not math.isfinite(amplitude) or amplitude <= 0.0:
            raise ValueError("Volterra tone amplitude must be finite and positive.")
        if not math.isfinite(phase):
            raise ValueError("Volterra tone phase must be finite.")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "frequency_hz", frequency)
        object.__setattr__(self, "amplitude", amplitude)
        object.__setattr__(self, "phase_deg", phase)


class _NonlinearSystem:
    def __init__(self, project: CircuitProject) -> None:
        allowed = {
            "resistor", "voltage_source", "current_source", "diode",
            "capacitor", "inductor",
            "behavioral_voltage_source", "behavioral_current_source",
            "vcvs", "vccs", "cccs", "ccvs",
        }
        unsupported = [element.name for element in project.elements if element.kind not in allowed]
        if unsupported:
            raise ValueError(
                "Nonlinear reference analysis supports R/L/C/V/I/diode/nonlinear-B only; unsupported: "
                + ", ".join(unsupported)
            )
        if any(element.waveform is not None for element in project.elements):
            raise ValueError("Nonlinear operating point requires constant independent sources.")
        self.project = project
        self.compiled: dict[str, CompiledBehavioralExpression] = {}
        nodes = {
            node for element in project.elements
            for node in (
                element.positive_node, element.negative_node,
                element.control_positive_node, element.control_negative_node,
            )
            if node is not None and node != "0"
        }
        for element in project.elements:
            if element.kind.startswith("behavioral_"):
                assert element.behavioral_expression is not None
                expression = element.behavioral_expression.split("=", 1)[1].strip()
                compiled = compile_behavioral_expression(expression)
                self.compiled[element.name] = compiled
                for signal in compiled.signals:
                    if signal.kind == "v":
                        nodes.update(node for node in (signal.first, signal.second) if node != "0")
        self.node_indices = {node: index for index, node in enumerate(sorted(nodes))}
        branch_names = [
            element.name for element in project.elements
            if element.kind in {
                "voltage_source", "behavioral_voltage_source", "vcvs", "ccvs", "inductor"
            }
        ]
        self.branch_indices = {
            name: len(self.node_indices) + index for index, name in enumerate(branch_names)
        }
        if len(self.node_indices) + len(self.branch_indices) > MAX_NONLINEAR_UNKNOWNS:
            raise ValueError(f"Nonlinear reference analysis is limited to {MAX_NONLINEAR_UNKNOWNS} unknowns.")
        for compiled in self.compiled.values():
            for signal in compiled.signals:
                if signal.kind == "i" and signal.first not in self.branch_indices:
                    raise ValueError(f"Behavioral I({signal.first}) references a non-voltage-defined branch.")

    def node(self, name: str) -> int | None:
        return self.node_indices.get(name)

    @staticmethod
    def _add(vector: np.ndarray, index: int | None, value: float) -> None:
        if index is not None:
            vector[index] += value

    @staticmethod
    def _matrix_add(matrix: np.ndarray, row: int | None, column: int | None, value: float) -> None:
        if row is not None and column is not None:
            matrix[row, column] += value

    def _stamp_pair(self, matrix: np.ndarray, p: int | None, n: int | None, value: float) -> None:
        self._matrix_add(matrix, p, p, value)
        self._matrix_add(matrix, n, n, value)
        self._matrix_add(matrix, p, n, -value)
        self._matrix_add(matrix, n, p, -value)

    def _signal_values(self, compiled: CompiledBehavioralExpression, x: np.ndarray) -> tuple[list[float], list[dict[int, float]]]:
        values: list[float] = []
        mappings: list[dict[int, float]] = []
        for signal in compiled.signals:
            if signal.kind == "v":
                p, n = self.node(signal.first), self.node(signal.second)
                values.append((0.0 if p is None else x[p]) - (0.0 if n is None else x[n]))
                mapping: dict[int, float] = {}
                if p is not None:
                    mapping[p] = mapping.get(p, 0.0) + 1.0
                if n is not None:
                    mapping[n] = mapping.get(n, 0.0) - 1.0
                mappings.append(mapping)
            else:
                branch = self.branch_indices[signal.first]
                values.append(x[branch])
                mappings.append({branch: 1.0})
        return values, mappings

    def assemble(
        self, x: np.ndarray, source_overrides: Mapping[str, float] | None = None
    ) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
        size = len(self.node_indices) + len(self.branch_indices)
        residual = np.zeros(size, dtype=float)
        jacobian = np.zeros((size, size), dtype=float)
        diode_currents: dict[str, float] = {}
        overrides = source_overrides or {}
        for element in self.project.elements:
            p, n = self.node(element.positive_node), self.node(element.negative_node)
            vp = 0.0 if p is None else x[p]
            vn = 0.0 if n is None else x[n]
            voltage = vp - vn
            if element.kind == "resistor":
                conductance = 1.0 / element.value
                current = conductance * voltage
                self._add(residual, p, current)
                self._add(residual, n, -current)
                self._stamp_pair(jacobian, p, n, conductance)
            elif element.kind == "capacitor":
                # Open at the operating point; its descriptor stamp is built
                # separately for frequency-domain linearization.
                continue
            elif element.kind == "inductor":
                branch = self.branch_indices[element.name]
                self._add(residual, p, x[branch])
                self._add(residual, n, -x[branch])
                self._matrix_add(jacobian, p, branch, 1.0)
                self._matrix_add(jacobian, n, branch, -1.0)
                residual[branch] += voltage
                self._matrix_add(jacobian, branch, p, 1.0)
                self._matrix_add(jacobian, branch, n, -1.0)
            elif element.kind == "current_source":
                current = float(overrides.get(element.name, element.value))
                self._add(residual, p, current)
                self._add(residual, n, -current)
            elif element.kind == "voltage_source":
                branch = self.branch_indices[element.name]
                self._add(residual, p, x[branch])
                self._add(residual, n, -x[branch])
                self._matrix_add(jacobian, p, branch, 1.0)
                self._matrix_add(jacobian, n, branch, -1.0)
                residual[branch] += voltage - float(overrides.get(element.name, element.value))
                self._matrix_add(jacobian, branch, p, 1.0)
                self._matrix_add(jacobian, branch, n, -1.0)
            elif element.kind == "diode":
                assert element.diode_model is not None
                model = element.diode_model
                thermal_voltage = BOLTZMANN_J_K * model.temperature_k / ELEMENTARY_CHARGE_C
                argument = voltage / (model.emission_coefficient * thermal_voltage)
                exponential = math.exp(min(argument, 40.0))
                current = model.saturation_current_a * (
                    exponential - 1.0 if argument <= 40.0
                    else exponential * (1.0 + argument - 40.0) - 1.0
                )
                conductance = model.saturation_current_a * exponential / (model.emission_coefficient * thermal_voltage)
                diode_currents[element.name] = current
                self._add(residual, p, current)
                self._add(residual, n, -current)
                self._stamp_pair(jacobian, p, n, conductance)
            elif element.kind in {"vccs", "cccs"}:
                if element.kind == "vccs":
                    cp, cn = self.node(element.control_positive_node or "0"), self.node(element.control_negative_node or "0")
                    control = (0.0 if cp is None else x[cp]) - (0.0 if cn is None else x[cn])
                    gradient = {index: coefficient for index, coefficient in ((cp, element.value), (cn, -element.value)) if index is not None}
                else:
                    assert element.control_source_id is not None
                    control_index = self.branch_indices[element.control_source_id]
                    control = x[control_index]
                    gradient = {control_index: element.value}
                current = element.value * control if element.kind == "vccs" else element.value * control
                self._add(residual, p, current)
                self._add(residual, n, -current)
                for column, derivative in gradient.items():
                    self._matrix_add(jacobian, p, column, derivative)
                    self._matrix_add(jacobian, n, column, -derivative)
            elif element.kind in {"vcvs", "ccvs"}:
                branch = self.branch_indices[element.name]
                self._add(residual, p, x[branch])
                self._add(residual, n, -x[branch])
                self._matrix_add(jacobian, p, branch, 1.0)
                self._matrix_add(jacobian, n, branch, -1.0)
                residual[branch] += voltage
                self._matrix_add(jacobian, branch, p, 1.0)
                self._matrix_add(jacobian, branch, n, -1.0)
                if element.kind == "vcvs":
                    cp, cn = self.node(element.control_positive_node or "0"), self.node(element.control_negative_node or "0")
                    control = (0.0 if cp is None else x[cp]) - (0.0 if cn is None else x[cn])
                    residual[branch] -= element.value * control
                    self._matrix_add(jacobian, branch, cp, -element.value)
                    self._matrix_add(jacobian, branch, cn, element.value)
                else:
                    assert element.control_source_id is not None
                    control_index = self.branch_indices[element.control_source_id]
                    residual[branch] -= element.value * x[control_index]
                    jacobian[branch, control_index] -= element.value
            else:
                compiled = self.compiled[element.name]
                values, mappings = self._signal_values(compiled, x)
                evaluated = compiled.evaluate(values)
                gradient: dict[int, float] = {}
                for derivative, mapping in zip(evaluated.gradient, mappings):
                    for index, coefficient in mapping.items():
                        gradient[index] = gradient.get(index, 0.0) + derivative * coefficient
                if element.kind == "behavioral_current_source":
                    self._add(residual, p, evaluated.value)
                    self._add(residual, n, -evaluated.value)
                    for column, derivative in gradient.items():
                        self._matrix_add(jacobian, p, column, derivative)
                        self._matrix_add(jacobian, n, column, -derivative)
                else:
                    branch = self.branch_indices[element.name]
                    self._add(residual, p, x[branch])
                    self._add(residual, n, -x[branch])
                    self._matrix_add(jacobian, p, branch, 1.0)
                    self._matrix_add(jacobian, n, branch, -1.0)
                    residual[branch] += voltage - evaluated.value
                    self._matrix_add(jacobian, branch, p, 1.0)
                    self._matrix_add(jacobian, branch, n, -1.0)
                    for column, derivative in gradient.items():
                        jacobian[branch, column] -= derivative
        return residual, jacobian, diode_currents


def _solve(
    system: _NonlinearSystem,
    *,
    source_overrides: Mapping[str, float] | None = None,
    initial: np.ndarray | None = None,
) -> _OperatingPoint:
    size = len(system.node_indices) + len(system.branch_indices)
    x = np.zeros(size, dtype=float) if initial is None else np.asarray(initial, dtype=float).copy()
    if x.shape != (size,):
        raise ValueError("Initial nonlinear state size does not match the circuit.")
    for iteration in range(1, MAX_NEWTON_ITERATIONS + 1):
        residual, jacobian, diode_currents = system.assemble(x, source_overrides)
        norm = float(np.linalg.norm(residual, ord=np.inf))
        if norm <= 1.0e-11:
            return _OperatingPoint(x, residual, jacobian, iteration - 1, system.node_indices, system.branch_indices, diode_currents)
        try:
            update = np.linalg.solve(jacobian, -residual)
        except np.linalg.LinAlgError as exc:
            raise ValueError("Nonlinear Jacobian is singular.") from exc
        accepted = False
        damping = 1.0
        while damping >= 2.0 ** -20:
            candidate = x + damping * update
            try:
                candidate_residual, _, _ = system.assemble(candidate, source_overrides)
            except (ArithmeticError, ValueError):
                damping *= 0.5
                continue
            if np.linalg.norm(candidate_residual, ord=np.inf) < norm:
                x = candidate
                accepted = True
                break
            damping *= 0.5
        if not accepted:
            raise ValueError("Nonlinear Newton line search could not reduce the residual.")
    raise ValueError(f"Nonlinear operating point exceeded {MAX_NEWTON_ITERATIONS} Newton iterations.")


def _probe_vector(op: _OperatingPoint, probe: ProbeDescriptor) -> np.ndarray:
    size = len(op.x)
    vector = np.zeros(size, dtype=float)
    if probe.quantity == "node_voltage":
        positive = op.node_indices.get(probe.targets[0])
        negative = op.node_indices.get(probe.targets[1]) if len(probe.targets) == 2 else None
        if positive is not None:
            vector[positive] += 1.0
        if negative is not None:
            vector[negative] -= 1.0
    elif probe.quantity == "element_current" and probe.targets[0] in op.branch_indices:
        vector[op.branch_indices[probe.targets[0]]] = 1.0
    else:
        raise ValueError("Nonlinear analysis probe supports node voltage or voltage-defined branch current.")
    return vector


def _probe_value(op: _OperatingPoint, probe: ProbeDescriptor) -> float:
    return float(_probe_vector(op, probe) @ op.x)


def run_nonlinear_operating_point(project: CircuitProject) -> dict[str, Any]:
    system = _NonlinearSystem(project)
    op = _solve(system)
    return {
        "contract": NONLINEAR_OP_CONTRACT, "status": "completed",
        "model_status": "experimental_bounded_nonlinear_reference",
        "analysis": {"mode": "operating_point"},
        "data": {
            "node_voltage_v": {node: float(op.x[index]) for node, index in op.node_indices.items()},
            "branch_current_a": {name: float(op.x[index]) for name, index in op.branch_indices.items()},
            "diode_current_a": op.diode_currents,
        },
        "diagnostics": {"newton_iterations": op.iterations, "residual_inf": float(np.linalg.norm(op.residual, ord=np.inf))},
        "issues": [],
        "provenance": {"implementation": "python.spikes.nonlinear_analyses.dense_newton_analytic_jacobian"},
    }


def _source_rhs(system: _NonlinearSystem, source: CircuitElement) -> np.ndarray:
    rhs = np.zeros(len(system.node_indices) + len(system.branch_indices), dtype=float)
    p, n = system.node(source.positive_node), system.node(source.negative_node)
    if source.kind == "voltage_source":
        rhs[system.branch_indices[source.name]] = 1.0
    elif source.kind == "current_source":
        system._add(rhs, p, -1.0)
        system._add(rhs, n, 1.0)
    else:
        raise ValueError("Excitation must name an independent voltage or current source.")
    return rhs


def _descriptor_matrix(system: _NonlinearSystem) -> np.ndarray:
    """Return D in F(x) + D dx/dt = b for linear C/L storage."""

    size = len(system.node_indices) + len(system.branch_indices)
    descriptor = np.zeros((size, size), dtype=float)
    for element in system.project.elements:
        if element.kind == "capacitor":
            p, n = system.node(element.positive_node), system.node(element.negative_node)
            system._stamp_pair(descriptor, p, n, element.value)
        elif element.kind == "inductor":
            descriptor[
                system.branch_indices[element.name], system.branch_indices[element.name]
            ] -= element.value
    return descriptor


def _complex_value(value: complex) -> dict[str, float]:
    return {
        "real": float(value.real), "imaginary": float(value.imag),
        "magnitude": float(abs(value)),
        "phase_deg": float(math.degrees(math.atan2(value.imag, value.real))),
    }


def run_nonlinear_small_signal(
    project: CircuitProject, excitation: AcExcitation, output_probe: ProbeDescriptor
) -> dict[str, Any]:
    system = _NonlinearSystem(project)
    op = _solve(system)
    source = next((element for element in project.elements if element.name == excitation.source), None)
    if source is None:
        raise ValueError(f"Small-signal source {excitation.source} does not exist.")
    rhs = _source_rhs(system, source) * excitation.magnitude
    response = np.linalg.solve(op.jacobian, rhs)
    real_response = float(_probe_vector(op, output_probe) @ response)
    phase = math.radians(excitation.phase_deg)
    output = complex(real_response * math.cos(phase), real_response * math.sin(phase))
    return {
        "contract": NONLINEAR_SMALL_SIGNAL_CONTRACT, "status": "completed",
        "model_status": "experimental_bias_linearized_memoryless",
        "analysis": {"mode": "small_signal", "excitation": excitation.to_dict()},
        "output_probe": output_probe.to_dict(),
        "data": {"operating_point": _probe_value(op, output_probe), "output": {"real": output.real, "imaginary": output.imag, "magnitude": abs(output), "phase_deg": math.degrees(math.atan2(output.imag, output.real))}},
        "issues": [],
        "provenance": {"implementation": "analytic_operating_point_jacobian", "omissions": ["dynamic charge", "frequency dependence", "nonlinear capacitance"]},
    }


def run_frequency_dependent_volterra(
    project: CircuitProject,
    excitation: AcExcitation,
    output_probe: ProbeDescriptor,
    *,
    fundamental_frequency_hz: float,
    amplitude: float,
    derivative_step: float = 1.0e-3,
) -> dict[str, Any]:
    """Compute bounded one-tone H1/H2/H3 kernels for an index-1 RLC DAE.

    The nonlinear residual is differentiated by symmetric directional
    differences at the DC operating point. Each harmonic is solved through
    ``J + j*w*D``; unlike the local Taylor reducer this preserves linear RLC
    memory and harmonic loading. The API is intentionally one-source/one-tone
    and does not imply harmonic-balance or arbitrary multi-tone coverage.
    """

    frequency = float(fundamental_frequency_hz)
    signal_amplitude = float(amplitude)
    step = float(derivative_step)
    if not math.isfinite(frequency) or frequency <= 0.0:
        raise ValueError("Volterra fundamental frequency must be finite and positive.")
    if not math.isfinite(signal_amplitude) or signal_amplitude <= 0.0:
        raise ValueError("Volterra amplitude must be finite and positive.")
    if not math.isfinite(step) or step <= 0.0 or step > 0.1:
        raise ValueError("Volterra derivative step must be finite in (0, 0.1].")

    system = _NonlinearSystem(project)
    op = _solve(system)
    source = next(
        (element for element in project.elements if element.name == excitation.source), None
    )
    if source is None:
        raise ValueError(f"Volterra source {excitation.source} does not exist.")
    rhs = _source_rhs(system, source)
    descriptor = _descriptor_matrix(system)
    output_vector = _probe_vector(op, output_probe).astype(complex)
    angular_frequency = 2.0 * math.pi * frequency

    def harmonic_matrix(order: int) -> np.ndarray:
        return op.jacobian.astype(complex) + 1j * order * angular_frequency * descriptor

    try:
        source_phasor = signal_amplitude * complex(
            math.cos(math.radians(excitation.phase_deg)),
            math.sin(math.radians(excitation.phase_deg)),
        )
        x1 = np.linalg.solve(harmonic_matrix(1), rhs.astype(complex) * source_phasor)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Volterra first-order harmonic matrix is singular.") from exc

    def residual(offset: np.ndarray) -> np.ndarray:
        return system.assemble(op.x + offset)[0]

    def second_real(first: np.ndarray, second: np.ndarray) -> np.ndarray:
        if not np.any(first) or not np.any(second):
            return np.zeros_like(op.x)
        return (
            residual(step * (first + second))
            - residual(step * (first - second))
            - residual(step * (-first + second))
            + residual(step * (-first - second))
        ) / (4.0 * step * step)

    def second_complex(first: np.ndarray, second: np.ndarray) -> np.ndarray:
        result = np.zeros_like(x1)
        for left, left_coefficient in ((first.real, 1.0), (first.imag, 1.0j)):
            for right, right_coefficient in ((second.real, 1.0), (second.imag, 1.0j)):
                result += left_coefficient * right_coefficient * second_real(left, right)
        return result

    def third_real(
        first: np.ndarray, second: np.ndarray, third: np.ndarray
    ) -> np.ndarray:
        if not np.any(first) or not np.any(second) or not np.any(third):
            return np.zeros_like(op.x)
        result = np.zeros_like(op.x)
        for first_sign in (-1.0, 1.0):
            for second_sign in (-1.0, 1.0):
                for third_sign in (-1.0, 1.0):
                    result += (
                        first_sign * second_sign * third_sign *
                        residual(step * (
                            first_sign * first + second_sign * second +
                            third_sign * third
                        ))
                    )
        return result / (8.0 * step ** 3)

    def third_complex(
        first: np.ndarray, second: np.ndarray, third: np.ndarray
    ) -> np.ndarray:
        result = np.zeros_like(x1)
        components = lambda value: ((value.real, 1.0), (value.imag, 1.0j))
        for left, left_coefficient in components(first):
            for middle, middle_coefficient in components(second):
                for right, right_coefficient in components(third):
                    result += (
                        left_coefficient * middle_coefficient * right_coefficient *
                        third_real(left, middle, right)
                    )
        return result

    second_forcing = -0.25 * second_complex(x1, x1)
    try:
        x2 = np.linalg.solve(harmonic_matrix(2), second_forcing)
        third_forcing = -(
            0.5 * second_complex(x1, x2) +
            third_complex(x1, x1, x1) / 24.0
        )
        x3 = np.linalg.solve(harmonic_matrix(3), third_forcing)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Volterra higher-order harmonic matrix is singular.") from exc

    output_1 = complex(output_vector @ x1)
    output_2 = complex(output_vector @ x2)
    output_3 = complex(output_vector @ x3)
    thd = None if output_1 == 0.0 else math.hypot(abs(output_2), abs(output_3)) / abs(output_1)
    return {
        "contract": FREQUENCY_VOLTERRA_CONTRACT,
        "status": "completed",
        "model_status": "experimental_frequency_dependent_third_order_volterra",
        "analysis": {
            "mode": "frequency_volterra", "source": source.name,
            "fundamental_frequency_hz": frequency, "amplitude": signal_amplitude,
        },
        "output_probe": output_probe.to_dict(),
        "data": {
            "harmonic_frequency_hz": [frequency, 2.0 * frequency, 3.0 * frequency],
            "harmonic_output": {
                "fundamental": _complex_value(output_1),
                "second": _complex_value(output_2),
                "third": _complex_value(output_3),
            },
            "volterra_kernel": {
                "h1": _complex_value(output_1 / signal_amplitude),
                "h2": _complex_value(output_2 / signal_amplitude ** 2),
                "h3": _complex_value(output_3 / signal_amplitude ** 3),
            },
            "thd": thd,
        },
        "issues": [],
        "provenance": {
            "implementation": "symmetric_directional_derivatives_and_complex_descriptor_solves",
            "derivative_step": step,
            "qualified_scope": "one_source_one_tone_index1_RLC_DAE_through_third_order",
            "omissions": [
                "arbitrary multi-tone kernel grid", "nonlinear dynamic charge",
                "large-signal harmonic balance", "periodic operating points",
            ],
        },
    }


def run_multitone_volterra(
    project: CircuitProject,
    tones: Sequence[VolterraTone],
    output_probe: ProbeDescriptor,
    *,
    derivative_step: float = 1.0e-3,
) -> dict[str, Any]:
    """Solve a bounded arbitrary-tone third-order Volterra frequency lattice.

    Each input is a real sinusoid represented by conjugate Fourier
    coefficients. The solver forms every unique frequency generated through
    third order, including DC, harmonic, sum, and difference products. Linear
    R/L/C memory is retained through ``J + j*omega*D`` at each product.
    """

    configured = tuple(tones)
    step = float(derivative_step)
    if not configured or len(configured) > MAX_VOLTERRA_TONES:
        raise ValueError(
            f"Multi-tone Volterra requires 1 to {MAX_VOLTERRA_TONES} tones."
        )
    if any(not isinstance(tone, VolterraTone) for tone in configured):
        raise ValueError("Multi-tone Volterra inputs must be VolterraTone values.")
    if not math.isfinite(step) or step <= 0.0 or step > 0.1:
        raise ValueError("Volterra derivative step must be finite in (0, 0.1].")
    mixing_work = (2 * len(configured)) ** 2 + (2 * len(configured)) ** 3
    if mixing_work > MAX_VOLTERRA_MIXING_TERMS:
        raise ValueError("Multi-tone Volterra mixing work exceeds its hard bound.")

    system = _NonlinearSystem(project)
    op = _solve(system)
    sources = {
        element.name: element for element in project.elements
        if element.kind in {"voltage_source", "current_source"}
    }
    missing = sorted({tone.source for tone in configured} - set(sources))
    if missing:
        raise ValueError("Volterra tone references unknown source(s): " + ", ".join(missing))
    descriptor = _descriptor_matrix(system)
    output_vector = _probe_vector(op, output_probe).astype(complex)
    maximum_frequency = 3.0 * max(tone.frequency_hz for tone in configured)
    frequency_tolerance = max(1.0e-12, maximum_frequency * 1.0e-12)
    frequency_values: dict[int, float] = {}

    def frequency_key(value: float) -> int:
        key = int(round(value / frequency_tolerance))
        previous = frequency_values.get(key)
        if previous is None:
            frequency_values[key] = float(value)
        elif not math.isclose(previous, value, rel_tol=1.0e-11, abs_tol=frequency_tolerance):
            raise ValueError("Volterra frequency quantization collision exceeded tolerance.")
        return key

    def matrix(frequency_hz: float) -> np.ndarray:
        return (
            op.jacobian.astype(complex) +
            1j * 2.0 * math.pi * frequency_hz * descriptor
        )

    def solve_frequency(forcing: Mapping[int, np.ndarray], label: str) -> dict[int, np.ndarray]:
        result: dict[int, np.ndarray] = {}
        for key, value in forcing.items():
            try:
                result[key] = np.linalg.solve(matrix(frequency_values[key]), value)
            except np.linalg.LinAlgError as exc:
                raise ValueError(
                    f"Volterra {label} matrix is singular at {frequency_values[key]} Hz."
                ) from exc
        return result

    first_forcing: dict[int, np.ndarray] = {}
    for tone in configured:
        source_rhs = _source_rhs(system, sources[tone.source]).astype(complex)
        coefficient = 0.5 * tone.amplitude * complex(
            math.cos(math.radians(tone.phase_deg)),
            math.sin(math.radians(tone.phase_deg)),
        )
        for frequency, phasor in (
            (tone.frequency_hz, coefficient),
            (-tone.frequency_hz, coefficient.conjugate()),
        ):
            key = frequency_key(frequency)
            contribution = source_rhs * phasor
            first_forcing[key] = first_forcing.get(
                key, np.zeros_like(contribution)
            ) + contribution
    first = solve_frequency(first_forcing, "first-order")

    def residual(offset: np.ndarray) -> np.ndarray:
        return system.assemble(op.x + offset)[0]

    def second_real(left: np.ndarray, right: np.ndarray) -> np.ndarray:
        if not np.any(left) or not np.any(right):
            return np.zeros_like(op.x)
        return (
            residual(step * (left + right))
            - residual(step * (left - right))
            - residual(step * (-left + right))
            + residual(step * (-left - right))
        ) / (4.0 * step * step)

    def second_complex(left: np.ndarray, right: np.ndarray) -> np.ndarray:
        result = np.zeros(len(op.x), dtype=complex)
        for left_value, left_factor in ((left.real, 1.0), (left.imag, 1.0j)):
            for right_value, right_factor in ((right.real, 1.0), (right.imag, 1.0j)):
                result += left_factor * right_factor * second_real(left_value, right_value)
        return result

    def third_real(
        first_value: np.ndarray, second_value: np.ndarray, third_value: np.ndarray
    ) -> np.ndarray:
        if not np.any(first_value) or not np.any(second_value) or not np.any(third_value):
            return np.zeros_like(op.x)
        result = np.zeros_like(op.x)
        for first_sign in (-1.0, 1.0):
            for second_sign in (-1.0, 1.0):
                for third_sign in (-1.0, 1.0):
                    result += first_sign * second_sign * third_sign * residual(
                        step * (
                            first_sign * first_value +
                            second_sign * second_value +
                            third_sign * third_value
                        )
                    )
        return result / (8.0 * step ** 3)

    def third_complex(
        first_value: np.ndarray, second_value: np.ndarray, third_value: np.ndarray
    ) -> np.ndarray:
        result = np.zeros(len(op.x), dtype=complex)
        components = lambda value: ((value.real, 1.0), (value.imag, 1.0j))
        for left, left_factor in components(first_value):
            for middle, middle_factor in components(second_value):
                for right, right_factor in components(third_value):
                    result += (
                        left_factor * middle_factor * right_factor *
                        third_real(left, middle, right)
                    )
        return result

    second_forcing: dict[int, np.ndarray] = {}
    for left_key, left in first.items():
        for right_key, right in first.items():
            key = frequency_key(
                frequency_values[left_key] + frequency_values[right_key]
            )
            contribution = -0.5 * second_complex(left, right)
            second_forcing[key] = second_forcing.get(
                key, np.zeros_like(contribution)
            ) + contribution
    second = solve_frequency(second_forcing, "second-order")

    third_forcing: dict[int, np.ndarray] = {}
    for left_key, left in first.items():
        for right_key, right in second.items():
            key = frequency_key(
                frequency_values[left_key] + frequency_values[right_key]
            )
            contribution = -second_complex(left, right)
            third_forcing[key] = third_forcing.get(
                key, np.zeros_like(contribution)
            ) + contribution
    for first_key, first_value in first.items():
        for second_key, second_value in first.items():
            for third_key, third_value in first.items():
                key = frequency_key(
                    frequency_values[first_key] + frequency_values[second_key] +
                    frequency_values[third_key]
                )
                contribution = -third_complex(
                    first_value, second_value, third_value
                ) / 6.0
                third_forcing[key] = third_forcing.get(
                    key, np.zeros_like(contribution)
                ) + contribution
    third = solve_frequency(third_forcing, "third-order")

    def products(order: int, values: Mapping[int, np.ndarray]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key in sorted(values, key=lambda item: frequency_values[item]):
            frequency = frequency_values[key]
            if frequency < -frequency_tolerance:
                continue
            coefficient = complex(output_vector @ values[key])
            peak_phasor = coefficient if abs(frequency) <= frequency_tolerance else 2.0 * coefficient
            result.append({
                "order": order,
                "frequency_hz": 0.0 if abs(frequency) <= frequency_tolerance else frequency,
                "fourier_coefficient": _complex_value(coefficient),
                "real_signal_peak_phasor": _complex_value(peak_phasor),
            })
        return result

    product_records = products(1, first) + products(2, second) + products(3, third)
    return {
        "contract": MULTITONE_VOLTERRA_CONTRACT,
        "status": "completed",
        "model_status": "experimental_frequency_dependent_multitone_third_order_volterra",
        "analysis": {
            "mode": "multitone_frequency_volterra",
            "tones": [
                {
                    "source": tone.source, "frequency_hz": tone.frequency_hz,
                    "amplitude": tone.amplitude, "phase_deg": tone.phase_deg,
                }
                for tone in configured
            ],
        },
        "output_probe": output_probe.to_dict(),
        "data": {
            "products": product_records,
            "frequency_merge_tolerance_hz": frequency_tolerance,
        },
        "issues": [],
        "provenance": {
            "implementation": "third_order_frequency_lattice_symmetric_directional_derivatives",
            "derivative_step": step,
            "fourier_convention": "real tone A*cos(wt+phase) has positive coefficient A/2*exp(j*phase)",
            "qualified_scope": (
                f"up_to_{MAX_VOLTERRA_TONES}_tones_multiple_independent_sources_"
                "index1_linear_RLC_storage_memoryless_nonlinearity"
            ),
            "omissions": [
                "nonlinear dynamic charge", "large-signal harmonic balance",
                "periodic operating points", "orders_above_three",
            ],
        },
    }


def run_biased_noise(
    project: CircuitProject, output_probe: ProbeDescriptor, *,
    temperature_k: float = 300.15,
    frequency_hz: Sequence[float] | None = None,
    correlations: Sequence[NoiseCorrelation] | None = None,
) -> dict[str, Any]:
    temperature = float(temperature_k)
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("Noise temperature must be finite and positive.")
    system = _NonlinearSystem(project)
    op = _solve(system)
    output_vector = _probe_vector(op, output_probe)
    frequencies = tuple(float(value) for value in (frequency_hz or (1.0,)))
    if (
        not frequencies or any(not math.isfinite(value) or value <= 0.0 for value in frequencies)
        or any(right <= left for left, right in zip(frequencies, frequencies[1:]))
    ):
        raise ValueError("Noise frequencies must be finite, positive, and strictly increasing.")
    total_psd = [0.0] * len(frequencies)
    spectral_contributions: dict[str, list[float]] = {}
    source_psd_by_name: dict[str, list[float]] = {}
    transfer_by_name: dict[str, float] = {}
    for element in project.elements:
        if element.kind == "resistor":
            source_psd = [4.0 * BOLTZMANN_J_K * temperature / element.value] * len(frequencies)
        elif element.kind == "diode":
            assert element.diode_model is not None
            current = abs(op.diode_currents[element.name])
            white = 2.0 * ELEMENTARY_CHARGE_C * current
            source_psd = [
                white + element.diode_model.flicker_noise_coefficient *
                current ** element.diode_model.flicker_noise_exponent / frequency
                for frequency in frequencies
            ]
        else:
            continue
        rhs = np.zeros(len(op.x), dtype=float)
        p, n = system.node(element.positive_node), system.node(element.negative_node)
        system._add(rhs, p, -1.0)
        system._add(rhs, n, 1.0)
        response = np.linalg.solve(op.jacobian, rhs)
        transfer = float(output_vector @ response)
        transfer_squared = transfer ** 2
        contribution = [transfer_squared * value for value in source_psd]
        spectral_contributions[element.name] = contribution
        source_psd_by_name[element.name] = source_psd
        transfer_by_name[element.name] = transfer
        total_psd = [left + right for left, right in zip(total_psd, contribution)]
    correlation_records: list[dict[str, Any]] = []
    requested_pairs: set[tuple[str, str]] = set()
    configured = tuple(correlations or ())
    coefficient_by_pair: dict[tuple[str, str], tuple[complex, ...]] = {}
    for correlation in configured:
        if not isinstance(correlation, NoiseCorrelation):
            raise ValueError("Noise correlations must be NoiseCorrelation values.")
        first, second = correlation.first_source, correlation.second_source
        if first not in source_psd_by_name or second not in source_psd_by_name:
            raise ValueError(
                f"Noise correlation references unknown source pair {first}/{second}."
            )
        pair = tuple(sorted((first, second)))
        if pair in requested_pairs:
            raise ValueError(f"Duplicate noise correlation pair {pair[0]}/{pair[1]}.")
        requested_pairs.add(pair)
        values = correlation.coefficients(len(frequencies))
        coefficient_by_pair[(first, second)] = values
        cross_values: list[float] = []
        for index, coefficient in enumerate(values):
            cross = 2.0 * (
                transfer_by_name[first] * transfer_by_name[second] *
                coefficient * math.sqrt(
                    source_psd_by_name[first][index] * source_psd_by_name[second][index]
                )
            ).real
            cross_values.append(float(cross))
            total_psd[index] += float(cross)
        key = f"correlation:{first}:{second}"
        spectral_contributions[key] = cross_values
        correlation_records.append({
            "first_source": first,
            "second_source": second,
            "coefficient": [
                {"real": value.real, "imaginary": value.imag} for value in values
            ],
            "output_cross_psd_v2_hz": cross_values,
        })

    source_names = tuple(source_psd_by_name)
    for frequency_index in range(len(frequencies)):
        correlation_matrix = np.eye(len(source_names), dtype=complex)
        source_index = {name: index for index, name in enumerate(source_names)}
        for (first, second), values in coefficient_by_pair.items():
            left, right = source_index[first], source_index[second]
            correlation_matrix[left, right] = values[frequency_index]
            correlation_matrix[right, left] = values[frequency_index].conjugate()
        minimum_eigenvalue = float(np.linalg.eigvalsh(correlation_matrix).min())
        if minimum_eigenvalue < -1.0e-10:
            raise ValueError(
                "Noise correlation matrix is not positive semidefinite at "
                f"{frequencies[frequency_index]} Hz."
            )
        if total_psd[frequency_index] < -1.0e-20:
            raise ValueError("Correlated noise propagation produced negative output PSD.")
        total_psd[frequency_index] = max(0.0, total_psd[frequency_index])
    integrated_variance = sum(
        0.5 * (left + right) * (f_right - f_left)
        for left, right, f_left, f_right in zip(
            total_psd, total_psd[1:], frequencies, frequencies[1:]
        )
    )
    contributions = {
        name: values[0] for name, values in spectral_contributions.items()
    }
    return {
        "contract": BIASED_NOISE_CONTRACT, "status": "completed",
        "model_status": "experimental_resistor_thermal_diode_shot_and_flicker",
        "analysis": {"mode": "biased_noise", "temperature_k": temperature},
        "output_probe": output_probe.to_dict(),
        "data": {
            "frequency_hz": list(frequencies),
            "output_noise_psd": total_psd[0],
            "output_noise_density": math.sqrt(total_psd[0]),
            "output_noise_psd_v2_hz": total_psd,
            "integrated_output_noise_v_rms": math.sqrt(max(0.0, integrated_variance)),
            "contributions": contributions,
            "spectral_contributions": spectral_contributions,
            "correlations": correlation_records,
        },
        "issues": [],
        "provenance": {
            "models": ["resistor_4kT_over_R", "diode_2q_abs_Id", "diode_KF_abs_Id_power_AF_over_f"],
            "covariance": "complex_Hermitian_PSD_source_correlation_matrix",
            "omissions": ["induced-gate noise", "BSIM compact-model channel noise", "cyclostationary switching noise"],
        },
    }


def run_nonlinear_adjoint_sensitivity(
    project: CircuitProject, output_probe: ProbeDescriptor, element_names: Sequence[str]
) -> dict[str, Any]:
    system = _NonlinearSystem(project)
    op = _solve(system)
    output_vector = _probe_vector(op, output_probe)
    adjoint = np.linalg.solve(op.jacobian.T, output_vector)
    output_value = float(output_vector @ op.x)
    by_name = {element.name: element for element in project.elements}
    sensitivities: dict[str, Any] = {}
    for raw_name in element_names:
        name = str(raw_name).upper()
        element = by_name.get(name)
        if element is None or element.kind not in {"resistor", "diode", "voltage_source", "current_source"}:
            raise ValueError(f"Adjoint sensitivity parameter {name} must be an R, D, V, or I element.")
        fp = np.zeros(len(op.x), dtype=float)
        p, n = system.node(element.positive_node), system.node(element.negative_node)
        if element.kind == "resistor":
            voltage = (0.0 if p is None else op.x[p]) - (0.0 if n is None else op.x[n])
            derivative_current = -voltage / (element.value * element.value)
            system._add(fp, p, derivative_current)
            system._add(fp, n, -derivative_current)
            nominal = element.value
            parameter = "resistance_ohm"
        elif element.kind == "diode":
            assert element.diode_model is not None
            nominal = element.diode_model.saturation_current_a
            derivative_current = op.diode_currents[element.name] / nominal
            system._add(fp, p, derivative_current)
            system._add(fp, n, -derivative_current)
            parameter = "saturation_current_a"
        elif element.kind == "voltage_source":
            nominal, parameter = element.value, "dc_value"
            fp[system.branch_indices[element.name]] = -1.0
        else:
            nominal, parameter = element.value, "dc_value"
            system._add(fp, p, 1.0)
            system._add(fp, n, -1.0)
        derivative = -float(adjoint @ fp)
        normalized = None if output_value == 0.0 else nominal * derivative / output_value
        sensitivities[name] = {"parameter": parameter, "nominal": nominal, "derivative": derivative, "normalized": normalized}
    return {
        "contract": ADJOINT_SENSITIVITY_CONTRACT, "status": "completed",
        "model_status": "experimental_nonlinear_adjoint",
        "analysis": {"mode": "adjoint_sensitivity"}, "output_probe": output_probe.to_dict(),
        "data": {"output_value": output_value, "elements": sensitivities}, "issues": [],
        "provenance": {"implementation": "one_transposed_jacobian_solve", "adjoint_solves": 1},
    }


def run_local_distortion(
    project: CircuitProject,
    source_name: str,
    output_probe: ProbeDescriptor,
    *,
    amplitude: float,
    derivative_step: float | None = None,
) -> dict[str, Any]:
    system = _NonlinearSystem(project)
    source = next((element for element in project.elements if element.name == str(source_name).upper()), None)
    if source is None or source.kind not in {"voltage_source", "current_source"}:
        raise ValueError("Distortion source must name an independent V or I source.")
    signal_amplitude = float(amplitude)
    if not math.isfinite(signal_amplitude) or signal_amplitude <= 0.0:
        raise ValueError("Distortion amplitude must be finite and positive.")
    step = float(derivative_step if derivative_step is not None else max(signal_amplitude * 1.0e-2, 1.0e-6))
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("Distortion derivative step must be finite and positive.")
    base = _solve(system)
    nominal = source.value

    def output(offset: float) -> float:
        solved = _solve(system, source_overrides={source.name: nominal + offset}, initial=base.x)
        return _probe_value(solved, output_probe)

    ym2, ym1, y0, yp1, yp2 = output(-2.0 * step), output(-step), output(0.0), output(step), output(2.0 * step)
    first = (yp1 - ym1) / (2.0 * step)
    second = (yp1 - 2.0 * y0 + ym1) / (step * step)
    third = (yp2 - 2.0 * yp1 + 2.0 * ym1 - ym2) / (2.0 * step ** 3)
    fundamental = first * signal_amplitude + third * signal_amplitude ** 3 / 8.0
    second_harmonic = second * signal_amplitude ** 2 / 4.0
    third_harmonic = third * signal_amplitude ** 3 / 24.0
    thd = None if fundamental == 0.0 else math.hypot(second_harmonic, third_harmonic) / abs(fundamental)
    return {
        "contract": LOCAL_DISTORTION_CONTRACT, "status": "completed",
        "model_status": "experimental_local_third_order_volterra",
        "analysis": {"mode": "local_distortion", "source": source.name, "amplitude": signal_amplitude},
        "output_probe": output_probe.to_dict(),
        "data": {
            "bias_output": y0, "derivatives": {"first": first, "second": second, "third": third},
            "harmonic_amplitudes": {"fundamental": fundamental, "second": second_harmonic, "third": third_harmonic}, "thd": thd,
        },
        "issues": [],
        "provenance": {"implementation": "five_operating_point_local_taylor", "derivative_step": step, "omissions": ["frequency-dependent Volterra kernels", "intermodulation", "large-signal harmonic balance"]},
    }


def run_two_tone_intermodulation(
    project: CircuitProject,
    source_name: str,
    output_probe: ProbeDescriptor,
    *,
    amplitude_1: float,
    amplitude_2: float,
    derivative_step: float | None = None,
) -> dict[str, Any]:
    """Reduce a memoryless third-order Taylor model into two-tone products.

    The operating point and first three local derivatives come from the same
    five-point nonlinear solves as :func:`run_local_distortion`.  Reported
    products are signed peak amplitudes; no frequency-dependent kernels,
    dynamic charge, or harmonic-balance solution is implied.
    """

    a1, a2 = float(amplitude_1), float(amplitude_2)
    if not math.isfinite(a1) or not math.isfinite(a2) or a1 <= 0.0 or a2 <= 0.0:
        raise ValueError("Two-tone amplitudes must be finite and positive.")
    local = run_local_distortion(
        project, source_name, output_probe,
        amplitude=max(a1, a2), derivative_step=derivative_step,
    )
    derivative = local["data"]["derivatives"]
    first, second, third = (
        float(derivative["first"]), float(derivative["second"]), float(derivative["third"])
    )
    fundamental_1 = first * a1 + third * a1 ** 3 / 8.0 + third * a1 * a2 ** 2 / 4.0
    fundamental_2 = first * a2 + third * a2 ** 3 / 8.0 + third * a2 * a1 ** 2 / 4.0
    im2 = second * a1 * a2 / 2.0
    im3_2f1 = third * a1 * a1 * a2 / 8.0
    im3_2f2 = third * a2 * a2 * a1 / 8.0
    return {
        "contract": TWO_TONE_DISTORTION_CONTRACT,
        "status": "completed",
        "model_status": "experimental_memoryless_two_tone_third_order",
        "analysis": {
            "mode": "two_tone_intermodulation", "source": str(source_name).upper(),
            "amplitude_1": a1, "amplitude_2": a2,
        },
        "output_probe": output_probe.to_dict(),
        "data": {
            "bias_output": local["data"]["bias_output"],
            "derivatives": derivative,
            "signed_peak_amplitudes": {
                "f1": fundamental_1, "f2": fundamental_2,
                "f1_plus_f2": im2, "abs_f1_minus_f2": im2,
                "2f1_minus_f2": im3_2f1, "2f1_plus_f2": im3_2f1,
                "2f2_minus_f1": im3_2f2, "2f2_plus_f1": im3_2f2,
            },
        },
        "issues": [],
        "provenance": {
            "implementation": "five_operating_point_memoryless_taylor_reduction",
            "derivative_step": local["provenance"]["derivative_step"],
            "omissions": [
                "frequency-dependent Volterra kernels", "dynamic charge",
                "large-signal harmonic balance", "tone-frequency assignment",
            ],
        },
    }


__all__ = [
    "NONLINEAR_OP_CONTRACT", "NONLINEAR_SMALL_SIGNAL_CONTRACT", "BIASED_NOISE_CONTRACT",
    "NoiseCorrelation", "FREQUENCY_VOLTERRA_CONTRACT",
    "MULTITONE_VOLTERRA_CONTRACT", "VolterraTone",
    "ADJOINT_SENSITIVITY_CONTRACT", "LOCAL_DISTORTION_CONTRACT", "TWO_TONE_DISTORTION_CONTRACT",
    "run_nonlinear_operating_point", "run_nonlinear_small_signal",
    "run_frequency_dependent_volterra", "run_multitone_volterra", "run_biased_noise",
    "run_nonlinear_adjoint_sensitivity", "run_local_distortion", "run_two_tone_intermodulation",
]
