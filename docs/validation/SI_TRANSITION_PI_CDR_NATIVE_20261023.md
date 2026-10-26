<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native transition-PI CDR source-reference evidence — 2026-10-23

## Claim and scope

`src/si/transition_pi_cdr.cpp` is a bounded C++20, IEEE-754 binary64
transcription of the transition-gated proportional/integral recurrence owned by
`python/spike_core/solvers/signal_integrity/receivers/si_clock_recovery.py`. Inputs are finite transition locations
and a finite record endpoint in nominal unit intervals (UI). Outputs are sample
centers and recovered periods in UI, accepted phase errors and crossing
locations in UI, and exact detector/update counters.

This source reference has a strict-FP static-library and CTest target in the
main CMake build; it is not registered with the worker or Python bindings.
It does not detect voltage crossings, declare lock, recover data,
estimate BER, model a transistor CDR, or qualify any protocol. Its presence does
not promote the existing approximate behavioral method. Knowledgeable human
numerical review and measured receiver/protocol qualification remain open.

## Governing method and lineage

The exact owned governing derivation and limitations are in
[`docs/SI_CLOCK_RECOVERY.md`](../SI_CLOCK_RECOVERY.md), and the executable
behavioral owner is [`python/spike_core/solvers/signal_integrity/receivers/si_clock_recovery.py`](../../python/spike_core/solvers/signal_integrity/receivers/si_clock_recovery.py).
This increment adds no new physical model or external method. No external source
code, prose, fixture, or example was copied. Consequently this record does not
close the existing detector/physical-model provenance or validation limits.
The separately reviewed stability foundation below concerns only the locally
linear recurrence, not the complete acquisition algorithm.

Reviewed 23 October 2026: E. I. Jury, *Proof of the Generation Rule for the
Stability Constraints in Linear Discrete Systems*, UCB/ERL M39, 5 December 1963,
[author's institutional report](https://www2.eecs.berkeley.edu/Pubs/TechRpts/1963/ERL-m-39.pdf),
theorem and proof, printed pages 1–4. The original equations were visually
inspected, not reconstructed from corrupted text extraction. This is a
mathematical foundation; no report text, implementation or example is copied.

Independent specialization: with one true transition per nominal UI and no
clipping, use state `(phase_error, period_minus_one)`. The update matrix is
`[[1-Kp-Ki,-1],[Ki,1]]`, with trace `2-Kp-Ki` and determinant `1-Kp`.
The second-order unit-circle conditions become `0<Kp<2`, `Ki>0`,
`2*Kp+Ki<4`. Current gain limits satisfy these strict inequalities.
This establishes local unclipped linear stability only; missing/ambiguous
transitions, nonlinear acquisition, measurement noise and physical lock remain
outside this argument.

At predicted boundary `B`, current period `P`, and a non-decreasing list of
already detected transition coordinates, the closed gate is
`[B - 0.45 P, B + 0.45 P]`. Exactly one not-yet-consumed transition `C` gives
`e = C - B`; zero transitions holds the state, and more than one increments the
ambiguity counter and skips the update. Every transition at or left of the
right gate edge is then consumed. For an accepted event,

```
d = max_frequency_offset_ppm * 1e-6
Pmin = 1 / (1 + d)
Pmax = 1 / (1 - d)
Pnew = clip(P + Ki e, Pmin, Pmax)
Bcorrected = B + Kp e
center = Bcorrected + Pnew / 2
Bnext = Bcorrected + Pnew
```

The only declared clipping is the period-integrator bound. The code increments
`frequency_bound_hit_count` exactly when the proposed period differs from the
clipped period. `detected_transition_count` is the admitted input count;
`accepted_transition_count` is the exact accepted-event history length.

## Admission, numerical behavior, and resource bounds

- C++20 and IEEE-754 binary64 are required. The standalone build enables
  `/fp:strict` on MSVC or `-fno-fast-math -ffp-contract=off` on GCC/Clang.
- `last_x_ui` must be finite and nonnegative. Crossings must be finite, within
  `[0,last_x_ui]`, and non-decreasing. Reversed coordinates fail closed.
  Coincident crossings are retained, never deduplicated: each contributes to
  the closed-gate multiplicity and two coincident events make that gate
  ambiguous. This matches valid exact-threshold-touch output from the owned
  Python detector.
- Phase is in `[0,1)`, `0 < Kp <= 0.5`, `0 < Ki <= Kp/4`, and
  `0 < max_frequency_offset_ppm <= 100000`.
- `max_symbols` is 1 through 65536; crossings are capped at 1,048,575, matching
  the maximum transitions possible between the owned Python detector's
  1,048,576 input samples.
- A record beyond `(max_symbols + 1) Pmax`, an output beyond `max_symbols`, an
  event history beyond `max_symbols + 1`, or non-finite intermediate state is
  rejected. Output capacities are checked before reservation. There is no
  silent truncation or input sorting.
- Storage is `O(max_symbols + accepted events)`. Each loop iteration performs
  lower/upper binary searches over the retained crossing array. The caller owns
  process cancellation and time limits.

The normalized-UI API deliberately excludes absolute seconds and voltage.
Upstream translation, nominal-rate normalization, crossing detection, signal
identity, and units remain the caller's responsibility. This separation avoids
claiming that the native kernel owns or validates acquisition provenance.

## Executable verification design

`tests/test_si_transition_pi_cdr.cpp` runs both as a standalone executable and
as the main CMake `test_si_transition_pi_cdr` target. It contains hand-calculated checks for one PI update,
nominal no-transition holdover, the inclusive `+0.45 P` edge and consume-once
rule, the exact binary64 `-0.45 P` edge, one-ULP inside/outside checks at both
gate ends, retention of a sample center exactly equal to the record endpoint, a
two-transition ambiguous gate, exact period saturation, malformed and
over-budget rejection, and fail-closed output exhaustion. These checks use
independent expected counts and hand results rather than Python as their oracle.

The parity harness additionally constructs the owned detector counterexample
`t = arange(9)/4`, zero voltage except `v[1] = 0.5 V`, a 1 Hz nominal rate, and
the default 0.5 V threshold. The threshold touch produces two crossings at
0.25 UI. Both native and Python must report two detected transitions, one
ambiguous gate, zero accepted transitions, and unchanged holdover centers.

`scripts/benchmark_si_transition_pi_cdr.py` creates a fresh standalone directory
strictly below `build/`, builds with warnings-as-errors and strict floating-point
options, runs the native tests, and compares a separate mixed accepted/ambiguous
fixture with an independently written Python recurrence. It then runs one
untimed warm-up and five measured native executions at 1,000, 30,000, and
65,000 symbols. Its JSON includes every timing, compiler/configure identity,
strict flags, platform, executable hash, and source hashes. Timings characterize
only that recorded machine/build; they are not protocol throughput or a release
performance guarantee.

The final report also checks source hashes before and after execution and
rejects source drift. An explicit output path must be fresh and is created
exclusively; prior evidence cannot be overwritten. The accepted local record
is `build/si-transition-pi-cdr-accepted-20261023.json`. Earlier mutable reports
are historical iteration evidence, not the current source binding.

Reproduce with:

```powershell
.venv\Scripts\python.exe scripts\benchmark_si_transition_pi_cdr.py
```

No production-backend, protocol, or release qualification follows from a
passing standalone run.
