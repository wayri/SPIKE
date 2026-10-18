# SPDX-License-Identifier: Apache-2.0
"""Recompute the bounded native STEP reference; never enable source projection."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

if __package__:
    from .parity_component_placement_math import bounds, native_vertices, spike_vertices
else:
    from parity_component_placement_math import bounds, native_vertices, spike_vertices

VALIDATORS = ('scripts/parity_native_step_placement_gate.py', 'scripts/parity_component_placement_math.py')
MODELS = (([1.25, -2.5, 3.], [15., 30., 45.], [2., 1., .5]),
          ([-1., 0., 4.], [0., 0., 90.], [1., 1., 1.]),
          ([0., 0., 0.], [0., 0., 0.], [1., 1., 1.]))
TOLERANCE = 1e-6


def bound(root, name, digest):
    path = (root / name).resolve()
    if (not path.is_relative_to(root.resolve()) or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
        raise ValueError('Native STEP source/artifact evidence is stale or foreign')
    return path


def close(actual, expected):
    if (isinstance(actual, bool) or not isinstance(actual, (int, float))
            or not math.isfinite(actual) or abs(actual - expected) > TOLERANCE):
        raise ValueError('Native STEP numerical reference differs')


def points(actual, expected):
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValueError('Native STEP corner coverage differs')
    matches = set()
    for p in actual:
        if len(p) != 3 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in p):
            raise ValueError('Native STEP invalid corner')
        distances = [max(abs(x-y) for x, y in zip(p, q)) for q in expected]
        index = min(range(len(expected)), key=distances.__getitem__)
        close(distances[index], 0.)
        matches.add(index)
    if len(matches) != len(expected):
        raise ValueError('Native STEP corners are duplicated or missing')


def solid(actual, expected_points, volume):
    if actual.get('valid') is not True:
        raise ValueError('Native STEP solid is invalid')
    close(actual.get('volume_mm3'), volume)
    points(actual.get('vertices_mm'), expected_points)
    actual_bounds = actual.get('bounds_mm', [])
    if len(actual_bounds) != 6:
        raise ValueError('Native STEP bounds are incomplete')
    for a, b in zip(actual_bounds, bounds(expected_points)):
        close(a, b)


def validate_receipt(receipt, root):
    if (receipt.get('contract') != 'spike/native-step-placement-stage/v1'
            or receipt.get('stage_id') != 'WF01-S04C3' or receipt.get('status') != 'passed'
            or any(receipt.get(k) is not False for k in
                   ('production_qualified', 'material_qualified', 'source_projection_enabled'))):
        raise ValueError('Native STEP stage scope/status differs')
    if set(receipt.get('validators', {})) != set(VALIDATORS):
        raise ValueError('Native STEP validator bindings missing')
    for name, sha in receipt['validators'].items():
        bound(root, name, sha)
    reference = json.loads(bound(root, receipt['reference'], receipt['reference_sha256']).read_text())
    if (reference.get('contract') != 'spike/native-step-placement-reference/v1'
            or reference.get('status') != 'passed_local_black_box_reference'
            or reference.get('native_version') != '10.0.6'):
        raise ValueError('Native STEP reference identity differs')
    bindings = reference['bindings']
    if set(bindings['sources']) != {'benchmarks/parity-import/models.kicad_pcb', 'benchmarks/parity-import/component-solid.step'}:
        raise ValueError('Native STEP original source coverage differs')
    for name, sha in bindings['sources'].items():
        bound(root, name, sha)
    artifact_root = receipt['artifact_root']
    artifacts = {name: bound(root, artifact_root + '/' + name, sha) for name, sha in bindings['artifacts'].items()}
    required = {'observed-solids.json', 'inputs.json', 'prepare.py', 'export.py', 'inspect_solids.py', 'check_reference.py', 'run_reference.py'}
    if not required <= set(artifacts):
        raise ValueError('Native STEP reproduction artifacts incomplete')
    observed = json.loads(artifacts['observed-solids.json'].read_text())['files']
    inputs = json.loads(artifacts['inputs.json'].read_text())
    if inputs != reference['inputs']:
        raise ValueError('Native STEP input facts differ')
    frame = reference['frame']
    for side, copper, mount in (('front', 1.565, 1.615), ('back', -.035, -.085)):
        close(frame['physical_copper_surfaces_mm'][side], copper)
        close(frame['model_mounting_planes_mm'][side], mount)
    names = {f'{side}-{angle}' for side in ('front', 'back') for angle in (90, 37)}
    if {c['name'] for c in inputs['cases']} != names or len(inputs['cases']) != 4:
        raise ValueError('Native STEP input cohort differs')
    for entry in inputs['cases']:
        side, angle = entry['name'].split('-')
        if (entry['footprint_position_mm'] != [20., 10.] or entry['footprint_angle_deg'] != int(angle)
                or entry['layer'] != ('F.Cu' if side == 'front' else 'B.Cu')
                or entry['board_thickness_mm'] != 1.6 or len(entry['models']) != 3):
            raise ValueError('Native STEP footprint/stack facts differ')
        board = observed[entry['name'] + '.step']['solids'][-1]
        if board['valid'] is not True or len(board['bounds_mm']) != 6:
            raise ValueError('Native STEP board body invalid')
        for a, b in zip(board['bounds_mm'], [-1., -20., 0., 30., 1., 1.53]):
            close(a, b)
        close(board['volume_mm3'], 989.91)
    expected_ids = {(name, i) for name in names for i in range(3)}
    cases = reference['cases']
    if len(cases) != 12 or {(c['name'], c['model_index']) for c in cases} != expected_ids:
        raise ValueError('Native STEP occurrence coverage differs')
    import itertools
    source_points = list(itertools.product([0., 2.], [0., 3.], [0., 4.]))
    if len(observed['component-solid.step']['solids']) != 1:
        raise ValueError('Native STEP source solid count differs')
    solid(observed['component-solid.step']['solids'][0], source_points, 24.)
    for case in cases:
        side, angle = case['name'].split('-')
        if case['side'] != side or case['footprint_angle_deg'] != int(angle):
            raise ValueError('Native STEP side/angle differs')
        offset, rotation, scale = MODELS[case['model_index']]
        source = case['source_inputs']
        entry = next(c for c in inputs['cases'] if c['name'] == case['name'])
        if source != entry['models'][case['model_index']]:
            raise ValueError('Native STEP model metadata differs')
        if source['offset_mm'] != offset or source['rotation_deg'] != rotation or source['scale'] != scale:
            raise ValueError('Native STEP source vectors differ')
        native = observed[case['name'] + '.step']['solids'][case['native_solid_index']]
        if native != case['native']:
            raise ValueError('Native STEP observed solid differs from retained reader output')
        expected = native_vertices(side, int(angle), offset, rotation, scale,
                                   surface_z=1.615 if side == 'front' else -.085)
        solid(native, expected, 24.)
        points(case['spike_vertices_mm'], spike_vertices(native['vertices_mm'], top_z=1.565))
    for side in ('front', 'back'):
        control = reference['datum_controls'][side]
        if control['no_extra_flag_changes_component_placement'] is not False:
            raise ValueError('Native STEP mounting control differs')
        close(control['observed_mounting_clearance_mm'], .05)
        for suffix in ('', '-no-extra', '-copper'):
            filename = side + '-90' + suffix + '.step'
            rows = observed[filename]['solids']
            if len(rows) != (6 if suffix == '-copper' else 4):
                raise ValueError('Native STEP control solid count differs')
            for i, (offset, rotation, scale) in enumerate(MODELS):
                solid(rows[i], native_vertices(side, 90, offset, rotation, scale,
                                              surface_z=1.615 if side == 'front' else -.085), 24.)
            for a, b in zip(rows[-1]['bounds_mm'], [-1., -20., 0., 30., 1., 1.53]):
                close(a, b)
            close(rows[-1]['volume_mm3'], 989.91)
            if suffix == '-copper':
                if rows[3:5] != control['copper_solids']:
                    raise ValueError('Native STEP copper control differs')
                for row, limits in zip(rows[3:5], [(1.53, 1.565), ((1.53, 1.565) if side == 'front' else (-.035, 0.))]):
                    close(row['bounds_mm'][2], limits[0])
                    close(row['bounds_mm'][5], limits[1])
    exports = reference['exports']
    expected_exports = {name + '-export.json' for name in names} | {
        side + '-90' + suffix + '-export.json' for side in ('front', 'back') for suffix in ('-no-extra', '-copper')}
    if set(exports) != expected_exports:
        raise ValueError('Native STEP export coverage differs')
    for name, run in exports.items():
        if (run != json.loads(artifacts[name].read_text()) or run.get('returncode') != 0
                or run.get('timed_out') or '--user-origin' not in run['command'] or '0x0mm' not in run['command']):
            raise ValueError('Native STEP export failed or has a different datum')
