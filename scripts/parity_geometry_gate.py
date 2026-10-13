# SPDX-License-Identifier: Apache-2.0
"""Recompute bounded geometry-transport observables from real CLI import data."""
from __future__ import annotations
import math
from pathlib import Path
import sys

# Direct scripts/ invocation does not put the repository package on sys.path.
# The trusted gate source, not receipt data, determines this import root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _area(points):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points, [*points[1:],points[0]]))) / 2


def evaluate_geometry_gate(payload):
    from python.spike_core.spider_v2 import SpiDeRV2
    from python.spike_core.geometry_arrow import canonical_geometry_rows
    from python.spike_core.assembly_thermal_meshing import _board_model
    from python.spike_core.spikes_layout_geometry_handoff import _supported_sources

    design = SpiDeRV2.from_dict(payload['design'])
    parents = {arc.source_id for arc in design.arcs}
    if any(track.extensions.get('spike.v1', {}).get('source_parent_id') in parents for track in design.tracks):
        raise ValueError('Canonical copper contains both exact arcs and their chord surrogates.')
    legacy = design.to_v1()
    rows = canonical_geometry_rows(design)
    physical = [layer for layer in design.layers if layer.extensions.get('spike.v1.stackup')]
    compiled, _ = _board_model(design.to_dict(), {'representation': 'layer_homogenized',
                              'layer_materials': {layer.id: 'explicit-fixture-effective' for layer in physical}})
    volume = 0.
    for solid in compiled['solids']:
        shape = solid['shape']
        area = _area(shape['outer_mm']) - sum(_area(hole) for hole in shape['holes_mm'])
        volume += area * (shape['z_max_mm'] - shape['z_min_mm'])
    # The full fixture's rotated pad is outside this native layout adapter's
    # envelope. This explicitly selected Arc-only handoff does not admit it.
    arc_only = SpiDeRV2.from_dict(design.to_dict())
    arc_only.pads, arc_only.pins, arc_only.components = [], [], []
    handed = _supported_sources(arc_only)
    return {'arc_count': len(design.arcs), 'canonical_track_count': len(design.tracks),
            'arrow_arc_count': sum(row['kind'] == 'arc' for row in rows),
            'native_arc_handoff_count': len(handed['arcs']), 'native_handoff_scope': 'explicit_arc_only',
            'legacy_track_count': len(legacy.tracks),
            'board_area_mm2': compiled['evidence']['board_area_mm2'], 'stack_volume_mm3': volume,
            'hole_count_per_layer': [len(solid['shape']['holes_mm']) for solid in compiled['solids']],
            'board_bounds_mm': design.metadata['board_bounds_mm'], 'production_qualified': False}


def validate_geometry_gate(payload, expected):
    actual = evaluate_geometry_gate(payload)
    if not isinstance(expected, dict) or set(expected) != set(actual):
        raise ValueError('Geometry gate requires every declared bounded observable.')
    for name, value in expected.items():
        if type(value) is float:
            if (type(actual[name]) not in (int, float) or not math.isfinite(value)
                    or not math.isfinite(actual[name]) or abs(actual[name]-value) > 1e-9):
                raise ValueError(f'Geometry gate mismatch: {name}')
        elif actual[name] != value:
            raise ValueError(f'Geometry gate mismatch: {name}')
    return actual
