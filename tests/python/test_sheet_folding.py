# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import json
import math
from pathlib import Path
import unittest
from collections import Counter

from python.spike_core.sheet_folding import CONTRACT, fold_sheet, import_sheet_text, validate_sheet
from python.spike_core.material_library import load_catalog, material_snapshot


def definition(**updates):
    value = {"contract": CONTRACT, "id": "coupon", "kind": "sheet_metal",
             "sheet": {"length_mm": 100.0, "width_mm": 20.0, "thickness_mm": 2.0,
                       "material": {"name": "unspecified test material"}},
             "bends": [{"id": "b1", "start_x_mm": 30.0, "angle_deg": 90.0,
                        "inside_radius_mm": 4.0, "k_factor": 0.5,
                        "fixed_side": "negative_x", "segments": 8}],
             "flex_regions": []}
    value.update(updates)
    return value


def positions(mesh):
    return {item["id"]: item["position_mm"] for item in mesh["vertices"]}


def signed_volume(mesh):
    vertices = positions(mesh)
    total = 0.0
    for triangle in mesh["triangles"]:
        a, b, c = (vertices[item] for item in triangle["vertex_ids"])
        cross = (b[1] * c[2] - b[2] * c[1], b[2] * c[0] - b[0] * c[2],
                 b[0] * c[1] - b[1] * c[0])
        total += sum(a[i] * cross[i] for i in range(3)) / 6.0
    return total


class SheetFoldingTests(unittest.TestCase):
    def test_bend_allowance_and_ninety_degree_endpoint(self):
        result = fold_sheet(definition())
        bend = result["bends"][0]
        expected_allowance = 0.5 * math.pi * (4.0 + 0.5 * 2.0)
        self.assertAlmostEqual(bend["bend_allowance_mm"], expected_allowance, places=12)
        mesh = result["folded_mesh"]
        last_mid_x = 0.5 * (mesh["vertices"][-4]["position_mm"][0] + mesh["vertices"][-3]["position_mm"][0])
        last_mid_z = 0.5 * (mesh["vertices"][-4]["position_mm"][2] + mesh["vertices"][-3]["position_mm"][2])
        downstream = 100.0 - (30.0 + expected_allowance)
        self.assertAlmostEqual(last_mid_x, 30.0 + 5.0, places=12)
        self.assertAlmostEqual(last_mid_z, 5.0 + downstream, places=12)

    def test_negative_angle_mirrors_z_and_retains_x(self):
        positive = fold_sheet(definition())
        negative_raw = definition()
        negative_raw["bends"][0]["angle_deg"] = -90.0
        negative = fold_sheet(negative_raw)
        pv = positive["folded_mesh"]["vertices"][-4:]
        nv = negative["folded_mesh"]["vertices"][-4:]
        p = [sum(v["position_mm"][i] for v in pv) / 4 for i in range(3)]
        n = [sum(v["position_mm"][i] for v in nv) / 4 for i in range(3)]
        self.assertAlmostEqual(p[0], n[0], places=12)
        self.assertAlmostEqual(p[2], -n[2], places=12)

    def test_thickness_places_inner_and_outer_surfaces_at_requested_radii(self):
        result = fold_sheet(definition())
        mesh = result["folded_mesh"]
        # End of the bend is station 8 after the initial station. At +90 degrees,
        # the +normal face is the inner face and the -normal face is outer.
        bend_end = mesh["vertices"][4 * 9:4 * 10]
        center = (30.0, 5.0)
        radii = []
        for vertex in (bend_end[0], bend_end[1]):
            x, _, z = vertex["position_mm"]
            radii.append(math.hypot(x - center[0], z - center[1]))
        self.assertAlmostEqual(radii[0], 6.0, places=12)
        self.assertAlmostEqual(radii[1], 4.0, places=12)

    def test_zero_fraction_is_flat_and_ids_are_stable(self):
        first = fold_sheet(definition(), fraction=0)
        second = fold_sheet(definition(), fraction=0)
        self.assertEqual(first["folded_mesh"], second["folded_mesh"])
        self.assertTrue(all(abs(v["position_mm"][2]) == 1.0 for v in first["folded_mesh"]["vertices"]))
        self.assertEqual(len({v["id"] for v in first["flat_mesh"]["vertices"]}),
                         len(first["flat_mesh"]["vertices"]))

    def test_tiny_fraction_is_finite_and_converges_to_flat(self):
        flat = fold_sheet(definition(), fraction=0)["folded_mesh"]["vertices"]
        for fraction, tolerance in ((1e-320, 0.0), (1e-12, 1e-9)):
            tiny = fold_sheet(definition(), fraction=fraction)["folded_mesh"]["vertices"]
            for actual, expected in zip(tiny, flat):
                self.assertTrue(all(math.isfinite(value) for value in actual["position_mm"]))
                for observed, reference in zip(actual["position_mm"], expected["position_mm"]):
                    self.assertLessEqual(abs(observed - reference), tolerance)

    def test_noncentral_neutral_axis_preserves_length_and_surface_radii(self):
        raw = definition()
        raw["bends"][0].update(angle_deg=60.0, inside_radius_mm=3.0, k_factor=0.3,
                                segments=1)
        theta = math.pi / 3
        neutral_radius = 3.0 + 0.3 * 2.0
        allowance = theta * neutral_radius
        for fraction in (0.00001, 0.5, 1.0):
            mesh = fold_sheet(raw, fraction=fraction)["folded_mesh"]
            # stations are x=0, bend start, bend end, sheet end
            end = mesh["vertices"][8:12]
            mid = [sum(v["position_mm"][i] for v in end) / 4 for i in range(3)]
            applied = theta * fraction
            mid_radius = neutral_radius / fraction + (0.5 - 0.3) * 2.0
            center = (30.0, mid_radius)
            face_radii = []
            for vertex in end[:2]:
                x, _, z = vertex["position_mm"]
                face_radii.append(math.hypot(x - center[0], z - center[1]))
            self.assertAlmostEqual(face_radii[0], neutral_radius / fraction + (1 - 0.3) * 2.0, places=8)
            self.assertAlmostEqual(face_radii[1], neutral_radius / fraction - 0.3 * 2.0, places=8)
            self.assertAlmostEqual((mid_radius - (0.5 - 0.3) * 2.0) * applied,
                                   allowance, places=12)
            if fraction == 0.00001:
                self.assertAlmostEqual(mid[0], 30.0 + allowance, places=4)
                self.assertAlmostEqual(mid[2], 0.0, places=4)

    def test_negative_noncentral_k_factor_has_correct_surface_radii(self):
        raw = definition()
        raw["bends"][0].update(angle_deg=-60.0, inside_radius_mm=3.0,
                                k_factor=0.3, segments=1)
        mesh = fold_sheet(raw)["folded_mesh"]
        end = mesh["vertices"][8:12]
        center = (30.0, -(3.0 + 1.0))
        radii = []
        for vertex in end[:2]:
            x, _, z = vertex["position_mm"]
            radii.append(math.hypot(x - center[0], z - center[1]))
        self.assertAlmostEqual(radii[0], 3.0, places=12)
        self.assertAlmostEqual(radii[1], 5.0, places=12)

    def test_mesh_is_closed_consistently_oriented_and_positive_volume(self):
        for mesh in fold_sheet(definition()).values():
            if not isinstance(mesh, dict) or "triangles" not in mesh:
                continue
            directed = Counter()
            undirected = Counter()
            for triangle in mesh["triangles"]:
                ids = triangle["vertex_ids"]
                for edge in zip(ids, ids[1:] + ids[:1]):
                    directed[edge] += 1
                    undirected[tuple(sorted(edge))] += 1
            self.assertTrue(all(count == 2 for count in undirected.values()))
            self.assertTrue(all(directed[(b, a)] == count for (a, b), count in directed.items()))
            self.assertGreater(signed_volume(mesh), 0.0)

    def test_multiple_parallel_bends_compose_in_sequence(self):
        raw = definition()
        first_end = 30.0 + 0.5 * math.pi * 5.0
        raw["bends"].append({"id": "b2", "start_x_mm": first_end + 10.0,
                             "angle_deg": -90.0, "inside_radius_mm": 4.0,
                             "k_factor": 0.5, "fixed_side": "negative_x", "segments": 8})
        result = fold_sheet(raw)
        end_vertices = result["folded_mesh"]["vertices"][-4:]
        last = [sum(v["position_mm"][i] for v in end_vertices) / 4 for i in range(3)]
        self.assertGreater(last[0], 30.0)
        self.assertGreater(last[2], 0.0)
        self.assertAlmostEqual(last[2], 20.0, places=12)

    def test_overlap_and_unsupported_fixed_side_are_rejected(self):
        raw = definition()
        raw["bends"].append({"id": "b2", "start_x_mm": 31.0, "angle_deg": 45.0,
                             "inside_radius_mm": 2.0, "k_factor": 0.5,
                             "fixed_side": "negative_x", "segments": 4})
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_sheet(raw)
        raw = definition()
        raw["bends"][0]["fixed_side"] = "positive_x"
        with self.assertRaisesRegex(ValueError, "negative_x"):
            validate_sheet(raw)
        raw = definition()
        raw["bends"][0]["inside_radius_mm"] = 0
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_sheet(raw)

    def test_recognized_material_snapshot_is_validated_and_regions_are_bounded(self):
        raw = definition()
        raw["sheet"]["material"] = material_snapshot(load_catalog()[0])
        self.assertEqual(validate_sheet(raw)["sheet"]["material"], raw["sheet"]["material"])
        raw["sheet"]["material"]["digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "recognized snapshot is invalid"):
            validate_sheet(raw)
        raw = definition(kind="flex_pcb")
        raw["flex_regions"] = [{"id": f"r{i}", "start_x_mm": 0.0, "end_x_mm": 1.0}
                               for i in range(257)]
        with self.assertRaisesRegex(ValueError, "at most 256"):
            validate_sheet(raw)

    def test_flex_bends_must_be_confined_to_declared_regions(self):
        raw = definition(kind="rigid_flex_pcb",
                         flex_regions=[{"id": "flex", "start_x_mm": 25.0, "end_x_mm": 45.0}])
        validate_sheet(raw)
        raw["flex_regions"][0]["end_x_mm"] = 35.0
        with self.assertRaisesRegex(ValueError, "confined"):
            validate_sheet(raw)

    def test_json_and_minimal_ascii_dxf_import(self):
        imported_json = import_sheet_text(json.dumps(definition()), "json")
        self.assertEqual(imported_json["id"], "coupon")
        self.assertEqual(validate_sheet(imported_json), imported_json)
        preview = fold_sheet(imported_json)
        self.assertTrue(all(vertex["id"].startswith("coupon:")
                            for vertex in preview["folded_mesh"]["vertices"]))
        reimported = import_sheet_text(json.dumps(imported_json), "json")
        self.assertEqual(fold_sheet(reimported), preview)
        dxf = """0
SECTION
2
HEADER
9
$INSUNITS
70
4
0
ENDSEC
0
SECTION
2
ENTITIES
0
LWPOLYLINE
70
1
10
0
20
0
10
50
20
0
10
50
20
20
10
0
20
20
0
ENDSEC
0
EOF
"""
        imported = import_sheet_text(dxf, "dxf")
        self.assertEqual(imported["sheet"]["length_mm"], 50.0)
        self.assertEqual(imported["sheet"]["width_mm"], 20.0)
        self.assertIsNone(imported["sheet"]["thickness_mm"])
        self.assertEqual(imported["import_status"], "requires_thickness")
        self.assertTrue(imported["sheet"]["material"]["thickness_requires_review"])
        unsupported = dxf.replace("LWPOLYLINE", "LINE")
        with self.assertRaisesRegex(ValueError, "LINE is unsupported"):
            import_sheet_text(unsupported, "dxf")
        coordinates = """10
0
20
0
10
50
20
0
10
50
20
20
10
0
20
20"""
        bowtie = """10
0
20
0
10
50
20
20
10
50
20
0
10
0
20
20"""
        with self.assertRaisesRegex(ValueError, "cyclic order"):
            import_sheet_text(dxf.replace(coordinates, bowtie), "dxf")
        mismatched = coordinates.rsplit("\n20\n20", 1)[0]
        with self.assertRaisesRegex(ValueError, "matching x and y"):
            import_sheet_text(dxf.replace(coordinates, mismatched), "dxf")
        for codes, message in (("38\n1\n", "elevation"), ("39\n1\n", "thickness"),
                               ("210\n1\n", "extrusion")):
            malformed = dxf.replace("0\nLWPOLYLINE\n", "0\nLWPOLYLINE\n" + codes)
            with self.assertRaisesRegex(ValueError, message):
                import_sheet_text(malformed, "dxf")
        unitless = import_sheet_text(dxf.replace("$INSUNITS\n70\n4", "$INSUNITS\n70\n0"), "dxf")
        self.assertEqual(unitless["sheet"]["material"]["source_units"], "unitless")
        self.assertEqual(unitless["sheet"]["material"]["interpreted_units"], "mm")
        self.assertTrue(unitless["sheet"]["material"]["units_assumption_requires_review"])

    def test_checked_in_example_executes(self):
        root = Path(__file__).resolve().parents[2]
        raw = json.loads((root / "examples/mcad/folded-sheet.spike-sheet.json").read_text())
        result = fold_sheet(raw)
        self.assertEqual(result["model_status"], "analytical_geometry_preview")
        self.assertEqual(len(result["bends"]), 2)


if __name__ == "__main__":
    unittest.main()
