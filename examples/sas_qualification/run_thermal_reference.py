# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original eight-resistor shared-sink reference, NOT actual SAS fan cooling."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from python.spike_core.transient_resistive_electrothermal import run_transient_resistive_electrothermal
from python.spikes.qualification_artifacts import export_qualification_evidence


def setup():
    value = {'contract':'spike/transient-resistive-electrothermal-request/v1',
             'circuit':{'contract':'spike/native-mna-request/v1','request_id':'original-shared-sink',
                        'ground_node':'0','analysis':{'mode':'operating_point'},'elements':[]},
             'thermal':{'ambient_temperature_k':300.,'nodes':[],'links':[]},'loss_mappings':[],'loss_ledger':[],
             'time':{'stop_time_s':200.,'maximum_time_step_s':1.},
             'iteration':{'max_iterations':30,'relaxation':1.,'temperature_tolerance_k':1e-9,'power_tolerance_w':1e-9,
                          'balance_tolerance_w':1e-8,'electrical_relative_tolerance':1e-10,'time_limit_s':120.}}
    for i in range(8):
        node,resistor,source = f'device-{i}',f'R{i}',f'I{i}'
        value['circuit']['elements'] += [
            {'id':source,'type':'current_source','positive_node':'0','negative_node':f'p{i}','dc_value':1.},
            {'id':resistor,'type':'resistor','positive_node':f'p{i}','negative_node':'0','resistance_ohm':3.}]
        value['thermal']['nodes'].append({'id':node,'capacitance_j_per_k':1.,'initial_temperature_k':300.,
                                        'minimum_temperature_k':290.,'maximum_temperature_k':500.})
        value['thermal']['links'].append({'id':node,'from_id':node,'to_id':'synthetic-sink','resistance_k_per_w':2.})
        value['loss_mappings'].append({'element_id':resistor,'thermal_node_id':node,'reference_temperature_k':300.,
                                      'temperature_coefficient_per_k':.01})
        value['loss_ledger'] += [{'element_id':resistor,'disposition':'joule_heat','reason':'Original synthetic resistor.'},
                                {'element_id':source,'disposition':'external_ideal_source','reason':'Original ideal fixture supply.'}]
    value['thermal']['nodes'].append({'id':'synthetic-sink','capacitance_j_per_k':2.,'initial_temperature_k':300.,
                                      'minimum_temperature_k':290.,'maximum_temperature_k':500.})
    value['thermal']['links'].append({'id':'sink-air','from_id':'synthetic-sink','to_id':'ambient','resistance_k_per_w':.5})
    return value


def run(output):
    request = setup()
    result = run_transient_resistive_electrothermal(request)
    if result['status']!='completed': raise ValueError(str(result['issues']))
    expected = {'device-0':300+18/.82,'synthetic-sink':300+12/.82}
    errors = {node:abs(result['samples'][-1]['temperature_k'][node]-temperature) for node,temperature in expected.items()}
    if max(errors.values())>1e-6: raise ValueError('Original steady thermal oracle failed')
    traces = {f'T({node})':[sample['temperature_k'][node] for sample in result['samples']] for node in expected}
    report = {'id':'eight-synthetic-resistors','status':'PASS','hardware_qualified':False,'request':request,
              'coupled_result':result,'steady_oracle_k':expected,'steady_error_k':errors,
              'runs':[{'time_s':[s['time_s'] for s in result['samples']],'traces':traces}],
              'scope':'Thermal transient/quasi-static electrical synthetic reference; not SAS installed cooling.'}
    export_qualification_evidence(report,output)
    return {'status':report['status'],'hardware_qualified':False,'steady_error_k':errors,
            'final_temperature_k':result['samples'][-1]['temperature_k']}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().output),indent=2,allow_nan=False))
