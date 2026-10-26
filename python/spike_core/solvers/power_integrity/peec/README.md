<!-- SPDX-License-Identifier: Apache-2.0 -->
# Power Integrity / Peec

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/power-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [ac_power_integrity.py](ac_power_integrity.py)
- [conductor_ac_loss.py](conductor_ac_loss.py)
- [loop_parasitics.py](loop_parasitics.py)
- [peec_capacitance_dispatch.py](peec_capacitance_dispatch.py)
- [peec_conforming_dc.py](peec_conforming_dc.py)
- [peec_conforming_mesh.py](peec_conforming_mesh.py)
- [peec_field_provider.py](peec_field_provider.py)
- [peec_magnetic_geometry.py](peec_magnetic_geometry.py)
- [peec_matrices.py](peec_matrices.py)
- [peec_native_factory.py](peec_native_factory.py)
- [peec_network.py](peec_network.py)
- [peec_plugin.py](peec_plugin.py)
- [peec_rt0_iterative.py](peec_rt0_iterative.py)
- [peec_spice_export.py](peec_spice_export.py)
- [peec_volume_adapter.py](peec_volume_adapter.py)
- [peec_volume_resistance.py](peec_volume_resistance.py)
- [peec_volume_support.py](peec_volume_support.py)
- [transient_peec.py](transient_peec.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
