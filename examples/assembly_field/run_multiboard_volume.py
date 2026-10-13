# SPDX-License-Identifier: Apache-2.0
"""Original two-slab reduced PI/SI coupling fixture; no measured-board claims."""
import copy
import json

from examples.assembly_field.run_examples import setup
from python.spike_core.multiboard_circuit import compile_multiboard_circuit
from python.spike_core.multiboard_volume_electrothermal import run_multiboard_volume_electrothermal


def request(domain='pi', *, mechanical_part=False, alpha=0.):
    geometry, thermal = setup()
    for boundary in thermal['boundaries']:
        boundary['temperature_k'] = 300
    if not mechanical_part:
        part = geometry['assembly']['parts'].pop()
        geometry['assembly']['boards'].append({'id': 'case', 'design_id': part['model_id'], 'frame': part['frame']})
        geometry['bodies'][1]['stack_binding'] = copy.deepcopy(geometry['bodies'][0]['stack_binding'])
    source = {'id': 'supply', 'type': 'voltage_source', 'positive_node': 'J:1', 'negative_node': 'J:2',
              'dc_value': 12 if domain == 'pi' else 0, 'ac_magnitude': 1}
    load = {'id': 'load', 'type': 'resistor', 'positive_node': 'J:1', 'negative_node': 'J:2', 'resistance_ohm': 6}
    circuit = {'contract': 'spike/multiboard-circuit-request/v1', 'domain': domain,
               'board_models': [{'board_id': 'board', 'elements': [source]}],
               'link_models': [], 'ground': {'board_id': 'board', 'node': 'J:2'},
               'analysis': {'mode': 'operating_point'} if domain == 'pi' else
                           {'mode': 'ac', 'start_hz': 1000, 'stop_hz': 1000, 'points': 1}}
    if mechanical_part:
        circuit['part_models'] = [{'part_id': 'case', 'elements': [load]}]
        geometry['assembly']['electrical_bonds'] = [
            {'id': name, 'endpoint_a': 'board', 'endpoint_b': 'case'} for name in ('feed', 'return')]
        circuit['electrical_bond_models'] = [
            {'bond_id': name, 'endpoint_a': {'board_id': 'board', 'node': f'J:{pin}'},
             'endpoint_b': {'part_id': 'case', 'node': f'J:{pin}'}, 'resistance_ohm': resistance, 'inductance_h': 0}
            for name, pin, resistance in [('feed', 1, .1), ('return', 2, .2)]]
    else:
        circuit['board_models'].append({'board_id': 'case', 'elements': [load]})
        geometry['assembly']['harnesses'] = [{'id': 'cable', 'endpoint_a': 'board::J', 'endpoint_b': 'case::J',
                                             'pin_map': {'1': '1', '2': '2'}}]
        circuit['link_models'] = [{'link_id': 'cable', 'kind': 'harness', 'pins': [
            {'source_pin': str(i), 'target_pin': str(i), 'resistance_ohm': r, 'inductance_h': 0}
            for i, r in [(1, .1), (2, .2)]]}]
    circuit['assembly'] = copy.deepcopy(geometry['assembly'])
    compiled = compile_multiboard_circuit(circuit)
    # Uniform distribution over equal-volume tetrahedra provides a conservative
    # heat-transfer fixture. This coarse mesh is not an exact quadratic T field.
    distribution = [{'occurrence_id': body['occurrence_id'], 'cell_id': cell['id'], 'weight': 1/12}
                    for body in geometry['bodies'] for cell in body['mesh']['cells']]
    bindings = [{'element_id': e['id'], 'distribution': copy.deepcopy(distribution),
                 'temperature_law': {'temperature_coefficient_per_k': alpha, 'reference_temperature_k': 300,
                                     'temperature_range_k': [250, 1000]}}
                for e in compiled['native_request']['elements'] if e['type'] == 'resistor']
    result = {'contract': 'spike/multiboard-volume-electrothermal-request/v1', 'geometry': geometry,
              'thermal_problem': thermal, 'circuit': circuit, 'loss_bindings': bindings,
              'loss_accounting': 'exhaustive_resistor_losses', 'thermal_engine': 'internal',
              'iteration': {'initial_temperature_k': 300, 'max_iterations': 50, 'relaxation': .8,
                            'temperature_tolerance_k': 1e-6, 'power_relative_tolerance': 1e-9}}
    if domain == 'si':
        result['ac_heating'] = {'frequency_hz': 1000, 'phasor_convention': 'rms'}
    return result


def run_examples():
    return [run_multiboard_volume_electrothermal(request(domain, mechanical_part=part, alpha=.004))
            for domain, part in [('pi', False), ('si', False), ('pi', True)]]


if __name__ == '__main__':
    print(json.dumps([{'domain': r['domain'], 'loss_balance': r['loss_balance'],
                      'temperatures': r['thermal']['occurrence_temperatures']} for r in run_examples()], indent=2))
