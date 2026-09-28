<!-- SPDX-License-Identifier: Apache-2.0 -->
# Python workspace

Open **Settings → Python workspace**, use **Tools → Python workspace**, or find
it from Search. The workspace has a script editor, `.py` open/save, run and
stop controls, a time limit, and separate standard output and error panes.
`Ctrl+Enter` runs the editor; `Tab` inserts four spaces. Scripts run in a
separate local Python child process and require the desktop app. The browser
preview can edit and download a script but cannot execute it.

The injected `spike` object has:

| Member | Use |
| --- | --- |
| `spike.design` | Current normalized `spike/v1` board data, or `None`. Coordinates are in millimetres. |
| `spike.results` | Current `spike/results-context/v1`, or `None`. `complete` tells whether `result` is present or a bounded preview was supplied. |
| `spike.call(method, params={})` | Call a registered local worker method through its ordinary validation and return contract. |
| `spike.extensions()` | Inspect the extension catalog. |
| `spike.invoke_extension(id, contribution_id, parameters={})` | Run an installed, session-trusted adapter with the current board and any declared result context. |
| `spike.publish_scalar_field(name, samples, ...)` | Send one explicit board field into the result viewer. Requires a loaded board. |
| `spike.publish_result(result)` | Send a complete `spike/v1` AnalysisResult. Requires matching board provenance. |

For example, with a board loaded:

```python
print(spike.design["name"])
print(spike.call("health")["worker_version"])
print(len(spike.design["vias"]))
```

For an external adapter, review and trust it in **Extension manager** first.
That session trust is carried into the script child. For example:

```python
reply = spike.invoke_extension("org.example.field-data-adapter", "import-voltage-field", {
    "samples": [{"x_mm": 12.0, "y_mm": 8.0, "value": 11.92}]
})
print(reply["data"]["analysis_result"]["summary"])
```

An analysis contribution invoked this way is also published to the viewer
after the script finishes successfully. Its upstream extension ID and solver
remain in provenance; the parent worker records the Python workspace as the
immediate result source.

For a field computed by your script or external engine:

```python
samples = [{"x_mm": 12.0, "y_mm": 8.0, "layer": "F.Cu", "value": 11.92}]
spike.publish_scalar_field(
    "voltage_v", samples,
    mode="dc", solver="my-adapter/1.0", model_status="unvalidated",
    summary={"quantity": "voltage", "units": "V"},
)
```

The sample above illustrates the interface; it is not a computed board value.
Publishing a field does not imply that another quantity, such as current
density or voltage drop, was solved. The host checks the same finite-value,
sample-limit, and design-binding rules used by process extensions. See the
[external analysis API](EXTENSION_ANALYSIS_API.md) for result fields and units.

Scripts are user-authored local Python with the user's filesystem and package
access. The child process is a stability and cancellation boundary, not a
security sandbox. The default time limit is 120 seconds and the editor can set
1–600 seconds. Standard output and standard error are capped at 1 MB each;
script code is capped at 512 KB, context at 64 MB, and the result at 16 MB.
Use **Stop** to request desktop worker cancellation before closing the editor.
Scripts that need unattended operation can also use
[`SpikeAutomation`](../python/spike_core/automation.py) outside the app.
