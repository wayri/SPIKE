# SPIKES Studio product plan

## Current implementation

A runnable wxPython/wxWidgets workbench now exists in
`studio/python/spikes_studio/desktop.py`, using the owned C++ engine and
Matplotlib. It implements persisted property tabs, probes, signal expressions,
shortcuts, source editors, real HDL tool calls, and result files. See
`WORKBENCH_GUIDE.md` for supported operations and actual screenshots. The C++/VTK
desktop architecture below remains the target design; the Python workbench does
not complete those milestones or establish full external-format compatibility.

## Product boundary

SPIKES Studio is a standalone circuit authoring, simulation, instrumentation,
model-building, and automation application over the versioned SPIKES C ABI. The
desktop process owns presentation and document editing; solver sessions run in
owned worker processes so a failed model, long solve, or compiled block cannot
freeze or corrupt the workbench.

The first desktop implementation is C++20 with wxWidgets ribbon/AUI docking and
VTK. VTK supplies the retained 2D schematic scene, picking, overlays, annotations,
large-waveform GPU plots, and future coupled-domain views. Matplotlib runs in a
separate Python plotting worker for publication-quality static plots and export.
The UI never imports Python or an untrusted model into its process.

## Workbench layout

- **Ribbon:** Home, Place, Schematic, Simulation, Instruments, Models, Automation,
  Results, and View pages. Commands are the same actions exposed by context menus,
  keyboard shortcuts, command palette, and the text command API.
- **Left dock:** project/sheet tree above the component-library browser. Library
  search filters by family, technology, voltage/current envelope, fidelity,
  qualification, package, manufacturer, and license.
- **Center document area:** tabbed schematic sheets, hierarchical block diagrams,
  dashboards, text/netlist/model editors, and result plots. A VTK retained scene
  provides pan/zoom, orthogonal wires, buses, junctions, port glyphs, selection,
  rubber-band operations, alignment guides, probe overlays, and live heat/failure
  annotations.
- **Right dock:** selection inspector, model/parameter editor, pin mapping,
  simulation profile, and live property binding.
- **Bottom dock:** simulation manager, waveform/instrument tabs, console, log,
  diagnostics, measurements, and warnings.
- **Status bar:** cursor/grid, active sheet, compile state, engine/session, time,
  timestep, speed, queue utilization, memory, capture state, and worst failure
  margin.

All docks may float, hide, auto-hide, or save into named workspace layouts.
Project layout and user layout remain separate so opening a project cannot move
the user's windows unexpectedly.

## Schematic document model

The native document is not a picture. It is a stable-ID graph containing:

- sheets and parameterized subcircuits;
- components, pins, ports, named nets, buses, wires, junctions and labels;
- model bindings, value expressions, tolerances, temperatures, initial states,
  operating limits and provenance;
- probes, controls, instruments and dashboard bindings;
- C/C++/Verilog/VHDL/Verilog-A block manifests and explicit port maps;
- analysis profiles, sweeps, corners, Monte Carlo runs, captures and plot layouts.

Undo/redo stores semantic commands. Autosave uses an append-only recovery journal.
The project serializer is deterministic and migrates versioned contracts without
rewriting external model files. Unknown future objects survive a save round trip.

## Component library and creator

Libraries are content-addressed packages with a manifest, symbol, pins, model
artifacts, parameters, limits, licensing, provenance, qualification state,
validity envelope, examples, and optional KiCad mapping. Search indexes metadata;
it never executes model code.

The creator has five entry routes:

1. choose an ideal or generic archetype and tune parameters;
2. paste one `.MODEL` statement;
3. import a `.SUBCKT`/vendor library and choose an entry point;
4. bind a reviewed OSDI/Verilog-A model;
5. define a compiled C/C++/HDL control or mixed-signal block.

A sixth assisted route accepts locally extracted datasheet evidence and calls an
explicitly configured LM Studio or Ollama instance over loopback HTTP. The
formation prompt requires a versioned JSON draft containing pin identity, symbol
anchors and keep-outs, equations/source, units, operating envelope, evidence for
each fitted value, unknowns and a validation plan. Generated code is inert,
`unreviewed`, and cannot enter a solver or compiler until the user reviews the
source, resolves every pin and unit, runs qualification fixtures and approves the
resulting content digest.

PDF ingestion is a pipeline rather than a magic import: a restricted extraction
worker emits page-addressed text, tables and image regions; an optional OpenCV
worker finds plot axes, traces, pin diagrams and table cells; deterministic curve
fitting produces candidate values with residuals; the local model then forms a
draft from that evidence. The UI keeps the original crop beside every extracted
claim so a reviewer can reject OCR, diagram or unit mistakes. No provider is
contacted, and no model is downloaded, until the user configures and invokes it.

Pasting `.MODEL` invokes `spikes_studio.model_import`. Known model types receive a
conventional editable symbol and pin order. Unknown types become visible generic
blocks and require explicit pin mapping. The resulting part is local and
`unreviewed`; the user must separately validate accuracy and redistribution.
Creating a visual part never implies that its compact-model backend is executable.

The symbol editor supports pins, pin groups, hidden power pins, IEEE/IEC shapes,
aliases, units/gates, alternate bodies, dynamic parameter text and preview at all
zoom levels. The model editor keeps the original source beside normalized
parameters, diagnostics, curve overlays and qualification evidence.

### Standards-traceable symbol library

The symbol system uses a neutral geometric intermediate representation rather
than embedding toolkit drawing calls. Every library glyph records its source
family (`IEC 60617`, `IEEE/ANSI 315`, manufacturer-specific or user-defined),
source identifier when licensed, revision, terminal anchors, modular-grid size,
orientation rules and redistribution status. IEEE/ANSI 315 is retained as an
optional North-American presentation profile; IEC 60617 is the default global
profile. Projects store semantic component identity, not a baked-in appearance,
so the display profile can change without changing connectivity or simulation.

Normative IEC/IEEE artwork is not copied from a paywalled database without an
appropriate licence. The redistributable base library is independently drawn
from public geometric conventions, reviewed against licensed references and
tagged `conformant`, `derived`, or `unverified` at glyph level. User-supplied
symbol packs remain separate and carry their own licence metadata.

The first qualified library covers resistors (IEC rectangle and ANSI zig-zag),
capacitors, polarized capacitors, inductors, coupled windings, transformers,
voltage/current sources, ground/reference nodes, diodes and diode variants,
BJT/JFET/MOSFET/IGBT devices, switches, fuses, relays, op-amps, comparators,
logic gates, connectors, transmission lines, motors, generators, meters and
generic functional blocks. Each symbol has automated pin-anchor, rotation,
mirror, minimum-size, text-clearance and raster-at-zoom tests.

### Geometry and selection invariants

- every electrical pin has a visible terminal leg ending in a persistent
  connection indicator; the snap target and simulation pin use the same anchor;
- a routed net may touch only a terminal anchor or junction and may not cross a
  symbol body, capacitor dielectric gap, winding, label keep-out or selection
  handle unless the user explicitly creates a crossing;
- reference, value and auxiliary labels use measured keep-out rectangles and are
  automatically moved or flagged instead of being painted across the glyph;
- click selects one component, Ctrl/Command-click toggles, Shift-click extends,
  and marquee/lasso select spatial sets; selection is semantic and survives zoom;
- double-click opens the property editor. The right inspector edits the current
  selection and shows only common editable fields for multiple objects;
- bulk edits show the target count, before/after values and validation failures,
  then commit as one undoable transaction.

The BoM view groups placed instances by resolved manufacturer part, value/model,
package and variant. It supports DNP and fitted/not-fitted variants, reference
expansion, quantity, manufacturer/supplier IDs, license, model qualification and
CSV export. BoM edits are semantic project edits and never silently rewrite a
simulation model or contact a supplier.

The part-creation suite combines symbol geometry, terminal/pin mapping, package
metadata, parameter/limit schemas, model backends, equations, datasheet evidence,
curve-fit plots and qualification fixtures. It continuously checks unconnected
pins, duplicate numbers, missing units, body/label clearance and unsupported
backend features at all rotations and zoom levels.

### Infinite schematic canvas

The VTK scene uses double-precision world coordinates with an origin-rebasing
camera so very large hierarchical sheets do not lose picking accuracy. Mouse,
pen and trackpad gestures provide cursor-centred wheel zoom, middle-button or
space-drag pan, marquee/lasso selection, zoom-to-selection and fit-sheet. Zoom
is bounded and continuous; wires, pins and junctions retain a constant readable
screen-space weight while component geometry remains snapped to the engineering
grid. A spatial R-tree limits picking, redraw and ERC overlays to the visible
region. Level-of-detail rules progressively hide value text and internal block
details but never hide terminals or connectivity.

## Context menus

Context menus are selection-aware projections of the command registry:

- empty canvas: place/search part, paste model/subcircuit, wire, bus, port, label,
  directive, note, dashboard control, zoom and sheet properties;
- component: open model, parameters, limits, operating point, probe V/I/P/T/flux,
  toggle/sweep/Monte Carlo parameter, rotate/mirror, replace while preserving
  nets, enter hierarchy, create reusable block, and qualification/provenance;
- wire/net: name, highlight across hierarchy, differential/multiphase grouping,
  voltage/current/power probe, impedance/network analysis and break/reroute;
- port/block: edit direction/domain/units, expand implementation, compile, inspect
  latency/state, or replace implementation;
- plot trace: cursor, math, FFT, eye, Smith conversion, measurements, event capture,
  export and source navigation;
- warning glyph: explain limit, navigate to contributing part/waveform, acknowledge,
  create trigger or add a protection assertion.

Every destructive action states its scope and participates in undo. Commands that
start execution show the exact analysis profile and target engine.

## Simulation lifecycle

The state machine is `Draft -> Compiling -> Ready -> Running <-> Paused ->
Stopping -> Completed|Failed|Cancelled`. Run, pause, resume, single-step, stop and
restart are explicit engine commands with acknowledgements. Closing a document
cannot silently orphan a worker.

The Simulation Manager lists jobs and live sessions with analysis, variant,
priority, engine, threads, memory, progress, simulated time, wall time, warnings,
capture size and provenance. The parallel coordinator has bounded CPU, memory,
GPU, license and worker pools; it can schedule sweeps/corners/Monte Carlo variants,
pause low-priority work, retry only policy-approved failures and compare results.
It never equates more threads with determinism or hard real time.

Continuous sessions preserve checkpoints and expose a control mailbox. Dashboard
buttons, keys such as `kp-a`, scripts, Python clients and authorized HIL adapters
write timestamped control events into that mailbox. Inputs are applied only at
solver safe points and are recorded in the event log.

## Results, plots and instruments

The result store is chunked, compressed and content-addressed. Each signal has
units, domain, interpolation, sample clock and provenance. Rolling live rings feed
the UI while an asynchronous writer stores selected multirate signals. Triggers
retain pre/post windows, event metadata and relevant solver checkpoints instead of
recording every sample forever.

VTK renders high-rate interactive traces, large decimated envelopes, schematic
heat overlays, phasors and linked cursors. Matplotlib produces deterministic PNG,
SVG and PDF plots from the same query contract. Built-in instruments are scope,
DMM, logic analyzer, spectrum analyzer, network analyzer, Bode/Nyquist/Smith,
power analyzer, thermal monitor and magnetic/mechanical monitor. Instrument
frontends are views over signals; they do not create a second simulation truth.

Scientific plots have explicit quantities, SI units, reference directions,
linear/log/symlog axes, engineering-prefix tick formatting and provenance. Each
plot supports cursor-centred wheel zoom, drag pan, rectangle zoom, autoscale,
undo/redo view, linked X axes, dual cursors with ΔX/ΔY/slope, point inspection,
interpolation policy, trace math, uncertainty/envelope display and event markers.
Complex-domain plots support magnitude/phase, real/imaginary, group delay,
Nyquist, polar and Smith representations without silently changing normalization.

Live rendering uses min/max-preserving multiresolution pyramids so narrow spikes
and switching edges survive decimation. Measurements always operate on the
requested source samples, never on display-decimated pixels. Publication export
records the data query, axis transforms, visible traces, cursor values, font and
renderer versions so the figure can be regenerated exactly. CSV/HDF5/Touchstone
export keeps units and signal provenance alongside values.

## Text and automation surfaces

Every project supports synchronized schematic, SPICE text, parameter table and
Python automation views. A generated netlist is inspectable but edits are applied
as semantic patches where possible; irreconcilable edits create a review diff.

The command palette and console expose stable verbs such as:

```text
place resistor at 1200,800
probe voltage /power/input
set /control/enable 1 at 4.2ms
run profile startup variants all
capture arm trigger "V(sw)>650" pre 50us post 200us
plot V(out) I(L1) on scope-1
```

Python uses the C ABI/session protocol through an explicit local connection.
Scripts are project assets with declared inputs, outputs and permissions. C/C++
and HDL blocks compile out of process into digest-bound artifacts and execute only
through the approved compiled-block/OSDI boundaries. Source pasted into a project
is never executed merely because the document was opened.

## Delivery sequence

### M0 — standalone foundation

- deterministic source/SDK project package;
- engine worker discovery and capability handshake;
- versioned project, part and command contracts;
- `.MODEL` paste-to-part converter and component schema;
- opening workbench shell with ribbon/docks and non-executing schematic canvas.

Exit: clean build, schema/model-import tests, empty project save/reopen, worker
handshake and crash recovery.

### M1 — schematic authoring

- VTK 2D scene, selection, wire router, junction/net connectivity and ERC;
- standards-traceable IEC 60617 and IEEE/ANSI 315 presentation profiles;
- cursor-centred continuous zoom, pan, fit/selection views and level of detail;
- standard passive/source/semiconductor/switch/behavioral symbols;
- hierarchy, subcircuits, ports, parameter propagation and undo/recovery;
- library browser, part creator, `.MODEL` and `.SUBCKT` flows.

Exit: author and round-trip the reference converter, RF and motor circuits without
editing JSON or losing stable IDs.

### M2 — run control and plotting

- compile diagnostics linked to objects;
- run/pause/resume/step/stop and persistent sessions;
- Simulation Manager and parallel variant coordinator;
- scientific multi-axis plots, linked/dual cursors, plot zoom/pan/view history;
- min/max-preserving live waveforms, Matplotlib export and event capture.

Exit: interactive converter session remains responsive under bounded capture and
replays its command/event log exactly.

### M3 — dashboards and instruments

- dashboard editor and reusable meter/control widgets;
- scope, DMM, spectrum/network/power/thermal/magnetic instruments;
- keyboard and console controls, checkpointing, alarms and limit overlays;
- Python closed-loop client API.

Exit: one dashboard drives a switching session, logs triggered windows and restores
the same checkpoint deterministically.

Dashboard projects can also define explicit SIL, PIL and HIL workflows as typed
graphs: plant/session, controller, I/O adapter, clocks, scaling/calibration,
fault injection, assertions, recorder and safety interlock. Every edge declares
quantity, units, direction, rate, latency budget and timestamp domain. A live
monitor compares deadline, jitter, queue depth, dropped samples and safety state;
only measured physical-loop evidence can qualify a HIL workflow.

### Deployable plant and observer models

`spikes/deployment-model/v1` packages a selected circuit or subcircuit as an
explicit input/output/state contract for a library block, observer, control
plant, SIL, PIL or HIL target. Export records the integration mode, nominal step,
deadline, validity envelope, deterministic guarantee, state initialization,
project/engine/model hashes and qualification evidence. Initial adapters target
the SPIKES C ABI and FMI 3.0 Co-Simulation/Model Exchange. Reduced/order-fitted
equations remain linked to their source validation sweeps, and runtime range
violations are observable outputs rather than silently extrapolated behavior.

### M4 — programmable and mixed-signal blocks

- graphical block/port editor;
- safe C/C++ SDK and installed Verilog/VHDL/Verilog-A toolchain adapters;
- digest/approval UI, compile logs, timing/state inspection and sandbox policies;
- ADC/DAC/digital bridge and multirate scheduler views.

Exit: reviewed first-party blocks compile and execute out of process while hostile
fixtures fail closed.

### M5 — qualification and distribution

- signed installers, updater/rollback and reproducible component indexes;
- large-project performance, accessibility and crash-recovery qualification;
- vendor model licensing/qualification workflows;
- authorized physical-HIL adapter, timing/calibration evidence capture and signed
  certification package generation.

Exit: only evidence-backed capability badges can become `qualified`; preview,
simulation-only and physical-HIL states remain visibly distinct.

## Non-negotiable acceptance rules

- UI state never substitutes for engine state; every transition is acknowledged.
- No UI thread performs solving, model compilation, Python execution or bulk I/O.
- Project opening executes no embedded code and makes no network request.
- Unknown models remain editable but visibly unrunnable until mapped.
- Units and reference directions are present on properties, plots and ports.
- A warning can always navigate to its source object and underlying samples.
- Every result binds engine/model/project hashes and complete run settings.
- Hard-real-time and physical-HIL badges require the separate physical evidence
  gate; desktop pacing or loopback can never earn them.
