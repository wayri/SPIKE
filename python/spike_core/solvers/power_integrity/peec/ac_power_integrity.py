# SPDX-License-Identifier: Apache-2.0
"""Explicit uniform-line AC diagnostics and imposed-field slab Joule loss.

Independent derivation and limits: docs/AC_POWER_INTEGRITY_EFFECTS.md.
These reference models do not infer PCB geometry or qualify native PEEC.
"""
from __future__ import annotations

import cmath
import math
from typing import Any, Mapping

MU0 = 4e-7 * math.pi


def _number(value: Any, name: str, minimum: float = 0, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    result = float(value)
    if not math.isfinite(result) or result < minimum or (positive and result == 0):
        raise ValueError(f"{name} is outside its finite passive domain.")
    return result


def _complex(value: Any, name: str, *, passive: bool = False) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} requires [real, imaginary].")
    result = complex(*[_number(v, name, -math.inf) for v in value])
    if passive and result.real < 0:
        raise ValueError(f"{name} must have nonnegative real part.")
    return result


def _pair(value: complex) -> list[float]:
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        raise ValueError("AC response exceeded finite numerical range.")
    return [value.real, value.imag]


def slab_field_loss(frequency_hz: float, width_m: float, thickness_m: float,
                    conductivity_s_m: float, h_left_a_m: complex, h_right_a_m: complex,
                    relative_permeability: float = 1) -> dict[str, Any]:
    """RMS signed tangential surface fields; exact infinite-width 1D diffusion.

    P/l = w Re(Eright Hright* - Eleft Hleft*) is Joule loss. The
    imaginary boundary power is deliberately not added to line inductance.
    """
    f = _number(frequency_hz, "frequency_hz")
    w = _number(width_m, "width_m", positive=True)
    t = _number(thickness_m, "thickness_m", positive=True)
    sigma = _number(conductivity_s_m, "conductivity_s_m", positive=True)
    mu = MU0 * _number(relative_permeability, "relative_permeability", positive=True)
    for value in (h_left_a_m, h_right_a_m):
        if not isinstance(value, complex) or not math.isfinite(abs(value)):
            raise ValueError("Slab surface fields require finite complex RMS amplitudes.")
    avg, diff = (h_right_a_m+h_left_a_m)/2, (h_right_a_m-h_left_a_m)/2
    k = cmath.sqrt(1j*2*math.pi*f*mu*sigma)
    u = k*t/2
    if abs(u) < 1e-3:
        # k*coth(u) = (1+u²/3-u⁴/45+2u⁶/945)/(t/2).
        kcoth = (1+u*u/3-u**4/45+2*u**6/945)/(t/2)
        ktanh = k*(u-u**3/3+2*u**5/15)
    else:
        tangent = cmath.tanh(u)
        kcoth, ktanh = k/tangent, k*tangent
    e_right, e_left = (ktanh*avg+kcoth*diff)/sigma, (-ktanh*avg+kcoth*diff)/sigma
    skin_loss = 2*w*kcoth.real*abs(diff)**2/sigma
    imposed_bias_loss = 2*w*ktanh.real*abs(avg)**2/sigma
    if min(skin_loss, imposed_bias_loss) < -1e-15:
        raise ValueError("Slab Joule loss violated nonnegative diffusion energy.")
    loss = max(0., skin_loss)+max(0., imposed_bias_loss)
    current = w*(h_right_a_m-h_left_a_m)
    resistance = loss/abs(current)**2 if abs(current) > 0 else None
    if not math.isfinite(loss) or (resistance is not None and not math.isfinite(resistance)):
        raise ValueError("Slab loss exceeded finite numerical range.")
    return {"current_a_rms": _pair(current), "joule_loss_w_per_m": loss,
            "isolated_skin_loss_w_per_m": max(0., skin_loss),
            "imposed_field_proximity_loss_w_per_m": max(0., imposed_bias_loss),
            "effective_resistance_ohm_per_m": resistance,
            "dc_resistance_ohm_per_m": 1/(sigma*w*t),
            "e_left_v_m": _pair(e_left), "e_right_v_m": _pair(e_right),
            "skin_depth_m": math.sqrt(1/(math.pi*f*mu*sigma)) if f else None}


def analyze_ac_power_integrity(request: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate explicit passive RLGC and source/load boundary conditions."""
    if not isinstance(request, Mapping) or request.get("contract") != "spike/ac-pi-request/v1":
        raise ValueError("Expected spike/ac-pi-request/v1.")
    required = {"contract", "frequencies_hz", "length_m", "R_ohm_per_m", "L_h_per_m",
                "G_s_per_m", "C_f_per_m", "source_impedance_ohm", "load_impedance_ohm"}
    if not required.issubset(request) or set(request)-required-{"conductor"}:
        raise ValueError("AC request needs all declared fields and no unknown fields.")
    values = request.get("frequencies_hz")
    if not isinstance(values, list) or not 1 <= len(values) <= 2048:
        raise ValueError("AC sweep needs 1–2048 ascending frequencies.")
    frequencies = [_number(v, "frequency_hz") for v in values]
    if any(b <= a for a, b in zip(frequencies, frequencies[1:])):
        raise ValueError("AC frequencies must strictly increase.")
    length = _number(request.get("length_m"), "length_m", positive=True)
    r, l, g, c = [_number(request.get(key), key) for key in
                   ("R_ohm_per_m", "L_h_per_m", "G_s_per_m", "C_f_per_m")]
    source = _complex(request.get("source_impedance_ohm"), "source impedance", passive=True)
    load = None if request.get("load_impedance_ohm") is None else _complex(
        request["load_impedance_ohm"], "load impedance", passive=True)
    conductor = request.get("conductor")
    if conductor is not None and not isinstance(conductor, Mapping):
        raise ValueError("conductor must be an explicit slab object.")
    if conductor is not None and (not {"width_m", "thickness_m", "conductivity_s_m"}.issubset(conductor)
            or set(conductor)-{"width_m", "thickness_m", "conductivity_s_m", "relative_permeability", "field_bias_ratio", "roughness_rms_um", "include_internal_reactance"}):
        raise ValueError("Slab needs explicit width, thickness, conductivity and no unknown fields.")
    if conductor is not None and not isinstance(conductor.get("include_internal_reactance", False), bool):
        raise ValueError("include_internal_reactance must be boolean; L must be external when enabled.")
    samples = []
    for f in frequencies:
        slab = None
        resistance = r
        internal_reactance = 0.0
        if conductor is not None:
            width = _number(conductor.get("width_m"), "width_m", positive=True)
            bias = _complex(conductor.get("field_bias_ratio", [0, 0]), "field_bias_ratio")
            # Unit total current: Hdiff=1/(2w), Havg=bias*Hdiff.
            diff, avg = 1/(2*width), bias/(2*width)
            slab = slab_field_loss(f, width, conductor.get("thickness_m"),
                conductor.get("conductivity_s_m"), complex(avg-diff), complex(avg+diff),
                conductor.get("relative_permeability", 1))
            from .conductor_ac_loss import slab_internal_impedance_per_m
            diffusion = slab_internal_impedance_per_m(frequency_hz=f, width_m=width,
                thickness_m=conductor.get("thickness_m"), conductivity_s_per_m=conductor.get("conductivity_s_m"),
                relative_permeability=conductor.get("relative_permeability", 1),
                roughness_rms_m=_number(conductor.get("roughness_rms_um", 0), "roughness_rms_um")*1e-6)
            resistance = slab["effective_resistance_ohm_per_m"] * diffusion["roughness_correction"]
            slab["roughness_correction"] = diffusion["roughness_correction"]
            slab["roughness_corrected_loss_w_per_m"] = slab["joule_loss_w_per_m"] * diffusion["roughness_correction"]
            if conductor.get("include_internal_reactance", False):
                if abs(bias) > 0:
                    raise ValueError("Internal reactance currently requires zero imposed field bias.")
                internal_reactance = diffusion["reactance_ohm_per_m"]
        z, y = complex(resistance, 2*math.pi*f*l+internal_reactance)*length, complex(g, 2*math.pi*f*c)*length
        q = cmath.sqrt(z*y)
        if not math.isfinite(abs(q)) or q.real > 300:
            raise ValueError("Uniform-line electrical length exceeds bounded numerical range.")
        sinhc = 1+q*q/6+q**4/120 if abs(q) < 1e-3 else cmath.sinh(q)/q
        a, b, cc, d = cmath.cosh(q), z*sinhc, y*sinhc, cmath.cosh(q)
        # Vr=vl*scale, Ir=il*scale avoids reciprocal short-load singularities.
        vl, il = (1+0j, 0j) if load is None else (load, 1+0j)
        sending, input_current = a*vl+b*il, cc*vl+d*il
        denominator = sending+source*input_current
        scale = max(abs(vl), abs(z*il), abs(source*il),
                    abs(a*vl)+abs(b*il)+abs(source*cc*vl)+abs(source*d*il))
        relative_margin = abs(denominator)/max(scale, 1e-300)
        if relative_margin < 1e-12 or abs(denominator) == 0:
            samples.append({"frequency_hz": f, "status": "singular_source_load_resonance",
                            "denominator_relative_margin": relative_margin, "slab": slab})
            continue
        vload, vsend, iinput = vl/denominator, sending/denominator, input_current/denominator
        gain = abs(vload/vsend) if vsend != 0 else None
        if gain is not None:
            _number(gain, "load-to-sending voltage gain")
        _number(abs(vload), "load-to-source voltage gain")
        samples.append({"frequency_hz": f, "status": "computed", "R_ohm_per_m": resistance,
            "internal_reactance_ohm_per_m": internal_reactance,
            "input_impedance_ohm": _pair(sending/input_current) if input_current != 0 else None,
            "input_impedance_state": "finite" if input_current != 0 else "open",
            "load_voltage_v_rms": _pair(vload), "sending_voltage_v_rms": _pair(vsend),
            "input_current_a_rms": _pair(iinput), "load_to_source_voltage_gain": abs(vload),
            "load_to_sending_voltage_gain": gain,
            "voltage_rise_above_sending": gain is not None and gain > 1+1e-9,
            "denominator_relative_margin": relative_margin, "slab": slab})
    return {"contract": "spike/ac-pi-result/v1", "status": "completed_with_warnings",
            "model_status": "experimental", "source_voltage_v_rms": [1, 0], "samples": samples,
            "assumptions": ["Explicit uniform passive RLGC, RMS phasors with exp(+jωt).",
                "Slab replaces R; imposed surface field bias is not extracted from nearby PCB conductors.",
                "Slab resistance describes this conductor; return-conductor loss is not included automatically.",
                "No radiation, geometry-derived proximity, material dispersion, nonlinear loads, vias or full-board qualification.",
                "Internal reactance is opt-in; when enabled L is external only, avoiding double-counted internal energy.",
                "Optional RMS roughness scales resistance only; it is not a causal broadband phase model."],
            "provenance": {"solver": "spike.explicit_uniform_ac_pi", "production_qualified": False,
                           "request": dict(request)}}
