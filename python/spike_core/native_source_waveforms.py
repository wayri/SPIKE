# SPDX-License-Identifier: Apache-2.0
"""Point evaluation for validated native-MNA independent-source waveforms."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def source_value(element: dict[str, Any], time_s: float) -> float:
    """Evaluate one already-validated source at a nonnegative transient time."""

    waveform = element.get("waveform")
    if not isinstance(waveform, dict):
        return float(element.get("dc_value", element.get("value", 0.0)) or 0.0)
    kind = str(waveform.get("type", "constant")).lower()
    if kind == "constant":
        return float(waveform.get("value", element.get("dc_value", 0.0)) or 0.0)
    if kind == "step":
        initial = float(waveform.get("initial", 0.0))
        final = float(waveform.get("final", initial))
        delay = max(0.0, float(waveform.get("delay_s", 0.0)))
        rise = max(0.0, float(waveform.get("rise_time_s", 0.0)))
        if time_s < delay:
            return initial
        if rise and time_s < delay + rise:
            return initial + (final - initial) * (time_s - delay) / rise
        return final
    if kind == "pulse":
        low = float(waveform.get("low", 0.0))
        high = float(waveform.get("high", low))
        delay = max(0.0, float(waveform.get("delay_s", 0.0)))
        rise = max(0.0, float(waveform.get("rise_time_s", 0.0)))
        fall = max(0.0, float(waveform.get("fall_time_s", 0.0)))
        width = max(0.0, float(waveform.get("pulse_width_s", 0.0)))
        period = max(0.0, float(waveform.get("period_s", 0.0)))
        if time_s < delay:
            return low
        local = time_s - delay
        if period:
            local %= period
        if rise and local < rise:
            return low + (high - low) * local / rise
        if local < rise + width:
            return high
        if fall and local < rise + width + fall:
            return high + (low - high) * (local - rise - width) / fall
        return low
    if kind == "pwl":
        points = waveform.get("points", [])
        parsed = sorted(
            (float(item[0]), float(item[1]))
            for item in points
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
        if not parsed:
            return 0.0
        if time_s <= parsed[0][0]:
            return parsed[0][1]
        for (left_t, left_v), (right_t, right_v) in zip(parsed, parsed[1:]):
            if time_s <= right_t:
                ratio = (time_s - left_t) / max(right_t - left_t, np.finfo(float).eps)
                return left_v + ratio * (right_v - left_v)
        return parsed[-1][1]
    if kind == "sin":
        offset = float(waveform.get("offset", 0.0))
        amplitude = float(waveform.get("amplitude", 0.0))
        frequency = float(waveform.get("frequency_hz", 0.0))
        delay = float(waveform.get("delay_s", 0.0))
        damping = float(waveform.get("damping_per_s", 0.0))
        phase = math.radians(float(waveform.get("phase_deg", 0.0)))
        # Hold the phase-dependent time-zero value until the source delay.
        elapsed = max(0.0, time_s - delay)
        return offset + amplitude * math.exp(-damping * elapsed) * math.sin(
            2.0 * math.pi * frequency * elapsed + phase
        )
    if kind == "exp":
        initial = float(waveform.get("initial", 0.0))
        pulsed = float(waveform.get("pulsed", initial))
        rise_delay = float(waveform.get("rise_delay_s", 0.0))
        rise_tau = float(waveform.get("rise_time_constant_s", 0.0))
        fall_delay = float(waveform.get("fall_delay_s", rise_delay))
        fall_tau = float(waveform.get("fall_time_constant_s", 0.0))
        if time_s < rise_delay:
            return initial
        rise = (pulsed - initial) * -math.expm1(-(time_s - rise_delay) / rise_tau)
        if time_s < fall_delay:
            return initial + rise
        fall = (initial - pulsed) * -math.expm1(-(time_s - fall_delay) / fall_tau)
        return initial + rise + fall
    if kind == "sffm":
        delay = float(waveform.get("delay_s", 0.0))
        if time_s <= delay:
            return 0.0
        elapsed = time_s - delay
        modulation_phase = (
            2.0 * math.pi * float(waveform.get("modulating_frequency_hz", 0.0)) * elapsed
            + math.radians(float(waveform.get("modulating_phase_deg", 0.0)))
        )
        carrier_phase = (
            2.0 * math.pi * float(waveform.get("carrier_frequency_hz", 0.0)) * elapsed
            + float(waveform.get("modulation_index", 0.0)) * math.sin(modulation_phase)
            + math.radians(float(waveform.get("carrier_phase_deg", 0.0)))
        )
        return float(waveform.get("offset", 0.0)) + float(waveform.get("amplitude", 0.0)) * math.sin(carrier_phase)
    raise ValueError(f"Unsupported source waveform: {kind}")


__all__ = ["source_value"]
