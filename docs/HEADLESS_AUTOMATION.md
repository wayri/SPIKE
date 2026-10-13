# Headless automation

SPIKE can inspect projects, execute engineering studies, and create reports without starting the desktop application. The same worker remains responsible for input contracts, solver admission, numerical results, and capability status.

Use the CLI for scripts and CI. Use the stdio MCP server when a local LLM needs bounded tool discovery. Neither interface turns an available solver into a validated solver or upgrades an approximate result.

## Launchers

From a source checkout:

```powershell
python -m python.spike_cli --version
python -m python.spike_cli --help
python scripts/spike_mcp.py
```

The current source interface can also be included in a future rebuilt package:

```powershell
spike-worker.exe --cli --version
spike-worker.exe --cli --help
spike-worker.exe --mcp
```

On non-Windows systems the executable is normally `spike-worker`. Existing released packages may not contain these CLI or MCP entry points. Use the source checkout until a package containing them is built and verified.

The CLI writes JSON to stdout by default. Global options precede the subcommand:

```powershell
python -m python.spike_cli --compact --output artifacts/capabilities.json capabilities
```

Use `--quiet` with `--output` when a caller needs no stdout copy. Use `--fail-on-warning` when warnings must fail CI.

## Discover the installed capabilities

Start each portable workflow from the runtime being used for the solve:

```powershell
python -m python.spike_cli --output artifacts/capabilities.json capabilities
python -m python.spike_cli --output artifacts/capability-ledger.json capability-ledger
python -m python.spike_cli --output artifacts/solvers.json solvers
python -m python.spike_cli --output artifacts/available-solvers.json solvers --available
```

`capabilities` reports the running worker. `capability-ledger` describes ownership, validation, and release gates. `solvers` includes validity limits; `solvers --available` filters the catalog to the current runtime. Registration, availability, input admission, completion, and qualification are separate facts.

For a local assistant or another MCP client, export the exact allowlisted tool
catalog without starting the stdio server:

```powershell
python -m python.spike_cli --output artifacts/assistant-tools.json assistant-tools
```

The catalog includes each MCP tool description and JSON input schema plus the
protocol version and safety policy. It is generated from the same registry used
by `scripts/spike_mcp.py`, so it is suitable for prompt context, tool selection,
and client configuration. Catalog membership describes reachability, not solver
availability, successful input admission, completion, or qualification. The MCP
registry excludes arbitrary worker dispatch and shell execution; use the
documented CLI `worker-call` path for reviewed worker requests.

## Inspect a saved project

Inspection does not extract or rewrite the package:

```powershell
python -m python.spike_cli --output artifacts/project.json project-inspect examples/optycal/viewport_example.spike
python -m python.spike_cli --output artifacts/validation.json validate examples/optycal/viewport_example.spike
python -m python.spike_cli --output artifacts/design-summary.json inspect examples/optycal/viewport_example.spike --section summary
```

Use `project-inspect` to confirm the project format, manifest identity, boards, studies, and retained state before selecting work. Use `validate` for geometry and contract diagnostics. Do not run a project merely because it opens successfully.

## Explicit request workflow

For PI analyses, the `setup-dc`, `setup-ac`, and `setup-transient` commands build a versioned request without solving it. Their matching `analyze-*` commands perform the solve directly. Saving the request gives review and CI a durable input:

```powershell
python -m python.spike_cli setup-dc board.kicad_pcb `
  --net VCC --source "10,20,F.Cu,3.3" --load "40,20,F.Cu,1.0" `
  --save-request artifacts/vcc-dc-request.json

python -m python.spike_cli --output artifacts/vcc-preflight.json `
  preflight artifacts/vcc-dc-request.json

python -m python.spike_cli --output artifacts/vcc-result.json `
  run artifacts/vcc-dc-request.json
```

Use `mesh-preview` only to inspect the pre-solve mesh. Mesh generation is not solver completion. Use `converge` when the analysis requires mesh-convergence evidence.

`run` accepts a versioned analysis request, a batch manifest, or a `.spike` project. This legacy project path derives its supported analysis request from project state; it is not a general saved-study selector. Use the bounded worker calls below for exact saved assembly study operations.

## Exact worker calls

`worker-call` runs one registered SPIKE worker operation in an isolated worker subprocess and preserves its full response envelope:

```json
{
  "method": "capabilities",
  "params": {}
}
```

```powershell
python -m python.spike_cli --output artifacts/worker-capabilities.json `
  worker-call requests/capabilities.json --timeout-seconds 30
```

Use the worker method catalog and project inspection to construct domain-specific requests; do not invent method names or parameters. Every registered operation is reachable, including operations that explicitly mutate files or registered settings. `worker-call` does not grant permission or bypass worker enforcement: the caller must authorize each mutation, and the worker still applies its contracts, path checks, and gates. A worker envelope with `ok: false` produces a nonzero CLI exit. The subprocess has a bounded response and the launcher terminates its owned process tree on timeout.

## Sequential workflows

`workflow` executes a bounded list of named worker calls in order. A later `params` value can reference a prior step's response with `{"$ref":"stepName#/result/path"}`. The fragment is a JSON Pointer into the prior full worker envelope.

```json
{
  "contract": "spike/headless-workflow/v1",
  "steps": [
    {
      "name": "load",
      "method": "load_design",
      "params": {"path": "C:/work/board.kicad_pcb"}
    },
    {
      "name": "validate",
      "method": "validate_design",
      "params": {
        "design": {"$ref": "load#/result"}
      }
    }
  ]
}
```

```powershell
python -m python.spike_cli --output artifacts/workflow-result.json `
  workflow workflows/validate-project.json --timeout-seconds 120
```

References can only address completed earlier steps. Use exact step names and RFC 6901 JSON Pointer escaping. A workflow stops at the first failed step, keeps completed step envelopes for diagnosis, and does not roll back completed mutations. Treat the plan as code: review any file write, registration, or other mutation and run it only with the caller's authorization.

## Timeouts and resource limits

Input documents are limited to 2 MiB; worker stdout and stderr each to 32 MiB,
and combined workflow result payloads to 32 MiB. Workflows admit 1..64 steps.
The combined result budget reserves room for step names and diagnostics.
Timeouts apply per step, not to the entire workflow. For MCP, set
`SPIKE_HEADLESS_TIMEOUT_SECONDS` in the server environment for longer analyses
(default 120, valid range greater than zero through 86400 seconds).

Use both layers when available:

- `worker-call` and `workflow --timeout-seconds` bound the isolated worker subprocess and terminate its owned process tree on timeout.
- An outer caller timeout bounds a stuck launcher or transport.
- A command option such as `--timeout-seconds`, `--max-solver-time-s`, or `--memory-limit-mb` bounds the solver or adapter according to that command's help.

Do not assume every solver uses the same option name or default. Read the installed subcommand help. Give the outer limit enough time for orderly solver cancellation and structured diagnostics.

On timeout, retain stdout, the exit code, the request, and any solver job directory. Do not treat a partial result or report as complete. An unchanged automatic retry usually repeats the same failure; adjust a justified bound, fix admission, or choose a supported solver first.

An OS policy that refuses process-tree termination produces `cleanup_warning`;
descendant cleanup is then unverified. Inspect owned solver processes before
restarting. A caller that force-kills the CLI must supervise its descendants too.

## Results and reports

Before consuming numerical values, check at least:

- top-level contract and `status`;
- `model_status` and solver identity;
- issues, warnings, and unsupported or missing inputs;
- units and input/design provenance;
- convergence, benchmark, or qualification evidence required by the claim.

Generate a report only from the retained result:

```powershell
python -m python.spike_cli report artifacts/vcc-result.json `
  --report-format html --report-output artifacts/vcc-report.html
```

Supported report formats are `html`, `pdf`, `csv`, and `json`. The report inherits the result's scope and validity. Report generation does not validate an approximate, experimental, screening-only, partial, stale, or unconverged result.

## Exit codes and errors

Headless execution returns these diagnostic codes. Preserve prior outputs and
repair the specific condition before retrying:

| Code | Recovery |
| --- | --- |
| `SPIKE-HEADLESS-START` | Repair the source/frozen worker installation or interpreter path. |
| `SPIKE-HEADLESS-TIMEOUT` | Inspect solver limits and inputs; choose an explicitly justified time bound. |
| `SPIKE-HEADLESS-CANCELLED` | Inspect any already completed writes before restarting. |
| `SPIKE-HEADLESS-OUTPUT-LIMIT` | Use existing artifact/file outputs or a smaller bounded result request. |
| `SPIKE-HEADLESS-EXIT` | Read the returned stderr tail and repair missing dependencies or runtime failures. |
| `SPIKE-HEADLESS-PROTOCOL` | Repair malformed stdout or response identity; diagnostics belong on stderr. |
| `SPIKE-HEADLESS-REFERENCE` | Correct the prior-step name or JSON Pointer; completed writes are not undone. |

The CLI uses these process exit classes:

| Code | Meaning |
| --- | --- |
| `0` | The command completed; inspect the returned engineering status and validity. |
| `1` | Usage or operational CLI error. |
| `2` | Analysis failed. |
| `3` | Validation failed. |
| `4` | Warning promoted by `--fail-on-warning`. |

Operational failures are emitted as structured JSON on stdout, including `ok: false`, an error type, and a message. Check both the process code and JSON. Keep stderr for launcher/runtime diagnostics and never infer success from an output file's existence.

## MCP and local LLM use

The MCP server is a local stdio process. Configure the host to launch `python scripts/spike_mcp.py` or a future packaged worker containing the feature with `--mcp`. The server exposes a fixed allowlist and does not expose a shell, generic worker dispatcher, arbitrary file reads or writes, extension trust, or project save.

Non-GUI project and assembly tools are available without the desktop bridge:

| Tool | Required input | Purpose |
| --- | --- | --- |
| `spike_read_project` | `path` | Read a supported `.spike` project through the worker's project-package boundary. |
| `spike_linked_assembly_nets` | `request` | Resolve explicit linked-net identity for an assembly request. |
| `spike_prepare_multiboard_study` | `request` | Validate and prepare a reduced multiboard study without solving it. |
| `spike_run_multiboard_circuit` | `request` | Run the reduced multiboard PI or SI circuit domain selected by the request. |
| `spike_run_multiboard_thermal` | `request` | Run the reduced multiboard thermal model selected by the request. |
| `spike_run_multiboard_em` | `request` | Run the reduced multiboard EM screening model selected by the request. |
| `spike_prepare_assembly_field` | `request` | Prepare an admitted assembly field study. |
| `spike_run_assembly_field_thermal` | `request`, `problem` | Run the assembly field thermal problem for the prepared request. |
| `spike_run_assembly_electrothermal` | `request` | Run the supported assembly electrothermal request. |
| `spike_import_assembly_field_study` | `record`; optional `current_request`, `current_problem` | Validate and import retained assembly field study evidence against current inputs when supplied. |

These names are bounded adapters to specific worker methods. They do not add new physics or strengthen existing qualification. Reduced multiboard circuit, thermal, and EM paths retain the limits reported by their worker results; assembly field import does not make stale or incompatible evidence current.

By default, each non-GUI MCP operation runs in a supervised source or frozen worker subprocess with a 120-second limit. A failed call returns an MCP error and keeps the worker response envelope in `structuredContent`, including worker diagnostic codes when present. Inspect that envelope before deciding whether to correct inputs, change an explicit bound through another supported interface, or stop. Do not repeat an unchanged timed-out call.

Use this order for headless analysis:

1. Call `spike_capabilities`, `spike_list_solvers`, and the relevant catalog tool.
2. Use `spike_contract_schema` and `spike_validate_contract` for input shape. Schema validity is not solver admission.
3. Read a saved project with `spike_read_project`, or load and validate a design with `spike_load_design` and `spike_validate_design`.
4. For saved assemblies, resolve linked nets and call `spike_prepare_multiboard_study` or `spike_prepare_assembly_field` before the matching domain run tool.
5. Inspect actual returned status, issues, provenance, model status, and validity evidence.

For manifest-bound occurrence placement and harness editing, including the
display-only boundary for hide, explode, and section controls, see
[Assembly command line workflows](ASSEMBLY_CLI.md).

Desktop `spike_gui_*` tools require the separately enabled loopback bridge and operate on the current desktop state. They are useful for a conversation bound to a loaded board, but unsaved study edits remain unsaved and the conversation's case/job records are transient. See [Local LLM control with MCP](LOCAL_LLM_MCP.md) for the asynchronous desktop analysis sequence and local model host examples.

## CI acceptance pattern

A useful CI job preserves and asserts:

1. exact command and SPIKE version;
2. input path plus project manifest or request identity;
3. selected study/case and solver;
4. process exit code;
5. result contract, `status`, `model_status`, issues, and provenance;
6. required convergence or qualification evidence;
7. explicit numerical tolerances;
8. result and derived report paths.

Command success and report creation alone are insufficient engineering acceptance evidence.
