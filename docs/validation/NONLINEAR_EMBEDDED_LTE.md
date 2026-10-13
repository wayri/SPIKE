# Native nonlinear embedded LTE qualification

The native transient solver now applies its adaptive controller to circuits
containing the Shockley diode, charge-storage dynamic diode, coupled
electrothermal resistor, smooth saturating inductor, and smooth
voltage-controlled switch. For every
eligible BDF2 or trapezoidal candidate step it solves two discrete systems at
the same endpoint:

1. the requested order-two BDF2 or trapezoidal DAE; and
2. a backward-Euler companion DAE using the same accepted history and source
   value.

Both systems are solved with damped Newton iteration and analytic device
Jacobians. The scaled infinity norm of their state difference drives timestep
rejection and growth. A singular, non-finite, or nonconvergent nonlinear BE companion is
treated as an infinite defect, so the candidate state is discarded and the
step is retried at a smaller timestep. No extrapolated state is presented as
an LTE estimate.

`adaptive_embedded_lte_solves_nonlinear_diode_dae` compares an adaptive
nonlinear diode-capacitor trajectory with a fine fixed-step BDF2 reference. It
also requires a real embedded solve, at least one LTE rejection, nonlinear
Newton work, and an accepted timestep below the configured maximum. The six
native SPIKES core/C-ABI/transient/session test executables originally covered
this change. The current eight-executable regression harness and additional
recovery/cache/conditioning checks are recorded in
[adaptive switching foundation](../SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md).

## Release boundary

- The startup step and each discontinuity restart use backward Euler and do
  not have an embedded estimate. The requested initial timestep therefore
  remains the maximum startup timestep.
- Sparse nonlinear Jacobian assembly and reusable symbolic LU are available.
  The BE companion now retains a separate cache. Changed matrix values require
  full numeric factorization; local partial numeric updates are not implemented.
- A bounded two-terminal reverse-recovery state, R(T)-Rth-Cth thermal state,
  and single-valued smooth saturation flux law are integrated. Dynamic
  compact-device charge implementations have separately bounded capabilities;
  they are not universal production MOSFET/BJT/WBG qualification. OSDI transient
  remains limited to its admitted fixed-BE path. Hysteretic/path-dependent core
  state and general coupled mechanical DAEs are not established by this test.
- The order-two/BE difference is a defect controller, not a calibrated universal
  LTE estimator. Linear companion failures still fail closed; nonlinear companion
  failures participate in rejection. Startup steps have no embedded estimate.
- This qualification does not constitute BSIM, IGBT, thyristor, GaN, SiC, or
  converter hardware correlation.
