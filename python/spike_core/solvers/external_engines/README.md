<!-- SPDX-License-Identifier: Apache-2.0 -->
# External Engines

[Methods, setup routes, validity and evidence](../../../../docs/solvers/external-engines/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Subgroups

- [calculix](calculix/README.md)
- [circuits](circuits/README.md)
- [openems](openems/README.md)
- [openfoam](openfoam/README.md)
- [sparselizard](sparselizard/README.md)
- [su2](su2/README.md)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
