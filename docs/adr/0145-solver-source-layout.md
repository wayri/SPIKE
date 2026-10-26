<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0145: Domain and subgroup source layout

Date: 24 October 2026. Status: implemented source organization; release and
physics qualification remain subject to existing gates.

## Context and decision

The owner requested physical organization of solver code following the domain
documentation, with updated imports/references and no numerical behavior change.
The former flat Python implementation tree obscured numerical versus service
ownership. Native directories used a separate naming layout.

Move implementation modules into `python/spike_core/solvers/<domain>/<subgroup>/`
and native sources into `src/solvers/<domain>/<subgroup>/`. Retain neutral contracts,
registries, services and executable command entry points at their existing
application boundary. Update import statements, dynamic import/mock targets,
native includes, CMake, packaging discovery and active documentation references.
No new numerical backend, constitutive law, tolerance or capability is introduced.

The machine-readable [layout manifest](../solvers/source-layout.json) identifies
every moved file. Python modules use canonical imports; the old internal flat
module locations are retired rather than duplicating numerical implementations.
External scripts importing those implementation modules must use the new paths.
Public root exports, request/result contracts and worker method names are retained.

## Source-relative resources and provenance

Repository-root calculations preserve their original physical ancestor. Named
sibling-source inventories use `solver_source_paths.py` for cross-subgroup files;
the basename keys and original SHA-256 algorithms remain unchanged. Moving and
editing import statements changes source identity even when mathematics is equal.

Historical validation receipts, hashes, saved fields and frozen artifacts are not
rewritten to pretend they qualify new bytes. They remain historical. Source-bound
gates must be rerun and newly bound; a fresh frozen build and installed lifecycle
qualification are separate from source tests.

The migration retains a local pre-move source backup and a computational-AST
receipt under `build/solver-reorg/`. The comparison excludes import nodes and
reverses the declared module/path and source-location adjustments before comparing
all other syntax. Regression tests supplement this structural check; it is not
a new physical-validation claim.

## Unpublished research

New optical/photonics, particle and electron-optics research stays local and
ignored. A fail-closed publication gate checks Git HEAD/index and optional
release file lists. It rejects forced additions too. CI and release entry points
run the gate. Existing public Optycal RF physical-optics workflows remain public,
as explicitly directed by the owner. No history rewrite, remote deletion or
publication is authorized or performed by this migration.

## Verification and maintenance

Run `scripts/verify_solver_layout.py`, `scripts/check_architecture.py`,
`scripts/check_private_research.py`, Python regressions, native builds/tests and
the required frontend/host checks. Verify frozen-module names against the new
canonical source tree when creating a new packaged worker. Domain READMEs link
source owners, setup, methods and evidence; the generated capability and block
catalogs retain runtime/dependency authority.
