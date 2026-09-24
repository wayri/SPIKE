# SPDX-License-Identifier: MIT
"""Area, connectivity, and resistance oracles for opt-in owned copper."""
import math
import unittest
from dataclasses import replace

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import _Builder, _point_in_polygon
from python.spike_core.hybrid_owned_copper import area, difference, hull
from python.spike_core.hybrid_dc_solver import solve_hybrid_dc


def builder(pad, target=.25, zone=True):
    design = DesignIR(layers=[{"name":"F.Cu"}], nets=[{"id":1,"name":"VCC"}],
        stackup=[{"name":"F.Cu","type":"copper","thickness":.035}],
        pads=[dict(id="pad",net_name="VCC",layers=["F.Cu"],at=[0,0],pad_kind="smd",
                   zone_connection_override="inherit",zone_connection_declared=False,thermal_settings_valid=True,**pad)],
        zones=([{"id":"zone","net_name":"VCC","layer":"F.Cu","points":[[-3,-3],[3,-3],[3,3],[-3,3]],
                 "source_zone_id":"source-zone","filled_copper_id":"zone","zone_kind":"copper",
                 "filled_copper_state":"source_filled","zone_connection_default":"solid","zone_connection_declared":True,
                 "clearance_mm":.2,"thermal_gap_mm":.2,"thermal_spoke_width_mm":.2,"fill_mode":"solid","thermal_settings_valid":True}] if zone else []))
    return _Builder(design,AnalysisSpec(mode="dc",net_names=["VCC"],mesh={
        "target_size_mm":target,"zone_cell_mm":target,"pad_zone_coupling":"owned_shared_faces"}))


class OwnedCopperTests(unittest.TestCase):
    def test_convex_difference_area_and_disjoint_pieces(self):
        square=[(-2,-2),(2,-2),(2,2),(-2,2)]
        diamond=[(0,-1),(1,0),(0,1),(-1,0)]
        pieces=difference(square,diamond)
        self.assertAlmostEqual(sum(area(p) for p in pieces),14)
        for i,p in enumerate(pieces):
            self.assertAlmostEqual(area(p)-sum(area(q) for q in difference(p,diamond)),0)
            for other in pieces[:i]:
                self.assertAlmostEqual(area(p)-sum(area(q) for q in difference(p,hull(other))),0)

    def test_rotated_pad_owns_overlap_and_has_distributed_faces(self):
        b=builder({"shape":"rect","size":[2,1],"rotation":31})
        mesh=b.build()
        self.assertFalse([i for i in mesh.issues if i.severity=="error"])
        self.assertAlmostEqual(sum(area([p[:2] for p in c["vertices_mm"]]) for c in mesh.cells if c["source_kind"] in {"zone","pad"}),36,places=7)
        contacts=mesh.branch_admission["owned_copper"]["contacts"]
        self.assertGreater(contacts[0]["face_count"],4)
        self.assertAlmostEqual(contacts[0]["face_length_mm"],6,places=5)
        profile=b.owned_pad_profiles[("F.Cu","VCC")]["pad"]
        for region in b.zone_regions:
            for poly in region["cell_polygons"].values():
                self.assertLess(abs(area(poly)-sum(area(p) for p in difference(poly,profile["outline"]))),1e-8)

    def test_pad_drill_has_no_zone_copper_and_union_area_is_conserved(self):
        b=builder({"shape":"circle","size":[2,2],"drill":.8,"drill_size":[.8,.8]})
        mesh=b.build()
        self.assertFalse([i for i in mesh.issues if i.severity=="error"])
        audit=mesh.branch_admission["owned_copper"]
        metal=sum(area([p[:2] for p in c["vertices_mm"]]) for c in mesh.cells if c["source_kind"] in {"zone","pad"})
        self.assertAlmostEqual(metal,36-audit["pad_void_area_mm2"],places=7)
        self.assertGreater(audit["pad_void_area_mm2"],math.pi*.4**2)
        for region in b.zone_regions:
            for poly in region["cell_polygons"].values():
                self.assertTrue(all(math.hypot(*p)>=.4-1e-8 for p in poly))

    def test_roundrect_outline_survives_grid_clipping(self):
        for rotation in (0,31):
            b=builder({"shape":"roundrect","size":[1.016,1.016],"roundrect_rratio":.5,"rotation":rotation},.5)
            mesh=b.build()
            self.assertFalse([i for i in mesh.issues if i.severity=="error"])
            self.assertAlmostEqual(sum(area([p[:2] for p in c["vertices_mm"]]) for c in mesh.cells if c["source_kind"] in {"zone","pad"}),36,places=7)

    def test_concave_zone_centroids_remain_in_copper_without_dropping_area(self):
        b=builder({"shape":"rect","size":[1,1]},1)
        b.design.pads=[]
        polygon=[(0,0),(1,0),(1,.2),(.2,.2),(.2,1),(0,1)]
        b.design.zones[0]["points"]=polygon
        mesh=_Builder(b.design,b.spec).build()
        self.assertFalse([i for i in mesh.issues if i.severity=="error"])
        self.assertAlmostEqual(sum(area([p[:2] for p in c["vertices_mm"]]) for c in mesh.cells),.36)
        for node in mesh.nodes:self.assertTrue(_point_in_polygon((node.x_mm,node.y_mm),polygon,1e-9))
        links={node.id:set() for node in mesh.nodes}
        for branch in mesh.branches:
            links[branch.node_p].add(branch.node_n);links[branch.node_n].add(branch.node_p)
        visited=set();pending=[0]
        while pending:
            n=pending.pop()
            if n not in visited:visited.add(n);pending.extend(links[n]-visited)
        self.assertEqual(len(visited),len(mesh.nodes))

    def test_radial_annulus_resistance_and_area_converge(self):
        expected=math.log(2)/(2*math.pi*5.8e7*.035e-3)
        errors=[]
        for target in (.5,.25,.125):
            b=builder({"shape":"circle","size":[4,4],"drill":2,"drill_size":[2,2]},target,zone=False)
            mesh=b.build()
            cells=[c for c in mesh.cells if c["source_kind"]=="pad"]
            rings=[(int(c["id"].split(":")[-2]),c["node_id"]) for c in cells]
            last=max(r for r,n in rings); sides=sum(r==0 for r,n in rings)
            count=len(mesh.nodes); source=count; sink=count+1
            edges=[(e.node_p,e.node_n,1/e.resistance_ohm) for e in mesh.branches if e.kind=="pad"]
            # Exact continuum half-cell boundary resistances isolate the
            # production interior radial discretization from electrode snapping.
            for ring,node in rings:
                radius=math.hypot(mesh.nodes[node].x_mm,mesh.nodes[node].y_mm)
                if ring==0: edges.append((source,node,5.8e7*.035e-3*(2*math.pi/sides)/math.log(radius)))
                if ring==last: edges.append((node,sink,5.8e7*.035e-3*(2*math.pi/sides)/math.log(2/radius)))
            rows=[];cols=[];values=[]
            for a,c,g in edges:
                rows.extend((a,c,a,c));cols.extend((a,c,c,a));values.extend((g,g,-g,-g))
            matrix=coo_matrix((values,(rows,cols)),shape=(count+2,count+2)).tocsr()
            voltage=spsolve(matrix[:count,:count],-matrix[:count,source].toarray().ravel())
            current=sum(g*(1-voltage[c]) for a,c,g in edges if a==source)
            resistance=1/current
            errors.append(abs(resistance/expected-1))
            self.assertLess(sum(area([p[:2] for p in c["vertices_mm"]]) for c in cells),3*math.pi)
        self.assertLess(errors[-1],.01)
        self.assertLess(errors[-1],errors[0])

    def test_unsupported_shape_fails_closed(self):
        mesh=builder({"shape":"custom","size":[2,2]}).build()
        self.assertTrue(any(i.severity=="error" and i.status=="unsupported" for i in mesh.issues))

    def test_missing_source_fill_and_invalid_thermal_policy_fail_closed(self):
        for mutation in ("fill","thermal"):
            b=builder({"shape":"rect","size":[2,2]})
            if mutation=="fill": b.design.zones[0]["filled_copper_state"]="unfilled"
            else: b.design.pads[0]["thermal_settings_valid"]=False
            mesh=_Builder(b.design,b.spec).build()
            self.assertFalse(mesh.branches)
            self.assertTrue(any(i.severity=="error" for i in mesh.issues))

    def test_none_policy_cannot_gain_a_shared_face_contact(self):
        b=builder({"shape":"rect","size":[2,2]})
        b.design.pads[0].update(zone_connection_override="none",zone_connection_declared=True)
        mesh=_Builder(b.design,b.spec).build()
        self.assertFalse(any(b.kind=="pad_zone_attachment" for b in mesh.branches))

    def test_owned_dc_kcl_and_dissipation_balance(self):
        b=builder({"shape":"rect","size":[.5,6]})
        pad=b.design.pads[0]
        b.design.pads=[dict(pad,id="source",at=[-2.75,0]),dict(pad,id="load",at=[2.75,0])]
        spec=replace(b.spec,sources=[{"id":"source","position_mm":[-2.75,0],"layer":"F.Cu","voltage_v":1,
            "geometry_anchor":{"type":"pad","id":"source"}}],
            loads=[{"id":"load","position_mm":[2.75,0],"layer":"F.Cu","current_a":1,
            "geometry_anchor":{"type":"pad","id":"load"}}],options={"require_exact_terminal_geometry":True})
        result=solve_hybrid_dc(b.design,spec)
        self.assertEqual(result.status,"completed",result.issues)
        evidence=result.networks["source_to_load"]
        self.assertEqual(evidence["status"],"validated")
        self.assertLess(abs(evidence["source_current_balance_a"]),1e-7)
        self.assertLess(result.summary["max_scaled_linear_residual"],1e-8)
        loss=result.summary["total_copper_loss_w"]
        self.assertLess(abs(loss-evidence["paths"][0]["supply_drop_v"])/loss,1e-7)


if __name__=="__main__":unittest.main()
