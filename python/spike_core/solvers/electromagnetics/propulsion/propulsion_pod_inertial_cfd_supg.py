# SPDX-License-Identifier: Apache-2.0
"""Original residual-consistent P2 symmetric-stress SUPG assembly.

Numerical streamline stabilization work is explicitly separate from heat.
"""
import numpy as np
from scipy.sparse import coo_matrix


def p2_hessians(gradients):
    import itertools
    values=[4*np.outer(g,g) for g in gradients]
    values.extend(4*(np.outer(gradients[i],gradients[j])+np.outer(gradients[j],gradients[i])) for i,j in itertools.combinations(range(4),2))
    return np.array(values)


def assemble(solver,u,p,omega,origin,body_quad,*,jacobian=True):
    """Smooth steady SUPG scale; h=min tetra altitude, explicit research choice.

    tau=[(2|w|/h)^2+(12nu/h^2)^2]^-1/2, finite at w=0.
    This fixed geometric length is conservative on anisotropic tets; it is
    not an automatic wall-model or a qualified P2 high-Re parameter choice.
    Complete tau, test-weight and physical strong-residual derivatives enter
    the Newton matrix. No PSPG is needed for this conforming P2/P1 pair.
    """
    b=solver.base;m=b.mesh;N=solver.N;rho=solver.rho;mu=solver.mu;nu=mu/rho
    rows=[];cols=[];data=[];pr=[];pc=[];pd=[];res=np.zeros(b.K.shape[0]);strong_l2=0.;tau_min=float('inf');tau_max=0.
    cross=np.array([[0.,-omega[2],omega[1]],[omega[2],0.,-omega[0]],[-omega[1],omega[0],0.]])
    for c,nodes in enumerate(b.local):
        g=solver.grad[c];weights=solver.weights[c];hessian=p2_hessians(m['barycentric_gradients'][c]);lap=np.trace(hessian,axis1=1,axis2=2)
        uq=N@u[nodes];gu=np.einsum('ia,qib->qab',u[nodes],g);w=uq-np.cross(omega,solver.points[c]-origin);psi=np.einsum('qb,qjb->qj',w,g)
        viscous=mu*(np.einsum('i,ia->a',lap,u[nodes])+np.einsum('iab,ib->a',hessian,u[nodes]))
        gradp=p[m['cells'][c]]@m['barycentric_gradients'][c]
        rm=rho*(np.einsum('qab,qb->qa',gu,w)+np.cross(omega,uq))-viscous+gradp-body_quad[c]
        h=1/np.max(np.linalg.norm(m['barycentric_gradients'][c],axis=1));tau=1/np.sqrt(4*np.sum(w*w,axis=1)/h**2+144*nu*nu/h**4)
        tau_min=min(tau_min,float(tau.min()));tau_max=max(tau_max,float(tau.max()));strong_l2+=float(np.sum(weights*np.sum(rm*rm,axis=1)))
        local=np.einsum('q,qi,qa,q->ia',tau,psi,rm,weights);np.add.at(res,solver.dofs[c],local.ravel())
        if not jacobian:continue
        # Rm derivative includes advector change, full symmetric P2 viscosity,
        # physical pressure gradient, rotation and supplied body force.
        dr=rho*(psi[:,None,:,None]*np.eye(3)[None,:,None,:]+np.einsum('qj,qab->qajb',N,gu)+N[:,None,:,None]*cross[None,:,None,:])
        dr-=mu*(lap[None,None,:,None]*np.eye(3)[None,:,None,:]+hessian.transpose(1,0,2)[None,:,:,:])
        dt=-4*tau[:,None]**3*w/h**2
        # d(tau*psi_i)/du_jb = (dt_b*psi_i+tau*d_b Ni)*Nj.
        dtest=(dt[:,None,:]*psi[:,:,None]+tau[:,None,None]*g)
        j=np.einsum('q,qi,qajb,q->iajb',tau,psi,dr,weights)+np.einsum('qib,qj,qa,q->iajb',dtest,N,rm,weights)
        dofs=solver.dofs[c];rows.append(np.repeat(dofs,30));cols.append(np.tile(dofs,30));data.append(j.reshape(-1))
        jp=np.einsum('q,qi,ja,q->iaj',tau,psi,m['barycentric_gradients'][c],weights).reshape(30,4)
        pr.append(np.repeat(dofs,4));pc.append(np.tile(m['cells'][c],30));pd.append(jp.ravel())
    ju=coo_matrix((np.concatenate(data),(np.concatenate(rows),np.concatenate(cols))),shape=b.K.shape).tocsr() if jacobian else None
    jp=coo_matrix((np.concatenate(pd),(np.concatenate(pr),np.concatenate(pc))),shape=(b.K.shape[0],len(p))).tocsr() if jacobian else None
    diagnostics={'strong_physical_momentum_L2_n_m3_times_m3_over2':float(np.sqrt(strong_l2)),'SUPG_tau_min_s':tau_min,'SUPG_tau_max_s':tau_max,'SUPG_length':'minimum_tetrahedron_altitude','SUPG_power_w':float(u.ravel()@res)}
    return res,ju,jp,diagnostics
