# SPDX-License-Identifier: Apache-2.0
"""Inert placement drafts for the bounded native STEP reference envelope."""
from __future__ import annotations

import math

import numpy as np

from .mcad_export_contract import rigid_transform
from .spider_v2_schema import content_digest

REFERENCE_STEP_SHA256 = '9144054f0ec8ae87e131c88f9383815d4ffaf6605557c891cd95c9451e29bdfc'


def _review_context(design, component_id, model_id, *, native_version,
                    expected_design_digest, step_sha256):
    """Return a review draft; no file reads, geometry mutation or placement commit.

    Only the original mm-valued STEP, 0.035/1.53/0.035 stack, footprint (20,10),
    37/90 degree orientations are admitted. Callers enforce their measured model
    controls. Extension facts are required: canonical position may be a centroid.
    """
    frame = design.get('frame', {})
    values = frame.get('transform', ())
    if (design.get('contract') != 'spike/design-ir/v2' or frame.get('units') != 'mm'
            or frame.get('handedness') != 'right' or frame.get('parent_frame_id') != ''
            or not isinstance(values, (list, tuple))
            or any(isinstance(v, bool) for v in values)
            or list(values) != np.eye(4).reshape(-1).tolist()):
        raise ValueError('PLACEMENT_FRAME: canonical mm/right board datum required')
    if design.get('source', {}).get('source_format') != 'kicad' or native_version != '10.0.6':
        raise ValueError('PLACEMENT_SCOPE: requires the referenced KiCad version/source')
    baseline = content_digest(design)
    if expected_design_digest != baseline:
        raise ValueError('PLACEMENT_STALE: retained design changed')
    if step_sha256 != REFERENCE_STEP_SHA256:
        raise ValueError('PLACEMENT_SCOPE: only the referenced original STEP is admitted')
    layers = [l for l in design.get('layers', []) if l.get('thickness_mm') is not None]
    if any(l.get('thickness_mm') is None and (l.get('layer_type') in ('copper', 'core', 'dielectric', 'prepreg')
           or str(l.get('name', '')).endswith('.Cu') or 'dielectric' in str(l.get('name', '')).lower())
           for l in design.get('layers', [])):
        raise ValueError('PLACEMENT_STACK: physical layer thickness is unknown')
    if ([(l.get('name'), l.get('thickness_mm'), l.get('z_mm')) for l in layers] !=
            [('F.Cu', .035, 0.), ('dielectric 1', 1.53, .035), ('B.Cu', .035, 1.565)]):
        raise ValueError('PLACEMENT_STACK: stack or board datum is outside the native reference')
    components = [c for c in design.get('components', []) if c.get('id') == component_id]
    models = [m for m in design.get('models', []) if m.get('id') == model_id]
    if len(components) != 1 or len(models) != 1 or model_id not in components[0].get('model_ids', []):
        raise ValueError('PLACEMENT_OWNER: exact component/model ownership required')
    component, model = components[0], models[0]
    facts = component.get('extensions', {}).get('spike.v1', {})
    source = model.get('extensions', {}).get('spike.v1', {})
    declaration = source.get('source_placement', {})
    ordinal = declaration.get('ordinal')
    declarations = facts.get('model_sources', [])
    if (isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 0 <= ordinal < len(declarations)
            or declarations[ordinal] != declaration):
        raise ValueError('PLACEMENT_SOURCE: component and model declarations conflict')
    if (source.get('component') != component.get('source_id') or model.get('transform') != []
            or declaration.get('valid_source_vectors') is not True or declaration.get('errors') != []
            or declaration.get('projection') != 'forbidden'
            or declaration.get('semantic_state') != 'source_placement_unapplied'
            or declaration.get('uri') != model.get('uri')
            or (model.get('digest') and model['digest'] != step_sha256)):
        raise ValueError('PLACEMENT_SOURCE: consistent unapplied source facts required')
    angle, side = component.get('rotation_deg'), component.get('side')
    if (isinstance(angle, bool) or angle not in (37., 90.) or side not in ('top', 'bottom')
            or facts.get('native_footprint_at_mm') != [20., 10.]
            or facts.get('rotation') != angle
            or facts.get('layer') != ('F.Cu' if side == 'top' else 'B.Cu')):
        raise ValueError('PLACEMENT_SCOPE: footprint origin/side/angle outside native reference')
    vectors = declaration.get('declared_vectors', {})
    offset, rotation, scale = (vectors.get(k) for k in ('offset', 'rotate', 'scale'))
    for values in (offset, rotation, scale):
        if (not isinstance(values, list) or len(values) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)):
            raise ValueError('PLACEMENT_SOURCE: finite numerical xyz vectors required')
    node = declaration.get('source_node', [])
    try:
        if len(node) != 5 or node[0] != 'model' or str(node[1]).strip('"') != model['uri']:
            raise ValueError('source node identity')
        raw = {}
        for key, xyz in node[2:]:
            if key in raw or len(xyz) != 4 or xyz[0] != 'xyz':
                raise ValueError('source xyz declaration')
            raw[key] = [float(v) for v in xyz[1:]]
        if raw != vectors:
            raise ValueError('source vectors')
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError('PLACEMENT_SOURCE: retained node and normalized vectors conflict') from error
    return baseline, angle, side, offset, rotation, scale


def _rigid_matrix(angle, side, offset, rotation):
    """Measured native order, with scale carried by geometry instead of frame."""
    def rz(degrees):
        a = math.radians(degrees)
        return np.array([[math.cos(a), -math.sin(a), 0.],
                         [math.sin(a), math.cos(a), 0.], [0., 0., 1.]])
    def rx(degrees):
        a = math.radians(degrees)
        return np.array([[1., 0., 0.], [0., math.cos(a), -math.sin(a)], [0., math.sin(a), math.cos(a)]])
    def ry(degrees):
        a = math.radians(degrees)
        return np.array([[math.cos(a), 0., math.sin(a)], [0., 1., 0.], [-math.sin(a), 0., math.cos(a)]])
    base = rz(angle) @ np.diag([1., -1., -1.] if side == 'bottom' else [1., 1., 1.])
    datum = np.diag([1., -1., -1.])
    matrix = np.eye(4)
    matrix[:3, :3] = datum @ base @ rz(-rotation[2]) @ ry(-rotation[1]) @ rx(-rotation[0])
    mount = 1.615 if side == 'top' else -.085
    matrix[:3, 3] = datum @ (np.array([20., -10., mount]) + base @ np.array(offset)) + [0., 0., 1.565]
    return rigid_transform(matrix.reshape(-1).tolist())


def draft_kicad_component_placement(design, component_id, model_id, *, native_version,
                                    expected_design_digest, step_sha256):
    """Inert, unchanged unit-scale review API within the C3 native envelope."""
    baseline, angle, side, offset, rotation, scale = _review_context(
        design, component_id, model_id, native_version=native_version,
        expected_design_digest=expected_design_digest, step_sha256=step_sha256)
    controls = (([-1., 0., 4.], [0., 0., 90.]), ([0., 0., 0.], [0., 0., 0.]))
    if scale != [1., 1., 1.] or (offset, rotation) not in controls:
        raise ValueError('PLACEMENT_SCALE: only verified rigid controls admitted; bake/review other geometry separately')
    transform = _rigid_matrix(angle, side, offset, rotation)
    return {'contract': 'spike/component-placement-review/v1', 'status': 'review_required',
            'component_id': component_id, 'model_id': model_id, 'design_digest': baseline,
            'step_sha256': step_sha256, 'model_to_board_mm': transform,
            'mounting_clearance_mm': .05, 'native_version': native_version,
            'reference': 'WF01-S04C3', 'source_projection_enabled': False,
            'material_qualified': False, 'solver_ready': False}
