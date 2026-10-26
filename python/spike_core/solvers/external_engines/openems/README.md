<!-- SPDX-License-Identifier: Apache-2.0 -->
# External Engines / Openems

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/external-engines/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [openems_adapter_source.py](openems_adapter_source.py)
- [openems_assembly_geometry.py](openems_assembly_geometry.py)
- [openems_benchmarks.py](openems_benchmarks.py)
- [openems_case_integrity.py](openems_case_integrity.py)
- [openems_geometry_admission.py](openems_geometry_admission.py)
- [openems_stopping.py](openems_stopping.py)
- [openems_validation.py](openems_validation.py)
- [openems_validation_evidence.py](openems_validation_evidence.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
