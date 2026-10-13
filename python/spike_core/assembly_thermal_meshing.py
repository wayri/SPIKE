# SPDX-License-Identifier: Apache-2.0
"""Retained project geometry to explicitly assigned assembly thermal volumes.

This orchestration consumes canonical source geometry, never renderer buffers.
Board effective-layer admission is an explicit model reduction. Exact STEP
solids and planar board volumes are meshed in the bounded optional OCC worker.
No contacts, heat sources, boundary conditions, or materials are inferred.
"""
import copy
import hashlib
from pathlib import Path

from .assembly_frames import IDENTITY, validate_rigid_transform
from .assembly_field_handoff import _assembly, _materials, digest, prepare_assembly_field_handoff
from .assembly_thermal_cad import MAX_STEP_BYTES
from .gmsh_occ_mesher import validate_request
from .multiboard_identity import canonical_json_digest


def _artifact(reader, uri, expected):
    digest(expected)
    if not isinstance(uri, str) or not uri.startswith('package:'):
        raise ValueError('SOURCE_MISSING: source must be retained in the project package')
    value = reader(uri)
    if not isinstance(value, bytes) or not 0 < len(value) <= MAX_STEP_BYTES:
        raise ValueError('SOURCE_BUDGET: retained artifact must contain 1..64 MiB of bytes')
    if hashlib.sha256(value).hexdigest() != expected:
        raise ValueError('SOURCE_STALE: retained source digest mismatch')
    return value


def _board_model(design, assignment):
    from .mcad_export_design import _rings_from_drawings
    from .pcb_volume_compiler import compile_pcb_volume_model
    if design.get('bends') or design.get('metadata', {}).get('technology', 'rigid') != 'rigid':
        raise ValueError('BOARD_FORMED: formed/flex geometry needs explicit placed solid volumes')
    if list(design.get('frame', {}).get('transform', IDENTITY)) != list(IDENTITY):
        raise ValueError('BOARD_FRAME: source design must use the board-local identity datum')
    metadata = design.get('metadata', {})
    if assignment.get('representation') != 'layer_homogenized':
        raise ValueError('BOARD_REPRESENTATION: explicitly review effective layer materials before meshing')
    if set(assignment) != {'representation', 'layer_materials'}:
        raise ValueError('BOARD_ASSIGNMENT: expected representation and layer_materials')
    rings = metadata.get('board_outline_rings') or _rings_from_drawings(metadata.get('board_outline_drawings', []))
    outer, holes = [], []
    for ring in rings:
        segments = ring.get('segments', [])
        if not segments or any(s.get('kind') != 'line' for s in segments):
            raise ValueError('BOARD_OUTLINE: only retained straight closed outline segments are supported')
        points = [ring['start_mm'], *[s['end_mm'] for s in segments]]
        if points[-1] != points[0]:
            raise ValueError('BOARD_OUTLINE: retained polygon is not exactly closed')
        if ring.get('role') == 'outer':
            outer.append(points[:-1])
        elif ring.get('role') == 'cutout':
            holes.append(points[:-1])
        else:
            raise ValueError('BOARD_OUTLINE: unknown ring ownership')
    if len(outer) != 1:
        raise ValueError('BOARD_OUTLINE: one retained outer outline required; bounds are insufficient')
    layers = [layer for layer in design.get('layers', []) if
              layer.get('layer_type') in ('copper', 'dielectric', 'soldermask', 'solder_mask', 'paste') or
              layer.get('extensions', {}).get('spike.v1.stackup')]
    if not layers:
        raise ValueError('BOARD_STACK: retained physical layer stack is missing')
    layers.sort(key=lambda layer: layer['order'])
    assignments = assignment['layer_materials']
    if not isinstance(assignments, dict) or set(assignments) != {layer['id'] for layer in layers}:
        raise ValueError('BOARD_MATERIAL: assign one reviewed effective material to every physical stack layer')
    rows = []
    for layer in layers:
        z, thickness = layer.get('z_mm'), layer.get('thickness_mm')
        if type(z) not in (int, float) or type(thickness) not in (int, float) or thickness <= 0:
            raise ValueError('BOARD_STACK: every physical layer requires finite positive thickness and elevation')
        rows.append({'id': layer['id'], 'z_min_mm': z, 'z_max_mm': z+thickness,
                     'background_material_id': assignments[layer['id']]})
    model = {'contract': 'spike/pcb-volume-model/v1',
             'board': {'id': design['design_id'], 'outer_mm': outer[0], 'holes_mm': holes},
             'layers': rows, 'copper': [], 'vias': [],
             'copper_material_id': '__unresolved_copper__', 'drill_material_id': '__unresolved_drill__'}
    compiled = compile_pcb_volume_model(model)
    return compiled, {'id': 'stack:'+design['design_id'], 'source_sha256': canonical_json_digest(layers)}


def prepare_assembly_thermal_mesh(payload, assignments, mesh_options, *, artifact_reader):
    """Inventory and validate project-owned volumes without executing a mesher.

    ``artifact_reader(package_uri)`` must read a manifest-verified retained
    member. The caller owns project freshness and permission checks. Physical
    values come exclusively from assignments.materials; assignments.boards is
    keyed by design identity and assignments.parts by occurrence identity.
    """
    if not isinstance(assignments, dict) or set(assignments) not in ({'materials', 'boards', 'parts'}, {'materials', 'boards', 'parts', 'encapsulation'}):
        raise ValueError('THERMAL_ASSIGNMENTS: expected materials, boards, parts')
    # Admit resource controls even when all occurrences use imported STEP.
    validate_request({'contract': 'spike/gmsh-occ-mesh/v1', 'mesh': mesh_options, 'solids': [
        {'id': 'resource-check', 'material_id': 'resource-check', 'priority': 0,
         'shape': {'kind': 'tube', 'center_mm': [0, 0], 'outer_radius_mm': 1,
                   'inner_radius_mm': 0, 'z_min_mm': 0, 'z_max_mm': 1}}]})
    materials = _materials(assignments['materials'], 'thermal')
    assembly = _assembly(payload['assembly_ir'])
    if not isinstance(assignments['boards'], dict) or not isinstance(assignments['parts'], dict):
        raise ValueError('THERMAL_ASSIGNMENTS: board and part assignments must be maps')
    designs = {d['design_id']: d for d in (payload.get('assembly_designs') or {}).get('designs', [])}
    active = payload.get('design_ir')
    if active:
        designs.setdefault(active['design_id'], active)
    models = {m['id']: m for m in (payload.get('models') or {}).get('models', [])}
    jobs, blockers = [], []
    occurrences = [*assembly.boards, *assembly.parts]
    for occurrence in occurrences:
        if getattr(occurrence, 'part_type', '') == 'subassembly' and not occurrence.model_id:
            continue
        try:
            if hasattr(occurrence, 'design_id'):
                reference = occurrence.design_id
                design = designs.get(reference)
                if not design:
                    raise ValueError('BOARD_SOURCE: retained design is missing')
                source = design['source']
                _artifact(artifact_reader, source['artifact_path'], source['source_digest'])
                compiled, stack = _board_model(design, assignments['boards'].get(reference, {}))
                job = {'contract': 'spike/gmsh-occ-mesh/v1', 'solids': compiled['solids'], 'mesh': copy.deepcopy(mesh_options)}
                validate_request(job)
                mids = {s['material_id'] for s in job['solids']}
                if not mids <= set(materials):
                    raise ValueError('BOARD_MATERIAL: effective stack material has no physical property assignment')
                entry = {'occurrence_id': occurrence.id, 'reference_id': reference,
                         'source_sha256': source['source_digest'], 'stack_binding': stack,
                         'job': job, 'material_map': {m:m for m in mids},
                         'object_metadata': compiled['object_metadata'],
                         'representation': 'explicit_effective_layers',
                         'approximations': ['Patterned copper and drill/via details are homogenized into reviewed layer properties.']}
            else:
                from .assembly_thermal_components import verify_promoted_component
                verify_promoted_component(payload, occurrence)
                reference = occurrence.model_id
                model = models.get(reference)
                if not model or model.get('model_type') != 'step':
                    raise ValueError('PART_SOLID: retain an exact STEP solid; decorative GLB/render meshes are unsupported')
                mid = assignments['parts'].get(occurrence.id)
                if mid not in materials:
                    raise ValueError('PART_MATERIAL: assign a reviewed physical material to this occurrence')
                _artifact(artifact_reader, model['uri'], model['digest'])
                transform = model.get('transform') or list(IDENTITY)
                validate_rigid_transform(transform, 'Retained model')
                entry = {'occurrence_id': occurrence.id, 'reference_id': reference,
                         'source_sha256': model['digest'], 'source_uri': model['uri'],
                         'model_transform': list(transform), 'material_map': {mid:mid},
                         'representation': 'exact_step_solid', 'approximations': []}
            jobs.append(entry)
        except (ValueError, KeyError, TypeError) as error:
            message = str(error)
            blockers.append({'occurrence_id': occurrence.id, 'code': message.split(':')[0], 'message': message})
    if not jobs and not blockers:
        blockers.append({'occurrence_id': '', 'code': 'EMPTY_ASSEMBLY', 'message': 'No physical occurrences to mesh.'})
    from .assembly_thermal_encapsulation import validate_encapsulation, augment_plan
    encapsulation = validate_encapsulation(assignments.get('encapsulation', []), materials,
                                         [entry['occurrence_id'] for entry in jobs], mesh_options)
    used_materials = {r['material_id'] for r in encapsulation} | {mid for entry in jobs for mid in entry['material_map'].values()}
    if len(jobs) > 1 and sum(len(entry['job']['solids']) if 'job' in entry else 1 for entry in jobs) > 64:
        blockers.append({'occurrence_id': '', 'code': 'ASSEMBLY_JOINT_BUDGET',
                         'message': 'Joint conformal assembly meshing supports at most 64 source solids; simplify the reviewed geometry.'})
    if not blockers and used_materials != set(materials):
        blockers.append({'occurrence_id': '', 'code': 'UNUSED_MATERIAL',
                         'message': 'Remove unused physical material records before generating the assembly handoff.'})
    plan = {'contract': 'spike/assembly-thermal-mesh-plan/v1', 'status': 'blocked' if blockers else 'ready',
            'assembly': copy.deepcopy(payload['assembly_ir']), 'materials': copy.deepcopy(assignments['materials']),
            'mesh_options': copy.deepcopy(mesh_options), 'jobs': jobs, 'blockers': blockers,
            'production_qualified': False}
    return augment_plan(plan, encapsulation) if encapsulation else plan


def run_assembly_thermal_mesh(payload, assignments, mesh_options, output_dir, *, artifact_reader,
                              timeout_s=180, memory_limit_mb=2048):
    """Generate complete local tetra volumes and admit the existing field handoff."""
    from .gmsh_occ_runtime import run_occ_case, verify_installation
    plan = prepare_assembly_thermal_mesh(payload, assignments, mesh_options, artifact_reader=artifact_reader)
    if plan['status'] != 'ready':
        return plan
    try:
        runtime = verify_installation()
    except ValueError as error:
        return {**plan, 'status': 'blocked', 'blockers': [{'occurrence_id': '', 'code': 'GMSH_RUNTIME',
                'message': str(error)+'; configure the supported separately installed OCC runtime.'}]}
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    if len(plan['jobs']) > 1:
        from .assembly_thermal_joint_mesh import run_joint_assembly_mesh
        return run_joint_assembly_mesh(plan, root, runtime, artifact_reader=artifact_reader,
                                       timeout_s=timeout_s, memory_limit_mb=memory_limit_mb)
    bodies, evidence, cache = [], [], {}
    total_cells = total_vertices = 0
    for index, entry in enumerate(plan['jobs']):
        cache_key = canonical_json_digest({k:v for k,v in entry.items() if k != 'occurrence_id'})
        if cache_key not in cache:
            if 'job' in entry:
                job = entry['job']
            else:
                path = root / (str(index)+'.step')
                path.write_bytes(_artifact(artifact_reader, entry['source_uri'], entry['source_sha256']))
                mid = next(iter(entry['material_map']))
                job = {'contract': 'spike/gmsh-occ-step/v1', 'mesh': copy.deepcopy(mesh_options), 'solids': [
                    {'id': entry['reference_id'], 'material_id': mid, 'priority': 0, 'shape': {
                        'kind': 'step_solid', 'path': str(path), 'sha256': entry['source_sha256'],
                        'transform': entry['model_transform']}}]}
            case = root/('case-'+str(index))
            try:
                generated = run_occ_case(job, case, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb)
            except RuntimeError as error:
                log = case/'worker.log'
                detail = str(error)
                if log.is_file() and not log.is_symlink():
                    with log.open('rb') as stream:
                        detail = stream.read(8192).decode('utf-8', errors='replace')
                return {**plan, 'status': 'blocked', 'blockers': [{'occurrence_id': entry['occurrence_id'],
                        'code': 'CAD_MESH_FAILED', 'message': detail}], 'evidence': evidence}
            if 'object_metadata' in entry:
                generated['mesh']['object_map'] = copy.deepcopy(entry['object_metadata'])
            cache[cache_key] = generated
        generated = cache[cache_key]
        total_cells += len(generated['mesh']['cells'])
        total_vertices += len(generated['mesh']['vertices'])
        if total_cells > mesh_options['max_cells'] or total_vertices > mesh_options['max_vertices']:
            raise ValueError('ASSEMBLY_MESH_BUDGET: aggregate occurrence mesh exceeds requested output budget')
        body = {k: copy.deepcopy(entry[k]) for k in ('occurrence_id', 'reference_id', 'source_sha256', 'material_map')}
        body['mesh'] = copy.deepcopy(generated['mesh'])
        body['boundary_faces'] = [{'id': 'surface:'+str(face['cad_surface_tag'])+':'+str(i), 'vertices': face['vertices']}
                                  for i, face in enumerate(generated['boundary_faces'])]
        if 'stack_binding' in entry:
            body['stack_binding'] = entry['stack_binding']
        bodies.append(body)
        evidence.append({'occurrence_id': entry['occurrence_id'], 'representation': entry['representation'],
                         'approximations': entry['approximations'], 'metrics': generated['metrics']})
    request = {'contract': 'spike/assembly-field-handoff-request/v1', 'assembly': plan['assembly'],
               'domain': 'thermal', 'materials': plan['materials'], 'bodies': bodies}
    handoff = prepare_assembly_field_handoff(request)
    return {'contract': 'spike/assembly-thermal-mesh-result/v1', 'status': 'completed', 'request': request,
            'handoff': handoff, 'evidence': evidence, 'runtime': runtime, 'production_qualified': False,
            'contacts_inferred': False, 'boundary_conditions_inferred': False}
