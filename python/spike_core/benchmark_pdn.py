"""PDN circuit-reference benchmark used by the solver benchmark corpus."""

from __future__ import annotations

from math import pi
from typing import TYPE_CHECKING, Callable, Dict

import numpy as np

from .pdn import review_pdn

if TYPE_CHECKING:
    from .benchmarks import Benchmark


ResultFactory = Callable[[str, float, float, float, str, str], "Benchmark"]
BenchmarkFactory = Callable[..., "Benchmark"]


def run_pdn_two_port_loading_benchmark(
    result_factory: ResultFactory,
    benchmark_factory: BenchmarkFactory,
) -> "Benchmark":
    """Compare PDN two-port loading with an independent nodal re-solve."""

    frequencies = np.geomspace(1e3, 1e8, 17)
    baseline: list[complex] = []
    local: list[complex] = []
    transfer: list[complex] = []
    directly_loaded: list[complex] = []
    capacitance_f = 47e-6
    capacitor_esr_ohm = 8e-3
    capacitor_esl_h = 0.6e-9
    mounting_resistance_ohm = 2e-3
    mounting_inductance_h = 0.3e-9

    for frequency in frequencies:
        omega = 2 * pi * float(frequency)
        observation_shunt = complex(0.08, omega * 3e-9)
        candidate_shunt = complex(0.12, omega * 4e-9)
        connection = complex(0.01, omega * 1e-9)
        admittance = np.array([
            [1 / observation_shunt + 1 / connection, -1 / connection],
            [-1 / connection, 1 / candidate_shunt + 1 / connection],
        ], dtype=complex)
        impedance = np.linalg.inv(admittance)
        baseline.append(complex(impedance[0, 0]))
        local.append(complex(impedance[1, 1]))
        transfer.append(complex(impedance[0, 1]))

        capacitor = complex(
            capacitor_esr_ohm + mounting_resistance_ohm,
            omega * (capacitor_esl_h + mounting_inductance_h)
            - 1 / (omega * capacitance_f),
        )
        loaded_admittance = admittance.copy()
        loaded_admittance[1, 1] += 1 / capacitor
        directly_loaded.append(complex(np.linalg.inv(loaded_admittance)[0, 0]))

    result = {
        "model_status": "validated",
        "networks": {"parasitics": [{
            "net": "VCC",
            "model_status": "validated",
            "impedance": [
                _impedance_point(frequency, value)
                for frequency, value in zip(frequencies, baseline)
            ],
        }]},
    }
    candidate = {
        "id": "C1-two-port",
        "capacitance_f": capacitance_f,
        "esr_ohm": capacitor_esr_ohm,
        "esl_h": capacitor_esl_h,
        "mounting_resistance_ohm": mounting_resistance_ohm,
        "mounting_inductance_h": mounting_inductance_h,
        "source_result_id": "analytical-two-node-nodal-reference",
        "endpoint_reviewed": True,
        "reciprocal": True,
        "model_status": "validated",
        "local_impedance": [
            _impedance_point(frequency, value)
            for frequency, value in zip(frequencies, local)
        ],
        "transfer_impedance": [
            _impedance_point(frequency, value)
            for frequency, value in zip(frequencies, transfer)
        ],
    }
    report = review_pdn(result, target_ohm=0.2, net="VCC", candidates=[candidate])
    screened = report["candidate_screening"][0]
    predicted = [
        complex(point["resistance_ohm"], point["reactance_ohm"])
        for point in screened.get("response", [])
    ]
    if screened.get("status") != "evaluated" or len(predicted) != len(directly_loaded):
        return benchmark_factory(
            "pdn_two_port_capacitor_loading_circuit_reference",
            "failed",
            None,
            0.0,
            None,
            1e-10,
            "relative",
            f"candidate_status={screened.get('status')}; issues={screened.get('issues', [])}",
        )
    errors = [
        abs(actual - expected) / max(abs(expected), 1e-30)
        for actual, expected in zip(predicted, directly_loaded)
    ]
    maximum_error = float(max(errors))
    tolerance = 1e-10
    return benchmark_factory(
        "pdn_two_port_capacitor_loading_circuit_reference",
        "passed" if maximum_error <= tolerance else "failed",
        maximum_error,
        0.0,
        maximum_error,
        tolerance,
        "relative",
        (
            "Compared the multiport loading response against an independent passive "
            f"two-node nodal re-solve at {len(frequencies)} frequencies; this validates "
            "the circuit reduction only, not PCB multiport extraction or placement accuracy."
        ),
    )


def _impedance_point(frequency_hz: float, value: complex) -> Dict[str, float]:
    return {
        "frequency_hz": float(frequency_hz),
        "resistance_ohm": float(value.real),
        "reactance_ohm": float(value.imag),
    }
