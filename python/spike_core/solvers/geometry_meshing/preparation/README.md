<!-- SPDX-License-Identifier: Apache-2.0 -->
# Geometry Meshing / Preparation

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/geometry-meshing/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [assembly_thermal_autolink.py](assembly_thermal_autolink.py)
- [assembly_thermal_body_power.py](assembly_thermal_body_power.py)
- [assembly_thermal_cad.py](assembly_thermal_cad.py)
- [assembly_thermal_components.py](assembly_thermal_components.py)
- [assembly_thermal_contact_model.py](assembly_thermal_contact_model.py)
- [assembly_thermal_encapsulation.py](assembly_thermal_encapsulation.py)
- [assembly_thermal_encapsulation_occ.py](assembly_thermal_encapsulation_occ.py)
- [assembly_thermal_joint_geometry.py](assembly_thermal_joint_geometry.py)
- [assembly_thermal_joint_mesh.py](assembly_thermal_joint_mesh.py)
- [assembly_thermal_meshing.py](assembly_thermal_meshing.py)
- [board_mesh_ownership.py](board_mesh_ownership.py)
- [boundary_spatial_index.py](boundary_spatial_index.py)
- [conforming_local_refinement.py](conforming_local_refinement.py)
- [crossboard_mesh.py](crossboard_mesh.py)
- [dynamic_tetra_adaptation.py](dynamic_tetra_adaptation.py)
- [generalized_reference_plane_mesh_quality.py](generalized_reference_plane_mesh_quality.py)
- [generalized_reference_plane_native_handoff.py](generalized_reference_plane_native_handoff.py)
- [geometry.py](geometry.py)
- [gmsh_environment.py](gmsh_environment.py)
- [gmsh_extension_api.py](gmsh_extension_api.py)
- [gmsh_extension_mesh.py](gmsh_extension_mesh.py)
- [gmsh_extension_runtime.py](gmsh_extension_runtime.py)
- [gmsh_occ_mesher.py](gmsh_occ_mesher.py)
- [gmsh_occ_runtime.py](gmsh_occ_runtime.py)
- [hybrid_mesh.py](hybrid_mesh.py)
- [internal_meshing_engine.py](internal_meshing_engine.py)
- [internal_tetra_generation.py](internal_tetra_generation.py)
- [local_mesh_controls.py](local_mesh_controls.py)
- [mesh_ownership.py](mesh_ownership.py)
- [meshing.py](meshing.py)
- [pcb_focus_sizing.py](pcb_focus_sizing.py)
- [pcb_volume_compiler.py](pcb_volume_compiler.py)
- [pcb_volume_mesh.py](pcb_volume_mesh.py)
- [planar_curve_tessellation.py](planar_curve_tessellation.py)
- [planar_polygon_topology.py](planar_polygon_topology.py)
- [reference_plane_antipad_geometry.py](reference_plane_antipad_geometry.py)
- [reference_plane_antipad_geometry_v2.py](reference_plane_antipad_geometry_v2.py)
- [reference_plane_antipad_geometry_v3.py](reference_plane_antipad_geometry_v3.py)
- [reference_plane_antipad_mesh.py](reference_plane_antipad_mesh.py)
- [reference_plane_antipad_mesh_quality.py](reference_plane_antipad_mesh_quality.py)
- [reference_plane_antipad_mesh_v2.py](reference_plane_antipad_mesh_v2.py)
- [reference_plane_antipad_native_handoff.py](reference_plane_antipad_native_handoff.py)
- [reference_plane_mesh_ownership.py](reference_plane_mesh_ownership.py)
- [solver_geometry.py](solver_geometry.py)
- [spatial_sampling.py](spatial_sampling.py)
- [tetra_aabb_candidates.py](tetra_aabb_candidates.py)
- [tetra_mesh_optimization.py](tetra_mesh_optimization.py)
- [tetra_mesh_refinement.py](tetra_mesh_refinement.py)
- [via_transition_geometry.py](via_transition_geometry.py)
- [via_transition_mesh.py](via_transition_mesh.py)
- [via_transition_mesh_quality.py](via_transition_mesh_quality.py)
- [via_transition_native_handoff.py](via_transition_native_handoff.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
