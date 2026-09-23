"""Deterministic PI power-path extraction from normalized board connectivity.

The KiCad board describes copper connectivity but not a component's internal
transfer function.  This module therefore reports the component chain between
two selected power terminals without inventing semiconductor behaviour.  It
keeps ground out of the series graph and returns ground-connected elements as
explicit shunts for the SPICE/model-assignment workflow.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, Mapping, Sequence

from .contracts import DesignIR


POWER_PATH_CONTRACT = "spike/power-path-extraction/v1"

_GROUND_NAME = re.compile(r"(?:^|[/_.+-])(gnd|agnd|dgnd|pgnd|vss|vssa|vssd|0)(?:$|[/_.+-])", re.IGNORECASE)
_NO_NET = {"", "no_net", "unconnected", "<no net>"}


@dataclass(frozen=True)
class _Terminal:
    """Resolved terminal used by the electrical graph and result contract."""

    kind: str
    net: str
    pad_id: str = ""
    component_ref: str = ""
    pad_name: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {
            "kind": self.kind,
            "net": self.net,
            "pad_id": self.pad_id,
            "component_ref": self.component_ref,
            "pad_name": self.pad_name,
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _pad_ref(pad: Mapping[str, Any]) -> str:
    return _text(pad.get("component") or pad.get("ref") or pad.get("component_ref"))


def _pad_name(pad: Mapping[str, Any]) -> str:
    return _text(pad.get("name") or pad.get("pad") or pad.get("number") or pad.get("pin"))


def _pad_id(pad: Mapping[str, Any], index: int) -> str:
    explicit = _text(pad.get("id") or pad.get("component_pad"))
    if explicit:
        return explicit
    reference = _pad_ref(pad)
    name = _pad_name(pad)
    return f"{reference}.{name}" if reference and name else f"pad-{index + 1}"


def _net_name(pad: Mapping[str, Any]) -> str:
    return _text(pad.get("net_name") or pad.get("net"))


def _is_ground(net: str, explicit_ground_nets: set[str]) -> bool:
    normalized = net.casefold()
    return normalized in explicit_ground_nets or bool(_GROUND_NAME.search(net))


def _is_usable_net(net: str) -> bool:
    return net.casefold() not in _NO_NET


def _component_model_kind(reference: str, value: str, library: str) -> str:
    """Classify only enough to seed a model-assignment wizard, never a solve."""

    identity = f"{reference} {value} {library}".casefold()
    if re.match(r"^r", reference, re.IGNORECASE):
        return "resistor"
    if re.match(r"^c", reference, re.IGNORECASE):
        return "capacitor"
    if re.match(r"^l", reference, re.IGNORECASE):
        return "inductor"
    if re.match(r"^(fb|bead)", reference, re.IGNORECASE):
        return "ferrite_bead"
    if re.match(r"^f", reference, re.IGNORECASE):
        return "fuse"
    if re.match(r"^d", reference, re.IGNORECASE):
        return "diode"
    if re.match(r"^q", reference, re.IGNORECASE):
        return "transistor"
    if re.match(r"^(t|xfmr)", reference, re.IGNORECASE) or "transformer" in identity:
        return "transformer"
    if re.match(r"^(u|ic)", reference, re.IGNORECASE):
        return "integrated_circuit"
    if re.match(r"^(j|p|cn)", reference, re.IGNORECASE):
        return "connector"
    return "component"


def _requires_pin_model(model_kind: str, pads: Sequence[Mapping[str, Any]]) -> bool:
    """Identify components whose topology is known but internal behaviour is not."""

    connected_nets = {
        _text(pad.get("_net")) for pad in pads
        if _is_usable_net(_text(pad.get("_net")))
    }
    return len(connected_nets) > 2 or model_kind in {
        "integrated_circuit", "transistor", "transformer", "diode",
    }


def _component_metadata(design: DesignIR) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for component in design.components:
        reference = _text(component.get("reference") or component.get("ref"))
        if reference and reference not in result:
            result[reference] = component
    return result


def _build_pad_index(design: DesignIR) -> tuple[list[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, list[Dict[str, Any]]]]:
    pads: list[Dict[str, Any]] = []
    by_id: Dict[str, Dict[str, Any]] = {}
    by_component: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for index, raw_pad in enumerate(design.pads):
        pad = dict(raw_pad)
        pad["_id"] = _pad_id(pad, index)
        pad["_ref"] = _pad_ref(pad)
        pad["_name"] = _pad_name(pad)
        pad["_net"] = _net_name(pad)
        pads.append(pad)
        by_id.setdefault(pad["_id"], pad)
        if pad["_ref"]:
            by_component[pad["_ref"]].append(pad)
    return pads, by_id, by_component


def _resolve_terminal(
    selector: str | Mapping[str, Any],
    *,
    role: str,
    pads: Sequence[Mapping[str, Any]],
    pads_by_id: Mapping[str, Mapping[str, Any]],
) -> _Terminal:
    """Resolve a terminal selector without relying on visual coordinates."""

    if isinstance(selector, str):
        token = selector.strip()
        if not token:
            raise ValueError(f"{role} terminal is required.")
        pad = pads_by_id.get(token)
        if pad is not None:
            net = _text(pad.get("_net"))
            if not _is_usable_net(net):
                raise ValueError(f"{role} pad {token} has no connected net.")
            return _Terminal("pad", net, token, _text(pad.get("_ref")), _text(pad.get("_name")))
        return _Terminal("net", token)
    if not isinstance(selector, Mapping):
        raise TypeError(f"{role} terminal must be a net string or selector object.")

    pad_id = _text(selector.get("pad_id") or selector.get("id") or selector.get("component_pad"))
    if pad_id:
        return _resolve_terminal(pad_id, role=role, pads=pads, pads_by_id=pads_by_id)
    reference = _text(selector.get("component_ref") or selector.get("component") or selector.get("ref"))
    pad_name = _text(selector.get("pad_name") or selector.get("pad") or selector.get("pin") or selector.get("name"))
    if reference and pad_name:
        matches = [
            pad for pad in pads
            if _text(pad.get("_ref")) == reference and _text(pad.get("_name")) == pad_name
        ]
        if len(matches) == 1:
            return _resolve_terminal(_text(matches[0].get("_id")), role=role, pads=pads, pads_by_id=pads_by_id)
        if len(matches) > 1:
            raise ValueError(f"{role} selector {reference}.{pad_name} is ambiguous.")
        raise ValueError(f"{role} pad {reference}.{pad_name} was not found in the design.")
    net = _text(selector.get("net") or selector.get("net_name"))
    if net:
        return _Terminal("net", net)
    raise ValueError(f"{role} terminal needs pad_id, component_ref plus pad_name, or net.")


def _pin_record(pad: Mapping[str, Any]) -> Dict[str, str]:
    return {
        "pad_id": _text(pad.get("_id")),
        "pad_name": _text(pad.get("_name")),
        "net": _text(pad.get("_net")),
    }


def _edge_record(
    reference: str,
    component: Mapping[str, Any],
    pads: Sequence[Mapping[str, Any]],
    input_net: str,
    output_net: str,
    *,
    requires_pin_model_assignment: bool,
) -> Dict[str, Any]:
    input_pads = [_pin_record(pad) for pad in pads if _text(pad.get("_net")) == input_net]
    output_pads = [_pin_record(pad) for pad in pads if _text(pad.get("_net")) == output_net]
    return {
        "component_ref": reference,
        "component_id": _text(component.get("id")),
        "value": _text(component.get("value")),
        "library": _text(component.get("library")),
        "model_kind": _component_model_kind(reference, _text(component.get("value")), _text(component.get("library"))),
        "input_net": input_net,
        "output_net": output_net,
        "input_pads": input_pads,
        "output_pads": output_pads,
        "requires_pin_model_assignment": requires_pin_model_assignment,
    }


def _series_graph(
    by_component: Mapping[str, Sequence[Mapping[str, Any]]],
    metadata: Mapping[str, Mapping[str, Any]],
    explicit_ground_nets: set[str],
) -> tuple[Dict[str, list[Dict[str, Any]]], list[str]]:
    graph: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    warnings: list[str] = []
    for reference in sorted(by_component, key=str.casefold):
        pads = by_component[reference]
        non_ground_nets = sorted({
            _text(pad.get("_net")) for pad in pads
            if _is_usable_net(_text(pad.get("_net")))
            and not _is_ground(_text(pad.get("_net")), explicit_ground_nets)
        }, key=str.casefold)
        if len(non_ground_nets) < 2:
            continue
        component = metadata.get(reference, {"reference": reference})
        ambiguous = len(non_ground_nets) > 2
        model_kind = _component_model_kind(
            reference, _text(component.get("value")), _text(component.get("library"))
        )
        needs_model = _requires_pin_model(model_kind, pads)
        if ambiguous:
            warnings.append(
                f"{reference} joins {len(non_ground_nets)} non-ground nets; the selected path is topological only and needs explicit pin/model assignment."
            )
        for start_index, input_net in enumerate(non_ground_nets):
            for output_net in non_ground_nets[start_index + 1:]:
                forward = _edge_record(
                    reference, component, pads, input_net, output_net,
                    requires_pin_model_assignment=needs_model,
                )
                reverse = _edge_record(
                    reference, component, pads, output_net, input_net,
                    requires_pin_model_assignment=needs_model,
                )
                graph[input_net].append(forward)
                graph[output_net].append(reverse)
    for edges in graph.values():
        edges.sort(key=lambda edge: (
            str(edge["output_net"]).casefold(),
            str(edge["component_ref"]).casefold(),
            str(edge["component_id"]).casefold(),
        ))
    return graph, warnings


def _shortest_path(graph: Mapping[str, Sequence[Mapping[str, Any]]], source: str, sink: str) -> list[Dict[str, Any]] | None:
    if source == sink:
        return []
    pending: deque[str] = deque([source])
    predecessor: Dict[str, tuple[str, Dict[str, Any]]] = {}
    visited = {source}
    while pending:
        current = pending.popleft()
        for edge in graph.get(current, []):
            destination = _text(edge["output_net"])
            if destination in visited:
                continue
            visited.add(destination)
            predecessor[destination] = (current, dict(edge))
            if destination == sink:
                pending.clear()
                break
            pending.append(destination)
    if sink not in predecessor:
        return None
    path: list[Dict[str, Any]] = []
    current = sink
    while current != source:
        previous, edge = predecessor[current]
        path.append(edge)
        current = previous
    path.reverse()
    return path


def _shunts(
    by_component: Mapping[str, Sequence[Mapping[str, Any]]],
    metadata: Mapping[str, Mapping[str, Any]],
    path_nets: Iterable[str],
    explicit_ground_nets: set[str],
) -> list[Dict[str, Any]]:
    selected_nets = set(path_nets)
    result: list[Dict[str, Any]] = []
    for reference in sorted(by_component, key=str.casefold):
        pads = by_component[reference]
        ground_pads = [pad for pad in pads if _is_ground(_text(pad.get("_net")), explicit_ground_nets)]
        if not ground_pads:
            continue
        component = metadata.get(reference, {"reference": reference})
        for rail_net in sorted({
            _text(pad.get("_net")) for pad in pads
            if _is_usable_net(_text(pad.get("_net")))
            and not _is_ground(_text(pad.get("_net")), explicit_ground_nets)
            and _text(pad.get("_net")) in selected_nets
        }, key=str.casefold):
            result.append({
                "component_ref": reference,
                "component_id": _text(component.get("id")),
                "value": _text(component.get("value")),
                "library": _text(component.get("library")),
                "model_kind": _component_model_kind(reference, _text(component.get("value")), _text(component.get("library"))),
                "rail_net": rail_net,
                "ground_pads": [_pin_record(pad) for pad in ground_pads],
                "rail_pads": [_pin_record(pad) for pad in pads if _text(pad.get("_net")) == rail_net],
                "requires_pin_model_assignment": len({
                    _text(pad.get("_net")) for pad in pads
                    if _is_usable_net(_text(pad.get("_net")))
                }) > 2,
            })
    return result


def extract_power_path(
    design: DesignIR,
    source: str | Mapping[str, Any],
    sink: str | Mapping[str, Any],
    *,
    ground_nets: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Find the deterministic shortest component chain between two PI terminals.

    This operates solely on imported net connectivity.  It is intentionally
    conservative: a multi-terminal component can appear in the path, but its
    internal direction and nonlinear behaviour are flagged for a model wizard
    rather than guessed from package placement or reference designator.
    """

    pads, pads_by_id, by_component = _build_pad_index(design)
    explicit_ground_nets = {_text(net).casefold() for net in (ground_nets or []) if _text(net)}
    source_terminal = _resolve_terminal(source, role="Source", pads=pads, pads_by_id=pads_by_id)
    sink_terminal = _resolve_terminal(sink, role="Sink", pads=pads, pads_by_id=pads_by_id)
    if _is_ground(source_terminal.net, explicit_ground_nets) or _is_ground(sink_terminal.net, explicit_ground_nets):
        raise ValueError("Source and sink must be non-ground power terminals; ground is represented as an explicit return or shunt.")

    metadata = _component_metadata(design)
    graph, warnings = _series_graph(by_component, metadata, explicit_ground_nets)
    series_path = _shortest_path(graph, source_terminal.net, sink_terminal.net)
    if series_path is None:
        return {
            "contract": POWER_PATH_CONTRACT,
            "status": "no_path",
            "source": source_terminal.as_dict(),
            "sink": sink_terminal.as_dict(),
            "series_path": [],
            "shunt_elements": [],
            "simulation_status": "no_path",
            "path_nets": [source_terminal.net, sink_terminal.net],
            "ground_nets": sorted({
                _text(pad.get("_net")) for pad in pads
                if _is_ground(_text(pad.get("_net")), explicit_ground_nets)
            }, key=str.casefold),
            "warnings": warnings + [
                "No non-ground component path connects the selected terminals. Copper on one net is direct; otherwise verify component pin/net import."
            ],
        }

    path_nets = [source_terminal.net]
    path_nets.extend(_text(edge["output_net"]) for edge in series_path)
    shunt_elements = _shunts(by_component, metadata, path_nets, explicit_ground_nets)
    model_assignment_required = any(edge["requires_pin_model_assignment"] for edge in series_path) or any(
        item["requires_pin_model_assignment"] for item in shunt_elements
    )
    if model_assignment_required:
        warnings.append("At least one active or multi-terminal component needs explicit input/output/ground pin assignment and a SPICE or behavioural model before closed-loop simulation.")
    if shunt_elements:
        warnings.append("Ground-connected shunts are listed separately and were not used as series traversal links.")
    return {
        "contract": POWER_PATH_CONTRACT,
        "status": "direct" if not series_path else "ready",
        "source": source_terminal.as_dict(),
        "sink": sink_terminal.as_dict(),
        "series_path": series_path,
        "shunt_elements": shunt_elements,
        "simulation_status": "needs_model_assignment" if model_assignment_required else "topology_ready",
        "path_nets": path_nets,
        "ground_nets": sorted({
            _text(pad.get("_net")) for pad in pads
            if _is_ground(_text(pad.get("_net")), explicit_ground_nets)
        }, key=str.casefold),
        "warnings": warnings,
    }
