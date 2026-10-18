# SPDX-License-Identifier: Apache-2.0
"""Execute and retain bounded component admission evidence, including native OCC."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = 'WF01-S04C2'
SOURCES = (
    'scripts/parity_component_admission_gate.py',
    'tests/python/test_thermal_component_promotion.py',
    'tests/python/test_assembly_thermal_meshing.py',
    'tests/python/test_project_assembly_field.py',
    'examples/assembly_field/run_examples.py',
    'python/spike_core/assembly_thermal_components.py',
    'python/spike_core/assembly_thermal_meshing.py',
    'python/spike_core/assembly_field_handoff.py',
    'python/spike_core/assembly_frames.py',
    'python/spike_core/gmsh_occ_runtime.py',
    'python/spike_core/gmsh_occ_mesher.py',
    'python/spike_core/service_project_thermal_mesh.py',
    'python/spike_core/project_package.py',
    'python/spike_core/project_member_metadata.py',
    'schemas/thermal-component-promotion-v1.schema.json',
    'schemas/assembly-thermal-mesh-assignments-v1.schema.json',
)
LIMITATION = ('Synthetic solids and supplied materials verify software admission only; '
              'native KiCad composition, conditioned package material laws and physics qualification remain open.')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_names(suite):
    return sorted(name for test in suite for name in
                  (test_names(test) if isinstance(test, unittest.TestSuite) else [test.id()]))


def expected_tests():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return unittest.defaultTestLoader.loadTestsFromName('tests.python.test_thermal_component_promotion')


def validate_receipt(receipt, root=ROOT):
    """Withhold Done on changed sources, failures, skips or incomplete native coverage."""
    if (receipt.get('contract') != 'spike/component-admission-evidence/v1'
            or receipt.get('stage_id') != STAGE or receipt.get('status') != 'passed'
            or receipt.get('production_qualified') is not False
            or receipt.get('material_qualified') is not False
            or receipt.get('limitation') != LIMITATION):
        raise ValueError('Component admission receipt status/scope differs')
    sources = receipt.get('sources', {})
    if set(sources) != set(SOURCES) or any(sources[name] != digest(root / name) for name in SOURCES):
        raise ValueError('Component admission source evidence is stale')
    names = test_names(expected_tests())
    result = receipt.get('tests', {})
    if (result.get('names') != names or result.get('run') != len(names)
            or any(result.get(key) != [] for key in ('failures', 'errors', 'skipped', 'unexpected_successes', 'expected_failures'))):
        raise ValueError('Component admission tests are incomplete or failed/skipped')
    runtime = receipt.get('runtime', {})
    if runtime.get('implementation') != 'CPython' or runtime.get('python', '').split('.')[:2] != ['3', '11']:
        raise ValueError('Component admission requires the admitted native runtime')
    log = root / receipt.get('log', '')
    if (not log.resolve().is_relative_to(root.resolve()) or not log.is_file()
            or digest(log) != receipt.get('log_sha256')):
        raise ValueError('Component admission execution log is stale')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error('Outputs must be new paths inside the repository')
        path.parent.mkdir(parents=True, exist_ok=True)
    suite = expected_tests()
    names = test_names(suite)
    before = {name: digest(ROOT / name) for name in SOURCES}
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    args.log.write_text(output.getvalue(), encoding='utf-8')
    receipt = {
        'contract': 'spike/component-admission-evidence/v1', 'stage_id': STAGE,
        'status': 'passed' if result.wasSuccessful() and not result.skipped else 'failed',
        'production_qualified': False, 'material_qualified': False, 'limitation': LIMITATION,
        'sources': before,
        'runtime': {'implementation': platform.python_implementation(), 'python': platform.python_version()},
        'tests': {'names': names, 'run': result.testsRun,
                  'failures': [t.id() for t, _ in result.failures],
                  'errors': [t.id() for t, _ in result.errors],
                  'skipped': [t.id() for t, _ in result.skipped],
                  'expected_failures': [t.id() for t, _ in result.expectedFailures],
                  'unexpected_successes': [t.id() for t in result.unexpectedSuccesses]},
        'log': args.log.resolve().relative_to(ROOT).as_posix(), 'log_sha256': digest(args.log),
    }
    # Source comparison after execution also catches concurrent edits during a run.
    args.output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    validate_receipt(receipt)
    print(json.dumps({'stage_id': STAGE, 'status': 'passed', 'tests': result.testsRun}))


if __name__ == '__main__':
    main()
