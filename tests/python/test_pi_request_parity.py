"""Regression coverage for equivalent PI request execution across transports."""

from __future__ import annotations

import math
import unittest
from typing import Any

from python.spike_core.cli import execute_request
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.service import handle


class PiRequestParityTests(unittest.TestCase):
    """The CLI must remain a thin transport over the local worker contract."""

    def test_cli_and_service_run_have_equivalent_dc_pi_results(self) -> None:
        request = self._request()

        cli_result = execute_request(request)
        service_preflight = handle({
            "method": "preflight_analysis",
            "params": {"design": request["design"], "spec": request["spec"]},
        })
        service_run = handle({
            "method": "run_analysis",
            "params": {"design": request["design"], "spec": request["spec"]},
        })

        self.assertTrue(service_preflight["ok"])
        self.assertTrue(service_preflight["result"]["can_solve"])
        self.assertTrue(service_run["ok"])
        service_result = service_run["result"]

        self.assertEqual(cli_result["status"], service_result["status"])
        self.assertEqual(cli_result["model_status"], service_result["model_status"])
        self.assertEqual(self._issue_codes(cli_result), self._issue_codes(service_result))
        self.assertEqual(
            self._solver_identity(cli_result),
            self._solver_identity(service_result),
        )
        self._assert_equivalent_summary(cli_result["summary"], service_result["summary"])

    @staticmethod
    def _request() -> dict[str, Any]:
        design = DesignIR(
            name="PI request parity fixture",
            source_format="fixture",
            metadata={"source_embedded": True},
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "track-1",
                "start": [0.0, 0.0],
                "end": [10.0, 0.0],
                "width": 1.0,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        spec = AnalysisSpec(
            analysis_id="pi-request-parity",
            mode="dc",
            net_names=["VCC"],
            sources=[{"position_mm": [0.0, 0.0], "layer": "F.Cu", "voltage_v": 5.0}],
            loads=[{"position_mm": [10.0, 0.0], "layer": "F.Cu", "current_a": 1.0}],
            mesh={"target_size_mm": 1.0},
        )
        return {
            "contract": "spike/analysis-request/v1",
            "design": design.to_dict(),
            "spec": spec.to_dict(),
        }

    @staticmethod
    def _issue_codes(result: dict[str, Any]) -> list[str]:
        return [str(issue.get("code", "")) for issue in result.get("issues", [])]

    @staticmethod
    def _solver_identity(result: dict[str, Any]) -> tuple[str, str]:
        provenance = result.get("provenance", {})
        return str(provenance.get("solver", "")), str(provenance.get("formulation", ""))

    def _assert_equivalent_summary(
        self,
        cli_summary: dict[str, Any],
        service_summary: dict[str, Any],
    ) -> None:
        excluded = {
            "mesh_build_time_s",
            "matrix_assembly_time_s",
            "linear_solve_time_s",
            "total_solver_time_s",
        }
        self.assertEqual(set(cli_summary) - excluded, set(service_summary) - excluded)
        for key in sorted(set(cli_summary) - excluded):
            with self.subTest(metric=key):
                self._assert_value_equal(cli_summary[key], service_summary[key])

    def _assert_value_equal(self, first: Any, second: Any) -> None:
        if isinstance(first, float) or isinstance(second, float):
            self.assertTrue(math.isclose(float(first), float(second), rel_tol=1e-12, abs_tol=1e-15))
        else:
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
