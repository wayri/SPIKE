<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE Assistant: setup and user guide

This guide describes the current source interface as of 23 October 2026.
An older installed executable or local preview can have fewer controls and tools.
Rebuilding source does not update an already installed copy. Check the executable
you opened before troubleshooting a missing feature.

The Assistant connects a language model to a fixed set of SPIKE tools. Its useful
engineering workflow is **inspect → prepare → review → preflight → run → inspect
evidence**. It also explains attached text/images and drafts code. Unrestricted file browsing,
arbitrary Python execution, and automatic script installation are not chat tools.
A better prompt cannot enable a missing tool.

The new [task harness](ASSISTANT_TASK_HARNESS.md) adds a user-selected work folder,
bounded file inspection, deterministic CSV summaries and reviewed staging of
Python drafts. Use that workflow to avoid copying file contents and code by hand.

## Contents

- [Choose the right interface](#choose-the-right-interface)
- [Set up LM Studio](#set-up-lm-studio)
- [Set up Ollama](#set-up-ollama)
- [Connect SPIKE and prove it works](#connect-spike-and-prove-it-works)
- [Load a file or attach evidence](#load-a-file-or-attach-evidence)
- [Perform an engineering analysis](#perform-an-engineering-analysis)
- [Analyze existing results or CSV data](#analyze-existing-results-or-csv-data)
- [Write and run a script](#write-and-run-a-script)
- [Use an external agent, CLI or MCP host](#use-an-external-agent-cli-or-mcp-host)
- [Prompt patterns](#prompt-patterns)
- [Troubleshooting](#troubleshooting)
- [Persistence, privacy and limits](#persistence-privacy-and-limits)
- [Acceptance evidence and remaining limits](#acceptance-evidence-and-remaining-limits)

## Choose the right interface

| What you want | Use | What to expect |
| --- | --- | --- |
| Inspect the open project, nets, studies or assembly | Assistant with project tools enabled | Actual bounded tool evidence from the current desktop |
| Prepare and execute a supported analysis | Assistant analysis tools or the dedicated analysis workspace | Explicit inputs, review, preflight, jobs and returned results |
| Explain a small CSV, JSON, log, netlist or screenshot | Chat attachment | Model interpretation; numerical claims need independent calculation |
| Calculate one numeric CSV column's count/min/max/mean | Task harness `csv_summary` | Complete admitted file, explicit units and source hashes |
| Transform arrays or make a custom plot | Python workspace | Reviewed code runs locally and produces reproducible output |
| Draft a Python script | Chat's `spike_python_draft` tool, then review | Stages an unsaved editor tab; saving and running remain separate actions |
| Open a board or `.spike` project | SPIKE's Open/Import controls | Native import and diagnostics, followed by chat inspection |
| Read arbitrary folders, edit repository files or develop a multi-file program | A separately configured coding agent | That agent needs its own file/terminal permissions; SPIKE chat does not supply them |
| Automate saved requests and repeatable studies | CLI, Python workspace or external MCP client | Explicit contracts and runtime-dependent solver support |

Three things must work independently: the model server must answer, the model
must produce structured tool calls, and SPIKE must admit the requested operation.
Conversational fluency proves none of the other two. A tool appearing in the
catalog also does not prove a particular solver or input is supported.

## Set up LM Studio

1. Install/open [LM Studio](https://lmstudio.ai/). Obtain a model with tool-calling
   support through its model manager. Model downloads, licenses and disk/memory
   requirements belong to that provider; SPIKE does not download models.
2. Load the model. Start with one that fits available RAM/VRAM while SPIKE is
   open. Close other inference workloads during diagnosis. A small model can
   pass simple tools yet struggle with a long engineering workflow.
3. Start LM Studio's local API server, bound to `127.0.0.1`, port `1234`.
4. Confirm its loaded model identifier and server status. Use that exact
   identifier in SPIKE; a downloaded filename and a loaded API alias can differ.

Optional PowerShell setup with the installed `lms` CLI:

```powershell
lms ls
lms load "MODEL_KEY_FROM_LMS_LS" --identifier "spike-local" --context-length 8192
lms server start --port 1234 --bind 127.0.0.1
lms server status
lms ps
```

Replace `MODEL_KEY_FROM_LMS_LS`; it is not an actual model name. The 8192-token
context is an example configuration, not a minimum or a guarantee of quality.
Increase it only within the model/runtime's supported memory budget. SPIKE sends
system instructions, tool schemas, history and evidence as well as your question.

See the official [model-loading reference](https://lmstudio.ai/docs/cli/local-models/load)
and [server-start reference](https://lmstudio.ai/docs/cli/serve/server-start).
SPIKE's native worker talks to the API directly; it does not require browser CORS.

In SPIKE select **LM Studio**, endpoint `http://127.0.0.1:1234`, and probe models.
Current discovery prefers an already loaded model and preserves the rest of the
list for manual selection. Older compatible servers may lack loaded-state
metadata; inspect the selected model before sending, especially if several large
cached models are listed. This transport does not provide a local API-key field;
an authentication-required local server is not covered by this setup.

If `lms` wakes another application or times out, open the actual LM Studio app
and start its API server there. A previous local diagnosis found the CLI's
installation registration pointing at a separate Bionic app. Do not edit hidden
registration files blindly or assume that retrying the same command repairs it.

## Set up Ollama

1. Install/open [Ollama](https://docs.ollama.com/quickstart).
2. Obtain a local model with tool support through Ollama. Use its exact local
   name, including the tag. Choose a local model rather than a cloud-backed name
   if you require local inference.
3. Start the installed service if it is stopped:

```powershell
ollama serve
```

Keep that terminal/service running. If the port is already in use, check whether
Ollama is already serving instead of starting competing copies. In another
terminal:

```powershell
ollama list
ollama ps
```

In SPIKE select **Ollama**, endpoint `http://127.0.0.1:11434`, then probe models.
Choose an installed model. The first request can include model-loading time.
Ollama's [tool-calling documentation](https://docs.ollama.com/capabilities/tool-calling)
describes the structured calls SPIKE expects. A model printing a JSON-looking
command in normal text has not executed a tool.

For the earlier local acceptance, `qwen3.5:4b` returned text and used SPIKE tools;
this is a test record for that machine, not a universal model recommendation.
Model size alone does not establish tool reliability or engineering competence.

## Connect SPIKE and prove it works

1. Open the intended SPIKE executable. Create a disposable project for the test.
2. Open **Tools > SPIKE Assistant**, or search for **SPIKE Assistant** with
   `Ctrl+K`. In the current conversation-first layout, open the **Assistant
   settings** gear for provider, model, endpoint, sharing and the tool catalog.
   Earlier previews show those controls directly above the conversation.
3. Select LM Studio or Ollama. Model discovery checks the API connection;
   **Connected** does not yet prove successful inference or tool calling.
4. Send: `Reply with exactly SPIKE_LOCAL_READY.` Check that a response completes.
5. In Assistant settings enable **Share selected project context and enable
   SPIKE tools**. It is off initially, including for local models. This change
   clears that chat, so enable it before starting a project conversation.
6. Send this read-only test:

   > Call spike_status and spike_studies. Report the actual project name and
   > study count from the returned evidence. Do not change anything.

7. Expand **SPIKE activity** and the individual actions. Both tools must have
   completed evidence. Confirm the project name and count agree with SPIKE.
   A polished answer without activity evidence is not a successful tool test.
8. Send this edit test only in the disposable project:

   > Propose creating one study named Local assistant smoke test. Use
   > spike_create_study and wait for review. After applying it, use spike_studies
   > to verify its ID and name. Do not run an analysis.

9. Inspect the proposed name and revision. Choose **Apply once** to perform the
   test or **Reject** to leave the project unchanged. Confirm the created study
   appears in the study manager and tool evidence. Save the project yourself if
   you want to keep it.

The integrated Assistant does **not** require enabling the separate LLM/MCP
desktop bridge. That bridge is for external MCP clients and the local chat runner.
Enabling it will not add file or Python execution tools to integrated chat.

## Load a file or attach evidence

### Board, project, mechanical model or network input

Use the application's appropriate importer first: Open/Import for the supported
board/project type, the mechanical attachment editor for STEP, or the relevant
network workspace for Touchstone data. Inspect import diagnostics and select the
intended board occurrence. Then ask chat to inspect the current project.

Giving chat `C:\work\board.kicad_pcb` does not grant file access. The built-in
catalog has no arbitrary file-open tool. `spike_assembly_workspace` and
`spike_step_import` can open existing import controls; they do not choose a file,
import it, or create geometry. Attaching text is also not project import.
For supported text/data files, **Choose work folder** in Assistant settings grants
the harness bounded access using relative filenames; see the [harness guide](ASSISTANT_TASK_HARNESS.md).

### Small text files and images

In builds with attachment support, use the paperclip, drag files onto the
composer, or paste a screenshot. Review the attached names/thumbnails before
Send. Missing paperclip controls indicate a different/older build.

| Evidence | Admission limit |
| --- | --- |
| UTF-8 `.txt`, `.md`, `.csv`, `.json`, `.log`, `.py`, `.spice`, `.cir`, `.net` | Nonempty, up to 256 KiB each; binary/NUL content rejected |
| PNG, JPEG, WebP | Nonempty, up to 5 MiB each; at most four images per conversation |
| Combined attachment history | At most eight attachments and 20 MiB decoded content |
| PDF, audio, video, native CAD, `.xlsx`, binary result files | Not admitted as chat attachments |

Images require a vision-capable selected model with supported provider metadata;
a text/tool model may not support images. Unsupported images are rejected rather
than silently converted into usable model evidence. Text attachments are evidence
only: an attached `.py` file is never executed. For a workbook, export the relevant
sheet to a small UTF-8 CSV or analyze it through a reviewed local script.

Useful attachment prompt:

> Inspect the attached CSV's header, units, row structure and missing values.
> Separate directly observed fields from inference. Do not invent a computed
> maximum or average. Draft a reproducible calculation for the requested metrics.

## Perform an engineering analysis

Ask for one bounded study, naming the analysis type, target, quantities, units
and known inputs. “Analyze this board” leaves important choices unresolved. A
board supplies geometry/identity, not every source, load, boundary condition,
material property or circuit model needed to solve it.

### 1. Discover and specify

> Inspect the selected board with spike_status and spike_context. Use
> spike_capabilities for PI. I want the DC voltage drop on a 3.3 V power rail with
> a 1 A load. First list the actual candidate net/pad identities, the supported
> model, required source/load/return inputs and missing values. Do not run yet.

The voltage and load above are example user-supplied requirements, not defaults
to substitute into another design. Supply exact source/load locations and return
assumptions after inspection. For thermal, supply actual power, material and
boundary/environment data; for SI, geometry, frequency, ports and terminations
must be explicit. Obtain each solver's current schema and validity limits from
capabilities; do not invent a universal parameter dictionary.

### 2. Prepare a draft and review it

> Using the agreed inputs and discovered contract, call spike_prepare for the
> admitted analysis kind and scope. Show the returned case ID, missing inputs,
> units and assumptions. Propose spike_patch only for values we have established.

`spike_prepare` creates a transient analysis draft. `spike_create_study` creates
a study organization record. `spike_add_case` captures current setup in a study.
None of these operations is a completed solve, and their IDs are not interchangeable.
Preparation/patching requires review. `active_board` and `reduced_assembly` are
distinct scopes; reduced assembly models are not general full-wave multiphysics.

### 3. Preflight and inspect its job

> Request spike_preflight for that exact case. After review, poll spike_job using
> the returned job ID. Show ready status, missing inputs and model limitations.
> Stop if it is blocked. Do not substitute guessed engineering inputs.

Job submission is not completion. Poll the returned job instead of starting a
duplicate run. Correct missing inputs through a reviewed patch and repeat
preflight. If the project or prepared setup changes, the old admission is stale.

### 4. Run, inspect evidence, then present

> If the current preflight admits this exact case, propose spike_run. After I
> review it, poll its job to completion. Read spike_evidence and report actual
> values, units, convergence, assumptions and qualification. Do not call a failed
> or approximate result validated. Display the result only if retained output exists.

Review **Apply once** at each edit/run proposal. A tool error is useful evidence:
read it before retrying. Unsupported physics, missing dependencies, failed
preflights and nonconvergence require an engineering/runtime correction, not a
more persuasive prompt. See [solver status](SOLVER_STATUS.md) and the domain
[user guides](README.md).

## Analyze existing results or CSV data

### Retained SPIKE results

> Call spike_saved_results. Identify the actual thermal result IDs and their
> status. For the selected result, read spike_result_evidence, page the required
> fields and state units and omitted data. Show the retained result with
> spike_show_result and open its report with spike_report if supported.

Use IDs returned by the tools. Result field selectors are JSON selectors, not
file paths. Request small pages for arrays; a page is not the complete dataset.
For comparisons or statistics over a whole field, use the Python workspace and
verify that its result context is complete. Model-written arithmetic over a few
displayed samples is not a complete-data calculation.

### A deterministic CSV example

For a small CSV in the selected work folder, first ask `spike_work_files` for
`csv_summary` with the exact column and supplied units. It computes the summary
without running generated code. The script below covers a reproducible manual
calculation or the starting point for a reviewed Python draft.

For a CSV with columns `time_s,value_V`, this read-only script computes the
sample count, minimum, maximum and arithmetic mean of `value_V`. It rejects
missing, nonnumeric and nonfinite values. It does not calculate time-weighted
means, ripple bandwidth, uncertainty or solver validity.

```python
import csv
import math
from pathlib import Path
from statistics import fmean

path = Path(r"C:\work\samples.csv")  # Choose your actual input file.
values = []
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream)
    if not reader.fieldnames or "value_V" not in reader.fieldnames:
        raise ValueError("Expected a value_V column with voltage in volts")
    for row_number, row in enumerate(reader, start=2):
        try:
            value = float(row["value_V"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid value_V at CSV row {row_number}") from exc
        if not math.isfinite(value):
            raise ValueError(f"Nonfinite value_V at CSV row {row_number}")
        values.append(value)
if not values:
    raise ValueError("CSV has no measurement rows")
print({"samples": len(values), "min_V": min(values),
       "max_V": max(values), "mean_V": fmean(values)})
```

Run it in the Python workspace after reviewing the path and code. For values
`3.2, 3.3, 3.4`, expect three samples, minimum 3.2 V, maximum 3.4 V and mean
approximately 3.3 V. Adapt column names and units explicitly for another dataset.
This example retains the column in memory; use a bounded/streaming calculation
for a large file. Share its actual output with chat for explanation.

## Write and run a script

1. Ask chat for a draft with a precise input/output contract:

   > Draft a Python script for SPIKE's Python workspace. Read a CSV with columns
   > time_s,value_V from an explicit input path. Validate missing and nonfinite
   > data, calculate min/max/mean in volts, and print the sample count. Use only
   > the standard library. Do not execute it or overwrite any file. Explain how
   > I can check it with a three-row fixture.

2. Ask the Assistant to use **spike_python_draft** with that source and a simple
   title. Review the proposed source and choose **Apply once** to stage a new
   unsaved tab in the Python workspace. It retains the selected work folder for
   relative input paths and does not run or save the code. Older builds require
   manual copy/paste instead.
3. Review the returned code. Chat can draft incorrect APIs, formulas and paths.
   Prefer an existing Python workspace template for SPIKE-specific operations.
4. Inspect the draft in **Tools > Python workspace**, or create a tab and paste
   the code if using an older build. Save it yourself. Review all file writes and worker calls.
5. Run with its Run control or `Ctrl+Enter`; inspect stdout, stderr and errors.
   Run/Debug execute a local child with ordinary user file access, not a security
   sandbox. Only execute code you have reviewed.
6. Verify a small known result before using real data. Preserve the script,
   inputs, output, units and runtime version for repeatable work.

For loaded project inspection, the workspace exposes `import spike`,
`spike.design`, `spike.results`, inventory queries and registered worker calls.
Check `spike.results`'s `complete` status before treating it as a full result.
Use [Python workspace](PYTHON_WORKSPACE.md) and the
[SPIKE Python API](PYTHON_SPIKE_API.md) for actual interfaces. Chat can stage a
reviewed draft through the task harness; execution and saving remain user actions.

## Use an external agent, CLI or MCP host

These are separate execution environments. An external coding agent may have
file/edit/terminal tools; SPIKE's MCP server itself exposes a fixed catalog and
does not add a shell or arbitrary script execution. Connecting MCP to LM Studio
does not turn its chat into a repository coding agent.

For repeatable source-checkout work, run from the repository root using its
configured Python runtime. On this Windows checkout that is normally `.venv`:

```powershell
.\.venv\Scripts\python.exe -m python.spike_cli --help
.\.venv\Scripts\python.exe -m python.spike_cli capabilities
.\.venv\Scripts\python.exe -m python.spike_cli assistant-tools
.\.venv\Scripts\python.exe scripts/spike_local_chat.py --provider ollama --list-models
```

Choose the runtime containing SPIKE's dependencies; bare `python` can select an
unrelated interpreter. Use the [headless guide](HEADLESS_AUTOMATION.md) for saved
requests, preflight, execution, exact worker calls and sequential workflows.
It documents authorization and file-mutation implications beyond integrated chat.

For LM Studio's external MCP host, register the source `scripts/spike_mcp.py`
using an absolute script path and the configured Python executable. To control
the open desktop, enable **Settings > LLM / MCP > Enable bridge** and select the
intended rendezvous file when several SPIKE windows are open. Follow
[Local LLM and MCP](LOCAL_LLM_MCP.md) for the exact configuration and external
`spike_gui_*` tool names. Integrated names such as `spike_status` and external
names such as `spike_gui_status` are different catalogs.

**External LLM handoff** only produces a transcript for manual copy. It does not
launch an agent, attach tools to it, execute its answer or apply files it proposes.

## Prompt patterns

Provide **goal + target + supplied inputs/units + requested evidence + stopping
condition**. Break a failed long workflow into one inspected operation at a time.

| Vague request | More useful request |
| --- | --- |
| Analyze my board | Inspect the selected occurrence, discover supported DC PI inputs, and list missing source/load/return data before proposing a case. |
| Load this path | I will import the file with Open/Import. Then use spike_status and spike_context to verify the loaded board identity and diagnostics. |
| Analyze this data | Inspect the attached CSV schema and draft a read-only calculation for these named columns/units. I will run it and return actual output. |
| Write a script | Draft code for the Python workspace with an explicit input/output contract, existing API references, validation and a known-answer fixture. |
| Make the results look right | Read actual result IDs, convergence and qualification; identify the cause of the discrepancy. Stop rather than altering evidence or inventing a solve. |

If the model narrates a tool call without making one, ask for one explicit named
read-only tool and inspect activity. If it still fails, test a different installed
tool-capable model or use the direct workspace/CLI. Repeatedly enlarging a prompt
does not repair a missing tool or an incompatible model template.

## Troubleshooting

| Symptom | Check and next action |
| --- | --- |
| No settings gear, paperclip or activity view | Check which executable/build you opened. Source docs can be newer than the installed or preview binary. |
| Connection refused / cannot reach provider | Start the actual provider service; check its loopback address and port, then probe again. |
| Connected but no response | Confirm the selected API model ID, loaded state, memory and provider logs. First-load time can consume the request deadline. |
| It answers but never acts | Enable project tools in Assistant settings, then test spike_status. Look for completed activity, not promises. |
| It says a tool does not exist | Check the actual catalog and interface. The integrated and external MCP catalogs have different names and reach. |
| It cannot open a path or execute a script | Choose a work folder for bounded text/CSV inspection. Native imports and script execution still use the dedicated import/Python controls. |
| CSV numbers look invented | Require a deterministic calculation over the actual complete input, retain its output and check a small reference case. |
| It asks many engineering questions | The solver needs explicit physical inputs. Inspect missing-input evidence; avoid guessing merely to pass preflight. |
| HTTP 400 | Check model tool/vision support, request/context size and the provider's logs. |
| HTTP 404 | Probe model IDs again and check the endpoint. A loaded alias may differ from a cached model name. |
| HTTP 503, memory or loading failure | Inspect service logs and memory; load a model/context that fits, then retry deliberately. |
| Model request timeout | Reduce unrelated history/evidence, use one bounded task, inspect inference speed and loading. Provider turns have a 120-second deadline; long solver jobs are separate. |
| Tool/round limit | Split the workflow at a completed checkpoint; do not restart already submitted analyses. |
| Project changed / stale revision | Reinspect and request a fresh plan. Switching projects requires closing/reopening the Assistant session. Never bypass the revision check. |
| Desktop bridge unavailable | Applies to external GUI MCP tools: enable the bridge and select the intended live rendezvous file. |
| No module named jsonschema | The selected Python runtime lacks project dependencies. Use the configured `.venv` or packaged worker; see development setup before repairing it. |
| Screenshot rejected | Use PNG/JPEG/WebP within limits and a model with verified vision metadata; text/tool capability is insufficient. |
| No completed result after creating a study | Study creation organizes setup. Prepare, preflight, run and inspect the analysis job separately. |

For a reproducible issue record: executable path/version, provider/model ID,
whether project tools were enabled, the smallest failing prompt, exact tool
arguments/error, job/case IDs if present, and whether the equivalent direct
workspace action works. Inspect logs and attachments before sharing them; omit
credentials and private bridge tokens.

## Persistence, privacy and limits

- Chats and attachments live in the Assistant window's memory, not `.spike`
  project persistence. Closing discards them. Use a reviewed manual handoff for
  a transcript you need to keep, and save scripts/results through their own UI.
- New chat isolates provider, model, messages and consent. Provider/sharing
  changes clear the selected conversation. Multiple chats do not provide shared
  long-term agent memory.
- Local providers are reached through loopback HTTP. Cloud providers need
  separate conversation consent and API access. Project sharing is independent
  of cloud consent; sending attachments also sends them to the selected provider.
- The model receives a small project summary, not automatic access to every
  board file, result array or folder. Tools retrieve bounded evidence on demand.
- Current turn limits are eight rounds, sixteen total calls, and eight calls
  per provider message. History is bounded to 128 messages. Oversized context and
  unsupported media fail explicitly. Attachment limits are listed above.
- Cancel stops the model's owned worker request. Previously started analysis
  jobs remain separate; inspect their status before submitting another run.
- File/solver capability, successful execution and engineering qualification
  remain distinct. See [solver status](SOLVER_STATUS.md) for validated claims.

## Acceptance evidence and remaining limits

The 22 October local native checks exercised Ollama `qwen3.5:4b` reading project
status/studies and returning the correct answer. LM Studio with the locally loaded
`spike-gemma-4-e2b` alias read status/studies and created a study after an actual
Apply once review. Its subsequent read exposed a revision-handling issue; the
narrow fix and loaded-model preference passed focused regressions. Final native
retesting of the optimized preview was interrupted by the user. Those records
do not establish a solver-analysis run, arbitrary scripting, attachment acceptance
in that binary, or end-to-end correctness of every model and analysis path.

Current source attachment controls and Python-workspace capabilities are described
from their implementation and dedicated guides. A full model-driven engineering
acceptance still needs a named real input, specified units/boundaries, passing
preflight, completed solver job, independently checked numerical results and
retained evidence. This guide does not claim that the earlier chat smoke tests
established that acceptance.
