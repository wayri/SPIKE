<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thermal Fluid / Flow

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/thermal-fluid/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [assembly_airflow.py](assembly_airflow.py)
- [assembly_airflow_admission.py](assembly_airflow_admission.py)
- [assembly_airflow_mesh.py](assembly_airflow_mesh.py)
- [assembly_airflow_runtime.py](assembly_airflow_runtime.py)
- [cfd_reference_correlation.py](cfd_reference_correlation.py)
- [cfd_tetra_cht.py](cfd_tetra_cht.py)
- [cfd_tetra_energy.py](cfd_tetra_energy.py)
- [cfd_tetra_intersections.py](cfd_tetra_intersections.py)
- [cfd_tetra_mesh.py](cfd_tetra_mesh.py)
- [cfd_tetra_stokes.py](cfd_tetra_stokes.py)
- [enclosure_cht.py](enclosure_cht.py)
- [enclosure_cht_v2.py](enclosure_cht_v2.py)
- [enclosure_energy.py](enclosure_energy.py)
- [enclosure_flow_analysis.py](enclosure_flow_analysis.py)
- [enclosure_laminar.py](enclosure_laminar.py)
- [enclosure_rans_research.py](enclosure_rans_research.py)
- [enclosure_rectilinear_momentum.py](enclosure_rectilinear_momentum.py)
- [enclosure_refinement.py](enclosure_refinement.py)
- [enclosure_rotating_frame.py](enclosure_rotating_frame.py)
- [enclosure_sa_transport.py](enclosure_sa_transport.py)
- [enclosure_stokes.py](enclosure_stokes.py)
- [enclosure_symmetric_stress.py](enclosure_symmetric_stress.py)
- [fan_system_operating_point.py](fan_system_operating_point.py)
- [internal_airflow.py](internal_airflow.py)
- [laminar_channel_cht.py](laminar_channel_cht.py)
- [native_airflow.py](native_airflow.py)
- [native_cht.py](native_cht.py)
- [native_cht_result.py](native_cht_result.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
