<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0044: Opt-in Prism snapshot bridge

- Status: source preview; installed-runtime and Prism-host qualification pending.
- Date: 2026-10-09.

## Context

Prism needs a simulation handoff to SPIKE without importing SPIKE numerical code
into its viewer/backend. SPIKE already has a trusted local process extension SDK,
an EDA importer registry and a common worker preflight/solver boundary. The active
SPIKE release checkout contains unrelated work that this integration must preserve.

## Decision

Add an opt-in source package under `integrations/prism`, outside the automatically
trusted distribution extension root. Its SPIKE manifest contributes capabilities,
snapshot import and design-bound analysis-result import through existing registries.
It adds no solver, new worker method, UI framework or desktop-host domain code.

The separate `bridge.py --request ... --result ...` endpoint accepts only the
versioned `spike/prism-request/v1` capabilities, inspect-board and analyze operations.
It imports exact UTF-8 KiCad bytes, verifies their SHA-256 and calls existing worker
services. Explicit `AnalysisSpec` is required for solving. Results carry the exact
source, design and study bindings; admission requires the expected current design
and study bindings and never supplies missing provenance to received physics.

Source-only imports preserve native identities and coordinates while omitting
machine-specific resolved 3D paths with a coverage warning. Both ends must use that
same snapshot policy. Enriched designs are different inputs and cannot inherit a
result merely because their PCB text matches.

Requests and results have finite JSON, depth and byte limits. Output uses an atomic
write and rejects request/source aliases. The supervising host owns process timeout,
cancellation and any external-engine process-tree cleanup. A trusted process is not
an OS sandbox. Frozen installers and manager-installed copies require qualification;
the verified source workflow discovers the package at its source location.

## Consequences

Prism can use a thin adapter to the endpoint, while desktop SPIKE can import the
same snapshot and admit completed results through its normal SDK. Unsupported and
blocked analysis states remain diagnostics; solver status and numerical data remain
unchanged. This boundary verifies lineage and structure, not solver accuracy.

Prism host implementation remains subject to the user's explicit approval. Its
existing authenticated job system should own execution/artifacts, and its initial
viewer workflow should use reports/charts and UUID navigation. A generic spatial
field-overlay API and dependent-asset snapshot are separate later contracts.

See [workflow and protocol](../PRISM_BRIDGE.md) and the versioned schemas in
`schemas/prism-{request,board,result}-v1.schema.json`.
