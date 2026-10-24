<!-- SPDX-License-Identifier: Apache-2.0 -->
# Full propulsion-loop independent derivation and review

23 October2026. Independent mathematical derivation, numerical oracles and property audit; no solver implementation edits by this reviewer. The selected OpenMotor125_25/ENOLA Casalino+5degree geometry is real source data, but actual-property and simulation validation must be established individually. This record does not promote synthetic motor fields, BEM, low-Re snapshots or inferred material values into a completed real full-speed air/thermal loop. Knowledgeable human numerical review remains required before release.

## 1. Governing magnetic functional and actual-geometry requirements

For a conservative, stable, anhysteretic magnetic constitutive law define a volume energy density `w(B,theta)` with `H=partial_B w`. The geometry, material orientation and installed magnetization enter this same functional. For a linear recoil PM a consistent choice is `.5(B-Br)^T nu(B-Br)`, with positive symmetric reluctivity nu; retain its Br-dependent reference term. General grain-oriented steel requires an energy-consistent directional law, not independent arbitrary component fits whose cross derivatives disagree. Hysteresis/eddy losses are separate dissipative processes and cannot be recovered from a single-valued static energy alone.

Let a be the field unknowns, `Lambda(a,theta)` the three winding linkages using the same signed current-loading basis, and

```
Pi(a;i,theta)=V(a,theta)-i^T Lambda(a,theta),
a*=argmin_a Pi(a;i,theta),
Wco(i,theta)=-Pi(a*;i,theta).
```

The stable constrained field branch gives `lambda=partial_i Wco=Lambda(a*,theta)` and `tau=partial_theta Wco|i`. These derivatives follow by stationarity (envelope theorem); their evaluation must include geometry, anisotropy, winding-basis and PM-source angle dependence. A moving segmented iron rotor changes the field operator as well as the PM direction. Its torque is not just a derivative of a fixed uniform sin/cos PM source. End-turn inductance, if separately supplied/derived, adds `.5 i^T Lend i` to Wco before the Legendre transform; do not add the same end-turn term again afterward.

For a nonlinear FE solve, a projected flux/energy table must preserve a common scalar functional and reciprocity. Independent interpolation of torque and linkage can break that contract even if each curve looks smooth. Finite differences of an angle-varying remeshed energy may contain geometry-quadrature artifacts; preserve periodicity, material identity, reference constants and mesh-convergence evidence. Signed-turn integrals, phase graph and winding linkage/load quadrature require explicit checks. Geometry alone does not establish installed polarity, phase connection or rolling direction.

Primary basis: [Haus and Melcher, Electromagnetic Fields and Energy(1989), section11.7](https://web.mit.edu/6.013_book/www/chapter11/11.7.html), multi-terminal energy/coenergy and mechanical virtual work. The finite-dimensional specialization and all coupling derivations below are independently authored.

## 2. Floating-star nonlinear flux coordinates

Let `E=[[1,0],[0,1],[-1,-1]]`, independent winding-current coordinates x in A and physical phase currents `i=E x`. Define `F(x,theta)=Wco(E x,theta)` and dual flux state `q=partial_x F=E^T lambda` in Wb-turn. Assume `F_xx=E^T Ldiff E` is symmetric positive definite on the admitted current/angle branch. Then the inverse x(q,theta) exists locally (globally on a strictly convex branch), and

```
H(q,theta)=x(q,theta)^T q-F(x(q,theta),theta),
partial_q H=x, partial_theta H=-tau.
```

Proof: `dH=dx^T q+x^T dq-F_x^T dx-F_theta dtheta=x^T dq-tau dtheta`. Thus H is physical magnetic storage with the same PM reference, while q uses balanced terminal flux differences. The leading2x2 block of L is not a valid star reduction. Hysteresis/multivalued magnetic branches, irreversible demagnetization or loss of positive differential inductance require a larger constitutive state or rejection; no inverse-branch selection by numerical convenience is permitted.

Continuous equations are

```
qdot=E^T v-E^T R(T)E x,
thetadot=omega,
J omegadot=tau-Qfluid-b omega.
```

A common neutral voltage adds no power because sum(i)=0. Consequently `Hdot+Kdot=v^T i-i^T R i-Qfluid omega-b omega²`, with `K=.5J omega²`. For28motor poles, theta is mechanical angle and electrical periodicity has14pole pairs; an actual geometry adapter must retain that relation rather than importing the old one-pole-pair synthetic phase law.

## 3. Symmetric coordinate-increment discrete gradient

Set `z=(q1,q2,theta)`, `delta=z1-z0`. For order pi=(1,2,3), move coordinates one at a time from z0 to z1. At each path segment j define `D_j^pi=[H(z_after)-H(z_before)]/delta_j`; for an exactly zero coordinate increment use `partial_j H` at that segment point. The sum of segment energies telescopes exactly:

```
sum_j D_j^pi delta_j=H(z1)-H(z0).
```

Repeat with reverse order piR=(3,2,1), and average the two vectors. This gives `D(z0,z1)=D(z1,z0)` (time symmetry), `D(z,z)=grad H(z)` and the same exact energy-chain identity in exact arithmetic. Coordinates have distinct physical units; each individual quotient has its own correct conjugate unit. No norm/projection mixing Wb-turn with rad is needed. Define `xDG=D_q H`, `iDG=E xDG`, `tauDG=-D_theta H`. For smooth H and a converged regular implicit solve, symmetry/consistency supplies second-order local behavior; conservation alone is not an accuracy estimate.

Primary discrete-gradient reference inspected: [McLachlan and Quispel, arXiv1302.4513v1, submitted19Feb2013, PDFdated20Feb2013, printedpp2–3](https://arxiv.org/pdf/1302.4513v1). It states the energy-chain and coincident-gradient axioms and integral-gradient construction. The coordinate-path telescoping/symmetrization proof here is given explicitly; it is not presented as a quoted implementation from that paper.

### Small increments and field-solve error

Subtracting two large PM baseline energies can corrupt a tiny quotient even when algebra is exact. Prefer `port.energy_difference(a,b)` that cancels constants before arithmetic and evaluates differences from the same constitutive functional. Merely subtracting a common constant after two rounded energy evaluations cannot restore lost digits. Direct nonzero quotients need scale-aware roundoff/field-error assessment, not a division-by-zero threshold alone.

Alternatively integrate the corresponding partial gradient over each coordinate segment, then symmetrize. Three-point Gaussian quadrature is exact only when that path integrand has degree<=5. For smooth general H its component error is at most `|delta_j|^6/2016000 sup|partial_j^7 H|`, so work error is at most `|delta_j|^7/2016000` times that derivative bound. This formula assumes that bound exists; piecewise/non-smooth mesh/material changes need separate handling. Gauss3/5 comparison is an indicator, not a rigorous a posteriori bound. With finite quadrature or finite field-solve tolerance, call the result an approximate discrete gradient and check the actual chain residual, field equations, phase circuit and shaft residuals separately. Do not claim exact preservation for arbitrary H merely because three-point quadrature was used.

Angle state is unwrapped. A physical periodic energy may evaluate trig/functions at reduced angles internally, but increments must use the actual unwrapped trajectory. Tests must cross2pi, cover zero increments separately, include tiny startup angles and check invariance to adding a large constant to H. Accepting small residuals must not depend on the absolute PM baseline masking small exchanges.

## 4. Complete discrete electromechanical and thermal ledger

For one held-controller interval h use

```
delta q/h=E^T v-E^T R(Tmid)E xDG,
delta theta=h omegabar, omegabar=(omega0+omega1)/2,
J delta omega/h=tauDG-Qfluid-b omegabar.
```

The chain identity and quadratic kinetic identity give

```
delta(H+K)=h v^T iDG-h iDG^T R iDG-h Qfluid omegabar-h b omegabar².
```

The dissipative current must be iDG, not the average of endpoint physical currents for a nonlinear/salient energy. Endpoint currents are `E partial_q H(q_endpoint,theta_endpoint)` and remain important for output/envelope checks. The two currents coincide only in special quadratic cases; silently replacing one by the other destroys the general chain proof.

For the averaged bridge, R includes winding R plus duty-weighted high/low conducting MOS resistance. Deposit the same `h iDG^T R(Tmid)iDG` into corresponding solid thermal nodes, and deposit bearing heat into its mechanical thermal owner. With positive constant heat capacities and symmetric passive conductances, the thermal midpoint step satisfies `delta Ethermal=h(Pelectrical_loss+Pbearing)-Qambient`. Thus

```
source work-fluid shaft work-delta H-delta K-delta Ethermal-Qambient=0.
```

Joule/bearing heat are internal transfers. If a resolved fluid participant also evolves temperature/energy, account for viscous deposition and solid-fluid heat through matched conservative interfaces; do not both count shaft power as an external sink and count the resulting fluid energy as additional loss. A quasi-steady isothermal fluid model is an external mechanical load and cannot establish conjugate motor/air thermal transfer. R(T)-only feedback leaves the field functional fixed. Br(T), L(T), thermal expansion and magnetic hysteresis need conjugate constitutive-energy terms and cannot be added by scalar rescaling without a new derivation.

An implicit multivariate nonlinear step is not guaranteed unique or globally bracketable. Require a consistent initial guess/continuation from the previous state, finite scales, differential-convexity/field convergence, current/temperature/speed envelope checks and physical residuals. Singular Jacobian, loss of branch, failed line search or ambiguous roots reject the entire candidate step. Smaller h may restore a local regular solution; retries must restore controller and physical state before the held sample. Convergence order requires same controller sample times and final time under refinement, plus independent magnetic/fluid spatial convergence. There is no rigorous global stability claim from Newton convergence or an energy identity alone.

## 5. Inertial rotating-flow derivation and work audit

Let fixed laboratory position be x=Q(t)y, with constant angular velocity vector Omega, and laboratory velocity `U(x,t)=Q(t)u(y)` for a steady rotating-frame representation. Then

```
DU/Dt = Q[(u-Omega cross y)·grad u+Omega cross u].
```

Write w=u-Omega cross y. Since `D(Omega cross y)=0`, `D(u)=D(w)` and `div w=div u`. Hence the proposed absolute-velocity-in-rotating-coordinates momentum equation is correct:

```
rho[(w·grad)u+Omega cross u]-div(2mu D(u)-pI)=f,
div u=0.
```

Dotting with u eliminates the angular cross term. Integration by parts yields kinetic transport `Fkin=integral_boundary .5rho|u|²(w·n)` and a continuity-error term `Cdiv=.5rho integral_volume(div w)|u|²`. With physical traction sigma n and body work Pf,

```
Pboundary+Pf=Pvisc+Fkin-Cdiv,
Pvisc=integral 2mu D:D.
```

For continuous incompressibility Cdiv=0. In a closed coaxial cylindrical vessel, stationary outeru=0 and rotor no-slipu=Omega cross y give w·n=0; rotor shaft power is viscous work. This is a closed-container load, not a far-wake/inlet-outlet propeller test. Noncoaxial walls or general farfield data require the actual kinetic flux; it must not be omitted by analogy.

For discrete P2/P1 velocity/pressure, weak divergence does not imply pointwise divergence. The skew form

```
csk(w;u,v)=rho/2[(w·grad u,v)-(w·grad v,u)]
         =cadv(w;u,v)+rho/2(div w,u·v)-rho/2< w·n,u·v >.
```

Thus plain skew convection is a Temam-corrected finite-element form when discrete divw is nonzero; it tends to physical convection with convergence, but is not algebraically the same finite-mesh advective operator. Its exact self-work cancellation can hide the continuity-energy discrepancy. Explicitly report/gate Cdiv, actual boundary flux, momentum/continuity residuals and recovered Cauchy-stress loads. Total weak-residual boundary reactions include all discrete terms and preserve that discrete virtual work; a physical traction recovery and mesh/domain/load convergence are separate checks. The Stokes pressure-work sign remains `work-dissipation+pressure_work=0` because reaction=Ku-B^Tp.

Primary mathematical support: [Wick, Numerical Methods for Partial Differential Equations,12Oct2019, section8.14, formulations8.56–8.57](https://www.thomaswick.org/links/lecture_notes_Numerics_PDEs_Oct_12_2019.pdf), physical symmetric stress and mixed incompressible weak forms. The rotating-coordinate and continuity-energy identities above are derived independently; no third-party flow implementation is copied.

## 6. Independently executed manufactured nonlinear oracle

The following dimensionally assigned mathematical energy is an oracle only, not motor data:

```
H(q,theta)=.5q^T A q+.7/4(q1^4+q2^4)
          +.2 q1q2 cos(2theta)+.1 q1 sin(theta)+.025 cos(2theta),
A=[[2,.3],[.3,1.5]].
```

Independent inline Python/NumPy evaluation of the two coordinate paths on23Oct2026 used z0=(.2,-.15,.4), z1=(.25,-.12,.43). Results: H0=.06926938807376914J, H1=.08783796370584726J, symmetricDG=(.4396064819787171A,-.10627710790303997A,-.00744784099221778Nm). Physical balanced current was(.4396064819787171,-.10627710790303997,-.33332937407567714)A. Chain defect3.47e-18J; order-reversal and coincident-gradient errors exactly0 in the executed arithmetic. Each of three distinct exact-zero-coordinate cases also passed a1e-14J chain check. At fixed q,128angle increments over a complete revolution gave torque work−2.08e-17J. This independently demonstrates the algebraic oracle; it does not substitute for calling the owner's forthcoming implementation or prove its numerical robustness.

Further discriminating executed owner checks must include nonlinear RL references, saliency-only torque, PM source energy, Legendre inverse residual/positive Hessian, mixed-scale startup/large-baseline invariance, field virtual work and mechanical/electrical angle periodicity, transient inertial-flow manufactured forcing, no-advection Stokes limit, rotation reversal, mesh/domain/load refinement and conservation with nonzero kinetic boundary flux. Owner-reported results are not counted as this reviewer's independent execution until actually run.

## 7. Primary property closure checkpoint

Actual OpenMotor datasheet identifies N52UH magnets and H070-20 steel but does not identify magnet supplier/lot, installed vector polarity or complete directional material data. Official[first-party OpenMotor technology](https://openmotor.org/) describes tangential magnetization; the exact per-instance alternating sign/global phase convention remains to be tied to CAD or measured back-EMF. CAD/website identity must not be replaced by a guessed uniform rotating PM cylinder. The24slot/28pole winding cannot be inferred from a generic120degree three-phase template.

Official[thyssenkrupp powercoreGO product range,02/2023](https://web-prod.tks.asiososys.com/media/content_1/produkte/elektroband/electrical_steel_integration/thyssenkrupp_electrical_steel_product_range.pdf), printedpp22,26,28: H070-20 is0.20mm; maximum1.7T specific loss.70W/kg@50Hz and.92W/kg@60Hz; minimum polarization1.88T@800A/m. Generic physical data include density7650kg/m³, resistivity.48microohm m and0.20mm stacking factor95%. The manufacturer explicitly warns of large off-rolling loss increases. These grade points do not define directional nonlinear B-H/coenergy or an electrical-frequency loss map; at4300rpm/14polepairs the fundamental is~1003Hz. No validated extrapolation from50Hz to that condition is admitted.

[Arnold G52UH/N52UH datasheet,rev210607](https://www.arnoldmagnetics.com/wp-content/uploads/2018/11/N52UH_GBDD_181031.pdf) supplies nominalBr1.43T andHcB1086kA/m with temperature-dependent demagnetization plots. A straight initial recoil candidate gives `mur=Br/(mu0 HcB)≈1.048`, but the knee/temperature curve and supplier substitution must remain explicit. Its nominal density7600kg/m³ and heat-capacity.11cal/gK≈460J/kgK are candidate supplier properties, not measurements of this motor. Temperature-dependent Br cannot be inserted into the fixed-field ledger without section4's additional thermomagnetic derivation.

## 8. Implementation review status

Independent derivation is ready before the new generic nonlinear magnetic port and inertial flow are publicly admitted. New owner sources/tests are being prepared. Exact reviewed source hashes, independently executed implementation oracles, findings/fixes and remaining physical-data uncertainty will be appended after stable code is available. No completed real full-loop/GUI claim is established by this document at this checkpoint.

## 9. Executed implementation review checkpoint

Independent execution of `.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_energy_step -v` passed all four tests (0.923s). Reviewed SHA256: energy-step source `2d297653a81052d6e5cd78056dd193f9db15c5e0f208219f3b1b958200aaf1a3`; tests `c3611deaca16521230e635e856eb2c58ee7cff63c98b54a4942389690b7448f9`. Additionally, this reviewer's distinct section6 Hamiltonian was supplied to the actual `symmetric_coordinate_gradient`: maximum difference from the independently computed path oracle was exactly zero; chain defect remained3.47e-18J. This is an executed implementation comparison, superseding section6's earlier pending status.

Inspection confirmed iDG is used for both electrical work and heating, final thermal-feedback resistance is rechecked in accepted circuit residuals, and rejected steps do not mutate input state. The mandatory stable energy-difference port avoids subtracting a large arbitrary PM energy baseline. Tiny-coordinate Gaussian integration remains approximate and is guarded by the actual chain defect. No consequential coupling-equation defect remains in this reviewed version. The magnetic port must still enforce branch selection, positive balanced differential inductance and hardware envelopes. A stateless quasi-steady fluid trial does not constitute an unsteady transactional fluid participant.

Independent execution of `.venv/Scripts/python.exe -m unittest output/promo-propulsion-pod-20261023/inertial_cfd/test_inertial_cases.py -v` passed five tests (4.020s): degree-five quadrature, full Newton Jacobian finite differences, rotating quadratic manufactured solution, actual no-slip blade density-to-zero Stokes limit, and explicit resource-budget extension preserving defaults. The tests were staged outside the backend during a coordinated build freeze. Reviewed inertial source SHA256 `06bff08dc4a74632042e510be7c9465d806ac5d2e80acc456b6bdcc7fa619c28`; staged tests `8df83c39aeb5bf78e5ab3ffdf5fe3090ee8d4e44d1e43a33040bebae0e115cb9`. The inspected full Newton derivative includes variation of transporting velocity; rotating cross-product work vanishes, and the boundary-consistent skew formulation reports its continuity-energy correction. These are method verification cases, not validated real-air propeller operating points or load convergence.

## 10. Moving finite-element energy and independent shape-derivative oracle

A consistent moving-mesh calculation pulls scalar axial potential back by `x=Ttheta(X)`, deformation gradient F and determinant J. With the planar curl matrix C, `B=C F^-T grad_X(a_hat)`. Assemble stiffness, remanent source and winding load from this same pullback:

```
K(theta)=integral J Bbasis^T nu(theta) Bbasis,
f(theta)=integral J Bbasis^T nu(theta) Br(theta),
Cw(theta)=integral J chi(theta) N.
```

Rigid rotor material axes and remanence rotate together: `nu=Q nu0 Q^T`, `Br=Q Br0`; stator axes and winding density stay fixed. Air remains isotropic. For unit-depth matrices, axial depth d, `K a=Cw i+f`, and PM reference c, envelope differentiation gives

```
tau=d[(Cw' i+f')^T a - .5 a^T K' a - c'].
```

For nonlinear conservative material use `tau=d[(Cw' i)^T a-partial_theta V(a,theta)|a]`. Holding nodal coefficients while differentiating the assembled energy is essential: equilibrium cancels the implicit derivative of a. Jacobian, transformed gradients, material tensors, source and winding transformations, and reference-energy dependence must all be included. Differentiating only the rotating source omits reluctance torque. Independently remeshing at theta±delta can introduce torque error of order spatial-energy-error/delta; shrinking delta alone is not a convergence demonstration.

A smooth radial air-gap twist can keep rotor rigid and stator fixed with unchanged connectivity locally. Check every mapped triangle's signed area and conditioning. Accumulated large rotation requires rebasing/remeshing with a coherent energy/field transfer; a local ALE derivative on an unrelated mesh is not automatically the derivative of a single canonical H(theta).

An independently executed two-degree-of-freedom moving-operator oracle used `K=Q diag(2,5) Q^T+diag(.3cos²theta,.2sin²theta)+2I`, `Cw=[[1,.2],[.1,1.2]]+[[0,.05sin theta],[.03cos theta,0]]`, `f=Q(.4,.1)`, i=(.7,-.4), d=.025 and theta=.31. The solved a was(.2122283392092519,.001813804363202394). Full shape torque was−.0020978422529987447Nm; dropping K' incorrectly gave−.0012381577086002572Nm. Centered coenergy differences at delta=.001,.0005,.00025rad had absolute errors3.697994649e-10,9.244927350e-11,2.311205090e-11Nm, with refinement ratios4.000026 and4.000046. This manufactured oracle verifies the derivative algebra independently; it is not a real-motor result.

The inspected native section has rotor/magnet outer radius44.2mm and tooth/core inner radius44.6mm. Subject to verifying every intervening region is vacuum, circular Maxwell-stress contours at44.3,44.4,44.5mm provide an independent torque comparison. For outward normal from the enclosed rotor, `tau_z=d r²/mu0 integral Br Btheta dphi`. Compare contours, angular quadrature, gap radial resolution and mesh refinement. P1 recovered stress need not be contour-invariant on a coarse mesh. Primary theory reference: [Meeker, Weighted Stress Tensor,27Aug2022](https://www.femm.info/doku/doku.php?id=WeightedStressTensor), vacuum Maxwell stress and finite-element contour dependence; no implementation code was copied.

## 11. Native conductor-graph finding and conditional resistance oracle

Native exact-solid intersection evidence identifies a consequential electrical-identity gap: Coil019's19-piece chain is0-9-1-10-...-8-17-18, while its Connect intersects both terminal piece0 and internal piece9 with4.49918678mm³ positive common volume. Literal conductive CAD therefore adds a bypass edge. Calling the intersection an intentional joint cannot erase that graph edge. The native geometry does not by itself verify a ten-turn series path. Preserve the literal graph and separately label any intended datasheet-ten-turn interpretation with its connector-clearance/insulating-interface repair assumption. A modified solid must retain the CERN-OHL modification notice and be re-audited. A prescribed-current magnetostatic source does not solve circulating currents in a shorted loop. Contact-point averaging is not a sufficient terminal/path traversal rule.

A useful conditional geometric oracle remains possible. Each native coil volume is1.70459223831471e-6m³. Assuming uniform .8x3mm copper section, no effective overlap, and copper resistivity at20°C of1.7241e-8ohm m, length=V/A=.71024676596446m and Rcoil=.005102235205ohm. If two equal coils in series and four equal parallel branches are independently established, coil-only phase resistance is .0025511176025ohm; three phases at61Arms dissipate28.4781257967W. This excludes buses, connectors, leads, contact resistance, branch imbalance and temperature rise; it is not a measured resistance or proof of that topology. Primary copper reference: [NBS Handbook100,Copper Wire Tables,21Feb1966,section1.1 and tables2–3](https://nvlpubs.nist.gov/nistpubs/Legacy/hb/nbshandbook100.pdf).

Directional H070-20 constitutive/loss data, installed magnet polarity, literal winding-path resolution, field torque refinement, real-blade inertial load convergence, coupled real-port execution and GUI acceptance remain open. This checkpoint supports verified algorithm progress with explicit material and geometry assumptions; it does not establish a qualified full real-hardware loop.

## 12. Periodic common-energy table and final inertial API review

Independent execution of the energy-table and final inertial suites passed8tests in4.160s: `.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_energy_table tests.python.test_propulsion_pod_inertial_cfd -q`. Reviewed hashes: periodic-table source `7cc750a0e85635d922523f46162c28ca8f6cce43f03ec7e5033c28ec43471fee`, tests `2881fa77b24af5ec5bdc7edf279b9d28b8ff456df2e3cea43e7d55b3aaa2a59d`; final inertial source `87b153515d8574de5fc28ed3a893c4c295c80c7ddff665411e17332f72a841a1`, tests `edf082ea1ee10cd8936d63023a7e0275957e590ef5801d1df91de9719815aa07`.

For cubic matrix polynomial `A(t)=d+ct+bt²+at³` on0<=t<=h, Bernstein controls are `d`, `d+hc/3`, `d+2hc/3+h²b/3`, `d+hc+h²b+h³a`. Bernstein weights are nonnegative and sum to1, so positive-definite balanced control matrices `E^T(Lcontrol+Lend)E` rigorously suffice for positive balanced inductance throughout the interval. This conservative certificate may reject an actually positive spline; it cannot admit an indefinite one in exact arithmetic. The same convex bounds also control condition number if each control obeys the stated common ratio bound. This is a mathematical certificate for the interpolated constitutive surrogate, not an accuracy certificate for the input field samples or hardware.

For `H=.5s^T M s-C`, s=q-p(theta), M=A^-1, the stable difference identity is

```
deltaM=-M1 deltaA M0,
deltaH=.5 deltaS^T M1(s1+s0)+.5 s0^T deltaM s0-deltaC.
```

This is exact algebra for symmetric matrices. Integrating spline derivatives obtains deltaA, deltap and deltaC without subtracting the arbitrary coenergy baseline. A new independent65-digit Decimal oracle evaluated the actual cubic coefficients with off-diagonal inductance,1e6J reference, deltaq=(2e-14,-3e-14)Wbturn and deltatheta=7e-11rad. Reference deltaH was−5.388119444190429e-12J; implemented stable difference was−5.388117614254669e-12J, absolute error1.82994e-18J, while naive endpoint energy subtraction returned0. The deliberately strict1e-18J assertion failed; the observed error is retained, not relabeled a pass. Spline antiderivative differences still have floating-point cancellation at tiny increments. This error is below the reviewed absolute chain gate, and the stable method is substantially more accurate here, but it is not exact floating arithmetic.

The table requires its own angular/mesh convergence. One local bounded-angle ALE model cannot directly supply a complete period through the convenience sampling helper; canonical per-angle/rebased sampling must preserve geometry and energy provenance. The table's endpoint periodicity assertion is an input condition to verify, not a substitute for mechanical/pole winding symmetry evidence.

The final inertial public API validates closed disjoint rotor surfaces, a declared coaxial cylindrical exterior, positive fluid properties and incompressible Mach bounds including a sufficient continuous P2 Bernstein velocity bound. Faceted-cylinder rotational invariance and outer-domain independence remain approximations explicitly disclosed. The block preconditioner changes only the iterative linear solve; full unpreconditioned residual gates remain. Its velocity ILU/pressure-mass/gauge block is an approximate preconditioner, not a pressure penalty or physical stabilization. No consequential equation/sign defect was found in this reviewed revision. Small-case tests do not establish scalable solution of the actual241771-tetrahedron blade mesh or converged blade loads.

## 13. Air-gap volume torque and convergence-screen interpretation

In a source-free vacuum cylindrical annulus, average section10's contour torque uniformly over radius a..b:

```
tauA=d/[mu0(b-a)] integral_annulus r Br Bphi dA.
```

This is independently obtained by exchanging the radial/azimuthal integrals. It also follows from virtual displacement `v=alpha(r) r ephi`, with alpha=1 at rotor and0 at stator: the vacuum Maxwell-stress virtual work is `tau=−d/mu0 integral r alpha'(r) Br Bphi dA`. A linear radial alpha produces the same annular expression. Thus a consistent fixed-coefficient ALE energy derivative and this volume work provide a useful same-field cross-check; agreement alone does not establish spatial accuracy. Integrate the actual vacuum annulus, not a centroid-selected set of boundary-straddling triangles. Refine CAD chord error, radial/angular gap resolution and integration independently. Primary implementation-owner theory reference: [COMSOL6.4 AC/DC Modeling Guide,Computing Electromagnetic Forces and Torques,equation3-12](https://doc.comsol.com/6.4/doc/com.comsol.help.acdc/acdc_ug_modeling.06.20.html), cylindrical radial-flux air-gap volume torque. No third-party implementation was copied.

The initial convergence assessor's4tests independently passed, but review raised a consequential interpretation concern to its owner: merely ordered mesh scales and a strictly enlarged domain permit negligible refinement, for example h=(1,.9999,.9998) and domain enlargement1.0001. Small load changes in that experiment cannot establish numerical convergence. Caller-declared physical absolute tolerances are acceptance budgets, not estimates of discretization error. Three decreasing monotone load increments still require credible asymptotic/order or other uncertainty evidence before estimating remaining error. Distinct hash strings identify reported cases but do not alone prove their execution. Preserve physical/production qualification false and treat a load-change screen as a bounded screening result unless meaningful geometry-aware refinement/domain checks and provenance are enforced.

## 14. Residual-consistent high-advection method candidate

This is a derived implementation path, not a completed high-Reynolds-number solver or evidence that steady laminar flow represents the selected real propeller. Keep the inf-sup-stable P2/P1 pair. SUPG addresses advection oscillation; PSPG is optional here and must not be justified as repairing an equal-order pressure instability that this pair does not have. A turbulence/transition model with wall treatment or genuinely resolved transient DNS remains separate from numerical stabilization.

Let w=u−Omega cross r, nu=mu/rho. For constant viscosity, define the elementwise physical strong momentum residual

```
Rm=rho[(w·grad)u+Omega cross u]
   -mu[Delta u+grad(div u)]+grad p-f.
```

P2 velocity has nonzero second derivatives. Dropping Delta u as in affine P1 implementations is inconsistent here. The symmetric-stress strong operator includes grad(div u) even though exact incompressibility eventually makes it vanish. Use the same body force, rotating acceleration and viscosity as the governing residual. One consistent extension of the existing Galerkin form adds

```
Ssupg(v)=sum_K integral_K tau_s (w·grad v)·Rm,
Spspg(q)=sum_K integral_K (tau_p/rho) grad q·Rm,
Sgd(v)=sum_K integral_K gamma div v div u.
```

Here tau has seconds, gamma has Pa s, and v has velocity units; all three tested energy contributions have watts when v=u and q=p. Exact smooth solutions have Rm=0 and divu=0, hence the added terms vanish: this proves consistency. The existing weak-divergence Temam form differs from the physical advective residual by `.5rho(divu)u`; include/report that choice explicitly rather than silently changing the target finite-mesh residual.

Primary sources: [Tezduyar,Mittal,Ray,Shih,CMAME95(1992)221–242,equations11–19](https://www.tafsm.org/PUB_PRE/jALL/j28-CMAME-PSPG.pdf) and [Tezduyar,Advances in Applied Mechanics28(1992),sectionIV](https://www.tafsm.org/PUB_PRE/jALL/j32-AAM-Stab92.pdf). Their residual-weighted stabilization separates advection and pressure concerns. The original examples and low-order parameter choices do not qualify a P2/P1 rotating blade at Re~0.9million. The equations above are independently adapted to the reviewed MRF formulation; no implementation was copied.

An established low-order starting timescale is `tau_s=h/(2|w|) min(Pe/3,1)`, Pe=|w|h/(2nu), with continuous zero-speed limit h²/(12nu). A directional geometric scale is `h=2/sum_vertex |s·grad Nvertex|`, s=w/|w|. This should not be transplanted as a proven optimal anisotropic P2 parameter: constants, stagnant-point direction convention, highly stretched near-wall elements, quadrature and parameter sensitivity need explicit tests. Rotation remains in Rm; inventing an arbitrary rotation-based damping law would need a separate derivation. A lagged tau is a Picard/quasi-Newton choice; a claimed full Newton derivative must include its dependence on u and on w.

Unlike an isolated advection-squared term, SUPG work `Ssupg(u)` is not generally nonnegative: the residual also contains pressure, diffusion, body force and rotation. The PSPG pressure test contributes `Spspg(p)` through the continuity equation; its sign must follow the implementation's continuity convention. Grad-div contributes nonnegative gamma integral(divu)² when gamma>=0. Retain each added work term in the algebraic boundary-work ledger and separate it from physical viscous heat and recovered Cauchy traction. Exact residual-work closure after stabilization is not a physical load validation.

Minimum discriminating oracles: existing quadratic rotating manufactured solution with its exact forcing must remain exact and have zero stabilization residual; choose a second divergence-free cubic manufactured field to exercise P2 approximation and viscous strong residual; verify assembled Jacobian by directional finite differences; recover Stokes/zero-advection limits; compare stabilization-parameter halving and mesh refinement; report physical traction, continuity-energy correction, stabilization work and nonlinear residual separately. An actual higher-Re benchmark with independent drag/lift or analytic layer reference is required before blade use. A million-Re steady laminar output cannot be promoted solely because its Newton iteration converges.

## 15. Spatial broadphase and source-surface coarsening review

The new deterministic AABB hierarchy in `cfd_tetra_intersections._strict_aabb_pairs` was inspected independently. Every node stores coordinatewise minima/maxima enclosing all descendant boxes. If any node upper bound<=query lower bound, or query upper bound<=node lower bound, no descendant can have strict positive AABB overlap. Leaves use the original strict predicate; ids>i prevent duplicate/self pairs and sorted results restore original lexicographic order. Thus the hierarchy does not alter the SAT/exact-predicate owner or decide actual tetrahedron overlap. Independent execution of `InertialOracles.test_spatial_broadphase_exact_bruteforce_pair_equivalence` passed in1.329s for4200random boxes plus touching/coincident bounds. An initial command used the wrong test class name and was corrected; no solver failure was involved. This fixture establishes exact pairlist equivalence, not an end-to-end performance speedup.

Installed repository .venv imports both vtk and pyvista, verified independently. Prefer available native decimation tools over copying an external mesh implementation. [Garland and Heckbert,SIGGRAPH1997,sections6.1 and8](https://www.cs.cmu.edu/~garland/Papers/quadrics.pdf) explicitly distinguish their quadric heuristic from independent approximation measurement. Quadric cost sums squared distance to infinite incident planes; it neither bounds maximum surface error nor guarantees closed manifold topology. Generic pair contraction can even join components. For a thin physical blade, require closed oriented2manifold output, no selfintersection, preserved blade/hub components and minimum thickness, with leading/trailing edges and mounting geometry treated as features. Compare radius, span/chord/twist, volume and bidirectional surface distances, not only face count.

[VTK vtkQuadricDecimation](https://vtk.org/doc/nightly/html/classvtkQuadricDecimation.html) is an available algorithm candidate; [vtkHausdorffDistancePointSetFilter](https://vtk.org/doc/nightly/html/classvtkHausdorffDistancePointSetFilter.html) supports point-to-cell comparisons. Its sampled distances must not be labeled an exact continuous Hausdorff certificate. Independently, distance to any closed target surface is1-Lipschitz: for a source sampling cover radius eta, directed continuous distance<=maximum sampled point-to-target distance+eta. Apply this in both directions. Subdivide source triangles into patches and use each patch centroid with eta=max distance from centroid to its vertices; convexity bounds every point of that patch. Adaptive subdivision near the largest upper bounds tightens the estimate. This mathematical bound assumes accurate point-to-triangle queries; floating-point query errors need their own margin before calling it certified. Retain original licensed STL, transformation history, units and source/derived hashes. Geometry coarsening remains a separate error axis from volume mesh refinement and fluid-model validity.

Additional independent manufactured forcing for section14: choose `u=(a x³,−3a x²y,0)`, `p=beta(x−.5)+gamma y²`, Omega=Omega ez. Then divu=0, `Delta u=(6ax,−6ay,0)`, and exact physical forcing is `fx=rho(3a²x⁵+6a Omega x²y)−6mu ax+beta`, `fy=rho(3a²x⁴y+4a Omega x³−6a Omega xy²)+6mu ay+2gamma y`, fz=0. This smooth field is not exactly representable by P2/P1 and can exercise actual approximation convergence. Body force times P2 basis has degree7; existing degree5 exact quadrature does not integrate it exactly. A six-point-per-coordinate Duffy rule suffices for the polynomial forcing/work references including degree9 boundary flux. This is a proposed discriminating oracle, not a reported executed CFD result.

## 16. Read-only field performance observations

No additional large solve was launched. In the reviewed `magnetic_fem.PlanarMagneticOperator` constructor, material grouping converts the full string region list to a NumPy array inside every material iteration. Hoisting that immutable conversion or building index buckets once preserves exact region identity while avoiding repeated allocation. In `solve_magnetostatic`, the harmonic initial solve is unnecessary when every prescribed Az is exactly zero: zero is already the exact harmonic initial vector. A guarded zero-boundary path may skip its Laplace factorization while retaining all mesh/gauge/finite-value admission and the original nonzero-boundary path. These are proposed semantic-preserving optimizations, not implemented or benchmarked by this reviewer. At one fixed angle, multiple linear basis solves share the same stiffness/factorization, but exposing reusable operators needs explicit ownership and equivalence tests. Coalescing equal magnetostatic material laws must not be generalized to eddy-current conducting regions, whose separate circuit identities are physical contracts.

## 17. Executed SUPG implementation and torque-motion checkpoint

The new SUPG implementation was independently inspected and `.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_inertial_cfd -q` passed9tests in11.211s. Hashes: inertial source `c6fb11f8017ef053ae2cf64fbecb781c71f4353a3ea0ae5f707a5cd02e4a4472`; SUPG helper `538007e90b56754cbe14f2ad38e4cf8b56d62434ea65818277e697a8f1921901`; tests `39659e1c0111805ddee7d6386df4f0054793f40c6e63156111fbdc5cc7430e9c`. Coverage includes full symmetric P2 strong viscosity, simultaneous velocity/pressure/tau Jacobian finite differences, and this reviewer's nonexact cubic rotating manufactured field with refinement and nonzero stabilization work in the ledger. The helper's P2 Hessians, grad-div contribution to strong viscosity, rotating source, pressure columns and smooth tau derivative were checked against section14. No consequential assembly/sign finding was identified. These method tests establish no experimental high-speed-air load accuracy.

The reviewed torque implementation (`propulsion_pod_real_motor.py`, hash `e37f3b2cb62c9652657fcf0f99318f6d4df74110bf8b10b79f61b6e87abdef72`) uses nodal motion velocity v_i=alpha_i J x_i, `G_ab=sum_i v_ia grad_b N_i`, and vacuum shape work `−d/mu0 sum area[B·G B−.5|B|²traceG]`. This is the correct discrete P1 fixed-coefficient vacuum derivative when the transition support is entirely vacuum, rotor material is rigid isotropic with co-rotating remanence and stator/source geometry is fixed. Other material/source functional derivatives then vanish by rigid covariance, not by arbitrarily dropping K' or f'. The optional different-annulus diagnostic changes virtual velocity and is not necessarily the derivative of the configured model Hamiltonian. Only using that same annulus in the actual mesh-motion map establishes that identity.

Owner-reported central-band agreement is useful diagnostic evidence but was not independently rerun on the large meshes here. Freeze the selected mesh-motion annulus before the accepted refinement ladder, use identical geometry/current/angle/material declarations, and retain failed whole-gap comparisons. Do not average or replace the energy-derived torque with a more convenient unmatched stress estimate. Require finite-difference step refinement and consistent shape/traction comparisons on the same refined field, then actual mesh/geometry refinement. A post-hoc torque substitution would break the coupled energy identity.

For the actual propeller, a0.3mm bidirectional surface bound is0.1percent of diameter but does not by itself bound aerodynamic load error. Minimum local blade thickness, leading/trailing edges, normal/chord/twist and hub topology need protection. An unfinished distance-cover budget remains an unfinished geometric bound. Surface-coarsening sensitivity and volume-mesh refinement are separate error axes; hold other inputs fixed when comparing them. Million-Re stabilization, even when mathematically residual-consistent and converged, still requires the physical transition/turbulence/wall or resolved-transient evidence identified in section14.

## 18. Independently derived globally coherent annular interface

This section reviews the proposed analytic vacuum annulus; it is not a claim
that the actual motor's interface or torque has converged. Primary separation
reference read directly: [Sho Seto,MATH124B notes,5September2016,section2.4](https://web.math.ucsb.edu/~shoseto/teaching/124B/Lecture/124B.pdf);
[Victor Ivrii,PDE textbook,section6.4.1,equations6.4.10–11 and annulus remark](https://www.math.utoronto.ca/ivrii/PDE-textbook/PDE-textbook.pdf),
accessed23October2026. These give the polar harmonic separation underlying the
following independently derived energy and rotation identities. No external
implementation was copied.

Let a<r<b be a source-free isotropic vacuum annulus, x=log(r/a),
t=log(b/a), nu=1/mu0 and axial depth d. For A=Az,

```
Egap=nu*d/2 integral_0^t integral_0^(2pi) (Ax²+Aphi²) dphi dx.
```

Use orthonormal angular functions phi0=1/sqrt(2pi), and
(cos(nphi),sin(nphi))/sqrt(pi). At each n>=1, let r_n be the rotor-LOCAL
coefficient pair and s_n the stator-GLOBAL pair. Physical positive rotation
means `Arotor_global(phi)=Arotor_local(phi-theta)`; hence the global rotor
coefficients are u=R(n theta)r_n, where R is the positive2D rotation matrix.
The exact radial pair is

```
y(x)=sinh(n(t-x))/sinh(nt)*u+sinh(nx)/sinh(nt)*s_n.
```

Integrating its quadratic energy, or using the endpoint identity
`integral(yx²+n²y²)=[y·yx]_0^t`, gives

```
En=nu*d*n/2 [coth(nt)(|r_n|²+|s_n|²)
             -2csch(nt) s_n^T R(n theta)r_n].
```

Thus for block order [rotorLOCAL,statorGLOBAL], Krr=Kss=nu*d*n*coth(nt)I,
Krs=−nu*d*n*csch(nt)R^T and Ksr=Krs^T. The n=0 block is
`nu*d/t [[1,-1],[-1,1]]`. Only the common constant trace is a null mode;
it is a physical Az gauge, to be fixed by the exterior/subdomain gauge rather
than arbitrary diagonal gap jitter. Nonconstant modal eigenvalues are
`nu*d*n*tanh(nt/2)` and `nu*d*n*coth(nt/2)`, each twice, independent of rotation.
With J=[[0,-1],[1,0]], torque on the rotor is

```
tau=-partial_theta Egap
   =nu*d*n²*csch(nt) s_n^T J R(n theta)r_n.
```

For r=(A,0), s=(Bcos(delta),Bsin(delta)), torque is proportional to
sin(delta−n theta), with the positive sign aligning the two physical patterns.
This sign also follows from Maxwell stress because
`Br=Aphi/r`, `Bphi=−Ax/r`, and therefore
`tau=−nu*d integral Aphi Ax dphi` on every circular vacuum contour.

Independent executed oracle (inline NumPy,64Gauss radial and512uniform angular
points) used a=.04426m,b=.04454m,d=.025m,n=3,theta=.27rad,
r=(.003,-.002),s=(.001,.004). These are manufactured mathematical
coefficients, not motor values. Closed energy26.214219222089653J versus
integrated26.21421922208965J; analytic torque125.62160778617066Nm versus
Maxwell torque125.62160778617064Nm at x/t=.2,.5,.8. Centered negative energy
derivative errors at h=.001,.0005,.00025rad were1.8843232769e-4,
4.7108090044e-5,1.1777052393e-5Nm, with ratios3.9999993 and3.9999899.
A constant-mode coefficient jump .001 to.004 gave14.196005465669385J;
equal constant coefficients gave zero. These verify the independent formulas;
owner implementation comparison is still required after its source is ready.

For stable energy evaluation use the equivalent positive form
`En=nu*d*n/4[tanh(nt/2)|u+s|²+coth(nt/2)|u-s|²]`.
Compute t by log1p((b-a)/a) for thin gaps. Stable hyperbolic ratios are
`csch(z)=2exp(-z)/[-expm1(-2z)]` and
`coth(z)=1+2exp(-2z)/[-expm1(-2z)]`. Thin-gap conditioning remains real;
these formulas do not authorize arbitrarily ill-conditioned geometry.

Static rotor and stator FE bodies can be condensed separately without angle
remeshing. From `Phi=.5a^TKa-f^Ta+c`, partition interiorI and boundaryB:

```
S=KBB-KBI KII^-1 KIB,
g=fB-KBI KII^-1 fI,
C=c-.5 fI^T KII^-1 fI.
```

Constrain the FE boundary values by `aB=V z`, with V evaluating the angular
basis at all boundary DOFs. Then use V^TSV and V^Tg; add the gap K(theta)
in coefficient space. This is a variational constraint, not an inverse
collocation fit. At stationary z, the envelope torque is−.5z^TKgap' z if
all local bodies/sources truly remain angle independent in their local frames.
Retain C: it is angle independent in this construction but can depend on
current, since fI contains winding source. Omitting it corrupts linkage and
inductance even if torque still looks correct. Recover interior potentials
and compute linkage from the same winding loads, or differentiate every
current-dependent Schur term.

Trace admission must require full column rank/well-scaled singular values,
correct constant basis normalization, odd count2K+1, and a cutoff below the
independent trace sampling Nyquist limit. Unrepresented Nyquist components
must be explicitly discarded, not inverted or claimed resolved. Refine mode
cutoff, boundary mesh, volume mesh and material geometry independently. A
straight-sided P2 trace interpolating Fourier nodal samples is not exactly an
analytic circle trace between nodes. Combining such polygonal subdomains
with exact circular-annulus energy is a geometric/trace variational crime,
not exact continuum conformity. Quantify/refine it or supply truly curved
consistent maps. None of the new spectral identities removes the need to
resolve the actual motor's global energy/torque discrepancy.

Annular implementation checkpoint: independently executed the section18
manufactured n=3 case against `AnnularGap`. Source at inspection SHA256
`63e341d5d3f877ab25f404ba4762e4a14d118e84ae33e20288f46df25ed22580`.
Computed energy26.214219222089937J, torque125.62160778617202Nm; analytic-field
Maxwell torque at three radii was125.62160778617209,125.62160778617205,
125.62160778617205Nm. Relative agreement with the separate earlier log(b/a)
oracle was approximately1e-14. A deliberately strict1e-12Nm absolute
comparison failed by1.36e-12Nm; the constructor's more accurate log1p ratio
versus the initial oracle's log(b/a) explains the small difference. It is
retained as a tolerance observation, not a method failure or a falsely passed
assertion. The owner's two annular tests independently passed in0.318s,
covering constant-mode logarithmic field/gauge, modal torque/energy derivative,
Maxwell contours, positivity and periodicity.

Inspection found the rotation blocks, derivative and stable radial field ratios
consistent with the independent derivation. Review requested fail-closed
validation of `field` mechanical angle and finite derived dimensional scales:
finite positive input dimensions alone can still overflow radius-ratio/scale
calculations; NaN angle must not silently produce NaN fields. These requests
were sent to the owner and need binding to a final revised hash before closing.

## 19. Static-domain Schur implementation review and executed oracle

Reviewed final `propulsion_pod_separated_motor.py` SHA256
`fe065ae2ca7c5766ebae36df24352ef77980970ae52aeaa42426a70f1c7a422a`.
The static condensation keeps the source quadratic term
`R=FI^T KII^-1 FI`. With columns ordered PMsource then three phase sources,
G the condensed/projected loads, X=Ktotal(theta)^-1G and z=(1,iA,iB,iC),

```
M=G^T X+R,
Wco=.5 z^T M z-c,
lambda=M[1:,:] z,
D=-X^T Kgap' X,
tau=.5 z^T D z.
```

These are the correct source dimensions, signs and envelope derivative.
Recovery `aI=KII^-1 FI z-KII^-1 KIB Vcoeff` and `aB=Vcoeff` retains the
same stationary field. Physical magnetic energy is i·lambda−Wco for the
zero fixed exterior potential used here. Independent physical phase fluxes
are intentionally retained by this magnetic port; floating-star circuit
admission/projected linkage E^Tlambda belongs to its caller. Full-phase basis
solves must not be mistaken for violating or enforcing electrical-neutral KCL.

A separately authored eight-sector mathematical fixture was executed against
a FULL uncondensed constrained variational system, independently of the Schur
formula. Rotor disc radius.5m, stator inner/outer radii.6/.9m, depth.02m,
three Fourier modes, uniform mu_r1, rotor Br=(.02,.01)T, stator element phase
sources cos(phi),sin(phi),−cos(phi)−sin(phi), theta=.37rad and currents
(.7,-.2,-.5)A were used. These are mathematical oracle dimensions, not the
native motor. The full system retained all P2 interior DOFs and trace
coefficients; only external stator boundary potentials were fixed0.
Maximum recovered-potential difference1.47723e-18Wb/m, maximum phase-linkage
difference6.77626e-21Wbturn, coenergy difference exactly0J and torque difference
3.82496e-16Nm. Full-system torque was−1.2495317007865658e-5Nm and coenergy
−1.86365182547355J. This check exercises the Schur reference/current terms,
field recovery, load dimensions and torque sign independently.

Reviewer execution of
`.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_annular_gap tests.python.test_propulsion_pod_separated_motor -q`
passed4tests in0.012s. The owner's separate12-sector fixture checks its own
full constrained system, angle coenergy derivative, all three phase-current
coenergy derivatives and a nonzero R phase block. It also rejects a missing
global gauge. Separated tests SHA256
`bf0d1f3fce60286f867dd3e6055f076f5b591734f9ab806a34ad39811c005f3f`;
annular tests `7a0155c0d23a5d3b0d896f3aa73dc9bff4c38eadbe0ad01e7bb340b2c60fe070`.
Final annular source SHA256
`0ac01369fae9b90f75312b311aef269b24545218991a3d592f679c9c716bd596`
includes the requested finite-angle and finite-derived-scale guards.

Review findings fixed by the owner: an interface anchor permits local
condensation but does not fix the full common-constant gauge; require an
actual exterior fixed trace. The final module enforces that requirement,
strict include_field bool, and finite computed flux/coenergy/torque/coefficient
results. No consequential algebra/sign/recovery issue remains in this reviewed
revision. Native geometry, spectral/interface refinement, material assumptions
and actual torque convergence remain open; no hardware qualification follows.

## 20. Bounded linear-solver recommendation for actual air meshes

The flow owner reported a near-Stokes density-continuation solve missing the
unchanged true-residual gate by a small factor on a highly stretched blade
mesh. This is not evidence to relax that gate or alter physical viscosity.
A pressure-mass Schur approximation is natural on suitable Stokes meshes, but
its practical constants can deteriorate with complex no-slip geometry and
anisotropy. An exact-equation-preserving candidate is the sparse SIMPLE-type
pressure approximation `Sapprox=B diag(Avel)^-1 B^T`, with the same gauge,
using a positive Stokes/symmetric-viscous diagonal in an indefinite Oseen
case. Compare its iteration count and true residual on the identical case.
It is a preconditioner change, not a physical pressure penalty. A nested
variable-tolerance inner solve generally requires flexible outer Krylov
iteration; ordinary GMRES assumes a fixed linear preconditioner.

Primary reference read: [Pimanov,Iliev,Oseledets,Muravleva,arXiv2307.05266v2,
21October2023](https://arxiv.org/pdf/2307.05266), Schur/SIMPLE comparison for
staggered finite-difference Stokes in tight geometries. Its discretization is
not the present P2/P1 blade mesh, so it supports a candidate test rather than
a transferred performance guarantee. [Wathen,Preconditioning,Acta Numerica2015,
section5](https://people.maths.ox.ac.uk/wathen/preconditioning.pdf) supplies the
general saddle-point/Schur framework. No implementation code was copied and
no new actual-air convergence result is claimed by this recommendation.

## 21. Retained repeated-sector motor convergence assessment

Read-only inspection covered the three initially requested repeated-sector
receipts and three finer receipts that appeared during review. No new native
field case was run by this reviewer. Receipt SHA256 values:

| N / boundary segment target | Receipt SHA256 |
| --- | --- |
|1008 /1mm|3bb46e55312210a9fd8e2c8a6db34af8c867e8d9067e2c717c6fe1190c4093b8|
|1008 /.6mm|32f393294a1bed0f69919518d5bdeae0fbf6969967f920abe523e8bc4bb3893c|
|1008 /.4mm|37d368e12ae03179385905c8770a160de63ed9aa29e01f758b14a1a7004bf2ed|
|1008 /.3mm|20db01c96502bfcde4fdad171d3cf2daceaf61a806f7c9026d88375819545da0|
|1008 /.2mm|7256aba28ed89eb3ed496a8acedccd5ef1e9c94b93e766a92b5e9469373abd99|
|2016 /1mm|34fe9db733745f1468df1406f7f53cb73225398d683a20049fe735938e81ef21|

At N1008/1mm, Fourier cutoff447,639,895 gives torque at theta=.002rad
.415106,.417310,.415236Nm: nonmonotone. At theta=.012rad it gives
.531102,.525511,.517788Nm, with successive changes5.59 and7.72mNm,
not a decreasing sequence. At fixed N1008/cutoff895, changing the segment
target1mm to.6mm changes torque by−.050967Nm(−12.27percent) and
−.048149Nm(−9.30percent) at those two angles. Ring doubling1008→2016
at1mm/cutoff895 changes+.002729Nm(+.657percent) and−.006632Nm
(−1.281percent). Ring changes also retriangulate the domains and therefore
are not a pure circular-chord-error isolation.

The finer N1008/cutoff895 receipts show progress:

|Boundary segment target|Torque at .002rad,Nm|Torque at .012rad,Nm|
|---|---:|---:|
|.4mm|.346956354|.453592529|
|.3mm|.343394518|.443869617|
|.2mm|.340389766|.434486395|

Last differences are−.003005Nm(.88percent) and−.009383Nm(2.16percent).
At.2mm, cutoff639→895 changes+.002716Nm(.80percent) and−.003397Nm
(.78percent). These are load changes, not error bounds. The .012rad
spatial increments decrease slowly and do not establish an asymptotic rate.
Importantly `edge_m` currently segmentizes MATERIAL BOUNDARIES before
constrained Delaunay triangulation; it is not a controlled global maximum
triangle diameter and inserts no independent interior size field. Treating
these parameter ratios as global h for Richardson estimates is unjustified.
Capture actual diameter, angle/conditioning, per-material and air-gap resolution
statistics, or use independently validated interior mesh-size control.

Algorithm checks are strong: retained centered coenergy derivatives approach
the same analytic torque; analytic gap stress at three radii agrees to about
1e-12Nm; repeated-period torque defects are roughly2e-9..6.4e-9Nm,
coenergy defects about1e-10J and phase-flux defects below7e-13Wbturn.
These validate coherent finite-dimensional covariance/energy evaluation, not
spatial or hardware accuracy. Both sampled angles lie within.012rad of a
.448799rad period, so they cover only about2.7percent of that period.
No whole-period convergence conclusion is warranted.

The repeated-sector helper was inspected at source hash
`3cc4e648a9dab7c3e87b0d1cda91334f6ec5307b35e07916ecf2c24f33078ef7`.
It first verifies native rotor iron/magnet geometry and declared PM vector
covariance, clips one2pi/14sector, repeats its connectivity and remaps PM
identities. Explicit radial seam welding is1e-10m; it is a documented derived
geometry change, not exact untouched CAD. Independent execution of the source
coefficient-period proof on retained fine geometry reported maximum Hausdorff
1.09337534525e-12m and magnetization-unit-vector error9.42055e-16, under the
DECLARED alternating tangential PM pattern. The code's pattern is an explicit
physical assumption, not proof of installed magnet polarity. Repeated isotropic
material/PM connectivity makes the discrete rotor covariance credible, but
cannot manufacture material or torque convergence. Preserve licensing and
modification notices for the derived periodic mesh.

Small discriminating next cases: use the finer existing N1008 domain at more
than one cutoff, then N2016 at the SAME finer segmentation/cutoff and a higher
cutoff. Compare over a distributed angular set including0,T/8,T/4,3T/8,T/2,
not only the two near-origin points; seek worst coefficient changes rather
than declaring the set a full continuum proof. Once the angular dependence is
resolved, compare the coenergy-derived ports over the requested current
range. With U an orthonormal balanced basis, phase box |ij|<=Imax,sum i=0
implies norm(i)<=sqrt2 Imax and the conservative difference bound

```
|delta tau| <= Imax² ||U^T deltaL' U||2
              +sqrt2 Imax ||U^T deltapsi'||2+|deltaC'|.
```

It can be evaluated from retained ports without more PDE solves and reveals
high-current amplification hidden by the1A example. Separate angular table
interpolation from field/trace error; use physical absolute torque budgets
near zero. Current receipts remain insufficient to admit a qualified whole-
period field table or actual complete motor-air loop.

## 22. Executed fixed SIMPLE-Schur preconditioner review

Reviewed `propulsion_pod_inertial_cfd_schur.py` SHA256
`71651faed004e1b04e8c237ef1ed22b03d9ec9667c5d3cc05e4b78020317e629`.
Its fixed bordered negative Schur block and block-factor inverse signs match
section20, including arbitrary gauge right-hand sides. Test SHA256
`85555cece5e7e6b6fcae16cf63dc8213944e513990d2d06695e9ae26989349b5`;
independent dedicated test execution passed1test in.020s. The oracle uses
exact diagonal velocity A, a gauge different from the pressure null vector
and arbitrary last RHS. Using the initial Stokes diagonal for pressure and
new fixed velocity ILU per Newton step is a linear preconditioner within each
ordinary GMRES call. Ignoring a SUPG pressure-upper-block correction in the
PRECONDITIONER is an approximation, not a PDE omission, as long as the full
assembled Newton matrix and final unpreconditioned gates remain unchanged.
No consequential algebra issue was found. Actual blade iteration improvement
and physical flow/load convergence are not established by this small oracle.

## 23. Nested-space response monotonicity and prepared cutoff restriction

For fixed geometry, material laws, winding density functions, boundary trace
mapping, outer gauge and exact stated quadrature, let source z=(1,iA,iB,iC)
and fixed load matrix F. The discrete current-source coenergy is

```
Wco_h(z)=max_a_in_Vh [z^T F^T a-.5 a^T K a]-c
       =.5 z^T M_h z-c.
```

If the conforming spaces are genuinely nested, Vcoarse subset Vfine, every
coarse trial is available to the fine maximization. Thus
`z^T(Mfine-Mcoarse)z>=0` for all z: the augmented response difference is PSD.
The source-first coordinate can also vary mathematically to establish the
full4x4 statement. The PM reference cancels only if physical volumes and
constitutive reference remain unchanged. Torque, an angle derivative of this
matrix response, need not be monotone or have a fixed sign under refinement.
A violation beyond numerical error discriminates non-nested geometry/source
changes, inconsistent condensation/reference or solve errors; it does not
justify changing torque to force monotonicity.

Boundary-protected red/green subdivision can make a conforming nested P2
interior space with exactly unchanged boundary traces: restriction of each
coarse quadratic to child triangles is still quadratic, and original boundary
edge polynomials remain available. Inherited region/source functions and
unchanged trace V are essential. New vacuum-layer boundaries independently
retriangulate the domain; they are not automatically a nested refinement of
the unlayered mesh. Sector seam welding after refinement can move new seam
midpoints by up to the declared0.1nm, so exact inclusion into the already-welded
coarse geometry must be checked rather than assumed. The reviewed refinement
helper also protects all edges with endpoints on one ring, including possible
internal chords; this preserves conformity but weakens a claim of uniformly
refining every interior edge. The issue was sent to its owner.

An independently executed square oracle used two coarse triangles, red-split
children, fixed zero boundary values, depth.3m, region permeabilities1.2/.8H/m,
region remanence(.2,.1)/(-.1,.3)T and three fixed piecewise constant source
columns. Eigenvalues of Mfine−Mcoarse were
(-3.55474e-20,3.62509e-35,.0008328512072,.0031708630785), PSD to roundoff.
PM reference difference was1.73472e-18J. This is a mathematical nested-space
oracle, not a real-motor refinement result.

The prepared `restrict_modes` implementation was inspected at separated-motor
source SHA256 `1d63c758ac92aa60f7926ae962b2d568f35361983527a590d8ed254a5290f61d`.
Its lower Fourier basis is exactly the leading V columns, with the corresponding
principal S blocks and G rows; the interior response R and PM reference remain
unchanged. This is the correct Galerkin restriction without recondensation,
resampling or fitting high modes into lower ones. Three owner tests independently
passed in.012s, including comparison with independently prepared lower cutoff.
A separate harmonic-source fixture modified source columns to
cos(3phi),sin(2phi),−cos(3phi)−sin(2phi). Comparing prepared maximum mode3 with
restricted1 at theta=0,.27,1rad gave minimum response-difference eigenvalues
between−1.5e-30 and−2.9e-32, with positive eigenvalues approximately
7.6e-9..3.13e-8. The initial linear-source fixture excited no higher modes and
gave only near-zero differences; the harmonic fixture is the discriminating
check. Nested trace enrichment has the same PSD response property, but neither
this property nor correct restriction proves its cutoff error is small.

The augmented matrix mixes J,Wbturn and H coefficients. Mathematical PSD is
unchanged by physical unit rescaling, but an absolute eigenvalue tolerance on
the raw mixed-unit matrix is not a universal energy tolerance. Use a congruence
D=diag(1,Iref,Iref,Iref), examine D deltaM D in energy units relative to the
scaled response/linear-solve error, and report Iref. Small negative roundoff
eigenvalues should not be misrepresented as either physical failure or proof
of continuum convergence.

## 24. Fixed inexact-Newton forcing checkpoint

Inspection of the new flow source found GMRES requested rtol5e-9 while its
independently recomputed true linear residual gate remains1e-8, info0 is still
required, and final nonlinear/backtracking/continuity/energy/range checks remain.
For e=Jdelta+F, forcing `norm(e)<=eta norm(F)` gives
`F(x+delta)=e+O(norm(delta)^2)` locally. Eta<1 supports contraction once the
Taylor remainder is sufficiently small; it does not establish global convergence.
Step error also satisfies `norm(delta-deltaNewton)<=norm(J^-1) norm(e)`, so
conditioning still matters. Aligning the requested Krylov stopping tolerance
inside the unchanged true-residual contract does not weaken that contract;
previous info-failed receipts must not be retroactively accepted.

Primary author copy read: [Eisenstat and Walker,SIAM J.Scientific Computing17(1),
January1996,16–32,section1](https://users.wpi.edu/~walker/Papers/forcing_terms%2CSISC_17%2C1996%2C16-32.pdf),
DOI10.1137/0917003. The current constant forcing is not their adaptive forcing
selection algorithm. Independent execution of the current inertial and Schur
suites passed11tests in11.537s. Reviewed flow source SHA256
`6e587891b49f3305561498fb8eb18a38507f69be02585b983b0329ebf55ad9dc`.
No actual blade-load result or qualification follows from this stopping-rule
review; nonlinear failure and resource limits still reject the trial.

## 25. Pressure-gauge pin reduction of the unchanged retained system

This is a linear-algebra reduction, not removal of a physical continuity
condition. For the actual assembled/scaled block matrix, write

```
[A  G  0] [u]   [fu]
[C  0  g] [p] = [fp]
[0 g^T 0] [L]   [fg].
```

Let z be the pressure-constant mode in THESE coordinates. Require BOTH
`Gz=0` and `z^TC=0`; with SUPG, G need not equal C^T, so one null check does
not imply the other. Also require z^Tg nonzero and no additional uncontrolled
pressure-null modes. Then

```
L=(z^T fp)/(z^T g),
fp_projected=fp-gL.
```

Choose k with z_k nonzero, preferably maximum absolute magnitude. Remove
pressure column k and continuity row k, set the intermediate pressure p_k=0,
and solve the resulting square velocity/pressure system. Recover the original
gauge by `p←p+z*(fg-g^Tp)/(g^Tz)`. The velocity equation is unchanged because
Gz=0. The omitted row follows from `z^T fp_projected=0` and z^TC=0. The
multiplier L is retained, not silently set to zero. A full original-system
residual check must include the omitted continuity row and gauge row.

Under the current constant-viscosity scaling sp=sqrt(mu/pressure_mass), the
physical constant pressure mode is z=1/sp. The normalized mean-pressure
functional g=pressure_mass*sp is proportional to z in this particular case;
that relation is not generic and must not be assumed in a reusable reduction.
For closed Dirichlet velocity boundaries, constant pressure gives zero
pressure gradient and the constant pressure test integrates divergence to
zero boundary flux. The P1 partition of unity and exact polynomial integration
support these discrete identities, including the SUPG pressure-gradient term.
Natural/open boundaries, different stabilization or assembly roundoff can
invalidate them; check the ACTUAL retained matrix rather than imposing a
null by projection or changing the PDE.

For approximate nulls, the dropped residual obeys
`z_k r_k=(z^TC)u-z^Tfp_projected-sum_kept z_i r_i`; pressure restoration also
adds `Gz` times its shift to momentum residual. Small normalized null defects
therefore do not alone guarantee the full residual, especially with large
pressure shifts. Fail-closed prechecks plus independently recomputed original
relative residual<=the existing1e-8 threshold are mandatory. A bounded direct
factorization must still report failure on singularity, memory or time budget.
The goal is to remove a dense numerical gauge border from the factorization,
not to weaken momentum, continuity, nonlinear, energy or physical-load gates.

Primary support: [PETSc3.26,Guide to the Stokes Equations using Finite Elements,
physical/weak-form introduction](https://petsc.org/release/tutorials/physics/guide_to_stokes/),
pressure as a Lagrange multiplier and the mixed signs; [Wathen,Acta Numerica2015,
section5](https://people.maths.ox.ac.uk/wathen/preconditioning.pdf), saddle-point
algebra. The pin/elimination proof above is independently derived. No external
implementation is copied; only the physical/linear-algebra theory is used.

An independently authored nonsymmetric oracle used5velocity and3pressure
unknowns, z=(1,2,4), g=(2,-1,3), arbitrary velocity/continuity/gauge RHS,
G!=C^T but both prescribed null identities, and a nonsymmetric positive-
symmetric-part velocity block. The independently coded pin/recover procedure
matched full direct solution with maximum difference1.11022e-16 and original
relative residual3.32752e-16; omitted-row residual2.22045e-16. The multiplier
was.6415017034 and nonzero gauge RHS.4677595282, both preserved.

The same oracle then exercised the owner's actual pressure-pin helper and
reproduced those errors. Dedicated owner test independently passed1test in.004s.
Reviewed helper source SHA256
`43746ad9a0207021f68cba76d9bf55584545f587a1c7eb595c5508142a7c5b9c`;
test SHA256
`8ac4b4da45d82e7fc3b581a08b5bfd2977abb699e5ad2ef103b5760a2aa11725`.
Inspection found block/null/gauge signs consistent. The helper intentionally
does not admit a result; reconstruction finiteness and original full residual
must be checked by its caller. No new actual-air solve or physical validation
was performed by this reviewer.

## 26. Hub-only surface repair and pressure-kernel preflight review

Bounded independent review read the retained surfaces/receipts and performed
sparse matrix-vector checks only; no large flow assembly or solve was duplicated.
The cleaned simulation surface SHA256 is
`1acd73405d9bfb2c9961511f336f487bb8dfafbc37225940cd51a7cbde0e8abd`.
Its input was the already marked simulation hub-regularized surface,
`fc451de0211a6da4a8a1315465c3540580271d07db768856ca79f6ebb8fd1a45`,
not untouched supplier CAD. Whole-source distance receipts separately bind it
to the original selected propeller SHA4659b1f7... and retain CC-BY-SA4.0.

Independent inspection of the actual two meshes confirmed exactly two changed
input vertices, original384→383 and433→432, each0.419093206micrometre.
Both are pre-existing edges. For each, the common vertex-link is precisely the
two opposite vertices of its incident faces and the vertex-links have no common
edge: the2D edge-collapse link condition holds on this actual fixture. Connected
surface components remain1→1. Retained receipts report vertices2677→2675,
faces5362→5358, Euler characteristic−4 unchanged, closed consistently oriented
edges, no zero-area triangles, unchanged bounding box and maximum uncollapsed
normal change.336745degrees. Signed volume changes by about8.82e-7mm³.
This strengthens the actual topology evidence beyond Euler alone; a generic
nearby-vertex VTK merge is not guaranteed to preserve topology without such
checks. Future adversarial tests should include nonadjacent near hub sheets,
a tetrahedron-surface edge with a common link edge, an outside-hub close pair,
a topology-changing contraction and normal inversion.

Whole-original-to-cleaned and reverse continuous distance bounds were
.299964129/.299996741mm under the declared.3mm tolerance, using the previously
reviewed convex-triangle/Lipschitz cover and floating margin. The coarse source
approximation dominates this bound; it does not establish aerodynamic geometry
accuracy. Fresh HXT mesh receipts retain10602positive tetrahedra, maximum
condition9325.4523 and no condition>1e6. Full topology/intersection admission
was subsequently recorded as passed. These are geometry prerequisites, not
near-wall, pressure-stability or flow/load convergence certificates.

The assembly-only pressure preflight retained C of shape3539×23799 and eight
lowest eigenpairs of CC^T. Receipt zero threshold was3.1910e-13, eigenvalues
started−1.4391e-17,5.44227e-6,5.45144e-6. Independent postprocessing of those
saved matrices, without recomputing eigenvalues, found eigenvector
orthogonality error3.60e-15, matrix-free Gram residual maximum9.97e-17 and
actual norm(C^Tv) values2.78e-16,.002332866,.002334832 for the first three
vectors. Actual upper-G and C^T products of the supplied constant/gauge vector
were both1.45e-16, and the supplied gauge exactly matched the retained matrix
column. This is strong case-specific evidence that the two previously resolved
extra continuity-left-null modes are absent in this REMESHED Stokes operator.
It is not a uniform inf-sup/LBB proof or a statement about every later SUPG
Newton operator, pressure accuracy, traction or load.

Review found robustness gaps in the initial preflight helper: it assumed a
physical constant mode from g without receiving actual pressure scaling,
did not bind its g argument to the actual matrix gauge, recorded eigenpair
residuals without gating them, and saved inputs only after a successful dense
eigensolve. These findings were sent to the owner. Version2 under development
now supplies1/sp independently, checks the matrix/gauge blocks and upper/right
constant mode, retains C/input metadata before eigensolve, records failure,
and gates eigenpair residuals. A test run during that signature update failed
with a missing pressure_scaling argument; that was a snapshot mismatch and
is not reported as a passed final test.

One remaining classification caution was sent: a relative eigenpair-residual
gate1e-10 is looser than the numerical-zero cutoff1e-12. Near the cutoff,
classification uncertainty must be screened explicitly, for example requiring
null/non-null residual intervals separated from the cutoff or direct
norm(C^Tv)² Rayleigh checks and orthogonality. Failure/nonconvergence or an
unresolved spectral gap must reject the screen and retain evidence. The ACTUAL
retained case has a gap over seven orders above the zero cutoff and residuals
near1e-16, so this concern does not undermine that case-specific observation.
An upper pressure block with a different kernel, additional disconnected
pressure modes or a gauge orthogonal to the physical constant requires its
own rejection; a C-only screen must not be relabeled full saddle-point
stability. No source repair was adopted as a reason to relax the original
linear, nonlinear, continuity, energy, Mach or load gates.

### Section 26 follow-up: atomic v2 independently checked

The final v2 now derives the physical constant mode from actual pressure scaling, binds the gauge to the matrix row/column, checks both continuity-left and upper pressure constant modes, retains inputs before eigensolution, and rejects ambiguous spectral classification using bs(lambda0)+rho0 < threshold and lambda1-rho1 > threshold. Inspection found these changes address the review findings. This residual-interval screen remains a finite-precision numerical diagnostic; it does not certify uniform inf-sup stability or aerodynamic loads.

Independent execution: .venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_inertial_cfd_preflight -v passed all 3 tests (0.114 s), including constant-only versus extra-mode cases, eigensolve failure/input retention and invalid eigenpairs, and uncertain spectral classification rejection. No actual assembly or flow solve was repeated. Reviewed source SHA256: 5c0fbd79d37b06f16e9f16d08467dc82c4b1b713f73774486f329b812438818b. Reviewed test SHA256: 71113b953b285f87c988ddfe4e382451098299f059de8da9b74094cea735c438. This supersedes the preceding transient API/test-race status only; the retained actual case receipt described above was produced before v2 and is not silently relabeled as a v2 execution.


## 27. Independent geometry-loop capture/package integration review

This bounded read-only integration review inspected geometryPodStudy.ts, GeometryPodCapture.tsx, GeometryPodFields.tsx, normalizer/dispatcher changes, package_geometry_loop.py and attach_geometry_snapshots.py. No PDE or actual coupled result was run. Source/result hashes, effective thermal normalization versus original request-file hash, endpoint currents/angle binding, unqualified flags and interval-versus-endpoint labels are retained. Native packaging passes preserved archive members, retains assets/KiCad companions and reconstructs adjacent exact embedded board bytes through the established colocator; no actual final package/GUI verification is asserted by this inspection.

Two concrete corrections were sent to root. (1) Exact equality of interval end and next sample time rejects genuine runner output when now+dt differs from (index+1)*dt by rounding; align runner indexed times or use a small scale-aware presentation tolerance. Add a multi-step generated fixture, not only a one-step example. (2) Admission validates rotor/stator domains but the field renderer iterates every Object.values(domains); an extra unvalidated domain can pass admission and crash rendering. Admit exactly the two supported domain keys, or render only those validated keys, and add an extra-domain rejection fixture.

Independent focused checks executed: tests.python.test_propulsion_pod_package, 2 tests PASS (0.001 s); node scripts/test-geometry-pod-capture.mjs PASS. These existing fixtures do not cover the two findings above. Remaining integration limitations: the package helper checks request/file/table identity and endpoints rather than full GUI history schema; passing its tests alone does not prove a newly packaged result will be admitted by the UI. Snapshot attachment separately re-solves the retained model at endpoint state, and the retained derivation identifies that reconstruction; it must not be represented as controller integration steps or continuous fluid history. Physical-load and production qualifications remain false. Root owns corrections and final verification.


Section 27 correction check: root changed interval admission to finite, scale-aware 32-epsilon comparisons, future generation to (index+1)*dt, and domain admission to exactly rotor/stator. Independent source inspection confirmed these changes; the updated JavaScript capture script passed, including the 20-step roundoff history and unsupported-domain rejection. Reviewed geometryPodStudy.ts SHA256 620d2d65afb5095e4476dfa2a39eeb9f2f535f3f678649ad5411cb354d630be4; capture test SHA256 5d1d2fdfdcba060978aefe2dc873fc2c0d18050878b8378e37dcb44f5256fb52. No further consequential integration finding in this bounded inspection. Final actual package admission, source inventory and GUI verification remain the integration owner's checks, conditional on actual numerical results.


## 28. Repaired-matrix SIMPLE review and closed torque diagnostic

Independent inspection of the fixed SIMPLE owner confirms the bordered algebra for the scaled base matrix [K,C^T,0; C,0,g; 0,g^T,0]. With D=diag(K), S=C D^{-1} C^T, y=K_ILU^{-1} r_u, solve [-S,g;g^T,0](p,lambda)=(r_p-Cy,r_g), then x_u=y-K_ILU^{-1}C^T p. The sign and arbitrary gauge RHS are retained. A pressure null vector z need not equal g, but g^T z must be nonzero; extra C-left-null modes orthogonal to g make the bordered S singular. Removing the observed extra modes by geometry repair therefore changes the applicability of the previous failed preconditioner experiment; replay on the new retained matrix is discriminating, not guaranteed successful.

with_velocity keeps the original C/S/g and substitutes a new velocity ILU; it still uses C^T rather than the possibly different SUPG upper G. This is a permissible fixed approximate preconditioner, not the exact new Jacobian inverse. Full original-system true residual remains the acceptance criterion. SIMPLE's diagonal velocity approximation can remain weak on anisotropic meshes and advection-dominated systems; the finite kernel screen alone does not prove useful spectral equivalence. Wathen (2015), Preconditioning, section 5, supplies the previously reviewed saddle-point block context; no external implementation was copied. Independent dedicated Schur test PASS (1 test, 0.026 s), covering non-null-aligned gauge and arbitrary full RHS. Reviewed source SHA256: fdcd765aa112b64baf5241a320bda166f9dd17c6c560db6b0ce4f4ebdbef4f6a. No heavy matrix replay, linear solve or PDE was duplicated.

For a cheap postprocessor on retained fields, use the global rigid angular test v=e_axis cross (x-origin). It is exactly representable by P2 and has symmetric gradient and divergence zero, so volume viscous and pressure virtual torque vanish. Let w=u-Omega cross r. The consistent Temam angular transport equals boundary integral rho*(u dot v)*(w dot n) minus one-half volume integral rho*div(u)*(u dot v); the angular Coriolis term cancels the derivative of v in the advective integration by parts. Retain body virtual torque integral f dot v. SUPG contributes its actual test work integral tau*((w dot grad)v) dot R_m, with (w dot grad)v=e_axis cross w. This term is not physical stress or dissipation. Sum weak boundary reactions on rotor and outer boundary separately, plus the free residual tested with v; compare with the same complete transport/body/SUPG terms. Independently integrate recovered Cauchy torque on both boundary groups. This closed torque balance distinguishes reaction/operator consistency from derivative-based traction recovery without a new flow solve. Do not discard expected-zero outer fluxes before measuring them, and do not infer load convergence from an energy identity.


## 29. Independent full-period phase/RMS/bridge convention audit

The retained datasheet text states phase current RMS and torque constant Nm/Arms. Independent reconstruction used the actual 512-table PM linkage, periodic cubic differentiation, balanced projection P=I-11^T/3, and direct sine/cosine least squares on 8192 uniformly spaced mechanical angles (no PDE solve and no parameter fitting). This independently reproduces the owner's Fourier audit: mean PM torque coefficient 0.194978403807849 Nm per unit total phase-RMS norm, versus datasheet 0.13, ratio 1.499833875445. Individual phase RMS currents of this normalized fundamental-aligned template are 0.9996915,1.0001742,1.0001342 A; this tiny model asymmetry does not explain the 50% discrepancy. Datasheet continuous and peak operating ratios are 8.2/61=0.134426 and17.5/138=0.126812 Nm/Arms, independently consistent with the declared approximately0.13 convention. These are source plausibility comparisons, not calibrated tests of our constitutive substitutions.

General reciprocal PM work is e=omega_m*P*dpsi/dtheta and tau_PM=i^T*dpsi/dtheta for balanced i, so e^T i=omega_m*tau_PM pointwise. A sinusoidal balanced special case with phase PM flux peak Psi and p pole pairs has phase EMF peak p*Psi*omega, phase EMF RMS k_e*omega where k_e=p*Psi/sqrt(2), and mean PM torque3*k_e*I_phase_rms=(3/2)*p*Psi*I_phase_peak. RMS line voltage is sqrt(3) times phase RMS; peak line voltage is sqrt(2) times line RMS. Accordingly, if Kt is per phase RMS and Kv is rpm per line RMS volt, Kt*Kv=sqrt(3)*60/(2*pi)=16.53986686, not60/(2*pi).

Ideal linear SVPWM gives fundamental phase peak m*Vdc/sqrt(3), phase RMS m*Vdc/sqrt(6), and line RMS m*Vdc/sqrt(2). At maximum linear modulation m=1 and no voltage drops, Kv_bus=Kv_lineRMS/sqrt(2), hence Kt_phaseRMS*Kv_bus=sqrt(3/2)*60/(2*pi)=11.69545202. At arbitrary modulation the no-load bus-speed slope changes with m. Current and voltage conventions must therefore both be declared. Lossless averaged bridge power is Vdc*Ibus=sum(v_phase*i_phase), with Ibus=sum(d_phase*i_phase) for balanced currents; zero-sequence/common-duty offsets do not change power. Balanced sinusoidal unity-power-factor conversion gives Ibus=sqrt(3/2)*m*I_phaseRMS. Only a matched bus-current torque coefficient at the same ideal operating/modulation point recovers the simple scalar Kt_busCurrent*Kv_bus=60/(2*pi). With harmonics, reactive current, resistance/losses, cogging or saliency there is no universal scalar replacement for the actual waveform work relation.

Independent receipt: output/promo-propulsion-pod-20261023/real_motor/independent-constant-convention-review.json. Source table SHA256 f9d83d98f41e6412abb5dffb8cf2384caba52cb2cc2c69ea4021eb5f92d42e03. Fundamental phase EMF RMS coefficients0.064973..0.065004 V/(rad/s), line RMS0.112551..0.112606, imply Kv_lineRMS84.803..84.844 rpm/V and ideal maximal-linear-SVPWM Kv_bus59.965..59.994 rpm/V. An independent ideal averaged-bridge power identity at omega100rad/s, one phase-RMS-norm ampere and0.1% modulation headroom uses bus15.93584V, mean DC current1.223521A, converted19.497840W and defect1.07e-14W; admitted duties0.000345..0.999655. This is arithmetic on the table, not a switching/controller or hardware run.

Primary references actually reviewed: MathWorks R2026b official PMSM Torque Estimator equations (3/2*p torque, P=tau*omega), https://www.mathworks.com/help/mcb/ref/pmsmtorqueestimator.html ; and PWM Generator (Three-phase, Two-level), Overmodulation section, explicit phase-neutral fundamental peak and linear SVM voltage relation, https://www.mathworks.com/help/simscape-electrical/ref/pwmgeneratorthreephasetwolevel.html . No external implementation was copied. The retained datasheet Kv74 rpm/V voltage convention is unspecified. Its numerical proximity to60/(2*pi*0.13) suggests a scalar convention or source inconsistency but cannot identify which; neither its Kv nor RMS/peak reinterpretation repairs the explicitly same-phase-RMS Kt discrepancy. Isotropic illustrative steel, substitute PM recoil, intended-versus-literal winding connectivity, 2D/extruded versus3D/end effects and absent hardware calibration remain material limitations; no rescaling/fitting is authorized by this audit.

### Saved-field angular ledger follow-up

Read-only inspection of output/inertial_cfd/independent_angular_ledger.py confirms the section28 rigid-test signs and terms. Its retained weak rotor/outer torques6.32153e-5/-6.35584e-5 Nm and free residual approximately-9e-17 close the global discrete identity to2e-20 Nm. Recovered rotor/outer torques1.47765e-5/-6.10052e-5 have raw global imbalance approximately-4.616e-5 Nm. Temam/SUPG terms approximately-6.823e-8/-2.749e-7 Nm are insufficient to explain the raw/weak gap. This identifies a recovered stress/balance discrepancy and does not qualify either traction or the physical formulation. Parameter hardcodes (rho,Omega,origin) should be asserted against retained stage metadata before applying the postprocessor to other stages; mesh/field hashes alone do not enforce those parameter identities. No integration or solve was repeated in this inspection.

Angular-ledger follow-up from owner: parameter provenance is now derived from exact request plus stage-2 history and both are hashed; reported rerun matches prior values. Updated script SHA2567a1b44b3fdb2c62711afda390ca03d6814eddae9e294ad7ad6aad31e60f89ee7. The full script path is output/promo-propulsion-pod-20261023/inertial_cfd/independent_angular_ledger.py. This update was reported by its owner; the independent algebra inspection above remains the executed review evidence.


## 30. Independent relative-forcing Newton derivation and applicability review

The retained absolute-budget choice eta=min(0.1,0.1*target/E) requires eta~1e-10 for E~1,target1e-9, even far from the nonlinear root. A separately named fixed-relative method with eta=0.1 is mathematically established and can avoid this early oversolve. It must preserve the old algorithms, equations, final nonlinear target1e-9 and all continuity/energy/load gates; it is not retroactive acceptance of failed runs. No heavy numerical job was performed in this review.

Independent derivation in the actual fixed scaled physical coordinates: let F be the assembled physical residual after enforcing boundary values and pressure gauge, and s the update actually applied. Require the independently recomputed actual-direction defect e=F+J*s to satisfy norm(e)<=eta*norm(F), eta<1. If J is Lipschitz with constant L along the step, the integral Taylor remainder gives norm(F(x+s))<=eta*norm(F)+L*norm(s)^2/2. For damped alpha in(0,1], the bound is [1-alpha*(1-eta)]*norm(F)+L*alpha^2*norm(s)^2/2. Consequently norm-Armijo with factor1-c*alpha*(1-eta),0<c<1, is locally achievable for sufficiently small alpha. Invertibility/bounded inverse of the gauge-fixed Jacobian controls step size and supplies the local convergence hypothesis. Constant eta0.1 supports local linear convergence only; superlinear convergence requires eta tending to zero and is not claimed. A finite bounded backtracking list can fail before reaching a suitable alpha and must refuse the step.

Code inspection identified two important applicability conditions communicated to root/flow. First, the current line search merely checks E_trial<E_current; E=norm(rr)/S(u), and S includes state-dependent transport on prescribed boundary data. This is not fixed-merit Armijo, since a growing denominator can mask residual growth. For the new method use the norm of the actual fixed-scaled rr, or freeze the current S while comparing all trials. Recompute the original final normalized target independently afterward. Second, the bordered linear system includes continuity contribution g*delta_lambda, but the physical update discards the multiplier delta_lambda and the residual gauge row is hardcoded zero. Therefore actual-direction linear defect is bordered_defect minus [0,g*delta_lambda,0], not automatically the bordered defect. Gate the actual physical-direction defect or explicitly bound this discarded multiplier term, and preserve/check pressure mean. Exact compatible closed-boundary algebra should make that multiplier small, but finite-precision compatibility cannot be assumed. Re-evaluate actual trial residual for backtracking regardless.

Practical bounded recommendation: new explicit fixed_relative_forcing_v1 with eta0.1, inner requested reduction0.05, independently measured actual-direction forcing<=0.1, norm-Armijo c1e-4 with retained bounded halvings, unchanged final physical/nonlinear admission. Retain eta, requested and measured linear norms, multiplier contribution, accepted alpha, pre/post residual norms, normalizing scale and final target in receipts. If singular/poorly conditioned Jacobian, incompatible continuity, nonfinite state/correction, insufficient Krylov budget, no acceptable backtrack, or final physical gates fail, return failed/incomplete. Do not claim efficiency until measured. A non-scalar change of residual scaling changes the chosen norm and must be declared; scalar normalization of a linear RHS alone preserves its relative residual criterion.

Primary source actually reopened/reviewed: Eisenstat and Walker, SIAM J.Sci.Comput.17(1),16-32(1996), Choosing the Forcing Terms in an Inexact Newton Method, DOI10.1137/0917003, author PDF https://users.wpi.edu/~walker/Papers/forcing_terms,SISC_17,1996,16-32.pdf . Section1 equation1.2 defines forcing, Lemma1.4 gives the local residual bound, and section3.1 treats globalization; its fixed0.1 experiments do not establish performance for this mesh. This recommendation is the explicitly fixed relative method, not an implementation or convergence claim for adaptive Eisenstat-Walker choices. No third-party implementation was copied. Source snapshots reviewed: {'propulsion_pod_inertial_cfd.py': '2746b59d819a73df44f6c9482176a9b1a909db7d6a64dca78e2b36ec1d3aa02a', 'propulsion_pod_inertial_cfd_inexact.py': 'dab7d180d0d563e9311010524e6a765dc205ef969f3a4d3988faff2733ad799f', 'propulsion_pod_inertial_cfd_linear.py': 'b5fafa6f4473ee532193656d497c8d93783fd3fa88c463112880917c4d1e9e8c'}. Required focused verification before actual use includes a nonlinear manufactured solution reaching final target, backtracking rejection where variable-normalized E would decrease despite raw residual growth, nonzero discarded-multiplier counterexample, and unchanged failure after a bounded unconverged outer iteration. Source edits and executed new-method tests belong to the flow owner.


### Section 30 implementation review: fixed_relative_forcing_v1

The implemented method was independently inspected after the derivation: the physical pressure gauge residual is g dot(p/sp), matching the scaled Jacobian gauge row; the actual applied direction removes g*delta_lambda from continuity while preserving the pressure-mean derivative. Its independently recomputed defect is bounded by eta0.1, and the norm directional derivative is F dot(Jphysical*s)/norm(F), required negative. Norm-Armijo uses the same raw scaled residual vectors and c1e-4. Final nonlinear target and boundary work gates remain in force. strict_refined remains default, with the prior absolute-budget and strict branches preserved. No consequential finding in this bounded source inspection; it supports a separately identified research restart, not flow convergence or qualified loads.

Independent execution of the two cheap helper adversarial tests (discarded multiplier and variable-denominator false decrease) passed2/2 in0.005s. The owner's additional nonlinear/MMS/gauge and regression executions were reported separately; they were not duplicated here. Reviewed source hashes: {'propulsion_pod_inertial_cfd_forcing.py': '7ba3cedaa17b92acea0da5b4da515ec96c3c9c9aac8686c2a3261d96b5f1751e', 'propulsion_pod_inertial_cfd.py': '89b88eeafbe0e85c9a3efe06d6742f98a65289cd1616e7b855c15d7345077697'}. No heavy solve or numerical source edit was performed by this reviewer.


## 31. Independent supplied-law nonlinear P2 review

The numerical author and independent reviewer are distinct. Inspected propulsion_pod_nonlinear_p2.py SHA25648cf046044d373fa95f21985afae8cf377cf78cded51a0d433a344389725f304 and tests SHA2567587b9530ac75e0c03175e038137b9e044c02ba85cff59ccea5675d7fcab2aba. Independently ran all10 focused tests: PASS0.049s. No actual motor mesh or coupled study was run.

Independent derivation confirms for isotropic single-valued H(B)=h(b)B/b, w(b)=integral_0^b h(s)ds; D=(h/b)I+(h_prime-h/b)uu^T, with positive radial/transverse eigenvalues for the admitted strictly increasing curve. At zero the first-segment slope defines both. Piecewise-linear h gives continuous H and energy but a tangent jump at knots, so smooth quadratic Newton convergence is not asserted. The implemented generalized one-sided tangent, energy and residual use exactly the same fixed positive quadrature. Current load is subtracted once. Unreplaced linear PM regions use the full shifted energy0.5(B-Br)^Tnu(B-Br), including the constant PM reference; their H already incorporates the PM source, so adding base.pm_load again would double count. Nonlinear replacement is restricted to zero-Br regions and supersedes their original linear law entirely.

Units check: A_z Wb/m, curl basis1/m, energy densityJ/m³, depth-weighted residual A*m, tangent A*m²/Wb=m²/H. Positive D and positive order>=2 quadrature preserve positive free tangent after every connected component is gauged, subject to finite-precision conditioning. Duffy barycentric mapping has normalized Jacobian2s and positive product weights; nonlinear quadrature error is separate from exact discrete variational consistency. Since P2 B is affine, norm(B(lambda))<=sum lambda_i norm(B(vertex_i))<=maximum vertex norm, so the element-vertex range guard bounds the entire straight triangle. The declared1e-13 numerical endpoint allowance is not material-range extension.

Distinct independently authored analytic fixture: two triangles on the unit square, depth0.37m, uniform supplied curve[(0,0),(.4,.8),(2,5.6)], exact affine A=.6x+.8y+2 giving B=(.8,-.6), b1T. Direct curve integration gives h(1)=2.6A/m and w(1)=.16+.8*.6+1.5*.6²=1.18J/m³, U=.4366J. The solver returned exact nodal A to displayed precision and U=.4366000000000003J (error3.33e-16); free residual3.89e-16A*m. Adding constant10 to A changed U by1.94e-15J and residual by at most5.44e-15A*m. This independently checks nonlinear material integration and gauge invariance, not realistic dimensional material values.

No consequential assembly finding in this bounded review. The base prepared operator must remain unchanged during adapter use, as documented. Current-source coenergy fJ dot A-U omits prescribed-boundary source work: Wmaterial-Wcurrent=A_fixed dot reaction at equilibrium. Therefore a subsequent nonlinear annulus/circuit adapter must retain the boundary/reaction and annulus functional; this class is not a substitute constant response matrix for the existing linear Schur reduction. Quadrature/mesh/source-property convergence and hardware calibration remain separate. Actual H070 directional B-H/loss, actual PM identity and native wiring ambiguities are not closed by supplied-law support.

Primary foundation actually reopened for this independent review: Haus and Melcher, Electromagnetic Fields and Energy(1989), section11.4 Energy Storage, https://web.mit.edu/6.013_book/www/chapter11/11.4.html , single-valued constitutive energy and field/terminal coenergy. The nonlinear author's detailed derivation is docs/validation/PROPULSION_POD_NONLINEAR_P2_20261023.md; its authorship is not treated as independent review. No external implementation was copied. Human numerical review remains required before release.


## 32. Bounded exact-grade H070-20 primary-data admission review

Primary manufacturer evidence was checked on23October2026: [powercore product page](https://www.thyssenkrupp-steel.com/en/products/electrical-steel/electrical-steel-grain-oriented/powercore/powercore.html), its linked [grain-oriented catalogue](https://www.thyssenkrupp-steel.com/media/content_1/produkte/elektroband/electrical_steel_integration/thyssenkrupp_electrical_steel_product_range.pdf), revision03/2026, printed pages22,26,28-29 and32; and [family typical properties](https://www.thyssenkrupp-steel.com/en/products/electrical-steel/electrical-steel-grain-oriented/powercore/typical-physical-properties/typical-properties-and-tolerances.html). Grade H070-20 corresponds to M70-20R5,0.20mm. Its listed minimum is polarization J=1.88T at H800A/m, with maximum loss0.70/0.92W/kg at1.7T50/60Hz. Tests use SST IEC60404-3 and disclosed conversions. These are grade specifications, not a full static directional constitutive law. The catalogue warns that rolling direction and mechanical processing matter, and laser domain refinement is not heatproof.

No exact-grade directional static B(H) dataset with valid temperature/stress/processing/range metadata was located in this bounded review. The manufacturer family typicals are not batch measurements or the missing constitutive function. A wrong-grade020-130Y320 search result explicitly concerns50Hz directional polarization and is not admitted. Manufacturer-grade name correspondence does not establish the actual motor supplier or batch.

Independent interpretation: polarization and induction differ by B=J+mu0*H, so J800 cannot silently become B800; even a correctly converted minimum is only an inequality and does not determine low-field slope, saturation approach, directional response or an energy primitive. AC loss and exciting-current quantities do not identify a static reversible law without additional measured/model assumptions. A nonlinear actual-motor study therefore still needs measured directional static data, actual per-piece rolling orientation, assembly/cutting/stress and thermal conditions, and verified source/reuse rights. It may instead execute explicitly supplied illustrative curves, retaining model/property uncertainty. Kt matching is not material identification.

Receipt: output/promo-propulsion-pod-20261023/real_motor/material-evidence/H070-20-primary-data-admission.json. Manufacturer material is copyrighted; no open-data license was found. No raw PDF is redistributed or hash asserted: a bounded local urllib download failed DNS, while primary contents were read through the web tool. This is a bounded search result, not a claim that private supplier measurements do not exist. No implementation data conversion, extrapolation, coefficient fitting or PDE job was performed. Required source-property admission remains open.


## 33. Independent nonlinear separated-motor integration review

Inspected the joint operator and focused tests independently of their numerical author. Unknowns combine both domain interiors and their Fourier traces. With expansion maps T_r,T_s, the implemented scalar potential is Pi=sum_d[U_d(T_d*x)-fJ_d dot(T_d*x)]+0.5*c^T*Kgap(theta)*c. Its residual is sum T_d^T*r_d plus gap trace residual, and tangent is sum T_d^T*Kd*T_d plus gap. The outer zero essential gauge is inherited from the prepared separated motor. Nonlinear material replacement preserves full linear PM reference and incorporates its source in H exactly once; current loads appear once. At an admitted stationary state the envelope derivative gives flux=sum loads_d^T*A_d and shaft torque=-0.5*c^T*Kgap_prime*c. Wprime=i dot flux-Ujoint; nonzero internal trace boundary work cancels through the joint gap stationarity, unlike an isolated prescribed-trace source coenergy. This relies on material/source geometry held fixed in each local rotating frame and on theta dependence being confined to the analytic gap. No physical validity follows from that modelling assumption.

The reference inverse follows exact linear block elimination: solve each Kii for interior RHS, reduce trace RHS by V^T*Kbi*Kii^{-1}*rhs_i, solve the positive gauged combined reference Schur, then recover interiors by subtracting Kii^{-1}*Kib*V*c. It is used only as an SPD preconditioner for the new nonlinear tangent. Positive material differential tangent/positive quadrature plus real outer gauge support CG applicability; actual CG residual and descent are separately checked. Range failures, factor/CG/iteration/time budgets and failed line search reject rather than return an admitted field. CPU limits are cooperative between library operations, not hard preemption inside factorization.

Independent focused execution:6 tests PASS0.330s. A separately selected nonlinear synthetic fixture at currents[9000,-2000,-7000]A and theta0.173rad checked balanced direction[.3,-.8,.5] with independent coenergy differences: flux derivative error2.3431e-14Wb-turn; angular coenergy derivative versus torque error4.82455e-10Nm; two balanced differential-current directions give reciprocity defect1.89735e-18H; Legendre energy identity defect0J. Receipt output/promo-propulsion-pod-20261023/real_motor/independent-nonlinear-coupled-review.json identifies the synthetic fixture and executed source SHA25602eb60178f21aaabeefe2e1e872dca51476155ba202a6c14571ee28070417983. No actual motor material or mesh job was run.

One consequential integration finding was sent to root and author: returned source/spec identities initially identified only the prepared linear motor, so two distinct supplied nonlinear B-H laws could share the same reported constitutive identity. Author is adding an immutable canonical descriptor/hash binding exact supplied SI curve pairs/range, retained linear tensor/PM laws, geometry/depth/region identities and quadrature; prepared linear identities must remain separately identifiable. A supplied-law descriptor is not measured-material provenance. This finding must be verified closed before coupled-source binding is relied on. Prepared dependencies must remain unchanged under the documented internal contract; checking this must not add repeated expensive full-mesh hashing to every CG matvec. No further consequential variational/tangent/torque finding in this bounded review. Actual anisotropic steel law, PM identity, winding interpretation, numerical refinement and hardware calibration remain open.


## 34. Independent traction-recovery discrimination plan

The exact retained global ledger is stage2,rho1.225e-5kg/m³,Omega200rad/s; it must not be relabeled as auxiliary1e-4 or full air. Its weak torque balance closes while raw recovered Cauchy traction does not. This proves discrete virtual-work consistency, not traction accuracy. P2 velocity and P1 pressure are continuous, but the recovered velocity gradient and hence viscous stress generally jump across tetrahedra. Describing the pressure itself as discontinuous would be incorrect for this space.

Independent elementwise integration-by-parts identity: select continuous P2 v equal to axis cross r on the rotor and zero on outer boundary. For outward-fluid tractions, Lweak(v)-Lraw(rotor)=sum_K integral[R_m+0.5*rho*div(u)*u] dot v +sum_interior_faces integral[[sigma*n]] dot v +SUPG(v), where R_m=rho*((w dot grad)u+Omega cross u)-f-div(sigma), and the traction jump is sigma_plus*n_plus+sigma_minus*n_minus. Boundary consistency flux is included in the strong Temam representation. This identity distinguishes direct stress recovery from force definition without smoothing or redefining the admitted load. Use exactly the original local basis and quadrature; report cell residual, face jumps, Temam and SUPG separately, with wall/nearwall/hub/outer localization. These diagnostic contributions can cancel and are not a certified error bound.

Smallest tests before another large solve: (1) on each exact closed rotor/outer face set, add constant pressure and verify integrated force and torque unchanged; this checks normals, closure and patch identity. (2) choose two P2 interior extensions with identical boundary trace; their weak load difference must equal the stored free-momentum residual tested by their zero-boundary difference. This validates extraction invariance but not physical accuracy. (3) close the selector-wise residual/jump identity above on the saved field. (4) repeat fixed-field integration with order4/6 to distinguish quadrature from spatial recovery error; physical terms have degree at most5 here, while SUPG tau is nonpolynomial. (5) only then run a matched fixedgeometry/samedensity/samespeed nearwall refinement ladder. Both raw and weak loads must stabilise and approach under the existing directstress/traction and continuity gates; no swap to weak loads is authorized by this plan. Spatial singularities, insufficient wall resolution, geometryfaceting, SUPG or physical-regime limitations remain possible until discriminated.

Primary reference actually reviewed: official NGSolve tutorial3.2, Supplementary1 Computing stresses, https://ngsolve.org/ngsolve/docs/i-tutorials/unit-3.2-navierstokes/navierstokes.html , retrieved23October2026. It derives residual evaluation of obstacle force and recommends comparison with direct surface stress. Its displayed gradient-form stress differs from SPIKE symmetric Cauchy stress; only the residual-extraction principle is used here, with the identity independently rederived for SPIKE's operator. No implementation was copied. Retained bounded plan/source binding: output/promo-propulsion-pod-20261023/inertial_cfd/independent-traction-recovery-test-plan.json. No large assembly, linear/PDE solve or owner source edit was performed.


Section34 implemented postprocessor review: inspected output/promo-propulsion-pod-20261023/inertial_cfd/independent_jump_ledger.py SHA256661cdc0bd471fd89b8f92ef0c2e5ef351e656096e89c812dc047fd7c390a9506, without rerunning it. Owner's output-only integration matches the independently derived signs: sorted shared-face barycentrics map to the owning tetra correctly, normals point outward per owner, the continuous P2 selector has the intended rotor rigid/outerzero trace, full symmetric-stress divergence is retained, and Temam/SUPG terms have consistent signs. Reported weak-minus-raw4.84387953e-5Nm decomposes into strong-cell2.01078354e-5, interiorjump2.78958266e-5, Temam2.72488e-8 andSUPG4.07885e-7Nm, with identitydefect approximately-6.2e-19Nm. This identifies unresolved equilibrium/jump contributions, not load accuracy or convergence. The implementation author is the flow owner; separate-author source inspection supplies independent review. The script runpy-executes the preceding angular diagnostic and rewrites its parent receipt before hashing, so the parent diagnostic is recomputed rather than treated as an immutable input artifact. No solver state or PDE is changed by these diagnostics.


Section33 constitutive-identity finding CLOSED after independent reinspection: nonlinear P2 sourcee5ffd6e9ea92f3bcbc44d85cc6ff2e950821e3c0681394ca0acb896b975e9b30, nonlinear motor sourcef3af4419011c205058f8c1fcb5912de2a9fa061bfde1445e4936a8aaf5310a20. The canonical descriptor binds exact copied supplied B-H SI pairs/range/status, retained per-region tensor reluctivity/PM laws, depth, wrapped mesh/operator and exact quadrature. The coupled identity adds gap/trace/source dependencies; prepared linear spec is nested separately and no longer reused as nonlinear spec. Detached metadata and owned read-only arrays prevent ordinary snapshot edits from changing the operator. Entry/exit fingerprint checks reject changed operator/material/trace/gap/source/factor dependencies. Coupled trial assemblies use the verified internal path; no full dependency hashing occurs inside CG matvecs or trial assemblies. Independent focused execution of all four new identity/mutation tests PASS0.099s, including changed law/quadrature identity, detached metadata and changed-dependency rejection. This closes constitutive identity binding, not actual material provenance, directional-law adequacy, convergence or hardware calibration.


## 35. Memory-only CFD restart changes, independent review24October2026

Inspected explicit SimpleSchurStokes(reference_velocity=False): defaultTrue remains; omitted seed sets ILU/preconditionerNone, solve refuses explicitly, and with_velocity constructs the same current velocity ILU and C/Schur action. Its closure retains the current ILU for the returned operator lifetime. Stokes assembly chunk deletion occurs after CSR conversion and before factorization; contiguous gradient preallocation assigns the same local basis gradients without a temporary complete list. No mathematical formula change found. Independently executed full-border/omitted-seed/current-action test PASS1/1 in0.021s. No actual mesh solve, memory-cap change or numerical-owner edit was made.

One concrete counterexample invalidates a claimed count equivalence: SuperLU.nnz is not generally equal to the exposed L.nnz+U.nnz. For independently constructed tridiagonal[-1,4,-1], sizes3,10,50, LU scalar counts are12,110,290 while exposed L+U counts10,40,200; ILU scalar counts12,110,281 versus10,40,200. The initial parity assertion failed, and direct printed counts established the mismatch. This does not indicate changed PDE or factor action, but a budget based on scalar nnz must not be described as the exact prior L+U count. It is larger in these examples; storage-proxy semantics and any conservative change to rejection behaviour must be explicit. Sent findings to flow owner and root before actual restart claims.

Reviewed source snapshots: Schur d64c34919ce4701f68a24dfbc7e705f7035b4ddeffbe23a147241c449f1c66a3; inertial8610028d0fbce78de4bee1044cd5d63c4ad74aeceac09927ea470ac21fd760e4; Stokes91da8f6ebd49a1b05a6aca8eaf5b56c77354d3dea21a949f505d816564a98361. Observational memory callbacks do not prove the bounded restart fits2GiB; that requires the owner's separately retained actual profile/run.


Section35 pinned primary-source resolution: installed scipy.__version__ is1.17.0. Reviewed [SciPy v1.17.0 _superluobject.c](https://raw.githubusercontent.com/scipy/scipy/v1.17.0/scipy/sparse/linalg/_dsolve/_superluobject.c), getter lines134-137 and170-175, conversion414-456 and519-638. The scalar getter sums native factor nnz fields. Accessing either exported factor creates and caches both CSC factors. Conversion splits supernodal storage, skips exact-zero entries and inserts unit L diagonal. Separate native-count bounds constrain both emitted CSC counts. Therefore for successful conversion in this pinned implementation, the scalar sum upper-bounds exported L.nnz+U.nnz; it need not equal it. This is a source-level inference, not a general API guarantee across versions. The integer sum must remain representable; the project30million cap is well below the signed32bit boundary. It is not a bound on peak process bytes, native workspace or factorization before the count is available. Using the same numeric threshold with this native counter is an explicitly conservative gate change for the prior exported-entry budget and avoids CSC conversion allocation. Installed docstring alone was too imprecise to establish these semantics. Negative tridiagonal evidence above remains valid. No expensive jobs or implementation copying were performed.


## 36. Executed v12 fraction0.001 residual/jump localization

Owned output-only script output/promo-propulsion-pod-20261023/inertial_cfd/localize_v12_traction_gap.py directly reads the exact v12 stage2 field, source mesh, request/history and existing order4 global ledger. It does not runpy/import executable parent diagnostic scripts, assemble sparse operators, factorize, solve PDEs, refine or modify prior receipts. Inputs are SHA-bound before and after execution; fieldcf7b9298e0465e85f1fb659169810efa7ddc927a9a0c3b91a5ad963c0c72e0cb, meshc95c93da935b1c8b9114ca79be3a9f1996b9acdbc5addd7e99166a270630c6ef. Stage2 has densityfraction0.001,rho0.001225kg/m³,mu1.81e-5Pa*s,Omega200rad/s,axisY,origin[0,.01,0]m and is explicitly auxiliary, not fullair. Existing volume order4 and face quadrature were retained. Initial run6.75s; final repeat after adding SUPG topcell reporting5.016s, both below60s. No new numerical quadrature or physical equation was introduced.

The weak-minus-raw rotor torque0.0003818152738121763Nm decomposes into strongcell0.0001467942651965408, interiorjump0.0000535091209503557, Temam0.0000110168878027719 andSUPG0.0001704949998625080Nm. Summed selector identity defect4.81e-19Nm reproduces the bound stage ledger. Stage-specific SUPG contribution is substantial; the earlier v10 tiny-SUPG observation must not be transferred here.

Absolute contribution concentration (signed quantities may cancel): strongcell absolute sum0.0005748478Nm reaches50%in92cells,80%in526,90%in988; facejump absolute sum0.0002324609Nm reaches50%in45faces,80%in362,90%in914. SUPG absolute sum0.0001751748Nm reaches50%in5cells,80%in13,90%in21; top10cells account73.24%. Leading SUPG cellIDs617,6499,10566,1882,8113 have respective centroids[-.0433856,.0167276,-.184741],[.0271857,.0234798,-.197275],[-.0304796,-.0498916,-.176075],[.00992485,-.0359101,-.201207],[.0215536,.0363282,-.151756]m. These IDs provide a small first inspection set for geometry/flow-layer diagnostics, not certified refinement marks. Strong contributions are split by exact topological rotor-boundary-face adjacency; anatomical hub/blade-tip/outer classifications are not invented.

Output directory independent-v12-traction-localization contains localization-receipt.json (hashes, summaries, top30cells/faces), cell-contributions.npz (all original zero-based cellIDs/centroids/three volume contributions), and interior-face-contributions.json (vertextriples, owners,centroids,jumps). The raw NPZ has no internal face numbering; a deterministic lexicographic face ordinal is explicitly named sorted_face_id and accompanied by exact sourcevertexIDs/ownercellIDs rather than misrepresented as an existing meshface index. Findings were sent to root/flow. This is functional-contribution triage only: not a norm/errorbound, automatic refinement admission, converged load or fullspeed air result. Matched refinement and unchanged rawstress/continuity/physical gates remain required.


## 37. Independent current-Jacobian diagonal-Schur review24October2026

Reviewed propulsion_pod_jacobian_schur.py SHA2568cb32b94d9af70c18ce94d85b2600f7e770d8b4b55629bde2629979d35b758d5 and final test90564e8b6133c1f7327f3c07bb84aceab10154dcb02ef8dd55aa7089920024a0. For [V,G,0;C,0,g;0,g^T,0], y=V_ILU^{-1}r_u; solve[-C*D^{-1}*G,g;g^T,0](p,lambda)=(r_p-C*y,r_g); recover u=y-V_ILU^{-1}G*p. These general C/G signs and full arbitrary gauge RHS are correct. C and G need not be transposes and neither V nor the approximate Schur is claimed SPD. The diagonal Schur differs from the ILU-based velocity correction, so this is an approximate block action; the full original matrix residual must admit the solve. A nonsingular full matrix does not guarantee the approximate Schur or ILU can be factored; failure is rejected.

The constructor snapshots the input matrix and gauge, preventing later C/G/g edits from mixing with old factors. Positive finite velocity diagonal is a necessary admitted approximation condition, not proof of invertibility. Shape/sparse-entry and combined native-factor entry budgets are checked; factor counts are post-allocation and follow section35's version-specific conservative storage semantics. They do not bound allocation peaks, so external process memory/time containment remains necessary. There is no factorization cancellation or hidden fallback. No owner implementation was edited.

Independent focused suite6tests PASS0.019s. A distinct independently selected diagonal oracle uses Vdiag[2,3,7], C[[1,-1,0],[-2,2,0]], G[[1,3],[2,6],[-1,-3]], gauge[1,2] and full RHS[2,-1,.3,4,-.7,1.2]. C/G are nonsymmetric and gauge is not the pressure null vector; preconditioner versus dense full-system inverse difference2.66454e-15 and full residual7.87006e-16. This exact diagonal case verifies algebra independently of the author's fixture; it does not show quality for nonsymmetric nonlinear operators.

Inspected retained bounded-comparison receipt: both v10 runs bind identical matrix/vector hashes, zero starts, target2.9289380026866373e-9, same initial forcing, SciPy1.17.0 and explicit2GiB/85s child containment. Baseline386iterations/9.531s solve/true residual1.44873e-9; candidate201iterations/5.563s/3.82404e-10. Setup2.141→2.359s and peak process commit843984896→876670976bytes, an increase32686080bytes. These are single retained auxiliary v10 measurements, not repeated timing statistics, current v17 performance or air-load convergence. A same-current-matrix replay with unchanged original residual/forcing and containment is still required before case integration. No heavy replay/PDE was duplicated by this reviewer. Evidence receipt: output/promo-propulsion-pod-20261023/inertial_cfd/independent-jacobian-schur-review-20261024.json. No consequential mathematical finding in this bounded review; knowledgeable human numerical release review remains required.
