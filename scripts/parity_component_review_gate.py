# SPDX-License-Identifier: Apache-2.0
"""Execute source-bound placement-review tests against accepted native evidence."""
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

from scripts.parity_native_step_placement_gate import validate_receipt as validate_native

SOURCES = ('scripts/parity_component_review_gate.py', 'python/spike_core/component_placement_review.py',
           'tests/python/test_component_placement_review.py', 'python/spike_core/kicad_importer.py',
           'python/core/board_parser.py', 'python/core/kicad_model_sources.py',
           'python/spike_core/spider_v2.py', 'python/spike_core/spider_v2_schema.py',
           'python/spike_core/mcad_export_contract.py', 'python/spike_core/mcad_component_models.py',
           'python/spike_core/mcad_export_design.py')
NATIVE = 'docs/validation/parity/WF01-S04C3.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite():
    return unittest.defaultTestLoader.loadTestsFromName('tests.python.test_component_placement_review')


def names(tests):
    return sorted(name for test in tests for name in
                  (names(test) if isinstance(test, unittest.TestSuite) else [test.id()]))


def validate_receipt(receipt, root=ROOT):
    if (receipt.get('contract') != 'spike/component-review-stage/v1'
            or receipt.get('stage_id') != 'WF01-S04C4' or receipt.get('status') != 'passed'
            or any(receipt.get(k) is not False for k in ('production_qualified', 'material_qualified', 'source_projection_enabled'))):
        raise ValueError('Placement review stage status/scope differs')
    sources = receipt.get('sources', {})
    if set(sources) != set(SOURCES) or any(sources[n] != digest(root/n) for n in SOURCES):
        raise ValueError('Placement review source evidence stale')
    if receipt.get('native_receipt_sha256') != digest(root/NATIVE):
        raise ValueError('Placement review native evidence stale')
    validate_native(json.loads((root/NATIVE).read_text()), root)
    result = receipt.get('tests', {})
    expected = names(suite())
    if (result.get('names') != expected or result.get('run') != len(expected)
            or any(result.get(k) != [] for k in ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes'))):
        raise ValueError('Placement review execution incomplete or failed')
    path = (root/receipt.get('log', '')).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != receipt.get('log_sha256'):
        raise ValueError('Placement review execution log stale')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error('Outputs must be new repository paths')
        path.parent.mkdir(parents=True, exist_ok=True)
    validate_native(json.loads((ROOT/NATIVE).read_text()), ROOT)
    sources = {n: digest(ROOT/n) for n in SOURCES}
    tests = suite()
    expected = names(tests)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(tests)
    args.log.write_text(output.getvalue(), encoding='utf-8')
    receipt = {'contract': 'spike/component-review-stage/v1', 'stage_id': 'WF01-S04C4',
               'status': 'passed' if result.wasSuccessful() and not result.skipped else 'failed',
               'production_qualified': False, 'material_qualified': False, 'source_projection_enabled': False,
               'sources': sources, 'native_receipt_sha256': digest(ROOT/NATIVE),
               'tests': {'names': expected, 'run': result.testsRun,
                         **{key: [t.id() for t, _ in getattr(result, attr)] for key, attr in
                            (('failures', 'failures'), ('errors', 'errors'), ('skipped', 'skipped'), ('expected_failures', 'expectedFailures'))},
                         'unexpected_successes': [t.id() for t in result.unexpectedSuccesses]},
               'log': args.log.resolve().relative_to(ROOT).as_posix(), 'log_sha256': digest(args.log)}
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    validate_receipt(receipt)
    print(json.dumps({'stage_id': receipt['stage_id'], 'status': 'passed', 'tests': result.testsRun}))


if __name__ == '__main__':
    main()
