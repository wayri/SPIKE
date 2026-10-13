# SPDX-License-Identifier: Apache-2.0
"""Evidence-bound local linear parameter changes under supplied exposure.

These mappings produce fault-site values; they do not infer a radiation response,
corrosion process, vibration damage, or a complete hazardous-environment solver.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .reliability import finite
from .fault_injection import FaultSite


def _validate_binding(target, result, baseline):
    try:
        descriptor = target.fault_sites[result["fault_site"]]
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError("Environment application requires a declared target fault site") from exc
    expected = {"V": "threshold_voltage_v", "ohm": "resistance_ohm"}[result["unit"]]
    if not isinstance(descriptor, FaultSite) or descriptor.parameter != expected:
        raise ValueError("Environment parameter unit conflicts with target fault parameter")
    if descriptor.healthy_value != baseline:
        raise ValueError("Environment baseline conflicts with the declared healthy parameter")
    descriptor.validate(result["value"])


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError(f"{name} must be nonempty bounded text")
    return value.strip()


@dataclass(frozen=True)
class Exposure:
    temperature_k: float
    dose_rad_si: float = 0.0
    relative_humidity: float = 0.0
    vibration_rms_g: float = 0.0

    def __post_init__(self):
        for name in ("temperature_k", "dose_rad_si", "relative_humidity", "vibration_rms_g"):
            object.__setattr__(self, name, finite(getattr(self, name), name, positive=name == "temperature_k"))
        if self.relative_humidity > 1:
            raise ValueError("Relative humidity is a fraction in [0,1]")


@dataclass(frozen=True)
class ParameterResponse:
    """One specified local coefficient, explicitly calibrated or a what-if.

    Dose reference is silicon only; no conversion from SiO2 or fluence is made.
    Conditions/applicability must describe bias, dose-rate/particle or vibration
    spectrum, lot, temperature, annealing and endpoint as relevant to the axis.
    """
    fault_site: str
    part_number: str
    manufacturer: str
    axis: str
    reference: float
    coefficient: float
    baseline: float
    minimum_exposure: float
    maximum_exposure: float
    parameter_unit: str
    source_locator: str
    conditions: str
    applicability_basis: str
    reviewed: bool = False

    def __post_init__(self):
        for name in ("fault_site", "part_number", "manufacturer", "source_locator", "conditions", "applicability_basis"):
            object.__setattr__(self, name, text(getattr(self, name), name))
        if self.axis not in {"temperature_k", "dose_rad_si", "relative_humidity", "vibration_rms_g"}:
            raise ValueError("Unsupported exposure axis; supply an explicitly modeled effect")
        if self.parameter_unit not in {"V", "ohm"} or type(self.reviewed) is not bool:
            raise ValueError("Parameter unit must be V/ohm and reviewed must be boolean")
        for name in ("reference", "coefficient", "baseline", "minimum_exposure", "maximum_exposure"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, float(value))
        if not 0 <= self.minimum_exposure <= self.reference <= self.maximum_exposure or self.minimum_exposure == self.maximum_exposure:
            raise ValueError("Exposure calibration interval must be nonnegative, distinct and contain reference")
        if self.axis == "temperature_k" and self.minimum_exposure <= 0:
            raise ValueError("Calibrated temperature interval must be above absolute zero")
        if self.axis == "relative_humidity" and self.maximum_exposure > 1:
            raise ValueError("Calibrated relative humidity cannot exceed one")

    def evaluate(self, exposure: Exposure, *, part_number: str, manufacturer: str) -> dict:
        # Normalize case/spacing only; never drop an ordering suffix or assume family equivalence.
        if text(part_number, "part_number").casefold() != self.part_number.casefold() or text(manufacturer, "manufacturer").casefold() != self.manufacturer.casefold():
            raise ValueError("Exposure evidence belongs to a different exact part/manufacturer")
        if not isinstance(exposure, Exposure):
            raise TypeError("Expected an Exposure")
        value = getattr(exposure, self.axis)
        if not self.minimum_exposure <= value <= self.maximum_exposure:
            raise ValueError("Exposure is outside the specified local response interval")
        parameter = self.baseline + self.coefficient * (value-self.reference)
        if not math.isfinite(parameter) or (self.parameter_unit == "ohm" and parameter <= 0):
            raise ValueError("Exposure produces an invalid parameter; no clamping is applied")
        return {"fault_site": self.fault_site, "value": parameter, "unit": self.parameter_unit,
            "model_status": "conditional_calibrated_mapping" if self.reviewed else "unverified_scenario",
            "axis": self.axis, "exposure": value, "part_number": self.part_number,
            "manufacturer": self.manufacturer, "source_locator": self.source_locator,
            "conditions": self.conditions, "applicability_basis": self.applicability_basis,
            "limitations": "Supplied local linear response only; review flag is not source authentication or hardware qualification."}

    def apply(self, target, exposure: Exposure, *, part_number: str, manufacturer: str) -> dict:
        result = self.evaluate(exposure, part_number=part_number, manufacturer=manufacturer)
        _validate_binding(target, result, self.baseline)
        target.inject_fault(result["fault_site"], result["value"])
        return result


def combined_response(responses, exposure: Exposure, *, part_number: str, manufacturer: str) -> dict:
    """Add supplied local deltas for one site around one common baseline.

    No nonlinear interaction or automatic combined-stress qualification is
    implied. Re-evaluation uses the baseline, never an already degraded value.
    """
    records = tuple(responses)
    if not 1 <= len(records) <= 64 or any(not isinstance(r, ParameterResponse) for r in records):
        raise ValueError("Supply 1..64 typed responses for one fault site")
    first = records[0]
    if any((r.fault_site, r.parameter_unit, r.baseline) !=
           (first.fault_site, first.parameter_unit, first.baseline) for r in records):
        raise ValueError("Combined responses must share the site, unit and baseline")
    if len({r.axis for r in records}) != len(records):
        raise ValueError("Duplicate exposure axis would double-count its response")
    evaluations = [r.evaluate(exposure, part_number=part_number, manufacturer=manufacturer) for r in records]
    value = first.baseline + math.fsum(r["value"]-first.baseline for r in evaluations)
    if not math.isfinite(value) or (first.parameter_unit == "ohm" and value <= 0):
        raise ValueError("Combined response produces an invalid parameter")
    return {"fault_site": first.fault_site, "value": value, "unit": first.parameter_unit,
        "model_status": "conditional_calibrated_mapping" if all(r.reviewed for r in records) else "unverified_scenario",
        "effects": evaluations, "limitations": "Additive local deltas only; combined-stress interactions remain unvalidated."}


def apply_combined_response(target, responses, exposure: Exposure, *, part_number: str, manufacturer: str) -> dict:
    records = tuple(responses)
    result = combined_response(records, exposure, part_number=part_number, manufacturer=manufacturer)
    _validate_binding(target, result, records[0].baseline)
    target.inject_fault(result["fault_site"], result["value"])
    return result
