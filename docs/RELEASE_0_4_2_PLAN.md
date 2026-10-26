# SPIKE 0.4.2 release plan

Status: next development candidate, 26 October 2026. Application version 0.4.2;
release channel alpha. Experimental capability labels and all execution gates
remain in force. This plan does not approve publication or establish an
installed 0.4.2 release.

## Candidate scope

- Carry forward accumulated desktop navigation, recovery, viewport, setup and
  guarded solver integration described in the [previous scope](releases/v0.4.1.md).
- Include current source solver integration and its owning capability/evidence
  limits in [solver status](SOLVER_STATUS.md) and [integration map](SOLVER_INTEGRATION.md).
  Runtime availability and UI entry points do not establish solver qualification.
- Include [work examples](WORK_EXAMPLES.md), with offline assets, exact inputs,
  explicit setup/run prerequisites and readiness distinctions. Keep the current
  `test:work-examples` aggregate and bundled SI resources.
- Include [IBIS and spatial SI](SI_IBIS_SPATIAL_WORKFLOW.md), preserving explicit
  compile/run/trust admission, experimental model bounds and returned-data-only
  visualization. IBIS refinement and accuracy/coverage qualification remain open.
- Carry current [promo showcase](../examples/promo_showcase/README.md) and example
  source workflows, with source provenance, redistribution limits, prerequisites
  and original model-status labels. Promo presentation is not validation evidence.

## Version and artifact identity

The npm package and root lock entry, UI constant, Tauri config, Cargo package
and its lock entry, Python `spike_core` and CMake project use 0.4.2. Preserve the
alpha channel. Do not alter dependency versions, schema/fixture versions,
legacy core history, or the independently versioned SPIKES engine.

The existing `D:/SPIKE-0.4.2-beta-20261025` installed beta is a separate candidate.
Its binaries, receipts, hashes and source capture are not evidence for this
source tree or final 0.4.2. Earlier 0.4.1 Linux/macOS receipts retain their
recorded version and scope; the macOS hard-resource-limit admission issue stays
open until new evidence resolves it. Do not relabel retained artifacts.

`release_automation.version()` checks application authorities and WiX override
consistency; separately inspect the owned Cargo lock entry. Windows and Unix
release workflows derive package versions from canonical metadata. The local
beta staging helper derives its source baseline and the native numeric core,
rather than requiring a frozen 0.4.1 baseline. No workflow dispatch, package
build, installation, tag, push or publication is part of this metadata update.

## Required acceptance before publication

1. Freeze a complete source revision, bundled worker/resources and dependency
   manifests. Record source and worker identity, exact tool versions and hashes.
   Regenerate evidence for changed inputs; retain historical evidence unchanged.
2. Run the full required project checks in `CONTRIBUTING.md`, including architecture,
   Python, TypeScript/parser and Cargo checks, plus affected solver/example and
   packaged-resource checks. Focused metadata checks cannot waive the full suite.
3. Complete knowledgeable human review of numerical changes, independent method
   evidence and validity limits under `NUMERICAL_METHOD_EVIDENCE.md`. Keep
   unsupported, approximate and experimental outcomes explicit. Complete or
   explicitly hold outstanding IBIS refinement; do not imply broad qualification.
4. Complete native desktop visual and interaction acceptance for accumulated UI,
   example staging, restore/error/recovery states and supported window sizes.
5. Build each Windows/Linux/macOS artifact from the frozen revision. Verify
   payload completeness and actual dependency/license notices, offline and
   clean-machine execution, upgrade, reinstall and uninstall. Resolve platform
   admission failures before claiming platform qualification. Prior beta or
   earlier-version receipts are not substitutes.
6. Review final candidate evidence and outstanding limitations with the owner.
   Obtain the publication decision only after this concrete candidate is reviewable.
   Follow `ATTRIBUTION_POLICY.md`: canonical wayri author/committer and local Git
   identity, pre-push guard and fail-closed publication actor/repository checks.

## Evidence for this preparation

Record the exact executed metadata checks and focused release tests in the
change report. No installed lifecycle, full suite, native UI, numerical human
review or cross-platform acceptance is asserted by this plan. Open gates above
remain required even when metadata consistency passes.

## Current local candidate

The [26 October integration receipt](validation/RELEASE_042_CANDIDATE_20261026.md) records the rebuilt worker, production frontend, promo examples, latest solver inclusion and failed full-suite baseline. This supersedes metadata-only preparation; publication and installed-platform qualification remain open.
