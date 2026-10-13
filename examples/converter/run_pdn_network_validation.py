# SPDX-License-Identifier: Apache-2.0
"""Original PDN/filter/sharing cases, actual solves and hash-bound evidence."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.pdn_network import evaluate_pdn_network
from python.spike_core.service_pdn_network import handle_pdn_network_request
from python.spike_core.pdn_series_capacitors import review_series_capacitor_leg
from tests.python.test_pdn_network import basic, element
from tests.python.test_pdn_electrostatic import plate, EPSILON_0


def cases():
    transient = {'port_id': 'load', 'points': [{'time_s': 0., 'current_a': 0.},
        {'time_s': 2e-6, 'current_a': .1}, {'time_s': .0005, 'current_a': .1},
        {'time_s': .000502, 'current_a': 0.}, {'time_s': .001, 'current_a': 0.}],
        'output_times_s': [float(t) for t in np.linspace(0, .001, 101)], 'max_step_s': 2e-6}
    frequency = [float(f) for f in np.geomspace(100, 1e6, 17)]
    rc = basic([element('source', 'source_output_impedance', positive='V', negative='GND', resistance_ohm=.1, inductance_h=0.),
                element('Cnet', 'net_ground_capacitance', node='V', capacitance_f=1e-3)], frequencies=frequency, transient=transient)
    dm = basic([element('source', 'source_output_impedance', positive='input', negative='GND', resistance_ohm=.1, inductance_h=10e-9),
                element('choke', 'dm_choke', positive='input', negative='V', resistance_ohm=.05, inductance_h=1e-6),
                element('decap', 'decap', positive='V', negative='GND', capacitance_f=10e-6, esr_ohm=.03, esl_h=5e-9),
                element('Cplane', 'net_ground_capacitance', node='V', capacitance_f=1e-9)], nodes=['input', 'V'], frequencies=frequency, transient=transient)
    series = basic([element('source', 'source_output_impedance', positive='V', negative='GND', resistance_ohm=.1, inductance_h=0.),
                    element('C1', 'decap', positive='V', negative='mid', capacitance_f=10e-6, esr_ohm=.03, esl_h=5e-9),
                    element('C2', 'decap', positive='mid', negative='GND', capacitance_f=10e-6, esr_ohm=.03, esl_h=5e-9),
                    element('balance1', 'resistor', positive='V', negative='mid', resistance_ohm=1e4),
                    element('balance2', 'resistor', positive='mid', negative='GND', resistance_ohm=1e4)], nodes=['V', 'mid'], frequencies=frequency, transient=transient)
    cm = basic([element('S1', 'resistor', positive='pin', negative='GND', resistance_ohm=1.),
                element('S2', 'resistor', positive='nin', negative='GND', resistance_ohm=1.),
                element('CMC', 'cm_choke', winding_a={'positive': 'pin', 'negative': 'pout', 'inductance_h': 1e-3, 'resistance_ohm': .1},
                    winding_b={'positive': 'nin', 'negative': 'nout', 'inductance_h': 1e-3, 'resistance_ohm': .1}, coupling_coefficient=.98, polarity='a_positive_to_b_positive'),
                element('X', 'capacitor', positive='pout', negative='nout', capacitance_f=1e-6),
                element('Y1', 'capacitor', positive='pout', negative='GND', capacitance_f=1e-8),
                element('Y2', 'capacitor', positive='nout', negative='GND', capacitance_f=1e-8)],
        nodes=['pin', 'nin', 'pout', 'nout'], ports=[{'id': 'load', 'mode': 'differential', 'positive': 'pout', 'negative': 'nout'},
            {'id': 'cm-in', 'mode': 'common', 'positive_nodes': ['pin', 'nin'], 'negative_nodes': ['GND', 'GND']},
            {'id': 'cm-out', 'mode': 'common', 'positive_nodes': ['pout', 'nout'], 'negative_nodes': ['GND', 'GND']}], frequencies=frequency, transient=transient)
    return {'rc': rc, 'dm_filter': dm, 'series_capacitors': series, 'cm_dm_filter': cm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    artifacts, summaries = {}, {}
    def retain(name, value):
        data = (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()
        (args.output_dir/name).write_bytes(data)
        artifacts[name] = hashlib.sha256(data).hexdigest()
    for name, request in cases().items():
        result = evaluate_pdn_network(request)
        assert result['diagnostics']['max_ac_relative_residual'] <= 1e-10
        assert result['load_transient']['max_relative_residual'] <= 1e-10
        assert result['load_transient']['energy_balance_error_j'] <= 1e-9
        retain(f'{name}-request.json', request)
        retain(f'{name}-result.json', result)
        summaries[name] = {'max_ac_relative_residual': result['diagnostics']['max_ac_relative_residual'],
            'energy_balance_error_j': result['load_transient']['energy_balance_error_j'],
            'net_nodes': list(result['load_transient']['points'][0]['node_voltage_v'])}
    field_request = plate(3)
    field = handle_pdn_network_request('extract_pdn_electrostatic', {'request': field_request})
    assert field['ok'], field
    assert abs(field['result']['matrix_f'][0][0]/(4*EPSILON_0)-1) <= 1e-12
    retain('electrostatic-request.json', field_request)
    retain('electrostatic-result.json', field['result'])
    leg = {'contract': 'spike/series-capacitor-leg/v1', 'voltage_v': 12., 'capacitors': [
        {'id': name, 'capacitance_f': 10e-6, 'tolerance_fraction': .2, 'rated_voltage_v': 6.3,
         'leakage_resistance_ohm': None, 'balancing_resistance_ohm': None} for name in ('C1', 'C2')]}
    review = review_series_capacitor_leg(leg)
    assert all(row['capacitive_rating_exceeded'] for row in review['capacitors'])
    assert not review['automatic_voltage_uprating_permitted']
    retain('series-rating-request.json', leg)
    retain('series-rating-result.json', review)
    sources = ['python/spike_core/pdn_network.py', 'python/spike_core/pdn_electrostatic.py',
               'python/spike_core/pdn_shunt_capacitance.py', 'python/spike_core/pdn_series_capacitors.py',
               'python/spike_core/service_pdn_network.py', 'examples/converter/run_pdn_network_validation.py']
    report = {'status': 'bounded_reference_cases_passed', 'production_qualified': False,
              'python': platform.python_version(), 'platform': platform.platform(), 'cases': summaries,
              'artifacts': dict(artifacts), 'source_sha256': {s: hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},
              'limits': ['Original mathematical models, not measured components or a qualified PCB.',
                         'Constant linear passive models; no saturation, ferrite dispersion or regulator control.',
                         'Finite insulating dielectric plate is not an arbitrary-PCB/fringing mesh study.',
                         'Capacitor labels do not establish safe DC sharing or automatic voltage uprating.']}
    retain('evidence.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
