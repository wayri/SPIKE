<!-- SPDX-License-Identifier: Apache-2.0 -->
# Electromagnetics / Machines

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/electromagnetics/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [actuator_force_map.py](actuator_force_map.py)
- [actuator_motion.py](actuator_motion.py)
- [em_machines.py](em_machines.py)
- [machine_geometry.py](machine_geometry.py)
- [magnetic_fem.py](magnetic_fem.py)
- [magnetic_machine_study.py](magnetic_machine_study.py)
- [magnetic_thermal.py](magnetic_thermal.py)
- [voice_coil_drive.py](voice_coil_drive.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
