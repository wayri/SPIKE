import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.peec_plugin import native_available
from python.spike_core.preflight import preflight_analysis
from python.spike_core.solver_plugins import default_solver_registry
from python.spike_core.transient_peec import (
    _admit_visual_records,
    _assess_passive_inductance,
    estimate_line_capacitance_per_m,
    solve_peec_rl_transient,
    transient_settings,
    waveform_value,
)


class TransientWaveformTests(unittest.TestCase):
    def test_step_pulse_and_piecewise_linear_profiles(self):
        step = {
            "current_a": 2.0,
            "profile": {"kind": "step", "initial_value": 0.0, "delay_s": 1e-6, "rise_time_s": 2e-6},
        }
        self.assertEqual(waveform_value(step, 0.5e-6), 0.0)
        self.assertAlmostEqual(waveform_value(step, 2e-6), 1.0)
        self.assertEqual(waveform_value(step, 4e-6), 2.0)

        pulse = {
            "voltage_v": 5.0,
            "profile": {
                "kind": "pulse", "initial_value": 1.0, "delay_s": 1e-6,
                "rise_time_s": 1e-6, "pulse_width_s": 2e-6,
                "fall_time_s": 1e-6, "period_s": 6e-6,
            },
        }
        self.assertEqual(waveform_value(pulse, 0.0), 1.0)
        self.assertAlmostEqual(waveform_value(pulse, 1.5e-6), 3.0)
        self.assertEqual(waveform_value(pulse, 3e-6), 5.0)
        self.assertAlmostEqual(waveform_value(pulse, 4.5e-6), 3.0)
        self.assertEqual(waveform_value(pulse, 6e-6), 1.0)

        pwl = {
            "current_a": 99.0,
            "profile": {"kind": "piecewise_linear", "points": "0:0, 1e-6:2, 3e-6:0"},
        }
        self.assertAlmostEqual(waveform_value(pwl, 2e-6), 1.0)


class TransientPeecTests(unittest.TestCase):
    def setUp(self):
        self.design = DesignIR(
            name="straight RL transient fixture",
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "trace",
                "start": [0.0, 0.0],
                "end": [10.0, 0.0],
                "width": 1.0,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )

    def spec(self, **transient):
        return AnalysisSpec(
            mode="transient",
            solver_id="spike.peec_rl_transient",
            formulation="peec_rl_transient",
            required_capabilities=["transient_waveforms", "geometry_transient", "partial_inductance"],
            net_names=["VCC"],
            sources=[{
                "id": "source", "name": "Source", "position_mm": [0, 0],
                "layer": "F.Cu", "net": "VCC", "voltage_v": 5.0,
                "profile": {"kind": "constant"},
            }],
            loads=[{
                "id": "load", "name": "Load", "position_mm": [10, 0],
                "layer": "F.Cu", "net": "VCC", "current_a": 1.0,
                "profile": {"kind": "step", "initial_value": 0.0, "delay_s": 2e-6, "rise_time_s": 1e-6},
            }],
            transient={
                "stop_time_s": 8e-6,
                "time_step_s": 2e-7,
                "output_decimation": 5,
                "playback_fps": 20,
                "initial_condition": "operating_point",
                **transient,
            },
            mesh={"target_size_mm": 2.0, "zone_cell_mm": 2.0, "max_preview_cells": 1000},
        )

    def test_preflight_accepts_transient_without_frequency_sweep(self):
        catalog = default_solver_registry().catalog()
        for solver in catalog:
            if solver["id"] == "spike.peec_rl_transient":
                solver["state"] = "available"
        result = preflight_analysis(self.design, self.spec(), catalog)
        self.assertTrue(result["can_solve"])
        self.assertNotIn("FREQUENCY_SWEEP_REQUIRED", {issue["code"] for issue in result["issues"]})

    def test_nonpassive_inductance_is_reported_without_projection(self):
        input_matrix = np.asarray([[1.0, 2.0], [2.0, 1.0]])
        assessed, metrics = _assess_passive_inductance(input_matrix)
        self.assertEqual(metrics["negative_eigenmode_count"], 1)
        self.assertFalse(metrics["projection_applied"])
        self.assertEqual(metrics["frobenius_correction_ratio"], 0.0)
        np.testing.assert_array_equal(assessed, input_matrix)
        self.assertLess(float(np.min(np.linalg.eigvalsh(assessed))), 0)

    def test_passive_singular_graph_link_is_unchanged(self):
        input_matrix = np.diag([2e-9, 0.0])
        assessed, metrics = _assess_passive_inductance(input_matrix)
        self.assertEqual(metrics["negative_eigenmode_count"], 0)
        self.assertFalse(metrics["projection_applied"])
        np.testing.assert_array_equal(assessed, input_matrix)

    def test_nonpassive_native_transient_fails_without_waveform(self):
        def make_solver(mesh, _epsilon):
            count = len(mesh.branches)
            solver = SimpleNamespace(
                compute_partial_inductance=lambda: np.diag([1e-9] * (count - 1) + [-1e-9]),
                compute_resistance=lambda _frequency: np.eye(count),
            )
            return solver, SimpleNamespace(eps_r=4.2)

        with patch("python.spike_core.transient_peec.native_available", return_value=True), patch(
            "python.spike_core.transient_peec._make_native_solver", side_effect=make_solver,
        ):
            result = solve_peec_rl_transient(self.design, self.spec())
        self.assertEqual(result.status, "failed")
        self.assertIn("TRANSIENT_INDUCTANCE_NONPASSIVE", {issue.code for issue in result.issues})
        self.assertFalse(result.fields)
        self.assertFalse(result.provenance["solved"])
        self.assertEqual(result.provenance["inductance_units"], "H")
        quality = result.provenance["numerical_quality"]["inductance_passivity"]
        self.assertEqual(quality["negative_eigenmode_count"], 1)
        self.assertFalse(quality["projection_applied"])

    def test_preflight_blocks_excessive_saved_frames(self):
        result = preflight_analysis(
            self.design,
            self.spec(stop_time_s=1.0, time_step_s=1e-5, output_decimation=1, output_decimation_mode="manual", max_internal_steps=200000, max_output_frames=1000),
            default_solver_registry().catalog(),
        )
        self.assertFalse(result["can_solve"])
        self.assertIn("TRANSIENT_TIME_CONTROL_INVALID", {issue["code"] for issue in result["issues"]})

    def test_auto_decimation_respects_frame_limit(self):
        settings = transient_settings(self.spec(
            stop_time_s=1.0,
            time_step_s=1e-5,
            output_decimation=1,
            output_decimation_mode="auto",
            max_internal_steps=200000,
            max_output_frames=1000,
        ))
        self.assertGreater(settings.output_decimation, 1)
        self.assertLessEqual(int(np.ceil(settings.internal_steps / settings.output_decimation)) + 1, 1000)

    def test_branch_settings_keep_explicit_and_memory_caps_distinct(self):
        settings = transient_settings(self.spec(max_branches=1300, memory_budget_mb=2048))
        self.assertEqual(settings.configured_max_branches, 1300)
        self.assertEqual(settings.memory_admitted_max_branches, 2953)
        self.assertEqual(settings.max_branches, 1300)

    def test_native_solver_construction_failure_is_structured(self):
        with patch("python.spike_core.transient_peec.native_available", return_value=True), patch(
            "python.spike_core.transient_peec._make_native_solver",
            side_effect=ValueError("PEEC filaments require positive length"),
        ):
            result = solve_peec_rl_transient(self.design, self.spec())
        self.assertEqual(result.status, "failed")
        self.assertIn("PEEC_MATRIX_EXTRACTION_FAILED", {issue.code for issue in result.issues})
        self.assertIn("positive length", result.issues[-1].message)

    def test_explicit_volume_request_fails_closed_without_fallback(self):
        spec = self.spec()
        spec.options["peec_volume_extraction"] = "enabled"
        solver = SimpleNamespace(
            compute_partial_inductance=lambda: self.fail("filament fallback must not run"),
            compute_resistance=lambda _frequency: self.fail("filament fallback must not run"),
        )
        with patch("python.spike_core.transient_peec.native_available", return_value=True), patch(
            "python.spike_core.transient_peec._make_native_solver",
            return_value=(solver, SimpleNamespace(eps_r=4.2)),
        ), patch(
            "python.spike_core.transient_peec.extract_volume_matrices",
            side_effect=ValueError("volume integration did not converge"),
        ):
            result = solve_peec_rl_transient(self.design, spec)
        self.assertEqual(result.status, "failed")
        self.assertIn("PEEC_VOLUME_EXTRACTION_FAILED", {issue.code for issue in result.issues})
        self.assertEqual(result.provenance["failure_stage"], "volume_matrix_extraction")
        self.assertEqual(result.provenance["volume_current_model"], "uniform_volume_current")

    def test_explicit_volume_request_drives_transient_matrices(self):
        spec = self.spec()
        spec.options["peec_volume_extraction"] = "enabled"
        solver = SimpleNamespace(
            compute_partial_inductance=lambda: self.fail("filament fallback must not run"),
            compute_resistance=lambda _frequency: self.fail("filament fallback must not run"),
        )

        def volume_result(_native, _design, branches):
            count = len(branches)
            return SimpleNamespace(
                inductance_h=np.eye(count) * 1e-9,
                dc_resistance_ohm=np.eye(count) * 1e-3,
                quality={"method": "uniform_volume_current", "pair_count": count * count},
            )

        with patch("python.spike_core.transient_peec.native_available", return_value=True), patch(
            "python.spike_core.transient_peec._make_native_solver",
            return_value=(solver, SimpleNamespace(eps_r=4.2)),
        ), patch(
            "python.spike_core.transient_peec.extract_volume_matrices", side_effect=volume_result,
        ):
            result = solve_peec_rl_transient(self.design, spec)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.model_status, "approximate")
        self.assertEqual(result.provenance["volume_current_model"], "uniform_volume_current")
        self.assertEqual(result.provenance["volume_extraction_work"], "bounded_adaptive_pair_integration")
        self.assertEqual(result.provenance["volume_extraction"]["method"], "uniform_volume_current")

    def test_stackup_line_capacitance_is_physical_and_finite(self):
        value = estimate_line_capacitance_per_m(1.0, 0.2, 4.2)
        self.assertGreater(value, 50e-12)
        self.assertLess(value, 1e-9)

    def test_visual_admission_is_order_independent_and_preserves_stitched_geometry(self):
        records = [
            {
                "id": f"front-track-{index}", "source_id": f"front-track-{index}",
                "source_kind": "track", "net": "VCC", "layer": "F.Cu",
                "start_mm": [float(index), 0.0, 0.0], "end_mm": [float(index) + 0.5, 0.0, 0.0],
                "_physical_index": index,
            }
            for index in range(20)
        ] + [
            {
                "id": f"back-track-{index}", "source_id": f"back-track-{index}",
                "source_kind": "track", "net": "VCC", "layer": "B.Cu",
                "start_mm": [float(index), 1.0, 0.0], "end_mm": [float(index) + 0.5, 1.0, 0.0],
                "_physical_index": 100 + index,
            }
            for index in range(20)
        ] + [
            {
                "id": "via-stitch", "source_id": "via-stitch", "source_kind": "via",
                "net": "VCC", "layer": "F.Cu->B.Cu",
                "start_mm": [10.0, 0.0, 0.0], "end_mm": [10.0, 0.0, 1.0], "_physical_index": 200,
            },
            {
                "id": "zone-plane", "source_id": "zone-plane", "source_kind": "zone",
                "net": "VCC", "layer": "In1.Cu",
                "start_mm": [10.0, 2.0, 0.0], "end_mm": [12.0, 2.0, 0.0], "_physical_index": 201,
            },
        ]
        original = [dict(record) for record in records]

        selected = _admit_visual_records(records, 4)
        shuffled_selected = _admit_visual_records(list(reversed(records)), 4)

        self.assertEqual(records, original)
        self.assertEqual(
            [record["id"] for record in selected],
            [record["id"] for record in shuffled_selected],
        )
        self.assertEqual(
            {(record["layer"], record["source_kind"]) for record in selected},
            {("F.Cu", "track"), ("B.Cu", "track"), ("F.Cu->B.Cu", "via"), ("In1.Cu", "zone")},
        )
        self.assertEqual(len({record["_physical_index"] for record in selected}), len(selected))

    @unittest.skipUnless(native_available(), "Native PEEC extension is not built")
    def test_geometry_rl_step_generates_timestamped_fields(self):
        result = default_solver_registry().run(self.design, self.spec())
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.mode, "transient")
        self.assertGreater(result.summary["peak_inductive_drop_v"], 0)
        self.assertGreater(result.summary["max_voltage_drop_v"], 0)
        self.assertGreater(result.summary["max_current_density_a_mm2"], 0)
        series = result.fields["visualization"]["time_series"]
        self.assertEqual(series["contract"], "spike/compact-field-series/v1")
        self.assertEqual(series["times_s"][0], 0.0)
        self.assertAlmostEqual(series["times_s"][-1], 8e-6)
        self.assertEqual(result.summary["frame_count"], len(series["frames"]))
        self.assertGreater(len(series["frames"][-1]["scalar_values"]["voltage_drop_v"]), 0)
        self.assertIn("current_density", series["frames"][-1]["vector_values"])
        self.assertIn("nodes", series["layouts"])
        self.assertIn("TRANSIENT_CAPACITANCE_UNSUPPORTED", {issue.code for issue in result.issues})
        self.assertGreater(result.provenance["transient_branch_limit"], 1200)
        self.assertEqual(result.provenance["transient_memory_budget_bytes"], 2048 * 1024 * 1024)
        self.assertEqual(result.provenance["branch_admission"]["workload_class"], "dense")

    def _explicit_return_case(self):
        design = DesignIR(
            name="two-layer RLC transient fixture",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "VCC"}, {"id": 2, "name": "GND"}],
            tracks=[
                {"id": "rail", "start": [0.0, 0.0], "end": [10.0, 0.0], "width": 1.0, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "return", "start": [0.0, 0.0], "end": [10.0, 0.0], "width": 2.0, "layer": "B.Cu", "net_name": "GND"},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.07},
                {"name": "dielectric 1", "type": "prepreg", "thickness": 0.1, "epsilon_r": 4.2},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        spec = self.spec(capacitance_model="stackup_shunt")
        spec.net_names = ["VCC", "GND"]
        spec.return_path = {"mode": "explicit", "net": "GND"}
        spec.sources.append({
            "id": "return-source", "name": "Return source", "position_mm": [0, 0],
            "layer": "B.Cu", "net": "GND", "voltage_v": 0.0, "terminal_role": "source_return",
            "profile": {"kind": "constant"},
        })
        spec.loads[0]["terminal_role"] = "load_positive"
        spec.loads[0]["pair_id"] = "pair-1"
        spec.loads.append({
            "id": "return-load", "name": "Return load", "position_mm": [10, 0],
            "layer": "B.Cu", "net": "GND", "current_a": -1.0, "terminal_role": "load_return",
            "pair_id": "pair-1", "profile": {"kind": "constant"},
        })
        return design, spec

    @unittest.skipUnless(native_available(), "Native PEEC extension is not built")
    def test_real_native_two_layer_result_is_passive_or_fails_closed(self):
        design, spec = self._explicit_return_case()
        result = default_solver_registry().run(design, spec)
        if result.status == "failed":
            self.assertIn("TRANSIENT_INDUCTANCE_NONPASSIVE", {issue.code for issue in result.issues})
            self.assertFalse(result.fields)
        else:
            self.assertEqual(result.status, "completed")
            quality = result.provenance["inductance_passivity"]
            self.assertEqual(quality["negative_eigenmode_count"], 0)
            self.assertFalse(quality["projection_applied"])

    def test_explicit_return_stackup_adds_distributed_capacitance_with_passive_matrix(self):
        design, spec = self._explicit_return_case()
        # Isolate the stackup-capacitance behavior from the native inductance
        # model, which currently fails the required passivity check for this
        # two-layer geometry. The real native extraction is separately checked.
        def passive_solver(mesh, _epsilon):
            count = len(mesh.branches)
            solver = SimpleNamespace(
                compute_partial_inductance=lambda: np.eye(count) * 1e-9,
                compute_resistance=lambda _frequency: np.eye(count) * 0.01,
            )
            return solver, SimpleNamespace(eps_r=4.2)

        with patch("python.spike_core.transient_peec.native_available", return_value=True), patch(
            "python.spike_core.transient_peec._make_native_solver", side_effect=passive_solver,
        ):
            result = default_solver_registry().run(design, spec)
        self.assertEqual(result.status, "completed")
        self.assertGreater(result.summary["estimated_distributed_capacitance_f"], 0)
        self.assertGreater(result.summary["peak_capacitive_current_a"], 0)
        self.assertIn("TRANSIENT_CAPACITANCE_APPROXIMATE", {issue.code for issue in result.issues})


if __name__ == "__main__":
    unittest.main()
