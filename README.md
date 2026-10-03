<img src="app/public/spike-icon.png" alt="SPIKE icon" width="96" height="96">

# SPIKE: PCB simulation for KiCad

[![Preview release: v0.3.1](https://img.shields.io/badge/preview_release-v0.3.1-blue)](https://github.com/wayri/SPIKE/releases/tag/v0.3.1)
[![Community preview](https://img.shields.io/badge/status-community_preview-orange)](https://github.com/wayri/SPIKE/releases/tag/v0.3.1)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue)](LICENSE)

SPIKE is an open-source PCB analysis and simulation workbench for KiCad boards.
Explore **power integrity (PI), signal integrity (SI), board thermal analysis,
and RF antenna simulation** in one desktop app. Import a board, inspect its
copper and components in 2D or 3D, set up a study, and probe the results in the
board viewport. Optional **[EMerge](https://github.com/FennisRobert/EMerge)** and
**[openEMS](https://openems.de/)** extensions add electromagnetic
simulation workflows.

SPIKE runs locally and includes a command-line interface. **v0.3.1 is a
community preview.** Review the [solver status and numerical limits](docs/SOLVER_STATUS.md)
before relying on an analysis.

## Start here

- [Five-minute ESP32 walkthrough](docs/ESP32_QUICKSTART.md)
- [User guides](docs/README.md)
- [Build from source](docs/DEVELOPER_GUIDE.md)
- [Automated builds](docs/BUILD_AND_RELEASE.md)

## Download

| Platform | v0.3.1 package | Status |
| --- | --- | --- |
| Windows x64 | [Installer](https://github.com/wayri/SPIKE/releases/download/v0.3.1/SPIKE_0.3.1_x64-setup.exe) | Community preview |
| Linux x64 | [Flatpak](https://github.com/wayri/SPIKE/releases/download/v0.3.1/SPIKE_0.3.1_linux-x86_64_EXPERIMENTAL.flatpak) | Experimental |
| macOS Apple Silicon | [DMG](https://github.com/wayri/SPIKE/releases/download/v0.3.1/SPIKE_0.3.1_macos-arm64_EXPERIMENTAL.dmg) | Experimental |
| macOS Intel | [DMG](https://github.com/wayri/SPIKE/releases/download/v0.3.1/SPIKE_0.3.1_macos-x86_64_EXPERIMENTAL.dmg) | Experimental |

[Release notes and SHA-256 files](https://github.com/wayri/SPIKE/releases/tag/v0.3.1)
and [Linux/macOS installation and CLI commands](docs/PLATFORM_PACKAGES.md).
Each package includes the local analysis worker; Linux and macOS packages also
include CLI launchers.

## Contents

- [New in 0.3.1](#new-in-031)
- [PCB and antenna examples](#esp32-pcb-and-antenna-simulation-examples)
- [Analysis capabilities and limits](#pcb-analysis-capabilities)
- [Circuit simulation choices](#circuit-simulation-choices)
- [Extensions and dependencies](#extensions-emerge-openems-and-board-workflows)
- [CLI examples](#try-the-cli)
- [Guides and support](#more-information)
- [License](#license) and [acknowledgements](#acknowledgements)

<details>
<summary>Preview status, warranty and responsibility</summary>

**Disclaimer:** SPIKE is a work in progress and is provided **AS IS**, without
warranty or guarantee of any kind, including accuracy, reliability, or fitness
for a particular purpose. Use it at your own risk. To the extent permitted by
applicable law, and unless otherwise agreed in writing, Yawar B (wayri) and
the contributors are not liable for any damage, loss, or other consequences
arising from using or being unable to use SPIKE, including incorrect results,
design errors, equipment damage, data loss, or financial loss. You are
responsible for checking inputs, assumptions, and results before relying on
them. This summarizes the warranty and liability provisions in the
[Apache License 2.0](LICENSE); the license terms govern.

</details>

Current limits are summarized below and described in
[Solver Status](docs/SOLVER_STATUS.md).

## New in 0.3.1

- View EM fields on the board, link plots to probes, and inspect EMerge results in 3D.
- Prepare whole-board volume meshes with fine sizing around selected nets and traces and a coarser background. Review material interfaces, coverage and cell quality before choosing a solver.
- Set up coupled assembly circuit, thermal and EM studies using the supported reduced models.

The [focused meshing guide](docs/PCB_FOCUSED_VOLUME_MESHING.md) includes a complete example. This path accepts a normalized planar board model; automatic KiCad conversion and bent rigid-flex volume meshes are not yet supported.

## ESP32 PCB and antenna simulation examples

Start with the [five-minute walkthrough](docs/ESP32_QUICKSTART.md) to import
the board, open saved thermal and antenna results, and probe the viewport.

![ESP32 board imported into SPIKE's 3D viewport](examples/esp32/evidence/viewport_3d.png)

*An open ESP32 board in SPIKE's 3D view. This capture shows the imported board
before an analysis is run.*

![Solved relative ESP32 antenna radiation pattern](examples/esp32/evidence/rf_surrogate_pattern_3d.png)

*An [EMerge](https://github.com/FennisRobert/EMerge) antenna solve displayed as a relative 3D pattern. SPIKE exported a
two-conductor model of the board; the [ESP32 example](examples/esp32/README.md)
records its inputs, assumptions, and plots.*

![ESP32 board and EMerge radiation pattern in the SPIKE viewport](examples/esp32/evidence/emerge_pattern_in_spike_viewport.png)

*The ESP32 board and its [EMerge](https://github.com/FennisRobert/EMerge)-powered radiation pattern together in SPIKE's
3D viewport at 2.45 GHz. This saved run uses a simplified two-conductor
antenna model; the surface shows relative far-field shape, not absolute gain.*

For more examples, see the [thermal walkthrough](docs/THERMAL_USER_GUIDE.md),
[SI walkthrough](docs/SI_USER_GUIDE.md), and
[simulation studies guide](docs/SIMULATION_STUDIES.md).

## PCB analysis capabilities

Use SPIKE to investigate DC voltage drop and power distribution, inspect
S-parameters and NEXT/FEXT crosstalk, compare board cooling conditions, and view
2D antenna cuts and 3D radiation patterns. Each workflow has its own model
requirements and limits, summarized below.

### Board and project

Import KiCad PCB data into SPIKE projects with ordered stackup, copper, tracks, vias,
pads, filled zones, components, rigid-flex regions, and import diagnostics. Inspect 2D
layers and the assembled 3D scene; select nets and objects, place probes, and save
versioned `.spike` projects with multiple study cases.

**Limit:** Some KiCad features or 3D models may be omitted or substituted; review the
import report for the specific board.

### Power integrity and circuits

Set sources, loads, returns, mesh and limits; run supported DC voltage-drop, harness,
PEEC, PDN, power-tree, and circuit workflows. Converter models can include voltage,
efficiency, and loss settings.

**Limit:** DC and PEEC paths use simplified conductor and return models. Converter
behavior and pin mapping must be supplied; a footprint alone does not provide them.

### Signal integrity

Analyze loaded RLGC or Touchstone channels with explicit ports and terminations; inspect
S-parameters, reflection/VSWR, TDR/TDT, waveforms, eyes, and NEXT/FEXT.

**Limit:** Port-network results do not contain spatial E/H fields. Nonlinear IBIS-AMI
models and protocol checks are not implemented in this workflow.

### Thermal

Solve object-node, 2D board-plate, and layered steady/transient board models with
explicit powers, heat paths and boundaries. Compare still-air, sealed-box, and
forced-air presets; inspect layer maps, temperature history, case/junction estimates and
board-aligned result overlays.

**Limit:** Cooling presets use specified heat-transfer coefficients instead of solving
airflow. Board grids omit detailed package geometry and conjugate heat transfer.

### Electromagnetics

Run EMerge on the exported antenna model and view its solved S-parameters, 2D cuts, and
sampled 3D radiation pattern in SPIKE. The EM workspace also offers separate openEMS and
internal screening workflows.

**Limit:** The SPIKE-to-EMerge adapter exports selected antenna and reference copper as
a two-layer model with one dielectric; other layers and components are omitted. The 3D
display interpolates and normalizes EMerge's solved angular samples, so its radius and
color show relative pattern shape rather than absolute gain.

### Visualization and reports

Orbit or inspect the board in 2D/3D, toggle geometry and result layers, probe returned
values, compare studies, and preview/export reports with units, run settings, warnings,
and result status.

**Limit:** Only quantities returned by the selected analysis can be plotted or probed.

### Automation

Use the local worker and CLI, extension manager, solver manager, and optional MCP
bridge. LM Studio and Ollama can use SPIKE tools to inspect projects, set up studies,
and run supported analyses.

**Limit:** Local models need a separately installed runtime and tool-capable model. MCP
access is limited to SPIKE's available tools.

### Circuit simulation choices

SPIKE's circuit workspace offers a built-in linear solver and two separate
circuit-engine paths: [ngspice](docs/SOLVER_STATUS.md) and the SPIKES backend.
Select the engine that matches the circuit model and check its availability in
the app. **SPIKES Studio is a separate program and is not part of the SPIKE
desktop release.** SPIKE uses only its backend engine for supported structured
circuit runs. The [circuit workflow](docs/USER_TASK_SEQUENCES.md) explains the
model and pin setup.

SPIKE reads KiCad boards directly. The bundled ODB++ extension can also import
board jobs; keep the original archive because the saved SPIKE project stores a
normalized copy. See [Importer Architecture](docs/IMPORTER_ARCHITECTURE.md),
[task sequences](docs/USER_TASK_SEQUENCES.md), and
[Solver Status](docs/SOLVER_STATUS.md) for details.

## Extensions: EMerge, openEMS, and board workflows

These are the eight packages under [`extensions/`](extensions/). Their Python
entry points run in separate processes. A bundled package supplies an adapter
or utility; optional third-party engines are installed separately. The
[Extension Manager and SDK](extension_sdk/README.md)
describe installation, permissions, and session trust for other local packages.

### [OpenEMS Suite](extensions/openems_suite/README.md)

Preflight, prepare, and run explicit-port high-frequency PI and SI interconnect sweeps;
import S-parameters and supported near-to-far-field outputs.

**Limit:** Requires separately installed openEMS/CSXCAD. Exactly one excited port per
run; no DC PI or thermal coupling. Unsupported PCB topology blocks a solve.

### [EMerge Suite](extensions/emerge_suite/README.md)

Build a selected-net two-layer PCB model for one/two-port S-parameters, 2D far-field
cuts, and sampled 3D radiation patterns, including a simple dielectric cover. The
pattern samples come from EMerge's field solve.

**Limit:** Requires a compatible separate EMerge Python runtime. The SPIKE adapter
limits the model to selected copper, aligned pad ports, rectangular bounds, one
dielectric and surface PEC; additional copper layers, components, many cutouts and
complex surroundings are omitted. The display normalizes the pattern to a relative peak.

### [Optycal Suite](extensions/optycal_suite/README.md)

Use a solved complex EMerge antenna pattern to study scattering from a placed STEP
structure and review fields and reports.

**Limit:** Requires a separate Optycal runtime. Structures are treated as PEC; the
source must be in the supported far-field regime. It does not model arbitrary dielectric
structures or feedback into the antenna solve.

### [ODB++ Import](docs/ODB_AND_HARNESS_EXTENSIONS.md)

Import a job archive/folder, choose a board step, inspect import quality, and open the
normalized board in SPIKE.

**Limit:** Experimental; unsupported symbols, compositing, and panel step repeats are
reported. Keep the original ODB++ export because a `.spike` snapshot is not the source
archive.

### [Harness Engineering](docs/ODB_AND_HARNESS_EXTENSIONS.md)

Import JSON/CSV/TSV connections, edit wire nets and lengths, validate connectivity,
compile an electrical fragment, bind an assembly, and export JSON.

**Limit:** Reads the listed connection-list formats; it does not import other harness
database formats.

### [MCAD Collaboration](docs/MCAD_EXPORT.md)

Preview a mechanical assembly and export named STEP, FreeCAD, BREP, and metadata
artifacts.

**Limit:** Requires installed FreeCAD. Geometry exchange only; inspect listed omissions
before export.

### [PWM Converter Analysis](extensions/converter-analysis/spike-extension.json)

Check converter-study readiness and create a versioned setup envelope.

**Limit:** Assistant and validator only: the extension does not contribute a converter
solver run or calculate efficiency and losses.

### [Net Inventory](extensions/net-inventory/spike-extension.json)

Example SDK utility that counts normalized nets and conductors and emits report data.

**Limit:** Inventory only; it performs no numerical analysis.

The [extension analysis contract](docs/EXTENSION_ANALYSIS_API.md) binds external
results to the current design and checks their format, source, units, and bounds;
these checks do not repeat an external engine's calculation. The SDK's
[field-data and mesh-field examples](extension_sdk/README.md) demonstrate
handoff and display, not supported solver integrations.

## Try the CLI

```powershell
.\spike.cmd --help
.\spike.cmd --output-format text inspect board.kicad_pcb
.\spike.cmd --output result.json analyze-dc board.kicad_pcb `
  --net VCC `
  --source 10,10,F.Cu,5 `
  --load 50,20,F.Cu,1
```

The CLI can also run saved requests and batches, inspect available solvers, and
generate reports. See the [CLI reference](docs/CLI.md).

## More information

- [Guides and tutorials](docs/README.md), including [thermal](docs/THERMAL_USER_GUIDE.md), [signal integrity](docs/SI_USER_GUIDE.md), and the [ESP32 example](examples/esp32/README.md)
- [Solver status and numerical limits](docs/SOLVER_STATUS.md)
- [Local LLM and MCP setup](docs/LOCAL_LLM_MCP.md) for LM Studio or Ollama
- [Contributing](CONTRIBUTING.md), [developer setup](docs/DEVELOPER_GUIDE.md), and [architecture](ARCHITECTURE.md)
- [Report a bug](https://github.com/wayri/SPIKE/issues/new?template=bug_report.yml) with a small reproducible example; review your report before sharing board data

## Help improve SPIKE

Tried the same board or circuit in another tool? We'd love to hear how the
results and workflow compare, including where SPIKE falls short. If you can,
share a small example you have permission to publish, the tool versions and
settings, and what differed. Comparisons with measurements are welcome too.
Matching geometry, materials, ports, and boundary conditions makes differences
easier to investigate. [Open an issue](https://github.com/wayri/SPIKE/issues)
with your observations; a brief usability note is just as welcome as a detailed
numerical comparison.

## License

Copyright 2026 Yawar B (wayri) and SPIKE contributors.
SPIKE-owned code and documentation are licensed under [Apache 2.0](LICENSE),
except where a file or directory specifies different terms.
Dependencies, external engines, and example boards retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).

## Acknowledgements

- The KiCad project and its contributors for the PCB ecosystem SPIKE works with.
- The Tauri, React, Three.js, Plotly.js, and Lucide projects behind the desktop interface and plots.
- The NumPy, SciPy, Shapely/GEOS, PyVista, wxPython, nanobind, Matplotlib, mplcursors, ReportLab, Apache Arrow, jsonschema, and Eigen projects used by the Python and native tooling.
- [ngspice](https://ngspice.sourceforge.io/) and its contributors for the optional circuit engine.
- [openEMS](https://openems.de/) and [CSXCAD](https://github.com/thliebig/CSXCAD) contributors for the optional electromagnetic solver and geometry tools.
- Robert Fennis and the [EMerge](https://github.com/FennisRobert/EMerge) contributors for the optional electromagnetic solver used in the ESP32 antenna example.
- Robert Fennis and the [Optycal](https://github.com/FennisRobert/Optycal) contributors for optional physical-optics studies.
- The [Gmsh](https://gmsh.info/) contributors for optional conforming volume meshing.
- The [OpenFOAM](https://www.openfoam.com/) community for the optional airflow solver.
- The [FreeCAD](https://www.freecad.org/) community for the optional mechanical CAD integration.
- Berkeley Lab and the Regents of the University of California for the Marble reference board, and uysan for the open `iot-esp-eth` ESP32 board used in the worked example.
- Contributors, testers, issue reporters, and documentation authors who help improve SPIKE.

If we have missed a credit, please open an issue or pull request. License and
source details for included examples and integrations are in the
[third-party notices](THIRD_PARTY_NOTICES.md).
