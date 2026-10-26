<!-- SPDX-License-Identifier: Apache-2.0 -->
# Electromagnetics, machines and propulsion research

[All solver families](../README.md) · [Methods](../../SOLVER_MATHEMATICS.md)


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Additional completion states

| Solver or supporting workflow | Completion state |
| --- | --- |
| Reduced PM motor/generator and reluctance actuator | Implemented reduced models; resolved machine qualification separate |
| Public Optycal RF physical-optics extension | External integration; model/runtime qualification separate |

## Reduced machines and actuators

[em_machines.py](../../../python/spike_core/solvers/electromagnetics/machines/em_machines.py) owns lumped PM
motor/generator electrical-shaft dynamics and a single-path electromagnet.
Reciprocal motor constants and implicit midpoint support discrete energy
accounting. The reluctance actuator assumes a linear core and uniform gap.
[Setup and equations](../../EM_MACHINES.md) describe the Machines workflow and
explicit material/load parameters. These are reduced models, not resolved motors.

## Planar magnetic field and machine studies

| Subgroup | Code | Method and limits | Completion state |
| --- | --- | --- | --- |
| Linear/nonlinear magnetostatics | [magnetic_fem.py](../../../python/spike_core/solvers/electromagnetics/machines/magnetic_fem.py) | P1 triangular Az, supplied remanence/B-H law, exact supported constitutive tangent and potential-decrease Newton line search | Partial / experimental within stated scope |
| Stationary eddy fields | [Magnetic FEM method](../../MAGNETIC_FEM.md) | Az plus per-region axial electric offsets; implicit storage and Joule/work checks | Partial / experimental within stated scope |
| Force, torque and motion | [magnetic_machine_study.py](../../../python/spike_core/solvers/electromagnetics/machines/magnetic_machine_study.py) | Maxwell stress on admitted closed air contours and bounded mechanical stepping | Partial / experimental within stated scope |
| Magnetic heating | [magnetic_thermal.py](../../../python/spike_core/solvers/electromagnetics/machines/magnetic_thermal.py) | Explicit stationary Joule-heat composition | Partial / experimental within stated scope |

Use [machine-study setup](../../MAGNETIC_MACHINE_STUDIES.md) and
[thermal coupling](../../MAGNETIC_THERMAL.md). Gauge, B-H range, air-box and mesh
convergence are required. Motion plus stationary eddy physics is not general
motional v-cross-B coupling; conservative remesh-state transfer is not implied.

## Controller, field and propeller compositions

| Subgroup | Source owner | Executed scope and remaining limits | Completion state |
| --- | --- | --- | --- |
| Synthetic coupled benchmark | [propulsion_pod.py](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod.py), [field](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_field.py), [controller](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_controller.py), [propeller](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_propeller.py) | Sampled compiled controller, reciprocal motor ports, shaft dynamics and hover BEM reaction | Partial / experimental within stated scope |
| Three-phase extension | [Run](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_three_phase_run.py), [electrical step](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_three_phase.py), [thermal](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_thermal.py) | Separate floating-neutral/field/controller composition | Partial / experimental within stated scope |
| Explicit geometry ports | [Run boundary](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_geometry_run.py), [loop](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_geometry_loop.py) | Retained magnetic/load tables and thermal feedback with explicit identity | Partial / experimental within stated scope |
| Rotor/inertial CFD candidates | [Rotor CFD](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_rotor_cfd.py), [current-Jacobian adapter](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_inertial_cfd_current.py), [Schur candidate](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_jacobian_schur.py) | Separate blade/inertial research; accepted full-speed actual-air load remains open | Research / incomplete; actual-air closure open |
| Magnetic/refinement candidates | [Modal gap](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_modal_gap.py), [CFD refinement](../../../python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_cfd_refinement.py) | Optional bounded operators/transfer; not independent source-specific convergence qualification | Research / incomplete |

The desktop propulsion workflow and source runners have different runtime and
capture requirements. Read [coupling derivation](../../validation/PROPULSION_POD_COUPLING_DERIVATION_20261023.md),
[geometry-port ADR](../../adr/0136-explicit-geometry-propulsion-ports.md) and
[numerical candidate ledger](../../NUMERICAL_METHOD_EVIDENCE.md).
Synthetic controller/field execution does not establish actual VESC/product-motor
identity, accepted real-air CFD, enclosure cooling or flight performance.

## Radiation postprocessing and MoM groundwork

| Owner | Scope | Completion state |
| --- | --- | --- |
| [huygens_far_field.py](../../../python/spike_core/solvers/electromagnetics/fields/huygens_far_field.py) | Closed-box supplied E/H integration in a homogeneous lossless exterior | Implemented supplied-field postprocessing |
| [mom_surface_basis.py](../../../python/spike_core/solvers/electromagnetics/fields/mom_surface_basis.py) | RWG surface basis groundwork; related singular integral and supplied-current operators | Partial groundwork; full MoM unavailable |

Read [operator evidence](../../validation/MOM_REFERENCE_OPERATORS_20260930.md)
and [retained EM](../../RETAINED_ASSEMBLY_EM.md). Supplied-current radiation does
not solve induced currents. Complete surface MoM and owned arbitrary-PCB full-wave
3D remain unavailable. openEMS/EMerge/PALACE belong to
[external engines](../external-engines/README.md); quasi-static PEEC belongs to
[power integrity](../power-integrity/README.md).

## Verification and planned scope

Entry tests include `tests/python/test_em_machines.py`, `test_magnetic_fem.py`,
`test_magnetic_machine_study.py` and the `test_propulsion_pod_*` family.
Check energy reciprocity, constitutive range, residuals, stress-contour sensitivity,
mesh/domain/time refinement and independent load evidence separately.
[Propulsion planning](../../PROPULSION_MACHINES_FLUID_POWER_PLAN.md) does not enable
general reacting flow or qualify jet/gas-turbine combustion.
