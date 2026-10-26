<!-- SPDX-License-Identifier: Apache-2.0 -->
# Execution / Resources

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/execution/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [acceleration.py](acceleration.py)
- [gpu_acceleration.py](gpu_acceleration.py)
- [parallel_pool.py](parallel_pool.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
