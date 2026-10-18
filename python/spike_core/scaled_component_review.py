# SPDX-License-Identifier: Apache-2.0
"""Bounded bake-then-rigid placement proposal; no source/project mutation."""
from __future__ import annotations

import copy
import hashlib
import json

from .component_placement_review import _review_context, _rigid_matrix, REFERENCE_STEP_SHA256
from .component_step_scale import scale_component_step, MAX_BYTES
from .spider_v2_schema import content_digest


def prepare_scaled_component_review(design, component_id, model_id, source_step, *,
                                    native_version, expected_design_digest,
                                    freecad_executable=None, cancellation_event=None):
    """Supervised native asset preparation for the C3 nonuniform control only.

    The synchronous call belongs in an existing worker/CLI. Original geometry
    bytes are verified before preprocessing. Derived registration and placement
    approval remain separate; this does not return an executable model binding.
    """
    if (not isinstance(source_step, bytes) or not 0 < len(source_step) <= MAX_BYTES
            or hashlib.sha256(source_step).hexdigest() != REFERENCE_STEP_SHA256):
        raise ValueError('PLACEMENT_ASSET: original referenced STEP bytes required')
    size = 0
    for chunk in json.JSONEncoder(allow_nan=False).iterencode(design):
        size += len(chunk.encode('utf-8'))
        if size > 8*1024**2:
            raise ValueError('PLACEMENT_BUDGET: review design exceeds 8 MiB control budget')
    snapshot = copy.deepcopy(design)
    baseline, angle, side, offset, rotation, scale = _review_context(
        snapshot, component_id, model_id, native_version=native_version,
        expected_design_digest=expected_design_digest, step_sha256=REFERENCE_STEP_SHA256)
    if (offset != [1.25, -2.5, 3.] or rotation != [15., 30., 45.] or scale != [2., 1., .5]):
        raise ValueError('PLACEMENT_SCALE: source scale/rotation outside the measured nonuniform control')
    asset = scale_component_step(source_step, scale, expected_sha256=REFERENCE_STEP_SHA256,
                                 freecad_executable=freecad_executable,
                                 cancellation_event=cancellation_event)
    # A job result must not propose placement against a baseline changed while
    # native preprocessing was running. The snapshot also protects vector aliases.
    if content_digest(design) != baseline:
        raise ValueError('PLACEMENT_STALE: source design changed during native preparation')
    return {'contract': 'spike/scaled-component-review/v1', 'status': 'review_required',
            'source_component_id': component_id, 'source_model_id': model_id,
            'design_digest': baseline, 'source_sha256': REFERENCE_STEP_SHA256,
            'derived_asset': asset, 'model_to_board_mm': _rigid_matrix(angle, side, offset, rotation),
            'mounting_clearance_mm': .05, 'native_version': native_version,
            'derived_model_registration_required': True, 'source_projection_enabled': False,
            'material_qualified': False, 'solver_ready': False, 'reference': 'WF01-S04C3'}
