<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE Python application and numerical modules

Use the [solver directory](../../docs/solvers/README.md) to browse modules by
physical domain, subgroup, method, setup route and evidence. Implementations live
in [`solvers/`](solvers/README.md); services, contracts and fixed command entry
points remain here. This directory is not itself a single solver package.

## Domain ownership

| Domain | Source prefixes/examples | Guide |
| --- | --- | --- |
| Circuits | `native_mna`, `spikes_*` | [Circuits](../../docs/solvers/circuits/README.md) |
| Power integrity | `hybrid_dc_solver`, `dc_*`, `peec_*`, `pdn*`, `transient_peec` | [PI](../../docs/solvers/power-integrity/README.md) |
| Signal integrity | `si_*`, `rlgc_*`, `sparameter*`, `harness_*` | [SI](../../docs/solvers/signal-integrity/README.md) |
| Heat and flow | `component_thermal`, `layered_board_thermal`, `assembly_tetra_thermal`, `cfd_*` | [Thermal/CFD](../../docs/solvers/thermal-fluid/README.md) |
| EM and propulsion | `magnetic_*`, `em_*`, `propulsion_pod*`, `huygens_*`, `mom_*` | [EM](../../docs/solvers/electromagnetics/README.md) |
| Mechanics | `assembly_tetra_structural`, `service_structural` | [Mechanics](../../docs/solvers/mechanics/README.md) |
| Geometry | `*_mesh*`, `*_geometry*`, source/ownership validation | [Meshes](../../docs/solvers/geometry-meshing/README.md) |
| Coupling/resources | `cosimulation`, `field_circuit_cosim`, `parallel_*`, `cluster_*`, `acceleration` | [Execution](../../docs/solvers/execution/README.md) |
| External runtimes | Engine adapters, extension services and process supervisors | [Engines](../../docs/solvers/external-engines/README.md) |

Prefixes are navigation hints, not registration or dependency rules. A module may
prepare geometry, validate a contract, supervise a runtime or compose existing
solves without defining new physics. `service_*` modules expose application
boundaries; versioned schemas and registries retain request/routing authority.

Read [architecture](../../ARCHITECTURE.md), [subsystem ownership](../../docs/SUBSYSTEM_INDEX.md),
[language policy](../../docs/LANGUAGE_POLICY.md) and [contribution gates](../../CONTRIBUTING.md)
before changing code. Test owners are under `tests/python/`; retained validation
records are under `docs/validation/`. Do not treat a filename or runnable route as
physical qualification, or move source-bound modules without a migration review.
