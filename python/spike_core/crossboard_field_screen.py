# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Hash-bound four-excitation numerical screens, never field qualification."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from .openems_assembly_geometry import compile_assembly_geometry
from .fdtd_completion import screen_fdtd_completion


def _digest(data):return hashlib.sha256(data).hexdigest()


def _tolerance(value):
    if type(value) not in (int,float) or not np.isfinite(value) or not 0<value<=1:
        raise ValueError("Explicit finite tolerance must be in (0,1]")
    return float(value)


def screen_case(path, *, passivity_excess=.02, reciprocity_absolute=.02):
    """Check existing local trusted-runner artifacts; refuse partial/tampered runs."""
    passivity_excess=_tolerance(passivity_excess);reciprocity_absolute=_tolerance(reciprocity_absolute)
    path=Path(path).resolve();hashes={};total=0
    def read(relative,limit=8*1024**2):
        nonlocal total
        target=path/relative
        if target.is_symlink() or not target.resolve().is_relative_to(path):
            raise ValueError("Evidence symlink is not admitted")
        if not target.is_file() or target.stat().st_size>limit:raise ValueError("Missing or oversized evidence")
        data=target.read_bytes();total+=len(data)
        if total>512*1024**2:raise ValueError("Evidence budget exceeded")
        hashes[relative]=_digest(data);return data
    execution=json.loads(read("execution.json"))
    if execution.get("status")!="executed" or execution.get("sources_unchanged") is not True or execution.get("execution",{}).get("returncode")!=0:
        raise ValueError("Incomplete or unstable execution")
    records={name:json.loads(read(name)) for name in ("geometry.json","compiled.json","field-result.json")}
    for name in records:
        if execution.get("artifact_sha256",{}).get(name)!=hashes[name]:raise ValueError("Execution artifact hash mismatch")
    compiled=compile_assembly_geometry(records["geometry.json"])
    if compiled!=records["compiled.json"]:raise ValueError("Compiled geometry binding mismatch")
    result=records["field-result.json"]
    temporal=screen_fdtd_completion(read("solver.log").decode('utf-8',errors='replace'),
                                   expected_runs=4,end_criteria=result['end_criteria'])
    if result.get("status")!="executed" or result.get("field_coupling_executed") is not True:
        raise ValueError("Field columns have not completed")
    if result.get("ports")!=["A.near","A.far","B.near","B.far"] or result.get("reference_impedance_ohm")!=50:
        raise ValueError("Unsupported port order or reference impedance")
    freq=np.asarray(result["frequency_hz"],float)
    s=np.asarray(result["s_real"],float)+1j*np.asarray(result["s_imag"],float)
    if freq.ndim!=1 or not 2<=freq.size<=8193 or not np.isfinite(freq).all() or not np.all(np.diff(freq)>0) or freq[0]<=0 or s.shape!=(freq.size,4,4) or not np.isfinite(s).all():
        raise ValueError("Invalid bounded four-port frequency response")
    meshes=result["meshes"]
    if len(meshes)!=4:raise ValueError("Four completed excitation meshes required")
    for index,mesh in enumerate(meshes):
        inner=np.asarray(mesh["inner_pml_bounds_mm"],float)
        if inner.shape!=(3,2) or not np.isfinite(inner).all():raise ValueError("Invalid PML bounds")
        for box in compiled["boxes"]:
            if not all(inner[i,0]<box["start_mm"][i]<box["stop_mm"][i]<inner[i,1] for i in range(3)):
                raise ValueError("PML overlaps assembly")
        xml=ET.fromstring(read(f"excitation-{index}/geometry.xml",2*1024**2))
        active=xml.findall(".//Excitation")
        if len(active)!=1 or active[0].get("Name")!=f"port_excite_{index+1}" or not any(float(v)!=0 for v in active[0].get("Excite","0").split(",")):
            raise ValueError("Independent excitation identity mismatch")
        for port in range(1,5):
            for kind in ("ut","it"):
                if not read(f"excitation-{index}/simulation/port_{kind}_{port}",16*1024**2).strip():
                    raise ValueError("Empty terminal history")
    singular=float(np.max(np.linalg.svd(s,compute_uv=False)))
    reciprocity=float(np.max(np.abs(s-s.transpose(0,2,1))))
    for name,digest in hashes.items():
        if _digest((path/name).read_bytes())!=digest:raise ValueError("Evidence changed during screening")
    return {"contract":"spike/crossboard-field-screen/v1","screen_passed":temporal['screen_passed'] and singular<=1+passivity_excess and reciprocity<=reciprocity_absolute,
        "temporal_completion":temporal,
        "maximum_singular_value":singular,"maximum_reciprocity_absolute_error":reciprocity,
        "thresholds":{"passivity_excess":passivity_excess,"reciprocity_absolute":reciprocity_absolute},
        "artifact_sha256":hashes,"production_qualified":False,"physical_accuracy_qualified":False,
        "scope":"Numerical sanity and trusted-runner completion only; no duration, PML, mesh, independent or measured qualification."}


def compare_mesh_cases(paths, *, absolute_s_tolerance=.02):
    tolerance=_tolerance(absolute_s_tolerance)
    if not isinstance(paths,(list,tuple)) or not 3<=len(paths)<=8:raise ValueError("Require 3..8 independently executed mesh levels")
    cases=[]
    for path in paths:
        screen=screen_case(path)
        if not screen["screen_passed"]:raise ValueError("Numerical sanity screen failed")
        payload=(Path(path)/"field-result.json").read_bytes()
        raw=json.loads(payload)
        if _digest(payload)!=screen["artifact_sha256"]["field-result.json"]:raise ValueError("Changed result")
        cases.append((raw,screen))
    cases.sort(key=lambda c:c[0]["mesh_resolution_mm"],reverse=True)
    reference=cases[0]
    for raw,screen in cases:
        if screen["artifact_sha256"]["geometry.json"]!=reference[1]["artifact_sha256"]["geometry.json"] or any(raw[k]!=reference[0][k] for k in ("ports","frequency_hz","reference_impedance_ohm","end_criteria","max_timesteps")):
            raise ValueError("Convergence cases differ beyond mesh resolution")
    resolutions=[c[0]["mesh_resolution_mm"] for c in cases]
    if not all(np.isfinite(x) and x>0 for x in resolutions) or len(set(resolutions))!=len(cases):raise ValueError("Distinct finite positive mesh resolutions required")
    values=[np.asarray(c[0]["s_real"])+1j*np.asarray(c[0]["s_imag"]) for c in cases]
    errors=[float(np.max(np.abs(a-b))) for a,b in zip(values,values[1:])]
    bounds=[m['inner_pml_bounds_mm'] for raw,_ in cases for m in raw['meshes']]
    fixed_pml=all(np.allclose(b,bounds[0],rtol=0,atol=1e-12) for b in bounds)
    return {"contract":"spike/crossboard-mesh-comparison/v1","mesh_resolutions_mm":resolutions,
        "successive_max_complex_s_differences":errors,"absolute_s_tolerance":tolerance,
        "fixed_physical_pml_interface":fixed_pml,
        "screen_passed":fixed_pml and all(x<=tolerance for x in errors),"production_qualified":False,
        "scope":"Successive full complex S differences only; no proven order, asymptotic regime or PML/duration convergence."}
