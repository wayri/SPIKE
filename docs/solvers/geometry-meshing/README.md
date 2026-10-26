<!-- SPDX-License-Identifier: Apache-2.0 -->
# Geometry, meshes and numerical bases

[All solver families](../README.md)


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Additional completion states

| Solver or supporting workflow | Completion state |
| --- | --- |
| Native planar topology / constrained triangulation | Implemented bounded geometry foundation; solve convergence separate |

## Topology and identity before discretization

[planar_topology.cpp](../../../src/solvers/geometry_meshing/geometry/planar_topology.cpp) and
[constrained_triangulation.cpp](../../../src/solvers/geometry_meshing/geometry/constrained_triangulation.cpp)
own native planar predicates and triangulation foundations. Source geometry must
retain units, holes, material/layer/net ownership, contacts and positive measure.
Exact topology, physical contacts and engineering clearances are different inputs.

See [native geometry foundation](../../CAD_NEUTRAL_NATIVE_MULTIPHYSICS_FOUNDATION.md)
and [meshing diagnostics](../../MESHING_ENGINE.md). A mesh that passes topology
checks is not thereby a converged electrical, fluid or thermal solution.

## Mesh preparation subgroups

| Subgroup | Owner or workflow | Role | Completion state |
| --- | --- | --- | --- |
| PCB solid compilation | [pcb_volume_compiler.py](../../../python/spike_core/solvers/geometry_meshing/preparation/pcb_volume_compiler.py) | Neutral model/volume preparation | Implemented preparation; downstream solve separate |
| Focused PCB volume mesh | [Workflow](../../PCB_FOCUSED_VOLUME_MESHING.md) | Local resolution and retained identity | Implemented preparation; downstream solve separate |
| OCC/Gmsh conforming volumes | [OCC mesher](../../../python/spike_core/solvers/geometry_meshing/preparation/gmsh_occ_mesher.py), [workflow](../../OCC_CONFORMING_PCB_MESH.md) | Optional external meshing; runtime/admission required | Implemented preparation; downstream solve separate |
| Thermal assembly solids | [assembly_thermal_meshing.py](../../../python/spike_core/solvers/geometry_meshing/preparation/assembly_thermal_meshing.py), [reviewed component solids](../../THERMAL_COMPONENT_SOLIDS.md) | Explicit retained solids and contacts | Implemented preparation; downstream solve separate |
| Authenticated DC board partition | [dc_board_partition.py](../../../python/spike_core/solvers/power_integrity/dc/dc_board_partition.py), [compiler](../../../python/spike_core/solvers/power_integrity/dc/dc_board_volume.py) | Source-bound copper/contact partitions; separate experimental budgets | Partial / experimental; resource limits open |
| Retained CFD topology | [cfd_tetra_mesh.py](../../../python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_mesh.py) | SI tetrahedra, material phases, oriented faces and patches | Implemented preparation; downstream solve separate |
| Tetra refinement | [tetra_mesh_refinement.py](../../../python/spike_core/solvers/geometry_meshing/preparation/tetra_mesh_refinement.py) | Supported refinement operations; field transfer and convergence require their own contracts | Implemented preparation; downstream solve separate |

## Which discretization belongs to which solve?

| Representation | Consumers | Resolution considerations |
| --- | --- | --- |
| Lumped graph | Circuit, harness DC, object thermal | Physical topology and parameters; no spatial field inferred |
| Structured cells/faces | Board thermal, native MAC flow | Cell size, boundary treatment, copper/material sampling |
| P1 tetrahedra/triangles | Dielectric, solid thermal/electrical/elastic, planar magnetic | Shape quality, interfaces, contacts, finite-domain and mesh refinement |
| Mixed RT0 and CR/P0 spaces | Conservative DC/energy and creeping flow | Shared flux/face identities, local balance and admitted operator |
| PEEC current basis | Quasi-static conductor extraction | Basis support, overlap, self/mutual quadrature and energy |
| RWG surface basis | MoM groundwork | Basis availability does not provide a full integral-equation solve |
| Analytic line or sampled network | SI and reduced port coupling | Parameter/bandwidth/model validity rather than volume mesh |

Meshes cannot be interchanged merely because both contain tetrahedra. Boundary
identities, variable locations, constitutive operators and conservative transfer
must agree. Coordinate-nearest matching does not prove physical correspondence.
No general meshfree PDE solver is implied by the graph or analytic paths.

## Verification and performance

Preserve source digests and check orientation, ownership, holes, volume/area
budgets, conformity, hanging nodes and intersections before field assembly.
Then perform physics-specific refinement and independent comparisons.
[Shared audit scaling](../../DC_GEOMETRY_SCALING.md) accelerates admission without
relaxing geometry predicates; [executed DC scaling evidence](../../validation/PI01_SCALABLE_20261024.md)
retains failed as well as successful board outcomes.

Gmsh/FreeCAD runtime roles are documented under
[external engines](../external-engines/README.md). CPU/GPU and native migration
boundaries are under [execution](../execution/README.md).
