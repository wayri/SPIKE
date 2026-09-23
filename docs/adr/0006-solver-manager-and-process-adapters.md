# ADR 0006: Solver Manager And Process Adapters

- Status: Accepted
- Date: 2026-08-09

## Context

SPIKE must choose native and third-party solvers without hiding validity limits,
executing arbitrary discovered binaries, coupling GPL libraries into the desktop
host, or allowing solver-specific settings to leak into the normalized project
and result contracts.

## Decision

1. Workload recommendation is capability- and runtime-gated. An unavailable
   workload has no recommendation; it does not silently fall back.
2. External physics engines execute only behind fixed process adapters. Engine
   libraries are not loaded into Tauri or the Python worker.
3. Local registration records an explicit path but grants no trust or execution
   capability. Removal forgets the registration and deletes no third-party file.
4. Managed installation stays disabled until signed package manifests, digests,
   SBOM/license metadata, atomic activation, and rollback exist.
5. Tuning uses typed, bounded, allowlisted schemas. Raw flags, source code,
   environment variables, and arbitrary library paths are forbidden.
6. Upstream candidate capabilities are distinct from implemented SPIKE adapter
   capabilities.
7. sparseLizard integration targets a separately licensed
   `spike-sparselizard-adapter`, not an arbitrary upstream example executable,
   in-process library, or project-compiled formulation.
8. EMI net recommendation is labeled screening-only. Far-field and compliance
   remain unavailable until validated field/result contracts exist.
9. Commercial deployment is a hard eligibility gate. Each engine and adapter
   must declare desktop redistribution, hosted execution, linking, source and
   notice obligations, SBOM coverage, and an approved replacement strategy.
   Discovery or technical compatibility alone never makes an engine eligible
   for a commercial build.

## Consequences

- The UI and CLI can expose one coherent manager now without claiming missing
  physics.
- Adding an engine requires discovery metadata, an adapter contract, provenance,
  resource controls, result normalization, fixtures, and a license review.
- Users may configure tuning before an adapter is installed, but that profile
  cannot make the engine runnable.
- GPL and other reciprocal-license obligations stay confined to separately
  distributed linked adapters, subject to legal review and complete compliance.
