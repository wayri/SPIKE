# SPDX-License-Identifier: Apache-2.0
"""Verify a source-pinned same-study three-level selected-volume DC refinement."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def require(test, message):
    if not test: raise ValueError(message)


def verify(case_paths, native_audit, study, *, replay=True):
    from python.spike_core.solvers.power_integrity.dc.dc_board_study import compile_model, canonical, MODEL
    from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc
    from scripts.benchmark_board_volume_scaling import METHODS
    snapshots = {}
    def snapshot(path):
        path = path.resolve(); require(path.is_relative_to(ROOT), 'Foreign refinement input')
        value = sha(path)
        require(path not in snapshots or snapshots[path] == value, 'Refinement input changed during replay')
        snapshots[path] = value
        return value
    snapshot(native_audit)
    audit = load(native_audit); item = audit['studies'][study]
    native = ROOT/audit['source_path']; native_sha = snapshot(native)
    require(audit['source_unchanged'] is True and native_sha == audit['source_sha256_before'] == audit['source_sha256_after']
            and audit['native_inventory']['authenticated'] is True, 'Native source changed or unauthenticated')
    source_model = ROOT/item['model']; require(snapshot(source_model) == item['model_sha256'], 'Native model detached')
    expected_model = load(source_model)
    require(len(case_paths) == 3, 'Three completed refinement levels required')
    levels = []; bindings = {str(native_audit.relative_to(ROOT)):sha(native_audit),
                             str(source_model.relative_to(ROOT)):sha(source_model)}
    for path in case_paths:
        snapshot(path)
        report = load(path); folder = path.parent; model_path = folder/'model.json'
        snapshot(model_path); model = load(model_path)
        require(report['status'] == 'discrete_fields_verified' and report['stage_complete'] is False
                and report['production_qualified'] is False and report['methods_unchanged'] is True
                and report['model_unchanged'] is True, 'Incomplete or drifting refinement attempt')
        require(snapshot(model_path) == report['model_sha256'], 'Case model changed')
        require(set(report['methods_before']) == set(METHODS) == set(report['methods_after']), 'Method coverage differs')
        for name, digest in report['methods_before'].items():
            require(snapshot(ROOT/name) == digest == report['methods_after'][name], 'Refinement method stale')
        normalized = dict(model, contract=MODEL, max_cells=expected_model['max_cells'], target_mm=expected_model['target_mm'])
        require(normalized == expected_model, 'Refinement changed physical geometry/material/electrodes')
        summary_path = folder.parent/'summary.json'; snapshot(summary_path); parent = load(summary_path)
        outcome = next(c for c in parent['cases'] if (ROOT/c['case']).resolve() == folder.resolve())
        process = outcome['process']
        require(outcome['report_sha256'] == snapshot(path) and outcome['model_sha256'] == snapshot(model_path), 'Supervised case binding differs')
        require(Path(parent['source_model']).resolve() == source_model.resolve()
                and parent['source_model_sha256_before'] == parent['source_model_sha256_after'] == snapshot(source_model),
                'Supervisor source-model binding differs')
        policy = parent['process_policy']; memory = report['native_memory']
        peak = memory.get('os_reported_peak_pagefile_usage_bytes') if isinstance(memory,dict) else None
        require(policy['memory_limit_mb'] == 4096 and 1 <= policy['timeout_s'] <= 600
                and policy['output_limit_bytes'] == 512*1024**2 and policy['blas_threads'] == 1
                and type(peak) is int and 0 < peak <= 4096*1024**2,
                'Missing or exceeded supervised resource evidence')
        require(process['return_code'] == 0 and process['memory_limit_enforced'] is True
                and parent['source_model_unchanged'] is True, 'Refinement process failed or unbounded')
        field_path = folder/'fields.json'; request_path = folder/'tetra-request.json'
        require(snapshot(field_path) == report['fields_sha256'] and snapshot(request_path) == report['tetra_request_sha256'], 'Raw field/request changed')
        result = load(field_path)
        require(result['source_request'] == load(request_path), 'Raw field detached from mesh')
        if replay:
            compiled = compile_model(model)
            require(compiled['request'] == result['source_request']
                    and canonical(compiled['coverage']) == report['coverage'], 'Source coverage/contact replay differs')
            validate_tetra_dc(result)
        require(report['coverage']['complete_selected_geometry'] is True
                and report['coverage']['no_intentional_geometry_omission'] is True, 'Incomplete selected conductor support')
        contacts = result['contacts']; source = [c for c in contacts if c['inward_current_a'] == 1.]
        sink = [c for c in contacts if c['inward_current_a'] == -1.]
        require(len(contacts) == 2 and len(source) == len(sink) == 1, 'Expected explicit one-amp transfer pair')
        density = result['current_density_observable']
        levels.append({'target_mm':model['target_mm'],'cells':len(result['cells']),
            'resistance_ohm':source[0]['mean_potential_v']-sink[0]['mean_potential_v'],
            'heat_w':result['joule_heat_w'],'p95_a_m2':density['p95']['upper_a_m2'],
            'p99_a_m2':density['p99']['upper_a_m2'],'physical_volume_m3':density['physical_volume_m3']})
        for artifact in (path,model_path,field_path,request_path,folder.parent/'summary.json'):
            bindings[artifact.relative_to(ROOT).as_posix()] = snapshot(artifact)
    require(all(b['target_mm'] == a['target_mm']/2 and b['cells'] > a['cells'] for a,b in zip(levels,levels[1:])), 'No factor-two actual mesh refinement')
    require(all(abs(l['physical_volume_m3']/levels[0]['physical_volume_m3']-1) <= 1e-10 for l in levels), 'Refinement changed physical volume')
    change = lambda a,b: (abs(b/a-1) if a else (0. if b == 0 else 1.))
    successive = [{key:change(a[key],b[key]) for key in
                  ('resistance_ohm','heat_w','p95_a_m2','p99_a_m2')} for a,b in zip(levels,levels[1:])]
    changes = successive[-1]
    limits = {'resistance_ohm':.01,'heat_w':.01,'p95_a_m2':.02,'p99_a_m2':.02}
    accepted = all(step[key] <= limits[key] for step in successive for key in limits)
    require(all(sha(path) == digest for path,digest in snapshots.items()), 'Input or method changed during refinement replay')
    return {'contract':'spike/selected-board-volume-refinement/v1','study':study,
        'status':('inspection_only' if not replay else 'passed_refinement_stability' if accepted else 'needs_further_refinement'),
        'stage_complete':False,'production_qualified':False,'full_board_pisi_ready':False,
        'source_sha256':native_sha,'levels':levels,'last_step_relative_changes':changes,
        'successive_relative_changes':successive,
        'frozen_relative_limits':limits,'retained_fields_replayed':replay,'artifacts':bindings,
        'native_provenance':'Trusted executed native-source audit, pinned current source hash; no new native parser solve in this verifier.',
        'scope':'Explicit full-pad same-net transfer only; original point study, full rail/board and AC/SI gates remain open.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',nargs=3,type=Path,required=True)
    parser.add_argument('--native-audit',type=Path,required=True)
    parser.add_argument('--study',required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); output=args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT), 'Fresh repository output required')
    paths=[p.resolve() for p in args.cases]; audit=args.native_audit.resolve()
    require(all(p.is_relative_to(ROOT) for p in [*paths,audit]), 'Foreign refinement artifacts')
    result=verify(paths,audit,args.study)
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','last_step_relative_changes','stage_complete')}))


if __name__=='__main__': main()
