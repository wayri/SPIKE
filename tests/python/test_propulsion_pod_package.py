# SPDX-License-Identifier: Apache-2.0
"""Tamper admission for retained loop packaging; fixtures are not physics runs."""
import copy
from pathlib import Path
import tempfile
import unittest
from examples.promo_showcase.propulsion_pod.coupled.package_geometry_loop import (
    canonical_hash,digest,validate_capture_inputs,validate_native_sources)


class PackageIdentityTests(unittest.TestCase):
    def setUp(self):
        self.request={'transient':{'duration_s':.003}}
        self.magnetic={'contract':'fixture-only','values':[1,2]}
        self.fluid={'contract':'fixture-only','values':[3,4]}
        self.hashes={key:letter*64 for key,letter in (
            ('magnetic_table','a'),('cfd_table','b'),('request','c'))}
        self.result={'contract':'spike/geometry-propulsion-loop-result/v1','status':'completed',
            'production_qualified':False,'physical_load_qualified':False,
            'request':copy.deepcopy(self.request),'input_file_sha256':dict(self.hashes),
            'field_table_sha256':canonical_hash(self.magnetic),'fluid_port_sha256':canonical_hash(self.fluid),
            'accepted_steps':3,'history':[{'time_s':k*.001} for k in range(4)]}

    def check_inputs(self,result=None,magnetic=None):
        validate_capture_inputs(self.result if result is None else result,self.request,
            self.magnetic if magnetic is None else magnetic,self.fluid,self.hashes)

    def test_representation_hash_is_order_independent_and_byte_hash_not_optional(self):
        self.check_inputs()
        self.check_inputs(magnetic={'values':[1,2],'contract':'fixture-only'})
        changed=copy.deepcopy(self.result);changed['input_file_sha256']['request']='d'*64
        with self.assertRaisesRegex(ValueError,'input-file'):self.check_inputs(changed)
        with self.assertRaisesRegex(ValueError,'Constitutive'):self.check_inputs(magnetic={'values':[1,3]})

    def test_incomplete_or_qualification_escalating_capture_refused(self):
        for key,value in (('status','running'),('physical_load_qualified',True),
                          ('production_qualified',True),('accepted_steps',4)):
            changed=copy.deepcopy(self.result);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check_inputs(changed)
        changed=copy.deepcopy(self.result);changed['history'][-1]['time_s']=.002
        with self.assertRaisesRegex(ValueError,'span'):self.check_inputs(changed)
        changed=copy.deepcopy(self.result);changed['request']['transient']['duration_s']=.004
        with self.assertRaisesRegex(ValueError,'request differ'):self.check_inputs(changed)

    def test_native_scene_must_match_port_sources_and_exact_adjacent_assets(self):
        scratch=Path(__file__).resolve().parents[2]/'output/.tmp'
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            folder=Path(temporary)
            names=('CIAG_2_28 125_25.step','CASALINO_D30cm_pitch+5deg.stl')
            for name in names:(folder/name).write_bytes(name.encode())
            files={name:digest(folder/name) for name in names}
            preparation={'asset_manifest':{'files':files}}
            magnetic={'source_field_evidence':[{'source_sha256':files[names[0]]}]}
            fluid={'evidence':{'source_geometry_sha256':files[names[1]]}}
            validate_native_sources(preparation,magnetic,fluid,folder)
            with self.assertRaisesRegex(ValueError,'Field source'):
                validate_native_sources(preparation,{'source_field_evidence':[]},fluid,folder)
            with self.assertRaisesRegex(ValueError,'Fluid source'):
                validate_native_sources(preparation,magnetic,{'evidence':{'source_geometry_sha256':'a'*64}},folder)
            (folder/names[0]).write_bytes(b'different-source')
            with self.assertRaisesRegex(ValueError,'asset bytes'):
                validate_native_sources(preparation,magnetic,fluid,folder)


if __name__=='__main__':unittest.main()
