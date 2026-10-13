---
name: spike-headless
description: Run and troubleshoot SPIKE engineering studies without the desktop UI through its checked-in CLI, packaged worker, or bounded MCP tools. Use for CI, local automation, saved .spike projects, deterministic solver runs, result validity, and report generation; use spike-ui for desktop-only interaction.

---

# SPIKE headless automation

Locate the SPIKE repository from the active workspace. Read its applicable `AGENTS.md`, `CONTRIBUTING.md`, and `docs/HEADLESS_AUTOMATION.md` before running or changing automation. Consult `docs/SOLVER_STATUS.md` for capability claims and `docs/LOCAL_LLM_MCP.md` when an LLM or MCP host is involved.

## Choose the surface

- Prefer the CLI for scripts, CI, explicit files, saved `.spike` studies, durable result files, and reports. In a source checkout invoke `python -m python.spike_cli`. A future package built from a revision containing these entry points can invoke `spike-worker --cli` (or `spike-worker.exe --cli`); do not assume an older installed package has them.
- Prefer the stdio MCP server when an LLM needs bounded discovery and structured tool calls. Use `python scripts/spike_mcp.py` in a checkout or `spike-worker --mcp` in an installed build.
- Use desktop bridge tools only when the request explicitly depends on the currently open workspace, view, or transient analysis conversation. The bridge is opt-in and does not make unsaved desktop changes durable.

Never substitute shell access, an MCP generic dispatcher, arbitrary file reads or writes, or extension trust for a missing bounded operation. Do not parse human-facing help text when JSON output or MCP schemas are available. CLI `worker-call` accepts registered worker operations, including explicit mutations, but retains worker revision, path and trust checks: confirm that the caller authorized each mutation.

## Discovery before execution

Discover the installed runtime rather than assuming that a solver shown in source is runnable. For CLI work inspect `capabilities`, `capability-ledger`, `solvers`, and the relevant project or input. For MCP work begin with `spike_capabilities`, `spike_list_solvers`, and the relevant schema or catalog tool.

Treat these states separately:

- installed or registered;
- available in this runtime;
- admitted for the supplied inputs;
- completed by the solver;
- validated or qualified for the claimed use.

An available command, schema-valid document, generated mesh, or completed approximate model does not establish a stronger state.

## Reproducible runs

Use the narrowest deterministic workflow supported by the installed interface:

1. Inspect and validate the input without extracting or modifying a saved project.
2. Select the exact saved study/case or construct and save an explicit versioned request.
3. Preflight when the workflow exposes preflight. Treat missing inputs and admission failures as blockers.
4. Run once with an explicit output path and an outer process timeout suitable for the workload. Also pass the solver's own timeout or memory controls when exposed.
5. Inspect `status`, `model_status`, issues, provenance, solver identity, units, and convergence or qualification evidence before interpreting metrics.
6. Generate a report from the retained result file. Preserve the machine-readable result beside derived HTML, PDF, CSV, or JSON reports.

Use `worker-call` for one exact registered worker request. Use `workflow` for a checked-in sequence whose later steps reference earlier envelopes. A workflow is sequential orchestration, not a transaction: it provides no rollback across completed steps. Include mutating methods only when the caller has authorized those mutations. The worker continues to enforce its own contracts, paths, and gates.

Do not retry an unchanged timed-out or failed job automatically. Preserve its JSON diagnostics, determine whether the failure came from admission, the outer process limit, the solver limit, or the runtime, then change one relevant condition before retrying.

## Output and failure contract

Keep stdout machine-readable. CLI operational failures are structured JSON; route process-launch diagnostics separately. Treat a nonzero exit code as failure even if a partial file exists, and treat a zero exit code as transport success only until the returned engineering status and validity evidence are checked.

Never turn a blocked, partial, approximate, experimental, screening-only, unconverged, stale, or unsupported result into a completed validated claim. Reports inherit the source result's status and limits.

## Acceptance evidence

Record the exact invocation, SPIKE version, input identity, selected study/case, output paths, process exit code, result contract and status, model status, solver identity, issues, and relevant validity evidence. For CI, assert these fields and required numerical tolerances; do not rely on command success or report existence alone.

When changing this skill or the automation interface, verify command help, one focused successful fixture, and one malformed or blocked input. Run `quick_validate.py` on this skill. Report untested external solver availability and package-only behavior as limitations.
