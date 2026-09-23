# Qt-free workbench: Stage A development increment

Status: partial implementation, not a release. The installed beta.6 is unchanged.

## Working changes

- `.MODEL` placement now exposes all existing native semiconductor terminals to
  drawing, hit testing and routing. MOSFET gate/bulk and BJT base connections edit
  only terminal tokens, preserving model names and parameter suffixes. Electrical
  connectivity remains independent of route geometry. Pin labels are shown on
  multi-terminal blocks. These are not yet production symbols for every family.
- A toolkit-independent command registry provides dispatch, availability reasons
  and search. Menus, keyboard bindings and the main workflow ribbon use it.
  `Ctrl+Shift+K` opens Find command. Some older contextual controls still require
  migration to this registry; this is not a completed replacement shell.
- View offers Power electronics, Analog/RF and Controls/dashboard presets.
  File → Export workspace / Import workspace saves or loads `.spkworkspace` files.
  The format stores page, split-view and browser/properties visibility. It does
  not yet preserve floating-window positions, pane dimensions or every layout.
- View → Interactive result report opens the offline report panel. Finish or stop
  acquisition, then select Refresh acquired snapshot. Plotted expressions are
  taken from visible traces, or up to eight available signals if none are selected.
  Export offline HTML writes a self-contained interactive Plotly report. No CDN,
  account or local server is needed. At most 32 traces and 4,000 display points per
  trace are transferred; the table uses original-sample min/max/latest values.
  This is a read-only snapshot, not a live web dashboard or control bridge.
- Native dashboard controls remain attached to the native session. The report
  panel cannot invoke Python/C++, access arbitrary files or issue solver commands.
  Content Security Policy denies report network requests, and navigation is
  restricted to its generated local file. WebView2 itself is an external runtime;
  OS-level network-isolation certification is not claimed.
- Scientific waveform artists now retain a reusable multiresolution min/max
  index. Panning/zooming can query the index rather than rescanning the complete
  visible sample array. Numerical measurements still use original samples.
  Full figure rebuilds and the existing SignalMath input limit remain to be fixed.
- Packaging collects the offline Plotly asset and licence files, scans collected
  modules and payload names for Qt dependencies, emits an initial CycloneDX
  inventory and requires reviewed release evidence for release distribution.
  The inventory is not yet a complete transitive/native licensing review.

## Architecture introduced

`command_registry.py`: `Command`, `Context`, `CommandRegistry`, command search and
disabled reasons. Handlers stay in the desktop integration layer; the registry
has no wx imports and is unit-testable.

`pin_geometry.py`: shared ordered pins, anchors, lead endpoints and stable
component/ordinal-derived pin identities. Existing v1 semiconductor order is
preserved: collector/drain, emitter/source, base/gate, optional bulk. Netlist
serialization explicitly restores the SPICE order. No existing file is silently
converted to a different authoritative project representation.

`workbench_layout.py`: `spikes/workspace/v1`; validation precedes UI changes.

`offline_report.py`: `spikes/offline-report/v1`; expression evaluation and exact
statistics are separate from bounded display arrays. HTML content is escaped.
The wx panel prepares snapshots in the existing background-job coordinator.
Missing WebView support reports the limitation; HTML export remains available.

`waveform_index.py`: `WaveformIndex` retains original-array references and cached
sample indices. Callers must not mutate those source arrays after construction.
This index is a display accelerator, not a solver or an approximate measurement
engine.

`release_policy.py`: mandatory reviewed gate records with artifact SHA-256 checks,
zero failed/skipped checks and candidate source-manifest binding. It verifies
evidence structure and integrity, not physical truth or reviewer identity.

## Verification and reproducibility

Run with the project's Python 3.11 environment and `.tmp/studio-deps`:

```text
python scripts/verify_spikes_studio_tests.py --library <native DLL> --wx --output <report.json>
python scripts/verify_workbench_stage_a.py
python scripts/benchmark_spikes_waveform_index.py --output <benchmark.json>
python scripts/check_spikes_release.py --evidence <reviewed-evidence.json>
```

The real wx integration test pastes a model, checks four hit-testable pins, wires
the gate, saves/reopens, undoes, changes workspace presets, runs the C++ RC
transient, waits for Plotly's render completion and exports the acquired report.
It isolates preferences and disables autosave. On this Windows host WebView2
child processes require an ordinary desktop process rather than the restricted
agent sandbox. No mocked waveform or browser is used in this integration test.

The waveform microbenchmark uses explicitly synthetic performance data. On this
16-logical-CPU host, eight ten-million-sample traces used 720 MB of original NumPy
arrays plus approximately 10 MB of indices. A 100-query run measured about 2.74 ms
p95 for querying all eight indices. Cold index builds took about 17–20 ms per
trace. These numbers exclude GUI rendering, process RSS and solver execution;
they do not meet or substitute for the specified reference-system release gate.

Development evidence lives under `artifacts/workbench-stage-a`. The integration
test's native-window bitmap can capture ordinary wx controls but cannot reliably
capture the GPU-composited browser surface. The separate computer-use screenshot
approval timed out. No blank browser image is published as documentation proof.

## Release gate operation

Installer/AppImage release creation requires `--release-evidence`. An explicit
`--candidate` build is allowed for local packaging tests before qualification;
its manifest says unqualified and not releasable. This permits testing candidate
installers without circularly requiring installed-package evidence first.
Candidate builds must not replace the user's installed release.

Freeze a development candidate first to obtain `source-manifest.json`; review
evidence against that digest. Each mandatory gate requires a reviewer, nonzero
check count, zero failures/skips and existing hash-matched artifacts within the
evidence directory. Any changed source manifest or evidence artifact blocks
release. Missing gate evidence is not inferred from passing unit tests.

## Still required from the approved plan

Stage A remains incomplete: authoritative hierarchical semantic graph and v1
migration, full `.SUBCKT`/dependency paste and symbol placement, persistent unified
executable libraries, general dynamic-device API/Device Studio, explicit
native/ngspice session routing, complete property/fidelity integration, complete
replacement docking shell, full context-command migration and live Plotly
dashboard bindings. Optional VTK integration has not been added.

Stage B remains incomplete: complete grammar/analysis coverage, production
semiconductor physics and manufacturer qualification, frozen broad manufacturer
catalog, full coupled-physics/HDL workflows, solver-scale performance evidence,
Linux package validation, complete dependency/model redistribution review and
final EULA, documentation screenshots and installed-release qualification.

Generic IGBT/SCR models have not become manufacturer-qualified models in this
increment. No hard-real-time certification, full SPICE parity or competitive
superiority is claimed.
