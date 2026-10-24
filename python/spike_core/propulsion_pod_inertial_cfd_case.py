# SPDX-License-Identifier: Apache-2.0
"""Bounded actual adapted-STL air MRF continuation, artifact-first research job.

Auxiliary density stages are never advertised as air operating points. The
physical target is accepted only if its own nonlinear/geometry checks finish.
"""
import argparse,hashlib,json,math,time,os
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from .propulsion_pod_inertial_cfd import RotatingNavierStokes,_admit_coaxial_outer,_line_search_steps
from .propulsion_pod_rotor_cfd import _EDGES,_p2_values


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _write(path,value):
    if isinstance(value,dict):value={**value,'artifact_written_utc':datetime.now(timezone.utc).isoformat(),'process_cpu_seconds':time.process_time()}
    path=Path(path);tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)


def run_case(mesh_npz,geometry_dir,output_dir,*,omega_rad_s=200.,density_kg_m3=1.225,dynamic_viscosity_pa_s=1.81e-5,max_seconds=1800,preconditioner='pressure_mass',restart_case=None,linear_method='strict_refined',density_growth_factor=3.,maximum_line_search_trials=7):
    if not 0<omega_rad_s<=650 or not 0<density_kg_m3<10 or not 1e-6<dynamic_viscosity_pa_s<.01 or not 60<=max_seconds<=3600:raise ValueError('Explicit bounded air research inputs required')
    if isinstance(density_growth_factor,bool) or not isinstance(density_growth_factor,(int,float)) or not math.isfinite(density_growth_factor) or not 1<density_growth_factor<=3:raise ValueError('Explicit density growth factor must be finite, greater than one and at most three')
    _line_search_steps(maximum_line_search_trials)
    output=Path(output_dir).resolve();output.mkdir(parents=True,exist_ok=True);geometry=Path(geometry_dir).resolve();mesh_path=Path(mesh_npz).resolve();start=time.monotonic();deadline=start+max_seconds
    sourcefiles=[Path(__file__),Path(__file__).with_name('propulsion_pod_inertial_cfd.py'),Path(__file__).with_name('propulsion_pod_inertial_cfd_supg.py'),Path(__file__).with_name('propulsion_pod_rotor_cfd.py'),Path(__file__).with_name('cfd_tetra_mesh.py'),Path(__file__).with_name('cfd_tetra_intersections.py')];hashes={p.name:_sha(p) for p in sourcefiles}
    sourcefiles.append(Path(__file__).with_name('propulsion_pod_transport_contractions.py'));sourcefiles.append(Path(__file__).with_name('propulsion_pod_inertial_cfd_memory.py'));sourcefiles.append(Path(__file__).with_name('propulsion_pod_inertial_cfd_linear.py'));hashes={p.name:_sha(p) for p in sourcefiles}
    sourcefiles.append(Path(__file__).with_name('propulsion_pod_inertial_cfd_preflight.py'));hashes={p.name:_sha(p) for p in sourcefiles}
    if linear_method not in ('strict_refined','inexact_absolute_budget_v1','fixed_relative_forcing_v1'):raise ValueError('Explicit supported Newton linear method required')
    if linear_method=='inexact_absolute_budget_v1':
        sourcefiles.append(Path(__file__).with_name('propulsion_pod_inertial_cfd_inexact.py'));hashes={p.name:_sha(p) for p in sourcefiles}
    if linear_method=='fixed_relative_forcing_v1':
        sourcefiles.append(Path(__file__).with_name('propulsion_pod_inertial_cfd_forcing.py'));hashes={p.name:_sha(p) for p in sourcefiles}
    if preconditioner not in ('pressure_mass','simple_schur','current_jacobian_schur_strong','current_jacobian_schur_signed_strong'):raise ValueError('Explicit supported preconditioner required')
    if preconditioner=='simple_schur':
        sourcefiles.append(Path(__file__).with_name('propulsion_pod_inertial_cfd_schur.py'));hashes={p.name:_sha(p) for p in sourcefiles}
    if preconditioner in ('current_jacobian_schur_strong','current_jacobian_schur_signed_strong'):
        if restart_case is None:raise ValueError('Explicit field restart required for current-Jacobian research preconditioner')
        sourcefiles.extend([Path(__file__).with_name('propulsion_pod_inertial_cfd_current.py'),Path(__file__).with_name('propulsion_pod_jacobian_schur.py')]);hashes={p.name:_sha(p) for p in sourcefiles}
    snapshot=output/'source_snapshot';snapshot.mkdir(exist_ok=True)
    for p in sourcefiles:(snapshot/p.name).write_bytes(p.read_bytes())
    proof=json.loads((geometry/'source-distance-evidence.json').read_text());surface=geometry/'casalino-simulation-surface.stl';surface_hash=_sha(surface)
    directions=[v for k,v in proof.items() if k.startswith(('original_to','regularized_to','repaired_to','adapted_to','cleaned_to')) and isinstance(v,dict)]
    if proof.get('simulation_surface_sha256')!=surface_hash or len(directions)!=2 or not all(v.get('passed') for v in directions):raise ValueError('Complete BIDIRECTIONAL geometry-bound evidence for this exact adapted surface required')
    raw=np.load(mesh_path);vertices=raw['vertices_m'];cells=raw['tetrahedra'];used=np.unique(cells);mapping=np.full(len(vertices),-1,dtype=int);mapping[used]=np.arange(len(used));vertices=vertices[used]
    mesh={'contract':'spike/cfd-tetra-mesh/v1','units':'m','vertices':vertices.tolist(),'cells':mapping[cells].tolist(),'boundary_patches':{'rotor':mapping[raw['rotor_triangles']].tolist(),'stationary':mapping[raw['stationary_triangles']].tolist()}}
    if any(np.any(np.array(faces)<0) for faces in mesh['boundary_patches'].values()):raise ValueError('Surface orphan nodes in raw native mesh')
    origin=np.array([0.,.01,0.]);axis=np.array([0.,1.,0.]);Omega=axis*omega_rad_s;R=.45;L=.45
    outer_evidence=_admit_coaxial_outer(raw['vertices_m'],raw['stationary_triangles'],axis,origin,R,L)
    request={'contract':'spike/actual-adapted-propeller-air-MRF-research/v1','mesh_sha256':_sha(mesh_path),'surface_sha256':surface_hash,'source_geometry_sha256':proof.get('source_sha256'),'omega_rad_s':omega_rad_s,'axis_unit':axis.tolist(),'origin_m':origin.tolist(),'dynamic_viscosity_pa_s':dynamic_viscosity_pa_s,'density_kg_m3':density_kg_m3,'speed_of_sound_m_s':343.,'fluid_inputs_supplied_not_source_measured_conditions':True,'outer_radius_m':R,'outer_half_length_m':L,'outer_geometry_evidence':outer_evidence,'SUPG':True,'quadrature_order':4,'max_seconds':max_seconds,'maximum_line_search_trials':maximum_line_search_trials,'density_growth_factor':float(density_growth_factor),'source_files':hashes,'geometry_distance_proof_sha256':_sha(geometry/'source-distance-evidence.json'),'load_qualified':False}
    request['transport_tensor_resource_limit']={'maximum_output_bytes':224*1024**2,'maximum_cells_with_Jacobian':224*1024**2//(1100*8),'not_a_physical_qualification_limit':True};request['process_id']=os.getpid();request['started_utc']=datetime.now(timezone.utc).isoformat();request['process_cpu_seconds_at_request']=time.process_time()
    _write(output/'request.json',request);history=[];last=None;fraction=1e-6;accepted=0.;consecutive_failures=0;step=0
    def cancelled():return time.monotonic()>deadline
    try:
        _write(output/'progress.json',{'status':'preparing_mesh_and_P2_system','elapsed_seconds':time.monotonic()-start,'cells':len(cells)})
        factory=None
        if preconditioner=='simple_schur':
            from .propulsion_pod_inertial_cfd_schur import SimpleSchurStokes
            if restart_case is not None:
                from functools import partial
                factory=partial(SimpleSchurStokes,reference_velocity=False)
            else:factory=SimpleSchurStokes
        if preconditioner in ('current_jacobian_schur_strong','current_jacobian_schur_signed_strong'):
            from .propulsion_pod_inertial_cfd_current import RestartCurrentSchur
            from functools import partial
            diagonal_policy='signed_current_nonzero_v1' if preconditioner=='current_jacobian_schur_signed_strong' else 'positive_current_v1'
            factory=partial(RestartCurrentSchur,diagonal_policy=diagonal_policy)
            request['preconditioner_parameters']={'diagonal_policy':diagonal_policy,'velocity_drop_tol':1e-6,'velocity_fill_factor':20,'maximum_native_factor_storage_entries':30000000,'current_C_and_G_including_SUPG':True,'no_automatic_preconditioner_fallback':True}
            request['factor_options']={'diagonal_policy':diagonal_policy,'velocity_drop_tol':1e-6,'velocity_fill_factor':20.,'maximum_factor_nonzeros':30000000}
            request['factor_options_sha256']=hashlib.sha256(json.dumps(request['factor_options'],sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest()
        request['reference_velocity_seed_factor_omitted']=preconditioner in ('simple_schur','current_jacobian_schur_strong','current_jacobian_schur_signed_strong') and restart_case is not None;request['linear_preconditioner']=preconditioner;request['Newton_linear_method']=linear_method;_write(output/'request.json',request)
        def pressure_preflight(base):
            from .propulsion_pod_inertial_cfd_preflight import check_pressure_kernel
            gauge=np.asarray(base.A[len(base.free):-1,-1].toarray()).ravel()
            check_pressure_kernel(base.A,len(base.free),gauge,output/'pressure-kernel-preflight',pressure_scaling=base.sp,metadata={'raw_mesh_sha256':request['mesh_sha256'],'surface_sha256':surface_hash,'source_distance_sha256':request['geometry_distance_proof_sha256'],'before_velocity_factor':True})
        memory_history=[]
        def memory_report(event,values):
            memory_history.append({'event':event,'elapsed_s':time.monotonic()-start,**values});_write(output/'memory-profile.json',memory_history)
        def linear_system_observer(matrix,rhs,context):
            from scipy.sparse import save_npz
            folder=output/'current-linear-systems'/(f'stage-{step:02d}-iteration-00' if context['iteration']==0 else f'stage-{step:02d}-latest-nonzero-iteration');folder.mkdir(parents=True,exist_ok=True)
            save_npz(folder/'matrix.npz',matrix);np.savez_compressed(folder/'vectors.npz',rhs=rhs,gauge=context['gauge'],n_velocity=context['n_velocity'])
            current=solver.last_iterate
            np.savez_compressed(folder/'current-state.npz',P2_nodes_m=solver.base.xyz,P2_velocity_m_s=current['u'],P1_nodes_m=solver.base.mesh['vertices'],P1_pressure_pa=current['p'],tetrahedra=solver.base.mesh['cells'],cell_P2_nodes=solver.base.local,density_fraction=fraction,accepted_as_result=False)
            _write(folder/'evidence.json',{'contract':'spike/retained-current-Jacobian/v1','step':step,'density_fraction':fraction,'iteration':context['iteration'],'bounded_retention_policy':'first_and_latest_nonzero_per_stage','method':context['method'],'nonlinear_relative_error':context['nonlinear_relative_error'],'n_velocity':context['n_velocity'],'current_state_sha256':_sha(folder/'current-state.npz'),'state_is_current_Newton_iterate_not_accepted_density_stage':True,'matrix_sha256':_sha(folder/'matrix.npz'),'vectors_sha256':_sha(folder/'vectors.npz'),'mesh_sha256':request['mesh_sha256'],'surface_sha256':request['surface_sha256'],'source_geometry_sha256':request['source_geometry_sha256'],'source_files':hashes,'request_sha256':_sha(output/'request.json'),'new_PDE_reconstruction':False,'load_qualified':False})
        solver=RotatingNavierStokes(mesh,dynamic_viscosity_pa_s,density_kg_m3,supg=True,linear_solver_factory=factory,linear_method=linear_method,pre_factor_check=pressure_preflight,memory_report=memory_report,linear_system_observer=linear_system_observer);b=solver.base;rotor=b.patch_nodes['rotor'];radius=float(np.linalg.norm((b.xyz[rotor]-origin)[:,[0,2]],axis=1).max())
        if restart_case is not None:
            prior=Path(restart_case).resolve();oldrequest=json.loads((prior/'request.json').read_text());oldrecord=json.loads((prior/'last-accepted-stage.json').read_text())
            for key in ('mesh_sha256','surface_sha256','omega_rad_s','dynamic_viscosity_pa_s','density_kg_m3','SUPG','quadrature_order'):
                if oldrequest.get(key)!=request[key]:raise ValueError('Restart case input mismatch: '+key)
            saved=prior/f"stage-{oldrecord['step']:02d}-actual-fields.npz";data=np.load(saved)
            if not np.array_equal(data['P2_nodes_m'],b.xyz) or not np.array_equal(data['P1_nodes_m'],b.mesh['vertices']) or not np.array_equal(data['tetrahedra'],b.mesh['cells']) or not np.array_equal(data['cell_P2_nodes'],b.local):raise ValueError('Restart exact geometry/P2 numbering mismatch')
            fraction=float(oldrecord['density_fraction'])
            if not 0<fraction<=1:raise ValueError('Invalid supplied restart fraction')
            last={'u':data['P2_velocity_m_s'],'p':data['P1_pressure_pa']}
            request['restart']={'case':str(prior),'field_sha256':_sha(saved),'record_sha256':_sha(prior/'last-accepted-stage.json'),'requires_current_full_residual_revalidation':True};_write(output/'request.json',request)
        if omega_rad_s*radius/343>.3:raise ValueError('Target blade speed violates incompressible Mach0.3 limit')
        velocity=lambda name,x:np.cross(Omega,x-origin) if name=='rotor' else np.zeros(3)
        while True:
            if cancelled():raise InterruptedError('Declared case wall-clock budget exhausted')
            step+=1;solver.rho=density_kg_m3*fraction;stage_start=time.monotonic()
            def report(iteration,error):
                _write(output/'progress.json',{'status':'solving_auxiliary_density' if fraction<1 else 'solving_actual_air_target','step':step,'density_fraction':fraction,'target_omega_rad_s':omega_rad_s,'iteration':iteration,'nonlinear_relative_residual':error,'elapsed_seconds':time.monotonic()-start})
                _write(output/'Newton-profile.json',{'step':step,'density_fraction':fraction,'iterations':getattr(solver,'iteration_profile',[])})
                print('stage',step,'fraction',fraction,'Newton',iteration,'residual',error,flush=True)
            try:
                state=solver.solve(velocity,Omega,origin,initial=last,max_iterations=20,cancel_check=cancelled,iteration_callback=report,maximum_line_search_trials=maximum_line_search_trials)
                if preconditioner in ('current_jacobian_schur_strong','current_jacobian_schur_signed_strong') and b.factor.last_factor_options is not None and b.factor.last_factor_options_sha256!=request['factor_options_sha256']:raise ValueError('Actual factor options differ from bound research request')
                force=np.sum(state['reaction'][rotor],axis=0);moment=np.sum(np.cross(b.xyz[rotor]-origin,state['reaction'][rotor]),axis=0);torque=float(axis@moment);thrust=-float(axis@force);rawstress=b.recovered_surface(state,['rotor'],origin,axis)
                speed=0.
                for nodes in b.local:
                    nodal=state['u'][nodes];control=[*nodal[:4]];control.extend(2*nodal[4+k]-.5*(nodal[i]+nodal[j]) for k,(i,j) in enumerate(_EDGES));speed=max(speed,max(np.linalg.norm(v) for v in control))
                if speed/343>.3 or torque<0:raise ValueError('Computed velocity/shaft-reaction physical range failed; no air target acceptance')
                record={'step':step,'density_fraction':fraction,'actual_air_target':fraction==1.,'auxiliary_continuation_only':fraction<1.,'torque_nm':torque,'thrust_n':thrust,'power_w':torque*omega_rad_s,'raw_Cauchy_torque_nm':rawstress['axis_moment_nm'],'traction_torque_recovery_relative_difference':abs(torque-rawstress['axis_moment_nm'])/abs(torque) if torque else 0.,'tip_reynolds':solver.rho*omega_rad_s*radius*radius/dynamic_viscosity_pa_s,'continuous_speed_Mach_bound':speed/343,'diagnostics':state['diagnostics'],'stage_seconds':time.monotonic()-stage_start,'elapsed_seconds':time.monotonic()-start,'load_qualified':False}
                history.append(record);_write(output/'continuation-history.json',history);np.savez_compressed(output/f'stage-{step:02d}-actual-fields.npz',P2_nodes_m=b.xyz,P2_velocity_m_s=state['u'],P1_nodes_m=b.mesh['vertices'],P1_pressure_pa=state['p'],tetrahedra=b.mesh['cells'],cell_P2_nodes=b.local)
                _write(output/'last-accepted-stage.json',record);last=state;accepted=fraction;consecutive_failures=0
                if fraction==1.:
                    sampled=np.unique(np.linspace(0,len(b.local)-1,min(256,len(b.local)),dtype=int));u=np.einsum('qi,cia->cqa',_p2_values(np.full((1,4),.25)),state['u'][b.local[sampled]])[:,0]
                    _write(output/'field-preview.json',{'sampling_only':True,'cell_ids':sampled.tolist(),'centres_m':b.mesh['cell_centroids'][sampled].tolist(),'absolute_velocity_in_rotor_coordinates_m_s':u.tolist()})
                    result={**record,'status':'completed_unqualified_actual_air_target','model':'steady_laminar_SUPG_MRF','production_qualified':False,'convergence_proven':False,'source_files_at_start':hashes,'source_files_at_end':{p.name:_sha(p) for p in sourcefiles},'limitations':['steady constant-speed fluid trial only','supplied air properties, not matched measured atmospheric conditions','adapted surface and finite faceted outer cylinder','no turbulence/transition/conjugate cooling','weak/physical Cauchy load, volume/domain/surface refinement and stabilization independence required']};_write(output/'result.json',result);_write(output/'progress.json',result);return result
                fraction=min(1.,fraction*(10 if fraction<1e-3 else density_growth_factor))
            except (ValueError,RuntimeError) as error:
                failure={'step':step,'density_fraction':fraction,'actual_air_target':fraction==1.,'error':str(error),'stage_seconds':time.monotonic()-stage_start,'elapsed_seconds':time.monotonic()-start};_write(output/f'stage-{step:02d}-failure.json',failure);consecutive_failures+=1
                if accepted==0 or consecutive_failures>=2:raise
                fraction=math.sqrt(accepted*fraction)
    except Exception as error:
        if 'solver' in locals() and hasattr(solver,'last_iterate'):
            np.savez_compressed(output/'partial-unqualified-fields.npz',P2_nodes_m=b.xyz,P2_velocity_m_s=solver.last_iterate['u'],P1_nodes_m=b.mesh['vertices'],P1_pressure_pa=solver.last_iterate['p'],tetrahedra=b.mesh['cells'],cell_P2_nodes=b.local,density_fraction=fraction,accepted_as_result=False)
            _write(output/'Newton-profile.json',{'step':step,'density_fraction':fraction,'iterations':getattr(solver,'iteration_profile',[]),'partial_iterate_is_not_accepted_result':True})
        if hasattr(error,'matrix'):
            from scipy.sparse import save_npz
            save_npz(output/'failed-Newton-matrix.npz',error.matrix);np.savez_compressed(output/'failed-Newton-vectors.npz',rhs=error.rhs,iterate=error.iterate)
            _write(output/'failed-Newton-linear-history.json',error.linear_history)
        failure={'status':'stopped_without_qualified_air_result','error_type':type(error).__name__,'error':str(error),'last_accepted_density_fraction':accepted,'last_stage_is_actual_air':accepted==1.,'elapsed_seconds':time.monotonic()-start,'source_files_at_start':hashes,'source_files_at_end':{p.name:_sha(p) for p in sourcefiles},'load_qualified':False};_write(output/'failure.json',failure);_write(output/'progress.json',failure);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mesh_npz');parser.add_argument('geometry_dir');parser.add_argument('output_dir');parser.add_argument('--omega',type=float,default=200.);parser.add_argument('--seconds',type=int,default=1800);parser.add_argument('--preconditioner',choices=('pressure_mass','simple_schur','current_jacobian_schur_strong','current_jacobian_schur_signed_strong'),default='pressure_mass');parser.add_argument('--restart-case');parser.add_argument('--density-growth-factor',type=float,default=3.);parser.add_argument('--maximum-line-search-trials',type=int,default=7);parser.add_argument('--linear-method',choices=('strict_refined','inexact_absolute_budget_v1','fixed_relative_forcing_v1'),default='strict_refined');args=parser.parse_args();run_case(args.mesh_npz,args.geometry_dir,args.output_dir,omega_rad_s=args.omega,max_seconds=args.seconds,preconditioner=args.preconditioner,restart_case=args.restart_case,linear_method=args.linear_method,density_growth_factor=args.density_growth_factor,maximum_line_search_trials=args.maximum_line_search_trials)
