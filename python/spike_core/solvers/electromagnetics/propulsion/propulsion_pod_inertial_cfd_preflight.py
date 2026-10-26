# SPDX-License-Identifier: Apache-2.0
"""Case-specific numerical pressure-kernel research preflight, not LBB proof."""
import hashlib,json
from pathlib import Path
import numpy as np
from scipy.linalg import eigh,norm
from scipy.sparse import save_npz


class PressureKernelError(ValueError):pass


def check_pressure_kernel(matrix,n_velocity,gauge,output_dir,*,pressure_scaling,metadata=None,max_pressure=5000):
    """Reject resolved extra continuity-left-null modes before long flow runs.

    The actual pressure scaling supplies the physical constant-p mode1/sp.
    Gauge functional and null mode are checked independently. No general
    stability theorem is inferred from this finite-precision case screen.
    """
    n=n_velocity;N=matrix.shape[0];g=np.asarray(gauge,dtype=float);sp=np.asarray(pressure_scaling,dtype=float)
    if type(max_pressure) is not int or not 2<=max_pressure<=5000 or type(n) is not int or matrix.shape!=(N,N) or not 0<n<N-2 or g.shape!=(N-n-1,):raise PressureKernelError('Invalid bounded pressure preflight dimensions')
    if len(g)>max_pressure:raise PressureKernelError('Pressure spectral-preflight resource cap exceeded')
    if not np.isfinite(g).all() or not np.any(g) or not np.isfinite(matrix.data).all() or sp.shape!=g.shape or not np.isfinite(sp).all() or np.any(sp<=0):raise PressureKernelError('Finite pressure-kernel inputs/scaling required')
    actual_g=np.asarray(matrix[n:-1,-1].toarray()).ravel();actual_row=np.asarray(matrix[-1,n:-1].toarray()).ravel()
    if not np.array_equal(g,actual_g) or not np.array_equal(g,actual_row) or matrix[:n,-1].nnz or matrix[-1,:n].nnz or matrix[-1,-1]!=0 or matrix[n:-1,n:-1].nnz:raise PressureKernelError('Actual matrix gauge/pressure block mismatch')
    constant=np.min(sp)/sp
    if np.any(constant==0):raise PressureKernelError('Unrepresentable scaled physical pressure-constant mode')
    constant/=norm(constant);gauge_norm=norm(g)
    if not np.isfinite(gauge_norm) or abs(g@constant)<=1e-12*gauge_norm:raise PressureKernelError('Actual gauge does not constrain physical constant pressure')
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True);C=matrix[n:-1,:n].tocsr();G=matrix[:n,n:-1].tocsr();upper=min(7,len(g)-1)
    sources=[Path(__file__),Path(__file__).with_name('propulsion_pod_rotor_cfd.py'),(Path(__file__).resolve().parents[5] / 'python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_mesh.py'),(Path(__file__).resolve().parents[5] / 'python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_intersections.py')]
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    save_npz(out/'scaled-continuity-C.npz',C);np.savez_compressed(out/'pressure-kernel-input.npz',gauge=g,constant_mode=constant,pressure_scaling=sp)
    baseline={'contract':'spike/pressure-kernel-research-preflight/v2','pressure_dofs':len(g),'free_velocity_dofs':n,'uniform_inf_sup_proven':False,'formal_exact_rank_proven':False,'load_qualified':False,'metadata':metadata or {},'source_sha256':source_hashes}
    (out/'preflight-input.json').write_text(json.dumps(baseline,indent=2)+'\n')
    try:
        gram=(C@C.T).toarray();values,vectors=eigh(gram,subset_by_index=(0,upper),driver='evr',check_finite=True)
    except Exception as error:
        failed={**baseline,'passed':False,'status':'eigensolve_failed','error_type':type(error).__name__,'error':str(error)}
        (out/'pressure-kernel-evidence.json').write_text(json.dumps(failed,indent=2)+'\n')
        raise PressureKernelError('Pressure eigensolve failed; inputs retained, no flow admission') from error
    # A declared finite-precision screen, not exact rank certification. The
    # actual observed spectral gap and residuals remain in the receipt.
    threshold=1e-12*max(float(np.max(np.sum(abs(gram),axis=1))),np.finfo(float).tiny)
    small=int(np.sum(abs(values)<=threshold));constant_res=float(norm(C.T@constant)/max(norm(C.data),np.finfo(float).tiny));upper_res=float(norm(G@constant)/max(norm(G.data),np.finfo(float).tiny));alignment=abs(float(constant@vectors[:,0]));residuals=[float(norm(gram@vectors[:,i]-values[i]*vectors[:,i])) for i in range(len(values))]
    eigen_scale=max(float(np.max(np.sum(abs(gram),axis=1))),np.finfo(float).tiny);relative_eigen_residuals=np.array(residuals)/eigen_scale
    separated=bool(abs(values[0])+residuals[0]<threshold and values[1]-residuals[1]>threshold)
    passed=bool(separated and small==1 and values[0]>=-threshold and constant_res<=1e-12 and upper_res<=1e-12 and alignment>=1-1e-6 and np.isfinite(relative_eigen_residuals).all() and np.max(relative_eigen_residuals)<=1e-10)
    np.savez_compressed(out/'pressure-kernel-modes.npz',gauge=g,constant_mode=constant,pressure_scaling=sp,eigenvalues=values,eigenvectors=vectors)
    evidence={**baseline,'passed':passed,'residual_interval_separation_passed':separated,'numerical_small_eigenvalues_found':small,'eigenvalues':values.tolist(),'declared_numerical_zero_threshold':threshold,'eigenvector_residuals':residuals,'relative_eigenvector_residuals':relative_eigen_residuals.tolist(),'eigenvector_residual_relative_gate':1e-10,'constant_mode_relative_C_transpose_residual':constant_res,'constant_mode_relative_upper_G_residual':upper_res,'smallest_eigenvector_constant_alignment':alignment,'physical_constant_mode_from_actual_pressure_scaling':True,'gauge_alignment_with_physical_constant':float(abs((g/gauge_norm)@constant)),'artifact_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ('scaled-continuity-C.npz','pressure-kernel-input.npz','pressure-kernel-modes.npz')}}
    (out/'pressure-kernel-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    if not passed:raise PressureKernelError('Extra/invalid numerical pressure kernel; retained preflight evidence, no flow admission')
    return evidence
