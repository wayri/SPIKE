# SPDX-License-Identifier: Apache-2.0
"""Independent, fail-closed convergence evidence for coupled propulsion loads."""
import hashlib
import json
import math


def assess_load_convergence(samples, mesh_tolerance=.02, recovery_tolerance=.05,
                            domain_tolerance=.02):
    """Compare three fixed-domain grids and one independently enlarged domain.

    Inputs are supplied case summaries, not a fitted torque law. Relative changes
    alone cannot qualify a nearly zero load: an explicit positive absolute
    tolerance in physical units must accompany each quantity. This assessment
    never proves asymptotic convergence or upgrades material/regime validation.
    Hashes identify reported cases; they do not by themselves prove execution.
    """
    if not isinstance(samples,list) or len(samples)!=4:
        raise ValueError('Three mesh levels and one enlarged-domain case required')
    for tolerance in (mesh_tolerance,recovery_tolerance,domain_tolerance):
        if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or not 0<tolerance<=.1:
            raise ValueError('Convergence tolerances must be positive and at most ten percent')
    required={'mesh_scale','domain_scale','torque_nm','thrust_n','torque_absolute_tolerance_nm',
              'thrust_absolute_tolerance_n','traction_relative_error','continuity_energy_relative_error',
              'nonlinear_relative_residual','geometry_sha256','physics_sha256','case_sha256'}
    for s in samples:
        if not isinstance(s,dict) or set(s)!=required:raise ValueError('Incomplete convergence case evidence')
        for key in required-{'geometry_sha256','physics_sha256','case_sha256'}:
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]):raise ValueError('Nonfinite case evidence: '+key)
        for key in ('geometry_sha256','physics_sha256','case_sha256'):
            if not isinstance(s[key],str) or len(s[key])!=64 or any(c not in '0123456789abcdef' for c in s[key]):
                raise ValueError('Exact case/source hashes required')
        if min(s['mesh_scale'],s['domain_scale'],s['torque_absolute_tolerance_nm'],s['thrust_absolute_tolerance_n'])<=0:
            raise ValueError('Positive mesh/domain scales and physical absolute tolerances required')
        if min(s['traction_relative_error'],s['continuity_energy_relative_error'],s['nonlinear_relative_residual'])<0:
            raise ValueError('Residual/error magnitudes cannot be negative')
    if len({s['case_sha256'] for s in samples})!=4:raise ValueError('Four distinct executed cases required')
    if len({s['geometry_sha256'] for s in samples})!=1 or len({s['physics_sha256'] for s in samples})!=1:
        raise ValueError('Geometry and physical operating point must remain identical')
    a,b,c,d=samples
    if not a['mesh_scale']>b['mesh_scale']>c['mesh_scale'] or d['mesh_scale']!=c['mesh_scale']:
        raise ValueError('Three successively finer grids and a matched fine enlarged domain required')
    if not a['domain_scale']==b['domain_scale']==c['domain_scale'] or not d['domain_scale']>c['domain_scale']:
        raise ValueError('Mesh and domain refinement must be independent')
    if min(a['mesh_scale']/b['mesh_scale'],b['mesh_scale']/c['mesh_scale'])<1.4 or d['domain_scale']/c['domain_scale']<1.5:
        raise ValueError('Insufficient declared mesh refinement or domain enlargement')
    reasons=[];quantities={}
    for name,absolute_key in (('torque_nm','torque_absolute_tolerance_nm'),('thrust_n','thrust_absolute_tolerance_n')):
        v=[s[name] for s in samples];absolute=min(s[absolute_key] for s in samples)
        delta0=v[1]-v[0];delta1=v[2]-v[1]
        bound=absolute+mesh_tolerance*abs(v[2]);domain_bound=absolute+domain_tolerance*abs(v[3])
        monotone=delta0*delta1>=0 or max(abs(delta0),abs(delta1))<=absolute
        decreasing=abs(delta1)<=abs(delta0) or abs(delta1)<=absolute
        grid_ok=monotone and decreasing and abs(delta1)<=bound
        domain_ok=abs(v[3]-v[2])<=domain_bound
        quantities[name]={'coarse_change':delta0,'fine_change':delta1,'mesh_bound':bound,
                          'domain_change':v[3]-v[2],'domain_bound':domain_bound,
                          'mesh_passed':grid_ok,'domain_passed':domain_ok}
        if not grid_ok:reasons.append(name+': grid load convergence failed')
        if not domain_ok:reasons.append(name+': outer-domain independence failed')
    for index,s in enumerate(samples):
        if s['traction_relative_error']>recovery_tolerance:reasons.append(f'case {index}: independent traction recovery failed')
        if s['continuity_energy_relative_error']>.001:reasons.append(f'case {index}: continuity energy correction too large')
        if s['nonlinear_relative_residual']>1e-7:reasons.append(f'case {index}: nonlinear residual failed')
    return {'contract':'spike/propulsion-load-convergence/v1','declared_load_change_screen_passed':not reasons,
            'production_qualified':False,'physical_regime_qualified':False,'convergence_proven':False,
            'interpretation':'Declared load-change screen only; absolute tolerances are caller budgets, not error estimates. Mesh scales must describe comparable local wall/gap resolution.',
            'quantities':quantities,
            'reasons':reasons,'case_hashes':[s['case_sha256'] for s in samples],
            'evidence_sha256':hashlib.sha256(json.dumps(samples,sort_keys=True,allow_nan=False).encode()).hexdigest()}
