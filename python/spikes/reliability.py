# SPDX-License-Identifier: Apache-2.0
"""Explicit scenario hazards for fault scheduling; not part qualification.

Time/age are device operating hours. Electrical integration stays in the native
engine. This module only computes conditional event probabilities and timings.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

BOLTZMANN_EV_PER_K = 8.617333262145e-5


def finite(value: float, name: str, *, minimum: float = 0.0, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum or (positive and result == minimum):
        raise ValueError(f"{name} is outside its finite bounds")
    return result


def _result(value: float) -> float:
    if not math.isfinite(value) or value < 0:
        raise ValueError("Hazard exceeds the finite numerical range")
    return value


@dataclass(frozen=True)
class WeibullHazard:
    shape: float
    scale_hours: float
    weight: float = 1.0

    def __post_init__(self):
        for name in ("shape", "scale_hours", "weight"):
            object.__setattr__(self, name, finite(getattr(self, name), name, positive=name != "weight"))

    def increment(self, age_hours: float, duration_hours: float, *, multiplier: float = 1.0) -> float:
        """Integral of hazard over the interval, avoiding close-power subtraction."""
        age = finite(age_hours, "age_hours")
        duration = finite(duration_hours, "duration_hours")
        multiplier = finite(multiplier, "multiplier")
        if duration == 0 or self.weight == 0 or multiplier == 0:
            return 0.0
        try:
            if age == 0:
                logarithm = self.shape * (math.log(duration) - math.log(self.scale_hours))
            else:
                log_ratio = math.log(duration) - math.log(age)
                if log_ratio < -36 and log_ratio + math.log(self.shape) < -36:
                    # expm1(beta*log1p(r)) ~ beta*r; retained in log space
                    # even when the ratio itself would underflow to zero.
                    log_difference = math.log(self.shape) + log_ratio
                else:
                    log_sum = (log_ratio + math.log1p(math.exp(-log_ratio))
                               if log_ratio > 36 else math.log1p(math.exp(log_ratio)))
                    exponent = self.shape * log_sum
                    log_difference = (exponent + math.log1p(-math.exp(-exponent))
                                      if exponent > 50 else math.log(math.expm1(exponent)))
                logarithm = self.shape * (math.log(age)-math.log(self.scale_hours)) + log_difference
            return _result(math.exp(math.log(self.weight) + math.log(multiplier) + logarithm))
        except OverflowError as exc:
            raise ValueError("Weibull hazard exceeds numerical range") from exc

    def rate_per_hour(self, age_hours: float, *, multiplier: float = 1.0) -> float:
        age = finite(age_hours, "age_hours")
        multiplier = finite(multiplier, "multiplier")
        if self.weight == 0 or multiplier == 0:
            return 0.0
        if age == 0:
            if self.shape < 1:
                raise ValueError("Early-life Weibull instantaneous hazard is singular at age zero; use an interval")
            if self.shape > 1:
                return 0.0
            try:
                return _result(math.exp(math.log(self.weight)+math.log(multiplier)-math.log(self.scale_hours)))
            except OverflowError as exc:
                raise ValueError("Weibull rate exceeds numerical range") from exc
        try:
            return _result(math.exp(math.log(self.weight) + math.log(multiplier) + math.log(self.shape) - math.log(self.scale_hours)
                + (self.shape - 1) * (math.log(age) - math.log(self.scale_hours))))
        except (OverflowError, ValueError) as exc:
            raise ValueError("Weibull rate exceeds numerical range") from exc


@dataclass(frozen=True)
class BathtubHazard:
    """Independent competing early-life, constant-FIT and wear-out hazards.

    Parameters are supplied scenario inputs. This is not a fitted lifetime model
    and does not identify which electrical failure mode will occur.
    """
    constant_fit: float
    early_life: WeibullHazard | None = None
    wear_out: WeibullHazard | None = None
    multiplier: float = 1.0

    def __post_init__(self):
        object.__setattr__(self, "constant_fit", finite(self.constant_fit, "constant_fit"))
        object.__setattr__(self, "multiplier", finite(self.multiplier, "multiplier"))
        if self.early_life is not None and (not isinstance(self.early_life, WeibullHazard) or self.early_life.shape >= 1):
            raise ValueError("Early-life hazard requires a Weibull shape below one")
        if self.wear_out is not None and (not isinstance(self.wear_out, WeibullHazard) or self.wear_out.shape <= 1):
            raise ValueError("Wear-out hazard requires a Weibull shape above one")

    def cumulative_increment(self, age_hours: float, duration_hours: float) -> float:
        age, duration = finite(age_hours, "age_hours"), finite(duration_hours, "duration_hours")
        if self.multiplier == 0:
            return 0.0
        try:
            constant = (math.exp(math.log(self.constant_fit)-math.log(1e9)+math.log(duration)+math.log(self.multiplier))
                        if self.constant_fit and duration else 0.0)
            parts = [constant]
            parts += [term.increment(age, duration, multiplier=self.multiplier)
                      for term in (self.early_life, self.wear_out) if term is not None]
            return _result(math.fsum(parts))
        except OverflowError as exc:
            raise ValueError("Cumulative hazard exceeds numerical range") from exc

    def probability(self, age_hours: float, duration_hours: float) -> float:
        return -math.expm1(-self.cumulative_increment(age_hours, duration_hours))

    def rate_per_hour(self, age_hours: float) -> float:
        age = finite(age_hours, "age_hours")
        if self.multiplier == 0:
            return 0.0
        try:
            constant = (math.exp(math.log(self.constant_fit)-math.log(1e9)+math.log(self.multiplier))
                        if self.constant_fit else 0.0)
            parts = [constant]
            parts += [term.rate_per_hour(age, multiplier=self.multiplier)
                      for term in (self.early_life, self.wear_out) if term is not None]
            return _result(math.fsum(parts))
        except OverflowError as exc:
            raise ValueError("Hazard rate exceeds numerical range") from exc


def arrhenius_acceleration(temperature_k: float, reference_temperature_k: float,
                          activation_energy_ev: float) -> float:
    """Supplied single-mechanism activation energy; no default device coefficient."""
    temperature = finite(temperature_k, "temperature_k", positive=True)
    reference = finite(reference_temperature_k, "reference_temperature_k", positive=True)
    energy = finite(activation_energy_ev, "activation_energy_ev")
    try:
        value = math.exp(energy / BOLTZMANN_EV_PER_K * (1/reference - 1/temperature))
    except OverflowError as exc:
        raise ValueError("Arrhenius acceleration exceeds numerical range") from exc
    return _result(value)


def failure_delay_hours(hazard: BathtubHazard, *, age_hours: float, quantile: float,
                        horizon_hours: float) -> float | None:
    """Invert a conditional event quantile on a bounded horizon, with no RNG state.

    None means the selected event is beyond the horizon. Supplying a quantile
    makes campaigns reproducible without relying on a platform RNG algorithm.
    """
    if not isinstance(hazard, BathtubHazard):
        raise TypeError("Expected a BathtubHazard")
    age = finite(age_hours, "age_hours")
    horizon = finite(horizon_hours, "horizon_hours", positive=True)
    q = finite(quantile, "quantile", positive=True)
    if q >= 1:
        raise ValueError("Quantile must lie strictly between zero and one")
    target = -math.log1p(-q)
    if hazard.cumulative_increment(age, horizon) < target:
        return None
    low, high = 0.0, horizon
    # Covers the full binary64 exponent span; ordinary scenarios stop much earlier.
    for _ in range(2200):
        middle = low + (high-low)/2
        if middle == low or middle == high:
            break
        if hazard.cumulative_increment(age, middle) < target:
            low = middle
        else:
            high = middle
    return high


def report(hazard: BathtubHazard, age_hours: float, duration_hours: float) -> dict:
    probability = hazard.probability(age_hours, duration_hours)
    try:
        rate, reason = hazard.rate_per_hour(age_hours), None
    except ValueError as exc:
        rate, reason = None, str(exc)
    return {"contract": "spikes/reliability-scenario/v1", "model_status": "unverified_scenario",
        "age_hours": float(age_hours), "duration_hours": float(duration_hours),
        "conditional_event_probability": probability, "hazard_per_hour": rate,
        "unavailable_reason": reason, "constant_fit": hazard.constant_fit,
        "limitations": "Specified nonrepairable competing-hazard scenario; no physical mode allocation or hardware qualification."}
