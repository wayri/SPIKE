# PEEC repair follow-up — 2026-10-19

Status: **experimental numerical primitives verified in bounded cases; original
EBrake repair and release qualification remain failed.** No acceptance threshold,
original terminal, fixture, production density dispatch or passivity rejection
was relaxed. A successful helper test is not an original-board repair.

## Owner decision and physical input

The owner explicitly requested that the EBrake contact area remain unspecified;
no pad, probe area or pin/barrel boundary condition may be invented. The pinned
board SHA-256 is
`d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.
Independent native inspection puts the original load at (149.05,116.3) mm on
B.Cu inside J7.2's drill void. Its center is (149.075,116.275) mm, radius
0.475 mm; distance from the specified point is 0.03535533906 mm.
A track envelope entering a bore does not establish a finite conductor contact.
This prevents a silent reinterpretation of the existing graph diagnostic as a
specified continuum electrode. It does not invalidate the graph diagnostic or
prove that a bulk percentile can never converge.

## Implemented and independently checked

- Complete planar copper/void preparation and constrained triangle partitions,
  explicit finite-contact admission, local refinement and resource caps.
  Foreign-net drills and NPTH voids are retained; ambiguous drilled-pad types
  fail explicitly. Selected NPTH is not converted into an invented land/barrel.
- Signed RT0 vector-current reconstruction, local Joule-energy consistency and
  volume-weighted current-density percentile enclosures. Undriven represented
  planar volume is retained. Axial/landing ownership is explicitly incomplete;
  `complete_physical_volume` remains false.
- Exact binary64 weighted-rank fallback fixed a real percentile jump-collapse
  defect. Independent rational arithmetic checked 3,716 comparisons, including
  extreme and subnormal weights. This is not a formal outward-rounded interval
  proof for the entire field calculation.
- Regrouped Joule-loss arithmetic fixes a false zero from intermediate overflow
  at finite conductivity; nonzero-loss underflow fails instead of reporting zero.
- An independently authored same-slab affine magnetic integral, checked against
  separate rectangular and separated-volume oracles, reciprocity, scaling and
  finite-dimensional positive-energy tests. Its error estimate is a posteriori,
  not a certified bound. No production native binding or AC dispatch was changed.

Method derivations, sources, assumptions and limits are in
[DC RT0 density](../DC_RT0_DENSITY.md),
[affine slab kernel](PEEC_AFFINE_SLAB_KERNEL_20261019.md) and
[numerical method evidence](../NUMERICAL_METHOD_EVIDENCE.md).

Executed checks:

| Check | Actual outcome |
| --- | --- |
| Numerical/domain/old RT0 plus independent board-audit tests | 47 passed, 8.529 s |
| Exact-rational weighted-rank oracle | 3,716 comparisons passed; inputs unchanged |
| MSVC Release `test_affine_triangle_basis` | 1/1 passed, 14.40 s |
| GCC 16.2 Windows standalone affine checks | Passed; not Linux qualification |
| High-speed report renderer, Python 3.11 / 3.12 | 4/4 passed on each interpreter |
| Explicit KLayout 0.30.12 hierarchical GDS suite | 8/8 passed |
| Ordered benchmark/compiled-board/fault/GPIO group | 48/48 passed on each of Python 3.11 and 3.12 |
| Explicit pinned ngspice sine and synthetic PDK comparisons | 2/2 passed on Python 3.11 |

The renderer fix changes one f-string's nested quotation marks, preserving the
Python 3.12 AST while allowing Python 3.11 tokenization. Actual execution, not
`ast.parse(feature_version=...)`, verifies compatibility. Python 3.12's first
restricted-temp attempt failed with a filesystem permission error; rerunning
with a writable workspace temporary directory passed. ReportLab 4.5.1 was
installed for the 3.11 test profile from its SHA-256-verified upstream wheel;
this is not dependency redistribution approval.

## Unchanged original-board replay

Retained receipt:
`build/board-repair-source-bound-20261019-rechecked/report.json`, SHA-256
`b7e0b0c83b8b2ccf5c6b24a231353ac2c854662079dccf742d471bc9c30a604c`.
All 42 raw-artifact hashes were independently rechecked; 556 covered source
inputs, loaded native extension/runtime and five acceptance controls were stable.
Five groups including eleven public-board diagnostics actually executed.

- Original EBrake: 2 passed, **2 failed**. DC branch p95 changes
  10.7504311295 → 7.41691870367 A/mm², a 31.0082% delta against the unchanged
  10% gate. AC retains 46 outside-copper zone bases and four negative-energy
  modes; no projection or omitted-copper workaround was applied.
- Exact retained Marble refined DC ladder passed its 2% resistance gate:
  4.196854930 / 4.140156100 / 4.108869814 mΩ; successive changes
  1.36949% / 0.761433%. This does not close Marble AC or arbitrary-board density.
- Opt-in owned DC p95 refinement still fails its original gate. Marble AC,
  ambiguous EBrake SI reference selection and unsupported bent Marble SI paths
  remain explicitly rejected; approximate diagnostics are not promoted.

## Full regression, not a release pass

`build/qualification-20261019-followup/full-regression-002.json` SHA-256:
`003a8b77fc0a51240bfb969213d45f86558f770845a6b111c7e7301a40832992`.
The retained log SHA-256 is
`186859826285bf1789e49a514b64ccd597752ae6758e65e09486446c017ebef2`.

**4,397 tests, 2 failures, 19 errors, 6 skips; 1,584.574 s.** Both failures are
the unchanged EBrake tests. Runtime artifacts remained stable, but unrelated
help/gallery/document edits occurred during execution; whole-tree source
coherence did not pass. The receipt explicitly has `release_qualified: false`.
It must not be retrospectively relabelled using later focused test results.

One error was the now-repaired renderer Python 3.11 syntax incompatibility.
Sixteen GPIO errors identified an explicitly selected stale native DLL lacking
six required pad APIs. Two compiled-board setup errors correctly rejected a
different loaded-engine identity. The identity guard remains mandatory; a
matching ABI number alone is insufficient. Follow-up runtime rebuilding and
ordered mixed-consumer checks are recorded separately, not substituted for this
failed full run.

The follow-up rebuilt the current `spikes_c_api` target in an isolated folder
with MSVC and the existing admitted Eigen input, without overwriting the old
runtime. The new DLL SHA-256 is
`229692f7c6893959b90c02d5830a2eeb5062c27d379e240ba5e43762416df840`.
Two benchmark test fixtures had ignored the explicit native-library selection
and loaded a different DLL basename first. They now honor
`SPIKES_TEST_NATIVE_LIBRARY` with their legacy fallback retained. Assertions,
skip predicates, numerical budgets and the compiled-board engine-identity
check are unchanged. The ordered 48-case run includes both benchmark modules,
compiled boards/faults and GPIO/edge tests **in one process**, on each interpreter;
isolated pad-only passes are not used to explain away the earlier identity error.
Build inputs and raw logs are retained under
`build/qualification-20261019-followup-release/native-current/`.

Six recorded skips were CUDA, Windows symlink privilege, missing explicit
KLayout selection, two missing explicit ngspice selections, and Xyce. CUDA
remains owner-blocked until real hardware is available; Xyce is owner-deferred.
The later actual KLayout execution above closes that focused execution gap, not
the historical full-run skip or all release requirements.
The later two actual ngspice comparisons likewise execute those previously
unselected cases; the PDK fixture is synthetic, not foundry qualification.

## Remaining closure requirements

An owner-defined electrical contact interpretation is still required before
the original EBrake point request can be treated as a physical finite-contact
continuum problem. It remains unspecified by explicit owner choice.
Production work also remains: conforming copper/shared-contact compilation,
consistent axial/landing ownership, admitted mixed/inter-layer magnetic terms,
native assembly/bindings, frequency-dependent resistance, and unchanged-board
AC/density refinement. The new primitives alone do not satisfy these items.

Release additionally needs coherent full-suite evidence, qualified platform and
installed-package runs, dependency/legal approvals, signing/CI evidence where
required, and knowledgeable human numerical review. Current package artifacts
and those external approvals were not created by this work. No commit, push,
tag, signing, publication or qualification-status promotion is claimed here.
