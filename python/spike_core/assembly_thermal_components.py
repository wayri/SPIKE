# SPDX-License-Identifier: Apache-2.0
"""Explicit promotion of retained component STEP references to physical parts.

Component placement is only two-dimensional in SpiDeR. A reviewed proper-rigid
component-to-board frame is therefore mandatory: mounting elevation, bottom
orientation and model datum alignment are never inferred from render assets.
"""
import copy
import json

from .assembly_field_geometry import keys, number
from .assembly_field_handoff import _assembly, _materials, bounded_json, text
from .assembly_frames import IDENTITY, validate_rigid_transform
from .multiboard_identity import canonical_json_digest

PROVENANCE_KEY = 'spike.thermal-component'
MATERIALS_KEY = 'spike.thermal-component-materials'


def _designs(payload):
    designs = {d['design_id']: d for d in (payload.get('assembly_designs') or {}).get('designs', [])}
    active = payload.get('design_ir')
    if active:
        designs.setdefault(active['design_id'], active)
    return designs


def _model_identity(model):
    return {key: model.get(key) for key in ('id', 'uri', 'digest', 'model_type', 'transform')}


def _resolve(payload, board_id, component_id, model_id):
    assembly = _assembly(payload['assembly_ir'])
    board = next((b for b in assembly.boards if b.id == board_id), None)
    if board is None:
        raise ValueError('COMPONENT_BOARD: retained board occurrence required')
    design = _designs(payload).get(board.design_id)
    if design is None:
        raise ValueError('COMPONENT_DESIGN: retained board design required')
    matches = [c for c in design.get('components', []) if c.get('id') == component_id]
    if len(matches) != 1:
        raise ValueError('COMPONENT_IDENTITY: one exact retained component required')
    component = matches[0]
    if model_id not in component.get('model_ids', []):
        raise ValueError('COMPONENT_MODEL: model must be explicitly referenced by the retained component')
    models = [m for m in (payload.get('models') or {}).get('models', []) if m.get('id') == model_id]
    if len(models) != 1 or models[0].get('model_type') != 'step':
        raise ValueError('COMPONENT_STEP: retain the referenced exact STEP in the authoritative project model index first')
    model = models[0]
    if not isinstance(model.get('uri'), str) or not model['uri'].startswith('package:models/artifacts/'):
        raise ValueError('COMPONENT_STEP: STEP bytes must be retained in the project model artifacts')
    # If the design also carries this model, contradictory transforms or source
    # references must not be resolved by silently preferring one inventory.
    declared = [m for m in design.get('models', []) if m.get('id') == model_id]
    if len(declared) > 1 or (declared and _model_identity(declared[0]) != _model_identity(model)):
        raise ValueError('COMPONENT_MODEL_CONFLICT: design and project model references disagree')
    validate_rigid_transform(model.get('transform') or IDENTITY, 'Retained component model')
    return board, design, component, model


def thermal_component_inventory(payload):
    """Review identities and eligibility only; no CAD process or file read."""
    assembly = _assembly(payload['assembly_ir'])
    designs = _designs(payload)
    rows = []
    for board in assembly.boards:
        design = designs.get(board.design_id, {})
        for component in design.get('components', []):
            if len(rows) >= 5000:
                raise ValueError('COMPONENT_INVENTORY_BUDGET: at most 5000 component occurrences may be inventoried')
            cid = component.get('id')
            models = []
            for mid in component.get('model_ids', []):
                row = {'model_id': mid, 'status': 'blocked'}
                try:
                    _, _, _, model = _resolve(payload, board.id, cid, mid)
                    row.update(status='ready', source_sha256=model['digest'],
                               model_transform=list(model.get('transform') or IDENTITY),
                               reason='Review component frame and material; closed-solid eligibility is checked by Gmsh.')
                except (ValueError, KeyError, TypeError) as error:
                    row['reason'] = str(error)
                models.append(row)
            promoted = [p.id for p in assembly.parts if
                        p.extensions.get(PROVENANCE_KEY, {}).get('board_occurrence_id') == board.id and
                        p.extensions.get(PROVENANCE_KEY, {}).get('component_id') == cid]
            rows.append({'board_occurrence_id': board.id, 'design_id': board.design_id,
                         'component_id': cid, 'reference': component.get('reference', cid),
                         'placement': {key: copy.deepcopy(component.get(key)) for key in ('position_mm', 'rotation_deg', 'side')},
                         'models': models, 'promoted_part_ids': promoted})
    bounded_json(rows)
    return rows


def promote_thermal_components(payload, selections, materials, *, artifact_reader):
    """Return a proposed retained assembly mutation; the project service commits."""
    from .assembly_thermal_meshing import _artifact
    bounded_json(selections)
    properties = _materials(materials, 'thermal')
    if not isinstance(selections, list) or not 1 <= len(selections) <= 100:
        raise ValueError('COMPONENT_SELECTION: select 1..100 explicit component models')
    result = copy.deepcopy(payload)
    assembly = _assembly(payload['assembly_ir'])
    if len(assembly.parts)+len(selections) > 100:
        raise ValueError('COMPONENT_BUDGET: assembly supports at most 100 retained parts')
    replacement = assembly.to_dict()
    existing = {part.id for part in assembly.parts}
    parts, seen, used = [], set(), set()
    for selection in selections:
        keys(selection, ('board_occurrence_id', 'component_id', 'model_id', 'component_to_board_transform_mm',
                         'material_id', 'placement_reviewed'))
        if selection['placement_reviewed'] is not True:
            raise ValueError('COMPONENT_PLACEMENT: explicit review of mounting frame required')
        board_id, cid, mid, material_id = (text(selection[key]) for key in
            ('board_occurrence_id', 'component_id', 'model_id', 'material_id'))
        identity = (board_id, cid, mid)
        part_id = 'thermal-component-'+canonical_json_digest(identity)[:32]
        if identity in seen or part_id in existing:
            raise ValueError('COMPONENT_DUPLICATE: selected model already has a retained thermal part')
        seen.add(identity)
        if material_id not in properties:
            raise ValueError('COMPONENT_MATERIAL: explicit reviewed physical material assignment required')
        used.add(material_id)
        transform = selection['component_to_board_transform_mm']
        if not isinstance(transform, list) or len(transform) != 16:
            raise ValueError('COMPONENT_PLACEMENT: a 16-number component-to-board transform is required')
        for value in transform:
            number(value)
        validate_rigid_transform(transform, 'Reviewed component placement')
        board, design, component, model = _resolve(payload, board_id, cid, mid)
        _artifact(artifact_reader, model['uri'], model['digest'])
        provenance = {'contract': 'spike/thermal-component-provenance/v1',
                      'board_occurrence_id': board_id, 'design_id': board.design_id,
                      'component_id': cid, 'model_id': mid,
                      'component_digest': canonical_json_digest(component),
                      'design_source_digest': canonical_json_digest(design.get('source', {})),
                      'model_digest': canonical_json_digest(_model_identity(model)),
                      'source_sha256': model['digest'], 'component_to_board_transform_mm': list(transform)}
        part = {'id': part_id, 'source_id': cid, 'name': component.get('reference') or cid,
                'part_type': 'component', 'model_id': mid, 'material_id': material_id,
                'frame': {'frame_id': part_id+'-frame', 'parent_frame_id': board.frame.frame_id,
                          'units': 'mm', 'handedness': 'right', 'transform': list(transform)},
                'extensions': {PROVENANCE_KEY: provenance}}
        replacement['parts'].append(part)
        parts.append(part)
    if set(properties) != used:
        raise ValueError('COMPONENT_MATERIAL: supplied material records must all be used by selected components')
    # Store the exact reviewed tensor/provenance without reducing it to the
    # AssemblyIR material scalar. Meshing still requires explicit assignments.
    retained = replacement.setdefault('extensions', {}).setdefault(MATERIALS_KEY, {})
    for mid, material in properties.items():
        if mid in retained and retained[mid] != material:
            raise ValueError('COMPONENT_MATERIAL: retained material id has different reviewed properties')
        retained[mid] = copy.deepcopy(material)
    result['assembly_ir'] = json.loads(json.dumps(_assembly(replacement).to_dict(), allow_nan=False))
    return {'payload': result, 'promoted_parts': parts,
            'part_material_assignments': {part['id']: part['material_id'] for part in parts},
            'materials': copy.deepcopy(materials)}


def verify_promoted_component(payload, occurrence):
    """Withhold thermal meshes when retained component source/placement changes."""
    provenance = occurrence.extensions.get(PROVENANCE_KEY)
    if provenance is None:
        return
    if not isinstance(provenance, dict) or provenance.get('contract') != 'spike/thermal-component-provenance/v1':
        raise ValueError('COMPONENT_STALE: invalid promotion provenance')
    board, design, component, model = _resolve(payload, provenance['board_occurrence_id'],
                                              provenance['component_id'], provenance['model_id'])
    expected = {'design_id': board.design_id, 'component_digest': canonical_json_digest(component),
                'design_source_digest': canonical_json_digest(design.get('source', {})),
                'model_digest': canonical_json_digest(_model_identity(model)), 'source_sha256': model['digest']}
    if any(provenance.get(key) != value for key, value in expected.items()) or occurrence.model_id != model['id']:
        raise ValueError('COMPONENT_STALE: component or model changed after promotion; review and replace the retained part')
    # Subsequent explicit part movement/reparenting is permitted by assembly
    # tools; source placement remains bound above and the current part frame
    # is authoritative for the next mesh. The original reviewed frame is audit.
