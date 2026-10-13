# SPDX-License-Identifier: Apache-2.0
"""Owned STEP plus explicit neutral placements; never infer KiCad model frames."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.mcad_export_design import assembly_from_context

PLACEMENTS = (
    [0., -1., 0., 10., 1., 0., 0., 20., 0., 0., 1., 2., 0., 0., 0., 1.],
    [1., 0., 0., 15., 0., 1., 0., 8., 0., 0., 1., 3., 0., 0., 0., 1.],
    [1., 0., 0., 25., 0., -1., 0., 10., 0., 0., -1., -1., 0., 0., 0., 1.],
)
BOUNDS = ([7., 20., 2., 10., 22., 6.], [15., 8., 3., 17., 11., 7.],
          [25., 7., -5., 27., 10., -1.])


def component_model_context(imported: dict, payload: bytes) -> dict:
    design = imported['design']
    context = {'design': design, 'parameters': {'allow_partial': True}}
    plan = assembly_from_context(context)
    occurrences = plan['properties']['component_occurrences']
    if len(occurrences) != 1 or len(occurrences[0]['model_ids']) != 3:
        raise ValueError('Owned component-solid cohort requires exactly three retained model occurrences.')
    occurrence = occurrences[0]
    digest = plan['properties']['retained_design_digests'][occurrence['design_id']]
    context['parameters']['component_models'] = [
        {'occurrence_id': occurrence['id'], 'model_id': model_id, 'design_digest': digest,
         'model_to_board_mm': transform,
         'placement_reference': 'Owned 2x3x4 mm cuboid; explicit neutral fixture placement, not inferred source vectors.',
         'geometry': {'type': 'step', 'data_base64': base64.b64encode(payload).decode(),
                      'sha256': hashlib.sha256(payload).hexdigest()}}
        for model_id, transform in zip(occurrence['model_ids'], PLACEMENTS)]
    return context


def validate_component_model_gate(imported: dict, solid: bytes, native: dict) -> None:
    context = component_model_context(imported, solid)
    assembly = assembly_from_context(context)
    actual = [row for row in assembly['objects'] if row['kind'] == 'component']
    recorded = [row for row in native.get('objects', []) if row.get('kind') == 'component']
    if (native.get('contract') != 'spike/mcad-export-manifest/v1' or native.get('units') != 'mm'
            or native.get('solver_qualified') is not False
            or len(actual) != 3 or len(recorded) != 3):
        raise ValueError('Component-solid native evidence is incomplete.')
    by_id = {row['id']: row for row in recorded}
    if len(by_id) != 3 or set(by_id) != {row['id'] for row in actual}:
        raise ValueError('Component-solid native occurrence identities differ.')
    if any(item['code'] == 'COMPONENT_GEOMETRY_REQUIRED' for item in assembly['diagnostics']):
        raise ValueError('Complete explicit solids did not close the geometry omission.')
    for row, transform, bounds in zip(actual, PLACEMENTS, BOUNDS):
        observed = by_id[row['id']]
        if (row['transform'] != transform or observed.get('transform') != transform
                or observed.get('parent_id') != row['parent_id']
                or observed.get('material_id') != row.get('material_id', '')
                or observed.get('source') != row['source'] or observed.get('solid_count') != 1
                or observed.get('step_roundtrip') != 'passed'
                or observed.get('properties') != row['properties']):
            raise ValueError('Component-solid native placement or provenance differs.')
        volume = observed.get('volume_mm3')
        if (isinstance(volume, bool) or not isinstance(volume, (int, float))
                or not math.isfinite(volume) or abs(volume - 24.) > 1e-6):
            raise ValueError('Component-solid native volume differs from owned analytical cuboid.')
        observed_bounds = observed.get('bounds_mm', [])
        if (not isinstance(observed_bounds, list) or len(observed_bounds) != 6
                or any(isinstance(a, bool) or not isinstance(a, (int, float))
                       or not math.isfinite(a) or abs(a-b) > 1e-6
                       for a, b in zip(observed_bounds, bounds))):
            raise ValueError('Component-solid native bounds differ from explicit analytical placement.')
        if (row['properties']['solver_ready'] is not False
                or row['properties']['material_qualified'] is not False):
            raise ValueError('Mechanical handoff promoted physics/material readiness.')
    if any(model['transform'] for model in imported['design']['models']):
        raise ValueError('Source model transforms must remain unapplied in this cohort.')


def validate_receipt(gate: dict, root: Path) -> None:
    def bound(name: str, digest_name: str) -> Path:
        path = (root / gate[name]).resolve()
        if (not path.is_relative_to(root.resolve()) or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != gate[digest_name]):
            raise ValueError('Component-solid gate path/digest is stale.')
        return path
    runner = bound('runner', 'runner_sha256')
    if runner != (root / 'scripts/parity_component_model_gate.py').resolve():
        raise ValueError('Component-solid gate runner identity differs.')
    solid = bound('solid_file', 'solid_sha256')
    imported = bound('import_file', 'import_sha256')
    native = bound('native_file', 'native_sha256')
    bound('export_file', 'export_sha256')
    validate_component_model_gate(json.loads(imported.read_text(encoding='utf-8')),
        solid.read_bytes(), json.loads(native.read_text(encoding='utf-8')))
