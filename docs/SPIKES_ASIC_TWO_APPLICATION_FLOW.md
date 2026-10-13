<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKES + KLayout: two-application IC/ASIC workflow

## Agreed product boundary

The user-facing design/layout applications are **SPIKES and KLayout only**.
The user explicitly permits approved engines bundled inside SPIKES. Synthesis,
static timing, physical implementation, extraction and simulation may therefore
use licensed headless C/C++ backends managed by SPIKES; users should not have to
operate their consoles or additional design GUIs. This is the target workflow,
not a claim that every backend is already integrated or qualified.

SPIKES remains Qt-free. KLayout is a separately selected application/process;
its GUI/runtime is not embedded in or imported into the SPIKES interpreter.
PDK installation, engine distribution rights, foundry access and fabrication
services remain explicit dependencies even when their tooling is managed by
the two applications. Commercial distribution requires review of complete
backend dependency licences, not only a repository's headline licence.

## Ownership and required exchange

| Work | User interface | Required inputs/results |
| --- | --- | --- |
| Analog/transistor design | SPIKES schematic/model tools | PDK pins/models, hierarchy, testbenches, operating envelopes |
| Digital design/verification | SPIKES HDL suite | RTL, testbenches, assertions, constraints, coverage/equivalence |
| Technology synthesis | SPIKES-managed backend | Liberty, mapped netlist, timing/area/constraint reports |
| Physical implementation | SPIKES-managed backend; KLayout review/edit | Technology/cell LEF, floorplan, placement, power network, CTS, routed DEF |
| Custom cells/analog layout | KLayout | PCells, layer maps, wells/substrate, pins, GDS/OASIS |
| DRC/LVS/antenna/density | SPIKES manager + KLayout review | Exact PDK runsets, executed check coverage, violations/waivers, correspondence |
| Parasitic extraction | SPIKES-managed qualified backend | Process stack and extraction corner; distributed RC/coupling, SPEF/DSPF/extracted SPICE |
| Post-layout closure | SPIKES | STA/setup/hold, simulation/noise/corners, IR/EM/power and recorded margins |
| Stream-out/release | SPIKES manager + KLayout | Exact final layout/netlists, hashes, all reviewed closure evidence |

Manual analog layout and automated digital layout are both supported targets.
Mixed-signal preflight additionally requires explicit analog macro LEF, GDS and
model views; it does not infer macro timing or electrical behavior from shapes.
There must be no requirement to rewrite an analog design as RTL. Hierarchical
pin identity, geometry units and model geometry scaling must survive every
handoff. LVS reference-netlist format and simulation model wrappers may differ;
translation must be explicit, reviewed and loss-reported.

## Implemented foundation in this pass

- `python/spikes/asic_project.py` and `.spkasic` contract track exact source,
  constraints, library/layout artifacts, PDK revision labels, runsets and engine
  identities. The preflight hashes actual files and marks missing/changed
  resources and unexecuted predecessor stages as blockers. It never presents
  file presence or a successful preflight as design completion or sign-off.
- `python/spikes/klayout_bridge.py` invokes the installed KLayout in headless
  batch mode with a checked-in original probe. It inspects real layout cells,
  hierarchy/transforms, layers, shape counts, DBU and micrometre bounds; it
  retains executable/layout/script hashes and rejects mutation. SPIKES imports
  no Qt module. This bridge is read-only inspection, **not DRC/LVS/PEX**.
- Existing SPIKES HDL tools invoke actual compilers/Yosys, and the PDK service
  can explicitly prepare/run approved ngspice model decks. Those capabilities
  do not yet provide technology-mapped ASIC physical closure or real PDK
  qualification. The native device-field kernel is a separate TCAD track.

```powershell
python -m python.spikes asic-plan examples/spikes/asic/minimal_project.spkasic
python -m python.spikes layout-inspect design.gds --klayout C:/Users/yawar/AppData/Roaming/KLayout/klayout_app.exe -o layout-inspection.json
```

The initial project intentionally has no fabricated models, layouts, engines
or runsets: every unfinished stage is blocked. Fill it with hashes of actual
files. Artifacts and runset/licence records are root-relative and root-contained;
engine paths may be explicitly external. `asic-plan` never executes supplied
runsets. Output cannot replace input projects/artifacts/engines/runsets/licence
records. Inspection stages outputs temporarily and leaves the original layout
unchanged. A separate process is not a hostile-file security sandbox.

The native KLayout test and CLI smoke used the installed version 0.30.5.
See [actual evidence and limitations](validation/SPIKES_ASIC_KLAYOUT_20261013.md).
Layout parsing happens before geometry-limit checks; input/report/output bounds
do not constitute a hard parser-memory guarantee.

## PEX is a separate deliverable, not an LVS checkbox

KLayout can extract device connectivity and write hierarchical SPICE/L2N/LVS
results; see [its official netlist I/O documentation](https://klayout.org/downloads/master/doc-qt4/manual/lvs_io.html).
Its release notes describe experimental resistance-extraction support, not
universal complete RC sign-off extraction:
[KLayout development notes](https://www.klayout.de/development.html).
We must not label pure connectivity or a bounding-box approximation as PEX.

The extraction integration must retain layer thickness/resistivity, via/contact
resistance, dielectric stack, lateral/vertical/fringing coupling, explicit
ground/reference treatment, corners and temperature dependence. Analog/RF
designs additionally need supported inductance/substrate/frequency effects or
explicit exclusions. Device-internal charge and interconnect parasitics must
not be double counted. Exported parasitics need original net identifiers and
provenance, with reduction error and validity bounds before acceleration is
allowed. Timing and simulation measurements use the original extracted model,
not a visually simplified schematic.

## Backend selection and licensing gates

Yosys is an existing candidate for managed synthesis under its
[ISC licence](https://github.com/YosysHQ/yosys/blob/main/COPYING), with additional
component/frontend terms still requiring review. OpenROAD is a candidate for
managed physical design; its main repository is
[BSD-3-Clause](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/LICENSE),
but its build includes other components such as OpenSTA. OpenSTA's
[GPL-3.0 terms](https://github.com/The-OpenROAD-Project/OpenSTA) must be reviewed
for the actual distributed binary. No such engines or third-party source were
downloaded, copied, approved for redistribution or newly bundled by this pass.
Process boundaries do not erase licence obligations. Every approved backend
must record version, platform, exact hashes, notices/source obligations and
qualified capabilities. Windows/Linux execution and offline package tests
remain mandatory; a Linux-only engine cannot be silently advertised as native
Windows capability.

## Completion sequence and release gates

1. Freeze one open-PDK revision with transistor/standard-cell models, Liberty,
   LEF/GDS, layer maps and reviewed KLayout rule decks. Qualify device/corner
   simulation and model-to-layout pin/geometry mappings.
2. Implement a SPIKES IC/ASIC project manager: analog/digital workspaces,
   constraints, stage controls, artifact browser and KLayout cross-probing.
3. Bind pinned synthesis and physical-design backends, implement staged
   execution/cancellation/checkpoints and provenance. Qualify mapped RTL,
   floorplan/place/CTS/route and equivalence rather than just generic synthesis.
4. Execute real PDK DRC/LVS/antenna/density rules and parse their semantic
   outcomes. Exit code zero or an empty report alone is not rule-coverage proof.
5. Integrate and qualify distributed parasitic extraction and post-layout
   timing/simulation, then IR/EM, power, ESD/ERC and relevant reliability checks.
6. Demonstrate an analog inverter/current mirror and a small digital counter
   from design to layout and extracted simulation through only the two visible
   applications. Scale to mixed-signal blocks and larger ASICs with reproducible
   runtime/memory/accuracy evidence.
7. Package approved backends and PDK libraries with offline install/upgrade/
   rollback tests and notices. Release readiness requires all mandatory
   executed evidence, knowledgeable review and applicable foundry checks.

Full end-to-end ASIC design is **not ready yet**. Native layout inspection and
project preflight are useful foundations, not a place/router, PEX engine or
sign-off suite. Physical fabrication/tape-out approval remains process/foundry
specific, and TCAD is not a substitute for those checks.
