# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from python.spike_core.openfoam_turbulence import validate_turbulence_model, turbulence_dictionary, field_bodies, turbulence_schemes, turbulence_solution


def model():
    return {'type':'kOmegaSST','initial_k_m2_s2':.001,'inlet_k_m2_s2':.001,
            'initial_omega_per_s':100,'inlet_omega_per_s':100,'turbulent_prandtl':.85}


class TurbulenceTests(unittest.TestCase):
    def test_laminar_unchanged(self):
        self.assertIsNone(validate_turbulence_model(None))
        self.assertEqual(turbulence_dictionary(None),'simulationType laminar;\n')
        self.assertEqual(field_bodies(None,{}),{})

    def test_explicit_parameters(self):
        self.assertEqual(validate_turbulence_model(model()),model())
        for key,value in [('type','LES'),('initial_k_m2_s2',False),('inlet_omega_per_s',-1),
                          ('turbulent_prandtl',float('nan')),('turbulent_prandtl',.01),('initial_k_m2_s2',10**1000)]:
            raw=model(); raw[key]=value
            with self.assertRaises(ValueError): validate_turbulence_model(raw)
        raw=model(); raw['native_code']='execute'
        with self.assertRaises(ValueError): validate_turbulence_model(raw)

    def test_boundary_dimensions(self):
        fields=field_bodies(model(),{'inlet':'fan:f','exit':'external:pressure_outlet','wall':'external:adiabatic','board':'interface:contact'})
        self.assertEqual(set(fields),{'k','omega','nut','alphat'})
        self.assertIn('dimensions [1 -1 -1 0 0 0 0]',fields['alphat'])
        self.assertIn('compressible::alphatWallFunction',fields['alphat'])
        self.assertIn('omegaWallFunction',fields['omega'])
        self.assertIn('inletOutlet',fields['k'])
        self.assertIn('fixedValue',fields['k'])
        with self.assertRaises(ValueError): field_bodies(model(),{'wall;execute':'external:adiabatic'})

    def test_schemes_and_solver(self):
        self.assertIn('div(phi,omega)',turbulence_schemes('divSchemes { default none; }'))
        self.assertIn('omegaFinal',turbulence_solution('solvers\n{\n}\n'))
        self.assertIn('kOmegaSSTCoeffs { Prt',turbulence_dictionary(model()))

    def test_materialized_sst_fields_and_no_laminar_energy_claim(self):
        from python.spike_core import openfoam_fan_fixture as fixture
        original = fixture.prepare_runnable_multiregion_case
        def prepare(request,*args,**kwargs):
            request['environment']['turbulence_model']=model()
            return original(request,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'fixture'
            with patch.object(fixture,'prepare_runnable_multiregion_case',side_effect=prepare):
                fixture.build_fan_heated_fixture(root,divisions=2,end_time_s=.01,write_interval_steps=10)
            case=root/'case'
            self.assertIn('RASModel kOmegaSST',(case/'constant/air/turbulenceProperties').read_text())
            for field in ('k','omega','nut','alphat'):
                self.assertTrue((case/'0/air'/field).is_file())
            control=(case/'system/controlDict').read_text()
            self.assertIn('type yPlus',control)
            self.assertNotIn('gradT_air',control)
            self.assertFalse((case/'constant/geometryDiagnostic.json').exists())


if __name__=='__main__': unittest.main()
