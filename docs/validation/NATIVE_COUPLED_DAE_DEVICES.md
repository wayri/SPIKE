# Native coupled electrothermal and magnetic DAE qualification

SPIKES now has two bounded native multiphysics circuit-level devices in
addition to its charge-storage dynamic diode.

## Electrothermal resistor

The electrical law is `I = V / (R0 * (1 + alpha * temperature_rise))`. Its
thermal-node residual is

`Cth * d(temperature_rise)/dt + temperature_rise/Rth - V*I = 0`.

The C++ kernel stamps the electrical/thermal cross derivatives and the Joule
power Jacobian. Model construction enforces a finite temperature envelope and
positive resistance throughout that envelope. Newton trial states outside the
envelope are rejected through damping.

## Saturating inductor

The single-valued flux linkage is

`lambda(i) = Lsat*i + (L0-Lsat)*Isat*tanh(i/Isat)`.

The branch DAE stamps `v - d(lambda)/dt = 0`. Its differential inductance is
strictly positive from `L0` at the origin to `Lsat` at high current, avoiding
the nonphysical energy discontinuity of a clipped inductance. This first model
is smooth and non-hysteretic.

Both devices support backward Euler and unequal-step BDF2, persistent history,
and the nonlinear BDF2/BE embedded-LTE pair. Hybrid trapezoidal mode fails
closed until charge/flux-consistent companions are qualified.

Evidence:

- `tests/test_spikes_transient.cpp`
- `tests/python/test_spikes_native_abi.py`
- `src/spikes/transient_solver.cpp`

This is not a core-loss/hysteresis model, multiwinding transformer, WBG thermal
transient, mechanical actuator, or hardware-correlated qualification.
