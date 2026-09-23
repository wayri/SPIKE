# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Single observable free-decay mode identification, not a general eigensolver.

Original AR(2) identification with independent reconstruction checks. The
complex-frequency definition Q=pi*f/alpha uses amplitude exp(-alpha*t), as
in https://github.com/NanoComp/harminv . No Harminv code is used here.
Input must be a real physical probe after the excitation is switched off.
Numerical checks cannot establish provenance, exclude invisible modes or prove
that a fitted decay is intrinsic rather than loaded/radiative loss.
"""
import hashlib
import math
import numpy as np


def _identify(t, y):
    y = y / np.max(np.abs(y))
    dt = float(np.mean(np.diff(t)))
    matrix = np.column_stack((y[1:-1], y[:-2]))
    condition = float(np.linalg.cond(matrix))
    if condition > 1e6:
        raise ValueError("ill_conditioned_recurrence")
    coefficient = np.linalg.lstsq(matrix, y[2:], rcond=None)[0]
    roots = np.roots([1., -coefficient[0], -coefficient[1]])
    root = roots[np.argmax(roots.imag)]
    if root.imag <= 0 or not 0 < abs(root) < 1:
        raise ValueError("no_resolved_decaying_oscillatory_pair")
    alpha = -math.log(abs(root)) / dt
    frequency = float(np.angle(root)) / (2 * math.pi * dt)
    tau = t - t[0]
    envelope = np.exp(-alpha * tau)
    basis = envelope[:, None] * np.column_stack((np.cos(2*np.pi*frequency*tau), np.sin(2*np.pi*frequency*tau)))
    predicted = basis @ np.linalg.lstsq(basis, y, rcond=None)[0]
    error = float(np.linalg.norm(predicted-y)/np.linalg.norm(y))
    return {"frequency_hz": frequency, "amplitude_decay_per_s": alpha,
            "q_factor": math.pi*frequency/alpha, "relative_reconstruction_error": error,
            "recurrence_condition": condition}


def qualify_ringdown(time_s, probe, *, source_off_time_s):
    """Bounded real uniform trace; thresholds are screening, not uncertainty bars."""
    if np.iscomplexobj(probe) or np.iscomplexobj(time_s):
        raise ValueError("Real probe and time arrays required")
    t, y = np.asarray(time_s, dtype=float), np.asarray(probe, dtype=float)
    if t.ndim != 1 or y.shape != t.shape or not 128 <= len(t) <= 262144:
        raise ValueError("Aligned 128..262144 sample vectors required")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)) or np.any(np.diff(t) <= 0):
        raise ValueError("Finite increasing times and finite probes required")
    if isinstance(source_off_time_s, bool) or not math.isfinite(source_off_time_s) or source_off_time_s > t[0]:
        raise ValueError("Entire observation must follow declared source switch-off")
    dt = float(np.mean(np.diff(t)))
    # Text probes commonly retain 12 significant digits; allow bounded output
    # quantization only (0.2 ppm), without changing the supplied sample times.
    if not np.allclose(np.diff(t), dt, rtol=2e-7, atol=0):
        raise ValueError("Uniform sampling required; no hidden resampling")
    result = {"contract": "spike/single-mode-ringdown/v1", "status": "not_qualified",
              "physical_eigenmode_qualified": False, "production_qualified": False,
              "source_off_time_s": float(source_off_time_s), "sample_count": len(t),
              "input_sha256": hashlib.sha256(t.astype('<f8').tobytes()+y.astype('<f8').tobytes()).hexdigest(),
              "reasons": [], "limitations": ["Single observable mode only; hidden modes are not excluded.",
                  "Q describes total observed decay, not separated intrinsic/external losses.",
                  "Source-off declaration and solver/probe provenance require external evidence."]}
    if np.max(np.abs(y)) == 0:
        result["reasons"] = ["zero_probe"]
        return result
    try:
        fit = _identify(t,y)
        checks = [_identify(t[:len(t)//2],y[:len(t)//2]),
                  _identify(t[len(t)//2:],y[len(t)//2:]), _identify(t[::2],y[::2])]
        result["candidate"] = fit
        result["stability_checks"] = checks
        duration = float(t[-1]-t[0])
        if fit["frequency_hz"]*duration < 8:
            result["reasons"].append("fewer_than_eight_observed_cycles")
        if fit["frequency_hz"]*dt > .05:
            result["reasons"].append("fewer_than_twenty_samples_per_cycle")
        if fit["amplitude_decay_per_s"]*duration < .1:
            result["reasons"].append("insufficient_observed_decay")
        if max(v["relative_reconstruction_error"] for v in [fit]+checks) > .01:
            result["reasons"].append("single_mode_reconstruction_failed")
        changes = {key: max(abs(v[key]/fit[key]-1) for v in checks)
                   for key in ("frequency_hz", "q_factor")}
        result["maximum_window_decimation_relative_changes"] = changes
        if changes["frequency_hz"] > .001 or changes["q_factor"] > .02:
            result["reasons"].append("window_or_decimation_instability")
        if not result["reasons"]:
            result["status"] = "qualified_observed_single_mode"
            result["mode"] = {key: fit[key] for key in ("frequency_hz", "q_factor", "amplitude_decay_per_s")}
    except (ValueError, np.linalg.LinAlgError) as exc:
        result["reasons"].append(str(exc))
    return result


def qualify_ringdown_convergence(reports, spatial_resolution_m):
    """Three distinct refinement observations; empirical stability, not validation."""
    h = np.asarray(spatial_resolution_m, dtype=float)
    if h.shape != (3,) or not np.all(np.isfinite(h)) or np.any(h <= 0) or np.any(np.diff(h) >= 0) or len(reports) != 3:
        raise ValueError("Three strictly decreasing positive mesh resolutions required")
    reasons = []
    if any(r.get("status") != "qualified_observed_single_mode" for r in reports):
        reasons.append("unqualified_observation")
    if len({r.get("input_sha256") for r in reports}) != 3:
        reasons.append("distinct_observations_required")
    changes = {}
    if not reasons:
        for key, tolerance in (("frequency_hz", .001), ("q_factor", .02)):
            values = [r["mode"][key] for r in reports]
            steps = [abs(values[i]/values[i+1]-1) for i in (0,1)]
            changes[key] = steps
            if steps[1] > tolerance or steps[1] > steps[0] + 1e-9:
                reasons.append(key+"_not_converged")
    return {"status": "numerically_stable_observed_mode" if not reasons else "not_qualified",
            "physical_eigenmode_qualified": False, "reasons": reasons, "relative_changes": changes,
            "spatial_resolution_m": h.tolist(),
            "limitations": ["Same mode identity, geometry, materials, boundaries and probe placement must be independently established.",
                            "Three-level stability does not validate the physical model or solver."]}
