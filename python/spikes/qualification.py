"""Reproducible native-solver and interactive-session qualification corpus.

This suite combines closed-form electrical fixtures, converter invariants,
bounded performance observations, and persistent-session behavior.  It does
not turn best-effort desktop measurements into a hard-real-time or competitive
performance claim.
"""

from __future__ import annotations

import hashlib
import math
import platform
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .native_abi import (
    NativeLibrary,
    NativeTransientCheckpoint,
    NativeTransientSession,
    load_native_library,
)
from .session import FunctionalPlant, Lifecycle, SimulationSession, VirtualClockScheduler
from .session_contracts import CompiledBlock, ControlType, InputDescriptor, SignalDescriptor


QUALIFICATION_REPORT_CONTRACT = "spikes/qualification-report/v1"
QUALIFICATION_CASE_CONTRACT = "spikes/qualification-case/v1"
MAX_REPETITIONS = 20
MAX_WALL_STEPS = 1_000


def _percentile(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _time_weighted_mean(times: Sequence[float], values: Sequence[float]) -> float:
    if len(times) != len(values) or len(times) < 2:
        raise ValueError("time-weighted mean requires at least two aligned samples")
    duration = times[-1] - times[0]
    if duration <= 0.0:
        raise ValueError("time-weighted mean requires increasing sample times")
    area = sum(
        0.5 * (values[index] + values[index - 1]) *
        (times[index] - times[index - 1])
        for index in range(1, len(times))
    )
    return area / duration


def _case(
    case_id: str,
    title: str,
    category: str,
    behavior: str,
    repetitions: int,
    runner: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    cold_started = time.perf_counter_ns()
    try:
        cold_observation = dict(runner())
        cold_elapsed = time.perf_counter_ns() - cold_started
    except Exception as exc:
        return {
            "contract": QUALIFICATION_CASE_CONTRACT,
            "case_id": case_id,
            "title": title,
            "category": category,
            "behavior": behavior,
            "status": "failed",
            "repetitions": repetitions,
            "timing_scope": "in_process_ctypes_build_and_solve",
            "cold_elapsed_ns": None,
            "timing_ns": [],
            "median_elapsed_ns": None,
            "p95_elapsed_ns": None,
            "observations": [],
            "issues": [{
                "code": "SPIKES_QUALIFICATION_EXECUTION_FAILED",
                "message": str(exc)[:4096],
            }],
        }
    timings: list[int] = []
    observations: list[Mapping[str, Any]] = [cold_observation]
    try:
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            observation = dict(runner())
            timings.append(time.perf_counter_ns() - started)
            observations.append(observation)
        passed = all(bool(item.get("passed")) for item in observations)
        issues = [] if passed else [{
            "code": "SPIKES_QUALIFICATION_BEHAVIOR_MISMATCH",
            "message": "One or more repetitions violated the declared behavior gate.",
        }]
    except Exception as exc:
        passed = False
        issues = [{
            "code": "SPIKES_QUALIFICATION_EXECUTION_FAILED",
            "message": str(exc)[:4096],
        }]
    return {
        "contract": QUALIFICATION_CASE_CONTRACT,
        "case_id": case_id,
        "title": title,
        "category": category,
        "behavior": behavior,
        "status": "passed" if passed else "failed",
        "repetitions": repetitions,
        "timing_scope": "in_process_ctypes_build_and_solve",
        "cold_elapsed_ns": cold_elapsed,
        "timing_ns": timings,
        "median_elapsed_ns": int(statistics.median(timings)) if timings else None,
        "p95_elapsed_ns": _percentile(timings, 0.95) if timings else None,
        "observations": observations,
        "issues": issues,
    }


def _balanced_bridge(library: NativeLibrary) -> Mapping[str, Any]:
    with library.circuit() as circuit:
        circuit.add_voltage_source("V1", "in", "0", 10.0)
        circuit.add_resistor("R1", "in", "a", 1_000.0)
        circuit.add_resistor("R2", "a", "0", 2_000.0)
        circuit.add_resistor("R3", "in", "b", 2_000.0)
        circuit.add_resistor("R4", "b", "0", 4_000.0)
        circuit.add_resistor("Rbridge", "a", "b", 317.0)
        with circuit.solve_operating_point() as result:
            difference = result.node_voltage("a") - result.node_voltage("b")
            error = abs(difference)
            return {
                "passed": result.status == "converged" and error <= 2.0e-12,
                "observed_differential_v": difference,
                "expected_differential_v": 0.0,
                "absolute_error_v": error,
                "error_limit_v": 2.0e-12,
                "diagnostics": result.diagnostics(),
            }


def _large_resistor_ladder(library: NativeLibrary, sections: int = 200) -> Mapping[str, Any]:
    resistance = 100.0
    with library.circuit() as circuit:
        circuit.add_voltage_source("V1", "n0", "0", 10.0)
        for index in range(sections):
            circuit.add_resistor(
                f"R{index}", f"n{index}", f"n{index + 1}", resistance
            )
        circuit.add_resistor("Rterm", f"n{sections}", "0", resistance)
        with circuit.solve_operating_point() as result:
            probe_index = sections // 2
            observed = result.node_voltage(f"n{probe_index}")
            expected = 10.0 * (sections + 1 - probe_index) / (sections + 1)
            error = abs(observed - expected)
            return {
                "passed": result.status == "converged" and error <= 2.0e-10,
                "matrix_order": result.diagnostics()["matrix_order"],
                "sections": sections,
                "observed_voltage_v": observed,
                "expected_voltage_v": expected,
                "absolute_error_v": error,
                "error_limit_v": 2.0e-10,
                "diagnostics": result.diagnostics(),
            }


def _threaded_cg_ladder(library: NativeLibrary, sections: int = 200) -> Mapping[str, Any]:
    with library.circuit() as circuit:
        circuit.add_resistor("R0", "n0", "0", 1.0)
        for index in range(1, sections):
            circuit.add_resistor(
                f"R{index}", f"n{index - 1}", f"n{index}", 1.0
            )
        circuit.add_current_source("I1", "0", f"n{sections - 1}", 1.0)
        with circuit.solve_operating_point(
            linear_solver="conjugate_gradient", linear_threads=2,
            max_linear_iterations=sections * 4,
        ) as result:
            observed = result.node_voltage(f"n{sections - 1}")
            diagnostics = result.diagnostics()
            error = abs(observed - float(sections))
            return {
                "passed": (
                    result.status == "converged" and error <= 2.0e-8 and
                    diagnostics.get("linear_solver") == "conjugate_gradient" and
                    diagnostics.get("linear_threads") == 2 and
                    diagnostics.get("linear_iterations", 0) > 0
                ),
                "sections": sections,
                "observed_voltage_v": observed,
                "expected_voltage_v": float(sections),
                "absolute_error_v": error,
                "error_limit_v": 2.0e-8,
                "diagnostics": diagnostics,
            }


def _sparse_solver_ladder(
    library: NativeLibrary, sections: int = 1000
) -> Mapping[str, Any]:
    with library.circuit() as circuit:
        circuit.add_voltage_source("V1", "n0", "0", 10.0)
        for index in range(1, sections + 1):
            circuit.add_resistor(
                f"R{index}", f"n{index - 1}", f"n{index}", 1.0
            )
        circuit.add_resistor("Rterm", f"n{sections}", "0", float(sections))
        observations: dict[str, tuple[str, float, Mapping[str, Any]]] = {}
        for method in ("sparse_lu", "ilu_gmres"):
            with circuit.solve_operating_point(
                linear_solver=method, max_linear_iterations=4000
            ) as result:
                observations[method] = (
                    result.status,
                    result.node_voltage(f"n{sections}"),
                    result.diagnostics(),
                )
    direct_status, direct_voltage, direct_diagnostics = observations["sparse_lu"]
    iterative_status, iterative_voltage, iterative_diagnostics = observations[
        "ilu_gmres"
    ]
    difference = abs(direct_voltage - iterative_voltage)
    order = int(direct_diagnostics["matrix_order"])
    nonzeros = int(direct_diagnostics.get("matrix_nonzeros", order * order))
    return {
        "passed": (
            direct_status == "converged" and iterative_status == "converged" and
            abs(direct_voltage - 5.0) <= 2.0e-8 and difference <= 2.0e-8 and
            direct_diagnostics.get("linear_solver") == "sparse_lu" and
            iterative_diagnostics.get("linear_solver") == "ilu_gmres" and
            nonzeros < 4 * order and
            direct_diagnostics.get("symbolic_analyses") == 1 and
            direct_diagnostics.get("numeric_factorizations") == 1
        ),
        "sections": sections,
        "matrix_order": order,
        "matrix_nonzeros": nonzeros,
        "expected_voltage_v": 5.0,
        "sparse_lu_voltage_v": direct_voltage,
        "ilu_gmres_voltage_v": iterative_voltage,
        "absolute_difference_v": difference,
        "difference_limit_v": 2.0e-8,
        "sparse_lu_diagnostics": direct_diagnostics,
        "ilu_gmres_diagnostics": iterative_diagnostics,
    }


def _gmres_controlled_switch(library: NativeLibrary) -> Mapping[str, Any]:
    def solve(method: str) -> tuple[str, float, Mapping[str, Any]]:
        with library.circuit() as circuit:
            circuit.add_voltage_source("Vs", "in", "0", 10.0)
            circuit.add_voltage_source("Vg", "gate", "0", 2.5)
            circuit.add_voltage_controlled_switch(
                "S1", "in", "out", "gate", "0"
            )
            circuit.add_resistor("Rload", "out", "0", 10.0)
            with circuit.solve_operating_point(
                linear_solver=method, linear_threads=2
            ) as result:
                return result.status, result.node_voltage("out"), result.diagnostics()

    direct_status, direct_voltage, direct_diagnostics = solve("dense_lu")
    gmres_status, gmres_voltage, gmres_diagnostics = solve("gmres")
    difference = abs(gmres_voltage - direct_voltage)
    return {
        "passed": (
            direct_status == "converged" and gmres_status == "converged" and
            difference <= 2.0e-9 and
            gmres_diagnostics.get("linear_solver") == "gmres" and
            gmres_diagnostics.get("linear_iterations", 0) > 0
        ),
        "direct_voltage_v": direct_voltage,
        "gmres_voltage_v": gmres_voltage,
        "absolute_difference_v": difference,
        "difference_limit_v": 2.0e-9,
        "direct_diagnostics": direct_diagnostics,
        "gmres_diagnostics": gmres_diagnostics,
    }


def _shockley_diode(library: NativeLibrary) -> Mapping[str, Any]:
    current = 1.0e-3
    saturation = 1.0e-12
    temperature = 300.15
    thermal_voltage = 8.617333262145e-5 * temperature
    expected = thermal_voltage * math.log1p(current / saturation)
    with library.circuit() as circuit:
        circuit.add_current_source("I1", "0", "junction", current)
        circuit.add_diode(
            "D1", "junction", "0", saturation_current_a=saturation,
            emission_coefficient=1.0, temperature_k=temperature,
        )
        with circuit.solve_operating_point() as result:
            observed = result.node_voltage("junction")
            error = abs(observed - expected)
            return {
                "passed": result.status == "converged" and error <= 2.0e-9,
                "observed_voltage_v": observed,
                "expected_voltage_v": expected,
                "absolute_error_v": error,
                "error_limit_v": 2.0e-9,
                "diagnostics": result.diagnostics(),
            }


def _underdamped_series_rlc(library: NativeLibrary) -> Mapping[str, Any]:
    resistance = 10.0
    inductance = 1.0e-3
    capacitance = 10.0e-6
    stop = 1.0e-3
    with library.circuit() as circuit:
        circuit.add_voltage_source("V1", "in", "0", 1.0)
        circuit.add_resistor("R1", "in", "n1", resistance)
        circuit.add_inductor("L1", "n1", "out", inductance)
        circuit.add_capacitor("C1", "out", "0", capacitance)
        with circuit.solve_transient(
            time_step_s=2.0e-6, stop_time_s=stop,
            initialize_from_operating_point=False,
            integration_method="hybrid_trapezoidal",
        ) as result:
            last = result.point_count - 1
            observed = result.node_voltage(last, "out")
            alpha = resistance / (2.0 * inductance)
            omega_0 = math.sqrt(1.0 / (inductance * capacitance))
            omega_d = math.sqrt(omega_0 * omega_0 - alpha * alpha)
            expected = 1.0 - math.exp(-alpha * stop) * (
                math.cos(omega_d * stop) +
                alpha / omega_d * math.sin(omega_d * stop)
            )
            error = abs(observed - expected)
            diagnostics = result.diagnostics()
            return {
                "passed": (
                    result.status == "converged" and error <= 2.0e-6 and
                    diagnostics["factorization_reuses"] > 400
                ),
                "observed_voltage_v": observed,
                "expected_voltage_v": expected,
                "absolute_error_v": error,
                "error_limit_v": 2.0e-6,
                "diagnostics": diagnostics,
            }


def _rf_series_resonator(library: NativeLibrary) -> Mapping[str, Any]:
    """Resolve a 50 MHz-class resonator against its closed-form step response."""

    resistance = 5.0
    inductance = 100.0e-9
    capacitance = 100.0e-12
    stop = 100.0e-9
    with library.circuit() as circuit:
        circuit.add_voltage_source("Vrf", "in", "0", 1.0)
        circuit.add_resistor("Rsrc", "in", "tank", resistance)
        circuit.add_inductor("Lrf", "tank", "out", inductance)
        circuit.add_capacitor("Crf", "out", "0", capacitance)
        with circuit.solve_transient(
            time_step_s=0.25e-9, stop_time_s=stop,
            initialize_from_operating_point=False,
            integration_method="hybrid_trapezoidal",
        ) as result:
            observed = result.node_voltage(result.point_count - 1, "out")
            alpha = resistance / (2.0 * inductance)
            omega_0 = math.sqrt(1.0 / (inductance * capacitance))
            omega_d = math.sqrt(omega_0 * omega_0 - alpha * alpha)
            expected = 1.0 - math.exp(-alpha * stop) * (
                math.cos(omega_d * stop) +
                alpha / omega_d * math.sin(omega_d * stop)
            )
            error = abs(observed - expected)
            resonant_frequency = omega_0 / (2.0 * math.pi)
            return {
                "passed": result.status == "converged" and error <= 3.0e-4,
                "resonant_frequency_hz": resonant_frequency,
                "samples_per_undamped_period": 1.0 / (
                    resonant_frequency * 0.25e-9
                ),
                "observed_voltage_v": observed,
                "expected_voltage_v": expected,
                "absolute_error_v": error,
                "error_limit_v": 3.0e-4,
                "diagnostics": result.diagnostics(),
            }


def _motor_armature_fixed_speed(library: NativeLibrary) -> Mapping[str, Any]:
    """Qualify an R-L armature at a fixed mechanical-speed/back-EMF point."""

    bus_voltage = 24.0
    back_emf = 12.0
    resistance = 0.5
    inductance = 2.0e-3
    stop = 20.0e-3
    with library.circuit() as circuit:
        circuit.add_voltage_source("Vbus", "bus", "0", bus_voltage)
        circuit.add_resistor("Rarm", "bus", "winding", resistance)
        circuit.add_inductor("Larm", "winding", "emf", inductance)
        circuit.add_voltage_source("Vbemf", "emf", "0", back_emf)
        with circuit.solve_transient(
            time_step_s=20.0e-6, stop_time_s=stop,
            initialize_from_operating_point=False,
            integration_method="hybrid_trapezoidal",
        ) as result:
            observed = result.element_current(result.point_count - 1, "Larm")
            steady_current = (bus_voltage - back_emf) / resistance
            expected = steady_current * (
                1.0 - math.exp(-resistance * stop / inductance)
            )
            error = abs(observed - expected)
            observed_torque = 0.08 * observed
            expected_torque = 0.08 * expected
            return {
                "passed": result.status == "converged" and error <= 2.0e-5,
                "mechanical_boundary": "fixed_speed_back_emf_source",
                "torque_constant_n_m_per_a": 0.08,
                "observed_armature_current_a": observed,
                "expected_armature_current_a": expected,
                "observed_electromagnetic_torque_n_m": observed_torque,
                "expected_electromagnetic_torque_n_m": expected_torque,
                "absolute_current_error_a": error,
                "error_limit_a": 2.0e-5,
                "diagnostics": result.diagnostics(),
            }


def _pwm_resistive_switch(library: NativeLibrary) -> Mapping[str, Any]:
    edges = (100.0e-6, 200.0e-6, 400.0e-6, 500.0e-6)
    with library.circuit() as circuit:
        circuit.add_voltage_source("Vs", "in", "0", 10.0)
        circuit.add_pulse_voltage_source(
            "Vgate", "gate", "0", initial_value=0.0, pulsed_value=5.0,
            delay_s=100.0e-6, rise_time_s=100.0e-6,
            fall_time_s=100.0e-6, pulse_width_s=200.0e-6,
            period_s=500.0e-6,
        )
        circuit.add_voltage_controlled_switch(
            "S1", "in", "out", "gate", "0", on_resistance_ohm=1.0,
            off_resistance_ohm=1.0e6, threshold_voltage_v=2.5,
            transition_voltage_v=0.1,
        )
        circuit.add_resistor("Rload", "out", "0", 10.0)
        with circuit.solve_transient(
            time_step_s=70.0e-6, stop_time_s=2.5e-3,
            initialize_from_operating_point=False,
            integration_method="hybrid_trapezoidal",
        ) as result:
            times = [result.time(index) for index in range(result.point_count)]
            found = {
                f"{edge:.12g}": any(abs(time_value - edge) <= 2.0e-15 for time_value in times)
                for edge in edges
            }
            high_index = min(range(len(times)), key=lambda index: abs(times[index] - 200.0e-6))
            low_index = min(range(len(times)), key=lambda index: abs(times[index] - 100.0e-6))
            high = result.node_voltage(high_index, "out")
            low = result.node_voltage(low_index, "out")
            expected_high = 10.0 * 10.0 / 11.0
            diagnostics = result.diagnostics()
            return {
                "passed": (
                    result.status == "converged" and all(found.values()) and
                    abs(high - expected_high) <= 1.0e-8 and abs(low) <= 2.0e-4 and
                    diagnostics["factorization_reuses"] >
                    diagnostics["matrix_factorizations"]
                ),
                "edge_alignment": found,
                "observed_high_voltage_v": high,
                "expected_high_voltage_v": expected_high,
                "observed_low_voltage_v": low,
                "diagnostics": diagnostics,
            }


def _synchronous_buck(library: NativeLibrary) -> Mapping[str, Any]:
    input_voltage = 24.0
    duty = 0.4
    stop = 2.0e-3
    period = 10.0e-6
    with library.circuit() as circuit:
        circuit.add_voltage_source("Vs", "vin", "0", input_voltage)
        for source, node, initial, pulsed in (
            ("Vgh", "gh", 0.0, 5.0), ("Vgl", "gl", 5.0, 0.0)
        ):
            circuit.add_pulse_voltage_source(
                source, node, "0", initial_value=initial,
                pulsed_value=pulsed, delay_s=0.0, rise_time_s=0.2e-6,
                fall_time_s=0.2e-6, pulse_width_s=3.6e-6,
                period_s=period,
            )
        for switch, positive, gate in (
            ("Sh", "vin", "gh"), ("Sl", "0", "gl")
        ):
            circuit.add_voltage_controlled_switch(
                switch, positive, "sw", gate, "0",
                on_resistance_ohm=0.1, off_resistance_ohm=1.0e6,
                threshold_voltage_v=2.5, transition_voltage_v=0.5,
            )
        circuit.add_inductor("L1", "sw", "out", 47.0e-6)
        circuit.add_capacitor("C1", "out", "0", 100.0e-6)
        circuit.add_resistor("Rload", "out", "0", 5.0)
        with circuit.solve_transient(
            time_step_s=0.5e-6, stop_time_s=stop,
            initialize_from_operating_point=False,
            integration_method="hybrid_trapezoidal",
            max_newton_iterations=200, max_backtracks=30,
        ) as result:
            window_start = stop - 10.0 * period
            samples = [
                (result.time(index), result.node_voltage(index, "out"))
                for index in range(result.point_count)
                if result.time(index) >= window_start
            ]
            times = [item[0] for item in samples]
            voltages = [item[1] for item in samples]
            average = _time_weighted_mean(times, voltages)
            ideal = duty * input_voltage
            relative_error = abs(average - ideal) / ideal
            ripple = max(voltages) - min(voltages)
            return {
                "passed": (
                    result.status == "converged" and relative_error <= 0.08 and
                    ripple <= 1.0 and min(voltages) >= 0.0 and
                    max(voltages) <= input_voltage
                ),
                "model": "synchronous smooth-switch buck; no dead time",
                "steady_window_s": [times[0], times[-1]],
                "time_weighted_output_v": average,
                "ideal_duty_output_v": ideal,
                "relative_error": relative_error,
                "peak_to_peak_ripple_v": ripple,
                "diagnostics": result.diagnostics(),
            }


@dataclass
class _NativePersistentRcPlant:
    library: NativeLibrary
    resistance_ohm: float = 1_000.0
    capacitance_f: float = 1.0e-6
    step_timings_ns: list[int] = field(default_factory=list)
    _session: NativeTransientSession | None = field(default=None, init=False)
    _checkpoints: dict[int, NativeTransientCheckpoint] = field(
        default_factory=dict, init=False
    )
    _next_checkpoint: int = field(default=1, init=False)

    def initialize(self, _block: CompiledBlock) -> Sequence[float]:
        if self._session is not None:
            raise RuntimeError("persistent native RC plant was initialized twice")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vdrive", "in", "0", 0.0)
            circuit.add_resistor("R1", "in", "out", self.resistance_ohm)
            circuit.add_capacitor("C1", "out", "0", self.capacitance_f)
            self._session = circuit.transient_session()
        return (0.0,)

    def step(
        self, _simulation_time_s: float, step_s: float,
        inputs: Sequence[float], previous_signals: Sequence[float],
    ) -> Sequence[float]:
        del previous_signals
        started = time.perf_counter_ns()
        drive = inputs[0] + inputs[1]
        if self._session is None:
            raise RuntimeError("persistent native RC plant is not initialized")
        self._session.set_source_value("Vdrive", drive)
        if not self._session.step(step_s):
            raise RuntimeError(self._session.message)
        values = (self._session.node_voltage("out"),)
        self.step_timings_ns.append(time.perf_counter_ns() - started)
        return values

    def checkpoint(self) -> int:
        if self._session is None:
            raise RuntimeError("persistent native RC plant is not initialized")
        checkpoint_id = self._next_checkpoint
        self._next_checkpoint += 1
        self._checkpoints[checkpoint_id] = self._session.checkpoint()
        return checkpoint_id

    def restore(self, state: Any) -> None:
        if self._session is None:
            raise RuntimeError("persistent native RC plant is not initialized")
        try:
            checkpoint = self._checkpoints[int(state)]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("unknown persistent native RC checkpoint") from exc
        self._session.restore(checkpoint)

    def close(self) -> None:
        for checkpoint in self._checkpoints.values():
            checkpoint.close()
        self._checkpoints.clear()
        if self._session is not None:
            self._session.close()
            self._session = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def _interactive_block(step_s: float) -> CompiledBlock:
    return CompiledBlock.build(
        "native_interactive_rc",
        (SignalDescriptor(0, "output_voltage", "V"),),
        (
            InputDescriptor(
                0, "drive", ControlType.SET, unit="V", minimum=-2.0,
                maximum=2.0, default_value=0.0, safe_value=0.0,
            ),
            InputDescriptor(
                1, "key_a", ControlType.MOMENTARY, unit="V",
                active_value=1.0, default_value=0.0, safe_value=0.0,
            ),
        ),
        nominal_step_s=step_s,
        metadata={"engine": "SPIKES C ABI", "execution": "persistent-native-session-v1"},
        implementation_fingerprint="native-persistent-rc-step-v1",
    )


def _be_rc(previous: float, drive: float, step_s: float, tau_s: float = 1.0e-3) -> float:
    ratio = step_s / tau_s
    return (previous + ratio * drive) / (1.0 + ratio)


def _interactive_control_and_replay(library: NativeLibrary) -> Mapping[str, Any]:
    step_s = 100.0e-6
    plant = _NativePersistentRcPlant(library)
    session = SimulationSession(_interactive_block(step_s), plant)
    session.start()
    session.apply_control("drive", 1.0)
    expected = 0.0
    for _ in range(10):
        expected = _be_rc(expected, 1.0, step_s)
    session.run_lockstep(10)
    first_error = abs(session.read("output_voltage") - expected)

    before_key = session.read("output_voltage")
    applied_at_step = session.step_index
    dispatch_started = time.perf_counter_ns()
    session.apply_control("key_a")
    control_dispatch_ns = time.perf_counter_ns() - dispatch_started
    session.step()
    expected_key = _be_rc(before_key, 2.0, step_s)
    key_error = abs(session.read(0) - expected_key)
    control_to_effect_steps = session.step_index - applied_at_step
    momentary_released = session.inputs[1] == 0.0

    checkpoint = session.checkpoint()
    session.apply_control("drive", -0.5)
    session.run_lockstep(5)
    first_replay = session.signals
    session.restore(checkpoint)
    session.start()
    session.apply_control("drive", -0.5)
    session.run_lockstep(5)
    replay_exact = session.signals == first_replay
    observation = {
        "passed": (
            first_error <= 2.0e-12 and key_error <= 2.0e-12 and
            control_to_effect_steps == 1 and momentary_released and replay_exact
        ),
        "initial_sequence_error_v": first_error,
        "momentary_key_error_v": key_error,
        "control_to_effect_steps": control_to_effect_steps,
        "control_dispatch_ns": control_dispatch_ns,
        "momentary_released": momentary_released,
        "checkpoint_replay_bit_exact": replay_exact,
        "stats": session.stats.to_dict(),
        "native_session_diagnostics": (
            plant._session.diagnostics() if plant._session is not None else {}
        ),
    }
    plant.close()
    return observation


def _continuous_pacing_observation(
    library: NativeLibrary, wall_steps: int
) -> Mapping[str, Any]:
    step_s = 2.0e-3
    plant = _NativePersistentRcPlant(library)
    session = SimulationSession(
        _interactive_block(step_s), plant, deadline_s=step_s
    )
    session.apply_control("drive", 1.0)
    session.start()
    started = time.perf_counter_ns()
    session.run_continuous(max_steps=wall_steps)
    elapsed = time.perf_counter_ns() - started
    target = wall_steps * step_s
    elapsed_s = elapsed / 1.0e9
    stats = session.stats.to_dict()
    compute = plant.step_timings_ns
    observation = {
        "passed": (
            session.step_index == wall_steps and elapsed_s >= 0.75 * target and
            elapsed_s <= max(1.0, 10.0 * target)
        ),
        "steps": wall_steps,
        "target_wall_duration_s": target,
        "observed_wall_duration_s": elapsed_s,
        "deadline_s": step_s,
        "compute_latency_ns": {
            "minimum": min(compute),
            "median": int(statistics.median(compute)),
            "p95": _percentile(compute, 0.95),
            "maximum": max(compute),
            "p95_deadline_utilization": _percentile(compute, 0.95) / (step_s * 1.0e9),
        },
        "stats": stats,
        "hard_realtime_qualified": False,
        "hil_qualified": False,
    }
    plant.close()
    return observation


def _deadline_trip() -> Mapping[str, Any]:
    clock = VirtualClockScheduler()
    block = CompiledBlock.build(
        "deadline_trip_reference",
        (SignalDescriptor(0, "state"),),
        (InputDescriptor(
            0, "drive", ControlType.SET, default_value=1.0,
            safe_value=0.0,
        ),),
        nominal_step_s=1.0e-3,
        implementation_fingerprint="deadline-trip-v1",
    )

    def slow_step(_time: float, dt: float, inputs: Sequence[float], signals: Sequence[float]):
        clock.advance_ns(2_000_000)
        return (signals[0] + dt * inputs[0],)

    session = SimulationSession(
        block, FunctionalPlant((0.0,), slow_step), deadline_s=1.0e-3,
        trip_after_consecutive_overruns=2,
    )
    session.start()
    session.run_lockstep(3, scheduler=clock)
    safe_trip_event = any(event.kind == "safe_trip" for event in session.events)
    return {
        "passed": (
            session.lifecycle is Lifecycle.TRIPPED and session.inputs == (0.0,) and
            session.stats.deadline_overruns == 2 and safe_trip_event
        ),
        "lifecycle": session.lifecycle.value,
        "safe_inputs": list(session.inputs),
        "safe_trip_event": safe_trip_event,
        "stats": session.stats.to_dict(),
    }


def run_qualification_suite(
    library_path: str | Path,
    *,
    repetitions: int = 3,
    wall_steps: int = 20,
) -> dict[str, Any]:
    """Run the bounded corpus and return one claim-controlled JSON report."""

    if isinstance(repetitions, bool) or not 1 <= int(repetitions) <= MAX_REPETITIONS:
        raise ValueError(f"repetitions must be from 1 through {MAX_REPETITIONS}")
    if isinstance(wall_steps, bool) or not 1 <= int(wall_steps) <= MAX_WALL_STEPS:
        raise ValueError(f"wall_steps must be from 1 through {MAX_WALL_STEPS}")
    repetitions = int(repetitions)
    wall_steps = int(wall_steps)
    library = load_native_library(library_path)
    library_sha256 = hashlib.sha256(library.path.read_bytes()).hexdigest()
    cases = [
        _case("dc.balanced_bridge", "Balanced loaded Wheatstone bridge", "dc_linear",
              "matched divider ratios produce zero bridge voltage", repetitions,
              lambda: _balanced_bridge(library)),
        _case("dc.large_resistor_ladder", "200-section resistor ladder", "dc_scale",
              "interior voltage follows the closed-form linear divider", repetitions,
              lambda: _large_resistor_ladder(library)),
        _case("dc.threaded_cg_ladder", "Threaded 200-section SPD ladder", "dc_iterative",
              "preconditioned CG matches the closed form using two workers", repetitions,
              lambda: _threaded_cg_ladder(library)),
        _case("dc.sparse_solver_ladder", "Sparse 1000-section MNA ladder", "dc_sparse",
              "sparse LU and ILU-GMRES agree while retaining linear structural storage",
              repetitions, lambda: _sparse_solver_ladder(library)),
        _case("dc.gmres_controlled_switch", "GMRES controlled-switch MNA", "dc_iterative",
              "restarted GMRES matches pivoted LU on a nonsymmetric Newton system", repetitions,
              lambda: _gmres_controlled_switch(library)),
        _case("dc.shockley_diode", "Nonlinear Shockley operating point", "dc_nonlinear",
              "junction voltage matches the analytic diode law", repetitions,
              lambda: _shockley_diode(library)),
        _case("transient.series_rlc", "Underdamped series-RLC step", "transient_linear",
              "capacitor voltage matches the second-order closed form", repetitions,
              lambda: _underdamped_series_rlc(library)),
        _case("rf.series_resonator", "50 MHz-class series resonator", "rf",
              "high-frequency tank response matches the damped closed form", repetitions,
              lambda: _rf_series_resonator(library)),
        _case("motor.fixed_speed_armature", "Fixed-speed motor armature", "motor",
              "R-L current and torque match the fixed-back-EMF closed form", repetitions,
              lambda: _motor_armature_fixed_speed(library)),
        _case("switching.pwm_resistive", "Breakpoint-aligned PWM switch", "switching",
              "all edges are exact and on/off levels match the circuit", repetitions,
              lambda: _pwm_resistive_switch(library)),
        _case("switching.synchronous_buck", "Synchronous buck steady-state window", "converter",
              "bounded output settles near duty-ratio conversion with low ripple", repetitions,
              lambda: _synchronous_buck(library)),
        _case("interactive.native_control_replay", "Native closed-loop control and replay", "interactive",
              "controls affect the next native step and checkpoint replay is exact", 1,
              lambda: _interactive_control_and_replay(library)),
        _case("realtime.continuous_pacing", "Best-effort continuous native pacing", "soft_realtime",
              "bounded continuous mode advances every requested native step", 1,
              lambda: _continuous_pacing_observation(library, wall_steps)),
        _case("realtime.deadline_trip", "Deterministic deadline safety trip", "soft_realtime_safety",
              "two consecutive deadline overruns force safe inputs", 1, _deadline_trip),
    ]
    passed = sum(item["status"] == "passed" for item in cases)
    circuit_categories = {
        "dc_linear", "dc_scale", "dc_iterative", "dc_sparse", "dc_nonlinear", "transient_linear",
        "switching", "converter", "rf", "motor",
    }
    return {
        "contract": QUALIFICATION_REPORT_CONTRACT,
        "status": "passed" if passed == len(cases) else "failed",
        "engine_id": "spikes.owned_cpp_kernel",
        "library": str(library.path),
        "library_sha256": library_sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "configuration": {"repetitions": repetitions, "wall_steps": wall_steps},
        "summary": {"total": len(cases), "passed": passed, "failed": len(cases) - passed},
        "cases": cases,
        "claims": [],
        "qualification": {
            "analytical_circuit_behaviors": all(
                item["status"] == "passed" for item in cases
                if item["category"] in circuit_categories
            ),
            "soft_realtime_functionally_tested": all(
                item["status"] == "passed" for item in cases
                if item["category"].startswith("soft_realtime") or item["category"] == "interactive"
            ),
            "hard_realtime_qualified": False,
            "hil_qualified": False,
            "competitive_speed_claim_eligible": False,
        },
        "limitations": [
            "Timings apply only to this host, library, workload, and timing scope.",
            "The synchronous-buck case uses smooth controlled switches and is not a qualified semiconductor loss model.",
            "The RF fixture is a lumped RLC resonator; it does not qualify distributed, EM, or radiation physics.",
            "The motor fixture holds speed/back-EMF fixed; it does not qualify a coupled rotor-mechanical or magnetic field model.",
            "Persistent session v1 reassembles each dense step but reuses bounded full-matrix-keyed LU factorizations when coefficients are unchanged.",
            "Continuous pacing uses a general-purpose OS and Python orchestration; it is not deterministic WCET evidence.",
            "No physical I/O latency, jitter, fault injection, or HIL hardware is exercised.",
            "No competitive superiority is inferred from these measurements.",
        ],
    }


__all__ = [
    "QUALIFICATION_CASE_CONTRACT",
    "QUALIFICATION_REPORT_CONTRACT",
    "run_qualification_suite",
]
