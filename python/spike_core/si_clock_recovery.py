# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Bounded, finite-record NRZ threshold-transition PI timing recovery.

This behavioral clock is approximate; updates are not a lock detector. See
docs/SI_CLOCK_RECOVERY.md for independently derived equations and limitations.
"""
from collections.abc import Mapping
from numbers import Real
from typing import TypedDict

import numpy as np


MAX_INPUT_SAMPLES = 1_048_576
MAX_SYMBOLS = 65_536


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"cdr {name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"cdr {name} must be a finite number") from exc
    if not np.isfinite(result):
        raise ValueError(f"cdr {name} must be a finite number")
    return result


class CdrModel(TypedDict):
    kind: str
    threshold_v: float
    normalization_v: float
    initial_phase_ui: float
    proportional_gain: float
    integral_gain: float
    max_frequency_offset_ppm: float
    max_symbols: int


def validate_cdr_model(model) -> CdrModel:
    """Normalize explicit behavioral loop options; reject unknown keys."""
    defaults = dict(kind="transition_pi", threshold_v=0.5, normalization_v=1.0,
                    initial_phase_ui=0.0, proportional_gain=0.2,
                    integral_gain=0.002, max_frequency_offset_ppm=10000.0,
                    max_symbols=MAX_SYMBOLS)
    if not isinstance(model, Mapping):
        raise ValueError("cdr model must be an object")
    if set(model) - set(defaults):
        raise ValueError("cdr model has unknown options")
    options = defaults | dict(model)
    if options["kind"] != "transition_pi":
        raise ValueError("cdr kind must be transition_pi")
    for key in defaults.keys() - {"kind", "max_symbols"}:
        options[key] = _finite_number(options[key], key)
    count = options["max_symbols"]
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or not 1 <= count <= MAX_SYMBOLS:
        raise ValueError(f"cdr max_symbols must be an integer in [1, {MAX_SYMBOLS}]")
    options["max_symbols"] = int(count)
    if not 1e-12 <= options["normalization_v"] <= 1e12:
        raise ValueError("cdr normalization_v must be in [1e-12, 1e12] V")
    if not 0 <= options["initial_phase_ui"] < 1:
        raise ValueError("cdr initial_phase_ui must be in [0, 1)")
    if not 0 < options["proportional_gain"] <= 0.5:
        raise ValueError("cdr proportional_gain must be in (0, 0.5]")
    if not 0 < options["integral_gain"] <= options["proportional_gain"] / 4:
        raise ValueError("cdr integral_gain must be positive and <= proportional_gain/4")
    if not 0 < options["max_frequency_offset_ppm"] <= 100000:
        raise ValueError("cdr max_frequency_offset_ppm must be in (0, 100000]")
    return options


def recover_nrz_clock(times, voltage, nominal_rate_hz, model):
    """Return bounded center samples and transition-error history, without BER.

    Input must be full-resolution real 1-D arrays, at least 4 samples/nominal UI
    at every gap. Time is seconds, voltage volts, rate symbols/second. Boundary
    phase is relative to times[0]; samples are one half recovered period later.
    """
    options = validate_cdr_model(model)
    nominal_rate_hz = _finite_number(nominal_rate_hz, "nominal_rate_hz")
    if not 1e-6 <= nominal_rate_hz <= 1e15:
        raise ValueError("cdr nominal_rate_hz must be finite in [1e-6, 1e15]")
    arrays = []
    for name, value in (("times", times), ("voltage", voltage)):
        array = np.asarray(value)
        if array.ndim != 1 or not 4 <= array.size <= MAX_INPUT_SAMPLES:
            raise ValueError(f"cdr {name} must contain 4..{MAX_INPUT_SAMPLES} scalar samples")
        if array.dtype.kind not in "fiu" or not np.all(np.isfinite(array)):
            raise ValueError(f"cdr {name} must contain finite real numbers")
        arrays.append(array.astype(float, copy=False))
    t, v = arrays
    if t.size != v.size:
        raise ValueError("cdr times and voltage must have equal lengths")
    nominal_period = 1.0 / float(nominal_rate_hz)
    with np.errstate(over="ignore", invalid="ignore"):
        gaps = np.diff(t)
    if (not np.all(np.isfinite(gaps)) or not np.all(gaps > 0)
            or np.max(gaps) > nominal_period * (0.25 + 1e-10)):
        raise ValueError("cdr time must strictly increase with at least four samples/UI")
    # Relative UI coordinates avoid repeatedly adding sub-nanosecond periods to
    # potentially much larger acquisition timestamps.
    x = (t - t[0]) / nominal_period
    if not np.all(np.isfinite(x)):
        raise ValueError("cdr time range overflows normalized coordinates")
    bound = options["max_frequency_offset_ppm"] * 1e-6
    min_period, max_period = 1 / (1 + bound), 1 / (1 - bound)
    if x[-1] > (options["max_symbols"] + 1) * max_period:
        raise ValueError("cdr record exceeds max_symbols resource budget")
    with np.errstate(over="ignore", invalid="ignore"):
        u = (v - options["threshold_v"]) / options["normalization_v"]
    if not np.all(np.isfinite(u)):
        raise ValueError("cdr voltage normalization overflow")
    # >= assigns an exact threshold sample to the upper half-plane, preventing
    # duplicate detections on an otherwise monotone sampled edge.
    indices = np.flatnonzero((u[:-1] >= 0) != (u[1:] >= 0))
    a, b = np.abs(u[indices]), np.abs(u[indices + 1])
    scale = np.maximum(a, b)
    fraction = (a / scale) / (a / scale + b / scale)
    crossings = x[indices] + fraction * (x[indices + 1] - x[indices])
    boundary, period = options["initial_phase_ui"], 1.0
    centers, periods, errors, accepted = [], [], [], []
    ambiguous = saturated = 0
    next_crossing = 0
    while boundary + 0.5 * min_period <= x[-1]:
        left = max(next_crossing, int(np.searchsorted(crossings, boundary - 0.45 * period)))
        right = int(np.searchsorted(crossings, boundary + 0.45 * period, side="right"))
        if right - left == 1:
            error = float(crossings[left] - boundary)
            proposed = period + options["integral_gain"] * error
            period = float(np.clip(proposed, min_period, max_period))
            saturated += int(proposed != period)
            boundary += options["proportional_gain"] * error
            errors.append(error)
            accepted.append(float(crossings[left]))
        elif right - left > 1:
            ambiguous += 1
        next_crossing = max(next_crossing, right)
        center = boundary + 0.5 * period
        if center > x[-1]:
            break
        if center >= 0:
            if len(centers) >= options["max_symbols"]:
                raise ValueError("cdr recovered clock exceeds max_symbols resource budget")
            centers.append(center)
            periods.append(period)
        boundary += period
    sample_x = np.asarray(centers)
    recovered_periods = np.asarray(periods) * nominal_period
    diagnostics = ["Behavioral transition PI clock; tracking does not establish lock, BER or compliance."]
    if not accepted:
        diagnostics.append("No usable transitions: clock free-ran at its initial nominal rate and phase.")
    if ambiguous:
        diagnostics.append("Multiple crossings in timing gate were skipped; ringing/noise may invalidate timing.")
    if saturated:
        diagnostics.append("Frequency integrator reached its configured bound; acquisition is not established.")
    return {
        "model": options, "model_status": "approximate",
        "status": "tracking" if len(accepted) >= 8 else "insufficient_transitions",
        "sample_times_s": sample_x * nominal_period + t[0],
        "sample_values_v": np.interp(sample_x, x, v),
        "period_s": recovered_periods,
        "frequency_offset_ppm": (nominal_period / recovered_periods - 1) * 1e6,
        "phase_error_ui": np.asarray(errors),
        "transition_times_s": np.asarray(accepted) * nominal_period + t[0],
        "detected_transition_count": int(crossings.size),
        "accepted_transition_count": len(accepted),
        "ambiguous_gate_count": ambiguous, "frequency_bound_hit_count": saturated,
        "diagnostics": diagnostics,
    }
