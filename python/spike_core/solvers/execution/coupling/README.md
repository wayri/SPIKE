<!-- SPDX-License-Identifier: Apache-2.0 -->
# Execution / Coupling

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/execution/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [assembly_field_geometry.py](assembly_field_geometry.py)
- [assembly_field_handoff.py](assembly_field_handoff.py)
- [assembly_field_result.py](assembly_field_result.py)
- [assembly_field_study.py](assembly_field_study.py)
- [assembly_field_thermal.py](assembly_field_thermal.py)
- [assembly_field_transient.py](assembly_field_transient.py)
- [cosimulation.py](cosimulation.py)
- [coupled_surface_exchange.py](coupled_surface_exchange.py)
- [digital_twin.py](digital_twin.py)
- [electrothermal_sharing.py](electrothermal_sharing.py)
- [em_body_heating.py](em_body_heating.py)
- [em_network_ac.py](em_network_ac.py)
- [em_network_resistor_cht.py](em_network_resistor_cht.py)
- [em_network_resistor_thermal.py](em_network_resistor_thermal.py)
- [em_spice_coupling.py](em_spice_coupling.py)
- [em_spice_coupling_circuit.py](em_spice_coupling_circuit.py)
- [field_circuit_cosim.py](field_circuit_cosim.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
