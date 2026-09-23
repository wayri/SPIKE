# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Prescribed-volume fan inlet and pressure outlet translation, not fan curves."""
from __future__ import annotations

from collections.abc import Mapping


def fan_temperature(fan, environment):
    from .openfoam_multiregion import MultiRegionOpenFoamError, _finite
    allowed = {"id", "fluid_region_id", "flow_rate_m3_s", "boundary_evidence", "boundary_patch", "inlet_temperature_k"}
    if set(fan) - allowed:
        raise MultiRegionOpenFoamError("Fan supports prescribed volumetric inflow only; unknown fan properties are unsupported.")
    return _finite(fan.get("inlet_temperature_k", environment.get("ambient_temperature_k", 298.15)), "fan inlet_temperature_k", positive=True)


def outlets(environment, regions):
    from .openfoam_multiregion import MultiRegionOpenFoamError, _finite, _identifier
    raw = environment.get("pressure_outlets", [])
    if not isinstance(raw, list) or len(raw) > 256:
        raise MultiRegionOpenFoamError("pressure_outlets must contain at most 256 records.")
    result, seen = [], set()
    keys = {"fluid_region_id", "boundary_patch", "static_pressure_pa", "backflow_temperature_k"}
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != keys:
            raise MultiRegionOpenFoamError("Pressure outlet requires exactly region, patch, static pressure and backflow temperature.")
        region = _identifier(item["fluid_region_id"], "outlet fluid_region_id")
        patch = _identifier(item["boundary_patch"], "outlet boundary_patch")
        if region not in regions or regions[region]["kind"] != "fluid" or (region, patch) in seen:
            raise MultiRegionOpenFoamError("Pressure outlets must be unique patches on declared fluid regions.")
        seen.add((region, patch))
        result.append({"fluid_region_id": region, "boundary_patch": patch,
                       "static_pressure_pa": _finite(item["static_pressure_pa"], "outlet pressure", positive=True),
                       "backflow_temperature_k": _finite(item["backflow_temperature_k"], "outlet temperature", positive=True)})
    return sorted(result, key=lambda item: (item["fluid_region_id"], item["boundary_patch"]))


def validate_flow_boundaries(case, meshes):
    from .openfoam_multiregion import MultiRegionOpenFoamError
    outlet_keys = {(item["fluid_region_id"], item["boundary_patch"])
                   for item in case["environment"].get("pressure_outlets", [])}
    fan_keys = {(item["fluid_region_id"], item["boundary_patch"]): f"fan:{item['id']}" for item in case["fans"]}
    if len(fan_keys) != len(case["fans"]) or len({item["id"] for item in case["fans"]}) != len(case["fans"]):
        raise MultiRegionOpenFoamError("Fan IDs and inlet patches must be unique.")
    if case["fans"] and case["environment"]["enclosure"] == "sealed":
        raise MultiRegionOpenFoamError("A prescribed inlet fan requires an open or vented enclosure; sealed internal fans are unsupported.")
    for fan in case["fans"]:
        if fan["boundary_evidence"]["sha256"] != meshes[fan["fluid_region_id"]]["digest"]:
            raise MultiRegionOpenFoamError("Fan boundary evidence must bind the exact materialized polyMesh digest.")
    radiating = {(item["region_id"], item["patch"]) for item in case["environment"].get("radiation_model", {}).get("boundaries", [])}
    if radiating & outlet_keys:
        raise MultiRegionOpenFoamError("An outlet cannot also be a radiating wall.")
    for region, patch in outlet_keys:
        if meshes[region]["ownership"].get(patch) != "external:pressure_outlet":
            raise MultiRegionOpenFoamError("Pressure outlet must own an exact external:pressure_outlet mesh patch.")
    for region, patch in fan_keys:
        if not any(key[0] == region for key in outlet_keys):
            raise MultiRegionOpenFoamError("Every fan-driven fluid region requires an explicit pressure outlet.")
    for region, mesh in meshes.items():
        for patch, owner in mesh["ownership"].items():
            if owner.startswith("fan:") and fan_keys.get((region, patch)) != owner:
                raise MultiRegionOpenFoamError("Orphan or multiply owned fan patch.")
            if owner == "external:pressure_outlet" and (region, patch) not in outlet_keys:
                raise MultiRegionOpenFoamError("Pressure outlet patch requires explicit pressure and backflow temperature.")


def boundary_body(case, region, patch, owner, field):
    """Return a supported flow BC body, or None for existing wall/interface BCs."""
    if region["kind"] != "fluid":
        return None
    if owner.startswith("fan:") and field == "T":
        fan = next(item for item in case["fans"] if owner == f"fan:{item['id']}")
        temperature = fan["inlet_temperature_k"]
        return f"type fixedValue; value uniform {temperature:.17g};"
    if owner != "external:pressure_outlet":
        return None
    outlet = next(item for item in case["environment"]["pressure_outlets"]
                  if item["fluid_region_id"] == region["id"] and item["boundary_patch"] == patch)
    if field == "U":
        return "type pressureInletOutletVelocity; value uniform (0 0 0);"
    if field == "p_rgh":
        return f"type prghPressure; rho rho; p uniform {outlet['static_pressure_pa']:.17g}; value uniform {outlet['static_pressure_pa']:.17g};"
    if field == "T":
        temperature = outlet["backflow_temperature_k"]
        return f"type inletOutlet; inletValue uniform {temperature:.17g}; value uniform {temperature:.17g};"
    return None
