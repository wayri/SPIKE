# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Guarded service exposure for the experimental tetra CFD/CHT composer."""
import unittest
from unittest.mock import patch

from python.spike_core.service_cfd import METHODS, handle_cfd_request


class TetraChtServiceTests(unittest.TestCase):
    def test_catalog_reports_exact_experimental_limits(self):
        response = handle_cfd_request("cfd_capabilities", {})
        self.assertTrue(response["ok"], response)
        engine = response["result"]["engines"]["spike.tetra_cht"]
        self.assertEqual(engine["request_contract"], "spike/cfd-tetra-cht/v1")
        self.assertEqual(engine["result_contract"], "spike/cfd-tetra-cht-result/v1")
        self.assertEqual(engine["model_status"], "experimental")
        self.assertEqual(engine["coupling"], "one_way_flow_to_energy_face_mass_flux")
        self.assertEqual(engine["fluid_solid_interface"],
                         "stationary_no_slip_perfect_thermal_contact")
        for unsupported in ("inertia", "turbulence", "buoyancy_feedback",
                            "general_cad_import", "production_qualified"):
            self.assertIs(engine[unsupported], False)
        self.assertFalse(response["result"]["production_qualified"])
        self.assertFalse(response["result"]["assembly_cht_supported"])

    def test_allowlisted_route_passes_only_the_exact_request(self):
        self.assertIn("run_cfd_tetra_cht", METHODS)
        request = {"contract": "sentinel", "nested": {"retained": [1, 2, 3]}}
        completed = {"contract": "spike/cfd-tetra-cht-result/v1",
                     "status": "completed", "model_status": "experimental",
                     "production_qualified": False}
        with patch("python.spike_core.cfd_tetra_cht.solve_cfd_tetra_cht",
                   return_value=completed) as solve:
            response = handle_cfd_request("run_cfd_tetra_cht", {"request": request})
        self.assertEqual(response, {"ok": True, "result": completed})
        solve.assert_called_once_with(request)

    def test_wrapper_rejects_extra_or_nonobject_parameters_before_solver(self):
        invalid = (
            None,
            {},
            {"request": []},
            {"request": {}, "executable": "untrusted"},
        )
        with patch("python.spike_core.cfd_tetra_cht.solve_cfd_tetra_cht") as solve:
            for params in invalid:
                response = handle_cfd_request("run_cfd_tetra_cht", params)
                self.assertFalse(response["ok"], response)
                self.assertEqual(response["error_code"], "SPIKE-BE-IPC-E-0001")
                self.assertEqual(response["error_detail"]["context"]["method"],
                                 "run_cfd_tetra_cht")
            solve.assert_not_called()

    def test_solver_block_is_a_successful_transport_not_promoted_capability(self):
        response = handle_cfd_request("run_cfd_tetra_cht", {"request": {}})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["contract"], "spike/cfd-tetra-cht-result/v1")
        self.assertEqual(response["result"]["status"], "blocked")
        self.assertEqual(response["result"]["model_status"], "experimental")
        self.assertFalse(response["result"]["production_qualified"])
        self.assertEqual(response["result"]["issues"][0]["code"], "CFD_TETRA_CHT_REJECTED")
        self.assertNotIn("fields", response["result"])


if __name__ == "__main__":
    unittest.main()
