# SPIKE promo example projects

This pack prepares real existing SPIKE/Studio projects for manual UI demonstration. It does not add solver capabilities, UI controls or hardware qualification. Native package readback and numerical execution are checked; desktop interaction/recording is a separate acceptance step.

The generated sharing pack is `output/promo-showcase-20261023/READY_TO_OPEN/`, with `START_HERE.md` as the recording and import index. `SPIKE-promo-projects-20261023.zip` contains the complete portable pack, including source/license evidence.

The [restrained propulsion-pod build](propulsion_pod/START_HERE.md) now adds an
executed compiled-C controller / reciprocal P1 FEM / hover-BEM feedback loop,
a native assembly with retained results/views, and exact KiCad companions.
The synthetic two-phase/BEM scope is distinct from real VESC firmware and
blade-resolved CFD. Earlier independent thermal and circuit studies remain
separate. Its archive is under `output/promo-propulsion-pod-20261023/`.

## Build/reproduce in this checkout

1. `.venv/Scripts/python.exe examples/promo_showcase/boards/build.py`
2. `.venv/Scripts/python.exe examples/promo_showcase/electrical/verify.py`
3. `.venv/Scripts/python.exe examples/promo_showcase/electrical/package_studies.py`
4. `.venv/Scripts/python.exe examples/promo_showcase/electrical/package_arduino.py`
5. `.venv/Scripts/python.exe examples/promo_showcase/thermal_flow/build_thermal_flow.py`
6. `.venv/Scripts/python.exe examples/promo_showcase/thermal_flow/verify_outputs.py`
7. `.venv/Scripts/python.exe examples/promo_showcase/thermal_flow/run_flow.py`
8. `node examples/promo_showcase/build_field_imports.mjs`
9. `.venv/Scripts/python.exe examples/promo_showcase/assemble.py`

Existing native circuit/CFD kernels, C compiler and the configured Gmsh/OCC runtime are prerequisites where used. No runtime or compiler binaries are distributed. The Arduino builder uses already cached pinned source archives and projects; it does not download CAD or grant third-party rights.

## Readiness

- Native projects: original EBrake layered board transients, original PCB/hollow-case contact transients, Arduino reduced PI/SI, five magnetic/motor workspaces, Studio controller/dashboard.
- Supported input decks: three Studio circuit transients.
- Native Fields imports: actual native cavity fields, bounded channel CHT temperatures, and returned solenoid A_z/temperature history. They are presentation datasets, not native analysis setup importers. Frame timestamps are unchanged.
- Manual setup: fixed native CFD benchmark with supplied settings.
- API rerun only: exact bounded channel CHT owner; imported field data can be shown in the main UI.
- Not supplied as working scenes: PCB spiral air/core field model, geometry-resolved human-finger touch sensor, arbitrary case CFD/CHT, controller-driven motor FEM. Existing linear electromagnet comparisons and separately driven motor fields do not establish these capabilities.

## Licensing

Original SPIKE code, EBrake board, authored generic case/board geometry and simulation examples use Apache-2.0 with the included notices. Arduino CAD/derived geometry is segregated under its original CC BY-SA 4.0 terms, with full source archives, original notices, source hashes and conversion attribution. Do not apply Apache-2.0 to that CAD. Raspberry Pi and White Rabbit candidates with unresolved redistribution review are excluded; no unreviewed third-party component models, logos, audio or stock footage are added.

The numerical evidence records are existing repository documents: `docs/NUMERICAL_METHOD_EVIDENCE.md`, `docs/ASSEMBLY_THERMAL_TRANSIENT.md`, `docs/THERMAL_USER_GUIDE.md`, `docs/MAGNETIC_MACHINE_STUDIES.md`, `docs/MAGNETIC_THERMAL.md`, `docs/EM_MACHINES.md`, `docs/ENCLOSURE_FLOW_RESEARCH.md` and `docs/INTERNAL_AIRFLOW.md`. Their exact source hashes and relevant solver hashes are retained in the assembled pack. Parameterized examples reuse established methods; no new governing laws are introduced.
# Source companions

The proposed maximum-scope integration target, present capability boundaries
and completion gates are in [FLAGSHIP_SYSTEM.md](FLAGSHIP_SYSTEM.md).

Every PCB-based `.spike` example includes exact copies of its embedded KiCad
board inputs beside the project. Portable native project, schematic and local
library folders are under the adjacent `KiCad/<board-name>/` directories so
multiple boards do not collide on library-table names. Per-project `.sources.json`
files identify the sources, licenses, hashes and available schematics. Board-only
inputs get explicitly labelled empty project launchers; generated solid/machine
examples declare that no KiCad input was used. No source schematic is invented.

`colocate_kicad_sources.py` enforces this rule in all five promo packagers and
rejects unknown or conflicting source bytes. `KICAD_SOURCE_INVENTORY.json` records
the checked examples. New source fixtures must be added to its explicit registry.

