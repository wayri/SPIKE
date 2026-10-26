# SPDX-License-Identifier: Apache-2.0
"""P2 field adapter for the same source-bound OpenMotor geometry and ALE map.

Original adapter; CAD-derived inputs retain CERN-OHL-W-2.0 source rights.
No calibrated H070 directional law or manufactured winding continuity claim.
"""
from __future__ import annotations
import copy,math
import numpy as np
from .propulsion_pod_real_motor import RealMotorFieldModel, _number
from .propulsion_pod_magnetic_p2 import P2MagneticOperator, QUADRATURE, MU0

class RealMotorP2FieldModel(RealMotorFieldModel):
    def __init__(self,geometry,spec):
        super().__init__(geometry,spec)
        if 'bh_curve' in self.spec['steel']:raise ValueError('P2 adapter currently requires explicit linear isotropic steel')
        self._p2_operators={}

    def _operator_at(self,angle):
        if angle in self._p2_operators:return self._p2_operators[angle]
        nodes,tris,regions,boundary,area,materials,chi,signed,ratio=self._setup_state(angle)
        materials=copy.deepcopy(materials)
        for value in materials.values():
            if 'relative_permeability' in value:value['mu_r']=value.pop('relative_permeability')
        op=P2MagneticOperator(nodes.tolist(),tris.tolist(),self._solver_regions,materials,.025,maximum_nodes=100000)
        data=(op,nodes,tris,regions,boundary,chi,signed,ratio)
        if len(self._p2_operators)>=3:self._p2_operators.clear()
        self._p2_operators[angle]=data
        return data

    def _state(self,currents,angle):
        key=tuple(currents)+(float(angle),)
        if key in self._cache:return self._cache[key]
        op,nodes,tris,regions,boundary,chi,signed,ratio=self._operator_at(angle)
        fixed={int(k):0. for k in op.boundary_dofs(boundary)}
        result=op.solve((chi@currents).tolist(),dirichlet_a_wb_per_m=fixed)
        A=np.array(result['potential_a_wb_per_m']);flux=np.array([op.source_load(chi[:,k])@A for k in range(3)])
        Bq=np.array(result['quadrature_b_t']);Bcenter=op.evaluate_b(A,np.array([[1/3,1/3,1/3]]))[:,0,:]
        # B is linear inside an affine P2 element; recover its values at the
        # three geometric vertices for arbitrary clipped-annulus quadrature.
        Bvertices=op.evaluate_b(A,np.eye(3))
        field={'nodes_m':nodes.tolist(),'triangles':tris.tolist(),'region_ids':regions,
            'potential_a_wb_per_m':A[:len(nodes)].tolist(),'element_b_t':Bcenter.tolist(),
            'p2_nodes_m':op.nodes_m.tolist(),'p2_triangles':op.triangles_p2.tolist(),
            'p2_potential_a_wb_per_m':A.tolist(),'p2_quadrature_b_t':Bq.tolist(),
            'p2_barycentric_b_t':Bvertices.tolist(),'element_area_m2':op.areas.tolist(),
            'winding_chi_per_m2':chi.tolist(),'formulation':'conforming six-node P2 Az on straight native-section triangles'}
        diagnostics={**result['diagnostics'],'nodes':len(nodes),'p2_nodes':len(op.nodes_m),'triangles':len(tris),
            'signed_turn_integrals':signed.tolist(),'minimum_jacobian_ratio':ratio,
            'mesh_method':'fixed native affine geometry/ALE; quadratic field basis',
            'convergence':{'converged':True,'residual_norm_a_m':result['diagnostics']['free_residual_a_m'],
                'relative_residual':result['diagnostics']['relative_free_residual']},'torque_convergence_qualified':False}
        out={'flux_linkage_wb_turn':flux.tolist(),'magnetic_energy_j':result['magnetic_energy_j'],
             'magnetic_coenergy_j':result['current_source_coenergy_j'],'field':field,'diagnostics':diagnostics}
        if len(self._cache)>=12:self._cache.clear()
        self._cache[key]=out
        return out

    def volume_weighted_virtual_work(self,currents,angle_rad,annulus_radii_m=None):
        theta=_number(angle_rad,'angle',-1e5,1e5)
        i=self._currents(currents)
        central=self._state(i,theta);op,nodes,tris,regions,boundary,chi,signed,ratio=self._operator_at(theta)
        weights=self._weights
        if annulus_radii_m is not None:
            if not isinstance(annulus_radii_m,(list,tuple)) or len(annulus_radii_m)!=2:raise ValueError('Annulus pair required')
            a=_number(annulus_radii_m[0],'inner radius',.04421,.04457);b=_number(annulus_radii_m[1],'outer radius',.04422,.04458)
            if a>=b:raise ValueError('Annulus radii must be ordered')
            weights=np.clip((b-np.linalg.norm(nodes,axis=1))/(b-a),0,1)
        velocity=weights[:,None]*np.column_stack((-nodes[:,1],nodes[:,0]))
        G=np.einsum('eia,eib->eab',velocity[tris],op.barycentric_gradients)
        B=np.array(central['field']['p2_quadrature_b_t'])
        density=(np.einsum('eqa,eab,eqb->eq',B,G,B)-.5*np.sum(B*B,axis=2)*np.trace(G,axis1=1,axis2=2)[:,None])/MU0
        air=np.array([name=='air' or name.startswith('air_mesh_separator') for name in regions])
        return {'torque_n_m':-.025*float(op.areas[air]@density[air].mean(axis=1)),
                'method':'P2 field quadrature of exact affine-geometry ALE vacuum stress contraction',
                'annulus_radii_m':annulus_radii_m,'torque_convergence_qualified':False}

    def fixed_potential_virtual_work(self,currents,angle_rad,delta_rad=None):
        theta=_number(angle_rad,'angle',-1e5,1e5);delta=self.delta if delta_rad is None else _number(delta_rad,'delta',1e-7,.001)
        if abs(theta-self.anchor)+delta>self.patch+1e-14:raise ValueError('Virtual-work perturbation exceeds local patch')
        i=self._currents(currents);central=self._state(i,theta);A=np.array(central['field']['p2_potential_a_wb_per_m']);integrals=[]
        for angle in (theta+delta,theta-delta):
            op,nodes,tris,regions,boundary,chi,signed,ratio=self._operator_at(angle)
            B=op.evaluate_b(A);air=np.array([name=='air' or name.startswith('air_mesh_separator') for name in regions])
            integrals.append(op.areas[air]*np.sum(B[air]*B[air],axis=2).mean(axis=1)/(2*MU0))
        return {'torque_n_m':-.025*float(np.sum(integrals[0]-integrals[1]))/(2*delta),
                'method':'P2 fixed-central-potential vacuum functional difference','delta_rad':delta,'torque_convergence_qualified':False}

    @staticmethod
    def _currents(currents):
        if not isinstance(currents,(list,tuple,np.ndarray)) or len(currents)!=3:raise ValueError('Three balanced phase currents required')
        i=[_number(x,'current',-150,150) for x in currents]
        if abs(sum(i))>1e-10:raise ValueError('Floating star requires balanced currents')
        return i

    def evaluate(self,currents,angle,include_field=False):
        result=super().evaluate(currents,angle,include_field)
        result['contract']='spike/real-motor-geometry-p2-field/v1'
        result['torque_method']='P2 scalar field, exact affine-geometry vacuum shape derivative'
        return result

    def linear_ports(self,angle_rad,include_fields=False):
        result=super().linear_ports(angle_rad,include_fields)
        op=self._operator_at(float(angle_rad))[0]
        result['field_formulation']='conforming six-node P2 Az, fixed affine native geometry'
        result['factorization_count']=op.factorization_count
        result['p2_nodes']=len(op.nodes_m)
        return result
