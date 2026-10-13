# SPICE faults, reliability scenarios and environment exposure

The internal persistent engine and compiled-board objects expose named,
bounded parameter faults. [Native fault semantics](INTERNAL_SPICE_FAULTS.md)
and [compiled-board API](COMPILED_BOARD_LIBRARY.md) define the electrical
implementation. This document defines the separate scenario/event layer.
It does not establish complete ngspice parity or physical failure prediction.

## Electrical failure representation

| Requested mechanism | Admitted circuit change | Interpretation and limit |
| --- | --- | --- |
| Gate-source short | Reduce an explicitly provisioned gate/source shunt resistor | Finite bridge resistance; no gate-oxide fracture geometry or unmodeled damage |
| Body-diode short | Reduce the shunt across the modeled junction; D/S in the example with body tied to source | Conductive bypass, not a new reverse-recovery, avalanche or burnout model; independent bulk requires the corresponding junction terminals |
| Degraded short/leakage | Use an intermediate finite shunt resistance | Healthy high-resistance leakage is included in the baseline; no ideal open/zero-ohm substitution |
| Degraded Vgs threshold | Change an admitted NMOS Level-1 VTO parameter | Parameter shift within this compact model; PMOS, WBG and arbitrary vendor-model mutation remain unsupported |
| Aging/environment impacts | Apply supplied bounded local parameter deltas, or schedule a selected failure mode | No automatic device coefficients or physical failure-mode allocation |

Outputs remain the last accepted electrical solution until the next step. Clearing
a fault restores its declared healthy value at the current time; restoring a
checkpoint also restores physical state and clock. Those operations are distinct.

## FIT and bathtub scenarios

`python.spikes.reliability` takes supplied operating age/duration in **hours**.
One FIT is one failure per billion device operating hours, so the constant hazard
is `FIT * 1e-9 / hour`. This unit definition follows
[TI reliability terminology](https://www.ti.com/quality-reliability/reliability/terminology.html).
It does not identify whether a failed part suffers a short, open or threshold shift.

The implemented competing-hazard scenario independently sums three cumulative
terms: early-life Weibull (`shape < 1`), constant FIT and wear-out Weibull
(`shape > 1`). For each supplied Weibull scale `eta` and shape `beta`,
`H(t) = weight * (t/eta)^beta`; constant FIT contributes `FIT * 1e-9 * t`.
An explicit scenario multiplier scales the total hazard. This is one chosen
parametric scenario, not a universally fitted bathtub lifetime law. See
[NIST's bathtub discussion](https://www.itl.nist.gov/div898/handbook/apr/section1/apr124.htm)
and [Weibull model](https://www.itl.nist.gov/div898/handbook/apr/section1/apr162.htm).

For a surviving device aged `a`, conditional event probability over `d` hours is
`1 - exp(-(H(a+d)-H(a)))`. `expm1`, logarithms and close-interval evaluations avoid
losing tiny probabilities or subtracting nearly equal powers. The early-life
instantaneous rate is singular at age zero; reports return null with a reason
while finite interval probabilities remain available. Overflow is rejected;
binary64 underflow can make physically negligible terms zero.

`failure_delay_hours()` inverts a supplied conditional quantile on a finite
horizon with bounded bisection. A quantile is explicit to permit exact replay;
no implicit random seed/state or platform RNG is introduced. `None` means the
selected event is beyond that horizon. `event_from_hazard()` converts hours to
electrical seconds using 3600 s/hour, with no silent aging acceleration.
The supplied hazard must already be allocated to the selected mode. A total
part FIT must not be reused for every individual short mode.

`arrhenius_acceleration()` computes
`exp(Ea/k * (1/Tref - 1/T))` from supplied positive Kelvin temperatures and a
supplied activation energy in eV, with `k = 8.617333262145e-5 eV/K`.
[NIST describes Arrhenius acceleration](https://www.itl.nist.gov/div898/handbook/apr/section1/apr151.htm).
The coefficient is mechanism-specific; multiplying a whole bathtub curve by
that factor is an explicitly chosen scenario, not automatic lifetime evidence.

## Supplied hazardous-environment response

`environment_faults.ParameterResponse` applies one local linear response:
`parameter = baseline + coefficient * (exposure-reference)`.
Supported exposure axes are temperature (K), cumulative silicon-referenced
ionizing dose (`rad(Si)`), relative humidity (fraction), and specified vibration
RMS acceleration (`g`). Outputs are named resistance (ohm) or threshold (V)
fault-site values. All coefficients, calibration intervals and baselines are
supplied; none is inferred from component family or the hazard name.

Every response binds exact part number and manufacturer, source locator,
conditions and applicability basis. Ordering suffixes remain significant.
Out-of-range exposure, conflicting identity, invalid final resistance and
nonfinite values are rejected without clamping. Unreviewed scenarios remain
`unverified_scenario`; a reviewed mapping is only
`conditional_calibrated_mapping`, not source authentication or device qualification.
For dose, the conditions/applicability must address lot, bias, dose rate,
temperature, annealing and electrical endpoint. `rad(SiO2)`, fluence and unspecified
rad cannot be reinterpreted as `rad(Si)`.

Applying a response also requires the target's declared `FaultSite` to agree
with its V/ohm unit and immutable healthy baseline; validation precedes mutation.

`combined_response()` adds local deltas for distinct axes sharing one site, unit
and baseline. It rejects duplicate axes rather than double-counting. Reapplying
the same exposure starts from the immutable baseline and does not accumulate
the same dose twice. Nonlinear combined-stress interactions are unvalidated.
The model does not compute heat feedback, vibration spectra/fatigue, corrosion,
pressure, chemical attack, radiation transport or annealing.

NASA's [power-MOSFET radiation guideline](https://nepp.nasa.gov/files/16408/08_163_4_JPL_Scheick.pdf)
distinguishes accumulated-dose parameter degradation from destructive
single-event effects and stresses test conditions. No generic SEE cross section,
particle spectrum or destructive-event rate is supplied by this implementation.
Users can schedule an explicit what-if short, but cannot label it a radiation
failure prediction without applicable measurements and a separate rate model.

## Deterministic co-simulation campaigns

`FaultCampaign(target, sites, events, ...)` works with a compiled `Board` or
`NativeFaultTarget(session, sites)`. It prevalidates an ordered finite schedule,
advances within declared step/count limits, splits steps at event boundaries,
and records scheduled/applied times. Events are applied before the next solve;
there is no wall-clock/HIL guarantee. Roundoff tolerance is expressed in ULPs.
Consumers must use steps and sites that agree with the target's own bounds.

```python
from python.spikes.fault_campaign import FaultCampaign, FaultEvent

campaign = FaultCampaign(board, fault_sites,
    [FaultEvent(1e-3, "gate_short", 10.0),
     FaultEvent(2e-3, "gate_short", None)], maximum_step_s=1e-5)
campaign.save()
campaign.advance_to(3e-3)
campaign.restore()  # electrical state, parameters, clock and event cursor replay
```

The campaign owns the target's single saved slot; outside callers must not
replace it. The native adapter owns its saved checkpoint, not its session;
call `close()` to release it. The whole campaign is not transactional: failed
advancement retains prior accepted steps/events and surfaces the error. The
engine preserves state on a failed step. No user callbacks run during commit.
The separate general scalar co-simulation master is not automatically connected
to these objects; its adapters and coupling validation remain a distinct boundary.

## Evidence and provenance

`test_spikes_reliability.py` independently checks FIT units, power-law integrals,
interval composition, tiny-duration/quantile numerics, bathtub shape, acceleration,
identity/bounds and combined exposure without duplicate damage.
`test_spikes_fault_campaign.py` checks scheduling/replay and actual native RC
response plus synthetic dose/VTO/current behavior. Synthetic inputs are
explicitly labeled and establish arithmetic, not hardware correlation.

`examples.compiled_board_faults.qualify_ngspice` compares five static scenarios
with actual ngspice 46, separately constructed native sessions and a generated
board DLL. The retained [reference report](validation/spikes-fault-ngspice46-2026-10-10.json) records
engine/executable hashes, exact equivalent decks and a 1 microvolt tolerance;
all five pass. The actual C++ consumer and 20 compiled-board regressions also
pass. This does not establish cross-engine transient fault timing or arbitrary
compact-model mutation. See the [reproducible example](../examples/compiled_board_faults/README.md).

The probability equations follow survival of independent competing hazards;
the local parameter mapping is a supplied first-order response, not an imported
damage algorithm. Source, fixtures, derivations and oracles are independently
authored. No external source code, device measurements or third-party models
were copied. Numerical human review before release remains required.
