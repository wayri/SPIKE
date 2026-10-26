<!-- SPDX-License-Identifier: Apache-2.0 -->
# Signal Integrity / Si

[Methods, setup routes, validity and evidence](../../../../docs/solvers/signal-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [ami_host_main.cpp](ami_host_main.cpp)
- [transition_pi_cdr.cpp](transition_pi_cdr.cpp)
- [transition_pi_cdr.hpp](transition_pi_cdr.hpp)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
