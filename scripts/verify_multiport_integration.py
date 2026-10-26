# SPDX-License-Identifier: Apache-2.0
"""Retain SI08-S05 worker/schema and headless desktop integration evidence."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_multiport_deembedding import digest, names

MODULES = ('tests.python.test_sparameter_multiport_deembedding',
           'tests.python.test_sparameter_multiport_deembedding_contract',
           'tests.python.test_multiport_deembedding_workflow')
SOURCES = ('scripts/verify_multiport_integration.py',
           'scripts/verify_multiport_deembedding.py',
           'python/spike_core/solvers/signal_integrity/networks/sparameter_multiport_deembedding.py',
           'python/spike_core/solvers/signal_integrity/networks/sparameter_sampling.py',
           'python/spike_core/service.py',
           'python/spike_core/service_simulation_handlers.py',
           'python/spike_core/service_sparameter_processing.py',
           'python/spike_core/service_helpers.py',
           'python/spike_core/contract_catalog.py',
           'schemas/manifest.json',
           'schemas/multiport-deembedding-request-v1.schema.json',
           'schemas/multiport-deembedding-result-v1.schema.json',
           'tests/python/test_sparameter_multiport_deembedding.py',
           'tests/python/test_sparameter_multiport_deembedding_contract.py',
           'tests/python/test_multiport_deembedding_workflow.py',
           'app/src/MultiportFixturePanel.tsx',
           'app/src/multiportFixtureModel.ts',
           'app/src/multiportFixture.css',
           'app/src/SParameterWorkbench.tsx',
           'app/src/workerBridge.ts',
           'app/scripts/test-multiport-fixture.mjs',
           'app/scripts/check-button-standard.mjs',
           'app/package.json',
           'app/src-tauri/src/lib.rs',
           'examples/multiport_deembedding/run_fixture.py',
           'docs/MULTIPORT_DEEMBEDDING.md',
           'docs/validation/MULTIPORT_DEEMBEDDING_ORACLES_20261024.md')
COMMANDS = (('node', ['node', 'scripts/test-multiport-fixture.mjs']),
            ('buttons', ['npm.cmd', 'run', 'test:button-standard']))
FALSE_FLAGS = ('stage_complete', 'family_complete', 'production_qualified', 'native_visual_verified')
TRUE_FLAGS = ('worker_schema_verified', 'headless_desktop_verified')


def retained_path(root, name):
    if not isinstance(name, str) or Path(name).is_absolute():
        raise ValueError('Evidence paths must be repository-relative')
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Missing or out-of-repository evidence')
    return path


def checked_log(root, name, expected_hash):
    path = retained_path(root, name)
    if digest(path) != expected_hash:
        raise ValueError('Stale integration log hash')
    return path.read_text(encoding='utf-8')


def validate_receipt(receipt, root=ROOT):
    expected = names(unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    if (receipt.get('contract') != 'spike/multiport-integration-evidence/v1'
            or receipt.get('stage_id') != 'SI08-S05' or receipt.get('status') != 'passed'
            or any(receipt.get(flag) is not False for flag in FALSE_FLAGS)
            or any(receipt.get(flag) is not True for flag in TRUE_FLAGS)
            or len(expected) != 13 or any('_FailedTest' in name for name in expected)):
        raise ValueError('Invalid or promoted integration evidence scope')
    before, after = receipt.get('sources_before'), receipt.get('sources_after')
    if not isinstance(before, dict) or set(before) != set(SOURCES) or before != after:
        raise ValueError('Integration source coverage or drift')
    for name, value in before.items():
        if digest(retained_path(root, name)) != value:
            raise ValueError('Stale integration source: ' + name)
    tests = receipt.get('tests', {})
    if (tests.get('names') != expected or tests.get('run') != len(expected)
            or any(tests.get(key) != [] for key in
                   ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes'))):
        raise ValueError('Failed, skipped or incomplete integration tests')
    log = checked_log(root, receipt.get('log'), receipt.get('log_sha256'))
    for name in expected:
        owner, method = name.rsplit('.', 1)
        if not any(f'{method} ({identity}) ... ok' in log for identity in (name, owner)):
            raise ValueError('Incomplete integration test log')
    if f'Ran {len(expected)} tests' not in log or not log.rstrip().endswith('OK'):
        raise ValueError('Incomplete integration test summary')
    commands = receipt.get('commands')
    if not isinstance(commands, list) or len(commands) != len(COMMANDS):
        raise ValueError('Missing integration commands')
    paths = [receipt.get('log')]
    for command, (label, argv) in zip(commands, COMMANDS):
        if (command.get('name') != label or command.get('argv') != argv
                or command.get('cwd') != 'app' or command.get('returncode') != 0
                or command.get('status') != 'passed' or command.get('completed') is not True):
            raise ValueError('Failed or incomplete integration command')
        text = checked_log(root, command.get('log'), command.get('log_sha256'))
        if not text.startswith(json.dumps({'argv': argv, 'cwd': 'app'}) + '\n'):
            raise ValueError('Integration command log identity mismatch')
        if not text.rstrip().endswith('RETURN_CODE=0'):
            raise ValueError('Incomplete integration command log')
        marker = ('Multiport fixture UI admission, worker lifecycle, cancellation, imports and immutable capture passed.'
                  if label == 'node' else 'SPIKE button/control standard passed for the desktop entrypoint and ')
        if marker not in text:
            raise ValueError('Integration command completion evidence missing')
        paths.append(command.get('log'))
    if len(set(paths)) != len(paths):
        raise ValueError('Integration logs must be distinct')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    output, log = args.output.resolve(), args.log.resolve()
    command_logs = [log.with_name(log.stem + '.' + label + log.suffix) for label, _ in COMMANDS]
    paths = [output, log, *command_logs]
    if len(set(paths)) != len(paths) or any(path.exists() or not path.is_relative_to(ROOT) for path in paths):
        parser.error('Choose distinct fresh repository receipt and log paths')
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT/name) for name in SOURCES}
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    expected = names(suite)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    with log.open('x', encoding='utf-8') as target:
        target.write(stream.getvalue())
    commands = []
    for (label, argv), path in zip(COMMANDS, command_logs):
        completed = True
        try:
            run = subprocess.run(argv, cwd=ROOT/'app', capture_output=True, text=True,
                                 timeout=120, check=False)
            code, stdout, stderr = run.returncode, run.stdout, run.stderr
        except (OSError, subprocess.TimeoutExpired) as error:
            completed, code, stdout, stderr = False, None, '', str(error)
        text = json.dumps({'argv': argv, 'cwd': 'app'}) + '\nSTDOUT:\n' + stdout + '\nSTDERR:\n' + stderr
        text += '\nRETURN_CODE=' + str(code) + '\n'
        with path.open('x', encoding='utf-8') as target:
            target.write(text)
        commands.append({'name': label, 'argv': argv, 'cwd': 'app', 'returncode': code,
                         'completed': completed, 'status': 'passed' if completed and code == 0 else 'failed',
                         'log': path.relative_to(ROOT).as_posix(), 'log_sha256': digest(path)})
    after = {name: digest(ROOT/name) for name in SOURCES}
    passed = (before == after and len(expected) == 13 and result.testsRun == 13
              and result.wasSuccessful() and not result.skipped and not result.expectedFailures
              and all(command['status'] == 'passed' for command in commands))
    receipt = {'contract': 'spike/multiport-integration-evidence/v1', 'stage_id': 'SI08-S05',
               'status': 'passed' if passed else 'failed', **{flag: False for flag in FALSE_FLAGS},
               **{flag: passed for flag in TRUE_FLAGS}, 'sources_before': before, 'sources_after': after,
               'tests': {'names': expected, 'run': result.testsRun,
                         **{key: [test.id() for test, _ in getattr(result, attribute)] for key, attribute in
                            (('failures', 'failures'), ('errors', 'errors'), ('skipped', 'skipped'),
                             ('expected_failures', 'expectedFailures'))},
                         'unexpected_successes': [test.id() for test in result.unexpectedSuccesses]},
               'commands': commands, 'log': log.relative_to(ROOT).as_posix(), 'log_sha256': digest(log)}
    with output.open('x', encoding='utf-8') as target:
        target.write(json.dumps(receipt, indent=2) + '\n')
    validate_receipt(receipt)
    print(json.dumps({'status': 'passed', 'tests': result.testsRun, 'stage_complete': False,
                      'native_visual_verified': False}))


if __name__ == '__main__':
    main()
