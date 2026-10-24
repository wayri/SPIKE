# SPDX-License-Identifier: Apache-2.0
"""Original symmetric-stress laminar Navier-Stokes rotating-frame reference.

Experimental, no turbulence or air-propeller load qualification is implied.
"""
import math
import time
import numpy as np
from scipy.sparse import coo_matrix, bmat, diags
from scipy.sparse.linalg import LinearOperator, gmres, spilu
from .propulsion_pod_rotor_cfd import SymmetricStokes, _gradients, _p2_values


def _quadrature(order=4):
    x,w=np.polynomial.legendre.leggauss(order);x=(x+1)/2;w=w/2
    q=[];weights=[]
    for i,a in enumerate(x):
        for j,b in enumerate(x):
            for k,c in enumerate(x):
                q.append([1-a,a*(1-b),a*b*(1-c),a*b*c])
                weights.append(w[i]*w[j]*w[k]*a*a*b*6)
    return np.array(q),np.array(weights)

_Q,_W=_quadrature();_N=_p2_values(_Q)
# Four-point Gauss in Duffy triangle, degree>=6 for cubic boundary products.
_t,_tw=np.polynomial.legendre.leggauss(4);_t=(_t+1)/2;_tw=_tw/2
_TQ=np.array([[1-a,a*(1-b),a*b] for a in _t for b in _t])
_TW=np.array([2*_tw[i]*_tw[j]*a for i,a in enumerate(_t) for j,b in enumerate(_t)])


def _line_search_steps(maximum_line_search_trials=7):
    """Explicit bounded trial budget; acceptance formula is unchanged."""
    if type(maximum_line_search_trials) is not int or not 1<=maximum_line_search_trials<=14:
        raise ValueError('maximum_line_search_trials must be an exact integer from 1 through 14')
    return tuple(2.**(-k) for k in range(maximum_line_search_trials))


class _BlockStokes:
    """Velocity ILU / pressure-mass gauge preconditioner, residual-checked GMRES.

    This changes the linear solution algorithm only. No physical penalty,
    pressure stabilisation or reduced momentum equation is introduced.
    """
    def __init__(self,A,n,npres,gauge):
        self.A=A;self.n=n;self.npres=npres;self.gauge=gauge
        self.ilu=spilu(A[:n,:n].tocsc(),drop_tol=1e-3,fill_factor=8)
        # Legacy attribute name: native stored-entry counter, not exposed CSC nnz.
        self.factor_nonzeros=self.ilu.nnz
        self.preconditioner=LinearOperator(A.shape,matvec=self.apply)
        self.last_iterations=0
    def apply(self,r):
        n=self.n;p=r[n:n+self.npres];g=self.gauge;dot=float(g@p)
        return np.r_[self.ilu.solve(r[:n]),-p+g*(dot+r[-1]),dot]
    def with_velocity(self,matrix):
        ilu=spilu(matrix[:self.n,:self.n].tocsc(),drop_tol=1e-4,fill_factor=10)
        if not 0<=ilu.nnz<=30_000_000:raise ValueError('Explicit Newton velocity-ILU factor budget exceeded')
        def apply(r):
            p=r[self.n:self.n+self.npres];g=self.gauge;dot=float(g@p)
            return np.r_[ilu.solve(r[:self.n]),-p+g*(dot+r[-1]),dot]
        return LinearOperator(matrix.shape,matvec=apply)
    def solve(self,rhs):
        history=[]
        if not np.any(rhs):return np.zeros_like(rhs)
        result,info=gmres(self.A,rhs,M=self.preconditioner,rtol=1e-12,atol=0.,restart=100,maxiter=40,callback=lambda r:history.append(float(r)),callback_type='pr_norm')
        self.last_iterations=len(history)
        if info or np.linalg.norm(self.A@result-rhs)>1e-10*np.linalg.norm(rhs):raise ValueError('Block-preconditioned Stokes solve failed residual gate')
        return result


class RotatingNavierStokes:
    """Steady-rotation absolute-velocity formulation, conforming P2/P1.

    rho[((u-Omega cross r).grad)u+Omega cross u] - div(sigma)=f.
    Skew volume convection plus its boundary consistency flux is used.
    Newton iteration solves the actual nonlinear residual, not BEM loads.
    """
    def __init__(self,mesh,mu,rho,*,max_cells=40000,supg=False,quadrature_order=4,linear_solver_factory=None,linear_method='strict_refined',pre_factor_check=None,memory_report=None,linear_system_observer=None):
        if type(rho) not in (int,float) or not math.isfinite(rho) or rho<=0:raise ValueError('Positive finite density required')
        if type(supg) is not bool or type(quadrature_order) is not int or quadrature_order not in (4,5,6):raise ValueError('Explicit SUPG bool and quadrature order4..6 required')
        if linear_method not in ('strict_refined','inexact_absolute_budget_v1','fixed_relative_forcing_v1'):raise ValueError('Explicit supported Newton linear method required')
        self.linear_system_observer=linear_system_observer
        self.memory_report=memory_report
        self._report_memory("before_base")
        self.linear_method=linear_method;self.supg_enabled=supg;self.quadrature_order=quadrature_order;self.Q,self.W=_quadrature(quadrature_order);self.N=_p2_values(self.Q)
        x,ww=np.polynomial.legendre.leggauss(quadrature_order);x=(x+1)/2;ww=ww/2
        self.TQ=np.array([[1-a,a*(1-b),a*b] for a in x for b in x]);self.TW=np.array([2*ww[i]*ww[j]*a for i,a in enumerate(x) for j,b in enumerate(x)])
        self.base=SymmetricStokes(mesh,mu,max_cells=max_cells,max_unknowns=400000,max_factor_nonzeros=30_000_000,linear_solver_factory=linear_solver_factory or _BlockStokes,pre_factor_check=pre_factor_check)
        self.rho=float(rho);self.mu=float(mu);b=self.base;m=b.mesh
        self._report_memory("after_base")
        self.dofs=(b.local[:,:,None]*3+np.arange(3)).reshape(-1,30)
        self.grad=np.empty((len(b.local),len(self.Q),10,3))
        for c,g in enumerate(m['barycentric_gradients']):self.grad[c]=_gradients(self.Q,g)
        self._report_memory('after_gradients')
        self.points=np.einsum('qi,cid->cqd',self.Q,m['vertices'][m['cells']])
        self.weights=m['cell_volumes'][:,None]*self.W
        self.boundary=[]
        for faces in m['boundary_patches'].values():
            for face in faces:
                c=int(m['face_owners'][face,0]);vertices=list(m['face_vertices'][face]);ids=[list(m['cells'][c]).index(v) for v in vertices]
                q=np.zeros((len(self.TQ),4));q[:,ids]=self.TQ
                self.boundary.append((c,face,_p2_values(q),q@m['vertices'][m['cells'][c]],self.TW*m['face_areas'][face]))

        self._report_memory('initialization_complete')

    def _report_memory(self,event):
        if self.memory_report is not None:
            from .propulsion_pod_inertial_cfd_memory import current_process_memory
            self.memory_report(event,current_process_memory())

    def operators(self,u,omega,origin,*,jacobian=True):
        """Exact degree-five volume quadrature; full consistent boundary flux."""
        b=self.base;m=b.mesh;rho=self.rho
        cross=np.array([[0.,-omega[2],omega[1]],[omega[2],0.,-omega[0]],[-omega[1],omega[0],0.]])
        uq=np.einsum('qi,cia->cqa',self.N,u[b.local]);gu=np.einsum('cia,cqib->cqab',u[b.local],self.grad)
        frame=np.cross(omega,self.points-origin);w=uq-frame
        from .propulsion_pod_transport_contractions import volume_transport_contractions
        skew,mass,extra=volume_transport_contractions(self.N,self.grad,self.weights,uq,gu,w,rho,jacobian=jacobian)
        block=skew[:,:,None,:,None]*np.eye(3)[None,None,:,None,:]+rho*mass[:,:,None,:,None]*cross[None,None,:,None,:]
        # axis layout c,i,a,j,b. Differentiating the transporting velocity adds:
        # 1/2 rho [Ni Nj (d_b u_a) - (d_b Ni) Nj u_a].
        boundary_flux=0.
        for c,face,n,points,weights in self.boundary:
            local=u[b.local[c]];velocity=n@local;wface=velocity-np.cross(omega,points-origin);normal=m['face_normals'][face]
            speed=wface@normal
            bm=.5*rho*np.einsum('qi,qj,q,q->ij',n,n,speed,weights)
            block[c]+=bm[:,None,:,None]*np.eye(3)[None,:,None,:]
            if jacobian:extra[c]+=.5*rho*np.einsum('qi,qj,qa,b,q->iajb',n,n,velocity,normal,weights)
            boundary_flux+=.5*rho*float(np.sum(weights*speed*np.sum(velocity*velocity,axis=1)))
        values=block.reshape(-1,30,30)
        rows=np.broadcast_to(self.dofs[:,:,None],values.shape).ravel();cols=np.broadcast_to(self.dofs[:,None,:],values.shape).ravel()
        cmat=coo_matrix((values.ravel(),(rows,cols)),shape=b.K.shape).tocsr()
        if jacobian:jmat=coo_matrix((extra.reshape(-1,30,30).ravel(),(rows,cols)),shape=b.K.shape).tocsr()+cmat
        else:jmat=None
        return cmat,jmat,boundary_flux

    def solve(self,boundary_velocity,omega_rad_s=(0.,0.,0.),origin_m=(0.,0.,0.),body_force=None,*,initial=None,max_iterations=30,tolerance=1e-9,cancel_check=None,iteration_callback=None,maximum_line_search_trials=7):
        line_search_steps=_line_search_steps(maximum_line_search_trials)
        b=self.base;omega=np.asarray(omega_rad_s,dtype=float);origin=np.asarray(origin_m,dtype=float)
        if omega.shape!=(3,) or origin.shape!=(3,) or not np.isfinite(omega).all() or not np.isfinite(origin).all():raise ValueError('Finite axis-speed vector and origin required')
        prescribed=np.zeros_like(b.xyz);seen={}
        for name,nodes in b.patch_nodes.items():
            for node in nodes:
                value=np.asarray(boundary_velocity(name,b.xyz[node]),dtype=float)
                if value.shape!=(3,) or not np.isfinite(value).all():raise ValueError('Invalid boundary velocity')
                if node in seen and not np.allclose(seen[node],value,rtol=1e-11,atol=1e-14):raise ValueError('Conflicting Dirichlet values')
                prescribed[node]=value;seen[node]=value
        force=np.zeros(b.K.shape[0]);body_quad=np.zeros((len(b.local),len(self.Q),3))
        if body_force is not None:
            for c,nodes in enumerate(b.local):
                f=np.array([body_force(x) for x in self.points[c]])
                if f.shape!=(len(self.Q),3) or not np.isfinite(f).all():raise ValueError('Nonfinite body force')
                body_quad[c]=f
                local=np.einsum('qi,qa,q->ia',self.N,f,self.weights[c])
                np.add.at(force,self.dofs[c],local.ravel())
        if initial is None:
            state=b.solve(boundary_velocity);u=state['u'].copy();p=state['p'].copy()
        else:u=np.array(initial['u'],dtype=float).copy();p=np.array(initial['p'],dtype=float).copy()
        u.ravel()[b.fixed]=prescribed.ravel()[b.fixed]
        n=len(b.free);pressure_mass=np.zeros(len(p))
        for c,cell in enumerate(b.mesh['cells']):np.add.at(pressure_mass,cell,b.mesh['cell_volumes'][c]/4)
        gauge=pressure_mass*b.sp;gauge/=np.linalg.norm(gauge);su=diags(b.su);sp=diags(b.sp);coupling=sp@b.B[:,b.free]@su
        history=[]
        def residual(velocity,pressure):
            if cancel_check and cancel_check():raise InterruptedError('Bounded inertial case cancelled')
            c,_,flux=self.operators(velocity,omega,origin,jacobian=False)
            physical=b.K@velocity.ravel()+c@velocity.ravel()-b.B.T@pressure-force
            if self.supg_enabled:
                from .propulsion_pod_inertial_cfd_supg import assemble
                stabilization,_,_,_=assemble(self,velocity,pressure,omega,origin,body_quad,jacobian=False);physical+=stabilization
            mass=b.B@velocity.ravel()
            mean=float(gauge@(pressure/b.sp)) if self.linear_method=='fixed_relative_forcing_v1' else 0.
            rr=np.r_[b.su*physical[b.free],-b.sp*mass,mean]
            scale=max(np.linalg.norm(b.su*force[b.free]),np.linalg.norm(b.su*(b.K@prescribed.ravel())[b.free]),np.linalg.norm(b.su*(c@prescribed.ravel())[b.free]),1e-30)
            return rr,physical,mass,c,flux,float(np.linalg.norm(rr)/scale)
        linear_solver_history=[];self.iteration_profile=[]
        self.last_iterate={'u':u.copy(),'p':p.copy()}
        for iteration in range(max_iterations+1):
            rr,physical,mass,c,flux,error=residual(u,p);history.append(error)
            if iteration_callback:iteration_callback(iteration,error)
            if error<tolerance:break
            if iteration==max_iterations:raise ValueError('Rotating Navier-Stokes nonlinear residual did not converge: '+str(history))
            profile_start=time.perf_counter();profile_cpu=time.process_time()
            _,j,_=self.operators(u,omega,origin,jacobian=True)
            transport_assembly_seconds=time.perf_counter()-profile_start;supg_start=time.perf_counter()
            jp=None;ju=None
            if self.supg_enabled:
                from .propulsion_pod_inertial_cfd_supg import assemble
                _,ju,jp,_=assemble(self,u,p,omega,origin,body_quad);j+=ju
            supg_assembly_seconds=time.perf_counter()-supg_start
            jf=b.K[b.free][:,b.free]+j[b.free][:,b.free]
            upper=-coupling.T if jp is None else -coupling.T+su@jp[b.free]@sp
            matrix=bmat([[su@jf@su,upper,None],[-coupling,None,gauge[:,None]],[None,gauge[None,:],None]],format='csc')
            if self.linear_system_observer is not None:self.linear_system_observer(matrix,-rr,{'iteration':iteration,'n_velocity':n,'gauge':gauge,'nonlinear_relative_error':error,'method':self.linear_method})
            self._report_memory("Newton_matrix_assembled")
            assembly_seconds=time.perf_counter()-profile_start;mark=time.perf_counter()
            preconditioner=b.factor.with_velocity(matrix)
            self._report_memory("Newton_preconditioner_ready")
            preconditioner_seconds=time.perf_counter()-mark;mark=time.perf_counter()
            from .propulsion_pod_inertial_cfd_linear import refined_gmres
            if self.linear_method=='fixed_relative_forcing_v1':
                from .propulsion_pod_inertial_cfd_forcing import solve_fixed_step
                delta,linear_history,merit_slope=solve_fixed_step(matrix,rr,preconditioner,n,gauge,cancel_check=cancel_check)
            elif self.linear_method=='inexact_absolute_budget_v1':
                from .propulsion_pod_inertial_cfd_inexact import solve_inexact_step
                delta,linear_history=solve_inexact_step(matrix,-rr,preconditioner,error,tolerance,cancel_check=cancel_check)
            else:delta,linear_history=refined_gmres(matrix,-rr,preconditioner,cancel_check=cancel_check)
            linear_seconds=time.perf_counter()-mark
            # Physical direction/descent are checked inside solve_fixed_step.
            # Residual-only trial evaluation does not need these factors/matrices.
            del j,jf,upper,jp,ju,matrix,preconditioner,c
            self._report_memory('Newton_linear_temporaries_released_before_line_search')
            mark=time.perf_counter()
            linear_solver_history.append(linear_history)
            accepted=False
            for attempted_trials,step in enumerate(line_search_steps,1):
                trial=u.copy();trial.ravel()[b.free]+=step*b.su*delta[:n];tp=p+step*b.sp*delta[n:-1]
                trial_residual=residual(trial,tp)
                if self.linear_method=='fixed_relative_forcing_v1':
                    from .propulsion_pod_inertial_cfd_forcing import armijo_trial
                    decreases=armijo_trial(rr,trial_residual[0],step,merit_slope)
                else:decreases=trial_residual[-1]<error
                if decreases:
                    u=trial;p=tp;accepted=True;break
            self.iteration_profile.append({'iteration':iteration,'Jacobian_and_matrix_assembly_s':assembly_seconds,'transport_Jacobian_s':transport_assembly_seconds,'SUPG_Jacobian_s':supg_assembly_seconds,'scaled_block_assembly_s':assembly_seconds-transport_assembly_seconds-supg_assembly_seconds,'preconditioner_s':preconditioner_seconds,'Krylov_and_refinement_s':linear_seconds,'line_search_s':time.perf_counter()-mark,'total_profiled_wall_s':time.perf_counter()-profile_start,'total_profiled_cpu_s':time.process_time()-profile_cpu,'accepted_step':step if accepted else None,'configured_line_search_trials':maximum_line_search_trials,'attempted_line_search_trials':attempted_trials,'linear_iterations':sum(v['iterations'] for v in linear_history),'factor_options':getattr(b.factor,'last_factor_options',None),'factor_options_sha256':getattr(b.factor,'last_factor_options_sha256',None),'native_factor_storage_entries':getattr(b.factor,'last_factor_nonzeros',None)})
            if accepted:self.last_iterate={'u':u.copy(),'p':p.copy()}
            # Prior Newton matrices/factor closures must not overlap next assembly.
            del delta,trial_residual,trial,tp
            self._report_memory('Newton_iteration_temporaries_released')
            if not accepted:raise ValueError('Nonlinear Newton line search failed')
        uq=np.einsum('qi,cia->cqa',self.N,u[b.local]);gu=np.einsum('cia,cqib->cqab',u[b.local],self.grad)
        divergence=np.trace(gu,axis1=2,axis2=3)
        correction=.5*self.rho*float(np.sum(self.weights*divergence*np.sum(uq*uq,axis=2)))
        divergence_l2=float(np.sqrt(np.sum(self.weights*divergence*divergence)))
        cwork=float(u.ravel()@(c@u.ravel()));diss=float(u.ravel()@(b.K@u.ravel()));bodywork=float(u.ravel()@force);pressurework=float(p@mass)
        reactions=np.zeros_like(u);reactions.ravel()[b.fixed]=physical[b.fixed]
        supg_diagnostics={};supg_work=0.
        if self.supg_enabled:
            from .propulsion_pod_inertial_cfd_supg import assemble
            _,_,_,supg_diagnostics=assemble(self,u,p,omega,origin,body_quad,jacobian=False);supg_work=supg_diagnostics['SUPG_power_w']
        work=float(np.sum(reactions*u));scale=max(abs(work),abs(diss),abs(cwork),abs(bodywork),abs(supg_work),1e-30)
        defect=abs(work-diss-cwork-supg_work+pressurework+bodywork)/scale
        if defect>1e-7:raise ValueError('Inertial physical boundary work identity failed')
        state={'u':u,'p':p,'reaction':reactions,'diagnostics':{'nonlinear_relative_residual':error,'Newton_history':history,'viscous_dissipation_w':diss,'transport_work_w':cwork,'boundary_kinetic_flux_w':flux,'body_work_w':bodywork,'pressure_work_w':pressurework,'boundary_work_w':work,'relative_energy_residual':defect,'weak_continuity_norm_m3_s':float(np.linalg.norm(mass)),'tetrahedra':len(b.mesh['cells']),'velocity_nodes':len(u),'pressure_nodes':len(p),'weak_incompressibility_only':True,'SUPG_enabled':self.supg_enabled,'volume_quadrature_order':self.quadrature_order,'SUPG_power_w':supg_work,'SUPG_work_relative':abs(supg_work)/scale,**supg_diagnostics,'divergence_l2_m3_over_2_s':divergence_l2,'Temam_advective_energy_correction_w':correction,'continuity_energy_correction_relative':abs(correction)/scale,'transport_vs_boundary_flux_relative':abs(cwork-flux)/scale}}
        state['diagnostics']['linear_solver_history']=linear_solver_history
        state['diagnostics']['Newton_component_timings']=self.iteration_profile
        state['diagnostics']['Newton_linear_method']=self.linear_method
        if self.linear_method=='fixed_relative_forcing_v1':state['diagnostics']['actual_scaled_pressure_mean_residual']=float(gauge@(p/b.sp))
        return state

def _admit_coaxial_outer(vertices,triangles,axis,origin,radius,half_length):
    """Admit an inscribed polygon-cylinder, including planar-face mesh nodes.

    Interior side-facet vertices have radius smaller than the circumradius;
    testing every vertex against radius alone incorrectly rejects true meshes.
    Every exterior triangle must lie on one cap or one convex hull side plane.
    """
    from scipy.spatial import ConvexHull
    points=np.asarray(vertices)[np.asarray(triangles,dtype=int)];p=points-origin
    basis=np.eye(3)[int(np.argmin(abs(axis)))];e1=np.cross(axis,basis);e1/=np.linalg.norm(e1);e2=np.cross(axis,e1)
    q=np.stack([p@e1,p@e2],axis=2);allq=q.reshape(-1,2);hull=ConvexHull(allq);corners=allq[hull.vertices];tol=max(radius,half_length)*1e-8
    if np.any(abs(np.linalg.norm(corners,axis=1)-radius)>tol):raise ValueError('Outer convex polygon vertices do not match cylinder radius')
    axial=p@axis;plane=q@hull.equations[:,:2].T+hull.equations[:,2]
    cap=np.all(abs(axial-half_length)<tol,axis=1)|np.all(abs(axial+half_length)<tol,axis=1)
    side=np.any(np.all(abs(plane)<tol,axis=1),axis=1)
    if np.any(~(cap|side)) or np.any(abs(axial)>half_length+tol) or np.any(plane>tol) or not np.any(np.all(abs(axial-half_length)<tol,axis=1)) or not np.any(np.all(abs(axial+half_length)<tol,axis=1)):raise ValueError('Exterior triangles do not match declared coaxial faceted cylinder/caps')
    return {'polygon_facets':len(hull.vertices),'maximum_radius_deficit_fraction':float(1-np.min(-hull.equations[:,2])/radius)}


CONTRACT='spike/rotor-inertial-cfd/v1'
RESULT_CONTRACT='spike/rotor-inertial-cfd-result/v1'


def evaluate(spec,omega_rad_s):
    """Pure quasi-steady laminar MRF trial with actual no-slip blade boundaries.

    Numerically converged does not mean load/mesh/turbulence qualified. No
    unsteady fluid state or changed-speed Euler acceleration is represented.
    Returns complete fields for artifact retention and bounded preview samples.
    """
    import hashlib,json,itertools
    from .propulsion_pod_rotor_cfd import _EDGES
    required={'contract','mesh','rotor_patches','axis_unit','origin_m','dynamic_viscosity_pa_s','density_kg_m3','speed_of_sound_m_s','outer_boundary'}
    if not isinstance(spec,dict) or not required<=set(spec) or not set(spec)<=required|{'stabilization','quadrature_order'} or spec['contract']!=CONTRACT:raise ValueError('Invalid inertial rotor CFD contract')
    if type(omega_rad_s) not in (int,float) or not math.isfinite(omega_rad_s) or omega_rad_s<0:raise ValueError('Finite nonnegative angular speed required')
    for name in ('dynamic_viscosity_pa_s','density_kg_m3','speed_of_sound_m_s'):
        if type(spec[name]) not in (int,float) or not math.isfinite(spec[name]) or spec[name]<=0:raise ValueError('Positive finite '+name+' required')
    axis=np.asarray(spec['axis_unit'],dtype=float);origin=np.asarray(spec['origin_m'],dtype=float)
    if axis.shape!=(3,) or origin.shape!=(3,) or not np.isfinite(axis).all() or not np.isfinite(origin).all() or abs(np.linalg.norm(axis)-1)>1e-12:raise ValueError('Finite origin and unit axis required')
    outer=spec['outer_boundary']
    if not isinstance(outer,dict) or set(outer)!={'kind','radius_m','half_length_m'} or outer['kind']!='coaxial_cylinder':raise ValueError('Explicit coaxial stationary cylindrical far boundary required')
    for name in ('radius_m','half_length_m'):
        if type(outer[name]) not in (int,float) or not math.isfinite(outer[name]) or outer[name]<=0:raise ValueError('Invalid cylinder size')
    canonical=json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(canonical)>64*1024**2:raise ValueError('Explicit inertial CFD mesh request exceeds64MB')
    stabilization=spec.get('stabilization','none')
    if stabilization not in ('none','supg'):raise ValueError('Explicit none or supg stabilization required')
    solver=RotatingNavierStokes(spec['mesh'],spec['dynamic_viscosity_pa_s'],spec['density_kg_m3'],supg=stabilization=='supg',quadrature_order=spec.get('quadrature_order',4));b=solver.base
    patches=spec['rotor_patches']
    if not isinstance(patches,list) or not patches or any(not isinstance(p,str) for p in patches) or len(set(patches))!=len(patches) or not set(patches)<set(b.patch_nodes):raise ValueError('Distinct rotor patches and stationary exterior required')
    rotor=np.unique(np.concatenate([b.patch_nodes[p] for p in patches]));stationary=np.unique(np.concatenate([v for p,v in b.patch_nodes.items() if p not in patches]))
    if np.intersect1d(rotor,stationary).size:raise ValueError('Closed rotor must be separate from outer vessel')
    triangles=np.concatenate([b.mesh['face_vertices'][b.mesh['boundary_patches'][p]] for p in patches]);edges={}
    for tri in triangles:
        for e in itertools.combinations(tri,2):e=tuple(sorted(map(int,e)));edges[e]=edges.get(e,0)+1
    if any(v!=2 for v in edges.values()):raise ValueError('Rotor surface must be closed')
    outer_triangles=np.concatenate([b.mesh['face_vertices'][faces] for p,faces in b.mesh['boundary_patches'].items() if p not in patches]);outer_evidence=_admit_coaxial_outer(b.mesh['vertices'],outer_triangles,axis,origin,outer['radius_m'],outer['half_length_m'])
    rr=b.xyz[rotor]-origin;radius=np.linalg.norm(rr-(rr@axis)[:,None]*axis,axis=1);tip_mach=float(omega_rad_s*max(radius)/spec['speed_of_sound_m_s'])
    if tip_mach>.3:raise ValueError('Incompressible reference rejects blade Mach above0.3')
    Omega=axis*omega_rad_s
    state=solver.solve(lambda patch,x:np.cross(Omega,x-origin) if patch in patches else np.zeros(3),Omega,origin)
    force=np.sum(state['reaction'][rotor],axis=0);moment=np.sum(np.cross(b.xyz[rotor]-origin,state['reaction'][rotor]),axis=0);torque=float(axis@moment);thrust=-float(axis@force);power=torque*omega_rad_s
    raw=b.recovered_surface(state,patches,origin,axis);recovery=abs(torque-raw['axis_moment_nm'])/abs(torque) if torque else 0.
    speed=0.
    for nodes in b.local:
        nodal=state['u'][nodes];controls=[*nodal[:4]];controls.extend(2*nodal[4+k]-.5*(nodal[i]+nodal[j]) for k,(i,j) in enumerate(_EDGES));speed=max(speed,max(np.linalg.norm(v) for v in controls))
    if speed/spec['speed_of_sound_m_s']>.3:raise ValueError('Continuous P2 speed bound exceeds incompressible Mach0.3')
    sampled=np.unique(np.linspace(0,len(b.local)-1,min(len(b.local),256),dtype=int));centres=b.mesh['cell_centroids'][sampled];values=np.einsum('qi,cia->cqa',_p2_values(np.full((1,4),.25)),state['u'][b.local[sampled]])[:,0]
    return {'contract':RESULT_CONTRACT,'status':'completed','model_status':'experimental_laminar_quasisteady_MRF','production_qualified':False,'load_qualified':False,'load_status':'mesh_traction_domain_and_physical_regime_convergence_required','omega_rad_s':float(omega_rad_s),'torque_nm':torque,'thrust_n':thrust,'power_w':power,'torque_from_recovered_Cauchy_stress_nm':raw['axis_moment_nm'],'thrust_from_recovered_Cauchy_stress_n':-float(axis@np.asarray(raw['force_on_fluid_n'])),'traction_torque_recovery_relative_difference':recovery,'tip_reynolds':float(spec['density_kg_m3']*omega_rad_s*max(radius)**2/spec['dynamic_viscosity_pa_s']),'continuous_speed_Mach_bound':speed/spec['speed_of_sound_m_s'],'outer_geometry':outer_evidence,'diagnostics':state['diagnostics'],'fields':{'P2_nodes_m':b.xyz.tolist(),'P2_velocity_absolute_in_rotor_coordinates_m_s':state['u'].tolist(),'P1_nodes_m':b.mesh['vertices'].tolist(),'P1_pressure_pa':state['p'].tolist(),'tetra_vertices':b.mesh['cells'].tolist()},'preview':{'cell_ids':sampled.tolist(),'centres_m':centres.tolist(),'velocity_m_s':values.tolist(),'sampling_only':True},'spec_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'limitations':['Actual laminar inertial equations and blade walls; no BEM or supplied torque coefficient','Steady constant-speed rotor frame only: no fluid stored-energy/Euler acceleration state','Faceted-cylinder outer boundary approximates rotationally invariant far field; outer geometry/domain convergence required','Weak P2/P1 incompressibility with explicit Temam correction; corrected weak work is not physical traction validation','No turbulence/transition, total-energy, compressible, conjugate-cooling or measured-hardware qualification','Numerical residual closure does not promote unconverged blade loads to qualified coupling']}
