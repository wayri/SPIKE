# SPDX-License-Identifier: Apache-2.0
"""Analytic KCL capacity oracles, independent of copper discretization."""
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import AnalysisSpec, SpiDeR
from python.spike_core.hybrid_dc_solver import solve_hybrid_dc
from python.spike_core.preflight import preflight_analysis
from python.spike_core.source_current_limits import current_limit_issues, source_capacity
from python.spike_core.solver_plugins import default_solver_registry, ExternalProcessSolverPlugin, SolverPluginManifest


def fixture(limit=1.0):
    design = SpiDeR(nets=[{"name": "VCC"}], layers=[{"name": "F.Cu"}],
        tracks=[{"id": f"track-{i}", "start": [5*i, 0], "end": [5*(i+1), 0],
                 "width": 1, "layer": "F.Cu", "net_name": "VCC"} for i in range(2)],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}])
    def terminal(name, x, track):
        return {"id": name, "position_mm": [x, 0], "layer": "F.Cu", "net": "VCC",
                "geometry_anchor": {"id": track, "type": "track"}}
    source = {**terminal("source", 0, "track-0"), "voltage_v": 5}
    if limit is not None:
        source["current_limit_a"] = limit
    spec = AnalysisSpec(net_names=["VCC"], sources=[source], loads=[
        {**terminal("sink-1", 5, "track-0"), "current_a": 0.4},
        {**terminal("sink-2", 10, "track-1"), "current_a": 0.6}],
        options={"require_exact_terminal_geometry": True})
    return design, spec


class SourceCurrentLimitTests(unittest.TestCase):
    def test_two_sinks_below_at_and_over_capacity(self):
        for limit, expected in ((2, "feasible"), (1, "feasible"), (0.999, "infeasible")):
            with self.subTest(limit=limit):
                design, spec = fixture(limit)
                result = solve_hybrid_dc(design, spec)
                self.assertEqual(result.summary["source_capacity_status"], expected)
                self.assertAlmostEqual(result.fields["source_current_results"][0]["required_current_a"], 1, places=10)
                if expected == "infeasible":
                    self.assertEqual(result.status, "failed")
                    self.assertNotIn("node_voltages", result.fields)
                    self.assertIn("SPIKE-BE-PI-E-0112", [i.code for i in result.issues])
                else:
                    self.assertEqual(result.status, "completed")

    def test_unlimited_preserves_voltage_solution(self):
        design, limited = fixture(2)
        unlimited = deepcopy(limited)
        del unlimited.sources[0]["current_limit_a"]
        a, b = solve_hybrid_dc(design, limited), solve_hybrid_dc(design, unlimited)
        self.assertEqual(a.fields["node_voltages"], b.fields["node_voltages"])
        self.assertEqual(b.summary["source_capacity_status"], "not_requested")

    def test_invalid_limits_and_preflight(self):
        registry = default_solver_registry()
        for value in (0, -1, float("nan"), float("inf"), True, "1", None):
            with self.subTest(value=value):
                design, spec = fixture()
                spec.sources[0]["current_limit_a"] = value
                self.assertTrue(current_limit_issues(spec))
                self.assertEqual(solve_hybrid_dc(design, spec).status, "failed")
                self.assertFalse(preflight_analysis(design, spec, registry.catalog())["can_solve"])

    def test_multiple_sources_share_by_resistance_not_total_demand(self):
        design, spec = fixture(0.8)
        spec.sources[0]["contact_resistance_ohm"] = 1
        spec.sources.append({**deepcopy(spec.sources[0]), "id": "second", "current_limit_a": 0.3,
                             "contact_resistance_ohm": 3})
        result = solve_hybrid_dc(design, spec)
        self.assertEqual(result.status, "completed", result.issues)
        self.assertAlmostEqual(result.fields["source_current_results"][0]["required_current_a"], .75, places=9)
        self.assertAlmostEqual(result.fields["source_current_results"][1]["required_current_a"], .25, places=9)
        spec.sources[1]["current_limit_a"] = .2
        self.assertEqual(solve_hybrid_dc(design, spec).summary["source_capacity_status"], "infeasible")

    def test_overlapping_ideal_sources_are_indeterminate(self):
        design, spec = fixture(2)
        spec.sources.append({**spec.sources[0], "id": "second"})
        result = solve_hybrid_dc(design, spec)
        self.assertEqual(result.summary["source_capacity_status"], "unsupported")
        self.assertIsNone(result.fields["source_current_results"][0]["required_current_a"])

    def test_reverse_flow_is_not_positive_capacity_headroom(self):
        design, spec = fixture(2)
        for load in spec.loads:
            load["current_a"] *= -1
        result = solve_hybrid_dc(design, spec)
        self.assertEqual(result.summary["source_capacity_status"], "unsupported")
        self.assertAlmostEqual(result.fields["source_current_results"][0]["required_current_a"], -1)

    def test_source_node_load_and_return_sign(self):
        spec = AnalysisSpec(sources=[{"current_limit_a": 1}, {"current_limit_a": 1}])
        sources = [{"id": "a", "domain_id": "d", "role": "source_positive", "boundary_nodes": [0]},
                   {"id": "b", "domain_id": "d", "role": "source_return", "boundary_nodes": [1]}]
        records, issues, status = source_capacity(spec, sources, [], [-1, 1])
        self.assertEqual(status, "feasible")
        self.assertEqual([r["forward_current_a"] for r in records], [1, 1])

    def test_separate_domains_use_their_own_current(self):
        spec = AnalysisSpec(sources=[{"current_limit_a": .5}, {"current_limit_a": 2}])
        sources = [{"id": "a", "domain_id": "one", "role": "source_positive", "boundary_nodes": [0]},
                   {"id": "b", "domain_id": "two", "role": "source_positive", "boundary_nodes": [2]}]
        edges = [{"a": 0, "b": 1, "current_a": .4}, {"a": 2, "b": 3, "current_a": 1.5}]
        rows, issues, status = source_capacity(spec, sources, edges, [0, -.4, 0, -1.5])
        self.assertEqual(status, "feasible")
        self.assertEqual([r["required_current_a"] for r in rows], [.4, 1.5])

    def test_zero_demand_and_absolute_voltage_offset(self):
        design, spec = fixture(1)
        for load in spec.loads:
            load["current_a"] = 0
        self.assertAlmostEqual(solve_hybrid_dc(design, spec).fields["source_current_results"][0]["required_current_a"], 0)
        design, spec = fixture(1)
        spec.sources[0]["voltage_v"] = 1e9
        result = solve_hybrid_dc(design, spec)
        self.assertEqual(result.summary["source_capacity_status"], "feasible")
        self.assertAlmostEqual(result.fields["source_current_results"][0]["required_current_a"], 1, places=10)

    def test_unsupported_solver_and_mode_do_not_ignore_limit(self):
        registry = default_solver_registry()
        design, spec = fixture()
        spec.solver_id = "spike.peec_2_5d"
        spec.mode = "ac"
        result = registry.run(design, spec)
        self.assertEqual(result.status, "failed")
        self.assertIn("SPIKE-BE-PI-E-0111", [i.code for i in result.issues])

    def test_direct_external_plugin_rejects_before_launch(self):
        plugin = ExternalProcessSolverPlugin(SolverPluginManifest(
            id="test.external", name="Test", version="1", provider="Test", analyses=["dc"],
            formulations=["test"], capabilities=[], execution="process", entrypoint="CONTRIBUTING.md"), Path(__file__).resolve().parents[2])
        design, spec = fixture()
        with patch("subprocess.Popen", side_effect=AssertionError("must not launch")):
            result = plugin.run(design, spec)
        self.assertIn("SPIKE-BE-PI-E-0111", [i.code for i in result.issues])

    def test_native_pi_path_compile_and_run_reject_limits(self):
        from tests.python.test_pi_path_circuit import ac_spec, extraction, mappings, three_net_design
        from python.spike_core.pi_path_circuit import compile_pi_path_to_native_mna, run_pi_path_native_mna

        for mode in ("dc", "ac", "transient"):
            with self.subTest(mode=mode):
                spec = ac_spec()
                spec.mode = mode
                spec.transient = {"time_step_s": 1e-6, "stop_time_s": 1e-4}
                # The otherwise valid path compiles normally without a limit.
                baseline = compile_pi_path_to_native_mna(three_net_design(), spec, extraction(), mappings())
                self.assertEqual(baseline["status"], "ready", baseline["issues"])
                spec.sources[0]["current_limit_a"] = 1
                compiled = compile_pi_path_to_native_mna(three_net_design(), spec, extraction(), mappings())
                self.assertEqual(compiled["status"], "blocked")
                self.assertIsNone(compiled["request"])
                self.assertIn("SPIKE-BE-PI-E-0111", [i["code"] for i in compiled["issues"]])
                with patch("python.spike_core.pi_path_circuit.run_native_mna", side_effect=AssertionError("must not solve")):
                    result = run_pi_path_native_mna(three_net_design(), spec, extraction(), mappings())
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["result"])

    def test_direct_peec_rejects_limit_before_native_or_mesh_work(self):
        from python.spike_core.peec_plugin import solve_peec_2_5d

        design, spec = fixture()
        spec.mode = "ac"
        with patch("python.spike_core.peec_plugin.build_hybrid_mesh", side_effect=AssertionError("must not mesh")):
            result = solve_peec_2_5d(design, spec)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.model_status, "unsupported")
        self.assertIn("SPIKE-BE-PI-E-0111", [i.code for i in result.issues])


if __name__ == "__main__":
    unittest.main()
