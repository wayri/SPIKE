# SPDX-License-Identifier: Apache-2.0
"""Source-bound SI08-S06 offline calibration/UQ foundation gate."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.solvers.signal_integrity.networks.one_port_calibration import calibrate_one_port
from examples.one_port_calibration.run_calibration import demonstration

MODULES = ('tests.python.test_one_port_calibration', 'tests.python.test_one_port_calibration_oracles')
SOURCES = ('python/spike_core/solvers/signal_integrity/networks/one_port_calibration.py', 'examples/one_port_calibration/run_calibration.py', 'tests/python/test_one_port_calibration.py', 'tests/python/test_one_port_calibration_oracles.py', 'scripts/verify_one_port_calibration.py', 'tests/python/test_one_port_calibration_evidence.py', 'docs/ONE_PORT_CALIBRATION.md', 'docs/validation/ONE_PORT_CALIBRATION_DERIVATION_20261024.md')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(suite):
    return sorted(name for test in suite for name in
                  (names(test) if isinstance(test, unittest.TestSuite) else [test.id()]))


def retained(root, record):
    if not isinstance(record, dict) or set(record) != {'path', 'sha256'}:
        raise ValueError('Invalid retained artifact binding')
    raw = record['path']
    if not isinstance(raw, str) or Path(raw).is_absolute():
        raise ValueError('Artifact must use a repository-relative path')
    path = (root/raw).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != record['sha256']:
        raise ValueError('Retained artifact missing, outside repository or changed')
    return path


def binding(path):
    return {'path': path.resolve().relative_to(ROOT).as_posix(), 'sha256': digest(path)}


def validate_receipt(receipt, root=ROOT):
    if (receipt.get('contract') != 'spike/one-port-calibration-evidence/v1'
            or receipt.get('stage_id') != 'SI08-S06' or receipt.get('status') != 'passed'
            or receipt.get('stage_complete') is not True
            or receipt.get('workflow') != 'offline_reference'
            or any(receipt.get(k) is not False for k in
                   ('family_complete', 'production_qualified', 'measurement_qualified', 'linearization_qualified'))):
        raise ValueError('Unsupported calibration evidence scope')
    expected = names(unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    if len(expected) != 19 or any('_FailedTest' in v for v in expected):
        raise ValueError('Calibration test inventory differs')
    source = receipt.get('sources_before')
    if not isinstance(source, dict) or set(source) != set(SOURCES) or source != receipt.get('sources_after'):
        raise ValueError('Calibration source coverage or drift')
    for name, value in source.items():
        retained(root, {'path': name, 'sha256': value})
    tests = receipt.get('tests', {})
    if (tests.get('names') != expected or tests.get('run') != len(expected)
            or any(tests.get(k) != [] for k in ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes'))):
        raise ValueError('Incomplete calibration test execution')
    log = retained(root, receipt.get('log')).read_text(encoding='utf-8')
    if f'Ran {len(expected)} tests' not in log or not log.rstrip().endswith('OK'):
        raise ValueError('Calibration log incomplete')
    capture = json.loads(retained(root, receipt.get('capture')).read_text(encoding='utf-8'))
    if not isinstance(capture, dict) or set(capture) != {'source', 'result'}:
        raise ValueError('Malformed calibration capture')
    result = capture['result']
    canonical = json.dumps(capture['source'], sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    if (capture['source'] != demonstration() or result.get('source_request') != capture['source']
            or result.get('input_digest') != hashlib.sha256(canonical.encode('utf-8')).hexdigest()
            or result.get('contract') != 'spike/one-port-calibration-result/v1'
            or result.get('model_status') != 'experimental'
            or result.get('uncertainty_method') != 'first_order_joint_real_covariance'
            or any(result.get(k) is not False for k in ('production_qualified', 'measurement_qualified', 'linearization_qualified'))):
        raise ValueError('Capture source identity or scope differs')
    network = result['derived_network']
    if (network['port_names'] != [capture['source']['port_name']]
            or network['frequencies_hz'] != [1e8, 1e9] or network['reference_impedance_ohm'] != 50
            or len(network['s_parameters']) != 2):
        raise ValueError('Capture named reference/grid differs')
    for sample, wanted in zip(network['s_parameters'], (.2+.3j, -.4+.1j)):
        if len(sample) != 1 or len(sample[0]) != 1:
            raise ValueError('Capture matrix dimensions differ')
        value = sample[0][0]
        error = abs(complex(value['real'], value['imag'])-wanted)
        if not np.isfinite(error) or error > 2e-12:
            raise ValueError('Independent example DUT reference differs')
    covariance = np.asarray(result['covariance'])
    sensitivity = np.asarray(result['sensitivity'])
    if (covariance.shape != (4, 4) or sensitivity.shape != (4, 28)
            or not np.isfinite(covariance).all() or not np.isfinite(sensitivity).all()):
        raise ValueError('Capture covariance/sensitivity incomplete')
    # Oracle checks live in independent tests; retain the complete capture and
    # ensure its covariance has not diverged from the stated local transform.
    expected_cov = sensitivity@np.asarray(capture['source']['covariance']['matrix'])@sensitivity.T
    if not np.allclose(covariance, expected_cov, atol=2e-22, rtol=1e-12):
        raise ValueError('Capture uncertainty transform differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('output', 'log', 'capture'):
        parser.add_argument('--'+option, type=Path, required=True)
    args = parser.parse_args()
    paths = [getattr(args, k).resolve() for k in ('output', 'log', 'capture')]
    if len(set(paths)) != 3 or any(p.exists() or not p.is_relative_to(ROOT) for p in paths):
        parser.error('Choose three fresh, distinct repository paths')
    for p in paths: p.parent.mkdir(parents=True, exist_ok=True)
    before = {n: digest(ROOT/n) for n in SOURCES}
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    expected = names(suite)
    stream = io.StringIO()
    executed = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    args.log.write_text(stream.getvalue(), encoding='utf-8')
    request = demonstration()
    capture = {'source': request, 'result': calibrate_one_port(request)}
    args.capture.write_text(json.dumps(capture, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    after = {n: digest(ROOT/n) for n in SOURCES}
    receipt = {'contract': 'spike/one-port-calibration-evidence/v1', 'stage_id': 'SI08-S06',
               'status': 'passed' if before == after and executed.wasSuccessful() and not executed.skipped else 'failed',
               'stage_complete': before == after and executed.wasSuccessful() and not executed.skipped,
               'workflow': 'offline_reference', 'family_complete': False, 'production_qualified': False,
               'measurement_qualified': False, 'linearization_qualified': False,
               'sources_before': before, 'sources_after': after,
               'runtime': {'python': platform.python_version(), 'numpy': np.__version__},
               'tests': {'names': expected, 'run': executed.testsRun,
                         **{key: [test.id() for test, _ in getattr(executed, attribute)] for key, attribute in
                            (('failures','failures'), ('errors','errors'), ('skipped','skipped'),
                             ('expected_failures','expectedFailures'))},
                         'unexpected_successes': [test.id() for test in executed.unexpectedSuccesses]},
               'log': binding(args.log), 'capture': binding(args.capture)}
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    validate_receipt(receipt)
    print(json.dumps({'status': 'passed', 'tests': executed.testsRun, 'stage_complete': True, 'family_complete': False}))


if __name__ == '__main__': main()
