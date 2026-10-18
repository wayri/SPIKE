# SPDX-License-Identifier: Apache-2.0
"""Original 10 ohm / 100 microhenry drive into a 1 microfarad fitted port."""
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))


def request():
    reference, capacitance = 50., 1e-6
    rate=1/(reference*capacitance)
    frequencies=[0.,100.,1000.,10000.,100000.]
    def pair(value):return {'real':value.real,'imag':value.imag}
    return {'contract':'spike/inductive-network-transient-request/v1',
            'fit_request':{'contract':'spike/sparameter-rational-fit-request/v1',
                           'source':{'id':'original-rlc-capacitor','port_names':['capacitor'],
                                     'reference_impedance_ohm':reference,'frequencies_hz':frequencies,
                                     's_parameters':[[[pair((rate-2j*math.pi*f)/(rate+2j*math.pi*f))]] for f in frequencies]},
                           'pole_rates_rad_s':[rate],'max_absolute_error':1e-12},
            'terminations':[{'port_name':'capacitor','resistance_ohm':10.,'inductance_h':100e-6,
                             'voltage_points':[{'time_s':0.,'voltage_v':1.},{'time_s':.001,'voltage_v':1.}]}],
            'output_times_s':[0.,2e-6,5e-6,1e-5,2e-5,5e-5,.0001,.0002,.0005,.001]}


if __name__=='__main__':
    from python.spike_core.sparameter_inductive_terminated import run_inductive_network_transient
    result=run_inductive_network_transient(request())
    print(json.dumps({'contract':result['contract'],'model_status':result['model_status'],
                      'production_qualified':result['production_qualified'],
                      'input_digest':result['input_digest'],'points':result['points'],
                      'diagnostics':result['diagnostics']}))
