# SPDX-License-Identifier: Apache-2.0
"""Source-bound native STEP scale execution and retained asset verification."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.component_step_scale import validate_facts
from scripts.parity_native_step_placement_gate import points

SOURCES = ('scripts/parity_step_scale_gate.py', 'python/spike_core/component_step_scale.py',
           'python/spike_core/freecad_scale_step.py', 'tests/python/test_component_step_scale.py',
           'python/spike_core/mcad_importer.py', 'python/spike_core/mcad_tessellation.py',
           'python/spike_core/sparselizard_process.py', 'scripts/parity_native_step_placement_gate.py',
           'benchmarks/parity-import/component-solid.step',
           'benchmarks/parity-import/step-scale/cylinder.step',
           'benchmarks/parity-import/step-scale/probe_native.py',
           'benchmarks/parity-import/step-scale/report.json',
           'benchmarks/parity-import/step-scale/cylinder_failure_evidence.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite():
    return unittest.defaultTestLoader.loadTestsFromName('tests.python.test_component_step_scale')


def names(tests):
    return sorted(name for test in tests for name in
                  (names(test) if isinstance(test, unittest.TestSuite) else [test.id()]))


def bound(root, name, sha):
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != sha:
        raise ValueError('STEP scale evidence stale or foreign')
    return path


def validate_receipt(receipt, root=ROOT):
    if (receipt.get('contract') != 'spike/step-scale-stage/v1' or receipt.get('stage_id') != 'WF01-S04C5'
            or receipt.get('status') != 'passed'
            or any(receipt.get(k) is not False for k in ('production_qualified', 'material_qualified', 'source_projection_enabled'))):
        raise ValueError('STEP scale stage scope/status differs')
    sources = receipt.get('sources', {})
    if set(sources) != set(SOURCES):
        raise ValueError('STEP scale source coverage differs')
    for name, sha in sources.items():
        bound(root, name, sha)
    result = receipt.get('tests', {})
    expected = names(suite())
    if (result.get('names') != expected or result.get('run') != len(expected)
            or any(result.get(k) != [] for k in ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes'))):
        raise ValueError('STEP scale execution incomplete or failed')
    bound(root, receipt['log'], receipt['log_sha256'])
    witness = json.loads(bound(root, receipt['native_evidence'], receipt['native_evidence_sha256']).read_text())
    cases = witness.get('cases', [])
    scales = ([2., 1., .5], [.5, 3., 2.], [1., 1., 1.])
    if len(cases) != 3 or [c['scale_xyz'] for c in cases] != list(scales):
        raise ValueError('STEP scale native cohort differs')
    import itertools
    source_sha = digest(root/'benchmarks/parity-import/component-solid.step')
    for case, scale in zip(cases, scales):
        data = base64.b64decode(case['geometry']['data_base64'], validate=True)
        sha = hashlib.sha256(data).hexdigest()
        if (sha != case['geometry']['sha256'] or case['source_sha256'] != source_sha
                or any(case[k] is not False for k in ('material_qualified', 'solver_ready', 'placement_scaled'))):
            raise ValueError('STEP scale asset digest/scope differs')
        validate_facts(case['native_facts'], source_sha, sha, scale)
        expected_points = [[p[i]*scale[i] for i in range(3)]
                           for p in itertools.product([0., 2.], [0., 3.], [0., 4.])]
        for key in ('scaled', 'roundtrip'):
            points(case['native_facts'][key]['vertices_mm'], expected_points)
    probe = json.loads((root/'benchmarks/parity-import/step-scale/report.json').read_text())
    if (probe['worker_sha256'] != sources['python/spike_core/freecad_scale_step.py']
            or len(probe['cases']) != 19 or sum(c['status'] == 'passed' for c in probe['cases']) != 6
            or sum(c['status'] == 'expected_rejection' for c in probe['cases']) != 13):
        raise ValueError('STEP scale native probe evidence differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'log', 'native-evidence'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log, args.native_evidence):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error('Outputs must be new repository paths')
        path.parent.mkdir(parents=True, exist_ok=True)
    sources = {n: digest(ROOT/n) for n in SOURCES}
    tests = suite()
    expected = names(tests)
    stream = io.StringIO()
    previous = os.environ.get('SPIKE_SCALE_TEST_EVIDENCE')
    os.environ['SPIKE_SCALE_TEST_EVIDENCE'] = str(args.native_evidence.resolve())
    try:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    finally:
        if previous is None:
            os.environ.pop('SPIKE_SCALE_TEST_EVIDENCE', None)
        else:
            os.environ['SPIKE_SCALE_TEST_EVIDENCE'] = previous
    args.log.write_text(stream.getvalue(), encoding='utf-8')
    receipt = {'contract': 'spike/step-scale-stage/v1', 'stage_id': 'WF01-S04C5',
               'status': 'passed' if result.wasSuccessful() and not result.skipped else 'failed',
               'production_qualified': False, 'material_qualified': False, 'source_projection_enabled': False,
               'sources': sources, 'tests': {'names': expected, 'run': result.testsRun,
               **{k: [t.id() for t, _ in getattr(result, attr)] for k, attr in
                  (('failures', 'failures'), ('errors', 'errors'), ('skipped', 'skipped'), ('expected_failures', 'expectedFailures'))},
               'unexpected_successes': [t.id() for t in result.unexpectedSuccesses]},
               'log': args.log.resolve().relative_to(ROOT).as_posix(), 'log_sha256': digest(args.log),
               'native_evidence': args.native_evidence.resolve().relative_to(ROOT).as_posix(),
               'native_evidence_sha256': digest(args.native_evidence) if args.native_evidence.exists() else None}
    args.output.write_text(json.dumps(receipt, indent=2)+'\n')
    validate_receipt(receipt)
    print(json.dumps({'stage_id': receipt['stage_id'], 'status': 'passed', 'tests': result.testsRun}))


if __name__ == '__main__':
    main()
