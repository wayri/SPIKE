<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver implementations

[Methods, setup routes, validity and evidence](../../docs/solvers/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Subgroups

- [circuits](circuits/README.md)
- [geometry_meshing](geometry_meshing/README.md)
- [power_integrity](power_integrity/README.md)
- [signal_integrity](signal_integrity/README.md)
- [thermal_fluid](thermal_fluid/README.md)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
