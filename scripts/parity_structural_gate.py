# SPDX-License-Identifier: Apache-2.0
"""Run bounded structural numerical stages and retain source-bound test evidence."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGES = {'GP07-S01': (
    ('tests.python.test_assembly_tetra_structural', 'tests.python.test_assembly_thermomechanical',
     'tests.python.test_assembly_structural_contract'),
    ('python/spike_core/assembly_tetra_structural.py', 'python/spike_core/assembly_thermomechanical.py',
     'python/spike_core/service_structural.py', 'python/spike_core/service_assembly_field.py',
     'python/spike_core/service.py', 'python/spike_core/service_helpers.py',
     'python/spike_core/assembly_tetra_thermal.py', 'python/spike_core/assembly_tetra_thermal_validation.py',
     'python/spike_core/assembly_tetra_radiation.py', 'python/spike_core/tetra_aabb_candidates.py',
     'tests/python/test_assembly_tetra_structural.py', 'tests/python/test_assembly_thermomechanical.py',
     'tests/python/test_assembly_structural_contract.py', 'tests/python/test_assembly_tetra_thermal.py',
     'schemas/assembly-tetra-structural-request-v1.schema.json',
     'schemas/assembly-tetra-structural-result-v1.schema.json',
     'schemas/assembly-thermomechanical-request-v1.schema.json',
     'schemas/assembly-thermomechanical-result-v1.schema.json'))}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(tests):
    return sorted(name for test in tests for name in
                  (names(test) if isinstance(test, unittest.TestSuite) else [test.id()]))


def suite(stage):
    modules = STAGES[stage][0]
    return unittest.defaultTestLoader.loadTestsFromNames((modules,) if isinstance(modules, str) else modules)


def sources(stage):
    return ('scripts/parity_structural_gate.py', *STAGES[stage][1])


def bound(root, name, sha):
    if not isinstance(name, str):
        raise ValueError('Evidence path required')
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != sha:
        raise ValueError('structural evidence stale or foreign')
    return path


def validate_receipt(receipt, root=ROOT, stage=None):
    actual = receipt.get('stage_id')
    if (actual not in STAGES or (stage is not None and stage != actual)
            or receipt.get('contract') != 'spike/structural-numerical-stage/v1'
            or receipt.get('status') != 'passed' or receipt.get('production_qualified') is not False):
        raise ValueError('structural stage identity, status or scope differs')
    hashes = receipt.get('sources', {})
    if set(hashes) != set(sources(actual)):
        raise ValueError('structural stage source coverage differs')
    for name, sha in hashes.items():
        bound(root, name, sha)
    expected = names(suite(actual))
    result = receipt.get('tests', {})
    if (not expected or any('_FailedTest' in name for name in expected)
            or result.get('names') != expected or result.get('run') != len(expected)
            or any(result.get(k) != [] for k in ('failures', 'errors', 'skipped',
                                                'expected_failures', 'unexpected_successes'))):
        raise ValueError('structural execution incomplete or failed')
    log = bound(root, receipt.get('log'), receipt.get('log_sha256')).read_text(encoding='utf-8')
    if f'Ran {len(expected)} tests' not in log or not log.rstrip().endswith('OK'):
        raise ValueError('structural execution log incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=STAGES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error('Outputs must be new repository paths')
        path.parent.mkdir(parents=True, exist_ok=True)
    hashes = {name: digest(ROOT/name) for name in sources(args.stage)}
    tests = suite(args.stage); expected = names(tests)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding='utf-8')
    receipt = {'contract':'spike/structural-numerical-stage/v1', 'stage_id':args.stage,
               'status':'passed' if result.wasSuccessful() and not result.skipped else 'failed',
               'production_qualified':False, 'sources':hashes,
               'tests':{'names':expected, 'run':result.testsRun,
                        **{k:[t.id() for t,_ in getattr(result,a)] for k,a in
                           (('failures','failures'), ('errors','errors'), ('skipped','skipped'),
                            ('expected_failures','expectedFailures'))},
                        'unexpected_successes':[t.id() for t in result.unexpectedSuccesses]},
               'log':args.log.resolve().relative_to(ROOT).as_posix(), 'log_sha256':digest(args.log)}
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    validate_receipt(receipt, stage=args.stage)
    print(json.dumps({'stage_id':args.stage, 'status':'passed', 'tests':result.testsRun}))


if __name__ == '__main__':
    main()
