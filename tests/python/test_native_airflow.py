# SPDX-License-Identifier: Apache-2.0
"""Native cavity process contract, failure admission and dimensional scaling."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_core.native_airflow import detect_native_airflow, run_native_cavity, _settings, _centerline


class NativeAirflowContractTests(unittest.TestCase):
    def test_frozen_discovery_is_independent_of_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            suffix = ".exe" if sys.platform == "win32" else ""
            expected = Path(directory) / "native" / ("spike_native_airflow" + suffix)
            with patch.dict("os.environ", {}, clear=True), patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", directory, create=True):
                missing = detect_native_airflow()
                self.assertEqual(missing["executable"], str(expected))
                self.assertFalse(missing["available"])
                expected.parent.mkdir()
                expected.touch()
                self.assertTrue(detect_native_airflow()["available"])
                with patch.dict("os.environ", {"SPIKE_NATIVE_AIRFLOW_EXECUTABLE": __file__}):
                    self.assertEqual(detect_native_airflow()["executable"], str(Path(__file__).resolve()))

    def test_rejects_unsupported_and_invalid_settings(self):
        for request in ({"n": 9}, {"n": 3}, {"n": True}, {"n": 16.5},
                        {"reynolds": math.nan}, {"reynolds": 401},
                        {"executable": "untrusted"}, {"temperature": 300},
                        {"max_steps": 0}, {"steady_tolerance": 0}, {"length_m": 0}, {"n":10**1000}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                _settings(request)

    def test_malformed_native_output_is_rejected(self):
        for payload in ("not json", "null", '{"status":"converged"}'):
            with patch("spike_core.native_airflow.subprocess.run", return_value=subprocess.CompletedProcess([],0,payload,"")):
                with self.assertRaises(RuntimeError):
                    run_native_cavity({}, executable=__file__)

    def test_forged_convergence_diagnostics_and_fields_are_rejected(self):
        valid = {"schema":"spike-native-cavity-v1", "n":8, "reynolds":100,
                 "status":"converged", "steps":10, "time":.1, "dt":.01,
                 "divergence_linf":0, "steady_rate_linf":1e-8, "poisson_residual_linf":1e-10,
                 "u":[0]*64, "v":[0]*64, "pressure":[0]*64}
        for change in ({"divergence_linf":1e-3}, {"steady_rate_linf":1e-6},
                       {"poisson_residual_linf":1e-5}, {"dt":0}, {"time":.001},
                       {"steps":True}, {"n":8.0}, {"status":"failed_to_converge"},
                       {"u":[0]*63}, {"pressure":[math.nan]*64}, {"u":[1e308]*64}):
            with self.subTest(change=change), patch("spike_core.native_airflow.subprocess.run",
                    return_value=subprocess.CompletedProcess([],0,json.dumps({**valid,**change}),"")):
                with self.assertRaises(RuntimeError):
                    run_native_cavity({"n":8,"lid_velocity_m_s":3}, executable=__file__)

    def test_centerline_uses_wall_values_on_coarse_grid(self):
        # Exact affine lid profile reconstructs to every sample, including the
        # points between a wall and the nearest centre on an eight-cell grid.
        field = [(j+.5)/8 for j in range(8) for i in range(8)]
        for actual, expected in zip(_centerline(field,8,True),[i/20 for i in range(1,20)]):
            self.assertAlmostEqual(actual,expected)

    def test_timeout_is_not_partial_success(self):
        with patch("spike_core.native_airflow.subprocess.run", side_effect=subprocess.TimeoutExpired([],1)):
            with self.assertRaisesRegex(RuntimeError,"timed out"):
                run_native_cavity({}, executable=__file__)

    @unittest.skipUnless(detect_native_airflow()["available"], "native airflow executable not built")
    def test_real_native_failure_and_scaling(self):
        partial = run_native_cavity({"n":8,"max_steps":1})
        self.assertEqual(partial["status"],"failed_to_converge")
        self.assertIsNone(partial["fields"])
        base = run_native_cavity({"n":16})
        scaled = run_native_cavity({"n":16,"length_m":2,"lid_velocity_m_s":3,"density_kg_m3":4})
        self.assertEqual(base["status"],"converged")
        self.assertLess(base["diagnostics"]["divergence_linf"],1e-8)
        self.assertEqual(base["centerlines"],scaled["centerlines"])
        self.assertFalse(base["production_qualified"])
        self.assertEqual(len(base["provenance"]["request_sha256"]),64)
        self.assertNotEqual(base["provenance"]["request_sha256"],scaled["provenance"]["request_sha256"])
        self.assertAlmostEqual(scaled["dimensional_diagnostics"]["time_s"],base["diagnostics"]["time"]*2/3)
        self.assertAlmostEqual(scaled["dynamic_viscosity_pa_s"],.24)
        for key, factor in (("x_m",2),("y_m",2),("u_m_s",3),("v_m_s",3),("pressure_pa",36)):
            for a,b in zip(base["fields"][key],scaled["fields"][key]):
                self.assertAlmostEqual(b,a*factor)
        self.assertAlmostEqual(sum(base["fields"]["pressure_pa"]),0,places=9)


if __name__ == "__main__":
    unittest.main()
