# SPDX-License-Identifier: Apache-2.0
"""Original finite Thevenin drive into a resistive port with shunt capacitance."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def request():
    reference,load=50.,75.
    frequencies=[0.,100.,1000.,10000.,100000.]
    return {'contract':'spike/capacitive-network-transient-request/v1',
            'fit_request':{'contract':'spike/sparameter-rational-fit-request/v1',
                           'source':{'id':'original-resistive-receiver','port_names':['receiver'],
                                     'reference_impedance_ohm':reference,'frequencies_hz':frequencies,
                                     's_parameters':[[[{'real':(load-reference)/(load+reference),'imag':0.}]] for _ in frequencies]},
                           'pole_rates_rad_s':[1000.],'max_absolute_error':1e-12},
            'terminations':[{'port_name':'receiver','resistance_ohm':25.,'capacitance_f':1e-5,
                             'voltage_points':[{'time_s':0.,'voltage_v':2.},{'time_s':.002,'voltage_v':2.}]}],
            'output_times_s':[0.,1e-5,5e-5,.0001,.0002,.0005,.001,.002]}


if __name__=='__main__':
    from python.spike_core.sparameter_capacitive_terminated import run_capacitive_network_transient
    result=run_capacitive_network_transient(request())
    print(json.dumps({'contract':result['contract'],'model_status':result['model_status'],
                      'production_qualified':result['production_qualified'],'input_digest':result['input_digest'],
                      'points':result['points'],'diagnostics':result['diagnostics']}))
