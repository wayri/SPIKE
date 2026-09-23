# SPIKES Nonlinear Language and Analysis Wave 4

Wave 4 is an executable nonlinear reference slice. It does not constitute
complete SPICE3 grammar, semiconductor analysis, or production sparse MNA.

## Differentiable behavioral expressions

Safe B-source expressions may reference up to 32 distinct `V(node)`,
`V(node+,node-)`, and `I(voltage_defined_branch)` signals. Arithmetic,
parentheses, bounded powers, and one-argument `exp`, `log`, `sqrt`, `sin`,
`cos`, and `tanh` are accepted. A bounded AST is interpreted directly; Python
evaluation, attributes, subscripts, comprehensions, lambdas, imports, and
arbitrary calls are rejected during parsing.

The interpreter returns the expression value and its analytic gradient with
respect to every signal. Expressions and their signal references are scoped
during subcircuit flattening. Existing constant and one-control zero-offset
affine expressions continue to lower to ordinary independent or E/G/F/H
sources and run in linear MNA. Other safe differentiable expressions become
explicit nonlinear B elements and are rejected by linear MNA rather than being
silently approximated.

Discontinuous/stateful forms such as comparisons, Boolean operations,
conditionals, `abs`, `min`, `max`, delay, Laplace, `ddt`, random functions,
time, frequency, and device internals are not accepted.

## Nonlinear reference analyses

The dense reference Newton engine supports resistors, constant independent
sources, E/G/F/H sources, bounded nonlinear B voltage/current sources, and the
owned Shockley diode card. It stamps analytic Jacobians, uses residual-reducing
backtracking, enforces a 4,096-unknown limit, and exposes a versioned operating-
point result. It is a correctness fixture, not the native production solver.

The following executable reductions reuse the converged analytic Jacobian:

- `spikes/nonlinear-small-signal-result/v1`: memoryless bias-linearized source-
  to-probe response, including excitation phase.
- `spikes/biased-noise-result/v1`: uncorrelated resistor `4kT/R` and diode
  `2q|Id|` noise propagated through the biased Jacobian.
- `spikes/nonlinear-adjoint-sensitivity-result/v1`: one transposed-Jacobian
  solve followed by R, diode saturation-current, and independent-source
  parameter contractions.
- `spikes/local-distortion-result/v1`: a five-operating-point local Taylor
  reduction reporting first/second/third derivatives, fundamental, second and
  third harmonics, and THD for a one-tone input.

Analytical tests cover expression gradients, multi-control and hierarchical B
sources, polynomial bias gain and harmonic terms, resistor-divider adjoint
sensitivity, and diode shot noise through its biased small-signal impedance.

## Explicit omissions

- Dynamic charge, nonlinear capacitance, frequency-dependent nonlinear noise,
  flicker noise, and correlated device noise.
- Frequency-dependent Volterra kernels, two-tone intermodulation, shooting,
  harmonic balance, and large-signal periodic steady state.
- BJT/MOSFET compact-model bias linearization.
- Sparse nonlinear assembly, production device limiting, continuation,
  homotopy, and production convergence qualification.
- `.noise`, `.pz`, `.sens`, `.disto`, and general B-source deck compatibility.

Focused qualification is in
`tests/python/test_spikes_language_analysis_wave4.py`.

Wave 5 extends the safe function grammar, adds deck-facing bounded nonlinear
analysis adapters, and adds a memoryless two-tone intermodulation reduction;
see `SPIKES_LANGUAGE_ANALYSIS_WAVE5.md`.
