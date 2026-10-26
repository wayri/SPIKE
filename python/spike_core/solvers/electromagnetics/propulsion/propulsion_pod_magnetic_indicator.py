# SPDX-License-Identifier: Apache-2.0
"""Residual/constitutive-flux jump indicators for experimental P2 refinement.

Values have energy units, but are marking indicators, not certified error bounds.
They exclude boundary/Fourier/geometry/material errors. See the independently
authored pod numerical review for the governing variational derivation.
"""
import numpy as np
from .propulsion_pod_magnetic_p2 import EDGES, QUADRATURE


def magnetic_refinement_indicator(operator, potential_a_wb_per_m, current_density_a_per_m2):
    """Integrate constant cell residual and linear interior-edge jumps exactly.

    q=C.T nu(C grad(A)-Br); residual=J+div(q). The normal jump is
    q_K.n_K+q_L.n_L, including PM terms, not the always-continuous B normal.
    Boundary traces need a separate error assessment by their coupling owner.
    """
    op=operator;A=np.asarray(potential_a_wb_per_m,float);J=np.asarray(current_density_a_per_m2,float)
    if A.shape!=(len(op.nodes_m),) or J.shape!=(len(op.triangles),) or not np.isfinite(np.r_[A,J]).all():
        raise ValueError('Aligned finite P2 potential and element current density required')
    C=np.array([[0.,1.],[-1.,0.]])
    D=np.einsum('ai,eab,bj->eij',C,op.nu,C)
    alpha=np.linalg.eigvalsh(D)[:,0]
    g=op.barycentric_gradients;local=A[op.triangles_p2]
    hessian=4*np.einsum('ei,eia,eib->eab',local[:,:3],g,g)
    for k,(i,j) in enumerate(EDGES):
        hessian+=4*local[:,3+k,None,None]*(np.einsum('ea,eb->eab',g[:,i],g[:,j])+np.einsum('ea,eb->eab',g[:,j],g[:,i]))
    residual=J+np.einsum('eab,eab->e',D,hessian)
    vertices=op.nodes_m[op.triangles]
    lengths=np.array([np.linalg.norm(vertices[:,j]-vertices[:,i],axis=1) for i,j in EDGES]).T
    diameter=lengths.max(axis=1)
    cell=op.depth*op.areas*diameter**2/alpha*residual**2
    edge_part=np.zeros(len(cell))
    t=np.array([.5-1/np.sqrt(12),.5+1/np.sqrt(12)])
    points=np.zeros((6,3))
    for k,(i,j) in enumerate(EDGES):points[2*k:2*k+2,i]=1-t;points[2*k:2*k+2,j]=t
    B=op.evaluate_b(A,points)
    H=np.einsum('eab,eqb->eqa',op.nu,B-op.br[:,None,:])
    q=H@C
    # Trace order is normalized to global edge endpoint order so neighboring
    # Gauss values refer to the same physical positions, even on CW triangles.
    flux=np.empty((len(cell),3,2))
    for k,(i,j) in enumerate(EDGES):
        vector=vertices[:,j]-vertices[:,i]
        normal=np.column_stack([-vector[:,1],vector[:,0]])/lengths[:,k,None]
        other=3-i-j
        inward=np.einsum('ea,ea->e',normal,vertices[:,other]-vertices[:,i])>0
        normal[inward]*=-1
        flux[:,k]=np.einsum('eqa,ea->eq',q[:,2*k:2*k+2],normal)
        reverse=op.triangles[:,i]>op.triangles[:,j]
        flux[reverse,k]=flux[reverse,k,::-1]
    ids=(op.triangles_p2[:,3:]-op.vertex_count).ravel()
    order=np.argsort(ids,kind='stable');ordered_ids=ids[order]
    starts=np.r_[0,np.flatnonzero(np.diff(ordered_ids))+1];counts=np.diff(np.r_[starts,len(order)])
    shared=starts[counts==2]
    left=order[shared];right=order[shared+1]
    left_cell=left//3;right_cell=right//3
    jump=flux.reshape(-1,2)[left]+flux.reshape(-1,2)[right]
    edge_length=lengths.ravel()[left]
    # Two-point Gauss on the segment integrates the squared linear jump.
    energy=op.depth*edge_length**2/np.minimum(alpha[left_cell],alpha[right_cell])*np.mean(jump**2,axis=1)
    np.add.at(edge_part,left_cell,.5*energy);np.add.at(edge_part,right_cell,.5*energy)
    total=cell+edge_part
    if not np.isfinite(total).all() or not np.isfinite(total.sum()):raise ValueError('Refinement indicator exceeds numerical range')
    return {'element_indicator_j':total.tolist(),'cell_residual_indicator_j':cell.tolist(),
        'interior_flux_jump_indicator_j':edge_part.tolist(),'sum_indicator_j':float(total.sum()),
        'maximum_element_diameter_m':float(diameter.max()),
        'boundary_edges_excluded':int(np.sum(counts==1)),
        'certified_error_bound':False,'purpose':'refinement marking only',
        'limitations':['No boundary/Fourier, geometry, winding or material error is estimated.',
            'High-contrast, anisotropic and shape-regularity constants are not certified.']}


def hierarchical_magnetic_correction(coarse, fine, coarse_potential, fine_potential, *, nesting_tolerance_m=0.):
    """Exact local energy of a nested P2 field difference, without h weights.

    This is an enrichment indicator, not a true-error bound. In a coupled model
    add the analytic gap's coefficient-difference energy separately before
    comparing global correction energy to the coenergy gain.
    """
    from matplotlib.tri import Triangulation
    if type(nesting_tolerance_m) not in (float,int) or not np.isfinite(nesting_tolerance_m) or not 0<=nesting_tolerance_m<=2e-12:
        raise ValueError('Explicit nesting tolerance must be finite in0..2picometres')
    a=np.asarray(coarse_potential,float);b=np.asarray(fine_potential,float)
    if a.shape!=(len(coarse.nodes_m),) or b.shape!=(len(fine.nodes_m),) or not np.isfinite(np.r_[a,b]).all():
        raise ValueError('Aligned finite coarse/fine P2 potentials required')
    if coarse.depth!=fine.depth:raise ValueError('Identical stack depth required')
    nodes=coarse.nodes_m[:coarse.vertex_count];tri=coarse.triangles
    p=nodes[tri];edge1=p[:,1]-p[:,0];edge2=p[:,2]-p[:,0]
    signed=edge1[:,0]*edge2[:,1]-edge1[:,1]*edge2[:,0]
    oriented=tri.copy();oriented[signed<0]=oriented[signed<0][:,[0,2,1]]
    finder=Triangulation(nodes[:,0],nodes[:,1],oriented).get_trifinder()
    child=fine.nodes_m[fine.triangles];centres=child.mean(axis=1)
    parent=np.asarray(finder(centres[:,0],centres[:,1]))
    if np.any(parent<0):raise ValueError('Fine cell lies outside coarse domain')
    p=p[parent];e=edge1[parent];f=edge2[parent];det=signed[parent]
    def barycentric(points):
        delta=points-p[:,None,0,:]
        l1=(delta[:,:,0]*f[:,None,1]-delta[:,:,1]*f[:,None,0])/det[:,None]
        l2=(e[:,None,0]*delta[:,:,1]-e[:,None,1]*delta[:,:,0])/det[:,None]
        return np.stack([1-l1-l2,l1,l2],axis=-1)
    child_bary=barycentric(child)
    opposite_lengths=np.stack([np.linalg.norm(p[:,1]-p[:,2],axis=1),
        np.linalg.norm(p[:,0]-p[:,2],axis=1),np.linalg.norm(p[:,0]-p[:,1],axis=1)],axis=1)
    altitudes=np.abs(det[:,None])/opposite_lengths
    normal_violation=np.maximum(-child_bary,0)*altitudes[:,None,:]
    outside=np.zeros(child_bary.shape[:2])
    ci,vi=np.nonzero(np.any(child_bary<0,axis=2))
    if len(ci):
        # Supporting-line distances understate distance beyond an acute corner.
        # Outside a convex triangle the nearest point is on a closed segment.
        start=p[ci];end=np.roll(start,-1,axis=1);vector=end-start
        delta=child[ci,vi,None,:]-start
        parameter=np.clip(np.einsum('eia,eia->ei',delta,vector)/np.sum(vector**2,axis=2),0.,1.)
        nearest=start+parameter[:,:,None]*vector
        outside[ci,vi]=np.min(np.linalg.norm(child[ci,vi,None,:]-nearest,axis=2),axis=1)
    roundoff=64*np.finfo(float).eps*np.max(np.abs(p),axis=(1,2))
    if np.any(outside>nesting_tolerance_m+roundoff[:,None]):
        raise ValueError('Fine cell is not contained in one coarse ancestor')
    coverage=np.bincount(parent,weights=fine.areas,minlength=len(tri))
    original_points=nodes[tri]
    perimeter=sum(np.linalg.norm(original_points[:,i]-original_points[:,j],axis=1) for i,j in EDGES)
    area_tolerance=1e-8*coarse.areas+1e-16+2*nesting_tolerance_m*perimeter
    if np.any(np.abs(coverage-coarse.areas)>area_tolerance):
        raise ValueError('Coarse/fine area coverage mismatch')
    if not np.allclose(fine.nu,coarse.nu[parent],rtol=1e-13,atol=0) or not np.array_equal(fine.br,coarse.br[parent]):
        raise ValueError('Constitutive properties changed between levels')
    points=np.einsum('qi,eia->eqa',QUADRATURE,child)
    l=barycentric(points);g=coarse.barycentric_gradients[parent]
    grad=(4*l[:,:,:,None]-1)*g[:,None,:,:]
    edges=[4*(l[:,:,i,None]*g[:,None,j,:]+l[:,:,j,None]*g[:,None,i,:]) for i,j in EDGES]
    grad=np.concatenate([grad,np.stack(edges,axis=2)],axis=2)
    gradient=np.einsum('ei,eqia->eqa',a[coarse.triangles_p2[parent]],grad)
    Bcoarse=np.stack([gradient[:,:,1],-gradient[:,:,0]],axis=-1)
    delta=fine.evaluate_b(b,QUADRATURE)-Bcoarse
    energy=.5*fine.depth*fine.areas/3*np.einsum('eqa,eab,eqb->e',delta,fine.nu,delta)
    if not np.isfinite(energy).all() or not np.isfinite(energy.sum()):
        raise ValueError('Hierarchical correction exceeds finite numerical range')
    return {'element_correction_energy_j':energy.tolist(),'sum_correction_energy_j':float(energy.sum()),
        'coarse_parent_triangle_ids':parent.tolist(),'certified_error_bound':False,
        'declared_nesting_tolerance_m':float(nesting_tolerance_m),
        'maximum_physical_outside_distance_m':float(outside.max()),
        'maximum_edge_normal_violation_m':float(normal_violation.max()),
        'maximum_parent_area_difference_m2':float(np.max(np.abs(coverage-coarse.areas))),
        'gap_energy_included':False,'purpose':'nested-space interior refinement marking only'}
