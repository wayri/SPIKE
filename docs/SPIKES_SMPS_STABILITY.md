<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native ideal CCM SMPS stability analysis

`src/spikes/smps_stability.cpp` executes the supplied-parameter analytical model
in C++. `python/spikes/smps_stability.py` remains an explicitly selected test
reference. Neither is a periodic operating-point extractor, automatic circuit
linearizer, or universal SMPS qualification suite. It covers ideal buck, boost,
inverting buck-boost, and single-output flyback stages in continuous conduction
mode (CCM), with voltage-mode negative feedback and a rational PI/type-II/type-III
compensator. A completed result remains `model_status="approximate"`.

## Workflow and API

In Studio, open **Frequency > SMPS stability**. Enter the ideal power stage and
compensator parameters, select **C++ native** (the default), choose **Analyze model**, then select Loop/Plant Bode,
Nyquist or Poles/zeros. The floating window uses a bounded background worker;
invalid inputs retain the prior graph with a diagnostic. Setup can be saved as
one undoable project-metadata change without changing the circuit. Export writes
the completed analytical result including its exact resolved configuration.

CLI: `python -m python.spikes smps-stability --default-config` emits a template.
Use `--library path/to/spikes_c_api.dll --config setup.json -o report.json`
to run the native kernel. On Linux select the built shared library instead.
`--backend reference` explicitly selects the Python reference; a missing native
library or ABI never triggers a silent fallback. Duplicate fields and malformed
inputs are rejected; the output cannot overwrite the input setup. Executable
5 W, 1 kW, 1 MW and isolated-flyback studies are under
`examples/spikes/smps_stability`; none is a construction-ready converter.

```python
from python.spikes.smps_stability import default_config, validate
from python.spikes.native_smps import analyze

config = default_config()
config.update(topology="buck", controller_gain=5.0)
validated_inputs = validate(config)  # Normalizes inputs only; no model execution.
result = analyze(validated_inputs, library="build-spikes-native-analysis-20261013/Release/spikes_c_api.dll")
print(result["stability"], result["margins"])
```

`default_config()` returns a new dictionary. `validate(config)` and
`analyze(config)` accept partial dictionaries over these defaults; neither
mutates the caller. Unknown keys are rejected so parasitics cannot silently be
ignored. Invalid inputs or a rejected CCM point raise `ValueError`; no stale or
partial result should replace an earlier completed UI result. The Studio
integration runs analysis in a background worker and labels this as an
analytical study, independently of the active deck. The default gain of 100 is
deliberately not a tuned recommendation: its buck model is unstable. Gain 5
produces a mathematically stable example with three unity-gain crossings.

| Input | Meaning |
| --- | --- |
| `topology` | `buck`, `boost`, `buck_boost`, or `flyback` |
| `input_voltage_v`, `duty_cycle` | Positive DC source voltage and fixed equilibrium duty |
| `inductance_h` | Inductor value; primary magnetizing inductance for flyback |
| `capacitance_f`, `load_resistance_ohm` | Ideal output capacitor and positive resistive load |
| `switching_frequency_hz` | Used for the ripple/CCM screen and averaging warning, not a sampled PWM model |
| `turns_ratio` | Flyback `Ns/Np`; must equal 1 for other stages |
| `controller_type` | `pi`, `type_ii`, or `type_iii` |
| `controller_gain` | Positive integral coefficient K in the explicitly defined transfer below |
| `zero1_hz`, `zero2_hz`, `pole1_hz`, `pole2_hz` | Positive compensator break frequencies; unused second fields remain inert |
| `feedback_gain`, `pwm_gain` | Positive scalar sensor and duty/modulator gains |
| `start_hz`, `stop_hz`, `points` | Increasing positive logarithmic display sweep and integer 3..10000 samples |

Numbers must be finite real values, excluding booleans, within `[1e-12,1e12]`.
Duty is further limited to `[1e-6,1-1e-6]`; this is a numerical boundary, not a
controller timing guarantee. Physical feasibility is not inferred from numeric
admission. The ratio between retained model damping/resonance and controller
break rates cannot exceed `1e10`; extreme values require a better-conditioned
specialized calculation rather than unqualified extrapolation.

The JSON-safe result includes normalized `config`, `frequency_hz`, `plant` and
`loop` arrays of `[real, imaginary]` pairs, and separate gain-dB and continuous
phase-degree arrays. It also includes equilibrium voltage/current/power,
estimated ripple and CCM admissibility, state-space matrices, plant DC gain,
plant and closed-loop poles and plant zeros in rad/s, rational polynomial
coefficients, all numerically resolved finite positive model crossings,
`stability`, `warnings`, and `limitations`. Empty margin lists do not certify
infinite gain or phase margin. Crossing entries identify whether they are
inside the displayed sweep and below the `fs/10` screening limit.

## Independent averaged derivation

Use state `x=[i,v]`, positive output magnitude `v`, `q=1-d`, turns `n=Ns/Np`,
and ideal constants `L,C,R,Vin`. For inverting buck-boost the actual output is
`-v`; its controller must sense magnitude with the appropriate physical
feedback polarity. Flyback state `i` is primary-referred magnetizing current,
not the discontinuous physical primary-terminal current.

Time-weighting the two ideal switch states gives:

| Stage | `L di/dt` | `C dv/dt` | Equilibrium `V` |
| --- | --- | --- | --- |
| Buck | `d Vin-v` | `i-v/R` | `d Vin` |
| Boost | `Vin-q v` | `q i-v/R` | `Vin/q` |
| Inverting buck-boost magnitude | `d Vin-q v` | `q i-v/R` | `d Vin/q` |
| Flyback magnitude | `d Vin-q v/n` | `q i/n-v/R` | `n d Vin/q` |

Define `k=1` for buck and `k=q/n` otherwise (`n=1` outside flyback).
All four yield `I=V/(R k)`. The linearized state matrix is
`A=[[0,-k/L],[k/C,-1/(R C)]]`. The duty input column is:

| Stage | `B_i` | `B_v` |
| --- | --- | --- |
| Buck | `Vin/L` | `0` |
| Boost | `V/L` | `-I/C` |
| Inverting buck-boost magnitude | `(Vin+V)/L` | `-I/C` |
| Flyback magnitude | `(Vin+V/n)/L` | `-I/(n C)` |

The observation is `[0,1]`, with no feedthrough. Direct inversion of `sI-A`
therefore gives the exact transfer for this averaged model:

`Gvd(s) = [B_v s + k B_i/C] / [s^2 + s/(R C) + k^2/(L C)]`.

This preserves the RHP zero rather than treating it as a compensating LHP
zero. Its angular frequency is `R q^2/L` for boost and
`R q^2/(d L n^2)` for flyback/buck-boost. Buck has no finite zero. The DC
duty derivative is `Vin` for buck, `Vin/q^2` for boost/buck-boost and
`n Vin/q^2` for flyback. The equilibrium reference voltage is explicitly
`feedback_gain*V`; this is not an assertion that an arbitrary requested setpoint
can be achieved at the supplied duty.

## Compensator and stability calculation

Let each break angular frequency be `w=2*pi*f`. The compensator is
`Gc(s)=K/s * product(1+s/wz) / product(1+s/wp)`.
PI uses one zero and no finite pole, type II one zero and one pole, and
type III two zeros and two poles. `K` is the integral coefficient, not an
unlabelled dB gain. With error voltage and controller output voltage units,
K has units 1/s, feedback is V/V and PWM gain is duty/V. More generally their
product must make the return ratio dimensionless.

`T=Gvd Gc feedback_gain pwm_gain` uses negative feedback. Closed-loop poles
are the roots of the *uncancelled* polynomial `D_T+N_T`; retaining factors
prevents a pole-zero cancellation from concealing internal modes. Pole signs,
not a selected phase margin, determine `stable`, `unstable`, or
`marginal_or_unresolved`. A pole real part within
`1e-8*max(plant_resonance_rad_s,abs(pole))` of the imaginary axis remains
unresolved. Even `stable` is scoped only to this continuous-time averaged
model and cannot certify switching-loop or hardware stability.

Computations use `x=s/plant_resonance_rad_s` to reduce dimensional coefficient
spread. Root backward residuals must not exceed `1e-7` relative to the
absolute-coefficient polynomial at the root magnitude. Gain candidates solve
`|N(jx)|^2-|D(jx)|^2=0` as a real polynomial in `x^2`. Negative-real-axis
candidates solve `Im[N(jx)conj(D(jx))]/x=0` in the same variable and are then
filtered by the actual negative real response. Candidate response residuals
are checked to `1e-5`; near-real roots use relative imaginary tolerance
`1e-7` and duplicate frequencies-squared use relative `1e-6`. Multiple or
near-tangent roots can be ill-conditioned even with small backward error;
these numerical tolerances are not rigorous root-interval certificates.
Crossings are independent of the displayed logarithmic grid, including
crossings outside that range. No sampled unwrap or first-crossing shortcut
is used. Model phase is assembled from the known factor branches.

## CCM, ripple and applicability

The ideal current ripple estimate is `di_pp=(Vin-V)*d/(L fs)` for buck and
`Vin*d/(L fs)` otherwise. The valley `I-di_pp/2` must exceed
`1e-9*max(I,di_pp)`; boundary/DCM points are rejected. This is a conventional
small-ripple screen, not a switched periodic solution. Capacitor ripple is
estimated by `di_pp/(8 fs C)` for buck and `V*d/(R fs C)` for the other
stages. Large ripple warnings start at 50% current ripple and 5% voltage
ripple; these are screening prompts, not validated hardware limits.

Sweeps or gain crossings above `fs/10` warn that averaged high-frequency
response is illustrative. No universal accuracy threshold is established
even below that limit. ESR/DCR are explicitly excluded rather than appended
as inconsistent pole/zero corrections. Other exclusions include switching
losses, current-mode inner loops, sampling/subharmonic behavior, delay, dead
time, discontinuous/burst modes, input filters, nonlinear loads, leakage,
opto-isolator dynamics, clamps, duty saturation, startup, protection, and
thermal/component/EMI qualification. A few-watt, kilowatt, or megawatt
parameter set is only a mathematical scaling exercise; especially a flyback
scaling does not imply a physically suitable high-power architecture.

## Provenance and verification

Method references (consulted 2026-10-12):

- [TI SLVA274A, voltage-mode boost small-signal analysis](https://www.ti.com/lit/pdf/slva274a),
  Appendix A: state-space averaging; ideal-limit double pole and RHP-zero
  invariants provide a comparison, not a TPS61030 controller implementation.
- [TI SLVAFK6, flyback topology](https://www.ti.com/document-viewer/lit/html/SLVAFK6/GUID-0B3C241B-688B-44BB-847B-682F017BB8A9),
  equations 1 and 4: ideal-limit CCM conversion ratio and primary-inductance,
  turns-ratio-dependent RHP zero.

Clean-room statement: the equations above were derived from the ideal switch
states; code, prose, and synthetic test fixtures are original SPIKE material.
No vendor source implementation, diagrams, test data, or compact model was
copied or adapted. Citations establish method lineage, not redistribution
rights or device qualification.

Reproduce software checks with:

```powershell
python -m unittest tests.python.test_spikes_smps_stability -v
```

The original tests check DC conversion and power balance for all topologies,
pole/zero invariants, finite differences of independently written on/off
equations, DC derivative sensitivity, direct state-space frequency response,
controller factor products, the independent cubic Routh stability inequality
for PI/buck, multiple exact crossings under display-grid refinement, invalid
inputs, DCM rejection, strict JSON finiteness, and mathematical power scaling.
These are analytical/software evidence. Switched-transient comparison,
controller/vendor-specific comparison, measured-loop correlation, robustness
over component corners, and knowledgeable human numerical release review
remain outstanding.
