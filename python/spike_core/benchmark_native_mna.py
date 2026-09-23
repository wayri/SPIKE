"""Native linear-MNA reference benchmarks used by the solver benchmark corpus."""

from __future__ import annotations

from math import pi, sqrt
from typing import TYPE_CHECKING, Callable

from .native_mna import REQUEST_CONTRACT as MNA_REQUEST_CONTRACT, run_native_mna

if TYPE_CHECKING:
    from .benchmarks import Benchmark


ResultFactory = Callable[[str, float, float, float, str, str], "Benchmark"]


def run_native_mna_reference_benchmarks(result_factory: ResultFactory) -> list["Benchmark"]:
    """Return the native-MNA references in their stable corpus order."""

    return [
        _native_mna_dc_benchmark(result_factory),
        _native_mna_ac_benchmark(result_factory),
        _native_mna_transient_benchmark(result_factory),
    ]


def _native_mna_dc_benchmark(result_factory: ResultFactory) -> "Benchmark":
    result = run_native_mna({
        "contract": MNA_REQUEST_CONTRACT,
        "request_id": "benchmark-mna-dc-divider",
        "ground_node": "0",
        "elements": [
            {"id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0", "dc_value": 10.0},
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "vout", "resistance_ohm": 1000.0},
            {"id": "R2", "type": "resistor", "positive_node": "vout", "negative_node": "0", "resistance_ohm": 1000.0},
        ],
        "analysis": {"mode": "operating_point"},
    })
    measured = float((result.get("data") or {}).get("node_voltage_v", {}).get("vout", float("nan")))
    return result_factory(
        "native_mna_dc_voltage_divider_reference",
        measured,
        5.0,
        1e-12,
        "volt",
        "Independent closed-form 1:1 resistive divider reference for native linear MNA.",
    )


def _native_mna_ac_benchmark(result_factory: ResultFactory) -> "Benchmark":
    resistance = 1000.0
    capacitance = 1e-6
    corner_hz = 1.0 / (2.0 * pi * resistance * capacitance)
    result = run_native_mna({
        "contract": MNA_REQUEST_CONTRACT,
        "request_id": "benchmark-mna-ac-rc",
        "ground_node": "0",
        "elements": [
            {"id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0", "ac_magnitude": 1.0},
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "vout", "resistance_ohm": resistance},
            {"id": "C1", "type": "capacitor", "positive_node": "vout", "negative_node": "0", "capacitance_f": capacitance},
        ],
        "analysis": {"mode": "ac", "start_hz": corner_hz, "stop_hz": corner_hz, "points": 1, "scale": "log"},
    })
    series = ((result.get("data") or {}).get("node_voltage_v", {}).get("vout") or {})
    measured = float((series.get("magnitude") or [float("nan")])[0])
    return result_factory(
        "native_mna_ac_rc_corner_reference",
        measured,
        1.0 / sqrt(2.0),
        1e-10,
        "volt/volt",
        "Independent first-order RC transfer magnitude at the analytical -3 dB corner.",
    )


def _native_mna_transient_benchmark(result_factory: ResultFactory) -> "Benchmark":
    resistance = 1000.0
    capacitance = 1e-6
    step_s = 1e-5
    stop_s = 1e-3
    result = run_native_mna({
        "contract": MNA_REQUEST_CONTRACT,
        "request_id": "benchmark-mna-transient-rc",
        "ground_node": "0",
        "elements": [
            {
                "id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0",
                "waveform": {"type": "step", "initial": 0.0, "final": 1.0, "delay_s": 0.0},
            },
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "vout", "resistance_ohm": resistance},
            {"id": "C1", "type": "capacitor", "positive_node": "vout", "negative_node": "0", "capacitance_f": capacitance},
        ],
        "analysis": {"mode": "transient", "time_step_s": step_s, "stop_time_s": stop_s},
    })
    measured = float(((result.get("data") or {}).get("node_voltage_v", {}).get("vout") or [float("nan")])[-1])
    # The native transient contract returns the first backward-Euler state at
    # t=0, followed by one state for every configured interval.
    steps = int(round(stop_s / step_s)) + 1
    expected = 1.0 - (1.0 / (1.0 + step_s / (resistance * capacitance))) ** steps
    return result_factory(
        "native_mna_transient_rc_backward_euler_reference",
        measured,
        expected,
        1e-12,
        "volt",
        "Closed-form discrete backward-Euler RC step response using the solver contract's t=0 state.",
    )
