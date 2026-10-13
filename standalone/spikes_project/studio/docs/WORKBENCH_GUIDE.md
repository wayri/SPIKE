# SPIKES Studio workbench guide

The source increment dated 2026-10-12 adds a cleaner plot/dashboard workflow,
exact-MPN manufacturer seed, offline NMOS table fitting, direct virtual source
controls and explicit hidden-wire RLC. See the complete
[workflow and limits](../../../../docs/SPIKES_SOURCED_PARTS_WORKBENCH.md).
It does not update the installed beta or qualify all vendor device families.

## Clean workspaces and appearance

### Analysis forms and canvas text (T)

**Simulation → Manager → Analysis command / parameters** opens the saved analysis
directive. **S** also opens the directive editor, or double-click a directive on
the canvas. The **Directive type** dropdown selects the relevant labeled fields:
transient timing, AC sweep, DC source ranges, operating point, noise, transfer,
pole/zero, sensitivity, distortion, Fourier, temperature, initial conditions,
parameters, sweeps, options and measurement. **Raw SPICE** remains available;
commands that cannot be safely split stay raw and are not silently rewritten.
An editor form does not establish execution support: enabled cards still undergo
the selected parser/backend validation. Pole-zero port ordering follows the
[ngspice manual](https://nmg.gitlab.io/ngspice-manual/analysesandoutputcontrol_batchmode/analyses/pz_pole-zeroanalysis.html).

Press **T** on the schematic to enter text. Text starting with **.** is a SPICE
directive or a block of top-level directives; other text is an inert note.
Validate, then click to place it. Escape cancels placement. Continuations start
with **+**. Uncheck **Enable SPICE commands** or start with **\* .command** to place
commented-out directives. The whole block is one undoable transaction, with no
partial changes if validation fails. Structural `.subckt`, `.control` and `.lib`
blocks still require Circuit text/model-import workflows, not this text tool.

Right-click a directive and choose **Comment out directive** or **Enable directive**.
Disabled cards have a muted **[COMMENTED OUT]** heading and **\*** prefixes; their
source lines are actual comments. Comment state, grouping and placement persist
with the project. Run-profile overrides remain separate from saved directives.

### Symbol-and-text browsing

The schematic palette, catalog family tree, generic/manufacturer result rows,
component-model dropdown, symbol library, circuit-component list and battery
market list pair small symbols with text. Search, filtering, sorting, keyboard
selection and insertion retain their existing semantics. Symbols follow light
and dark themes; a bounded family-level image set is reused rather than allocating
an image per catalog record. Unknown/custom families use a generic terminal block
beside their name. These navigation glyphs are common-convention family markers,
not evidence of a validated model or an exact manufacturer pinout.

### Click-to-edit waveforms and draggable cursors

**Grid** and **Legends** in the plot toolbar show/hide these elements. Right-click
a pane to add a text box or labeled arrow. Drag the text to move it; dragging an
arrow tip moves its endpoint. Right-click the annotation to edit its text or
delete it. Annotations persist in project metadata in pane/data coordinates and
are included in image exports. Escape cancels a drag; accepted moves are one
undoable project transaction.

**Sweep values…** shows every retained run at each cursor, optionally for every
plotted expression, with parameter coordinates and original-sample values.
Out-of-range or missing signals are labeled unavailable, never extrapolated.
The table updates during cursor drag and is bounded to 16,384 readings.
Native parameter `.step` batch results retain individual runs for selection and
overlay; continuous simulation still does not execute `.step`.

Select **Tools → Monte Carlo**. Enter explicit component-value
tolerances, distribution, case count, seed and probe; **Run Monte Carlo** executes
the existing Python linear R/L/C/V/I reference backend, not the native nonlinear
solver. Maximums are 256 cases, 16 varied values and 250,000 aggregate solve points.
The plot shows actual per-case probe values (final sample for time series), not
waveform envelopes. Applied circuit text and validity checks are mandatory.
For `.ic`, `.temp`, and B/E/F/G/H coverage and exclusions see
[initial state and source support](../../../../docs/SPIKES_INITIAL_DIRECTIVES.md).

Click a trace name in the plot heading/legend to open the waveform editor, or
double-click it in **Plotted traces**. Select a recorded voltage/current/power
channel or enter an expression. Examples: `v(in)-v(out)`, `v(out)*i(R1)`,
`derivative(v(out))`, `integral(v(out)*i(R1))`, `sin(v(out)/V)`.
Use **Validate** to check units and finite values, then **Apply waveform**.
Changing units reallocates a compatible custom pane; cursor bindings for that
trace follow the new expression on their original runs. Invalid expressions,
duplicate traces and missing run channels leave the current trace unchanged.
Right-click the heading for edit or visibility actions; checkbox visibility
remains available. Right-click the plot → **Add signal / mathematical expression**
opens the same picker for a new trace. This is recorded-signal mathematics, not
arbitrary executable Python or a simulator equation.

Click a waveform to place a cursor. Drag its vertical line or A/B badge to move
it; the mouse is captured until release. Time is bounded by that cursor's original
run, and docked readings refresh during motion using original samples. No
floating window is forced open by placement. **Cursors…** opens the detailed
run/expression bindings and relative math (`a`, `b`, `dt`, e.g. `(b-a)/dt`). Escape
ends an active drag. Actual heading/edit/drag verification and captured solver
results are in `artifacts/studio-waveform-edit-20261012/`.

The compact shell has **Back**, **Forward** and **Home** navigation beside the
file/run controls, with a current-section label. **Alt+Left / Alt+Right / Alt+Home**
perform the same actions. Home returns to the live schematic, including from a
split layout. Navigation keeps a bounded session history (128 visits), separate
from circuit undo; opening a new section after Back discards the forward branch.
It does not apply, discard or undo text drafts and circuit changes.

**Schematic**, **Waveforms**, **Netlist** and **Dashboard** are the main-window tabs.
Specialist tools open in dedicated modeless windows from grouped menus:

- **Libraries**: parts, component catalog, manufacturer parts, symbols and controllers.
- **Analysis**: directives, frequency/pole-zero, power tree, analytics and reports.
- **Tools**: C/C++/Verilog IDE, battery laboratory and Monte Carlo.
- **Simulation**: simulation manager; **Help**: the help workspace.

These windows contain the original stateful panel, not a duplicate circuit or
simulation. Closing hides a tool and retains drafts, filters and selections;
selecting its menu command reopens it. Multiple tools can remain open while
switching the main view. **Return to workspace** puts the same panel back in
the central area. Existing workspace profiles can still select specialist pages.
Returned panels receive their own main-window tab. Right-click a specialist tab
to open it as a floating window again; its tab is removed without losing state.
Back/Forward follow workspace changes and opened tool windows; Forward can reopen
a previously hidden tool. Navigation history and temporary tabs are session-local.
Catalog openers float by default, including the direct component-browser opener;
opening a previously side-pinned catalog returns it to its floating window.
Side-pinning remains an explicit option. **Add component** opens a separate,
resizable selection/value dialog over the main workbench, including when invoked
through placement shortcuts; it does not replace the schematic.

Schematic tools occupy a short labeled row: **Select, Wire, Move, Rotate,
Properties, Probe V, Parts, Fit**. Icons supplement the labels. Tooltips explain
click sequences, shortcuts and disabled reasons. Rotate/Properties/Move require
a selected component; the active Select/Wire/Probe tool is highlighted.
Wire and Probe keep the actual editor active in split mode. Fit on this row fits
the schematic, not waveform axes. Drag, mirror and lasso are in **Edit**;
differential/current/power probes are in **Probes**; split layouts and mini plots
are in **View**. Interaction, limit markers and libraries remain menu commands;
the duplicate navigator tools and permanent canvas instruction banners are
removed. **Navigator** hides/restores the schematic sidebar. Empty properties
and probe lists take no space; selecting a part reveals its summary and property
actions. View → Theme owns appearance selection. A stale running source session
retains its imported UI code until restarted; an old installed build is separate.

To inspect the light appearance without changing saved preferences:
`python scripts/launch_spikes_studio.py --theme Light`.
Actual schematic and acquired waveform screenshots and geometry checks are in
`artifacts/studio-compact-shell-20261012/`.

For terminal-bound power flags, reference/signal/chassis/earth grounds and the
prescribed-current battery laboratory, see
[power and battery workflows](../../../../docs/SPIKES_POWER_BATTERY_WORKFLOW.md).
The battery laboratory is not yet coupled to circuit simulation; market-cell
metadata is not a qualified fitted device model.

Windows startup sets the `SPIKES.Studio` shell identity before creating wx
windows. Window icons use the bundled multi-size ICO rather than a single PNG;
the Windows installer shortcuts use the same identity and executable icon.
Restart an updated build to apply it. Previously pinned shortcuts to Python or
an older build may need to be unpinned and the updated application re-pinned.
Source changes do not update an already installed executable.

Light is the default for new appearance preferences. Dark and the legacy
Midnight selection now share a neutral graphite palette; High contrast remains
available. Existing theme choices are retained. Top-level commands and workspace
navigation use quiet controls with hover, keyboard focus, selection and disabled
states. Tab moves focus; Space or Enter activates a focused command.

Waveforms has one navigation strip; **More…** reveals archive, sweep, analysis
and continuous-control tools. **Browser** hides or restores signal and cursor
readings. Charts use restrained grids and frameless legends. Original retained
samples still supply all measurements.

Dashboard **Inspector** hides or restores properties. Global run commands replace
duplicate dashboard run buttons. Hover over the session summary to inspect full
solver/source provenance and hardware-disconnected status. Captures in
`artifacts/studio-polish-final-20261012/` are real wx windows driven by the owned
C++ RC and continuous simulations, not rendered mockups.

This guide describes the runnable wxPython/wxWidgets workbench. It uses the
owned C++ solver through the C ABI and Matplotlib for plots. The earlier HTML
preview is a design reference; its canned values are not used in this application.
The planned C++/VTK editor remains a separate implementation milestone.
The frequency workspace is an explicitly labeled exception: it currently uses
the existing Python/SciPy linear AC and descriptor pole-zero analysis backend.

## Connect, rotate and enter passive values

**Add component** opens on **Value & parameters**, with engineering-value inputs
and instance count. **Pins & connections** is a separate optional tab; it edits
net assignments, not model pin order. Every default pin/instance starts isolated,
and no pin is automatically grounded. Defaults are unique across separate
insertions. Wire after placing the component, or intentionally assign shared net
names in the connections tab. Invalid parameters keep the dialog open.
Basic R/C/L, termination and cable presets place directly wireable primitives;
other compound recipes retain their existing subcircuit placement limitations.
Manufacturer insertion also separates nominal/model details from net mapping;
sourced nominal values are not silently relabeled as arbitrary manufacturer parts.

## Search and select manufacturer parts

**Manufacturer library** presents sortable Manufacturer, MPN, Category, Nominal
and Model readiness columns. Click a heading to change sorting; the arrow shows
direction. Search and manufacturer/category/readiness filters combine. Selection
is preserved while its record remains in the results. Drag the divider or resize
columns to give the list or details more space. Overview, Pins and Evidence tabs
separate ratings, pin labels and source/qualification information.

In **Add component → Value & parameters**, **Component / library model** offers
matching exact-MPN records alongside **Custom / generic**. Filter by MPN or maker.
Available nominal R/C approximations show their sourced values read-only; choose
Custom / generic to edit arbitrary values (your draft is retained). Records
without a runnable model remain selectable for discovery but disable placement.
Placed manufacturer R/C primitives retain identity, provenance and ratings through
save/reopen and can be wired normally. Ratings remain metadata, not enforced
solver limits. The current catalog is a 23-record seed, not a complete or qualified
manufacturer-model library.

Select a component, then **Rotate** on the toolbar, **Edit → Rotate**, or **Space**
to turn it 90 degrees. The angle is saved with the project and undoable. Text stays
upright. **M** arms Move: the next click places the selection and calculates fresh
routes for attached wires. **G** arms Drag: the next click places the selection
while retaining nearby attached-wire bends. Pointer dragging uses Drag behavior.
All placement previews snap to the 10-unit schematic grid; **Escape** cancels an
armed move without changing the document.

**Wire** on the toolbar or **W** enters continuous terminal-to-terminal wiring.
Click a terminal marker, optional grid-snapped corners, then the destination
terminal. The dashed orthogonal preview follows the pointer. **/** flips its
horizontal-first or vertical-first bend posture, and **Backspace** retracts the
last explicit corner. The first **Escape** cancels the wire in progress while
leaving Wire active; a second **Escape** exits the tool. After a wire is committed,
Wire remains active for the next connection. This is an electrical net merge, not
a decorative line: the destination net is renamed to the first net, except that
ground wins. The preview latches to a terminal inside its hit radius and shows the
same route that will be committed. For terminal-to-terminal connections, if the
selected no-corner posture would enter an endpoint symbol body, both preview and
commit use the body-avoiding autoroute.
Undo restores both the drawing and source in one step.

To create a deliberate branch, start **Wire** at the new branch terminal and
finish on the interior of an existing wire. Studio first checks whether its
authoritative SPICE node can be merged safely, then splits the drawn route at a
saved junction dot and adds the branch as one transaction. The junction records
both a stable source-terminal identity and its current source-node name; rotate
and mirror operations therefore do not infer connectivity from screen position.
If source rewriting is unsupported, no junction, route split, or partial source
change is retained. Save/open and Undo preserve the complete junction topology.

The wire editor supports every terminal exposed by a top-level component, stored
orthogonal waypoints, shared-terminal dots, and explicit three-leg branches on
existing wire interiors. Arbitrary free-standing junctions, bus entry, joining
two existing wires at a crossing, and multi-pin subcircuit editing are not yet
available. Hierarchical/model-library source and dependent expressions that
cannot be rewritten safely are rejected instead of silently changing behavior.
Wire crossings remain distinct unless a branch was explicitly finished on that
wire. Existing equal node names remain electrically connected even when no drawn
wire joins them.

Press **E** for properties. Enter the value manually using SPICE engineering
suffixes. For R/C/L, choose E6, E12 or E24 and use **Nearest standard value…** to
review the lower, nearest and upper values. Confirming changes the draft only;
**Apply** commits it. Preferred values are suggestions, not manufacturer stock or
rating guarantees. Limits and descriptive properties do not add missing physical
effects to an ideal device model.

## Appearance and stacked waveform panes

Use the toolbar theme selector or **View → Theme** for **Dark**, **Light**,
**Midnight**, or **High contrast**. Dark uses a genuinely black schematic/plot
background. Palettes cover workbench controls, property/setup editors, source
editors, grids, canvas annotations, figures, text and contrast-aware vector icons.
Text/muted/accent palette combinations are tested at a minimum 4.5:1 contrast
against the main surfaces. Appearance is saved separately from circuit data in
`%LOCALAPPDATA%/SPIKES Studio/appearance.json`. OS-owned message/file dialogs,
titlebars and some native control chrome may retain Windows styling, particularly
after a live switch; these are not all custom-drawn surfaces. Native Windows dark
support was exercised on wxPython 4.3.1 / wxWidgets 3.3.3; older wx builds provide
less native theming. See the [wxPython appearance limitations](https://www.wxpython.org/Phoenix/docs/html/wx.PyApp.html).

In **Plots → Stack / arrange panes**, choose grouping by unit, one pane per
trace, or custom pane assignments. Like-unit traces can share a pane; unlike
units cannot share a single Y axis. Up to 16 panes have independent Y ranges,
relative height weights, shared time zoom and shared A/B cursors. Pane numbers
define vertical order. Layout is saved with `.spksch` and is undoable. It is a
pane-allocation editor, not yet LTspice-style drag-and-drop pane rearrangement.
Display decimation remains separate from full-sample measurements. The shortened
workspace tabs and their overflow menu provide access without reordering pages.

Use the mouse wheel over a plot to zoom time around the pointer, or Shift-wheel
to zoom its Y axis. **Fit all** resets the display; **Fit Y in view** scales visible
signals to the current time window, ignoring hidden traces and cursor lines.
Display samples are selected again from the original capture when zoom changes;
zooming no longer stays restricted to the initial overview's reduced samples.
The original recorded values remain the inputs to signal math and measurements.

![Actual dark stacked plots](media/reliability/upgrade-dark.png)

![Actual light stacked plots](media/reliability/upgrade-light.png)

![Actual themed properties](media/reliability/upgrade-properties.png)

## Power-tree planning and real subcircuit stages

Open **Power tree** (`Ctrl+Shift+P`). Add root supplies, then select a supply or
converter and add downstream converters/loads. Select blocks on the diagram or
with the stage selector. Edit nominal voltage, load typical/maximum current,
fixed efficiency, input quiescent current and output current limit. Fields not
used by that stage kind are disabled. Reparent with the upstream selector; cycles
and children of loads are rejected. Delete children or reparent them before
deleting their parent. Wheel zoom, middle-button pan and **Fit tree** manage the
diagram. Typical/maximum budgets propagate downstream power demand upstream and
report conversion loss and current-limit warnings. These are **declared planning
assumptions**, not voltages or efficiencies measured by the solver. Maximum
demand changes the budget report, not the generated SPICE load values.

Any stage may attach a real, self-contained `.SUBCKT` file. The project embeds
the source snapshot, original path, SHA-256 and ordered port bindings. Known
IN/INPUT/VIN, OUT/OUTPUT/VOUT and GND/GROUND/0 names receive suggested bindings;
unknown pins remain blank and must be assigned. **Review every binding before
Apply**: `{in}` is the upstream rail, `{out}` the stage's output rail, `{gnd}`
global node 0. Explicit additional net names are supported. No file watcher
silently reloads a changed vendor file—reattach to replace the snapshot.

**Compile to circuit** validates the tree, presents a replacement confirmation,
and produces actual X instances with the attached subcircuit definitions. The
change is undoable and retains the tree. An unmodeled supply becomes an ideal DC
voltage source; an unmodeled load becomes an ideal **typical-current** load.
Converters without models cannot compile: an efficiency percentage is not a
switching model. Compilation starts with `.op`; set an appropriate `.tran` and
model drive signals explicitly for switching studies, then run the existing
native solver. The attached model's behavior, not the budget's nominal output
voltage, determines simulated results. The included `series-loss.cir` is a
verified two-ohm interconnect example, **not a converter model**.

This first implementation supports up to 256 stages and one self-contained
subcircuit definition per attachment. External includes, control scripts and
unrelated top-level statements are rejected; different files cannot silently
reuse a conflicting subcircuit name. Only the owned parser/solver's supported
devices execute. Model synthesis, converter sizing/compensation, efficiency
surfaces, simulation-to-budget back-annotation, sequencing and automatic
electrothermal qualification are not implemented here. It is an initial
power-tree/model-composition workflow, not full feature parity with
[PTree](https://github.com/smariel/PTree).

![Actual power-tree editor with a real attached subcircuit](media/reliability/upgrade-power-tree.png)

## Integrated analytics and user extensions

Open **Analytics** (`Ctrl+Shift+A`) after a transient run or loading `.spkdata`.
Statistics include time-weighted mean/RMS/standard deviation, extrema, ripple,
integral, finite-difference slew and sampling intervals, with source provenance.
The amplitude spectrum and PSD use a Hann window with coherent-gain/energy
normalization respectively. They accept 8–262144 real samples. Nonuniform data
requires the explicit linear-resampling checkbox; the report marks resampling,
which can alter high-frequency content. No silent detrending or automatic
anti-aliasing is claimed. Plots use the active theme and standard plot toolbar.

**Export extension template** creates an editable `.spkanalytics` JSON file.
Extensions use `spikes/analytics-extension/v1`, with an ID/name, scalar
measurement expressions, and plotted trace expressions. `x` denotes the selected
signal. For example, `pp(x)` measures ripple and `x-mean(x)` plots the AC
component. **Load analytics extension** only registers its recipes in the
project; **Run selected extension** explicitly evaluates them on recorded data.
Up to 32 extensions can be stored in a project, with up to 32 measurements and
32 traces each, subject to the existing bounded expression interpreter. Remove
an extension before replacing its ID. Exported reports retain numeric values
and units; the example `ripple-analytics.json` is included in the library.

This is integrated **Python/NumPy analytics and declarative expression
extension support**, not a C++ analytics kernel or an arbitrary executable plugin
host. Python/C/C++/HDL entrypoints are not accepted or loaded by this interface.
The repository's separate process-extension SDK is not yet wired into Studio's
analytics tab; hostile-code sandboxing and general UI-contribution plugins remain
separate work. Loading a model or extension never executes arbitrary host code.

## Native run controls

The toolbar in the native workbench is executable. The old dark ribbon preview
shown in conversation is not connected to a solver and must not be used as the
application. Start `spikes-studio.cmd` in the repository.

- **Run batch / F5** validates and applies the current circuit text, then runs
  the unchanged C++ batch solver in a separate cancellable process. **Stop /
  Shift+F5** terminates that process. Pause is disabled for batch execution.
- **Continuous / Ctrl+F5** creates persistent C++ transient state and follows
  `.tran` TSTEP until Stop (TSTOP does not end continuous mode). **F6** pauses
  at a native step boundary and resumes the same state. This is best-effort
  software pacing, not a hard-real-time/HIL guarantee. A difficult native step
  can delay pause/stop acknowledgement.
- The plot's **Live DC source** control queues an independent constant source
  value in SI units for the next step. Changes made while paused apply on resume.
  Recorded events have simulation timestamps; the saved circuit is not changed.
- Continuous mode keeps the latest **20,000 accepted samples**, with explicit
  dropped/total counts. Old history is overwritten, not written to an unlimited
  file. Exporting `.spkdata` saves the retained window, not earlier history.
- The full-history batch limit remains **1,000,000 output points**. Over-limit
  requests produce a non-blocking error bar; they do not allocate the history or
  silently coarsen the timestep. Those sources remain editable and can be run in
  bounded continuous mode. Batch streaming beyond this limit remains future work.
- Source edits survive refreshes; Run, Save and property editing apply pending
  text after validation. Reconciliation retains IDs, layout, probes and metadata
  for matching component references and kinds. Invalid edits remain in the editor.
- Drag components on a 10-unit grid; one drag is one undoable transaction. Save
  clears the dirty state. Open/New/Close ask whether to save unsaved work.
- `V(...)`, `I(...)`, `P(...)` and lowercase forms work in graph expressions.
  Runs restore saved probes/expressions. Cursor placement retains the current
  plot zoom. Display decimation preserves bin extrema; measurements use all
  retained samples, not the reduced display vertices.

The 20 real GUI event-handler checks and native control traces are recorded in
`media/reliability/evidence.json`. These complement numerical tests; they are
not evidence that every requested editor, device or external format is complete.

![Actual paused persistent session](media/reliability/02-continuous-paused.png)

![Actual source-control response](media/reliability/03-live-control.png)

## Startup performance evidence

The same nine-case, three-repetition cold-process benchmark was run before and
after making optional public-API and CLI imports lazy. SPIKES' median of per-case
median elapsed times changed from **728.76 ms to 203.74 ms**. The after-run values
were **53.10 ms for ngspice** and **530.14 ms for LTspice**. All three passed the
nine shared-subset accuracy checks. Reports retain individual measurements,
executable/library identities, hashes, deck hashes and limitations.

This measures process startup, execution and result parsing together. It does
not isolate numerical-kernel performance, nor establish full solver or UI
superiority. The fixtures include idealized converter/RF/motor electrical
surrogates, not production semiconductor or multiphysics qualification. PSIM,
PLECS and QucsStudio were not measured. See
`media/reliability/performance-before.json` and `performance-after.json`.

## Launch

In the integration checkout:

```powershell
python scripts/launch_spikes_studio.py
```

The development launcher finds the existing native DLL and the workspace's
Matplotlib dependencies. In a generated standalone source package:

```powershell
python -m pip install ".[studio]"
spikes-studio --library path/to/spikes_c_api.dll
```

The default circuit is a 1 kΩ / 1 µF RC network driven by 1 V, initialized with
UIC and run for 5 ms with 10 µs output steps. Press F5. The documented run produced
501 samples with a maximum error of 49.18 µV against 1 − exp(−t/RC). The actual
result, source hash and screenshots are in `media/evidence.json` and neighboring
files. These are local validation results, not cross-engine performance claims.

![Recorded RC response and derived resistor power](media/01-recorded-plots.png)

## Plot expressions and units

Enter an expression in Plots & measurements, then choose Add expression. Scalars
can be plotted as constant traces. Traces of different dimensions occupy separate
panels with linked time axes. No unit conversion or resampling is inferred.

| Purpose | Expression |
|---|---|
| Node voltage | `v(out)` |
| Differential voltage | `v(in,out)` |
| Component current | `i(R1)` |
| Recorded component power | `p(R1)` |
| Derived resistor power | `v(in,out)*i(R1)` |
| Energy dissipated | `integral(v(in,out)*i(R1))` |
| Slew rate | `derivative(v(out))` |
| Mean voltage | `mean(v(out))` |
| RMS current | `rms(i(R1))` |
| Ripple | `pp(v(out))` |
| Voltage magnitude in dBV | `20*log10(abs(v(out)/V))` |
| Trigonometric identity | `sin(v(out)/V)**2+cos(v(out)/V)**2` |
| Conditional trace | `where(v(out)>0.5*V,v(out),0*V)` |
| General recorded trace | `signal("v(out)")` |

Addition, subtraction and comparisons require equal dimensions. Multiply/divide
combine dimensions, and scalar powers transform them. Transcendental functions
require dimensionless inputs. `sin(v(out))` is rejected; use `sin(v(out)/V)` if
that normalization is intended. Trigonometric inputs are radians.

Available functions include sine/cosine/tangent and inverses, hyperbolic and
inverse hyperbolic functions, exp/expm1, log/log10/log2/log1p, erf/erfc, square
root, absolute value, real/imaginary/conjugate/phase, unwrap, degree/radian
conversion, atan2, hypot, minimum/maximum, clip and where. Constants include pi,
e and j; unit literals include V, A, s, K, Hz, ohm and W.

Integrals use trapezoidal accumulation over the recorded timestamps; derivatives
use timestamp-aware finite differences. Mean and RMS are time weighted. These
are numerical reductions, not symbolic identities. In particular, a sparse
capture cannot reconstruct a switching edge that was never recorded.

The expression evaluator interprets a restricted syntax tree. Attribute access,
imports, comprehensions and arbitrary Python calls are not expressions. Domain
errors and nonfinite results produce messages instead of silently drawing gaps.

## Measurements, cursors and equation solving

Measure evaluates min, max, peak-to-peak, mean and RMS of the expression on the
entire loaded capture, or select A/B window for reductions between the cursors.
Window endpoints use explicit linear interpolation. Click twice in the plot for
A/B cursors, delta time, delta value and slope. Further clicks add cursors C–P;
use **Cursors / relative math** to edit or delete them. A/B window reductions
use the first two cursors and the currently selected run.

Hover reports interpolated values at the pointer time. Click a legend label to
hide/show its trace. The Matplotlib toolbar provides zoom rectangles, pan,
home/back/forward view history, subplot configuration and PNG/SVG/PDF export.
Axes chooses linear, log or symlog scaling. Crossings reports threshold times
for rising/falling/either edges. Plot expression recipes are saved in `.spksch`.

Solve equation accepts an expression equal to zero and a scalar bracket:

```text
cos(x)-x; 0; 1
```

It uses bounded bisection and returns approximately 0.7390851332. A root must be
bracketed. This is a numerical scalar root finder, not a general symbolic CAS or
an arbitrary coupled nonlinear equation-system solver. The Python API also
provides interpolated rising/falling/either-edge threshold crossings.

## Probes on the schematic

P arms voltage probing: click a terminal connection circle. Shift+P arms a
differential probe: click positive, then negative. I and Shift+I arm component
current and power probes. The probe expression is saved in the document and
shown beside the anchored component. Double-click its entry in the left list to
plot it after a run. Unknown nodes or components are rejected.

![Differential probe on the actual schematic](media/02-differential-probe.png)

The initial canvas uses named terminals: equal labels mean an electrical
connection. It is not a complete orthogonal-wire authoring tool. Mouse wheel
zooms around the pointer; middle-drag pans. Click selects a part and Ctrl-click
adds/removes it from the selection. E or double-click opens properties.

## Complete property transactions

Select a component and press **E** (or double-click). The top of the dialog now
has a unit-labelled **Value** input and **Simulation model type** selector.
Use engineering values such as `4.7k`, `220u` or `10n`; SPICE `m` means milli,
while `Meg` means mega. Restart an already-running workbench after updating code.

The selector offers only the models currently connected to the native workbench:
ideal R/C/L with C/L initial conditions, DC/PULSE/PWL independent sources, existing
`.MODEL D` references or private custom Shockley diode cards, and the smooth
voltage-controlled switch. Selecting a type reveals its actual parameter fields.
PULSE/PWL replace the source's DC/AC definition; AC attributes are available in DC
mode. Switching a resistor to an unrelated semiconductor family is not supported.

![Value and PULSE model entry in the actual application](media/reliability/property-source.png)
![Actual custom diode fields](media/reliability/property-diode.png)

Custom diode edits create a separate model card rather than modifying another
part's shared model. Existing model references are checked. Unchanged parameter
expressions remain expressions, not frozen elaborated numbers. Unsupported
hierarchical/source-defined model edits are explicitly directed to Circuit text.
The Shockley editor does not imply charge storage or reverse-recovery support.
TNOM is stored on the card; this path uses circuit `.TEMP` for actual temperature.

The four pages have separate fields:

- Parameters: model-specific electrical fields, user metadata, declared temperature, package,
  assembly variant.
- Pins: ordered node names.
- Limits: positive finite limits expressed in SI units.
- Model & evidence: source text and datasheet/qualification notes.

![Actual Limits page](media/03-limits-editor.png)
![Actual Model & evidence page](media/04-model-editor.png)

Apply validates all changes before committing one undoable transaction. Reopening
shows stored values. Ctrl+Z and Ctrl+Y operate on document history; text editors
keep their own editing shortcuts. In bulk selection, unchanged mixed fields are
left untouched. Any invalid change aborts the whole transaction.

Value, node and model-field edits update the supported top-level netlist records
and are validated before committing. General model-source notes, user metadata,
declared temperature and limits do not automatically stamp a device or generate
failure warnings. Run applies edited circuit text and captures that revision.

File > Bill of materials groups current parts by kind, value, package and variant
and exports a real CSV. It does not fabricate supplier or qualification data.

## C/C++, Verilog and VHDL IDE

### Configurable standard passives

Search `id:standard.` in Component catalog for preferred-value R/L/C and
four-terminal Kelvin templates. Double-click to edit nominal value, package
(inch code), construction and tolerance; the nearest-value control offers
E3 through E192 without claiming a stocked manufacturer part. Open Parasitics
& temperature for explicit ESR/DCR, ESL, parallel C, leakage and static TC/corner
coefficients; Pins & connections remains separate. A package or construction
label never guesses parasitics, ratings, thermal drift or accuracy.
Standard resistor templates span 1mΩ to 1GΩ; arbitrary custom values remain
editable. Zero parasitics mean omitted. Manufacturer library entries are
selectively sourced: ideal nominal R/L/C placements are not manufacturer
models, and four-terminal Isabellenhuette entries remain review-only.

### Fuzzy discovery search

Studio discovery searches share typo-tolerant matching: component and manufacturer
catalogs, component model selectors, canvas quick insert, symbol browser, model
collections and library packages, command palette, nets/pins, directives, battery
entries, waveform/run/trace selectors and HDL timing signals. Literal matches
rank before misspellings. Multiword queries require every positive term.
Words of 4..7 characters allow one edit; longer words allow two, including
adjacent-letter swaps. Package suffixes can follow a typo-matched part stem.
Terms shorter than four characters and numeric terms stay literal. Quoted
phrases, exclusions and catalog field values (such as family:resistor) stay
literal. Category, readiness, scope and model-kind filters are never relaxed.
Search cannot change a circuit, approve a model, place a part or rewrite a net.
Exact ID/MPN resolution and code syntax remain exact. No dependency is added.

### Derived analysis plots

After a transient run, choose **Analysis plots...** from the waveform toolbar
or right-click menu. The floating window captures that run and provides XY,
FFT amplitude, PSD, eye diagrams, histograms and cumulative integrals using
signal/math expressions. Select an interval to keep calculations within
262144 samples. FFT requires uniform timestamps; eyes need a supplied symbol
period and at least eight retained samples per symbol. Reports show measured
retained-data statistics, not model qualification. Shift-wheel zooms Y;
the toolbar/context menu provides fit, pan, zoom, grid and PNG/SVG/PDF export.

Six original domain-circuits netlists in the examples folder demonstrate RF RLC,
ideal high-speed interconnect, precision bridge, idealized buck, HV divider and
high-current path behavior. Select ngspice explicitly for those decks. These
examples do not qualify real silicon, PCB SI, high-voltage safety or thermal
behavior.

### Standard IC discovery and functional logic

The manufacturer browser and canvas search include sourced TI 54HC/74HC logic
packages and additional common opamps, instrumentation amplifiers, BJTs and
MOSFETs, with explicit package pins and source links. Review-only records are
not insertable electrical models. Functional HC logic can be exercised through
the standard_logic Python API; it is not yet coupled to the Studio circuit.
Arduino/Pico/ESP32/STM32 firmware execution is not available. Do not interpret
a controller symbol, package pinout or emulator target record as a runnable MCU
or a validated SPI signal-integrity model.

### Canvas quick insert and completion

Double-click blank schematic space to open the small search palette at that
location. Components, Monitors, Text and SPICE filters narrow the suggestions;
the list shows symbols and placement/review status. Up/Down selects, Enter
accepts, Tab fills a completion, and Escape or clicking elsewhere cancels.
Double-clicking an existing object retains its normal editor behavior; wires
do not count as blank space.

Search component names, families, exact manufacturer MPNs or catalog IDs.
Runnable entries open the existing value/model/pin editor and place at the
clicked coordinate after acceptance. Vendor entries without runnable models
and equation-bench-only presets open review instead of pretending to simulate.
Sourced R/C entries retain their ideal-nominal approximation status. Shared
subsheet component insertion still requires Circuit text; the palette reports
that restriction rather than adding an invisible top-level component.

Type free text and choose **Add as text** for an inert note. Dot-prefixed input
offers **Add as SPICE directive** and **Add as text** separately; selecting text
never executes it. Directive placement validates the actual source and is one
undoable edit; failure leaves the draft and saved circuit intact. Partial dot
commands suggest labeled parameter templates. Enter on a template fills it;
Enter again on the directive action validates and places it.

Voltage/current/power meters and Mini scope open a signal/expression binding
dialog using real visible circuit names. They create normal schematic readouts
or attached mini plots, not invented readings. Known `V(net)`, `I(ref)`, `P(ref)`
and basic mathematical function names are suggested while typing; complete
expressions can open a meter-binding editor. This is bounded context-aware
completion, not a compiler/LSP IntelliSense implementation. Unknown or absent
recorded channels remain unavailable until a suitable real simulation provides
them. The displayed search list is capped at 48 suggestions.

### Junctions, wire hops, labels and hierarchy

Branching a wire creates an explicit junction and merges admitted native nets
in one undoable transaction. Junctions can start or end wires. Right-click a
wire and choose **Add junction on clicked wire** to split it at a new connection
point. This alone does not join another net crossing there. Connected T/4-way
points also display automatic dots based on actual net identity; hovering a
junction or highlighting its net shows a halo.

**View > Toggle wire hops** or context **View / navigation > Wire hops** enables
automatic bridges where different nets cross. The newer route bridges the older
route. Hops are presentation only and never change Circuit text or connectivity.
The setting saves in the project and supports undo. Geometry detection assumes
orthogonal routes and is capped at 20,000 markers; an exceeded budget reports a
display error instead of silently changing connectivity.

**Edit > Net label** / **Ctrl+L** arms label placement; click a pin or wire, choose
Local, Global or Hierarchical and review the resolved native net. Double-click
or right-click a marker to edit it. Scope and electrical changes are described
in [scoped net labels](SCOPED_NET_LABELS.md). Source edits that invalidate label
bindings are rejected atomically and require marker review; old labels are not
silently attached to unrelated nets.

**View > Schematic hierarchy** lists real subcircuit instances with ordered port
mappings. Open an instance to view its components and nested descendants;
**Parent sheet** and **Flat schematic** navigate back. Component context menus
also open the containing subsheet. Label, selection and wire hit-testing respect
the current instance view. These are scoped views of source-backed flattened
devices, not full graphical sheet-block authoring. Shared definitions and new
hierarchy ports still use the existing explicit subcircuit/Circuit text workflow.

### Context menus

Right-click a component or empty schematic area for grouped **Edit / selection**,
**Move / transform**, **Place / annotate**, **Probe / instruments** and **View /
navigation** actions. Component properties appear directly for a selection;
wire parasitics appear only when a wire is hit. Existing directive, controller,
annotation and attached-instrument menus remain object-specific. Keyboard menu
invocation (Menu key / Shift+F10) uses the selected symbol or canvas center.

Waveform menus group expression editing, cursors/original-sample measurements,
view controls and annotations, with image export through the plotting toolbar.
Catalog menus target the clicked row; keyboard invocation keeps the selection,
and blank space does not reuse a stale part. Manufacturer menus expose ideal
R/C insertion only where supported, pinouts, provenance, vendor-model review and
exact-MPN copying; a context action does not qualify a manufacturer model.

Dashboard menus select the clicked item and offer properties, duplication,
visual linking, stacking order, grid snapping and deletion. Design edits are
disabled in Run mode. Source-control application still requires an actual
continuous simulation; DUT mapping remains disconnected metadata.

Code editors have their own Undo/Redo, Cut/Copy/Paste, Delete selection, Select
all and Word wrap menus. These operate on the editor, not circuit history or
schematic clipboard. Read-only or unavailable operations are disabled. Shortcut
labels are shown where assigned; unavailable operations stay visibly disabled.

### Code beside the schematic

Controller setup uses visual fields for language, sample interval and state
count, alongside a scrollable block preview with labeled AI/DI/AO/DO pins and
their circuit bindings. Configuration JSON is internal, not an editor the user
must understand. Double-click the preview or use **Pin properties** to edit the
pin table separately. **Apply / save setup** validates before committing;
invalid values leave the saved setup unchanged.

### Dashboard diagrams and future DUT mappings

In Dashboard **Design** mode, add **Block** or **Note** alongside meters, scopes
and source controls. The Signal / expression field is the description for
diagram items, not executable equations. Select an item, press **Connect**, then
click the target; click empty space to cancel. **Unlink** removes links attached
to the selected item. Links follow movement/resizing and are saved with stable
item IDs. Deleting an item removes its incident links; edits support undo/redo.
These connectors are visual relationships, not schematic nets or causal solvers.

**DUT mapping** stores a device/debug-adapter label, connector and pin, MCU GPIO,
Read/Write direction and requested disconnect-safe digital level. These mappings
are data-only drafts: opening, saving or clicking them never accesses hardware.
The existing Source control still controls a simulated DC source, never the DUT.
The preview explicitly marks mappings disconnected.

Future SIL/PIL/HIL adapters must use an explicit target/session selection rather
than silently substituting hardware for simulation, validate bindings against a
target manifest, and require deliberate connect/arm actions for writes. Results
must distinguish requested, acknowledged and measured values and record target
timestamps, latency and errors. Stop, disconnect, stale telemetry and process
failure need tested disarm/watchdog behavior; the requested safe level is not
an implemented safety guarantee. A debug connection alone does not establish
physical real-time performance, instrument safety or hardware qualification.

Use **View > Netlist beside schematic**, **Netlist above/below schematic**, or
**IDE beside schematic** to share the actual editor and canvas in a resizable
split. The editor's **Beside schematic** action does the same. **Home** or
**Code only** restores the ordinary workspace. These views retain the same
draft; they do not copy the source into a second editor. Split layout is
session-only.

Select a known net/component name in SPICE, C/C++ or Verilog source to highlight
the corresponding schematic objects. Controller pin names and indexed
`inputs[n]` / `outputs[n]` references use the configured controller bindings.
Clicking a word also works. Names are matched exactly, not by substring; unknown
names do not create connections. This is a navigation aid, not compiler-level
HDL elaboration or C data-flow analysis. Lexical syntax colors follow the theme.

Double-click a controller card to open its compact floating code editor. **Pins**
opens the settings and **Return editor** puts the same source widget back into
the controller workspace. Closing the floating window hides it and preserves
the draft. **Save setup** commits the controller configuration. Compilation
requires explicit trust; opening the editor does not grant it. The sampled
controller currently executes C/C++, not HDL co-simulation, and runs with the
user's permissions rather than in a hostile-code sandbox.

The editor has line numbers, syntax highlighting, source open/save and actual
compiler logs. Check / compile invokes Icarus for Verilog and Clang or MSVC for
C/C++ syntax analysis. Compiler discovery checks PATH, the repository's installed
HDL tool directory, and installed Visual Studio for MSVC. These are user-managed
toolchains, not downloaded or bundled by opening a project.

![Actual MSVC C++ syntax analysis](media/08-cpp-analysis.png)

Verilog synthesis runs Yosys hierarchy checks, synthesis, statistics and JSON
netlist output. It checks the selected top module and reports the tool's actual
exit status. The built-in initial AND-gate example synthesized successfully on
this host.

![Real Yosys synthesis in the IDE](media/05-real-synthesis.png)

Simulate testbench compiles with Icarus, invokes VVP and plots a generated VCD.
Use a terminating testbench with `$finish` and `$dumpfile("wave.vcd")`:

```verilog
`timescale 1ns/1ps
module top;
  reg clk=0;
  reg [3:0] count=0;
  always #5 clk=~clk;
  always @(posedge clk) count<=count+1;
  initial begin
    $dumpfile("wave.vcd"); $dumpvars(0,top);
    #100; $finish;
  end
endmodule
```

![Timing from an actual Icarus/VVP run](media/06-real-vcd-timing.png)

The lower IDE suite has **Diagnostics**, **Synthesis** and **Timing** tabs. Drag
the divider between source and the suite to allocate space. Synthesis displays
actual Yosys module hierarchy, labeled ports and cell-type counts, not estimated
hardware resources. The inventory tooltip distinguishes detected tools from
connected capabilities. Select **VHDL** for GHDL VHDL-2008 analysis and bounded
testbench execution. The selected top entity is elaborated before execution;
the generated VCD enters the same viewer. Simulation is bounded to 1 ms model
time and 15 seconds wall time per execution stage; build logs and VCD sizes are
limited. VHDL synthesis remains explicitly unsupported. Source dialogs accept
`.vhd` and `.vhdl`, and the editor uses VHDL lexical highlighting.

![Actual GHDL testbench and VCD timing in Studio](media/hdl-suite/vhdl.png)

![Actual native HDL suite with Yosys cell report beside schematic](media/hdl-suite/synthesis.png)

Open VCD also accepts existing simulation captures. Search and check signals to
choose their visibility. Hierarchical scalar and vector signals, timescale, X/Z
and value transitions are retained. Nonzero vector levels are drawn high and
exact vector values are annotated. Drag the dashed A/B cursors directly when
pan/zoom is inactive; the dedicated table shows original-data values, delta,
edge counts, mean complete-cycle period and known-time duty ratio. X/Z intervals
do not count as known duration or invent edges. Export measurements as JSON/CSV.
Display is bounded to 128 signals, 5,000 transitions per signal and 256 value
annotations per signal; skipped display transitions may conceal narrow pulses.
Measurements use the original transitions, not the displayed reduction. This is
a digital value plot, not electrical delay prediction.

![Actual Icarus VCD and dragged cursor readings in the HDL suite](media/hdl-suite/timing.png)

Technology-specific timing closure, STA constraints, place-and-route,
language-server completion and debugging are not yet integrated. Generated/native
code must be trusted; this IDE does not claim an OS hostile-code sandbox.

## Parts browser and designer

Search filters library IDs and names. Open library reads the toolkit-neutral
symbol format. The JSON editor and live drawing share terminal positions,
terminal legs, circles/arcs/polygons and body bounds. Save symbol edits validates
the record; Save library persists the current library. New symbol creates an
editable generic two-pin block. No nominal electrical behavior is invented.

![Actual live symbol designer](media/07-symbol-designer.png)

This is a geometry/source designer. Direct manipulation of pins/shapes, package
wizards and automatic executable-model binding are further work.

## Shortcuts

Edit > Keyboard shortcuts edits command-to-key JSON, detects duplicate key
combinations and loads/saves `.spkkeys`. Profiles are SPIKES, KiCad-inspired and
LTspice-inspired. They cover implemented actions, not every shortcut in those
applications. Single-letter shortcuts are scoped away from text entry fields.

Default keys: Ctrl+O open, Ctrl+S save, Ctrl+I import, Ctrl+E export, Ctrl+Z/Y
undo/redo, Ctrl+V paste, E properties, P/Shift+P voltage/differential probes,
I/Shift+I current/power probes, Home fit, F5 run, A parts, Ctrl+M plots, Ctrl+K IDE,
and F1 help.

## Interchange and clipboard

File import and paste use the same detector and review dialog. A valid supported
SPICE netlist becomes an editable electrical document. A `.MODEL` statement
becomes an unreviewed part record. Unknown syntax reports an error rather than
silently dropping circuitry.

Modern KiCad s-expression drawings and LTspice ASC text can be read as component
inventories with their original text preserved. They do not
yet become electrically translated drawings. QSPICE drawing geometry is not
decoded. Export a SPICE netlist from the originating application for simulation
exchange, subject to the owned engine's supported grammar. Source export writes
the actual netlist. There is no claim of full ASC/QSCH/KiCad schematic round-trip.

KiCad format work follows its [official schematic specification](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/).
Yosys synthesis follows the [official synthesis command documentation](https://yosyshq.readthedocs.io/projects/yosys/en/v0.52/using_yosys/synthesis/synth.html).

## Project thermal setup and simulation manager

Open **Simulation → Thermal setup** (`Ctrl+Shift+T`), or use **Board / thermal
setup** in the **Simulation manager** tab (`Ctrl+J`, also on the toolbar).
Setup is saved inside the `.spksch` project and supports undo/redo:

- Board length, width, total thickness, material and orientation.
- 1–64 copper layers, each with thickness and coverage percentage.
- Open-air, ventilated or sealed enclosure, dimensions, material, wall thickness
  and vent area.
- Ambient temperature, still/natural/forced airflow, speed and direction,
  altitude, an optional known convection coefficient, and mounting/heatsink notes.

Initial values are explicitly **authoring assumptions**, not measured defaults.
These inputs do not yet calculate board or junction temperatures, heat flow or
convection. They are marked `not_coupled`. Ambient does **not** silently set the
electrical `.TEMP` directive. Invalid geometry, inconsistent airflow and nonfinite
values are rejected without changing the document.

The manager has one editable project run profile, with `.spkrun` import/export
for reusable profiles. Choose the owned C++ `native` backend or explicit
`ngspice` compatibility backend, batch or continuous execution, analysis from the
netlist or an explicit transient/operating-point override, integration method,
continuous capture size and best-effort simulation/wall-time ratio. Timestep,
stop and UIC override only apply when Transient is selected; continuous execution
ignores the finite stop time. Optional electrical `.TEMP` is a separate explicit
override. Applying a profile saves settings but does not rewrite the circuit text.
The main toolbar's Batch/Continuous commands choose that execution mode using the
saved profile; **Run profile** first applies the manager's current fields.

The ngspice selection runs a self-contained deck in the existing isolated
process adapter. It never silently substitutes for the owned solver. External
`.include`/`.lib` files and executable control directives are rejected; selected
model-tier or parasitic rewrites that cannot be honored are blocked. ngspice
continuous pause/step/control is unavailable. Completed real transient voltage
vectors can be plotted; currents, power and temperature are not inferred from
backend vectors, and unprojected vectors remain in the result for inspection.
The run record preserves the requested backend and source hash. Older profiles
retain their original native behavior when opened.
The self-closing development GUI check for this flow is
`python scripts/verify_workbench_stage_a.py --backend-only` from the integration
checkout, using the pinned Python 3.11 Studio dependencies and native library.

Run and stop operate the selected backend. Pause/resume is native continuous only.
This is not a parallel queue or hard-real-time scheduler. The last 50 run records
retain status, timing, sample count, source hash and copies of the profile and
thermal assumptions. Later project edits cannot change those recorded copies.
History is session-local metadata, not 50 retained waveforms. Export a selected
JSON report and the latest `.spkdata` capture to retain evidence; capture provenance
also contains the setup/profile and run ID. Exporting a report does not itself
save waveform samples. New project defaults are inserted on loading older files.

![Actual board setup dialog](media/reliability/thermal-board.png)

![Actual native simulation manager](media/reliability/simulation-manager.png)

## SPICE directives on the canvas and in the manager

Press **S** (outside text fields) to add a directive, or right-click the canvas
and choose **Add SPICE directive here**. The dialog includes templates, a SPICE
text editor, an optional annotation title, an editable group, **Enabled in
netlist**, and **Show on canvas**. Paste a statement directly into its editor;
continuation lines must begin with `+`. Each annotation represents one directive.
Double-click an annotation, or select it and press **E**, to edit it. Drag to
position it; Ctrl+Z/Ctrl+Y undo/redo source and annotation changes.

Open the **SPICE directives** tab using **Ctrl+D** or View → Directives. Existing
top-level directives are discovered automatically. Search by text/title/group;
filter by group. Built-in groups are Simulation, Observations, Processing,
Models & libraries, Initial conditions and Other. You can type your own group
names. Select multiple rows to group, enable/disable, show/hide or delete them.
**Locate on canvas** reveals and centers one selected annotation. Hiding an
annotation does not disable execution. Group changes do not reorder the netlist
or turn a label such as “Processing” into a new scripting language.

Enabled edits are validated against the currently supported owned parser.
Rejected edits retain the previous source and document. If Circuit text contains
unapplied edits, apply those first; the directive editor will not overwrite the
draft. Parameter edits re-elaborate affected component values while preserving
component identity, layout and user metadata. Disabled drafts use the ordinary
SPICE comment prefix `* @spikes-off `, so exported netlists cannot execute them.
Source remains authoritative; `.spksch` also retains groups, titles, visibility
and canvas coordinates. Structural `.subckt`, `.control`, `.lib` and `.end`
blocks remain in Circuit text. Their bodies are not flattened into this editor.

Batch `.measure` supports the parser's OP/DC/transient MIN, MAX, AVG, RMS and
FIND subset. The C++ solver produces the electrical samples, then Python reduces
those samples. Transient AVG/RMS use time-weighted integrals of the
piecewise-linear sample interpolant with interpolated window boundaries;
DC reductions remain sample-weighted. FIND uses linear interpolation. Measurements appear in the plot's
measurement panel, run report and capture provenance. A failed measurement is
reported separately from a successful circuit solve. Full arbitrary SPICE
post-processing is not implied: batch `.step` and continuous `.measure`/`.step`
remain unsupported by this workbench. Run-profile overrides may supersede the
deck's analysis and `.TEMP`; inspect the simulation manager's recorded profile.

For schematic cross-probing, choose View > Nets and pins (Ctrl+Shift+N), or
Nets and pins from the canvas context menu. Search by net name or component
reference, choose a net, and double-click a terminal to center its component.
All matching terminal circles and drawn routes are highlighted. Add voltage
probe binds an actual V(net) probe to the project; merely viewing nets does not
modify the circuit. Closing the viewer clears its highlight. Drawing groups
describe routed geometry, not electrical isolation: matching named nodes are
connected even when they have no drawn wire. This is not a pin-type ERC check.

![Actual directive editor](media/reliability/directive-editor.png)

![Actual categorized manager](media/reliability/directive-manager.png)

![Actual source-backed canvas annotations](media/reliability/directive-canvas.png)

## Frequency-domain and pole-zero workspace

Open **View → Frequency** or press **Ctrl+Shift+F**. This separate tab keeps
complex phasors and frequency axes distinct from transient samples; it never
relabels time samples as a frequency response. Select an independent source,
start/stop frequencies, point count, log/linear sweep, and a voltage output for
pole-zero calculation, then press **Run AC / PZ**. `1Meg` and `1MHz` both mean
one megahertz; bare SPICE `1m` means one millihertz. The selected source has a
unit AC phasor and other independent AC sources are zero. DC source levels,
transient settings, `.measure`, and run-profile transient overrides do not define
this explicit frequency sweep. Waveform sources and nonlinear devices are
rejected, not silently linearized. `.step` is unsupported here.

Available views:

- Bode dB/phase and linear-magnitude/phase; real/imaginary versus frequency.
- Nyquist complex-plane locus, polar magnitude/phase, and Nichols gain/phase.
- Group delay from the sampled unwrapped phase derivative.
- Smith impedance and admittance grids; return loss and VSWR.
- Calculated descriptor poles and SISO transmission zeros, with a numeric table.

Use complex expressions such as `V(out)/V(in)`, `V(in)/(-I(V1))`,
`I(R1)/V(in)`, or `exp(-j*2*pi*f*1e-3*s)`. `f` has hertz units; `t` and
time-weighted integral/derivative/mean/RMS functions are rejected on frequency
data. dB gain and Nichols require dimensionless expressions. **Transfer preset**
uses the captured output and source voltage; **Input impedance preset** uses
source-terminal voltage divided by current delivered into the circuit. For a
current-source excitation, this voltage ratio is still a voltage ratio—not a
transimpedance transfer definition. The pole-zero transfer is instead from the
configured excitation to the configured output voltage.

For Smith/return-loss/VSWR, explicitly select **Impedance**, **Admittance**, or
**Reflection coefficient** input and a positive real reference impedance `Z₀`
(initially 50 Ω). Impedance/admittance expressions have unit checks. A
dimensionless expression is accepted as reflection data only when you select
that interpretation; an arbitrary voltage transfer is not automatically S11.
Grids are normalized and traces are drawn in reflection-coefficient coordinates,
following the [scikit-rf Smith chart convention](https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.plotting.plot_smith.html).
Negative-resistance results outside the unit circle remain visible. Singular
`Z = −Z₀` conversion is rejected. VSWR samples with `|Γ| ≥ 1` are undefined and
masked (an all-invalid trace is rejected); negative return loss may describe an
active load. dB magnitude has a −300 dB display floor / return-loss 300 dB ceiling.

Nyquist plots show the positive-frequency sampled locus. Optional conjugate
mirroring assumes a real LTI system; it is not a computed closed contour or an
encirclement/stability certificate. Group delay is a numerical derivative and
requires adequate frequency resolution; it is rejected at transfer zeros.
Pole-zero calculation uses the existing linear MNA descriptor pencil and a
[generalized eigenvalue solve](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.eigvals.html),
not a fit to the displayed trace. Infinite descriptor eigenvalues are counted
but omitted. No pole-zero cancellation reduction, nonlinear bias linearization,
MIMO zeros or production semiconductor small-signal models are implied.

The current workspace is limited to 256 MNA unknowns and 2–10,000 frequency
points, with additional backend output budgets. It uses Python/SciPy linear MNA,
**not the owned C++ AC engine**. Runs execute in a cancellable process and appear
in the simulation manager with their frequency settings and backend label.
Thermal setup is retained in provenance but remains uncoupled.

Use the Matplotlib toolbar to zoom, pan, set axes, and export PNG/SVG/PDF. Click
near a trace for its actual frequency, complex value, magnitude and phase.
Circle/square markers indicate sweep start/end. **Export expression CSV** writes
the evaluated complex values; **Pole-zero table** shows finite values in rad/s.
**Save frequency archive** writes a new lossless gzip JSON `.spkfreq` file,
contract `spikes/studio-frequency/v1`, containing complex samples, pole/zero
results, source hash, backend/settings, and the current plot recipe/reference
impedance. Loading enforces a 64 MiB expanded budget and validates frequency
ordering and finite complex arrays. It does not run circuit code. These archives
are separate from time-domain `.spkdata`; this is not a Touchstone importer or a
multiport calibration/de-embedding implementation.

![Actual calculated Bode response](media/reliability/frequency-bode.png)

![Actual calculated Smith trace](media/reliability/frequency-smith.png)

![Actual calculated pole-zero diagram](media/reliability/frequency-pole-zero.png)

## Split views, stepped runs and schematic instruments

The new **Component catalog** and **Controller** tabs are documented in the
[component library and controller guide](COMPONENT_LIBRARY.md), including exact
preset/native counts, model limitations, code trust and measured alert semantics.

The catalog now includes a virtualized searchable table, category/family tree,
numeric filters, sorting, favorites, symbol/pin previews and 1–100-copy native
insertion with explicit node mapping. **Pin browser to side** keeps it beside the
canvas; **View → Pin properties** exposes the full editable component form as a
resizable, dockable panel. Drafts survive selection changes until applied or
explicitly reloaded. **R/C/L/D** open part placement; **Edit → Enable
part-placement shortcuts** turns those bindings off. Right-click a native preset
to assign its own key, and save/load the bindings in Keyboard shortcuts.

In **Plots**, choose **Layout → Side by side** or **Top / bottom** to put the
actual editable schematic beside or above the graphs. **Plot only** returns
the editor to its schematic workspace. These options are also in the View menu.
Drag the divider to resize. Workspace exports retain the chosen orientation;
older profiles use top/bottom. **Tools / readout** expands the
measurement output, archive controls and continuous-source controls; these are
collapsed initially in split mode to leave room for graphs. Toggle split again
to return the editor to its Schematic tab. **Plot grid** and **View → Canvas grid**
toggle independently. **Stack / arrange panes** overlays same-unit traces or
assigns them to separate, height-weighted panels sharing time zoom/pan.

Use the **Mini plot** schematic tool (or **View → Insert attached mini plot**):
click a terminal or wire, then click to drop the waveform card. Right-click a
pin/wire and choose **Drop mini plot attached here…** to start at that point.
Escape cancels placement. Drag a card to move it; right-click it to edit or
remove it. The card, leader line and attached net's wires/pins use one stable,
theme-aware color. Terminal leaders follow component movement/rotation; wire
leaders retain the exact clicked schematic coordinate. Cards show real retained
run data, with explicit unavailable/stale messages rather than invented curves.
Cards and attachment bindings are saved with the circuit and are undoable.
**Fit view** includes cards; wheel zoom and pan operate on the whole schematic.

Batch F5 now executes each parameter variant through the owned C++ solver:

```spice
Stepped RC startup
.param resistance=1k
.step param resistance list 1k 2k 4k
V1 in 0 1
R1 in out {resistance}
C1 out 0 1u
.tran 10u 5m uic
.end
```

Linear `.step param resistance 1k 4k 1k` and nested parameter axes also work.
Declare parameters before their use. These are sequential native solves, not
parallel solves or reference-engine substitutions. Sweeps are limited to 128
variants and an estimated 2,000,000 retained scalar values across all channels,
in addition to parser limits. Continuous mode still rejects `.step`.

The run selector changes the active capture. **Overlay step runs** adds the
others; **Select overlays** filters individual runs. Legend clicks hide traces.
Measurements, expression additions and `.spkdata` export operate on the selected
run, retaining its step parameters in provenance. The latest step collection is
session-local; exporting an entire collection in one archive is not implemented.

Click a plot to add up to 16 linked cursors across its panes. Open **Cursors /
relative math** to select each cursor's run, signal expression and exact time;
add, update or delete cursors; and choose any two for comparison. Example math:
`b-a`, `b/a`, `(b-a)/dt`, `atan2(b,a)`. Units are checked, incompatible subtraction
is rejected, and each cursor is interpolated on its own run's original grid.
Changing the active run does not reassign existing cursors. Outside-capture
coordinates are rejected; expired continuous-window cursors show unavailable.
Cursor positions/visibility and split layout are session state, not saved recipes.

![Actual native stepped RC, split editor and linked cursor lines](media/reliability/workspace-split.png)

Use **Schematic instruments** from View, the plot controls, or the canvas context
menu. Attach a **Readout** or **Mini plot** to a component and enter `V(out)`,
`V(out,ref)`, `I(R1)`, `P(R1)` or a signal-math expression. Instruments are saved
in `.spksch`; drag their cards with undo/redo or edit their canvas coordinates in
the manager. Double-click a card to reopen the manager. Voltage attachment lines
terminate at the matching component terminal when identifiable; other expressions
attach to the component body. No extra electrical connection is created.

Selected-run readouts use the last sample, or the newest linked cursor's time
on the selected run. `.op` readouts use actual scalar operating-point results,
never generated waveforms. **AC frequency** uses the separately calculated
linear-frequency result at the entered Hz, with engineering, rectangular complex
or magnitude/phase notation. On canvas, `@` separates magnitude from phase in
degrees for reliable font rendering. Complex-power expressions such as
`V(out)*conj(I(R1))` preserve the excitation convention; no RMS factor is inferred.
Mini plots need real-valued expressions, e.g. `abs(V(out))` for frequency data.
They are decimated previews; use the main plot for axes and measurements.

Missing signals, detached parts, expired cursor times and OP mini-waveforms show
**Unavailable**, not zero. Source changes mark known mismatched results stale.
Temperature/failure readouts require actual solver channels and are not invented.
AC remains the bounded linear Python/SciPy backend, not native nonlinear AC.

![Cursor manager using recorded native runs](media/reliability/workspace-cursors.png)

![Operating-point and solved AC phasor readouts on the actual canvas](media/reliability/workspace-phasor.png)

### Schematic and waveform contracts

`.spksch`: UTF-8 versioned JSON, contract `spikes/schematic/v1`, with source,
semantic components, layout, probes, expression recipes and metadata. Saves use a
same-directory temporary file followed by replacement. Future major contracts are
rejected. Opening a file never runs its circuit/model source.

`.spkdata`: ZIP container, contract `spikes/result-archive/v1`. A manifest stores
signal names/dimensions, run provenance and sample count. Each 4096-sample block
contains independent compressed NumPy arrays, including explicit timestamps.
Float/complex values round-trip exactly; pickle is forbidden. ZIP CRCs detect
damaged entries and uncompressed-size budgets apply on load. It is a completed
capture export, not a crash-recoverable live writer; the engine's existing
`SPKWF1` streaming store supplies live rings and triggered capture separately.

`.spkkeys`: versioned JSON shortcut profile. Symbol libraries use the existing
`spikes/studio-symbol-library/v1` JSON contract.

## Recorded walkthrough and evidence

![Walkthrough captured from the running application](media/workbench-walkthrough.gif)

The walkthrough consists of actual window captures after running the C++ RC
solver, placing a differential probe, applying/reopening properties, synthesizing
with Yosys, and simulating a counter with Icarus/VVP. The capture helper asks only
SPIKES' own windows to paint; it does not substitute mockups or sampled formulas.
All screenshot hashes and run provenance are saved in `media/evidence.json`.
# Board-circuit handoff

The desktop can explicitly open a staged board-circuit review with
`spikes-studio --board-circuit-handoff <workspace>/.local/studio-handoff/<file>.json`.
The v1 JSON retains exact board component centers, rotations, sides, pins, nets,
display wires, source digest, occurrence, and reference cross-selection IDs.
Only bindings already marked `reviewed` by the source workspace and supported as
Studio primitives become executable records. Unavailable parts and reviewed
subcircuits without an admitted implementation remain visible and inert with an
explicit reason. Studio never infers a model from a reference or displayed value.
