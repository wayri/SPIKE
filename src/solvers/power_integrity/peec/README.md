<!-- SPDX-License-Identifier: Apache-2.0 -->
# Power Integrity / Peec

[Methods, setup routes, validity and evidence](../../../../docs/solvers/power-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [affine_slab_inductance.cpp](affine_slab_inductance.cpp)
- [affine_slab_inductance.hpp](affine_slab_inductance.hpp)
- [affine_triangle_basis.cpp](affine_triangle_basis.cpp)
- [affine_triangle_basis.hpp](affine_triangle_basis.hpp)
- [annular_inductance.cpp](annular_inductance.cpp)
- [annular_inductance.hpp](annular_inductance.hpp)
- [generalized_reference_plane_mesh_input.cpp](generalized_reference_plane_mesh_input.cpp)
- [generalized_reference_plane_mesh_input.hpp](generalized_reference_plane_mesh_input.hpp)
- [peec_solver.cpp](peec_solver.cpp)
- [peec_solver.hpp](peec_solver.hpp)
- [reference_plane_antipad_mesh_input.cpp](reference_plane_antipad_mesh_input.cpp)
- [reference_plane_antipad_mesh_input.hpp](reference_plane_antipad_mesh_input.hpp)
- [sparse_magnetic_energy.cpp](sparse_magnetic_energy.cpp)
- [sparse_magnetic_energy.hpp](sparse_magnetic_energy.hpp)
- [via_transition_mesh_input.cpp](via_transition_mesh_input.cpp)
- [via_transition_mesh_input.hpp](via_transition_mesh_input.hpp)
- [volume_inductance.cpp](volume_inductance.cpp)
- [volume_inductance.hpp](volume_inductance.hpp)
- [volume_matrix.cpp](volume_matrix.cpp)
- [volume_matrix.hpp](volume_matrix.hpp)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
