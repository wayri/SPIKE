# Explicit steady CCM converter blocks

SPIKE's `smps_converter.evaluate_smps_converter` evaluates a user-declared
synchronous buck, synchronous boost, or synchronous inverting buck-boost block.
This is an **approximate steady operating estimate**, with software verification
against original analytical examples. It is not measured device validation,
switching transient simulation, controller synthesis, or release qualification.
Numerical changes require knowledgeable human review before release.

## Workflow and contract

Declare an input voltage, regulated output voltage, output current magnitude,
frequency, two MOSFET groups, and one inductor. Output voltage is negative for
the inverting topology and positive otherwise. Every numerical value is SI.
Use supplied operating-temperature Rds(on) and DCR values. Explicit zeros denote
an idealized or omitted term; they are not a device characterization.

The `on` group conducts during fraction D and the `off` group during 1-D. For
buck these are the high-side and synchronous rectifier groups. For boost these
are the ground switch and output rectifier groups. For inverting buck-boost
these are the input and output transfer groups. A group has identical devices
arranged as `parallel_count` identical strings of `series_count` devices. Its
`devices` list must identify every device by `(occurrence_id, component_ref)`.
Voltage and current sharing are explicitly assumed equal. A reference repeated
on another board occurrence is distinct. Reusing the same pair is rejected.

The request schema is [smps-converter-request-v1.schema.json](../schemas/smps-converter-request-v1.schema.json).
All fields are mandatory and unknown fields fail admission. The kernel does not
infer wiring, device models, pads, ratings or board membership from references.
An integration layer must resolve those identities before using a block in a
board path. A bare series MOSFET or diode rectifier requires a different model;
it does not satisfy this two-switch CCM contract.

For a runnable synthetic example and its expected values:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_smps_converter -v
```

`tests/python/test_smps_converter.py::request` constructs a complete request.
The core API returns a JSON-compatible dictionary; `SmpsConverterError.code`
is a stable diagnostic for the service boundary. This module adds no dependency.
JSON Schema checks use the project's existing `jsonschema` test dependency.

## Independent derivation

Let `T=1/fs`, phase lengths `t1=D*T`, `t2=(1-D)*T`, output magnitude `Vo`,
and phase resistances `Rj=Rinductor + Rds_on*series_count/parallel_count`.
The following ideal source voltages appear across each phase's series RL path:

| Topology | On voltage E1 | Off voltage E2 | Output charge balance | Conduction input current |
| --- | --- | --- | --- | --- |
| Buck | Vin-Vo | -Vo | Io=D*m1+(1-D)*m2 | D*m1 |
| Boost | Vin | Vin-Vo | Io=(1-D)*m2 | D*m1+(1-D)*m2 |
| Inverting buck-boost | Vin | -Vo | Io=(1-D)*m2 | D*m1 |

Here `mj` is the current averaged over that phase, not over the full cycle.
Each interval satisfies `L di/dt = Ej-Rj*i`. On normalized interval `u=t/tj`,
write `i(u)=sum(c[k]*u^k)`, where

```text
c[0] = initial current
c[1] = (Ej-Rj*c[0])*tj/L
c[k] = -(Rj*tj/L)*c[k-1]/k, k >= 2
phase mean = sum(c[k]/(k+1))
phase mean square = sum(c[a]*c[b]/(a+b+1))
```

Linearity determines the initial current from output charge balance at each
trial duty: compute the response from zero initial current and the homogeneous
response from unit initial current, then solve the scalar affine load equation.
The outer solve sets the sum of both phase current increments to zero. This
avoids dividing by `1-exp(-R*T/L)` and remains conditioned as R tends to zero.
The squared-current integral retains ripple loss rather than replacing RMS
current by its average. No sampled waveform is returned or interpreted as a
switching transient.

Duty is scanned over `[1e-6, 1-1e-6]` using 256 equal cells. The first
negative-to-positive residual bracket is bisected at most 64 times. Bracket
width must reach the floating-point termination threshold (2e-15); the returned
periodic current residual must be below 1e-9 of the operating-current scale.
This chooses the lower-duty branch when resolved. Very narrow roots near the
maximum-power boundary can escape the scan: `duty_unbracketed` means this solver
did not resolve a root, not proof that no physical operating point exists.

Admission requires each full-period `Rj/(fs*L) <= 0.5`. At this bound a degree-18
series has its first omitted coefficient below 2e-22 of its first increment.
`math.fsum` limits summation cancellation. This is a bounded approximation of
the exponential RL solution, not an iterative transient settling calculation.
There are at most 128 device rows and one inductor row, with constant-size
phase polynomials and bounded scan/bisection work. Output is withheld if CCM,
ratings, finite arithmetic or balance checks fail.

## Losses and power accounting

Conduction losses are `D*mean(i_on^2)*Ron`, `(1-D)*mean(i_off^2)*Roff`, and
`DCR*(D*mean(i_on^2)+(1-D)*mean(i_off^2))`. A group's conduction and transition
loss are split equally over its declared identical devices. Per-device peak
current and blocking voltage are compared with caller-supplied ratings. The
blocking magnitude is Vin, Vo, or Vin+Vo for buck, boost, or inverting operation.
These checks do not establish safe operating area or transient overshoot margin.

For each group the supplied linear overlap approximation is
`Ptransition = 0.5*Vblocking*fs*(Iturnon*tr + Iturnoff*tf)`. Edge currents come
from the periodic RL solution. Because equal series voltage and parallel
current sharing cancel the device-count multiplier, this is a group-level
expression; its loss is then divided among the devices. Supplied zero transition
durations can represent an excluded overlap term or idealized soft commutation.
The calculation does not infer which device commutates softly.

Total gate-drive supply power is `N*Qg*Vdrive*fs` per group. Its split between
driver, external resistor and internal gate resistance is unknown, so it is
returned only as `auxiliary_loss_w`, with location `unassigned_gate_drive`.
It is **not** silently added to MOSFET thermal loss rows.

The model treats transition and gate power as input-supplied overhead:

```text
Iin = topology conduction input current + (Ptransition + Pgate)/Vin
Pin = Vin*Iin
Pout = abs(Vout)*Iout
Ploss = sum(component loss rows) + unassigned gate-drive power
```

The independently computed residual `Pin-Pout-Ploss` must be within relative
1e-8 of the larger input/output power. Conduction energy balance follows by
multiplying the RL equation by current and integrating over a periodic cycle;
stored inductor energy then cancels. Overhead is added exactly once to input
power and the loss ledger. Transition and gate losses **do not change the
computed duty or inductor trajectory**. This is the declared reduced model;
large commutation losses require a more complete electrical model.

Loss rows retain stable occurrence/reference pairs, role, conduction power,
transition power and total watts. They are suitable as inputs to an explicit
electrothermal mapping step. They are not thermal sources by themselves: no
mesh cells, package resistances, temperatures or material values are fabricated.
The overhead's unlocated gate loss must remain visible in any thermal handoff.

## Verification and limits

The original synthetic tests cover:

- Lossless voltage-second and charge-balance oracles for all three topologies,
  including the independent triangular RMS identity `Irms^2=Imean^2+ripple^2/12`.
- The exact equal-phase-resistance buck relation `D=(Vo+R*Io)/Vin`, including
  zero, nearly zero and appreciable R.
- RL endpoint, mean and mean-square against direct exponential expressions,
  and independent RK4 integration refined from 2 to 4 to 8 intervals. The error
  decreases by more than a factor of 12 on each refinement, consistent with
  fourth-order convergence. These checks include the worst admitted RL decay.
- Independent input, output and loss balance with finite resistance, ripple,
  transition and gate losses for all three topologies; series/parallel loss
  allocation and unlocated gate-drive energy.
- Rejection of DCM, zero load, invalid voltage polarity/ratio, unresolved duty,
  exceeded caller ratings, duplicate bindings, excessive resource/transition/RL
  requests, nonfinite numbers and malformed contracts; strict JSON serialization.

The test suite verifies the declared equations and invariants. It does not
validate real MOSFET loss accuracy or converter hardware. Rds(on), DCR, transition
times and gate charge must be selected for the intended operating conditions.
The model omits dead time, body-diode conduction, reverse recovery, nonlinear
Coss, core loss, capacitor ESR, driver quiescent power, PCB loss, tolerance and
temperature feedback. It assumes stiff input/output voltages and positive
inductor current throughout the cycle. Control stability, startup, DCM,
four-switch noninverting buck-boost, flyback and other isolated converters,
magnetic saturation curves and fault operation remain unsupported.

Failures preserve a coded explanation. For a low-load DCM failure, review
whether the specified operating point should use a DCM-capable switching model;
increasing L or switching frequency reduces ripple and can restore CCM within
the supplied component limits. Reducing load further worsens low-load DCM.
For a peak-current/rating failure, reduce demand or use explicitly suitable
component ratings. Recalculate after every operating-point change.
An RL-envelope or near-limit root failure needs a different admitted operating
point or a more complete model. Do not suppress checks to manufacture a result.

## Method provenance

Primary references consulted for physical principles, not implementation:

- Texas Instruments, [Basic Calculation of a Buck Converter's Power Stage,
  SLVA477](https://www.ti.com/lit/an/slva477b/slva477b.pdf): CCM duty, ripple and
  current-rating relationships. SPIKE derives its own phase RL integration.
- Texas Instruments, [Basic Calculation of a Boost Converter's Power Stage,
  SLVA372D](https://www.ti.com/lit/an/slva372d/slva372d.pdf): CCM boost current,
  duty and ripple relationships; SPIKE solves losses rather than assuming an
  efficiency to calculate duty.
- Texas Instruments, [Understanding Inverting Buck-Boost Power Stages,
  SLVA059B](https://www.ti.com/lit/an/slva059a/slva059a.pdf), sections 2.1 and 5:
  switching-state and CCM principles. SPIKE substitutes a declared synchronous
  resistance for the output rectifier; it does not implement the paper's
  small-signal or DCM model.
- Texas Instruments, [Optimizing MOSFET Characteristics by Adjusting Gate Drive
  Amplitude, SLUA341A](https://www.ti.com/lit/an/slua341a/slua341a.pdf): the
  distinction between conduction, overlap and gate-drive supply loss. SPIKE
  retains only the explicitly described terms and leaves gate dissipation
  location unresolved.

The derivation, implementation, schema, fixtures and prose here were authored
independently for SPIKE. No external source implementation, vendor device
dataset, upstream example or third-party test fixture was copied or adapted.
References establish method provenance and do not confer redistribution rights
or measured qualification. All added material is original Apache-2.0 material.
