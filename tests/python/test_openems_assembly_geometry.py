# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Exact geometry/air-gap assertions, without pretending a mock solves fields."""
import copy
import unittest
from unittest.mock import Mock
from python.spike_core.openems_assembly_geometry import compile_assembly_geometry,emit_csxcad_geometry


def fixture():
    boxes=[{"id":"substrate","kind":"dielectric","start_mm":[0,0,-1],"stop_mm":[30,10,0],
            "epsilon_r":4.,"conductivity_s_m":0.},
           {"id":"strip","kind":"conductor","start_mm":[0,4,0],"stop_mm":[30,5,.035],
            "epsilon_r":1.,"conductivity_s_m":5.8e7}]
    return {"contract":"spike/openems-box-assembly/v1","air_margin_mm":10.,"boards":[
        {"id":name,"world_from_local_mm":[1,0,0,0,0,1,0,0,0,0,1,z,0,0,0,1],"boxes":copy.deepcopy(boxes)}
        for name,z in (("A",0),("B",5))]}


class AssemblyGeometryTests(unittest.TestCase):
    def test_separate_boards_and_intervening_air(self):
        raw=fixture();out=compile_assembly_geometry(raw)
        dielectric=[b for b in out["boxes"] if b["kind"]=="dielectric"]
        self.assertEqual([(b["start_mm"][2],b["stop_mm"][2]) for b in dielectric],[(-1,0),(4,5)])
        self.assertEqual(out["background"]["epsilon_r"],1.)
        self.assertFalse(any(all(b["start_mm"][i]<p<b["stop_mm"][i] for i,p in enumerate((10,4.5,2))) for b in out["boxes"]))
        raw["boards"][0]["boxes"][0]["epsilon_r"]=7
        self.assertEqual(dielectric[0]["epsilon_r"],4)
        self.assertNotEqual(out["input_sha256"],compile_assembly_geometry(raw)["input_sha256"])

    def test_right_angle_rotation_exact_volume(self):
        raw=fixture();raw["boards"]=raw["boards"][:1]
        raw["boards"][0]["world_from_local_mm"]=[0,-1,0,100,1,0,0,20,0,0,1,3,0,0,0,1]
        box=compile_assembly_geometry(raw)["boxes"][0]
        self.assertEqual(box["start_mm"],[90,20,2]);self.assertEqual(box["stop_mm"],[100,50,3])

    def test_overlap_oblique_and_nonfinite_rejected(self):
        raw=fixture();raw["boards"][1]["world_from_local_mm"][11]=0
        with self.assertRaisesRegex(ValueError,"Overlapping"):compile_assembly_geometry(raw)
        raw=fixture();c=2**-.5;raw["boards"][0]["world_from_local_mm"]=[c,-c,0,0,c,c,0,0,0,0,1,0,0,0,0,1]
        with self.assertRaisesRegex(ValueError,"axis-permutation"):compile_assembly_geometry(raw)
        for value in (float("nan"),float("inf"),True):
            raw=fixture();raw["air_margin_mm"]=value
            with self.assertRaises(ValueError):compile_assembly_geometry(raw)

    def test_csxcad_lowering_and_fail_before_mutation(self):
        csx=Mock();raw=fixture();compiled=emit_csxcad_geometry(csx,raw)
        self.assertEqual(csx.AddMaterial.call_count,4)
        calls=csx.AddMaterial.return_value.AddBox.call_args_list
        self.assertEqual(calls[2].args,([0.,0.,4.],[30.,10.,5.]))
        self.assertEqual(calls[1].kwargs,{"priority":10})
        raw["boards"][0]["boxes"][0]["stop_mm"][0]=0
        csx.reset_mock()
        with self.assertRaises(ValueError):emit_csxcad_geometry(csx,raw)
        csx.AddMaterial.assert_not_called()
        self.assertFalse(compiled["production_qualified"])

    def test_resource_identity_and_unknown_fields(self):
        for change in (lambda r:r.update(extra=1),
                       lambda r:r["boards"].__setitem__(1,copy.deepcopy(r["boards"][0])),
                       lambda r:r["boards"][0].__setitem__("boxes",r["boards"][0]["boxes"]*129)):
            raw=fixture();change(raw)
            with self.assertRaises(ValueError):compile_assembly_geometry(raw)

    def test_transform_reflection_shear_scale_and_homogeneous_row(self):
        for index,value in ((0,-1),(1,1),(0,2),(12,1),(15,2),(3,True)):
            raw=fixture();raw["boards"][0]["world_from_local_mm"][index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                compile_assembly_geometry(raw)
