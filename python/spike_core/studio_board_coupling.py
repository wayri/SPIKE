# SPDX-License-Identifier: Apache-2.0
"""Native electrical/compact thermal partitioned coupling with accepted windows.

Original application orchestration. Existing native MNA owns electrical state;
existing lumped thermal kernel owns thermal integration. No transistor or CAD
physics is inferred. Backward Euler electrical samples supply window heat.
"""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import bisect
import math
import time

from python.spikes.native_runner import _populate, _nodes
from .cosimulation import bounded_digest
from .thermal import ThermalScenario
from .thermal_network import estimate_lumped_thermal_network
from .studio_board_coupling_contract import REQUEST, RESULT, admit, require, resistance, source_breakpoints

LIMITATIONS = [
    "Approximate explicit lumped thermal network, not spatial FEM, CFD or cooling qualification.",
    "Only resistor heat/temperature feedback; ideal L/C storage and external source power are separate.",
    "Geometry feedback is supplied uniform rho*L/(width*thickness) re-extraction with isotropic expansion; no CAD deformation.",
    "Constant, continuous PWL and positive-rise/fall PULSE supplies only; parameter sweeps are unsupported.",
    "Electrical and communication time-step refinement is required; no automatic error estimator.",
    "Cooperative cancellation between native calls; no hard real-time or HIL qualification.",
]


def validate_studio_board_cosimulation(request, *, board_binding_context=None):
    result = {"contract": "spike/studio-board-cosimulation-admission/v1", "status": "rejected", "model_status": "approximate", "issues": []}
    try:
        _, project, nodes, bindings, windows = admit(request, board_binding_context=board_binding_context)
        result.update(status="accepted", board_revision=request["board_revision"], request_sha256=bounded_digest(request),
                      elements=len(project.elements), thermal_nodes=len(nodes), bindings=len(bindings), windows=windows)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        result["issues"] = [{"code": "STUDIO_COUPLING_ADMISSION", "severity": "error", "message": str(exc)}]
    return result


def _thermal(request, nodes, previous, power, dt):
    scenario = ThermalScenario(mode=request["mode"], ambient_temperature_c=request["thermal"]["ambient_temperature_k"]-273.15,
        thermal_elements=[{"id": nid, "power_w": power[nid], "thermal_capacitance_j_per_c": node["capacitance_j_per_k"],
                           "initial_temperature_c": previous[nid]-273.15} for nid, node in nodes.items()],
        thermal_links=[{"id": link["id"], "from_id": link["from_id"], "to_id": link["to_id"],
                        "resistance_c_per_w": link["resistance_k_per_w"]} for link in request["thermal"]["links"]],
        run={"end_time_s": dt, "write_interval_s": dt})
    result = estimate_lumped_thermal_network(scenario)
    require(result["status"] == "completed", "Thermal kernel did not complete")
    if request["mode"] == "transient":
        temperatures = {nid: v+273.15 for nid, v in result["transient"][-1]["temperatures_c"].items()}
    else:
        temperatures = {node["id"]: node["steady_temperature_c"]+273.15 for node in result["nodes"]}
    require(set(temperatures) == set(nodes), "Thermal kernel returned incomplete nodes")
    require(all(math.isfinite(t) and nodes[nid]["minimum_temperature_k"] <= t <= nodes[nid]["maximum_temperature_k"] for nid,t in temperatures.items()), "Temperature leaves supplied model validity")
    residual = {nid: -power[nid] for nid in nodes}
    if request["mode"] == "transient":
        for nid in nodes: residual[nid] += nodes[nid]["capacitance_j_per_k"]*(temperatures[nid]-previous[nid])/dt
    for link in request["thermal"]["links"]:
        a,b = link["from_id"],link["to_id"]
        ambient=request["thermal"]["ambient_temperature_k"]
        flux=(temperatures.get(a,ambient)-temperatures.get(b,ambient))/link["resistance_k_per_w"]
        if a in residual: residual[a] += flux
        if b in residual: residual[b] -= flux
    return temperatures, max(abs(v) for v in residual.values())


def _sample(solved, project):
    value = {"node_voltage_v": {nid: solved.node_voltage(nid) for nid in _nodes(project)},
             "element_current_a": {e.name: solved.element_current(e.name) for e in project.elements},
             "element_power_w": {e.name: solved.element_power(e.name) for e in project.elements}}
    require(all(math.isfinite(x) for values in value.values() for x in values.values()), "Nonfinite electrical sample")
    return value


def _storage_state(project, sample):
    state = {}
    for e in project.elements:
        if e.kind == "capacitor":
            value=sample["node_voltage_v"][e.positive_node]-sample["node_voltage_v"][e.negative_node]
            state[e.name]=value
        elif e.kind == "inductor":
            value=sample["element_current_a"][e.name]
            state[e.name]=value
    return state


def _storage(project, state):
    return {e.name:.5*e.value*state[e.name]**2 for e in project.elements if e.kind in {"capacitor","inductor"}}


class _Stop(Exception):
    pass


def run_studio_board_cosimulation(raw, *, board_binding_context=None, library=None, cancel_check=None, progress=None):
    """Each iteration restores the start-window native checkpoint before replay.

    Only accepted windows are retained/published. Checkpoints are internal native
    snapshots, released after each window; returned accepted histories are not
    serialized native restart state. A failed window cannot alter prior frames.
    """
    result={"contract":RESULT,"status":"rejected","model_status":"approximate","frames":[],"issues":[],
            "limitations":list(LIMITATIONS),"hard_realtime_qualified":False,"hil_qualified":False,
            "completed_windows":0}
    started=time.monotonic()
    try:
        request, project, nodes, bindings, windows=admit(raw,board_binding_context=board_binding_context)
        controls=request["controls"]
        if library is None:
            from .spikes_runtime import _engine
            library=_engine()
        result.update(board_revision=request["board_revision"], request_sha256=bounded_digest(request),
                      engine_sha256=hashlib.sha256(library.path.read_bytes()).hexdigest(),
                      bindings=deepcopy(request["bindings"]), mode=request["mode"],
                      loss_ledger=[{"element_id":e.name,"disposition":"joule_heat" if e.kind=="resistor" else "ideal_energy_storage" if e.kind in {"capacitor","inductor"} else "external_ideal_source"} for e in project.elements])
        def check():
            if cancel_check and cancel_check(): raise _Stop("cancelled")
            if time.monotonic()-started >= controls["time_limit_s"]: raise _Stop("timed_out")
        previous={nid:n["initial_temperature_k"] for nid,n in nodes.items()}
        references={e.name:e.value for e in project.elements if e.name in bindings}
        def parameters(values):
            rs, geometry={},{}
            for eid,b in bindings.items():
                rs[eid], dimensions=resistance(b,values[b["thermal_node_id"]],references[eid])
                if dimensions is not None: geometry[eid]=dimensions
            return rs,geometry
        def power_map(powers):
            mapped={nid:0. for nid in nodes}
            for eid,b in bindings.items():
                require(math.isfinite(powers[eid]) and powers[eid]>=0, "Invalid resistor heat")
                mapped[b["thermal_node_id"]]+=powers[eid]
            return mapped
        with ExitStack() as stack:
            session=None
            if request["mode"] == "transient":
                initial_rs,_=parameters(previous)
                initial_project=replace(project,elements=tuple(replace(e,value=initial_rs[e.name]) if e.name in initial_rs else e for e in project.elements))
                if project.analysis.use_initial_conditions:
                    initial_state={e.name:e.initial_condition for e in project.elements if e.kind in {"capacitor","inductor"}}
                else:
                    with library.circuit() as initial_circuit:
                        _populate(initial_circuit,initial_project)
                        with initial_circuit.solve_operating_point() as initial_op:
                            require(initial_op.status=="converged", "Initial operating point failed")
                            initial_state=_storage_state(project,_sample(initial_op,project))
                # Freeze the chosen initial state. Native first-step OP would
                # otherwise be recomputed after every Picard resistance change.
                frozen=replace(initial_project,elements=tuple(replace(e,initial_condition=initial_state[e.name]) if e.name in initial_state else e for e in initial_project.elements))
                circuit=stack.enter_context(library.circuit())
                _populate(circuit,frozen)
                session=stack.enter_context(circuit.transient_session(initialize_from_operating_point=False,integration_method="backward_euler"))
            breakpoints=source_breakpoints(project,controls["stop_time_s"])
            elapsed=0.
            retained_bytes=0
            for window in range(windows):
                check()
                dt=min(controls["window_s"],controls["stop_time_s"]-elapsed) if session else controls["window_s"]
                checkpoint=session.checkpoint() if session else None
                guess=dict(previous)
                prior_powers=None
                try:
                    for iteration in range(1,controls["maximum_iterations"]+1):
                        check()
                        rs,geometry=parameters(guess)
                        if session:
                            session.restore(checkpoint)
                            for eid,r in rs.items(): session.set_resistance(eid,r)
                            powers={eid:0. for eid in bindings}
                            source_energy=0.
                            prior_state=dict(initial_state) if window==0 else _storage_state(project,result["frames"][-1]["electrical"])
                            initial_storage=_storage(project,prior_state)
                            numerical_energy=0.
                            electrical_balance=0.
                            cursor=session.position[0]
                            while cursor < elapsed+dt:
                                check()
                                end=min(elapsed+dt,cursor+controls["electrical_step_s"])
                                index=bisect.bisect_right(breakpoints,cursor)
                                if index<len(breakpoints):
                                    corner=breakpoints[index]
                                    # Land on a nearby corner rather than leave a
                                    # roundoff-size interval for the native adapter.
                                    if corner <= end+64*math.ulp(max(abs(end),abs(corner))):
                                        end=min(elapsed+dt,corner)
                                if elapsed+dt-end <= 64*math.ulp(abs(elapsed+dt)):
                                    end=elapsed+dt
                                step=end-cursor
                                require(step>0,"Nonpositive breakpoint step")
                                prior_index=session.diagnostics()["completed_steps"]
                                require(session.step(step), "Native electrical step failed: "+session.message)
                                require(session.diagnostics()["completed_steps"]==prior_index+1,"Native hidden subdivisions require integrated heat output")
                                cursor=session.position[0]
                                require(cursor==end,"Native time did not land on requested external endpoint")
                                sample=_sample(session,project)
                                for eid in powers: powers[eid]+=sample["element_power_w"][eid]*step/dt
                                source=-step*sum(sample["element_power_w"][e.name] for e in project.elements if e.kind in {"voltage_source","current_source"})
                                heat=step*sum(sample["element_power_w"][eid] for eid in bindings)
                                state=_storage_state(project,sample)
                                stored=sum(_storage(project,state).values())-sum(_storage(project,prior_state).values())
                                numerical=0.
                                for e in project.elements:
                                    if e.kind in {"capacitor","inductor"}:
                                        delta=state[e.name]-prior_state[e.name]
                                        numerical+=.5*e.value*delta*delta
                                error=source-heat-stored-numerical
                                require(abs(error)<=controls["balance_tolerance_w"]*step+1e-8*max(abs(source),abs(heat),abs(stored),numerical), "Electrical BE energy balance failed")
                                electrical_balance=max(electrical_balance,abs(error))
                                source_energy+=source
                                numerical_energy+=numerical
                                prior_state=state
                            electrical=sample
                        else:
                            current=replace(project,elements=tuple(replace(e,value=rs[e.name]) if e.name in rs else e for e in project.elements))
                            with library.circuit() as c:
                                _populate(c,current)
                                with c.solve_operating_point() as solved:
                                    require(solved.status=="converged", "Native operating point failed: "+solved.message)
                                    electrical=_sample(solved,project)
                            powers={eid:electrical["element_power_w"][eid] for eid in bindings}
                            require(abs(sum(electrical["element_power_w"].values())) <= controls["balance_tolerance_w"], "Electrical OP power balance failed")
                        mapped=power_map(powers)
                        temperature,balance=_thermal(request,nodes,previous,mapped,dt)
                        delta=max(abs(temperature[nid]-guess[nid]) for nid in nodes)
                        power_delta=max(abs(powers[eid]-prior_powers[eid]) for eid in powers) if prior_powers else None
                        if power_delta is not None and delta<=controls["temperature_tolerance_k"] and power_delta<=controls["power_tolerance_w"] and balance<=controls["balance_tolerance_w"]:
                            check()
                            frame={"time_s":elapsed+dt if session else 0.,"temperature_k":temperature,"applied_temperature_k":guess,
                                   "node_power_w":mapped,"electrical":{**electrical,"resistance_ohm":rs},"geometry":geometry,
                                   "iteration":iteration,"temperature_residual_k":delta,"power_residual_w":power_delta,"balance_residual_w":balance}
                            if session:
                                frame["energy"]={"source_j":source_energy,"resistor_heat_j":sum(powers.values())*dt,
                                                 "stored_j":_storage(project,_storage_state(project,electrical)), "initial_stored_j":initial_storage,
                                                 "storage_change_j":sum(_storage(project,_storage_state(project,electrical)).values())-sum(initial_storage.values()),
                                                 "be_numerical_dissipation_j":numerical_energy,"maximum_step_balance_error_j":electrical_balance,
                                                 "integration":"backward_euler_endpoint_power_window_average"}
                            frame_bytes=len(json.dumps(frame,allow_nan=False).encode("utf-8"))
                            require(frame_bytes <= 400*1024, "Accepted frame exceeds progress byte budget")
                            require(retained_bytes+frame_bytes <= 7*1024*1024, "Accepted history exceeds result byte budget")
                            retained_bytes+=frame_bytes
                            result["frames"].append(frame)
                            result["completed_windows"]=window+1
                            previous=temperature
                            elapsed+=dt
                            if progress: progress(deepcopy(frame))
                            break
                        prior_powers=powers
                        guess={nid:guess[nid]+controls["relaxation"]*(temperature[nid]-guess[nid]) for nid in nodes}
                    else:
                        raise _Stop("failed_to_converge")
                except BaseException:
                    if session: session.restore(checkpoint)
                    raise
                finally:
                    if checkpoint: checkpoint.close()
            result["status"]="completed"
    except _Stop as exc:
        result["status"]=str(exc)
        result["issues"]=[{"code":"STUDIO_COUPLING_"+str(exc).upper(),"severity":"error","message":"Only accepted windows retained; inspect controls/model validity before rerun."}]
    except (ValueError,TypeError,KeyError,OverflowError,RuntimeError,OSError,ArithmeticError) as exc:
        result["status"]="failed" if "engine_sha256" in result else "rejected"
        result["issues"]=[{"code":"STUDIO_COUPLING_FAILED","severity":"error","message":str(exc)}]
    result["accepted_history_sha256"]=bounded_digest(result["frames"])
    bounded_digest(result)
    return result
