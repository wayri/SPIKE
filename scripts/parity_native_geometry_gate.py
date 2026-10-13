# SPDX-License-Identifier: Apache-2.0
"""Recompute bounded native source/export fidelity; never qualify physics."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import tempfile
import zipfile
import sys
from contextlib import redirect_stdout
from io import StringIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if __package__:
    from .capture_parity_native_geometry import pose_source, shape_source
else:
    from capture_parity_native_geometry import pose_source, shape_source


def close(actual, expected, tolerance=1e-9):
    if isinstance(expected, list):
        return isinstance(actual, (list, tuple)) and len(actual) == len(expected) and all(close(a, b, tolerance) for a, b in zip(actual, expected))
    return type(actual) in (int, float) and math.isfinite(actual) and abs(actual - expected) <= tolerance


def polygon_bbox(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def outline_facts(design):
    rings = design['metadata']['board_outline_rings']
    area = 0.0
    for ring in rings:
        if any(s['kind'] != 'line' for s in ring['segments']):
            raise ValueError('Native export gate admits only straight source outlines.')
        points = [ring['start_mm'], *[s['end_mm'] for s in ring['segments']]]
        contribution = abs(sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(points, points[1:]))) / 2
        area += contribution if ring['role'] == 'outer' else -contribution
    return {'area_mm2': area, 'outer_count': sum(r['role'] == 'outer' for r in rings),
            'cutout_count': sum(r['role'] == 'cutout' for r in rings)}


def validate_native_facts(native, source):
    if (native.get('contract') != 'spike/native-kicad-geometry/v1' or not native.get('kicad_version')
            or native.get('source_sha256') != hashlib.sha256(source.read_bytes()).hexdigest()
            or native.get('runner_sha256') != hashlib.sha256((ROOT / 'scripts/capture_parity_native_geometry.py').read_bytes()).hexdigest()):
        raise ValueError('Native geometry source or runner binding is stale.')


def validate_kicad_source_geometry(payload, native):
    from python.spike_core.hybrid_mesh import _pad_boundary_polygon
    if payload['report']['source_sha256'] != native['source_sha256']:
        raise ValueError('Native pad gate source differs from CLI import.')
    pads = payload['design']['pads']
    if len(pads) != len(native['pads']):
        raise ValueError('Native pad coverage differs.')
    for expected in native['pads']:
        matches = [p for p in pads if p['source_id'] == expected['source_id']]
        if len(matches) != 1: raise ValueError('Native pad identity differs.')
        p = matches[0]
        raw = p['extensions']['spike.v1']
        if (not close(p['center_mm'], expected['center_mm'], 1e-6)
                or not close(p['size_mm'], expected['size_mm'])
                or not close(raw['rotation'], -expected['native_angle_deg'])
                or not close(raw['native_pad_rotation_deg'], expected['native_angle_deg'])
                or not close(polygon_bbox(_pad_boundary_polygon(raw, 64)), expected['bbox_mm'], 2e-6)):
            raise ValueError('Native pad pose or physical perimeter differs.')
    observed = outline_facts(payload['design'])
    if observed != native['outline']:
        raise ValueError('Native source outline area/topology differs.')


def validate_pad_cohort(native, source):
    from python.core.board_parser import KicadParser
    from python.spike_core.hybrid_mesh import _pad_boundary_polygon
    base = source.read_text(encoding='utf-8')
    expected_keys = {(t,s,f,p) for t in ('footprint','module') for s in ('F.Cu','B.Cu') for f in (0,90,37) for p in (None,0,23,90)}
    rows = native['pad_cases']
    if len(rows) != 48 or {(r['token'],r['side'],r['footprint_angle'],r['pad_angle']) for r in rows} != expected_keys:
        raise ValueError('Native pose cohort coverage is incomplete.')
    scratch = ROOT / 'build/parity-test-temp'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        path = Path(directory) / 'case.kicad_pcb'
        for row in rows + native['shape_cases']:
            if not close(row['native_angle_deg'], row['pad_angle'] or 0):
                raise ValueError('Native cohort did not exercise its declared pad angle.')
            if 'token' in row and not close(row['native_footprint_angle_deg'], row['footprint_angle']):
                raise ValueError('Native cohort did not exercise its declared footprint angle.')
            text = (pose_source(base, row['token'], row['side'], row['footprint_angle'], row['pad_angle'])
                    if 'token' in row else shape_source(base, row['side'], row['pad_angle'], row['kind']))
            if hashlib.sha256(text.encode('utf-8')).hexdigest() != row['source_sha256']:
                raise ValueError('Native pose source recipe differs.')
            path.write_text(text, encoding='utf-8', newline='\n')
            with redirect_stdout(StringIO()):
                parser = KicadParser(path)
            pad = parser.pads[0]
            if (not close(pad['at'], row['center_mm'], 1e-6)
                    or not close(pad['rotation'], -row['native_angle_deg'])
                    or not close(pad['native_pad_rotation_deg'], row['native_angle_deg'])
                    or not close(polygon_bbox(_pad_boundary_polygon(pad, 64)), row['bbox_mm'], 2e-6)):
                raise ValueError('Imported native pose/shape cohort differs.')
            if row.get('kind') == 'custom' and pad['custom_geometry']['mirror_x'] is not False:
                raise ValueError('Native custom pad acquired an extra reflection.')
            if row.get('kind') == 'slot':
                width, height = pad['drill_size']
                if row['pad_angle'] == 90: width, height = height, width
                expected = [pad['at'][0]-width/2, pad['at'][1]-height/2, width, height]
                if not close(expected, row['hole_bbox_mm'], 2e-6):
                    raise ValueError('Native slot aperture orientation differs.')
    if len(native['shape_cases']) != 8 or {(r['kind'],r['side'],r['pad_angle']) for r in native['shape_cases']} != {(k,s,a) for k in ('custom','slot') for s in ('F.Cu','B.Cu') for a in (0,90)}:
        raise ValueError('Native shape cohort coverage is incomplete.')


def validate_native_export_geometry(payload, native, archive):
    exported = native['native_export']
    if (hashlib.sha256(archive.read_bytes()).hexdigest() != exported['archive_sha256']
            or payload['report']['source_sha256'] != exported['archive_sha256']):
        raise ValueError('Native export archive binding differs.')
    with zipfile.ZipFile(archive) as package:
        expected = {'job/'+r['name']:r for r in exported['members']}
        if set(package.namelist()) != set(expected): raise ValueError('Native export member coverage differs.')
        for name, row in expected.items():
            data = package.read(name)
            if len(data) != row['size_bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('Native export member bytes differ.')
    d = payload['design']
    if len(d['arcs']) != len(native['arcs']) or len(d['pads']) != len(native['pads']) or len(d['components']) != len(native['components']):
        raise ValueError('Native exported object coverage differs.')
    # The observed native writer reflects XY's Y axis and may reverse arc
    # endpoint order; this gate compares unoriented conductor geometry only.
    reflect = lambda p: [p[0], -p[1]]
    arc, expected = d['arcs'][0], native['arcs'][0]
    ends = [reflect(expected['start_mm']), reflect(expected['end_mm'])]
    if (not any(close(arc['start_mm'], ends[i]) and close(arc['end_mm'], ends[1-i]) for i in (0,1))
            or not close(arc['mid_mm'], reflect(expected['mid_mm']))
            or not close(arc['width_mm'], expected['width_mm'])):
        raise ValueError('Native arc geometry differs.')
    p, expected_pad = d['pads'][0], native['pads'][0]
    raw = p['extensions']['spike.v1']
    if (not close(p['center_mm'], reflect(expected_pad['center_mm']))
            or not close(p['size_mm'], expected_pad['size_mm'])
            or not close(raw['rotation'] % 360, expected_pad['native_angle_deg'] % 360)):
        raise ValueError('Native exported pad differs.')
    c, expected_component = d['components'][0], native['components'][0]
    if c['reference'] != expected_component['reference'] or not close(c['position_mm'], reflect(expected_component['position_mm'])) or not close(c['rotation_deg'] % 360, expected_component['native_angle_deg'] % 360):
        raise ValueError('Native exported component differs.')
    if outline_facts(d) != native['outline']:
        raise ValueError('Native export profile/cutout differs.')
    nets = {r['id']:r['name'] for r in d['nets']}
    layers = {r['id']:r['name'] for r in d['layers']}
    if nets.get(arc['net_id']) != expected['net'] or nets.get(p['net_id']) != expected['net'] or layers.get(arc['layer_id']) != expected['layer'] or p['component_id'] != c['id']:
        raise ValueError('Native export ownership/connectivity differs.')
    if any(r['ready'] is not False for r in payload['report']['solver_readiness'].values()):
        raise ValueError('Bounded native export evidence cannot promote solver readiness.')
