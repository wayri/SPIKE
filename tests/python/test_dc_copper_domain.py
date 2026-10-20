# SPDX-License-Identifier: Apache-2.0
"""Source-void and explicit physical footprint admission regressions."""
import unittest
from shapely.geometry import Point, box

from python.spike_core.contracts import AnalysisSpec, SpiDeR
from python.spike_core.dc_copper_domain import source_copper_groups, explicit_terminal_contacts
from python.spike_core.dc_triangle_partition import partition_polygon_groups


class CopperDomainTests(unittest.TestCase):
    def design(self):
        return SpiDeR(layers=[{"name":"F.Cu"},{"name":"B.Cu"}],
            stackup=[{"name":"F.Cu","type":"copper","thickness":.035},
                     {"name":"core","type":"dielectric","thickness":1.5},
                     {"name":"B.Cu","type":"copper","thickness":.035}],
            tracks=[{"id":"track","net_name":"N","layer":"F.Cu",
                     "start":[-2,0],"end":[2,0],"width":1.}])

    def test_foreign_net_and_unassigned_npth_drills_cut_selected_tracks(self):
        for net in ("OTHER",""):
            d = self.design()
            d.pads=[{"id":"hole","net_name":net,"layers":["B.Cu"],"at":[0,0],
                     "shape":"circle","size":[1.,1.],"drill":.8,"type":"np_thru_hole"}]
            groups,axial = source_copper_groups(d,["N"])
            copper = groups["F.Cu","N"]["geometry"]
            self.assertFalse(copper.covers(Point(0,0)))
            self.assertTrue(copper.covers(Point(1,0)))
            self.assertEqual(axial,[])
            self.assertEqual(len(groups["F.Cu","N"]["source_inventory"]),1)

    def test_roundrect_and_oval_drill_keep_actual_void_and_outer_radius(self):
        d=self.design()
        d.tracks=[]
        d.pads=[{"id":"land","net_name":"N","layers":["F.Cu"],"at":[0,0],
                 "shape":"roundrect","size":[2.,1.5],"roundrect_rratio":.2,
                 "drill_size":[.8,.5],"drill_shape":"oval","rotation":23.,"type":"thru_hole"}]
        groups,axial = source_copper_groups(d,["N"])
        copper = groups["F.Cu","N"]["geometry"]
        self.assertFalse(copper.covers(Point(0,0)))
        self.assertEqual(len(axial),1)
        self.assertGreater(copper.area,2.5)
        self.assertLess(copper.area,3.)

    def test_drilled_smd_unknown_and_conflicting_kinds_are_not_void_authority(self):
        for fields in ({"type":"smd"},{"pad_kind":"smd"},{"type":"unknown"},{},
                       {"type":"thru_hole","pad_kind":"smd"},
                       {"type":"thru_hole","plated":False}):
            with self.subTest(fields=fields):
                d=self.design()
                d.pads=[{"id":"foreign","net_name":"OTHER","layers":["B.Cu"],
                         "at":[0,0],"shape":"circle","size":[1.,1.],"drill":.8,**fields}]
                with self.assertRaisesRegex(ValueError,"kind|plating"):
                    source_copper_groups(d,["N"])

    def test_selected_npth_does_not_invent_a_land_or_barrel(self):
        d=self.design()
        d.pads=[{"id":"npth","net_name":"N","layers":["F.Cu","B.Cu"],
                 "at":[0,0],"shape":"circle","size":[1.,1.],"drill":.8,
                 "type":"np_thru_hole","pad_kind":"np_thru_hole"}]
        with self.assertRaisesRegex(ValueError,"selected NPTH copper support is unspecified"):
            source_copper_groups(d,["N"])
        d.pads[0]["plated"]=True
        with self.assertRaisesRegex(ValueError,"plating"):
            source_copper_groups(d,["N"])

    def test_cross_group_prism_overlap_and_boolean_contact_node_rejected(self):
        group={"geometry":box(0,0,1,1),"z_mm":0.,"thickness_mm":.035,"conductivity_s_m":5.8e7}
        with self.assertRaisesRegex(ValueError,"prisms overlap"):
            partition_polygon_groups({("F.Cu","N"):group,("B.Cu","OTHER"):group},[],target_mm=.5)
        with self.assertRaisesRegex(ValueError,"pre-existing node"):
            partition_polygon_groups({("F.Cu","N"):group},
                [{"id":"bad","layer":"F.Cu","net":"N","geometry":box(.1,.1,.2,.2),"node":True}],target_mm=.5)

    def test_explicit_contact_does_not_mutate_request_and_must_cover_position(self):
        spec=AnalysisSpec(mode="dc",net_names=["N"],sources=[{"id":"s","layer":"F.Cu",
            "position_mm":[.5,.5],"contact_polygon_mm":[[0,0],[1,0],[1,1],[0,1]]}])
        contacts=explicit_terminal_contacts(spec)
        self.assertAlmostEqual(contacts[0]["geometry"].area,1.)
        self.assertNotIn("node",spec.sources[0])
        spec.sources[0]["position_mm"]=[2,2]
        with self.assertRaisesRegex(ValueError,"does not cover"):
            explicit_terminal_contacts(spec)

    def test_contacts_reused_across_refinement_and_failure_remain_unchanged(self):
        group={"geometry":box(0,0,2,1),"z_mm":0.,"thickness_mm":.035,"conductivity_s_m":5.8e7}
        contacts=[{"id":"source","layer":"F.Cu","net":"N","geometry":box(0,0,.5,1)},
                  {"id":"load","layer":"F.Cu","net":"N","geometry":box(1.5,0,2,1)}]
        original=[dict(contact) for contact in contacts]
        for target in (.5,.25):
            mesh=partition_polygon_groups({("F.Cu","N"):group},contacts,target_mm=target)
            returned=mesh.branch_admission["conforming_partition"]["terminal_contacts"]
            self.assertEqual([contact["id"] for contact in returned],["source","load"])
            self.assertEqual([contact["node"] for contact in returned],[0,1])
            self.assertEqual(contacts,original)
        # Budget failure occurs after contact nodes are allocated locally.
        with self.assertRaisesRegex(ValueError,"budget"):
            partition_polygon_groups({("F.Cu","N"):group},contacts,target_mm=.001,max_triangles=10)
        self.assertEqual(contacts,original)
        self.assertTrue(all("node" not in contact for contact in contacts))


if __name__ == "__main__":
    unittest.main()
