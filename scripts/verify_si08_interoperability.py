# SPDX-License-Identifier: Apache-2.0
"""Execute and bind finite offline SI08 interoperability/policy campaigns."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCES = (
    'python/spike_core/solvers/signal_integrity/networks/sparameters.py',
    'python/spike_core/solvers/signal_integrity/networks/sparameter_modes.py',
    'examples/si08_interoperability/run_campaign.py',
    'tests/python/test_si08_interoperability_campaign.py',
    'tests/python/test_si08_interoperability_oracles.py',
    'tests/python/test_si08_interoperability_evidence.py',
    'tests/python/test_sparameter_modes.py',
    'scripts/verify_si08_interoperability.py',
    'docs/SI08_INTEROPERABILITY_CAMPAIGN.md',
    'docs/validation/SI08_I01_INTEROP_ORACLE_20261025.md',
)
MODULES = ('tests.python.test_si08_interoperability_campaign',
           'tests.python.test_si08_interoperability_oracles',
           'tests.python.test_sparameter_modes')
FLAGS = ('physical_qualified', 'production_qualified', 'family_complete', 'native_visual_verified')
EXPECTED_TEST_COUNT = 22
POLICY_SOURCES = (
    'python/spike_core/solvers/signal_integrity/networks/sparameter_sampling.py',
    'python/spike_core/solvers/signal_integrity/networks/sparameter_rational.py',
    'python/spike_core/service.py',
    'python/spike_core/service_simulation_handlers.py',
    'python/spike_core/service_sparameter_processing.py',
    'python/spike_core/service_helpers.py',
    'python/spike_core/contract_catalog.py',
    'schemas/manifest.json',
    'schemas/sparameter-resampling-request-v1.schema.json',
    'schemas/sparameter-resampling-result-v1.schema.json',
    'examples/si08_causality_policy/run_campaign.py',
    'tests/python/test_si08_causality_policy_campaign.py',
    'tests/python/test_si08_causality_policy_oracles.py',
    'tests/python/test_si08_causality_policy_evidence.py',
    'tests/python/test_sparameter_sampling.py',
    'tests/python/test_sparameter_sampling_contract.py',
    'tests/python/test_sparameter_rational.py',
    'scripts/verify_si08_interoperability.py',
    'docs/SI08_CAUSALITY_POLICY_CAMPAIGN.md',
    'docs/validation/SI08_I02_CAUSALITY_ORACLE_20261025.md',
)
POLICY_MODULES = ('tests.python.test_si08_causality_policy_campaign',
                  'tests.python.test_si08_causality_policy_oracles',
                  'tests.python.test_sparameter_sampling',
                  'tests.python.test_sparameter_sampling_contract',
                  'tests.python.test_sparameter_rational')
POLICY_TEST_COUNT = 29


def config(point_id):
    if point_id == 'I01':
        return SOURCES, MODULES, EXPECTED_TEST_COUNT
    if point_id == 'I02':
        return POLICY_SOURCES, POLICY_MODULES, POLICY_TEST_COUNT
    raise ValueError('Unsupported campaign point')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite(point_id='I01'):
    return unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in config(point_id)[1])


def names(tests):
    result = []
    for test in tests:
        result.extend(names(test) if isinstance(test, unittest.TestSuite) else [test.id()])
    return result


def validate_receipt(receipt, root=ROOT, *, point_id='I01'):
    sources, _, expected_count = config(point_id)
    keys = {'contract', 'point_id', 'status', 'implementation_point_complete',
            'sources_before', 'sources_after', 'tests', 'log', *FLAGS}
    if (not isinstance(receipt, dict) or set(receipt) != keys
            or receipt['contract'] != 'spike/si08-interoperability-evidence/v1'
            or receipt['point_id'] != point_id or receipt['status'] != 'passed'
            or receipt['implementation_point_complete'] is not True
            or any(receipt[key] is not False for key in FLAGS)):
        raise ValueError('Unsupported I01 receipt identity/scope')
    before, after = receipt['sources_before'], receipt['sources_after']
    if not isinstance(before, dict) or set(before) != set(sources) or before != after:
        raise ValueError('I01 source coverage/stability differs')
    for name, value in before.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != value:
            raise ValueError('I01 source differs: '+name)
    expected = names(suite(point_id))
    if len(expected) != expected_count or any('_FailedTest' in name for name in expected):
        raise ValueError('I01 test inventory unavailable')
    tests = receipt['tests']
    outcomes = ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes')
    if (not isinstance(tests, dict) or set(tests) != {'names', 'run', *outcomes}
            or tests['names'] != expected or tests['run'] != len(expected)
            or any(tests[key] != [] for key in outcomes)):
        raise ValueError('I01 execution incomplete')
    log = receipt['log']
    if not isinstance(log, dict) or set(log) != {'path', 'sha256'} or not isinstance(log['path'], str):
        raise ValueError('I01 log binding invalid')
    path = (root/log['path']).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != log['sha256']:
        raise ValueError('I01 log differs')
    text = path.read_text(encoding='utf-8')
    if (f'Ran {len(expected)} tests' not in text or not text.rstrip().endswith('OK')
            or any(name.rsplit('.', 1)[-1] not in text for name in expected)):
        raise ValueError('I01 log incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--point', choices=('I01', 'I02'), default='I01')
    args = parser.parse_args()
    if args.output.resolve() == args.log.resolve():
        parser.error('Receipt and log must differ')
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error('Outputs must be new retained project files')
        path.parent.mkdir(parents=True, exist_ok=True)
    sources, _, expected_count = config(args.point)
    before = {name: digest(ROOT/name) for name in sources}
    tests = suite(args.point); expected = names(tests)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding='utf-8')
    after = {name: digest(ROOT/name) for name in sources}
    passed = (before == after and result.wasSuccessful() and not result.skipped
              and not result.expectedFailures and not result.unexpectedSuccesses
              and result.testsRun == len(expected) == expected_count
              and not any('_FailedTest' in name for name in expected))
    receipt = {'contract': 'spike/si08-interoperability-evidence/v1', 'point_id': args.point,
               'status': 'passed' if passed else 'failed', 'implementation_point_complete': passed,
               'sources_before': before, 'sources_after': after,
               'tests': {'names': expected, 'run': result.testsRun,
                         'failures': [t.id() for t, _ in result.failures],
                         'errors': [t.id() for t, _ in result.errors],
                         'skipped': [t.id() for t, _ in result.skipped],
                         'expected_failures': [t.id() for t, _ in result.expectedFailures],
                         'unexpected_successes': [t.id() for t in result.unexpectedSuccesses]},
               'log': {'path': args.log.resolve().relative_to(ROOT).as_posix(), 'sha256': digest(args.log)},
               **{flag: False for flag in FLAGS}}
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    if passed:
        validate_receipt(receipt, point_id=args.point)
    print(json.dumps({'status': receipt['status'], 'tests': result.testsRun, 'point': args.point}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
