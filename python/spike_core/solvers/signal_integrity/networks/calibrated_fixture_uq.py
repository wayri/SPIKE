# SPDX-License-Identifier: Apache-2.0
"""Joint first-order calibration and coupled-fixture uncertainty composition.

Original governing derivative: docs/CALIBRATED_FIXTURE_UQ.md. No independence
assumption is introduced between calibration inputs and physical fixture data.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
import numpy as np
from . import multiport_calibration as calibration
from . import one_port_calibration as scalar
from . import sparameter_multiport_deembedding as fixture_solver


class CalibratedFixtureUQError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code='CALIBRATED_FIXTURE_UQ_'+code.upper()


def require(value,message,code='invalid_request'):
    if not value:raise CalibratedFixtureUQError(code,message)


def input_basis(calibration_request,fixture):
    ports=calibration_request['port_names'];calibration.port_set(ports)
    grid=calibration_request['frequencies_hz']
    require(isinstance(grid,list) and 1<=len(grid)<=2,'Supply 1..2 calibration frequencies','resource_limit')
    count=len(grid)
    result=calibration.input_basis(ports,count)
    n=2*len(ports)
    require(isinstance(fixture,dict) and isinstance(fixture.get('port_names'),list)
            and len(fixture['port_names'])==n,'Fixture must have 2N ports')
    return result+[f'fixture.f{k}.p{i}.p{j}.{part}' for k in range(count)
                   for i in range(n) for j in range(n) for part in ('real','imag')]


def realify(derivative):
    rows,columns=derivative.shape
    result=np.zeros((2*rows,2*columns))
    result[::2,::2]=derivative.real;result[::2,1::2]=-derivative.imag
    result[1::2,::2]=derivative.imag;result[1::2,1::2]=derivative.real
    return result


def removal_derivative(measured,fixture,external,internal,poll):
    n=len(external);eye=np.eye(n)
    ee=fixture[np.ix_(external,external)];ei=fixture[np.ix_(external,internal)]
    ie=fixture[np.ix_(internal,external)];ii=fixture[np.ix_(internal,internal)]
    first,_=scalar.solve(ei,measured-ee)
    xt,_=scalar.solve(ie.T,first.T);x=xt.T
    recovery=eye+x@ii
    calibration.screened(recovery)
    dut,_=scalar.solve(recovery,x)
    calibration.screened(eye-ii@dut)
    out=np.zeros((n*n,n*n+4*n*n),dtype=complex)
    for k in range(out.shape[1]):
        poll();dm=np.zeros((n,n),dtype=complex);df=np.zeros_like(fixture)
        if k<n*n:dm.flat[k]=1
        else:df.flat[k-n*n]=1
        de=df[np.ix_(external,external)];dei=df[np.ix_(external,internal)]
        die=df[np.ix_(internal,external)];dii=df[np.ix_(internal,internal)]
        rhs=dm-de-dei@x@ie-ei@x@die
        left,_=scalar.solve(ei,rhs);right,_=scalar.solve(ie.T,left.T);dx=right.T
        derivative,_=scalar.solve(recovery,dx@(eye-ii@dut)-x@dii@dut)
        out[:,k]=derivative.ravel()
    require(np.isfinite(out).all(),'Nonfinite joint sensitivity','numerical_failure')
    return realify(out)


def compose_calibrated_fixture(request,*,cancel_check=None):
    require(cancel_check is None or callable(cancel_check),'Cancellation hook must be callable')
    def poll():
        if cancel_check is None:return
        try:stopped=cancel_check()
        except Exception as error:raise CalibratedFixtureUQError('cancel_check_failed','Cancellation hook failed') from error
        require(not stopped,'Joint fixture study cancelled','cancelled')
    poll()
    try:
        size,chunks=0,[]
        for chunk in json.JSONEncoder(sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).iterencode(request):
            size+=len(chunk.encode('utf-8'))
            require(size<=8*1024*1024,'Request exceeds 8 MiB','resource_limit');chunks.append(chunk)
        encoded=''.join(chunks).encode('utf-8');source=json.loads(encoded)
        scalar.fields(source,('contract','calibration','fixture','external_ports','dut_ports','covariance'),'joint request')
        require(source['contract']=='spike/calibrated-fixture-uq-request/v1','Unsupported joint fixture contract')
        cal_request=source['calibration'];fixture=source['fixture']
        require(isinstance(cal_request,dict),'Calibration request required')
        basis=input_basis(cal_request,fixture)
        uncertainty=source['covariance'];scalar.fields(uncertainty,('basis','matrix','provenance'),'joint covariance')
        scalar.name(uncertainty['provenance']);require(uncertainty['basis']==basis,'Joint covariance basis differs')
        with np.errstate(over='raise',divide='raise',invalid='raise'):
            poll();cov=scalar.covariance(uncertainty['matrix'],len(basis))
            split=len(calibration.input_basis(cal_request['port_names'],len(cal_request['frequencies_hz'])))
            require(cal_request['covariance']['matrix']==[row[:split] for row in uncertainty['matrix'][:split]],
                    'Nested calibration covariance must equal joint leading block','covariance_mismatch')
            # Existing owners retain their original admission/physics and
            # classify cancellation using the original caller hook.
            cal=calibration.calibrate_multiport(cal_request,cancel_check=cancel_check)
            network=cal['derived_network']
            nominal=fixture_solver.deembed_multiport({'contract':fixture_solver.REQUEST_CONTRACT,
                'measured':network,'fixture':fixture,'external_ports':source['external_ports'],
                'dut_ports':source['dut_ports']},cancel_check=cancel_check)
            n=len(network['port_names']);count=len(network['frequencies_hz'])
            ei=[fixture['port_names'].index(p) for p in source['external_ports']]
            ii=[fixture['port_names'].index(p) for p in source['dut_ports']]
            measured=calibration.samples(network['s_parameters'],count,(n,n))
            fvalues=calibration.samples(fixture['s_parameters'],count,(2*n,2*n))
            chained=np.zeros((2*count*n*n,len(basis)))
            old_jac=np.asarray(cal['sensitivity'])
            for k in range(count):
                poll();local=removal_derivative(measured[k],fvalues[k],ei,ii,poll)
                rows=slice(2*k*n*n,2*(k+1)*n*n)
                chained[rows,:split]=local[:,:2*n*n]@old_jac[rows,:]
                start=split+8*k*n*n
                chained[rows,start:start+8*n*n]=local[:,2*n*n:]
            result_cov=chained@cov@chained.T;result_cov=(result_cov+result_cov.T)/2
            scalar.covariance(result_cov.tolist(),2*count*n*n)
        result={'contract':'spike/calibrated-fixture-uq-result/v1','model_status':'experimental',
                'production_qualified':False,'measurement_qualified':False,'linearization_qualified':False,
                'input_digest':sha256(encoded).hexdigest(),'source_request':source,
                'calibration_result':cal,'fixture_result':nominal,
                'derived_network':deepcopy(nominal['derived_network']),
                'sensitivity':chained.tolist(),'covariance':result_cov.tolist(),
                'output_basis':[f'f{k}.dut.s_parameters.p{i}.p{j}.{part}' for k in range(count)
                                for i in range(n) for j in range(n) for part in ('real','imag')],
                'uncertainty_method':'first_order_joint_real_covariance',
                'limitations':['Retains existing port-separable calibration and full supplied coupled physical fixture scope',
                               'One full joint covariance, including calibration/fixture correlations; no inferred independence',
                               'Nested calibration covariance is the matching leading block, never added a second time',
                               'Fixed known frequency/reference metadata; supplied budgets/provenance do not establish traceability',
                               'Local linearization only; physical measurement, coverage, human release and desktop qualification remain open']}
        require(len(json.dumps(result,allow_nan=False).encode('utf-8'))<=16*1024*1024,'Result exceeds 16 MiB','resource_limit')
        poll();return result
    except CalibratedFixtureUQError:raise
    except (calibration.MultiportCalibrationError,scalar.OnePortCalibrationError,fixture_solver.MultiportDeembeddingError) as error:
        code=error.code
        for prefix in ('MULTIPORT_CALIBRATION_','ONE_PORT_CALIBRATION_','MULTIPORT_DEEMBEDDING_'):
            code=code.removeprefix(prefix)
        raise CalibratedFixtureUQError(code,str(error)) from error
    except (ValueError,TypeError,KeyError,OverflowError,ArithmeticError,np.linalg.LinAlgError) as error:
        raise CalibratedFixtureUQError('invalid_request',str(error)) from error
