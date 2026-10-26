<!-- SPDX-License-Identifier: Apache-2.0 -->
# External Engines / Su2

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/external-engines/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [su2_airflow.py](su2_airflow.py)
- [su2_cht.py](su2_cht.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
