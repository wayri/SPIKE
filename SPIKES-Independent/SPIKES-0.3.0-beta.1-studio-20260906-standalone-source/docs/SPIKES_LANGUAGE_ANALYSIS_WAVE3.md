# SPIKES Language and Linear Analysis Wave 3

This wave adds executable, fail-closed compatibility slices. It is not a claim
of complete SPICE3 language or analysis compatibility.

## Controlled and behavioral sources

The owned netlist elaborator accepts standard linear source forms:

```text
Ename out+ out- control+ control- voltage_gain
Gname out+ out- control+ control- transconductance
Fname out+ out- controlling_voltage_source current_gain
Hname out+ out- controlling_voltage_source transresistance
```

They lower directly to the existing VCVS, VCCS, CCCS, and CCVS stamps in the
linear MNA reference engine. Current controls must name a voltage-defined branch
in the elaborated project. Control nodes and branch names are scoped when a
subcircuit is flattened.

Wave 3 initially accepted this affine B-source slice:

```text
Bname out+ out- V={constant}
Bname out+ out- I={constant}
Bname out+ out- V={gain * V(node+,node-)}
Bname out+ out- I={gain * I(Vsense)}
```

The same arithmetic-only expression evaluator and AST/work limits used for
parameters are applied. An expression may contain no more than one distinct
voltage or branch-current control, must be affine in that control, and a
controlled expression must have zero offset. It is lowered to an independent
or standard controlled source before execution. Wave 4 subsequently added a
separate bounded nonlinear reference path for safe differentiable multi-control
expressions. Ordinary linear MNA still accepts only the affine lowering
described here. See `SPIKES_LANGUAGE_ANALYSIS_WAVE4.md`; arbitrary calls,
state/time access, discontinuities, Laplace forms, and code execution still
fail closed.

## Linear analysis contracts

`spikes/linear-noise-result/v1` propagates one Norton current-noise density per
resistor through the exact complex MNA system and sums uncorrelated power
spectral densities. It reports output PSD, amplitude density, per-resistor
contributions, and trapezoidally integrated RMS noise. Its model is exactly
`4 k T / R`; semiconductor shot/flicker/correlated noise is not included.

`spikes/ac-sensitivity-result/v1` reports central-difference complex
derivatives and normalized logarithmic sensitivities for selected positive
R/L/C values. The bounded relative perturbation and solve count are recorded.
It is not an adjoint or nonlinear sensitivity implementation.

`spikes/pole-zero-result/v1` extracts finite poles from the generalized MNA
pencil `G + s C` and finite SISO transmission zeros from its augmented system
pencil. Infinite descriptor modes are counted separately. The present output
is a node-voltage probe driven by one independent source. Cancellation
reduction, nonlinear bias linearization, and MIMO zeros are not implemented.

The executable API functions are `run_linear_noise_analysis`,
`run_ac_sensitivity`, and `run_linear_pole_zero` in
`python.spikes.advanced_analyses`. Deck directives and CLI subcommands for
these analyses are not part of this wave.

## Explicit remaining gaps

- Complete SPICE3 B-source expressions and device/control variables; Wave 4
  covers a bounded differentiable memoryless subset only.
- `.noise`, `.pz`, `.sens`, and distortion directive parsing.
- Semiconductor operating-point linearization and noise models.
- Harmonic-balance, Volterra-series, intermodulation, and nonlinear
  small-signal analyses.
- Independent cross-engine compatibility qualification.

Focused qualification is in
`tests/python/test_spikes_language_analysis_wave3.py`.
