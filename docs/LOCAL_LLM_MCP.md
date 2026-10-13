# Local LLM control with MCP


Integrated desktop chat: [SPIKE Assistant](INTEGRATED_ASSISTANT.md), including provider consent, reviewed tools and assembly workflows.
Harness automation uses `spike_run_harness_pi`, `spike_run_harness_si` and
`spike_prepare_harness_em` with explicit request contracts. The first two run
bounded DC and supplied uniform-line SI models; EM returns unsupported field
requirements. See [harness engineering](HARNESS_ENGINEERING.md). Roles, net
names and twist pitch must not be used to invent missing electrical models.

For operation without a desktop, use the [headless workflow and portable agent
skill](HEADLESS_AUTOMATION.md). Saved-project and assembly tools use supervised
workers; `SPIKE_HEADLESS_TIMEOUT_SECONDS` sets their per-call limit (default 120,
maximum 86400 seconds). Tool results include structured content and retain worker
error codes. These additions are currently in source, after Windows v0.3.8.

SPIKE exposes a local [Model Context Protocol](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle) stdio server. It offers a fixed set of worker tools for capability inspection, design loading and validation, admitted PI and SI workflows, thermal estimates, and EM screening. Solver qualification, assumptions, and blocked preflights come from the existing SPIKE worker. The server also offers desktop tools for workspace selection, 2D/3D view, and study management when the desktop bridge is enabled.

The server does not expose a shell, generic worker dispatch, extension trust, project save, or arbitrary file write. Analysis tools may take time and return large results. A model response is guidance until a SPIKE tool reports a completed result.

## Analysis conversation against the loaded board

The desktop bridge exposes a discovery-first analysis conversation. The local
model can inspect the board currently loaded in SPIKE, prepare a case, request
missing inputs, patch its setup, run preparation and simulation, and read actual
returned evidence. It does not need to export and resend the entire board.

1. Call `spike_gui_analysis_context` for current nets, pads, layers, assembly
   scope and installed extensions. Call `spike_gui_analysis_describe` for the
   supported analysis paths and their contract schema filenames. Use
   `spike_capabilities`, `spike_list_solvers`, `spike_thermal_capabilities`
   and `spike_extension_catalog` for worker/runtime availability, qualification
   and contribution schemas. These catalog calls do not grant extension trust.
2. Call `spike_contract_schema` to read a published schema and
   `spike_validate_contract` to check supplied input objects. These tools read
   only installed schema catalog files and resolve references offline. Passing a
   schema does not establish physical or numerical solver admission.
3. Call `spike_gui_analysis_prepare` with an explicit `kind`, `scope` and
   `parameters`. Supported kinds are `pi`, `si`, `si_workflow`, `thermal`,
   `board_thermal`, `em`, `extension`, and reduced `multiboard_pi`,
   `multiboard_si`, `multiboard_thermal`, `multiboard_em` paths. Use
   `active_board` scope for one board and `reduced_assembly` for the reduced
   multiboard paths. Preparation returns a case ID, a loaded-design binding and
   missing inputs; it does not solve. `spike_gui_analysis_patch` replaces the
   supplied top-level parameter objects and invalidates prior preparation.
4. Call `spike_gui_analysis_preflight` with the case ID. It immediately returns
   a job ID. Poll `spike_gui_analysis_job` until preparation finishes and inspect
   `ready`, missing inputs and admission evidence. PI, compact thermal and EMI
   screening use their worker preflights. EMerge/Optycal use a generated-script
   preview with an exact source digest. Paths without a separate numerical
   preflight explicitly report that the worker validates them at execution.
5. After a passing current-revision preflight, call `spike_gui_analysis_run`.
   It also returns a job ID immediately; poll it instead of repeating the run.
   The desktop receives completed results for its normal result presentation.
6. Call `spike_gui_analysis_evidence` with `query` containing a result `path`,
   `offset` and `limit` (1–200) to read actual arrays, metrics, issues and
   provenance. Evidence pages are bounded; a missing or oversized path asks for
   a narrower query instead of inventing or silently truncating data.

For example, ask the local model: “Inspect the loaded board and determine what
inputs you need to estimate NEXT and FEXT from net A into net B. Show the model
limits, then prepare the admitted SI study, run it and explain the returned
coupling samples.” The model must discover actual net names and obtain explicit
reference geometry, frequency grid, port orientation and termination values.
It must not substitute the SI catalog's demonstration defaults for measured
board or endpoint properties. Eye calculations also need defensible timing and
source/receiver assumptions; missing bandwidth, failed passivity or unsupported
geometry remain blockers.

Cases are bound to the loaded design and assembly and to an exact revision.
Changing the board or assembly requires a new case; patching a setup requires a
new preflight. One MCP analysis job runs at a time, so long preparations do not
hold the short desktop socket open or create duplicate hidden simulations.
The conversation holds at most 32 cases and 32 retained jobs; restarting SPIKE
resets these transient conversation records. Repeating a preflight or run call
for an unchanged case returns its existing job ID. Patch the case to begin a
deliberate new execution.

Reduced multiboard paths require explicit circuit, contact, heat or inductive
models. Their draft requests contain missing values for review. They do not
advertise coupled full-wave assembly solving. EMI screening does not produce
radiation or compliance results. Trusted installed extensions retain their own
physics limits; MCP cannot trust an extension, execute arbitrary scripts, or
dispatch an arbitrary worker method.

## Desktop bridge

In the SPIKE desktop app, open **Settings → LLM / MCP → Enable bridge**. The bridge is off initially and listens only on `127.0.0.1`. SPIKE shows the private rendezvous file path. The MCP server discovers the newest active local bridge automatically; if several SPIKE windows are open, set `SPIKE_MCP_BRIDGE_FILE` to the path shown in the intended window. The file contains a private token and is deleted when the bridge stops or the app exits. Keep it local. GUI changes to studies remain unsaved until you save the SPIKE project.

## LM Studio as MCP host

[LM Studio supports local MCP servers](https://lmstudio.ai/docs/app/mcp). Open its **Program → Install → Edit mcp.json** and add the SPIKE entry, replacing the path with your checkout path and the Python executable with your configured SPIKE Python environment:

```json
{
  "mcpServers": {
    "spike-local": {
      "command": "python",
      "args": ["C:/path/to/SPIKE/scripts/spike_mcp.py"]
    }
  }
}
```

Load a local model with tool support in LM Studio. Ask it to call `spike_gui_status`, then `spike_gui_list_studies` or `spike_capabilities`. Desktop tools need the enabled bridge. Worker tools need the SPIKE Python runtime dependencies from `requirements.txt`. No remote MCP URL is needed.

When using a newly built packaged SPIKE worker, its executable supports `spike-worker.exe --mcp` as the MCP command. Set LM Studio's `command` to that executable and `args` to `["--mcp"]`. The current source checkout launcher remains available for development. A package built before this option was added needs rebuilding.

## Ollama or LM Studio through the local chat runner

SPIKE also includes a dependency-free client for the local [Ollama tool-calling API](https://docs.ollama.com/capabilities/tool-calling) and [LM Studio chat-completions tool API](https://lmstudio.ai/docs/developer/openai-compat/tools). Start the provider's local server and load a model that supports tools. From the SPIKE checkout:

```powershell
python scripts/spike_local_chat.py --provider ollama --list-models
python scripts/spike_local_chat.py --provider ollama --model YOUR_LOCAL_MODEL "Show SPIKE status and list studies"
python scripts/spike_local_chat.py --provider lmstudio --list-models
python scripts/spike_local_chat.py --provider lmstudio --model YOUR_LOCAL_MODEL "Which PI solvers are available?"
```

Omit the prompt for an interactive session. The default endpoints are `http://127.0.0.1:11434` for Ollama and `http://127.0.0.1:1234` for LM Studio. `--endpoint` accepts only a loopback HTTP origin with a port. The client sends the MCP tool schemas to the local model and executes only tools in SPIKE's allowlist. It caps each prompt at eight tool rounds and sixteen calls. It does not download models or start provider services.

The newly built packaged worker also supports `spike-worker.exe --local-chat --provider ollama` (or `lmstudio`) with the same options. This provides offline linking without a source checkout once that worker artifact is rebuilt.

For a GUI interaction, enable the desktop bridge first. For example, ask: “Show SPIKE status, create a study called ESP32 airflow comparisons, add thermal and EM cases, then open the Thermal run controls.” The model can prepare the study and open controls; it does not run a solver merely by opening them. Ask for a preflight before a worker analysis and inspect status and assumptions in the returned result.

## Troubleshooting

- “Connection refused” means the LM Studio or Ollama local API is not running at the selected endpoint.
- “Desktop bridge unavailable” means it is off, the app is closed, or `SPIKE_MCP_BRIDGE_FILE` points to a stale file.
- “No module named jsonschema” means the selected Python interpreter lacks the existing SPIKE worker dependencies. Install the project's requirements into that interpreter or use the bundled worker environment.
- If a small model does not produce tool calls, try a locally installed tool-capable model. Neither provider guarantees that every model will format tool calls correctly.

Retained result IDs from `spike_gui_analysis_context` can be opened with
`spike_gui_analysis_view_result`. EM field results accept actual `frequencyIndex`,
`quantity` and `sampleIndex` values; network-only results open linked graphs without
inventing a field overlay. `spike_gui_analysis_generate_report` opens the existing
offline engineering report preview for the loaded board and selected results. It
neither saves a file nor prints automatically. Unsupported output contracts remain
available through job evidence and the Local LLM panel rather than becoming a fake
viewport layer. EMI `completed_screening_only` retains its screening qualification.

## Updated MCP and SpiDeR interfaces

See [MCP/SpiDeR workflow](MCP_SPIDER_INTERFACES.md) for dual-era discovery, schema
resources, typed read-only design queries, revision comparisons and Studio
feedback admission. The existing desktop bridge still requires opt-in.
