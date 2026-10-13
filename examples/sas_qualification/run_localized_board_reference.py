# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Source-bound local-grid sensitivity replay; not installed hardware qualification."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.layered_board_thermal import solve_layered_board_thermal
from examples.sas_qualification.run_board_reference import digest, export_fields


def focused_edges(low, high, intervals, local_step, background_step=6.0):
    """Partition at exact contact boundaries, with bounded steps in each segment."""
    cuts = sorted({low, high, *(max(low, min(high, v)) for span in intervals for v in span)})
    edges = [low]
    for a, b in zip(cuts, cuts[1:]):
        step = local_step if any(lo <= (a + b) / 2 <= hi for lo, hi in intervals) else background_step
        count = math.ceil((b - a) / step)
        edges.extend(a + (b - a) * i / count for i in range(1, count + 1))
    return edges


def replay(board, request_path, output):
    sources = {str(p.resolve()): digest(p) for p in (board, request_path)}
    engine_paths = [ROOT / 'python/spike_core' / name for name in (
        'layered_board_thermal.py', 'thermal_grid.py', 'thermal_copper_geometry.py', 'board_thermal.py', 'kicad_importer.py')]
    engine_paths += [ROOT / 'python/core/board_parser.py', Path(__file__), Path(__file__).with_name('run_board_reference.py')]
    engines = {str(p.resolve()): digest(p) for p in engine_paths}
    design = import_kicad_design(str(board))
    base = json.loads(request_path.read_text(encoding='utf-8'))
    positions = {c['reference']: c['at'] for c in design.components}
    intervals = [[], []]
    for part in base['components']:
        if part.get('contact_mode') != 'square':
            raise ValueError('This diagnostic replay requires explicit square contacts.')
        half = part['contact_size_mm'] / 2
        for axis in (0, 1):
            center = positions[part['component_ref']][axis]
            intervals[axis].append((center - half, center + half))
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for step in (2.0, 1.0, 0.75):
        request = json.loads(json.dumps(base))
        request.pop('transient', None)
        request['board'].pop('grid_step_mm', None)
        request['board'].update(x_edges_mm=focused_edges(0, 180, intervals[0], step),
                                y_edges_mm=focused_edges(0, 115, intervals[1], step),
                                copper_raster_step_mm=2.0, include_zones=True)
        request['study_scope'] = 'Single Blade local-grid sensitivity; fixed sampled copper, assumed square contacts and convection. Not assembly qualification.'
        result = solve_layered_board_thermal(design, request)
        stem = f'local-{step:g}mm'
        for suffix, payload in (('request', request), ('result', result)):
            (output / f'{stem}-{suffix}.json').write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        export_fields(result, output, stem)
        case = {'local_step_mm': step, 'shape': result['grid']['shape'], 'summary': result['summary'],
                'junction_temperature_c': {p['component_ref']: p['junction_temperature_c'] for p in result['components']}}
        cases.append(case)
        print(json.dumps(case, allow_nan=False), flush=True)
    comparisons = [{'from_mm': a['local_step_mm'], 'to_mm': b['local_step_mm'],
                    'maximum_junction_change_k': max(abs(v - b['junction_temperature_c'][ref]) for ref, v in a['junction_temperature_c'].items()),
                    'peak_change_k': abs(a['summary']['maximum_board_temperature_c'] - b['summary']['maximum_board_temperature_c'])}
                   for a, b in zip(cases, cases[1:])]
    for paths in (sources, engines):
        if any(digest(Path(path)) != sha for path, sha in paths.items()):
            raise ValueError('Source/engine changed during replay; no evidence commit.')
    report = {'contract': 'spike/localized-board-replay-evidence/v1', 'source_hashes': sources, 'engine_hashes': engines,
              'cases': cases, 'comparisons': comparisons, 'comparison_threshold_k': 0.1,
              'comparison_gate_passed': all(max(c['maximum_junction_change_k'], c['peak_change_k']) < .1 for c in comparisons),
              'hardware_qualified': False, 'limitations': ['Fixed 2 mm sampled copper, not conforming interfaces or copper geometry convergence',
                  'Assumed 9.4 mm square contacts, losses, plating and convection; no package bodies',
                  'Single Blade only; no installed fan curve, parallel passage/contact coupling or Base board']}
    (output / 'evidence.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (output / 'COMMITTED.json').write_text(json.dumps({p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.board, args.request, args.output)
    print(json.dumps({'comparison_gate_passed': report['comparison_gate_passed'], 'hardware_qualified': False}))
