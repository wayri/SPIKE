<!-- SPDX-License-Identifier: Apache-2.0 -->

# SPIKE examples

Use the [current UI quick start](../docs/UI_QUICKSTART.md) for navigation and the
[analysis gallery](../docs/ANALYSIS_GALLERY.md) for plots and interpretation.
Examples exercise specific models with explicit inputs. They do not establish
accuracy for arbitrary boards, assemblies or materials. Review each example's
prerequisites, units, assumptions, runtime status and output diagnostics.

## Reproducible analytics

The [analysis gallery bundle](analysis_gallery/README.md) generates eight visual
examples with result data and provenance. It distinguishes computed model
outputs from UI screenshots. Run its documented command from the repository
root; a compatible native runtime is required for native cases.

| Area | Start here | Inspect |
| --- | --- | --- |
| PI | [Dielectric/PDN and feedback scripts](pdn_dielectric_thermal/) and [PI/SI tutorial](tutorial_pi_si/README.md) | Admittance/impedance, voltage drop, source/load balance, return assumptions and losses. |
| SI | [RLGC line fields](rlgc_line_fields/) and [high-speed SI cases](high_speed_si/README.md) | Terminated response, reflection, transmission, crosstalk or time traces available in that model; ports and frequency coverage. |
| EM | [Entity-port patch](em/run_entity_port_patch.py) and [ESP32 antenna example](esp32/README.md) | Returned E/H or far-field samples, normalization, ports, material/mesh admission and external engine prerequisites. |
| Thermal | [Thermal requests](thermal/README.md) and [retained assembly fields](assembly_field/README.md) | Temperature with units, boundary heat flows, energy residuals and thermal contacts. |
| Hybrid multi-solve | [Co-simulation](cosimulation/README.md), [electrothermal example](assembly_field/run_electrothermal.py) | Coupling order, exchanged quantities, time-grid/relaxation assumptions, iteration convergence and balance. |
| CFD | [Internal airflow](assembly_field/run_internal_airflow.py) and [thermal/flow requests](thermal/README.md) | Velocity/pressure, residuals, mass balance, admitted laminar geometry and boundary conditions. |
| CHT | [Laminar channel request](thermal/laminar_channel_cht_request.json) and [SU2 CHT guide](../docs/SU2_CHT.md) | Solid/fluid temperatures, transferred heat and energy closure; reduced/native channel and external adapters are distinct. |
| Multiboard | [Curated board assemblies](multiboard/README.md) and [interboard harness](high_speed_si/harness/README.md) | Instance IDs, connector mapping, supply/return topology, reduced PI/SI/Thermal results and interconnect parameters. |

## Board and circuit walkthroughs

- [ESP32](esp32/README.md): public board source, historical viewport captures and
  an explicitly simplified antenna example; preserve its license/provenance.
- [SPIKES Studio tutorials](spikes/studio_tutorials/): circuit examples for the
  separate solver suite. Check the chosen engine and adapter before assuming a
  Studio feature is available inside SPIKE desktop.
- [Compiled board](compiled_board/): compiler/run workflow with explicit models.
- [EM machines](em_machines/README.md): bounded magnetic machine examples with
  their own excitation, geometry and validation limits.

## Before comparing results

Retain the request, source revision, engine version, mesh/discretization, units,
boundaries and diagnostics alongside each result. Change one input at a time.
A plot should identify its quantity and scale; never label a normalized radiation
pattern as absolute gain or a lumped thermal network as a spatial temperature
field. Mesh, time-step and coupling convergence are separate checks. See
[solver status](../docs/SOLVER_STATUS.md) and
[solver mathematics](../docs/SOLVER_MATHEMATICS.md).
