# SPDX-License-Identifier: Apache-2.0
"""Retain the actual coupled run and matching benchmark CAD in a native project."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from python.spike_core.service_project import import_design
from python.spike_core.project_package import write_spike_package, read_project, _source_member_name
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.assembly_frames import IDENTITY
from examples.promo_showcase.colocate_kicad_sources import colocate_tree

OUT = ROOT / 'output/promo-propulsion-pod-20261023'
COUPLED = OUT / 'coupled'
SOURCE = ROOT / 'output/promo-esc-20261023/source/bldc-hardware-f1c65014d0caab5d99d888fc3025377861ac6ae2/design/BLDC_4.kicad_pcb'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def call(method, **params):
    response = handle_project_request(method, params, request_id='coupled-pod', application_version='source')
    if not response or not response.get('ok'):
        raise RuntimeError(response)
    return response['result']

def main():
    scratch = COUPLED / '.tmp'
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch.resolve())
    freecad = Path('C:/Users/yawar/AppData/Local/Programs/FreeCAD 1.1/bin')
    if freecad.is_dir():
        os.environ['PATH'] = str(freecad)+os.pathsep+os.environ.get('PATH', '')
    result_path = COUPLED / 'actual-coupled-result-views-fixed.json'
    result = json.loads(result_path.read_text())
    execution = json.loads((COUPLED / 'python-workspace-execution.json').read_text())
    assert result['status'] == 'completed' and execution['status'] == 'completed'
    binding = json.loads((OUT / 'coupled_geometry/benchmark-geometry-binding.json').read_text())['parameters']
    assert binding['field_motor'] == result['request']['field_motor']
    assert binding['propeller'] == result['request']['propeller']
    design = import_design(str(SOURCE), with_report=True)['design']
    design['source']['artifact_path'] = 'package:'+_source_member_name(SOURCE.name, sha(SOURCE))
    project = COUPLED / 'restrained-propulsion-pod-coupled.spike'
    manifest = write_spike_package(project, {'project': {'name': 'Working coupled propulsion benchmark - C controller / FEM / BEM'},
        'design_ir': design}, source_artifacts={SOURCE.name: SOURCE.read_bytes()}, application_version='source')
    files = [('stand', 'Original high-axis fixed stand', 'benchmark-stand.step'),
             ('motor', 'Synthetic planar benchmark motor regions', 'benchmark-motor-envelope.step'),
             ('shaft', 'Original shaft - common motor/propeller axis', 'benchmark-shaft.step'),
             ('propeller', 'BEM blade dimensions - illustrative flat-plate loft', 'benchmark-propeller-flat-plate-visual.step')]
    exchange = COUPLED / 'coupled-benchmark.spikeassembly'
    with zipfile.ZipFile(exchange, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('assembly.json', json.dumps({'contract': 'spike/assembly-exchange/v1', 'units': 'mm',
            'name': 'Coupled benchmark geometry', 'occurrences': [{'id': key, 'kind': 'part', 'name': name,
                'part_type': 'other', 'asset': file, 'transform': list(IDENTITY)} for key, name, file in files]}))
        for _, _, file in files:
            archive.write(OUT / 'coupled_geometry' / file, file)
    call('import_into_assembly_project', project_path=str(project), source_paths=[str(exchange)],
         expected_manifest_payload_sha256=manifest['manifest_payload_sha256'])
    opened = read_project(project, include_members=True)
    payload = dict(opened.payload)
    assembly = payload['assembly_ir']
    transform = list(IDENTITY)
    transform[3], transform[7], transform[11] = -132.75, -120.5, 12.
    assembly['boards'][0]['frame']['transform'] = transform
    assembly['boards'][0]['name'] = 'VESC source reference board - not a calibrated hardware model'
    AssemblyIRV1.from_dict(assembly)
    result_member = 'reports/artifacts/coupled-result.json'
    view_member = 'reports/artifacts/coupled-data-views.json'
    metadata = {'contract': 'spike/propulsion-pod-saved-study/v1', 'state': 'completed_reference_benchmark',
        'request': result['request'], 'request_sha256': result['request_sha256'],
        'result_member': result_member, 'result_sha256': sha(result_path),
        'data_views_member': view_member, 'source_board_sha256': sha(SOURCE),
        'benchmark_machine_origin_m': [0., 0., .2], 'shaft_axis': '+x', 'propeller_disk_x_m': .085,
        'board_role': 'Exact KiCad source/context; no inferred VESC winding/controller/terminal identity',
        'physical_board_motor_terminal_bindings': [],
        'scope': result['limitations'], 'controller_ticks': result['controller_ticks'],
        'accepted_steps': result['accepted_steps'], 'field_frames': len(result['frames'])}
    payload.setdefault('extensions', {})['spike.propulsion-pod-coupled-study'] = metadata
    write_spike_package(project, payload, preserved_members=opened.members,
        report_artifacts={'coupled-result.json': result_path.read_bytes(),
                          'coupled-data-views.json': json.dumps(execution['views'], allow_nan=False).encode()},
        application_version='source')
    tessellations = []
    for part in read_project(project).payload['assembly_ir']['parts']:
        current = read_project(project)
        tessellations.append(call('tessellate_mcad_part_in_project', project_path=str(project),
            expected_manifest_payload_sha256=current.manifest['manifest_payload_sha256'], part_id=part['id']))
    final = read_project(project, include_members=True)
    assert final.members[result_member] == result_path.read_bytes()
    assert json.loads(final.members[view_member]) == execution['views']
    assert final.payload['extensions']['spike.propulsion-pod-coupled-study'] == metadata
    assert len(final.payload['assembly_ir']['boards']) == 1 and len(final.payload['assembly_ir']['parts']) == 4
    assert any(data == SOURCE.read_bytes() for name, data in final.members.items() if name.endswith('.kicad_pcb'))
    colocate_tree(COUPLED)
    checks = {'status': 'passed', 'native_project': str(project), 'native_readback': 'exact result and all data views',
        'source_board_bytes_exact': True, 'boards': 1, 'STEP_parts': 4, 'tessellations_succeeded': len(tessellations),
        'accepted_coupled_steps': result['accepted_steps'], 'actual_compiled_controller_ticks': result['controller_ticks'],
        'computed_field_frames': len(result['frames']), 'saved_views': len(execution['views']),
        'result_sha256': sha(result_path), 'project_sha256': sha(project),
        'interactive_desktop_visual_acceptance': False, 'VESC_hardware_qualification': False}
    (COUPLED / 'native-project-verification.json').write_text(json.dumps(checks, indent=2)+'\n')
    print(json.dumps(checks))

if __name__ == '__main__':
    main()
