<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Fixed-excitation actuator motion

The [request schema](../schemas/actuator-motion-v1.schema.json) defines the
public shape. Runtime checks add finite arithmetic, uniqueness and stroke bounds.

`python/spike_core/actuator_motion.py` executes a bounded one-dimensional
mechanical response from an admitted `spike/actuator-force-map/v1` request. It
is useful for reproducible early-stage travel and energy studies. It is not a
field solver, circuit solver, contact model, controller, or production-qualified
actuator simulation.

Run a request with:

```powershell
build/qualification-py311/Scripts/python.exe -m python.spike_core.actuator_motion --request examples/actuator/voice-coil-motion.json --result build/voice-coil-motion-result.json
```

The `spike/actuator-motion/v1` request contains exactly these fields:

- `force_map`: the complete force-map request, including its fixed current or
  voltage and provenance;
- `mass_kg`, `damping_n_s_per_m`, and `spring_n_per_m`: positive mass and
  nonnegative linear mechanical coefficients;
- `spring_equilibrium_position_m`, `initial_position_m`, and
  `initial_velocity_m_per_s`;
- `duration_s` and `time_step_s`, both positive.

The initial position must lie in the force-map stroke. At most 100,000 time
steps and an 8 MiB CLI input are admitted. Unknown, duplicate, nonfinite, and
inconsistent force-map data fail before integration. The result records every
time, position and velocity sample, termination reason, map and numerical work, viscous
dissipation, initial/final mechanical energy, energy-balance residual, the
complete force-map review, and explicit limitations. Output parents must exist.

## Mechanical model and numerical method

The implemented equation, with positive displacement matching the map, is

`m*x'' + c*x' + k*(x-x_eq) = F_map(x)`.

Excitation is fixed at the value declared by the map. Piecewise-linear
interpolation is used only between supplied positions. There is no force
extrapolation. Reaching either stroke endpoint terminates at that endpoint;
impact, rebound, stops, friction and contact force are not invented.

Each time step uses implicit midpoint. Eliminating midpoint velocity leaves a
continuous piecewise-linear scalar equation for the new position. Its slope on
a force-map segment is

`2*m/h^2 + c/h + (k-dF/dx)/2`.

The request is rejected unless this is strictly positive on every segment, so
the bounded bisection solve has a unique root. If that root lies beyond the
stroke, a second bounded solve locates the first endpoint time and terminates.
This conditioning gate also prevents an unresolved negative-stiffness/pull-in
branch from being silently selected.

Implicit midpoint exactly satisfies its discrete work identity:

`Delta(0.5*m*v^2 + 0.5*k*(x-x_eq)^2) = F(x_mid)*Delta x - c*v_mid^2*h`.

The reported `midpoint_actuator_work_j` and residual evaluate this identity over the full run. They detect
implementation and accumulation regressions; it is not an estimate of force-map
error or real loss omitted by the model. `force_map_work_j` instead integrates
the admitted piecewise-linear force exactly, splitting travel at every crossed
map knot. `force_quadrature_error_j` is map work minus midpoint work, explicitly
quantifying this time-step quadrature difference. The method is second order in
time for smooth motion. Users must repeat with smaller time steps and denser
source maps for their own accuracy evidence.

## Verification and limits

Run `python scripts/qualify_actuator_motion.py` to execute all three original
actuator-class examples against an independently derived forced oscillator.
The report includes input requests, hashes, displacement and energy errors,
absolute and relative criteria, and full motion traces; any failed criterion
returns a nonzero exit code. See [verification record](SOLVER_CLOCK_MOTION_20260920.md).

`tests/python/test_actuator_motion.py` compares constant-force motion with its
closed form, demonstrates second-order convergence against the closed-form
underdamped oscillator, checks discrete mechanical energy/work balance, and
tests endpoint termination, malformed data, inconsistent maps, uniqueness, and
resource limits. These equations and tests were independently authored for
SPIKE; no external implementation was consulted or adapted.

The force is quasi-static and conservative at one excitation. Coil/electrode
dynamics, back EMF, drive impedance, saturation, hysteresis, eddy-current loss,
temperature, multidimensional motion, flexures, nonlinear springs/damping,
friction, impacts, acoustic radiation, and control are absent. A passing result
does not authenticate the supplied map and does not establish field, measured,
safety, lifetime, or production validation. Numerical code requires
knowledgeable human review before release.
