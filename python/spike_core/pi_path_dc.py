"""Stamp reviewed cross-net component interfaces into the DC conductor graph."""

from __future__ import annotations

from math import sqrt
from typing import Any, Dict, List, Tuple

from .contracts import AnalysisSpec, DesignIR, ValidationIssue
from .hybrid_mesh import HybridMesh, nearest_mesh_node
from .pi_path import validate_pi_path


PI_PATH_INTERFACE_ELEMENT_CONTRACT = "spike/pi-path-interface-elements/v1"


def build_pi_path_interface_elements(
    mesh: HybridMesh,
    design: DesignIR,
    spec: AnalysisSpec,
) -> Tuple[List[Dict[str, Any]], List[ValidationIssue]]:
    """Resolve reviewed cross-net component models onto exact conductor nodes.

    These records are electrical equivalent branches, not fabricated package
    solids.  The explicit distinction lets previews and result viewers show the
    part-mediated continuation while keeping package current density and field
    claims unavailable until physical package/bond geometry is assigned.
    """

    pi_path = spec.options.get("pi_path")
    if not isinstance(pi_path, dict):
        return [], []
    validation = validate_pi_path(pi_path, design, "dc")
    issues = [
        ValidationIssue(item["code"], item["severity"], item["message"])
        for item in validation["issues"]
    ]
    if not validation["valid"]:
        return [], issues

    pads = {str(item.get("id", "")): item for item in design.pads}

    def interface_node(pad_id: str, net: str) -> int | None:
        pad = pads.get(pad_id)
        if pad is None:
            return None
        return nearest_mesh_node(mesh, {
            "position_mm": pad.get("at", (0, 0)),
            "net": net,
            "layer_scope": "connected_conductor",
            "geometry_anchor": {"id": pad_id, "type": "pad"},
        }, net)

    elements: List[Dict[str, Any]] = []
    for interface in validation["interfaces"]:
        input_node = interface_node(interface["input_pad_id"], interface["from_net"])
        output_node = interface_node(interface["output_pad_id"], interface["to_net"])
        if input_node is None or output_node is None:
            issues.append(ValidationIssue(
                "PI_PATH_INTERFACE_NOT_ON_MESH", "error",
                f"{interface['component_ref'] or interface['id']} could not connect both reviewed pads to the conductor mesh.",
            ))
            continue

        start_node = mesh.nodes[input_node]
        stop_node = mesh.nodes[output_node]
        start = [start_node.x_mm, start_node.y_mm, start_node.z_mm]
        stop = [stop_node.x_mm, stop_node.y_mm, stop_node.z_mm]
        requested_resistance = float(interface["dc_resistance_ohm"])
        elements.append({
            "contract": PI_PATH_INTERFACE_ELEMENT_CONTRACT,
            "id": f"pi-path:{interface['id']}",
            "kind": "series_component",
            "source_kind": "component_bridge",
            "topology": "line2",
            "vertices_mm": [start, stop],
            "input_node": input_node,
            "output_node": output_node,
            "start_mm": start[:2],
            "end_mm": stop[:2],
            "start_z_mm": start[2],
            "end_z_mm": stop[2],
            "x_mm": (start[0] + stop[0]) / 2,
            "y_mm": (start[1] + stop[1]) / 2,
            "z_mm": (start[2] + stop[2]) / 2,
            "length_mm": sqrt(sum((right - left) ** 2 for left, right in zip(start, stop))),
            "layer": f"{start_node.layer}->{stop_node.layer}",
            "from_layer": start_node.layer,
            "to_layer": stop_node.layer,
            "net": f"{interface['from_net']}->{interface['to_net']}",
            "from_net": interface["from_net"],
            "to_net": interface["to_net"],
            "source_id": interface["component_ref"] or interface["id"],
            "component_ref": interface["component_ref"],
            "input_pad_id": interface["input_pad_id"],
            "output_pad_id": interface["output_pad_id"],
            "model_ref": interface.get("model_ref", ""),
            "requested_resistance_ohm": requested_resistance,
            "resistance_ohm": max(requested_resistance, 1e-12),
            "resistance_source": interface.get("resistance_source", ""),
            "geometry_model": "pad_center_equivalent_branch",
            "spatial_material_model": "unavailable_without_package_and_bond_geometry",
            "current_density_supported": False,
        })
    return elements, issues


def stamp_pi_path_interfaces(
    mesh: HybridMesh,
    design: DesignIR,
    spec: AnalysisSpec,
    node_positions: List[tuple[float, float, str]],
    edges: List[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Validate and stamp linear DC equivalents between ordered net segments."""
    elements, issues = build_pi_path_interface_elements(mesh, design, spec)
    for element in elements:
        edges.append({
            **element,
            "a": element["input_node"],
            "b": element["output_node"],
            "width_mm": 1.0,
            "thickness_mm": 1.0,
        })
    return issues


__all__ = [
    "PI_PATH_INTERFACE_ELEMENT_CONTRACT",
    "build_pi_path_interface_elements",
    "stamp_pi_path_interfaces",
]
