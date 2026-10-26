<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thermal conduction, airflow and CFD

[All solver families](../README.md) · [Thermal setup](../../THERMAL_WORKFLOW.md) ·
[Current status](../../SOLVER_STATUS.md)


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Lumped and structured heat models

| Subgroup | Source | Method and validity | Completion state |
| --- | --- | --- | --- |
| Object/component temperatures | [component_thermal.py](../../../python/spike_core/solvers/thermal_fluid/heat/component_thermal.py) | Conductance/capacity nodes and supplied boundary paths; markers are not a spatial board field. | Implemented approximate model |
| Board plate and layered stack | [board_thermal.py](../../../python/spike_core/solvers/thermal_fluid/heat/board_thermal.py), [layered_board_thermal.py](../../../python/spike_core/solvers/thermal_fluid/heat/layered_board_thermal.py) | Structured lateral/vertical conduction, sampled copper occupancy and stackup storage; approximate bounding geometry. | Implemented approximate model |
| Structured solids | [structured_solid_thermal.py](../../../python/spike_core/solvers/thermal_fluid/heat/structured_solid_thermal.py) | Harmonic Fourier face conductance, implicit sensible storage and supported radiation iteration. | Partial / experimental within stated scope |
| Structured electrical feedback | [structured_electrothermal.py](../../../python/spike_core/solvers/thermal_fluid/electrothermal/structured_electrothermal.py) | Supported electrical dissipation and temperature-dependent material feedback. | Partial / experimental within stated scope |

Set up power, material properties, contacts and cooling boundaries explicitly.
See [component models](../../COMPONENT_THERMAL.md). Virtual heatsinks use
prescribed contact/sink resistances; they do not derive fin/airflow performance.
Board copper sampling and depth resolution remain model assumptions.

## Retained tetrahedral fields

| Subgroup | Source | Numerical formulation | Completion state |
| --- | --- | --- | --- |
| Steady thermal | [assembly_tetra_thermal.py](../../../python/spike_core/solvers/thermal_fluid/heat/assembly_tetra_thermal.py) | Affine P1 tetrahedral weak form, explicit convection and paired contact integrals | Partial / experimental within stated scope |
| Geometry admission | [assembly_tetra_thermal_validation.py](../../../python/spike_core/solvers/thermal_fluid/heat/assembly_tetra_thermal_validation.py) | Conforming retained SI geometry/ownership checks | Implemented within stated scope |
| Transient | [assembly_tetra_transient.py](../../../python/spike_core/solvers/thermal_fluid/heat/assembly_tetra_transient.py), [retained_thermal_step.py](../../../python/spike_core/solvers/thermal_fluid/heat/retained_thermal_step.py) | Implicit storage and accepted-state histories | Partial / experimental within stated scope |
| Ambient radiation | [assembly_tetra_radiation.py](../../../python/spike_core/solvers/thermal_fluid/heat/assembly_tetra_radiation.py) | Separate nonlinear boundary treatment and energy gates | Partial / experimental within stated scope |
| Assembly electrical feedback | [assembly_electrothermal.py](../../../python/spike_core/solvers/thermal_fluid/electrothermal/assembly_electrothermal.py), [multiboard volume](../../../python/spike_core/solvers/thermal_fluid/electrothermal/multiboard_volume_electrothermal.py) | Explicit bonds, Joule heat and temperature-dependent conductivity iteration | Partial / experimental within stated scope |

[Assembly electrothermal](../../ASSEMBLY_ELECTROTHERMAL.md),
[transient](../../ASSEMBLY_THERMAL_TRANSIENT.md),
[multiboard setup](../../MULTIBOARD_VOLUME_ELECTROTHERMAL.md) and
[PWM volume coupling](../../PWM_VOLUME_ELECTROTHERMAL.md) describe separate
admitted workflows. Relaxed updates cannot replace the unrelaxed coupling-defect
check. Every heat source and contact loss must be deposited exactly once.

## Channels and structured flow

| Subgroup | Owner | Boundary | Completion state |
| --- | --- | --- | --- |
| Developed laminar channel | [laminar_channel_cht.py](../../../python/spike_core/solvers/thermal_fluid/flow/laminar_channel_cht.py), [derivation](../../BOUNDED_CHT_AND_RADIATION.md) | Reduced developed flow and finite-volume energy; not arbitrary enclosure momentum. | Partial / experimental within stated scope |
| Internal airflow/fan screening | [Workflow](../../INTERNAL_AIRFLOW.md) | Supplied duct/fan-system relations; no inferred spatial fan field. | Implemented approximate model |
| Native 2D cavity | [cavity.cpp](../../../src/solvers/thermal_fluid/airflow/cavity.cpp) | Incompressible staggered MAC reference with projection/pressure solve. | Partial / experimental within stated scope |
| Native conjugate energy | [cht.cpp](../../../src/solvers/thermal_fluid/airflow/cht.cpp), [method](../../validation/NATIVE_CHT_METHOD_20261020.md) | Conservative Fourier/upwind energy on the bounded reference geometry. | Partial / experimental within stated scope |
| Rectilinear enclosure research | [Momentum method](../../validation/ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md), [energy method](../../validation/ENCLOSURE_CHT_METHOD_20261020.md) | Supported obstacle/grid operators and bounded convergence; isolated RANS/rotation operator checks are not general turbulence qualification. | Research / bounded operators only |

## Retained tetrahedral creeping-flow CHT

| Stage | Source | Method and admission | Completion state |
| --- | --- | --- | --- |
| Mesh | [cfd_tetra_mesh.py](../../../python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_mesh.py) | Retained tetrahedra, phases, patch identities and explicit limits | Partial / experimental within stated scope |
| Flow | [cfd_tetra_stokes.py](../../../python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_stokes.py) | CR/P0 mixed creeping flow, broken vector-Laplacian and pseudo-traction; declared Reynolds ceiling 0.1 | Partial / experimental within stated scope |
| Energy | [cfd_tetra_energy.py](../../../python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_energy.py) | RT0 conductive flux, P0 temperature and shared donor-cell enthalpy | Partial / experimental within stated scope |
| Composition | [cfd_tetra_cht.py](../../../python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_cht.py) | Accepted flow face fluxes drive solid/fluid energy on retained geometry | Partial / experimental within stated scope |
| Worker | [service_cfd.py](../../../python/spike_core/service_cfd.py) | Guarded versioned request/result transport | Partial / experimental within stated scope |

Read [flow evidence](../../validation/CFD_TETRA_STOKES_20261021.md) and
[CHT release boundary](../../validation/CFD_CHT_RELEASE_20261023.md).
The composition is one-way: no inertia, turbulence or buoyancy/temperature-to-flow
feedback is inferred. Its pseudo-traction is not a generally qualified symmetric
Newtonian stress boundary. Source-declared digests are not source authentication.
The exact Python runner is listed in [integration](../../SOLVER_INTEGRATION.md).

## Verification and performance

[thermal_accuracy.py](../../../python/spike_core/solvers/thermal_fluid/heat/thermal_accuracy.py) and
[time-refinement workflow](../../THERMAL_ACCURACY_CHECKS.md) compare dt, dt/2 and
dt/4 retained histories without changing experimental status. Independent spatial
refinement, boundary/material sensitivity and physical correlation remain separate.
Check input-output-storage energy, local mass/heat balance, actual residuals and
conditioning; a smooth temperature plot or low residual does not bound model error.

Tests start at `tests/python/test_thermal_accuracy.py`, `test_assembly_tetra_thermal.py`,
`test_cfd_tetra_cht.py` and the corresponding flow/energy owners.
External OpenFOAM/SU2/CalculiX workflows are in
[external engines](../external-engines/README.md); rotor/inertial CFD experiments
are under [propulsion](../electromagnetics/README.md).
