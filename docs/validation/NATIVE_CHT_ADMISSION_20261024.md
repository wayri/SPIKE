<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors -->
# Native CHT result admission hardening — 24 October 2026

This source-only increment tightens acceptance of the existing experimental
cavity/slab solver. It adds no physical model, mesh capability or release
qualification. The previously built 0.4.1 installers remain unchanged and do
not contain these later edits.

## Reproduced defects and repair

Finite returned MAC face values can still overflow intermediate arithmetic.
An independently authored, closed four-face circulation with magnitude 1e307
has zero cell divergence. With equal thermal boundaries, theta is zero, but
Pe times a face velocity overflows: infinite capacity times zero becomes NaN.
The previous maximum reduction could silently retain zero instead of rejecting
that invalid reconstructed energy residual. Admission now requires finite face
capacity, heat-flux terms, row diagonal and row residual before reduction.
The existing comparison helper also rejects nonfinite operands explicitly.
No residual or conservation tolerance was relaxed.

Accepted iteration metadata must agree with the owned native implementation:
`cavity.cpp::solve_cavity` requires ten consecutive settled steps, hence at
least ten accepted flow steps; `cht.cpp::solve_cht` starts thermal sweeps at one.
The pressure solver's zero-mean gauge is checked using scaled summation, avoiding
overflow without requiring bitwise zero after native floating-point subtraction.
The relative gauge tolerance is 1e-10, not a momentum-error acceptance tolerance.

For the zero-lid branch only, zero initial velocity/pressure, stationary walls,
no body force and no temperature feedback preserve exact zero flow and pressure
through every native operation. Its accepted flow count is exactly ten.
Admission now rejects nonzero returned state or flow residuals in that branch,
including a divergence-free circulation that mass balance alone cannot reject.

These are execution invariants and finite-arithmetic checks of the existing
discrete algorithm, not a new discretization. The independent governing-law,
finite-volume flux and SI derivation and primary-source ledger remain in
[the native CHT method record](NATIVE_CHT_METHOD_20261020.md). No external
implementation, source, fixture or data was copied. The new test fixtures were
independently authored for admission testing, not measured or continuum data.

## Executed verification

`tests/python/test_native_cht_result_invariants.py` adds seven no-binary tests:
positive rest state; impossible flow/thermal counters; pressure gauge shift;
unforced closed circulation; unforced mean-zero pressure; and finite-input
overflow. The separate actual native conduction, dimensional-scaling,
cancellation, incomplete-solve and field-forgery tests also execute.

The retained combined run passes **81 tests, zero failures/errors/skips** in
8.688 seconds, including adjacent AC resistor-to-CHT, tetrahedral CHT/service,
co-simulation, numerical runtime and packaged-probe contract checks:
`build/solver-continuation-regression-20261024.log`.
The first adjacent run rejected a forged face earlier than an existing test's
expected mass-balance diagnostic. Reordering the new rest check after the
existing mass/velocity checks preserved that diagnostic without changing the
test or accepting the forged result.

The existing fresh-process AC/flowing-tetra-CHT benchmark was also rerun:
`build/solver-continuation-runtime-20261024.json`. One warmup per configuration
was discarded, then five samples per configuration were measured. Its source
hashes and input digests stayed unchanged; analytical AC error <=1e-12,
energy defects <=1e-9, mixed residual <=1e-10 and cross-configuration numerical
equivalence all pass. Backend-default versus explicit-one-thread median solve
times were 0.134012 versus 0.122040 seconds; median lifetime peak private commit
was 1,135,276,032 versus 123,863,040 bytes. These are observations of the existing
thread policy on this synthetic fixture, not speed gains from admission changes.
The benchmark profiles level two; the 81-test run separately executes the
unchanged finest-level refinement/error gate.

## Remaining limits

Historical scope below: the missing moving-lid discrete momentum check is
superseded by [the 25 October independent checker](NATIVE_CAVITY_MOMENTUM_20261025.md).
The earlier 81-test run remains bound to its original source snapshot.

Mass balance, thermal balance and pressure gauge do **not** independently
reconstruct moving-lid momentum. An arbitrary mean-zero pressure field is not
excluded by a gauge check alone. The result now explicitly reports this limit.
Complete momentum reconstruction and timestep/history consistency remain open.
General CAD CFD, turbulence, physical correlation and knowledgeable human
numerical release review remain separate gates. The full repository suite and
Linux/frozen installers have not been rerun for these source-only edits; the
previous 5518-test result remains bound to its previous source snapshot.
