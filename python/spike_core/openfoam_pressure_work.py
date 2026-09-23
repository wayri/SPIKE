# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Explicit pressure-derivative policy, separate from solver qualification."""


def pressure_work_policy(environment, materials, gravity):
    from .openfoam_multiregion import MultiRegionOpenFoamError
    enabled=environment.get("dpdt_enabled",True)
    if type(enabled) is not bool:
        raise MultiRegionOpenFoamError("environment.dpdt_enabled must be boolean")
    if not enabled and (any(gravity) or any(item.get("density_model") for item in materials) or not any(item["phase"]=="fluid" for item in materials)):
        raise MultiRegionOpenFoamError("dpdt_enabled=false requires a constant-density fluid with zero gravity and no buoyancy model")
    # Preserve legacy manifest identity when callers have not selected a policy.
    return ({"dpdt_enabled":enabled,"pressure_work_model":"enthalpy_dpdt" if enabled else "constant_density_no_dpdt"}
            if "dpdt_enabled" in environment else {})
