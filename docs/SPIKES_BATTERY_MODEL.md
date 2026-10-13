# Prescribed-current battery reference study

`python/spikes/battery.py` implements an original, reduced-order, single-cell
reference model. Its result status is always `approximate_unqualified`.
It is **not a battery device in the native SPIKES circuit/MNA solver**. A
current profile is supplied; the model does not solve a connected circuit,
charger, BMS, pack, or load-control loop. No external dependency is added.

## Chemistry labels and evidence boundary

`CHEMISTRIES` enumerates lithium-ion NMC/NCA/LCO/LMO/LFP/LTO, lithium polymer,
solid-state lithium, lithium-sulfur, lithium metal, primary lithium,
zinc-carbon, alkaline, zinc-air, zinc-ion, sodium-ion, sodium-sulfur,
nickel-cadmium, nickel-metal hydride, nickel-iron, lead-acid flooded/AGM/gel,
silver oxide, silver-zinc, aluminum-air, iron-air, other metal-air, flow and
custom identifiers. These are configurable template labels, not implemented
chemistry-specific reaction mechanisms. No finite catalog covers all battery
chemistries, electrode combinations, construction variants or future cells.

Every `generic_model()` deliberately starts with the **same synthetic 1 Ah,
3-to-4 V OCV table** and illustrative resistance/thermal values, regardless of
label. These values do not represent the selected chemistry or a purchasable
cell. Defaults omit aging, self-discharge, entropy and temperature dependence
(coefficients zero); this means those effects have not been parameterized,
not that an actual cell has none. The evidence note is retained in results.

Primary labels disable charging by default. A custom `rechargeable` declaration
is a user modeling assumption, not permission to charge a real cell. Chemistry
labels do not establish safe operating temperatures, voltage thresholds,
charging regimes, reversibility or suitability of an equivalent-circuit model.
For example, the default temperature interval is not a sodium-sulfur operating
envelope; that requires explicit cell-specific parameters and validation.

Replace the table and constants using traceable, condition-specific test data
before interpreting results physically. Merely changing `evidence_note` does
not promote model status. Capacity, thermal properties, pulse-fit resistance,
time constants, current/temperature domain and aging parameters all require
independent evidence. No measured dataset or manufacturer parameters are bundled.

## API and units

```python
from spikes.battery import BatteryState, generic_model, simulate

model = generic_model(
    "lithium_ion_lfp",
    evidence_note="Illustrative only; all values must be replaced by cell data.",
)
result = simulate(
    model,
    times_s=[0, 60, 120],
    currents_a=[1.0, 0.0],
    ambient_k=298.15,
    initial_state=BatteryState(soc=0.8),
    max_step_s=1.0,
)
last = result["samples"][-1]
print(last["voltage_v"], last["soc"], last["temperature_k"])
```

With the repository root on the import path, use `python.spikes.battery` instead.
`BatteryModel` and `BatteryState` are immutable dataclasses; use
`dataclasses.replace` for variations. The OCV table is converted to immutable
tuples so later changes to the caller's input list cannot change a run.

- Positive current discharges; negative current charges. Time is seconds,
  temperature kelvin, voltage volts, current amperes, resistance ohms, thermal
  capacity J/K, thermal resistance K/W, and RC capacitance farads.
- `nominal_capacity_ah` is beginning-of-life capacity in ampere-hours.
  `capacity_soh` is its remaining fraction. `resistance_growth` is a multiplier
  starting at one. Efficiencies are coulombic, not power-conversion efficiencies.
- `ocv_soc_v` has 2-1000 strictly increasing SOC coordinates covering exactly
  0 through 1, with positive voltages. Voltage need not be monotonic; no
  extrapolation is allowed. SOC is a fraction, not a percentage.
- `times_s` has N increasing nonnegative timestamps, and interval current and
  ambient inputs have N-1 elements or are scalars. Inputs are constant within
  each interval, not linearly interpolated. At interior knots voltage/current
  samples use the new, right-hand current. The last sample uses the last current.
- `elapsed_s` accumulates duration from the initial state independently of the
  timestamp origin. Resume with `BatteryState(**result["final_state"])`.
  Energy totals restart at zero each call; elapsed time and throughput continue.
- Result schema `spikes/battery-study/v1` retains model, state, original interval
  inputs, step setting/count, limitations, and JSON-safe samples. Samples expose
  voltage, OCV, SOC, temperature, SOH, available Ah, polarization, resistance
  growth, throughput, equivalent full cycles, terminal energy and generated heat.

## Independent formulation

Let `I > 0` discharge, `z` be fractional SOC, `s` be capacity SOH, `g` the
resistance-growth multiplier, and `Tref` the reference temperature.

```text
Q_C = 3600 Qnom_Ah s
Ieffective = I / eta_discharge  (I >= 0)
           = I eta_charge     (I < 0)
dz/dt = -Ieffective/Q_C - kself z / 86400
Rj = Rj_reference g exp(alpha_R (Tref - T)), j = 0,1
dvp/dt = (I - vp/R1)/C1
U = linear_interpolation(OCV_table, z) + beta (T - Tref)
Vterminal = U - I R0 - vp
Pheat = I^2 R0 + vp^2/R1 - I T beta
Cthermal dT/dt = Pheat - (T - Tambient)/Rthermal
```

`beta` is the optional constant `dU/dT` in V/K. Its reversible heat term follows
the discharge sign convention: reaction free-energy release gives electrical
work per charge `U`; differentiating free energy with temperature gives
entropy transfer, hence outward reaction heat `-I T dU/dT`. Both reversible
cooling and heating are possible. Defaults set beta to zero.

Ohmic and RC heating follow resistor power, not simply `I*(U-V)`: multiplying
`C1 dvp/dt = I - vp/R1` by `vp` gives
`I vp = d(C1 vp^2/2)/dt + vp^2/R1`. Thus some polarization work changes stored
RC energy, rather than instantaneously becoming heat. For fixed parameters,
constant OCV and no entropy/chemical-loss terms, the oracle verifies
`integral(I U dt) = terminal_energy + resistor_heat + change(RC_energy)`.
This is a circuit-model identity, not a measured cell energy balance.

For each internal substep, beginning-of-step capacity/resistance/temperature
coefficients are frozen. Integrating the linear SOC equation yields
`z1 = z0 exp(-k dt) - (Ieffective/Q_C) dt phi(k dt)`, with
`phi(x) = (1-exp(-x))/x` and `phi(0)=1`.
The RC update is `vp1 = I R1 + (vp0-I R1) exp(-dt/(R1 C1))`.
Its mean voltage and mean squared voltage are evaluated analytically. The
mean-square expression is organized as squared mean plus nonnegative variance;
small-argument Taylor series avoid catastrophic cancellation when `dt << RC`.
`R1=0` explicitly disables polarization and requires zero initial polarization.

Thermal evolution uses the exact scalar constant-power exponential for the
substep's average resistor heat and beginning-of-step reversible heat. This
averaging is not the exact convolution of a varying RC heat pulse with thermal
decay; it converges with substep refinement. Terminal energy integrates the
analytic mean polarization, constant ohmic drop and endpoint OCV trapezoid.
OCV knees, self-discharge, temperature changes and feedback require refinement.

The explicit empirical degradation law is:

```text
dEFC = abs(I) dt / (7200 Qnom_Ah)
dDays = dt / 86400
A(T) = exp(Tactivation (1/Tref - 1/T))
s1 = s0 - A(T) (kcalendar_capacity dDays + kcycle_capacity dEFC)
g1 = g0 + A(T) (kcalendar_resistance dDays + kcycle_resistance dEFC)
```

Coefficients are nonnegative capacity fractions or resistance-multiplier
increments per day/EFC. `Tactivation` is an activation-temperature parameter
in kelvin, not an energy. Throughput is absolute terminal Ah; one full
charge/discharge pair is one EFC at nominal capacity. Rates do not depend on
SOC, C-rate, depth of discharge or elapsed age except through temperature.
Capacity loss proportionally removes available charge while preserving the
post-coulomb-count fractional SOC; subsequent steps use the diminished capacity.
That convention is explicit, not a lithium-inventory or side-reaction model.
Empirical aging must not be interpreted as universal chemistry behavior.

## Evidence, provenance and excluded physics

The network equations, integrations, series, implementation and synthetic
oracles are independently authored. No external implementation, text, data,
fitted parameters or tests were copied, translated or adapted. The primary
research context [Richardson and Korotkin, *Heat Generation and a Conservation
Law for Chemical Energy in Lithium-ion Batteries*](https://arxiv.org/abs/2104.01590)
(DOI `10.1016/j.electacta.2021.138909`) identifies that full electrochemical
energy accounting requires mechanisms beyond a simple terminal-loss formula.
This implementation does not implement that paper's DFN equations or claim
its validation. The exact method implemented here is the explicitly derived
RC network plus lumped thermal/empirical degradation closure above.

Self-discharge, coulombic inefficiency and capacity degradation alter stored
charge without a reaction-energy model. Their heat is **not** accounted for.
Generated heat can therefore not establish full chemical energy conservation.
The model also excludes electrochemical diffusion, hysteresis, phase changes,
lithium plating, dendrites, thermal runaway, abuse, gas evolution, oxygen and
reactant transport, Peukert/rate capacity, spatial temperature fields, pack
imbalance, BMS switching and flow-battery pumping/auxiliaries. No safety,
certification, manufacturing or remaining-life conclusion is supported.

## Admission, conditioning and verification

NaN/infinity, booleans used as numbers, invalid efficiencies, malformed tables,
negative resistances/rates, unknown chemistry identifiers, non-increasing time,
profile-length mismatches and invalid state are rejected. Current, ambient and
cell temperature must stay inside user-declared model domains. Terminal voltage
reversal, empty/full SOC crossing and SOH below `min_capacity_soh` fail without
returning a partial result. SOC is never silently clipped. The caller should
shorten the profile/step or change its current, not ignore a domain error.
The temperature/current domains are mathematical admission limits, not cell
protection specifications. Extreme finite inputs can exceed the numerical
domain; these fail explicitly. Exponential multipliers are limited to exponent
magnitude 50. Positive time constants/coulomb conversion must remain finite.

At most 100001 output times and 200000 internal steps are admitted. Runtime and
memory are linear in those bounds; no dense solve or new runtime is required.
`max_step_s` controls internal coupling resolution without increasing output
samples. The UI must bound its request and avoid large studies on its event
thread. The pure API does not itself provide cancellation or background jobs.

Run `python -m unittest tests.python.test_spikes_battery -v` from the repository
root. Synthetic tests cover exact Coulomb counting/energy, efficiencies, RC
pulse/rest and its energy identity, short-step conditioning, analytic lumped
thermal heating/cooling, self-discharge, calendar/cycle degradation, entropic
sign, interpolation, domain errors, JSON serialization, deterministic restart
and chemistry-label honesty. A coupled temperature/aging fixture checks
monotonically falling errors at 2, 1 and 0.5 s against a 0.025 s numerical
reference; it is convergence evidence, not measured physical correlation.
Analytic fixtures use approximately 1e-11 absolute tolerance in their stated
SI observables (or explicitly tighter small-signal tolerances in the test).
Numerical changes require knowledgeable human review before release.
