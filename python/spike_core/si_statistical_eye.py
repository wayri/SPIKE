"""Bounded statistical NRZ sampling over a geometry-derived LTI channel.

The channel response and deterministic ISI come from the retained network.
Receiver voltage noise and sampling jitter are explicit user inputs; they are
never inferred from PCB geometry.  Gaussian random jitter is integrated with
Gauss-Hermite quadrature and bounded deterministic jitter with Gauss-Legendre
quadrature, so the result is reproducible and does not depend on Monte Carlo
seed length.
"""

from __future__ import annotations

from math import isfinite, pi, sqrt
from typing import Any, Callable, Mapping

import numpy as np
from scipy.special import ndtr

from .sparameters import NetworkData


CONTRACT = "spike/si-statistical-nrz-eye/v1"
MAX_PHASE_BINS = 129
MAX_QUADRATURE_ORDER = 15


class SiStatisticalEyeError(ValueError):
    """Raised when a statistical-eye request exceeds its stated model."""


def _finite_nonnegative(model: Mapping[str, Any], key: str, *, maximum: float) -> float:
    value = float(model.get(key, 0.0))
    if not isfinite(value) or value < 0.0 or value > maximum:
        raise SiStatisticalEyeError(f"{key} must be finite and in [0, {maximum:g}].")
    return value


def _quadrature_offsets(random_rms_s: float, deterministic_pp_s: float) -> tuple[np.ndarray, np.ndarray]:
    random_order = 9 if random_rms_s > 0.0 else 1
    deterministic_order = 7 if deterministic_pp_s > 0.0 else 1
    if random_order > MAX_QUADRATURE_ORDER or deterministic_order > MAX_QUADRATURE_ORDER:
        raise SiStatisticalEyeError("The requested jitter quadrature exceeds the hard order limit.")
    if random_order == 1:
        random_offsets = np.asarray([0.0])
        random_weights = np.asarray([1.0])
    else:
        nodes, weights = np.polynomial.hermite.hermgauss(random_order)
        random_offsets = sqrt(2.0) * random_rms_s * nodes
        random_weights = weights / sqrt(pi)
    if deterministic_order == 1:
        deterministic_offsets = np.asarray([0.0])
        deterministic_weights = np.asarray([1.0])
    else:
        nodes, weights = np.polynomial.legendre.leggauss(deterministic_order)
        deterministic_offsets = 0.5 * deterministic_pp_s * nodes
        deterministic_weights = 0.5 * weights
    offsets = (random_offsets[:, None] + deterministic_offsets[None, :]).reshape(-1)
    combined_weights = (random_weights[:, None] * deterministic_weights[None, :]).reshape(-1)
    return offsets, combined_weights


def _error_probability(voltage: np.ndarray, high: np.ndarray, threshold: float, sigma: float) -> np.ndarray:
    if sigma == 0.0:
        return np.where(high, voltage <= threshold, voltage >= threshold).astype(float)
    high_error = ndtr((threshold - voltage) / sigma)
    low_error = ndtr((voltage - threshold) / sigma)
    return np.where(high, high_error, low_error)


def statistical_nrz_eye(
    network: NetworkData,
    *,
    bit_rate_hz: float,
    model: Mapping[str, Any],
    bit_count: int = 1024,
    source_port: int = 0,
    sink_port: int = 1,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Return a deterministic BER-vs-phase estimate for an explicit model."""

    # Import implementation primitives lazily to avoid a module cycle.
    from .si_channel import (
        MAX_EYE_BITS,
        MAX_EYE_WAVEFORM_SAMPLES,
        SiChannelError,
        _fft_convolve_prefix,
        _frequency_grid,
        _prbs7,
        _real_impulse,
    )

    if not isinstance(model, Mapping):
        raise SiStatisticalEyeError("statistical_eye_model must be an object.")
    allowed = {
        "voltage_noise_rms_normalized", "random_jitter_rms_s",
        "deterministic_jitter_pp_s", "decision_threshold_normalized",
        "phase_bins", "target_ber",
    }
    unknown = set(model) - allowed
    if unknown:
        raise SiStatisticalEyeError(f"statistical_eye_model has unknown fields: {sorted(unknown)}.")
    if not isfinite(bit_rate_hz) or bit_rate_hz <= 0.0:
        raise SiStatisticalEyeError("bit_rate_hz must be positive and finite.")
    if not 128 <= bit_count <= MAX_EYE_BITS:
        raise SiStatisticalEyeError(f"bit_count must be 128..{MAX_EYE_BITS}.")
    if not (0 <= source_port < network.port_count and 0 <= sink_port < network.port_count):
        raise SiStatisticalEyeError("Statistical-eye source/sink port indices are outside the network.")

    unit_interval_s = 1.0 / bit_rate_hz
    voltage_noise = _finite_nonnegative(model, "voltage_noise_rms_normalized", maximum=10.0)
    random_jitter = _finite_nonnegative(model, "random_jitter_rms_s", maximum=0.25 * unit_interval_s)
    deterministic_jitter = _finite_nonnegative(model, "deterministic_jitter_pp_s", maximum=unit_interval_s)
    threshold = float(model.get("decision_threshold_normalized", 0.0))
    target_ber = float(model.get("target_ber", 1e-12))
    phase_bins = int(model.get("phase_bins", 65))
    if not isfinite(threshold) or abs(threshold) > 10.0:
        raise SiStatisticalEyeError("decision_threshold_normalized must be finite and within +/-10.")
    if not isfinite(target_ber) or not 0.0 < target_ber < 0.5:
        raise SiStatisticalEyeError("target_ber must be finite and in (0, 0.5).")
    if phase_bins < 17 or phase_bins > MAX_PHASE_BINS or phase_bins % 2 == 0:
        raise SiStatisticalEyeError(f"phase_bins must be an odd integer from 17 through {MAX_PHASE_BINS}.")

    frequencies = _frequency_grid(network.frequencies_hz)
    impulse = _real_impulse(network.s_parameters()[:, sink_port, source_port])
    delta_t = 1.0 / ((2 * len(frequencies) - 1) * float(frequencies[1] - frequencies[0]))
    samples_per_ui = int(round(unit_interval_s / delta_t))
    if samples_per_ui < 8:
        raise SiStatisticalEyeError("The frequency grid provides fewer than eight samples per UI.")
    represented_rate = 1.0 / (samples_per_ui * delta_t)
    if abs(represented_rate / bit_rate_hz - 1.0) > 0.01:
        raise SiStatisticalEyeError("The frequency grid cannot represent the requested bit rate within one percent.")

    waveform_samples = bit_count * samples_per_ui
    if waveform_samples > MAX_EYE_WAVEFORM_SAMPLES:
        raise SiStatisticalEyeError(
            f"The statistical-eye waveform needs {waveform_samples} samples; "
            f"the hard limit is {MAX_EYE_WAVEFORM_SAMPLES}."
        )
    if cancel_check is not None and cancel_check():
        raise SiChannelError("SI statistical-eye analysis was cancelled.")
    bits = _prbs7(bit_count)
    waveform = np.repeat(bits.astype(float) - 0.5, samples_per_ui)
    response = _fft_convolve_prefix(waveform, impulse)
    delay_samples = int(np.argmax(np.abs(impulse)))
    start_bit = 16
    retained = np.arange(start_bit, bit_count - 2, dtype=int)
    high = bits[retained].astype(bool)
    offsets_s, weights = _quadrature_offsets(random_jitter, deterministic_jitter)
    sample_axis = np.arange(len(response), dtype=float)
    phases = np.linspace(0.0, 1.0, phase_bins)
    bathtub: list[dict[str, float]] = []
    for phase_index, phase in enumerate(phases):
        if cancel_check is not None and phase_index % 4 == 0 and cancel_check():
            raise SiChannelError("SI statistical-eye analysis was cancelled.")
        base = retained.astype(float) * samples_per_ui + delay_samples + phase * samples_per_ui
        probability = 0.0
        for offset_s, weight in zip(offsets_s, weights):
            shifted = base + offset_s / delta_t
            voltage = np.interp(shifted, sample_axis, response)
            probability += float(weight) * float(np.mean(_error_probability(voltage, high, threshold, voltage_noise)))
        bathtub.append({"phase_ui": float(phase), "estimated_ber": max(0.0, min(0.5, probability))})

    ber_values = np.asarray([point["estimated_ber"] for point in bathtub])
    best_index = int(np.argmin(ber_values))
    passing = ber_values <= target_ber
    left = best_index
    right = best_index
    if passing[best_index]:
        while left > 0 and passing[left - 1]:
            left -= 1
        while right + 1 < len(passing) and passing[right + 1]:
            right += 1
    eye_width_ui = float(phases[right] - phases[left]) if passing[best_index] else 0.0
    evaluations = int(len(phases) * len(retained) * len(offsets_s))
    return {
        "contract": CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "source_port_index": source_port,
        "sink_port_index": sink_port,
        "bit_rate_hz": float(bit_rate_hz),
        "represented_bit_rate_hz": represented_rate,
        "bit_count": bit_count,
        "samples_per_ui": samples_per_ui,
        "model": {
            "source": "ideal normalized NRZ",
            "voltage_noise_distribution": "zero-mean Gaussian",
            "voltage_noise_rms_normalized": voltage_noise,
            "random_jitter_distribution": "zero-mean Gaussian",
            "random_jitter_rms_s": random_jitter,
            "deterministic_jitter_distribution": "bounded uniform",
            "deterministic_jitter_pp_s": deterministic_jitter,
            "decision_threshold_normalized": threshold,
        },
        "integration": {
            "method": "deterministic Gaussian-Hermite x Gauss-Legendre quadrature",
            "jitter_quadrature_points": int(len(offsets_s)),
            "phase_bins": phase_bins,
            "evaluations": evaluations,
        },
        "best_sampling_phase_ui": float(phases[best_index]),
        "minimum_estimated_ber": float(ber_values[best_index]),
        "target_ber": target_ber,
        "eye_width_at_target_ber_ui": eye_width_ui,
        "bathtub": bathtub,
        "limitations": [
            "PRBS7 finite-pattern deterministic ISI over an LTI channel, not full random-bit statistical enumeration",
            "ideal normalized NRZ source; no IBIS/AMI transmitter or receiver, package, equalization, CDR, DFE, FEC, or nonlinearity",
            "noise and jitter are explicit user inputs and are not inferred from PCB geometry",
            "Gaussian random jitter and voltage noise plus bounded-uniform deterministic jitter only",
            "BER is a numerical model estimate, not measured evidence or protocol compliance",
        ],
    }


__all__ = ["CONTRACT", "MAX_PHASE_BINS", "SiStatisticalEyeError", "statistical_nrz_eye"]
