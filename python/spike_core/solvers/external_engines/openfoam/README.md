<!-- SPDX-License-Identifier: Apache-2.0 -->
# External Engines / Openfoam

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/external-engines/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [openfoam.py](openfoam.py)
- [openfoam_buoyancy.py](openfoam_buoyancy.py)
- [openfoam_fan_fixture.py](openfoam_fan_fixture.py)
- [openfoam_flow_diagnostics.py](openfoam_flow_diagnostics.py)
- [openfoam_flow_energy_validation.py](openfoam_flow_energy_validation.py)
- [openfoam_materials.py](openfoam_materials.py)
- [openfoam_mesh_geometry_audit.py](openfoam_mesh_geometry_audit.py)
- [openfoam_multiregion.py](openfoam_multiregion.py)
- [openfoam_multiregion_execution.py](openfoam_multiregion_execution.py)
- [openfoam_multiregion_fixture.py](openfoam_multiregion_fixture.py)
- [openfoam_multiregion_flow.py](openfoam_multiregion_flow.py)
- [openfoam_multiregion_render.py](openfoam_multiregion_render.py)
- [openfoam_multiregion_validation.py](openfoam_multiregion_validation.py)
- [openfoam_polymesh.py](openfoam_polymesh.py)
- [openfoam_rectilinear_assembly.py](openfoam_rectilinear_assembly.py) — explicit
  source-bound cuboid-proxy partitioning; evidence qualification binds topology
  and digests only and is not physical qualification
- [openfoam_pressure_work.py](openfoam_pressure_work.py)
- [openfoam_refinement_study.py](openfoam_refinement_study.py)
- [openfoam_runtime.py](openfoam_runtime.py)
- [openfoam_streamline_export.py](openfoam_streamline_export.py) — bounded native
  `streamLine` U/T export to `spike/field-volume-view/v1`
- [openfoam_turbulence.py](openfoam_turbulence.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
