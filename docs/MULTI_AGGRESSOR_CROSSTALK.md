<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sampled multi-aggressor crosstalk: SI07-S08

Experimental, production-unqualified. This API attributes victim voltage to
1–6 independent aggressor source waveforms and returns exact signed-family
envelopes at requested observation times, subject to floating-point tolerance.
It reuses the [initialized RLC solver](RLC_INITIAL_STATES.md); all underlying
rational-fit, regular closure, stability and supplied topology limits apply.
This bounded stage does not complete SI07 or HyperLynx parity.

## Physical model and independent derivation

For the admitted constant linear network, write the existing mixed physical
and fitted state equations as `z' = A z + F u`, with linear victim output
`v = H z + J u`. Units of source/victim voltage are V, physical currents A,
time s, R ohm, L H and C F. Fitted memory retains the parent's sqrt(W)
convention and is not assigned physical stored energy.

For aggressor j, the caller supplies waveform `w_j(t)` and reference voltage
`b_j`. Define deviation `d_j(t) = w_j(t) - b_j`. A family member uses the fixed
polarity `sigma_j` in {-1,+1} for its entire waveform:

```
u_j(t) = b_j + sigma_j d_j(t)
z_sigma(t) = z_base(t) + sum_j sigma_j z_j(t)
v_sigma(t) = v_base(t) + sum_j sigma_j v_j(t)
```

The baseline uses constant aggressor references, all original nonaggressor
sources and the complete original initial state. Each basis uses only its
aggressor deviation; all other sources and all fitted/L/C initial states are
zero. Substitution into the linear differential equation and the common
initial condition proves the decomposition by uniqueness. Keeping the common
initial state in each basis instead would incorrectly count its response N+1
times. The matrices, fit request and R/L/C values stay fixed across the family.

At a requested time k, let `r[k] = sum_j abs(v_j[k])`. Each independent sign can
make its real scalar contribution nonnegative or nonpositive. Consequently:

```
v_min[k] = v_base[k] - r[k]
v_max[k] = v_base[k] + r[k]
lower_margin[k] = v_min[k] - lower_limit
upper_margin[k] = upper_limit - v_max[k]
```

These are extrema over the finite family of 2^N complete waveforms at that
sample. Maximizing `v_max` over the requested samples selects a global sampled
upper witness; minimizing `v_min` selects a lower witness. They can be different
patterns. A single pattern need not attain an entire envelope curve. Exact
extremum ties select the earliest requested time. Upper zero contributions use
+1; lower signs are opposite, so zero contributions use −1.

Each selected pattern is solved directly, retaining original common state and
fixed sources. At every requested output, its direct voltage must agree with
superposition within `2e-10 V + 1e-9 * scale`, where scale is the largest of the
direct magnitude, summed magnitude, baseline magnitude and sum of contribution
magnitudes. The result's witness voltage/margin is the envelope value; the
separate direct trace and maximum residual expose numerical disagreement.
Failure rejects the complete result.

## Referenced subject knowledge and method lineage

Reviewed 18 October 2026:

- Anant Agarwal and Jeffrey Lang, MIT 6.002 course materials hosted Spring
  2007, *Lecture 3: Superposition, Thévenin and Norton*, slides marked Fall
  2000, PDF pages 3–13: linear node equations, homogeneity, independent-source
  superposition and zeroed-source boundary semantics.
  [Official lecture PDF](https://ocw.mit.edu/courses/6-002-circuits-and-electronics-spring-2007/5ec9a8524891d6940e4572e1c97b0cf1_6002_l3.pdf).
  This is foundational circuit linearity, not a vendor crosstalk benchmark.
- David H. Staelin, *Electromagnetics and Applications* (2011), section 3.4.2,
  linear simultaneous circuit equations; physical KCL/KVL, capacitor and
  inductor laws and initial conditions are also recorded in the parent RLC
  method ledgers.
  [MIT-hosted textbook](https://live.ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf).

The bias/common-state decomposition, finite sign-envelope proof, direct witness
admission and implementation are original derivations from those foundations.
No external source code or figures were copied. Existing SciPy matrix
exponential propagation and rational fitting are reused through the parent
solver; this stage introduces no dependency or new time integrator.

## Public API and reproducible workflow

Worker method `run_multi_aggressor_crosstalk` accepts exactly `{'request': ...}`.
Request contract `spike/multi-aggressor-crosstalk-request/v1` has exactly:
`contract`, `transient_request` (initialized RLC v2), `victim_port`, `aggressors`,
`lower_limit_v`, `upper_limit_v`. Aggressors are exact records
`{port_name, reference_voltage_v}`. Names must be unique known ports, exclude
the victim, and references/limits must be finite with lower < upper. Voltage
limits are caller assumptions, not standard-derived compliance thresholds.

For example, original 0↔3.3 V with reference 1.65 V admits the complementary
3.3↔0 V waveform for negative polarity. Reference zero instead admits a
negative-voltage waveform. Neither bias nor switching amplitude is inferred.

Result contract `spike/multi-aggressor-crosstalk-result/v1` preserves the exact
original source request and its complete-request SHA-256 digest, source-ordered
aggressor names/references, actual baseline result/v2, contribution voltage
traces and their derived request digests, envelopes, direct witness traces and
digests, signs, sample times, raw margins and residual/work diagnostics. Digests
use canonical UTF-8 JSON with sorted keys, compact separators, non-ASCII
preserved and nonfinite numbers forbidden. Derived requests can be reconstructed
from original source, biases, signs and the above zero-state rule.

Registered strict request/result schemas are in `schemas/manifest.json`.
Runtime additionally enforces cross-field identities, finite arithmetic and
physical/numerical admission. Run the original coupled conductance example:

```powershell
.venv/Scripts/python.exe examples/multi_aggressor_crosstalk/run_crosstalk.py
```

## Conditioning, resources and verification

The implementation performs N+3 actual fits and trajectories: baseline, N
bases and two witnesses. It does not cache a single fit or enumerate every
pattern. Before fitting, original and basis states/topologies are admitted,
all mirrored endpoint arithmetic is checked (even unselected polarities),
and combined parent work must be at most 100 million. Full request/result
limits are 8/16 MiB with conservative output preflight and final actual check.
Cancellation, finite sums/differences, envelope and margin arithmetic fail
closed without partial success. Source knot grid and full integration horizon
are retained even if the output grid omits the horizon endpoint.

Large common-mode values can hide small contributions through cancellation.
Compensated finite sums and the scale-aware direct-witness residual expose
some numerical failures; they do not certify arbitrary conditioning, fit
uncertainty or absolute small-signal precision. A direct residual cannot replace
an independent physical reference or qualify a poor rational fit.

Verification includes independent conductance/RLC PWL equations
`C V' = I - G V`, `L I' = Vs - R I - V`, finite-family enumeration, nonzero
physical fitted-memory references, analytic checks, fixed sources/common state,
ordering/ties, reference and time scaling, admission and actual worker/schema/
example checks. Analytic/physical voltage acceptance is 2e-10 V absolute plus
1e-9 relative. Parent propagation is exact for each PWL interval up to numerical
matrix-exponential/fit errors; output-grid refinement is an observation change,
not a convergence claim for unknown physical signals. The
[execution record](validation/SI07_MULTI_AGGRESSOR_CROSSTALK.md) retains actual
checks and independent review. Knowledgeable human review before release remains
required.

## Multiphysics boundaries and remaining scope

Shared port identity, original source/state provenance and complete baseline
result allow later coupling without inventing geometry, material or thermal
ownership. Voltage/current superposition does not extend to quadratic energy:
`R*(I_base + sum sigma_j I_j)^2` contains cross terms. Do not sum basis heat,
work or storage. To obtain a pattern's heat, construct that full initialized
request and run the [continuous energy ledger](RLC_ENERGY_LEDGER.md); this API
does not execute a thermal transfer or field/mechanical solve.

This is not an intersample peak guarantee, timing-skew search, eye/jitter/BER
bound, arbitrary data-sequence optimization, nonlinear IBIS/AMI simulation,
field extraction, measured/vendor correlation or production qualification.
Changing output samples can reveal larger extrema. SI07 and complete PI/SI
parity remain open, with broader multiphysics stages separately gated.
