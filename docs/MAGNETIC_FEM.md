<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental planar magnetic FEM

`python/spike_core/magnetic_fem.py` provides a planar, triangular P1 magnetic
vector-potential operator, a nonlinear magnetostatic solve, and a separate
stationary-conductor backward-Euler eddy step. These are numerical verification
increments. They do not qualify an arbitrary machine or a geometry compiler.

The derivation, code and fixtures were independently authored from the
equations below. No third-party implementation, example, mesh, or dataset was
consulted or adapted. This is a classical variational discretization, not a new
research algorithm. Numerical code requires knowledgeable human review before
release.

## Public Python interface

`solve_magnetostatic` takes keyword arguments:

- `nodes_m`: finite N by 2 Cartesian coordinates in metres.
- `triangles`: M by 3 integer node indices, either orientation.
- `region_ids`: M nonempty string IDs.
- `materials`: exactly one entry per used region, with either positive `mu_r`
  (alias `relative_permeability`) or `bh_curve: [[B_t,H_a_per_m],...]`.
  A curve begins at [0,0] and is strictly increasing in both columns.
  Optional `remanence_t: [Bx,By]` is accepted only with linear permeability.
  Optional nonnegative `conductivity_s_m` is metadata in magnetostatics.
- `stack_depth_m`: positive uniform depth; only integrated quantities use it.
- `dirichlet_a_wb_per_m`: dictionary of integer node indices to Az values.
  Every connected mesh component needs an essential boundary/gauge.
- `current_density_a_per_m2`: optional region-to-Jz dictionary or M-element
  sequence. Missing dictionary regions use zero.
- `relative_tolerance`, `absolute_tolerance_a`, `maximum_iterations`:
  defaults 1e-9, 1e-10 A, 60. Relative tolerance is at most 0.01; iteration
  count is bounded to 1..200.

Unspecified boundary edges use the natural weak boundary condition. The caller
must identify an appropriate outer air boundary and demonstrate air-box
convergence. The kernel checks indices, degeneracy, duplicate triangles and
unused nodes; it does not prove a non-overlapping, manifold CAD discretization.

Result `spike/planar-magnetostatic-result/v1` contains:

- `potential_a_wb_per_m` (N), `element_b_t` and `element_h_a_per_m` (M by 2);
- `element_area_m2`, `element_region_ids`;
- `element_magnetic_energy_density_j_per_m3` and the corresponding
  `element_magnetic_coenergy_density_j_per_m3`;
- `magnetic_energy_j`, `magnetic_coenergy_j`, `dirichlet_reaction_a`;
- `convergence` with residual history, threshold, iteration count and status;
- `joule_loss_w: null`, `joule_loss_status: not_solved`.

The nodal/element ordering is exactly the caller's ordering. Metadata explicitly
retains experimental status and false production qualification. Failure to
converge raises ValueError and withholds a result.

## Static weak form and tangent

With Az(x,y), B = (partial_y Az, -partial_x Az), in tesla. Define the material
potential density w(B) by H = partial_B w. Ampere's equation gives

`integral curl(v) dot H dS = integral v Jz dS`.

The per-depth functional is `Pi(a) = integral w(B(a)) dS - f dot a`.
On a triangle, the P1 shape-function gradients and B are constant.
Area is the absolute signed determinant divided by two; gradients retain the
signed determinant. Thus element orientation does not change the physics.
The assembled residual is `sum area*C.T*H - f` and tangent is
`sum area*C.T*D*C`, where columns of C are curls of shape functions.
A constant Jz source has consistent nodal load `area*Jz/3`.

For linear recoil permeability mu = mu0*mu_r and constant Br,

`H = (B-Br)/mu`, `D = I/mu`,
`w = |B|^2/(2*mu) - Br dot B/mu`.

The declared engineering value is mu0 = 4*pi*1e-7 H/m. For an isotropic
single-valued B-H curve h(b), with b=|B|,

`H = (h(b)/b) B`,
`D = (h/b) I + (dh/db-h/b) u u.T`,
`w = integral_0^b h(s) ds`.

At zero, D is the first segment slope times I. Segment integrals are exact
trapezoids plus the exact quadratic partial-segment integral. The differential
tangent uses the right segment at knots; Newton is piecewise smooth. There is
no extrapolation past the supplied B-H range. Strictly positive slopes give
a convex potential and a positive tangent after gauge elimination.

The solver starts from the harmonic interpolation of prescribed boundary
values to avoid an artificial zero-interior boundary layer. Newton uses a
sparse tangent solve and bounded potential-decrease line search. Convergence
requires the free-node residual norm to meet `atol + rtol*initial_residual`.
A 64-machine-epsilon potential comparison allowance handles objective
roundoff; it does not relax residual convergence. Excessive material contrast,
thin triangles and coordinate scales can still cause conditioning failure.
A harmonic initial field outside a supplied B-H range is rejected; there is
no guarantee of convergence for every admissible physical solution.

## Energy interpretation

All potentials use the explicit reference w(B=0)=0.
Coenergy density is `H dot B - w`. Integrals include the declared stack depth.
The ideal-PM potential w can be negative: it includes the fixed remanent source.
It is not a claim of complete physical stored energy inside a real magnet,
its hysteresis, demagnetization, or temperature-dependent state.

Force/torque extraction must preserve the prescribed-excitation and boundary
source-work convention. For homogeneous zero outer Az, stationary weak-form
work identifies the integrated coenergy with the reduced fixed-current
functional. Nonzero prescribed boundaries also exchange work; differentiating
an isolated material energy is not a general force law. This module does not
extract forces or torque.

## Stationary-conductor eddy step

`solve_eddy_current_step` takes the same mesh/material/Dirichlet/source
arguments, plus `previous_a_wb_per_m` and positive `time_step_s`.
Its default absolute tolerance is 1e-9 A. At least one region must have
positive conductivity. Each conductive region is assumed to be one isolated
axial circuit; disconnected region meshes must be split into separate IDs.
Region topology and conductivity must remain fixed across steps.

For each conductive region r, use a constant axial electric offset Ez_r.
Then `E_z = -dAz/dt + Ez_r`, `J_induced = sigma*E_z`, and require
`integral_region J_induced dS = 0`. This removes spurious gauge-dependent
current and heating. Impressed Jz, if supplied, remains a separate source.

Backward Euler uses delta_a=a_new-a_old, eta_r=dt*Ez_r, consistent conductivity
mass M, coupling C_ir=integral_region sigma*N_i dS, and
S_rr=integral_region sigma dS. Newton solves the sparse symmetric blocks

`[K + M/dt, -C/dt; -C.T/dt, S/dt]`

against residual `[r_mag + (M*delta_a-C*eta)/dt;
(-C.T*delta_a+S*eta)/dt]`, after eliminating prescribed Az nodes.
Regional offsets are solved jointly, without creating a dense rank-one
elimination matrix. Conductivity is piecewise constant and at most 1,024
conductive regions are admitted.

Electric field is P1 within each triangle. Joule watts are integrated exactly:

`depth*sigma*area*(sum(E_i^2)+(sum E_i)^2)/12`.

The result `spike/planar-eddy-step-result/v1` retains static-compatible
potential, B/H, region, area and energy fields, plus:

- `element_electric_field_z_nodal_v_per_m` (M by 3 in triangle-node order);
- `element_induced_current_density_z_a_per_m2` (element mean);
- `region_electric_offset_v_per_m`, `region_net_induced_current_a`;
- `element_joule_loss_w`, `joule_loss_w`, and solved-fixed-conductor status;
- `energy_audit` with magnetic-energy change, Joule energy, source/boundary
  work, backward-Euler numerical dissipation and balance residual.

The discrete identity is
`input work = Delta W + dt*Q_joule + D_BE`.
Here `D_BE=integral(w_old-w_new+H_new dot (B_new-B_old)) dV` is the
nonnegative convexity defect. It is numerical damping, never physical heat.
Dirichlet reaction work is included. This audit assumes unchanged material
laws and remanence across the step.

No moving-conductor v cross B, sliding mesh, remesh transfer, end-current
closure, 3D scalar electric potential, hysteresis, temperature feedback,
drive-circuit evolution or mechanical equation is solved. Zero net induced
current is appropriate for the declared isolated axial circuits; it is not a
general winding or interconnected conductor model.

## Independent verification

Run:

`build/qualification-py311/Scripts/python.exe -B -m unittest tests.python.test_magnetic_fem -v`

Twelve checks cover:

1. Manufactured A=x(1-x)+y(1-y), Jz=4/mu: exact structured-grid nodal solution
   and first-order B refinement on 4, 8, 16 divisions.
2. Affine PM B=Br, H=0, and the declared energy/coenergy reference.
3. Two nonlinear layers at common H=100 A/m, B=0.2/0.15 T; independently
   integrated exact energies and a nontrivial Newton solve.
4. Material and assembled directional derivatives.
5. Reversed triangle orientation, depth scaling and per-element excitation.
6. Rejection of invalid materials, mesh, gauge, extrapolation and
   unconverged results.
7. Fourier mode sin(2*pi*x)*sin(pi*y): analytical backward-Euler resolvent
   spatial convergence and net-current/energy closure.
8. Separately assembled dense generalized eigenmode: exact discrete BE
   recurrence and first-order convergence toward the matrix-exponential decay.
9. Pure Az gauge shift: compensating Ez and zero induced heat.
10. Missing conductivity and malformed previous-state rejection.

The affine PM test explicitly uses 1e-9 A absolute tolerance: even its exact
analytical nodal values produce approximately 1.44e-10 A assembled residual
from floating-point cancellation. The potential-derivative test uses a 1e-5 T
directional step to avoid subtractive cancellation, while retaining a 2e-9
relative criterion.

Passing tests establish the listed mathematical limits. Machine CAD,
air-boundary convergence, force-contour convergence, skin-depth resolution,
measured material accuracy and device correlation remain separate evidence.
