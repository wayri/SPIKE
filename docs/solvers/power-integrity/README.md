<!-- SPDX-License-Identifier: Apache-2.0 -->
# Power integrity

[All solver families](../README.md) · [Methods](../../SOLVER_MATHEMATICS.md) ·
[Current status](../../SOLVER_STATUS.md)


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Resistive graphs and authored conductors

| Subgroup | Code owner | Method and boundary | Completion state |
| --- | --- | --- | --- |
| Routed tracks, zones, pads and vias | [Hybrid DC](../../../python/spike_core/solvers/power_integrity/dc/hybrid_dc_solver.py) | Branch Ohm law and reduced graph Laplacian; zone spreading uses an admitted finite-volume representation. Terminal/contact geometry matters. | Partial / experimental within stated scope |
| Harness DC | [Harness workflow](../../HARNESS_PI.md) | Explicit pin/wire/contact network; declared lengths and cross-sections, not inferred physical bonds. | Partial / experimental within stated scope |
| Multinet path composition and engineering screening | [PI setup](../../PI_PATH_ANALYSIS.md), [engineering tools](../../PI_ENGINEERING_TOOLS.md) | Reviewed paths, sources/returns and supplied limits; screening is not field or hardware qualification. | Partial / experimental within stated scope |

Set up sources, loads, physical returns, materials and contacts in PI or the
documented harness workflow. A shared net name does not establish a physical bond.
See [DC assumptions and workflow](../../DC_SOLVER.md) and
[analytical benchmark owner](../../../python/spike_core/solvers/power_integrity/dc/benchmarks.py).

## Conservative spatial DC and finite contacts

| Subgroup | Code owner | Method and working state | Completion state |
| --- | --- | --- | --- |
| Triangular sheet reference | [Conforming DC](../../../python/spike_core/solvers/power_integrity/peec/peec_conforming_dc.py) | Mixed RT0 signed edge flux/cell potential solve; local KCL and energy checks. Experimental, separate from production AC extraction. | Partial / experimental within stated scope |
| Rectangular land transition | [Land transition](../../../python/spike_core/solvers/power_integrity/dc/dc_land_transition.py) | Explicit finite face contacts and conservative mixed volume fields. | Partial / experimental within stated scope |
| Annular contacts/stacks | [Annular land](../../../python/spike_core/solvers/power_integrity/dc/dc_annular_land.py), [stack](../../../python/spike_core/solvers/power_integrity/dc/dc_annular_stack.py) | Cylindrical RT0 contact reference and explicit passive port circuit. | Partial / experimental within stated scope |
| Tetrahedral mixed conduction | [RT0 solve](../../../python/spike_core/solvers/power_integrity/dc/dc_tetra_rt0.py), [sparse profile](../../../python/spike_core/solvers/power_integrity/dc/dc_tetra_sparse.py), [density](../../../python/spike_core/solvers/power_integrity/dc/dc_tetra_density.py) | Conservative face currents, reconstructed fields, physical-volume density measures and separate scalable admission. | Partial / experimental within stated scope |
| Source-bound board volumes | [Volume compiler](../../../python/spike_core/solvers/power_integrity/dc/dc_board_volume.py), [source admission](../../../python/spike_core/solvers/power_integrity/dc/dc_board_source.py), [partition](../../../python/spike_core/solvers/power_integrity/dc/dc_board_partition.py) | Offline experimental native copper/pad/via provenance and conforming full-pad contacts. No general production board dispatch. | Partial / experimental; scaling and refinement open |
| Retained electrical solids | [Tetrahedral electrical](../../../python/spike_core/solvers/power_integrity/dc/assembly_tetra_electrical.py) | Potential FEM and explicit resistive bonds; used by retained electrothermal studies. | Partial / experimental within stated scope |

Read [land method](../../DC_LAND_TRANSITION.md),
[annular evidence](../../validation/PI01_ANNULAR_CONTACT_20261021.md),
[board-volume evidence](../../validation/PI01_BOARD_VOLUME_20261023.md), and
[scaling/refinement outcome](../../validation/PI01_SCALABLE_20261024.md).
The retained Marble refinement fails the frozen heat/p99 stability criteria;
full EBrake24V and Marble +1V0 preparation remains resource-blocked in that record.
Conservation or a completed discrete solve does not resolve these gaps.

## PEEC extraction and transient networks

| Owner | Implementation | Completion state |
| --- | --- | --- |
| [Native PEEC](../../../src/solvers/power_integrity/peec/peec_solver.cpp) | Resistive/partial-inductance numerical kernel | Partial / experimental within stated scope |
| [Volume integrals](../../../src/solvers/power_integrity/peec/volume_inductance.cpp) | Current-basis self/mutual magnetic integration | Implemented bounded kernel |
| [Adapter](../../../python/spike_core/solvers/power_integrity/peec/peec_plugin.py) and [network](../../../python/spike_core/solvers/power_integrity/peec/peec_network.py) | Geometry/model preparation and RLCG network composition | Partial / experimental within stated scope |
| [Transient PEEC](../../../python/spike_core/solvers/power_integrity/peec/transient_peec.py) | Implicit backward-Euler current/voltage block solves | Partial / experimental within stated scope |

PI setup exposes the admitted PEEC studies. See [transient setup](../../TRANSIENT_PI.md)
and [energy safety policy](../../PEEC_SAFETY_POLICY.md). Current bases and quadrature
are discretizations even without a tetrahedral volume mesh. Quasi-static PEEC
does not provide retarded full-wave radiation or general proximity redistribution.
Numerical damping must not be reported as physical dissipation.

## Dielectric fields, reduction and PDN studies

| Subgroup | Code | Method | Completion state |
| --- | --- | --- | --- |
| Capacitance | [Electrostatics](../../../python/spike_core/solvers/power_integrity/pdn/pdn_electrostatic.py) | P1 tetrahedral dielectric potential, unit-electrode fields, Maxwell C and energy | Partial / experimental within stated scope |
| AC dielectric | [Complex field solve](../../../python/spike_core/solvers/power_integrity/pdn/pdn_dielectric_ac.py) | Frequency-dependent conductivity/permittivity operator and terminal admittance | Partial / experimental within stated scope |
| Loaded port reduction | [Admittance reduction](../../../python/spike_core/solvers/power_integrity/pdn/pdn_admittance_reduction.py) | Conditioned Schur elimination of declared internal terminals | Implemented within stated scope |
| PDN/filter/transient loads | [PDN](../../../python/spike_core/solvers/power_integrity/pdn/pdn.py), [network](../../../python/spike_core/solvers/power_integrity/pdn/pdn_network.py) | Explicit RLC elements and supplied load/network composition | Partial / experimental within stated scope |
| Finite decap corners/selection | [Corners](../../../python/spike_core/solvers/power_integrity/pdn/pdn_decap_corners.py), [selection](../../../python/spike_core/solvers/power_integrity/pdn/pdn_decap_selection.py) | Evaluate supplied candidate and operating-corner sets | Implemented within stated scope |

Use PI setup or the exact guarded Python runner in the
[capability map](../../SOLVER_INTEGRATION.md). See [dielectric AC](../../PDN_DIELECTRIC_AC.md),
[reduction](../../PDN_ADMITTANCE_REDUCTION.md), [PDN screening](../../PDN_SCREENING.md)
and [simultaneous loads](../../PDN_SIMULTANEOUS_LOADS.md).
Finite outer dielectric boundaries are not an infinite open-domain model.
Candidate ranking does not solve missing placement fields or qualify a capacitor.

## Verification entry points

Start with `tests/python/test_pdn_electrostatic.py`, `test_pdn_dielectric_ac.py`,
`test_pdn_admittance_reduction.py`, `test_transient_peec.py` and the linked
source-bound DC evidence. Check terminal work, local/global KCL, positive energy,
actual residuals, geometry authentication and refinement separately. Cross-domain
heat transfer belongs to [execution/coupling](../execution/README.md).
