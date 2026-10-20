# SPDX-License-Identifier: Apache-2.0
"""Independent source/void/area checks for the bounded owned DC extension."""
import hashlib
import math
from dataclasses import replace
from pathlib import Path
import unittest

from python.spike_core.hybrid_mesh import (
    _Builder, _pad_world_to_local, _shared_polygon_face_length,
)
from python.spike_core.hybrid_owned_copper import area, centroid
from tests.python.test_hybrid_owned_copper import builder


J11 = dict(shape="roundrect", size=[1.7, 1.95], roundrect_rratio=.147059,
           drill=.95, drill_size=[.95, .95], drill_shape="circle")


def segment_distance_to_origin(a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    fraction = max(0, min(1, -(a[0]*dx+a[1]*dy)/(dx*dx+dy*dy)))
    return math.hypot(a[0]+fraction*dx, a[1]+fraction*dy)


class DrilledRoundrectTests(unittest.TestCase):
    def check_source_and_void(self, mesh, pad):
        self.assertFalse([i for i in mesh.issues if i.severity == "error"], mesh.issues)
        width, height = pad["size"]
        radius = min(width, height)*pad["roundrect_rratio"]
        cells = [c for c in mesh.cells if c["source_kind"] == "pad"]
        self.assertTrue(cells)
        polygons = {}
        for cell in cells:
            poly = [_pad_world_to_local(pad, tuple(p[:2])) for p in cell["vertices_mm"]]
            polygons[cell["node_id"]] = [tuple(p[:2]) for p in cell["vertices_mm"]]
            self.assertGreater(area(poly), 1e-12)
            # Exact segment-to-center minimum proves the entire edge avoids
            # the circular drill; every convex cell also lies outside it.
            for a, b in zip(poly, poly[1:]+poly[:1]):
                self.assertGreaterEqual(segment_distance_to_origin(a, b), pad["drill"]/2-1e-9)
                for k in range(9):
                    x, y = (a[j]+(b[j]-a[j])*k/8 for j in (0, 1))
                    corner_distance = math.hypot(max(abs(x)-(width/2-radius), 0),
                                                 max(abs(y)-(height/2-radius), 0))
                    self.assertLessEqual(corner_distance, radius+1e-9)
            node = mesh.nodes[cell["node_id"]]
            expected = centroid(polygons[cell["node_id"]])
            self.assertAlmostEqual(node.x_mm, expected[0], places=8)
            self.assertAlmostEqual(node.y_mm, expected[1], places=8)
        for branch in mesh.branches:
            if branch.kind == "pad":
                expected = _shared_polygon_face_length(polygons[branch.node_p], polygons[branch.node_n], 1e-8)
                self.assertGreater(expected, 1e-7)
                self.assertAlmostEqual(branch.width_mm, expected, places=8)
        return cells

    def test_j11_area_void_faces_and_rotation(self):
        for rotation in (0, 31, 90, -127):
            for target in (.5, .125, .05):
                with self.subTest(rotation=rotation, target=target):
                    b = builder(dict(J11, rotation=rotation), target, zone=False)
                    mesh = b.build()
                    cells = self.check_source_and_void(mesh, b.design.pads[0])
                    actual = sum(area([p[:2] for p in c["vertices_mm"]]) for c in cells)
                    w, h = J11["size"]; r = min(w,h)*J11["roundrect_rratio"]; a = J11["drill"]/2
                    n = max(24, min(192, math.ceil(math.pi*max(w,h)/target)))
                    exact = w*h-(4-math.pi)*r*r-math.pi*a*a
                    deficit = r*r/2*(2*math.pi-128*math.sin(2*math.pi/128)) + a*a*(n*math.tan(math.pi/n)-math.pi)
                    self.assertAlmostEqual(actual, exact-deficit, delta=1e-9)
                    self.assertLess(actual, exact)

    def test_zone_ownership_and_void_area_balance(self):
        b = builder(dict(J11, rotation=31), .5)
        mesh = b.build()
        self.check_source_and_void(mesh, b.design.pads[0])
        audit = mesh.branch_admission["owned_copper"]
        self.assertGreater(audit["contacts"][0]["face_count"], 4)
        total = sum(area([p[:2] for p in c["vertices_mm"]]) for c in mesh.cells
                    if c["source_kind"] in {"pad", "zone"})
        self.assertAlmostEqual(total, 36-audit["pad_void_area_mm2"], delta=1e-8)
        for cell in mesh.cells:
            if cell["source_kind"] != "zone":
                continue
            poly = [tuple(p[:2]) for p in cell["vertices_mm"]]
            for a, b in zip(poly, poly[1:]+poly[:1]):
                self.assertGreaterEqual(segment_distance_to_origin(a, b), .475-1e-9)

    def test_invalid_metadata_and_narrow_ligament_fail_closed(self):
        changes = [{"roundrect_rratio": value} for value in (None, -.1, .51, float("nan"), "bad", False)]
        changes += [{"size": [float("nan"), 2]}, {"size": [.001, 2]},
                    {"drill_size": [float("nan"), .95]}, {"drill_size": [0, .95]},
                    {"drill_offset": [0, .02]}, {"drill_offset": [float("nan"), 0]},
                    {"size": [True, 2]}, {"drill_size": [True, True]},
                    {"rotation": False}, {"at": [True, 0]}, {"at": [0]},
                    {"plating_thickness": True}, {"plating_thickness": None},
                    {"plating_thickness": .004}, {"plating_thickness": 0},
                    {"drill_offset": False}, {"drill_offset": []},
                    {"drill_shape": "polygon"}, {"drill_shape": "circle", "drill_size": [.8, 1]},
                    {"plating_thickness": float("nan")},
                    {"size": [.98, 1.2]},
                    {"size": [1.001, 1.001], "roundrect_rratio": .5, "drill": 1, "drill_size": [1, 1]}]
        for change in changes:
            with self.subTest(change=change):
                b = builder(J11, .5, zone=False)
                b.design.pads[0].update(change)
                mesh = b.build()
                self.assertFalse(mesh.branches)
                self.assertTrue(any(i.severity == "error" and i.status == "unsupported" for i in mesh.issues), mesh.issues)

    def test_budget_failure_precedes_cell_allocation(self):
        b = builder(J11, .05, zone=False)
        b.max_pad_cells = 4
        mesh = b.build()
        self.assertFalse(mesh.cells)
        self.assertFalse(mesh.branches)
        self.assertTrue(any("budget" in i.message for i in mesh.issues))

    def test_oval_drill_and_extreme_valid_radius_ratios(self):
        for ratio in (0, .147059, .5):
            mesh = builder(dict(J11, size=[2, 3], roundrect_rratio=ratio,
                                drill_shape="oval", drill_size=[.8, 1.2]), .25, zone=False).build()
            self.assertFalse([i for i in mesh.issues if i.severity == "error"], mesh.issues)
            for cell in mesh.cells:
                poly = [tuple(p[:2]) for p in cell["vertices_mm"]]
                # Capsule drill = vertical segment [-.2,.2] dilated by .4.
                for a, b in zip(poly, poly[1:]+poly[:1]):
                    for k in range(17):
                        x,y = (a[j]+(b[j]-a[j])*k/16 for j in (0,1))
                        self.assertGreaterEqual(math.hypot(x,max(abs(y)-.2,0)), .4-1e-9)

    def test_corner_track_attachment_does_not_use_rectangular_fallback(self):
        b = builder(J11, .25, zone=False)
        b.design.tracks = [dict(id="corner", net_name="VCC", layer="F.Cu",
                               start=[.84,.96], end=[1.2,1.2], width=.01)]
        mesh = _Builder(b.design, b.spec).build()
        self.assertFalse([i for i in mesh.issues if i.severity == "error"])
        self.assertFalse([e for e in mesh.branches if e.kind == "pad_attachment"])

    def test_owned_ac_guard_remains_closed(self):
        b = builder(J11, zone=False)
        mesh = _Builder(b.design, replace(b.spec, mode="ac")).build()
        self.assertFalse(mesh.branches)
        self.assertTrue(any(i.code == "OWNED_COPPER_UNSUPPORTED" for i in mesh.issues))


class NativeEBrakeDrilledRoundrectTests(unittest.TestCase):
    # Explicit fixture test imports the immutable real source, then isolates
    # its pad with original placement/layers/stackup. It is not a board solve.
    def test_native_j11_source_geometry_and_barrel_resistance(self):
        from python.spike_core.kicad_importer import import_kicad_design
        path = Path(__file__).resolve().parents[2]/"app/public/demo/ebrake1.kicad_pcb"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca")
        design = import_kicad_design(str(path))
        pad = next(p for p in design.pads if p.get("component_pad") == "J11.1")
        self.assertEqual(tuple(pad["size"]), (1.7,1.95))
        self.assertEqual(pad["roundrect_rratio"], .147059)
        self.assertEqual(pad["drill"], .95)
        isolated = replace(design, pads=[pad], tracks=[], vias=[], zones=[])
        spec = replace(builder(J11).spec, net_names=["3Vin"])
        mesh = _Builder(isolated, spec).build()
        DrilledRoundrectTests.check_source_and_void(self, mesh, pad)
        barrels = [e for e in mesh.branches if e.kind == "pad_barrel"]
        self.assertTrue(barrels)
        for edge in barrels:
            self.assertAlmostEqual(edge.width_mm*edge.thickness_mm, math.pi*(.95+.025)*.025, places=12)
            expected = edge.length_mm*1e-3/(5.8e7*math.pi*(.95+.025)*.025*1e-6)
            self.assertAlmostEqual(edge.resistance_ohm, expected, places=12)
        # The same real net also contains these two resolved convex custom
        # pads. Preserve their imported polygon instead of their anchor size.
        for name in ("U2.35", "U2.39"):
            custom = next(p for p in design.pads if p.get("component_pad") == name)
            source = custom["custom_geometry"]["positive_filled_polygon"]
            self.assertAlmostEqual(area(source), 4.8897876427994635, places=12)
            for target in (.5, .125):
                custom_design = replace(design, pads=[custom], tracks=[], vias=[], zones=[])
                custom_spec = replace(spec, mesh=dict(spec.mesh, target_size_mm=target))
                custom_mesh = _Builder(custom_design, custom_spec).build()
                self.assertFalse([i for i in custom_mesh.issues if i.severity == "error"], custom_mesh.issues)
                cells = [c for c in custom_mesh.cells if c["source_kind"] == "pad"]
                self.assertAlmostEqual(sum(area([p[:2] for p in c["vertices_mm"]]) for c in cells), area(source), delta=1e-8)
                for cell in cells:
                    local = [_pad_world_to_local(custom, p[:2]) for p in cell["vertices_mm"]]
                    from python.spike_core.hybrid_mesh import _polygon_is_contained_in
                    self.assertTrue(_polygon_is_contained_in(local, [tuple(p) for p in source], 1e-8))


if __name__ == "__main__":
    unittest.main()
