# SPDX-License-Identifier: Apache-2.0
"""Compare actual fixed-property and conductivity-feedback slab simulations."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from examples.pdn_dielectric_thermal.run_slab import setup
from python.spike_core.pdn_dielectric_feedback import run_pdn_dielectric_feedback
from python.spike_core.pdn_dielectric_thermal import run_pdn_dielectric_thermal


def feedback_setup():
    return {'contract':'spike/pdn-dielectric-feedback-request/v1','base_request':setup(),
        'conductivity_laws':[{'material_id':'bulk','reference_temperature_k':300.,
            'temperature_coefficient_per_k':.02,'temperature_range_k':[290.,350.]}],
        'iteration':{'initial_temperature_k':300.,'max_iterations':40,'relaxation':.7,
                     'temperature_tolerance_k':1e-6,'power_relative_tolerance':1e-8}}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plot',action='store_true')
    args=parser.parse_args(); request=feedback_setup()
    baseline=run_pdn_dielectric_thermal(request['base_request'])
    result=run_pdn_dielectric_feedback(request)
    coupled=result['last_coupled_result']
    output=ROOT/'build/pdn-dielectric-feedback-example';output.mkdir(parents=True,exist_ok=True)
    for name,data in (('request',request),('baseline',baseline),('result',result)):
        (output/(name+'.json')).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temperature=np.array(coupled['thermal_result']['node_temperatures_k'])
    print(json.dumps({'baseline_power_w':baseline['total_dielectric_power_w'],
        'feedback_power_w':coupled['total_dielectric_power_w'],'peak_temperature_k':float(temperature.max()),
        'iterations':len(result['history']),'coupling_mode':result['coupling_mode'],'result_path':str(output/'result.json')}))
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        x=np.array(request['base_request']['electrical_request']['mesh']['vertices'])[:,0]
        fig,(left,right)=plt.subplots(1,2,figsize=(11,4.6),layout='constrained')
        left.scatter(x,baseline['thermal_result']['node_temperatures_k'],s=28,c='gray',label='Fixed conductivity: computed')
        left.scatter(x,temperature,s=16,c='darkorange',label='Conductivity feedback: computed')
        left.set(xlabel='x (m)',ylabel='Temperature (K)',title='Actual steady thermal nodes')
        left.legend(fontsize=8)
        history=result['history']; controls=request['iteration']
        right.semilogy([h['iteration'] for h in history],
            [max(h['temperature_residual_k']/controls['temperature_tolerance_k'],1e-16) for h in history],
            'o-',label='Raw temperature residual / criterion')
        power=[h for h in history if h['power_relative_change'] is not None]
        right.semilogy([h['iteration'] for h in power],
            [max(h['power_relative_change']/controls['power_relative_tolerance'],1e-16) for h in power],
            's-',label='Relative power change / criterion')
        right.axhline(1,color='black',linestyle='--',label='Both must reach ≤ 1')
        right.set(xlabel='Iteration',ylabel='Residual divided by acceptance criterion',title='Verified fixed-point closure')
        right.legend(fontsize=8)
        fig.suptitle('Synthetic dielectric σ(T) ↔ steady temperature | experimental')
        fig.savefig(output/'feedback.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
