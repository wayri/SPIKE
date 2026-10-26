<!-- SPDX-License-Identifier: Apache-2.0 -->
# Geometry Meshing / Geometry

[Methods, setup routes, validity and evidence](../../../../docs/solvers/geometry-meshing/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [constrained_triangulation.cpp](constrained_triangulation.cpp)
- [planar_topology.cpp](planar_topology.cpp)
- [planar_topology.hpp](planar_topology.hpp)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
