# SPIKE Engineering Governance

## Source of truth

The source of truth is the versioned project and result contract, not a UI panel, vendor object, or legacy demo script. The desktop shell, CLI, CAD adapters, and future cloud worker must consume the same contract.

Checked-in source, tests, fixtures, dependency manifests, ADRs, and release
records are sufficient to maintain the program. Chat transcripts, AI memory,
private prompts, and undocumented generated state are not project records.

## Change classes

### Numerical change

Requires:

- Mathematical rationale.
- Fixture or regression test.
- Convergence or conditioning evidence.
- Before/after result comparison.
- Updated validity limits.

### Importer change

Requires:

- Fixture file.
- Object-count comparison.
- Unresolved-object behavior.
- Coordinate and unit test.
- Import-quality report update.

### UI change

Requires:

- Workflow description.
- Disabled/unsupported state behavior.
- Error and cancellation behavior.
- Screenshot or interactive review on supported viewport sizes.

### Packaging change

Requires:

- Clean-machine install test.
- Offline launch test.
- Upgrade test.
- License/dependency manifest update.

## Accuracy policy

SPIKE must never represent an approximation as validated. Every result includes:

- `model_status`.
- `validity_range`.
- `assumptions`.
- `warnings`.
- `solver_version`.
- `mesh_summary`.
- `convergence`.

## AI-assisted development policy

AI may help create adapters, UI code, documentation, and test scaffolding. AI-generated numerical changes require human review and fixture-based verification. AI explanations may summarize an issue but cannot alter severity, hide a warning, or approve a failed validation.

AI use is optional. Every AI-assisted change must be reviewable, reproducible,
buildable, and testable with ordinary local tools. Generated code has no relaxed
quality gate. Commit messages and documentation describe engineering behavior,
not the prompt that happened to produce it.

## Architecture policy

- Dependency directions in `ARCHITECTURE.md` are enforced by
  `scripts/check_architecture.py`.
- New EDA sources use importer adapters and return `DesignIR`.
- New solvers use the solver SDK/registry and return `AnalysisResult`.
- Process, persistence, contract, rendering-engine, and plugin-boundary changes
  require an ADR.
- Existing oversized composition modules are recorded debt. New functionality
  must not expand them when a focused service or component is viable.
- The application must remain useful offline and source-agnostic.

## Stability policy

Long operations require an operation ID, visible state, timeout, bounded memory
or data size, structured failure, and a recovery path. New worker operations
must be classified as light or heavy. Heavy work cannot execute on the UI event
thread. Silence, indefinite spinners, and swallowed exceptions are release
blocking defects.

## Documentation map

- `README.md`: user-facing project entry point.
- `ARCHITECTURE.md`: system architecture.
- `CONTRIBUTING.md`: human-first contribution and review process.
- `docs/DEVELOPER_GUIDE.md`: reproducible setup, test, debug, and extension guide.
- `docs/DESIGN_PRINCIPLES.md`: SOLID and dependency rules.
- `docs/SUBSYSTEM_INDEX.md`: file-level ownership map.
- `docs/STABILITY_AND_RECOVERY.md`: failure domains and recovery behavior.
- `docs/IMPORTER_ARCHITECTURE.md`: source-agnostic EDA ingestion.
- `docs/CONTRACTS.md` and `schemas/`: wire contracts and compatibility rules.
- `docs/adr/`: accepted architecture decisions.
- `docs/BUSINESS_PLAN.md`: product, pricing, revenue, and sustainability.
- `docs/DEPLOYMENT_STRATEGY.md`: installers, CI, cloud, privacy, and upgrades.
- `docs/ENGINEERING_GOVERNANCE.md`: quality and release policy.
- `codex_migration/`: migration status and legacy history.

Every public feature should have one user document, one API/contract description, and one validation fixture or an explicit statement explaining why a fixture is not yet possible.
