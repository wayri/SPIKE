# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Hash-bound sourced-deck checks; numerical PASS never means hardware qualified."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import time

from .contracts import ProbeDescriptor
from .netlist import NetlistParseError, parse_netlist
from .native_runner import run_native_project, _nodes
from .version import ENGINE_VERSION


def _require(condition, message):
    if not condition:
        raise ValueError('SOURCED_QUALIFICATION: '+message)


def _keys(value, fields):
    _require(isinstance(value,dict) and set(value) == set(fields),'unknown/missing fields')


def _finite(value):
    _require(type(value) in (int,float),'finite number required')
    try:
        value = float(value)
    except OverflowError:
        raise ValueError('SOURCED_QUALIFICATION: unrepresentable number') from None
    _require(math.isfinite(value),'finite number required')
    return value


def _path(root, name):
    _require(isinstance(name,str) and 0 < len(name) <= 512 and '\\' not in name and ':' not in name,'normalized relative path required')
    pieces = PurePosixPath(name)
    _require(not pieces.is_absolute() and all(p not in ('.','..') for p in name.split('/')),'path escape rejected')
    current = root
    for part in pieces.parts:
        current = current/part
        stat = current.lstat()
        _require(not current.is_symlink() and not getattr(stat,'st_file_attributes',0) & 0x400,'reparse/symlink rejected')
    _require(current.is_file() and current.resolve().is_relative_to(root),'regular contained file required')
    return current


def _sources(request,root):
    rows = request['sources']
    _require(isinstance(rows,list) and 1 <= len(rows) <= 64,'bounded source inventory required')
    loaded = {}
    for row in rows:
        _keys(row,('path','sha256','role','origin','revision','conditions','value_basis'))
        _require(isinstance(row['path'],str),'source path must be text')
        _require(row['path'] not in loaded,'duplicate source path')
        _require(row['role'] in ('deck','model'),'source role unsupported')
        for label in ('origin','revision','conditions','value_basis'):
            _require(isinstance(row[label],str) and 0 < len(row[label]) <= 4096,'conditioned provenance required')
        _require(isinstance(row['sha256'],str) and re.fullmatch('[0-9a-f]{64}',row['sha256']) is not None,'SHA256 required')
        path = _path(root,row['path'])
        _require(path.stat().st_size <= 2*1024*1024,'source byte budget exceeded')
        payload = path.read_bytes()
        _require(hashlib.sha256(payload).hexdigest() == row['sha256'],'source hash mismatch')
        loaded[row['path']] = (path,payload.decode('utf-8'))
    _require(sum(len(text.encode()) for _,text in loaded.values()) <= 8*1024*1024,'aggregate source budget exceeded')
    _require(request['deck_path'] in loaded and sum(row['role']=='deck' for row in rows)==1,'one bound deck required')
    _require(next(row for row in rows if row['path']==request['deck_path'])['role']=='deck','deck role mismatch')
    # Audit dependencies before the parser reads them. Library section markers
    # are not file references; all file-form directives must be hash admitted.
    for path,text in loaded.values():
        for line in text.splitlines():
            match = re.match(r'''(?i)^\s*\.(include|lib)\s+(?:"([^"]+)"|'([^']+)'|(\S+))(.*)$''',line.split('$',1)[0])
            if not match or (match[1].lower()=='lib' and not match[5].strip()):
                continue
            name = next(value for value in match.groups()[1:4] if value is not None)
            _require(not PurePosixPath(name).is_absolute() and all(p not in ('.','..') for p in name.split('/'))
                     and '\\' not in name and ':' not in name,'include requires normalized relative path')
            candidate = path.parent/name
            _require(candidate.resolve() in {p.resolve() for p,_ in loaded.values()},'unlisted include dependency')
    return loaded


def _trace(result,probe):
    descriptor = ProbeDescriptor.parse(probe)
    tables = {'node_voltage':'node_voltage_v','element_current':'element_current_a','element_power':'element_power_w'}
    values = result.data[tables[descriptor.quantity]]
    left = values.get(descriptor.targets[0],0.) if descriptor.targets[0]=='0' else values[descriptor.targets[0]]
    left = left if isinstance(left,list) else [left]
    if len(descriptor.targets)==2:
        right = values.get(descriptor.targets[1],0.) if descriptor.targets[1]=='0' else values[descriptor.targets[1]]
        right = right if isinstance(right,list) else [right]*len(left)
        left = [a-b for a,b in zip(left,right,strict=True)]
    _require(left and all(math.isfinite(v) for v in left),'empty/nonfinite observable')
    return left


def _observe(times,values,check):
    kind = check['measurement']
    if kind=='last': return values[-1]
    if kind=='min': return min(values)
    if kind=='max': return max(values)
    threshold = _finite(check['threshold'])
    for a,b,va,vb in zip(times,times[1:],values,values[1:]):
        if va < threshold <= vb:
            return a+(b-a)*(threshold-va)/(vb-va)
    return None


def qualify_sourced_deck(request,source_root):
    """Execute one admitted OP/transient deck at three output-step refinements.

    No timeout/process isolation is added here: this is a bounded local developer
    API, not an untrusted-model production runner. Vendor models are referenced,
    never copied into the report. Source integrity is distinct from authenticity.
    """
    _keys(request,('contract','id','deck_path','sources','checks','pin_mapping','purpose'))
    _require(request['contract']=='spikes/sourced-qualification-request/v1','unsupported contract')
    _require(request['purpose'] in ('solver_regression','design_prediction'),'purpose unsupported')
    _require(isinstance(request['id'],str) and re.fullmatch('[A-Za-z0-9._-]{1,128}',request['id']),'bounded id required')
    _require(isinstance(request['pin_mapping'],dict),'explicit caller pin mapping required')
    _require(len(json.dumps(request,allow_nan=False).encode()) <= 8*1024*1024,'control byte budget exceeded')
    root = Path(source_root).resolve(strict=True)
    loaded = _sources(request,root)
    path,text = loaded[request['deck_path']]
    checks = request['checks']
    _require(isinstance(checks,list) and 1 <= len(checks) <= 32,'bounded checks required')
    for check in checks:
        _keys(check,('probe','measurement','threshold','minimum','maximum','numerical_absolute_tolerance','numerical_relative_tolerance'))
        ProbeDescriptor.parse(check['probe'])
        _require(check['measurement'] in ('last','min','max','first_rising_crossing'),'measurement unsupported')
        _require(_finite(check['minimum']) <= _finite(check['maximum']),'invalid physical acceptance range')
        _require(_finite(check['numerical_absolute_tolerance']) >= 0 and _finite(check['numerical_relative_tolerance']) >= 0,'invalid numerical tolerance')
    report = {'contract':'spikes/sourced-qualification-result/v1','id':request['id'],'status':'NOT_RUN',
              'hardware_qualified':False,'model_status':'experimental','purpose':request['purpose'],
              'sources':request['sources'],'pin_mapping':request['pin_mapping'],
              'pin_mapping_status':'caller_declared_not_physical_verification','runs':[],
              'limitations':['local bounded in-process native runs, not OS-isolated vendor-model execution',
                             'numerical PASS is not guaranteed corners, SOA, installed cooling or hardware qualification']}
    try:
        project = parse_netlist(text,source_name=str(path),native_extensions=True,
                                probes=tuple(ProbeDescriptor.parse(c['probe']) for c in checks),
                                source_snapshots={str(p.resolve()):content for p,content in loaded.values()})
    except (NetlistParseError,ValueError) as error:
        report.update(status='BLOCKED',compatibility_error=str(error))
        return report
    _require(project.analysis.mode in ('operating_point','transient') and not project.steps and not project.measurements,'unsupported analysis orchestration')
    _require(len(project.elements) <= 256,'element budget exceeded')
    maximum_points = min(20000,2_000_000//(len(_nodes(project))+2*len(project.elements)+1))
    from python.spike_core.spikes_runtime import owned_library_path
    library = owned_library_path()
    report['solver'] = {'version':ENGINE_VERSION,'library_sha256':hashlib.sha256(library.read_bytes()).hexdigest(),
                        'integration':'backward_euler','expanded_source_sha256':project.source_sha256}
    observed = []
    for factor in ((1,2,4) if project.analysis.mode=='transient' else (1,)):
        step = project.analysis.time_step_s/factor if project.analysis.mode=='transient' else None
        if step is not None:
            points = math.ceil(project.analysis.stop_time_s/step)+1
            _require(points <= maximum_points,'trace allocation budget exceeded')
        refined = replace(project,analysis=replace(project.analysis,time_step_s=step))
        start = time.perf_counter()
        result = run_native_project(refined,library,integration_method='backward_euler',maximum_steps=maximum_points-1)
        run = {'output_step_s':step,'maximum_native_points':maximum_points,'wall_time_s':time.perf_counter()-start,'status':result.status,
               'diagnostics':result.diagnostics,'issues':result.issues,'stdout':None,'stderr':None}
        report['runs'].append(run)
        if result.status!='completed':
            report['status']='FAIL'
            return report
        times = result.data.get('time_s',[0.])
        _require(all(math.isfinite(t) for t in times) and all(b>a for a,b in zip(times,times[1:])),'nonfinite/nonmonotone time')
        traces = {c['probe']:_trace(result,c['probe']) for c in checks}
        _require(all(len(v)==len(times) for v in traces.values()),'misaligned waveforms')
        values = [_observe(times,traces[c['probe']],c) for c in checks]
        run.update(time_s=times,traces=traces,observations=values)
        observed.append(values)
    # Recheck source bytes after parsing/execution; any drift invalidates evidence.
    _sources(request,root)
    _require(hashlib.sha256(library.read_bytes()).hexdigest()==report['solver']['library_sha256'],'native library changed during run')
    gates = []
    for i,check in enumerate(checks):
        value = observed[-1][i]
        comparisons = []
        for previous,current in zip(observed,observed[1:]):
            tolerance = max(check['numerical_absolute_tolerance'],check['numerical_relative_tolerance']*abs(current[i])) if current[i] is not None else 0.
            comparisons.append(previous[i] is not None and current[i] is not None and abs(previous[i]-current[i]) <= tolerance)
        gates.append({'check':check,'observed':value,'acceptance_passed':value is not None and check['minimum'] <= value <= check['maximum'],
                      'refinement_passed':all(comparisons),'refinement_status':'checked' if comparisons else 'not_applicable_operating_point'})
    report['gates'] = gates
    report['status'] = 'PASS' if all(g['acceptance_passed'] and g['refinement_passed'] for g in gates) else 'FAIL'
    _require(len(json.dumps(report,allow_nan=False).encode()) <= 8*1024*1024,'result byte budget exceeded')
    return report
