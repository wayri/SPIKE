import threading
import unittest
from unittest.mock import patch

from python.spike_core.contracts import DesignIR
from python.spike_core.field_circuit_cosim import (
    FIELD_RESULT_CONTRACT,
    REQUEST_CONTRACT,
    run_iterative_field_circuit_cosimulation,
    validate_field_circuit_request,
)
from tests.python.test_native_circuit_compiler import design, workspace


def request(**overrides):
    value = {
        "contract": REQUEST_CONTRACT,
        "request_id": "fixture-coupling",
        "maximum_iterations": 8,
        "minimum_iterations": 2,
        "relaxation": 0.5,
        "parameter_relative_tolerance": 1e-6,
        "circuit_relative_tolerance": 1e-6,
        "absolute_floor": 1e-18,
        "time_limit_s": 30.0,
        "resource_limits": {"memory_limit_gb": 2.0},
    }
    value.update(overrides)
    return value


def coupled_workspace():
    candidate = workspace()
    candidate["assignments"][1]["pin_bindings"][0]["circuit_node"] = "LOAD"
    candidate["parasitics"] = [{
        "id": "path", "enabled": True, "endpoint_reviewed": True,
        "from_node": "VIN", "to_node": "LOAD", "reference_node": "GND",
        "resistance_ohm": 0.1, "inductance_h": 1e-9,
        "capacitance_f": 1e-12, "conductance_s": 1e-9,
    }]
    return candidate


def response(item, resistance):
    return {
        "contract": FIELD_RESULT_CONTRACT,
        "status": "completed",
        "provider": "analytical.test.fixture",
        "parasitics": [{
            "id": item["parasitics"][0]["id"],
            "resistance_ohm": resistance,
            "inductance_h": item["parasitics"][0]["inductance_h"],
            "capacitance_f": item["parasitics"][0]["capacitance_f"],
            "conductance_s": item["parasitics"][0]["conductance_s"],
        }],
        "diagnostics": {"fixture": True},
    }


class FieldCircuitCosimulationTests(unittest.TestCase):
    def test_request_validation_is_fail_closed(self):
        invalid = request(relaxation=1.5)
        result = validate_field_circuit_request(invalid)
        self.assertFalse(result["valid"])
        self.assertEqual(result["issues"][0]["code"], "SPIKE-BE-SPICE-E-0041")

        fractional = validate_field_circuit_request(request(maximum_iterations=2.5))
        self.assertFalse(fractional["valid"])
        self.assertEqual(fractional["issues"][0]["path"], "maximum_iterations")

        malformed_limits = validate_field_circuit_request(request(
            circuit_engine="owned_spice", owned_spice_limits=[],
        ))
        self.assertFalse(malformed_limits["valid"])
        self.assertEqual(malformed_limits["issues"][0]["path"], "owned_spice_limits")

    def test_requires_an_explicit_field_provider(self):
        result = run_iterative_field_circuit_cosimulation(
            design(), coupled_workspace(), request(), None,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["issues"][0]["code"], "SPIKE-BE-SOLVER-E-0001")

    def test_converges_and_preserves_reviewed_topology(self):
        calls = []

        def provider(item):
            calls.append(item)
            return response(item, 0.2)

        result = run_iterative_field_circuit_cosimulation(
            design(),
            coupled_workspace(),
            request(
                relaxation=1.0,
                parameter_relative_tolerance=1e-12,
                circuit_relative_tolerance=1e-12,
            ),
            provider,
        )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["converged"])
        self.assertEqual(result["iteration_count"], 3)
        self.assertEqual(len(calls), 3)
        self.assertAlmostEqual(result["workspace"]["parasitics"][0]["resistance_ohm"], 0.2)
        self.assertEqual(result["circuit"]["analysis_result"]["mode"], "dc")
        self.assertFalse(result["provenance"]["topology_changes_allowed"])

    def test_release_owned_spice_engine_executes_inside_field_iteration(self):
        def provider(item):
            return response(item, 0.2)

        result = run_iterative_field_circuit_cosimulation(
            design(),
            coupled_workspace(),
            request(
                circuit_engine="owned_spice",
                circuit_probes=[],
                relaxation=1.0,
                parameter_relative_tolerance=1e-12,
                circuit_relative_tolerance=1e-12,
            ),
            provider,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["provenance"]["circuit_engine"], "owned_spice")
        self.assertEqual(
            result["circuit"]["result"]["contract"], "spikes/circuit-result/v1",
        )
        self.assertTrue(
            result["circuit"]["owned_bridge"]["provenance"]["structured_workspace_only"],
        )

    def test_owned_circuit_stage_exception_is_a_structured_failure(self):
        provider_called = False

        def provider(item):
            nonlocal provider_called
            provider_called = True
            return response(item, 0.2)

        with patch(
            "python.spike_core.field_circuit_cosim.run_owned_spice_workspace",
            side_effect=RuntimeError("owned circuit integrity failure"),
        ):
            result = run_iterative_field_circuit_cosimulation(
                design(), coupled_workspace(), request(circuit_engine="owned_spice"), provider,
            )
        self.assertEqual(result["status"], "failed")
        self.assertFalse(provider_called)
        self.assertEqual(result["issues"][0]["path"], "circuit")

    def test_rejects_field_topology_changes(self):
        def provider(item):
            candidate = response(item, 0.2)
            candidate["parasitics"][0]["id"] = "different"
            return candidate

        result = run_iterative_field_circuit_cosimulation(
            design(), coupled_workspace(), request(), provider,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["issues"][0]["code"], "SPIKE-BE-SPICE-E-0042")

    def test_nonconvergence_and_cancellation_are_explicit(self):
        def oscillating(item):
            resistance = 0.2 if item["iteration"] % 2 else 0.1
            return response(item, resistance)

        failed = run_iterative_field_circuit_cosimulation(
            design(),
            coupled_workspace(),
            request(maximum_iterations=3, minimum_iterations=2, relaxation=1.0),
            oscillating,
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["issues"][0]["code"], "SPIKE-BE-SOLVER-E-0002")

        cancellation = threading.Event()
        cancellation.set()
        cancelled = run_iterative_field_circuit_cosimulation(
            design(), coupled_workspace(), request(), oscillating, cancellation_event=cancellation,
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["issues"][0]["code"], "SPIKE-BE-SOLVER-E-0003")

    def test_worker_exposes_validation_and_native_provider_execution(self):
        from python.spike_core.service import handle

        result = handle({"method": "validate_field_circuit_cosimulation", "params": {"request": request()}})
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["valid"])

        def provider(item):
            return response(item, 0.1)

        with patch(
            "python.spike_core.service.NativePeecFieldReductionProvider",
            return_value=provider,
        ):
            executed = handle({
                "method": "run_field_circuit_cosimulation",
                "params": {
                    "design": design().to_dict(),
                    "workspace": coupled_workspace(),
                    "request": request(),
                    "field_analysis_spec": {"analysis_id": "peec-ac-1", "mode": "ac"},
                },
            })
        self.assertTrue(executed["ok"])
        self.assertEqual(executed["result"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
