# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Fully developed plane-channel momentum and conjugate solid/fluid energy.

Steady incompressible constant-property laminar flow; 2-D finite-volume thermal
field with axial conduction and first-order upwind energy advection. This is
not an arbitrary-enclosure Navier-Stokes or turbulence implementation.
"""
from collections.abc import Mapping
import math
import warnings
import numpy as np
from scipy.sparse import lil_matrix, diags
from scipy.sparse.linalg import spsolve, MatrixRankWarning
from .structured_solid_thermal import _number, _positive_int, _strict_keys, StructuredThermalError

CONTRACT = "spike/laminar-channel-cht/v1"
RESULT_CONTRACT = "spike/laminar-channel-cht-result/v1"


def _positive(value, name):
    return _number(value, name, minimum=1e-20)


def _parse(request):
    if not isinstance(request, Mapping) or request.get("contract") != CONTRACT:
        raise StructuredThermalError(f"Expected {CONTRACT}")
    _strict_keys(request, {"contract", "geometry", "grid", "fluid", "walls", "drive", "boundaries"}, "request")
    sections = {}
    allowed = {"geometry": {"length_m", "fluid_height_m", "width_m", "lower_wall_thickness_m", "upper_wall_thickness_m"},
        "grid": {"nx", "fluid_cells", "lower_wall_cells", "upper_wall_cells"},
        "fluid": {"density_kg_m3", "dynamic_viscosity_pa_s", "specific_heat_j_kgk", "conductivity_w_mk"},
        "walls": {"lower_conductivity_w_mk", "upper_conductivity_w_mk", "lower_heat_w_m3", "upper_heat_w_m3"},
        "drive": {"pressure_gradient_pa_m", "inlet_temperature_k"}, "boundaries": {"lower", "upper"}}
    for name, keys in allowed.items():
        value = request.get(name)
        if not isinstance(value, Mapping) or set(value) != keys:
            raise StructuredThermalError(f"{name} requires exactly {sorted(keys)}")
        sections[name] = value
    g, grid, f, w, d, boundaries = [sections[k] for k in allowed]
    geo = {k: _positive(v,k) for k,v in g.items()}
    sizes = {k: _positive_int(v,k,maximum=256) for k,v in grid.items()}
    if sizes["fluid_cells"] < 2:
        raise StructuredThermalError("At least two fluid cells required")
    count = sizes["nx"] * (sizes["fluid_cells"]+sizes["lower_wall_cells"]+sizes["upper_wall_cells"])
    if count > 8192:
        raise StructuredThermalError("CHT sparse-direct reference admits at most8192 cells")
    fluid = {k: _positive(v,k) for k,v in f.items()}
    walls = {k: (_positive(v,k) if "conductivity" in k else _number(v,k)) for k,v in w.items()}
    drive = {"pressure_gradient_pa_m": _number(d["pressure_gradient_pa_m"], "pressure_gradient_pa_m", minimum=0),
             "inlet_temperature_k": _positive(d["inlet_temperature_k"], "inlet_temperature_k")}
    for name, bc in boundaries.items():
        if not isinstance(bc, Mapping):
            raise StructuredThermalError("Boundary must be an object")
        kinds = {"adiabatic": {"type"}, "temperature": {"type", "temperature_k"},
                 "convection": {"type", "ambient_temperature_k", "coefficient_w_m2k"}}
        if not isinstance(bc.get("type"), str) or bc["type"] not in kinds or set(bc) != kinds[bc["type"]]:
            raise StructuredThermalError("Unsupported exterior boundary")
        for key,value in bc.items():
            if key != "type":
                _positive(value,key)
    return geo,sizes,fluid,walls,drive,boundaries


def solve_laminar_channel_cht(request, *, cancel_check=None):
    try:
        def cancel():
            if cancel_check is not None and cancel_check():
                raise StructuredThermalError("CHT solve cancelled")
        geo,sizes,fluid,walls,drive,boundaries = _parse(request)
        cancel()
        nx,nf,nl,nu = [sizes[k] for k in ("nx","fluid_cells","lower_wall_cells","upper_wall_cells")]
        length,height,width = [geo[k] for k in ("length_m","fluid_height_m","width_m")]
        dx,h = length/nx,height/nf
        rho,mu,cp,kf = [fluid[k] for k in ("density_kg_m3","dynamic_viscosity_pa_s","specific_heat_j_kgk","conductivity_w_mk")]
        gradient,tin = drive["pressure_gradient_pa_m"],drive["inlet_temperature_k"]
        # Nodal -mu*u''=dp/dx, with no-slip at both solid-fluid interfaces.
        momentum = diags([-np.ones(nf-2),2*np.ones(nf-1),-np.ones(nf-2)],[-1,0,1],format="csc")
        rhs_u = np.full(nf-1,gradient*h*h/mu)
        inner = np.asarray(spsolve(momentum,rhs_u))
        velocity_nodes = np.concatenate(([0.],inner,[0.]))
        velocity = (velocity_nodes[:-1]+velocity_nodes[1:])/2
        flow = float(np.sum(velocity)*h*width)
        discrete_reynolds = rho*(flow/(height*width))*(2*height)/mu
        # Admission is a physical-domain condition, independent of mesh error.
        reynolds = rho*(gradient*height**2/(12*mu))*(2*height)/mu
        if not math.isfinite(reynolds) or reynolds > 2000 or np.any(velocity < 0):
            raise StructuredThermalError("Flow outside admitted Re<=2000 forward laminar envelope")
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            momentum_residual = float(np.linalg.norm(momentum@inner-rhs_u)/max(np.linalg.norm(rhs_u),1e-30))
        ny=nl+nf+nu
        dy=np.array([geo["lower_wall_thickness_m"]/nl]*nl+[h]*nf+[geo["upper_wall_thickness_m"]/nu]*nu)
        k=np.array([walls["lower_conductivity_w_mk"]]*nl+[kf]*nf+[walls["upper_conductivity_w_mk"]]*nu)
        viscous = mu*(np.diff(velocity_nodes)/h)**2
        heat=np.array([walls["lower_heat_w_m3"]]*nl+viscous.tolist()+[walls["upper_heat_w_m3"]]*nu)
        n=nx*ny
        matrix=lil_matrix((n,n)); rhs=np.repeat(heat*dx*dy*width,nx)
        adv=rho*cp*velocity*h*width
        inlet=[]; exterior=[]
        def edge(a,b,g):
            matrix[a,a]+=g; matrix[b,b]+=g; matrix[a,b]-=g; matrix[b,a]-=g
        for j in range(ny):
            cancel()
            for i in range(nx):
                cell=j*nx+i
                if i+1<nx: edge(cell,cell+1,k[j]*dy[j]*width/dx)
                if j+1<ny: edge(cell,cell+nx,dx*width/(dy[j]/(2*k[j])+dy[j+1]/(2*k[j+1])))
                if nl<=j<nl+nf:
                    transport=adv[j-nl]
                    matrix[cell,cell]+=transport
                    if i: matrix[cell,cell-1]-=transport
                    else:
                        conduction=2*k[j]*dy[j]*width/dx
                        matrix[cell,cell]+=conduction
                        rhs[cell]+=(transport+conduction)*tin
                        inlet.append((cell,conduction))
                if j in (0,ny-1):
                    bc=boundaries["lower" if j==0 else "upper"]
                    if bc["type"]!="adiabatic":
                        resistance=dy[j]/(2*k[j])
                        ambient=bc.get("temperature_k",bc.get("ambient_temperature_k"))
                        if bc["type"]=="convection": resistance+=1/bc["coefficient_w_m2k"]
                        conductance=dx*width/resistance
                        matrix[cell,cell]+=conductance; rhs[cell]+=conductance*ambient
                        exterior.append((cell,conductance,ambient))
        operator=matrix.tocsc()
        if not np.all(np.isfinite(operator.data)) or not np.all(np.isfinite(rhs)):
            raise StructuredThermalError("Nonfinite derived thermal operator")
        cancel()
        with warnings.catch_warnings():
            warnings.simplefilter("error",MatrixRankWarning)
            temperature=np.asarray(spsolve(operator,rhs))
        cancel()
        if not np.all(np.isfinite(temperature)) or np.any(temperature<=0):
            raise StructuredThermalError("Invalid absolute temperature solution")
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            linear_residual=float(np.linalg.norm(operator@temperature-rhs)/max(np.linalg.norm(rhs),1e-30))
        field=temperature.reshape(ny,nx)
        generated=float(np.sum(heat*dy)*length*width)
        inlet_conduction=math.fsum(g*(tin-temperature[c]) for c,g in inlet)
        outward=math.fsum(g*(temperature[c]-ta) for c,g,ta in exterior)
        enthalpy=float(np.dot(adv,field[nl:nl+nf,-1]-tin))
        imbalance=generated+inlet_conduction-outward-enthalpy
        scale=float(np.sum(abs(heat)*dy)*length*width)+abs(inlet_conduction)+abs(outward)+abs(enthalpy)
        roundoff=128*np.finfo(float).eps*float(np.dot(abs(rhs),np.ones(n))+np.sum(abs(operator.data))*max(temperature))
        mechanical_input=gradient*flow*length
        viscous_power=float(np.sum(viscous)*h*width*length)
        if not all(math.isfinite(value) for value in (momentum_residual,linear_residual,generated,inlet_conduction,
                outward,enthalpy,imbalance,scale,roundoff,mechanical_input,viscous_power)):
            raise StructuredThermalError("Nonfinite derived conservation or residual diagnostic")
        if (momentum_residual>1e-10 or linear_residual>1e-10 or
                abs(imbalance)>1e-8*max(scale,1e-30)+roundoff or
                abs(mechanical_input-viscous_power)>1e-10*max(mechanical_input,1e-30)):
            raise StructuredThermalError("Momentum, thermal or energy-conservation acceptance failed")
        # Shared finite-volume face conductance enforces equal/opposite fluxes.
        interfaces=[]
        for j in (nl-1,nl+nf-1):
            g=dx*width/(dy[j]/(2*k[j])+dy[j+1]/(2*k[j+1]))
            interfaces.append((g*(field[j]-field[j+1])).tolist())
        return {"contract": RESULT_CONTRACT,"status":"completed","shape":[nx,ny],"temperature_k":temperature.tolist(),
            "velocity_nodes_m_s":velocity_nodes.tolist(),"fluid_cell_velocity_m_s":velocity.tolist(),
            "interface_upward_heat_w":interfaces,"flow_m3_s":flow,"reynolds":reynolds,"discrete_reynolds":discrete_reynolds,
            "momentum_relative_residual":momentum_residual,"thermal_relative_residual":linear_residual,
            "energy":{"generated_w":generated,"inlet_conduction_w":inlet_conduction,"outward_w":outward,
                      "enthalpy_rise_w":enthalpy,"residual_w":imbalance,"roundoff_allowance_w":float(roundoff),
                      "pressure_work_w":mechanical_input,"viscous_heat_w":viscous_power},"issues":[],
            "qualification":{"production_qualified":False,"state":"bounded_laminar_channel_reference",
                "limitations":["Fully developed plane channel only; no general enclosure, fan, buoyancy or turbulence.",
                    "Constant properties; no radiation or transient flow; first-order upwind thermal advection.",
                    "Not integrated with desktop geometry or private distributed runtime; no measured qualification."]}}
    except (StructuredThermalError,ValueError,OverflowError,FloatingPointError,ZeroDivisionError,MatrixRankWarning) as exc:
        return {"contract":RESULT_CONTRACT,"status":"cancelled" if "cancelled" in str(exc).lower() else "blocked",
            "temperature_k":[],"issues":[{"code":"LAMINAR_CHT_REJECTED","message":str(exc)}],
            "qualification":{"production_qualified":False}}
