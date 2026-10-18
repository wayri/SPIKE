<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied crosstalk timing corners: SI07-S09

Experimental, production-unqualified. This API evaluates 1–8 caller-supplied
timing/skew corners above the [multi-aggressor crosstalk solver](MULTI_AGGRESSOR_CROSSTALK.md).
It reports worst signed-family victim voltages at requested samples across
those finite corners. All parent rational-fit, initialized RLC, regular stable
LTI closure and source bounds apply. This stage does not complete SI07 parity.

## Question, physical assumptions and independent derivation

For aggressor j with original PWL voltage `w_j(t)` on `[0,T]`, define the held
extension `wbar_j(q)` as the first voltage for q<0, the original PWL function for
0<=q<=T, and the last voltage for q>T. A supplied delay `d_cj` in seconds gives
corner c's positive waveform:

```
w_cj(t) = wbar_j(t - d_cj), 0 <= t <= T
u_cj,sigma(t) = b_j + sigma_j * (w_cj(t) - b_j)
```

Positive delay moves transitions later; negative delay advances them. Bias
`b_j` remains an explicit voltage reference, and `sigma_j` is fixed at ±1 for
the full waveform. Endpoint holds are a declared source model, not inferred
data outside the supplied trace or a periodic wrap. The original local-zero
fitted/L/C initial state stays identical across corners; it is not shifted,
settled or reconstructed from negative-time drives. An advanced waveform can
already be mid-transition at t=0 while the supplied state remains unchanged.
This is a well-defined initial-value experiment, not automatic steady-state
timing analysis. Nonaggressor drives, fit, R/L/C, biases, horizon and observation
times remain unchanged. Voltage is V, current A, delay/time s, R ohm, L H, C F.

Translation preserves piecewise linearity. Its exact breakpoints are the moved
original knots `t_i+d_cj` strictly inside `(0,T)`, plus 0 and T. On an original
segment, the clipped endpoint value follows the independently derived affine
identity `w(q)=(1-alpha)*w_i+alpha*w_(i+1)`, where
`alpha=(q-t_i)/(t_(i+1)-t_i)`. Holds supply values outside the interval. Thus no
new uniform sampling grid or waveform approximation is introduced. Zero delay
retains the exact original knot/value representation and request identity.

For each corner the parent linear initialized RLC equations give
`v_c,sigma[k]=v_c,base[k]+sum_j sigma_j*v_cj[k]`, with common initial response
and fixed drives only in that corner's baseline. Hence the parent extrema are
`l_c[k]=v_c,base[k]-sum_j abs(v_cj[k])` and
`h_c[k]=v_c,base[k]+sum_j abs(v_cj[k])`. Taking extrema over the finite union:

```
minimum[k] = min_c l_c[k]
maximum[k] = max_c h_c[k]
lower_margin[k] = minimum[k] - lower_limit
upper_margin[k] = upper_limit - maximum[k]
```

This is an exact extremum over the supplied finite corners and signed waveform
family at those samples up to numerical arithmetic, not over an interval of
possible skew. Each sample retains the attaining corner id. Exact corner ties
prefer declared input corner order. Global upper/lower witnesses first prefer
corner order on ties, then the parent's earliest sample within that corner;
parent polarity zero ties are unchanged. The global witness copies the actual
parent fixed-pattern full-trace verification, its derived request digest and
residual. A single corner/pattern need not attain the full envelope curve.

## Reviewed primary references and original lineage

Reviewed 18 October 2026:

- Alan V. Oppenheim, *Signals and Systems*, MIT RES.6-007, Lecture 2: Signals
  and Systems, Part I, 1987 course hosted Spring 2011, PDF pages 1–3 and
  transparency 2.2: continuous-time signal translation and its relation to
  sinusoidal phase. [Official notes](https://ocw.mit.edu/courses/res-6-007-signals-and-systems-spring-2011/b061322022d65a4bc2ed2e2d3c54d3c5_MITRES_6_007S11_lec02.pdf).
  The implementation uses direct time translation, not a phase-only model.
- Denny Freeman, MIT 6.003 *Signals and Systems*, lecture 1, September 8,
  2011, PDF pages 14–18: continuous versus discrete time, sampling, hold and
  piecewise linear reconstruction.
  [Official lecture slides](https://ocw.mit.edu/courses/6-003-signals-and-systems-fall-2011/012675925c0f652bb179b6a33cd3d13b_MIT6_003F11_lec01.pdf).
- The parent [method ledger](MULTI_AGGRESSOR_CROSSTALK.md) records Agarwal/Lang
  independent-source circuit superposition and Staelin linear KCL/KVL/RLC laws.
  Those physical equations remain the executed solver, rather than shifting an
  already computed victim trace with unchanged common initial state.

The clipped PWL construction, same-state experiment and finite-union envelope
proof above are original derivations from those foundations. All code, examples
and physical oracles are independently authored. No third-party source code,
figures, meshes or example data were copied. No new dependency/time integrator
is introduced; each corner executes the existing parent solver.

## Public workflow and contracts

Worker method `run_crosstalk_timing_corners` accepts exactly `{'request': ...}`.
Request/v1 contract `spike/crosstalk-timing-corners-request/v1` has exactly
`contract`, `crosstalk_request` (parent S08 request/v1) and `timing_corners`.
Each corner is exactly `{id, delay_s_by_port}`. Ids must be unique nonblank
strings of at most 128 characters. Each map must cover every aggressor exactly
once, with finite signed numerical seconds, excluding fixed/victim ports.
All corners are executed in declared order, including distinct ids with equal
delay values. Delay maps in results use the underlying source-port order.

Result/v1 contract `spike/crosstalk-timing-corners-result/v1` retains the exact
original crosstalk request and full new-request digest, declared corner records
with delays and complete actual parent results, combined envelope and its
attaining corner ids, copied global witnesses with `corner_id`, and diagnostics
`solution_count`, `estimated_work`, `corner_count`, `sample_count`. Child result
digests bind derived requests and preserve original fit/state identity. The
canonical JSON/digest convention is the parent's unchanged UTF-8 SHA-256 rule.
Raw caller voltage limits remain assumptions, not inferred compliance limits.

Schemas are strict and registered in `schemas/manifest.json`; runtime also
checks cross-field identities, finite arithmetic, numerical states and budgets.
Run the original nominal/late-clock/early-data example:

```powershell
.venv/Scripts/python.exe examples/crosstalk_timing_corners/run_timing.py
```

## Numerical admission, resources and verification

With C corners and N aggressors, this performs `C*(N+3)` actual fits and
trajectories; it claims neither one-fit caching nor a continuous optimization.
Before any fit, all corner waveforms, parent requests, common states and each
baseline/basis/mirrored source family pass admission. Aggregate work sums each
corner's actual parent estimate because shifted union grids can differ; the
total must not exceed 100 million. Request/result limits are 8/16 MiB, with
conservative complete nested-output preflight and an actual final byte check.
Failure or cancellation returns no successful partial result.

Endpoint interpolation uses finite compensated sums without extrapolation.
Finite delays wholly outside the horizon produce the appropriate constant hold
without adding irrelevant large times. Interior knot collision, absorbed delay,
collapsed endpoint fraction or nonzero interpolation-product underflow rejects
the request; it does not silently merge transitions or round a delay to zero.
These checks are representability gates, not a global conditioning certificate.
The parent direct-witness acceptance remains `2e-10 V + 1e-9 * scale`; large
common modes can mask smaller signals within that tolerance.

Independent verification uses hand-translated clipped PWL sources, physical
conductance/RLC equations, finite corner/polarity enumeration, nonzero fitted
memory and common state, fixed sources, source/corner ties, reference/time
scaling, grid refinement and finite-set enlargement. Analytical/physical voltage
comparisons require 2e-10 V absolute plus 1e-9 relative. The interval propagation
is unchanged; adding observations tests shared-value invariance and may reveal
larger extrema. Adding corners can only expand the finite-family envelope, up
to arithmetic tolerance. Neither test certifies omitted times or unsupplied
skews. See the [executed evidence](validation/SI07_CROSSTALK_TIMING_CORNERS.md).

## Multiphysics ownership and remaining scope

Corners retain source/port identity, explicit delays, fit and common initial
state, so later coupling can select a complete reproducible physical experiment.
Quadratic heat/work/storage cannot be added across basis responses or corners.
For a selected corner and polarity, reconstruct the full initialized transient
request and execute the [continuous energy ledger](RLC_ENERGY_LEDGER.md).
No thermal deposition, material feedback or geometry mapping is implicit.

Continuous skew optimization, intersample peak guarantees, probabilistic jitter,
BER, arbitrary data-pattern search, nonlinear IBIS/AMI drivers, physical/VNA/TDR
correlation and production qualification remain open. Knowledgeable human
numerical review before release remains required. SI07 and full PI/SI parity
remain incomplete; broader multiphysics stages keep their separate gates.
