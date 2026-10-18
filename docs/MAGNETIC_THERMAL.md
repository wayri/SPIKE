<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental planar magnetic and thermal coupling

`python/spike_core/magnetic_thermal.py` provides isotropic heat conduction on
a fixed planar triangular mesh extruded through a uniform stack depth. It also
couples that thermal step to the stationary-conductor eddy step described in
[MAGNETIC_FEM.md](MAGNETIC_FEM.md). This is an experimental numerical slice,
not complete rotating-machine or solenoid qualification.

The derivation, implementation and test oracles were independently authored.
No third-party source, examples, mesh or data were consulted or adapted.
Knowledgeable human review is required before releasing numerical code.

## Thermal API

`solve_thermal_step` takes keyword arguments:

- `nodes_m`, `triangles`, `region_ids`, `stack_depth_m`: the same SI mesh
  conventions as the magnetic kernel.
- `materials`: exactly one entry per region, with positive scalar
  `k_w_m_k`, `rho_kg_m3`, `cp_j_kg_k`.
- `previous_temperature_k`: N temperatures in (0,10000] K.
- `time_step_s`: positive timestep.
- `element_power_w`: M finite, nonnegative **integrated element watts**.
  These are not volumetric source densities.
- `convection_edges`: optional list of objects with `nodes: [i,j]`,
  positive `h_w_m2_k`, and `ambient_temperature_k` in (0,10000] K.
  Every named pair must be a unique exterior mesh edge.
- `dirichlet_temperature_k`: optional integer node-to-temperature mapping.
- `lumped_capacity`: false by default; true selects row-summed capacity.

Unspecified boundaries are adiabatic. Convection acts only on the rectangular
extruded face belonging to the explicitly named edge. There is no implicit
cooling on the front/back stack faces. The mesh is capped at 20,000 nodes and
40,000 triangles. Connectivity, degeneracy, duplicate triangles, unused nodes,
and nonmanifold edges are checked; arbitrary overlapping CAD elements are not
independently certified by this kernel.

`PlanarThermalOperator` accepts mesh/material/boundary arguments once.
Its `step(previous_temperature_k, time_step_s, element_power_w)` method
reuses those immutable matrices.

The result contract is `spike/planar-thermal-step-result/v1`, with
`temperature_k`, `element_mean_temperature_k`, `element_power_w`,
`nodal_heat_capacity_j_per_k`, `capacity_form`, free residual norm and
`heat_audit`. Audit fields are `input_energy_j`,
`stored_energy_change_j`, `convection_energy_out_j`,
`prescribed_temperature_energy_in_j`, and `balance_residual_j`.
Positive convection means heat leaving the solid; negative convection means
ambient heat enters. Prescribed-temperature exchange is signed positive inward.

## Thermal derivation

The extruded planar heat equation is

`rho*cp*dT/dt - div(k*grad T) = q`.

Galerkin P1 elements yield conductivity
`K_e = depth*area*k*(grad N_i dot grad N_j)` and consistent capacity
`C_e = depth*area*rho*cp*(ones(3,3)+I)/12`.
Capacity row summation gives the optional lumped diagonal matrix.

For each element, depositing its supplied power equally as `P_e/3`
preserves total watts exactly. P1 barycentric mean temperature is the arithmetic
mean of its three nodal values. A convective exterior edge of length L has

`K_edge = h*depth*L*[[2,1],[1,2]]/6`,
`f_edge = h*depth*L*T_ambient*[1,1]/2`.

Backward Euler solves
`(C/dt + K + K_conv) T_new = C*T_old/dt + f_power + f_ambient`.
Essential values are eliminated. Temperature excursions outside (0,10000] K
and nonfinite or failed linear residuals withhold the result. This method is
unconditionally stable for the linear parabolic model; that is not a claim of
time accuracy or nodal monotonicity on arbitrary meshes. Consistent capacity
and obtuse elements can yield local overshoots. Strong coefficient contrast
and near-degenerate geometry remain conditioning concerns.

Summing nodal equations gives

`input energy + prescribed-temperature energy in =
stored energy change + convection energy out`.

Storage is `1.T*C*(T_new-T_old)`; convection and reaction energies use the
new-time flux multiplied by dt, matching backward Euler. The returned balance
residual retains floating-point error rather than replacing it with zero.

## Fixed-mesh magnetic coupling

`simulate_magnetic_thermal` takes:

- shared mesh arguments and `stack_depth_m`;
- `magnetic_materials`, `thermal_materials`;
- `dirichlet_a_wb_per_m`, `initial_a_wb_per_m`,
  `initial_temperature_k`, `time_step_s`, `steps`;
- optional `conductivity_temperature_coefficients`, mapping magnetic region
  IDs to `{alpha_per_k, reference_temperature_k}`;
- optional `current_density_a_per_m2`, `winding_element_loss_w`,
  `convection_edges`, `dirichlet_temperature_k`,
  `lumped_capacity`, `snapshot_stride`.

The magnetic region's supplied conductivity is its reference conductivity.
At each step, compute the previous volume-weighted regional mean temperature,
then

`sigma = sigma_ref / (1 + alpha*(T_mean-T_reference))`.

The denominator and resulting conductivity must remain finite and positive.
Regions without a coefficient retain their reference conductivity. Magnetic
permeability, B-H curves, PM remanence, thermal conductivity, density and heat
capacity remain fixed. This is a region-mean conductivity model: it does not
represent conductivity variation within one region.

The magnetic step advances first on the unchanged mesh. Its actual integrated
`element_joule_loss_w` is added to explicitly supplied additional winding
watts, then deposited into the thermal solve. No Joule loss is inferred from
displayed B. Additional winding watts are an independent user-supplied heat
source; the caller must avoid double-counting winding eddy loss and must supply
its own circuit-loss provenance.

The returned `spike/planar-magnetic-thermal-result/v1` includes:

- `history`: initial time/A/T, followed by selected time/A/T/B/Joule/power
  snapshots; final state is always included;
- `step_audits`: every step's magnetic and thermal energy audits, eddy Joule
  energy, additional winding energy, and actually used regional conductivity;
- `final_magnetic_result`, `final_thermal_result`;
- explicit experimental status and validity limitations.

At most 1,000 steps, 20 million node-steps, one million retained field-history
values, and one million regional conductivity audit entries are admitted.
Changing snapshot stride reduces output retention, not numerical timesteps.
The wrapper neither mutates inputs nor maintains hidden integration state.

Sequential previous-temperature feedback is first order and needs coupling
timestep refinement. Backward-Euler numerical magnetic dissipation remains
separate from physical Joule heat. It must not be deposited as thermal energy.
The initial magnetic state and static source/Dirichlet drive belong to the
caller; there is no implicit circuit initialization or time-varying waveform
synthesis.

## Verification

Run:

`build/qualification-py311/Scripts/python.exe -B -m unittest tests.python.test_magnetic_thermal -v`

Nine tests cover exact uniform adiabatic heating and conservative deposition
for both capacity choices; an exact linear slab with convection and prescribed
temperature work; Fourier backward-Euler spatial refinement; independently
assembled generalized-eigenmode exponential time refinement; rejection of
interior convection and negative losses; exact user-winding heat and
temperature/conductivity feedback; actual eddy-loss-to-thermal energy transfer;
coupled timestep refinement; and invalid feedback/resource limits.

These tests verify mathematical and numerical contracts. They do not establish
material accuracy, machine loss correlation, CFD, radiation, axial conduction,
3D end effects, motion, hysteresis, PM temperature/demagnetization behavior, or
production qualification. Mesh, air-box, thermal-boundary and coupling-step
convergence and independent device evidence remain necessary.

