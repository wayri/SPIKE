# SPDX-License-Identifier: Apache-2.0
"""Source-bound SI08-I04 joint calibrated fixture uncertainty evidence."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import platform
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_one_port_calibration import digest, names, retained, binding
from python.spike_core.solvers.signal_integrity.networks.calibrated_fixture_uq import compose_calibrated_fixture
from examples.calibrated_fixture_uq.run_study import demonstration

MODULES = ('tests.python.test_calibrated_fixture_uq','tests.python.test_calibrated_fixture_uq_oracles')
SOURCES = ('python/spike_core/solvers/signal_integrity/networks/calibrated_fixture_uq.py', 'python/spike_core/solvers/signal_integrity/networks/multiport_calibration.py', 'python/spike_core/solvers/signal_integrity/networks/one_port_calibration.py', 'python/spike_core/solvers/signal_integrity/networks/sparameter_multiport_deembedding.py', 'python/spike_core/solvers/signal_integrity/networks/sparameter_sampling.py', 'examples/calibrated_fixture_uq/run_study.py', 'tests/python/test_calibrated_fixture_uq.py', 'tests/python/test_calibrated_fixture_uq_oracles.py', 'scripts/verify_calibrated_fixture_uq.py', 'docs/CALIBRATED_FIXTURE_UQ.md', 'docs/validation/CALIBRATED_FIXTURE_UQ_DERIVATION_20261025.md')
FLAGS = ('family_complete','production_qualified','measurement_qualified','linearization_qualified')


def validate_capture(capture):
    if not isinstance(capture,dict) or set(capture)!= {'source','result'}:
        raise ValueError('Malformed multiport capture')
    source,result = capture['source'],capture['result']
    if (source != demonstration() or result.get('source_request') != source
            or result.get('contract') != 'spike/calibrated-fixture-uq-result/v1'
            or result.get('model_status') != 'experimental'
            or any(result.get(k) is not False for k in FLAGS[1:])):
        raise ValueError('Multiport capture identity or scope differs')
    replay = compose_calibrated_fixture(source)
    # Exact source/contract maps, complete nested keys and a numerical replay
    # complement (not replace) the separately authored physical-wave oracles.
    def compare(actual,wanted):
        if type(wanted) is dict:
            if not isinstance(actual,dict) or set(actual)!=set(wanted):raise ValueError('Capture fields differ')
            for key in wanted:compare(actual[key],wanted[key])
        elif type(wanted) is list:
            if not isinstance(actual,list) or len(actual)!=len(wanted):raise ValueError('Capture shape differs')
            for a,b in zip(actual,wanted):compare(a,b)
        elif type(wanted) in (int,float):
            if type(actual) not in (int,float) or not np.isfinite(actual) or abs(actual-wanted)>2e-12*max(1.,abs(wanted)):
                raise ValueError('Capture numerical replay differs')
        elif type(actual) is not type(wanted) or actual!=wanted:raise ValueError('Capture semantic replay differs')
    compare(result,replay)
    wanted = np.array([[.1+.02j,.2-.03j,-.12+.07j],[.35+.04j,.15-.01j,.22j],[-.08j,.18+.06j,-.1]])
    actual=np.array([[[complex(v['real'],v['imag']) for v in row] for row in sample]
                     for sample in result['derived_network']['s_parameters']])
    if actual.shape!=(2,3,3) or not np.isfinite(actual).all() or not np.allclose(actual,[wanted,wanted],atol=2e-12,rtol=2e-12):
        raise ValueError('Independent multiport DUT reference differs')
    jac=np.asarray(result['sensitivity']);cov=np.asarray(result['covariance'])
    expected=jac@np.asarray(source['covariance']['matrix'])@jac.T
    if jac.shape!=(36,324) or cov.shape!=(36,36) or not np.allclose(cov,expected,atol=2e-22,rtol=1e-10):
        raise ValueError('Capture joint covariance differs')


def validate_receipt(receipt,root=ROOT):
    if (receipt.get('contract')!='spike/calibrated-fixture-uq-evidence/v1'
            or receipt.get('stage_id')!='SI08-I04' or receipt.get('status')!='passed'
            or receipt.get('stage_complete') is not True or receipt.get('workflow')!='offline_reference'
            or any(receipt.get(k) is not False for k in FLAGS)):
        raise ValueError('Unsupported multiport calibration evidence scope')
    expected=names(unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    if len(expected)!=13 or any('_FailedTest' in n for n in expected):raise ValueError('Test inventory differs')
    before=receipt.get('sources_before')
    if not isinstance(before,dict) or set(before)!=set(SOURCES) or before!=receipt.get('sources_after'):
        raise ValueError('Multiport source coverage or drift')
    for name,value in before.items():retained(root,{'path':name,'sha256':value})
    tests=receipt.get('tests',{})
    if (tests.get('names')!=expected or tests.get('run')!=len(expected)
            or any(tests.get(k)!=[] for k in ('failures','errors','skipped','expected_failures','unexpected_successes'))):
        raise ValueError('Incomplete multiport calibration execution')
    log=retained(root,receipt.get('log')).read_text(encoding='utf-8')
    if f'Ran {len(expected)} tests' not in log or not log.rstrip().endswith('OK'):raise ValueError('Execution log incomplete')
    validate_capture(json.loads(retained(root,receipt.get('capture')).read_text(encoding='utf-8')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ('output','log','capture'):parser.add_argument('--'+option,type=Path,required=True)
    args=parser.parse_args();paths=[getattr(args,k).resolve() for k in ('output','log','capture')]
    if len(set(paths))!=3 or any(p.exists() or not p.is_relative_to(ROOT) for p in paths):
        parser.error('Choose three fresh distinct repository paths')
    for p in paths:p.parent.mkdir(parents=True,exist_ok=True)
    before={n:digest(ROOT/n) for n in SOURCES}
    suite=unittest.defaultTestLoader.loadTestsFromNames(MODULES);expected=names(suite)
    stream=io.StringIO();executed=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    args.log.write_text(stream.getvalue(),encoding='utf-8')
    request=demonstration();capture={'source':request,'result':compose_calibrated_fixture(request)}
    args.capture.write_text(json.dumps(capture,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    after={n:digest(ROOT/n) for n in SOURCES}
    success=before==after and executed.wasSuccessful() and not executed.skipped
    receipt={'contract':'spike/calibrated-fixture-uq-evidence/v1','stage_id':'SI08-I04',
             'status':'passed' if success else 'failed','stage_complete':success,'workflow':'offline_reference',
             **{k:False for k in FLAGS},'sources_before':before,'sources_after':after,
             'runtime':{'python':platform.python_version(),'numpy':np.__version__},
             'tests':{'names':expected,'run':executed.testsRun,
                      **{k:[t.id() for t,_ in getattr(executed,a)] for k,a in
                         (('failures','failures'),('errors','errors'),('skipped','skipped'),('expected_failures','expectedFailures'))},
                      'unexpected_successes':[t.id() for t in executed.unexpectedSuccesses]},
             'log':binding(args.log),'capture':binding(args.capture)}
    args.output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    validate_receipt(receipt)
    print(json.dumps({'status':'passed','tests':executed.testsRun,'stage_complete':True,'family_complete':False}))


if __name__=='__main__':main()
