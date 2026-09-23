# Native dynamic-diode DAE qualification

The owned C++ transient kernel has an additive two-terminal dynamic diode with
one implicit diffusion-current state. Its charge-control equation is

`tau * dx/dt + x - Istatic(v) = 0`,

and terminal current combines conduction, stored-charge recovery, and junction
capacitance. Backward Euler and variable-step BDF2 stamp the state residual and
analytic Jacobian directly into native MNA. Stored charge therefore produces a
signed reverse-recovery tail after a forward-biased junction is commutated.

The device has explicit finite parameter validation and optional initial stored
charge. DC operating point treats it as the corresponding Shockley junction.
Hybrid trapezoidal mode rejects it until a charge-consistent trapezoidal
companion is implemented.

Evidence is provided by `tests/test_spikes_transient.cpp` and
`tests/python/test_spikes_native_abi.py`. This bounded qualification is not a
vendor diode, SPICE charge-card compatibility, avalanche model,
electrothermal model, or hardware correlation.
