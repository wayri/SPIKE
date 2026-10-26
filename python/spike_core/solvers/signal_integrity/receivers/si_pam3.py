# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded three-level PAM analysis over an explicit sampled LTI channel.

The source alphabet, voltage mapping, sample clock, channel impulse response,
decision thresholds, and additive voltage noise are explicit inputs.  This is
an experimental numerical precheck, not a USB4 encoder, receiver, mask, FEC,
or compliance implementation.
"""

from __future__ import annotations

from hashlib import sha256
from math import ceil, floor, isfinite
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.special import ndtr


CONTRACT = "spike/si-pam3-eye/v1"
MAX_SYMBOLS = 16_384
MAX_SAMPLES_PER_UI = 256
MAX_WAVEFORM_SAMPLES = 1_048_576
MAX_CHANNEL_TAPS = 65_536
MAX_CHANNEL_L1_GAIN = 1.0e6
MIN_CLASS_OBSERVATIONS = 8
_MAX_ABS_LEVEL_V = 1.0e3
_MAX_NOISE_RMS_V = 1.0e3
_MAX_ABS_THRESHOLD_V = 1.0e9
_MAX_SEED = (1 << 64) - 1


class SiPam3Error(ValueError):
    """Raised when a PAM3 request is malformed or exceeds a hard bound."""


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise SiPam3Error(f"{name} must be an integer in [{minimum}, {maximum}].")
    result = int(value)
    if not minimum <= result <= maximum:
        raise SiPam3Error(f"{name} must be an integer in [{minimum}, {maximum}].")
    return result


def _finite(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise SiPam3Error(f"{name} must be finite and in [{minimum:g}, {maximum:g}].")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SiPam3Error(f"{name} must be finite and in [{minimum:g}, {maximum:g}].") from exc
    if not isfinite(result) or not minimum <= result <= maximum:
        raise SiPam3Error(f"{name} must be finite and in [{minimum:g}, {maximum:g}].")
    return result


def _label(value: Any, name: str) -> int | str:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise SiPam3Error(f"{name} must be an integer or string label (booleans are not labels).")
    return value


def ternary_test_symbols(count: int, *, seed: int = 1) -> np.ndarray:
    """Return a reproducible three-symbol engineering stimulus.

    NumPy's explicitly selected PCG64 generator is used so global RNG state is
    irrelevant.  The result is only a balanced-looking test stimulus; it is not
    a protocol scrambler, line code, training sequence, or USB4 symbol stream.
    """

    count = _integer(count, "count", 3, MAX_SYMBOLS)
    seed = _integer(seed, "seed", 0, _MAX_SEED)
    generator = np.random.Generator(np.random.PCG64(seed))
    result = generator.integers(0, 3, size=count, dtype=np.int8)
    # Guarantee that short admitted records exercise every level without
    # claiming a maximal-length or standards-defined ternary sequence.
    result[:3] = np.asarray([0, 1, 2], dtype=np.int8)
    return result


def _source(
    symbols: Sequence[int | str], symbol_to_level_v: Mapping[int | str, float]
) -> tuple[list[int | str], list[int | str], np.ndarray, np.ndarray]:
    if isinstance(symbols, (str, bytes)) or not hasattr(symbols, "__len__"):
        raise SiPam3Error("symbols must be a finite sequence of integer or string labels.")
    symbol_count = len(symbols)
    if not 64 <= symbol_count <= MAX_SYMBOLS:
        raise SiPam3Error(f"symbols must contain 64..{MAX_SYMBOLS} entries.")
    if not isinstance(symbol_to_level_v, Mapping) or len(symbol_to_level_v) != 3:
        raise SiPam3Error("symbol_to_level_v must map exactly three labels to voltage levels.")

    normalized_map: dict[int | str, float] = {}
    for raw_label, raw_level in symbol_to_level_v.items():
        label = _label(raw_label, "symbol_to_level_v key")
        if label in normalized_map:
            raise SiPam3Error("symbol_to_level_v labels must be distinct.")
        normalized_map[label] = _finite(
            raw_level, f"symbol_to_level_v[{label!r}]", -_MAX_ABS_LEVEL_V, _MAX_ABS_LEVEL_V
        )
    if len(set(normalized_map.values())) != 3:
        raise SiPam3Error("symbol_to_level_v voltage levels must be distinct.")

    labels = [_label(item, f"symbols[{index}]") for index, item in enumerate(symbols)]
    unknown = set(labels) - set(normalized_map)
    if unknown:
        raise SiPam3Error(f"symbols contain labels absent from symbol_to_level_v: {sorted(unknown, key=str)!r}.")
    unused = set(normalized_map) - set(labels)
    if unused:
        raise SiPam3Error(f"symbols must exercise all three mapped labels; unused: {sorted(unused, key=str)!r}.")

    ordered = sorted(normalized_map, key=normalized_map.__getitem__)
    levels = np.asarray([normalized_map[item] for item in ordered], dtype=float)
    span = float(levels[-1] - levels[0])
    if span < 1.0e-15:
        raise SiPam3Error("symbol_to_level_v total voltage span must be at least 1e-15 V.")
    rank = {item: index for index, item in enumerate(ordered)}
    ranks = np.fromiter((rank[item] for item in labels), dtype=np.int8, count=symbol_count)
    waveform_levels = levels[ranks]
    return labels, ordered, levels, waveform_levels


def _channel(channel_impulse: Sequence[float]) -> np.ndarray:
    if isinstance(channel_impulse, (str, bytes)) or not hasattr(channel_impulse, "__len__"):
        raise SiPam3Error("channel_impulse must be a finite sequence of real dimensionless taps.")
    if not 1 <= len(channel_impulse) <= MAX_CHANNEL_TAPS:
        raise SiPam3Error(f"channel_impulse must contain 1..{MAX_CHANNEL_TAPS} taps.")
    try:
        raw_impulse = np.asarray(channel_impulse)
    except (TypeError, ValueError) as exc:
        raise SiPam3Error("channel_impulse must contain finite real taps.") from exc
    if np.iscomplexobj(raw_impulse):
        raise SiPam3Error("channel_impulse must contain real taps, not complex values.")
    try:
        impulse = np.asarray(raw_impulse, dtype=float)
    except (TypeError, ValueError) as exc:
        raise SiPam3Error("channel_impulse must contain finite real taps.") from exc
    if impulse.ndim != 1 or not np.all(np.isfinite(impulse)):
        raise SiPam3Error("channel_impulse must contain finite real taps.")
    l1_gain = float(np.sum(np.abs(impulse), dtype=float))
    if l1_gain == 0.0:
        raise SiPam3Error("channel_impulse must not be all zero.")
    if not isfinite(l1_gain) or l1_gain > MAX_CHANNEL_L1_GAIN:
        raise SiPam3Error(f"channel_impulse L1 gain must not exceed {MAX_CHANNEL_L1_GAIN:g}.")
    return impulse


def _thresholds(
    supplied: Sequence[float] | None, class_means: np.ndarray
) -> tuple[np.ndarray, str]:
    if supplied is None:
        if not np.all(np.diff(class_means) > 0.0):
            raise SiPam3Error(
                "Observed noiseless level means are not strictly increasing; "
                "this threshold receiver cannot infer an inverted or collapsed mapping."
            )
        return 0.5 * (class_means[:-1] + class_means[1:]), "training_mean_midpoints"
    if isinstance(supplied, (str, bytes)) or not hasattr(supplied, "__len__") or len(supplied) != 2:
        raise SiPam3Error("decision_thresholds_v must contain exactly two increasing voltages.")
    raw_values = np.asarray(supplied)
    if np.iscomplexobj(raw_values):
        raise SiPam3Error("decision_thresholds_v must contain real voltages, not complex values.")
    try:
        values = np.asarray(raw_values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise SiPam3Error("decision_thresholds_v must contain finite real voltages.") from exc
    if (
        values.ndim != 1
        or not np.all(np.isfinite(values))
        or np.any(np.abs(values) > _MAX_ABS_THRESHOLD_V)
        or not values[0] < values[1]
    ):
        raise SiPam3Error(
            f"decision_thresholds_v must contain two increasing finite values within +/-{_MAX_ABS_THRESHOLD_V:g} V."
        )
    return values, "explicit"


def _expected_gaussian_ser(
    noiseless: np.ndarray, true_ranks: np.ndarray, thresholds: np.ndarray, sigma_v: float
) -> float:
    predicted_without_noise = np.searchsorted(thresholds, noiseless, side="right")
    if sigma_v == 0.0:
        return float(np.mean(predicted_without_noise != true_ranks))
    below_lower = ndtr((thresholds[0] - noiseless) / sigma_v)
    above_lower = ndtr((noiseless - thresholds[0]) / sigma_v)
    below_upper = ndtr((thresholds[1] - noiseless) / sigma_v)
    above_upper = ndtr((noiseless - thresholds[1]) / sigma_v)
    errors = np.empty(len(noiseless), dtype=float)
    # Evaluate Gaussian survival probabilities as Phi(-z), never as
    # 1-Phi(z), so rare positive tails do not disappear by cancellation.
    errors[true_ranks == 0] = above_lower[true_ranks == 0]
    errors[true_ranks == 1] = (
        below_lower[true_ranks == 1] + above_upper[true_ranks == 1]
    )
    errors[true_ranks == 2] = below_upper[true_ranks == 2]
    return float(np.mean(errors))


def pam3_eye(
    symbols: Sequence[int | str],
    *,
    symbol_to_level_v: Mapping[int | str, float],
    channel_impulse: Sequence[float],
    symbol_rate_hz: float,
    samples_per_ui: int,
    sampling_phase_ui: float = 0.5,
    channel_cursor_samples: int | None = None,
    decision_thresholds_v: Sequence[float] | None = None,
    voltage_noise_rms_v: float = 0.0,
    noise_seed: int = 0,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Analyze two PAM3 eyes and hard-decision symbol errors.

    ``channel_impulse`` is a causal discrete-time voltage transfer: each tap is
    dimensionless, sampled at ``1 / (symbol_rate_hz * samples_per_ui)``.  The
    source uses a rectangular zero-order-hold pulse.  Additive noise is iid,
    zero-mean Gaussian voltage noise applied only at retained decision samples.
    """

    if cancel_check is not None and not callable(cancel_check):
        raise SiPam3Error("cancel_check must be callable when supplied.")
    _, ordered_labels, levels_v, source_levels_v = _source(symbols, symbol_to_level_v)
    impulse = _channel(channel_impulse)
    rate_hz = _finite(symbol_rate_hz, "symbol_rate_hz", 1.0, 1.0e12)
    samples_per_ui = _integer(samples_per_ui, "samples_per_ui", 8, MAX_SAMPLES_PER_UI)
    phase_ui = _finite(sampling_phase_ui, "sampling_phase_ui", 0.0, 1.0)
    if phase_ui == 1.0:
        raise SiPam3Error("sampling_phase_ui must be in [0, 1).")
    noise_rms_v = _finite(
        voltage_noise_rms_v, "voltage_noise_rms_v", 0.0, _MAX_NOISE_RMS_V
    )
    noise_seed = _integer(noise_seed, "noise_seed", 0, _MAX_SEED)

    waveform_samples = len(source_levels_v) * samples_per_ui
    if waveform_samples > MAX_WAVEFORM_SAMPLES:
        raise SiPam3Error(
            f"The PAM3 waveform needs {waveform_samples} samples; "
            f"the hard limit is {MAX_WAVEFORM_SAMPLES}."
        )
    cursor = int(np.argmax(np.abs(impulse))) if channel_cursor_samples is None else _integer(
        channel_cursor_samples, "channel_cursor_samples", 0, len(impulse) - 1
    )
    output_size = waveform_samples + len(impulse) - 1
    fft_points = 1 << (output_size - 1).bit_length()
    # Match the existing SI FFT convolution hard limit before allocation.
    if fft_points > 2_097_152:
        raise SiPam3Error(
            f"The PAM3 convolution needs {fft_points} FFT points; the hard limit is 2097152."
        )
    if cancel_check is not None and cancel_check():
        raise SiPam3Error("PAM3 analysis was cancelled before waveform allocation.")

    waveform_v = np.repeat(source_levels_v, samples_per_ui)
    from ..channels.si_channel import _fft_convolve_prefix

    response_v = _fft_convolve_prefix(waveform_v, impulse)
    if cancel_check is not None and cancel_check():
        raise SiPam3Error("PAM3 analysis was cancelled after channel convolution.")

    phase_samples = phase_ui * samples_per_ui
    sample_offset = cursor + phase_samples
    # Discard both the implicit zero-history transient and output positions that
    # would depend on the source record's zero-padded future.  The finite-record
    # decision population therefore has complete declared FIR support.
    first_symbol = max(0, int(ceil((len(impulse) - 1 - sample_offset) / samples_per_ui)))
    last_symbol = min(
        len(source_levels_v) - 1,
        int(floor((waveform_samples - 1 - sample_offset) / samples_per_ui)),
    )
    if last_symbol < first_symbol:
        raise SiPam3Error("No decision samples remain after the channel support bounds.")
    retained = np.arange(first_symbol, last_symbol + 1, dtype=int)
    positions = retained.astype(float) * samples_per_ui + sample_offset
    noiseless_v = np.interp(positions, np.arange(len(response_v), dtype=float), response_v)
    true_ranks = np.searchsorted(levels_v, source_levels_v[retained]).astype(np.int8)
    masks = [true_ranks == rank for rank in range(3)]
    counts = [int(np.count_nonzero(mask)) for mask in masks]
    if any(count < MIN_CLASS_OBSERVATIONS for count in counts):
        raise SiPam3Error(
            f"Each PAM3 level needs at least {MIN_CLASS_OBSERVATIONS} retained observations; got {counts}."
        )

    class_means = np.asarray([float(np.mean(noiseless_v[mask])) for mask in masks])
    thresholds_v, threshold_mode = _thresholds(decision_thresholds_v, class_means)
    generator = np.random.Generator(np.random.PCG64(noise_seed))
    noise_v = generator.normal(0.0, noise_rms_v, size=len(noiseless_v)) if noise_rms_v else np.zeros(len(noiseless_v))
    observed_v = noiseless_v + noise_v
    predicted_ranks = np.searchsorted(thresholds_v, observed_v, side="right").astype(np.int8)
    errors = predicted_ranks != true_ranks
    confusion = np.zeros((3, 3), dtype=np.int64)
    np.add.at(confusion, (true_ranks, predicted_ranks), 1)

    eyes: list[dict[str, Any]] = []
    for index in range(2):
        lower = noiseless_v[masks[index]]
        upper = noiseless_v[masks[index + 1]]
        lower_boundary = float(np.max(lower))
        upper_boundary = float(np.min(upper))
        threshold = float(thresholds_v[index])
        eyes.append({
            "lower_symbol": ordered_labels[index],
            "upper_symbol": ordered_labels[index + 1],
            "lower_max_v": lower_boundary,
            "upper_min_v": upper_boundary,
            "height_v": upper_boundary - lower_boundary,
            "threshold_v": threshold,
            "threshold_margin_v": min(threshold - lower_boundary, upper_boundary - threshold),
            "closed": bool(upper_boundary <= lower_boundary),
        })

    class_statistics = []
    for rank, mask in enumerate(masks):
        class_statistics.append({
            "symbol": ordered_labels[rank],
            "source_level_v": float(levels_v[rank]),
            "observation_count": counts[rank],
            "noiseless_mean_v": float(np.mean(noiseless_v[mask])),
            "noiseless_std_v": float(np.std(noiseless_v[mask])),
            "observed_mean_v": float(np.mean(observed_v[mask])),
            "observed_std_v": float(np.std(observed_v[mask])),
        })

    observed_errors = int(np.count_nonzero(errors))
    expected_ser = _expected_gaussian_ser(noiseless_v, true_ranks, thresholds_v, noise_rms_v)
    digest = sha256(np.asarray(observed_v, dtype="<f8").tobytes()).hexdigest()
    preview_count = min(32, len(observed_v))
    return {
        "contract": CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "source": {
            "modulation": "PAM3",
            "pulse": "rectangular_zero_order_hold",
            "symbol_count": len(source_levels_v),
            "mapping": [
                {"symbol": label, "level_v": float(level)}
                for label, level in zip(ordered_labels, levels_v)
            ],
            "protocol_encoding": None,
        },
        "sampling": {
            "symbol_rate_hz": rate_hz,
            "unit_interval_s": 1.0 / rate_hz,
            "samples_per_ui": samples_per_ui,
            "sample_interval_s": 1.0 / (rate_hz * samples_per_ui),
            "sampling_phase_ui": phase_ui,
            "channel_cursor_samples": cursor,
            "first_retained_symbol": first_symbol,
            "last_retained_symbol": last_symbol,
            "retained_symbol_count": len(retained),
        },
        "channel": {
            "model": "causal_sampled_lti_fir",
            "tap_unit": "dimensionless_voltage_transfer",
            "tap_count": len(impulse),
            "l1_gain": float(np.sum(np.abs(impulse), dtype=float)),
        },
        "receiver": {
            "kind": "memoryless_two_threshold",
            "threshold_mode": threshold_mode,
            "thresholds_v": thresholds_v.tolist(),
            "decision_regions": ["[-inf,t0)", "[t0,t1)", "[t1,+inf)"],
            "clock_recovery": None,
        },
        "eyes": eyes,
        "class_statistics": class_statistics,
        "errors": {
            "observed_symbol_errors": observed_errors,
            "observed_symbol_count": len(retained),
            "observed_symbol_error_rate": observed_errors / len(retained),
            "expected_symbol_error_rate_gaussian": expected_ser,
            "confusion_matrix": confusion.tolist(),
            "row_and_column_symbol_order": ordered_labels,
        },
        "noise": {
            "distribution": "iid_zero_mean_gaussian_at_decision_samples",
            "rms_v": noise_rms_v,
            "seed": noise_seed,
            "generator": "numpy.PCG64",
            "observed_sample_sha256_float64_le": digest,
            "observed_sample_preview_v": observed_v[:preview_count].tolist(),
            "preview_truncated": bool(preview_count < len(observed_v)),
        },
        "resource_admission": {
            "waveform_samples": waveform_samples,
            "channel_taps": len(impulse),
            "fft_points": fft_points,
            "retained_decisions": len(retained),
            "full_fir_support_at_every_decision": True,
            "cooperative_cancellation_supported": True,
        },
        "limitations": [
            "arbitrary three-label voltage mapping; no NRZ or PAM4 fallback is used",
            "the optional ternary_test_symbols helper is not a USB4 encoder, scrambler, or training sequence",
            "rectangular source pulses and an explicitly supplied causal sampled LTI FIR channel only",
            "fixed sampling phase and memoryless thresholds; no CDR, equalizer, DFE, jitter, or receiver nonlinearity",
            "the Gaussian expected SER is conditional on this finite deterministic symbol record and supplied RMS noise",
            "the observed SER is one seeded finite noise realization, not rare-event, FEC, measurement, or compliance evidence",
        ],
    }


__all__ = [
    "CONTRACT",
    "MAX_CHANNEL_TAPS",
    "MAX_SAMPLES_PER_UI",
    "MAX_SYMBOLS",
    "MAX_WAVEFORM_SAMPLES",
    "SiPam3Error",
    "pam3_eye",
    "ternary_test_symbols",
]
