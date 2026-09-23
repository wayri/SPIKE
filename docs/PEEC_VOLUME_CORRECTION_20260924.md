<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# PEEC finite-volume correction: implementation and outstanding qualification

## Status

The subsequent [safety policy and consumer audit](PEEC_SAFETY_POLICY.md) makes
the findings permanent runtime and regression requirements. It closes additional
unsafe admission/export paths, not the missing board-volume formulation.

**The real-board AC defect is not fixed yet. Do not synchronize a release claim
or enable a production capability based on this increment.** The new native
`spike_peec_volume` library is an isolated verification kernel, not the legacy
`PEECSolver` implementation or a packaged Python extension. It supports finite
rectangular volume current bases, not annular barrels. No matrix projection or
passivity tolerance relaxation is part of this work.

## Reproduced failures

The pinned Marble v1.4.4 board SHA-256 is
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
`scripts/diagnose_peec_inductance.py` retains the C383 net's source geometry and
stackup, constructs a bounded mesh, and exports the physical matrix plus branch
identities and binary hash. At a 1 mm target on the current CPython 3.11 native
extension, the 45-branch matrix has minimum eigenvalue **-22.1443162 pH** and
worst pair coupling **1.216651175**. Its eleven-barrel submatrix minimum is
**-9.10042334 pH**, with four negative modes. These are diagnostics, not a usable
impedance result; the matrix was not corrected.

The release task's exact `.tmp/run_public_board_pi_slice.py` driver was also run
unchanged under `.venv`: preflight succeeds, but AC fails with
`PEEC_INDUCTANCE_NONPASSIVE`, five negative modes and twelve excluded graph-only
field links. Provisional terminals U37.18 to C383.1 are sensitivity inputs, not
reviewed hardware operating points. Different interpreter/binary/mesh snapshots
must not be compared as identical numerical baselines.

The original MODULAR-BUS-NIB regression ran four checks: **three failed**, one
passed. It imported 84 zones against the existing minimum 160, failed AC, and
failed DC mesh convergence; the approximate DC path completed. No expected
count or convergence gate was changed to obtain a pass. Logs are retained under
`build/peec-volume-20260924/`.

## Consistent rectangular-volume formulation

For uniform basis `b_i = direction_i / area_i` on volume `V_i`, in SI units:

```text
L_ij = mu/(4*pi) integral(V_i) integral(V_j) b_i dot b_j / |r-r'| dV' dV.
```

Self and mutual entries use the same volume integral, including intersecting
supports. The inner rectangular Newton potential is evaluated from an original
corner-difference primitive using asinh and atan2 terms. Outer integration uses
adaptive 3/5-point tensor Gauss rules and direction-sensitive subdivision.
Positions are translated and scaled before evaluation. Both integration
directions are evaluated; reciprocity discrepancy contributes to the error
estimate. Work and cell budgets are explicit. Exhaustion returns
`converged=false`, never an accepted low-order substitute.

The error indicator is **not a certified bound**. Finite-volume continuum
energy is nonnegative, but approximate integration still requires matrix-level
passivity and refinement checks. Symmetry, a small residual or a positive
diagonal alone does not establish accuracy. The new target uses strict floating
point settings, separate from the existing legacy fast-math target policy.

An independently derived Duffy transform reduces the self-volume reference to
a nonsingular two-dimensional integral. The 1 mm cube reference is
**188.231264438966 pH**; the final MSVC kernel returned **188.231264665730 pH**.
Additional checks cover short/wide and thin/long conductors, SI scaling,
longitudinal subdivision, overlap, opposite duplicate bases, rotation,
orthogonal currents, far separation, malformed geometry and resource exhaustion.
These checks do not qualify arbitrary board geometry or high-frequency current
redistribution.

The relative-angle overlap test exposed a tolerance-allocation defect: each
direction consumed the full tolerance before the final reciprocity contribution
was added. Internal budgets now reserve half for each contribution, without
changing the requested final tolerance. The final 45-degree overlap mutual is
**430.85304221954 pH**, estimated error **0.000226266 pH**, compared with
**430.85309627293 pH** at the coarse setting. Its independently assembled
three-basis matrix minimum eigenvalue is **-2.61479e-25 H** on MSVC, at roundoff
scale. No eigenvalues were edited. The test needs a one-million-evaluation cap
(912,660 evaluations); the default 500,000 cap can return nonconvergence for
this case. This is not yet a fast board-scale extractor.

The final MSVC Release and Debug test executables passed, compiled with warnings-as-errors
and strict floating point. A separate agent also ran the extended tests using
GCC. Focused Python geometry, transient, topology and multiport tests passed
**31/31** with warnings treated as errors. These bounded tests do not override
the real-board failures recorded above.

Full default Python discovery passed **1,827 tests with two skips**, zero
failures/errors, in 310.417 seconds with warnings treated as errors. The optional
real-board profile is outside that default run; explicitly enabling it produces
the three MODULAR failures above. Architecture and local documentation-link
checks passed. No Linux, packaged-worker, measured-board or production release
qualification was performed here.

## Geometry and overlap requirements

The transient path previously projected negative magnetic modes to a positive
matrix. It now uses the AC passivity assessment and aborts with
`TRANSIENT_INDUCTANCE_NONPASSIVE`, preserving zero-energy topology modes and
leaving the compatibility correction-ratio field zero. The real two-layer
transient fixture now exposes five negative modes and emits no waveform.
Separate valid-matrix tests still exercise the capacitance behavior; the native
failure is retained, not replaced with mocked qualification.

`python/spike_core/peec_magnetic_geometry.py` provides independently validated
magnetic cross-section descriptors. A circular barrel uses actual drill and
plating radii. Its DC equivalent width remains `pi*(drill+plating)`, but that
length is **not a rectangular magnetic width**. Ambiguous source identities,
inconsistent areas and unsupported noncircular barrels fail explicitly. This
descriptor is not yet connected to the production kernel.

Track and pad graph branches can occupy the same copper volume. A correct
inductance integral does not cure duplicated conductor resistance. Completion
requires either a nonoverlapping, current-continuous support partition or the
consistent resistance bilinear form `R_ij = integral b_i dot b_j / conductivity`.
Contact/topology constraints and port stamping must agree with that basis.
The present diagonal-resistance graph is not evidence of such consistency.

## Reproduction and next acceptance checks

```powershell
cmake --build build/qualification-native-py311 --config Release --target test_volume_inductance
build/qualification-native-py311/Release/test_volume_inductance.exe
build/qualification-py311/Scripts/python.exe scripts/diagnose_peec_inductance.py --board build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb --net 'Net-(C383-Pad1)' --output build/peec-volume-20260924/marble-before.json
```

Still required: annular and slot volume integration; overlap-aware conductor
bases and resistance; topology/port integration; native API and package parity;
Marble and MODULAR AC/DC refinement convergence; performance/resource bounds;
independent measured correlation and knowledgeable human numerical review.

## Method provenance

All implementation, derivation, fixtures and prose in the new numerical module
are independently authored; no external implementation was copied or adapted.
Foundational method lineage is Ruehli's finite-volume partial inductance
([DOI](https://doi.org/10.1147/rd.165.0470)) and rectangular prism potential
([Nagy et al. DOI](https://doi.org/10.1007/s001900000116)). These DOI endpoints
could not be fetched in this run; they are lineage references, not claims that
the full papers were reviewed here.

A [recent finite-cross-section coil model](https://arxiv.org/abs/2310.12087)
was reviewed at abstract level. Its high-aspect-ratio coil reduction is not
adopted as a remedy for short PCB via segments. The 2026
[uniform-grid PEEC interpolation paper](https://www.mdpi.com/2673-4117/7/6/261)
was located, but the full page was rate-limited; its acceleration is not
implemented or claimed as validation evidence. Establish consistent geometry
and energy before applying interpolation acceleration.
