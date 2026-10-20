<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI01-S02A finite-contact planar DC verification — 21 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

The original execution below is historical. A genuine strengthened
[geometry replay](PI01_GEOMETRY_OWNERSHIP_20261021.md) now uses actual rotated
polygons with explicit precision admission and 18 tests. Its new source-bound
receipt is the active stage evidence; the original artifacts are retained.

**Done: bounded offline analytical acceptance benchmark.** This adds executable
verification and report admission for the existing experimental RT0 path, not
a new production solver. Full PI01-S02 and actual-board qualification stay open.
The [method record](../PI_FINITE_CONTACT_BENCHMARK.md) contains the independently
authored governing derivation, primary sources actually reviewed, assumptions,
units, frozen tolerances and explicit limits.

## Executed evidence

- [Source-bound receipt](parity/PI01-S02A-qualified-20261021.json),
  raw test log (unbundled local record: `parity/PI01-S02A-qualified-20261021.log`), and
  [complete retained ladder](parity/PI01-S02A-ladder-20261021.json): **9 tests,
  no skips**, all passing; 18 source files hashed before/after and checked
  against the current tree. The ladder additionally runs all 12 solves.
- **47 tests, no skips**, in one focused invocation: the nine new tests plus
  `test_dc_copper_domain`, `test_dc_rt0_density`, `test_peec_conforming_dc` and
  `test_peec_rt0_iterative`. Existing angular-annulus, exact-rank, finite-contact,
  conservation, barrel and iterative equivalence checks passed unchanged.
- Actual benchmark CLI creates and revalidates saved JSON; a repeated output
  path rejects without overwriting. Corrupted references, tolerances, ordering,
  volume, contact identities, solver status, raw work and NaNs reject.
- Independent Astra numerical review derived mean terminal potentials and
  integrated Joule power independently. It exposed two report-validation P2s:
  trusting the saved work-error diagnostic and accepting invalid node/count
  metadata. Both were repaired. The reviewer reran all nine tests and the
  original forged-work/NaN/missing-count counterexamples; no blocking findings
  remain for this bounded scope. Knowledgeable human release review is pending.
- **15 tracking/evidence tests passed**, no skips, including the actual new
  receipt, corruption controls and all current Done-stage source envelopes.
  Architecture and scoped whitespace checks passed. The recorded-reference
  inventory was regenerated; its separate consistency check passed. This is
  focused evidence, not a new full-suite, installed-package or release pass.

Runtime: Python 3.11, NumPy 2.2.6, SciPy 1.17.1, Shapely 2.1.2. No external
solver implementation, fixture or dataset was incorporated. No new dependency.
Production kernels, dispatch, board requests and thresholds were not edited.
Prior stage source envelopes are revalidated by the backlog checker; no prior
numerical stage required replay because none of its bound files changed.

## Results and physical limits

All four cases use target sizes 0.5 / 0.25 / 0.125 mm. Base relative resistance
errors are **1.46484375% / 0.36621094% / 0.09155273%**: factor-four improvement.
Rotated-mesh, doubled-conductivity and retained inactive-island cases reproduce
this behavior. Finest relative resistance errors are below the predeclared
0.2%; p95/p99 endpoint errors are below 1.4e-13 in these runs, within the
predeclared 2%. Those percentile results exercise a broad constant-current
plateau; they do not establish contact-ramp or arbitrary-board density accuracy.
Separate planar heat and conjugate terminal work agree within unchanged gates.
Heat is W at 1 A; no energy J or thermal-cell deposition is inferred.

An initial rotated-polygon overlay trial failed the existing degenerate/ill-shaped
triangle guard. A retained negative regression confirms that rejection; it is
not counted as a successful physical solve. The positive rotation fixture
rotates a conforming partition, preserving incidence and contact ownership.
General rotated overlay compilation remains a blocker; no slivers were removed,
current zero-filled or tolerances relaxed.

This verifies planar distributed contacts, not equipotential electrodes or
3-D landing/barrel ownership. EBrake's physical finite contact remains
unspecified and its density/AC failures remain; Marble AC/SI remains open.
No new EBrake/Marble execution or board pass is claimed. Continue with conforming
contact/geometry/axial ownership and actual original-board convergence before
closing PI01-S02 or claiming proper general-board SI/PI.
