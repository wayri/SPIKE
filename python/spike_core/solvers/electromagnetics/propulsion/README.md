<!-- SPDX-License-Identifier: Apache-2.0 -->
# Electromagnetics / Propulsion

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/electromagnetics/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [propulsion_pod.py](propulsion_pod.py)
- [propulsion_pod_annular_gap.py](propulsion_pod_annular_gap.py)
- [propulsion_pod_cfd_refinement.py](propulsion_pod_cfd_refinement.py)
- [propulsion_pod_controller.py](propulsion_pod_controller.py)
- [propulsion_pod_convergence.py](propulsion_pod_convergence.py)
- [propulsion_pod_energy_step.py](propulsion_pod_energy_step.py)
- [propulsion_pod_energy_table.py](propulsion_pod_energy_table.py)
- [propulsion_pod_field.py](propulsion_pod_field.py)
- [propulsion_pod_field_preview.py](propulsion_pod_field_preview.py)
- [propulsion_pod_geometry_loop.py](propulsion_pod_geometry_loop.py)
- [propulsion_pod_geometry_run.py](propulsion_pod_geometry_run.py)
- [propulsion_pod_inertial_cfd.py](propulsion_pod_inertial_cfd.py)
- [propulsion_pod_inertial_cfd_case.py](propulsion_pod_inertial_cfd_case.py)
- [propulsion_pod_inertial_cfd_coarsen.py](propulsion_pod_inertial_cfd_coarsen.py)
- [propulsion_pod_inertial_cfd_current.py](propulsion_pod_inertial_cfd_current.py)
- [propulsion_pod_inertial_cfd_foil.py](propulsion_pod_inertial_cfd_foil.py)
- [propulsion_pod_inertial_cfd_forcing.py](propulsion_pod_inertial_cfd_forcing.py)
- [propulsion_pod_inertial_cfd_geometry.py](propulsion_pod_inertial_cfd_geometry.py)
- [propulsion_pod_inertial_cfd_geometry_screen.py](propulsion_pod_inertial_cfd_geometry_screen.py)
- [propulsion_pod_inertial_cfd_inexact.py](propulsion_pod_inertial_cfd_inexact.py)
- [propulsion_pod_inertial_cfd_linear.py](propulsion_pod_inertial_cfd_linear.py)
- [propulsion_pod_inertial_cfd_memory.py](propulsion_pod_inertial_cfd_memory.py)
- [propulsion_pod_inertial_cfd_preflight.py](propulsion_pod_inertial_cfd_preflight.py)
- [propulsion_pod_inertial_cfd_pressure_pin.py](propulsion_pod_inertial_cfd_pressure_pin.py)
- [propulsion_pod_inertial_cfd_schur.py](propulsion_pod_inertial_cfd_schur.py)
- [propulsion_pod_inertial_cfd_stl.py](propulsion_pod_inertial_cfd_stl.py)
- [propulsion_pod_inertial_cfd_supg.py](propulsion_pod_inertial_cfd_supg.py)
- [propulsion_pod_inertial_cfd_surface_repair.py](propulsion_pod_inertial_cfd_surface_repair.py)
- [propulsion_pod_jacobian_schur.py](propulsion_pod_jacobian_schur.py)
- [propulsion_pod_load_table.py](propulsion_pod_load_table.py)
- [propulsion_pod_magnetic_indicator.py](propulsion_pod_magnetic_indicator.py)
- [propulsion_pod_magnetic_p2.py](propulsion_pod_magnetic_p2.py)
- [propulsion_pod_modal_gap.py](propulsion_pod_modal_gap.py)
- [propulsion_pod_nonlinear_motor.py](propulsion_pod_nonlinear_motor.py)
- [propulsion_pod_nonlinear_p2.py](propulsion_pod_nonlinear_p2.py)
- [propulsion_pod_nonlinear_port.py](propulsion_pod_nonlinear_port.py)
- [propulsion_pod_propeller.py](propulsion_pod_propeller.py)
- [propulsion_pod_real_motor.py](propulsion_pod_real_motor.py)
- [propulsion_pod_real_motor_domains.py](propulsion_pod_real_motor_domains.py)
- [propulsion_pod_real_motor_extract.py](propulsion_pod_real_motor_extract.py)
- [propulsion_pod_real_motor_p2.py](propulsion_pod_real_motor_p2.py)
- [propulsion_pod_rotor_cfd.py](propulsion_pod_rotor_cfd.py)
- [propulsion_pod_rotor_cfd_geometry.py](propulsion_pod_rotor_cfd_geometry.py)
- [propulsion_pod_separated_motor.py](propulsion_pod_separated_motor.py)
- [propulsion_pod_thermal.py](propulsion_pod_thermal.py)
- [propulsion_pod_three_phase.py](propulsion_pod_three_phase.py)
- [propulsion_pod_three_phase_controller.py](propulsion_pod_three_phase_controller.py)
- [propulsion_pod_three_phase_field.py](propulsion_pod_three_phase_field.py)
- [propulsion_pod_three_phase_run.py](propulsion_pod_three_phase_run.py)
- [propulsion_pod_transport_contractions.py](propulsion_pod_transport_contractions.py)
- [propulsion_pod_vesc_binding.py](propulsion_pod_vesc_binding.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
