# SPDX-License-Identifier: Apache-2.0
"""Strict supplied-model admission for Studio board coupling; no CAD inference."""
from copy import deepcopy
import math

from python.spikes.netlist import parse_netlist
from .cosimulation import bounded_digest, identity, number
from .owned_spice_workspace import _owned_engine_netlist

REQUEST = "spike/studio-board-cosimulation-request/v1"
RESULT = "spike/studio-board-cosimulation-result/v1"
CONTROLS = {"window_s", "electrical_step_s", "stop_time_s", "maximum_iterations",
            "temperature_tolerance_k", "power_tolerance_w", "balance_tolerance_w",
            "relaxation", "time_limit_s"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, expected, label):
    require(type(value) is dict and set(value) == set(expected), label + " has missing/unexpected fields")


def positive(value):
    v = number(value)
    require(v > 0, "Expected positive finite value")
    return v


def resistance(binding, temperature, reference):
    factor = 1 + binding["temperature_coefficient_per_k"] * (temperature - binding["reference_temperature_k"])
    geometry = binding.get("geometry")
    dimensions = None
    if geometry is not None:
        scale = 1 + geometry["expansion_per_k"] * (temperature - binding["reference_temperature_k"])
        require(math.isfinite(scale) and scale > 0, "Geometry expansion leaves positive dimensions")
        dimensions = {key: geometry[key] * scale for key in ("length_m", "width_m", "thickness_m")}
        reference = geometry["resistivity_ohm_m"] * geometry["length_m"] / (geometry["width_m"] * geometry["thickness_m"])
        factor /= scale
    value = reference * factor
    require(math.isfinite(value) and value > 0, "Resistance leaves positive finite validity range")
    return value, dimensions


def source_breakpoints(project, stop):
    points=set()
    for e in project.elements:
        w=e.waveform
        if w is None: continue
        require(w.kind in {"pulse","pwl"}, "Only continuous PWL and finite-rise/fall PULSE waveforms are supported")
        if w.kind=="pwl":
            points.update(t for t,_ in w.points if 0<t<stop)
        else:
            _,_,delay,rise,fall,width,period=w.pulse
            require(rise>0 and fall>0,"Discontinuous PULSE edges require an integrated native heat adapter")
            cycles=max(0,math.ceil((stop-delay)/period)+1)
            require(cycles<=100000,"Waveform breakpoint budget exceeded")
            for k in range(cycles):
                offsets=(0.,rise,rise+width,rise+width+fall)
                points.update(t for offset in offsets for t in (delay+offset+k*period,) if 0<t<stop)
        require(len(points)<=200000,"Waveform breakpoint budget exceeded")
    return sorted(points)


def admit(raw, *, board_binding_context=None):
    bounded_digest(raw)
    fields(raw, {"contract", "netlist", "board_revision", "mode", "bindings", "thermal", "controls"}, "request")
    require(raw["contract"] == REQUEST, "Unsupported request contract")
    request = deepcopy(raw)
    identity(request["board_revision"])
    require(request["mode"] in {"steady_state", "transient"}, "Unsupported coupling mode")
    require(isinstance(request["netlist"], str) and 0 < len(request["netlist"].encode()) <= 2*1024*1024, "Netlist missing or exceeds 2 MiB")
    project = parse_netlist(_owned_engine_netlist(request["netlist"]), source_name="<studio-board-coupling>", native_extensions=True)
    require(project.analysis.mode == ("transient" if request["mode"] == "transient" else "operating_point"), "Netlist analysis must agree with coupling mode")
    require(not project.steps and not project.step_variants, "Parameter sweeps are unsupported for board coupling")
    require(1 <= len(project.elements) <= 128, "Circuit requires 1..128 elements")
    allowed = {"resistor", "capacitor", "inductor", "voltage_source", "current_source"}
    require(all(e.kind in allowed for e in project.elements), "Unsupported device: only explicit R/L/C and ideal sources have a loss contract")
    require(all(e.waveform is None for e in project.elements) or request["mode"] == "transient", "Steady state requires constant sources")
    thermal = request["thermal"]
    fields(thermal, {"ambient_temperature_k", "nodes", "links"}, "thermal")
    positive(thermal["ambient_temperature_k"])
    require(type(thermal["nodes"]) is list and 1 <= len(thermal["nodes"]) <= 32, "Thermal node count must be 1..32")
    nodes = {}
    for node in thermal["nodes"]:
        fields(node, {"id", "capacitance_j_per_k", "initial_temperature_k", "minimum_temperature_k", "maximum_temperature_k"}, "thermal node")
        nid = identity(node["id"])
        require(nid != "ambient" and nid not in nodes, "Duplicate/reserved thermal node")
        for k in set(node)-{"id"}: positive(node[k])
        require(node["minimum_temperature_k"] <= node["initial_temperature_k"] <= node["maximum_temperature_k"] and node["minimum_temperature_k"] < node["maximum_temperature_k"], "Invalid temperature bounds")
        nodes[nid] = node
    require(type(thermal["links"]) is list and 1 <= len(thermal["links"]) <= 256, "Thermal link count must be 1..256")
    links = set()
    reachable, adjacency = set(), {nid: set() for nid in nodes}
    for link in thermal["links"]:
        fields(link, {"id", "from_id", "to_id", "resistance_k_per_w"}, "thermal link")
        lid = identity(link["id"])
        require(lid not in links, "Duplicate thermal link")
        links.add(lid)
        a, b = link["from_id"], link["to_id"]
        require(a in {*nodes, "ambient"} and b in {*nodes, "ambient"} and a != b, "Invalid thermal link endpoints")
        positive(link["resistance_k_per_w"])
        if "ambient" in (a, b): reachable.add(b if a == "ambient" else a)
        else: adjacency[a].add(b); adjacency[b].add(a)
    frontier = list(reachable)
    while frontier:
        for neighbor in adjacency[frontier.pop()]-reachable:
            reachable.add(neighbor); frontier.append(neighbor)
    require(reachable == set(nodes), "Missing explicit thermal path to ambient")
    resistors = {e.name: e for e in project.elements if e.kind == "resistor"}
    require(type(request["bindings"]) is list and 1 <= len(request["bindings"]) <= 128, "Missing resistor bindings")
    bindings = {}
    for binding in request["bindings"]:
        required = {"element_id", "component_id", "thermal_node_id", "reference_temperature_k", "temperature_coefficient_per_k"}
        require(type(binding) is dict and required <= set(binding) <= required | {"geometry"}, "Binding fields are invalid")
        eid = identity(binding["element_id"])
        identity(binding["component_id"])
        require(eid in resistors and eid not in bindings and binding["thermal_node_id"] in nodes, "Binding must uniquely map an existing resistor to a thermal node")
        positive(binding["reference_temperature_k"])
        number(binding["temperature_coefficient_per_k"])
        if "geometry" in binding:
            g = binding["geometry"]
            fields(g, {"length_m", "width_m", "thickness_m", "resistivity_ohm_m", "expansion_per_k"}, "geometry")
            for k in set(g)-{"expansion_per_k"}: positive(g[k])
            number(g["expansion_per_k"])
            extracted, _ = resistance(binding, binding["reference_temperature_k"], resistors[eid].value)
            require(math.isclose(extracted, resistors[eid].value, rel_tol=1e-6), "Geometry reference resistance disagrees with netlist")
        node = nodes[binding["thermal_node_id"]]
        for t in (node["minimum_temperature_k"], node["maximum_temperature_k"]):
            r, _ = resistance(binding, t, resistors[eid].value)
            if request["mode"] == "transient":
                require(1e-6 <= r <= 1e15, "Transient feedback resistance must stay in native setter range 1e-6..1e15 ohm")
        bindings[eid] = binding
    require(set(bindings) == set(resistors), "Every dissipative resistor requires an explicit board/thermal binding")
    if board_binding_context is not None:
        require(board_binding_context["board_revision"] == request["board_revision"], "Stale board revision")
        require(all(b["component_id"] in board_binding_context["component_ids"] for b in bindings.values()), "Missing board component")
    c = request["controls"]
    fields(c, CONTROLS, "controls")
    for k in CONTROLS-{"maximum_iterations"}: positive(c[k])
    require(type(c["maximum_iterations"]) is int and 2 <= c["maximum_iterations"] <= 100, "Maximum iterations must be integer 2..100")
    require(c["relaxation"] <= 1 and c["time_limit_s"] <= 120, "Relaxation/time budget exceeds bounds")
    require(c["electrical_step_s"] <= c["window_s"], "Electrical step exceeds communication window")
    windows = math.ceil(c["stop_time_s"]/c["window_s"]) if request["mode"] == "transient" else 1
    require(windows <= 2000 and windows*(len(nodes)+len(project.elements)*4) <= 100000, "Retained frame budget exceeded")
    breakpoints=source_breakpoints(project,c["stop_time_s"])
    require((windows*math.ceil(c["window_s"]/c["electrical_step_s"])+len(breakpoints))*c["maximum_iterations"] <= 2000000, "Replay step budget exceeded")
    if request["mode"] == "transient":
        require(math.isclose(project.analysis.stop_time_s, c["stop_time_s"], rel_tol=1e-12), "Netlist stop time disagrees with controls")
        require(c["electrical_step_s"] <= project.analysis.time_step_s, "Electrical step must respect netlist time step")
        if project.analysis.maximum_time_step_s is not None:
            require(c["electrical_step_s"] <= project.analysis.maximum_time_step_s, "Electrical step exceeds netlist maximum")
    return request, project, nodes, bindings, windows
