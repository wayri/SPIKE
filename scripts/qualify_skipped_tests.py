# SPDX-License-Identifier: Apache-2.0
"""Re-execute selected baseline skips with strict, source-bound evidence.

Use separate real interpreter/runtime profiles; this does not qualify a release.
Any skip, expected failure, source drift, or missing selected test fails admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GIT_EXECUTABLE = shutil.which('git')
SKIP = re.compile(r"^(?:\w+) \((test_\w+(?:\.\w+)+)\) \.\.\. skipped ")
CLASS_SKIP = re.compile(r"^setUpClass \((test_\w+\.\w+)\) \.\.\. skipped ")


def baseline_selectors(text):
    selectors = []
    for line in text.splitlines():
        match = SKIP.match(line) or CLASS_SKIP.match(line)
        if match:
            selectors.append('tests.python.' + match.group(1))
    if not selectors or len(selectors) != len(set(selectors)):
        raise ValueError('Baseline must contain unique verbose unittest skip records')
    return selectors


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read_baseline(path):
    resolved = path.resolve(strict=True)
    data = resolved.read_bytes()
    return resolved, baseline_selectors(data.decode('utf-8-sig')), hashlib.sha256(data).hexdigest()


def source_snapshot(root=ROOT):
    """Bind all version-controlled/nonignored project inputs, not only Python.

    Generated/build/runtime storage is deliberately excluded and must be bound
    explicitly with --bind when used. External installed runtimes are also
    explicit bindings, not implicitly approved release dependencies.
    """
    resolved_root = root.resolve()
    if GIT_EXECUTABLE is None:
        raise RuntimeError('A trusted Git executable must be available before test imports')
    listed = subprocess.run(
        [GIT_EXECUTABLE, 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root, capture_output=True, check=True,
    ).stdout
    names = sorted(set(value.decode('utf-8') for value in listed.split(b'\0') if value))
    excluded = {'build', 'output', 'artifacts', 'runtime'}
    snapshot = {}
    for name in names:
        relative = Path(name)
        if len(relative.parts) > 1 and (relative.parts[0] in excluded or
                relative.parts[0].startswith(('build-', 'build_', '.venv', '.local'))):
            continue
        path = root / relative
        if not path.resolve().is_relative_to(resolved_root):
            raise ValueError('Project input escapes snapshot root: ' + name)
        snapshot[name.replace('\\', '/')] = digest(path) if path.is_file() else None
    return snapshot


def runtime_snapshot():
    names = {'PATH', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'TEMP', 'TMP', 'USERPROFILE',
             'APPDATA', 'SPIKES_RENODE', 'SPIKE_STATE_HOME', 'SPIKE_PWM_TEST_LIBRARY'}
    controls = {key: value for key, value in os.environ.items() if key in names or
                key.startswith(('SPIKES_TEST_', 'SPIKE_FIXTURE_', 'SPIKES_BOARD_',
                                'SPIKE_EMERGE_', 'SPIKE_OPTYCAL_'))}
    tools = {sys.executable, getattr(sys, '_base_executable', sys.executable)}
    if GIT_EXECUTABLE:
        tools.add(GIT_EXECUTABLE)
    executables = {str(Path(name).resolve()): digest(Path(name)) for name in tools}
    return {'executable': sys.executable, 'version': sys.version,
            'platform': platform.platform(), 'executables': executables, 'controls': controls}


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


def admitted(result, expected, before, after):
    return (bool(expected) and len(expected) == len(set(expected))
            and result.testsRun == len(expected) and result.wasSuccessful()
            and not result.skipped and not result.expectedFailures
            and not result.unexpectedSuccesses and before == after)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--prefix', action='append', required=True,
                        help='Baseline test module/class prefix, without tests.python.')
    parser.add_argument('--bind', type=Path, action='append', default=[],
                        help='Additional actual runtime/fixture artifact to hash before/after')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    log = output.with_suffix('.log')
    if output.exists() or log.exists():
        parser.error('Evidence is immutable: choose new output and log paths')
    baseline, selectors, baseline_hash = read_baseline(args.baseline)
    selected = [name for name in selectors if any(
        name == 'tests.python.' + prefix or name.startswith('tests.python.' + prefix + '.')
        for prefix in args.prefix)]
    if not selected or any(not any(name == 'tests.python.' + prefix or
            name.startswith('tests.python.' + prefix + '.') for name in selected)
            for prefix in args.prefix):
        parser.error('Each prefix must select at least one baseline skip')
    sys.path.insert(0, str(ROOT))
    bound = [path.resolve(strict=True) for path in args.bind]
    before = {'sources': source_snapshot(), 'artifacts': {str(p): digest(p) for p in bound}}
    before['artifacts'][str(baseline)] = baseline_hash
    before['runtime'] = runtime_snapshot()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in selected)
    expected = list(test_ids(suite))
    output.parent.mkdir(parents=True, exist_ok=True)
    with log.open('x', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    after = {'sources': source_snapshot(), 'artifacts': {str(p): digest(p) for p in bound}}
    after['artifacts'][str(baseline)] = digest(baseline)
    after['runtime'] = runtime_snapshot()
    passed = admitted(result, expected, before, after)
    receipt = {
        'contract': 'spike/skip-reexecution-evidence/v1',
        'status': 'passed' if passed else 'failed', 'release_qualified': False,
        'baseline': str(baseline), 'selected_baseline_records': selected,
        'input_scope': 'All Git tracked/nonignored project inputs; excludes build/output/artifacts/runtime directories and build-/build_/.venv/.local prefixed directories. Used excluded/external artifacts require explicit --bind. Root files are not excluded by prefix.',
        'runtime': before['runtime'],
        'tests': {'expected': expected, 'run': result.testsRun,
                  'failures': [t.id() for t, _ in result.failures],
                  'errors': [t.id() for t, _ in result.errors],
                  'skipped': [(t.id(), reason) for t, reason in result.skipped],
                  'expected_failures': [t.id() for t, _ in result.expectedFailures],
                  'unexpected_successes': [t.id() for t in result.unexpectedSuccesses]},
        'before': before, 'after': after, 'log': str(log), 'log_sha256': digest(log),
    }
    with output.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'status': receipt['status'], 'baseline_records': len(selected),
                      'tests_run': result.testsRun, 'output': str(output)}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
