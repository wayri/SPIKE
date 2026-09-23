"""Electrical geometry extraction shared by PI, SI, reports, and the UI."""

from __future__ import annotations

from typing import Any, Dict

from .contracts import DesignIR


def _net_name(item: Dict[str, Any]) -> str:
    return str(item.get("net_name") or item.get("net") or "")


def extract_net_geometry(design: DesignIR, net_name: str) -> Dict[str, Any]:
    if not net_name:
        raise ValueError("A net name is required.")

    tracks = [item for item in design.tracks if _net_name(item) == net_name]
    zones = [item for item in design.zones if _net_name(item) == net_name]
    vias = [item for item in design.vias if _net_name(item) == net_name]
    pads = [item for item in design.pads if _net_name(item) == net_name]
    layer_names = set()
    for item in tracks + zones:
        if item.get("layer"):
            layer_names.add(str(item["layer"]))
    for item in vias + pads:
        for layer in item.get("layers", []):
            if str(layer).endswith(".Cu"):
                layer_names.add(str(layer))

    ordered_layers = [
        layer for layer in design.layers
        if str(layer.get("name", "")) in layer_names
    ]
    return {
        "contract": "spike/net-geometry/v1",
        "design_id": design.design_id,
        "net": net_name,
        "technology": design.technology,
        "regions": design.regions,
        "bends": design.bends,
        "layers": ordered_layers,
        "tracks": tracks,
        "zones": zones,
        "vias": vias,
        "pads": pads,
        "stackup": design.stackup,
        "counts": {
            "tracks": len(tracks),
            "zones": len(zones),
            "vias": len(vias),
            "pads": len(pads),
        },
    }
