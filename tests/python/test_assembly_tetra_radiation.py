# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent ambient radiation analytical, refinement and failure oracles."""
import math
import unittest
from unittest.mock import patch
import numpy as np
from python.spike_core.assembly_tetra_radiation import SIGMA, radiation_operator
from python.spike_core.assembly_tetra_thermal import run_assembly_tetra_thermal, AssemblyTetraThermalError
from python.spike_core.assembly_field_thermal import run_assembly_field_thermal, verify_assembly_field_result
from python.spike_core.assembly_field_study import export_assembly_field_study, import_assembly_field_study
from tests.python.test_assembly_tetra_thermal import cube, request, boundary, faces_at
from tests.python.test_assembly_field_handoff import fixture


def slab(n=2, emissivity=.8):
    raw = request(cube(n))
    outward = 10*50 + emissivity*SIGMA*(350**4-300**4)
    raw['boundaries'] = boundary(faces_at(raw['mesh'], 0), 'heat_flux', heat_flux_w_m2=outward)
    raw['boundaries'] += boundary(faces_at(raw['mesh'], 1), 'convection_radiation',
        heat_transfer_coefficient_w_m2k=10, ambient_temperature_k=300,
        emissivity=emissivity, radiation_temperature_k=300)
    return raw, outward


class RadiationTests(unittest.TestCase):
    def test_combined_boundary_exact_slab_and_refinement(self):
        for n in (1, 2, 4):
            raw, power = slab(n)
            out = run_assembly_tetra_thermal(raw)
            np.testing.assert_allclose(out['node_temperatures_k'],
                [350+power/2*(1-p[0]) for p in raw['mesh']['vertices']], atol=2e-6)
            self.assertAlmostEqual(out['heat_balance']['convection_outward_w'], 500, places=6)
            self.assertAlmostEqual(out['heat_balance']['radiation_outward_w'], power-500, places=6)
            self.assertLess(out['diagnostics']['free_relative_residual'], 1e-10)
            self.assertGreater(out['diagnostics']['newton_iterations'], 0)

    def test_quadratic_source_refinement(self):
        # Original exact slab: k=2, q=1000; T=600-250*x^2, outward right=1000.
        errors=[]
        for n in (1,2,4):
            raw,_=slab(n)
            h=(1000-.8*SIGMA*(350**4-300**4))/50
            raw['boundaries']=boundary(faces_at(raw['mesh'],0),'temperature',temperature_k=600)
            raw['boundaries']+=boundary(faces_at(raw['mesh'],1),'convection_radiation',
                heat_transfer_coefficient_w_m2k=h,ambient_temperature_k=300,
                emissivity=.8,radiation_temperature_k=300)
            raw['heat_sources_w_m3']={c['id']:1000 for c in raw['mesh']['cells']}
            out=run_assembly_tetra_thermal(raw)
            t=np.array(out['node_temperatures_k'])
            xyz=np.array(raw['mesh']['vertices'])
            errors.append(math.sqrt(np.mean([(t[c['vertices']].mean()-
                (600-250*xyz[c['vertices'],0].mean()**2))**2 for c in raw['mesh']['cells']])))
            self.assertLess(abs(out['heat_balance']['imbalance_w']),1e-5)
        self.assertTrue(all(b<a/3 for a,b in zip(errors,errors[1:])),errors)

    def test_exact_nonuniform_face_moment_and_tangent(self):
        t = np.array([280., 410., 550.])
        area, emissivity, ambient = 2.3, .7, 300
        power, tangent = radiation_operator(t, [((0,1,2),area,emissivity,ambient)])
        # E[T^4] = (2!*4!)/(6!) sum_{a+b+c=4} T0^a*T1^b*T2^c.
        exact = sum(t[0]**a*t[1]**b*t[2]**(4-a-b) for a in range(5) for b in range(5-a))/15
        self.assertAlmostEqual(sum(power), area*emissivity*SIGMA*(exact-ambient**4), places=9)
        for i in range(3):
            delta = np.eye(3)[i]*1e-3
            plus, _ = radiation_operator(t+delta, [((0,1,2),area,emissivity,ambient)])
            minus, _ = radiation_operator(t-delta, [((0,1,2),area,emissivity,ambient)])
            np.testing.assert_allclose((plus-minus)/2e-3,tangent.toarray()[:,i],rtol=1e-9)

    def test_radiation_only_anchor_and_zero_emissivity(self):
        raw, _ = slab()
        raw['boundaries'] = [b for b in raw['boundaries'] if b['type']=='convection_radiation']
        for b in raw['boundaries']:
            b['type']='radiation'
            del b['ambient_temperature_k'], b['heat_transfer_coefficient_w_m2k']
        out = run_assembly_tetra_thermal(raw)
        np.testing.assert_allclose(out['node_temperatures_k'],300,atol=1e-7)
        for b in raw['boundaries']: b['emissivity']=0
        with self.assertRaisesRegex(AssemblyTetraThermalError,'Unanchored'):
            run_assembly_tetra_thermal(raw)
        raw, power=slab(emissivity=0)
        out=run_assembly_tetra_thermal(raw)
        self.assertEqual(out['heat_balance']['radiation_outward_w'],0)

    def test_bad_ranges_and_bounded_failure(self):
        for field, value in [('emissivity',-1),('emissivity',1.1),('emissivity',True),
                             ('radiation_temperature_k',0),('radiation_temperature_k',10001),
                             ('radiation_temperature_k',float('nan')),('ambient_temperature_k',0)]:
            raw,_=slab()
            raw['boundaries'][-1][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(AssemblyTetraThermalError):
                run_assembly_tetra_thermal(raw)
        raw,_=slab()
        with patch('python.spike_core.assembly_tetra_radiation.MAX_NEWTON_ITERATIONS',0):
            with self.assertRaisesRegex(AssemblyTetraThermalError,'Newton iteration'):
                run_assembly_tetra_thermal(raw)
        for b in raw['boundaries']:
            if b['type']=='heat_flux': b['heat_flux_w_m2']=1e15
        with self.assertRaisesRegex(AssemblyTetraThermalError,'range|converge'):
            run_assembly_tetra_thermal(raw)

    def test_field_adapter_saved_compatibility_and_balance_admission(self):
        req, problem=fixture()
        for b in problem['boundaries']:
            if b['face']['occurrence_id']=='case':
                b.pop('temperature_k')
                b.update(type='convection_radiation',heat_transfer_coefficient_w_m2k=10,
                         ambient_temperature_k=300,emissivity=.8,radiation_temperature_k=300)
            else: b['temperature_k']=400
        result=run_assembly_field_thermal(req,problem)
        verify_assembly_field_result(req,problem,result)
        saved=export_assembly_field_study(req,problem,result)
        self.assertEqual(import_assembly_field_study(saved)['result'],result)
        self.assertGreater(result['field_result']['heat_balance']['radiation_outward_w'],0)
        from python.spike_core.multiboard_identity import canonical_json_digest
        result['field_result']['heat_balance']['radiation_outward_w']+=1
        result['result_digest']=canonical_json_digest({k:v for k,v in result.items() if k!='result_digest'})
        with self.assertRaisesRegex(ValueError,'heat balance'):
            verify_assembly_field_result(req,problem,result)
        req,problem=fixture()
        old=run_assembly_field_thermal(req,problem)
        old['field_result']['heat_balance'].pop('radiation_outward_w')
        old['field_result']['diagnostics'].pop('newton_iterations')
        old['result_digest']=canonical_json_digest({k:v for k,v in old.items() if k!='result_digest'})
        verify_assembly_field_result(req,problem,old)
