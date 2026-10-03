<!-- SPDX-License-Identifier: Apache-2.0 -->
# Python workspace

The desktop Python workspace is a local script editor for inspecting the loaded
design, reviewing returned analysis data, preparing explicit solver inputs, and
calling registered worker or trusted extension operations. It is intended for
reproducible engineering automation. It does not add solver capability or
change the qualification of a result.

## Files, tabs, and shortcuts

Open **Tools > Python workspace**. The activity bar switches between Files,
Templates, Backups, and Help; click the selected activity again to hide its sidebar.
Use **Open scripts folder** in Files to choose the file tree root. Tabs keep
their own code, breakpoints, output, and unsaved state.

The workspace file tree is confined to the configured workspace root. A path
that resolves outside that root is rejected. New and Open create editor tabs;
Close checks for unsaved changes. Save writes the current file and Save as
chooses a new name. A dirty marker identifies content that has not been saved.
Closing a dirty tab offers Save, Discard edits, or Cancel. Opening a file that
already has a tab selects it and preserves its current edits.

| Shortcut | Action |
| --- | --- |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+O` | Open |
| `Ctrl+N` | New file |
| `Ctrl+W` | Close tab |
| `Ctrl+Enter` | Run |
| `F5` | Start or continue debugging |
| `F9` | Toggle a breakpoint at the cursor |
| `F10` | Step over |
| `F11` | Step into |
| `Shift+F11` | Step out |

The backend file operation is `python_workspace_files`. Its root-confined list,
read, and write commands validate normalized paths, file types, optimistic
write hashes, and payload limits. The desktop remains responsible for
dirty-buffer prompts before replacing editor content.

The fixed **+** button adds a tab beside the horizontally scrolling tab strip.
Focused tabs support Left/Right, Home, and End. Each tab and the editor heading
show **Draft**, **Unsaved**, **Saving**, **Saved**, or **Save failed**. Edits typed
during an asynchronous save remain unsaved. Cancelling Save as retains the draft;
an external-file conflict retains the edits and offers Save as. Browser downloads
leave the draft unsaved because the application cannot verify a retained file.

Open tabs, draft contents, breakpoints, the active tab, and recent workspace
folders are restored from session storage. Automatic backups also retain up to
five recent workspace snapshots within a 2 MB local-storage record. The footer
shows backup progress or failure; **Backups > Restore copy** creates a separate
unsaved tab without a disk path or overwrite digest. On a restart with missing or
corrupt session storage, the newest valid durable snapshot opens as recovered
drafts. Closing a tab checkpoints its current state before removing it. Storage
quota or access failures remain visible. Save scripts to files for durable work.

**Files** includes open editors and a recent workspace-folder selector. **Git
worktrees > Find worktrees** inventories existing checkouts using bounded,
read-only Git commands. Switching the tree root preserves open documents and
their individual save roots; it does not create, move, or delete a checkout.
Missing Git and non-repository folders show a diagnostic. Folder contents load
on expansion; the filter searches loaded entries. Up/Down and Home/End navigate
visible file rows.

The compact header and wrapping toolbar share the application theme palette.
Tabs, folders, scripts, output, and inspectors have independent overflow. At
narrow laptop widths the debugger inspector stacks below the editor; its toggle,
the activity buttons, and the collapsible Output heading reclaim editor space.

## Run and debug

Run executes the active source in a separate local Python child process.
`print()` output and standard error appear in separate panes. The selected
timeout bounds a run; Stop requests worker cancellation. Code is limited to
512 KB, context to 64 MB, standard output and standard error to 1 MB each, and
the returned result to 16 MB.

Debug uses `start_python_debug` and its status/command operations. The editor
can set line breakpoints. While paused, the workspace shows the bounded call
stack and locals for the selected frame. Continue, step over, step into, step
out, pause, and stop apply to the supervised child session. Values can be
truncated by the debug protocol. Locals are bounded string representations; the
debugger does not expand or evaluate object properties. A debug session ending
unexpectedly is reported as failed rather than as a completed analysis.

Line breakpoints apply to the script that started the session. Step into can
enter local Python modules under that script's working directory; stack frame
links can open their source. Remote attach, separate thread debugging, and
expression evaluation are not available. You can edit another tab during a
run; the executing script stays locked until it stops.

A saved script runs with its parent folder as the working directory. An unsaved
tab runs from the selected workspace folder. Resolve important input and output
paths explicitly. The child has the user's ordinary local file and
installed-package access. The process boundary supports cancellation and fault
containment; it is not a security sandbox.

## Injected API

| Member | Use |
| --- | --- |
| `spike.design` | Current normalized `spike/v1` board data, or `None`. Coordinates use the design's declared units, normally millimetres. |
| `spike.results` | Current `spike/results-context/v1`, or `None`. Check `complete` before reading `result`; an incomplete context may contain only a bounded preview. |
| `spike.call(method, params={})` | Call a registered local worker method through its ordinary validation and result contract. Nested Python workspace execution is rejected. |
| `spike.extensions()` | Inspect installed extensions, contributions, permissions, and current-session trust. |
| `spike.invoke_extension(id, contribution_id, parameters={})` | Invoke an installed, session-trusted contribution with only its declared design/result permissions. |
| `spike.publish_scalar_field(name, samples, ...)` | Offer one explicit finite board field to the result viewer. Requires the matching loaded design. |
| `spike.publish_result(result)` | Offer a complete `spike/v1` AnalysisResult for host admission. Requires matching design provenance. |

Minimal context inspection:

```python
if spike.design is None:
    print("No design loaded")
else:
    print(spike.design.get("design_id"), spike.design.get("name"))

health = spike.call("health")
print(health.get("contract"), health.get("worker_version"))
```

`spike.call` exposes the registered worker surface; it does not bypass schema,
runtime, dependency, design-revision, or result-admission checks. Query
capabilities and catalogs first. Use the documented method schema rather than
guessing a request payload.

Extensions must be inspected and trusted in the Extension manager for the
current session before invocation. An extension result keeps its upstream
extension and solver provenance. Publishing a field or complete result does
not validate the external method or infer quantities that were not supplied.

## Template catalog

The template picker contains 50 scripts in 18 categories
covering design inspection, PI DC and AC setup, circuits and parasitics, SI
channels/crosstalk/protocol review, steady and transient thermal setup, board
and assembly thermal review, EM/EMI, extensions, multiboard studies, result
review, export, and bounded parameter sweeps.

Eleven execution templates dispatch actual registered analysis methods. Set
`REQUEST_FILE` to a JSON request with the inputs required by the chosen method;
an unset request path does not launch a solve. These templates reject a request
that names a different loaded design. Review the returned status, issues, and
model qualification before publishing or using a result.

Templates have explicit requirements. Entries labeled **setup**, **draft**, or
**plan** prepare and validate configuration but do not launch a solver. Their
required physical values are deliberately `None`, empty, or `TODO_*`; replace
them from engineering requirements and the loaded design. This prevents an
illustrative voltage, current, material, boundary condition, timing model, or
frequency range from becoming an accidental analysis input.

Export templates require an explicit destination. They write only the selected
returned data and do not fill, interpolate, or fabricate missing samples.
Parameter sweep templates cap their case count and require comparable design,
solver, unit, and model-status evidence before results are compared.

## Capability and accuracy limits

The workspace can orchestrate the currently registered PI, SI/NEXT/FEXT,
thermal, EMI-screening, trusted extension, and reduced multiboard worker paths.
Availability still depends on the selected method, complete required inputs,
installed runtime, design revision, and preflight result.

- A catalog entry or capability probe is not proof that a solver runtime is
  installed, that a case converged, or that its physical model is validated.
- DC, AC, circuit, thermal, and network scripts must preserve returned
  `model_status`, issues, assumptions, units, and provenance.
- Eye diagrams require a supported channel plus explicit timing, stimulus, and
  endpoint models. An eye plot alone does not establish protocol compliance.
- Board and layered thermal paths are approximate. Boundary conditions, power,
  stackup/material inputs, copper coverage, and interfaces are required.
- Internal tetra generation and focused PCB volume preparation are
  experimental. Geometry preparation does not establish EM, SI, PI, or thermal
  convergence.
- E/H samples, Poynting vectors, contours, radiation views, and imported
  extension data retain their source qualification. Visualization adds no new
  solved samples.
- EMI screening is not compliance certification. The workspace makes no
  general full-wave EM qualification claim.
- Multiboard identity is occurrence-specific. Equal net names on separate
  boards do not create connectivity. Independent per-board dispatch does not
  establish coupled assembly physics; use explicit connector pin maps and only
  supported reduced coupling paths.

For executable capability status and detailed method limits, use
[`SOLVER_STATUS.md`](SOLVER_STATUS.md). External result shape and provenance are
documented in [`EXTENSION_ANALYSIS_API.md`](EXTENSION_ANALYSIS_API.md).

## Recovery

If execution fails, read standard error first and keep the source tab open.
Resolve missing inputs, unavailable packages, rejected paths, stale design
bindings, or worker preflight diagnostics before retrying. After a timeout or
Stop, wait for the child session to finish before starting another run. Save
scripts and configuration beside the engineering inputs needed to reproduce
them; do not treat console text as the only record of an analysis.
