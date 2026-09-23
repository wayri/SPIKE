# MODULAR-BUS-NIB PI Analysis

Date: 2026-07-30

## Fixture

- Source: `C:\Users\yawar\Documents\Github\TEST\MODULAR-BUS-NIB\MODULAR-BUS-NIB.kicad_pcb`
- Application: 22-60 V input, selectable 12/5/3.3 V, 120 W buck converter
- Parsed geometry: 46 nets, 404 tracks, 617 vias, 260 pads, 192 zone
  polygons, 92 component groups, and 17 stackup entries
- Copper stack: six layers; 70 um outer copper and 35 um inner copper
- Imported dielectric properties: FR4 relative permittivity 4.5 and loss
  tangent 0.02
- Design validation: valid, with no importer errors or warnings

The source KiCad project was read-only during this analysis.

## DCIR Setup

Net: `/12Vout`

- 12 V source: R19 pad 3 at `(160.132, 81.660)` on `F.Cu`
- 10 A total load, divided equally across:
  - J14 pad 2 at `(165.025, 78.200)`
  - J20 pad 2 at `(165.025, 82.275)`
  - J15 pad 2 at `(165.025, 86.350)`
- Included geometry: 33 tracks, 7 zones, 76 vias, and 22 pads
- Via plating assumption: 0.025 mm where fabrication data was unavailable

Preflight passed with zero errors: 138 selected copper objects, 6,399
preview cells, and 8,477 estimated unknowns at the 1.0 mm preview setting.

## DCIR Results

| Mesh target | Nodes | Branches | Maximum drop | Copper loss |
| --- | ---: | ---: | ---: | ---: |
| 1.000 mm | 782 | 2,748 | 1.292 mV | 12.433 mW |
| 0.500 mm | 1,137 | 7,340 | 1.147 mV | 10.934 mW |
| 0.250 mm | 2,443 | 24,886 | 1.078 mV | 10.259 mW |
| 0.125 mm | 7,852 | 98,325 | 0.988 mV | 9.409 mW |

The 0.125 mm result differs from the 0.25 mm result by 9.0%. The sequence is
not converged to a sign-off threshold, so these values are `Approximate`.

### Pinned board convergence rerun

The repository copy at `app/public/demo/MODULAR-BUS-NIB.kicad_pcb` (SHA-256
`37639b58aa75c11265ecf7867c2d358942b70c9e0011a10da99f524e767c2f07`)
was imported and solved with the request's `/12Vout` terminals. The four-level
study used a 4 GiB solver memory budget; the default 2 GiB budget rejected the
fourth mesh at its 85,196-branch admission limit. The 4 GiB budget changes
resource admission only. The repeatable command is
`.venv/Scripts/python.exe -m scripts.verify_modular_bus_pi_convergence --output docs/validation/modular-bus-nib-pinned-dc-convergence.json`.

| Target / zone cell | Nodes / branches | Maximum load drop | Copper loss | p95 current density |
| --- | ---: | ---: | ---: | ---: |
| 2.0 / 1.0 mm | 3,126 / 4,909 | 2.84367 mV | 27.66355 mW | 4.56305 A/mm2 |
| 1.0 / 0.5 mm | 5,402 / 9,629 | 1.72457 mV | 15.42297 mW | 5.21345 A/mm2 |
| 0.5 / 0.25 mm | 13,636 / 26,245 | 1.75181 mV | 14.50160 mW | 5.15988 A/mm2 |
| 0.25 / 0.125 mm | 45,688 / 91,360 | 1.57518 mV | 14.94111 mW | 5.23818 A/mm2 |

The finest pair changes maximum load drop by 10.08% against a 3% limit.
Copper loss changes by 2.94% against a 5% limit, but rises after falling on
the preceding meshes. The run is therefore `failed_to_converge` and cannot
sign off. [Compact evidence](modular-bus-nib-pinned-dc-convergence.json) records
the pinned input hashes and per-level metrics; the separate
[2 GiB attempt](modular-bus-nib-pinned-dc-convergence-2gb.json) records the
resource rejection. These terminal coordinates are not yet bound to exact pad
IDs in the request, so a refinement-dependent terminal snap remains a possible
cause of the voltage-drop jump and requires a controlled anchored rerun.

The reported peak current density of 95.56 A/mm2 is at the idealized R19 source
injection element. This is a terminal singularity/model artifact and must not be
reported as a physical board hotspot until contact area and package geometry are
modeled.

## ACIR Setup And Results

The current PEEC adapter performs series R/L path extraction with skin-effect
resistance. It includes routed copper, zones, pads, and plated via barrels.

| Path | Mesh | Nodes / filaments | R at 1 kHz | Partial L | Magnitude at 30 MHz |
| --- | ---: | ---: | ---: | ---: | ---: |
| `/Vin_f`, J1 to F1.1 | 2.0 mm | 305 / 628 | 92.09 uohm | 2.113 nH | 0.3513 ohm |
| `/12Vout`, R19.3 to J20.2 | 5.0 mm | 577 / 1,163 | 235.89 uohm | 6.327 nH | 1.1884 ohm |

The 12 V extraction uses a coarse mesh to remain below the dense PEEC matrix
safety limit. The high-frequency values are exploratory, not sign-off data.

This is not yet a complete PDN impedance result. Capacitance matrices,
dielectric loss, conductor surface roughness, proximity effect, component and
package models, source impedance, and decoupling models are not included.
Resonance, anti-resonance, target impedance, and capacitor-placement conclusions
must wait for those models.

## Features This Board Can Test Now

- KiCad import, normalized DesignIR, layer stack, copper thickness, and
  dielectric extraction
- Import-quality and pre-solve validation
- Hybrid trace, zone, pad, through-hole, and via-barrel meshing
- 2D/3D mesh preview and source-geometry provenance
- Multi-sink DCIR, voltage drop, copper loss, branch current, and current-density
  fields
- Explicit source/load terminal placement and terminal snapping
- Probe mapping and probe-table result contracts
- Series AC R/L extraction on `/Vin_f`, `/12Vout`, `Vin`, and `SW_node`
- Batch CLI runs and machine-readable result bundles
- HTML report generation and numerical revision comparisons
- Layer/net isolation and solver-field visualization using the generated mesh and
  field envelopes
- Local 3D model resolution against the STEP assets included with the project

## High-Value Follow-Up Tests

1. Add source/contact/package resistance and realistic connector current sharing
   to remove the ideal-terminal current-density singularity.
2. Run adaptive mesh refinement around narrow necks, thermal spokes, via arrays,
   shunts, and terminal contacts until voltage drop and loss converge.
3. Add capacitance and dielectric-loss extraction, then model the input and
   output capacitor banks for full PDN impedance.
4. Extract the `SW_node` electric-field coupling into current-sense and control
   nets. This requires the capacitance matrix and proximity-aware conductor
   model.
5. Compare ISNS+ and ISNS- Kelvin paths for R/L symmetry and common-mode
   susceptibility.
6. Add MOSFET, inductor, capacitor, shunt, connector, and controller models for
   closed-loop ngspice co-simulation.
7. Use the 120 W operating point for board electrothermal and airflow validation
   after the OpenFOAM workflow is connected to solver losses.
8. Compare available board revisions to exercise geometry, result, and report
   regression workflows.

## Generated Artifacts

- `modular-bus-nib-12vout-dcir-request.json`: reproducible DC request
- `modular-bus-nib-12vout-dcir*.json`: DC mesh-refinement results
- `modular-bus-nib-vinf-acir.json`: input-filter AC extraction
- `modular-bus-nib-12vout-acir.json`: output-path AC extraction
- `modular-bus-nib-12vout-dcir.html`: compact DC report
- `modular-bus-nib-vinf-acir.html`: compact input AC report
- `modular-bus-nib-12vout-acir.html`: compact output AC report

## Accuracy Status

- Import and geometry counts: `Validated` by parser and regression tests
- DC and AC execution workflows: `Validated` for deterministic completion
- DC numerical result on this board: `Approximate`, mesh convergence not met
- AC series R/L result: `Approximate`, experimental PEEC extraction
- Full PDN impedance, capacitor optimization, crosstalk, fields, and SI:
  `Unsupported` by the current solver and must not be inferred from these runs
