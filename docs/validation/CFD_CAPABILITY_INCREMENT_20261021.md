<!-- SPDX-License-Identifier: Apache-2.0 -->
# Coupled-equation and analytical-flow increment, 21 October 2026

Status: experimental equation/reconstruction verification. The
[engineering capability target](../CFD_CHT_CAPABILITY_TARGET.md) is not complete.
No general CAD, aerodynamic, engineering-turbulence or CHT/FSI qualification is
implied by this increment. No existing runtime admission or release gate changed.

## Delivered and executed

- `enclosure_rans_research.py`: actual closed-box mean/positive-SA-noft2
  coupling, not frozen eddy viscosity. Both equations are reassembled at the
  same accepted u,p and updated q. Original molecular Reynolds admission <=20,
  inherited conditioning, positive state, energy and failure/no-field checks
  remain active. Inputs explicitly identify manufactured sources.
- `enclosure_flow_analysis.py`: flux-preserving RT0 point probes and exact
  cell-local trajectories of a supplied stationary shared-face field. Boundary
  events prevent cell/solid skipping. Normal continuity does not imply
  tangential no-slip or valid recovered vorticity. This is not a new PDE solve.
- Three independently authored test modules: nine coupled-equation tests,
  three independent derivative/forcing/covariance tests, and fourteen
  analytical-field/reconstruction tests.
- `scripts/benchmark_cfd_capability_increment.py`: executes the tests, retains
  exact requests/results, **reads the retained JSON back into both APIs**,
  checks meaningful cross-cell traversal and binds all source/artifact hashes.

The [coupled method](ENCLOSURE_RANS_RESEARCH_20261021.md) and
[analysis method](ENCLOSURE_FLOW_ANALYSIS_20261021.md) retain governing equations,
units, numerical assumptions, reviewed primary sources, independent derivations
and executed observations. The separate
[research queue](CFD_CHT_RESEARCH_REVIEW_20261021.md) is not adopted code.

## Current-source benchmark receipts

Commands actually executed with warnings as errors:

```powershell
.venv-emerge3/Scripts/python.exe -Werror scripts/benchmark_cfd_capability_increment.py --output build/cfd-capability-increment-20261021-py311-final
.venv/Scripts/python.exe -Werror scripts/benchmark_cfd_capability_increment.py --output build/cfd-capability-increment-20261021-py312-final
```

Both passed **26 tests, no skips/expected failures**, then the retained n=12
coupled and traced-field cases. Sources were unchanged during each run. Each
receipt binds31 source/oracle/runner files plus the assertion log and four exact
JSON artifacts. Source, log and artifact hashes were independently recomputed
after execution and matched. Fresh output directories are required; failed or
historical runs are not overwritten.

The separate existing prerequisite suite was genuinely rerun after the final
serialization repair: **50 tests passed without skips**, with warnings as errors,
in83.888 s. Receipt `build/enclosure-prerequisites-20261021-final/receipt.json`,
SHA-256 `241ab01f00c9733770ff0c5f09e4659f8896d4cbf2f249e60e80abde8067558b`.
There are76 distinct affected tests on Python3.11 across these separate runs,
plus the26-test Python3.12 repeat; this is not a whole-project suite claim.

| Interpreter | Whole benchmark seconds | Receipt SHA-256 |
| --- | ---: | --- |
| Python3.11.9 | 20.976 | `e5be4bb45631690f61b9f4fd03da6f2e789eedba1bc134b86c17b862fbe67879` |
| Python3.12.9 | 22.410 | `e4b93442a27bd372af1a24521114ff115eda066fdcade5dd48036a506f0a330e` |

Receipts and their `assertions.log`, `coupled-request.json`,
`coupled-result.json`, `trace-request.json` and `trace-result.json` are in the
corresponding output directories above. The receipt retains OS/interpreter,
NumPy/SciPy identities. Elapsed seconds are observations on a concurrent
development host, not performance/scaling qualification.

## Actual numerical observations

| n | Mean velocity relative L2 | q relative L2 | Outer iterations | Joint residual |
| --- | ---: | ---: | ---: | ---: |
| 4 | .1370932864 | .0229577627 | 3 | 9.546e-10 |
| 8 | .0607353161 | .0077845011 | 3 | 5.044e-10 |
| 12 | .0295241023 | .0040240235 | 3 | 4.244e-10 |

Predeclared gates remain finest velocity<.05, q<.1, each observed order>=.7
and both residuals<=1e-9. Velocity orders1.175/1.779 and q orders1.560/1.627
pass. The coarse13.7% velocity error is retained; this is not a general accuracy
bound. The n=4 closure feedback changes velocity by6.24% relative to the same
source solved with molecular viscosity alone. Its first outer momentum residual
is about.12; accepting the stale subsolve certificate would have been wrong.

The retained n=12 result has molecular Re upper bound1.29055, maximum nu_t/nu
.73436, divergence5.474e-16 /s and relative mean-work defect2.518e-12. The last
mean subsolve's scaled condition estimate is about17795; it is labeled as that
subsolve's heuristic certificate, not a freshly factored final-state condition
bound. No general pressure-accuracy or physical turbulence claim follows.

Two traces through those actual accepted faces each crossed six cell faces,
retained105 points, and reached the100-second reconstruction-parameter limit.
Arclengths were.3099006978 and.3106262337 m. The predeclared demonstration
required at least10 points, one cell event and.05 m, with `time_limit` completion.
This parameter is not measured residence time or an unsteady pathline. Separate
tests cover obstacles, disconnected fluid, affine2D/3D exact trajectories,
independent arclength integration, volume/normal-flux identities, stagnation,
ambiguous-corner stops, strict budgets, malformed inputs and cancellation.

## Defects found and preserved regressions

During integration, a valid JSON numeric grid passed geometric validation but
reached private mean kernels expecting tuple-indexed NumPy arrays. It failed
closed rather than returning a wrong field. The new coupled module now
canonicalizes **after** exact geometry validation; it does not recompute or
repair forged geometry. Native and serialized requests produce identical
fields, and forged volumes/centers/widths/areas/parents remain rejected. Field
analysis also has a native/JSON output and digest equivalence regression.

Earlier24-test/pre-replay receipts remain historical. Their hashes were not
patched. Both26-test final runs above were genuinely rerun after the repair and
new replay regressions. The field-analysis source normalizes admitted NumPy
coordinate scalars before hashing rather than rejecting them accidentally
during JSON encoding.

Independent review checks are now reproducible in
`test_enclosure_rans_independent.py`: complex-step closure differentiation,
separately differentiated polynomial forcing, and density/extreme time-unit
covariance. Agent review supplements, but does not replace, knowledgeable human
numerical review before release.

## Remaining engineering work

General conforming CAD/mesh and open boundaries, boundary layers and qualified
turbulence regimes, turbulent thermal closure, coupled temperature/material
feedback, general external forces/pressure qualification, real rotating blades,
UI/worker exposure, physical correlation and release qualification remain open.
The existing coarse stress-order and re-entrant-obstacle accuracy limits remain
in their prior records. No flag was promoted or test budget relaxed.

Compilation and scoped whitespace checks passed. The current architecture guard
passed. The research reference inventory is regenerated separately; these checks
do not establish clean-machine packaging, Linux/MPI or human release approval.
