# SPDX-License-Identifier: Apache-2.0
"""SDK process entry point for reviewed native Palace jobs."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from extension_sdk.python.spike_extension_sdk import write_result
from extensions.palace_suite import runtime

def execute(request,cancellation_event=None):
    if not isinstance(request,dict) or request.get('contract')!='spike/extension/v1':
        raise ValueError('PALACE_EXTENSION: invalid SDK contract')
    context = request.get('context')
    if not isinstance(context,dict) or not isinstance(context.get('parameters',{}),dict):
        raise ValueError('PALACE_EXTENSION: invalid context/parameters')
    params = context.get('parameters',{})
    if set(params)-{'config','mesh_path','expected_mesh_sha256','runtime_path','timeout_s','memory_limit_mb','threads','job_id'}:
        raise ValueError('PALACE_EXTENSION: unknown parameters; arbitrary commands prohibited')
    operation = str(request.get('contribution_id','')).removeprefix('palace-')
    binding = context.get('design_binding')
    if operation=='discover':
        info=runtime.runtime_info(params)
        data={'status':'available' if info['available'] else 'runtime_unavailable','runtime':info,
              'problem_types':list(runtime.PROBLEM_TYPES),'solved':False}
    else:
        if not isinstance(binding,dict) or not binding.get('design_id') or not binding.get('digest_sha256'):
            raise ValueError('PALACE_BINDING: host design binding required')
        if operation=='validate':
            data=runtime.supervised_run(params,binding,validate_only=True) if runtime.runtime_info(params)['available'] else {**runtime.validate(params),'runtime':runtime.runtime_info(params),'solved':False}
        elif operation=='prepare':
            case=runtime.prepare(params,binding)
            data={'case':case,'status':case['status'],'solved':False}
        elif operation=='run':
            data=runtime.run(params,binding,cancellation_event) if cancellation_event is not None else runtime.supervised_run(params,binding)
        elif operation=='import':
            data=runtime.import_outputs(params.get('job_id'),binding)
        else:
            raise ValueError('PALACE_EXTENSION: unknown contribution')
    data.update(operation=operation,model_status='experimental')
    return {'contract':'spike/extension-result/v1','status':'completed' if data['status'] in {'completed','ready_to_run','available'} else 'completed_with_warnings',
            'title':'Palace native workflow (experimental)','data':data}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True)
    parser.add_argument('--result',required=True)
    args=parser.parse_args()
    request=runtime.strict_json(runtime.read_file(Path(args.request),4*1024**2))
    write_result(args.result,execute(request))

if __name__=='__main__':
    main()
