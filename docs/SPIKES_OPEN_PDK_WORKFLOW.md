<!-- SPDX-License-Identifier: Apache-2.0 -->
# Open-PDK circuit workflows and semiconductor roadmap

## Implemented experimental foundation

SPIKES ships discovery profiles, not copies of PDK model libraries, for
[SKY130](https://github.com/google/skywater-pdk),
[GF180MCU](https://github.com/google/gf180mcu-pdk), and
[IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK). Catalog sources were
reviewed on 2026-10-13; this does not freeze a PDK installation revision. The
Google GF180 repository is archived and its documentation describes preview
status; users must choose and pin an appropriate maintained distribution and
review its terms. An open licence is not silicon qualification.

The initial workflow uses **explicit ngspice**, whose compiled C kernels execute
device equations and circuit analyses. Python owns discovery, model-text
preparation, provenance and orchestration, not transistor numerical evaluation.
The owned C++ SPIKES kernel does not yet support every BSIM3/BSIM4/PSP/VBIC or
PDK dialect. No missing family is replaced by a generic MOSFET or resistor.

### 1. Install and pin a PDK separately

Use the PDK's documented installation/distribution tools. Record its exact
commit/build version and all licences. Raw upstream repositories and installed
`open_pdks` trees do not necessarily share filenames or library structure. The
default profiles target common installed paths; `--entry` overrides the
root-relative model entry without modifying the source PDK. A local root must
contain all selected textual model dependencies. Imports do not execute code.

```powershell
python -m python.spikes pdk catalog
python -m python.spikes pdk inspect --id sky130 --root C:/PDKs --entry sky130A/libs.tech/ngspice/sky130.lib.spice -o pdk-inventory.json
```

Inspection records sections, subcircuit names, ordered pins, parameter
declarations, dependencies, SHA-256 hashes, duplicate declarations, unresolved
references and root licence-file hashes. Unresolved models remain visible;
metadata discovery never marks a device executable or qualified. Different
corners may legitimately repeat a subcircuit name; the report does not rename
them or count helpers as additional real parts.

### 2. Configure the selected model/corner and temperature

Start with `examples/spikes/pdk/sky130_nfet_dc.json`. Edit its root/entry for the
actual installation and check its device, pin order and geometry units against
the installed PDK. This example is **not executed foundry-model evidence**.
PDK transistor wrappers often use their own dimension scaling; the adapter
never silently converts W/L to metres or assumes a valid operating range.

The config supplies `pdk_id`, `root`, optional `entry`, `corner`,
`temperature_c`, explicit `backend="ngspice"` and self-contained circuit text.
Circuit text must omit `.end`, additional `.include`/`.lib`, `.temp`, control
commands and model-loader commands. The adapter owns those boundaries.

### 3. Prepare and review the reproducible circuit

```powershell
python -m python.spikes pdk prepare --config examples/spikes/pdk/sky130_nfet_dc.json --deck nfet-tt.cir -o nfet-tt-prepared.json
```

Preparation selects exactly one corner section and recursively inlines its
textual includes. Paths must resolve inside the chosen root; escaping symlinks,
missing active dependencies, recursive same-file references, ambiguous sections
and compiled-model loaders are rejected. Other corners are not merged into the
selected corner. Relative paths are resolved against the declaring file.
Expansion is bounded by depth, file count and byte limits, and the final deck
must pass the existing ngspice netlist safety policy. Local PDK files are never
modified. Deck exports refuse overwrites.

The prepared report retains exact dependency hashes, resolved configuration,
self-contained source and `approval_sha256`. If any executed model text,
circuit, corner or temperature changes, the approval digest changes. Prepared
status is not a solver result. Do not redistribute exported model text without
reviewing all relevant licences and required notices.

### 4. Explicitly approve and execute

```powershell
python -m python.spikes pdk run --config examples/spikes/pdk/sky130_nfet_dc.json --approve-models-sha256 DIGEST_FROM_PREPARED_REPORT -o nfet-tt-result.json
```

Execution uses the existing process-isolated ngspice adapter, bounded runtime
and raw-result admission. It does not use user `.spiceinit` or silently switch
engines. Results retain run digest, PDK configuration and dependency provenance.
Trusted model review is still required; process isolation and syntax checks are
not a filesystem/network hostile-code sandbox. OSDI/Verilog-A model loading,
including IHP configurations that require it, is not implemented in this
self-contained PDK route and is explicitly rejected rather than substituted.

## Validation and current limitations

Tests use original synthetic libraries, never falsely labelled foundry data.
They cover corner selection, hashes, dependency cycles/escape/missing files,
unsafe directives, approval mutation, CLI export and an actual ngspice NMOS
DC sweep. No installed SKY130/GF180/IHP device or corner is yet qualified here.
No PDK was downloaded, bundled or installed by this change. There is no new
PDK GUI, layout editor, DRC/LVS, extraction engine or native full-PDK binding.

## End-to-end circuit/IC completion gates

1. Pin installed PDK releases and import reviewed symbols, pin roles, geometry,
   model names, valid bias/temperature envelopes and evidence into the library.
2. Qualify N/P MOS, diodes, BJTs/HBTs, resistors, capacitors and RF structures
   per process: I-V/C-V, gm/gds, charge, noise and temperature against published
   PDK oracles. Preserve binning and all explicit substrate/well terminals.
3. Run corners/PVT and supported statistical mismatch models; do not treat a
   deterministic corner as Monte Carlo. Add inverter, ring oscillator, current
   mirror, differential pair, op-amp and mixed-signal examples with acceptance
   thresholds and reproducible timing/noise measurements.
4. Integrate layout/extracted-netlist tools through separate adapters with DRC,
   LVS and parasitic-extraction provenance; compare pre/post-layout results.
   Simulation acceptance is not fabrication sign-off.
5. Add owned native compact-model execution only after explicit compatibility
   and equal-model regression evidence. Keep ngspice routing visible meanwhile.

## TCAD/process simulation is a separate native subsystem

A PDK provides compact circuit models and process design rules; importing it
does not create a semiconductor field solver. Both tracks were explicitly
requested. The first [native 1D equilibrium kernel](SPIKES_TCAD_EQUILIBRIUM.md)
is now implemented separately. Full device TCAD still requires
geometry/mesh/material specification, electrostatic
Poisson and carrier continuity/transport, contacts and interface conditions,
recombination/traps, thermal coupling, convergence and mesh-refinement tests,
and material-specific parameters. Process TCAD adds fabrication-step/doping
evolution models. Advanced heterostructure/diamond/quantum models need further
equations and measured evidence. They are not implemented or implied by the
current equilibrium kernel, lumped I/Q builder or PDK workflow.
