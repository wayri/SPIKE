# SPDX-License-Identifier: Apache-2.0
"""Offline port-separable known-standard calibration and joint first-order UQ.

Original derivation and primary sources: docs/MULTIPORT_CALIBRATION.md.
No arbitrary crosstalk, switch acquisition or physical/release qualification.
"""
from __future__ import annotations
import json
from hashlib import sha256
import numpy as np
from . import one_port_calibration as scalar

REQUEST = 'spike/multiport-calibration-request/v1'
RESULT = 'spike/multiport-calibration-result/v1'


class MultiportCalibrationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = 'MULTIPORT_CALIBRATION_'+code.upper()


def require(value, message, code='invalid_request'):
    if not value: raise MultiportCalibrationError(code, message)


def port_set(names):
    require(isinstance(names, list) and 2 <= len(names) <= 4, 'Supply 2..4 named ports', 'resource_limit')
    for name in names: scalar.name(name, 80)
    require(len(set(names)) == len(names), 'Duplicate port identity')


def input_basis(port_names, count):
    port_set(port_names)
    require(type(count) is int and 1 <= count <= 2, 'Supply 1..2 frequencies', 'resource_limit')
    n = len(port_names)
    local = [f'reflection_standards{j}.{kind}.p{i}' for kind in ('reflection', 'measured')
             for j in range(3) for i in range(n)]
    local += [f'{owner}.{kind}.p{i}.p{j}' for owner, kind in
              (('coupling_standard','s_parameters'), ('coupling_standard','measured'), ('dut','measured'))
              for i in range(n) for j in range(n)]
    return [f'f{k}.{label}.{part}' for k in range(count) for label in local for part in ('real', 'imag')]


def samples(raw, count, shape):
    require(isinstance(raw, list) and len(raw) == count, 'Frequency sample count differs')
    def parse(value, dimensions):
        if not dimensions:
            scalar.fields(value, ('real','imag'), 'complex entry')
            return complex(scalar.number(value['real']), scalar.number(value['imag']))
        require(isinstance(value, list) and len(value) == dimensions[0], 'Sample shape differs')
        return [parse(v, dimensions[1:]) for v in value]
    return np.asarray([parse(v, shape) for v in raw], dtype=complex)


def records(values):
    if np.ndim(values) == 0: return scalar.pair(values)
    return [records(v) for v in values]


def screened(matrix):
    spectrum = np.linalg.svd(matrix, compute_uv=False)
    require(np.isfinite(spectrum).all() and spectrum[-1] > 0,
            'Singular calibration feedback operator', 'ill_conditioned')
    condition = float(spectrum[0]/spectrum[-1])
    require(np.isfinite(condition) and condition <= 1e8, 'Matrix singular or condition exceeds 1e8', 'ill_conditioned')
    require(spectrum[-1]/max(1.,float(spectrum[0])) >= 1e-10,
            'Calibration feedback operator near a pole', 'representation_limit')
    return condition


def gains(values):
    magnitudes = abs(values)
    require(np.isfinite(values).all() and np.min(magnitudes) > 0
            and np.max(magnitudes)/np.min(magnitudes) <= 1e8,
            'Directional gains unresolved or magnitude ratio exceeds 1e8', 'representation_limit')


def local_calibration(g, m, coupling, measured_coupling, measured_dut, reference, poll):
    n = len(measured_dut)
    length = 6*n+3*n*n
    d, t, v = (np.zeros(n, dtype=complex) for _ in range(3))
    # Each column is a holomorphic complex input direction in the explicit
    # local basis. Realification happens only at the covariance boundary.
    dd, dt, dv = (np.zeros((n, length), dtype=complex) for _ in range(3))
    reflection_diagnostics = []
    for p in range(n):
        poll()
        _, terms, _, diagnostic = scalar.sample(g[:, p], m[:, p], m[0, p])
        d[p], t[p], v[p] = terms
        reflection_diagnostics.append(diagnostic)
        b = t[p]-d[p]*v[p]
        matrix = np.column_stack((np.ones(3), g[:,p], m[:,p]*g[:,p]))
        rhs = np.zeros((3,6), dtype=complex)
        for j in range(3):
            rhs[j,j] = -(b+v[p]*m[j,p])
            rhs[j,3+j] = 1-v[p]*g[j,p]
        dq, _ = scalar.solve(matrix, rhs)
        indexes = [j*n+p for j in range(3)] + [3*n+j*n+p for j in range(3)]
        dd[p,indexes], dv[p,indexes] = dq[0], dq[2]
        dt[p,indexes] = dq[1]+v[p]*dq[0]+d[p]*dq[2]
    identity = np.eye(n)
    coupling_operator = identity-coupling*v[None,:]
    coupling_condition = screened(coupling_operator)
    kernel, _ = scalar.solve(coupling_operator, coupling)
    e = (measured_coupling-np.diag(d))/t[None,:]
    u = np.ones(n, dtype=complex)
    for p in range(n):
        if p == reference: continue
        require(abs(kernel[p,reference]) >= 1e-10*max(1., float(np.linalg.norm(kernel))),
                'Known coupling standard lacks a resolved reference-column path', 'unidentifiable')
        require(abs(e[p,reference]) >= 1e-12*max(1., float(np.linalg.norm(e))),
                'Measured reference-column path unresolved', 'unidentifiable')
        u[p] = e[p,reference]/kernel[p,reference]
    w = t/u
    gains(u); gains(w)
    x = (measured_dut-np.diag(d))/u[:,None]/w[None,:]
    recovery = identity+x*v[None,:]
    recovery_condition = screened(recovery)
    dut, recovery_residual = scalar.solve(recovery, x)
    feedback = identity-v[:,None]*dut
    feedback_condition = screened(feedback)
    incident, _ = scalar.solve(feedback, np.diag(w))
    reconstructed = np.diag(d)+u[:,None]*(dut@incident)
    residual = float(np.linalg.norm(reconstructed-measured_dut)/max(1., float(np.linalg.norm(measured_dut))))
    require(residual <= 1e-10, 'DUT measured-wave reconstruction exceeds 1e-10', 'numerical_failure')
    predicted_coupling = np.diag(d)+u[:,None]*kernel*w[None,:]
    consistency = float(np.linalg.norm(predicted_coupling-measured_coupling)/max(1.,float(np.linalg.norm(measured_coupling))))
    derivative = np.zeros((n*n,length), dtype=complex)
    max_sensitivity_residual = 0.
    for j in range(length):
        poll()
        dc, dmc, dmd = (np.zeros((n,n), dtype=complex) for _ in range(3))
        if 6*n <= j < 6*n+n*n: dc.flat[j-6*n] = 1
        if 6*n+n*n <= j < 6*n+2*n*n: dmc.flat[j-6*n-n*n] = 1
        if j >= 6*n+2*n*n: dmd.flat[j-6*n-2*n*n] = 1
        dk, _ = scalar.solve(coupling_operator,
                             dc@(identity+v[:,None]*kernel)+coupling@(dv[:,j,None]*kernel))
        de = (dmc-np.diag(dd[:,j]))/t[None,:]-e*(dt[:,j]/t)[None,:]
        du = np.zeros(n, dtype=complex)
        for p in range(n):
            if p != reference: du[p] = (de[p,reference]-u[p]*dk[p,reference])/kernel[p,reference]
        dw_relative = dt[:,j]/t-du/u
        dx = (dmd-np.diag(dd[:,j]))/u[:,None]/w[None,:]-(du/u)[:,None]*x-x*dw_relative[None,:]
        ds, backward = scalar.solve(recovery, dx@(identity-v[:,None]*dut)-x@(dv[:,j,None]*dut))
        derivative[:,j] = ds.ravel()
        max_sensitivity_residual = max(max_sensitivity_residual, backward)
    require(np.isfinite(derivative).all(), 'Nonfinite sensitivity', 'numerical_failure')
    error_box = np.block([[np.diag(d),np.diag(u)],[np.diag(w),np.diag(v)]])
    terms = dict(zip(('directivity','reflection_tracking','source_match','outward_gain','inward_gain'),
                     map(records,(d,t,v,u,w))))
    return dut, terms, error_box, derivative, {
        'coupling_condition':coupling_condition, 'recovery_condition':recovery_condition,
        'feedback_condition':feedback_condition, 'reconstruction_residual':residual,
        'recovery_backward_residual':recovery_residual, 'sensitivity_backward_residual':max_sensitivity_residual,
        'coupling_standard_consistency_residual':consistency,
        'max_reflection_condition':max(r['calibration_condition'] for r in reflection_diagnostics)}


def calibrate_multiport(request, *, cancel_check=None):
    """Derive a separate multiport network; uncertainty remains first-order only."""
    require(cancel_check is None or callable(cancel_check), 'Cancellation hook must be callable')
    def poll():
        if cancel_check is None: return
        try: stopped = cancel_check()
        except Exception as error:
            raise MultiportCalibrationError('cancel_check_failed','Cancellation hook failed') from error
        require(not stopped, 'Multiport calibration cancelled', 'cancelled')
    poll()
    try:
        size, chunks = 0, []
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',',':')).iterencode(request):
            size += len(chunk.encode('utf-8'))
            require(size <= 8*1024*1024, 'Request exceeds 8 MiB', 'resource_limit')
            chunks.append(chunk)
        encoded = ''.join(chunks).encode('utf-8')
        source = json.loads(encoded)
        scalar.fields(source, ('contract','id','port_names','reference_impedance_ohm','frequencies_hz',
                              'measurement_basis','gain_reference_port','reflection_standards','coupling_standard','dut','covariance'), 'request')
        require(source['contract'] == REQUEST, 'Unsupported multiport calibration contract')
        scalar.name(source['id']); port_set(source['port_names'])
        ports = source['port_names']; n = len(ports)
        require(scalar.number(source['reference_impedance_ohm']) > 0, 'Positive real reference required')
        grid = source['frequencies_hz']
        require(isinstance(grid,list) and 1 <= len(grid) <= 2, 'Supply 1..2 frequencies', 'resource_limit')
        frequencies = [scalar.number(v) for v in grid]
        require(frequencies[0] > 0 and all(b>a for a,b in zip(frequencies,frequencies[1:])), 'Positive strictly increasing resolvable grid required')
        require(source['measurement_basis'] == 'coherent_wave_matrix_ratio', 'Coherent wave matrix-ratio inputs required')
        require(source['gain_reference_port'] in ports, 'Unknown gain reference port')
        reference = ports.index(source['gain_reference_port']); count = len(grid)
        standards = source['reflection_standards']
        require(isinstance(standards,list) and len(standards)==3, 'Exactly three reflection standards per port required')
        gs, ms, ids = [], [], []
        for standard in standards:
            scalar.fields(standard, ('id','provenance','reflection','measured'), 'reflection standard')
            scalar.name(standard['id']); scalar.name(standard['provenance']); ids.append(standard['id'])
            gs.append(samples(standard['reflection'],count,(n,)))
            ms.append(samples(standard['measured'],count,(n,)))
        coupling = source['coupling_standard']; dut = source['dut']
        scalar.fields(coupling, ('id','provenance','s_parameters','measured'), 'coupling standard')
        scalar.fields(dut, ('id','provenance','measured'), 'DUT')
        for record in (coupling,dut):
            scalar.name(record['id']); scalar.name(record['provenance']); ids.append(record['id'])
        require(len(set(ids))==5, 'Standard and DUT identities must be distinct')
        cs = samples(coupling['s_parameters'],count,(n,n))
        mc = samples(coupling['measured'],count,(n,n)); md = samples(dut['measured'],count,(n,n))
        uncertainty = source['covariance']
        scalar.fields(uncertainty, ('basis','matrix','provenance'), 'covariance')
        scalar.name(uncertainty['provenance'])
        basis = input_basis(ports,count)
        require(uncertainty['basis']==basis, 'Explicit covariance basis differs')
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            poll(); covariance = scalar.covariance(uncertainty['matrix'],len(basis))
            local_length = 6*n+3*n*n
            jac = np.zeros((2*count*n*n,len(basis)))
            results, coefficients, boxes, diagnostics = [], [], [], []
            for k in range(count):
                poll()
                value, terms, box, derivative, diagnostic = local_calibration(
                    np.asarray(gs)[:,k,:],np.asarray(ms)[:,k,:],cs[k],mc[k],md[k],reference,poll)
                results.append(records(value)); coefficients.append(terms); boxes.append(records(box))
                diagnostics.append({'frequency_hz':grid[k], **diagnostic})
                rows = 2*k*n*n; columns = 2*k*local_length
                jac[rows:rows+2*n*n:2,columns:columns+2*local_length:2] = derivative.real
                jac[rows:rows+2*n*n:2,columns+1:columns+2*local_length:2] = -derivative.imag
                jac[rows+1:rows+2*n*n:2,columns:columns+2*local_length:2] = derivative.imag
                jac[rows+1:rows+2*n*n:2,columns+1:columns+2*local_length:2] = derivative.real
            propagated = jac@covariance@jac.T
            propagated = (propagated+propagated.T)/2
            scalar.covariance(propagated.tolist(),2*count*n*n)
        digest = sha256(encoded).hexdigest()
        result = {'contract':RESULT,'model_status':'experimental','production_qualified':False,
                  'measurement_qualified':False,'linearization_qualified':False,'model_consistency_qualified':False,
                  'input_digest':digest,'source_request':source,
                  'derived_network':{'id':'calibrated-'+digest[:20],'port_names':list(ports),
                                     'reference_impedance_ohm':source['reference_impedance_ohm'],
                                     'frequencies_hz':list(grid),'s_parameters':results},
                  'error_box':{'id':'calibration-error-box-'+digest[:20],
                               'port_names':[f'exterior.p{i}' for i in range(n)]+[f'dut.p{i}' for i in range(n)],
                               'reference_impedance_ohm':source['reference_impedance_ohm'],
                               'frequencies_hz':list(grid),'s_parameters':boxes},
                  'error_box_maps':{'exterior_ports':[f'exterior.p{i}' for i in range(n)],
                                    'dut_ports':[f'dut.p{i}' for i in range(n)], 'physical_ports':list(ports)},
                  'coefficients':coefficients,'diagnostics':diagnostics,'sensitivity':jac.tolist(),
                  'output_basis':[f'f{k}.dut.s_parameters.p{i}.p{j}.{part}' for k in range(count)
                                  for i in range(n) for j in range(n) for part in ('real','imag')],
                  'covariance':propagated.tolist(),'uncertainty_method':'first_order_joint_real_covariance',
                  'limitations':['Independent per-port error boxes; arbitrary instrument crosstalk is unsupported',
                                 'Supplied coherent wave matrix ratios only; no acquisition or switch correction',
                                 'Explicit reference-column known-standard estimator; other measured coupling entries are diagnostics only',
                                 'Supplied covariance and provenance only; no residual-derived noise, traceability or coverage inference',
                                 'Fixed exact frequency/reference metadata; local nonlinear adequacy unqualified',
                                 'Offline source reference only; measured, worker/UI, installed-release and full-family gates remain open']}
        require(len(json.dumps(result,allow_nan=False).encode('utf-8'))<=16*1024*1024, 'Result exceeds 16 MiB', 'resource_limit')
        poll(); return result
    except MultiportCalibrationError: raise
    except scalar.OnePortCalibrationError as error:
        raise MultiportCalibrationError(error.code.removeprefix('ONE_PORT_CALIBRATION_'),str(error)) from error
    except (ValueError,TypeError,KeyError,OverflowError,ArithmeticError,np.linalg.LinAlgError) as error:
        raise MultiportCalibrationError('numerical_failure',str(error)) from error
