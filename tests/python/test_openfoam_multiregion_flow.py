# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Dictionary/admission checks only: synthetic mesh stubs never qualify CFD."""
import copy
import tempfile
import unittest
from pathlib import Path

from python.spike_core.openfoam_multiregion import compile_multiregion_case, prepare_runnable_multiregion_case, MultiRegionOpenFoamError
from tests.python.test_openfoam_multiregion import materialize_runnable_request, request


class FanBoundaryTests(unittest.TestCase):
    def test_real_heated_duct_polymesh_preparation(self):
        from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            result = build_fan_heated_fixture(root, divisions=2)
            self.assertEqual(result["prepared"]["status"], "prepared_runnable_case")
            self.assertFalse(result["qualification"]["executed_cfd"])
            self.assertTrue((root / "case/constant/air/polyMesh/points").stat().st_size > 500)
            self.assertIn("pressureInletOutletVelocity", (root / "case/0/air/U").read_text())
            self.assertIn("board_source", (root / "case/constant/board/polyMesh/cellZones").read_text())
            schema = __import__("json").loads((Path(__file__).resolve().parents[2] / "schemas/openfoam-multiregion-request-v1.schema.json").read_text())
            from jsonschema import Draft202012Validator
            Draft202012Validator(schema).validate(result["request"])

    def render(self, mutate=lambda request: None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = materialize_runnable_request(root / "mesh")
            value["fans"][0]["inlet_temperature_k"] = 303.0
            value["environment"]["pressure_outlets"][0]["backflow_temperature_k"] = 304.0
            mutate(value)
            result = prepare_runnable_multiregion_case(value, root / "case", root / "mesh")
            fields = {name: (root / "case" / "0" / "air" / name).read_text() for name in ("U", "T", "p_rgh")} if result["status"] == "prepared_runnable_case" else {}
            return result, fields

    def test_inlet_outlet_velocity_pressure_temperature_pairing(self):
        result, fields = self.render()
        self.assertEqual(result["status"], "prepared_runnable_case")
        self.assertIn("flowRateInletVelocity", fields["U"])
        self.assertIn("volumetricFlowRate constant 0.012", fields["U"])
        self.assertIn("pressureInletOutletVelocity", fields["U"])
        self.assertIn("type prghPressure; rho rho; p uniform 101325", fields["p_rgh"])
        self.assertIn("internalField uniform 101325;", fields["p_rgh"])
        self.assertNotIn("value uniform 0;", fields["p_rgh"])
        self.assertIn("type fixedValue; value uniform 303", fields["T"])
        self.assertIn("type inletOutlet; inletValue uniform 304", fields["T"])
        self.assertFalse(result["manifest"]["qualification"]["production_qualified"])

    def test_prescribed_fan_in_sealed_enclosure_rejected(self):
        result, _ = self.render(lambda value: value["environment"].update(enclosure="sealed"))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("sealed", result["message"])

    def test_no_pressure_outlet_rejected(self):
        result, _ = self.render(lambda value: value["environment"].update(pressure_outlets=[]))
        self.assertEqual(result["status"], "blocked")

    def test_wrong_owner_rejected(self):
        def mutate(value):
            next(region for region in value["regions"] if region["id"] == "air")["boundary_ownership"]["fanOut"] = "external:outer"
        result, _ = self.render(mutate)
        self.assertEqual(result["status"], "blocked")

    def test_duplicate_fan_rejected(self):
        result, _ = self.render(lambda value: value["fans"].append(copy.deepcopy(value["fans"][0])))
        self.assertEqual(result["status"], "blocked")

    def test_tampered_fan_boundary_digest_rejected(self):
        result, _ = self.render(lambda value: value["fans"][0]["boundary_evidence"].update(sha256="a" * 64))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("digest", result["message"])

    def test_pressure_curve_is_not_silently_ignored(self):
        value = request()
        value["fans"][0]["pressure_curve"] = [[0, 100], [0.1, 0]]
        with self.assertRaisesRegex(MultiRegionOpenFoamError, "prescribed"):
            compile_multiregion_case(value)

    def test_outlet_semantics(self):
        valid = {"fluid_region_id": "air", "boundary_patch": "out", "static_pressure_pa": 101325, "backflow_temperature_k": 298.15}
        for key, bad in (("fluid_region_id", "board"), ("boundary_patch", "../out"), ("static_pressure_pa", 0), ("backflow_temperature_k", float("nan")), ("extra", 1)):
            with self.subTest(key=key):
                value = request()
                outlet = {**valid, key: bad}
                value["environment"]["pressure_outlets"] = [outlet]
                with self.assertRaises(MultiRegionOpenFoamError):
                    compile_multiregion_case(value)

    def test_duplicate_outlets_rejected(self):
        with self.assertRaises(MultiRegionOpenFoamError):
            self.render(lambda value: value["environment"]["pressure_outlets"].append(copy.deepcopy(value["environment"]["pressure_outlets"][0])))


if __name__ == "__main__":
    unittest.main()
