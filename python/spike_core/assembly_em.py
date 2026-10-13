# SPDX-License-Identifier: Apache-2.0
"""Explicit retained-volume OpenEMS execution through the managed runtime."""
from __future__ import annotations

import inspect
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from .assembly_field_handoff import bounded_json, field_resource_limits, prepare_assembly_field_handoff
from .multiboard_identity import canonical_json_digest
from .assembly_em_grid import retained_em_grid_axes
from .assembly_em_diagnostics import native_material_sampling
from .openems_stopping import parse_openems_stopping

REQUEST_CONTRACT = 'spike/assembly-em-request/v1'


def prepare_assembly_em(request):
    from extensions.openems_suite.retained_volume_geometry import compile_retained_volume_geometry
    if not isinstance(request,dict) or set(request)!={'contract','geometry','ports','settings'}:
        raise ValueError('ASSEMBLY_EM_FIELDS: contract, geometry, ports and settings required')
    limits=field_resource_limits(request['geometry'])
    bounded_json(request,max_bytes=limits['max_control_bytes'])
    if request['contract']!=REQUEST_CONTRACT:
        raise ValueError('ASSEMBLY_EM_CONTRACT: unsupported request')
    handoff=prepare_assembly_field_handoff(request['geometry'])
    compiled=compile_retained_volume_geometry(handoff,request['ports'])
    settings=request['settings']
    if not isinstance(settings,dict) or set(settings)-{'mesh_policy'}!={'frequency_hz','mesh_resolution_m','air_margin_m',
            'max_timesteps','end_criteria','timeout_s','threads'}:
        raise ValueError('ASSEMBLY_EM_SETTINGS: exact bounded settings required')
    if 'mesh_policy' in settings and (settings['mesh_policy']!='cartesian_sampling_v1' or request['geometry'].get('resource_profile')!='routed_pcb_em_v1'):
        raise ValueError('ASSEMBLY_EM_MESH: sampling policy requires the explicit routed EM profile')
    def numeric(value,low,high,label,integer=False):
        if (type(value) not in ((int,) if integer else (int,float)) or not math.isfinite(value)
                or not low<=value<=high):
            raise ValueError('ASSEMBLY_EM_SETTINGS: invalid '+label)
    frequencies=settings['frequency_hz']
    if not isinstance(frequencies,list) or not 2<=len(frequencies)<=1024:
        raise ValueError('ASSEMBLY_EM_SETTINGS: 2..1024 sweep samples required')
    for frequency in frequencies:numeric(frequency,1e3,1e12,'frequency')
    if any(b<=a for a,b in zip(frequencies[:-1],frequencies[1:])):
        raise ValueError('ASSEMBLY_EM_SETTINGS: frequencies must increase')
    numeric(settings['mesh_resolution_m'],1e-6,1,'mesh resolution')
    numeric(settings['air_margin_m'],1e-5,10,'air margin')
    numeric(settings['max_timesteps'],1000,2_000_000,'timesteps',True)
    numeric(settings['end_criteria'],1e-9,1e-3,'end criterion')
    numeric(settings['timeout_s'],10,1800,'timeout',True)
    numeric(settings['threads'],1,64,'threads',True)
    epsilon=max(p['material']['relative_permittivity']*p['material']['relative_permeability']
                for p in compiled['primitives'])
    if settings['mesh_resolution_m']>299792458/(frequencies[-1]*math.sqrt(epsilon)*20):
        raise ValueError('ASSEMBLY_EM_MESH: fewer than 20 cells per shortest material wavelength')
    if settings['air_margin_m']<3*settings['mesh_resolution_m']:
        raise ValueError('ASSEMBLY_EM_MESH: minimum three-cell material/PML clearance required')
    retained_em_grid_axes(compiled,settings)
    bounded_json(compiled,max_bytes=limits['max_control_bytes'])
    return {'compiled':compiled,'settings':settings,'request_digest':canonical_json_digest(request),
            'assembly_digest':handoff['assembly_digest']}


def run_assembly_em(request, directory):
    from extensions.openems_suite.retained_volume_geometry import emit_retained_volume_geometry
    from extensions.openems_suite.retained_volume_driver import WORKER
    from extensions.openems_suite.openems_mesh_policy import ACTUAL_GRID_POLICY_SOURCE
    from extensions.openems_suite.engine import _run_isolated_python
    from extensions.openems_suite.runtime import openems_python,openems_install_root
    prepared=prepare_assembly_em(request)
    prepared['run_id']=uuid4().hex
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    # Immutable trusted code and finite data sent through stdin. No editable
    # case driver or arbitrary executable supplied by the request is executed.
    source=('import json\nINPUT=json.loads('+repr(json.dumps(prepared,allow_nan=False))+')\n'
            +inspect.getsource(emit_retained_volume_geometry)+'\n'+inspect.getsource(retained_em_grid_axes)+'\n'+ACTUAL_GRID_POLICY_SOURCE+'\n'+WORKER).encode()
    (directory/'request.json').write_text(json.dumps(request,allow_nan=False),encoding='utf-8')
    environment={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','USERPROFILE','LD_LIBRARY_PATH') if k in os.environ}
    environment.update(OPENEMS_INSTALL_PATH=openems_install_root(),TEMP=str(directory),TMP=str(directory))
    execution=_run_isolated_python(openems_python(),source,[],cwd=directory,environment=environment,
        log_path=directory/'solver.log',output_root=directory,
        timeout_seconds=prepared['settings']['timeout_s']+30,output_limit_bytes=512*1024**2)
    log_path=directory/'solver.log'
    log_text=log_path.read_text(encoding='utf-8',errors='replace') if log_path.is_file() else ''
    command=execution.get('command')
    python_executable=command[0] if isinstance(command,list) and command else openems_python()
    runtime_identity={'engine':'openEMS','python_package_version':'unknown',
        'adapter':'SPIKE retained-volume driver','python_executable':python_executable,
        'openems_install_path':openems_install_root()}
    if not (execution['returncode'] or execution['timed_out'] or execution['quota_exceeded']):
        result_path=directory/'result.json'
        if result_path.is_file() and result_path.stat().st_size<=16*1024**2:
            candidate=json.loads(result_path.read_text(encoding='utf-8'))
            child_identity=candidate.get('runtime_identity')
            if isinstance(child_identity,dict):runtime_identity.update(child_identity)
    stopping=parse_openems_stopping(log_text,
        requested_end_criteria=prepared['settings']['end_criteria'],
        requested_max_timesteps=prepared['settings']['max_timesteps'],
        execution=execution,runtime_identity=runtime_identity)
    execution['status']=stopping['execution_status']
    execution['stopping']=stopping
    (directory/'execution.json').write_text(json.dumps(execution,allow_nan=False),encoding='utf-8')
    if execution['returncode'] or execution['timed_out'] or execution['quota_exceeded']:
        raise ValueError('ASSEMBLY_EM_EXECUTION: failed; inspect '+str(directory/'solver.log'))
    result_path=directory/'result.json'
    if not result_path.is_file() or result_path.stat().st_size>16*1024**2:
        raise ValueError('ASSEMBLY_EM_RESULT: absent or excessive result')
    result=json.loads(result_path.read_text(encoding='utf-8'))
    bounded_json(result)
    if (result.get('contract')!='spike/assembly-em-result/v1' or
            result.get('status')!='completed' or result.get('solver_executed') is not True or
            result.get('execution_status')!='completed' or
            result.get('model_status')!='unvalidated' or result.get('production_qualified') is not False or
            result.get('request_digest')!=prepared['request_digest'] or
            result.get('run_id')!=prepared['run_id'] or
            result.get('excited_port_id')!=next(p['id'] for p in prepared['compiled']['ports'] if p['excite']) or
            result.get('compiled_digest')!=prepared['compiled']['compiled_digest'] or
            result.get('frequency_hz')!=prepared['settings']['frequency_hz'] or
            [p.get('port_id') for p in result.get('s_parameter_column',[])]!=
                [p['id'] for p in prepared['compiled']['ports']]):
        raise ValueError('ASSEMBLY_EM_RESULT: geometry identity mismatch')
    count=len(prepared['settings']['frequency_hz'])
    for column in result['s_parameter_column']:
        for key in ('real','imag'):
            if not isinstance(column.get(key),list) or len(column[key])!=count or any(
                    type(value) not in (int,float) or not math.isfinite(value) for value in column[key]):
                raise ValueError('ASSEMBLY_EM_RESULT: malformed response column')
    artifacts={}
    for relative in ('geometry.xml','simulation/electric-field.h5','simulation/magnetic-field.h5'):
        path=directory/relative
        if not path.is_file():raise ValueError('ASSEMBLY_EM_RESULT: missing '+relative)
        with path.open('rb') as stream:artifacts[relative]=hashlib.file_digest(stream,'sha256').hexdigest()
    result['material_sampling']=native_material_sampling(log_text,prepared['compiled'])
    if result['material_sampling']['native_unused_primitive_count']:
        sample=result['material_sampling']
        result['limitations'].append(f"Native grid did not sample {sample['unused_conductive_primitive_count']} conductive and {sample['unused_nonconductive_primitive_count']} nonconductive polyhedra; this run is not an accuracy-qualified board result.")
    with (directory/'solver.log').open('rb') as stream:artifacts['solver.log']=hashlib.file_digest(stream,'sha256').hexdigest()
    result['stopping']=stopping
    # Historical compatibility only. New consumers use ``stopping`` so that
    # execution completion, cap detection and decay achievement stay separate.
    result['termination']={'timestep_limit_detected':stopping['timestep_cap_hit'],
        'did_reach_end_criteria':stopping['did_reach_requested_decay'],
        'evidence':stopping['evidence_source']}
    if stopping['timestep_cap_hit'] is True and stopping['did_reach_requested_decay'] is False:
        result['limitations'].append('Native solver reached timestep limit before requested energy decay; execution is complete but decay convergence failed.')
    result.update(request_digest=prepared['request_digest'],assembly_digest=prepared['assembly_digest'],
                  execution=execution,artifact_directory=str(directory),artifact_sha256=artifacts,
                  trusted_worker_sha256=hashlib.sha256(source).hexdigest())
    return result
