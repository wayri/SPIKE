# SPDX-License-Identifier: Apache-2.0
"""Build a source-bound restrained-pod scene, without inventing coupled results."""
from pathlib import Path
import hashlib, json, os, sys, tempfile, zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from python.spike_core.service_project import import_design
from python.spike_core.project_package import write_spike_package, read_project, _source_member_name
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.assembly_frames import IDENTITY
from examples.promo_showcase.colocate_kicad_sources import colocate_tree

OUT = ROOT / 'output/promo-propulsion-pod-20261023'
ASSEMBLY = OUT / 'assembly'
SOURCE = ROOT / 'output/promo-esc-20261023/source/bldc-hardware-f1c65014d0caab5d99d888fc3025377861ac6ae2/design/BLDC_4.kicad_pcb'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def call(method, **params):
    response = handle_project_request(method, params, request_id='propulsion-pod', application_version='source')
    if not response or not response.get('ok'):
        raise RuntimeError(response)
    return response['result']

def main():
    ASSEMBLY.mkdir(parents=True, exist_ok=True)
    (OUT / '.tmp').mkdir(exist_ok=True)
    tempfile.tempdir = str(OUT / '.tmp')
    freecad = Path('C:/Users/yawar/AppData/Local/Programs/FreeCAD 1.1/bin')
    if freecad.is_dir():
        os.environ['PATH'] = str(freecad) + os.pathsep + os.environ.get('PATH', '')
    design = import_design(str(SOURCE), with_report=True)['design']
    design['source']['artifact_path'] = 'package:' + _source_member_name(SOURCE.name, sha(SOURCE))
    project = ASSEMBLY / 'restrained-propulsion-pod.spike'
    manifest = write_spike_package(project, {'project': {'name': 'Restrained propulsion pod - VESC and original fixture'},
        'design_ir': design}, source_artifacts={SOURCE.name: SOURCE.read_bytes()}, application_version='source')
    assets = {'stand.step': OUT / 'thermal_geometry/original-pod-stand.step',
              'motor-envelope.step': OUT / 'thermal_geometry/original-motor-case-envelope.step'}
    exchange = ASSEMBLY / 'original-fixture.spikeassembly'
    occurrences = [{'id': key, 'kind': 'part', 'name': name, 'part_type': 'other',
                    'asset': asset, 'transform': list(IDENTITY)}
        for key, name, asset in [('stand', 'Original stationary stand - no strength qualification', 'stand.step'),
                                ('motor-envelope', 'Nominal motor envelope - no winding or rotor model', 'motor-envelope.step')]]
    with zipfile.ZipFile(exchange, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('assembly.json', json.dumps({'contract': 'spike/assembly-exchange/v1', 'units': 'mm',
            'name': 'Original restrained fixture', 'occurrences': occurrences}))
        for name, path in assets.items():
            archive.write(path, name)
    call('import_into_assembly_project', project_path=str(project), source_paths=[str(exchange)],
         expected_manifest_payload_sha256=manifest['manifest_payload_sha256'])
    opened = read_project(project, include_members=True)
    payload = dict(opened.payload)
    assembly = payload['assembly_ir']
    assert len(assembly['boards']) == 1 and len(assembly['parts']) == 2
    board = assembly['boards'][0]
    transform = list(IDENTITY)
    # Source outline x78.5..117/y80..145 -> x-54.25..-15.75/y-40.5..24.5.
    # Board plane z12; fixture pedestal x/y +/-10. This is a placement only.
    transform[3], transform[7], transform[11] = -132.75, -120.5, 12.0
    board['frame']['transform'] = transform
    board['name'] = 'Pinned VESC hardware - original copper and schematic'
    AssemblyIRV1.from_dict(assembly)
    nets = {n['id']: n['name'] for n in design['nets']}
    pins = {p['id']: p for p in design['pins']}
    components = {c['reference']: c for c in design['components']}
    terminal_inventory = []
    for reference in ('P4', 'P5', 'P6', 'P7', 'P9', 'P1'):
        component = components[reference]
        for pin_id in component['pin_ids']:
            pin = pins[pin_id]
            terminal_inventory.append({'board_occurrence_id': board['id'], 'component_id': component['id'],
                'reference': reference, 'value': component['value'], 'pin_id': pin_id, 'pin_number': pin['number'],
                'pad_ids': pin['pad_ids'], 'net_id': pin['net_id'], 'net_name': nets.get(pin['net_id'], '')})
    integration = {'contract': 'spike/promo-propulsion-pod-integration-draft/v1',
        'executable_solver_request': False, 'source_board_sha256': sha(SOURCE),
        'terminal_inventory': terminal_inventory, 'active_motor_terminal_bindings': [],
        'controller_firmware': None, 'motor_winding_geometry': None, 'motor_material_dataset': None,
        'propeller_geometry_and_reference_data': None,
        'required_loop': ['controller', 'inverter_phase_current', 'motor_FEM_torque', 'speed_and_load',
                          'backEMF_and_sensing', 'controller'],
        'unmet_gates': ['physical motor and propeller source data', 'controller/inverter adapter',
                       'current-driven moving motor FEM with reciprocal backEMF',
                       'conservative thermal and rotating-flow coupling', 'independent reference and refinement'],
        'scene_scope': 'PCB plus nominal fixture geometry; no electrical or thermal link to envelope is inferred',
        'fixture_strength_qualified': False, 'whole_drone_flight_executed': False}
    payload.setdefault('extensions', {})['spike.promo-propulsion-pod'] = integration
    write_spike_package(project, payload, preserved_members=opened.members, application_version='source')
    save(ASSEMBLY / 'integration-draft.json', integration)
    visual = []
    for part in read_project(project).payload['assembly_ir']['parts']:
        current = read_project(project)
        response = handle_project_request('tessellate_mcad_part_in_project', {'project_path': str(project),
            'expected_manifest_payload_sha256': current.manifest['manifest_payload_sha256'], 'part_id': part['id']},
            request_id='pod-visual', application_version='source')
        visual.append({'part': part['name'], 'response': response})
    save(ASSEMBLY / 'tessellation.json', visual)
    final = read_project(project, include_members=True)
    assert final.payload['extensions']['spike.promo-propulsion-pod'] == integration
    assert list(final.payload['assembly_ir']['boards'][0]['frame']['transform']) == transform
    assert any(data == SOURCE.read_bytes() for name, data in final.members.items() if name.endswith('.kicad_pcb'))
    source_inventory = colocate_tree(ASSEMBLY)
    save(ASSEMBLY / 'verification.json', {'status': 'passed', 'native_readback': True,
        'board_occurrences': 1, 'part_occurrences': 2, 'source_board_bytes_exact': True,
        'terminal_inventory_entries': len(terminal_inventory), 'active_motor_bindings': 0,
        'tessellations_succeeded': sum(bool(v['response'] and v['response'].get('ok')) for v in visual),
        'project_sha256': sha(project), 'GUI_visual_acceptance_executed': False,
        'coupled_propulsion_executed': False, 'source_inventory_present': bool(source_inventory)})
    print(project)

if __name__ == '__main__':
    main()
