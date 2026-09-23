# SPDX-License-Identifier: MIT
import unittest
from unittest.mock import patch

from python.spike_core.service_simulation_handlers import handle_simulation_request


class _SolverRegistry:
    def run(self, _design, _spec):
        raise AssertionError("the registry must not run without a design")


class SimulationServiceHandlerTests(unittest.TestCase):
    def test_unhandled_method_returns_none(self):
        self.assertIsNone(handle_simulation_request(
            "not_a_simulation_method", {}, assembly_scope={}, solver_registry=_SolverRegistry(),
        ))

    def test_run_analysis_without_design_remains_a_structured_blocked_result(self):
        response = handle_simulation_request(
            "run_analysis",
            {"spec": {"analysis_id": "analysis-1", "mode": "dc"}},
            assembly_scope={},
            solver_registry=_SolverRegistry(),
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "blocked")
        self.assertEqual(response["result"]["issues"][0]["code"], "DESIGN_CONTEXT_REQUIRED")

    @patch("python.spike_core.service_simulation_handlers.execute_thermal_field_job")
    def test_thermal_field_execution_uses_only_host_injected_adapters(self, execute):
        execute.return_value = {"contract": "spike/thermal-field-result/v1", "status": "blocked"}
        host_adapters = {"external.test": object()}
        request = {"contract": "spike/thermal-field-job-request/v1", "solver_selection": {"solver_id": "external.test"}}
        response = handle_simulation_request(
            "execute_thermal_field_job",
            {"request": request, "adapter_registry": {"untrusted.client": object()}},
            assembly_scope={}, solver_registry=_SolverRegistry(), thermal_adapter_registry=host_adapters,
        )
        self.assertTrue(response["ok"])
        execute.assert_called_once_with(request, adapter_registry=host_adapters)

    @patch("python.spike_core.service_simulation_handlers.write_case_scope")
    @patch("python.spike_core.service_simulation_handlers.prepare_case")
    def test_prepared_thermal_case_keeps_scope_commit_and_provenance(self, prepare_case, write_scope):
        prepare_case.return_value = {"status": "prepared", "case_dir": "case-a"}
        response = handle_simulation_request(
            "prepare_thermal_case",
            {"scenario": {"scenario_id": "thermal-1"}, "output_dir": "out-a"},
            assembly_scope={},
            solver_registry=_SolverRegistry(),
        )
        self.assertTrue(response["ok"])
        write_scope.assert_called_once_with("case-a", {})


if __name__ == "__main__":
    unittest.main()
