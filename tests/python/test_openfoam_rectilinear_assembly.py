from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from python.spike_core.solvers.external_engines.openfoam.openfoam_rectilinear_assembly import build_rectilinear_assembly_case


def config():
    provenance = {"kind": "declared_axis_aligned_cuboid", "exact": False, "source": "test declaration"}
    return {"domain_bounds_mm": [[0,0,0],[8,6,5]], "maximum_cell_size_mm": 2.0,
        "solids": [
            {"id":"board","role":"board","material_id":"fr4","bounds_mm":[[1,1,1],[7,5,2]],"power_w":0.0,"geometry_provenance":dict(provenance)},
            {"id":"u1","role":"package","material_id":"package","bounds_mm":[[3,2,2],[5,4,3]],"power_w":1.25,"geometry_provenance":dict(provenance)},
        ],
        "materials": [
            {"id":"fr4","phase":"solid","conductivity_w_mk":1,"density_kg_m3":1000,"specific_heat_j_kgk":1000},
            {"id":"package","phase":"solid","conductivity_w_mk":1,"density_kg_m3":1000,"specific_heat_j_kgk":1000},
            {"id":"air","phase":"fluid","conductivity_w_mk":.026,"density_kg_m3":1.2,"specific_heat_j_kgk":1006,"dynamic_viscosity_pa_s":1.8e-5},
        ], "ambient_temperature_k":298.15, "flow_rate_m3_s":1e-4,
        "numerics":{"end_time_s":.1,"delta_t_s":.01,"write_interval_steps":5,"validation_interval_steps":1},
        "source_evidence":{"id":"fixture","sha256":"0"*64}}


class RectilinearAssemblyTests(unittest.TestCase):
    def test_builds_air_complement_and_paired_interfaces(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            result = build_rectilinear_assembly_case(config(), Path(directory)/"case")
            self.assertEqual(result["status"], "prepared_runnable_case")
            self.assertGreater(result["cell_counts"]["air"], 0)
            request = result["request"]
            pairs = {(row["region_a"], row["region_b"]) for row in request["interfaces"]}
            self.assertIn(("air", "u1"), pairs)
            self.assertIn(("board", "u1"), pairs)
            source = request["heat_sources"][0]
            volume = 2*2*1*1e-9
            self.assertAlmostEqual(source["fv_option"]["volumetric_power_w_m3"]*volume, 1.25)
            self.assertTrue((Path(directory)/"case/case/spike_multiregion_runnable_case.json").is_file())

    def test_rejects_overlapping_or_unlabelled_proxies(self):
        overlap = config()
        overlap["solids"][1]["bounds_mm"] = [[2,2,1.5],[5,4,2.5]]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, self.assertRaisesRegex(ValueError, "overlap"):
            build_rectilinear_assembly_case(overlap, Path(directory)/"case")
        missing = config()
        missing["solids"][0]["geometry_provenance"]["exact"] = True
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, self.assertRaisesRegex(ValueError, "inexact"):
            build_rectilinear_assembly_case(missing, Path(directory)/"case")

    def test_input_is_not_mutated(self):
        supplied = config()
        original = copy.deepcopy(supplied)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            build_rectilinear_assembly_case(supplied, Path(directory)/"case")
        self.assertEqual(supplied, original)

    def test_cell_budget_rejects_before_allocating_or_writing(self):
        supplied = config()
        supplied["maximum_cell_size_mm"] = 1e-12
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            target = Path(directory)/"case"
            with self.assertRaisesRegex(ValueError, "exceeds 100000 cells"):
                build_rectilinear_assembly_case(supplied, target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
