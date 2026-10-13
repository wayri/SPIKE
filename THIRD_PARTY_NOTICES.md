# Third-party notices and example sources

SPIKE uses open-source libraries and can connect to separately installed tools. Their own license files govern those components. This page also records the sources of boards and images shown in SPIKE documentation.

SPIKE's Apache-2.0 license covers its own code; it does not relicense these
components. Bundled dependencies retain their license and notice files.
Optional solver runtimes are obtained separately from their upstream projects.
An adapter's license and the connected engine's license are separate; consult
the license for the version you install or redistribute.

## Software and integrations

| Project | How SPIKE uses it | Source and terms |
| --- | --- | --- |
| [SU2](https://su2code.github.io/) | Optional separately installed CFD reference executable through the original Python process adapter | Upstream [download and licensing information](https://su2code.github.io/docs/Download/) identifies LGPL-2.1. Development benchmarks use the native Windows v8.5.0 runtime; no engine source, upstream meshes/examples or engine binaries are bundled with SPIKE. Retain the runtime's notices when redistributing it separately. |
| KiCad | PCB import and example board files | [KiCad project](https://www.kicad.org/); KiCad and board authors retain their own notices. |
| Tauri, React, Three.js, Lucide, and Plotly.js | Desktop interface, 3D view, icons, and plots | Versions are recorded in `app/package-lock.json` and `app/src-tauri/Cargo.lock`. Plotly.js is MIT-licensed; consult each package's included license. |
| NumPy, SciPy, PyVista, wxPython, nanobind, Matplotlib, mplcursors, ReportLab, Apache Arrow/PyArrow, jsonschema, and Eigen | Python worker, native kernels, visualization, and reports | Versions are recorded in the Python requirements and native build files. Consult each installed package's license. |
| Shapely and GEOS | Geometry handling | Shapely is BSD 3-Clause; its bundled GEOS library is identified under LGPL-2.1 in the Windows wheel metadata. |
| [Gmsh](https://gmsh.info/) | Optional, separately installed 4.15.2 OCC process for normalized PCB and retained assembly volume meshes | Runtime terms are in the [upstream manual](https://gmsh.info/doc/texinfo/gmsh.html#Copying-conditions). SPIKE adds original typed compiler/sizing code, not Gmsh source. Only entry artifacts are hash-admitted; this development integration is not redistribution-approved or bundled. |
| [CalculiX](https://www.calculix.de/) | Optional separately installed CrunchiX thermal executable through the original Apache-2.0 adapter in `extensions/calculix_suite/` | Upstream GNU GPL v2 terms remain separate. SPIKE bundles no CalculiX source, binaries or upstream examples; local Windows testing used MSYS2 CCX 2.23. |
| FreeCAD SPIKE Workbench | Optional geometry exchange | The workbench under `integrations/freecad/SPIKEWorkbench/` has its own MIT license. FreeCAD is a separate project. |
| Robert Fennis's [EMerge](https://github.com/FennisRobert/EMerge) | Optional antenna and EM solver used through `extensions/emerge_suite/` | Separately installed; [EMerge's license](https://github.com/FennisRobert/EMerge/blob/main/LICENSE) identifies GPL-2.0-or-later Gmsh-derived components and a CC0 materials database. SPIKE does not include the EMerge solver runtime. The optional demonstration source bundle under examples/upstream-emerge is redistributed with its complete upstream license and retained corresponding source, pinned at commit75e6e98170a6628688593f917c1bb63b52578d02; this separately licensed bundle is not relicensed as Apache-2.0. |
| Robert Fennis's [EMCAD](https://pypi.org/project/emcad/) | Optional public polygon union API for EMerge selected copper, isolated in its runtime interpreter | Separately installed, MIT; SPIKE bundles no upstream code or data. |
| [PyGerber](https://pypi.org/project/pygerber/) | Optional Gerber dependency in the selected EMerge runtime; SPIKE calls EMerge's public native loader | Separately installed, MIT; SPIKE bundles no PyGerber source, artwork or runtime. |
| Robert Fennis's [Optycal](https://github.com/FennisRobert/Optycal) | Optional separately installed physical-optics engine through `extensions/optycal_suite/` | Optycal 0.2.0 is MIT-licensed and beta. SPIKE bundles no upstream runtime or example code. |
| [ngspice](https://ngspice.sourceforge.io/), [openEMS/CSXCAD](https://openems.de/), and [OpenFOAM](https://www.openfoam.com/) | Optional circuit, EM, and airflow engines | Separately installed; each project supplies its own license. SPIKE does not include these runtimes. |
| [PALACE](https://github.com/awslabs/palace) | Optional separately installed electromagnetic runtime through `extensions/palace_suite/` | Original Apache-2.0 SPIKE adapter; upstream runtime and dependencies retain their own [license](https://github.com/awslabs/palace/blob/main/LICENSE). No upstream binaries, examples or source are bundled. |
| [Xyce](https://github.com/Xyce/Xyce) | Optional separately installed circuit runtime through `extensions/xyce_suite/` | Original Apache-2.0 SPIKE adapter; consult upstream license and notices for the installed runtime. No upstream binaries, device libraries or examples are bundled. |
| sparseLizard | Optional native adapter | `integrations/sparselizard-native/LICENSE` identifies the adapter as GPL-2.0-or-later; the upstream runtime has its own GPL notices. |

## Boards and documentation images

- **ESP32 example:** The `iot-esp-eth` board by uysan is included under CERN-OHL-P-2.0. Its source, license, and upstream revision are recorded in [examples/esp32/source/LICENSE.md](examples/esp32/source/LICENSE.md) and the [worked example](examples/esp32/README.md). Upstream reference images and measurements are labeled separately from SPIKE results.
- **Marble reference board:** Berkeley Lab's Marble v1.4.4 board and documentation are credited to the Regents of the University of California through Lawrence Berkeley National Laboratory. The upstream documentation states CERN OHL v1.2 and a U.S. Government rights notice. The board-documentation image and front-copper SVG in `app/public/help/` come from the pinned source recorded in [Help maintenance](docs/HELP_MAINTENANCE.md). SPIKE interface captures showing Marble are labeled as captures; the report preview says analysis was not run.

If a source or credit is missing, please [open an issue](https://github.com/wayri/SPIKE-Main/issues). Preserve the original license and attribution when reusing third-party material.

## Gamma0.3.11 redistribution scope

Gamma0.3.11 excludes copied independent project archives, local model collections, downloaded HDL/solver runtimes and private/local-use board data from its source snapshot and installer. The source-only EMerge example bundle retains its upstream license in examples/upstream-emerge/source/LICENSE and its hash-bound manifest. Optional engines are installed separately. The original first-party SPIKES Studio source inherits the project Apache-2.0 boundary; its portable LICENSE copy is included. No Pocket KiVi source or assets are included. Production component notice approvals remain pending; this unsigned Gamma distribution makes no production/legal-review approval claim.

Gamma distributions retain dependency notice texts and their SHA-256 index under legal/licenses/runtime-notices. The index includes build and other-platform dependencies and does not assert that every listed component is bundled or that pending production review is approved. Exact worker file manifests identify the runtime payload.
