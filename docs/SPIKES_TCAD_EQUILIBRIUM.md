<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native semiconductor-field subsystem: first TCAD increment

## Current executable scope

`src/spikes/tcad_equilibrium.cpp` is an original C++ 1D equilibrium
Poisson-Boltzmann solver with a static library and native console. It is separate
from circuit MNA and PDK compact-model execution. It supports a uniform,
homogeneous material, constant temperature, nondegenerate Boltzmann carriers,
fully ionized prescribed net doping and one constant Fermi level. It does not
solve transport, biased I-V, geometry/process evolution or full TCAD.

Users supply relative permittivity, intrinsic carrier density, temperature,
length and a signed `ND-NA` profile in m^-3. A material name is not required.
This allows new parameter sets, but does not establish the physical validity of
diamond, heterostructures or other future materials. Ni is held constant at the
specified temperature; no temperature law or ionization fraction is inferred.
The console's illustrative defaults are not a PDK or manufacturer model.

## Equations, units and original derivation

Let `Vt = kB*T/q`, `u=phi/Vt`, `n=ni*exp(u)`, `p=ni*exp(-u)`,
`rho=q*(p-n+ND-NA)` and `epsilon=epsilon0*epsilon_r`. Solve
`-d(epsilon*dphi/dx)/dx = rho`, with Dirichlet contacts. The equilibrium
quasineutral contact convention is `u_contact=asinh((ND-NA)/(2*ni))`.
Explicit contacts in the C++ API remain electrostatic conditions at the same
Fermi level; they are not an applied-bias transport model.

On a uniform grid with spacing h and density scale Ns=max(ni,max|ND-NA|), the
dimensionless finite-volume residual at an interior node is

`F_i=A*(2*u_i-u_(i-1)-u_(i+1))+(n_i-p_i-(ND-NA)_i)/Ns`,

where `A=epsilon*Vt/(q*Ns*h^2)`. The Newton Jacobian has diagonal
`2*A+(n_i+p_i)/Ns` and off-diagonals `-A`. Dirichlet boundaries make this
positive definite in the admitted range. Checked tridiagonal elimination
uses O(N) work/storage per Newton step; no dense matrix, Python evaluation,
GPU transfer or unsafe fast-math is introduced. Residual-decreasing backtracking
accepts only finite states and is limited to 40 halvings per iteration.

Face fields are `E_(i+1/2)=-(phi_(i+1)-phi_i)/h`. The local flux balance gives
`epsilon*(E_(i+1/2)-E_(i-1/2))/h=rho_i`; tests also sum this relation across
interior control volumes. Reported charge/carriers are C/m^3 and m^-3, field
is V/m, potential V, coordinates m. Face fields, rather than averaged nodal
fields, are authoritative for the finite-volume conservation test.

This is a clean-room discretization and implementation; no external solver
source or semiconductor model coefficients were imported. The semiconductor
equation hierarchy is documented by
[TU Wien device-simulation research](https://www.iue.tuwien.ac.at/phd/vitanov/node43.html).
Constants use exact SI q and kB and the explicitly pinned
[2018 CODATA vacuum permittivity](https://physics.nist.gov/cuu/pdf/all_2018.pdf)
for reproducibility, not a claim to the latest constant adjustment.

## Build and use

```powershell
cmake --build build-spikes-native-analysis-20261013 --config Release --target spikes_tcad_console test_spikes_tcad_equilibrium -j 8
ctest --test-dir build-spikes-native-analysis-20261013 -C Release -R test_spikes_tcad_equilibrium --output-on-failure
build-spikes-native-analysis-20261013/Release/spikes_tcad_console.exe --profile pn --grid 501 --output pn-equilibrium.json
```

`--help` lists material and geometry inputs. `--doping-file` reads exactly one
signed SI density per grid node from bounded whitespace-delimited text. Output
is actual native-computed JSON, including inputs, residual history, fields,
carriers, charge and unqualified status. New output files are created
exclusively; existing files are preserved. Exit 0 means the algebraic solve
converged, 3 is a retained nonconverged result, and 2 indicates invalid inputs,
unrepresentable quantities or a console I/O error. The C++ `Config/Result`
interface is available through `spikes_tcad.lib`; no Python numerical kernel
or device-family switch is needed.

## Evidence and conditioning limits

Native tests cover intrinsic/doped neutrality, mass action, PN symmetry and
built-in contact potential, explicit contacts, local/global Gauss conservation,
bounded iteration failure, invalid parameters and a continuous manufactured
solution. For `phi=.04*sin(pi*x/L)` the independently prescribed doping is
`2*ni*sinh(phi/Vt)+epsilon*(pi/L)^2*phi/q`. On 33/65/129 nodes, maximum potential
errors were approximately 8.85e-6/2.21e-6/5.54e-7 V and face-field errors
18.55/4.64/1.16 V/m: second-order mesh refinement. These are mathematical
oracles, not measured device data. A 401-node PN test converged in six accepted
steps with normalized residual about 1.83e-12.

Admission bounds are 3..100001 nodes, 1..1000 iterations, residual tolerance
1e-13..1e-3, and scaled spatial coefficient A in [1e-14,1e12]. Finite carrier
representability is checked without clipping physical density or exponent.
Admission does not guarantee convergence or nondegenerate physical validity.
For a 65-node intrinsic fixture (ni=1e16 m^-3, L=1 um, contacts .03/.08 V),
tolerance 1e-11 encountered a floating-point floor around 3.4e-9 and returned
`line_search_failed`; the requirement was not relaxed to claim success.
Mesh error, statistics applicability and material evidence require separate
engineering review. Changing tolerance or physical scaling needs justification.

## Full TCAD roadmap, explicitly requested

Both circuit/PDK and device/process tracks are now in scope, but remain separate.
Next gates for native device TCAD are conservative electron/hole continuity
with Scharfetter-Gummel-type fluxes, mobility/recombination and contact models;
biased diode transport with analytical current/charge and conservation tests;
then nonuniform 1D and 2D material/oxide meshes, heterointerface conditions,
trapping, self-heating, degenerate statistics and high-field models. Device
charge/current extraction must produce fitted, qualified compact-model packages
with validity envelopes before circuit coupling is claimed.

Process TCAD additionally needs diffusion/activation, fabrication-step geometry
and calibrated process/material data. Quantum/ballistic models and new-material
parameters are further modules, not inferred from an open PDK. PDK layout,
DRC/LVS and parasitic extraction are toolchain adapters, not outputs of this
equilibrium kernel. Full device/process TCAD, HEMT MOS/BJT geometry simulation,
mixed-mode field/circuit coupling, graphical TCAD setup and semiconductor
qualification are still incomplete. Human numerical review is required before
release. No installers or installed application were updated.
