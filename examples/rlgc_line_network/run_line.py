# SPDX-License-Identifier: Apache-2.0
"""Original supplied 5-m line with independent sampled conductor/leakage loss."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from python.spike_core.rlgc_line_network import build_rlgc_line_network


def request():
    return {'contract':'spike/rlgc-line-network-request/v1','length_m':5.,
            'reference_impedance_ohm':50.,'inductance_h_per_m':250e-9,
            'capacitance_f_per_m':100e-12,
            'samples':[{'frequency_hz':f,'resistance_ohm_per_m':r,'conductance_s_per_m':g}
                       for f,r,g in [(0.,2.,.0001),(1e6,2.1,.0002),(10e6,3.,.0003),(100e6,5.,.0005)]]}


if __name__=='__main__':
    print(json.dumps(build_rlgc_line_network(request()),indent=2,allow_nan=False))
