from __future__ import annotations

import copy
import math
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.external_engines import prepare_openems_case
from python.spike_core.openems_adapter_source import OPENEMS_DRIVER
from python.spike_core.openems_validation import (
    FAR_FIELD_REQUEST_CONTRACT,
    FAR_FIELD_RESULT_CONTRACT,
    validate_far_field_request,
    validate_normalized_result,
)


def far_field_design() -> DesignIR:
    return DesignIR(
        design_id="nf2ff-fixture",
        name="NF2FF fixture",
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        nets=[{"id": "1", "name": "RF"}, {"id": "2", "name": "GND"}],
        tracks=[
            {"id": "rf", "start": [0.0, 0.0], "end": [20.0, 0.0], "width": 1.0, "layer": "F.Cu", "net_name": "RF"},
            {"id": "gnd", "start": [0.0, 2.0], "end": [20.0, 2.0], "width": 1.0, "layer": "F.Cu", "net_name": "GND"},
        ],
        stackup=[
            {"name": "F.Cu", "type": "copper", "thickness": 0.035},
            {"name": "core", "type": "core", "thickness": 1.53, "epsilon_r": 4.2, "loss_tangent": 0.02},
            {"name": "B.Cu", "type": "copper", "thickness": 0.035},
        ],
    )


def far_field_request() -> dict:
    return {
        "contract": FAR_FIELD_REQUEST_CONTRACT,
        "frequencies_hz": [100e6, 500e6],
        "theta": {"start_deg": 0, "stop_deg": 180, "points": 19},
        "phi": {"start_deg": -180, "stop_deg": 180, "points": 37},
        "radius_m": 1.0,
        "center_mm": [10.0, 1.0, -0.75],
    }


def far_field_spec(request: dict | None = None) -> AnalysisSpec:
    return AnalysisSpec(
        analysis_id="nf2ff-case",
        mode="broadband_hf",
        net_names=["RF", "GND"],
        frequency_start_hz=1e6,
        frequency_stop_hz=1e9,
        frequency_points=5,
        options={
            "ports": [{
                "start": [10.0, 0.0, 0.0],
                "stop": [10.0, 2.0, 0.0],
                "direction": "y",
                "impedance_ohm": 50,
                "excite": True,
            }],
            **({"far_field": request} if request is not None else {}),
        },
    )


class OpenEmsFarFieldTests(unittest.TestCase):
    def setUp(self):
        self.state_directory = tempfile.TemporaryDirectory()
        self.state_environment = patch.dict(os.environ, {"SPIKE_STATE_HOME": str(Path(self.state_directory.name) / "state")})
        self.state_environment.start()

    def tearDown(self):
        self.state_environment.stop()
        self.state_directory.cleanup()

    def test_prepare_persists_bounded_opt_in_request(self):
        with tempfile.TemporaryDirectory() as directory:
            result = prepare_openems_case(
                far_field_design(), far_field_spec(far_field_request()), Path(directory) / "case",
                {"mesh_resolution_mm": 1.0, "air_padding_mm": 10.0},
            )

        self.assertNotEqual(result["status"], "blocked")
        validation = result["validation"]
        self.assertTrue(validation["far_field"]["enabled"])
        self.assertEqual(validation["far_field"]["request"]["shape"], [2, 19, 37])
        self.assertEqual(validation["far_field"]["resources"]["samples"], 1406)
        self.assertIn("OPENEMS_FAR_FIELD_VALIDATION_REQUIRED", {item["code"] for item in validation["warnings"]})

    def test_request_rejects_outside_center_and_sample_budget(self):
        request = far_field_request()
        request["center_mm"] = [10_000.0, 1.0, 0.0]
        checked = validate_far_field_request(
            request,
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
            options={"max_far_field_samples": 1000, "air_padding_mm": 10.0},
            simulation_bounds_mm={"start": [-10.0, -10.0, -10.0], "stop": [30.0, 12.0, 10.0]},
            mesh_resolution_mm=1.0,
        )
        codes = {item["code"] for item in checked["errors"]}
        self.assertIn("OPENEMS_FAR_FIELD_CENTER_OUTSIDE_BOX", codes)
        self.assertIn("OPENEMS_FAR_FIELD_SAMPLE_BUDGET_EXCEEDED", codes)

    def test_driver_records_nf2ff_after_final_mesh_and_calculates_after_run(self):
        compile(OPENEMS_DRIVER, "run_openems.py", "exec")
        recording = OPENEMS_DRIVER.index('nf2ff = fdtd.CreateNF2FFBox("spike_nf2ff"')
        self.assertGreater(recording, OPENEMS_DRIVER.index('grid.SmoothMeshLines("all"'))
        self.assertGreater(recording, OPENEMS_DRIVER.index("ports.append(fdtd.AddLumpedPort"))
        self.assertLess(
            OPENEMS_DRIVER.index("ports.append(fdtd.AddLumpedPort"),
            OPENEMS_DRIVER.index('grid.SmoothMeshLines("all"'),
        )
        calculation = OPENEMS_DRIVER.index('result["far_field"] = normalized_far_field(')
        self.assertGreater(calculation, OPENEMS_DRIVER.index("fdtd.Run("))

    def test_embedded_normalizer_flattens_finite_nf2ff_arrays(self):
        csxcad = types.ModuleType("CSXCAD")
        csxcad.ContinuousStructure = object
        openems = types.ModuleType("openEMS")
        openems.openEMS = object
        constants = types.ModuleType("openEMS.physical_constants")
        constants.C0 = 299_792_458.0
        constants.EPS0 = 8.8541878128e-12
        openems.physical_constants = constants
        namespace = {"__name__": "spike_openems_driver_test"}
        with patch.dict(sys.modules, {"CSXCAD": csxcad, "openEMS": openems, "openEMS.physical_constants": constants}):
            exec(OPENEMS_DRIVER, namespace)

        class Result:
            freq = np.array([100e6])
            E_theta = np.ones((1, 2, 3), dtype=complex) * (1 + 2j)
            E_phi = np.ones((1, 2, 3), dtype=complex) * (0.5 - 0.25j)
            E_norm = np.ones((1, 2, 3)) * math.sqrt(5.3125)
            P_rad = np.ones((1, 2, 3)) * 0.01
            Prad = np.array([0.1])
            Dmax = np.array([4 * math.pi * 0.1])

        class Recorder:
            def CalcNF2FF(self, **kwargs):
                self.kwargs = kwargs
                return Result()

        recorder = Recorder()
        request = {
            "frequencies": np.array([100e6]), "theta": np.array([0.0, 180.0]),
            "phi": np.array([-180.0, 0.0, 180.0]), "radius": 1.0,
            "center": np.array([1.0, 2.0, 3.0]), "shape": (1, 2, 3),
        }
        with tempfile.TemporaryDirectory() as directory:
            result = namespace["normalized_far_field"](recorder, Path(directory), request, 0,
                                                       np.array([10.+0j]), 50.)

        self.assertEqual(result["shape"], [1, 2, 3])
        self.assertEqual(len(result["e_field_v_m"]["theta"]["real"]), 6)
        self.assertEqual(len(result["directivity"]["linear"]), 6)
        self.assertEqual(result["validation_status"], "not_validated")
        self.assertEqual(recorder.kwargs["center"], [.001, .002, .003])

    def test_normalized_far_field_is_shape_checked_and_never_auto_validated(self):
        request = {
            "contract": FAR_FIELD_REQUEST_CONTRACT,
            "frequencies_hz": [1.5e6],
            "theta": {"start_deg": 0, "stop_deg": 90, "points": 2},
            "phi": {"start_deg": 0, "stop_deg": 180, "points": 3},
            "radius_m": 1.0,
            "center_mm": [0.0, 0.0, 0.0],
        }
        expected_far_field = validate_far_field_request(
            request, frequency_start_hz=1e6, frequency_stop_hz=2e6,
        )["request"]
        samples = 6
        angular_power = [0.01] * samples
        directivity = [4 * math.pi * value / 0.1 for value in angular_power]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "simulation"
            artifact.mkdir()
            result = {
                "contract": "spike/external-result/v1",
                "engine_id": "external.openems",
                "status": "completed",
                "model_status": "unvalidated",
                "frequency_hz": [1e6, 2e6],
                "s_parameters": {"s11": {"real": [0.1, 0.2], "imag": [0.0, 0.0]}},
                "artifacts": ["simulation"],
                "mesh": {"resolution_mm": 0.5},
                "run_binding": {
                    "run_id": "run-1", "job_id": "job-1", "input_digest": "digest-1",
                    "mesh_resolution_mm": 0.5, "frequency_start_hz": 1e6,
                    "frequency_stop_hz": 2e6, "frequency_points": 2,
                },
                "far_field": {
                    "contract": FAR_FIELD_RESULT_CONTRACT,
                    "status": "computed",
                    "validation_status": "not_validated",
                    "normalization": {"kind": "incident_power", "incident_power_w": 1.0,
                        "incident_voltage_phase_deg": 0.0, "phasor": "peak",
                        "reference_impedance_ohm": 50., "source_spectrum": "single_sided_pulse_fourier_integral",
                        "frequency_sampling": "exact_port_reevaluation"},
                    "frequencies_hz": [1.5e6],
                    "theta_deg": [0.0, 90.0],
                    "phi_deg": [0.0, 90.0, 180.0],
                    "radius_m": 1.0,
                    "center_mm": [0.0, 0.0, 0.0],
                    "shape": [1, 2, 3],
                    "e_field_v_m": {
                        "theta": {"real": [1.0] * samples, "imag": [0.0] * samples},
                        "phi": {"real": [0.5] * samples, "imag": [0.0] * samples},
                        "magnitude": [math.sqrt(1.25)] * samples,
                    },
                    "directivity": {"linear": directivity, "maximum_linear": [max(directivity)]},
                    "radiated_power": {"angular_units": "W/sr", "angular_w": angular_power, "total_w": [0.1]},
                    "validation": {"status": "not_validated", "required": ["mesh_convergence"]},
                },
            }
            arguments = {
                "setup_only": False, "expected_points": 2, "expected_start_hz": 1e6,
                "expected_stop_hz": 2e6, "expected_job_id": "job-1",
                "expected_input_digest": "digest-1", "expected_run_id": "run-1",
                "ports": [{"excite": True}], "root": root,
                "expected_far_field": expected_far_field,
            }
            self.assertEqual(validate_normalized_result(result, **arguments)["model_status"], "unvalidated")

            for invalid in (None, {}, {**result["far_field"]["normalization"], "incident_power_w": True}):
                raw = copy.deepcopy(result)
                raw["far_field"]["normalization"] = invalid
                with self.assertRaisesRegex(ValueError, "one-watt"):
                    validate_normalized_result(raw, **arguments)

            overclaimed = copy.deepcopy(result)
            overclaimed["far_field"]["validation_status"] = "validated"
            with self.assertRaisesRegex(ValueError, "explicitly not validated"):
                validate_normalized_result(overclaimed, **arguments)
            malformed = copy.deepcopy(result)
            malformed["far_field"]["e_field_v_m"]["magnitude"] = [1.0]
            with self.assertRaisesRegex(ValueError, "invalid shape"):
                validate_normalized_result(malformed, **arguments)
            nonfinite = copy.deepcopy(result)
            nonfinite["far_field"]["radiated_power"]["total_w"] = [math.nan]
            with self.assertRaisesRegex(ValueError, "non-finite"):
                validate_normalized_result(nonfinite, **arguments)
            missing = copy.deepcopy(result)
            del missing["far_field"]
            with self.assertRaisesRegex(ValueError, "missing the requested"):
                validate_normalized_result(missing, **arguments)

    def test_setup_only_preserves_existing_status_with_far_field_request(self):
        request = validate_far_field_request(
            far_field_request(), frequency_start_hz=1e6, frequency_stop_hz=1e9,
        )["request"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "setup.xml"
            artifact.write_text("<openEMS/>", encoding="utf-8")
            result = {
                "contract": "spike/external-result/v1", "engine_id": "external.openems",
                "status": "setup_completed", "model_status": "approximate",
                "artifacts": ["setup.xml"], "mesh": {"resolution_mm": 0.5},
                "run_binding": {
                    "run_id": "run-1", "job_id": "job-1", "input_digest": "digest-1",
                    "mesh_resolution_mm": 0.5, "frequency_start_hz": 1e6,
                    "frequency_stop_hz": 1e9, "frequency_points": 5,
                },
            }
            checked = validate_normalized_result(
                result, setup_only=True, expected_points=5, expected_start_hz=1e6,
                expected_stop_hz=1e9, expected_job_id="job-1", expected_input_digest="digest-1",
                expected_run_id="run-1", ports=[{"excite": True}], root=root,
                expected_far_field=request,
            )
        self.assertEqual(checked["status"], "setup_completed")
        self.assertEqual(checked["model_status"], "approximate")


if __name__ == "__main__":
    unittest.main()
