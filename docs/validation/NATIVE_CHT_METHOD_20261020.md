<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental native cavity conjugate energy, 20 October 2026

## Claim and physical model

This is an independently authored, bounded first CHT slice, not general CFD,
production-qualified conjugate heat transfer, or a replacement for the existing
airflow and thermal gates. The owned C++ implementation is `src/airflow/cht.*`;
`cht_main.cpp` is its standalone process boundary. Existing accepted MAC cavity
faces are exposed without changing the previous cavity executable's JSON fields.

The domain is two-dimensional, invariant per unit out-of-plane span. A square
fluid of side L occupies x/L in [0,1], y/L in [0,1]. Equal-thickness solid
strips occupy y/L in [-1/4,0] and [1,5/4]. All side walls are insulated.
The outside lower and upper solid faces have supplied temperatures hot_k and
cold_k. All fluid boundaries are impermeable, with the upper tangential lid
speed either Uref or zero. Mechanical lid motion is prescribed independently
of the steady, spatially fixed thermal strips; this idealized combination is
not a moving-solid heat transport calculation.

Assumptions: single-phase constant positive density rho [kg/m3], dynamic
viscosity mu [Pa s], heat capacity cp [J/(kg K)], and isotropic fluid/solid
conductivity kf, ks [W/(m K)]. The fluid is incompressible and Newtonian.
Temperature does not change momentum or material properties. No buoyancy,
viscous heating, pressure work, radiation, contact resistance, volumetric heat,
phase change, turbulence, rotor physics, compressibility, deforming geometry
or FSI is included. Thus momentum-to-energy coupling is one-way, while
solid/fluid temperature and conductive flux are solved in one common system.
Supplied material values are assumptions, not measured or certified material
laws. Constant-property applicability and negligible dissipation/buoyancy must
be justified for any proposed physical application.

## Primary source ledger

The following specific mathematical passages were reviewed on 2026-10-20.
They are foundations, not copied implementation or independent validation.

| Primary publisher and source | Version and reviewed portion | Application |
| --- | --- | --- |
| US DOE, *Fundamentals Handbook, Thermodynamics, Heat Transfer, and Fluid Flow*, [Volume 2](https://www.energy.gov/sites/default/files/2026-04/DOE-HDBK-1012-92_VOL2.pdf) | DOE-HDBK-1012/2-92, June 1992, Rev. 0; HT-02 printed pp. 6-11, rectangular Fourier law (2-4), equivalent resistance (2-6), and serial layers. These portions were read as extracted PDF text. | Conductive law and independent series-resistance oracle; SI conversion is derived here, not adopted from the handbook's customary-unit examples. |
| NIST, [Finite Volume Method](https://pages.nist.gov/fipy/en/stable/numerical/discret.html) | FiPy 4.0.3 documentation, last updated June 18 2026; CC-FVM; Convection Term (2), Diffusion Term (3) and center-distance derivative; Linear Equations (5)-(6). | Integral conservation and orthogonal cell/face representation. Only mathematical documentation informed this work; FiPy implementation/source was not inspected or used. |
| NIST, [Numerical Schemes](https://pages.nist.gov/fipy/en/stable/numerical/scheme.html) | Same documented version/date; positivity inequalities and upwind equation (3), with false-diffusion warning. | Positive neighbor coefficients and the explicit first-order advection accuracy limitation. |
| NASA Glenn, [Navier-Stokes Equations](https://www.grc.nasa.gov/www/k-12/airplane/nseqs.html) | Updated May 13 2021; displayed continuity, momentum and energy equations and Reynolds scaling. | Governing-law context for the existing cavity and the explicitly reduced passive energy equation; not a new qualification of inherited momentum numerics. |
| NASA NPARC Alliance, [Examining Spatial (Grid) Convergence](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html) | Introduction, Grid Considerations, Order of Grid Convergence, and Asymptotic Range sections of the retrieved page. | Refinement is solution-verification evidence and cannot alone establish physical validation. |

All new code, notation, prose, data structures and test inputs/oracles were
independently authored. No external solver source, implementation, mesh,
reference-value table or benchmark data was copied or adapted. Documentation
pages include API illustrations, but those were not used as code/source
material. No new runtime dependency or external data is distributed.

## Independent formulation

For steady thermal energy with the stated omissions, conservation of sensible
enthalpy and Fourier conduction give

```
fluid: div(rho cp u T - kf grad T) = 0
solid: div(-ks grad T) = 0
interface: T_s = T_f, (-ks grad T_s).n = (-kf grad T_f).n
```

Let X=x/L, V=u/Uref, theta=(T-Tcold)/(Thot-Tcold),
Re=rho Uref L/mu, Pe=rho cp Uref L/kf and K=ks/kf.
The dimensionless fluid energy flux is Pe V theta-grad(theta); in solid it
is -K grad(theta). A constant reference temperature drops out by continuity.
For equal boundary temperatures theta is defined as exactly zero, without
dividing by zero, and all dimensional heat flow is zero.

There are n by n fluid cells and n by n/4 cells in each solid strip, all
width h=1/n. Cell-center temperature is the sole thermal unknown. For a
neighbor pair P,N, integrating the two half-cell conductive resistances gives

```
D = h / ((h/2)/kP + (h/2)/kN) = 2 kP kN/(kP+kN)
q(P->N) = D (thetaP-thetaN) + F theta_upwind
F = Pe h V_face_normal
```

Here kP,kN are conductivity ratios to kf. Fluid-fluid F uses the actual
accepted cavity MAC face value; it never uses reconstructed cell velocity.
All solid faces and solid/fluid interfaces have F=0. At a temperature boundary
only half a cell remains, giving conductance 2K. Insulated faces contribute
zero. Each internal conductive or advective face contribution is shared with
opposite sign, giving exact pairwise cancellation in the assembled balance.

With outward F for cell P, the row equation is

```
sum_f (D_f + max(F_f,0)) thetaP
    - sum_internal_f (D_f + max(-F_f,0)) thetaN = boundary_source
```

No independent solid and fluid temperature copies are relaxed across an
interface. The returned interface value is recovered from that same series
resistance: thetaI=thetaLower-q/(2 kLower). Using either adjacent half-cell
therefore yields equal/opposite outward flux. Actual plus-y interface flux
is returned for each of the n faces, not an estimated heat-transfer coefficient.

The closed-form rest oracle follows independently from a constant heat
flux through layers of lengths 1/4,1,1/4 and conductivity K,1,K:
q=1/(1+1/(2K)). At height Y, theta=1-q R(Y), where R is the sum of traversed
layer length/conductivity. This continuum result is exactly representable
at the present cell centers. It tests material jumps and half-cell boundaries,
not merely the implementation's row formula.

## Iteration, conditioning, stopping and resource limits

The common five-point stencil is solved by forward then reverse Gauss-Seidel
traversals. Neighbor coefficients are nonnegative; positive boundary
conductances remove the constant thermal null mode. Exact divergence-free
fluid faces give a diagonally dominant irreducible system with the discrete
maximum principle. Actual MAC divergence is retained and checked by the
inherited momentum acceptance gate, rather than assumed zero or corrected by
altering mass flux. Roundoff divergence is a remaining consistency error.

Diffusion on an orthogonal uniform mesh is centered; upwind advection is
first order and introduces mesh-dependent numerical diffusion. Low residuals
and conservation do not bound this discretization error. Conditioning and
iteration count worsen with mesh refinement and conductivity contrast;
high Pe also demands refinement that the n<=64 envelope may not provide.
No claim covers the full admitted envelope's accuracy or convergence.

`thermal_residual_linf` is max(abs(A theta-b)/max(1,A_PP)), a dimensionless
row-scaled backward residual, not an error estimator or dimensional heat
balance. `balance_raw` is hot_flux-cold_flux; `balance_relative` divides its
absolute value by max(abs(hot_flux),abs(cold_flux),1e-30).
Acceptance requires both the row residual and relative boundary imbalance
to be at most thermal_tolerance. Accepted theta must also lie within
[-1e-8,1+1e-8] (or within [-1e-8,1e-8] for equal boundary temperatures).
No clipping manufactures the maximum-principle result.

Bounds are n divisible by four, 8..64; Re 1..400; lid exactly 0 or 1;
Pe 0..5000; K 0.01..100000; temperatures 1..10000 K with hot>=cold;
flow steps 1..200000 and inherited steady tolerance 1e-10..1e-3;
thermal iterations 1..200000 and thermal tolerance 1e-12..1e-4.
All real inputs must be finite. These are software/resource limits, not
validated physical ranges. In particular high-conductivity metals in
low-conductivity fluids can exhaust the iteration cap.

There are at most 6144 thermal cells. Storage is O(n^2) with five-point row
coefficients and no dense matrix, factorization or fill; each thermal
iteration is O(n^2). Worst-case thermal cell visits scale with 200000 times
6144, in addition to the existing separately capped pressure/flow work.
This is not a short wall-time guarantee. No kernel cancellation callback is
implemented; callers must supervise/terminate the standalone process.
Iteration exhaustion returns failed_to_converge with all accepted field
arrays empty. Invalid input/nonfinite state throws and CLI exits 2.

## Native process contract and SI recovery

Build and run:

```powershell
cmake -S src/airflow -B build/native-cht-20261020 -G "Visual Studio 18 2026"
cmake --build build/native-cht-20261020 --config Release
ctest --test-dir build/native-cht-20261020 -C Release --output-on-failure -V
build/native-cht-20261020/Release/spike_native_cht.exe 16 100 1 10 1 310 300 100000 1e-7 1e-9 100000
```

The eleven positional arguments are n, Re, lid, Pe, K, hotK, coldK,
max_flow_steps, steady_tolerance, thermal_tolerance, max_thermal_iterations.
All are echoed in `spike-native-cht-v1` JSON as `n`, `reynolds`, `lid`,
`peclet`, `solid_k_ratio`, `hot_k`, `cold_k`, `max_flow_steps`,
`steady_tolerance`, `thermal_tolerance`, `max_thermal_iterations`.
Status is converged or failed_to_converge. Rows=3n/2. Theta is row-major,
starting at the bottom-left thermal cell; fluid u,v,pressure retain the
existing n*n cell ordering. MAC face_u uses j*(n+1)+i, i=0..n,j=0..n-1;
face_v uses j*n+i, i=0..n-1,j=0..n.

Flow diagnostics are flow_steps, flow_time, flow_dt, divergence_linf,
steady_rate_linf and poisson_residual_linf in inherited dimensionless units.
Thermal diagnostics are thermal_iterations, thermal_residual_linf,
hot_flux, cold_flux, balance_raw, balance_relative, theta_min, theta_max.
Interface arrays are interface_bottom_theta, interface_top_theta,
interface_bottom_flux and interface_top_flux, each with n entries.

T=Tcold+(Thot-Tcold)*theta, x=L*(i+.5)/n and
y=L*((j+.5)/n-.25). Total heat flow per span [W/m] equals
kf*(Thot-Tcold)*hot_flux (or cold_flux). Interface heat-flux density [W/m2]
equals kf*(Thot-Tcold)/L*n*interface_flux. Interface temperatures use the
same theta-to-K conversion. Flow scales are u=Uref V, p=rho Uref^2 pstar.
For actual stationary fluid, a caller can use Uref=mu/(rho L), Re=1,
Pe=mu cp/kf, lid=0; actual Reynolds number is then zero, not the reference Re.

## Verification and unresolved validation

The native test has Release-active throwing checks, not disabled assertions.
Predeclared acceptance: rest temperature and total flux error <2e-7;
interface half-cell conductive flux mismatch <1e-11 and integrated interface
to hot-boundary mismatch <2e-6; mass divergence <1e-8; moving-lid temperatures
in [0,1], heat above conduction-only 2/3, and successively smaller total-heat
changes on 8/16/32 grids. It also checks exact uniform 321 K at Pe=5000,
K=100000, truncated-flow/thermal-field suppression, nonfinite and out-of-range
input rejection. The large K/Pe uniform test does not qualify nonuniform heat
transport at those limits.

No measured physical validation, independent external CHT solver comparison,
full manufactured moving-flow energy solution, arbitrary geometry validation,
or knowledgeable human numerical release review has been completed.
Agent-authored evidence cannot substitute for that human review.

### Executed evidence

Visual Studio 18 2026, MSVC 19.51.36256.0, x64 Release, double precision;
strict floating-point options inherited from the native airflow target.
On 2026-10-20 CTest passed both executables: unchanged native_airflow in
94.57 s and native_cht in 6.14 s, 100.78 s total. These are measured local
wall times, not a speedup claim or portable performance guarantee.
`python scripts/check_architecture.py` also passed.

| Rest grid | Conductivity ratios tested | Largest theta error | Iterations for K=0.1 / 1 / 10 |
| --- | --- | --- | --- |
| 8 | 0.1, 1, 10 | 2.26119e-12 | 1619 / 318 / 170 |
| 16 | 0.1, 1, 10 | 2.27551e-12 | 6193 / 1196 / 636 |
| 32 | 0.1, 1, 10 | 2.27207e-12 | 23254 / 4486 / 2390 |

| Moving grid, Re=100, Pe=10, K=1 | Integrated heat | Row-scaled residual | Relative global imbalance | Iterations |
| --- | --- | --- | --- | --- |
| 8 | 0.718975 | 3.31979e-12 | 9.57269e-10 | 283 |
| 16 | 0.714575 | 8.73340e-13 | 9.90355e-10 | 1095 |
| 32 | 0.712514 | 2.23030e-13 | 9.98706e-10 | 4321 |

The decreasing changes approximately 0.004400 and 0.002061 are consistent
with the first-order advection limitation but do not establish an asymptotic
accuracy bound. All interface, finite-state, constant-temperature and rejection
assertions described above passed. The retained test log is
`build/native-cht-20261020/Testing/Temporary/LastTest.log`.

A separate process check at the maximum 64 grid (Re=1,lid=0,Pe=10,K=1,
hot=310 K,cold=300 K,flow cap=100000,steady=1e-7,thermal=1e-9,
thermal cap=100000) returned all 6144 temperatures, integrated heat
0.6666666663335763, row residual 4.987676938128516e-14, relative balance
9.994340350317503e-10, and 12439 thermal iterations. The command asserted
convergence, field count and heat error <2e-7 against 2/3.

SHA-256 bindings for the executed source/binary/log set (not release signatures):

| Artifact | SHA-256 |
| --- | --- |
| src/airflow/cavity.hpp | 5b20d3f352d6aad9792a157964a2d8715228aabb3fac7cf7b68333d9e32beff0 |
| src/airflow/cavity.cpp | a8a5493c939f75d23a3b7116a57cb85be961fba21042a7eb67ab148607f8b6d5 |
| src/airflow/cht.hpp | c307bf10a6d72f71cb3eb513d57ed1f1a2ee2d2d252e252a6013258b41ac9f87 |
| src/airflow/cht.cpp | d997e18230f76f82f08592f45f9eb3bfb5352b7f4bf099fe810711478146b448 |
| src/airflow/cht_main.cpp | 882e2dd547dc9aadb50fc2dbb0264970c7f415bca072e923dcd09aaf3a1f6b70 |
| src/airflow/CMakeLists.txt | e4c5778b03ae0e3d41e5d24b3ed2081e4528be7f247468750321e3a0fbdb819d |
| tests/test_native_cht.cpp | d9afce8e1fc4b43fd8af22af428fd781b91d6cce522ab47283e099923f5bdbe4 |
| Release/spike_native_cht.exe | 2f4c9c6727279d944de99890f868330880f0583eee3aa20d318222bc91c1d7d9 |
| Testing/Temporary/LastTest.log | 46f142642467927e34ecd23031b5ad81f92e452ce850c2587e4df8e4abfa65ca |
