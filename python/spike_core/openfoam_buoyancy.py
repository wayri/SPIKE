# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Explicit bounded thermal-expansion EOS admission and runtime observations.

OpenCFD Boussinesq EOS: rho=rho0*(1-beta*(T-T0)). Used inside
chtMultiRegionFoam's variable-density equations, not a claim that the complete
solver equals the classical incompressible Boussinesq approximation.
Reference: https://doc.openfoam.com/2212/tools/processing/models/thermophysical/equation-of-state/rtm/Boussinesq/
"""
import math
import re
import hashlib
import json
from collections.abc import Mapping


def validate_density_model(raw, reference_density):
    keys={"type","rho0_kg_m3","T0_k","beta_per_k","temperature_min_k","temperature_max_k"}
    if not isinstance(raw,Mapping) or set(raw)!=keys or raw["type"]!="Boussinesq":
        raise ValueError("density_model requires the explicit bounded Boussinesq fields")
    for key in keys-{"type"}:
        value=raw[key]
        if type(value) not in (int,float) or not 0<value<1e9:
            raise ValueError(f"density_model {key} must be positive finite")
    lo,hi,t0=raw["temperature_min_k"],raw["temperature_max_k"],raw["T0_k"]
    if not lo<=t0<=hi or lo==hi:raise ValueError("Density validity interval must bracket reference temperature")
    if raw["beta_per_k"]*max(abs(lo-t0),abs(hi-t0))>.1:
        raise ValueError("Boussinesq density departure must not exceed 10 percent over the admitted interval")
    if not math.isclose(raw["rho0_kg_m3"],reference_density,rel_tol=1e-12,abs_tol=0):
        raise ValueError("Material density must match Boussinesq rho0")
    return {k:(v if k=="type" else float(v)) for k,v in raw.items()}


def density_at_temperature(model, temperature):
    if type(temperature) not in (int,float) or not model["temperature_min_k"]<=temperature<=model["temperature_max_k"]:
        raise ValueError("Temperature lies outside admitted density interval")
    density=model["rho0_kg_m3"]*(1-model["beta_per_k"]*(temperature-model["T0_k"]))
    if not math.isfinite(density) or density<=0:raise ValueError("Nonpositive or nonfinite Boussinesq density")
    return density


def render_buoyancy_observers(case):
    """Trusted per-step min/max T and rho; append before manifest hashing."""
    materials={item["id"]:item for item in case["materials"]}
    blocks=[]
    for region in case["regions"]:
        model=materials[region["material_id"]].get("density_model")
        if not model:continue
        name=region["id"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}",name):raise ValueError("Invalid buoyancy observer region")
        density_at_temperature(model,case["environment"]["ambient_temperature_k"])
        for fan in case.get("fans",[]):
            if fan["fluid_region_id"]==name:density_at_temperature(model,fan["inlet_temperature_k"])
        for outlet in case["environment"].get("pressure_outlets",[]):
            if outlet["fluid_region_id"]==name:density_at_temperature(model,outlet["backflow_temperature_k"])
        for operation in ("min","max"):
            blocks.append(f"spikeBuoyancy{operation}_{name}\n{{\n type volFieldValue;\n"
                f" libs (fieldFunctionObjects);\n region {name};\n operation {operation};\n fields (T rho);\n"
                " writeFields false;\n executeControl timeStep;\n executeInterval 1;\n"
                " writeControl timeStep;\n writeInterval 1;\n writePrecision 17;\n log false;\n writeToFile true;\n}\n")
    return "\n".join(blocks)


def validate_buoyancy_runtime(root,manifest):
    """Reject missing/out-of-envelope every-step observations before field import."""
    from .openfoam_flow_energy_validation import read_numeric_history
    import numpy as np
    relative="spike_multiregion_case.json"
    expected=manifest.get("input_files",{}).get(relative)
    if expected is None:return {}
    path=root/relative
    if path.is_symlink() or path.stat().st_size>32*1024**2:raise ValueError("Invalid buoyancy case metadata")
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected:raise ValueError("Buoyancy case metadata changed")
    case=json.loads(payload);materials={item["id"]:item for item in case["materials"]}
    evidence={}
    for region in case["regions"]:
        model=materials[region["material_id"]].get("density_model")
        if not model:continue
        records=[];digests={}
        for operation in ("min","max"):
            directory=root/"postProcessing"/region["id"]/f"spikeBuoyancy{operation}_{region['id']}"
            paths=list(directory.glob("*/volFieldValue.dat"))
            if len(paths)!=1 or not paths[0].resolve().is_relative_to(root):raise ValueError("Missing buoyancy density observations")
            values,digest=read_numeric_history(paths[0],3)
            records.append(values);digests[paths[0].relative_to(root).as_posix()]=digest
        lo,hi=records
        dt=case["numerics"]["delta_t_s"];end=case["numerics"]["end_time_s"]
        if lo.shape!=hi.shape or not np.array_equal(lo[:,0],hi[:,0]) or not np.allclose(np.diff(lo[:,0]),dt,rtol=1e-9,atol=1e-12) or not math.isclose(lo[0,0],dt,rel_tol=1e-9,abs_tol=1e-12) or not math.isclose(lo[-1,0],end,rel_tol=1e-9,abs_tol=1e-12):
            raise ValueError("Incomplete buoyancy observation interval")
        tmin=float(lo[:,1].min());tmax=float(hi[:,1].max());rmin=float(lo[:,2].min());rmax=float(hi[:,2].max())
        density_at_temperature(model,tmin);density_at_temperature(model,tmax)
        allowed_min=density_at_temperature(model,model["temperature_max_k"])
        allowed_max=density_at_temperature(model,model["temperature_min_k"])
        tolerance=1e-9*model["rho0_kg_m3"]
        if rmin<=0 or rmin<allowed_min-tolerance or rmax>allowed_max+tolerance or np.any(lo[:,1:]>hi[:,1:]):
            raise ValueError("Observed density/temperature extrema exceed the admitted EOS interval")
        for rel,digest in digests.items():
            if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=digest:raise ValueError("Buoyancy observations changed during import")
        evidence[region["id"]]={"minimum_temperature_k":tmin,"maximum_temperature_k":tmax,
            "minimum_density_kg_m3":rmin,"maximum_density_kg_m3":rmax,"every_step_interval_passed":True,
            "diagnostic_sha256":digests,"production_qualified":False}
    return evidence
