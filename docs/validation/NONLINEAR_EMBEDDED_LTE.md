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
rejection and growth. A singular, non-finite, or nonconvergent BE companion is
treated as an infinite defect, so the candidate state is discarded and the
step is retried at a smaller timestep. No extrapolated state is presented as
an LTE estimate.

`adaptive_embedded_lte_solves_nonlinear_diode_dae` compares an adaptive
nonlinear diode-capacitor trajectory with a fine fixed-step BDF2 reference. It
also requires a real embedded solve, at least one LTE rejection, nonlinear
Newton work, and an accepted timestep below the configured maximum. The six
native SPIKES core/C-ABI/transient/session test executables pass after this
change.

## Release boundary

- The startup step and each discontinuity restart use backward Euler and do
  not have an embedded estimate. The requested initial timestep therefore
  remains the maximum startup timestep.
- Nonlinear transient assembly and factorization remain dense. Sparse direct
  assembly, reusable symbolic analysis, and numeric-only refactorization are
  currently limited to linear transient systems.
- A bounded two-terminal reverse-recovery state, R(T)-Rth-Cth thermal state,
  and single-valued smooth saturation flux law are integrated. Dynamic
  MOSFET/BJT/WBG terminal charge, hysteretic/path-dependent magnetic state,
  multiwinding magnetic coupling, and coupled mechanical DAEs are not
  integrated into this transient engine and continue to fail closed.
- This qualification does not constitute BSIM, IGBT, thyristor, GaN, SiC, or
  converter hardware correlation.
