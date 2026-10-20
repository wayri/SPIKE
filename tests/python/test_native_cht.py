# SPDX-License-Identifier: Apache-2.0
"""Native CHT admission, independent SI oracle and worker/process checks."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from python.spike_core import native_cht as cht
from python.spike_core.native_cht_result import admit_native_cht_result
from python.spike_core.service_cfd import handle_cfd_request


class NativeChtAdmissionTests(unittest.TestCase):
    def test_strict_settings_and_regime(self):
        for change in ({"n": 10}, {"n": True}, {"n": 68}, {"n": 10**1000},
                {"reynolds": 100}, {"timeout_s": 1.1}, {"lid_velocity_m_s": -1},
                {"density_kg_m3": float("nan")}, {"length_m": math.inf},
                {"hot_temperature_k": 290}, {"dynamic_viscosity_pa_s": 0},
                {"lid_velocity_m_s": 100}, {"fluid_conductivity_w_mk": 1e-6},
                {"executable": "bad.exe"}, {"turbulence": "SST"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                cht.settings({"contract": cht.REQUEST, **change})
        for value in (None, [], {}, {"contract": "spike/other/v1"}):
            with self.assertRaises(ValueError):
                cht.settings(value)

    def test_zero_lid_has_no_invented_actual_reynolds(self):
        s, scales = cht.settings({"contract": cht.REQUEST, "lid_velocity_m_s": 0})
        self.assertEqual(scales["actual_reynolds"], 0)
        self.assertEqual(scales["kernel_reynolds"], 1)
        self.assertEqual(scales["lid"], 0)
        self.assertAlmostEqual(scales["velocity_scale_m_s"], s["dynamic_viscosity_pa_s"] /
                               (s["density_kg_m3"]*s["length_m"]))

    def test_worker_paths_and_capability_are_not_a_physics_promotion(self):
        for method in ("run_native_cht", "run_coupled_surface_exchange"):
            self.assertFalse(handle_cfd_request(method, {"request": {}, "executable": __file__})["ok"])
            self.assertFalse(handle_cfd_request(method, {"request": {}})["ok"])
        self.assertFalse(cht.native_cht_capabilities()["production_qualified"])
        self.assertFalse(cht.native_cht_capabilities()["turbulence"])

    def test_packaged_discovery_never_falls_back_to_checkout(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "_MEIPASS", directory, create=True):
            self.assertEqual(cht.executable_path().parent, Path(directory)/"native")
            self.assertFalse(cht.native_cht_capabilities()["available"])

    def test_process_failures_duplicate_keys_and_malformed_results_reject(self):
        for output in ("null", "[]", '{"n":8,"n":16}', '{"x":NaN}', "bad"):
            with self.subTest(output=output), patch.object(cht, "run_adapter_process", return_value={
                    "return_code": 0, "stdout": output, "stderr": ""}), self.assertRaises(RuntimeError):
                cht.run_native_cht({"contract": cht.REQUEST}, executable=__file__)
        with patch.object(cht, "run_adapter_process", return_value={"return_code": 2, "stderr": "failed"}), \
                self.assertRaisesRegex(RuntimeError, "process failed"):
            cht.run_native_cht({"contract": cht.REQUEST}, executable=__file__)
        with patch.object(cht, "run_adapter_process", side_effect=RuntimeError("cancelled")), \
                self.assertRaisesRegex(RuntimeError, "cancelled"):
            cht.run_native_cht({"contract": cht.REQUEST}, executable=__file__)


@unittest.skipUnless(cht.executable_path().is_file(), "native CHT executable not built")
class NativeChtExecutionTests(unittest.TestCase):
    def test_actual_native_process_cancellation_has_no_result(self):
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            cht.run_native_cht({"contract": cht.REQUEST, "n": 64}, cancellation_event=event)

    def test_si_conduction_interface_heat_and_dimensional_scaling(self):
        request = {"contract": cht.REQUEST, "n": 8, "lid_velocity_m_s": 0,
                   "thermal_tolerance": 1e-10}
        r = cht.run_native_cht(request)
        self.assertEqual(r["status"], "converged")
        # Independent series resistance of two .25L solids and one L fluid.
        s = r["settings"]
        expected_w = (s["hot_temperature_k"]-s["cold_temperature_k"]) * s["span_m"] / (
            .5/s["solid_conductivity_w_mk"]+1/s["fluid_conductivity_w_mk"])
        self.assertAlmostEqual(r["diagnostics"]["hot_input_w"], expected_w, delta=1e-9)
        for value in r["diagnostics"]["interface_heat_flow_w"].values():
            self.assertAlmostEqual(value, expected_w, delta=1e-9)
        scaled = cht.run_native_cht({**request, "length_m": 2, "span_m": 3})
        self.assertEqual(r["fields"]["thermal"]["temperature_k"], scaled["fields"]["thermal"]["temperature_k"])
        self.assertAlmostEqual(scaled["diagnostics"]["hot_input_w"], 3*expected_w, delta=3e-9)
        self.assertFalse(r["production_qualified"])
        self.assertTrue(r["provenance"]["process_containment"]["memory_limit_enforced"])

    def test_incomplete_solve_exposes_no_fields(self):
        for change in ({"max_flow_steps": 1}, {"lid_velocity_m_s": 0, "max_thermal_iterations": 1}):
            r = cht.run_native_cht({"contract": cht.REQUEST, "n": 8, **change})
            self.assertEqual(r["status"], "failed_to_converge")
            self.assertIsNone(r["fields"])
            self.assertIsNone(r["interfaces"])

    def test_raw_field_forgery_cannot_reuse_convergence_certificate(self):
        s, scales = cht.settings({"contract": cht.REQUEST, "n": 8, "lid_velocity_m_s": 0})
        run = subprocess.run([str(cht.executable_path()), *map(str, cht.kernel_arguments(s, scales))],
                             capture_output=True, text=True, check=True, timeout=30)
        raw = json.loads(run.stdout)
        self.assertEqual(admit_native_cht_result(raw, s, scales)["status"], "converged")
        for key, change in (("rows", 8), ("reynolds", 2), ("theta", []),
                            ("hot_flux", 17), ("thermal_residual_linf", 1), ("status", "completed")):
            bad = {**raw, key: change}
            with self.subTest(key=key), self.assertRaises(ValueError):
                admit_native_cht_result(bad, s, scales)
        # Preserve outer boundaries and interfaces; corrupt only an interior cell.
        bad = deepcopy(raw)
        bad["theta"][6*8+4] += .01
        with self.assertRaisesRegex(ValueError, "local energy"):
            admit_native_cht_result(bad, s, scales)
        bad = deepcopy(raw)
        bad["face_u"][2*9+2] = 1.
        with self.assertRaisesRegex(ValueError, "mass balance"):
            admit_native_cht_result(bad, s, scales)

    def test_actual_worker_cli_conduction_and_atomic_result(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"result.json"
            run = subprocess.run([sys.executable, str(root/"scripts/run_cfd.py"), "--engine", "native-cht",
                "--request", str(root/"examples/internal_cfd/native-cht-conduction.json"), "--output", str(output)],
                capture_output=True, text=True, timeout=90)
            self.assertEqual(run.returncode, 0, run.stderr)
            r = json.loads(output.read_text())["result"]
            self.assertEqual(r["contract"], cht.RESULT)
            self.assertEqual(r["status"], "converged")
            self.assertEqual(len(r["provenance"]["executable_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
