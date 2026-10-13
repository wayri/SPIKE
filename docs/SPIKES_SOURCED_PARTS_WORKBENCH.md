# SPIKES sourced parts and interactive workbench

Source development increment, 2026-10-12. Installed beta and installers are
unchanged. This is not a universal manufacturer-model or accuracy release.

## Everyday workflow

Launch `python scripts/launch_spikes_studio.py --library <native-library>`.
The launcher admits only a matching native-wheel cache; the inspected runtime
was Python 3.14.2, wxPython 4.2.5, NumPy 2.4.2, Matplotlib 3.10.8 and SciPy 1.17.0.
This is separate from the older Python 3.11 packaging stack. Qt is not introduced.

The primary navigation exposes Schematic, Waveforms, Dashboard and Simulation.
Context tools have icons, names and shortcuts; the run bar uses themeable buttons
instead of black toolbar captions on a dark background. The schematic palette
hides when another workspace owns its inspector. A readable connected RC startup
uses routes derived from the source's existing named nets, not proximity.

Waveforms has searchable recorded signals, run/overlay selection, trace
visibility, engineering units and a persistent cursor table. Linked crosshairs,
draggable cursors, axis zoom, rectangle zoom, pan/history and context actions use
the existing Matplotlib interaction engine. Original samples own measurements;
bounded display representations do not replace them.

Dashboard supports design/run mode, scope, meter, threshold indicator and source
control widgets. Add or drag/resize widgets, edit bindings, then switch to Run.
Starter instruments use actual acquired signals, preferring output voltage over
ground. Controls are finite/bounded DC source commands queued at native step
boundaries, with explicit acknowledgement. A recorded capture is not live I/O;
hardware is explicitly shown disconnected. Digital-twin telemetry adapters and
physical SIL/PIL/HIL endpoints are not supplied by this UI increment.

## Real manufacturer parts, not generic-count inflation

**Manufacturer parts** opens the dedicated exact-MPN browser. Search/filter by
maker, category and readiness; inspect source URL, pin order, nominal values,
tolerance, selected ratings and model limits. The checked-in seed has 23 exact
MPNs from Murata, Yageo, TI, ADI, Infineon, ST, Vishay, TDK and Littelfuse.

Seven sourced R/C records are insertable as **ideal nominal approximations**.
Nominal value, exact MPN, manufacturer source, and selected voltage/power ratings
persist with each primitive. Ratings feed captured-limit screening, not physical
failure laws. No DC-bias MLCC loss, ESR/ESL, resistor frequency dependence or
thermal behavior is silently invented. Subcircuit insertion and pin mapping are
explicit and undoable; shared node templates do not guess parallel wiring.

LM358P, LM741CN/NOPB, LM393P and other active/thermal/protection records are
acquisition targets, not executable models disguised as renamed generic parts.
**Review vendor model** accepts a user-supplied plain SPICE file and licence
statement, preserving original bytes/hash, provenance and declared pins. Intake
does not approve execution, redistribution or manufacturer qualification.
Existing model-paste and compatibility-backend workflows remain separate.

The existing generic equation/preset catalog remains available as **Primitives**;
its 5,000 presets are not 5,000 manufacturer parts. MPS, Cree/Wolfspeed and broader
maker/device coverage, reviewed vendor dependencies, qualification and executable
LED/PTC/NTC/inrush/fuse/IC models remain open work. An ideal nominal library cannot
establish realistic runaway/current-sharing or predictive service-life accuracy.

## Offline MOSFET table fitting

Open **View → Fit MOSFET curves**. Import a UTF-8 CSV with exact column names
`vgs_v,vds_v,id_a`, all in SI, containing 15–5,000 unique forward NMOS biases
and at most 1 MiB. Enter a source note and identify measured versus datasheet
table data. Fitting runs in a bounded child process with a 45-s timeout.

The independent channel law integrates `KP*(Vgs-VTO-v)` over the channel;
triode is `KP*(u*d-d*d/2)`, saturation is `KP*u*u/2`, both multiplied by
`1+LAMBDA*Vds`. Four deterministic starts, analytic parameter derivatives,
bounded least squares, conditioning gates and held-out rows produce a report
and measured/fitted curves. VTO/KP/LAMBDA assume W/L=1 and bulk tied to source.

Explicit review is required to export/paste/place a `.model`. Evidence, fitting
errors and sampled validity ranges remain attached; the output is always an
**unqualified reduced-order DC draft**. It infers no transient charge, breakdown,
reverse conduction, thermal law, BSIM or WBG physics. CSV/table import is supported;
automatic bitmap/PDF curve extraction is not. Frozen installer worker support
also remains pending. Public Python API: `python.spikes.mosfet_curve_fit.fit_csv`
and `model_card(..., reviewed=True)`.

## Captured-limit indications and direct symbol interaction

Limit markers are an opt-in/hideable view feature. Symbols change color and gain
V!/I!/P! badges; a temperature finding adds a thermometer/T! mark. Warnings use
captured electrical channels or explicitly evidenced thermal screening. Missing
temperature remains unavailable, never an inferred solved temperature. Markers
are hidden when the displayed circuit revision differs from the result binding.
Exceeding a declared threshold does not itself mean breakdown or destruction.

Right-click a symbol and bind it to a controlling independent DC source with
low/high click-control values. This does not create a hidden physical connection:
for a switch, wire the chosen gate/control source explicitly. Start Continuous,
enable **Interact**, then click the symbol to toggle that source.
Editing and live interaction are distinct modes. Unsupported parts, inactive
sessions and outstanding unacknowledged commands are rejected. The saved source
is not overwritten by temporary controls. This is virtual-time interaction, not
hard-real-time or a hardware protection mechanism.

## Hidden wire parasitics and extraction handoff

Right-click a terminal-leaf wire and select **Hidden wire R/L/C**. Enter series
R in ohms, L in henries and endpoint shunt C in farads, plus an explicit return
node and extraction/measurement evidence. The saved canvas remains a wire;
run-only lowering splits its terminal node and adds hidden lumped primitives.
Actual pin-node mapping and the resolved wire model are retained in the result.

Only explicit leaf edges are currently admitted. Internal branches, return-ground
impedance, coupled transmission lines and distributed PCB networks are not
approximated. Unlike screen geometry, authoritative named nets still determine
connectivity. **File → Export wire extraction** produces stable IDs and a source
hash; **Import wire extraction** accepts a bounded `spikes/wire-rlc/v1` result:

```json
{"contract":"spikes/wire-rlc/v1","project_id":"saved-project-id",
 "source_sha256":"exact-source-hash","wires":[{"wire_id":"saved-wire-id",
 "model":{"enabled":true,"r_ohm":0.02,"l_h":1e-8,"c_f":1e-11,
 "reference":"0","evidence":"supplied extraction record"}}]}
```

Import validates all models atomically before committing, is undoable, and rejects
unknown IDs, mismatched circuit hashes, nonfinite values and unsupported topology.
This is an integration contract, not a finished wayriCAD RLC-plugin connector or
automatic schematic+PCB parasitic extraction/virtual-board workflow.

## KiCad interchange and verification

`.kicad_sch` file import uses installed `kicad-cli` (or `SPIKES_KICAD_CLI`) to
export SPICE and authoritative connectivity. Export-declared hierarchical net
names receive recorded safe aliases; the observed `/GND`→`GND` export maps to 0.
Absent analysis gets a disclosed `.op` setup for review. Basic placement is
retained, but native glyphs, wires and hierarchy drawing are not round-tripped.
Incompatible models produce a loss/recovery report, never a partial circuit.
Generic KiCad S-expression `.net` import currently admits two-pin R/C/L only;
other parts require explicit model/pin mapping. Paste and model-library dependency
translation are not equivalent to full KiCad editor parity.

Real native GUI evidence lives under `artifacts/studio-workbench-final-20261012/`:
RC response checked against the analytical exponential, recorded signals/cursor
panel, dashboard bindings, actual source-click acknowledgement, stop and reopen.
Wide/narrow screenshots capture the real program and computed data, not mockups.
The source regression suite, MOSFET fitting tests and native KiCad fixture test
have separate scopes; see the recorded acceptance reports for exact counts/skips.
No installer/installed-build acceptance or whole-product parity is implied.

Recorded final checks: 271 Studio tests, 269 passed and two explicit skips
(unconfigured ngspice comparison and unavailable symlink creation), plus 11/11
MOSFET fitting tests. Native KiCad 10 fixture import and actual wx controls were
enabled. Architecture and scoped diff checks passed. The verification report is
`artifacts/studio-regression-complete-20261012.json`; real GUI captures and eleven
workflow assertions are in `artifacts/studio-workbench-final-20261012/`.
Contributing-wide Python/TypeScript/Rust and installer checks were not run for
this separate Studio increment. Human review of the new numerical fit remains
required before a qualified release.
