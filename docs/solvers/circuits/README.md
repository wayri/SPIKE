<!-- SPDX-License-Identifier: Apache-2.0 -->
# Circuits, switching and semiconductor reference

[All solver families](../README.md) · [SPIKES workflow](../../SPIKES_BOARD_STUDIO.md)


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Additional completion states

| Solver or supporting workflow | Completion state |
| --- | --- |
| Ideal CCM SMPS / stability | Partial / experimental averaged-model family |
| 1D equilibrium semiconductor reference | Implemented bounded reference; full TCAD unavailable |
| Open-PDK / ASIC flow | External preflight/integration; physical closure incomplete |

## Operating point, AC and transient

| Subgroup | Code owner | Method and boundary | Completion state |
| --- | --- | --- | --- |
| Linear MNA boundary | [native_mna.py](../../../python/spike_core/solvers/circuits/models/native_mna.py) | Versioned application boundary for supported modified nodal analysis. | Implemented within stated scope |
| Nonlinear operating point | [DC kernel](../../../src/solvers/circuits/spikes/dc_solver.cpp) | Device current residual/Jacobian stamps and Newton iteration. | Partial / experimental within stated scope |
| Native transient | [Transient kernel](../../../src/solvers/circuits/spikes/transient_solver.cpp), [session](../../../src/solvers/circuits/spikes/transient_session.cpp) | Charge/flux histories; BE, BDF2 and trapezoidal/hybrid controls; accepted-state recovery. | Partial / experimental within stated scope |
| Python/native integration | [Native adapter](../../../python/spike_core/solvers/circuits/models/spikes_native_adapter.py), [runtime](../../../python/spike_core/spikes_runtime.py) | Runtime discovery and transport; native numerical state remains in C++. | Implemented within stated scope |

MNA augments node voltages with source/inductor constraint currents. AC uses
the operating-point linearization. Transient solves time-discretized device
current/charge equations. Adaptive stepping uses an order-two versus BE defect,
restores rejected histories and restarts at source corners. This is not a
rigorous universal time-error bound. Missing grounds or singular topology must
remain visible rather than being silently repaired.

Set up an admitted circuit in SPIKES/Studio. Consult
[adaptive method and evidence](../../SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md),
[transient controls](../../INTERNAL_SPICE_TRANSIENT_CONTROLS.md) and
[mathematics](../../SOLVER_MATHEMATICS.md). Native circuit support is experimental;
it does not imply arbitrary SPICE syntax, model or IBIS compatibility.

## Devices, reduced parts and controllers

| Subgroup | Authority | Implemented scope | Completion state |
| --- | --- | --- | --- |
| Current/charge equations and parasitics | [Equation devices](../../SPIKES_EQUATION_DEVICES.md) | Supported paired I/Q laws and lumped package R/L/C, not distributed package fields | Partial / experimental within stated scope |
| Passive/active/digital libraries | [Library coverage](../../SPIKES_ACTIVE_LIBRARY_COVERAGE.md), [passive laws](../../SPIKES_PASSIVE_MODEL_EQUATIONS.md) | Admitted laws, stamps and event models; catalog identity is separate from manufacturer qualification | Partial / experimental within stated scope |
| Supplied physics parts | [Lumped parts](../../SPIKES_LUMPED_PHYSICS_PARTS.md) | Multi-terminal reduced constitutive models, not automatic field extraction | Partial / experimental within stated scope |
| Compiled controllers and firmware | [Architecture and boundaries](../../../ARCHITECTURE.md), [digital kernel](../../../src/solvers/circuits/spikes/digital_kernel.hpp), [pad timing](../../../src/solvers/circuits/spikes/peripheral_timing.cpp) | Explicit sampled callbacks and separately admitted native firmware/pad modes | Partial / experimental within stated scope |
| One-RC battery | [Battery model](../../SPIKES_BATTERY_MODEL.md) | Supplied equivalent-circuit reference, not electrochemistry | Partial / experimental within stated scope |
| Electrothermal sharing | [Sharing owner](../../../python/spike_core/solvers/execution/coupling/electrothermal_sharing.py) | Bounded parallel-diode electrical/thermal reference | Partial / experimental within stated scope |

## Averaged power converters and stability

[SMPS kernel](../../../src/solvers/circuits/spikes/smps_stability.cpp) and
[method/workflow](../../SPIKES_SMPS_STABILITY.md) implement supplied ideal CCM
converter equations, compensation, crossings and closed-loop pole checks.
This is an averaged model, separate from switching transient execution.
One phase margin does not certify all poles or hardware stability.

## Equilibrium semiconductor field reference

[tcad_equilibrium.cpp](../../../src/solvers/circuits/spikes/tcad_equilibrium.cpp) solves 1D
Poisson-Boltzmann equilibrium using finite-volume residuals, a tridiagonal Newton
system and residual-decreasing backtracking. [Method/evidence](../../SPIKES_TCAD_EQUILIBRIUM.md)
records the homogeneous material, full-ionization and Boltzmann assumptions,
Gauss balance and refinement. No biased carrier transport, heterointerface or
process simulation is inferred. This is source/API reference scope.

## External circuit and ASIC tools

[Open-PDK workflow](../../SPIKES_OPEN_PDK_WORKFLOW.md) and
[ASIC/KLayout flow](../../SPIKES_ASIC_TWO_APPLICATION_FLOW.md) separate inert
inventory/preflight from external execution. ngspice and Xyce belong to
[external engines](../external-engines/README.md). Full TCAD and ASIC physical
closure remain planned, not enabled by these tools.

## Verification

Use the native circuit tests and `tests/python/test_spikes_native_adaptive_runner.py`,
`test_spikes_transient_controls.py` and `test_spikes_smps_stability.py` as entry
points. Check operating point, charge/flux histories, rejected-step recovery,
source events and time refinement, not only final plot samples. Recorded tests
do not establish every device's physical accuracy or frozen-package parity.
