# SPDX-License-Identifier: Apache-2.0
"""Execute bake-then-rigid proposals and compare to retained native STEP solids."""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.parity_step_scale_gate import digest, names, bound, validate_receipt as validate_scale
from scripts.parity_component_review_gate import validate_receipt as validate_unit_review
from scripts.parity_native_step_placement_gate import points
from python.spike_core.component_step_scale import validate_facts
from python.spike_core.mcad_export_contract import rigid_transform

SOURCES = ('scripts/parity_scaled_review_gate.py', 'python/spike_core/scaled_component_review.py',
           'python/spike_core/component_placement_review.py', 'tests/python/test_scaled_component_review.py',
           'tests/python/test_component_placement_review.py', 'scripts/parity_step_scale_gate.py',
           'docs/validation/parity/WF01-S04C4.json', 'docs/validation/parity/WF01-S04C5.json',
           'docs/validation/parity/WF01-S04C3-native-step.json')


def suite():
    return unittest.defaultTestLoader.loadTestsFromName('tests.python.test_scaled_component_review')


def validate_receipt(receipt, root=ROOT):
    if (receipt.get('contract') != 'spike/scaled-review-stage/v1' or receipt.get('stage_id') != 'WF01-S04C6'
            or receipt.get('status') != 'passed'
            or any(receipt.get(k) is not False for k in ('production_qualified', 'material_qualified', 'source_projection_enabled'))):
        raise ValueError('Scaled review stage scope/status differs')
    sources = receipt.get('sources', {})
    if set(sources) != set(SOURCES):
        raise ValueError('Scaled review source coverage differs')
    for name, sha in sources.items():
        bound(root, name, sha)
    validate_scale(json.loads((root/'docs/validation/parity/WF01-S04C5.json').read_text()), root)
    validate_unit_review(json.loads((root/'docs/validation/parity/WF01-S04C4.json').read_text()), root)
    result = receipt.get('tests', {})
    expected = names(suite())
    if (result.get('names') != expected or result.get('run') != len(expected)
            or any(result.get(k) != [] for k in ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes'))):
        raise ValueError('Scaled review execution incomplete or failed')
    bound(root, receipt['log'], receipt['log_sha256'])
    records = json.loads(bound(root, receipt['native_evidence'], receipt['native_evidence_sha256']).read_text())['cases']
    reference = json.loads((root/'docs/validation/parity/WF01-S04C3-native-step.json').read_text())
    native = {c['name']: c for c in reference['cases'] if c['model_index'] == 0}
    if len(records) != 4 or {r['name'] for r in records} != set(native):
        raise ValueError('Scaled review native coverage differs')
    source_sha = digest(root/'benchmarks/parity-import/component-solid.step')
    for record in records:
        proposal = record['proposal']
        asset = proposal['derived_asset']
        data = base64.b64decode(asset['geometry']['data_base64'], validate=True)
        import hashlib
        sha = hashlib.sha256(data).hexdigest()
        if (sha != asset['geometry']['sha256'] or proposal['source_sha256'] != source_sha
                or proposal['status'] != 'review_required' or proposal['derived_model_registration_required'] is not True
                or any(proposal[k] is not False for k in ('solver_ready', 'material_qualified', 'source_projection_enabled'))):
            raise ValueError('Scaled review asset provenance/scope differs')
        validate_facts(asset['native_facts'], source_sha, sha, [2., 1., .5])
        matrix = np.array(rigid_transform(proposal['model_to_board_mm'])).reshape(4,4)
        local = asset['native_facts']['roundtrip']['vertices_mm']
        world = (matrix @ np.array([p+[1.] for p in local]).T).T[:,:3].tolist()
        points(world, native[record['name']]['spike_vertices_mm'])
        points(record['positioned_vertices_mm'], world)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output','log','native-evidence'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    for path in (args.output,args.log,args.native_evidence):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error('Outputs must be new repository paths')
        path.parent.mkdir(parents=True,exist_ok=True)
    sources = {n:digest(ROOT/n) for n in SOURCES}
    tests = suite()
    expected = names(tests)
    stream = io.StringIO()
    previous = os.environ.get('SPIKE_SCALED_REVIEW_EVIDENCE')
    os.environ['SPIKE_SCALED_REVIEW_EVIDENCE'] = str(args.native_evidence.resolve())
    try:
        result = unittest.TextTestRunner(stream=stream,verbosity=2).run(tests)
    finally:
        if previous is None: os.environ.pop('SPIKE_SCALED_REVIEW_EVIDENCE',None)
        else: os.environ['SPIKE_SCALED_REVIEW_EVIDENCE'] = previous
    args.log.write_text(stream.getvalue(),encoding='utf-8')
    receipt = {'contract':'spike/scaled-review-stage/v1','stage_id':'WF01-S04C6',
               'status':'passed' if result.wasSuccessful() and not result.skipped else 'failed',
               'production_qualified':False,'material_qualified':False,'source_projection_enabled':False,
               'sources':sources,'tests':{'names':expected,'run':result.testsRun,
               **{k:[t.id() for t,_ in getattr(result,a)] for k,a in
                  (('failures','failures'),('errors','errors'),('skipped','skipped'),('expected_failures','expectedFailures'))},
               'unexpected_successes':[t.id() for t in result.unexpectedSuccesses]},
               'log':args.log.resolve().relative_to(ROOT).as_posix(),'log_sha256':digest(args.log),
               'native_evidence':args.native_evidence.resolve().relative_to(ROOT).as_posix(),
               'native_evidence_sha256':digest(args.native_evidence) if args.native_evidence.exists() else None}
    args.output.write_text(json.dumps(receipt,indent=2)+'\n')
    validate_receipt(receipt)
    print(json.dumps({'stage_id':receipt['stage_id'],'status':'passed','tests':result.testsRun}))


if __name__ == '__main__':
    main()
