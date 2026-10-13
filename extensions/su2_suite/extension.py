# SPDX-License-Identifier: Apache-2.0
"""SU2 CFD/CHT process extension; fixed physical cases, no user executable paths."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from extension_sdk.python.spike_extension_sdk import read_request, write_result
from python.spike_core.su2_airflow import (
    su2_airflow_capabilities, validate_su2_request, cavity_config,
    cavity_mesh, run_su2_airflow,
)
from python.spike_core.extensions import user_extension_root


def execute(request):
    contribution = request['contribution_id']
    context = request.get('context', {})
    parameters = context.get('parameters', {})
    if not isinstance(parameters, dict):
        raise ValueError('SU2 parameters must be an object.')
    if contribution == 'su2-probe':
        if parameters:
            raise ValueError('SU2 runtime check accepts no parameters.')
        from python.spike_core.su2_cht import su2_cht_capabilities
        data = {'cfd': su2_airflow_capabilities(), 'cht': su2_cht_capabilities()}
    elif contribution in ('su2-cfd', 'su2-cfd-preview'):
        admitted = validate_su2_request(parameters)
        if contribution.endswith('-preview'):
            import hashlib
            data = {'solved': False, 'case': admitted,
                    'geometry': '1 m square cavity; moving top; stationary impermeable sides',
                    'units': {'length': 'm', 'velocity': 'm/s', 'pressure': 'Pa'},
                    'config': cavity_config(admitted),
                    'mesh_sha256': hashlib.sha256(cavity_mesh(admitted['cells']).encode('ascii')).hexdigest(),
                    'runtime': su2_airflow_capabilities()}
        else:
            data = {'result': run_su2_airflow(admitted, output_root=user_extension_root().parent / 'solver-runs' / 'su2')}
    elif contribution in ('su2-cht', 'su2-cht-preview'):
        from python.spike_core.su2_cht import run_su2_cht, prepare_su2_cht, su2_cht_capabilities
        data = prepare_su2_cht(parameters) if contribution.endswith('-preview') else {'result': run_su2_cht(parameters, output_root=user_extension_root().parent / 'solver-runs' / 'su2')}
        if contribution.endswith('-preview'):
            data['runtime'] = su2_cht_capabilities()
    else:
        raise ValueError('Unknown SU2 contribution.')
    data.update(board_geometry_used=False, production_qualified=False,
                limitation='Bounded reference geometry; imported PCB/STEP assembly CFD is not supported by this adapter.')
    status = 'completed'
    if 'result' in data and data['result'].get('status') not in ('completed', 'converged'):
        status = 'failed'
    return {'contract': 'spike/extension-result/v1', 'status': status,
            'title': 'SU2 ' + ('CHT' if 'cht' in contribution else 'CFD'), 'data': data}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    write_result(args.result, execute(read_request(args.request)))
