#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise SU2 through the real extension process boundary and retain evidence."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.extensions import ExtensionManifest, ProcessExtension


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/su2-extension-20261011')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    verification = output / 'verification.json'
    # Invalidate previous evidence before starting; interrupted verification
    # must never leave an earlier green summary describing the current inputs.
    verification.write_text(json.dumps({'contract': 'spike/su2-extension-verification/v1',
        'checks': [], 'passed': False, 'status': 'running', 'board_geometry_used': False}, indent=2), encoding='utf-8')
    os.environ['SPIKE_STATE_HOME'] = str(output / 'state')
    directory = ROOT / 'extensions/su2_suite'
    manifest = ExtensionManifest.from_dict(json.loads((directory / 'spike-extension.json').read_text()))
    extension = ProcessExtension(manifest, directory, True)
    cases = [('su2-probe', {}), ('su2-cfd-preview', {'cells': 16}),
             ('su2-cfd', {'cells': 16}), ('su2-cht-preview', {'cells': 16}),
             ('su2-cht', {'cells': 16, 'lid_speed': 1})]
    outcomes = []
    for contribution, parameters in cases:
        result = extension.invoke(contribution, {'parameters': parameters}, timeout_seconds=320)
        (output / (contribution + '.json')).write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
        if result.get('status') != 'completed':
            raise RuntimeError('Extension did not complete: ' + contribution)
        if contribution in ('su2-cfd', 'su2-cht'):
            solver = result['data']['result']
            if solver['status'] != 'completed' or not solver['convergence']['converged']:
                raise RuntimeError('No accepted converged solution: ' + contribution)
            if not Path(solver['provenance']['run_directory']).is_dir():
                raise RuntimeError('Solver evidence disappeared with extension job cleanup')
        outcomes.append({'contribution': contribution, 'status': result['status']})
        print(contribution + ': completed', flush=True)
    verification.write_text(json.dumps({'contract': 'spike/su2-extension-verification/v1',
        'checks': outcomes, 'passed': True, 'status': 'completed', 'board_geometry_used': False}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
