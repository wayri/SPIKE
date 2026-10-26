<!-- SPDX-License-Identifier: Apache-2.0 -->
# Power Integrity / Pdn

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/power-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [benchmark_pdn.py](benchmark_pdn.py)
- [capacitor_placement.py](capacitor_placement.py)
- [pdn.py](pdn.py)
- [pdn_admittance_reduction.py](pdn_admittance_reduction.py)
- [pdn_decap_corners.py](pdn_decap_corners.py)
- [pdn_decap_selection.py](pdn_decap_selection.py)
- [pdn_dielectric_ac.py](pdn_dielectric_ac.py)
- [pdn_dielectric_feedback.py](pdn_dielectric_feedback.py)
- [pdn_dielectric_thermal.py](pdn_dielectric_thermal.py)
- [pdn_dielectric_thermomechanical.py](pdn_dielectric_thermomechanical.py)
- [pdn_electrostatic.py](pdn_electrostatic.py)
- [pdn_network.py](pdn_network.py)
- [pdn_series_capacitors.py](pdn_series_capacitors.py)
- [pdn_shunt_capacitance.py](pdn_shunt_capacitance.py)
- [quasistatic_capacitance.py](quasistatic_capacitance.py)
- [quasistatic_copper_area.py](quasistatic_copper_area.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
