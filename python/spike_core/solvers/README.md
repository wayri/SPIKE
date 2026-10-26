<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver implementations

[Methods, setup routes, validity and evidence](../../../docs/solvers/README.md)

[Mathematics, research references and complete grouped source inventory](MATHEMATICS_AND_REFERENCES.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Subgroups

- [_source_layout.py](_source_layout.py)
- [circuits](circuits/README.md)
- [electromagnetics](electromagnetics/README.md)
- [execution](execution/README.md)
- [external_engines](external_engines/README.md)
- [geometry_meshing](geometry_meshing/README.md)
- [mechanics](mechanics/README.md)
- [power_integrity](power_integrity/README.md)
- [signal_integrity](signal_integrity/README.md)
- [thermal_fluid](thermal_fluid/README.md)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
