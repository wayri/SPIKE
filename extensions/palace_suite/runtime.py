# SPDX-License-Identifier: Apache-2.0
"""Original SPIKE native Palace admission and bounded jobs; no copied solver code."""
from __future__ import annotations
import copy
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import uuid
from python.spike_core.sparselizard_process import run_adapter_process
from python.spike_core.solver_state import _state_root

PROBLEM_TYPES = ('Eigenmode','Driven','Transient','Electrostatic','Magnetostatic','BoundaryMode')
MAX_CONFIG = 2 * 1024**2
MAX_MESH = 256 * 1024**2
MAX_OUTPUT = 256 * 1024**2
MAX_TABLE = 2 * 1024**2

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('PALACE_JSON: duplicate key ' + key)
        value[key] = item
    return value

def strict_json(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=lambda v: (_ for _ in ()).throw(ValueError('PALACE_JSON: nonfinite '+v)))

def no_links(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('PALACE_PATH: links/reparse points prohibited')

def read_file(path, limit):
    no_links(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('PALACE_FILE: missing, irregular, or oversized file')
    with path.open('rb') as handle:
        data = handle.read(limit+1)
    if len(data) > limit:
        raise ValueError('PALACE_FILE: file exceeds limit')
    return data

def runtime_info(params):
    selected = params.get('runtime_path') or shutil.which('palace')
    if not selected:
        return {'available':False,'path':None,'reason':'Install Palace separately and select its executable.'}
    path = Path(selected)
    if not path.is_absolute():
        raise ValueError('PALACE_RUNTIME: runtime_path must be absolute')
    no_links(path)
    if not path.is_file() or path.suffix.lower() in {'.bat','.cmd','.ps1','.py'}:
        return {'available':False,'path':str(path),'reason':'Select Palace native binary or installed POSIX launcher.'}
    return {'available':True,'path':str(path.resolve()),'sha256':digest(read_file(path, MAX_MESH)),
            'version':None,'version_status':'not_probed','execution':'single_mpi_rank'}

def limits(params):
    result = {}
    for name, default, low, high in [('timeout_s',180,1,3300),('memory_limit_mb',2048,256,32768)]:
        value = params.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError('PALACE_LIMIT: invalid '+name)
        result[name] = value
    if params.get('threads',1) != 1:
        raise ValueError('PALACE_UNSUPPORTED: explicit thread/MPI allocation unavailable; use threads=1')
    return result

def validate(params):
    config = params.get('config')
    if not isinstance(config, dict) or set(config) != {'Problem','Model','Domains','Boundaries','Solver'}:
        raise ValueError('PALACE_CONFIG: supply exactly five native configuration sections')
    if any(not isinstance(config[key],dict) for key in config):
        raise ValueError('PALACE_CONFIG: native sections must be objects')
    payload = encoded(config)
    if len(payload) > MAX_CONFIG:
        raise ValueError('PALACE_CONFIG: exceeds 2 MiB')
    problem = config['Problem'].get('Type')
    issues = []
    if problem not in PROBLEM_TYPES:
        issues.append({'code':'unsupported_problem','message':'Unknown Palace problem type: '+str(problem)})
    l0 = config['Model'].get('L0')
    if type(l0) not in (float,int) or not math.isfinite(l0) or l0 <= 0:
        raise ValueError('PALACE_UNITS: explicitly supply positive Model.L0 in meters per coordinate unit')
    if not isinstance(config['Domains'].get('Materials'),list) or not config['Domains']['Materials']:
        raise ValueError('PALACE_MATERIALS: explicitly supply native domain materials')
    def check_assets(value, location=''):
        if isinstance(value,dict):
            for key,item in value.items():
                current = location+'/'+key
                if isinstance(item,str) and (key.lower().endswith(('file','path')) or key == 'Partitioning'):
                    issues.append({'code':'unsupported_asset','message':'External native asset not staged: '+current})
                check_assets(item,current)
        elif isinstance(value,list):
            for item in value:
                check_assets(item,location)
    check_assets(config)
    mesh_path = Path(params.get('mesh_path',''))
    if not mesh_path.is_absolute():
        raise ValueError('PALACE_MESH: supply absolute mesh_path')
    mesh = read_file(mesh_path, MAX_MESH)
    if not mesh:
        raise ValueError('PALACE_MESH: empty mesh')
    sha = digest(mesh)
    if params.get('expected_mesh_sha256') is not None and params['expected_mesh_sha256'] != sha:
        raise ValueError('PALACE_SOURCE: mesh changed; validate and review again')
    return {'status':'unsupported' if issues else 'ready_to_run','problem_type':problem,'issues':issues,
            'mesh_sha256':sha,'config_sha256':digest(payload),'mesh_bytes':len(mesh),'mesh_units_m':l0,
            'validation_scope':'adapter admission only; native schema/physics checks occur in Palace', 'limits':limits(params)}

def job_root():
    root = _state_root()/'palace-jobs'
    no_links(root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    return root

def job_path(job_id):
    if not isinstance(job_id,str) or not re.fullmatch('[0-9a-f]{32}',job_id):
        raise ValueError('PALACE_JOB: invalid job ID')
    path = job_root()/job_id
    no_links(path)
    return path

def prepare(params,binding):
    admission = validate(params)
    if admission['status'] != 'ready_to_run':
        return admission
    mesh = read_file(Path(params['mesh_path']), MAX_MESH)
    if digest(mesh) != admission['mesh_sha256']:
        raise ValueError('PALACE_SOURCE: mesh changed during preparation')
    job_id = uuid.uuid4().hex
    job = job_path(job_id)
    job.mkdir(mode=0o700)
    suffix = Path(params['mesh_path']).suffix
    if not re.fullmatch(r'\.[A-Za-z0-9]{1,10}',suffix):
        suffix = '.mesh'
    mesh_name = 'input'+suffix
    config = copy.deepcopy(params['config'])
    config['Model']['Mesh'] = mesh_name
    config['Problem']['Output'] = 'output'
    config_bytes = encoded(config)
    (job/mesh_name).write_bytes(mesh)
    (job/'config.json').write_bytes(config_bytes)
    record = {**admission,'job_id':job_id,'design_binding':binding,'mesh_name':mesh_name,
              'staged_config_sha256':digest(config_bytes),'solved':False}
    (job/'case.json').write_bytes(encoded(record))
    return record

def import_outputs(job_id,binding,cancellation_event=None):
    job = job_path(job_id)
    record = strict_json(read_file(job/'case.json',MAX_CONFIG))
    if record.get('design_binding') != binding:
        raise ValueError('PALACE_BINDING: retained case belongs to another design')
    if record.get('mesh_name') not in {'input.mesh','input.msh','input.vtk','input.vtu'}:
        if not re.fullmatch(r'input\.[A-Za-z0-9]{1,10}',str(record.get('mesh_name'))):
            raise ValueError('PALACE_BINDING: unsafe retained mesh reference')
    if digest(read_file(job/'config.json',MAX_CONFIG)) != record['staged_config_sha256'] or digest(read_file(job/record['mesh_name'],MAX_MESH)) != record['mesh_sha256']:
        raise ValueError('PALACE_BINDING: retained input changed')
    completion = strict_json(read_file(job/'completion.json',MAX_CONFIG))
    if completion.get('return_code') != 0:
        raise ValueError('PALACE_RESULT: failed or incomplete output cannot be imported')
    tables,artifacts,total = [],[],0
    output = job/'output'
    no_links(output)
    if not output.is_dir():
        raise ValueError('PALACE_RESULT: missing output directory')
    for path in output.rglob('*'):
        no_links(path)
        if not path.is_file():
            continue
        total += path.stat().st_size
        if total > MAX_OUTPUT or len(artifacts) >= 4096:
            raise ValueError('PALACE_RESULT: output exceeds resource limit')
        data = read_file(path,MAX_OUTPUT)
        name = path.relative_to(output).as_posix()
        artifact = {'name':name,'path':str(path),'bytes':len(data),'sha256':digest(data),
                    'kind':'field' if path.suffix.lower() in {'.vtu','.pvtu','.pvd','.vtk','.gf'} else 'metadata'}
        artifacts.append(artifact)
        if path.suffix.lower() == '.csv':
            if len(data) > MAX_TABLE:
                artifact['table_status'] = 'oversized_reference_only'
                continue
            rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
            if not rows or len(rows)>10001 or any(len(row)>256 or any(len(cell)>4096 for cell in row) for row in rows):
                raise ValueError('PALACE_TABLE: empty or oversized table')
            headers = [cell.strip() for cell in rows[0]]
            if any(len(row)!=len(headers) for row in rows[1:]):
                raise ValueError('PALACE_TABLE: inconsistent column count')
            tables.append({'name':name,'headers':headers,'rows':rows[1:],'units':'solver_header','truncated':False})
    if not tables and not any(item['kind']=='field' for item in artifacts):
        raise ValueError('PALACE_RESULT: no scalar tables or field artifacts')
    result = {'status':'completed','solved':True,'case':record,'tables':tables,'artifacts':artifacts,
              'model_status':'experimental','field_view_status':'optional_vtk_point_preview',
              'field_previews':field_previews(job,artifacts,record['mesh_units_m'],cancellation_event),
              'issues':[{'code':'accuracy_unqualified','message':'Completion does not establish solver accuracy or convergence.'}]}
    if len(encoded(result)) > 6*1024**2:
        raise ValueError('PALACE_RESULT: tables exceed 6 MiB; inspect retained artifacts locally')
    return result

def run(params,binding,cancellation_event=None):
    if not re.fullmatch('[a-f0-9]{64}',str(params.get('expected_mesh_sha256',''))):
        raise ValueError('PALACE_SOURCE: run requires reviewed expected_mesh_sha256')
    runtime = runtime_info(params)
    if not runtime['available']:
        return {'status':'runtime_unavailable','runtime':runtime,'solved':False}
    record = prepare(params,binding)
    if record['status'] != 'ready_to_run':
        return record
    job = job_path(record['job_id'])
    launcher = Path(runtime['path']).name == 'palace' and os.name != 'nt'
    command = [runtime['path'],*(['-np','1'] if launcher else []),'config.json']
    import threading
    cancellation_event = cancellation_event or threading.Event()
    output_overflow = threading.Event()
    monitor_done = threading.Event()
    def monitor_output():
        while not monitor_done.wait(0.25):
            try:
                files=[]
                for path in (job/'output').rglob('*'):
                    files.append(path)
                    if len(files)>8192:
                        break
                if len(files)>8192 or sum(path.lstat().st_size for path in files if path.is_file())>MAX_OUTPUT:
                    output_overflow.set()
                    cancellation_event.set()
                    return
                for path in files:
                    no_links(path)
            except (OSError,ValueError):
                output_overflow.set()
                cancellation_event.set()
                return
    threading.Thread(target=monitor_output,daemon=True).start()
    try:
        process = run_adapter_process(command,cwd=job,**record['limits'],output_limit_bytes=MAX_OUTPUT,
            stream_limit_bytes=2*1024**2,cancellation_event=cancellation_event,windows_active_process_limit=8)
    except RuntimeError as exc:
        return {'status':'resource_limit' if output_overflow.is_set() else ('cancelled' if cancellation_event.is_set() else 'failed'),
                'case':record,'solved':False,'issues':[{'code':'runtime_failure','message':str(exc)}]}
    finally:
        monitor_done.set()
    if output_overflow.is_set():
        return {'status':'resource_limit','case':record,'solved':False,'issues':[{'code':'output_limit','message':'Output quota exceeded.'}]}
    (job/'stdout.log').write_text(process['stdout'],encoding='utf-8')
    (job/'stderr.log').write_text(process['stderr'],encoding='utf-8')
    (job/'completion.json').write_bytes(encoded({'return_code':process['return_code'],'runtime':runtime}))
    if process['return_code'] != 0:
        return {'status':'failed','case':record,'solved':False,'return_code':process['return_code'],
                'issues':[{'code':'runtime_failure','message':process['stderr'][-8192:]}]}
    result = import_outputs(record['job_id'],binding,cancellation_event)
    result['runtime'] = runtime
    return result

def supervised_run(params,binding,validate_only=False):
    """Detached fixed-code guardian survives SDK wrapper termination to reap native jobs."""
    import subprocess
    import sys
    import time
    control=job_root()/('control-'+uuid.uuid4().hex)
    control.mkdir(mode=0o700)
    (control/'request.json').write_bytes(encoded({'owner_pid':os.getpid(),'parameters':params,'binding':binding,'operation':'validate' if validate_only else 'run'}))
    guardian=Path(__file__).with_name('guardian.py')
    process=subprocess.Popen(python_command(guardian,control),stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name!='nt',
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+limits(params)['timeout_s']+160
    while process.poll() is None:
        if time.monotonic()>deadline:
            (control/'cancel').write_text('timeout')
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
            raise ValueError('PALACE_GUARDIAN: exceeded supervision deadline')
        time.sleep(0.1)
    if process.returncode!=0:
        raise ValueError('PALACE_GUARDIAN: process failed')
    return strict_json(read_file(control/'result.json',8*1024**2))

def field_previews(job,artifacts,l0,cancellation_event=None):
    """Optional VTK parsing stays in a bounded process, never the UI event loop."""
    import sys
    result=[]
    fields=[item for item in artifacts if item['name'].lower().endswith('.vtu')]
    for item in fields[:4]:
        if cancellation_event is not None and cancellation_event.is_set():
            break
        if item['bytes']>64*1024**2:
            preview={'status':'unsupported','message':'VTU exceeds the 64 MiB preview bound.'}
        else:
            try:
                process=run_adapter_process(python_command(Path(__file__).with_name('field_preview.py'),item['path']),
                    cwd=job,timeout_s=30,memory_limit_mb=2048,output_limit_bytes=4*1024**2,stream_limit_bytes=4*1024**2,windows_active_process_limit=8,cancellation_event=cancellation_event)
                preview=strict_json(process['stdout']) if process['return_code']==0 else {'status':'failed','message':process['stderr'][-1024:]}
            except (RuntimeError,ValueError,OSError) as exc:
                preview={'status':'failed','message':str(exc)}
        result.append({'name':item['name'],'coordinate_units_m':l0,**preview})
    if len(fields)>4:
        result.append({'name':'remaining-fields','status':'unsupported','message':'Preview is limited to four VTU artifacts; complete field files are retained.'})
    return result





def python_command(script,*arguments):
    import sys
    mode=['--extension-host'] if getattr(sys,'frozen',False) else ['-I']
    return [sys.executable,*mode,str(script),*map(str,arguments)]

def native_validate(params,binding,cancellation_event=None):
    info=runtime_info(params)
    if not info['available']:
        return {**validate(params),'runtime':info,'solved':False}
    record=prepare(params,binding)
    if record['status']!='ready_to_run':
        return record
    job=job_path(record['job_id'])
    launcher=Path(info['path']).name=='palace' and os.name!='nt'
    command=[info['path'],*(['-np','1'] if launcher else []),'--dry-run','config.json']
    bounded={**record['limits'],'timeout_s':min(record['limits']['timeout_s'],120)}
    try:
        process=run_adapter_process(command,cwd=job,**bounded,output_limit_bytes=MAX_OUTPUT,
            stream_limit_bytes=2*1024**2,cancellation_event=cancellation_event,windows_active_process_limit=8)
    except RuntimeError as exc:
        return {'status':'failed','solved':False,'case':record,'issues':[{'code':'native_validation_failed','message':str(exc)}]}
    (job/'validation.log').write_text(process['stdout']+'\n'+process['stderr'],encoding='utf-8')
    return {'status':'ready_to_run' if process['return_code']==0 else 'failed','solved':False,'case':record,
        'mesh_sha256':record['mesh_sha256'],'config_sha256':record['config_sha256'],'runtime':info,
        'validation_scope':'Palace --dry-run schema and resolved configuration; no field solve or accuracy qualification',
        'native_validation':{'return_code':process['return_code'],'log':str(job/'validation.log')},
        'issues':[] if process['return_code']==0 else [{'code':'native_validation_failed','message':process['stderr'][-8192:]}]}
