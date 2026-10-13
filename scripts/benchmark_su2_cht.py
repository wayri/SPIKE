# SPDX-License-Identifier: Apache-2.0
"""Execute original conduction-oracle and moving-cavity SU2 CHT refinements."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.su2_cht import compile_su2_cht, parse_su2_cht, run_su2_cht
from python.spike_core.su2_airflow import _sha256, find_su2


def _resume(path, cells, speed, executable):
    result = json.loads(path.read_text(encoding='utf-8'))
    request = result['request']
    if request['cells']!=cells or request['lid_speed']!=speed or request['outer_iterations']!=5000:
        raise ValueError('Saved benchmark settings do not match the requested case.')
    provenance = result['provenance']
    directory = Path(provenance['run_directory'])
    program = find_su2(executable)
    if program is None or _sha256(program)!=provenance['executable_sha256']:
        raise ValueError('Saved benchmark runtime identity changed.')
    for name, content in compile_su2_cht(request).items():
        if (directory/name).read_text(encoding='ascii')!=content or _sha256(directory/name)!=provenance['input_sha256'][name]:
            raise ValueError('Saved benchmark input changed.')
    for name, digest in provenance['output_sha256'].items():
        if _sha256(directory/name)!=digest:
            raise ValueError('Saved benchmark output changed.')
    result.update(parse_su2_cht(directory,request))
    result['status'] = ('completed' if result['validation']['passed'] else 'failed_validation') if result['convergence']['converged'] else 'failed_to_converge'
    return result


def conduction_oracle(result):
    q = 10/(2*.25/.1+1/.01)
    errors = []
    for zone in ('solid','fluid','cold_solid'):
        fields = result['zones'][zone]
        for y,t in zip(fields['y_m'],fields['temperature_k']):
            expected = (310-q*(y+.25)/.1 if zone == 'solid' else
                        300+q*(1.25-y)/.1 if zone == 'cold_solid' else
                        300+q*(.25/.1+(1-y)/.01))
            errors.append(abs(t-expected))
    return {'heat_rate_w_per_m':q, 'temperature_max_error_k':max(errors),
            'heat_input_relative_error':abs(result['diagnostics']['heat_input_w_per_m']-q)/q}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cells',nargs='+',type=int,default=[16,32,64])
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/su2-cht-three-zone-benchmark')
    parser.add_argument('--su2-executable')
    parser.add_argument('--timeout-s',type=int,default=900)
    parser.add_argument('--resume',action='store_true',help='Revalidate saved outputs and reuse only matching input/runtime hashes.')
    args = parser.parse_args()
    if len(args.cells)<2 or args.cells!=sorted(set(args.cells)) or any(n<8 or n>64 or n%4 for n in args.cells):
        parser.error('cells must be at least two increasing multiples of four in [8,64]')
    args.output.mkdir(parents=True,exist_ok=True)
    report = {'contract':'spike/su2-cht-benchmark/v1','case':'cavity_between_thermal_slabs','passed':False,
              'model_status':'experimental','runs':[],
              'criteria':{'conduction_temperature_error_k':.001,'conduction_heat_relative_error':.001,
                'interface_temperature_jump_k':.001,'interface_flux_relative_error':.001,
                'global_energy_relative_error':.02,'finest_convective_heat_refinement_relative_change':.1},
              'limitations':['Fixed 2D laminar cavity between two slabs; not arbitrary assembly CHT.',
                             'Fourier flux diagnostics use one-sided differences and exported temperatures.']}
    report['criteria'].update(cold_boundary_max_error_k=1e-4,passive_temperature_range_k=[299.999,310.001])
    report['criteria']['minimum_convective_heat_enhancement'] = 1.2
    for speed in (0.0,1.0):
        previous = None
        for n in args.cells:
            name = f"{'conduction' if speed==0 else 'convection'}-{n}.json"
            result = (_resume(args.output/name,n,speed,args.su2_executable) if args.resume and (args.output/name).is_file()
                      else run_su2_cht({'cells':n,'lid_speed':speed,'timeout_s':args.timeout_s},
                                      executable=args.su2_executable,output_root=args.output/'runs'))
            (args.output/name).write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
            row = {'cells':n,'lid_speed':speed,'result_file':name,'status':result['status'],
                   'diagnostics':result['diagnostics'],'convergence':result['convergence'],
                   'provenance':result['provenance'],'validation':result['validation']}
            if speed == 0:
                row['oracle'] = conduction_oracle(result)
            else:
                baseline = next(item for item in report['runs'] if item['cells']==n and item['lid_speed']==0)
                row['convective_heat_enhancement'] = (result['diagnostics']['heat_input_w_per_m'] /
                                                      baseline['diagnostics']['heat_input_w_per_m'])
            if previous is not None:
                rate = result['diagnostics']['heat_input_w_per_m']
                row['heat_refinement_relative_change'] = abs(rate-previous)/abs(rate)
            previous = result['diagnostics']['heat_input_w_per_m']
            report['runs'].append(row)
            print(json.dumps({key:value for key,value in row.items() if key!='provenance'}),flush=True)
            (args.output/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    report['passed'] = all(row['status']=='completed' and
        row['diagnostics']['interface_temperature_jump_k'] < .001 and
        row['diagnostics']['interface_flux_relative_error'] < .001 and
        row['diagnostics']['cold_interface_temperature_jump_k'] < .001 and
        row['diagnostics']['cold_interface_flux_relative_error'] < .001 and
        row['diagnostics']['global_energy_relative_error'] < .02 and
        (row['lid_speed']!=0 or (row['oracle']['temperature_max_error_k']<.001 and
                                row['oracle']['heat_input_relative_error']<.001)) for row in report['runs'])
    report['passed'] = report['passed'] and report['runs'][-1]['heat_refinement_relative_change'] < .1
    report['passed'] = report['passed'] and all(row['convective_heat_enhancement']>1.2 and
        row['diagnostics']['maximum_fluid_speed_m_s']>.5 for row in report['runs'] if row['lid_speed']>0)
    (args.output/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
