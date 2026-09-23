import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
import contextlib

from python.spike_core.cli import EXIT_ANALYSIS, EXIT_OK, main
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.convergence import run_mesh_convergence
from python.spike_core.solver_plugins import default_solver_registry


class MeshConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.design = DesignIR(
            name="convergence trace",
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{"id": "t1", "start": [0, 0], "end": [20, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        self.spec = AnalysisSpec(
            analysis_id="convergence-test",
            mode="dc",
            net_names=["VCC"],
            sources=[{"position_mm": [0, 0], "layer": "F.Cu", "net": "VCC", "voltage_v": 5}],
            loads=[{"position_mm": [20, 0], "layer": "F.Cu", "net": "VCC", "current_a": 1}],
            mesh={"target_size_mm": 2, "zone_cell_mm": 2, "max_conductors": 1000},
        )

    def test_dc_convergence_returns_fine_result_and_signoff(self):
        report = run_mesh_convergence(self.design, self.spec, default_solver_registry().run)
        self.assertEqual(report["contract"], "spike/mesh-convergence/v1")
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["can_sign_off"])
        self.assertEqual(len(report["levels"]), 3)
        self.assertEqual(report["result"]["summary"]["mesh_convergence_status"], "passed")
        self.assertTrue(any(issue["code"] == "MESH_CONVERGENCE_PASSED" for issue in report["result"]["issues"]))

    def test_invalid_refinement_order_is_rejected(self):
        with self.assertRaises(ValueError):
            run_mesh_convergence(self.design, self.spec, default_solver_registry().run, levels=[1, 2])

    def test_cli_convergence_uses_same_contract(self):
        request = {"contract": "spike/analysis-request/v1", "design": self.design.to_dict(), "spec": self.spec.to_dict()}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["converge", str(path)])
            report = json.loads(output.getvalue())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(report["status"], "passed")

    def test_too_strict_tolerance_fails_signoff(self):
        # Inject a deterministic runner whose metric changes with mesh size.
        def runner(_design, spec):
            target = float(spec.mesh["target_size_mm"])
            from python.spike_core.contracts import AnalysisResult
            return AnalysisResult(
                status="completed",
                mode="dc",
                summary={
                    "max_load_voltage_drop_v": target,
                    "max_voltage_drop_v": target,
                    "total_copper_loss_w": target,
                    "total_load_current_a": 1,
                    "max_current_density_a_mm2": target,
                    "node_count": int(100 / target),
                    "edge_count": int(200 / target),
                },
            )

        report = run_mesh_convergence(self.design, self.spec, runner, metric_tolerance=0.001, density_tolerance=0.001)
        self.assertEqual(report["status"], "failed_to_converge")
        self.assertFalse(report["can_sign_off"])

    def test_mesh_sensitive_raw_peak_is_advisory_when_robust_density_converges(self):
        def runner(_design, spec):
            target = float(spec.mesh["target_size_mm"])
            from python.spike_core.contracts import AnalysisResult
            return AnalysisResult(
                status="completed",
                mode="dc",
                summary={
                    "max_load_voltage_drop_v": 0.01,
                    "max_voltage_drop_v": 0.01,
                    "total_copper_loss_w": 0.01,
                    "total_load_current_a": 1,
                    "p95_current_density_a_mm2": 2.0,
                    "max_current_density_a_mm2": 10.0 / target,
                    "node_count": int(100 / target),
                    "edge_count": int(200 / target),
                },
            )

        report = run_mesh_convergence(self.design, self.spec, runner)
        peak = next(item for item in report["comparisons"] if item["metric"] == "max_current_density_a_mm2")
        self.assertEqual(report["status"], "passed")
        self.assertFalse(peak["required"])
        self.assertEqual(peak["status"], "failed")
        self.assertTrue(any(
            issue["code"] == "CURRENT_DENSITY_PEAK_MESH_SENSITIVE"
            for issue in report["result"]["issues"]
        ))

    def test_adaptive_study_uses_extra_level_after_unstable_comparison(self):
        calls = []

        def runner(_design, spec):
            target = float(spec.mesh["target_size_mm"])
            calls.append(target)
            stable = 1.0 if target <= 0.5 else target
            from python.spike_core.contracts import AnalysisResult
            return AnalysisResult(
                status="completed",
                mode="dc",
                summary={
                    "max_load_voltage_drop_v": stable,
                    "max_voltage_drop_v": stable,
                    "total_copper_loss_w": stable,
                    "total_load_current_a": 1,
                    "p95_current_density_a_mm2": stable,
                    "max_current_density_a_mm2": stable,
                    "node_count": int(100 / target),
                    "edge_count": int(200 / target),
                },
            )

        report = run_mesh_convergence(
            self.design,
            self.spec,
            runner,
            levels=[2, 1, 0.5, 0.25],
            minimum_levels=3,
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(report["levels"]), 4)

    def test_near_zero_voltage_drop_can_pass_a_bounded_absolute_tolerance(self):
        values = iter((20e-6, 30e-6, 40e-6))
        counts = iter((100, 200, 400))

        def runner(_design, _spec):
            value = next(values)
            from python.spike_core.contracts import AnalysisResult
            return AnalysisResult(
                status="completed",
                mode="dc",
                summary={
                    "max_load_voltage_drop_v": value,
                    "max_voltage_drop_v": value,
                    "total_copper_loss_w": 0.01,
                    "total_load_current_a": 1,
                    "p95_current_density_a_mm2": 2.0,
                    "max_current_density_a_mm2": 2.0,
                    "node_count": (count := next(counts)),
                    "edge_count": count * 2,
                },
            )

        report = run_mesh_convergence(self.design, self.spec, runner)
        voltage = next(item for item in report["comparisons"] if item["metric"] == "max_load_voltage_drop_v")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(voltage["pass_basis"], "absolute")
        self.assertLessEqual(voltage["absolute_delta"], voltage["absolute_tolerance"])

    def test_unchanged_solved_network_cannot_sign_off(self):
        from python.spike_core.contracts import AnalysisResult

        def runner(_design, _spec):
            return AnalysisResult(status="completed", mode="dc", summary={
                "max_voltage_drop_v": 0.01,
                "max_load_voltage_drop_v": 0.01,
                "total_copper_loss_w": 0.01,
                "total_load_current_a": 1,
                "p95_current_density_a_mm2": 2,
                "node_count": 100,
                "edge_count": 200,
            })

        report = run_mesh_convergence(self.design, self.spec, runner)
        self.assertEqual(report["status"], "failed_to_converge")
        growth = next(item for item in report["comparisons"] if item["metric"] == "resolved_mesh_growth")
        self.assertEqual(growth["status"], "failed")

    def test_failed_later_level_revokes_earlier_convergence(self):
        from python.spike_core.contracts import AnalysisResult
        calls = 0

        def runner(_design, _spec):
            nonlocal calls
            calls += 1
            if calls == 4:
                return AnalysisResult(status="failed", mode="dc", summary={})
            return AnalysisResult(status="completed", mode="dc", summary={
                "max_voltage_drop_v": 0.01,
                "max_load_voltage_drop_v": 0.01,
                "total_copper_loss_w": 0.01,
                "total_load_current_a": 1,
                "p95_current_density_a_mm2": 2,
                "node_count": calls * 100,
                "edge_count": calls * 200,
            })

        report = run_mesh_convergence(
            self.design, self.spec, runner,
            levels=[2, 1, 0.5, 0.25], stop_when_converged=False,
        )
        self.assertEqual(report["status"], "failed_to_converge")
        self.assertFalse(report["can_sign_off"])
        self.assertEqual(len(report["comparison_history"]), 2)
        self.assertEqual(report["levels"][-1]["status"], "failed")

    def test_missing_required_density_is_unavailable_for_signoff(self):
        from python.spike_core.contracts import AnalysisResult
        calls = 0

        def runner(_design, _spec):
            nonlocal calls
            calls += 1
            return AnalysisResult(status="completed", mode="dc", summary={
                "max_load_voltage_drop_v": 0.01,
                "max_voltage_drop_v": 0.01,
                "total_copper_loss_w": 0.01,
                "total_load_current_a": 1,
                "max_current_density_a_mm2": 2,
                "node_count": calls * 100,
                "edge_count": calls * 200,
            })

        report = run_mesh_convergence(self.design, self.spec, runner)
        density = next(item for item in report["comparisons"] if item["metric"] == "p95_current_density_a_mm2")
        self.assertEqual(density["status"], "unavailable")
        self.assertFalse(report["can_sign_off"])

    def test_completed_unsupported_result_cannot_sign_off(self):
        from python.spike_core.contracts import AnalysisResult
        calls = 0

        def runner(_design, _spec):
            nonlocal calls
            calls += 1
            return AnalysisResult(status="completed", model_status="unsupported", mode="dc", summary={
                "max_load_voltage_drop_v": 0.01,
                "total_copper_loss_w": 0.01,
                "total_load_current_a": 1,
                "p95_current_density_a_mm2": 2,
                "node_count": calls * 100,
                "edge_count": calls * 200,
            })

        report = run_mesh_convergence(self.design, self.spec, runner)
        self.assertEqual(len(report["levels"]), 1)
        self.assertFalse(report["can_sign_off"])


if __name__ == "__main__":
    unittest.main()
