# SPDX-License-Identifier: Apache-2.0
"""Fixed CalculiX thermal extension entrypoint; no user scripts or solver decks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python.spike_core.calculix_thermal import prepare_calculix_thermal, run_calculix_thermal


def execute(request):
    if not isinstance(request, dict) or request.get('contract') != 'spike/extension/v1':
        raise ValueError('CALCULIX_EXTENSION: unsupported extension request.')
    contribution = request.get('contribution_id')
    if contribution not in ('calculix-thermal', 'calculix-thermal-prepare', 'calculix-thermal-run'):
        raise ValueError('CALCULIX_EXTENSION: unknown contribution.')
    context = request.get('context', {})
    if not isinstance(context, dict):
        raise ValueError('CALCULIX_EXTENSION: context must be an object.')
    params = context.get('parameters', {})
    if not isinstance(params, dict) or set(params) - {'request', 'problem', 'engine_options', 'operation'}:
        raise ValueError('CALCULIX_EXTENSION: only retained request/problem and bounded engine options are supported.')
    field_request, problem = params.get('request'), params.get('problem')
    operation = params.get('operation', 'run' if contribution == 'calculix-thermal-run' else 'prepare')
    if operation not in ('preflight', 'prepare', 'run'):
        raise ValueError('CALCULIX_EXTENSION: invalid operation.')
    if contribution != 'calculix-thermal-run' and operation == 'run':
        raise ValueError('CALCULIX_EXTENSION: execution requires calculix-thermal-run contribution.')
    if operation == 'run':
        result = run_calculix_thermal(field_request, problem, params.get('engine_options'))
        return {'contract': 'spike/extension-result/v1', 'status': 'completed',
                'title': 'CalculiX thermal result (experimental)',
                'data': {'operation': operation, 'status': 'completed', 'solved': True, 'result': result}}
    prepared = prepare_calculix_thermal(field_request, problem)
    return {'contract': 'spike/extension-result/v1',
            'status': 'completed' if prepared['status'] == 'ready_to_run' else 'completed_with_warnings',
            'title': 'CalculiX thermal preparation (experimental)',
            'data': {'operation': operation, 'status': prepared['status'], 'solved': False, 'case': prepared}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    source = Path(args.request)
    if source.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('CALCULIX_EXTENSION: request exceeds resource limit.')
    def reject_constant(value):
        raise ValueError('Invalid JSON constant: ' + value)
    payload = execute(json.loads(source.read_text(encoding='utf-8'), parse_constant=reject_constant))
    Path(args.result).write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
