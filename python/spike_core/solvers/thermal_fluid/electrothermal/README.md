<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thermal Fluid / Electrothermal

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/thermal-fluid/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [assembly_electrothermal.py](assembly_electrothermal.py)
- [assembly_electrothermal_setup.py](assembly_electrothermal_setup.py)
- [electrical_heat_sources.py](electrical_heat_sources.py)
- [energy_balanced_heat.py](energy_balanced_heat.py)
- [multiboard_volume_electrothermal.py](multiboard_volume_electrothermal.py)
- [multiboard_volume_electrothermal_setup.py](multiboard_volume_electrothermal_setup.py)
- [pcb_electrothermal_geometry.py](pcb_electrothermal_geometry.py)
- [pwm_electrothermal.py](pwm_electrothermal.py)
- [pwm_volume_electrothermal.py](pwm_volume_electrothermal.py)
- [structured_electrothermal.py](structured_electrothermal.py)
- [transient_resistive_electrothermal.py](transient_resistive_electrothermal.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
