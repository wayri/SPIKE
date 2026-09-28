# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Fail-closed openEMS geometry screen; NOT a mesher or deployment admission.

A passing screen only means the listed
known translation losses were not observed. Existing physics/resource/port
validation and independent field qualification remain mandatory.
"""
from __future__ import annotations

import hashlib
import json

from python.spike_core.contracts import AnalysisSpec, DesignIR
from .openems_adapter_source import pad_polygon


def screen_geometry(design: DesignIR, spec: AnalysisSpec) -> dict:
    if not isinstance(design, DesignIR) or not isinstance(spec, AnalysisSpec):
        raise TypeError("typed DesignIR and AnalysisSpec required")
    # This string is only digest input, never a control artifact. Preserve nonfinite
    # tokens so existing semantic preflight returns its stable errors for bad input.
    payload = json.dumps({"design": design.to_dict(), "spec": spec.to_dict()},
                         sort_keys=True, separators=(",", ":"), allow_nan=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    selected = set(spec.net_names)
    issues = []
    inspected = []

    def reject(code, identity, reason):
        issues.append({"code": code, "source_id": identity, "reason": reason})

    def active(item):
        return not selected or str(item.get("net_name") or item.get("net") or "") in selected

    if not selected:
        reject("GEOMETRY_SELECTION_REQUIRED", "design", "Explicit net selection required")
    if design.units != "mm":
        reject("GEOMETRY_UNITS_UNSUPPORTED", "design", "Only normalized mm supported")
    for collection in ("tracks", "pads", "zones", "vias", "component_bonds"):
        for index, item in enumerate(getattr(design, collection)):
            if not active(item):
                continue
            identity = str(item.get("id") or f"{collection}[{index}]")
            inspected.append({"collection": collection, "source_id": identity})
            if collection == "zones" and item.get("source_kind") == "zone_outline_intent" and not item.get("points"):
                reject("GEOMETRY_ZONE_FILL_MISSING", identity,
                       "Zone has outline intent but no filled copper; refilling or verified filled geometry is required")
            if collection == "zones" and any(item.get(key) for key in
                    ("holes", "holes_mm", "keepouts", "cutouts", "boundary_rings")):
                reject("GEOMETRY_COPPER_CUTOUT_UNMODELED", identity,
                       "Driver emits only outer polygon; copper cutouts cannot be discarded")
            if collection == "pads":
                try:
                    pad_polygon(item)
                except ValueError as error:
                    reject(str(error), identity,
                           "Pad shape, dimensions, rotation, and undrilled status must be supported by the shared contour lowerer")
            if collection == "tracks" and any(item.get(key) for key in
                    ("path", "arc", "mid", "mid_mm", "curve")):
                reject("GEOMETRY_TRACK_PATH_UNMODELED", identity, "Driver emits a straight rectangular segment")
            if collection == "vias":
                reject("GEOMETRY_VIA_PADSTACK_UNQUALIFIED", identity,
                       "Cylindrical-shell approximation lacks qualified padstack/antipad lowering")
            if collection == "component_bonds" and item.get("enabled", True):
                reject("GEOMETRY_COMPONENT_BOND_UNMODELED", identity,
                       "Driver has no component bond geometry construction, regardless of source readiness")
    if design.regions or design.bends or design.connectors:
        reject("GEOMETRY_ASSEMBLY_UNMODELED", "design", "Regions, bends and connectors need explicit lowering")
    if any(design.metadata.get(key) for key in
           ("board_outline", "board_outline_mm", "outline", "cutouts", "board_cutouts")):
        reject("GEOMETRY_BOARD_OUTLINE_UNMODELED", "design",
               "Driver substitutes selected-conductor bounds for dielectric board outline")
    return {"contract": "spike/openems-geometry-screen/v1", "input_sha256": digest,
            "screen_passed": not issues, "issues": issues, "inspected_sources": inspected,
            "production_qualified": False, "field_accuracy_validated": False,
            "integrated_into_runtime": True,
            "limitations": ["Supplementary known-loss screen, not exhaustive geometry validation",
                            "No board-outline proof, mesh/port admission or material accuracy proof",
                            "No solver execution or independent/measured qualification"]}


def verify_screen_binding(screen: dict, design: DesignIR, spec: AnalysisSpec) -> None:
    if screen != screen_geometry(design, spec):
        raise ValueError("Geometry screen is stale or tampered")
