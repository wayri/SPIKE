"""Bounded executable DC compact-device references.

Currents are positive into each named terminal and sum to zero.  These models
are constitutive references, not native MNA stamps or vendor-qualified models.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .dynamic_devices import DynamicDeviceModelError, _BOLTZMANN_EV_PER_K, _finite


STATIC_COMPACT_CONTRACT = "spikes/static-compact-devices/v1"


@dataclass(frozen=True, slots=True)
class StaticDeviceValidity:
    minimum_voltage_v: float = -1000.0
    maximum_voltage_v: float = 1000.0
    minimum_temperature_k: float = 200.0
    maximum_temperature_k: float = 600.0
    maximum_absolute_current_a: float = 1.0e6

    def __post_init__(self) -> None:
        values = tuple(_finite(getattr(self, name), name) for name in (
            "minimum_voltage_v", "maximum_voltage_v", "minimum_temperature_k",
            "maximum_temperature_k", "maximum_absolute_current_a",
        ))
        if values[0] >= values[1]:
            raise DynamicDeviceModelError("Minimum voltage must be below maximum voltage.")
        if values[2] <= 0.0 or values[2] >= values[3]:
            raise DynamicDeviceModelError("Temperature bounds must be positive and ordered.")
        if values[4] <= 0.0:
            raise DynamicDeviceModelError("Maximum absolute current must be positive.")
        for name, value in zip((
            "minimum_voltage_v", "maximum_voltage_v", "minimum_temperature_k",
            "maximum_temperature_k", "maximum_absolute_current_a",
        ), values):
            object.__setattr__(self, name, value)

    def validate(self, voltages: tuple[float, ...], temperature_k: float) -> tuple[tuple[float, ...], float]:
        checked = tuple(_finite(value, "terminal voltage") for value in voltages)
        if any(value < self.minimum_voltage_v or value > self.maximum_voltage_v for value in checked):
            raise DynamicDeviceModelError("Terminal voltage is outside the qualified range.")
        temperature = _finite(temperature_k, "temperature_k")
        if not self.minimum_temperature_k <= temperature <= self.maximum_temperature_k:
            raise DynamicDeviceModelError("Temperature is outside the qualified range.")
        return checked, temperature

    def validate_currents(self, currents: tuple[float, ...]) -> tuple[float, ...]:
        checked = tuple(_finite(value, "terminal current") for value in currents)
        if any(abs(value) > self.maximum_absolute_current_a for value in checked):
            raise DynamicDeviceModelError("Terminal current exceeds the qualified limit.")
        return checked


@dataclass(frozen=True, slots=True)
class TerminalDCEvaluation:
    terminal_names: tuple[str, ...]
    currents_a: tuple[float, ...]
    jacobian_s: tuple[tuple[float, ...], ...]
    jacobian_kind: str

    def __post_init__(self) -> None:
        size = len(self.terminal_names)
        if size < 2 or len(set(self.terminal_names)) != size:
            raise DynamicDeviceModelError("Terminal names must be unique.")
        if len(self.currents_a) != size or len(self.jacobian_s) != size:
            raise DynamicDeviceModelError("Terminal current/Jacobian dimensions do not match.")
        if any(len(row) != size for row in self.jacobian_s):
            raise DynamicDeviceModelError("Jacobian must be square.")
        if self.jacobian_kind not in {"analytic", "qualified_numeric"}:
            raise DynamicDeviceModelError("Unsupported Jacobian kind.")
        if abs(sum(self.currents_a)) > 1e-10 * max(1.0, *(abs(v) for v in self.currents_a)):
            raise DynamicDeviceModelError("Terminal currents violate KCL.")

    def current(self, terminal: str) -> float:
        return self.currents_a[self.terminal_names.index(terminal)]


def _numeric_jacobian(
    function: Callable[[tuple[float, ...]], tuple[float, ...]],
    voltages: tuple[float, ...],
) -> tuple[tuple[float, ...], ...]:
    columns: list[tuple[float, ...]] = []
    for index, value in enumerate(voltages):
        step = 2.0e-6 * max(1.0, abs(value))
        plus = list(voltages)
        minus = list(voltages)
        plus[index] += step
        minus[index] -= step
        high = function(tuple(plus))
        low = function(tuple(minus))
        columns.append(tuple((a - b) / (2.0 * step) for a, b in zip(high, low)))
    return tuple(tuple(columns[column][row] for column in range(len(voltages))) for row in range(len(voltages)))


def _scaled_saturation(value: float, tnom: float, temperature: float, bandgap: float, emission: float) -> float:
    ratio = temperature / tnom
    return value * ratio**3 * math.exp(
        bandgap / (emission * _BOLTZMANN_EV_PER_K) * (1.0 / tnom - 1.0 / temperature)
    )


@dataclass(frozen=True, slots=True)
class EbersMollBJT:
    """NPN Ebers–Moll DC reference; terminals are collector, base, emitter."""

    forward_saturation_current_a: float = 1e-15
    reverse_saturation_current_a: float = 1e-15
    forward_transport_factor: float = 0.99
    reverse_transport_factor: float = 0.5
    forward_emission_coefficient: float = 1.0
    reverse_emission_coefficient: float = 1.0
    nominal_temperature_k: float = 300.15
    bandgap_ev: float = 1.11
    validity: StaticDeviceValidity = StaticDeviceValidity()

    def __post_init__(self) -> None:
        positive = ("forward_saturation_current_a", "reverse_saturation_current_a",
                    "forward_emission_coefficient", "reverse_emission_coefficient",
                    "nominal_temperature_k", "bandgap_ev")
        for name in positive:
            value = _finite(getattr(self, name), name)
            if value <= 0.0:
                raise DynamicDeviceModelError(f"{name} must be positive.")
            object.__setattr__(self, name, value)
        for name in ("forward_transport_factor", "reverse_transport_factor"):
            value = _finite(getattr(self, name), name)
            if not 0.0 < value <= 1.0:
                raise DynamicDeviceModelError(f"{name} must be in (0, 1].")
            object.__setattr__(self, name, value)

    def evaluate(self, collector_v: float, base_v: float, emitter_v: float, temperature_k: float) -> TerminalDCEvaluation:
        (vc, vb, ve), temperature = self.validity.validate((collector_v, base_v, emitter_v), temperature_k)
        vt = _BOLTZMANN_EV_PER_K * temperature
        isf = _scaled_saturation(self.forward_saturation_current_a, self.nominal_temperature_k,
                                 temperature, self.bandgap_ev, self.forward_emission_coefficient)
        isr = _scaled_saturation(self.reverse_saturation_current_a, self.nominal_temperature_k,
                                 temperature, self.bandgap_ev, self.reverse_emission_coefficient)
        ef = math.exp((vb - ve) / (self.forward_emission_coefficient * vt))
        er = math.exp((vb - vc) / (self.reverse_emission_coefficient * vt))
        jf, jr = isf * (ef - 1.0), isr * (er - 1.0)
        gf = isf * ef / (self.forward_emission_coefficient * vt)
        gr = isr * er / (self.reverse_emission_coefficient * vt)
        af, ar = self.forward_transport_factor, self.reverse_transport_factor
        currents = self.validity.validate_currents((af * jf - jr,
                                                     (1.0 - af) * jf + (1.0 - ar) * jr,
                                                     -jf + ar * jr))
        # Rows/columns are C, B, E.  Each row and column sums to zero.
        jacobian = (
            (gr, af * gf - gr, -af * gf),
            (-(1.0 - ar) * gr, (1.0 - af) * gf + (1.0 - ar) * gr, -(1.0 - af) * gf),
            (-ar * gr, -gf + ar * gr, gf),
        )
        return TerminalDCEvaluation(("collector", "base", "emitter"), currents, jacobian, "analytic")


@dataclass(frozen=True, slots=True)
class Level1MOSFET:
    """Bidirectional n-channel Shichman–Hodges Level-1 DC reference."""

    threshold_voltage_v: float = 1.0
    transconductance_a_per_v2: float = 1e-3
    channel_length_modulation_per_v: float = 0.0
    body_effect_v_sqrt: float = 0.0
    surface_potential_v: float = 0.6
    threshold_temperature_coefficient_v_per_k: float = -2e-3
    mobility_temperature_exponent: float = 1.5
    nominal_temperature_k: float = 300.15
    validity: StaticDeviceValidity = StaticDeviceValidity()

    def __post_init__(self) -> None:
        for name in ("threshold_voltage_v", "threshold_temperature_coefficient_v_per_k"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        for name in ("transconductance_a_per_v2", "surface_potential_v", "nominal_temperature_k"):
            value = _finite(getattr(self, name), name)
            if value <= 0.0:
                raise DynamicDeviceModelError(f"{name} must be positive.")
            object.__setattr__(self, name, value)
        for name in ("channel_length_modulation_per_v", "body_effect_v_sqrt", "mobility_temperature_exponent"):
            value = _finite(getattr(self, name), name)
            if value < 0.0:
                raise DynamicDeviceModelError(f"{name} cannot be negative.")
            object.__setattr__(self, name, value)

    def _currents(self, voltages: tuple[float, ...], temperature: float) -> tuple[float, ...]:
        vd, vg, vs, vb = voltages
        reverse = vd < vs
        high, low = (vs, vd) if reverse else (vd, vs)
        vgs = vg - low
        vbs = vb - low
        root_argument = self.surface_potential_v - vbs
        if root_argument <= 0.0:
            raise DynamicDeviceModelError("MOS body-bias square root is outside its validity domain.")
        threshold = (self.threshold_voltage_v
                     + self.threshold_temperature_coefficient_v_per_k * (temperature - self.nominal_temperature_k)
                     + self.body_effect_v_sqrt * (math.sqrt(root_argument) - math.sqrt(self.surface_potential_v)))
        overdrive, vds = vgs - threshold, high - low
        beta = self.transconductance_a_per_v2 * (temperature / self.nominal_temperature_k) ** (-self.mobility_temperature_exponent)
        if overdrive <= 0.0:
            magnitude = 0.0
        elif vds < overdrive:
            magnitude = beta * (overdrive * vds - 0.5 * vds * vds) * (1.0 + self.channel_length_modulation_per_v * vds)
        else:
            magnitude = 0.5 * beta * overdrive * overdrive * (1.0 + self.channel_length_modulation_per_v * vds)
        drain_current = -magnitude if reverse else magnitude
        return self.validity.validate_currents((drain_current, 0.0, -drain_current, 0.0))

    def evaluate(self, drain_v: float, gate_v: float, source_v: float, body_v: float, temperature_k: float) -> TerminalDCEvaluation:
        voltages, temperature = self.validity.validate((drain_v, gate_v, source_v, body_v), temperature_k)
        function = lambda values: self._currents(values, temperature)
        currents = function(voltages)
        return TerminalDCEvaluation(("drain", "gate", "source", "body"), currents,
                                    _numeric_jacobian(function, voltages), "qualified_numeric")


@dataclass(frozen=True, slots=True)
class ShichmanHodgesJFET:
    """Bidirectional n-channel JFET DC reference with zero gate leakage."""

    pinch_off_voltage_v: float = -2.0
    transconductance_a_per_v2: float = 1e-3
    channel_length_modulation_per_v: float = 0.0
    mobility_temperature_exponent: float = 1.5
    nominal_temperature_k: float = 300.15
    validity: StaticDeviceValidity = StaticDeviceValidity()

    def __post_init__(self) -> None:
        pinch = _finite(self.pinch_off_voltage_v, "pinch_off_voltage_v")
        if pinch >= 0.0:
            raise DynamicDeviceModelError("N-channel JFET pinch-off voltage must be negative.")
        object.__setattr__(self, "pinch_off_voltage_v", pinch)
        for name in ("transconductance_a_per_v2", "nominal_temperature_k"):
            value = _finite(getattr(self, name), name)
            if value <= 0.0:
                raise DynamicDeviceModelError(f"{name} must be positive.")
            object.__setattr__(self, name, value)
        for name in ("channel_length_modulation_per_v", "mobility_temperature_exponent"):
            value = _finite(getattr(self, name), name)
            if value < 0.0:
                raise DynamicDeviceModelError(f"{name} cannot be negative.")
            object.__setattr__(self, name, value)

    def _currents(self, voltages: tuple[float, ...], temperature: float) -> tuple[float, ...]:
        vd, vg, vs = voltages
        reverse = vd < vs
        high, low = (vs, vd) if reverse else (vd, vs)
        overdrive = vg - low - self.pinch_off_voltage_v
        vds = high - low
        beta = self.transconductance_a_per_v2 * (temperature / self.nominal_temperature_k) ** (-self.mobility_temperature_exponent)
        if overdrive <= 0.0:
            magnitude = 0.0
        elif vds < overdrive:
            magnitude = beta * (overdrive * vds - 0.5 * vds * vds) * (1.0 + self.channel_length_modulation_per_v * vds)
        else:
            magnitude = 0.5 * beta * overdrive * overdrive * (1.0 + self.channel_length_modulation_per_v * vds)
        drain_current = -magnitude if reverse else magnitude
        return self.validity.validate_currents((drain_current, 0.0, -drain_current))

    def evaluate(self, drain_v: float, gate_v: float, source_v: float, temperature_k: float) -> TerminalDCEvaluation:
        voltages, temperature = self.validity.validate((drain_v, gate_v, source_v), temperature_k)
        function = lambda values: self._currents(values, temperature)
        currents = function(voltages)
        return TerminalDCEvaluation(("drain", "gate", "source"), currents,
                                    _numeric_jacobian(function, voltages), "qualified_numeric")
