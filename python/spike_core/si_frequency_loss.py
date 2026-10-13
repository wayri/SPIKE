# SPDX-License-Identifier: Apache-2.0
"""Isolated trace diffusion for bounded quasi-TEM SI channels."""
from math import isfinite
from typing import Mapping, Any


def validate_loss_model(value: Any) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, Mapping) or set(value)-{"conductor", "roughness_model", "rms_roughness_um"}:
        raise ValueError("loss_model requires conductor, roughness_model and RMS roughness only.")
    mode = value.get("conductor", "slab_skin")
    roughness = value.get("roughness_model", "none")
    rms = value.get("rms_roughness_um", 0.0)
    if not isinstance(mode, str) or not isinstance(roughness, str) or mode not in {"dc", "slab_skin"} or roughness not in {"none", "hammerstad"}:
        raise ValueError("Unsupported SI conductor or roughness model.")
    if isinstance(rms, bool) or not isinstance(rms, (int, float)) or not isfinite(rms) or rms < 0:
        raise ValueError("rms_roughness_um must be finite and nonnegative.")
    if (rms and (roughness == "none" or mode == "dc")) or (roughness != "none" and mode == "dc"):
        raise ValueError("Roughness requires slab_skin and an explicit hammerstad model.")
    return {"conductor": mode, "roughness_model": roughness, "rms_roughness_um": float(rms)}


def trace_impedance(extraction: Mapping, frequency_hz: float, width_m: float, dc_resistance: float) -> complex:
    values = extraction["rlgc_per_m"]
    # Old saved extraction records retain their declared DC model.
    if "conductor_loss" not in values:
        return complex(dc_resistance)
    model = validate_loss_model(values["conductor_loss"])
    if model["conductor"] == "dc":
        return complex(dc_resistance)
    from .conductor_ac_loss import slab_internal_impedance_per_m
    result = slab_internal_impedance_per_m(
        frequency_hz=float(frequency_hz), width_m=width_m,
        thickness_m=values["conductor_thickness_m"],
        conductivity_s_per_m=values["conductivity_s_per_m"],
        roughness_rms_m=model["rms_roughness_um"]*1e-6,
    )
    return result["impedance_ohm_per_m"]
