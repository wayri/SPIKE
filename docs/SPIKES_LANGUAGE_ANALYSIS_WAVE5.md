# SPIKES Nonlinear Language and Analysis Wave 5

Wave 5 extends the bounded Python correctness reference. It is release-usable
for the forms listed here, but it is not complete SPICE3 grammar or a
production sparse nonlinear engine.

## Behavioral expression additions

The safe analytic-gradient evaluator now accepts SPICE `^` powers,
case-insensitive function names, `PI` and `E`, and the aliases `LN` and
`ARCTAN`. In addition to the Wave 4 functions it implements:

- unary `abs`, `asin`, `acos`, `atan`, `sinh`, `cosh`, `asinh`, `acosh`, and
  `log10`;
- binary `atan2`, `hypot`, `min`, `max`, and `pow`;
- ternary `limit` and lazy `if`;
- one `>`, `>=`, `<`, or `<=` relation, principally for an `if` condition.

Every accepted form has an analytic first derivative. Nondifferentiable
points fail closed: `abs(0)`, equal `min`/`max` inputs, comparison equality,
and a `limit` input on either bound are errors. Lazy `if` evaluates only its
selected branch, allowing guarded domain expressions such as
`if(V(x)>0,log(V(x)),0)`. Attribute access, indexing, equality tests, Boolean
operators, Python conditionals, arbitrary calls, and all other Python syntax
remain rejected by the bounded AST validator.

## Deck-facing nonlinear analyses

`parse_nonlinear_analysis_deck()` and `run_nonlinear_analysis_deck()` provide a
fail-closed adapter around one operating-point circuit and exactly one of:

- `.noise V(out) SOURCE LIN|DEC|OCT POINTS START STOP`
- `.sens OUTPUT [ELEMENT ...]`
- `.disto OUTPUT SOURCE AMPLITUDE [DERIVATIVE_STEP]`
- `.disto2 OUTPUT SOURCE AMPLITUDE1 AMPLITUDE2 [DERIVATIVE_STEP]`
- `.nlss OUTPUT SOURCE [MAGNITUDE [PHASE_DEG]]`

The adapter inserts `.op` when absent and rejects `.dc` or `.tran`
combinations. It checks output targets, source kind, named sensitivity
parameters, numeric domains, sweep cardinality, and analysis cardinality
before execution. Results use the
`spikes/nonlinear-deck-analysis-result/v1` wrapper and retain the underlying
versioned analysis result.

The nonlinear noise deck propagates resistor thermal and biased diode shot
noise through the operating-point Jacobian. The current nonlinear device set
is memoryless, so its spectrum is white; the frequency axis and integrated
noise are a bounded white-noise reduction, not frequency-dependent compact-
model noise. Input-referred density is reported using the bias-linearized
source-to-output gain.

The sensitivity deck performs the existing one-solve nonlinear adjoint. With
no element list it selects every supported R, D, V, and I parameter. The
single-tone distortion deck reports the local cubic Taylor reduction. The new
two-tone reduction reports signed peak components at `f1`, `f2`, `f1+f2`,
`|f1-f2|`, `2f1±f2`, and `2f2±f1` from the same five operating-point solves.
It is a memoryless third-order reduction, not frequency-dependent Volterra or
harmonic balance. `.nlss` exposes the bias-linearized memoryless gain and
phase through a deck card.

The bounded `.disto` and `.disto2` forms above are SPIKES-owned syntax. A
SPICE3 `.disto DEC|OCT ...` card is deliberately rejected because the engine
does not yet implement its frequency-dependent Volterra semantics.

## Remaining release limitations

- Full SPICE3 B-expression grammar, `TABLE`, `POLY`, Laplace sources, `ddt`,
  `idt`, delay, time/frequency variables, random functions, and state history.
- BJT/MOSFET/BSIM bias linearization and their flicker, induced-gate, channel,
  avalanche, and correlated noise models.
- Dynamic charge and complex frequency-dependent nonlinear Jacobians.
- Frequency-dependent Volterra kernels, general intermodulation grids,
  harmonic balance, shooting, and periodic steady-state.
- Direct integration of these cards into the primary `parse_netlist()` and
  CLI execution path; Wave 5 exposes an explicit companion API so older
  project contracts remain stable.
- Sparse nonlinear assembly, limiting, continuation, and production-scale
  convergence qualification.

Analytical coverage is in
`tests/python/test_spikes_language_analysis_wave5.py` and the Wave 4 regression
suite remains mandatory.
