<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE native numerical source

The [solver directory](../docs/solvers/README.md) groups native kernels together
with their Python application boundaries, setup workflows and validation records.

## Native subgroups

| Directory | Responsibility | Guide |
| --- | --- | --- |
| `solvers/circuits/spikes/` | Circuit residuals, transient state/integration, devices, controller timing and equilibrium semiconductor reference | [Circuits](../docs/solvers/circuits/README.md) |
| `solvers/power_integrity/peec/` | Partial-element kernels, volume/basis integration and energy admission | [Power integrity](../docs/solvers/power-integrity/README.md) |
| `solvers/thermal_fluid/airflow/` | Bounded native cavity and conjugate-energy reference | [Thermal/CFD](../docs/solvers/thermal-fluid/README.md) |
| `solvers/thermal_fluid/thermal/` | Native thermal kernel source; exact application exposure follows the existing adapters/status | [Thermal/CFD](../docs/solvers/thermal-fluid/README.md) |
| `solvers/geometry_meshing/geometry/` | Planar topology and constrained triangulation foundations | [Geometry/meshes](../docs/solvers/geometry-meshing/README.md) |
| `solvers/signal_integrity/si/` | Native receiver reference and separate trusted development AMI host | [Signal integrity](../docs/solvers/signal-integrity/README.md) |

This is a solver-related directory map, not a claim that every native target is
publicly routed or production-qualified. CMake targets, bindings, runtime manifests
and [solver status](../docs/SOLVER_STATUS.md) retain their existing authority.
Tests live under `tests/` and application/integration tests under `tests/python/`.
Performance changes require equivalent numerical evidence and the
[method provenance/review gates](../docs/NUMERICAL_METHOD_EVIDENCE.md).
