# SPDX-License-Identifier: Apache-2.0
"""Run bounded PI/SI numerical stages and retain source-bound test evidence."""
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

STAGES = {
    'SI08-S01': ('tests.python.test_sparameter_modes',
                 ('python/spike_core/sparameter_modes.py', 'python/spike_core/sparameters.py',
                  'tests/python/test_sparameter_modes.py')),
    'PI04-S01': ('tests.python.test_pdn_transient_consistency',
                 ('python/spike_core/pdn_network.py', 'tests/python/test_pdn_transient_consistency.py')),
    'PI04-S02': (('tests.python.test_pdn_multiload', 'tests.python.test_pdn_multiload_contract'),
                 ('python/spike_core/pdn_network.py', 'tests/python/test_pdn_multiload.py',
                  'tests/python/test_pdn_multiload_contract.py', 'python/spike_core/service_pdn_network.py',
                  'schemas/pdn-network-request-v1.schema.json')),
    'PI02-S01': (('tests.python.test_pdn_dielectric_ac', 'tests.python.test_pdn_dielectric_ac_contract'),
                 ('python/spike_core/pdn_dielectric_ac.py', 'python/spike_core/pdn_electrostatic.py',
                  'python/spike_core/pdn_network.py', 'python/spike_core/assembly_tetra_thermal_validation.py',
                  'python/spike_core/tetra_aabb_candidates.py', 'python/spike_core/service_pdn_network.py',
                  'tests/python/test_pdn_dielectric_ac.py', 'tests/python/test_pdn_dielectric_ac_contract.py',
                  'tests/python/test_pdn_electrostatic.py', 'tests/python/test_assembly_tetra_thermal.py',
                  'schemas/pdn-dielectric-ac-request-v1.schema.json',
                  'schemas/pdn-dielectric-ac-result-v1.schema.json')),
}
STAGES['PI02-S02'] = (
    ('tests.python.test_pdn_admittance_reduction', 'tests.python.test_pdn_reduction_contract'),
    (*STAGES['PI02-S01'][1], 'python/spike_core/pdn_admittance_reduction.py',
     'tests/python/test_pdn_admittance_reduction.py', 'tests/python/test_pdn_reduction_contract.py',
     'schemas/pdn-admittance-reduction-request-v1.schema.json',
     'schemas/pdn-admittance-reduction-result-v1.schema.json'))
STAGES['PI02-S03'] = (
    ('tests.python.test_pdn_dielectric_thermal', 'tests.python.test_pdn_dielectric_thermal_contract'),
    (*STAGES['PI02-S01'][1], 'python/spike_core/pdn_dielectric_thermal.py',
     'python/spike_core/assembly_tetra_thermal.py', 'python/spike_core/assembly_tetra_radiation.py',
     'tests/python/test_pdn_dielectric_thermal.py', 'tests/python/test_pdn_dielectric_thermal_contract.py',
     'examples/pdn_dielectric_thermal/run_slab.py',
     'schemas/pdn-dielectric-thermal-request-v1.schema.json',
     'schemas/pdn-dielectric-thermal-result-v1.schema.json'))
STAGES['PI02-S04'] = (
    ('tests.python.test_pdn_dielectric_feedback', 'tests.python.test_pdn_dielectric_feedback_contract'),
    (*STAGES['PI02-S03'][1], 'python/spike_core/pdn_dielectric_feedback.py',
     'tests/python/test_pdn_dielectric_feedback.py', 'tests/python/test_pdn_dielectric_feedback_contract.py',
     'examples/pdn_dielectric_thermal/run_feedback.py',
     'schemas/pdn-dielectric-feedback-request-v1.schema.json',
     'schemas/pdn-dielectric-feedback-result-v1.schema.json'))
STAGES['PI03-S01'] = (
    ('tests.python.test_pdn_decap_corners', 'tests.python.test_pdn_decap_corners_contract'),
    ('python/spike_core/pdn_decap_corners.py', 'python/spike_core/pdn_network.py',
     'python/spike_core/service_pdn_network.py', 'tests/python/test_pdn_decap_corners.py',
     'tests/python/test_pdn_decap_corners_contract.py',
     'examples/pdn_decap_corners/run_corners.py',
     'schemas/pdn-network-request-v1.schema.json',
     'schemas/pdn-decap-corners-request-v1.schema.json',
     'schemas/pdn-decap-corners-result-v1.schema.json'))
STAGES['PI03-S02'] = (
    ('tests.python.test_pdn_decap_selection', 'tests.python.test_pdn_decap_selection_contract'),
    (*STAGES['PI03-S01'][1], 'python/spike_core/pdn_decap_selection.py',
     'tests/python/test_pdn_decap_selection.py', 'tests/python/test_pdn_decap_selection_contract.py',
     'schemas/pdn-decap-selection-request-v1.schema.json',
     'schemas/pdn-decap-selection-result-v1.schema.json'))
STAGES['SI08-S02'] = (
    ('tests.python.test_sparameter_deembedding', 'tests.python.test_sparameter_deembedding_contract'),
    ('python/spike_core/sparameter_deembedding.py',
     'python/spike_core/service_sparameter_processing.py',
     'python/spike_core/service_simulation_handlers.py',
     'tests/python/test_sparameter_deembedding.py',
     'tests/python/test_sparameter_deembedding_contract.py',
     'schemas/two-port-deembedding-request-v1.schema.json',
     'schemas/two-port-deembedding-result-v1.schema.json'))
STAGES['SI08-S03'] = (
    ('tests.python.test_sparameter_sampling', 'tests.python.test_sparameter_sampling_contract'),
    ('python/spike_core/sparameter_sampling.py',
     'python/spike_core/service_sparameter_processing.py',
     'python/spike_core/service_simulation_handlers.py',
     'tests/python/test_sparameter_sampling.py', 'tests/python/test_sparameter_sampling_contract.py',
     'schemas/sparameter-resampling-request-v1.schema.json',
     'schemas/sparameter-resampling-result-v1.schema.json'))
STAGES['SI08-S04'] = (
    ('tests.python.test_sparameter_rational', 'tests.python.test_sparameter_rational_contract'),
    ('python/spike_core/sparameter_rational.py', 'python/spike_core/sparameter_sampling.py',
     'python/spike_core/service_sparameter_processing.py',
     'python/spike_core/service_simulation_handlers.py',
     'tests/python/test_sparameter_rational.py', 'tests/python/test_sparameter_rational_contract.py',
     'schemas/sparameter-rational-fit-request-v1.schema.json',
     'schemas/sparameter-rational-fit-result-v1.schema.json'))


STAGES['SI07-S01'] = (
    ('tests.python.test_sparameter_transient', 'tests.python.test_sparameter_transient_contract'),
    ('python/spike_core/sparameter_transient.py', 'python/spike_core/sparameter_rational.py',
     'python/spike_core/sparameter_sampling.py',
     'python/spike_core/service_sparameter_processing.py',
     'python/spike_core/service_simulation_handlers.py',
     'tests/python/test_sparameter_transient.py', 'tests/python/test_sparameter_transient_contract.py',
     'schemas/sparameter-rational-fit-request-v1.schema.json',
     'schemas/sparameter-rational-fit-result-v1.schema.json',
     'schemas/rational-network-transient-request-v1.schema.json',
     'schemas/rational-network-transient-result-v1.schema.json'))


STAGES['SI07-S02'] = (
    ('tests.python.test_sparameter_terminated', 'tests.python.test_sparameter_terminated_contract'),
    ('python/spike_core/sparameter_terminated.py', 'python/spike_core/sparameter_transient.py',
     'python/spike_core/sparameter_rational.py', 'python/spike_core/sparameter_sampling.py',
     'python/spike_core/service_sparameter_processing.py',
     'python/spike_core/service_simulation_handlers.py',
     'tests/python/test_sparameter_terminated.py', 'tests/python/test_sparameter_terminated_contract.py',
     'schemas/sparameter-rational-fit-request-v1.schema.json',
     'schemas/sparameter-rational-fit-result-v1.schema.json',
     'schemas/terminated-network-transient-request-v1.schema.json',
     'schemas/terminated-network-transient-result-v1.schema.json'))


STAGES['SI07-S03'] = (
    ('tests.python.test_sparameter_inductive_terminated', 'tests.python.test_sparameter_inductive_contract'),
    (*STAGES['SI07-S02'][1], 'python/spike_core/sparameter_inductive_terminated.py',
     'tests/python/test_sparameter_inductive_terminated.py',
     'tests/python/test_sparameter_inductive_contract.py', 'tests/python/test_sparameter_transient.py',
     'examples/inductive_network_transient/run_rlc.py',
     'schemas/inductive-network-transient-request-v1.schema.json',
     'schemas/inductive-network-transient-result-v1.schema.json',
     'docs/INDUCTIVE_NETWORK_TRANSIENT.md'))


STAGES['SI07-S04'] = (
    ('tests.python.test_sparameter_capacitive_terminated', 'tests.python.test_sparameter_capacitive_contract'),
    (*STAGES['SI07-S02'][1], 'python/spike_core/sparameter_capacitive_terminated.py',
     'tests/python/test_sparameter_capacitive_terminated.py',
     'tests/python/test_sparameter_capacitive_contract.py', 'tests/python/test_sparameter_transient.py',
     'examples/capacitive_network_transient/run_rc.py',
     'schemas/capacitive-network-transient-request-v1.schema.json',
     'schemas/capacitive-network-transient-result-v1.schema.json',
     'docs/CAPACITIVE_NETWORK_TRANSIENT.md'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(tests):
    return sorted(name for test in tests for name in
                  (names(test) if isinstance(test, unittest.TestSuite) else [test.id()]))


def suite(stage):
    modules = STAGES[stage][0]
    return unittest.defaultTestLoader.loadTestsFromNames((modules,) if isinstance(modules, str) else modules)


def sources(stage):
    return ('scripts/parity_pisi_gate.py', *STAGES[stage][1])


def bound(root, name, sha):
    if not isinstance(name, str):
        raise ValueError('Evidence path required')
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != sha:
        raise ValueError('PI/SI evidence stale or foreign')
    return path


def validate_receipt(receipt, root=ROOT, stage=None):
    actual = receipt.get('stage_id')
    if (actual not in STAGES or (stage is not None and stage != actual)
            or receipt.get('contract') != 'spike/pisi-numerical-stage/v1'
            or receipt.get('status') != 'passed' or receipt.get('production_qualified') is not False):
        raise ValueError('PI/SI stage identity, status or scope differs')
    hashes = receipt.get('sources', {})
    if set(hashes) != set(sources(actual)):
        raise ValueError('PI/SI stage source coverage differs')
    for name, sha in hashes.items():
        bound(root, name, sha)
    expected = names(suite(actual))
    result = receipt.get('tests', {})
    if (not expected or any('_FailedTest' in name for name in expected)
            or result.get('names') != expected or result.get('run') != len(expected)
            or any(result.get(k) != [] for k in ('failures', 'errors', 'skipped',
                                                'expected_failures', 'unexpected_successes'))):
        raise ValueError('PI/SI execution incomplete or failed')
    log = bound(root, receipt.get('log'), receipt.get('log_sha256')).read_text(encoding='utf-8')
    if f'Ran {len(expected)} tests' not in log or not log.rstrip().endswith('OK'):
        raise ValueError('PI/SI execution log incomplete')


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
    receipt = {'contract':'spike/pisi-numerical-stage/v1', 'stage_id':args.stage,
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
