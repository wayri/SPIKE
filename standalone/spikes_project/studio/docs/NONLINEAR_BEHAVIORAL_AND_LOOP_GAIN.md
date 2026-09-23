# Native behavioral sources and loop-gain measurement

Development implementation, 7 September 2026. These changes are not included in
the previously installed beta.5 application.

## Nonlinear B sources

The owned C++ runner evaluates voltage and current behavioral sources inside the
Newton residual and Jacobian, rather than evaluating a Python callback per step.
Voltage probes, independent voltage-source branch currents and virtual simulation
time can participate in expressions. For example:

```spice
V1 in 0 2
R1 in out 1k
Bload out 0 I={0.001*V(out)^3}
Bmonitor monitor 0 V={tanh(V(out))+sin(2*pi*1000*time)}
.tran 1u 250u
.end
```

Supported operations include arithmetic, powers, comparisons, trigonometric and
hyperbolic functions, logarithms, exponentials, square root, abs, min/max, limit,
atan2, hypot, and lazy `if`. TABLE is piecewise linear with constant, strictly
increasing breakpoints and endpoint clamping. Only the selected conditional
branch is evaluated. No arbitrary host-language code is executed.

Programs are limited to 512 instructions and 32 input signals. Mathematical
domain errors and nonfinite derivatives are rejected rather than silently
clamped. Expressions must remain evaluable at Newton trial states, not just at
the intended final operating point. Discontinuous expressions require appropriate
timestep resolution: automatic time-expression breakpoint discovery is not
implemented. Dynamic operators such as delay, Laplace, ddt and idt, and complete
manufacturer-specific expression dialects, are not supported by this evaluator.

Regression coverage: `test_native_nonlinear_behavioral.py` checks nonlinear DC
feedback, transient feedback, functions, lazy conditionals, TABLE, and virtual
time against expected results using the actual native library.

## Linear voltage-injection loop gain

Insert a zero-DC independent voltage source with its positive terminal at the
forward loop node and its negative terminal at the return node. Neither terminal
may be ground. Then run, from the source checkout:

```console
python -m python.spikes loop-gain examples/spikes/advanced_systems/linear_loop_injection.cir --injection Vinject --assume-unilateral --start-hz 1 --stop-hz 100000 --points 501 -o loop-gain.json
```

The report contains `T=-V(return)/V(forward)`, complex response, magnitude, phase,
sampled unity crossings and interpolated phase margins, plus the source hash.
The example is checked against `10/(1+0.001*s)` in `test_loop_gain.py`.

This is a linear complex-MNA analysis limited to 256 unknowns. The user must
establish that unilateral voltage injection is appropriate; the program does not
verify injection-point impedance conditions. It is not automatic general return
ratio extraction, nonlinear-bias linearization, switching-loop FRA, multiloop
stability analysis, or a stability certificate. Transient FRA remains a separate
input-to-output transfer measurement.

## Remaining qualification gates

Production BSIM, IGBT and thyristor bindings and manufacturer qualification remain
open. Generic GaN/SiC equations and passing equation tests do not establish vendor
accuracy. Model-specific licenses, reference curves, operating envelopes and
cross-engine/measurement evidence are required before enabling a validated tier.
