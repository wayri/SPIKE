<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thermal Fluid / Heat

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/thermal-fluid/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [assembly_tetra_radiation.py](assembly_tetra_radiation.py)
- [assembly_tetra_thermal.py](assembly_tetra_thermal.py)
- [assembly_tetra_thermal_validation.py](assembly_tetra_thermal_validation.py)
- [assembly_tetra_transient.py](assembly_tetra_transient.py)
- [assembly_view_factors.py](assembly_view_factors.py)
- [board_thermal.py](board_thermal.py)
- [component_thermal.py](component_thermal.py)
- [layered_board_thermal.py](layered_board_thermal.py)
- [multiboard_thermal.py](multiboard_thermal.py)
- [multiboard_thermal_parts.py](multiboard_thermal_parts.py)
- [multiboard_thermal_scope.py](multiboard_thermal_scope.py)
- [retained_thermal_step.py](retained_thermal_step.py)
- [structured_solid_thermal.py](structured_solid_thermal.py)
- [thermal.py](thermal.py)
- [thermal_accuracy.py](thermal_accuracy.py)
- [thermal_copper_geometry.py](thermal_copper_geometry.py)
- [thermal_field_job.py](thermal_field_job.py)
- [thermal_grid.py](thermal_grid.py)
- [thermal_network.py](thermal_network.py)
- [thermal_relief_boundary_contact.py](thermal_relief_boundary_contact.py)
- [thermal_relief_observed_topology.py](thermal_relief_observed_topology.py)
- [thermal_spoke_observed_geometry.py](thermal_spoke_observed_geometry.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
