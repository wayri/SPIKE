# ADR 0048: Consent-bound integrated assistant

Status: Accepted for source implementation; live-provider and native release
qualification remain separate gates.

## Decision

Add an in-app provider chat using Python transports, an OS-protected credential
store and a bounded frontend tool broker. Reuse SPIKE's loaded-board MCP analysis
conversation rather than introducing a second numerical or CAD execution path.
Cloud conversation consent and project sharing are independent. Switching either
consent or provider clears evidence-bearing history. Model calls never directly
execute a worker method. Edit/run proposals require explicit review bound to both
engineering-state and mutable prepared-case revisions. Read-only evidence is paged
or rejected when over budget. Imports remain existing user-selected file workflows.

## Consequences

The tool catalog doubles as the assistant's discoverable skill inventory. It is
version-controlled with actual implementation and capability limits. Numerical
validity remains a deterministic solver responsibility. Rust retains only process
supervision and cancellation. Local servers are loopback only; remote authenticated
server enrollment and non-Windows credential stores need separate contracts.
No project or transcript field is added for credentials. No arbitrary shell/code
execution, automatic extension trust or unattended engineering signoff is exposed.

See [assistant workflow](../INTEGRATED_ASSISTANT.md) for acceptance and limits.
