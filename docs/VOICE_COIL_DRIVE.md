<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Linear voice-coil drive

`python/spike_core/voice_coil_drive.py` is a bounded, verification-only
electrical/mechanical simulation for an ideal reciprocal voice-coil actuator.
It closes the back-EMF loop that the fixed-excitation actuator workflow does
not model. It does not consume a geometry or force map and makes no magnetic
field or geometry-derived force claim.

Run the checked-in request with:

```powershell
build/qualification-py311/Scripts/python.exe -m python.spike_core.voice_coil_drive --request examples/actuator/voice-coil-drive.json --result build/voice-coil-drive-result.json
```

The request contract is `spike/voice-coil-drive/v1`. All values use SI units.
It supplies fixed `resistance_ohm`, `inductance_h`, reciprocal
`force_constant_n_per_a`, `mass_kg`, `damping_n_s_per_m`, `spring_n_per_m`,
spring equilibrium, constant terminal voltage, three initial states, duration,
requested maximum time step, and a bounded provenance string. Fields must be finite real JSON numbers;
unknown fields fail. The CLI rejects duplicate keys and inputs over 8 MiB.
At most 100,000 steps are admitted.

## Model and numerical method

For current `i`, position `x`, velocity `v`, and displacement
`q = x - x_eq`, the implemented equations are:

```text
L di/dt = V - R i - K v
dx/dt = v
m dv/dt = K i - c v - k q
```

The same signed SI coefficient `K` provides back EMF and force. Thus the two
coupling powers cancel rather than creating mechanical energy. Parameters and
voltage are constant for the run.

Implicit midpoint precomputes the constant three-state propagator and forcing,
then applies them once per step. The
solver chooses `N = ceil(duration/requested_step)` and the uniform step
`duration/N`; indexed times end exactly at the requested duration, without a
short floating-point remainder step. The dimensionless numerical condition
reported by NumPy for the assembled 3-by-3 coefficient array must not exceed
`1e12`. This practical arithmetic gate is not a physical conditioning metric;
because the state entries have different units, users should not compare it
between differently scaled formulations.

The stored energy is

```text
E = 0.5 L i^2 + 0.5 m v^2 + 0.5 k q^2.
```

With midpoint quantities, every accepted step satisfies the discrete identity

```text
Delta E = h V i_mid - h R i_mid^2 - h c v_mid^2.
```

The result reports supplied electrical work, both physical loss integrals,
initial/final stored energy, and their conservation residual. These audit the
implemented lumped equations; they do not account for unmodeled losses.

## Verification and validity limits

`tests/python/test_voice_coil_drive.py` checks the analytical uncoupled RL
response, exact lossless energy conservation, the opposing sign of back EMF,
second-order convergence against an independently evaluated eigensystem,
uniform-grid construction, the example, malformed/extreme values, conditioning,
and the step bound. The derivation, implementation, example, and oracles are
original SPIKE work; no external implementation or data was consulted or
adapted. Numerical code requires knowledgeable human review before release.

This model is limited to a linear, lumped, one-dimensional voice coil with
fixed parameters and a constant voltage. It is not a solenoid model. It omits
magnetic geometry, position-dependent force, saturation, hysteresis, eddy
currents, temperature, drive electronics, nonlinear suspension, friction,
stops, contact, acoustic loading, control, and multidimensional motion. A
passing run is not field, measurement, safety, lifetime, or production
validation.
