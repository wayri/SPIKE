<!-- SPDX-License-Identifier: Apache-2.0 -->
# External Engines / Sparselizard

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/external-engines/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [sparselizard_adapter.py](sparselizard_adapter.py)
- [sparselizard_process.py](sparselizard_process.py)
- [sparselizard_runtime.py](sparselizard_runtime.py)
- [sparselizard_validation.py](sparselizard_validation.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
