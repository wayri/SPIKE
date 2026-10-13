# SPDX-License-Identifier: Apache-2.0
"""Original ideal CCM averaged voltage-mode reference, not a circuit solver.

All voltages are output magnitudes. Negative feedback regulates magnitude for
the inverting buck-boost. See docs/SPIKES_SMPS_STABILITY.md for the derivation.
"""
from __future__ import annotations

import math
from numbers import Real

import numpy as np
from numpy.polynomial import polynomial as poly


TOPOLOGIES = ("buck", "boost", "buck_boost", "flyback")
CONTROLLERS = ("pi", "type_ii", "type_iii")
LIMITATIONS = [
    "Ideal CCM state-space averaged voltage-mode reference; not native switching FRA.",
    "Stability describes only the rational, continuous-time, negative-feedback model.",
    "No DCM, current-mode control, sampling/PWM delay, saturation, startup or protection.",
    "No ESR/DCR, semiconductor loss, leakage inductance, optocoupler or input-filter dynamics.",
    "Resistive load only; no constant-power load or multi-output/multiloop interaction.",
    "No thermal, EMI, component-rating, power-level or hardware qualification.",
    "Numerical root tolerances are not physical design margins; human review required.",
]


def default_config():
    """Return an independent editable configuration; quantities use SI units."""
    return dict(topology="buck", input_voltage_v=24., duty_cycle=.5,
                inductance_h=100e-6, capacitance_f=470e-6,
                load_resistance_ohm=6., switching_frequency_hz=100000.,
                turns_ratio=1., start_hz=1., stop_hz=10000., points=401,
                controller_type="type_ii", controller_gain=100., zero1_hz=100.,
                zero2_hz=1000., pole1_hz=10000., pole2_hz=20000.,
                feedback_gain=1., pwm_gain=1.)


def _config(config):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object")
    c = default_config()
    unknown = set(config) - set(c)
    if unknown:
        raise ValueError("Unsupported configuration fields: " + ", ".join(sorted(unknown)))
    c.update(config)
    if c["topology"] not in TOPOLOGIES or c["controller_type"] not in CONTROLLERS:
        raise ValueError("Unsupported topology or controller type")
    if type(c["points"]) is not int or not 3 <= c["points"] <= 10000:
        raise ValueError("points must be an integer in 3..10000")
    for name, value in c.items():
        if name in ("topology", "controller_type", "points"):
            continue
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite positive real number")
        try:
            value = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"{name} is outside the numerical envelope") from exc
        if not math.isfinite(value) or not 1e-12 <= value <= 1e12:
            raise ValueError(f"{name} must be finite and in [1e-12, 1e12]")
        c[name] = value
    if not 1e-6 <= c["duty_cycle"] <= 1 - 1e-6:
        raise ValueError("duty_cycle must be in [1e-6, 1-1e-6]")
    if c["start_hz"] >= c["stop_hz"]:
        raise ValueError("start_hz must be less than stop_hz")
    if c["topology"] != "flyback" and c["turns_ratio"] != 1:
        raise ValueError("turns_ratio is Ns/Np and applies only to flyback")
    return c


def validate(config):
    """Return normalized inputs without evaluating the model (CCM checked at run)."""
    return _config(config)


def _roots(coefficients):
    """Ascending coefficients, no pole-zero cancellations; backward-error gate."""
    coefficients = np.trim_zeros(np.asarray(coefficients, dtype=float), "b")
    if not np.isfinite(coefficients).all() or not len(coefficients):
        raise ValueError("Nonfinite or degenerate polynomial")
    coefficients = coefficients / np.max(np.abs(coefficients))
    roots = poly.polyroots(coefficients)
    for root in roots:
        scale = poly.polyval(abs(root), abs(coefficients))
        if not np.isfinite(root) or abs(poly.polyval(root, coefficients)) > 1e-7 * scale:
            raise ValueError("Polynomial roots failed backward-error check")
    return roots


def _pairs(values):
    return [[float(z.real), float(z.imag)] for z in values]


def _positive_roots(coefficients):
    candidates = sorted(float(z.real) for z in _roots(coefficients)
                        if z.real > 0 and abs(z.imag) <= 1e-7 * z.real)
    roots = []
    for candidate in candidates:
        if not roots or abs(candidate / roots[-1] - 1) > 1e-6:
            roots.append(candidate)
    return roots


def _crossings(numerator, denominator, omega_scale, phase, c):
    """Enumerate polynomial candidate crossings, then check the rational value."""
    # N(jx)N(-jx) - D(jx)D(-jx) is real/even; x^2 is the root variable.
    nj = numerator * (1j ** np.arange(len(numerator)))
    dj = denominator * (1j ** np.arange(len(denominator)))
    magnitude = poly.polysub(poly.polymul(nj, nj.conjugate()),
                            poly.polymul(dj, dj.conjugate())).real[::2]
    # Im(N(jx)D(-jx))/x is also a real polynomial in x^2.
    imaginary = poly.polymul(nj, dj.conjugate()).imag[1::2]
    gain, negative_real = [], []
    for kind, coefficients, target in (("gain", magnitude, gain),
                                        ("phase", imaginary, negative_real)):
        if not np.any(coefficients):
            raise ValueError("Degenerate continuum of loop crossings")
        for squared in _positive_roots(coefficients):
            x = math.sqrt(squared)
            frequency = x * omega_scale / (2 * math.pi)
            response = poly.polyval(1j * x, numerator) / poly.polyval(1j * x, denominator)
            item = dict(frequency_hz=frequency,
                        in_sweep=c["start_hz"] <= frequency <= c["stop_hz"],
                        below_averaging_limit=frequency <= c["switching_frequency_hz"] / 10)
            if kind == "gain":
                if abs(abs(response) - 1) > 1e-5:
                    raise ValueError("Gain crossing failed response residual check")
                angle = float(phase(x * omega_scale))
                item.update(phase_deg=angle, phase_margin_deg=180 + angle)
            else:
                if abs(response.imag) > 1e-5 * abs(response):
                    raise ValueError("Phase crossing failed response residual check")
                if response.real >= 0:
                    continue
                db = 20 * math.log10(abs(response))
                item.update(gain_db=db, gain_margin_db=-db)
            target.append(item)
    return dict(gain_crossings=gain, phase_crossings=negative_real,
                method="Positive real roots of rational crossing polynomials; not sampled interpolation",
                scope="All finite positive-frequency model crossings, including outside the display sweep",
                missing_crossing="An empty list means no finite crossing found, not infinite certified margin")


def analyze(config):
    """Analyze one ideal operating point. Invalid/DCM cases raise ValueError."""
    c = _config(config)
    vin, duty, inductance, capacitance, resistance = (
        c[name] for name in ("input_voltage_v", "duty_cycle", "inductance_h",
                             "capacitance_f", "load_resistance_ohm"))
    topology = c["topology"]
    q, turns = 1 - duty, c["turns_ratio"]
    coupling = 1. if topology == "buck" else q / turns
    excitation = vin if topology == "boost" else vin * duty
    voltage = excitation / coupling
    current = voltage / (resistance * coupling)
    slope_on = (vin - voltage) / inductance if topology == "buck" else vin / inductance
    ripple = slope_on * duty / c["switching_frequency_hz"]
    valley = current - ripple / 2
    if valley <= 1e-9 * max(current, ripple):
        raise ValueError("CCM not admissible: estimated inductor/magnetizing valley current is nonpositive or at the boundary")
    b_current = (vin if topology == "buck" else
                 voltage if topology == "boost" else vin + voltage / turns) / inductance
    b_voltage = 0. if topology == "buck" else -current / (turns * capacitance)
    a = 1 / (resistance * capacitance)
    omega_scale = coupling / math.sqrt(inductance * capacitance)
    b = omega_scale ** 2
    n0 = coupling * b_current / capacitance
    # Dimensionless x=s/omega_scale polynomials, ascending coefficient order.
    plant_num = np.array([n0 / b, b_voltage / omega_scale])
    plant_den = np.array([1., a / omega_scale, 1.])
    zeros_hz = [c["zero1_hz"]]
    poles_hz = [] if c["controller_type"] == "pi" else [c["pole1_hz"]]
    if c["controller_type"] == "type_iii":
        zeros_hz.append(c["zero2_hz"])
        poles_hz.append(c["pole2_hz"])
    breakpoints = np.array([a, omega_scale] + [2 * math.pi * f for f in zeros_hz + poles_hz])
    if max(breakpoints) / min(breakpoints) > 1e10:
        raise ValueError("Model time scales exceed the 1e10 numerical conditioning envelope")
    controller_num = np.array([c["controller_gain"] / omega_scale])
    controller_den = np.array([0., 1.])
    for frequency in zeros_hz:
        controller_num = poly.polymul(controller_num, [1., omega_scale / (2 * math.pi * frequency)])
    for frequency in poles_hz:
        controller_den = poly.polymul(controller_den, [1., omega_scale / (2 * math.pi * frequency)])
    loop_num = poly.polymul(plant_num, controller_num) * c["feedback_gain"] * c["pwm_gain"]
    loop_den = poly.polymul(plant_den, controller_den)
    common_scale = max(np.max(abs(loop_num)), np.max(abs(loop_den)))
    loop_num, loop_den = loop_num / common_scale, loop_den / common_scale
    closed_den = poly.polyadd(loop_den, loop_num)
    closed_poles = _roots(closed_den) * omega_scale
    tolerance = 1e-8 * np.maximum(omega_scale, abs(closed_poles))
    stability = ("unstable" if np.any(closed_poles.real > tolerance) else
                 "stable" if np.all(closed_poles.real < -tolerance) else "marginal_or_unresolved")

    def plant_phase(omega):
        return np.degrees(np.arctan2(b_voltage * omega, n0)
                          - np.arctan2(a * omega, b - omega * omega))

    def loop_phase(omega):
        angle = plant_phase(omega) - 90.
        for frequency in zeros_hz:
            angle = angle + np.degrees(np.arctan(omega / (2 * math.pi * frequency)))
        for frequency in poles_hz:
            angle = angle - np.degrees(np.arctan(omega / (2 * math.pi * frequency)))
        return angle

    frequency = np.geomspace(c["start_hz"], c["stop_hz"], c["points"])
    x = 2j * math.pi * frequency / omega_scale
    plant = poly.polyval(x, plant_num) / poly.polyval(x, plant_den)
    loop = poly.polyval(x, loop_num) / poly.polyval(x, loop_den)
    margins = _crossings(loop_num, loop_den, omega_scale, loop_phase, c)
    warnings = []
    if c["stop_hz"] > c["switching_frequency_hz"] / 10:
        warnings.append("Sweep exceeds fs/10: high-frequency averaged response is illustrative, not switching-loop evidence.")
    if any(not p["below_averaging_limit"] for p in margins["gain_crossings"]):
        warnings.append("A unity crossing exceeds fs/10; model stability cannot establish switching-loop stability.")
    if ripple / current > .5:
        warnings.append("Inductor ripple exceeds 50% of its average; small-ripple averaging accuracy is unverified.")
    output_ripple = (ripple / (8 * c["switching_frequency_hz"] * capacitance) if topology == "buck"
                     else voltage * duty / (resistance * c["switching_frequency_hz"] * capacitance))
    if output_ripple > .05 * voltage:
        warnings.append("Estimated capacitor ripple exceeds 5% of output; constant-voltage ripple/CCM estimates need switched verification.")
    report = dict(
        contract="spikes/smps-stability/v1", status="completed", model_status="approximate",
        backend="Python ideal CCM averaged analytical reference", config=c,
        frequency_hz=frequency.tolist(), plant=_pairs(plant), loop=_pairs(loop),
        plant_gain_db=(20 * np.log10(abs(plant))).tolist(),
        plant_phase_deg=plant_phase(2 * math.pi * frequency).tolist(),
        loop_gain_db=(20 * np.log10(abs(loop))).tolist(),
        loop_phase_deg=loop_phase(2 * math.pi * frequency).tolist(),
        operating_point=dict(output_voltage_v=voltage, output_polarity=-1 if topology == "buck_boost" else 1,
                             output_current_a=voltage / resistance, output_power_w=voltage ** 2 / resistance,
                             inductor_current_a=current, reference_voltage_v=c["feedback_gain"] * voltage),
        ccm=dict(admissible=True, inductor_ripple_pp_a=ripple, valley_current_a=valley,
                 peak_current_a=current + ripple / 2, output_ripple_pp_v_estimate=output_ripple,
                 method="Ideal constant-output-voltage triangular current ripple; not a switched-periodic solution"),
        state_space=dict(a_per_s=[[0., -coupling / inductance], [coupling / capacitance, -a]],
                         b_duty_per_s=[b_current, b_voltage], output=[0., 1.]),
        plant_dc_gain_v_per_duty=n0 / b,
        plant_poles_rad_s=_pairs(_roots(plant_den) * omega_scale),
        plant_zeros_rad_s=_pairs(_roots(plant_num) * omega_scale),
        closed_loop_poles_rad_s=_pairs(closed_poles), stability=stability,
        stability_scope="Internal poles of the uncancelled rational negative-feedback averaged model only",
        rational_model=dict(variable="x=s/omega_scale_rad_s", omega_scale_rad_s=omega_scale,
                            plant_numerator=plant_num.tolist(), plant_denominator=plant_den.tolist(),
                            loop_numerator=loop_num.tolist(), loop_denominator=loop_den.tolist(),
                            closed_loop_denominator=closed_den.tolist()),
        margins=margins, warnings=warnings, limitations=list(LIMITATIONS))
    # Reject every nonfinite derived value, rather than serializing invalid JSON.
    import json
    try:
        json.dumps(report, allow_nan=False)
    except ValueError as exc:
        raise ValueError("Derived values exceed the finite numerical envelope") from exc
    return report
