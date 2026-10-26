<!-- SPDX-License-Identifier: Apache-2.0 -->
# External Engines / Calculix

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/external-engines/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [calculix_deck.py](calculix_deck.py)
- [calculix_runtime.py](calculix_runtime.py)
- [calculix_thermal.py](calculix_thermal.py)
- [calculix_transient.py](calculix_transient.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
