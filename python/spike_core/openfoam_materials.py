# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Material admission shared by generated multiregion CHT dictionaries."""
from collections.abc import Mapping


def normalize_material(raw):
    # Deferred import preserves the public adapter's existing error type/helpers.
    from .openfoam_multiregion import MultiRegionOpenFoamError,_identifier,_finite
    if not isinstance(raw,Mapping):
        raise MultiRegionOpenFoamError("Every material must be an object.")
    material_id=_identifier(raw.get("id"),"material.id")
    phase=str(raw.get("phase") or "")
    if phase not in {"solid","fluid"}:
        raise MultiRegionOpenFoamError(f"Material {material_id} phase must be solid or fluid.")
    result={"id":material_id,"phase":phase}
    for key in ("conductivity_w_mk","density_kg_m3","specific_heat_j_kgk"):
        result[key]=_finite(raw.get(key),f"material {material_id} {key}",positive=True)
    if phase=="fluid":
        result["dynamic_viscosity_pa_s"]=_finite(raw.get("dynamic_viscosity_pa_s"),f"fluid material {material_id} dynamic_viscosity_pa_s",positive=True)
    if "density_model" in raw:
        if phase!="fluid":
            raise MultiRegionOpenFoamError("Thermal buoyancy density models require a fluid material.")
        from .openfoam_buoyancy import validate_density_model
        try:
            result["density_model"]=validate_density_model(raw["density_model"],result["density_kg_m3"])
        except ValueError as exc:
            raise MultiRegionOpenFoamError(str(exc)) from exc
    if "emissivity" in raw:
        result["emissivity"]=_finite(raw["emissivity"],f"material {material_id} emissivity",nonnegative=True)
        if result["emissivity"]>1:
            raise MultiRegionOpenFoamError(f"material {material_id} emissivity must not exceed one.")
    return result
