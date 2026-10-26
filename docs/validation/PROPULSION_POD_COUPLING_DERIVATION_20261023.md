<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent controller–field–shaft–propeller coupling derivation — 23 October 2026

Status: **experimental synthetic reference; not release qualified**. This record independently derives the exchange and acceptance conditions for the proposed in-process `propulsion_pod.py` orchestrator and reviews its two numerical owners. It does not establish an actual VESC, three-phase BLDC, aircraft, manufactured motor, or blade-resolved CFD model. Numerical human review before release remains required under `NUMERICAL_METHOD_EVIDENCE.md`.

## Reviewed primary foundations

Reviewed on 23 October 2026; the formulas below were independently derived for SPIKE, without copying third-party implementation or example data.

| Foundation | Exact reviewed source/version and location | What it supports / boundary |
| --- | --- | --- |
| MQS energy, coenergy and reciprocity | Haus and Melcher, *Electromagnetic Fields and Energy* (1989), MIT-hosted [§11.7](https://web.mit.edu/6.013_book/www/chapter11/11.7.html), energy principle and coenergy identities (1)–(8), reciprocity discussion and the zero-current-force caveat in the coenergy integration paragraph | Terminal magnetic work, virtual work and reciprocal flux/current derivatives. It does not validate the new synthetic motor's geometry/materials. |
| Exact discrete chain rule | McLachlan and Quispel, *Discrete gradient methods have an energy conservation law*, [arXiv:1302.4513v1](https://arxiv.org/pdf/1302.4513v1), 19 February 2013 submission / PDF dated 20 February, printed pp.2–3: discrete-gradient axiom, consistency and skew-system update | Finite-step energy identity. Ordinary implicit midpoint applied to a nonlinear angle dependence is not automatically energy exact. |
| Propeller force/torque projections and disk power | MIT Unified Engineering, *Thermodynamics and Propulsion*, [§11.7.1–11.7.3, Performance of Propellers](https://web.mit.edu/16.unified/www/SPRING/propulsion/notes/node86.html), online edition reviewed 23 October 2026: elemental lift/drag projections; momentum/kinetic-power control volume; five actuator-disk assumptions | Propeller signs and steady incompressible, no-swirl actuator-disk work. The page supplies foundations, not a qualified polar or measured IRIS/drone performance. |

The author-hosted [Gonzalez bibliography](https://web.ma.utexas.edu/users/og/numerics.html) identifies *Time Integration and Discrete Hamiltonian Systems*, J. Nonlinear Science 6 (1996),449–467. That bibliographic page was reviewed for lineage only; this record's discrete-gradient equation verification uses the full primary McLachlan–Quispel paper above. It does not claim the inaccessible Gonzalez article's complete text was reviewed. No frontier method replaces the established energy/work identities here.

## 1. Units, state and field assumptions

The electrical state is a vector of two winding currents `i` [A], linked flux `lambda` [Wb-turn], and supplied ideal phase voltages `v` [V]. The shaft states are mechanical angle `theta` [rad] and angular speed `omega` [rad/s]; inertia `J` is [kg m²], bearing coefficient `b` is [N m s], and propeller resisting torque `Q>=0` is [N m] for positive rotation. Electrical resistance `R` [ohm] must be passive (nonnegative scalar/diagonal, or symmetric positive-semidefinite matrix if generalized). Force/thrust is not power; rotational power is torque times angular speed.

These are real instantaneous currents/voltages and static field amplitudes, not RMS phasors. The Joule rate is `i^T R i`; no extra harmonic factor of one half belongs in the instantaneous port ledger.

The field owner is a fixed, linear, isotropic planar P1 vector-potential benchmark, not a moving-mesh reconstruction of product CAD. Its bounded circular interfaces are polygons; the outer Dirichlet boundary truncates the exterior. The retained material domain stays fixed while a supplied uniform remanence vector rotates as `(cos(theta),sin(theta))`. The present model has one mechanical/electrical angle ratio; additional pole pairs require explicit factors in every angle derivative, not a relabelled speed.

Let depth be `d` [m], the Dirichlet-reduced P1 stiffness be symmetric positive-definite `K`, and the source matrix assembled from normalized winding densities be `C`. For each winding, the positive/negative conductor-region integrals of chi are `+N/-N`; their signed sum is zero. Excitation and flux extraction use that same chi, so a constant potential shift does not change linkage. With `a` [Wb/m], the discrete field equation is

```
K a = C i + F r(theta),       r=(cos(theta),sin(theta)).
```

`C i` and `F r` have the native 2-D weak residual unit A. Include depth exactly once:

```
L = d C^T K^-1 C                         [H]
M = d C^T K^-1 F                         [Wb-turn]
S = d F^T K^-1 F                         [J]
psi(theta) = M r(theta)
c = d integral_PM |Br|²/(2 mu) dA         [J].
```

Thus `lambda=L i+psi`. The constant `c` is the stated rigid/isotropic recoil-reference offset. `K`, chi and the physical domain are fixed for this increment. Saturation, hysteresis, eddy currents, end turns, temperature-dependent properties and rotor/material deformation are outside this derivation. Four basis solves span this particular linear FE model exactly; factor reuse is not a claim of an independently qualified motor map.

## 2. PM potential and torque: the complete energy

The field variational potential at prescribed current is

```
Pi(a;i,theta)= d(.5 a^T K a - a^T C i - a^T F r) + c.
```

At its field solution, `-Pi` is the electromechanical coenergy:

```
W'(i,theta)=.5 i^T L i + i^T M r + .5 r^T S r - c.
Cpm(theta)=.5 r^T S r-c.
```

Here `Cpm` denotes a scalar PM-source potential and is distinct from the winding source matrix `C`. The Legendre transform with respect to the electrical ports gives

```
U(lambda,theta)= i^T lambda-W'
              =.5 i^T L i-Cpm(theta).
```

Equivalently the positive recoil-reference constitutive potential is `d integral |B-Br|²/(2mu)dA`, where `Br=0` outside the PM. The existing magnetic kernel's convention `w(B=0)=0` omits the angle-independent `c`; adding it changes the reference, not force or power. Bare `d integral |B|²/(2mu)dA` is **not** this full electromechanical storage. Omitting the PM-source term from the ledger incorrectly assigns PM work to the circuit or shaft.

At fixed electrical current, virtual-work torque is

```
tau = partial_theta W' = i^T M r' + r'^T S r,
r'=(-sin(theta),cos(theta)).
```

At fixed flux, equivalently `tau=-partial_theta U`. The second term must remain unless angle independence of `Cpm` is actually established. A nearly isotropic Gram matrix or a small computed no-current torque is evidence for this benchmark, not authority to discard the term in another mesh/material model. Reciprocity is `partial_i tau = partial_theta lambda = M r'`. For the present one-pole-pair sine/cosine source,

```
partial_theta tau = -i^T M r - r^T S r + r'^T S r'.
```

The differential identity is `dU=i^T d(lambda)-tau d(theta)`. It holds with changing currents and angle; it is not only a fixed-current argument.

## 3. Continuous exchange and shaft/air work

The circuit and shaft equations are

```
v=R i+lambda_dot,
theta_dot=omega,
J omega_dot=tau-b omega-Q(omega).
```

Combining them gives

```
d/dt [U + .5 J omega²] = v^T i - i^T R i - b omega² - Q omega.
```

The controller is a sampled ideal voltage source participant, not an energy-free torque command. Its held voltages determine `v^T i`; motor torque comes from the field derivative. A bounded P controller is the smallest sufficient closed-loop reference. If PI/antiwindup is used, specify its exact sample recursion and saturation before tests. Controller/inverter firmware, PWM and semiconductor/battery losses are not inferred from the held voltage.

`Q omega` exits the shaft once. A separate propeller energy decomposition may distribute that same work into axial induced-flow kinetic power and profile aerodynamic dissipation. Do not add `Q omega`, induced power and profile power together as three independent losses in the combined ledger. Profile aerodynamic power is not automatically motor heat.

## 4. An exact finite-step exchange for fixed L

Let an accepted common window have size `h`, endpoint increment `Delta`, and arithmetic midpoint bars. Use one held voltage over this window and solve all electrical/shaft unknowns together:

```
Delta lambda = h(v_hold-R i_bar),
Delta theta  = h omega_bar,
J Delta omega= h(tau_DG-b omega_bar-Q(omega_bar)).
```

Define angular secants of the *same field owner*:

```
Dpsi = [psi(theta1)-psi(theta0)]/Delta theta,
DCpm = [Cpm(theta1)-Cpm(theta0)]/Delta theta,
tau_DG = i_bar^T Dpsi+DCpm.
```

At zero angle increment these are continuous derivatives, not a division by an arbitrary epsilon. The exact quadratic product identity and the fixed L give

```
i_bar^T Delta lambda - Delta U = tau_DG Delta theta.
```

Together with the midpoint kinetic identity this proves, up to algebraic solve/roundoff error,

```
Delta(U+.5J omega²)
 = h(v_hold^T i_bar-i_bar^T R i_bar-b omega_bar²-Q_mid omega_bar).
```

For stable evaluation at small angle increments use the analytic harmonics, with `sinc(x)=sin(x)/x`, `sinc(0)=1`:

```
Dpsi = sinc(Delta theta/2) M r'(theta_bar).
Cpm = C0 + Cc cos(2theta) + Cs sin(2theta),
C0=(S11+S22)/4-c, Cc=(S11-S22)/4, Cs=S12/2,
DCpm = sinc(Delta theta) [-2Cc sin(2theta_bar)+2Cs cos(2theta_bar)].
```

An unwrapped angle is needed for the actual increment; independently wrapping endpoints can turn a small step across2pi into a spurious large secant. Modulo reduction may be used only inside trigonometric evaluation, with a consistent continuous increment. Very large absolute angles also need a phase-accuracy bound rather than relying solely on finite-float admission.

### Nonlinear acceptance must not be a success flag

Define raw equation defects `re=Delta lambda-h(v-R i_bar)` [Wb-turn], `rq=Delta theta-h omega_bar` [rad], `rm=J Delta omega-h(tau_DG-b omega_bar-Q)` [N m s]. The energy defect is algebraically

```
eE = i_bar^T re + omega_bar rm - tau_DG rq.
```

Accept each scaled equation residual independently, plus an independently recomputed energy ledger. Checking only total energy can hide large mutually cancelling residuals. Scale flux, angle and momentum with their own physical units; a nonlinear solver's boolean success or a residual normalized only by a strong unrelated port is insufficient. Reject nonfinite/over-limit fields, negative unsupported rotor speed, failed BEM roots, stale controller/field signatures, and inconsistent accepted-state certificates. Trial failure must not publish partial coupled success or advance controller state.

Energy tolerances should include declared absolute J allowance, relative *step exchange/storage-change* scales, and an explicit floating-point baseline allowance when subtracting large PM offsets. A large absolute PM energy must not hide errors in a weak electrical/shaft exchange. Suggested development targets are scaled equation residuals of order1e-9 or tighter and ledger error of order1e-8 of meaningful exchanged energy plus a documented absolute/roundoff floor; these are proposed test targets, not universal qualification tolerances or permission to weaken established owner gates.

Controller samples and target changes must lie exactly on accepted window boundaries. Hold decisions across substeps; time-step refinement must retain the same physical sample times. Halving the controller sample interval while halving the integrator step changes the controlled system and is not a temporal-convergence experiment. A failed step rolls back both physical and controller trial state.

## 5. Independent BEM hover work derivation

For an annulus at radius `r`, width `dr`, blade count `B`, chord `c_b`, positive speed `omega`, induced hover speed `vi`, and no induced swirl,

```
Ut=omega r,  W=sqrt(Ut²+vi²), phi=atan2(vi,Ut), alpha=beta-phi,
dL=.5 rho W² B c_b Cl dr,
dD=.5 rho W² B c_b Cd dr,
dT=dL cos(phi)-dD sin(phi),
dQ=r[dL sin(phi)+dD cos(phi)].
```

The present bounded attached polar is supplied `Cl=a alpha`, constant `Cd>=0`, and `0<beta<=0.3 rad` within an explicit alpha/Reynolds envelope. These are declared illustrative inputs, not extracted or validated airfoil data.

Hover annular momentum requires `dT=4pi rho r vi² dr=2rho dA vi²`, `dA=2pi r dr`. With `x=vi/(omega r)`, density and speed cancel from the root equation:

```
.5 B c_b sqrt(1+x²)[a(beta-atan x)-Cd x] = 4pi r x².
```

There is a unique nonnegative root on `[0,tan beta]`: the left-minus-right function is positive at0 and nonpositive at the upper endpoint. Its lift derivative is proportional to `[x(beta-atan x)-1]/sqrt(1+x²)<0` since `x beta<=tan(.3)*.3<1`; drag and momentum derivatives are also nonpositive. Thus bounded bisection has a valid monotone bracket. Caching that dimensionless root for an exact unchanged geometry/polar specification is mathematically valid; actual instantaneous loads must still use the actual density/speed and enforce Reynolds/Mach bounds. This specialization yields `T,Q proportional to rho omega²` and shaft power proportional to `rho omega³`, not an arbitrary supplied torque coefficient.

The elemental force projection gives an exact work identity:

```
omega dQ-vi dT = dD W >=0.
```

Hence `Pshaft=omega Q=sum(vi dT)+sum(dD W)`. With `dm_dot=rho vi dA` and far-wake speed `2vi`, the annular axial kinetic-power increment is `.5 dm_dot (2vi)²=vi dT` to the annular momentum tolerance. The active-annulus ideal power bound follows from the weighted convexity of velocity moments:

```
Pinduced >= T^(3/2)/sqrt(2rho A_active),
A_active=pi(Rtip²-Rhub²).
```

This steady annular model has no resolved wake storage, angular wake momentum, swirl, tip/root-loss correction, interference, dynamic inflow, stall, compressibility or blade-resolved CFD. The endpoint omega=0 must return exact zero loads without divisions by omega. Negative rotation/advance flow are rejected rather than silently mirrored. Its finite-Reynolds and low-Mach gates limit numerical applicability but do not qualify the assumed polar.

## 6. Required discriminating verification

| Gate | Independent oracle or failure control |
| --- | --- |
| Electrical constitutive terms | Re-solve the full P1 kernel at fresh current/angle pairs and quadrature linkage; compare with basis reconstruction. Test signed turns/gauge invariance, symmetric positive L, flux-current derivative and torque-flux reciprocity. |
| Complete PM energy and torque | Direct constitutive energy including recoil offset; angle finite-difference virtual work. Exercise a nonconstant PM Gram potential so a mistakenly dropped Cpm derivative cannot pass only through geometric symmetry. |
| Exact finite-step port work | Arbitrary endpoint currents/angles, including near-zero angular increments, a2pi crossing and current reversal; check the derived discrete chain identity without integrating the orchestrator. |
| Closed-cycle work | At fixed current a complete angle revolution returns psi/Cpm/U; integrated torque work is zero. Powered commutated currents are a separate case with electrical work and must not be asserted zero-work. |
| Decoupled continuous references | No-PM RL voltage response against the matrix exponential; no-PM positive-speed shaft with `Q=k omega²` from this unchanged hover specialization against the analytic quadratic-drag decay (plus optional linear bearing drag). Isolated no-load conservative electromechanics may use an explicit zero-load test fixture; do not relabel that fixture as actual propeller physics. |
| Same-state coupling | Recompute accepted field state/torque/flux and BEM loads at recorded states; detect stale field/basis/controller hashes and one-step-lag torque. A forged result digest is not an authenticated CAD/measurement identity. |
| Root and rollback failure | Force too few nonlinear/BEM iterations, bad scales, NaN/overflow and unsupported speed/current/geometry/polar. Confirm failure returns no completed time history and no advanced controller state. |
| Temporal refinement | h,h/2,h/4 on identical field/BEM mesh, fixed controller schedule/sample times and final time. Expect second-order endpoint behavior for smooth held-source windows; report observed slopes and scale-aware errors, including event boundaries. Exact ledger closure alone is not state accuracy. |
| Spatial and radial refinement | Independently refine P1 geometry/field mesh and BEM annuli; report L, PM linkage, torque and thrust/torque changes with source hashes. Independent direct FE re-solve checks an algebraic reduction, not continuum convergence or measured motor accuracy. |
| Propeller mathematical reference | Manufactured uniform vi; exact annular mass/momentum/far-wake energy, positive profile power, ideal-disk bound, geometry/speed/density scaling and radial midpoint-quadrature convergence. |

## 7. Completed independent code review and execution

Reviewed on 23 October 2026 against the source snapshot below. The review covered field energy/reciprocity, harmonic discrete gradients, explicit end-turn storage, current-reference phase signs, scalar implicit coupling, accepted-step residual gates, controller timing, endpoint output, public admission and failure semantics. No consequential remaining equation or API defect was found in this snapshot within this synthetic benchmark's stated scope.

The implementation eliminates the two linear electrical equations exactly at each candidate midpoint speed and solves the remaining shaft residual by bounded Brent root finding. The exact harmonic divided differences retain both winding/PM linkage and the PM Gram potential. The ledger includes the explicit end-turn inductance in stored magnetic energy. BEM torque uses the same midpoint speed as mechanical work. Individual circuit and shaft residual gates supplement the energy gate.

Two independent public-API checks initially exposed missing field validation in the validate endpoint and mutable global defaults returned by capabilities. The implementation owner fixed both: public validation now calls the shared pure field validator, including mesh budget, and capabilities returns a deep copy. The service also converts an unavailable runtime/compiler OSError into a failed response. The independent checks passed after those fixes. These were admission/ownership fixes, with no solver mathematics changed.

The controller is a bounded PI current-request generator with conditional integral update, followed by a voltage-limited two-phase current/EMF law. Its phase direction follows the flux-angle derivative and gives positive requested torque. `current_limit_a` limits the request; it is neither a hard actual-current clamp nor a protection qualification. Conditional integration addresses request saturation, not every voltage-saturation case. A controller event occurs only at an aligned sample time before its held-voltage interval. Nonlinear root trials do not advance controller state. The final endpoint is emitted without an extra sample. A failed physical step aborts and closes the whole run; no completed partial result is returned. There is no resumable step-retry contract. A future retry implementation would need a checkpoint before the controller sample as well as physical state rollback.

Independent final-snapshot test command:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_review tests.python.test_propulsion_pod_field tests.python.test_propulsion_pod_propeller -v
```

All 22 tests passed: four independently authored review tests, eleven field tests and seven propeller tests. The review tests exercise malformed field admission, default-object ownership, no-PM RL response against an independently evaluated matrix exponential with second-order refinement, and same-step PM/BEM work across an unwrapped full-revolution angle boundary. The verification criteria in section 6 are a broader research/release checklist; they are not all claimed executed by these 22 tests.

| Final reviewed source | SHA-256 |
| --- | --- |
| `python/spike_core/propulsion_pod.py` | `6f9cadfcd996f886c947f388c0165ebae581b766cf82a1542f10d4345ec323b2` |
| `python/spike_core/propulsion_pod_controller.py` | `18d59126f6e0795b1fc565be9b68ac0a587b01d80249d3190fbf51109c7f42f6` |
| `python/spike_core/service_propulsion_pod.py` | `2d91befc43dfcb4216652c5e752ab2e59813b38bee04976abf0cc14704a57740` |
| `python/spike_core/propulsion_pod_field.py` | `10ee7ec5979ed5f225a4fe27b7d7f8c42a183d2fa96e3be127b7e383829e3afe` |
| `python/spike_core/propulsion_pod_propeller.py` | `6184c0e9199c6c257cec3c30a8537d36ea7beb1af1d78be7e2ca6c9850eb83c3` |
| `tests/python/test_propulsion_pod_review.py` | `820d85657d7107f65b9831b63ea7c6767e3fff3fadfc51b4942409835bfc0287` |

An independent final-snapshot full default run called `run_propulsion_pod(copy.deepcopy(DEFAULT_REQUEST))` using the repository virtual environment, with Python `tempfile.tempdir` and TEMP/TMP pointed at `output/promo-propulsion-pod-20261023/.tmp`. The actual persistent compiled C controller executed, with source SHA-256 `8ac8c42b31bee6d865664bb99491ccb26d592c87036e7c57efb565020636ca26` and executable SHA-256 `c137fa53707b08669df067fa7c6b712af29a4c9d63c27b846b6d1c45b028d61d`. The run used four field basis solves, 705 nodes and 1344 triangles; field specification hash `f5fb805f828c757126eb1731670ed9546ae1955e3654e9998e6afdb19532a6b8`.

| Independent default-run observation | Value |
| --- | --- |
| Duration / accepted steps / controller ticks / frames | 0.25 s / 2500 / 500 / 26 |
| Final speed / thrust / propeller shaft power | 106.5848129761 rad/s / 0.09218654196 N / 0.10067921375 W |
| Maximum absolute phase current | 4.01741475891 A; exceeds the 4 A request cap, consistently with the stated semantics |
| Source work | 0.670439125560070 J |
| Copper / bearing heat | 0.624400752524889 J / 0.00192809365767039 J |
| Propeller shaft work | 0.0156664358698927 J |
| Magnetic / kinetic storage change | 0.0000430376147501964 J / 0.0284008058928614 J |
| Summed energy defect / maximum step defect | 4.18036589146e-15 J / 2.58444998800e-16 J |
| Maximum circuit / shaft equation residual | 2.22044604925e-15 V / 1.12926217382e-13 N m |

These observations establish this executed numerical path, not real motor accuracy, controller tuning quality or a hard current limit. The target was 100 rad/s; the observed final overshoot is reported without a stability/performance qualification. Exact discrete energy closure cannot establish temporal/spatial accuracy. The wall-time limit is a soft check between loop iterations and cannot preempt a compiler/FEM preparation call. Numerical source-runtime operation is demonstrated; frozen-release packaging, actual VESC three-phase firmware/machine, measured polar/propeller validation and resolved CFD remain outside the claim. Knowledgeable human numerical review remains required before release. Any edits to the hashed files require appropriately scoped revalidation.
