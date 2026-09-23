"""Executable, bounded compact-device references for SPIKES.

This module deliberately does not stamp the native MNA system.  It supplies a
reviewable constitutive model, analytic derivatives and transient state update
that the native device layer can consume in a later integration step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


DYNAMIC_DIODE_CONTRACT = "spikes/dynamic-diode/v1"
_BOLTZMANN_EV_PER_K = 8.617333262145e-5


class DynamicDeviceModelError(ValueError):
    """Raised when a model or evaluation fails its explicit safety contract."""


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise DynamicDeviceModelError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DynamicDeviceModelError(f"{label} must be a finite number.") from exc
    if not math.isfinite(result):
        raise DynamicDeviceModelError(f"{label} must be a finite number.")
    return result


@dataclass(frozen=True, slots=True)
class DynamicDiodeValidity:
    """Fail-closed voltage, temperature, current and step-size envelope."""

    minimum_voltage_v: float = -2_000.0
    maximum_voltage_v: float = 2.0
    minimum_temperature_k: float = 200.0
    maximum_temperature_k: float = 600.0
    maximum_absolute_current_a: float = 1.0e6
    maximum_timestep_s: float = 1.0

    def __post_init__(self) -> None:
        values = {
            name: _finite(getattr(self, name), name)
            for name in (
                "minimum_voltage_v", "maximum_voltage_v",
                "minimum_temperature_k", "maximum_temperature_k",
                "maximum_absolute_current_a", "maximum_timestep_s",
            )
        }
        if values["minimum_voltage_v"] >= values["maximum_voltage_v"]:
            raise DynamicDeviceModelError("Minimum voltage must be below maximum voltage.")
        if values["minimum_temperature_k"] <= 0.0:
            raise DynamicDeviceModelError("Minimum temperature must be positive.")
        if values["minimum_temperature_k"] >= values["maximum_temperature_k"]:
            raise DynamicDeviceModelError("Minimum temperature must be below maximum temperature.")
        if values["maximum_absolute_current_a"] <= 0.0:
            raise DynamicDeviceModelError("Maximum absolute current must be positive.")
        if values["maximum_timestep_s"] <= 0.0:
            raise DynamicDeviceModelError("Maximum timestep must be positive.")
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def validate_point(self, voltage_v: float, temperature_k: float) -> tuple[float, float]:
        voltage = _finite(voltage_v, "voltage_v")
        temperature = _finite(temperature_k, "temperature_k")
        if not self.minimum_voltage_v <= voltage <= self.maximum_voltage_v:
            raise DynamicDeviceModelError(
                f"Voltage {voltage:g} V is outside the qualified range "
                f"[{self.minimum_voltage_v:g}, {self.maximum_voltage_v:g}] V."
            )
        if not self.minimum_temperature_k <= temperature <= self.maximum_temperature_k:
            raise DynamicDeviceModelError(
                f"Temperature {temperature:g} K is outside the qualified range "
                f"[{self.minimum_temperature_k:g}, {self.maximum_temperature_k:g}] K."
            )
        return voltage, temperature

    def validate_timestep(self, timestep_s: float) -> float:
        timestep = _finite(timestep_s, "timestep_s")
        if timestep <= 0.0 or timestep > self.maximum_timestep_s:
            raise DynamicDeviceModelError(
                f"Timestep must be in (0, {self.maximum_timestep_s:g}] s."
            )
        return timestep

    def validate_current(self, current_a: float, label: str = "current") -> float:
        current = _finite(current_a, label)
        if abs(current) > self.maximum_absolute_current_a:
            raise DynamicDeviceModelError(
                f"{label} {current:g} A exceeds the qualified absolute-current limit "
                f"{self.maximum_absolute_current_a:g} A."
            )
        return current


@dataclass(frozen=True, slots=True)
class ReverseRecoveryState:
    """Non-negative mobile charge retained from forward conduction."""

    stored_charge_c: float = 0.0

    def __post_init__(self) -> None:
        charge = _finite(self.stored_charge_c, "stored_charge_c")
        if charge < 0.0:
            raise DynamicDeviceModelError("Stored reverse-recovery charge cannot be negative.")
        object.__setattr__(self, "stored_charge_c", charge)


@dataclass(frozen=True, slots=True)
class DynamicDiodeEvaluation:
    """Quasi-static constitutive values at one operating point."""

    current_a: float
    conductance_s: float
    saturation_current_a: float
    depletion_charge_c: float
    transport_charge_c: float
    depletion_capacitance_f: float
    diffusion_capacitance_f: float
    absorbed_power_w: float

    @property
    def total_charge_c(self) -> float:
        return self.depletion_charge_c + self.transport_charge_c

    @property
    def total_capacitance_f(self) -> float:
        return self.depletion_capacitance_f + self.diffusion_capacitance_f


@dataclass(frozen=True, slots=True)
class DynamicDiodeTransientEvaluation:
    """Backward-Euler charge update and its exact current Jacobian."""

    terminal_current_a: float
    terminal_conductance_s: float
    conduction_current_a: float
    depletion_displacement_current_a: float
    transport_current_a: float
    absorbed_power_w: float
    state: ReverseRecoveryState


@dataclass(frozen=True, slots=True)
class DynamicDiodeModel:
    """Charge-aware temperature-scaled diode reference model.

    ``saturation_current_a`` and ``zero_bias_capacitance_f`` are unit-area
    parameters and are multiplied by ``area``.  Transport charge follows
    ``dq/dt = max(i_cond, 0) - q/transit_time`` and is integrated with implicit
    Euler, yielding an analytic transient Jacobian and reverse-recovery tail.
    """

    saturation_current_a: float = 1.0e-14
    emission_coefficient: float = 1.0
    nominal_temperature_k: float = 300.15
    bandgap_ev: float = 1.11
    saturation_current_exponent: float = 3.0
    area: float = 1.0
    zero_bias_capacitance_f: float = 0.0
    junction_potential_v: float = 1.0
    grading_coefficient: float = 0.5
    forward_depletion_coefficient: float = 0.5
    transit_time_s: float = 0.0
    validity: DynamicDiodeValidity = field(default_factory=DynamicDiodeValidity)

    def __post_init__(self) -> None:
        finite_names = (
            "saturation_current_a", "emission_coefficient", "nominal_temperature_k",
            "bandgap_ev", "saturation_current_exponent", "area",
            "zero_bias_capacitance_f", "junction_potential_v", "grading_coefficient",
            "forward_depletion_coefficient", "transit_time_s",
        )
        values = {name: _finite(getattr(self, name), name) for name in finite_names}
        if values["saturation_current_a"] <= 0.0:
            raise DynamicDeviceModelError("Saturation current must be positive.")
        if values["emission_coefficient"] <= 0.0:
            raise DynamicDeviceModelError("Emission coefficient must be positive.")
        if values["nominal_temperature_k"] <= 0.0:
            raise DynamicDeviceModelError("Nominal temperature must be positive.")
        if values["bandgap_ev"] <= 0.0:
            raise DynamicDeviceModelError("Bandgap must be positive.")
        if values["area"] <= 0.0:
            raise DynamicDeviceModelError("Area must be positive.")
        if values["zero_bias_capacitance_f"] < 0.0:
            raise DynamicDeviceModelError("Zero-bias capacitance cannot be negative.")
        if values["junction_potential_v"] <= 0.0:
            raise DynamicDeviceModelError("Junction potential must be positive.")
        if not 0.0 <= values["grading_coefficient"] < 1.0:
            raise DynamicDeviceModelError("Grading coefficient must be in [0, 1).")
        if not 0.0 <= values["forward_depletion_coefficient"] < 1.0:
            raise DynamicDeviceModelError("Forward-depletion coefficient must be in [0, 1).")
        if values["transit_time_s"] < 0.0:
            raise DynamicDeviceModelError("Transit time cannot be negative.")
        if not isinstance(self.validity, DynamicDiodeValidity):
            raise DynamicDeviceModelError("validity must be a DynamicDiodeValidity instance.")
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def contract(self) -> str:
        return DYNAMIC_DIODE_CONTRACT

    def saturation_current(self, temperature_k: float) -> float:
        temperature = _finite(temperature_k, "temperature_k")
        if not self.validity.minimum_temperature_k <= temperature <= self.validity.maximum_temperature_k:
            raise DynamicDeviceModelError("Temperature is outside the qualified range.")
        ratio = temperature / self.nominal_temperature_k
        activation = self.bandgap_ev / (
            self.emission_coefficient * _BOLTZMANN_EV_PER_K
        ) * (1.0 / self.nominal_temperature_k - 1.0 / temperature)
        try:
            result = self.area * self.saturation_current_a * ratio ** self.saturation_current_exponent * math.exp(activation)
        except OverflowError as exc:
            raise DynamicDeviceModelError("Temperature-scaled saturation current overflowed.") from exc
        return _finite(result, "temperature-scaled saturation current")

    def _conduction(self, voltage_v: float, temperature_k: float) -> tuple[float, float, float]:
        voltage, temperature = self.validity.validate_point(voltage_v, temperature_k)
        thermal_voltage = _BOLTZMANN_EV_PER_K * temperature
        exponent = voltage / (self.emission_coefficient * thermal_voltage)
        try:
            exponential = math.exp(exponent)
        except OverflowError as exc:
            raise DynamicDeviceModelError("Diode exponential overflowed inside its validity envelope.") from exc
        saturation = self.saturation_current(temperature)
        current = saturation * math.expm1(exponent)
        conductance = saturation * exponential / (
            self.emission_coefficient * thermal_voltage
        )
        return (
            self.validity.validate_current(current, "conduction current"),
            _finite(conductance, "conductance"),
            saturation,
        )

    def depletion_charge(self, voltage_v: float) -> tuple[float, float]:
        """Return continuous depletion charge and its analytic derivative."""

        voltage = _finite(voltage_v, "voltage_v")
        if not self.validity.minimum_voltage_v <= voltage <= self.validity.maximum_voltage_v:
            raise DynamicDeviceModelError("Voltage is outside the qualified range.")
        c_zero = self.area * self.zero_bias_capacitance_f
        if c_zero == 0.0:
            return 0.0, 0.0
        potential = self.junction_potential_v
        grading = self.grading_coefficient
        fraction = self.forward_depletion_coefficient
        transition_v = fraction * potential

        def low_bias_charge(v: float) -> float:
            normalized = 1.0 - v / potential
            return c_zero * potential * (
                1.0 - normalized ** (1.0 - grading)
            ) / (1.0 - grading)

        if voltage <= transition_v:
            normalized = 1.0 - voltage / potential
            capacitance = c_zero * normalized ** (-grading)
            return _finite(low_bias_charge(voltage), "depletion charge"), _finite(
                capacitance, "depletion capacitance"
            )

        one_minus_fraction = 1.0 - fraction
        transition_charge = low_bias_charge(transition_v)
        transition_capacitance = c_zero * one_minus_fraction ** (-grading)
        capacitance_slope = (
            grading * c_zero / potential * one_minus_fraction ** (-grading - 1.0)
        )
        delta_v = voltage - transition_v
        charge = transition_charge + transition_capacitance * delta_v + 0.5 * capacitance_slope * delta_v * delta_v
        capacitance = transition_capacitance + capacitance_slope * delta_v
        return _finite(charge, "depletion charge"), _finite(capacitance, "depletion capacitance")

    def evaluate(self, voltage_v: float, temperature_k: float) -> DynamicDiodeEvaluation:
        voltage, temperature = self.validity.validate_point(voltage_v, temperature_k)
        current, conductance, saturation = self._conduction(voltage, temperature)
        depletion_charge, depletion_capacitance = self.depletion_charge(voltage)
        forward = max(current, 0.0)
        forward_conductance = conductance if current > 0.0 else 0.0
        transport_charge = self.transit_time_s * forward
        diffusion_capacitance = self.transit_time_s * forward_conductance
        return DynamicDiodeEvaluation(
            current_a=current,
            conductance_s=conductance,
            saturation_current_a=saturation,
            depletion_charge_c=depletion_charge,
            transport_charge_c=_finite(transport_charge, "transport charge"),
            depletion_capacitance_f=depletion_capacitance,
            diffusion_capacitance_f=_finite(diffusion_capacitance, "diffusion capacitance"),
            absorbed_power_w=_finite(voltage * current, "absorbed power"),
        )

    def advance(
        self,
        voltage_v: float,
        previous_voltage_v: float,
        temperature_k: float,
        timestep_s: float,
        previous_state: ReverseRecoveryState = ReverseRecoveryState(),
    ) -> DynamicDiodeTransientEvaluation:
        """Advance depletion and mobile charge by one implicit-Euler step."""

        if not isinstance(previous_state, ReverseRecoveryState):
            raise DynamicDeviceModelError("previous_state must be a ReverseRecoveryState.")
        voltage, temperature = self.validity.validate_point(voltage_v, temperature_k)
        previous_voltage, _ = self.validity.validate_point(previous_voltage_v, temperature)
        timestep = self.validity.validate_timestep(timestep_s)
        dc = self.evaluate(voltage, temperature)
        previous_depletion_charge, _ = self.depletion_charge(previous_voltage)
        depletion_current = (dc.depletion_charge_c - previous_depletion_charge) / timestep

        if self.transit_time_s == 0.0:
            new_charge = 0.0
            transport_current = 0.0
            transport_conductance = 0.0
        else:
            forward_current = max(dc.current_a, 0.0)
            forward_conductance = dc.conductance_s if dc.current_a > 0.0 else 0.0
            denominator = 1.0 + timestep / self.transit_time_s
            new_charge = (
                previous_state.stored_charge_c + timestep * forward_current
            ) / denominator
            transport_current = (new_charge - previous_state.stored_charge_c) / timestep
            transport_conductance = forward_conductance / denominator

        terminal_current = dc.current_a + depletion_current + transport_current
        terminal_conductance = (
            dc.conductance_s
            + dc.depletion_capacitance_f / timestep
            + transport_conductance
        )
        self.validity.validate_current(terminal_current, "transient terminal current")
        return DynamicDiodeTransientEvaluation(
            terminal_current_a=_finite(terminal_current, "terminal current"),
            terminal_conductance_s=_finite(terminal_conductance, "terminal conductance"),
            conduction_current_a=dc.current_a,
            depletion_displacement_current_a=_finite(depletion_current, "depletion displacement current"),
            transport_current_a=_finite(transport_current, "transport current"),
            absorbed_power_w=_finite(voltage * terminal_current, "transient absorbed power"),
            state=ReverseRecoveryState(new_charge),
        )
