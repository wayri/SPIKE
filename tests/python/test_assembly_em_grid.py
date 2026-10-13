# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from python.spike_core.assembly_em_grid import retained_em_grid_axes
from python.spike_core.assembly_em import prepare_assembly_em
from tests.python.test_assembly_em import fixture


class RetainedEmGridTests(unittest.TestCase):
    def test_sampling_preserves_geometry_ports_z_and_spacing(self):
        compiled={'primitives':[{'vertices_m':[[0,0,0],[.00123,.00234,.000035]]},
                                {'vertices_m':[[.00123000001,.00234000001,.001],[.012,.013,.001035]]}],
                  'ports':[{'start_m':[.002,.003,.000035],'stop_m':[.004,.005,.001]}]}
        original=copy.deepcopy(compiled)
        settings={'mesh_resolution_m':.001,'air_margin_m':.004,'mesh_policy':'cartesian_sampling_v1'}
        axes=retained_em_grid_axes(compiled,settings)
        self.assertEqual(compiled,original)
        for axis in range(3):
            for port in compiled['ports']:
                for end in ['start_m','stop_m']:self.assertIn(port[end][axis],axes[axis])
            self.assertTrue(all(0<b-a<=.0010000000001 for a,b in zip(axes[axis],axes[axis][1:])))
        for z in [0,.000035,.001,.001035]:self.assertIn(z,axes[2])
        self.assertNotIn(.00123,axes[0])
        strict=retained_em_grid_axes(compiled,{k:v for k,v in settings.items() if k!='mesh_policy'})
        self.assertIn(.00123,strict[0])
        self.assertIn(.00123000001,strict[0])

    def test_sampling_requires_explicit_profile(self):
        value=fixture();value['settings']['mesh_policy']='cartesian_sampling_v1'
        with self.assertRaisesRegex(ValueError,'explicit routed EM profile'):prepare_assembly_em(value)
        value['geometry']['resource_profile']='routed_pcb_em_v1'
        self.assertEqual(prepare_assembly_em(value)['settings']['mesh_policy'],'cartesian_sampling_v1')
        value['settings']['mesh_policy']='unknown'
        with self.assertRaisesRegex(ValueError,'sampling policy'):prepare_assembly_em(value)

    def test_sampling_does_not_bypass_cell_budget(self):
        compiled={'primitives':[{'vertices_m':[[0,0,0],[1,1,1]]}],'ports':[]}
        with self.assertRaisesRegex(ValueError,'cell budget'):
            retained_em_grid_axes(compiled,{'mesh_resolution_m':.005,'air_margin_m':.01,'mesh_policy':'cartesian_sampling_v1'})

    def test_native_unused_materials_are_not_silently_qualified(self):
        from python.spike_core.assembly_em_diagnostics import native_material_sampling
        compiled={'primitives':[{'material':{'conductivity_s_m':5.8e7}},{'material':{'conductivity_s_m':0}}]}
        log='Warning: Unused primitive (type: Polyhedron) detected in property: spike_retained_0!\nWarning: Unused primitive (type: Polyhedron) detected in property: spike_retained_1!'
        value=native_material_sampling(log,compiled)
        self.assertFalse(value['geometry_sampling_complete'])
        self.assertEqual(value['unused_conductive_primitive_count'],1)
        self.assertEqual(value['unused_nonconductive_primitive_count'],1)
        self.assertIsNone(native_material_sampling('',compiled)['geometry_sampling_complete'])
        with self.assertRaisesRegex(ValueError,'unknown native material'):
            native_material_sampling(log.replace('retained_1','retained_2'),compiled)
