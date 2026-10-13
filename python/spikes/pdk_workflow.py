# SPDX-License-Identifier: Apache-2.0
"""Bounded PDK model preparation and explicit compiled-backend orchestration."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shlex

from python.spike_core.spice_netlist_safety import validate_netlist

CONTRACT='spikes/pdk-run/v1'
MAX_BYTES=16*1024*1024


def _digest(data):return hashlib.sha256(data).hexdigest()


def _tokens(line):
    try:values=shlex.split(line,posix=False)
    except ValueError as exc:raise ValueError('Malformed PDK include/library syntax') from exc
    return [value[1:-1] if len(value)>1 and value[0]==value[-1] and value[0] in '\"\'' else value for value in values]


def _library(root,entry,corner):
    """Resolve only the selected textual library section; never load code."""
    root=Path(root).resolve(strict=True)
    if not root.is_dir():raise ValueError('PDK root must be a directory')
    files={};active=set();total=0;expansions=0

    def expand(path,section=None):
        nonlocal total,expansions
        path=path.resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('PDK dependency escapes root or is not a file')
        key=(path,section.lower() if section else None)
        if any(item[0]==path for item in active):raise ValueError('Cyclic or recursive same-file PDK library dependency')
        expansions+=1
        if expansions>256 or len(active)>32:raise ValueError('PDK dependency expansion limit exceeded')
        if path.stat().st_size>4*1024*1024:raise ValueError('PDK file exceeds 4 MiB')
        with path.open('rb') as stream:payload=stream.read(4*1024*1024+1)
        if len(payload)>4*1024*1024:raise ValueError('PDK file exceeds 4 MiB')
        total+=len(payload)
        if total>MAX_BYTES:raise ValueError('PDK expansion exceeds 16 MiB')
        files[path.relative_to(root).as_posix()]=_digest(payload)
        text=payload.decode('utf-8');active.add(key)
        result=[];block=None;found=0;result_bytes=0
        def append(items):
            nonlocal result_bytes
            result_bytes+=sum(len(item.encode('utf-8'))+1 for item in items)
            if result_bytes>MAX_BYTES:raise ValueError('Expanded PDK text exceeds limit')
            result.extend(items)
        try:
            for number,line in enumerate(text.splitlines(),1):
                stripped=line.strip()
                if not stripped or stripped.startswith('*'):
                    if block is None or (section is not None and block.lower()==section.lower()):append([line])
                    continue
                token=stripped.split(maxsplit=1)[0].lower()
                if token=='.lib':
                    args=_tokens(stripped)
                    if len(args)==2:
                        if block is not None:raise ValueError('Nested PDK .lib sections are unsupported')
                        block=args[1]
                        if section is not None and block.lower()==section.lower():found+=1
                        continue
                    if len(args)!=3:raise ValueError('PDK .lib requires section or file and section')
                if token=='.endl':
                    args=_tokens(stripped)
                    if block is None or len(args)>2 or (len(args)==2 and args[1].lower()!=block.lower()):
                        raise ValueError('Unmatched PDK .endl')
                    block=None;continue
                selected=block is None or (section is not None and block.lower()==section.lower())
                # Includes outside sections are global declarations; other
                # corners remain unexecuted and unexpanded.
                if not selected:continue
                if token in {'.include','.inc','.lib'}:
                    args=_tokens(stripped)
                    if token!='.lib' and len(args)!=2:raise ValueError('PDK include requires one literal path')
                    dependency=args[1]
                    if any(c in dependency for c in '$\r\n'):raise ValueError('Dynamic PDK include paths are unsupported')
                    target=Path(dependency)
                    if not target.is_absolute():target=path.parent/target
                    append(expand(target,args[2] if token=='.lib' else None))
                elif token in {'pre_osdi','.pre_osdi','.hdl','.verilog','.load','codemodel','osdi'}:
                    raise ValueError('PDK requires a compiled model loader not supported by this self-contained route')
                elif token=='.end':raise ValueError('PDK model dependency contains top-level .end')
                else:append([line])
            if block is not None:raise ValueError('Unterminated PDK .lib section')
            if section is not None and found!=1:raise ValueError('Requested PDK corner section is missing or ambiguous')
            return result
        finally:active.remove(key)

    lines=expand(Path(entry),corner)
    return '\n'.join(lines),[dict(path=path,sha256=sha) for path,sha in sorted(files.items())]


def prepare(config):
    """Prepare an inert corner-specific deck; backend selection is compulsory."""
    from .pdk_inventory import inspect
    if not isinstance(config,dict) or set(config)-{'pdk_id','root','entry','corner','temperature_c','backend','circuit'}:
        raise ValueError('Unknown PDK run configuration fields')
    if not isinstance(config.get('root'),str) or not config['root'].strip() or not isinstance(config.get('pdk_id'),str):
        raise ValueError('PDK config requires string pdk_id and local root')
    if config.get('entry') is not None and not isinstance(config['entry'],str):raise ValueError('entry must be a relative path string')
    if config.get('backend')!='ngspice':raise ValueError('PDK workflow currently requires explicit backend=ngspice; no native fallback')
    corner=config.get('corner')
    if not isinstance(corner,str) or not corner or len(corner)>64 or any(not(c.isascii() and (c.isalnum() or c=='_')) for c in corner):
        raise ValueError('PDK corner must be a bounded section identifier')
    temperature=config.get('temperature_c',27.)
    if type(temperature) not in (int,float) or not math.isfinite(temperature) or not -273.15<temperature<=1000:
        raise ValueError('temperature_c must be finite and above absolute zero, at most 1000 C')
    circuit=config.get('circuit')
    if not isinstance(circuit,str) or not circuit.strip() or len(circuit.encode())>1024*1024:raise ValueError('Circuit must be bounded SPICE text')
    # Reject additional corner selections and file/command access in user text.
    validate_netlist(circuit)
    for line in circuit.splitlines():
        parts=line.strip().split()
        if parts and parts[0].lower() in {'.end','.temp','pre_osdi','.pre_osdi','.hdl','.verilog'}:
            raise ValueError('Circuit must not override end, temperature or compiled-model setup')
    inventory=inspect(config.get('pdk_id'),config.get('root'),entry=config.get('entry'))
    root=Path(inventory['root']).resolve(strict=True)
    # Entry is root-relative in the inventory contract; resolution is checked
    # again by the selected-section reader before any model text is used.
    entry=root/inventory['entry']
    model_text,dependencies=_library(root,entry,corner)
    deck=validate_netlist('* SPIKES explicit PDK circuit study\n'+model_text+f'\n.temp {temperature:.17g}\n'+circuit+'\n.end\n')
    resolved=dict(pdk_id=config['pdk_id'],root=str(root),entry=inventory['entry'],corner=corner,
                  temperature_c=float(temperature),backend='ngspice',circuit_sha256=_digest(circuit.encode()))
    fingerprint=_digest(json.dumps(dict(config=resolved,dependencies=dependencies,deck_sha256=_digest(deck.encode())),sort_keys=True,separators=(',',':')).encode())
    return dict(contract=CONTRACT,status='prepared',model_status='unqualified',backend='ngspice',backend_substitution=False,
                config=resolved,dependencies=dependencies,approval_sha256=fingerprint,source=deck,
                inventory_issues=inventory['issues'],license_files=inventory['licenses'],
                limitations=['Circuit-level compact-model simulation only; no TCAD/process simulation, layout, DRC/LVS or extraction.',
                             'Geometry units, valid operating ranges and device names remain PDK-specific and user supplied.',
                             'Preparation is not model execution, foundry qualification or endorsement.',
                             'Compiled-model loading and automatic PDK download/installation are not supplied.'])


def run(prepared,*,approval_sha256):
    """Run an explicitly hash-approved prepared deck using existing ngspice."""
    if not isinstance(prepared,dict) or prepared.get('contract')!=CONTRACT or approval_sha256!=prepared.get('approval_sha256'):
        raise ValueError('Explicit approval of this exact PDK run digest is required')
    if prepared.get('backend')!='ngspice':raise ValueError('Unsupported PDK backend')
    if not isinstance(prepared.get('source'),str) or validate_netlist(prepared['source'])!=prepared['source']:
        raise ValueError('Prepared PDK source must be a canonical safe self-contained deck')
    for line in prepared['source'].splitlines():
        tokens=line.strip().split()
        if tokens and tokens[0].lower() in {'pre_osdi','.pre_osdi','.hdl','.verilog','.load','codemodel','osdi'}:
            raise ValueError('Compiled model loading is unsupported in this PDK route')
    fingerprint=_digest(json.dumps(dict(config=prepared['config'],dependencies=prepared['dependencies'],deck_sha256=_digest(prepared['source'].encode())),sort_keys=True,separators=(',',':')).encode())
    if fingerprint!=approval_sha256:raise ValueError('Prepared PDK run was modified after approval')
    from python.spike_core.contracts import AnalysisSpec,DesignIR
    from python.spike_core.ngspice_plugin import NgspicePlugin
    result=NgspicePlugin().run(DesignIR(design_id='pdk-circuit',name='Explicit PDK simulation'),
        AnalysisSpec(analysis_id='pdk-circuit',mode='spice',solver_id='spike.ngspice',
                     options={'spice_netlist':prepared['source'],'timeout_seconds':120})).to_dict()
    result.setdefault('provenance',{}).update(pdk_configuration=prepared['config'],pdk_dependencies=prepared['dependencies'],
                                            pdk_approval_sha256=approval_sha256,backend_substitution=False,pdk_qualification=False)
    return result
