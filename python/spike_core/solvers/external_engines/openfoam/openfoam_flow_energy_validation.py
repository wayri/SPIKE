# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Read per-step trusted OpenFOAM observations; audit bounded open-flow energy.

Restricted to constant-density, zero-gravity, laminar, orthogonal meshes with
adiabatic exterior walls. Optional startup audit requires actual time-zero
solver observations on identical admitted inputs; analytical defaults are not
used as the audit baseline. Euler transport uses right endpoints.
"""
import hashlib
import json
import math
import re
from pathlib import Path
import numpy as np
from .openfoam_multiregion_execution import load_verified_runnable_case


def _bounded_digest(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32*1024**2:
        raise ValueError("Missing, linked or oversized evidence file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dictionary(root, manifest, relative):
    path = root/relative
    if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file() or path.stat().st_size>32*1024**2:
        raise ValueError("Missing or oversized physical dictionary")
    payload=path.read_bytes()
    if len(payload)>32*1024**2 or hashlib.sha256(payload).hexdigest() != manifest["input_files"].get(relative):
        raise ValueError("Physical dictionary does not match admitted input digest")
    text = payload.decode("ascii")
    # Only inspect generated literal dictionaries: no includes/macros/expressions.
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    if "#" in text or "$" in text:
        raise ValueError("Dynamic dictionary syntax is outside energy evidence scope")
    return text


def _single_setting(text, key, allowed, *, default=None):
    matches = re.findall(r"(?m)^\s*"+re.escape(key)+r"\s+([^;{}]+);", text)
    if not matches and default is not None:
        return default
    if len(matches)!=1 or matches[0].strip() not in allowed:
        raise ValueError(f"Unsupported or ambiguous physical setting {key}")
    return matches[0].strip()


def _verify_equation_scope(root, manifest, case, dpdt_enabled):
    for region in case["regions"]:
        name=region["id"]
        thermo=_dictionary(root,manifest,f"constant/{name}/thermophysicalProperties")
        _single_setting(thermo,"equationOfState",{"rhoConst"})
        _single_setting(thermo,"thermo",{"hConst"})
        _single_setting(thermo,"energy",{"sensibleEnthalpy"})
        _single_setting(thermo,"transport",{"const"} if region["kind"]=="fluid" else {"constIso"})
        if region["kind"]=="fluid":
            # OpenCFD basicThermo defaults dpdt to true when omitted.
            value=_single_setting(thermo,"dpdt",{"true","false"},default="true")
            if (value=="true") != dpdt_enabled:
                raise ValueError("Requested dpdt accounting disagrees with admitted thermodynamics")
            turbulence=_dictionary(root,manifest,f"constant/{name}/turbulenceProperties")
            _single_setting(turbulence,"simulationType",{"laminar"})


def _verify_history_stability(root, hashes):
    for relative, expected in hashes.items():
        path=root/relative
        if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in path.parents if p!=root and p.is_relative_to(root)) or _bounded_digest(path)!=expected:
            raise ValueError("Diagnostic history changed during validation")


def _literal_number(text, key, default=None):
    values=re.findall(r"(?m)^\s*"+re.escape(key)+r"\s+([^;{}]+);",text)
    if not values and default is not None:
        return default
    if len(values)!=1:
        raise ValueError(f"Missing or ambiguous initial-state setting {key}")
    value=float(values[0])
    if not math.isfinite(value):
        raise ValueError("Initial thermodynamics must be finite")
    return value


def _uniform_initial(root,manifest,name,field,dimensions,vector=False):
    text=_dictionary(root,manifest,f"0/{name}/{field}")
    match=re.findall(r"(?m)^\s*dimensions\s*\[([^]]+)\];",text)
    if len(match)!=1 or match[0].split()!=dimensions.split():
        raise ValueError("Initial field dimensions do not match energy scope")
    values=re.findall(r"(?m)^\s*internalField\s+uniform\s+([^;]+);",text)
    if len(values)!=1:
        raise ValueError("Startup energy currently requires uniform initial fields")
    raw=values[0].strip()
    if vector:
        if not raw.startswith("(") or not raw.endswith(")"):
            raise ValueError("Uniform initial velocity must be a vector")
        result=[float(v)for v in raw[1:-1].split()]
        if len(result)!=3 or not all(math.isfinite(v)for v in result):
            raise ValueError("Initial velocity must contain three finite components")
        return result
    result=float(raw)
    if not math.isfinite(result):
        raise ValueError("Initial field must be finite")
    return result


def _initial_region_storage(root,manifest,region,material,volume,dpdt_enabled):
    """rhoConst has zero H departure; hConst Hs=Cp*(T-Tref)+Href.

    OpenCFD defaults Tref=Tstd=298.15K and Href=0J/kg. Hf is excluded from
    sensible enthalpy. Only immutable static-mesh, uniform-field inputs fit.
    """
    name=region["id"]
    if not math.isfinite(volume) or volume<=0:
        raise ValueError("Positive finite static region volume required")
    if any(key.endswith("dynamicMeshDict") for key in manifest["input_files"]):
        raise ValueError("Startup storage requires a static mesh")
    thermo=_dictionary(root,manifest,f"constant/{name}/thermophysicalProperties")
    cp=_literal_number(thermo,"Cp");rho=_literal_number(thermo,"rho")
    if cp!=material["specific_heat_j_kgk"] or rho!=material["density_kg_m3"] or cp<=0 or rho<=0:
        raise ValueError("Initial Cp/rho must match admitted constant material")
    tref=_literal_number(thermo,"Tref",298.15);href=_literal_number(thermo,"Href",0.)
    temperature=_uniform_initial(root,manifest,name,"T","0 0 0 1 0 0 0")
    if temperature<=0 or tref<=0:
        raise ValueError("Positive absolute initial/reference temperatures required")
    if (root/f"0/{name}/h").exists():
        raise ValueError("Explicit initial h field is outside derived startup scope")
    enthalpy=cp*(temperature-tref)+href
    kinetic=0.;pressure=0.
    if region["kind"]=="fluid":
        velocity=_uniform_initial(root,manifest,name,"U","0 1 -1 0 0 0 0",True)
        kinetic=.5*math.fsum(v*v for v in velocity)
        pressure=_uniform_initial(root,manifest,name,"p","1 -1 -2 0 0 0 0")
        reduced=_uniform_initial(root,manifest,name,"p_rgh","1 -1 -2 0 0 0 0")
        if pressure!=reduced:
            raise ValueError("Zero-gravity initial p and p_rgh must agree")
    storage=volume*(rho*(enthalpy+kinetic)-(pressure if dpdt_enabled else 0))
    if not math.isfinite(storage):
        raise ValueError("Initial storage overflow")
    return {"region":name,"volume_m3":volume,"temperature_k":temperature,"Tref_k":tref,"Href_j_kg":href,
        "sensible_enthalpy_j_kg":enthalpy,"kinetic_energy_j_kg":kinetic,"pressure_pa":pressure,
        "storage_j":storage,"definition":"V*(rho*(h+K)-p) for fluid dpdt; V*rho*h for solid"}


def _observed_startup(report_path,manifest,case,dpdt_enabled):
    """Only an actual time-zero solver postprocess on identical inputs counts."""
    report_path=Path(report_path).resolve()
    report_digest=_bounded_digest(report_path)
    report=json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report,dict) or report.get("contract")!="spike/openfoam-startup-baseline/v1" or report.get("status")!="observed" or report.get("source_manifest_digest")!=manifest["manifest_digest"]:
        raise ValueError("Startup observation does not bind this case")
    clone,cloned_manifest=load_verified_runnable_case(report_path.parent/"case")
    if cloned_manifest!=manifest:
        raise ValueError("Startup clone inputs do not match source inputs")
    command_path=report_path.parent/"command.json"
    if _bounded_digest(command_path)!=report.get("command_sha256"):
        raise ValueError("Startup command evidence changed")
    command=json.loads(command_path.read_text(encoding="utf-8"))
    if not isinstance(command,dict):
        raise ValueError("Startup command evidence must be an object")
    argv=command.get("argv",[])
    if not isinstance(argv,list) or command.get("return_code")!=0 or "chtMultiRegionFoam" not in argv or "-postProcess" not in argv or "-time" not in argv or argv[argv.index("-time")+1:]!=["0"] or "OPENFOAM=2606" not in command.get("stdout",""):
        raise ValueError("Startup requires successful actual v2606 solver time-zero postprocess")
    materials={item["id"]:item for item in case["materials"]}
    initial=[];hashes={}
    for region in case["regions"]:
        name=region["id"];fluid=region["kind"]=="fluid"
        relative=f"postProcessing/{name}/spikeEnergyVolume_{name}/0/volFieldValue.dat"
        path=clone/relative;digest=_bounded_digest(path)
        if digest!=report.get("histories",{}).get(relative,{}).get("sha256"):
            raise ValueError("Startup history changed")
        rows=[line.split()for line in path.read_text(encoding="ascii").splitlines()if line.strip() and not line.lstrip().startswith("#")]
        if len(rows)!=1 or len(rows[0])!=(4 if fluid else 2):
            raise ValueError("Exactly one startup observation per region required")
        values=[float(v)for v in rows[0]]
        if values[0]!=0 or not all(math.isfinite(v)for v in values):
            raise ValueError("Startup must be finite at time zero")
        rho=materials[region["material_id"]]["density_kg_m3"]
        storage=rho*values[1]
        if fluid:
            storage+=rho*values[2]-(values[3]if dpdt_enabled else 0)
        initial.append({"region":name,"storage_j":storage,"observed_volume_integrals":values[1:]})
        hashes[relative]=digest
    if report_digest!=_bounded_digest(report_path) or report["command_sha256"]!=_bounded_digest(command_path) or any(_bounded_digest(clone/relative)!=expected for relative,expected in hashes.items()):
        raise ValueError("Startup report changed while reading")
    return initial,{"report_sha256":report_digest,"command_sha256":report["command_sha256"],"history_sha256":hashes,
                    "method":"actual_v2606_time_zero_postprocess_identical_inputs"}


def read_numeric_history(path, columns):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32*1024**2:
        raise ValueError("Missing, linked or oversized diagnostic history")
    payload = path.read_bytes()
    rows = []
    for line in payload.decode("ascii").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = [float(token) for token in line.replace("(", " ").replace(")", " ").split()]
        if len(row) != columns or not all(math.isfinite(v) for v in row):
            raise ValueError("Malformed diagnostic row")
        rows.append(row)
        if len(rows) > 1_000_001:
            raise ValueError("Too many diagnostic timesteps")
    data = np.asarray(rows)
    if len(rows) < 2 or np.any(np.diff(data[:,0]) <= 0):
        raise ValueError("Need at least two strictly ordered diagnostic times")
    return data, hashlib.sha256(payload).hexdigest()


def integrate_energy_history(times, storage, outward_power, source_power, *, relative_tolerance=.01):
    arrays = [np.asarray(v, dtype=float) for v in (times, storage, outward_power)]
    t,s,q = arrays
    if any(a.ndim != 1 or a.shape != t.shape or not np.isfinite(a).all() for a in arrays) or len(t)<2 or np.any(np.diff(t)<=0):
        raise ValueError("Energy histories must be finite, aligned and increasing")
    if type(source_power) not in (int,float) or not math.isfinite(source_power) or source_power<=0:
        raise ValueError("Positive finite constant source power required")
    if type(relative_tolerance) not in (int,float) or not math.isfinite(relative_tolerance) or not 0<relative_tolerance<=.1:
        raise ValueError("Invalid energy tolerance")
    dt = np.diff(t)
    with np.errstate(over="raise", invalid="raise"):
        injected = float(source_power*(t[-1]-t[0]))
        outward = float(np.sum(q[1:]*dt))
        stored = float(s[-1]-s[0])
        defect = injected-outward-stored
        relative = abs(defect)/max(abs(injected),abs(outward),abs(stored),1e-30)
        local = source_power*dt-q[1:]*dt-np.diff(s)
        local_scale=np.maximum.reduce([np.abs(source_power*dt),np.abs(q[1:]*dt),np.abs(np.diff(s))])
        maximum_step_relative=float(np.max(np.abs(local)/np.maximum(local_scale,1e-30)))
    return {"status":"evaluated", "passed":max(relative,maximum_step_relative)<=relative_tolerance,
            "input_energy_j":injected,"boundary_energy_j":outward,"stored_energy_change_j":stored,
            "energy_defect_j":defect,"relative_residual":relative,"relative_tolerance":relative_tolerance,
            "maximum_step_defect_j":float(np.max(np.abs(local))),
            "maximum_step_relative_residual":maximum_step_relative,
            "interval_start_s":float(t[0]),"interval_end_s":float(t[-1]),"intervals":len(dt),
            "integration":"Euler_right_endpoint", "production_qualified":False}


def validate_flow_energy(case_dir, *, dpdt_enabled, orthogonal_constant_k, relative_tolerance=.01, include_startup=False, startup_baseline=None):
    """Evidence candidate; caller must verify admitted equation/orthogonal scope.

    dpdt_enabled is explicit because subtracting integrated p is valid only if
    that term is active in the solver's sensible-enthalpy equation. Pressure
    work must not also be added to h advection. This function does not certify
    numerical mesh orthogonality or source cell-zone volume admission.
    """
    if type(dpdt_enabled) is not bool or type(include_startup) is not bool or orthogonal_constant_k is not True:
        raise ValueError("Explicit dpdt setting and verified orthogonal constant-k scope required")
    root, manifest = load_verified_runnable_case(case_dir)
    case_payload=(root/"spike_multiregion_case.json").read_bytes()
    if len(case_payload)>32*1024**2 or hashlib.sha256(case_payload).hexdigest()!=manifest["input_files"].get("spike_multiregion_case.json"):
        raise ValueError("Physical case changed before reading")
    case = json.loads(case_payload.decode("utf-8"))
    if any(case["environment"]["gravity_m_s2"]) or case["environment"].get("radiation_model",{}).get("model") not in (None,"none"):
        raise ValueError("Energy reader supports zero gravity without radiation only")
    _verify_equation_scope(root,manifest,case,dpdt_enabled)
    if include_startup and startup_baseline is None:
        raise ValueError("Startup audit requires actual time-zero postprocess baseline evidence")
    materials = {v["id"]:v for v in case["materials"]}
    hashes = {}; time = None; storage = None; power = None; initial=[]
    def history(region_id, name, filename, columns):
        nonlocal time, storage, power
        directory = root/"postProcessing"/region_id/name
        paths = list(directory.glob(f"*/{filename}"))
        if len(paths)!=1 or not paths[0].resolve().is_relative_to(root):
            raise ValueError("Expected exactly one diagnostic history, without restarts")
        data,digest = read_numeric_history(paths[0],columns)
        hashes[paths[0].relative_to(root).as_posix()] = digest
        if time is None:
            time=data[:,0];storage=np.zeros(len(time));power=np.zeros(len(time))
        elif data.shape[0]!=len(time) or not np.array_equal(data[:,0],time):
            raise ValueError("Diagnostic times are not exactly aligned")
        return data[:,1:]
    for region in case["regions"]:
        name=region["id"]; fluid=region["kind"]=="fluid"
        material=materials[region["material_id"]]
        data=history(name,f"spikeEnergyVolume_{name}","volFieldValue.dat",4 if fluid else 2)
        storage += material["density_kg_m3"]*data[:,0]
        if fluid:
            storage += material["density_kg_m3"]*data[:,1]
            if dpdt_enabled: storage -= data[:,2]
        for patch,owner in region["boundary_ownership"].items():
            if owner.startswith("interface:") or owner=="external:adiabatic":
                continue
            if not fluid or not (owner.startswith("fan:") or owner=="external:pressure_outlet"):
                raise ValueError("Unmeasured external boundary in energy scope")
            adv=history(name,f"spikeEnergyAdvection_{name}_{patch}","surfaceFieldValue.dat",3)
            conduction=history(name,f"spikeEnergyConduction_{name}_{patch}","surfaceFieldValue.dat",2)
            power += adv.sum(axis=1)-material["conductivity_w_mk"]*conduction[:,0]
    dt=case["numerics"]["delta_t_s"]
    if not math.isclose(time[0],dt,rel_tol=1e-9,abs_tol=1e-12) or not np.allclose(np.diff(time),dt,rtol=1e-9,atol=1e-12) or not math.isclose(time[-1],case["numerics"]["end_time_s"],rel_tol=1e-9,abs_tol=1e-12):
        raise ValueError("Diagnostic history is missing steps or requested end time")
    source=sum(v["power_w"] for v in case["heat_sources"])
    first_step=None
    startup_identity=None
    if include_startup:
        initial,startup_identity=_observed_startup(startup_baseline,manifest,case,dpdt_enabled)
        initial_storage=math.fsum(item["storage_j"]for item in initial)
        time=np.concatenate(([0.],time));storage=np.concatenate(([initial_storage],storage))
        # q[0] is unused by right-endpoint integration, not an assumed flux.
        power=np.concatenate(([0.],power))
        first_step=integrate_energy_history(time[:2],storage[:2],power[:2],source,relative_tolerance=relative_tolerance)
    result=integrate_energy_history(time,storage,power,source,relative_tolerance=relative_tolerance)
    _verify_history_stability(root,hashes)
    _,after_manifest=load_verified_runnable_case(root)
    if after_manifest != manifest:
        raise ValueError("Admitted case identity changed during validation")
    return {**result,"manifest_digest":manifest["manifest_digest"],"diagnostic_sha256":hashes,
            "dpdt_enabled":dpdt_enabled,"scope":"orthogonal_constant_density_adiabatic_wall_open_flow",
            "startup_included":include_startup,"initial_state":initial,"first_step_audit":first_step,"startup_evidence":startup_identity}
