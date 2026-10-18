# SPDX-License-Identifier: Apache-2.0
"""Execute real SI/PI CLI workflows and retain bounded readiness evidence.

Original synthetic inputs exercise usability, analytical RC/RLC checks and
explicit model limits. This is not a board extraction or signoff certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition,message):
    if not condition:raise ValueError(message)


def check_rc(result):
    require(result['model_status']=='approximate','PI model status changed')
    for sample in result['ac']:
        frequency=sample['frequency_hz'];pair=sample['impedance_ohm'][0][0]
        expected=1/(20+2j*math.pi*frequency*1e-4)
        require(abs(complex(pair['real'],pair['imag'])-expected)<=1e-12,'RC impedance reference failed')
    for point in result['load_transient']['points']:
        t=point['time_s'];rise=1e-6;tau=5e-6
        expected=.05*(t/rise+tau/rise*math.expm1(-t/tau)) if t<=rise else .05*(1+tau/rise*math.expm1(-rise/tau)*math.exp(-(t-rise)/tau))
        require(abs(-point['port_voltage_v']['load']-expected)<=2e-7,'RC finite-rise droop reference failed')
    return {'max_requested_droop_v':max(-p['port_voltage_v']['load'] for p in result['load_transient']['points'])}


def check_rlc(result):
    for sample in result['ac']:
        w=2*math.pi*sample['frequency_hz'];source=.02+1j*w*1e-8
        bulk=.005+1j*(w*1e-9-1/(w*1e-4));small=.02+1j*(w*5e-10-1/(w*1e-7))
        expected=1/(1/source+1/bulk+1/small);actual=sample['impedance_ohm'][0][0]
        require(abs(complex(actual['real'],actual['imag'])-expected)<=1e-12,'RLC parallel-branch reference failed')
    require(result['load_transient']['energy_balance_relative_error']<1e-8,'RLC transient energy balance failed')
    return {'max_requested_droop_v':max(-p['port_voltage_v']['load'] for p in result['load_transient']['points']),
            'energy_balance_relative_error':result['load_transient']['energy_balance_relative_error']}


def check_si(result):
    require(result['status']=='completed','SI workflow did not complete')
    require(result['time_domain']['status']=='completed' and result['tdr']['status']=='completed','SI waveform/eye/TDR stage incomplete')
    require(result.get('production_qualified') is not True,'Unexpected SI qualification promotion')
    receivers=result['time_domain']['receivers'];require(bool(receivers),'SI returned no receiver data')
    for receiver in receivers:
        require(math.isfinite(receiver['eye_height_v']) and receiver['eye_height_v']>0,'Reference channel eye did not open')
        require(bool(receiver['traces']) and bool(receiver['waveform']),'SI returned no eye/waveform samples')
        require(all(math.isfinite(p['time_s']) and math.isfinite(p['voltage_v']) for p in receiver['waveform']),'SI waveform contains nonfinite data')
    require(bool(result['tdr']['tdr']) and all(math.isfinite(p['reflection']) for p in result['tdr']['tdr']),'SI returned no finite TDR trace')
    return {'status':result['status'],'time_domain_status':result['time_domain']['status'],'tdr_status':result['tdr']['status'],
            'reference_eye_heights_v':[r['eye_height_v'] for r in receivers]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python',default=sys.executable,help='Interpreter for supplied-model SI/PI; requires repository dependencies')
    parser.add_argument('--native-python',help='Optional interpreter with the compatible built native module, for routed-copper DC/AC/transient checks')
    parser.add_argument('--output-dir',required=True,type=Path,help='Fresh output folder; existing evidence is never overwritten')
    args=parser.parse_args();folder=args.output_dir.resolve()
    if folder.exists():parser.error('Select a new output folder to preserve previous evidence')
    folder.mkdir(parents=True)
    rows=[]
    def run(name,interpreter,arguments,check,source=None):
        output=folder/f'{name}.json';command=[interpreter,'-m','python.spike_core.cli','--quiet','--output',str(output),*map(str,arguments)]
        row={'name':name,'command':command,'status':'failed'}
        if source:
            row['source_sha256']=digest(ROOT/source)
            retained=folder/f'{name}-input.json';retained.write_bytes((ROOT/source).read_bytes())
            row['source_input']=str(retained)
        try:
            completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=180)
            (folder/f'{name}.log').write_text(completed.stdout+completed.stderr,encoding='utf-8')
            row['exit_code']=completed.returncode;require(completed.returncode==0,f'{name}: CLI failed; see retained log')
            result=json.loads(output.read_text(encoding='utf-8'));row['metrics']=check(result)
            row.update(status='passed',output_sha256=digest(output),model_status=result.get('model_status'),output=str(output))
        except (ValueError,KeyError,TypeError,OSError,subprocess.TimeoutExpired) as error:row['error']=str(error)
        rows.append(row);print(json.dumps({'name':name,'status':row['status'],'error':row.get('error')}),flush=True)
        return output
    run('pi-rc',args.python,['pdn-network',ROOT/'examples/tutorial_pi_si/rc-pdn.request.json'],check_rc,'examples/tutorial_pi_si/rc-pdn.request.json')
    rlc=run('pi-rlc',args.python,['pdn-network',ROOT/'examples/tutorial_pi_si/rlc-pdn.request.json'],check_rlc,'examples/tutorial_pi_si/rlc-pdn.request.json')
    # Refine the actual saved RLC setup and compare shared observations.
    refined=json.loads((ROOT/'examples/tutorial_pi_si/rlc-pdn.request.json').read_text());refined['load_transient']['max_step_s']/=2
    refined_path=folder/'rlc-refined.request.json';refined_path.write_text(json.dumps(refined,indent=2)+'\n',encoding='utf-8')
    def check_refined(result):
        check_rlc(result);coarse=json.loads(rlc.read_text());a=coarse['load_transient']['points'];b=result['load_transient']['points']
        require([p['time_s'] for p in a]==[p['time_s'] for p in b],'Refined observation times changed')
        errors=[abs(x['port_voltage_v']['load']-y['port_voltage_v']['load']) for x,y in zip(a,b)]
        require(all(e<=1e-6+2e-3*abs(y['port_voltage_v']['load']) for e,y in zip(errors,b)),'RLC load transient did not converge at requested observations')
        return {'max_shared_observation_difference_v':max(errors)}
    run('pi-rlc-refined',args.python,['pdn-network',refined_path],check_refined)
    channel=folder/'si-channel.s4p'
    run('si-coupled',args.python,['si-workflow',ROOT/'examples/si/analytical-coupled-rlgc.json','--touchstone-output',channel],check_si,'examples/si/analytical-coupled-rlgc.json')
    run('si-10g-reference',args.python,['si-workflow',ROOT/'examples/si/10g-nrz-cdr.json'],check_si,'examples/si/10g-nrz-cdr.json')
    def check_touchstone(result):
        require(result['status']=='completed' and result['port_count']==4,'Touchstone reinspection failed')
        return {'port_count':result['port_count']}
    run('si-touchstone',args.python,['sparam-inspect',channel],check_touchstone)
    if args.native_python:
        board=ROOT/'examples/tutorial_pi_si/straight_trace.design.json';common=['--net','VCC','--mesh-size-mm','2']
        def check_dc(result):
            require(result['status']=='completed' and result['model_status']=='approximate','DC did not complete as approximate')
            expected=.01/(5.8e7*.001*.000035);actual=result['summary']['max_load_voltage_drop_v']
            require(abs(actual-expected)<1e-10,'DC uniform copper reference failed')
            return {'load_drop_v':actual}
        run('copper-dc',args.native_python,['analyze-dc',board,*common,'--source','0,0,F.Cu,5','--load','10,0,F.Cu,1'],check_dc,'examples/tutorial_pi_si/straight_trace.design.json')
        def check_ac(result):
            require(result['status']=='completed' and result['model_status']=='approximate','AC did not complete as approximate')
            return {'status':result['status'],'scope':'R/L driving point only; distributed capacitance disabled; not a qualified SI channel'}
        run('copper-ac',args.native_python,['analyze-ac',board,*common,'--source','0,0,F.Cu,source','--load','10,0,F.Cu,load','--start-hz','1000000','--stop-hz','1000000000','--points','5','--capacitance-model','none'],check_ac,'examples/tutorial_pi_si/straight_trace.design.json')
        def check_transient(result):
            require(result['status']=='completed' and result['model_status']=='approximate','Transient did not complete as approximate')
            s=result['summary'];require(s['time_step_s']<=s['recommended_time_step_s']*(1+1e-12),'Copper transient exceeds recommended step')
            return {'max_voltage_drop_v':s['max_voltage_drop_v'],'time_step_s':s['time_step_s']}
        run('copper-transient',args.native_python,['analyze-transient',board,*common,'--source','0,0,F.Cu,5','--load','10,0,F.Cu,1','--source-waveform','constant','--load-waveform','step,0,2e-6,1e-6','--stop-time-s','8e-6','--time-step-s','8e-9','--output-decimation','25','--output-decimation-mode','manual','--capacitance-model','none'],check_transient,'examples/tutorial_pi_si/straight_trace.design.json')
    passed=all(row['status']=='passed' for row in rows)
    report={'contract':'spike/pisi-workflow-readiness/v1','status':'passed' if passed else 'failed','production_qualified':False,'board_specific_verified':False,'native_copper_requested':bool(args.native_python),'cases':rows,'source_sha256':{p:digest(ROOT/p) for p in ('scripts/check_pisi_readiness.py','python/spike_core/cli.py','python/spike_core/pdn_network.py','python/spike_core/si_workflow.py')},'limitations':['Synthetic supplied-model execution and software readiness only; no user-board extraction or measured correlation.','RLC refinement covers requested observations, not guaranteed intersample peaks.','Geometry SI/PI has separate topology, return, stackup, port, mesh/convergence and model-validity gates.','Native desktop visual/installed-package acceptance and whole-tool parity are separate.']}
    (folder/'readiness.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return 0 if passed else 2


if __name__=='__main__':raise SystemExit(main())
