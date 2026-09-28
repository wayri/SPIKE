# Workbench handbook

Use this handbook for the order of operations. The **Controls** section in Help lists the buttons, fields, menus, and ribbon tools from the interface. **CLI** contains command help from both parsers; **Diagnostics** contains the registered codes and their issued recovery actions. Search accepts several words, including a complete error code.

## Projects, import and assembly

Start with File → New project, import a board, then Save As. Check the net count, physical copper stack, units, source identity, and import-quality issues before adding analysis inputs. Open project restores a package; importing a different board creates new board-bound state. Save instance creates a separate revision for comparison.

For multi-board work, use the assembly editors to add board instances, set positions and rotations, assign electrical connections, and review scope/admission. Use **Stacked board connector mates** for direct board-to-board headers with explicit pin pairs, and **Harnesses** for cables. A visible board is not automatically included in the electrical or thermal solve. Check the active design, board instance, net and return path at each endpoint. The Harness planner creates proposed connections that need review; use Bond Manager for explicitly modeled connections and material/contact assumptions.

**Example:** import a board with a known connector-to-load rail. Compare its source and load pads with the CAD design, inspect Import Quality, save the project, then reopen it. The expected outcome is the same design and terminal identities. A screenshot of a loaded board demonstrates import/navigation only; it is not a completed analysis.

See [Project format](SPIKE_PROJECT_PACKAGE_V3.md), [Assembly analysis](MULTIBOARD_REDUCED_NETWORK_ORCHESTRATION.md), and [Import architecture](IMPORTER_ARCHITECTURE.md).

## Layout, 3D and selection

Choose 2D to inspect copper by layer and 3D to inspect stackup and mechanical context. Fit recovers off-screen geometry. Wheel zooms; 2D drag pans. In 3D, left drag orbits and middle/right drag pans; middle-click sets the orbit center. Selection filters limit picking to appropriate objects. Confirm the inspector's net, layer, object and coordinates before creating a terminal or probe. Use the context menu for selection, isolation and task actions.

Layers, object visibility, models, opacity and clipping control presentation. They do not remove electrically connected copper from a solve. Imported 3D models do not acquire material, loss or thermal properties merely by being visible.

**Example:** select the supply net, isolate its copper, switch to the bottom layer and inspect a through-via connection. Fit, restore visibility, then inspect in 3D. The expected result is consistent object identity across the views, not identical screen coordinates.

See [Task sequences](USER_TASK_SEQUENCES.md) and [Result visualization](RESULT_VISUALIZATION_AND_LIMITS.md).

## PI: DC drop

1. Open PI and select the power net and a compatible installed solver.
2. Place a voltage source and current load on exact connected copper. Define the return policy and domain. Confirm terminal units and polarity.
3. Preview mesh. Resolve disconnected terminals, missing geometry, unsupported via/zone conditions, and resource admission failures.
4. Run the DC analysis. Read operation status, model status and convergence separately.
5. Inspect voltage/drop, current density, resistance and power loss where provided. Probe the source, load and narrow copper sections.
6. Save the setup and completed result, then generate the engineering report.

**Worked check:** a standalone 1 ohm resistor carrying 1 ampere drops 1 volt and dissipates 1 watt. This is an analytical sanity check, not a prediction for an arbitrary PCB. For a real board, compare against its actual dimensions, copper conductivity, temperature and current paths. The report must retain its approximate/validated status and any convergence warnings.

See [DC solver](DC_SOLVER.md), [PI path analysis](PI_PATH_ANALYSIS.md), and [Solver status](SOLVER_STATUS.md).

## PI: AC extraction and PDN

Define the source-to-load path, explicit reference/return, frequency range, point count, via plating and mesh settings. Extract the supported geometry parasitics, then inspect port definitions and provenance before using the result in a circuit. Do not interpret partial inductance as a complete loop result without the corresponding return definition. PDN candidate comparison requires the same topology, limits and operating assumptions across candidates.

**Example:** retain one baseline request, change one decoupling candidate, and compare the impedance curves and limit crossings on the same frequency grid. Record ESR/ESL and mounting assumptions. A lower sampled peak alone does not establish broadband stability or regulator-loop stability.

See [PDN screening](PDN_SCREENING.md), [PDN optimization](PDN_OPTIMIZATION.md), [Loop parasitics](LOOP_PARASITICS.md), and [Extraction validity](RLCG_EXTRACTION_VALIDITY.md).

## PI: transient

Choose DC, Step, Pulse or PWL per source/load. Set delay, rise, high time, fall and period; a pulse period must contain its rise, high and fall durations. Use finite edges and review the preview. Set stop time, integration step, storage decimation, memory and time budgets. Preview/preflight before solving.

**Example:** a pulse with 1 us delay, 100 ns rise, 1 us high time, 100 ns fall and 5 us period is internally consistent. Run long enough to see multiple periods if periodic behavior is the question. Compare minimum load voltage and settling against the chosen limit. Increasing saved-frame decimation reduces stored frames; it does not substitute for a sufficiently small integration step.

Use playback and frame controls after a result exists. Missing fields stay unavailable. Geometry-derived RL behavior does not infer a nonlinear regulator or switching device from a footprint.

See [Transient PI](TRANSIENT_PI.md) and [PEEC/circuit coupling](PEEC_NGSPICE_HYBRID.md).

## Power Tree and topology editor

Extract from board, import a schematic/netlist, generate from inputs, or add symbols manually. Review the generation preview before Add/Replace. Place source, conversion stages, series/shunt parts and loads; connect OUT to IN. Escape cancels the wire. Ctrl-click extends selection, empty-canvas drag selects a region, and wheel zooms. Middle/Alt-drag pans. Arrange and Fit help with larger sheets.

Double-click a symbol or open Properties to edit it. Assign source voltage, load current/power, models and pad roles. Review isolated returns, operating cases and each connection. Use Undo/Redo for edits. Reset restores the opening sheet state; Clear is destructive to the current sheet and asks for confirmation. Use for analysis validates the topology and builds rail jobs.

**Example:** connect a supply through a series resistor to a load, assign the resistor's value and the source/load conditions, then inspect the generated analysis jobs. A successful topology handoff proves the requested path was assembled; inspect the numerical result separately.

See [Topology model](TOPOLOGY_MODEL.md) and [Power Tree benchmark](POWER_TREE_BENCHMARK.md).

## SPICE model and circuit workbench

Review component assignments, model identity, pad-to-pin mappings, analysis command, geometry parasitics and vector bindings. Use primitives for explicit R/L/C parts. Vendor subcircuits require reviewed model files and correct pin order. Validate the composed netlist before Run; unavailable runtimes, unreviewed mappings or unsupported model features remain blockers.

**Reproducible example:** the following circuit has a 2.5 V midpoint, 2.5 mA divider current and 6.25 mW dissipation in each resistor. These are analytical expectations. The evidence gallery separately identifies recorded solver output.

```spice
* 5 V resistor divider
V1 in 0 DC 5
R1 in out 1k
R2 out 0 1k
.op
.end
```

Save this as divider.cir. Run the standalone parser first, then the solver on a machine with the required native runtime. Confirm its status and exported vectors rather than accepting the expected values as measured evidence.

```powershell
.\spikes.cmd check divider.cir
.\spikes.cmd run divider.cir --help
```

See [SPICE workspace](SPICE_WORKSPACE.md), [SPIKES CLI](SPIKES_CLI.md), and [Model library](SPIKES_MODEL_LIBRARY.md).

## HF / SI: source-to-receiver

1. Open the S-parameter workbench and Source-to-receiver workflow.
2. Choose a uniform RLGC line, Touchstone input, or supported board-derived channel with explicit reference.
3. Set source/receiver ports, impedances, package R/L/C, source levels, rise/fall times, thresholds and passive tolerances.
4. Review IBIS inventory/corners and optional explicitly limited endpoint binding.
5. Run, then inspect loaded transfer, receiver waveform/eye, crosstalk, TDR and noise where the input supports them.
6. Save the study/result and export the channel as RI, MA or DB Touchstone as required.

**Example:** begin with a two-port uniform line and matched endpoints, retain the baseline, then change receiver capacitance. Compare the loaded transfer and edge shape. Time-domain work requires explicit DC, uniform spacing and enough bandwidth; frequency output may remain usable when an eye calculation is blocked. Touchstone channel export excludes source/receiver loading.

See [SI workflow](SI_WORKFLOW.md) and [Geometry-derived channel](GEOMETRY_DERIVED_SI_CHANNEL.md).

## HF / SI: network, geometry and protocol suites

The geometry/protocol tab retains port/network inspection, mixed-mode tools and NRZ/PAM4 studies. Check port order and reference impedance before renormalization, cascading or delay edits. Select the intended protocol suite and inspect its requested metric, test conditions and supported states. A plotted eye or suite result is not an automatic compliance certificate.

**Example:** import a two-port Touchstone network, inspect S11/S21, change reference impedance using the explicit operation, and export/reimport the same representation. Confirm frequency units, port count and complex values. Do not silently manufacture missing DC samples for TDR.

See [Network workbench](SIGNAL_INTEGRITY_NETWORK_WORKBENCH.md) and [Engine gates](SI_SPICE_EMI_RF_ENGINE_GATES.md).

## EMI and chamber

Define the domain, candidate nets, return paths, excitation, requested frequency range, probes and resource limits. Run preflight and the screening pre-pass before selecting a qualified external field route. Review the generated test schematic. The chamber view exposes setup geometry, DUT placement and observations; geometry alone does not establish a solved radiated-emission field.

**Example:** retain a baseline excitation and return, then change one return-path assumption. Compare screening evidence under the same setup. For a field run, retain the prepared case, runtime provenance, convergence and returned field data. Prepared, screened, blocked and solved are distinct outcomes.

See [EMI workflow](EMI_WORKFLOW.md) and [Chamber workflow](emi-chamber-workflow.md).

## Thermal, assembly and hardware

Define bounding volume, ambient, medium, gravity, enclosure intent and power at explicit coordinates. Select natural or forced flow; forced flow requires positive flow and direction. Use the assembly/hardware editors for declared materials, contacts and hardware intent. Select the compact RC estimator for its supported approximate screening route or a compatible qualified field adapter for the requested physics.

Run Preflight, Prepare and Run in order for an external case. A prepared case has no computed temperature field. After execution inspect residual convergence, temperature extrema, returned field counts and the physical extent. A heated case that reaches its iteration limit remains failed_to_converge.

**Example:** first check a zero-power ambient scenario; temperature should remain at ambient within the solver's qualification tolerance. Then add a documented power source inside the volume and compare to the baseline. Confirm units: canonical temperature may be Kelvin while the UI displays Celsius; scene dimensions are millimetres. Unsupported radiation, solids or contact physics must not be assumed from visible hardware.

See [Thermal workflow](THERMAL_WORKFLOW.md), [Thermal field jobs](THERMAL_FIELD_JOB_CONTRACT.md), and [Environment profiles](ENVIRONMENT_PROFILES.md).

## Probes, fields, limits and results

Choose the result and supported quantity before interpreting a color map. Set layers, scalar/vector visibility, range, units and playback/frame settings. Hover probe is temporary inspection; Place probe retains a location. The probe table compares persistent probes and exports CSV. A zero, unavailable value, missing sample and hidden overlay mean different things.

**Example:** place source, load and bottleneck probes for a DC result. Compare source-to-load drop with the limit; compare density at narrow copper using the displayed units. Save a separate revision before changing the design, then compare like-for-like result types and operating conditions.

See [Visualization and limits](RESULT_VISUALIZATION_AND_LIMITS.md).

## Reports, exports and verification

Preview the engineering report after selecting the relevant PI, SI or Thermal workspace. Verify result identity, model status, units, numerical warnings, plots and provenance. Print/PDF uses the report preview's print action. Probe CSV exports measurements; Touchstone exports network data; SPICE exports the explicit circuit; STEP exports available mechanical geometry. Save instance retains a project revision. Export buttons do not create solver results.

Accuracy and validation runs the installed benchmark corpus. Inspect the individual check and tolerance; a passing corpus does not validate every model or every physical regime. External Engine Center distinguishes detection, registration, readiness and qualification. Settings includes interface, visualization, resource and shortcut preferences.

See [Solver Manager](SOLVER_MANAGER.md), [Validation program](VALIDATION_PROGRAM.md), and [Troubleshooting](../TROUBLESHOOTING.md).

## CLI and repeatable automation

Use the integrated CLI category for the exact command and flag reference. Global SPIKE options precede the subcommand. SPIKES is the separate circuit engine and has its own arguments and exit codes. Save requests, result JSON, report artifacts and tool versions together.

```powershell
.\spike.cmd --help
.\spike.cmd capabilities
.\spike.cmd solvers
.\spike.cmd --output-format text inspect board.kicad_pcb
.\spike.cmd preflight spike-analysis-request.json
.\spike.cmd --output mesh-preview.json mesh-preview spike-analysis-request.json
```

Replace board/request paths with real files. A parser accepting an option does not guarantee a locally installed solver implements it. Check command exit status before consuming an output file; avoid mistaking an older result for a new successful run.

See [CLI reference](CLI.md), [CLI workflow](CLI_WORKFLOW.md), and [SPIKES CLI](SPIKES_CLI.md).
