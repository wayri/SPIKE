# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original coupled-solid conservation and explicit multiboard ownership tests."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from examples.assembly_field.run_examples import setup
from python.spike_core.assembly_electrothermal import run_assembly_electrothermal
from python.spike_core.multiboard_identity import canonical_json_digest


def request(alpha=0., multi_board=False):
    geometry,thermal = setup()
    if multi_board:
        part = geometry['assembly']['parts'].pop()
        geometry['assembly']['boards'].append({'id':'case','design_id':part['model_id'],'frame':part['frame']})
        geometry['bodies'][1]['stack_binding'] = {'id':'second-stack','source_sha256':'d'*64}
    geometry['assembly']['electrical_bonds'] = [{'id':'bond','endpoint_a':'board','endpoint_b':'case',
        'contact_area_mm2':1e6,'electrical_resistance_ohm':.25}]
    terminals = []
    for body,x,value in [(geometry['bodies'][0],0,0),(geometry['bodies'][1],1,2)]:
        for f in body['boundary_faces']:
            if all(body['mesh']['vertices'][v][0] == x for v in f['vertices']):
                terminals.append({'id':body['occurrence_id']+'-'+f['id'],
                                  'face':{'occurrence_id':body['occurrence_id'],'face_id':f['id']},'voltage_v':value})
    return {'contract':'spike/assembly-electrothermal-request/v1','geometry':geometry,'thermal_problem':thermal,
            'electrical':{'materials':[{'id':'k','conductivity_s_m':2,'temperature_coefficient_per_k':alpha,
                'reference_temperature_k':300,'temperature_range_k':[200,1000]}],
                'terminals':terminals,'contacts':[{'bond_id':'bond','face_pairs':thermal['contacts'][0]['face_pairs'],
                                                 'electrical_contact_conductance_s_m2':4}]},
            'heat_sources':[],'loss_accounting':'explicit_nonoverlapping_losses',
            'iteration':{'initial_temperature_k':300,'max_iterations':50,'relaxation':.8,
                         'temperature_tolerance_k':1e-6,'power_relative_tolerance':1e-9}}


class AssemblyElectrothermalTests(unittest.TestCase):
    def test_coupled_conduction_contact_loss_and_multiboard_ownership(self):
        for multi_board in (False,True):
            raw = request(multi_board=multi_board)
            before = copy.deepcopy(raw)
            result = run_assembly_electrothermal(raw)
            self.assertEqual(raw,before)
            # Electrical R=0.5+0.25+0.5=1.25 ohm; I=2/1.25=1.6 A.
            self.assertAlmostEqual(result['electrical']['source_power_w'],3.2,places=8)
            self.assertAlmostEqual(sum(result['cell_deposited_power_w'].values()),3.2,places=8)
            self.assertAlmostEqual(result['electrical']['contact_power_w'],.64,places=8)
            self.assertLess(abs(result['conservation']['thermal_imbalance_w']),1e-8)
            self.assertEqual(set(result['thermal']['occurrence_temperatures']),{'board','case'})
            self.assertFalse(result['production_qualified'])
            json.dumps(result,allow_nan=False)

    def test_temperature_feedback_reduces_current_and_fixed_point_is_checked(self):
        result = run_assembly_electrothermal(request(alpha=.004))
        self.assertLess(result['electrical']['source_power_w'],3.2)
        self.assertLess(result['history'][-1]['unrelaxed_temperature_defect_k'],1e-6)
        self.assertLess(result['history'][-1]['power_relative_defect'],1e-9)
        self.assertLess(result['coupled_power_defect_w'],1e-8)

    def test_waveform_spectral_and_semiconductor_heat_enters_actual_field(self):
        models = [
            {'kind':'terminal_waveform','time_s':[0,1],'voltage_v':[1,1],'current_a':[2,2],
             'energy_policy':'dissipative_terminal_power'},
            {'kind':'spectral_resistive','frequency_hz':[0,1000],'rms_current_a':[1,1],'resistance_ohm':[1,1]},
            {'kind':'semiconductor_loss_table','temperature_k':[200,1000],'conduction_power_w':[1,1],
             'turn_on_energy_j':[.1,.1],'turn_off_energy_j':[.1,.1],'reverse_recovery_energy_j':[0,0],
             'switching_frequency_hz':5,'energy_terms_nonoverlapping':True,'conditions':'Original bounded synthetic device fixture'}]
        for model in models:
            raw = request()
            raw['heat_sources'] = [{'contract':'spike/electrical-heat-source/v1','id':'device','model':model,
                'distribution':[{'occurrence_id':'board','cell_id':'0','weight':1}],
                'provenance':{'source_sha256':canonical_json_digest(model),'description':'Original test data, not measured device characterization'}}]
            result = run_assembly_electrothermal(raw)
            self.assertAlmostEqual(sum(result['cell_deposited_power_w'].values()),5.2,places=8)
            self.assertAlmostEqual(result['heat_source_results'][0]['average_power_w'],2,places=8)

    def test_nonconvergence_cancellation_and_unrepresented_links_fail(self):
        raw = request(alpha=.004)
        raw['iteration'].update(max_iterations=1,relaxation=1e-6)
        with self.assertRaisesRegex(ValueError,'NONCONVERGENCE'):
            run_assembly_electrothermal(raw)
        with self.assertRaisesRegex(ValueError,'CANCELLED'):
            run_assembly_electrothermal(request(),cancel_check=lambda:True)
        for mutation in [lambda r:r['electrical']['contacts'].clear(),
                         lambda r:r.update(loss_accounting='assume_no_overlap'),
                         lambda r:r['geometry']['assembly'].update(harnesses=[{'id':'h','endpoint_a':'board','endpoint_b':'case'}]),
                         lambda r:r['electrical']['materials'][0].update(temperature_range_k=[299,301])]:
            raw = request()
            mutation(raw)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                run_assembly_electrothermal(raw)

    def test_worker_exposes_bounded_coupled_method(self):
        from python.spike_core.service_assembly_field import handle_assembly_field_request
        answer = handle_assembly_field_request('run_assembly_electrothermal',{'request':request()})
        self.assertTrue(answer['ok'],answer)
        self.assertEqual(answer['result']['contract'],'spike/assembly-electrothermal-result/v1')
        self.assertFalse(handle_assembly_field_request('run_assembly_electrothermal',{'request':request(),'executable':'shell'})['ok'])

    def test_guided_examples(self):
        from examples.assembly_field.run_electrothermal import run_examples
        summaries = run_examples()
        self.assertEqual([row['case'] for row in summaries],
                         ['dc-conduction','temperature-feedback','switching-loss-table',
                          'stored-energy-corrected-loss','operating-loss-table'])
        self.assertTrue(all(not row['production_qualified'] for row in summaries))
        self.assertGreater(summaries[2]['total_deposited_heat_w'],summaries[1]['total_deposited_heat_w'])

    def test_nonfinite_material_law_is_rejected(self):
        raw = request()
        raw['electrical']['materials'][0].update(temperature_coefficient_per_k=1e308,
            reference_temperature_k=200,temperature_range_k=[200,1000])
        with self.assertRaisesRegex(ValueError,'ELECTROTHERMAL_MATERIAL'):
            run_assembly_electrothermal(raw)

    def test_schema_and_real_worker_process(self):
        from jsonschema import Draft202012Validator, ValidationError
        from referencing import Registry, Resource
        from python.spike_core.spider_v2 import AssemblyIRV1
        root = Path(__file__).resolve().parents[2]
        registry = Registry()
        names = ('assembly-ir-v1','design-ir-v2','assembly-placement-policy-v1','solver-mesh-v1',
                 'assembly-field-handoff-request-v1','assembly-field-thermal-problem-v1',
                 'electrical-heat-source-v1','assembly-electrothermal-request-v1')
        for name in names:
            raw = json.loads((root/'schemas'/f'{name}.schema.json').read_text())
            registry = registry.with_resource(raw['$id'],Resource.from_contents(raw))
        value = request()
        value['geometry']['assembly'] = json.loads(json.dumps(AssemblyIRV1.from_dict(value['geometry']['assembly']).to_dict()))
        schema = json.loads((root/'schemas'/'assembly-electrothermal-request-v1.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema,registry=registry)
        validator.validate(value)
        with self.assertRaises(ValidationError):
            validator.validate({**value,'executable':'shell'})
        completed = subprocess.run([sys.executable,'-W','error','-m','python.spike_core.service'],
            input=json.dumps({'id':'coupled','method':'run_assembly_electrothermal','params':{'request':value}})+'\n',
            text=True,capture_output=True,cwd=root,timeout=60,check=True)
        result = json.loads(completed.stdout)
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['result']['contract'],'spike/assembly-electrothermal-result/v1')
