<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0101: Logical solver blocks and inert selection plans

Status: accepted for metadata and preview implementation, 18 October 2026.

## Context

Solver and support workflows span PCB, harness, MCAD collaboration and multiple
physics domains. Domain bulk selection needs explicit dependencies while current
first-party code remains bundled together. A future minimal-base distribution
requires stronger artifact security and compatibility contracts than exist now.

## Decision

Own the descriptor graph and deterministic dependency resolver in the Python
application-service boundary. Expose `spike/solver-blocks/v1` through the existing
worker method `solver_blocks` and under the solver-manager catalog. TypeScript
presents descriptors and sends selections without independently resolving domain
rules. Required edges expand transitively; optional edges are visible but inert.
Reject inconsistent IDs and cyclic graphs across the whole catalog.

Select all bundled first-party blocks by default, including adapter code. An
explicit empty selection retains only mandatory base. Separate external engine
requirements from bundled adapters. Mark external runtimes and planned work as
unresolved and propagate unresolved required prerequisites to consumers. This
preview does not infer runtime installation or numerical qualification.

## Consequences

These are logical workflow blocks within today's monolithic payload. There is
no install, uninstall, download, physical isolation or minimal-base release in
this change. Existing runtime/license/numerical gates remain in force. Future
installer and in-app downloads require independent version/ABI compatibility,
signed manifests and hashes, SBOM/license/redistribution records, platform
adapters, safe staging, atomic activation and rollback. See
[the contract and distribution gates](../SOLVER_BLOCKS.md).

Graph/selection and worker integration tests check complete suite mapping,
cross-domain closure, determinism and external/planned honesty. Numerical code
is unchanged; architecture and existing solver-manager tests remain applicable.
