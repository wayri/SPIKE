<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solid mechanics and thermal strain

[All solver families](../README.md)


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Additional completion states

| Solver or supporting workflow | Completion state |
| --- | --- |
| Static retained-volume elasticity | Partial / experimental bounded implementation |
| Same-mesh thermoelasticity | Partial / experimental bounded implementation |

## Static retained-volume elasticity

[assembly_tetra_structural.py](../../../python/spike_core/solvers/mechanics/elasticity/assembly_tetra_structural.py)
owns bounded small-strain isotropic P1 tetrahedral elasticity. Element stiffness
is `K_e = V B.T C B`; explicit displacement constraints remove rigid modes.
The retained conforming mesh and SI ownership checks are shared with solid
thermal admission. Loads, material properties and constraints are model inputs.

## Same-mesh thermoelasticity

The same owner forms thermal eigenstrain from supplied retained temperatures,
expansion coefficient and reference temperature, and assembles its equivalent
load. Elastic energy uses mechanical strain minus thermal eigenstrain; it is not
blindly equated to external work in a thermally strained problem.

[service_structural.py](../../../python/spike_core/service_structural.py) exposes
the worker boundary. The exact reviewed runners are
`run-assembly-structural` and `run-assembly-thermomechanical` in
[the capability map](../../SOLVER_INTEGRATION.md). Read the
[mechanics scope](../../COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md) and
[AC-loss/heat/stress composition](../../validation/AC_THERMAL_ELASTIC_20261023.md).

## State, accuracy and exclusions

Both are experimental retained-mesh workflows. No automatic welding, contact,
mesh-to-mesh transfer, large-strain plasticity, fracture, dynamic FSI or general
actuator qualification is introduced. Geometry exchange with FreeCAD is separate.
Meaningful checks include manufactured/affine response, constraint reactions,
strain/stress units, residuals, rigid-mode rejection and spatial refinement.
Source-specific material and physical correlation remain separate requirements.

Find the corresponding `test_assembly_tetra_structural*` tests under
[Python tests](../../../tests/python/) and preserve their declared tolerances.
Thermal preparation belongs to [thermal/fluid](../thermal-fluid/README.md),
and composed execution belongs to [coupling](../execution/README.md).
