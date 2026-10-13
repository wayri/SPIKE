# SPDX-License-Identifier: Apache-2.0
"""Xyce suite entrypoint for SPIKE's versioned process extension SDK."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from extensions.xyce_suite.cases import artifacts, case_path, prepare, regular, verify_case
from extensions.xyce_suite.runner import budgets, inspect_case, run, runtime

ACTIONS = {'xyce-circuit': 'prepare', 'xyce-validate': 'validate', 'xyce-run': 'run',
           'xyce-inspect': 'inspect', 'xyce-cancel': 'cancel'}


def execute(request):
    if not isinstance(request, dict) or request.get('contract') != 'spike/extension/v1':
        raise ValueError('XYCE_EXTENSION: unsupported request contract.')
    action = request.get('contribution_id')
    if action not in ACTIONS:
        raise ValueError('XYCE_EXTENSION: unknown contribution.')
    context = request.get('context', {})
    params = context.get('parameters', {}) if isinstance(context, dict) else None
    if not isinstance(params, dict) or set(params) - {'operation', 'netlist', 'libraries', 'engine_options', 'case_id'}:
        raise ValueError('XYCE_EXTENSION: unknown or malformed parameters.')
    operation = params.get('operation', ACTIONS[action])
    if operation not in {'preflight', 'prepare', 'validate', 'run', 'inspect', 'cancel'}:
        raise ValueError('XYCE_EXTENSION: unsupported operation.')
    if operation != ACTIONS[action] and not (action == 'xyce-circuit' and operation == 'preflight'):
        raise ValueError('XYCE_EXTENSION: operation must match contribution.')
    data = {'engine': 'xyce', 'operation': operation, 'status': 'failed', 'solved': False,
            'model_status': 'experimental', 'production_qualified': False,
            'diagnostics': [], 'waveforms': [], 'artifacts': []}
    try:
        options = params.get('engine_options', {})
        selected = runtime(options)
        budgets(options)
        data['runtime'] = selected
        if operation == 'preflight':
            data['status'] = 'available' if selected['available'] else 'runtime_unavailable'
        else:
            if params.get('case_id') is not None:
                if 'netlist' in params or 'libraries' in params:
                    raise ValueError('XYCE_CASE: choose a prepared case or new input text, not both.')
                path = case_path(params['case_id'])
                verify_case(path)
            else:
                if operation in {'inspect', 'cancel'}:
                    raise ValueError('XYCE_CASE: inspect/cancel requires case_id.')
                path = prepare(params.get('netlist'), params.get('libraries', []))
            data['case_id'] = path.name
            if operation == 'prepare':
                data.update(status='prepared', artifacts=artifacts(path))
            elif operation == 'inspect':
                data.update(inspect_case(path))
            elif operation == 'cancel':
                marker = path / 'cancel.flag'
                regular(marker)
                marker.write_text('cancel', encoding='ascii')
                data['status'] = 'cancellation_requested'
            elif not selected['available']:
                data['status'] = 'runtime_unavailable'
                data['diagnostics'].append({'code': 'XYCE_RUNTIME_MISSING', 'severity': 'error',
                    'message': 'Select a separately installed native Xyce executable; no solver data was produced.'})
            else:
                data.update(run(path, selected, options, operation == 'validate'))
    except (ValueError, OSError, RuntimeError) as error:
        data.update(status='failed', solved=False, waveforms=[])
        data['diagnostics'].append({'code': 'XYCE_ADMISSION_OR_RUN', 'severity': 'error', 'message': str(error)[:2000]})
    success = data['status'] in {'prepared', 'available', 'validated_syntax', 'completed', 'cancellation_requested'}
    return {'contract': 'spike/extension-result/v1',
            'status': 'completed' if success else 'completed_with_warnings',
            'title': 'Xyce circuit (experimental)', 'data': data}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    source = Path(args.request)
    if source.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('XYCE_EXTENSION: request exceeds 4 MiB.')
    def reject_constant(value):
        raise ValueError('XYCE_EXTENSION: nonfinite JSON constant ' + value)
    result = execute(json.loads(source.read_text(encoding='utf-8'), parse_constant=reject_constant))
    encoded = json.dumps(result, allow_nan=False)
    if len(encoded.encode('utf-8')) > 8 * 1024 * 1024:
        result['data'].update(status='result_limit', solved=False, waveforms=[])
        result['data']['diagnostics'] = [{'code': 'XYCE_RESULT_LIMIT', 'severity': 'error',
                                       'message': 'Solver data exceeds 8 MiB transport budget; reduce printed vectors/time points.'}]
        result['status'] = 'completed_with_warnings'
        encoded = json.dumps(result, allow_nan=False)
    Path(args.result).write_text(encoded, encoding='utf-8')


if __name__ == '__main__':
    main()
