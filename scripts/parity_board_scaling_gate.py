# SPDX-License-Identifier: Apache-2.0
"""Source-bound scalable DC increment; never whole-board or full-stage promotion."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.parity_pisi_gate import bound, digest, names
from scripts.parity_board_volume_gate import MODULES as BASE_MODULES, SOURCES as BASE_SOURCES
from scripts.parity_board_volume_gate import build_report, validate_report

MODULES = (*BASE_MODULES, 'tests.python.test_dc_board_partition',
           'tests.python.test_dc_board_scaling', 'tests.python.test_dc_tetra_scaling',
           'tests.python.test_dc_geometry_scaling', 'tests.python.test_dc_refinement_evidence')
SOURCES = tuple(dict.fromkeys((*BASE_SOURCES, 'scripts/parity_board_scaling_gate.py',
    'scripts/benchmark_board_volume_scaling.py', 'python/spike_core/solvers/power_integrity/dc/dc_board_partition.py',
    'python/spike_core/solvers/power_integrity/dc/dc_tetra_sparse.py', 'python/spike_core/solvers/external_engines/sparselizard/sparselizard_process.py',
    'python/spike_core/numerical_runtime.py', 'python/spike_core/compute_policy.py',
    'tests/python/test_dc_board_partition.py', 'tests/python/test_dc_board_scaling.py',
    'tests/python/test_dc_tetra_scaling.py', 'docs/DC_BOARD_PARTITION.md',
    'tests/python/test_dc_geometry_scaling.py', 'docs/DC_GEOMETRY_SCALING.md',
    'scripts/verify_board_volume_refinement.py', 'tests/python/test_dc_refinement_evidence.py',
    'docs/DC_TETRA_SCALABLE.md', 'docs/DC_TETRA_SCALING_ORACLES.md')))


def require(condition, message):
    if not condition: raise ValueError(message)


def suite(): return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def validate_fields(report):
    import numpy as np
    from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc
    from tests.python.test_dc_tetra_rt0 import request, slab
    validate_report(report['baseline'])
    result = report['six_thousand_cell_fields']
    expected = request(slab(10), sigma=2., current=3.)
    expected['contract'] = 'spike/tetra-dc-rt0-scalable-request/v1'
    require(result['source_request'] == expected, 'Scalable analytical source differs')
    validate_tetra_dc(result)
    require(len(result['cells']) == 6000 and abs(result['joule_heat_w']-4.5) <= 4.5e-9,
            'Scalable analytical support/heat differs')
    for cell in result['cells']:
        require(np.max(np.abs(np.asarray(cell['vertex_density_a_m2'])-[3., 0., 0.])) <= 1e-8,
                'Scalable analytical field differs')


def validate_receipt(receipt, root=ROOT):
    require(receipt.get('contract') == 'spike/pi01-board-scaling-evidence/v1'
            and receipt.get('stage_id') == 'PI01-S02' and receipt.get('status') == 'passed'
            and receipt.get('stage_complete') is False and receipt.get('production_qualified') is False,
            'Scalable supplement cannot promote full stage')
    sources = receipt.get('sources_before', {})
    require(set(sources) == set(SOURCES) and sources == receipt.get('sources_after'), 'Scalable source coverage/drift differs')
    for name, sha in sources.items(): bound(root, name, sha)
    expected = names(suite()); execution = receipt.get('tests', {})
    require(len(expected) == 80 and execution.get('names') == expected and execution.get('run') == 80
            and all(execution.get(k) == [] for k in ('failures','errors','skipped','expected_failures','unexpected_successes')),
            'Scalable focused execution incomplete')
    log = bound(root, receipt['log'], receipt['log_sha256']).read_text(encoding='utf-8')
    require('Ran 80 tests' in log and log.rstrip().endswith('OK'), 'Scalable execution log differs')
    report = json.loads(bound(root, receipt['report'], receipt['report_sha256']).read_text(encoding='utf-8'))
    validate_fields(report)
    # Board attempts remain distinct from fixture qualification. Bind their raw
    # inputs/reports/fields without converting a blocked case into convergence.
    for artifact in receipt.get('board_artifacts', []):
        path = bound(root, artifact['path'], artifact['sha256'])
        if path.suffix == '.json':
            document = json.loads(path.read_text(encoding='utf-8'))
            if document.get('contract') == 'spike/selected-board-volume-refinement/v1':
                require(document.get('stage_complete') is False and document.get('production_qualified') is False
                        and document.get('full_board_pisi_ready') is False
                        and document.get('retained_fields_replayed') is True
                        and document.get('status') in ('passed_refinement_stability','needs_further_refinement'),
                        'Bound board refinement scope differs')
                for name, sha in document['artifacts'].items(): bound(root, name, sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output','log','report'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--board-artifact', action='append', type=Path, default=[])
    args = parser.parse_args(); paths = (args.output,args.log,args.report)
    require(len({p.resolve() for p in paths}) == 3, 'Outputs must differ')
    for p in paths:
        require(not p.exists() and p.resolve().is_relative_to(ROOT), 'Fresh repository outputs required')
        p.parent.mkdir(parents=True, exist_ok=True)
    before = {n:digest(ROOT/n) for n in SOURCES}
    artifacts = []
    for path in args.board_artifact:
        path = path.resolve(); require(path.is_relative_to(ROOT) and path.is_file(), 'Missing/foreign board artifact')
        artifacts.append({'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path)})
    tests = suite(); expected = names(tests); stream = io.StringIO()
    run = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding='utf-8')
    require(run.wasSuccessful() and not run.skipped and run.testsRun == 80, 'Scalable suite failed; log retained')
    from tests.python.test_dc_tetra_rt0 import request, slab
    from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0 import solve_tetra_dc
    raw = request(slab(10), sigma=2., current=3.); raw['contract']='spike/tetra-dc-rt0-scalable-request/v1'
    report = {'baseline':build_report(), 'six_thousand_cell_fields':solve_tetra_dc(raw)}
    args.report.write_text(json.dumps(report, separators=(',',':'), allow_nan=False)+'\n', encoding='utf-8')
    validate_fields(json.loads(args.report.read_text(encoding='utf-8')))
    after = {n:digest(ROOT/n) for n in SOURCES}
    receipt = {'contract':'spike/pi01-board-scaling-evidence/v1','stage_id':'PI01-S02','status':'passed',
        'stage_complete':False,'production_qualified':False,'sources_before':before,'sources_after':after,
        'tests':{'names':expected,'run':run.testsRun,'failures':[],'errors':[],'skipped':[],
                 'expected_failures':[],'unexpected_successes':[]},
        'log':args.log.resolve().relative_to(ROOT).as_posix(),'log_sha256':digest(args.log),
        'report':args.report.resolve().relative_to(ROOT).as_posix(),'report_sha256':digest(args.report),
        'board_artifacts':artifacts}
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8'); validate_receipt(receipt)
    print(json.dumps({'status':'passed','tests':80,'stage_complete':False}))


if __name__ == '__main__': main()
