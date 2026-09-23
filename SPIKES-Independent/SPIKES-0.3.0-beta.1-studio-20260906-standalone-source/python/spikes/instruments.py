"""Deterministic, dependency-free reference math for SPIKES instruments.

These classes are instrument engines, not widgets.  A CLI, dashboard, GUI, or
HIL transport can feed their explicit contracts and render the returned data.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import Callable, Iterable

from .instrument_contracts import (
    FrequencyResponse,
    Measurement,
    SampledWaveform,
    ScopeCapture,
    SmithPoint,
    SpectrumTrace,
    finite,
    finite_complex,
)


class InstrumentError(ValueError):
    """A malformed or unqualified acquisition cannot produce a claim."""


@dataclass(frozen=True, slots=True)
class ScopeTrigger:
    level: float = 0.0
    edge: str = "rising"

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", finite(self.level, "trigger level"))
        edge = str(self.edge).lower().strip()
        if edge not in {"rising", "falling", "either"}:
            raise ValueError("Trigger edge must be rising, falling, or either.")
        object.__setattr__(self, "edge", edge)


class Scope:
    """Edge-triggered bounded acquisition over an explicit sampled waveform."""

    def capture(
        self,
        waveform: SampledWaveform,
        *,
        trigger: ScopeTrigger,
        record_length: int,
        pretrigger_samples: int = 0,
    ) -> ScopeCapture:
        try:
            waveform.require_valid(timebase=True)
        except ValueError as exc:
            raise InstrumentError(str(exc)) from exc
        if isinstance(record_length, bool) or not 2 <= int(record_length) <= len(waveform.samples):
            raise InstrumentError("Record length must be 2..input sample count.")
        if isinstance(pretrigger_samples, bool) or not 0 <= int(pretrigger_samples) < int(record_length):
            raise InstrumentError("Pretrigger count must be inside the requested record.")
        record_length = int(record_length)
        pretrigger_samples = int(pretrigger_samples)
        found: tuple[int, float] | None = None
        earliest = max(1, pretrigger_samples)
        latest = len(waveform.samples) - (record_length - pretrigger_samples)
        for right_index in range(earliest, latest + 1):
            left = waveform.samples[right_index - 1]
            right = waveform.samples[right_index]
            rising = left < trigger.level <= right
            falling = left > trigger.level >= right
            if (trigger.edge in {"rising", "either"} and rising) or (
                trigger.edge in {"falling", "either"} and falling
            ):
                fraction = 0.0 if right == left else (trigger.level - left) / (right - left)
                found = (right_index, right_index - 1 + fraction)
                break
        if found is None:
            raise InstrumentError("No trigger crossing can produce the requested complete record.")
        source_trigger_index, fractional_index = found
        start = source_trigger_index - pretrigger_samples
        captured = SampledWaveform(
            channel=waveform.channel,
            unit=waveform.unit,
            sample_rate_hz=waveform.sample_rate_hz,
            samples=waveform.samples[start : start + record_length],
            calibration=waveform.calibration,
            provenance=waveform.provenance + ("spikes.scope.capture/v1",),
            status=waveform.status,
            t0_s=waveform.t0_s + start / waveform.sample_rate_hz,
        )
        trigger_time = waveform.t0_s + fractional_index / waveform.sample_rate_hz
        return ScopeCapture(
            waveform=captured,
            trigger_index=pretrigger_samples,
            trigger_time_s=trigger_time,
            pretrigger_samples=pretrigger_samples,
        )


class DMM:
    """Mean, total RMS, and threshold-crossing frequency measurements."""

    @staticmethod
    def _ready(waveform: SampledWaveform, *, timebase: bool = False) -> None:
        try:
            waveform.require_valid(timebase=timebase)
        except ValueError as exc:
            raise InstrumentError(str(exc)) from exc

    def mean(self, waveform: SampledWaveform) -> Measurement:
        self._ready(waveform)
        value = math.fsum(waveform.samples) / len(waveform.samples)
        return self._measurement("mean", value, waveform.unit, waveform)

    def rms(self, waveform: SampledWaveform, *, ac_coupled: bool = False) -> Measurement:
        self._ready(waveform)
        offset = math.fsum(waveform.samples) / len(waveform.samples) if ac_coupled else 0.0
        value = math.sqrt(math.fsum((item - offset) ** 2 for item in waveform.samples) / len(waveform.samples))
        return self._measurement("ac_rms" if ac_coupled else "rms", value, waveform.unit, waveform)

    def frequency(self, waveform: SampledWaveform, *, threshold: float | None = None) -> Measurement:
        self._ready(waveform, timebase=True)
        if len(waveform.samples) < 3:
            raise InstrumentError("Frequency measurement requires at least three samples.")
        level = (
            math.fsum(waveform.samples) / len(waveform.samples)
            if threshold is None
            else finite(threshold, "frequency threshold")
        )
        crossings: list[float] = []
        for index, (left, right) in enumerate(zip(waveform.samples, waveform.samples[1:])):
            if left < level <= right:
                fraction = 0.0 if right == left else (level - left) / (right - left)
                crossings.append(index + fraction)
        if len(crossings) < 2:
            raise InstrumentError("Frequency measurement requires two rising threshold crossings.")
        periods = [right - left for left, right in zip(crossings, crossings[1:])]
        mean_period_samples = math.fsum(periods) / len(periods)
        if mean_period_samples <= 0.0:
            raise InstrumentError("Frequency crossing period is not positive.")
        return self._measurement("frequency", waveform.sample_rate_hz / mean_period_samples, "Hz", waveform)

    @staticmethod
    def _measurement(kind: str, value: float, unit: str, waveform: SampledWaveform) -> Measurement:
        return Measurement(
            kind=kind,
            value=value,
            unit=unit,
            source=waveform.channel,
            uncertainty_fraction=waveform.calibration.uncertainty_fraction,
            provenance=waveform.provenance + (f"spikes.dmm.{kind}/v1",),
        )


def _window_coefficients(name: str, count: int) -> tuple[float, ...]:
    normalized = str(name).lower().strip()
    if normalized in {"rect", "rectangular", "none"}:
        return (1.0,) * count
    if count < 2:
        raise InstrumentError("Windowing requires at least two samples.")
    angle = 2.0 * math.pi / (count - 1)
    factories: dict[str, Callable[[int], float]] = {
        "hann": lambda index: 0.5 - 0.5 * math.cos(angle * index),
        "hamming": lambda index: 0.54 - 0.46 * math.cos(angle * index),
        "blackman": lambda index: 0.42 - 0.5 * math.cos(angle * index) + 0.08 * math.cos(2.0 * angle * index),
    }
    try:
        factory = factories[normalized]
    except KeyError as exc:
        raise InstrumentError("Window must be rectangular, hann, hamming, or blackman.") from exc
    return tuple(factory(index) for index in range(count))


def _fft_radix2(values: Iterable[complex]) -> list[complex]:
    output = [complex(item) for item in values]
    count = len(output)
    if count < 2 or count & (count - 1):
        raise InstrumentError("FFT length must be a power of two of at least two.")
    target = 0
    for source in range(1, count):
        bit = count >> 1
        while target & bit:
            target ^= bit
            bit >>= 1
        target ^= bit
        if source < target:
            output[source], output[target] = output[target], output[source]
    size = 2
    while size <= count:
        root = cmath.exp(-2j * math.pi / size)
        half = size // 2
        for base in range(0, count, size):
            factor = 1.0 + 0.0j
            for index in range(base, base + half):
                even = output[index]
                odd = factor * output[index + half]
                output[index] = even + odd
                output[index + half] = even - odd
                factor *= root
        size *= 2
    return output


class SpectrumAnalyzer:
    """Windowed one-sided peak-amplitude FFT with deterministic zero padding."""

    MAX_FFT_POINTS = 1_048_576

    def analyze(
        self,
        waveform: SampledWaveform,
        *,
        window: str = "hann",
        fft_points: int | None = None,
        remove_mean: bool = False,
    ) -> SpectrumTrace:
        try:
            waveform.require_valid(timebase=True)
        except ValueError as exc:
            raise InstrumentError(str(exc)) from exc
        source_count = len(waveform.samples)
        if source_count < 2:
            raise InstrumentError("Spectrum analysis requires at least two samples.")
        if fft_points is None:
            fft_points = 1 << (source_count - 1).bit_length()
        if isinstance(fft_points, bool) or int(fft_points) != fft_points:
            raise InstrumentError("FFT point count must be an integer.")
        fft_points = int(fft_points)
        if fft_points < source_count or fft_points > self.MAX_FFT_POINTS or fft_points & (fft_points - 1):
            raise InstrumentError("FFT points must be a bounded power of two no smaller than the input.")
        coefficients = _window_coefficients(window, source_count)
        coherent_gain = math.fsum(coefficients)
        if coherent_gain <= 0.0:
            raise InstrumentError("Selected window has zero coherent gain.")
        mean = math.fsum(waveform.samples) / source_count if remove_mean else 0.0
        transformed = _fft_radix2(
            [coefficient * (sample - mean) for coefficient, sample in zip(coefficients, waveform.samples)]
            + [0.0] * (fft_points - source_count)
        )
        last = fft_points // 2
        amplitudes: list[complex] = []
        for index, value in enumerate(transformed[: last + 1]):
            scale = 1.0 / coherent_gain if index in {0, last} else 2.0 / coherent_gain
            amplitudes.append(value * scale)
        frequencies = tuple(index * waveform.sample_rate_hz / fft_points for index in range(last + 1))
        return SpectrumTrace(
            source_channel=waveform.channel,
            amplitude_unit=waveform.unit,
            frequency_hz=frequencies,
            complex_amplitude=tuple(amplitudes),
            window=str(window).lower().strip(),
            sample_count=source_count,
            provenance=waveform.provenance + ("spikes.spectrum.fft/v1",),
        )


def impedance_to_reflection(impedance_ohm: complex, reference_impedance_ohm: float = 50.0) -> complex:
    impedance = finite_complex(impedance_ohm, "impedance")
    reference = finite(reference_impedance_ohm, "reference impedance", positive=True)
    denominator = impedance + reference
    if abs(denominator) <= 1e-15 * max(1.0, abs(impedance), reference):
        raise InstrumentError("Reflection is singular at Z = -Z0.")
    return (impedance - reference) / denominator


def reflection_to_impedance(reflection: complex, reference_impedance_ohm: float = 50.0) -> complex:
    gamma = finite_complex(reflection, "reflection")
    reference = finite(reference_impedance_ohm, "reference impedance", positive=True)
    denominator = 1.0 - gamma
    if abs(denominator) <= 1e-15 * max(1.0, abs(gamma)):
        raise InstrumentError("Impedance is singular at reflection coefficient 1.")
    return reference * (1.0 + gamma) / denominator


def smith_coordinates(reflection: complex) -> tuple[float, float]:
    """Return Cartesian Smith-chart coordinates (the real/imaginary parts of gamma)."""

    gamma = finite_complex(reflection, "reflection")
    return gamma.real, gamma.imag


class NetworkAnalyzer:
    """One-port S11/Z conversion and Smith-chart data preparation.

    Active and negative-resistance devices are retained: reflection magnitudes
    above one are valid mathematical results and are not clipped.
    """

    def to_impedance(self, response: FrequencyResponse) -> FrequencyResponse:
        self._ready(response)
        if response.quantity != "S11":
            raise InstrumentError("S11 input is required for S-to-Z conversion.")
        return FrequencyResponse(
            name=response.name,
            quantity="Z",
            unit="ohm",
            frequency_hz=response.frequency_hz,
            values=tuple(reflection_to_impedance(value, response.reference_impedance_ohm) for value in response.values),
            reference_impedance_ohm=response.reference_impedance_ohm,
            calibration=response.calibration,
            provenance=response.provenance + ("spikes.network.s11-to-z/v1",),
            status=response.status,
        )

    def to_reflection(self, response: FrequencyResponse) -> FrequencyResponse:
        self._ready(response)
        if response.quantity != "Z":
            raise InstrumentError("Z input is required for Z-to-S11 conversion.")
        return FrequencyResponse(
            name=response.name,
            quantity="S11",
            unit="1",
            frequency_hz=response.frequency_hz,
            values=tuple(impedance_to_reflection(value, response.reference_impedance_ohm) for value in response.values),
            reference_impedance_ohm=response.reference_impedance_ohm,
            calibration=response.calibration,
            provenance=response.provenance + ("spikes.network.z-to-s11/v1",),
            status=response.status,
        )

    def smith(self, response: FrequencyResponse) -> tuple[SmithPoint, ...]:
        self._ready(response)
        reflection = response if response.quantity == "S11" else self.to_reflection(response)
        if reflection.quantity != "S11":
            raise InstrumentError("Smith chart requires S11 or impedance input.")
        points = []
        for frequency, gamma in zip(reflection.frequency_hz, reflection.values):
            impedance = reflection_to_impedance(gamma, reflection.reference_impedance_ohm)
            normalized = impedance / reflection.reference_impedance_ohm
            points.append(
                SmithPoint(
                    frequency_hz=frequency,
                    reflection=gamma,
                    normalized_resistance=normalized.real,
                    normalized_reactance=normalized.imag,
                )
            )
        return tuple(points)

    @staticmethod
    def _ready(response: FrequencyResponse) -> None:
        try:
            response.require_valid()
        except ValueError as exc:
            raise InstrumentError(str(exc)) from exc

