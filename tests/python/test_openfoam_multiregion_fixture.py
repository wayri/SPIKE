import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.openfoam_multiregion_fixture import build_board_package_air_contact_fixture, build_solid_vacuum_fixture, build_two_region_slab_fixture


ROOT = Path(__file__).resolve().parents[2]


class OpenFoamMultiRegionFixtureTests(unittest.TestCase):
    def test_builds_board_package_contact_and_air_cht_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = build_board_package_air_contact_fixture(Path(directory) / "fixture")
            prepared = fixture["prepared"]
            self.assertEqual(prepared["status"], "prepared_runnable_case", prepared)
            manifest = prepared["runnable_manifest"]
            self.assertEqual(manifest["regions"], ["air", "board", "package"])
            self.assertEqual(manifest["region_kinds"], {"air": "fluid", "board": "solid", "package": "solid"})
            case = Path(prepared["case_dir"])
            self.assertIn("solid (board package)", (case / "constant" / "regionProperties").read_text(encoding="utf-8"))
            self.assertIn("fluid (air)", (case / "constant" / "regionProperties").read_text(encoding="utf-8"))
            package_t = (case / "0" / "package" / "T").read_text(encoding="utf-8")
            self.assertIn("package_board", package_t)
            self.assertIn("thicknessLayers (2e-05)", package_t)
            self.assertIn("kappaLayers (1.0)", package_t)
            self.assertIn("compressible::turbulentTemperatureRadCoupledMixed", package_t)
            self.assertIn("package_source", (case / "system" / "package" / "fvOptions").read_text(encoding="utf-8"))
            self.assertIn("kappa 130", (case / "constant" / "package" / "thermophysicalProperties").read_text(encoding="utf-8"))
            self.assertIn("nOuterCorrectors 10", (case / "system" / "fvSolution").read_text(encoding="utf-8"))
            self.assertIn("nOuterCorrectors 10", (case / "system" / "air" / "fvSolution").read_text(encoding="utf-8"))
            self.assertIn("frozenFlow true", (case / "system" / "fvSolution").read_text(encoding="utf-8"))
            self.assertFalse(prepared["manifest"]["requested_physics"]["fluid_flow"])
            schema = json.loads((ROOT / "schemas" / "openfoam-multiregion-runnable-case-v1.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(manifest)

    def test_builds_solid_only_vacuum_radiation_fixture_without_pseudo_fluid(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = build_solid_vacuum_fixture(Path(directory) / "fixture")
            prepared = fixture["prepared"]
            self.assertEqual(prepared["status"], "prepared_runnable_case", prepared)
            manifest = prepared["runnable_manifest"]
            self.assertEqual(manifest["regions"], ["board"])
            self.assertEqual(manifest["region_kinds"], {"board": "solid"})
            self.assertEqual(manifest["view_factor_regions"], [])
            case = Path(prepared["case_dir"])
            self.assertIn("fluid ()", (case / "constant" / "regionProperties").read_text(encoding="utf-8"))
            temperature = (case / "0" / "board" / "T").read_text(encoding="utf-8")
            self.assertIn("type externalWallHeatFluxTemperature", temperature)
            self.assertIn("h constant 0", temperature)
            self.assertIn("emissivity 0.85", temperature)
            self.assertIn("wallHeatFlux_board", (case / "system" / "controlDict").read_text(encoding="utf-8"))
            schema = json.loads((ROOT / "schemas" / "openfoam-multiregion-runnable-case-v1.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(manifest)

    def test_builds_digest_bound_runnable_two_region_slab_at_three_mesh_levels(self):
        digests = []
        for divisions in (1, 2, 4):
            with tempfile.TemporaryDirectory() as directory:
                fixture = build_two_region_slab_fixture(Path(directory) / "fixture", divisions=divisions)
                prepared = fixture["prepared"]
                self.assertEqual(prepared["status"], "prepared_runnable_case", prepared)
                self.assertEqual(prepared["runnable_manifest"]["status"], "runnable")
                self.assertEqual(prepared["runnable_manifest"]["region_kinds"], {"air": "fluid", "board": "solid"})
                case = Path(prepared["case_dir"])
                self.assertTrue((case / "constant" / "regionProperties").is_file())
                self.assertTrue((case / "constant" / "board" / "polyMesh" / "points").is_file())
                self.assertTrue((case / "constant" / "board" / "polyMesh" / "cellZones").is_file())
                self.assertIn("volumeMode specific", (case / "system" / "board" / "fvOptions").read_text(encoding="utf-8"))
                self.assertIn("type fixedValue", (case / "0" / "air" / "T").read_text(encoding="utf-8"))
                control = (case / "system" / "controlDict").read_text(encoding="utf-8")
                self.assertIn("wallHeatFlux_air", control)
                self.assertIn("patches (air_external)", control)
                self.assertIn("type grad", (case / "system" / "gradT").read_text(encoding="utf-8"))
                solid_schemes = (case / "system" / "board" / "fvSchemes").read_text(encoding="utf-8")
                fluid_schemes = (case / "system" / "air" / "fvSchemes").read_text(encoding="utf-8")
                self.assertIn("laplacian(alpha,h) Gauss harmonic limited corrected 0.5", solid_schemes)
                self.assertIn("laplacian(kappa,h) Gauss harmonic limited corrected 0.5", solid_schemes)
                self.assertNotIn("laplacian(alpha,h)", fluid_schemes)
                schema = json.loads((ROOT / "schemas" / "openfoam-multiregion-runnable-case-v1.schema.json").read_text(encoding="utf-8"))
                Draft202012Validator(schema).validate(prepared["runnable_manifest"])
                digests.append(prepared["runnable_manifest"]["manifest_digest"])
        self.assertEqual(len(set(digests)), 3)


if __name__ == "__main__":
    unittest.main()
