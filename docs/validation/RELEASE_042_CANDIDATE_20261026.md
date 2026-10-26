# 0.4.2 integration candidate - 26 October 2026

Status: local Windows frozen-worker and production-frontend candidate. No final
installer was built, no installation changed, and no tag/release was published.
Application metadata is 0.4.2 with the alpha/experimental channel retained.

## Integrated scope

- IBIS driver/Input sink workflow and sampled SI noise, with explicit native
  runtime admission, project persistence and source-bound display.
- Unified main-viewport playback for returned thermal, PI and CFD histories.
- Latest OpenFOAM rectilinear/component proxy preparation, native streamline
  export, tetrahedral subdivision and volume-only optimization with the existing
  surface, mesh and resource gates preserved.
- 38 searchable examples, 76 bounded text assets, seven complete saved promo
  snapshots and two original browser-preview capture guides. Original license,
  source/result identity and incomplete-case limits remain explicit.

See [latest solver audit](LATEST_SOLVER_INTEGRATION_20261026.md),
[example workflows](../WORK_EXAMPLES.md) and
[promo provenance](../../examples/promo_release/README.md).

## Actual artifacts

Candidate root: `D:/SPIKE-release-candidates/0.4.2-20261026-r1`.
`candidate.manifest.json` binds the worker, integrity manifest, all 233 frontend
files, catalog and eight latest backend owners. The production frontend is
130,040,788 bytes including pre-existing public assets and lazy example chunks.
TypeScript passed; Vite completed in 41.00 seconds. Large-chunk and mixed
static/dynamic-import warnings remain; these are not performance acceptance.

Worker executable SHA-256:
`75999760bad82bcca76925ecbce771d02df4e770248decc3e952b6bf5ff0cf13`.

Candidate manifest SHA-256:
`7cad7ba93b1a2fea3ea4c6ac114a356581070dc6e2bc08b09f82267274f70c68`.

The worker passed the existing full verifier: 15/15 benchmarks, 8/8
source/frozen runtime comparisons, schema and native CFD/CHT/momentum/tetrahedral
probes, geometry/extension probes, IBIS/spatial IPC and 558-module source
coherence with no missing/changed/required-missing modules. Separate PYZ
inventory checks verified all eight audited latest solver owners are present,
including the rectilinear, streamline and subdivision additions missing from
older workers. This does not qualify their physical accuracy.

The normal CLI restricts candidate outputs to repository build/. Because C:
had about 400 MB free, the retained D: build driver called the same existing
builder with task-owned D: output/scratch/report globals. Source/native inputs,
all verifier calls and the manifest writer were unchanged. Existing workers,
installed beta and previous artifacts were preserved. No broad source copy,
cache deletion or new dependency installation was performed.

## Verification history and remaining failures

The first freeze compiled but failed `runtime.external_engines` comparison.
The existing builder raises before retaining the failing inventory, so that
first exact difference is unavailable. A separately retained diagnostic replay
passed 8/8; a subsequent complete unchanged verifier also passed and generated
the candidate manifest. The initial log remains under the candidate root.
Its root cause is **unresolved**; the failure was not hidden or the gate weakened.

Current focused evidence includes 32 backend tests and the five-script transient
UI aggregate from the latest solver audit; the example/resource, project
save/reopen, SI workspace and source-binding aggregates; and metadata/release
checks. Offline Help passed for 2771 control sites, 114 CLI pages and 90
diagnostics. Architecture, shared controls and documentation checks passed.
Final integration-owner checks passed: 42 focused Python tests, project/package round trips, the architecture guard, shared controls and eight scoped documentation files. No new full-suite success is claimed.

The retained full suite is **failed**: 5728 tests, 2 failures, 5 errors,
87 skips. It predates the final subdivision changes and does not establish a
result for this exact candidate. Failures include stale native parity evidence,
CLI timeouts, the manufactured Stokes runtime gate and a Python debug-child
lifecycle expectation. They require repair/requalification without weakening
acceptance criteria. See the exact audit and retained log hash above.

IBIS strict voltage refinement remains unmet at three probes. Detailed
polygon-prism CAD CHT timed out without fields. Proxy CFD, sampled SI and
prescribed-angle motor examples retain their stated limits; none becomes a
fully qualified arbitrary-assembly, vendor-model or protocol implementation.

## Before publication

Freeze and review the complete source revision; obtain a passing full required
suite for those inputs; resolve or explicitly hold failed numerical gates;
complete knowledgeable human numerical review and native wide/narrow UI and
save/reopen acceptance; then build and qualify Windows/Linux/macOS delivery,
offline/clean-machine execution, upgrade and uninstall. Earlier 0.4.1 or separate
0.4.2-beta receipts do not substitute for these checks. The current candidate
contains a worker and frontend, not a verified final desktop installer.

## Later source follow-up

The [release-blocker follow-up](RELEASE_042_BLOCKER_FOLLOWUP_20261026.md)
records a later debugger repair and focused test recoveries. This r1 frozen
worker predates that repair and requires a rebuild before distributing it.
