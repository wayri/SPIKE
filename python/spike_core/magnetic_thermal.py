# SPDX-License-Identifier: Apache-2.0
"""Extruded planar heat conduction and bounded fixed-mesh magnetic coupling."""
from __future__ import annotations

import math
import warnings

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import MatrixRankWarning, spsolve

MAX_NODES = 20_000
MAX_ELEMENTS = 40_000
MAX_STEPS = 1000
MAX_HISTORY_VALUES = 1_000_000


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, name, positive=False):
    _require(type(value) in (int, float), name+" must be a real number")
    value = float(value)
    _require(math.isfinite(value) and (not positive or value > 0),
             name+" must be finite"+(" and positive" if positive else ""))
    return value


class PlanarThermalOperator:
    """Prepared constant thermal matrices for a fixed extruded planar mesh."""

    def __init__(self, *, nodes_m, triangles, region_ids, materials, stack_depth_m,
                 convection_edges=None, dirichlet_temperature_k=None, lumped_capacity=False):
        self.depth = _number(stack_depth_m, "stack_depth_m", True)
        self.nodes = np.asarray(nodes_m, dtype=float)
        raw = np.asarray(triangles)
        _require(self.nodes.ndim == 2 and self.nodes.shape[1] == 2
                 and 3 <= len(self.nodes) <= MAX_NODES and np.all(np.isfinite(self.nodes)),
                 "nodes_m requires bounded finite Nx2 coordinates")
        _require(raw.ndim == 2 and raw.shape[1] == 3 and 1 <= len(raw) <= MAX_ELEMENTS
                 and raw.dtype.kind in "iu" and np.all(raw >= 0) and np.all(raw < len(self.nodes)),
                 "triangles requires bounded integer Mx3 indices")
        self.triangles = raw.astype(np.int64)
        _require(len(np.unique(np.sort(raw, axis=1),axis=0)) == len(raw), "Duplicate triangles")
        _require(len(np.unique(raw)) == len(self.nodes), "Unused thermal nodes")
        _require(isinstance(region_ids,(list,tuple)) and len(region_ids)==len(raw)
                 and all(isinstance(k,str) and k for k in region_ids), "Invalid thermal region IDs")
        _require(isinstance(materials,dict) and set(materials)==set(region_ids),
                 "Thermal materials must exactly match regions")
        self.region_ids = list(region_ids)
        properties = {}
        for key, value in materials.items():
            _require(isinstance(value,dict) and set(value)=={"k_w_m_k","rho_kg_m3","cp_j_kg_k"},
                     "Thermal material requires exactly k_w_m_k, rho_kg_m3, cp_j_kg_k")
            properties[key] = tuple(_number(value[name],name,True)
                                   for name in ("k_w_m_k","rho_kg_m3","cp_j_kg_k"))
        k, rho, cp = np.asarray([properties[key] for key in region_ids]).T
        p = self.nodes[raw]
        dx1, dx2 = p[:,1]-p[:,0],p[:,2]-p[:,0]
        determinant = dx1[:,0]*dx2[:,1]-dx1[:,1]*dx2[:,0]
        scale2 = np.maximum(np.sum(dx1**2,axis=1),np.sum(dx2**2,axis=1))
        _require(np.all(np.abs(determinant)>1e-12*scale2), "Degenerate thermal triangle")
        self.areas = np.abs(determinant)/2
        gradients = np.stack((np.stack((p[:,1,1]-p[:,2,1],p[:,2,0]-p[:,1,0]),axis=1),
                              np.stack((p[:,2,1]-p[:,0,1],p[:,0,0]-p[:,2,0]),axis=1),
                              np.stack((p[:,0,1]-p[:,1,1],p[:,1,0]-p[:,0,0]),axis=1)),axis=1)
        gradients /= determinant[:,None,None]
        rows = np.repeat(raw,3,axis=1).ravel()
        cols = np.tile(raw,(1,3)).ravel()
        shape = (len(self.nodes),len(self.nodes))
        local_k = self.depth*self.areas[:,None,None]*k[:,None,None]*np.einsum("eik,ejk->eij",gradients,gradients)
        self.conduction = coo_matrix((local_k.ravel(),(rows,cols)),shape=shape).tocsr()
        local_c = (self.depth*self.areas*rho*cp)[:,None,None]*(np.ones((3,3))+np.eye(3))/12
        capacity = coo_matrix((local_c.ravel(),(rows,cols)),shape=shape).tocsr()
        _require(type(lumped_capacity) is bool,"lumped_capacity must be boolean")
        self.capacity = diags(np.asarray(capacity.sum(axis=1)).ravel()).tocsr() if lumped_capacity else capacity
        self.lumped = lumped_capacity
        self.fixed = {} if dirichlet_temperature_k is None else dirichlet_temperature_k
        _require(isinstance(self.fixed,dict) and all(type(i) is int and 0<=i<len(self.nodes) for i in self.fixed),
                 "Invalid prescribed-temperature indices")
        self.fixed = {i:_number(value,"prescribed temperature",True) for i,value in self.fixed.items()}
        _require(all(v<=10000 for v in self.fixed.values()),"Prescribed temperature exceeds 10000 K")
        self.fixed_indices = np.array(sorted(self.fixed),dtype=int)
        self.free = np.setdiff1d(np.arange(len(self.nodes)),self.fixed_indices)
        all_edges = np.sort(np.vstack((raw[:,[0,1]],raw[:,[1,2]],raw[:,[2,0]])),axis=1)
        unique_edges,counts = np.unique(all_edges,axis=0,return_counts=True)
        _require(np.all(counts<=2),"Nonmanifold thermal edges")
        exterior = {tuple(edge) for edge in unique_edges[counts==1]}
        edges = [] if convection_edges is None else convection_edges
        _require(isinstance(edges,list) and len(edges)<=len(exterior),"Invalid convection edge list")
        er,ec,ev = [],[],[]
        self.ambient_load = np.zeros(len(self.nodes))
        seen = set()
        for boundary in edges:
            _require(isinstance(boundary,dict) and set(boundary)=={"nodes","h_w_m2_k","ambient_temperature_k"},
                     "Convection edge requires nodes, h_w_m2_k, ambient_temperature_k")
            pair = boundary["nodes"]
            _require(isinstance(pair,(list,tuple)) and len(pair)==2 and all(type(i) is int for i in pair),
                     "Convection nodes must contain two integer indices")
            edge = tuple(sorted(pair))
            _require(edge in exterior and edge not in seen,"Convection must name unique exterior edges")
            seen.add(edge)
            h = _number(boundary["h_w_m2_k"],"h_w_m2_k",True)
            ambient = _number(boundary["ambient_temperature_k"],"ambient_temperature_k",True)
            _require(ambient<=10000,"Ambient temperature exceeds 10000 K")
            length = float(np.linalg.norm(self.nodes[pair[0]]-self.nodes[pair[1]]))
            coefficient = h*self.depth*length
            er.extend([pair[0],pair[0],pair[1],pair[1]])
            ec.extend([pair[0],pair[1],pair[0],pair[1]])
            ev.extend(coefficient*np.array([2,1,1,2])/6)
            self.ambient_load[pair] += coefficient*ambient/2
        self.convection = coo_matrix((ev,(er,ec)),shape=shape).tocsr()
        self.stiffness = self.conduction+self.convection
        _require(all(np.all(np.isfinite(matrix.data)) for matrix in
                     (self.capacity,self.conduction,self.convection))
                 and np.all(np.isfinite(self.ambient_load)), "Thermal assembly exceeds numerical range")

    def step(self, previous_temperature_k, time_step_s, element_power_w):
        dt = _number(time_step_s,"time_step_s",True)
        old = np.asarray(previous_temperature_k,dtype=float)
        power = np.asarray(element_power_w,dtype=float)
        _require(old.shape==(len(self.nodes),) and np.all(np.isfinite(old))
                 and np.all((old>0)&(old<=10000)), "Previous temperature must contain 0<T<=10000 K per node")
        _require(power.shape==(len(self.triangles),) and np.all(np.isfinite(power))
                 and np.all(power>=0),"One finite nonnegative watt value per element is required")
        source = np.zeros(len(self.nodes))
        np.add.at(source,self.triangles.ravel(),np.repeat(power/3,3))
        matrix = self.capacity/dt+self.stiffness
        rhs = self.capacity@old/dt+source+self.ambient_load
        temperature = old.copy()
        for i,value in self.fixed.items():
            temperature[i] = value
        reduced_rhs = rhs[self.free]-matrix[self.free][:,self.fixed_indices]@temperature[self.fixed_indices]
        if len(self.free):
            with warnings.catch_warnings():
                warnings.simplefilter("error",MatrixRankWarning)
                temperature[self.free] = spsolve(matrix[self.free][:,self.free],reduced_rhs)
        _require(np.all(np.isfinite(temperature)) and np.all((temperature>0)&(temperature<=10000)),
                 "Thermal solution outside finite (0,10000] K range; refine step or check sources")
        reaction = self.capacity@((temperature-old)/dt)+self.stiffness@temperature-source-self.ambient_load
        storage = float(np.sum(self.capacity@(temperature-old)))
        convection = dt*float(np.sum(self.convection@temperature-self.ambient_load))
        prescribed = dt*float(np.sum(reaction[self.fixed_indices]))
        input_energy = dt*float(np.sum(power))
        residual = input_energy+prescribed-storage-convection
        _require(all(math.isfinite(v) for v in (storage,convection,prescribed,input_energy,residual)),
                 "Thermal audit exceeds numerical range")
        free_residual = float(np.linalg.norm(reaction[self.free]))
        linear_scale = max(float(np.linalg.norm(rhs[self.free])),
                           float(np.linalg.norm((matrix@temperature)[self.free])),1e-30)
        _require(free_residual<=1e-8*linear_scale+1e-10,"Thermal linear residual failed")
        return {
            "contract":"spike/planar-thermal-step-result/v1","model_status":"experimental",
            "production_qualified":False,"temperature_k":temperature.tolist(),
            "element_mean_temperature_k":temperature[self.triangles].mean(axis=1).tolist(),
            "element_power_w":power.tolist(),"nodal_heat_capacity_j_per_k":np.asarray(self.capacity.sum(axis=1)).ravel().tolist(),
            "capacity_form":"lumped" if self.lumped else "consistent",
            "free_residual_norm_w":free_residual,"time_step_s":dt,
            "heat_audit":{"input_energy_j":input_energy,"stored_energy_change_j":storage,
                          "convection_energy_out_j":convection,
                          "prescribed_temperature_energy_in_j":prescribed,
                          "balance_residual_j":residual},
            "limitations":["Extruded planar isotropic conduction; no axial conduction, end-face cooling, radiation or CFD.",
                           "Only explicitly supplied exterior edges exchange convection heat.",
                           "Constant thermal properties and backward-Euler time discretization."],
        }


def solve_thermal_step(*, nodes_m, triangles, region_ids, materials, stack_depth_m,
                       previous_temperature_k, time_step_s, element_power_w,
                       convection_edges=None, dirichlet_temperature_k=None, lumped_capacity=False):
    """Prepare and solve one independent thermal step."""
    op = PlanarThermalOperator(nodes_m=nodes_m,triangles=triangles,region_ids=region_ids,
                              materials=materials,stack_depth_m=stack_depth_m,
                              convection_edges=convection_edges,
                              dirichlet_temperature_k=dirichlet_temperature_k,lumped_capacity=lumped_capacity)
    return op.step(previous_temperature_k,time_step_s,element_power_w)


def simulate_magnetic_thermal(*, nodes_m, triangles, region_ids, magnetic_materials,
                              thermal_materials, stack_depth_m, dirichlet_a_wb_per_m,
                              initial_a_wb_per_m, initial_temperature_k, time_step_s,
                              steps, conductivity_temperature_coefficients=None,
                              current_density_a_per_m2=None, winding_element_loss_w=None,
                              convection_edges=None, dirichlet_temperature_k=None,
                              lumped_capacity=False, snapshot_stride=1):
    """Fixed-mesh sequential coupling with regional conductivity-temperature feedback."""
    from .magnetic_fem import solve_eddy_current_step
    import copy
    dt = _number(time_step_s,"time_step_s",True)
    _require(type(steps) is int and 1<=steps<=MAX_STEPS,"steps must be 1..1000")
    _require(type(snapshot_stride) is int and 1<=snapshot_stride<=steps,"Invalid snapshot_stride")
    count = (steps//snapshot_stride)+1+(steps%snapshot_stride!=0)
    _require(count*(len(nodes_m)*2+len(triangles)*4)<=MAX_HISTORY_VALUES,
             "Stored magnetic/thermal history exceeds resource limit")
    _require(steps*len(nodes_m)<=20_000_000,"Coupled work exceeds node-step budget")
    _require(isinstance(magnetic_materials,dict) and set(magnetic_materials)==set(region_ids),
             "Magnetic materials must exactly match mesh regions")
    _require(steps*len(magnetic_materials)<=MAX_HISTORY_VALUES,
             "Stored conductivity audit exceeds resource limit")
    thermal = PlanarThermalOperator(nodes_m=nodes_m,triangles=triangles,region_ids=region_ids,
                                   materials=thermal_materials,stack_depth_m=stack_depth_m,
                                   convection_edges=convection_edges,
                                   dirichlet_temperature_k=dirichlet_temperature_k,
                                   lumped_capacity=lumped_capacity)
    coefficients = {} if conductivity_temperature_coefficients is None else conductivity_temperature_coefficients
    _require(isinstance(coefficients,dict) and set(coefficients)<=set(magnetic_materials),
             "Unknown conductivity-temperature region")
    coefficients = copy.deepcopy(coefficients)
    for key,row in coefficients.items():
        _require(isinstance(row,dict) and set(row)=={"alpha_per_k","reference_temperature_k"},
                 "Conductivity law requires alpha_per_k and reference_temperature_k")
        row["alpha_per_k"] = _number(row["alpha_per_k"],"alpha_per_k")
        row["reference_temperature_k"] = _number(row["reference_temperature_k"],"reference_temperature_k",True)
        _require(magnetic_materials[key].get("conductivity_s_m",0)>0,
                 "Temperature feedback requires positive reference conductivity")
    extra = np.zeros(len(triangles)) if winding_element_loss_w is None else np.asarray(winding_element_loss_w,dtype=float)
    _require(extra.shape==(len(triangles),) and np.all(np.isfinite(extra)) and np.all(extra>=0),
             "Additional winding losses require finite nonnegative watts per element")
    temperature = np.asarray(initial_temperature_k,dtype=float)
    _require(temperature.shape==(len(nodes_m),) and np.all(np.isfinite(temperature))
             and np.all((temperature>0)&(temperature<=10000)),"Invalid initial temperature")
    a = np.asarray(initial_a_wb_per_m,dtype=float)
    _require(a.shape==(len(nodes_m),) and np.all(np.isfinite(a)),"Invalid initial magnetic potential")
    regions = np.asarray(region_ids)
    groups = {key:np.flatnonzero(regions==key) for key in magnetic_materials}
    history = [{"time_s":0.0,"potential_a_wb_per_m":a.tolist(),"temperature_k":temperature.tolist()}]
    audits = []
    for index in range(1,steps+1):
        laws = copy.deepcopy(magnetic_materials)
        mean_temperature = temperature[thermal.triangles].mean(axis=1)
        sigma_used = {}
        for key,row in coefficients.items():
            selected = groups[key]
            mean = float(thermal.areas[selected]@mean_temperature[selected]/np.sum(thermal.areas[selected]))
            denominator = 1+row["alpha_per_k"]*(mean-row["reference_temperature_k"])
            _require(math.isfinite(denominator) and denominator>0,
                     "Conductivity-temperature denominator must stay positive")
            laws[key]["conductivity_s_m"] = magnetic_materials[key]["conductivity_s_m"]/denominator
            _require(math.isfinite(laws[key]["conductivity_s_m"]) and laws[key]["conductivity_s_m"]>0,
                     "Temperature-adjusted conductivity exceeds numerical range")
        sigma_used = {key:float(row.get("conductivity_s_m",0)) for key,row in laws.items()}
        magnetic = solve_eddy_current_step(nodes_m=nodes_m,triangles=triangles,region_ids=region_ids,
                    materials=laws,stack_depth_m=stack_depth_m,dirichlet_a_wb_per_m=dirichlet_a_wb_per_m,
                    previous_a_wb_per_m=a.tolist(),time_step_s=dt,
                    current_density_a_per_m2=current_density_a_per_m2)
        watts = np.asarray(magnetic["element_joule_loss_w"])+extra
        heat = thermal.step(temperature.tolist(),dt,watts.tolist())
        a = np.asarray(magnetic["potential_a_wb_per_m"])
        temperature = np.asarray(heat["temperature_k"])
        audits.append({"time_s":index*dt,"magnetic":magnetic["energy_audit"],
                       "thermal":heat["heat_audit"],"eddy_joule_energy_j":dt*magnetic["joule_loss_w"],
                       "additional_winding_energy_j":dt*float(extra.sum()),
                       "conductivity_s_m":sigma_used})
        if index%snapshot_stride==0 or index==steps:
            history.append({"time_s":index*dt,"potential_a_wb_per_m":a.tolist(),
                            "temperature_k":temperature.tolist(),"element_b_t":magnetic["element_b_t"],
                            "element_joule_loss_w":magnetic["element_joule_loss_w"],
                            "element_power_w":watts.tolist()})
    return {"contract":"spike/planar-magnetic-thermal-result/v1","model_status":"experimental",
            "production_qualified":False,"history":history,"step_audits":audits,
            "final_magnetic_result":magnetic,"final_thermal_result":heat,
            "limitations":["Fixed mesh and stationary conductors; no motion or remeshing.",
                           "Sequential explicit temperature feedback requires coupling-step refinement.",
                           "Conductivity uses the previous volume-weighted mean temperature per region.",
                           "Magnetic B-H and PM laws and thermal properties are temperature independent.",
                           "Additional winding watts are user-supplied losses, not solved circuit heating.",
                           "No CFD, 3D end effects, radiation, hysteresis or measured device qualification."]}

