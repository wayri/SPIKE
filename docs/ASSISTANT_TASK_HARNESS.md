<!-- SPDX-License-Identifier: Apache-2.0 -->
# Assistant task harness

The task harness gives the integrated Assistant a short path from local evidence
to useful work: select a folder once, inspect its admitted files, calculate a CSV
summary, and propose an unsaved Python editor draft. Existing analysis tools still
own preparation, review, preflight, execution and result evidence.

This is a source feature. Rebuild/reopen the application to obtain its controls;
older installed and local-preview executables do not change when sources change.

## Start a task

1. Open **SPIKE Assistant > Assistant settings** and select a working local
   provider/model. Follow the [setup guide](ASSISTANT_USER_GUIDE.md) if needed.
2. Choose **Choose work folder** and select a dedicated input folder in the native
   picker. It is shared across this project's chats and resets when the project
   identity changes or the app restarts. Changing it clears the selected chat.
3. Enable **Share selected project context and enable SPIKE tools**. Requested
   file evidence is sent to the selected model; cloud consent is still separate.
4. Give a bounded goal, the columns/units you know, and the desired output.

With an empty composer, **Inspect files**, **Analyze data**, and **Draft Python**
prefill a task request for you to edit and Send. They do not send automatically
or replace an existing typed message.

For a folder containing `measurements.csv` with `time_s,value_V` columns:

> List my work folder and inspect measurements.csv. Calculate a complete-file
> summary of value_V in V with spike_work_files. Report its count, minimum,
> maximum, mean and source hash. Then propose a Python draft that validates and
> reproduces that calculation. Stage it in the Python workspace after review;
> do not run or save it.

Expand **SPIKE activity** to inspect exact evidence. The numeric summary must
come from `csv_summary`, not the model's mental arithmetic. Inspect the proposed
source in the review, then select **Apply once** to stage it. The Python workspace
opens a new unsaved draft; it does not overwrite an existing editor or file.
The selected work folder is retained as that draft's working directory. Review
the editor's status/source before choosing Save or Run yourself.

Staging reports `draft_staged`, `saved: false`, `executed: false`, and a source
SHA-256. If the Python editor reports its tab or size limit, resolve that editor
diagnostic before proceeding; staging is not proof the editor accepted a tab.

## What the tools do

| Tool | Operation | Evidence / boundary |
| --- | --- | --- |
| `spike_work_files` | `list` | Paged relative names/types; at most 2000 scanned entries, 200 returned per page |
| `spike_work_files` | `read` | Complete admitted UTF-8 text plus source bytes and hashes |
| `spike_work_files` | `csv_summary` | Complete-file count/min/max/arithmetic mean for an exact named numeric column and explicit supplied units |
| `spike_python_draft` | Reviewed staging | New unsaved Python draft and source hash; no script execution or file save |

File operations accept `relativeName`, not an absolute filesystem path. Use names
returned by listing. `csv_summary` requires `column` and `units`; units are recorded
as supplied metadata rather than inferred or physically validated. CSV row widths
and headers must be consistent, header names unique, and every selected value
numeric and finite. Missing/invalid cells fail explicitly; they are not omitted.
The mean uses a compensated binary64 sum divided by the complete sample count;
overflow is rejected. It is not time-weighted, a spectral analysis, or a new
physics solver. Use a reviewed script for other calculations.

Readable types are `.txt`, `.md`, `.csv`, `.json`, `.log`, `.py`, `.spice`, `.cir`
and `.net`, at most 256 KiB each. Binary/NUL content, unsupported types, hidden
paths and recognized secret/configuration names are rejected. Symlinks, Windows
junctions, traversal, drive-relative paths and alternate data streams are blocked.
Raw-file and canonical decoded-text SHA-256 values are retained separately;
standard UTF-8 BOM files are supported. Opened file handles are checked against the selected root before reading; reads
are size-bounded and checked again afterward. The current handle verifier supports
Windows and Linux with `/proc/self/fd`; unsupported platforms fail closed for
file reads. These checks do not sandbox Python code you later choose to Run.

For native boards/projects/STEP, use the existing Open/Import controls. File
inspection does not import a design into SPIKE. For PDF, images and larger inputs,
use supported attachment/import workflows or explicit preprocessing; this harness
does not add arbitrary document parsers or folder-wide indexing.

## Errors and continuation

Recoverable known-tool schema errors are returned as tool evidence so the model
can correct arguments and continue. An identical failed request is blocked for
the rest of that user turn, preventing repeated unchanged dispatch. Unsafe
argument keys and unsupported commands remain blocked. Existing eight-round and
sixteen-call turn limits remain in place.

If no folder is selected, choose one in settings. If units or required engineering
inputs are unknown, provide them explicitly. A model request cannot select a root,
run a shell, change extension trust or execute its generated code. Changing the
folder invalidates pending file evidence and project-bound proposals. Closing or
switching a project does not preserve this transient folder configuration.

For simulation tasks, ask the Assistant to inspect capabilities, prepare a case,
request review, preflight, run only an admitted case and read actual evidence.
The harness does not change solver validity or repair missing numerical models.

## Developer checks

```powershell
cd app
npm.cmd run test:assistant
npm.cmd run test:python-workspace
cd ..
.\.venv\Scripts\python.exe -m unittest tests.python.test_assistant_harness tests.python.test_assistant_harness_service -v
```

An optional real-provider fixture check uses the actual conversation loop,
harness and Python service with a synthetic three-row CSV. Its picker/editor
callbacks are fixtures; it is not native desktop acceptance. It accepts review
only for an in-memory draft, never executes generated code, and saves a JSON
evidence record under `build/assistant-harness-live/`:

```powershell
cd app
node scripts/verify-assistant-harness-live.mjs lmstudio EXACT_LOADED_MODEL_ID
```

The harness tests cover folder authority, path/handle confinement, bounded I/O,
CSV known answers and malformed inputs, source provenance, project/folder drift,
script review/rejection, inert staging, retained working directories and schema
correction. A skipped OS symlink test is not evidence of executed symlink coverage.
See the [executed evidence and limitations](validation/ASSISTANT_TASK_HARNESS_20261023.md),
including the real local-model fixture and the separate native-acceptance status.

Native folder selection runs asynchronously so SPIKE remains responsive while
its picker is open. The detached Assistant allows up to 30 minutes for that
human interaction; other bridge requests retain their existing 150-second
limit. If a picker is already open behind another window, bring the SPIKE
folder dialog forward and finish or cancel it before retrying.
