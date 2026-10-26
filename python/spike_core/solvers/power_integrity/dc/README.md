<!-- SPDX-License-Identifier: Apache-2.0 -->
# Power Integrity / Dc

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/power-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [assembly_tetra_electrical.py](assembly_tetra_electrical.py)
- [assembly_tetra_electrical_validation.py](assembly_tetra_electrical_validation.py)
- [benchmarks.py](benchmarks.py)
- [dc_annular_evidence.py](dc_annular_evidence.py)
- [dc_annular_land.py](dc_annular_land.py)
- [dc_annular_land_input.py](dc_annular_land_input.py)
- [dc_annular_source.py](dc_annular_source.py)
- [dc_annular_stack.py](dc_annular_stack.py)
- [dc_annular_stack_input.py](dc_annular_stack_input.py)
- [dc_axial_ownership.py](dc_axial_ownership.py)
- [dc_board_filled.py](dc_board_filled.py)
- [dc_board_partition.py](dc_board_partition.py)
- [dc_board_source.py](dc_board_source.py)
- [dc_board_study.py](dc_board_study.py)
- [dc_board_volume.py](dc_board_volume.py)
- [dc_copper_domain.py](dc_copper_domain.py)
- [dc_land_transition.py](dc_land_transition.py)
- [dc_land_transition_evidence.py](dc_land_transition_evidence.py)
- [dc_land_transition_input.py](dc_land_transition_input.py)
- [dc_port_circuit.py](dc_port_circuit.py)
- [dc_precision_partition.py](dc_precision_partition.py)
- [dc_result_utils.py](dc_result_utils.py)
- [dc_rt0_density.py](dc_rt0_density.py)
- [dc_shifted_rhs.py](dc_shifted_rhs.py)
- [dc_solver.py](dc_solver.py)
- [dc_terminal_validation.py](dc_terminal_validation.py)
- [dc_tetra_density.py](dc_tetra_density.py)
- [dc_tetra_rt0.py](dc_tetra_rt0.py)
- [dc_tetra_rt0_evidence.py](dc_tetra_rt0_evidence.py)
- [dc_tetra_rt0_input.py](dc_tetra_rt0_input.py)
- [dc_tetra_sparse.py](dc_tetra_sparse.py)
- [dc_triangle_partition.py](dc_triangle_partition.py)
- [filled_copper_path.py](filled_copper_path.py)
- [hybrid_dc_solver.py](hybrid_dc_solver.py)
- [hybrid_drilled_roundrect.py](hybrid_drilled_roundrect.py)
- [hybrid_owned_copper.py](hybrid_owned_copper.py)
- [multiboard_volume_electrical_admission.py](multiboard_volume_electrical_admission.py)
- [pi_path.py](pi_path.py)
- [pi_path_circuit.py](pi_path_circuit.py)
- [pi_path_dc.py](pi_path_dc.py)
- [pi_return_path.py](pi_return_path.py)
- [source_current_limits.py](source_current_limits.py)
- [source_filled_boundary.py](source_filled_boundary.py)
- [zone_pad_connection_evidence.py](zone_pad_connection_evidence.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
