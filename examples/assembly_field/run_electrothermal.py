# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original coupled two-solid and supplied semiconductor loss examples."""
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from examples.assembly_field.run_examples import setup
from python.spike_core.assembly_electrothermal import run_assembly_electrothermal
from python.spike_core.multiboard_identity import canonical_json_digest


def setup_coupled():
    geometry,thermal = setup()
    geometry['assembly']['electrical_bonds'] = [{'id':'bond','endpoint_a':'board','endpoint_b':'case',
        'electrical_resistance_ohm':.25,'contact_area_mm2':1e6}]
    terminals = []
    for body,x,potential in [(geometry['bodies'][0],0,0),(geometry['bodies'][1],1,2)]:
        for face in body['boundary_faces']:
            if all(body['mesh']['vertices'][v][0] == x for v in face['vertices']):
                terminals.append({'id':body['occurrence_id']+'-'+face['id'],
                    'face':{'occurrence_id':body['occurrence_id'],'face_id':face['id']},'voltage_v':potential})
    return {'contract':'spike/assembly-electrothermal-request/v1','geometry':geometry,'thermal_problem':thermal,
        'electrical':{'materials':[{'id':'k','conductivity_s_m':2,'temperature_coefficient_per_k':0,
            'reference_temperature_k':300,'temperature_range_k':[200,1000]}], 'terminals':terminals,
            'contacts':[{'bond_id':'bond','face_pairs':thermal['contacts'][0]['face_pairs'],
                         'electrical_contact_conductance_s_m2':4}]},
        'heat_sources':[],'loss_accounting':'explicit_nonoverlapping_losses',
        'iteration':{'initial_temperature_k':300,'max_iterations':50,'relaxation':.8,
                     'temperature_tolerance_k':1e-6,'power_relative_tolerance':1e-9}}


def run_examples():
    base = setup_coupled()
    feedback = copy.deepcopy(base)
    feedback['electrical']['materials'][0]['temperature_coefficient_per_k'] = .004
    semiconductor = copy.deepcopy(feedback)
    model = {'kind':'semiconductor_loss_table','temperature_k':[200,1000],
        'conduction_power_w':[1,2],'turn_on_energy_j':[.0001,.0002],
        'turn_off_energy_j':[.0001,.0002],'reverse_recovery_energy_j':[0,0],
        'switching_frequency_hz':1000,'energy_terms_nonoverlapping':True,
        'conditions':'Original synthetic device, fixed drive; no vendor accuracy claim'}
    semiconductor['heat_sources'] = [{'contract':'spike/electrical-heat-source/v1','id':'device','model':model,
        'distribution':[{'occurrence_id':'board','cell_id':'0','weight':1}],
        'provenance':{'source_sha256':canonical_json_digest(model),'description':'Original analytic fixture, not measured data'}}]
    energy_balanced = copy.deepcopy(base)
    energy_model = {'kind':'energy_balanced_terminal_waveform','time_s':[0,1],
        'ports':[{'id':'input','voltage_v':[1,3],'current_a':[2,5]}],
        'stored_energy_j':[2,3],'energy_policy':'passive_ports_minus_stored_energy'}
    energy_balanced['heat_sources'] = copy.deepcopy(semiconductor['heat_sources'])
    energy_balanced['heat_sources'][0].update(model=energy_model,
        provenance={'source_sha256':canonical_json_digest(energy_model),'description':'Original first-law analytical fixture'})
    operating = copy.deepcopy(base)
    operating_model = {'kind':'semiconductor_operating_loss_table',
        'temperature_k':[200,1000],'voltage_v':[0,200],'current_a':[0,10],
        'operating_voltage_v':100,'operating_current_a':2,'switching_frequency_hz':1000,
        'conditions':'Synthetic fixed drive/duty; no real semiconductor accuracy claim',
        'energy_terms_nonoverlapping':True}
    for column,value in [('conduction_power_w',1),('turn_on_energy_j',.0005),
                         ('turn_off_energy_j',.0005),('reverse_recovery_energy_j',0)]:
        operating_model[column] = [[[value]*2 for _ in range(2)] for _ in range(2)]
    operating['heat_sources'] = copy.deepcopy(semiconductor['heat_sources'])
    operating['heat_sources'][0].update(model=operating_model,
        provenance={'source_sha256':canonical_json_digest(operating_model),'description':'Original rectangular loss fixture'})
    summaries = []
    for name,request in [('dc-conduction',base),('temperature-feedback',feedback),('switching-loss-table',semiconductor),
                         ('stored-energy-corrected-loss',energy_balanced),('operating-loss-table',operating)]:
        result = run_assembly_electrothermal(request)
        if name == 'dc-conduction':
            assert abs(result['electrical']['source_power_w']-3.2) < 1e-8
            assert abs(result['electrical']['contact_power_w']-.64) < 1e-8
        if name in ('stored-energy-corrected-loss','operating-loss-table'):
            expected = 9.7 if name == 'stored-energy-corrected-loss' else 5.2
            assert abs(sum(result['cell_deposited_power_w'].values())-expected) < 1e-8
        assert abs(result['conservation']['thermal_imbalance_w']) < 1e-8
        summaries.append({'case':name,'request_digest':result['request_digest'],'result_digest':result['result_digest'],
            'electrical_input_w':result['electrical']['source_power_w'],
            'contact_heat_w':result['electrical']['contact_power_w'],
            'total_deposited_heat_w':sum(result['cell_deposited_power_w'].values()),
            'temperature_ranges':result['thermal']['occurrence_temperatures'],
            'iterations':len(result['history']),'conservation':result['conservation'],
            'production_qualified':result['production_qualified']})
    return summaries


if __name__ == '__main__':
    print(json.dumps(run_examples(),indent=2,allow_nan=False))
