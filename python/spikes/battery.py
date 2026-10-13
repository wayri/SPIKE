# SPDX-License-Identifier: Apache-2.0
"""Original, unqualified prescribed-current one-RC battery reference study.

Positive current discharges. This is not a native SPIKES MNA device, an
electrochemical solver, a cell database, or a battery safety/remaining-life tool.
See docs/SPIKES_BATTERY_MODEL.md for equations, units and evidence boundaries.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from numbers import Real
from typing import Sequence


CHEMISTRIES = {
    "lithium_ion_nmc": "Lithium-ion NMC", "lithium_ion_nca": "Lithium-ion NCA",
    "lithium_ion_lco": "Lithium-ion LCO", "lithium_ion_lmo": "Lithium-ion LMO",
    "lithium_ion_lfp": "Lithium iron phosphate (LFP)",
    "lithium_ion_lto": "Lithium titanate (LTO)",
    "lithium_polymer": "Lithium polymer (electrode chemistry unspecified)",
    "solid_state_lithium": "Solid-state lithium (experimental template)",
    "lithium_sulfur": "Lithium-sulfur (experimental template)",
    "lithium_metal": "Lithium metal (experimental template)",
    "lithium_primary": "Primary lithium (reaction unspecified)",
    "zinc_carbon": "Zinc-carbon", "alkaline": "Alkaline zinc-manganese dioxide",
    "zinc_air": "Zinc-air", "zinc_ion": "Zinc-ion (experimental template)",
    "sodium_ion": "Sodium-ion", "sodium_sulfur": "Sodium-sulfur",
    "nickel_cadmium": "Nickel-cadmium", "nickel_metal_hydride": "Nickel-metal hydride",
    "nickel_iron": "Nickel-iron", "lead_acid_flooded": "Lead-acid flooded",
    "lead_acid_agm": "Lead-acid AGM", "lead_acid_gel": "Lead-acid gel",
    "silver_oxide": "Silver oxide", "silver_zinc": "Silver-zinc",
    "aluminum_air": "Aluminum-air", "iron_air": "Iron-air (experimental template)",
    "metal_air": "Other metal-air (reaction unspecified)",
    "flow_battery": "Flow battery (reaction unspecified)",
    "custom": "Custom user-parameterized cell",
}
_PRIMARY = {"lithium_primary", "zinc_carbon", "alkaline", "zinc_air",
            "silver_oxide", "aluminum_air", "metal_air"}
LIMITATIONS = (
    "Unqualified reduced-order reference study; no manufacturer or measured cell fit.",
    "Chemistry identifiers are labels, not universal chemistry-specific physics.",
    "Prescribed current only; not connected to the native SPIKES circuit/MNA solver.",
    "No runaway, abuse, dendrites, plating, gas, hysteresis, diffusion or spatial thermal model.",
    "Aging coefficients are user assumptions, not a remaining-life or safety prediction.",
    "No pack imbalance, BMS, charger, oxygen/reactant transport or flow-system auxiliaries.",
    "Chemical losses from inefficiency, self-discharge and aging are not a full heat balance.",
    "Refine max_step_s for coupled temperature/aging convergence; human review required.",
)
MAX_SAMPLES = 100001
MAX_STEPS = 200000


def _number(value, name):
    try:
        valid = not isinstance(value, bool) and isinstance(value, Real) and math.isfinite(value)
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def _positive(value, name, *, zero=False):
    number = _number(value, name)
    if number < 0 or (number == 0 and not zero):
        raise ValueError(f"{name} must be {'nonnegative' if zero else 'positive'}")
    return number


@dataclass(frozen=True)
class BatteryModel:
    """SI inputs except capacity (Ah), calendar rates (/day) and cycle rates (/EFC)."""

    chemistry: str = "custom"
    nominal_capacity_ah: float = 1.0
    ocv_soc_v: tuple[tuple[float, float], ...] = ((0.0, 3.0), (1.0, 4.0))
    r0_ohm: float = 0.05
    r1_ohm: float = 0.02
    c1_f: float = 1000.0
    thermal_capacity_j_k: float = 100.0
    thermal_resistance_k_w: float = 10.0
    reference_temperature_k: float = 298.15
    min_temperature_k: float = 250.0
    max_temperature_k: float = 350.0
    max_current_a: float = 10.0
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0
    self_discharge_per_day: float = 0.0
    resistance_temperature_coefficient_per_k: float = 0.0
    ocv_temperature_coefficient_v_k: float = 0.0
    calendar_capacity_loss_per_day: float = 0.0
    cycle_capacity_loss_per_efc: float = 0.0
    calendar_resistance_growth_per_day: float = 0.0
    cycle_resistance_growth_per_efc: float = 0.0
    aging_activation_temperature_k: float = 0.0
    min_capacity_soh: float = 0.1
    rechargeable: bool = True
    evidence_note: str = "Synthetic illustrative inputs; not measured, fitted or qualified."

    def __post_init__(self):
        if not isinstance(self.chemistry, str) or self.chemistry not in CHEMISTRIES:
            raise ValueError("Unknown chemistry; use a catalog identifier or custom")
        for name in ("nominal_capacity_ah", "c1_f", "thermal_capacity_j_k",
                     "thermal_resistance_k_w", "reference_temperature_k",
                     "min_temperature_k", "max_temperature_k", "max_current_a"):
            _positive(getattr(self, name), name)
        for name in ("r0_ohm", "r1_ohm", "self_discharge_per_day",
                     "calendar_capacity_loss_per_day", "cycle_capacity_loss_per_efc",
                     "calendar_resistance_growth_per_day", "cycle_resistance_growth_per_efc",
                     "aging_activation_temperature_k"):
            _positive(getattr(self, name), name, zero=True)
        for name in ("resistance_temperature_coefficient_per_k", "ocv_temperature_coefficient_v_k"):
            _number(getattr(self, name), name)
        for name in ("charge_efficiency", "discharge_efficiency", "min_capacity_soh"):
            if not 0 < _number(getattr(self, name), name) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if not self.min_temperature_k <= self.reference_temperature_k <= self.max_temperature_k:
            raise ValueError("Temperature domain must include the reference temperature")
        _positive(7200*self.nominal_capacity_ah, "capacity conversion to coulombs")
        _positive(self.thermal_capacity_j_k*self.thermal_resistance_k_w, "thermal time constant")
        if self.r1_ohm:
            _positive(self.r1_ohm*self.c1_f, "RC time constant")
        if not isinstance(self.rechargeable, bool):
            raise ValueError("rechargeable must be boolean")
        if not isinstance(self.evidence_note, str) or not self.evidence_note.strip():
            raise ValueError("evidence_note must describe parameter provenance/assumptions")
        if not isinstance(self.ocv_soc_v, (tuple, list)) or not 2 <= len(self.ocv_soc_v) <= 1000:
            raise ValueError("ocv_soc_v must contain 2 to 1000 [SOC, voltage] pairs")
        table = []
        for pair in self.ocv_soc_v:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError("Each OCV row must contain SOC and voltage")
            soc, voltage = _number(pair[0], "OCV SOC"), _positive(pair[1], "OCV voltage")
            if not 0 <= soc <= 1 or (table and soc <= table[-1][0]):
                raise ValueError("OCV SOC coordinates must strictly increase within [0, 1]")
            table.append((soc, voltage))
        if table[0][0] != 0 or table[-1][0] != 1:
            raise ValueError("OCV table must cover SOC=0 through SOC=1")
        object.__setattr__(self, "ocv_soc_v", tuple(table))


@dataclass(frozen=True)
class BatteryState:
    soc: float = 0.5
    temperature_k: float = 298.15
    polarization_v: float = 0.0
    capacity_soh: float = 1.0
    resistance_growth: float = 1.0
    elapsed_s: float = 0.0
    throughput_ah: float = 0.0

    def __post_init__(self):
        if not 0 <= _number(self.soc, "soc") <= 1:
            raise ValueError("soc must be in [0, 1]")
        if not 0 < _number(self.capacity_soh, "capacity_soh") <= 1:
            raise ValueError("capacity_soh must be in (0, 1]")
        if _number(self.resistance_growth, "resistance_growth") < 1:
            raise ValueError("resistance_growth must be >= 1")
        _positive(self.temperature_k, "temperature_k")
        _number(self.polarization_v, "polarization_v")
        _positive(self.elapsed_s, "elapsed_s", zero=True)
        _positive(self.throughput_ah, "throughput_ah", zero=True)


def generic_model(chemistry="custom", **overrides):
    """All labels deliberately share the same synthetic numerical defaults."""
    return BatteryModel(**{"chemistry": chemistry, "rechargeable": chemistry not in _PRIMARY,
                           **overrides})


def ocv(model: BatteryModel, soc: float, temperature_k: float) -> float:
    """Piecewise-linear user OCV curve with a constant optional dU/dT."""
    if not 0 <= _number(soc, "soc") <= 1:
        raise ValueError("SOC outside [0, 1]; OCV extrapolation is forbidden")
    _temperature(model, temperature_k)
    for (s0, v0), (s1, v1) in zip(model.ocv_soc_v, model.ocv_soc_v[1:]):
        if soc <= s1:
            value = v0 + (v1-v0)*(soc-s0)/(s1-s0)
            return _positive(value + model.ocv_temperature_coefficient_v_k *
                             (temperature_k-model.reference_temperature_k), "OCV")
    raise ValueError("SOC not covered by OCV table")


def _temperature(model, value):
    if not model.min_temperature_k <= _number(value, "temperature_k") <= model.max_temperature_k:
        raise ValueError("Temperature outside the declared model domain")


def _resistances(model, state):
    exponent = model.resistance_temperature_coefficient_per_k * (
        model.reference_temperature_k-state.temperature_k)
    if abs(exponent) > 50:
        raise ValueError("Resistance temperature multiplier outside numerical domain")
    factor = state.resistance_growth * math.exp(exponent)
    return (_positive(model.r0_ohm*factor, "effective R0", zero=True),
            _positive(model.r1_ohm*factor, "effective R1", zero=True))


def _phi(x):
    return -math.expm1(-x)/x if x else 1.0


def _rc_step(v0, current, resistance, capacitance, dt):
    if resistance == 0:
        if v0 != 0:
            raise ValueError("Nonzero polarization is invalid when R1=0")
        return 0.0, 0.0, 0.0
    tau = _positive(resistance*capacitance, "RC time constant")
    x = dt/tau
    target = current*resistance
    change = -math.expm1(-x)
    v1 = v0 + (target-v0)*change
    # Write mean(v^2) as mean(v)^2 + variance(v) to avoid cancellation
    # when a pulse starts from v0=0 and dt is much shorter than RC.
    one_minus_phi = (x/2-x*x/6+x**3/24-x**4/120) if x < 1e-3 else 1-_phi(x)
    mean = v0 + (target-v0)*one_minus_phi
    variance = (x*x/12-x**3/12+17*x**4/360-7*x**5/360) if x < 1e-3 else _phi(2*x)-_phi(x)**2
    heat = (mean*mean + (v0-target)**2*variance)/resistance
    return v1, mean, heat


def _advance(model, state, current, ambient, dt):
    r0, r1 = _resistances(model, state)
    vp, mean_vp, rc_heat = _rc_step(state.polarization_v, current, r1, model.c1_f, dt)
    effective_current = current/model.discharge_efficiency if current >= 0 else current*model.charge_efficiency
    rate = effective_current/(3600*model.nominal_capacity_ah*state.capacity_soh)
    decay = model.self_discharge_per_day*dt/86400
    next_soc = state.soc*math.exp(-decay) - rate*dt*_phi(decay)
    if not 0 <= next_soc <= 1:
        raise ValueError("Step crosses empty/full SOC; shorten the profile or change current")
    heat = current*current*r0 + rc_heat - current*state.temperature_k*model.ocv_temperature_coefficient_v_k
    thermal_tau = _positive(model.thermal_capacity_j_k*model.thermal_resistance_k_w, "thermal time constant")
    cooling = -math.expm1(-dt/thermal_tau)
    next_temperature = state.temperature_k + (ambient-state.temperature_k + heat*model.thermal_resistance_k_w)*cooling
    _temperature(model, next_temperature)
    exponent = model.aging_activation_temperature_k * (
        1/model.reference_temperature_k-1/state.temperature_k)
    if abs(exponent) > 50:
        raise ValueError("Aging temperature multiplier outside numerical domain")
    factor = math.exp(exponent)
    efc = abs(current)*dt/(7200*model.nominal_capacity_ah)
    days = dt/86400
    soh = state.capacity_soh-factor*(model.calendar_capacity_loss_per_day*days + model.cycle_capacity_loss_per_efc*efc)
    if soh < model.min_capacity_soh:
        raise ValueError("Capacity SOH falls below declared model domain")
    growth = state.resistance_growth + factor*(model.calendar_resistance_growth_per_day*days + model.cycle_resistance_growth_per_efc*efc)
    result = BatteryState(next_soc, next_temperature, vp, soh, growth,
                          state.elapsed_s+dt, state.throughput_ah+abs(current)*dt/3600)
    # Endpoint OCV trapezoid; refine around OCV knees and thermal feedback.
    mean_ocv = (ocv(model, state.soc, state.temperature_k) + ocv(model, next_soc, next_temperature))/2
    energy = current*(mean_ocv-current*r0-mean_vp)*dt
    return result, _number(energy, "terminal energy"), _number(heat*dt, "generated heat")


def _sample(model, state, time_s, current, energy_j, heat_j):
    _temperature(model, state.temperature_k)
    if state.capacity_soh < model.min_capacity_soh:
        raise ValueError("Capacity SOH below declared model domain")
    r0, _ = _resistances(model, state)
    voltage = ocv(model, state.soc, state.temperature_k)-current*r0-state.polarization_v
    _positive(voltage, "terminal voltage; reversal is unsupported")
    _number(energy_j, "cumulative terminal energy")
    _number(heat_j, "cumulative generated heat")
    return {"time_s": time_s, **asdict(state), "current_a": current,
            "voltage_v": voltage, "ocv_v": ocv(model, state.soc, state.temperature_k),
            "capacity_ah": model.nominal_capacity_ah*state.capacity_soh,
            "equivalent_full_cycles": state.throughput_ah/(2*model.nominal_capacity_ah),
            "terminal_energy_j": energy_j, "generated_heat_j": heat_j}


def _profile(value, count, name):
    if isinstance(value, Real):
        return [_number(value, name)]*count
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != count:
        raise ValueError(f"{name} must be a scalar or contain exactly {count} interval values")
    return [_number(item, name) for item in value]


def simulate(model: BatteryModel, times_s, currents_a, ambient_k=298.15,
             initial_state: BatteryState | None = None, *, max_step_s=10.0):
    """Return JSON-safe samples; N times and N-1 zero-order-held interval inputs.

    Samples at knots use the right-hand interval current, except the final
    sample uses the last interval. No partial result is returned on failure.
    """
    if not isinstance(model, BatteryModel):
        raise ValueError("model must be a BatteryModel")
    if not isinstance(times_s, Sequence) or isinstance(times_s, (str, bytes)) or not 2 <= len(times_s) <= MAX_SAMPLES:
        raise ValueError(f"times_s must contain 2 to {MAX_SAMPLES} values")
    times = [_number(value, "time_s") for value in times_s]
    if times[0] < 0 or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("times_s must be nonnegative and strictly increasing")
    max_step_s = _positive(max_step_s, "max_step_s")
    currents = _profile(currents_a, len(times)-1, "currents_a")
    ambients = _profile(ambient_k, len(times)-1, "ambient_k")
    for current in currents:
        if abs(current) > model.max_current_a:
            raise ValueError("Current exceeds declared model domain")
        if current < 0 and not model.rechargeable:
            raise ValueError("Charging is disabled for this primary-cell model")
    for ambient in ambients:
        _temperature(model, ambient)
    counts = []
    for a, b in zip(times, times[1:]):
        ratio = (b-a)/max_step_s
        if not math.isfinite(ratio) or ratio > MAX_STEPS:
            raise ValueError("Study exceeds bounded internal step budget")
        counts.append(max(1, math.ceil(ratio)))
    if sum(counts) > MAX_STEPS:
        raise ValueError("Study exceeds bounded internal step budget")
    state = initial_state if initial_state is not None else BatteryState(temperature_k=model.reference_temperature_k)
    if not isinstance(state, BatteryState):
        raise ValueError("initial_state must be a BatteryState")
    if model.r1_ohm == 0 and state.polarization_v != 0:
        raise ValueError("Nonzero polarization is invalid when R1=0")
    initial = asdict(state)
    energy_j = heat_j = 0.0
    samples = [_sample(model, state, times[0], currents[0], energy_j, heat_j)]
    try:
        for index, count in enumerate(counts):
            dt = _positive((times[index+1]-times[index])/count, "internal timestep")
            for _ in range(count):
                state, energy, heat = _advance(model, state, currents[index], ambients[index], dt)
                energy_j += energy
                heat_j += heat
                _sample(model, state, times[index+1], currents[index], energy_j, heat_j)
            next_current = currents[min(index+1, len(currents)-1)]
            samples.append(_sample(model, state, times[index+1], next_current, energy_j, heat_j))
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("Parameters exceed the numerical domain; rescale the model/profile") from exc
    return {"schema": "spikes/battery-study/v1", "model_status": "approximate_unqualified",
            "model": asdict(model), "initial_state": initial, "final_state": asdict(state),
            "times_s": times, "currents_a": currents, "ambient_k": ambients,
            "max_step_s": max_step_s, "internal_steps": sum(counts),
            "limitations": list(LIMITATIONS), "samples": samples}
