# ADR 0076: SpiDeR interoperability and dual-era MCP

Status: implemented for development.

## Context and decision

MCP must discover typed engineering capabilities without becoming a second
solver API. SpiDeR already has a legacy solver-facing v1 contract and a typed
canonical v2 contract. Preserve both versions, their existing adapters and
native-v2 solver ownership. Add read-only bounded validation, normalization,
entity/reference querying and revision comparisons at the Python boundary.

Admit v2 into explicitly listed v1-only worker operations only after a shared
lossless projection check. Record input/projected revision evidence separately
from the numerical result schema. Do not silently use stale imported geometry
or omit typed inputs. Keep physical solver admission separate from structural
validation.

Expose these services through the existing worker, automation, CLI and fixed
MCP registry. Desktop queries use current canonical data and recheck its binding.
Rust remains an authenticated command transport; it does not implement design
schemas or numerical algorithms. Installed schema resources remain offline and
path-confined.

Support the modern 2026-07-28 per-request discovery core and retain the existing
2025-11-25 handshake. Share tool dispatch across both. Publish only implemented
capabilities; tasks, subscriptions, shell, generic dispatch and trust mutation
remain absent. Bound frames, pagination, resources and issue reporting.

## Consequences and verification

Existing v1 callers and legacy hosts keep their workflows. Modern clients can
inspect exact tool/catalog revisions and typed source identities. Some valid
canonical designs cannot be used by a legacy worker; explicit projection
failure is preferable to a successful solve of different geometry. Review-only
normalization can return its loss report for human assessment.

See [interface workflow](../MCP_SPIDER_INTERFACES.md),
[protocol checks](../MCP_PROTOCOL_UPGRADE.md) and
[SpiDeR checks](../SPIDER_INTEROPERABILITY.md).
