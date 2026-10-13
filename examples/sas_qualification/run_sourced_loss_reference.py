# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Replay a hash-bound SAS estimated-loss ledger without inventing package data."""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.kicad_importer import import_kicad_design
from examples.sas_qualification.run_board_reference import digest, export_fields


def replay(board, ledger, template, output, case_index):
    snapshots = {str(p.resolve()): digest(p) for p in (board, ledger, template)}
    engine_paths = [ROOT / 'python/spike_core' / name for name in (
        'layered_board_thermal.py', 'board_thermal.py', 'thermal_grid.py', 'thermal_copper_geometry.py', 'kicad_importer.py')]
    engine_paths += [ROOT / 'python/core/board_parser.py', Path(__file__), Path(__file__).with_name('run_board_reference.py')]
    engines = {str(p.resolve()): digest(p) for p in engine_paths}
    deck = json.loads(ledger.read_text(encoding='utf-8'))
    if deck.get('native_board_sha256') != digest(board):
        raise ValueError('Loss ledger does not bind the supplied native board.')
    case = deck['cases'][case_index]
    sources = case['sources']
    if not 1 <= len(sources) <= 256:
        raise ValueError('Loss sources exceed the bounded source count.')
    design = import_kicad_design(str(board))
    positions = {c['reference']: c['native_footprint_at_mm'] for c in design.components}
    base = json.loads(template.read_text(encoding='utf-8'))
    package_rows = {p['component_ref']: p for p in base['components']}
    request = {k: v for k, v in base.items() if k not in ('components', 'transient', 'board_heat_sources')}
    request['components'], request['board_heat_sources'] = [], []
    request['study_scope'] = 'Estimated loss sensitivity; prescribed air/contact paths; no measured or assembly qualification. Unlocated auxiliary remainder is NOT deposited.'
    seen = set()
    for source in sources:
        ref, power = source['reference'], source['power_w']
        if ref in seen or ref not in positions or isinstance(power, bool) or not isinstance(power, (int, float)) or not math.isfinite(power) or power < 0:
            raise ValueError('Invalid, duplicated or unmapped ledger source.')
        seen.add(ref)
        if len(source['position_mm']) != 2 or any(abs(a - b) > 1e-9 for a, b in zip(source['position_mm'], positions[ref])):
            raise ValueError(f'{ref}: ledger position differs from native geometry.')
        if ref in package_rows:
            row = dict(package_rows[ref])
            row.pop('contact_size_mm', None)
            row.update(power_w=power, contact_mode='pads', contact_pad_numbers=['2'])
            request['components'].append(row)
        else:
            request['board_heat_sources'].append({'id': f'estimated-{ref}', 'component_ref': ref,
                                                  'power_w': power, 'contact_mode': 'pads'})
    modeled_power = math.fsum(source['power_w'] for source in sources)
    if not math.isclose(modeled_power, case['modeled_source_loss_w'], abs_tol=1e-9, rel_tol=1e-12):
        raise ValueError('Ledger total does not equal mapped source power.')
    output.mkdir(parents=True, exist_ok=False)
    result = run_board_thermal(design, request)
    for name, payload in (('request.json', request), ('result.json', result)):
        (output / name).write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    if result['status'] == 'completed':
        export_fields(result, output, 'sourced')
    if any(digest(Path(path)) != sha for path, sha in {**snapshots, **engines}.items()):
        raise ValueError('Input or engine changed during replay; no evidence commit.')
    evidence = {'contract': 'spike/sourced-board-loss-replay-evidence/v1', 'source_hashes': snapshots,
        'engine_hashes': engines, 'mode': case['mode'], 'variant': case['variant'], 'status': result['status'],
        'modeled_source_loss_w': modeled_power, 'summary': result['summary'],
        'unlocated_auxiliary_power_not_deposited_w': case.get('auxiliary_remainder_sensitivity_w'),
        'package_sources': list(package_rows), 'direct_board_sources': len(request['board_heat_sources']),
        'hardware_qualified': False, 'mesh_convergence_status': 'not_demonstrated',
        'limitations': ['Analytical estimated losses, not measured power',
            'Package RJC/RCB from diagnostic template retained as supplied assumptions, not validated body models',
            'Drain pad2 selected for package rows; all copper pads retained',
            'Other source power fully delivered to PCB pads; their case/junction temperatures UNSOLVED',
            'Auxiliary remainder has no supplied location and is not deposited',
            'Prescribed h=50 and scalar ambient; no fan/airflow/assembly coupling',
            'Sampled copper and one z-cell per stackup row; mesh convergence not qualified'],
        'issues': result.get('issues', [])}
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (output / 'COMMITTED.json').write_text(json.dumps({p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, allow_nan=False), flush=True)
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('board', 'ledger', 'template', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--case-index', type=int, default=0)
    args = parser.parse_args()
    replay(args.board, args.ledger, args.template, args.output, args.case_index)
