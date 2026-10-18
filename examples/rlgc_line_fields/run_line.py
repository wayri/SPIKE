# SPDX-License-Identifier: Apache-2.0
"""Original coherent two-end excitation of a supplied uniform 5-m RLGC line."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from examples.rlgc_line_network.run_line import request as line_request
from python.spike_core.rlgc_line_fields import run_rlgc_line_fields


def request():
    line=line_request();line['samples']=line['samples'][1:]
    return {'contract':'spike/rlgc-line-fields-request/v1','line_request':line,
            'excitations':[{'frequency_hz':s['frequency_hz'],'incident_left':{'real':1.,'imag':.2},
                            'incident_right':{'real':.3,'imag':-.4}} for s in line['samples']],
            'probes':[{'id':name,'fractional_position':q} for name,q in [('left',0.),('midpoint',.5),('right',1.)]]}


if __name__=='__main__':print(json.dumps(run_rlgc_line_fields(request()),indent=2,allow_nan=False))
