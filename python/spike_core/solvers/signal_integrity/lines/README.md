<!-- SPDX-License-Identifier: Apache-2.0 -->
# Signal Integrity / Lines

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/signal-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [distortionless_line_transient.py](distortionless_line_transient.py)
- [harness_mtl.py](harness_mtl.py)
- [harness_pi.py](harness_pi.py)
- [harness_rlgc_geometry.py](harness_rlgc_geometry.py)
- [harness_signal.py](harness_signal.py)
- [lossless_line_transient.py](lossless_line_transient.py)
- [rlgc_coupled_cascade.py](rlgc_coupled_cascade.py)
- [rlgc_coupled_pair.py](rlgc_coupled_pair.py)
- [rlgc_coupled_star.py](rlgc_coupled_star.py)
- [rlgc_line_cascade.py](rlgc_line_cascade.py)
- [rlgc_line_fields.py](rlgc_line_fields.py)
- [rlgc_line_junction.py](rlgc_line_junction.py)
- [rlgc_line_network.py](rlgc_line_network.py)
- [rlgc_loaded_cascade.py](rlgc_loaded_cascade.py)
- [rlgc_loaded_star.py](rlgc_loaded_star.py)
- [rlgc_reactive_pair.py](rlgc_reactive_pair.py)
- [rlgc_terminated_pair.py](rlgc_terminated_pair.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
