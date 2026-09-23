# ADR 0003: Importer Registry

- Status: Accepted
- Date: 2026-08-09

## Context

SPIKE needs KiCad, IPC-2581, ODB++, Gerber packages, and eventual Altium,
Allegro, and Xpedition support. Central extension checks and direct parser use
would spread vendor coupling across the application.

## Decision

Use an importer protocol and registry. Each adapter declares source IDs and
extensions, parses one source family, normalizes into `DesignIR`, and records
provenance. Ambiguous and unsupported formats fail explicitly. Source-specific
parsers are imported only inside adapter modules.

## Consequences

- New formats are additive and independently testable.
- Standards-first ingestion can coexist with native vendor bridges.
- Format detection must handle package/directory sources in a future extension.
- Frontend and backend registries currently both exist; their descriptors need
  a generated/shared catalog as the contract matures.

## Rejected alternatives

- A single parser with format conditionals: violates open/closed design and
  grows a fragile central module.
- Native vendor APIs throughout SPIKE: prevents offline interchange workflows.
- Filename extension alone as proof of validity: detection selects an adapter,
  but the adapter must still validate content.
