<!-- SPDX-License-Identifier: Apache-2.0 -->
# Electromagnetics / Fields

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/electromagnetics/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [antenna_measured_comparison.py](antenna_measured_comparison.py)
- [assembly_em.py](assembly_em.py)
- [assembly_em_board_geometry.py](assembly_em_board_geometry.py)
- [assembly_em_diagnostics.py](assembly_em_diagnostics.py)
- [assembly_em_grid.py](assembly_em_grid.py)
- [assembly_em_planar_mesher.py](assembly_em_planar_mesher.py)
- [assembly_em_study.py](assembly_em_study.py)
- [crossboard_field_screen.py](crossboard_field_screen.py)
- [emi.py](emi.py)
- [fdtd_completion.py](fdtd_completion.py)
- [huygens_far_field.py](huygens_far_field.py)
- [mom_far_field.py](mom_far_field.py)
- [mom_singular_source.py](mom_singular_source.py)
- [mom_surface_basis.py](mom_surface_basis.py)
- [multi_excitation_network.py](multi_excitation_network.py)
- [multiboard_em.py](multiboard_em.py)
- [multiboard_radiation.py](multiboard_radiation.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
