# SPDX-License-Identifier: Apache-2.0
"""Revision-bound two-application IC/ASIC flow preflight, never tool execution."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

CONTRACT='spikes/asic-project/v1'
_ID=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}\Z')
_HASH=re.compile(r'[0-9a-f]{64}\Z')
_ROLES={'rtl','schematic','constraints','liberty','technology_lef','cell_lef','cell_gds','layout','pdk_models','reference_netlist',
        'analog_macro_lef','analog_macro_gds','analog_macro_models'}
_ENGINES={'synthesis','place_route','timing','pex','klayout','simulation'}
_STAGES={
 'digital':[
  ('rtl_check','synthesis',('rtl',)),
  ('technology_synthesis','synthesis',('rtl','liberty','constraints')),
  ('floorplan_place_cts_route','place_route',('technology_lef','cell_lef','liberty','constraints')),
  ('stream_out','klayout',('cell_gds',)),
  ('drc','klayout',()),('lvs','klayout',('reference_netlist',)),
  ('parasitic_extraction','pex',()),('post_layout_timing','timing',('liberty','constraints')),
  ('post_layout_simulation','simulation',('pdk_models',)),
 ],
 'analog':[
  ('schematic_simulation','simulation',('schematic','pdk_models')),
  ('layout_edit','klayout',('layout',)),('drc','klayout',()),
  ('lvs','klayout',('reference_netlist',)),('parasitic_extraction','pex',()),
  ('post_layout_simulation','simulation',('pdk_models',)),
 ]}
_STAGES['mixed_signal']=[
 ('schematic_simulation','simulation',('schematic','pdk_models','analog_macro_models')),
 *_STAGES['digital'][:2],
 ('floorplan_place_cts_route','place_route',('technology_lef','cell_lef','liberty','constraints','analog_macro_lef')),
 ('layout_edit','klayout',('layout','analog_macro_gds')),
 ('stream_out','klayout',('cell_gds','analog_macro_gds')),
 *_STAGES['digital'][4:],
]


def _digest(path,max_bytes):
    size=path.stat().st_size
    if size>max_bytes:raise ValueError('Artifact exceeds admitted size: '+str(path))
    sha=hashlib.sha256();read=0
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            read+=len(chunk)
            if read>max_bytes:raise ValueError('Artifact grew beyond size limit')
            sha.update(chunk)
    return sha.hexdigest(),size


def plan(project,root):
    """Validate actual inputs/engine identity and expose all missing flow gates.

    A matching hash is identity evidence, not a foundry approval or indication
    that the engine supports the selected PDK. No script or engine runs here.
    """
    if not isinstance(project,dict) or set(project)-{'contract','name','kind','top','pdk_revision','artifacts','engines','runsets'}:
        raise ValueError('Unknown ASIC project fields')
    if project.get('contract')!=CONTRACT:raise ValueError('Unsupported ASIC project contract')
    for key in ('name','top'):
        if not isinstance(project.get(key),str) or not _ID.fullmatch(project[key]):raise ValueError(key+' must be a bounded identifier')
    kind=project.get('kind')
    if kind not in _STAGES:raise ValueError('kind must be analog, digital or mixed_signal')
    revision=project.get('pdk_revision')
    if not isinstance(revision,str) or not revision.strip() or len(revision)>256:raise ValueError('Exact PDK revision is required')
    root=Path(root).resolve(strict=True)
    if not root.is_dir():raise ValueError('Project root must be a directory')
    artifacts=project.get('artifacts',[]);engines=project.get('engines',{});runsets=project.get('runsets',{})
    if not isinstance(artifacts,list) or len(artifacts)>128:raise ValueError('At most 128 input artifacts')
    if not isinstance(engines,dict) or set(engines)-_ENGINES:raise ValueError('Unknown engine role')
    if not isinstance(runsets,dict) or len(runsets)>32:raise ValueError('runsets must be a bounded mapping')
    known_stages={stage for rows in _STAGES.values() for stage,_,_ in rows}
    if set(runsets)-known_stages:raise ValueError('Unknown stage runset')
    records=[];by_role={};issues=[];input_paths=set()

    def local_path(value):
        if not isinstance(value,str) or len(value)>1024:raise ValueError('Artifact path must be bounded text')
        relative=Path(value)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Artifact must be root-relative without parent traversal')
        path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('Artifact path escapes project root')
        return path

    def identity(item,path):
        expected=item.get('sha256')
        if not isinstance(expected,str) or not _HASH.fullmatch(expected):raise ValueError('Require exact lowercase SHA-256 identity')
        if not path.is_file():return dict(status='missing',path=str(path),expected_sha256=expected)
        actual,size=_digest(path,1024*1024*1024)
        return dict(status='matched' if actual==expected else 'changed',path=str(path),sha256=actual,expected_sha256=expected,bytes=size)

    for item in artifacts:
        if not isinstance(item,dict) or set(item)!={'role','path','sha256'} or item['role'] not in _ROLES:raise ValueError('Invalid artifact record')
        path=local_path(item['path'])
        if path in input_paths:raise ValueError('Duplicate input artifact path')
        input_paths.add(path)
        record=dict(identity(item,path),role=item['role']);records.append(record)
        by_role.setdefault(item['role'],[]).append(record)
    resolved_engines={}
    for role,item in engines.items():
        if not isinstance(item,dict) or set(item)!={'path','sha256','license_record'}:raise ValueError('Engine requires path/hash/licence evidence')
        license_path=local_path(item['license_record'])
        if not license_path.is_file():raise ValueError('Engine licence record is missing')
        if not isinstance(item['path'],str):raise ValueError('Engine path must be text')
        executable=Path(item['path'])
        if not executable.is_absolute():executable=local_path(item['path'])
        record=identity(item,executable.resolve())
        record['license_record']=str(license_path);record['license_review']='not_established_by_preflight'
        record['license_record_sha256']=_digest(license_path,4*1024*1024)[0]
        resolved_engines[role]=record
    resolved_runsets={}
    for stage,item in runsets.items():
        if not isinstance(item,dict) or set(item)!={'path','sha256'}:raise ValueError('Runset requires path and hash')
        resolved_runsets[stage]=identity(item,local_path(item['path']))
    stages=[]
    for index,(stage,engine,required) in enumerate(_STAGES[kind]):
        missing=[]
        for role in required:
            if not by_role.get(role) or any(item['status']!='matched' for item in by_role[role]):missing.append('missing/changed '+role)
        if resolved_engines.get(engine,{}).get('status')!='matched':missing.append('missing/changed '+engine+' engine')
        if resolved_runsets.get(stage,{}).get('status')!='matched':missing.append('missing/changed '+stage+' PDK runset')
        if index:missing.append('preceding stage result has not been executed/validated')
        stages.append(dict(id=stage,engine=engine,required_inputs=list(required),
                           status='blocked' if missing else 'ready_for_review',blockers=missing,
                           evidence_status='not_run',foundry_qualified=False))
    for item in records:
        if item['status']!='matched':issues.append(dict(code='ASIC_INPUT_'+item['status'].upper(),path=item['path']))
    return dict(contract='spikes/asic-flow-plan/v1',project=project['name'],top=project['top'],kind=kind,
                user_facing_applications=['SPIKES','KLayout'],pdk_revision=revision,
                artifacts=records,engines=resolved_engines,runsets=resolved_runsets,stages=stages,issues=issues,
                release_ready=False,qualification=False,
                limitations=['Preflight and revision identity only; no synthesis, physical design, DRC/LVS or PEX execution occurs here.',
                             'KLayout connectivity extraction is not complete parasitic extraction.',
                             'Physical/analog/digital closure and foundry sign-off require PDK-specific runsets and actual reviewed results.',
                             'Bundled engines need independent licence and distribution approval; matching hashes do not establish rights.'])
