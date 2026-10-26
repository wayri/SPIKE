<!-- SPDX-License-Identifier: Apache-2.0 -->
# Signal Integrity / Channels

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/signal-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [si_channel.py](si_channel.py)
- [si_coupled_channel.py](si_coupled_channel.py)
- [si_frequency_loss.py](si_frequency_loss.py)
- [si_impedance.py](si_impedance.py)
- [si_material_scenario.py](si_material_scenario.py)
- [si_pair_geometry.py](si_pair_geometry.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
