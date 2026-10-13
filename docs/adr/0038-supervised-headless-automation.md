# ADR 0038: Supervised headless automation

Status: accepted for source implementation; packaging verification pending.

## Context

The CLI exposes many analysis workflows, while the worker exposes project,
assembly, extension and solver services. Automation previously needed custom
Python code for worker-only methods. Default stdio MCP calls ran in-process,
so a stuck solver could stall the MCP host without an outer deadline.

## Decision

Keep domain authority in existing Python worker services. Add `worker-call`
and `workflow` CLI commands in `headless.py`, launching the existing source or
frozen worker entry point without shell interpretation or a desktop. Requests
are finite JSON objects; responses retain worker diagnostic and validity fields.
Deadlines terminate the owned process tree. Input is limited to 2 MiB; stdout
and stderr each to 32 MiB. Workflows contain at most 64 sequential steps,
may reference prior response JSON pointers, and stop on the first failure.

MCP retains a fixed tool allowlist and gains specific saved-project and assembly
methods. Default non-GUI calls use the same supervised worker, with a 120-second
default deadline configurable by `SPIKE_HEADLESS_TIMEOUT_SECONDS` (greater than
zero, at most 86400 seconds). Success and worker failure objects are available
as structured MCP content. No arbitrary dispatcher, shell, extension trust
change, or project-write tool is added to MCP.

## Consequences

The CLI is an explicit trusted local automation interface. It can invoke
mutating registered operations; callers must authorize those operations.
Worker revision/path/trust checks remain effective, but the worker is not a
general authorization broker or security sandbox. Workflows are not transactions
and do not undo completed writes. SIGINT cancels the owned worker; callers that
force-kill the CLI must also supervise its descendants.

Each operation starts a fresh worker, trading startup cost for isolated failure
and cancellation. Optional solvers still require installed runtimes and valid
inputs; no numerical capabilities or qualification states are upgraded.
Results beyond transport limits need existing artifact/file workflows.

See [user workflow and agent skill](../HEADLESS_AUTOMATION.md).
