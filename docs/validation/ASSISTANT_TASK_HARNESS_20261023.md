<!-- SPDX-License-Identifier: Apache-2.0 -->
# Assistant task harness evidence — 23 October 2026

## Scope

The source implementation adds work-folder file inspection, deterministic CSV
column summaries and reviewed unsaved Python drafts to the integrated Assistant.
It adds no Python execution, filesystem write, new solver or native design-import
authority to chat. The main workspace retains the selected root and revision;
the model only supplies relative names and typed operation arguments.

## Executed checks

- Assistant chat/media/assembly/window/task-harness regression suites passed.
- Python workspace suites passed, including an unsaved harness draft opening
  without execution and using its retained work folder only on a later Run.
- The combined Python harness/service/provider suite ran 30 tests with one OS
  symlink-privilege skip; the remaining 29 passed. Tests include opened-handle
  confinement, bounded scan/read, traversal/drive/stream rejection, source hashes,
  UTF-8 BOM, malformed CSV, nonfinite/overflow rejection and safe error routing.
- Architecture, shared button/control standard, documentation links and focused
  whitespace checks passed.

## Real local-provider fixture

Command, from `app` with the installed service already running:

```powershell
node scripts/verify-assistant-harness-live.mjs lmstudio spike-gemma-4-e2b
```

This exercises the real local provider, current tool catalog, conversation loop,
main-workspace harness adapter and Python service. Native folder selection and
editor callbacks are replaced with fixture callbacks. Review accepts only the
fixture's Python-draft tool; no generated source is executed or saved as a script.

Four bounded user steps passed: list folder, read `measurements.csv`, calculate
the `value_V` summary with supplied units `V`, and stage one Python draft. The
complete file contained three rows with 3.2, 3.3 and 3.4 V. Returned count was 3,
minimum 3.2 V, maximum 3.4 V, and binary64 mean 3.3000000000000003 V, within
1e-12 V of the known 3.3 V answer. Its 33 raw bytes had SHA-256
`501cdc9e3339d43ca6bb03b2bafad0b09653f750ec15355f18347e1dac04e556`.
The resulting draft retained the fixture folder and reported unexecuted/unsaved.
The runner retained JSON evidence under `build/assistant-harness-live/case-one9FJ/`.

An earlier combined request summarized the data and staged a draft but skipped
the separately requested list/read calls. Its acceptance assertion failed and
its evidence was retained separately. The successful bounded-step test does not
establish reliable autonomous planning of every multi-operation prompt.

## Limits

This is not native picker/editor visual acceptance, an installed-artifact test,
validation of generated script calculations, or a model-driven solver run.
The full repository Python suite was not run for this change. File-handle path
verification supports Windows and Linux `/proc/self/fd`; other platforms fail
closed for reads. A skipped real symlink test is not executed symlink evidence.

An earlier full TypeScript check encountered two errors in `CameraViewIcons.tsx`
outside the harness changes. Those were resolved in the shared workspace; the
final full TypeScript check passed. Native picker/editor acceptance remains
separate from the real-provider fixture described above.

## Rebuilt native preview

`npm run build` and `cargo build --release --features custom-protocol` passed.
The resulting source-runtime preview is `SPIKE-harness-preview.exe` at the
repository root (SHA-256
`FA4242D2ABF18E49EE0156CFC03F1BB26CD6317188E0CCBF4962DA93B7B50140`).
It uses the repository Python runtime and sources; this is not a frozen-worker
or installed-release acceptance result. The installed application was untouched.

Native UI inspection confirmed the preview executable identity, settings,
33-tool catalog, task shortcuts, and work-folder disclosure. Selecting LM Studio
discovered six models and selected `spike-gemma-4-e2b`; enabling project tools
updated the context disclosure. After clicking Choose work folder, the computer
use helper reported an active request and prevented further observation.
Consequently native folder selection, reviewed draft application, Python editor
handoff, and narrow-window layout acceptance remain incomplete. No generated
script was run or saved during this inspection.

## Completed native workflow — 23 October 2026

This section supersedes the incomplete native-acceptance status above.

Two failures found by native testing were fixed:

- The synchronous native import picker blocked the UI thread. It now uses
  `rfd::AsyncFileDialog` in an async Tauri command, preserving filters and exact
  approved-path registration. Folder requests have a dedicated 30-minute human
  interaction budget; other bridge requests retain 150 seconds.
- Windows native selection returns an extended path (`\\?\C:\...`). The
  opened-handle verifier stripped that prefix only from the actual handle path,
  so an in-folder file was falsely rejected. Resolved actual, base and expected
  paths now use one namespace spelling for comparisons. File opening, bounded
  reads, handle checks and confinement remain enforced. A Windows regression
  covers read/summary through an extended root and rejection of an outside
  handle.

The rebuilt source-runtime preview is `SPIKE-harness-verified.exe`, SHA-256
`BFA13C37A0DE210858EC7BAC0FFEE2CE1703EFC05D0A3EA635190C08EB7CEDAB`.
It uses the repository Python sources, including the path fix; it is not an
installed/frozen-worker release acceptance result. Existing windows and the
installed application were retained.

Executed in this exact executable, in a disposable untitled project:

1. Opened Assistant from universal search. Selected LM Studio, discovered six
   models, and used `spike-gemma-4-e2b` at loopback port 1234.
2. Enabled project tools and selected `build/assistant-harness-native` with the
   actual Windows folder dialog. Selection returned successfully without freezing.
3. Asked the model to list the folder. Its actual tool call returned
   `measurements.csv`.
4. Asked the model to read the file. After the path fix, the tool returned all
   33 bytes and the expected source hash
   `501cdc9e3339d43ca6bb03b2bafad0b09653f750ec15355f18347e1dac04e556`.
5. Asked for `csv_summary` on `value_V`, supplied units `V`. The actual tool
   completed; the UI showed count 3, min 3.2, max 3.4, mean
   3.3000000000000003, agreeing with 3.3 V within 1e-12 V.
6. Requested a Python CSV-summary draft. Reviewed its actual source and clicked
   Apply once. `CSV Voltage Summary.py` opened as Unsaved in the main Python
   workspace with the selected extended-path working directory. The status
   instructed review before Run. Output showed `No standard output yet`.
   Save and Run were not invoked. Generated script calculations were not validated.

Native screenshots and redacted accessibility observations are retained under
`build/assistant-harness-native/`: `native-summary.png`, `native-summary.txt`,
`native-editor.png`, and `native-editor.txt`.

Post-fix validation: frontend production build (including full TypeScript),
release Rust build, Assistant suite, Python workspace suite, parser regression,
architecture/button checks passed. Focused Python suite: 31 tests, 30 passed,
1 symlink privilege skip. Rust: 75 passed, 1 ignored. Initial sandbox runs failed
local sockets/private rendezvous access; reruns with those permissions passed.
The full repository Python suite and installed distribution were not tested.
