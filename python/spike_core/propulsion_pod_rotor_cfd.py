# SPDX-License-Identifier: Apache-2.0
"""Conforming symmetric-stress Taylor-Hood creeping-flow rotor snapshots.

Actual blade boundary velocity/pressure solve, not BEM or actuator forcing.
Strict Re<=0.1; no finite-RPM air-propeller or inertial CFD qualification.
"""
import copy
import hashlib
import itertools
import json
import math
from functools import lru_cache

import numpy as np
from scipy.sparse import bmat, coo_matrix, diags
from scipy.sparse.linalg import splu

from .cfd_tetra_mesh import admit_cfd_tetra_mesh

CONTRACT='spike/rotor-creeping-cfd/v1'
RESULT_CONTRACT='spike/rotor-creeping-cfd-result/v1'
_EDGES=tuple(itertools.combinations(range(4),2))
_a=(5+3*math.sqrt(5))/20; _b=(5-math.sqrt(5))/20
_QUAD=np.array([[_a if j==i else _b for j in range(4)] for i in range(4)])
_TRI_QUAD=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
MAX_CELLS=1800
MAX_UNKNOWNS=18000
MAX_FACTOR_NONZEROS=12_000_000


def _finite(value,name,positive=False):
    if type(value) not in (int,float) or not math.isfinite(value) or (positive and value<=0):
        raise ValueError(name+' must be finite'+(' and positive' if positive else ''))
    return float(value)


def _gradients(lambdas,g):
    result=np.empty((len(lambdas),10,3))
    result[:,:4,:]=(4*lambdas[:,:,None]-1)*g[None,:,:]
    for k,(i,j) in enumerate(_EDGES):
        result[:,4+k,:]=4*(lambdas[:,i,None]*g[j]+lambdas[:,j,None]*g[i])
    return result


def _p2_values(lambdas):
    result=np.empty((len(lambdas),10));result[:,:4]=lambdas*(2*lambdas-1)
    for k,(i,j) in enumerate(_EDGES):result[:,4+k]=4*lambdas[:,i]*lambdas[:,j]
    return result


class SymmetricStokes:
    """Zero-body-force P2/P1 all-Dirichlet reference; no natural stress shortcut."""
    def __init__(self,raw_mesh,mu,*,max_cells=MAX_CELLS,max_unknowns=MAX_UNKNOWNS,max_factor_nonzeros=MAX_FACTOR_NONZEROS,linear_solver_factory=None,pre_factor_check=None):
        self.mesh=admit_cfd_tetra_mesh(raw_mesh,max_cells=max_cells)
        m=self.mesh;self.mu=_finite(mu,'dynamic viscosity',True)
        if len(m['cells'])>max_cells or len(m['components'])!=1:
            raise ValueError('Rotor reference fluid component/cell budget exceeded')
        coordinates=m['vertices'].tolist();edge_ids={};local=[]
        for cell in m['cells']:
            row=list(map(int,cell))
            for i,j in _EDGES:
                key=tuple(sorted((int(cell[i]),int(cell[j]))))
                if key not in edge_ids:
                    edge_ids[key]=len(coordinates);coordinates.append(((m['vertices'][key[0]]+m['vertices'][key[1]])*.5).tolist())
                row.append(edge_ids[key])
            local.append(row)
        self.xyz=np.asarray(coordinates);self.local=np.asarray(local,dtype=int)
        nv=len(self.xyz);npres=len(m['vertices']);rows=[];cols=[];data=[];br=[];bc=[];bv=[]
        pressure_mass=np.zeros(npres)
        for c,nodes in enumerate(self.local):
            grad=_gradients(_QUAD,m['barycentric_gradients'][c]);w=np.full(4,m['cell_volumes'][c]/4)
            gram=np.einsum('qid,qjd,q->ij',grad,grad,w)
            block=self.mu*(gram[:,None,:,None]*np.eye(3)[None,:,None,:]+np.einsum('qib,qja,q->iajb',grad,grad,w))
            dofs=(nodes[:,None]*3+np.arange(3)).ravel();block=block.reshape(30,30)
            ri,ci=np.nonzero(block);rows.append(dofs[ri]);cols.append(dofs[ci]);data.append(block[ri,ci])
            divergence=np.einsum('qk,qid,q->kid',_QUAD,grad,w)
            for k,vertex in enumerate(m['cells'][c]):
                br.append(np.full(30,int(vertex)));bc.append(dofs);bv.append(divergence[k].ravel())
                pressure_mass[vertex]+=m['cell_volumes'][c]/4
        self.K=coo_matrix((np.concatenate(data),(np.concatenate(rows),np.concatenate(cols))),shape=(3*nv,3*nv)).tocsr()
        self.B=coo_matrix((np.concatenate(bv),(np.concatenate(br),np.concatenate(bc))),shape=(npres,3*nv)).tocsr()
        # Assembly chunks are no longer needed; release before native factorization.
        del rows,cols,data,br,bc,bv
        self.patch_nodes={}
        for name,faces in m['boundary_patches'].items():
            nodes=set()
            for face in faces:
                corners=list(map(int,m['face_vertices'][face]));nodes.update(corners)
                nodes.update(edge_ids[tuple(sorted(e))] for e in itertools.combinations(corners,2))
            self.patch_nodes[name]=np.array(sorted(nodes),dtype=int)
        fixed=np.unique(np.concatenate(list(self.patch_nodes.values())))
        self.fixed=np.sort((fixed[:,None]*3+np.arange(3)).ravel())
        self.free=np.setdiff1d(np.arange(3*nv),self.fixed)
        if len(self.free)+npres+1>max_unknowns:raise ValueError('Taylor-Hood unknown budget exceeded')
        kff=self.K[self.free][:,self.free]
        diagonal=kff.diagonal()
        if not len(diagonal) or np.any(diagonal<=0):raise ValueError('No coercive free velocity block')
        self.su=1/np.sqrt(diagonal);self.sp=np.sqrt(self.mu/pressure_mass)
        coupling=diags(self.sp)@self.B[:,self.free]@diags(self.su)
        gauge=pressure_mass*self.sp;gauge/=np.linalg.norm(gauge)
        self.A=bmat([[diags(self.su)@kff@diags(self.su),-coupling.T,None],
                     [-coupling,None,gauge[:,None]],[None,gauge[None,:],None]],format='csc')
        if pre_factor_check is not None:pre_factor_check(self)
        self.factor=splu(self.A) if linear_solver_factory is None else linear_solver_factory(self.A,len(self.free),npres,gauge)
        # Legacy attribute name: native stored-entry counter, not exposed CSC nnz.
        self.factor_nonzeros=self.factor.nnz if linear_solver_factory is None else self.factor.factor_nonzeros
        if not 0<=self.factor_nonzeros<=max_factor_nonzeros:raise ValueError('Taylor-Hood sparse factor budget exceeded')

    def solve(self,boundary_velocity):
        """Boundary callable(name,xyz)->3-vector; shared patch nodes must agree."""
        m=self.mesh;u=np.zeros((len(self.xyz),3));seen={}
        for name,nodes in self.patch_nodes.items():
            for node in nodes:
                v=np.asarray(boundary_velocity(name,self.xyz[node]),dtype=float)
                if v.shape!=(3,) or not np.isfinite(v).all():raise ValueError('Nonfinite boundary velocity')
                if node in seen and not np.allclose(v,seen[node],rtol=1e-12,atol=0):raise ValueError('Incompatible shared Dirichlet node')
                seen[node]=v;u[node]=v
        prescribed=u.ravel().copy();rhs=np.concatenate([-self.su*(self.K@prescribed)[self.free],self.sp*(self.B@prescribed),[0.]])
        solution=self.factor.solve(rhs) if np.any(rhs) else np.zeros(len(rhs))
        n=len(self.free);u.ravel()[self.free]=self.su*solution[:n];p=self.sp*solution[n:-1]
        residual=self.A@solution-rhs;scale=np.linalg.norm(rhs)
        relative=np.linalg.norm(residual)/scale if scale else np.linalg.norm(residual)
        if not math.isfinite(relative) or relative>1e-9:raise ValueError('Taylor-Hood saddle residual failed')
        # Continuous P1 pressure tests imply weak incompressibility, not exact cellwise flux.
        mass=self.B@u.ravel();mass_scale=np.linalg.norm(self.B.data)*np.linalg.norm(u)
        mass_relative=np.linalg.norm(mass)/mass_scale if mass_scale else np.linalg.norm(mass)
        if mass_relative>1e-10:raise ValueError('Taylor-Hood weak continuity residual failed')
        pressure_force=self.B.T@p;reaction=self.K@u.ravel()-pressure_force
        free_res=np.linalg.norm(reaction[self.free]);force_scale=max(np.linalg.norm(self.K@u.ravel()),np.linalg.norm(pressure_force),np.linalg.norm(self.K.data)*np.linalg.norm(u))
        if free_res>(1e-9*force_scale if force_scale else 0):raise ValueError('Physical free momentum residual failed')
        reactions=np.zeros_like(u);reactions.ravel()[self.fixed]=reaction[self.fixed]
        dissipation=0.;cell_u=[];cell_p=[];grad_centres=[];max_div=0.
        for c,nodes in enumerate(self.local):
            grad=_gradients(_QUAD,m['barycentric_gradients'][c]);gu=np.einsum('ia,qib->qab',u[nodes],grad);D=.5*(gu+gu.transpose(0,2,1))
            dissipation+=self.mu*m['cell_volumes'][c]/2*float(np.sum(D*D))
            lc=np.full((1,4),.25);gc=_gradients(lc,m['barycentric_gradients'][c]);grad_centres.append(np.einsum('ia,qib->qab',u[nodes],gc)[0].tolist())
            cell_u.append((_p2_values(lc)@u[nodes])[0].tolist());cell_p.append(float(np.mean(p[m['cells'][c]])));max_div=max(max_div,float(np.max(np.abs(np.trace(gu,axis1=1,axis2=2)))))
        work=float(np.sum(reactions*u));pressure_work=float(p@mass)
        energy_scale=max(abs(work),dissipation,np.linalg.norm(self.K.data)*np.linalg.norm(u)**2)
        energy_defect=abs(work-dissipation+pressure_work)/energy_scale if energy_scale else 0.
        if energy_defect>1e-9:raise ValueError('Symmetric-stress Dirichlet work identity failed')
        return {'u':u,'p':p,'reaction':reactions,'diagnostics':{'saddle_relative_residual':float(relative),'weak_mass_relative_residual':float(mass_relative),'maximum_quadrature_divergence_s_inv':max_div,'symmetric_viscous_dissipation_w':dissipation,'dirichlet_work_w':work,'pressure_work_w':pressure_work,'relative_energy_residual':energy_defect,'tetrahedra':len(m['cells']),'P2_velocity_nodes':len(u),'P1_pressure_nodes':len(p),'sparse_factor_nonzeros':self.factor_nonzeros,'sparse_factor_count_semantics':'native_stored_entries','cellwise_mass_conservative':False},'cell_velocity_m_s':cell_u,'cell_pressure_pa':cell_p,'cell_velocity_gradient_s_inv':grad_centres}

    def recovered_surface(self,state,patches,origin,axis):
        """Physical symmetric Cauchy stress quadrature; separate recovery estimate."""
        m=self.mesh;force=np.zeros(3);moment=np.zeros(3);faces=[]
        for name in patches:
            for face in m['boundary_patches'][name]:
                c=int(m['face_owners'][face,0]);corners=list(map(int,m['face_vertices'][face]));local_corners=[list(m['cells'][c]).index(v) for v in corners];lambdas=np.zeros((3,4));lambdas[:,local_corners]=_TRI_QUAD
                gradients=_gradients(lambdas,m['barycentric_gradients'][c]);gu=np.einsum('ia,qib->qab',state['u'][self.local[c]],gradients);pressure=lambdas@state['p'][m['cells'][c]]
                stress=self.mu*(gu+gu.transpose(0,2,1))-pressure[:,None,None]*np.eye(3)
                traction=stress@m['face_normals'][face];positions=_TRI_QUAD@m['vertices'][corners];weights=m['face_areas'][face]/3
                f=weights*np.sum(traction,axis=0);q=weights*np.sum(np.cross(positions-origin,traction),axis=0);force+=f;moment+=q
                faces.append({'face_id':int(face),'centroid_m':m['face_centroids'][face].tolist(),'area_m2':float(m['face_areas'][face]),'fluid_outward_normal':m['face_normals'][face].tolist(),'average_traction_on_fluid_pa':np.mean(traction,axis=0).tolist()})
        return {'force_on_fluid_n':force.tolist(),'moment_on_fluid_nm':moment.tolist(),'axis_moment_nm':float(axis@moment),'faces':faces}


@lru_cache(maxsize=2)
def _prepared(canonical):
    spec=json.loads(canonical)
    if not isinstance(spec,dict):raise ValueError('Specification must be an object')
    if set(spec)!={'contract','mesh','rotor_patches','axis_unit','origin_m','dynamic_viscosity_pa_s','density_kg_m3'} or spec['contract']!=CONTRACT:raise ValueError('Invalid rotor creeping CFD specification')
    axis=np.asarray(spec['axis_unit'],dtype=float);origin=np.asarray(spec['origin_m'],dtype=float)
    if axis.shape!=(3,) or origin.shape!=(3,) or not np.isfinite(axis).all() or not np.isfinite(origin).all() or abs(np.linalg.norm(axis)-1)>1e-12:raise ValueError('Finite origin/unit axis required')
    rho=_finite(spec['density_kg_m3'],'density',True);mu=_finite(spec['dynamic_viscosity_pa_s'],'viscosity',True)
    solver=SymmetricStokes(spec['mesh'],mu);patches=spec['rotor_patches']
    if not isinstance(patches,list) or not patches or len(set(patches))!=len(patches) or not set(patches)<=set(solver.patch_nodes):raise ValueError('Explicit unique rotor boundary patches required')
    if set(patches)==set(solver.patch_nodes):raise ValueError('A stationary container patch is required')
    rotor=np.unique(np.concatenate([solver.patch_nodes[n] for n in patches]));stationary=np.unique(np.concatenate([v for n,v in solver.patch_nodes.items() if n not in patches]))
    if np.intersect1d(rotor,stationary).size:raise ValueError('Rotor and stationary boundaries must not share nodes')
    # Require a closed moving body so pressure gauge cannot change net reaction.
    ids=np.concatenate([solver.mesh['boundary_patches'][n] for n in patches]);tris=solver.mesh['face_vertices'][ids];edges={}
    for tri in tris:
        for e in itertools.combinations(tri,2):e=tuple(sorted(map(int,e)));edges[e]=edges.get(e,0)+1
    if any(n!=2 for n in edges.values()):raise ValueError('Rotor wetted surface must be closed')
    state=solver.solve(lambda name,x:np.cross(axis,x-origin) if name in patches else np.zeros(3))
    generalized_force=np.sum(state['reaction'][rotor],axis=0);generalized_moment=np.sum(np.cross(solver.xyz[rotor]-origin,state['reaction'][rotor]),axis=0);torque=float(axis@generalized_moment)
    if torque<=0:raise ValueError('Rotating-body viscous reaction is nonpositive')
    recovered=solver.recovered_surface(state,patches,origin,axis)
    return spec,solver,state,rotor,axis,origin,rho,generalized_force,generalized_moment,torque,recovered


def evaluate(spec,omega_rad_s):
    """Actual fixed-orientation no-slip creeping rotor CFD snapshot, omega>=0.

    Reaction uses consistent physical symmetric-stress FE surface loads. Nodal
    reactions are forces exerted by the blade on fluid; blade force is opposite.
    This is not full-RPM air CFD, MRF inertia, resolved wake or unsteady fluid.
    """
    omega=_finite(omega_rad_s,'omega_rad_s')
    if omega<0:raise ValueError('Negative rotation not admitted in this research wrapper')
    try:canonical=json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError) as exc:raise ValueError('Finite JSON rotor specification required') from exc
    if len(canonical)>8_000_000:raise ValueError('Rotor mesh payload exceeds8MB')
    clean,solver,unit,rotor,axis,origin,rho,force,moment,torque,recovered=_prepared(canonical)
    m=solver.mesh;extent=float(np.linalg.norm(np.ptp(m['vertices'],axis=0)))
    # P2 Bernstein hull bounds the continuous quadratic velocity, not just its nodes.
    speed=0.
    for nodes in solver.local:
        nodal=unit['u'][nodes];controls=[*nodal[:4]]
        controls.extend(2*nodal[4+i]-.5*(nodal[a]+nodal[b]) for i,(a,b) in enumerate(_EDGES))
        speed=max(speed,max(np.linalg.norm(v) for v in controls)*omega)
    reynolds=rho*speed*extent/solver.mu
    if not math.isfinite(reynolds) or reynolds>.1:raise ValueError('Actual resolved velocity Reynolds bound exceeds creeping-flow0.1; real air RPM remains unsupported')
    power=torque*omega*omega;diss=unit['diagnostics']['symmetric_viscous_dissipation_w']*omega*omega
    defect=abs(power-diss)/max(power,diss) if power or diss else 0.
    if defect>1e-9:raise ValueError('Rotor shaft/symmetric-stress fluid work failed')
    raw_torque=recovered['axis_moment_nm']*omega;weak_torque=torque*omega
    raw_thrust=-float(axis@np.asarray(recovered['force_on_fluid_n']))*omega;thrust=-float(axis@force)*omega
    recovery=abs(raw_torque-weak_torque)/abs(weak_torque) if weak_torque else 0.
    return {'contract':RESULT_CONTRACT,'status':'completed','model_status':'experimental','production_qualified':False,'load_qualified':False,'load_status':'mesh_and_outer_domain_convergence_required','scope':'instantaneous_blade_boundary_resolved_creeping_symmetric_stress_Taylor_Hood_snapshot','omega_rad_s':omega,'torque_nm':weak_torque,'thrust_n':thrust,'power_w':power,'fluid_viscous_dissipation_w':diss,'relative_shaft_power_residual':defect,'reynolds_upper_bound':reynolds,'torque_from_recovered_Cauchy_stress_nm':raw_torque,'thrust_from_recovered_Cauchy_stress_n':raw_thrust,'traction_torque_recovery_relative_difference':recovery,'blade_force_n':(-force*omega).tolist(),'blade_moment_nm':(-moment*omega).tolist(),'fields':{'P2_nodes_m':solver.xyz.tolist(),'P2_velocity_m_s':(unit['u']*omega).tolist(),'P1_pressure_pa':(unit['p']*omega).tolist(),'cell_velocity_m_s':(np.asarray(unit['cell_velocity_m_s'])*omega).tolist(),'cell_pressure_pa':(np.asarray(unit['cell_pressure_pa'])*omega).tolist(),'tetra_vertices':m['cells'].tolist(),'vertices_m':m['vertices'].tolist()},'blade_surface_weak_loads':[{'P2_node_id':int(n),'position_m':solver.xyz[n].tolist(),'force_on_fluid_n':(unit['reaction'][n]*omega).tolist()} for n in rotor],'surface_traction_recovery':[{**f,'average_traction_on_fluid_pa':(np.asarray(f['average_traction_on_fluid_pa'])*omega).tolist()} for f in recovered['faces']],'unit_operator_diagnostics':copy.deepcopy(unit['diagnostics']),'spec_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'limitations':['Strict low-Re instantaneous Stokes snapshot; no advection,Coriolis,centrifugal,unsteady fluid or full-RPM air qualification','Resolved finite-element blade boundary geometry; no BEM/body-force replacement','Consistent symmetric-stress weak boundary reactions preserve force/moment/virtual work; recovered pointwise stress is a separate convergent estimate','P2/P1 weak incompressibility is not exact cellwise mass conservation','Stationary closed container, no inlet/outlet thrust test, far wake or total-energy thermal participant','Geometry/source authenticity, mesh/outer-domain/traction convergence and physical validation remain case-specific gates']}
