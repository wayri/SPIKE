"""Bounded PAM4 eye analysis over an explicit linear channel.

This is an independently implemented engineering precheck.  It uses explicit
FFE, CTLE, DFE, noise, and phase-search controls; it does not infer transmitter,
receiver, package, jitter, or protocol limits from board geometry.
"""

from __future__ import annotations

from math import erfc, isfinite, sqrt
from typing import Any, Callable, Mapping

import numpy as np

from .sparameters import NetworkData


CONTRACT = "spike/si-pam4-eye/v1"
MAX_SYMBOLS = 4096
MAX_PHASE_BINS = 129
MAX_FFE_TAPS = 9
MAX_DFE_TAPS = 8


class SiPam4EyeError(ValueError):
    """Raised when a PAM4 request exceeds the bounded model."""


def _finite(value: Any, name: str, minimum: float, maximum: float) -> float:
    number = float(value)
    if not isfinite(number) or not minimum <= number <= maximum:
        raise SiPam4EyeError(f"{name} must be finite and in [{minimum:g}, {maximum:g}].")
    return number


def _taps(model: Mapping[str, Any], key: str, limit: int, default: list[float]) -> np.ndarray:
    raw = model.get(key, default)
    if not isinstance(raw, list) or not 1 <= len(raw) <= limit:
        raise SiPam4EyeError(f"{key} must contain 1..{limit} finite taps.")
    taps = np.asarray(raw, dtype=float)
    if not np.all(np.isfinite(taps)):
        raise SiPam4EyeError(f"{key} must contain only finite taps.")
    return taps


def _pam4_symbols(count: int) -> np.ndarray:
    from .si_channel import _prbs7

    bits = _prbs7(2 * count).reshape((-1, 2))
    # Gray order: 00, 01, 11, 10.
    indices = bits[:, 0] * 2 + bits[:, 1]
    levels = np.asarray([-1.0, -1.0 / 3.0, 1.0, 1.0 / 3.0])
    return levels[indices]


def pam4_eye(
    network: NetworkData,
    *,
    symbol_rate_hz: float,
    model: Mapping[str, Any],
    symbol_count: int = 1024,
    source_port: int = 0,
    sink_port: int = 1,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Calculate three PAM4 eyes using explicit bounded equalizer controls."""

    from .si_channel import (
        MAX_EYE_WAVEFORM_SAMPLES,
        SiChannelError,
        _fft_convolve_prefix,
        _frequency_grid,
        _real_impulse,
    )

    if not isinstance(model, Mapping):
        raise SiPam4EyeError("pam4_model must be an object.")
    allowed = {
        "tx_ffe_taps", "rx_ctle_dc_gain", "rx_ctle_zero_hz", "rx_ctle_pole_hz",
        "rx_dfe_taps", "voltage_noise_rms_normalized", "phase_bins",
        "target_ber", "cdr_mode",
    }
    unknown = set(model) - allowed
    if unknown:
        raise SiPam4EyeError(f"pam4_model has unknown fields: {sorted(unknown)}.")
    symbol_rate = _finite(symbol_rate_hz, "symbol_rate_hz", 1.0, 1.0e12)
    if not 256 <= symbol_count <= MAX_SYMBOLS:
        raise SiPam4EyeError(f"symbol_count must be 256..{MAX_SYMBOLS}.")
    if not (0 <= source_port < network.port_count and 0 <= sink_port < network.port_count):
        raise SiPam4EyeError("PAM4 source/sink ports are outside the network.")
    phase_bins = int(model.get("phase_bins", 65))
    if phase_bins < 17 or phase_bins > MAX_PHASE_BINS or phase_bins % 2 == 0:
        raise SiPam4EyeError(f"phase_bins must be an odd integer from 17 through {MAX_PHASE_BINS}.")
    cdr_mode = str(model.get("cdr_mode", "ideal_phase_search"))
    if cdr_mode not in {"fixed_center", "ideal_phase_search"}:
        raise SiPam4EyeError("cdr_mode must be fixed_center or ideal_phase_search.")

    ffe = _taps(model, "tx_ffe_taps", MAX_FFE_TAPS, [1.0])
    dfe = _taps(model, "rx_dfe_taps", MAX_DFE_TAPS, [0.0])
    if np.sum(np.abs(ffe)) <= 0.0:
        raise SiPam4EyeError("tx_ffe_taps must not be all zero.")
    noise = _finite(model.get("voltage_noise_rms_normalized", 0.0), "voltage_noise_rms_normalized", 0.0, 10.0)
    target_ber = _finite(model.get("target_ber", 1e-12), "target_ber", 1e-18, 0.49)

    frequencies = _frequency_grid(network.frequencies_hz)
    transfer = network.s_parameters()[:, sink_port, source_port].copy()
    ctle_gain = _finite(model.get("rx_ctle_dc_gain", 1.0), "rx_ctle_dc_gain", 1e-6, 1e6)
    zero_hz = _finite(model.get("rx_ctle_zero_hz", 0.0), "rx_ctle_zero_hz", 0.0, 1e13)
    pole_hz = _finite(model.get("rx_ctle_pole_hz", 0.0), "rx_ctle_pole_hz", 0.0, 1e13)
    if (zero_hz == 0.0) != (pole_hz == 0.0) or (zero_hz and pole_hz <= zero_hz):
        raise SiPam4EyeError("CTLE requires zero_hz and pole_hz together with pole_hz greater than zero_hz.")
    if zero_hz:
        frequency = frequencies.astype(complex)
        transfer *= ctle_gain * (1.0 + 1j * frequency / zero_hz) / (1.0 + 1j * frequency / pole_hz)
    else:
        transfer *= ctle_gain
    impulse = _real_impulse(transfer)
    delta_t = 1.0 / ((2 * len(frequencies) - 1) * float(frequencies[1] - frequencies[0]))
    samples_per_ui = int(round((1.0 / symbol_rate) / delta_t))
    if samples_per_ui < 8:
        raise SiPam4EyeError("The frequency grid provides fewer than eight samples per PAM4 UI.")
    represented_rate = 1.0 / (samples_per_ui * delta_t)
    if abs(represented_rate / symbol_rate - 1.0) > 0.01:
        raise SiPam4EyeError("The frequency grid cannot represent the requested PAM4 symbol rate within one percent.")
    waveform_samples = symbol_count * samples_per_ui
    if waveform_samples > MAX_EYE_WAVEFORM_SAMPLES:
        raise SiPam4EyeError(
            f"The PAM4 waveform needs {waveform_samples} samples; the hard limit is {MAX_EYE_WAVEFORM_SAMPLES}."
        )
    if cancel_check is not None and cancel_check():
        raise SiChannelError("PAM4 eye analysis was cancelled.")

    symbols = _pam4_symbols(symbol_count)
    driven = np.convolve(symbols, ffe, mode="full")[:symbol_count]
    waveform = np.repeat(driven, samples_per_ui)
    response = _fft_convolve_prefix(waveform, impulse)
    delay = int(np.argmax(np.abs(impulse)))
    retained = np.arange(32 + len(ffe) + len(dfe), symbol_count - 2, dtype=int)
    phases = np.linspace(0.0, 1.0, phase_bins)
    if cdr_mode == "fixed_center":
        phases = np.asarray([0.5])
    # Interpolation is valid only inside the computed, finite convolution
    # record. np.interp otherwise extends its endpoint silently. Use the same
    # observed symbols at every phase so the phase search is comparable.
    retained = retained[
        retained * samples_per_ui + delay + float(np.max(phases)) * samples_per_ui
        <= len(response) - 1
    ]
    if len(retained) < 64:
        raise SiPam4EyeError(
            "Too few PAM4 symbols remain after equalizer settling and channel delay; "
            "increase symbol_count or provide a shorter-delay channel."
        )
    phase_metrics: list[dict[str, Any]] = []
    for phase_index, phase in enumerate(phases):
        if cancel_check is not None and phase_index % 4 == 0 and cancel_check():
            raise SiChannelError("PAM4 phase search was cancelled.")
        positions = retained * samples_per_ui + delay + phase * samples_per_ui
        samples = np.interp(positions, np.arange(len(response), dtype=float), response)
        # Explicit ideal-training DFE: prior transmitted symbols are known.  This
        # avoids silently claiming a decision-directed adaptive receiver.
        for tap_index, tap in enumerate(dfe, start=1):
            samples -= tap * symbols[retained - tap_index]
        groups = [samples[np.isclose(symbols[retained], level)] for level in (-1.0, -1.0 / 3.0, 1.0 / 3.0, 1.0)]
        if any(len(group) == 0 for group in groups):
            raise SiPam4EyeError("The retained PAM4 pattern did not exercise all four levels.")
        means = [float(np.mean(group)) for group in groups]
        sigmas = [sqrt(float(np.var(group)) + noise * noise) for group in groups]
        openings = [means[index + 1] - means[index] for index in range(3)]
        q_values = [
            opening / max(sigmas[index] + sigmas[index + 1], 1e-30)
            for index, opening in enumerate(openings)
        ]
        ber = [0.5 * erfc(max(q, 0.0) / sqrt(2.0)) for q in q_values]
        phase_metrics.append({
            "phase_ui": float(phase),
            "level_means": means,
            "level_sigmas": sigmas,
            "eye_heights_normalized": openings,
            "ber_proxies": ber,
            "worst_eye_height_normalized": min(openings),
            "worst_ber_proxy": max(ber),
        })
    best = max(phase_metrics, key=lambda item: (item["worst_eye_height_normalized"], -item["worst_ber_proxy"]))
    return {
        "contract": CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "symbol_rate_hz": symbol_rate,
        "represented_symbol_rate_hz": represented_rate,
        "symbol_count": symbol_count,
        "samples_per_ui": samples_per_ui,
        "source_port_index": source_port,
        "sink_port_index": sink_port,
        "best_sampling_phase_ui": best["phase_ui"],
        "eye_heights_normalized": best["eye_heights_normalized"],
        "ber_proxies": best["ber_proxies"],
        "passes_user_target_proxy": bool(max(best["ber_proxies"]) <= target_ber),
        "target_ber": target_ber,
        "bathtub": phase_metrics,
        "equalization": {
            "tx_ffe_taps": ffe.tolist(),
            "rx_ctle_dc_gain": ctle_gain,
            "rx_ctle_zero_hz": zero_hz,
            "rx_ctle_pole_hz": pole_hz,
            "rx_dfe_taps": dfe.tolist(),
            "dfe_mode": "ideal_training_with_known_prior_symbols",
            "cdr_mode": cdr_mode,
        },
        "resource_admission": {
            "waveform_samples": waveform_samples,
            "observed_symbols_per_phase": len(retained),
            "channel_peak_delay_samples": delay,
            "response_extrapolation_used": False,
            "phase_evaluations": len(phase_metrics) * len(retained),
            "cooperative_cancellation_supported": True,
        },
        "limitations": [
            "ideal normalized Gray-coded PAM4 source over an LTI channel",
            "FFE, CTLE, DFE, voltage noise, and CDR mode are explicit user inputs; no IBIS-AMI model is inferred",
            "DFE uses known prior transmitted symbols and is optimistic compared with decision-directed error propagation",
            "BER values are Gaussian level-separation proxies, not rare-event simulation, measurement, or protocol compliance",
            "package, connector, launch, and receiver nonlinearity require explicit extracted network models",
        ],
    }


__all__ = ["CONTRACT", "SiPam4EyeError", "pam4_eye"]
