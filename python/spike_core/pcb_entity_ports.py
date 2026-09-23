# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Entity-bound lumped ports for the existing screened openEMS PCB workflow.

No automatic port inference or eigenmode construction: callers select two
physical source entities and attachment coordinates. Recompile after every
geometry mutation; preparation binds the derived ports and source IDs together.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from .contracts import AnalysisSpec, DesignIR
from .openems_geometry_admission import screen_geometry
from .openems_validation import _conductor_hits, _stackup_elevations

CONTRACT = "spike/pcb-entity-ports/v1"


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("E_PORT_CONTRACT: exact object fields required")


def _number(value):
    try:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("E_PORT_NUMBER: finite numeric value required")
        return float(value)
    except OverflowError as exc:
        raise ValueError("E_PORT_NUMBER: value out of range") from exc


def compile_entity_ports(design: DesignIR, spec: AnalysisSpec, request: dict) -> AnalysisSpec:
    """Return a new spec accepted by prepare_openems_case, without executing it.

The zero-tolerance source test is complemented by the normal runtime geometry,
resource and port checks. Only straight axis-aligned lumped excitations are
constructed. Fields remain unqualified for arbitrary-PCB accuracy.
"""
    if not isinstance(design, DesignIR) or not isinstance(spec, AnalysisSpec):
        raise ValueError("E_PORT_CONTRACT: typed design/spec required")
    _keys(request, ("contract", "ports"))
    if request["contract"] != CONTRACT:
        raise ValueError("E_PORT_CONTRACT: unsupported version")
    ports = request["ports"]
    if not isinstance(ports, list) or not 1 <= len(ports) <= 64:
        raise ValueError("E_PORT_RESOURCE: one to 64 ports required")
    report = screen_geometry(design, spec)
    if not report["screen_passed"]:
        raise ValueError("E_PORT_GEOMETRY: " + ",".join(i["code"] for i in report["issues"]))
    sources = {}
    for collection in ("tracks", "pads", "zones"):
        for entity in getattr(design, collection):
            identity = entity.get("id")
            if not isinstance(identity, str) or not identity:
                continue
            if identity in sources:
                raise ValueError("E_PORT_ID: duplicate source entity identity")
            sources[identity] = (collection, entity)
    elevations = _stackup_elevations(design)
    layer_names = [layer.get("name") for layer in design.stackup]
    if len(layer_names) != len(set(layer_names)):
        raise ValueError("E_PORT_LAYER: duplicate stackup layer identity")

    def attachment(value):
        _keys(value, ("entity_id", "layer", "at_mm"))
        identity, layer, xy = value["entity_id"], value["layer"], value["at_mm"]
        if not isinstance(identity, str) or identity not in sources:
            raise ValueError("E_PORT_ID: unknown source entity")
        if not isinstance(layer, str) or layer not in elevations:
            raise ValueError("E_PORT_LAYER: unknown copper layer")
        if not isinstance(xy, list) or len(xy) != 2:
            raise ValueError("E_PORT_POINT: two coordinates required")
        point = [_number(xy[0]), _number(xy[1]), elevations[layer]]
        collection, entity = sources[identity]
        net = str(entity.get("net_name") or entity.get("net") or "")
        if not net or net not in spec.net_names:
            raise ValueError("E_PORT_NET: selected entity net required")
        if collection == "tracks":
            # The exporter emits a rectangle, not the round endcaps allowed by
            # the general contact helper. Never attach outside that rectangle.
            def xy_pair(value):
                if isinstance(value, dict):
                    value = [value.get("x"), value.get("y")]
                if not isinstance(value, (list, tuple)) or len(value) != 2:
                    raise ValueError("E_PORT_ATTACHMENT: invalid track endpoint")
                return [_number(v) for v in value]
            start, stop = xy_pair(entity.get("start")), xy_pair(entity.get("end"))
            dx, dy = stop[0] - start[0], stop[1] - start[1]
            length = math.hypot(dx, dy)
            if not math.isfinite(length) or length <= 0:
                raise ValueError("E_PORT_ATTACHMENT: degenerate track")
            ux, uy = dx / length, dy / length
            px, py = point[0] - start[0], point[1] - start[1]
            along, across = px * ux + py * uy, -px * uy + py * ux
            if not (0 <= along <= length and abs(across) <= _number(entity.get("width")) / 2):
                raise ValueError("E_PORT_ATTACHMENT: point outside exported track rectangle")
        isolated = DesignIR(stackup=copy.deepcopy(design.stackup))
        setattr(isolated, collection, [copy.deepcopy(entity)])
        if _conductor_hits(isolated, {net}, point, 0.0) != {net}:
            raise ValueError("E_PORT_ATTACHMENT: point is not on declared source")
        if _conductor_hits(design, set(spec.net_names), point, 0.0) != {net}:
            raise ValueError("E_PORT_ATTACHMENT: ambiguous overlapping electrical nets")
        return point, net

    derived, identities, excited = [], set(), 0
    for port in ports:
        _keys(port, ("id", "signal", "reference", "impedance_ohm", "excite"))
        identity = port["id"]
        if not isinstance(identity, str) or not 1 <= len(identity) <= 256 or identity in identities:
            raise ValueError("E_PORT_ID: unique bounded port identity required")
        identities.add(identity)
        signal, signal_net = attachment(port["signal"])
        reference, reference_net = attachment(port["reference"])
        if signal_net == reference_net:
            raise ValueError("E_PORT_SHORT: distinct signal/reference nets required")
        axes = [i for i in range(3) if signal[i] != reference[i]]
        if len(axes) != 1:
            raise ValueError("E_PORT_DIRECTION: exactly one axis must differ")
        impedance = _number(port["impedance_ohm"])
        if not 0 < impedance <= 1e6 or type(port["excite"]) is not bool:
            raise ValueError("E_PORT_EXCITATION: positive impedance and boolean excite required")
        excited += int(port["excite"])
        derived.append({"start": reference, "stop": signal, "direction": "xyz"[axes[0]],
                        "impedance_ohm": impedance, "excite": port["excite"]})
    if excited != 1:
        raise ValueError("E_PORT_EXCITATION: exactly one excited port per run")
    result = copy.deepcopy(spec)
    result.options["ports"] = derived
    # Keep mapping in authenticated AnalysisSpec rather than a disconnected sidecar.
    # Bind precisely the physical fields retained by the runtime's authenticated
    # DesignIR reconstruction; UI name/net catalog/source-path are not geometry.
    physical = {key: getattr(design, key) for key in ("design_id", "units", "layers",
        "tracks", "zones", "vias", "pads", "components", "component_bonds", "connectors",
        "stackup", "technology", "regions", "bends", "metadata")}
    result.options["entity_port_binding"] = {
        "request": copy.deepcopy(request),
        "geometry_sha256": hashlib.sha256(json.dumps(physical, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        "kind": "axis_aligned_lumped", "production_qualified": False,
    }
    return result


def prepare_entity_port_case(design, spec, request, **kwargs):
    """Prepare the ordinary authenticated PCB->openEMS->NF2FF job, never run it."""
    from .external_engines import prepare_openems_case
    return prepare_openems_case(design, compile_entity_ports(design, spec, request), **kwargs)


def validate_entity_port_binding(design, spec):
    """Runtime check: changed geometry or port coordinates invalidate the binding."""
    if "entity_port_binding" not in spec.options:
        return []
    try:
        binding = spec.options["entity_port_binding"]
        if not isinstance(binding, dict):
            raise ValueError("E_PORT_BINDING: object required")
        rebuilt = compile_entity_ports(design, spec, binding.get("request"))
        if (rebuilt.options["entity_port_binding"] != binding
                or rebuilt.options["ports"] != spec.options.get("ports")):
            raise ValueError("E_PORT_BINDING: stale geometry or modified derived ports")
    except (ValueError, TypeError, OverflowError) as exc:
        return [{"code": "OPENEMS_ENTITY_PORT_BINDING_INVALID", "message": str(exc)}]
    return []
