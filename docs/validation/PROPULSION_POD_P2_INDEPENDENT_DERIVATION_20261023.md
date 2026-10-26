<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independently derived quadratic magnetic field formulation

23 October 2026. This derivation is authored by the integration owner before
reviewing the separate worker's P2 implementation. That worker previously
reviewed other modules; its forthcoming P2 source is not independently reviewed
merely because its author previously served as a reviewer.

The shape-function reference is Yijun Liu, University of Cincinnati,
[Introduction to the Finite Element Method, 2015 notes, section 3](https://www.yijunliu.com/Teaching/Intro_FEM/FEM_Lecture_Notes_Liu_2015.pdf).
Only the established mathematical basis is used; no external implementation is
copied or adapted. The magnetic energy/virtual-work source remains Haus and
Melcher, Electromagnetic Fields and Energy, section 11.7, cited in the full-loop
review. This specialization, its integration formulas and its oracles are
independently derived here.

On an affine triangle, barycentric coordinates lambda_i are linear with constant
gradients g_i and sum to one. Define vertex functions
N_i=lambda_i(2 lambda_i-1) and shared edge functions N_ij=4 lambda_i lambda_j.
Then grad N_i=(4 lambda_i-1)g_i and
grad N_ij=4(lambda_i g_j+lambda_j g_i). These functions reproduce every quadratic
polynomial and their gradients reproduce every linear gradient exactly. Shared
edge midpoint identities enforce conformity; no separate unknown is created
for the same physical mesh edge.

For Az in Wb/m, B=(partial_y Az,-partial_x Az) in tesla. With positive symmetric
reluctivity nu in A/(T m), prescribed Br in tesla, current density Jz in A/m^2
and stack depth l in m, the discrete potential is

```
Pi(a)=l sum_e integral_e [.5(B-Br)^T nu (B-Br)-Jz Az] dA.
K_ij=l integral curl(N_i)^T nu curl(N_j) dA,
f_i=l integral [curl(N_i)^T nu Br+Jz N_i] dA.
```

The positive PM reference .5 integral Br^T nu Br is retained. The field energy
is the first term of Pi, not Pi itself; coenergy is i^T lambda minus that field
energy. Source and linkage must use the same signed winding loading. For a
constant winding chi on each source triangle,
lambda_phase=l sum_e integral chi_phase Az dA.

Three equal quadrature weights area/3 at permutations of (2/3,1/6,1/6)
integrate all degree-two polynomials exactly. Thus linear-material K, PM load,
J load and energy are exact for the affine finite-dimensional basis. This does
not establish geometric or physical accuracy. Vertex shape integrals are zero;
each edge shape integral is area/3. Derivation follows from
integral lambda_1^a lambda_2^b lambda_3^c dA =
2 area a!b!c!/(a+b+c+2)!, not a borrowed quadrature implementation.

For an affine P1 mesh-motion field, its gradient is constant per triangle.
P2 B is linear and vacuum Maxwell stress is quadratic, so the same three-point
rule exactly integrates T:grad(u) on whole source triangles. An annulus clips
triangles; its quadrature must evaluate the original P2 field at each clipped
quadrature point using original barycentric coordinates. Using a cell-mean B
would defeat the higher-order force calculation. Annular radius factors need
their own quadrature refinement and geometric coverage checks.

Independent oracles: A=x^2-y^2 with quadratic boundary values solves the zero-J,
uniform-mu problem exactly; A=x^2+y^2 requires J=-4 nu in the same convention.
Both must reproduce interior potential and linear B, including midside values.
Check nonzero Dirichlet elimination, every-component gauge, orientation reversal,
PM energy reference, full winding reciprocity and common-field virtual work.
Nonlinear steel and directional source-specific material qualification are not
established by this linear P2 extension. Actual motor mesh/torque convergence
must still be executed and recorded before admission to the demonstration.
