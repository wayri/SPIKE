<!-- SPDX-License-Identifier: Apache-2.0 -->
# Circuits / Models

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/circuits/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [benchmark_native_mna.py](benchmark_native_mna.py)
- [converter_study.py](converter_study.py)
- [multiboard_circuit.py](multiboard_circuit.py)
- [multiboard_circuit_bonds.py](multiboard_circuit_bonds.py)
- [native_circuit_compiler.py](native_circuit_compiler.py)
- [native_circuit_result.py](native_circuit_result.py)
- [native_mna.py](native_mna.py)
- [native_source_waveforms.py](native_source_waveforms.py)
- [semiconductor_operating_losses.py](semiconductor_operating_losses.py)
- [smps_converter.py](smps_converter.py)
- [spikes_native_adapter.py](spikes_native_adapter.py)
- [topology_circuit.py](topology_circuit.py)
- [transient_diode_field.py](transient_diode_field.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
