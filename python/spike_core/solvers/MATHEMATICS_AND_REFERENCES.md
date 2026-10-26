<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver mathematics, methods and research reference compendium

**Working-tree snapshot: 26 October 2026.** This is the entry point inside the
solver folder for the mathematics, implementation owners, research lineage and
verification records of SPIKE's public solver families. It includes numerical
references, geometry preparation, adapters and supporting algorithms; these are
not all independent physics solvers. The source inventory below is exhaustive for
the stated roots/extensions at this snapshot. Mathematical coverage is organized
by family, with detailed derivations linked to their maintained authorities.
It is not a claim that every device stamp or empirical coefficient has a complete
primary-source derivation, nor that every listed module is qualified.

The compilation uses existing repository derivations/reference ledgers and direct
inspection of representative numerical owners. It introduces no new numerical
method and does not claim a fresh full-text review of the cited literature or a
new execution of historical numerical tests. Existing evidence retains its exact
date, source identity, runtime, tolerances and limitations.

## How to find the full mathematical record

| Record | What it supplies |
| --- | --- |
| [Detailed governing mathematics](../../../docs/SOLVER_MATHEMATICS.md) | Equations, units, signs, discrete operators, boundary conditions and method-specific code/test links |
| [Research and standards ledger](../../../docs/SOLVER_REFERENCES.md) | Recorded authors, titles, DOI/official URLs, exact reviewed portions where available, and provenance gaps |
| [Recorded reference inventory](../../../docs/generated/solver-reference-inventory.json) | Existing URL/DOI occurrences with file/line evidence; includes non-paper links and is not an endorsed bibliography |
| [Numerical method evidence](../../../docs/NUMERICAL_METHOD_EVIDENCE.md) | Independent derivations and dated additions, primary-source review scope and acceptance evidence |
| [Solver status](../../../docs/SOLVER_STATUS.md) | Current recorded execution, convergence, measured-validation and release limitations |
| [Completion inventory](../../../docs/solvers/completion.md) | All catalog capabilities and their bounded implementation/integration state |
| [Domain guides](../../../docs/solvers/README.md) | Setup routes, source owners, supporting subgroups and exclusions |
| [Source-layout manifest](../../../docs/solvers/source-layout.json) | Former-to-current module paths; historical source receipts do not acquire new hashes after a move |
| [Handbook](../../../docs/SOLVER_HANDBOOK.md) | Study interpretation, model selection and verification practice |

Read an equation together with its model assumptions and evidence. A small
linear/nonlinear residual verifies the discrete solve; mesh/time/domain/bandwidth
refinement addresses discretization; independent measurements address different
model errors. Source availability, worker/UI integration, external installation,
reference verification, physical validation and release approval are separate.

## Symbols, units and conventions

Unless a method says otherwise, geometry is SI: m, m², m³; time s; voltage V;
current A; resistance Ω; inductance H; capacitance F; temperature K; power W;
energy J; force N; stress/pressure Pa; angular speed rad/s. PCB mm convert by
`1e-3` for length, `1e-6` for area and `1e-9` for volume. Conductivity is S/m,
permittivity F/m, permeability H/m, thermal conductivity W/(m K), volumetric
heat capacity J/(m³ K), and volumetric heating W/m³. Frequency `f` is Hz and
`ω=2πf` is rad/s. Radiation requires absolute Kelvin temperatures.

`T` on a matrix denotes transpose and `H` conjugate transpose. Symbols such as
`B`, `C`, `G` and `A` are local to each formulation. Electrical phasors below use
`exp(+jωt)`; line/network and dielectric-power formulas use RMS phasors, while
the Huygens reference explicitly uses peak phasors. Do not transfer a factor of
one half between conventions. Port ordering, reference planes, inward-current
signs and real positive reference impedances are explicit model inputs.

## 1. Geometry and discrete spaces

Signed polygon area is `½ Σ(x_i y_(i+1)-y_i x_(i+1))`; orientation and exact-grid
intersection predicates establish topology, not tolerance-based clearances.
Constrained triangles preserve boundaries. Tetrahedron orientation/volume,
intersection and hanging-node audits protect conforming volume ownership.
Material thickness, holes, terminal areas, barrel versus land and component/net
identity must survive meshing. A shared name or nearby coordinate is not a bond.

P1 tetrahedra have affine shape functions and constant gradients. RT0 bases have
single-valued normal face flux and cellwise constant divergence. RWG surface
bases have piecewise-linear tangential currents and interior-edge continuity.
These are distinct approximation spaces; transferring a coefficient does not
transfer physical accuracy. Polygon-prism/four-hex subdivision and declared
cuboids are explicit proxies, not exact retained STEP flow geometry.

Authorities: [geometry guide](../../../docs/solvers/geometry-meshing/README.md),
[native geometry](../../../docs/CAD_NEUTRAL_NATIVE_MULTIPHYSICS_FOUNDATION.md),
[mesh admission](../../../docs/MESHING_ENGINE.md),
[four-hex derivation](../../../docs/validation/ASSEMBLY_AIRFLOW_SUBDIVISION_DERIVATION_20261026.md),
[cuboid CHT review](../../../docs/validation/RECTILINEAR_CHT_GEOMETRY_20261026.md).
Research: Shewchuk predicate/CDT papers, Gmsh and surface-space documentation
are classified in [R13–R15](../../../docs/SOLVER_REFERENCES.md#r13---robust-predicates).
SPIKE's exact-grid predicates do not imply use of Shewchuk's implementation.

## 2. DC, PEEC, capacitance and power integrity

| Method | Governing/discrete mathematics | Assumptions and detailed authority |
| --- | --- | --- |
| Routed/harness DC and zone spreading | `R=l/(σS)`, `I=ΔV/R`, `J=I/S`; incidence `B` gives `B diag(1/R) Bᵀ v=j`. Conservative zone faces approximate `∇·(σ∇V)=0`. | Explicit contacts, sources, returns and conducting cross-sections; geometry/contact discretization affects spreading. [DC](../../../docs/DC_SOLVER.md), [harness](../../../docs/HARNESS_PI.md) |
| Retained tetrahedral potential | `K_e=V_e grad(N) σ grad(N)ᵀ`, `J=-σ∇V`, bulk `q=J·E`. | Finite admitted mesh and explicit contacts/Dirichlet data. [Electrothermal derivation](../../../docs/ASSEMBLY_ELECTROTHERMAL.md) |
| Mixed sheet and volume RT0 | Triangle `w_i=(x-v_i)/(2A)`; tetrahedron `w_i=(x-v_i)/(3V)` has unit integrated outward flux. `M_ij=∫w_i·w_j/σ dV`, with thickness in the sheet law; signed flux/potential saddle equations enforce cell conservation. | Oriented face-current DOFs, gauge/conditioning and volume-weighted density ranks; experimental. [Tetra RT0](../../../docs/DC_TETRA_RT0.md), [independent oracles](../../../docs/DC_TETRA_RT0_ORACLES.md), [sheet density](../../../docs/DC_RT0_DENSITY.md) |
| PEEC current bases | `R_ij=∫f_i·f_j/σ dV`; `L_ij=μ/(4π)∫∫f_i(r)·f_j(r′)/|r-r′| dV dV′`; `W_m=½iᵀLi`. Frequency blocks use `Z=R+jωL`, `Zi-Aᵀv=0`, `Ai+Yv=j_s`. | Quasistatic finite bases; self/mutual terms share a basis. PSD/energy rejection cannot be repaired by invented floors. [Full formulation](../../../docs/SOLVER_MATHEMATICS.md#peec-partial-elements-and-transient-pi), [safety policy](../../../docs/PEEC_SAFETY_POLICY.md) |
| PEEC transient | `Ri+L di/dt-Aᵀv=0`, `Ai+C dv/dt=j(t)`; backward Euler replaces derivatives by accepted-state differences. | Optional stackup shunts are not arbitrary field-extracted C. BE damping is not heat. [Transient PI](../../../docs/TRANSIENT_PI.md) |
| Electrostatics | `-∇·(ε∇φ)=0`; `K_e=V_e grad(N) ε grad(N)ᵀ` in F; unit-electrode fields `P` give `C=PᵀKP`, `U=½vᵀCv`. | Natural exterior means zero normal displacement, not an infinite open boundary. [Owner/derivation](power_integrity/pdn/pdn_electrostatic.py) |
| Lossy dielectric AC | `γ=σI+ω tanδ ε+jωε`; solve `∇·(γ∇φ)=0`; `Y=PᴴKP`; dissipative density `q=Re(EᴴγE)`. | Supplied per-frequency materials, RMS convention, finite domain and field re-solve. [Owner](power_integrity/pdn/pdn_dielectric_ac.py), [heat transfer](../../../docs/PDN_DIELECTRIC_THERMAL.md) |
| Reduction and decoupling | `Y_red=Y_ee-Y_ei solve(Y_ii+Y_load,Y_ie)`; capacitor `Z=ESR+jωESL+1/(jωC)` away from DC; target impedance may be `ΔV_allowed/ΔI`. | Explicit termination, conditioning, finite candidate/frequency/corner inputs; no automatic placement-field or part qualification. [PDN guide](../../../docs/solvers/power-integrity/README.md) |

References: Ruehli 1974 PEEC, Rosa/Grover 1912 inductance, Haus/Melcher steady
conduction and Vohralík mixed-method foundations have recorded scopes in the
[reference ledger](../../../docs/SOLVER_REFERENCES.md) and linked RT0 methods.
The [same-slab singular-kernel record](../../../docs/validation/PEEC_AFFINE_SLAB_KERNEL_20261019.md)
records Reid's reviewed sections and distinguishes an error estimate from a
certified bound. [PI01-S02 evidence](../../../docs/validation/PI01_SCALABLE_20261024.md)
retains real-board refinement failure/resource rejection; a solved matrix does
not close board qualification.

## 3. Transmission lines, sampled networks and measurement mathematics

Scalar telegrapher equations are `dV/dz=-(R+jωL)I`,
`dI/dz=-(G+jωC)V`, with per-length R [Ω/m], L [H/m], G [S/m], C [F/m].
`γ=sqrt(ZY)`, `Z_c=sqrt(Z/Y)` and a spatial matrix exponential propagate fields.
The supplied uniform implementation scales growing hyperbolic terms into
decaying exponentials and admits analytic DC series/shunt/thru limits.

| Subfamily | Mathematical contract | Detailed reference |
| --- | --- | --- |
| Geometry-derived quasi-TEM channels | Scalar planar approximation; homogeneous pair uses electrostatic vacuum `C0`, `C=ε_r C0`, `L=C0⁻¹/c0²`. | [Geometry-derived SI](../../../docs/GEOMETRY_DERIVED_SI_CHANNEL.md); bounded cross-section/outer-boundary assumptions |
| Skin and roughness | `δ=sqrt(2/(ωμσ))`; slab `Z_int=k coth(kt/2)/(2σw)`, `k²=jωμσ`; empirical real-R multiplier `1+(2/π)atan(1.4(RMS/δ)²)`. | [High-frequency losses](../../../docs/HIGH_FREQUENCY_LOSSES.md); no general proximity or causal broadband material law |
| Uniform sampled RLGC | Scaled analytic two-port, positive real references, supplied nonnegative losses. | [Network](../../../docs/RLGC_LINE_NETWORK.md), [field/loss integrals](../../../docs/RLGC_LINE_FIELDS.md) |
| Physical fields and losses | `d Re(V I*)/dz=-(R|I|²+G|V|²)`; analytic coherent spatial integrals give W, nominal stored density `½(C|V|²+L|I|²)` gives J/m. | Coherent drives combine before quadratic loss; probe density does not set integrated-loss accuracy. Same field/loss reference above |
| Pair, cascade, junction, star | Symmetric pair `Q=1/√2 [[1,1],[1,-1]]` preserves power/storage; equal-reference ideal star `a=(2/m 11ᵀ-I)b`. | [Pair](../../../docs/RLGC_COUPLED_PAIR.md), [cascade](../../../docs/RLGC_LINE_CASCADE.md), [junction](../../../docs/RLGC_LINE_JUNCTION.md), [coupled star](../../../docs/RLGC_COUPLED_STAR.md) |
| Resistive/reactive physical endpoints | `V+R_t I_into=V_s` gives `(I-diag(Γ)S)a=d`; R/L/C boundary state closure retains signed source work and separate resistor/line heat. | [Terminated pair](../../../docs/RLGC_TERMINATED_PAIR.md), [reactive pair](../../../docs/RLGC_REACTIVE_PAIR.md), [loaded cascade](../../../docs/RLGC_LOADED_CASCADE.md), [loaded star](../../../docs/RLGC_LOADED_STAR.md) |
| General wave connections | `S_eff=S_ee+S_ei solve(I-C_w S_ii,C_w S_ie)`; simultaneous feedback includes repeated reflections. | [Network mathematics](../../../docs/SOLVER_MATHEMATICS.md#transmission-lines-and-network-composition), [network owner](signal_integrity/networks/si_network_graph.py) |
| Sampled fitting and transient response | Bounded rational state model, mixed boundary closure, exact-in-model linear/PWL propagation via matrix exponentials; sampled fitting and stability do not certify unknown-source causality. | [SI guide](../../../docs/solvers/signal-integrity/README.md), [RLC transient](../../../docs/RLC_NETWORK_TRANSIENT.md), [initial states](../../../docs/RLC_INITIAL_STATES.md), [energy ledger](../../../docs/RLC_ENERGY_LEDGER.md) |
| Lossless/distortionless delay lines | Traveling waves with flight time; distortionless `R=κL`, `G=κC` weights delayed waves by `exp(-κτ)`; `∂u/∂t+∂p/∂z=-loss`, `loss=2κu`. | [Lossless line](../../../docs/LOSSLESS_LINE_TRANSIENT.md), [distortionless line](../../../docs/DISTORTIONLESS_LINE_TRANSIENT.md) |
| Crosstalk/candidate corners | Linear signed-family sampled envelope `v_base±Σ|v_j|`; finite timing/candidate unions retain attaining witnesses. | [Multi-aggressor](../../../docs/MULTI_AGGRESSOR_CROSSTALK.md), [timing](../../../docs/CROSSTALK_TIMING_CORNERS.md), [candidate studies](../../../docs/SI_CANDIDATE_STUDY.md); no continuous-skew or intersample-extrema claim |
| Reflectometry | `V±=sqrt(Z0){a,b}`, `V=V++V-`, `I=(V+-V-)/Z0`; unresolved ratios remain unresolved. | [Reflectometry](../../../docs/NETWORK_REFLECTOMETRY.md); instantaneous loaded ratios are not isolated frequency-domain S11 |
| Fixture removal | Block simultaneous-wave elimination with named DUT/fixture interfaces; separate transmission/recovery/feedback conditioning and backward errors. | [Multiport de-embedding](../../../docs/MULTIPORT_DEEMBEDDING.md), [independent oracle](../../../docs/validation/MULTIPORT_DEEMBEDDING_ORACLES_20261024.md) |
| One-port calibration | Three known standards determine the three-term complex reflection map; implicit derivatives propagate supplied correlated inputs. | [One-port](../../../docs/ONE_PORT_CALIBRATION.md), [independent derivation](../../../docs/validation/ONE_PORT_CALIBRATION_DERIVATION_20261024.md) |
| Multiport calibration | Diagonal error boxes obey `M=D+U S(I-VS)⁻¹W`; a named gain-reference port fixes the common complex gauge; solve `(I+XV)S=X` after diagonal scaling. | [Multiport](../../../docs/MULTIPORT_CALIBRATION.md); 2–4 ports, port-separable errors, coherent wave matrices, no arbitrary crosstalk/switch-acquisition model |
| Joint uncertainty | Real/imaginary Jacobian `J` gives `C_out=J C_in Jᵀ`; implicit differentiation retains calibration/fixture cross-covariance. | [Joint fixture UQ](../../../docs/CALIBRATED_FIXTURE_UQ.md); local first-order propagation, no automatically qualified distribution/coverage probability |

Foundations are Staelin's MIT *Electromagnetics and Applications* (2011), the
reviewed Steer even/odd-mode sections, Kurokawa wave conventions, Marks/Williams
(1992), NIST TN2079, Jargon/Williams/Sanders (2019), JCGM 102:2011, and Van Loan
(1978) block-exponential integral identities. Exact reviewed sections, access
limits and independent derivations reside in each linked method and the
[research ledger](../../../docs/SOLVER_REFERENCES.md); this compendium does not
retroactively expand those reviews. Touchstone and IBIS are format/model
standards, not evidence of extraction accuracy. IEEE 370 is recorded measurement
guidance, not a claim of compliance. [SI08 closure](../../../docs/SI08_FAMILY_CLOSURE.md)
keeps physical measurement and human release gates separate.

## 4. Waveform, receiver and device postprocessing

Convolution/FFT reconstructions depend on finite bandwidth, sample grid, DC
policy, interpolation and windowing. Eyes fold samples by unit interval/phase;
clock recovery, PAM3/PAM4 decisions, DFE training, mask segment-crossing tests
and Gaussian BER proxies operate within their declared finite-record contracts.
They are not a measured BER or automatic USB/Ethernet compliance result.
An isolated ringdown `exp(-αt)cos(2πft+φ)` has `Q=πf/α`; AR(2) roots estimate
decay/frequency subject to aliasing, residual and single-mode checks.

Authorities: [SI workflow](../../../docs/SI_WORKFLOW.md),
[clock recovery](../../../docs/SI_CLOCK_RECOVERY.md),
[eye masks](../../../docs/SI_EYE_MASK_TESTING.md),
[ringdown owner](signal_integrity/receivers/si_ringdown.py),
[IBIS derivation](../../../docs/validation/IBIS_DRIVER_RECEIVER_DERIVATION_20261025.md).
Classic IBIS signed I/V and two-fixture switching-weight recovery are distinct
from earlier slope/ramp reductions and external AMI execution. The
[executed IBIS record](../../../docs/validation/IBIS_SPATIAL_IMPLEMENTATION_20261025.md)
retains an unmet strict waveform-refinement gate. MIT resonance/Harminv links
in [R9](../../../docs/SOLVER_REFERENCES.md#r9---resonance-terminology-and-independent-ringdown-derivation)
are convention references, not claims to implement Harminv.

## 5. Circuits, switching, reduced parts and equilibrium semiconductor fields

MNA solves `F(x,t)+dQ(x,t)/dt=0` with node voltages and constraint currents.
Newton updates solve `J Δx=-F`; AC linearizes conductance/charge at the admitted
operating point. BE capacitor history is `C(v-v_n)/h`; trapezoidal history is
`2C(v-v_n)/h-i_n`; variable-step BDF2 uses its actual history coefficients.
Adaptive order-two versus BE defect control restores rejected state and restarts
at source corners; this defect is not a universal rigorous local-error bound.

| Scope | Mathematics and evidence owner | Limit |
| --- | --- | --- |
| Native DC/AC/transient and equation devices | [Circuit guide](../../../docs/solvers/circuits/README.md), [adaptive switching](../../../docs/SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md), [controls](../../../docs/INTERNAL_SPICE_TRANSIENT_CONTROLS.md), [I/Q devices](../../../docs/SPIKES_EQUATION_DEVICES.md) | Admitted syntax/stamps and convergence; not arbitrary SPICE/device qualification |
| Passive, active and digital parts | [Passive equations](../../../docs/SPIKES_PASSIVE_MODEL_EQUATIONS.md), [active coverage](../../../docs/SPIKES_ACTIVE_LIBRARY_COVERAGE.md), [lumped physical parts](../../../docs/SPIKES_LUMPED_PHYSICS_PARTS.md) | Constitutive laws, limiting/event policies and charge histories are distributed across these documents and native stamps |
| Battery and fitted device models | [Battery](../../../docs/SPIKES_BATTERY_MODEL.md), [sourced-parts workbench](../../../docs/SPIKES_SOURCED_PARTS_WORKBENCH.md) | Supplied one-RC/equivalent-circuit and curve-fit scope, not electrochemistry or manufacturer qualification |
| Averaged ideal CCM SMPS | `A=[[0,-k/L],[k/C,-1/(RC)]]`; `Gvd=(B_v s+k B_i/C)/(s²+s/(RC)+k²/(LC))`. Compensation zeros/poles and uncancelled closed-loop polynomial determine resolved crossings/poles. [Full derivation](../../../docs/SPIKES_SMPS_STABILITY.md) | Topology-specific duty column and CCM/ripple assumptions; one phase margin does not certify stability |
| Equilibrium 1D TCAD | `V_T=k_B T/q`, `n=n_i exp(φ/V_T)`, `p=n_i exp(-φ/V_T)`, `-∂x(ε∂xφ)=q(p-n+N_D-N_A)`; scaled FV tridiagonal Newton with residual backtracking and Gauss-law checks. [Method](../../../docs/SPIKES_TCAD_EQUILIBRIUM.md) | Homogeneous material, full ionization, Boltzmann carriers, equilibrium; no biased transport/process simulation |
| Controllers and firmware | Explicit sampled callbacks, event ordering and separately admitted native peripherals/pads; [architecture](../../../ARCHITECTURE.md) and [native timing evidence](../../../docs/validation/NATIVE_PERIPHERAL_TIMING_20261020.md) | Timing/state coupling is not a new field solver or automatic hardware fidelity |

The historical MNA and per-device primary-reference gaps remain open where
the linked owners do not record them. A generic textbook must not be assigned
as invented implementation lineage.

## 6. Heat conduction, radiation and electrothermal composition

The governing equation is `ρc_p ∂T/∂t=∇·(k∇T)+q`, with Fourier flux `-k∇T`.
Convection outward is `h(T-T_ambient)`; ambient radiation outward is
`ε_surface σ_SB(T⁴-T_ambient⁴)`. Matched contact exchanges are equal/opposite.
For two FV half-cells, `G_face=A/(d1/k1+d2/k2)` in W/K. BE storage adds
`ρc_p V/Δt` to the diagonal. P1 tetrahedra use `K_e=V grad(N)k grad(N)ᵀ`,
uniform source `Vq/4` and face mass `A(I+11ᵀ)/12`; convection/contact use that
face integral. Anchoring, conductivity positivity, residuals and conditioning
are separate admission gates.

Reduced component/package networks, layered board volumes, structured solids,
retained tetrahedral steady/transient fields, nonlinear radiation and external
CalculiX thermal are separate routes. Temperature feedback may use
`σ(T)=σ_ref/[1+α(T-T_ref)]` only within its declared range. Unrelaxed thermal
defect and power change govern fixed-point convergence. `I_rms²R`, supplied
switching-energy tables and integrated terminal work minus storage are distinct
heat sources; electrical storage and numerical damping must not be deposited
as heat. Each source/contact loss is assigned exactly once.

Authorities: [thermal/fluid guide](../../../docs/solvers/thermal-fluid/README.md),
[thermal accuracy](../../../docs/THERMAL_ACCURACY_CHECKS.md),
[component network](../../../docs/COMPONENT_THERMAL.md),
[assembly electrothermal](../../../docs/ASSEMBLY_ELECTROTHERMAL.md),
[transient](../../../docs/ASSEMBLY_THERMAL_TRANSIENT.md),
[PWM composition](../../../docs/PWM_VOLUME_ELECTROTHERMAL.md),
[bounded radiation](../../../docs/BOUNDED_CHT_AND_RADIATION.md).
DOE thermal/Fourier, NIST FiPy FV/upwind and NASA convergence sources have exact
review scopes in [native CHT](../../../docs/validation/NATIVE_CHT_METHOD_20261020.md)
and [enclosure energy](../../../docs/validation/ENCLOSURE_CHT_METHOD_20261020.md).
Those newer reviews do not fill every earlier thermal module's provenance gap.

## 7. Fluid momentum and conjugate heat transfer

### COMSOL inspiration and the complete CHT target

COMSOL is the owner's primary capability inspiration. Nicolas Huc's
[Conjugate Heat Transfer](https://www.comsol.com/blogs/conjugate-heat-transfer)
(6 January 2014; equation/interface sections reviewed 26 October 2026) is a
published explanation and comparison reference, **not an independent SPIKE
validation oracle or a claim of product parity**. Its fluid temperature equation is

```text
ρ cp (∂T/∂t + u·∇T) = ∇·(k∇T) + Q + αp T Dp_absolute/Dt + τ:S
```

Here `αp` is thermal expansion [1/K], `τ` viscous stress [Pa], and `S` strain
rate [1/s]. Pressure work and viscous heating have units W/m³. The immobile
solid equation omits advection and fluid terms. For an ideal stationary
impermeable interface without contact resistance, `T_s=T_f` and
`n_s·(-k_s∇T_s)+n_f·(-k_f∇T_f)=0`. Momentum and thermal boundary layers must
both be resolved. These equations explain the requested combined geometry,
velocity and solid/fluid temperature visualization, including transient fields.

SPIKE's implementation boundaries, from the repository authorities above/below:

| Target term or capability | Present boundary and omission flag |
| --- | --- |
| Solid storage/conduction | Implemented in bounded transient thermal routes; not every CHT runner supports a transient field history |
| Fluid advection and interface exchange | Implemented in admitted channel/native/rectilinear routes; geometry admission and field refinement remain route-specific |
| Viscous heat `τ:S` | Explicit in the developed-channel model; do not infer it in every flow/CHT adapter from the word CHT |
| Pressure work `αp T Dp/Dt` | Not established by the bounded incompressible native routes documented here; a generic compressible temperature/energy solver is not claimed |
| Solved buoyancy/turbulence/rotation | Distinct model and convergence gates; isolated SA/rotation operators do not establish joint turbulent natural-convection capability |
| Arbitrary retained assembly surfaces and transient air/solid fields | Proxy geometry, strict mesh rejection and incomplete convergence remain visible; exact-STEP general CHT closure is not established |
| Radiation | Ambient surface exchange is separate from arbitrary view-factor exchange or participating-media transport; these broader features are not implied |

For a future increment, declare retained terms and regime, derive independent
discrete conservation and analytic/manufactured oracles, then execute spatial
and temporal refinement plus relevant measured/reference comparison. A visual
resemblance to a published COMSOL figure is not acceptance evidence.

| Route | Equations/method | Boundary and evidence |
| --- | --- | --- |
| Native square cavity | Nondimensional `∇·u=0`, `∂u/∂t=-∇·(u⊗u)-∇p+∇²u/Re`; staggered MAC centered flux/diffusion and incremental pressure projection with zero-mean gauge. | No-slip walls/moving lid, explicit advective/diffusive timestep bounds. [Native CFD](../../../docs/NATIVE_CFD.md), [independent returned-field momentum check](../../../docs/validation/NATIVE_CAVITY_MOMENTUM_20261025.md) |
| Developed channel | Constant-pressure-gradient no-slip momentum, parabolic velocity oracle; `ρc_p u ∂T/∂x=∇·(k∇T)+q_viscous`, conservative Fourier/upwind CHT. | Developed extruded model, no entrance momentum/sidewall/turbulence. [Bounded channel](../../../docs/BOUNDED_CHT_AND_RADIATION.md) |
| Native/rectilinear CHT | Shared Fourier half-resistances and equal/opposite upwind enthalpy; BE sensible storage. Integrated momentum `Bu=0`, `(K+C(u))u-Bᵀp=F`. | Actual nonuniform face areas/dual volumes and checked mass/energy/momentum. [Rectilinear derivation](../../../docs/validation/ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md), [CHT evidence](../../../docs/validation/ENCLOSURE_CHT_V2_VALIDATION_20261020.md) |
| Symmetric stress | `K=EᵀWE` retains shear cross-components and positive strain energy. | [Isolated operator evidence](../../../docs/validation/ENCLOSURE_SYMMETRIC_STRESS_20261020.md) |
| SA-noft2 transport | Fixed-velocity nonlinear positive-branch scalar closure, diffusion variable `H(q)=νq+q²/2`, positivity-preserving Newton line search. | [Exact variant/source ledger](../../../docs/validation/ENCLOSURE_SA_TRANSPORT_20261020.md); isolated closure is not qualified coupled RANS |
| Rotating frame | Weighted skew Coriolis block and physical-pressure reconstruction from centrifugal-potential differences. | [Rotation record](../../../docs/validation/ENCLOSURE_ROTATING_FRAME_20261020.md); no general moving-mesh/GCL or blade validation |
| Retained tetrahedral creeping flow/heat | Bounded supplied geometry/material/boundary solve with conservative thermal transfer. | [AC/CHT composition](../../../docs/validation/AC_NETWORK_CHT_20261023.md), [admission hardening](../../../docs/validation/NATIVE_CHT_ADMISSION_20261024.md); preserve source-specific limits |

Veldman's reviewed CFD sections, NIST FV/upwind, NASA/TMBWG exact SA variants
and NASA refinement guidance are recorded in the linked ledgers. The
[CFD research review](../../../docs/validation/CFD_CHT_RESEARCH_REVIEW_20261021.md)
separates sharp-immersed/high-order/ALE/preprint candidates from executed methods.
External OpenFOAM and SU2 own their native kernels; their versioned setup,
result import and acceptance are in the external-engine guide below.

## 8. Mechanics, magnetic machines and propulsion

Small-strain isotropic elasticity uses engineering strain order
`[xx,yy,zz,xy,yz,xz]`, Lamé constants `μ=E/[2(1+ν)]`,
`λ=Eν/[(1+ν)(1-2ν)]`, and `K_e=V Bᵀ C B`. Thermal eigenstrain is
`α(mean_cell(T)-T_ref)[1,1,1,0,0,0]`; equivalent load is `V BᵀC ε_th`.
Stress is `C(Bu-ε_th)` and stored energy is `½V(Bu-ε_th)ᵀC(Bu-ε_th)`.
Explicit displacement constraints remove rigid modes. The bounded implementation
rejects near-incompressibility beyond its admitted Poisson range; it provides no
plasticity, contact/welding, fracture, large-strain or dynamic FSI model.
[Mechanics guide](../../../docs/solvers/mechanics/README.md),
[source derivation](mechanics/elasticity/assembly_tetra_structural.py) and
[AC/heat/stress record](../../../docs/validation/AC_THERMAL_ELASTIC_20261023.md)
retain affine/free-expansion/clamped-slab checks and reviewed Bower/Staelin
sections. Power in W is not elastic energy in J; thermal eigenstrain invalidates
blindly identifying elastic energy with half external mechanical work.

Reduced PM machines use `L di/dt=V-Ri-Kω`,
`J dω/dt=Ki+τ_external-bω`, `dθ/dt=ω`. Reciprocal K and implicit midpoint
support a discrete work identity. Linear reluctance actuators use
`R_m=l_core/(μ0 μr A_core)+g/(μ0 A_gap)`, `Φ=NI/R_m`,
`L=N²/R_m`, `F=Φ²/(2μ0 A_gap)` with a single uniform gap.

Planar magnetic FEM solves `B=(∂y Az,-∂x Az)` and
`∫curl(v)·H dA=∫v Jz dA`. Supplied constitutive energy/tangent supports
potential-decreasing Newton; unsupported B-H extrapolation fails. Stationary
eddy regions use `E_z=-∂t Az+E_offset` and zero integrated induced current,
with BE storage, Joule heating and separate numerical-dissipation accounting.
Air-contour Maxwell stress is `(BBᵀ-|B|²I/2)/μ0`; depth-scaled contour traction
and moment give force/torque. Gauge, air-box, mesh and contour studies matter.
[Magnetic FEM](../../../docs/MAGNETIC_FEM.md),
[machines](../../../docs/EM_MACHINES.md),
[machine studies](../../../docs/MAGNETIC_MACHINE_STUDIES.md) and
[magnetic heating](../../../docs/MAGNETIC_THERMAL.md) preserve reduced/planar
and stationary-versus-moving scope.

Experimental propulsion composes balanced circuit fluxes, a magnetic Hamiltonian,
shaft state, sampled controller and supplied aerodynamic/CFD load. The symmetric
coordinate-increment discrete gradient checks
`H(z_new)-H(z_old)=discrete_grad(H)·(z_new-z_old)`; tiny-step quadrature has its
own chain-defect gate. P2 magnetic triangles, Fourier annular gaps, Schur
condensation, nonlinear material ports and inertial CFD/preconditioning candidates
are separate operators, not a verified actual motor/propeller product.
[Full-loop independent derivation](../../../docs/validation/PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md),
[P2 derivation](../../../docs/validation/PROPULSION_POD_MAGNETIC_P2_DERIVATION_20261023.md),
[modal-gap review](../../../docs/validation/PROPULSION_POD_MODAL_GAP_REVIEW_20261024.md),
[inexact/backtracking evidence](../../../docs/validation/PROPULSION_POD_EXTENDED_BACKTRACKING_20261024.md)
and [EM domain guide](../../../docs/solvers/electromagnetics/README.md) retain
exact operators, sources, failed convergence and resource boundaries.
Actual-air loads and source-specific motor torque convergence remain open.
The [propulsion plan](../../../docs/PROPULSION_MACHINES_FLUID_POWER_PLAN.md)
does not enable general chemical engineering or unverified reacting flow.

## 9. Maxwell fields, radiation and external engines

Continuum Maxwell laws are `∇×E=-∂B/∂t`, `∇×H=J+∂D/∂t` with explicit material
and excitation data. Installed openEMS performs its FDTD solve; SPIKE owns
admitted geometry/ports and result normalization. Multiple excitations satisfy
`S A=B`, requiring a matrix solve, not independent scalar column division.
Grid/domain/PML/time-termination studies remain separate gates.

The owned closed-box Huygens postprocessor uses peak `exp(+jωt)` fields,
`J_s=n×H`, `M_s=-n×E`, and surface quadrature for
`E_far=F(r_hat)exp(-jkr)/r`. It requires a closed surface enclosing sources in a
homogeneous lossless exterior, with no PML intersection. RWG bases, singular
Green moments and supplied-current far-field/RCS operators do not determine
induced currents and do not constitute an EFIE/MoM solver.
Authorities: [retained EM](../../../docs/RETAINED_ASSEMBLY_EM.md),
[independent reference](../../../docs/RETAINED_EM_INDEPENDENT_REFERENCE.md),
[Huygens/radiation](../../../docs/BOUNDED_CHT_AND_RADIATION.md),
[RWG/operator evidence](../../../docs/validation/MOM_REFERENCE_OPERATORS_20260930.md).
Recorded foundations include Rao/Wilton/Glisson (1982), Duffy (1982), MIT radiation
potentials and CODATA constants, with exact use in
[R17](../../../docs/SOLVER_REFERENCES.md#r17---surface-em-reference-operators).

[External engine status](../../../docs/solvers/external-engines/README.md)
separately catalogs openEMS/CSXCAD, EMerge, SU2, OpenFOAM, CalculiX, ngspice,
PALACE, Xyce, sparseLizard and unavailable/planned engines. Gmsh and FreeCAD
prepare or exchange geometry; they do not qualify physics. Runtime documentation
is not proof that all engine algorithms are implemented by SPIKE. Preserve the
actual executable version and model/settings rather than a moving documentation
URL. Native arbitrary-geometry full-wave and full surface MoM remain unavailable.

## 10. Coupling, linear algebra and execution support

Fixed-point coupling requires the **unrelaxed** defect `F(x)-x` as well as
application-specific power/temperature criteria. A reduced relaxed update can
hide a failed fixed point. Conservative exchange maps equal/opposite loads and
adjoint field transfers; `L=-Oᵀq`, `x_s=A_s⁻¹ O x_d` in the
[surface-exchange method](../../../docs/COUPLED_SURFACE_EXCHANGE.md) is not itself
a coupling time integrator or FSI solver. Same-mesh composition must retain
source/region identity and avoid duplicate heating. A recorded digital-twin
residual compares supplied aligned quantities, not automatic system identification.

Sparse/dense direct factorization, CG on admitted positive systems, MINRES on
admitted symmetric systems, Newton/backtracking, Schur reduction, state matrix
exponentials, quadrature and interpolation are numerical mechanisms; their
presence does not determine a model's physical validity. Scale/conditioning,
backward error, conservation, iteration termination and refinement tests are
method-specific. Never infer a universal accuracy percentage from a norm or
repair a rejected model by arbitrary grounding/PSD projection/clipping.

[Execution guide](../../../docs/solvers/execution/README.md),
[co-simulation](../../../docs/COSIMULATION_DIGITAL_TWIN.md),
[runtime resource policy](../../../docs/WORKER_NUMERICAL_RUNTIME.md) and
[native/HPC roadmap](../../../docs/NATIVE_HPC_MIGRATION.md) distinguish inner
BLAS/OpenMP threads, independent CPU/LAN jobs, optional GPU sparse operations
and planned distributed solves. Scheduling, caching, byte admission and adapters
appear in the source inventory because they support solvers, not because they
implement additional governing physics.

## Reference coverage and open work

The linked ledgers are the research bibliography, including DOI/official URLs
and exact reviewed versions/sections where recorded. The generated inventory
also indexes references embedded in source, tests, benchmarks and method
documents. It is a recorded-link snapshot with its own exclusions; it is not
proof that every URL was read or every paper adopted. Bibliographic access,
implementation provenance, clean-room rights, numerical evidence and physical
validation must remain separate.

Known gaps are intentionally preserved:

- Some historical MNA/thermal implementations and empirical Hammerstad/Jensen
  formulas lack complete primary edition/section provenance. Device stamps,
  limits, scaling and histories do not yet form one fully reviewed derivation.
- Source reference modules and a passing synthetic oracle do not establish
  arbitrary geometry, continuous-band causality/passivity, real-device accuracy,
  measured uncertainty, turbulence/propeller performance or release approval.
- Literature marked candidate/design guidance (including high-order/immersed
  CFD, FMM and EFIE preconditioning) is not implemented coverage merely because
  it appears in a bibliography or plan. Dataset admission is not a matching run.
- Later source edits/moves and dependency versions require fresh evidence;
  historical hashes, frozen workers and installer receipts remain historical.
- Knowledgeable human numerical review remains required before release under
  [CONTRIBUTING](../../../CONTRIBUTING.md) and the evidence policy.

Maintain this document when adding/removing solver owners: update the inventory,
link the independently authored method and primary-reference ledger, retain
explicit experimental/unsupported states, and record executed evidence separately.

## Complete grouped source inventory

The following is a filesystem snapshot of non-ignored `.py`, `.cpp`, `.hpp`,
`.h` and `.c` files beneath `python/spike_core/solvers` and `src/solvers`, excluding
Python `__init__.py` package markers. Generated bytecode, documentation, tests,
extension packages, services outside these roots and private/ignored research
are excluded. Domain guides above cover external adapters and services outside
the roots. Each entry is an implementation/support file, **not a solver count**.
Inventory generation enumerates files; it does not claim line-by-line mathematical
review of every file. Detailed method owners remain the links above and each
subgroup README.

<!-- SOURCE_INVENTORY -->

**Inventory: 484 implementation/support files in 31 directory groups.**

### `python/spike_core/solvers`

[Subgroup guide](README.md)

- [_source_layout.py](_source_layout.py)

### `python/spike_core/solvers/circuits/models`

[Subgroup guide](circuits/models/README.md)

- [benchmark_native_mna.py](circuits/models/benchmark_native_mna.py)
- [converter_study.py](circuits/models/converter_study.py)
- [multiboard_circuit.py](circuits/models/multiboard_circuit.py)
- [multiboard_circuit_bonds.py](circuits/models/multiboard_circuit_bonds.py)
- [native_circuit_compiler.py](circuits/models/native_circuit_compiler.py)
- [native_circuit_result.py](circuits/models/native_circuit_result.py)
- [native_mna.py](circuits/models/native_mna.py)
- [native_source_waveforms.py](circuits/models/native_source_waveforms.py)
- [semiconductor_operating_losses.py](circuits/models/semiconductor_operating_losses.py)
- [smps_converter.py](circuits/models/smps_converter.py)
- [spikes_native_adapter.py](circuits/models/spikes_native_adapter.py)
- [topology_circuit.py](circuits/models/topology_circuit.py)
- [transient_diode_field.py](circuits/models/transient_diode_field.py)

### `python/spike_core/solvers/electromagnetics/fields`

[Subgroup guide](electromagnetics/fields/README.md)

- [antenna_measured_comparison.py](electromagnetics/fields/antenna_measured_comparison.py)
- [assembly_em.py](electromagnetics/fields/assembly_em.py)
- [assembly_em_board_geometry.py](electromagnetics/fields/assembly_em_board_geometry.py)
- [assembly_em_diagnostics.py](electromagnetics/fields/assembly_em_diagnostics.py)
- [assembly_em_grid.py](electromagnetics/fields/assembly_em_grid.py)
- [assembly_em_planar_mesher.py](electromagnetics/fields/assembly_em_planar_mesher.py)
- [assembly_em_study.py](electromagnetics/fields/assembly_em_study.py)
- [crossboard_field_screen.py](electromagnetics/fields/crossboard_field_screen.py)
- [emi.py](electromagnetics/fields/emi.py)
- [fdtd_completion.py](electromagnetics/fields/fdtd_completion.py)
- [huygens_far_field.py](electromagnetics/fields/huygens_far_field.py)
- [mom_far_field.py](electromagnetics/fields/mom_far_field.py)
- [mom_singular_source.py](electromagnetics/fields/mom_singular_source.py)
- [mom_surface_basis.py](electromagnetics/fields/mom_surface_basis.py)
- [multi_excitation_network.py](electromagnetics/fields/multi_excitation_network.py)
- [multiboard_em.py](electromagnetics/fields/multiboard_em.py)
- [multiboard_radiation.py](electromagnetics/fields/multiboard_radiation.py)

### `python/spike_core/solvers/electromagnetics/machines`

[Subgroup guide](electromagnetics/machines/README.md)

- [actuator_force_map.py](electromagnetics/machines/actuator_force_map.py)
- [actuator_motion.py](electromagnetics/machines/actuator_motion.py)
- [em_machines.py](electromagnetics/machines/em_machines.py)
- [machine_geometry.py](electromagnetics/machines/machine_geometry.py)
- [magnetic_fem.py](electromagnetics/machines/magnetic_fem.py)
- [magnetic_machine_study.py](electromagnetics/machines/magnetic_machine_study.py)
- [magnetic_thermal.py](electromagnetics/machines/magnetic_thermal.py)
- [voice_coil_drive.py](electromagnetics/machines/voice_coil_drive.py)

### `python/spike_core/solvers/electromagnetics/propulsion`

[Subgroup guide](electromagnetics/propulsion/README.md)

- [propulsion_pod.py](electromagnetics/propulsion/propulsion_pod.py)
- [propulsion_pod_annular_gap.py](electromagnetics/propulsion/propulsion_pod_annular_gap.py)
- [propulsion_pod_cfd_refinement.py](electromagnetics/propulsion/propulsion_pod_cfd_refinement.py)
- [propulsion_pod_controller.py](electromagnetics/propulsion/propulsion_pod_controller.py)
- [propulsion_pod_convergence.py](electromagnetics/propulsion/propulsion_pod_convergence.py)
- [propulsion_pod_energy_step.py](electromagnetics/propulsion/propulsion_pod_energy_step.py)
- [propulsion_pod_energy_table.py](electromagnetics/propulsion/propulsion_pod_energy_table.py)
- [propulsion_pod_field.py](electromagnetics/propulsion/propulsion_pod_field.py)
- [propulsion_pod_field_preview.py](electromagnetics/propulsion/propulsion_pod_field_preview.py)
- [propulsion_pod_geometry_loop.py](electromagnetics/propulsion/propulsion_pod_geometry_loop.py)
- [propulsion_pod_geometry_run.py](electromagnetics/propulsion/propulsion_pod_geometry_run.py)
- [propulsion_pod_inertial_cfd.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd.py)
- [propulsion_pod_inertial_cfd_case.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_case.py)
- [propulsion_pod_inertial_cfd_coarsen.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_coarsen.py)
- [propulsion_pod_inertial_cfd_current.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_current.py)
- [propulsion_pod_inertial_cfd_foil.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_foil.py)
- [propulsion_pod_inertial_cfd_forcing.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_forcing.py)
- [propulsion_pod_inertial_cfd_geometry.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_geometry.py)
- [propulsion_pod_inertial_cfd_geometry_screen.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_geometry_screen.py)
- [propulsion_pod_inertial_cfd_inexact.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_inexact.py)
- [propulsion_pod_inertial_cfd_linear.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_linear.py)
- [propulsion_pod_inertial_cfd_memory.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_memory.py)
- [propulsion_pod_inertial_cfd_preflight.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_preflight.py)
- [propulsion_pod_inertial_cfd_pressure_pin.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_pressure_pin.py)
- [propulsion_pod_inertial_cfd_schur.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_schur.py)
- [propulsion_pod_inertial_cfd_stl.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_stl.py)
- [propulsion_pod_inertial_cfd_supg.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_supg.py)
- [propulsion_pod_inertial_cfd_surface_repair.py](electromagnetics/propulsion/propulsion_pod_inertial_cfd_surface_repair.py)
- [propulsion_pod_jacobian_schur.py](electromagnetics/propulsion/propulsion_pod_jacobian_schur.py)
- [propulsion_pod_load_table.py](electromagnetics/propulsion/propulsion_pod_load_table.py)
- [propulsion_pod_magnetic_indicator.py](electromagnetics/propulsion/propulsion_pod_magnetic_indicator.py)
- [propulsion_pod_magnetic_p2.py](electromagnetics/propulsion/propulsion_pod_magnetic_p2.py)
- [propulsion_pod_modal_gap.py](electromagnetics/propulsion/propulsion_pod_modal_gap.py)
- [propulsion_pod_nonlinear_motor.py](electromagnetics/propulsion/propulsion_pod_nonlinear_motor.py)
- [propulsion_pod_nonlinear_p2.py](electromagnetics/propulsion/propulsion_pod_nonlinear_p2.py)
- [propulsion_pod_nonlinear_port.py](electromagnetics/propulsion/propulsion_pod_nonlinear_port.py)
- [propulsion_pod_propeller.py](electromagnetics/propulsion/propulsion_pod_propeller.py)
- [propulsion_pod_real_motor.py](electromagnetics/propulsion/propulsion_pod_real_motor.py)
- [propulsion_pod_real_motor_domains.py](electromagnetics/propulsion/propulsion_pod_real_motor_domains.py)
- [propulsion_pod_real_motor_extract.py](electromagnetics/propulsion/propulsion_pod_real_motor_extract.py)
- [propulsion_pod_real_motor_p2.py](electromagnetics/propulsion/propulsion_pod_real_motor_p2.py)
- [propulsion_pod_rotor_cfd.py](electromagnetics/propulsion/propulsion_pod_rotor_cfd.py)
- [propulsion_pod_rotor_cfd_geometry.py](electromagnetics/propulsion/propulsion_pod_rotor_cfd_geometry.py)
- [propulsion_pod_separated_motor.py](electromagnetics/propulsion/propulsion_pod_separated_motor.py)
- [propulsion_pod_thermal.py](electromagnetics/propulsion/propulsion_pod_thermal.py)
- [propulsion_pod_three_phase.py](electromagnetics/propulsion/propulsion_pod_three_phase.py)
- [propulsion_pod_three_phase_controller.py](electromagnetics/propulsion/propulsion_pod_three_phase_controller.py)
- [propulsion_pod_three_phase_field.py](electromagnetics/propulsion/propulsion_pod_three_phase_field.py)
- [propulsion_pod_three_phase_run.py](electromagnetics/propulsion/propulsion_pod_three_phase_run.py)
- [propulsion_pod_transport_contractions.py](electromagnetics/propulsion/propulsion_pod_transport_contractions.py)
- [propulsion_pod_vesc_binding.py](electromagnetics/propulsion/propulsion_pod_vesc_binding.py)

### `python/spike_core/solvers/execution/coupling`

[Subgroup guide](execution/coupling/README.md)

- [assembly_field_geometry.py](execution/coupling/assembly_field_geometry.py)
- [assembly_field_handoff.py](execution/coupling/assembly_field_handoff.py)
- [assembly_field_result.py](execution/coupling/assembly_field_result.py)
- [assembly_field_study.py](execution/coupling/assembly_field_study.py)
- [assembly_field_thermal.py](execution/coupling/assembly_field_thermal.py)
- [assembly_field_transient.py](execution/coupling/assembly_field_transient.py)
- [cosimulation.py](execution/coupling/cosimulation.py)
- [coupled_surface_exchange.py](execution/coupling/coupled_surface_exchange.py)
- [digital_twin.py](execution/coupling/digital_twin.py)
- [electrothermal_sharing.py](execution/coupling/electrothermal_sharing.py)
- [em_body_heating.py](execution/coupling/em_body_heating.py)
- [em_network_ac.py](execution/coupling/em_network_ac.py)
- [em_network_resistor_cht.py](execution/coupling/em_network_resistor_cht.py)
- [em_network_resistor_thermal.py](execution/coupling/em_network_resistor_thermal.py)
- [em_spice_coupling.py](execution/coupling/em_spice_coupling.py)
- [em_spice_coupling_circuit.py](execution/coupling/em_spice_coupling_circuit.py)
- [field_circuit_cosim.py](execution/coupling/field_circuit_cosim.py)

### `python/spike_core/solvers/execution/resources`

[Subgroup guide](execution/resources/README.md)

- [acceleration.py](execution/resources/acceleration.py)
- [gpu_acceleration.py](execution/resources/gpu_acceleration.py)
- [parallel_pool.py](execution/resources/parallel_pool.py)

### `python/spike_core/solvers/external_engines/calculix`

[Subgroup guide](external_engines/calculix/README.md)

- [calculix_deck.py](external_engines/calculix/calculix_deck.py)
- [calculix_runtime.py](external_engines/calculix/calculix_runtime.py)
- [calculix_thermal.py](external_engines/calculix/calculix_thermal.py)
- [calculix_transient.py](external_engines/calculix/calculix_transient.py)

### `python/spike_core/solvers/external_engines/circuits`

[Subgroup guide](external_engines/circuits/README.md)

- [ngspice_plugin.py](external_engines/circuits/ngspice_plugin.py)
- [owned_spice_process.py](external_engines/circuits/owned_spice_process.py)

### `python/spike_core/solvers/external_engines/openems`

[Subgroup guide](external_engines/openems/README.md)

- [openems_adapter_source.py](external_engines/openems/openems_adapter_source.py)
- [openems_assembly_geometry.py](external_engines/openems/openems_assembly_geometry.py)
- [openems_benchmarks.py](external_engines/openems/openems_benchmarks.py)
- [openems_case_integrity.py](external_engines/openems/openems_case_integrity.py)
- [openems_geometry_admission.py](external_engines/openems/openems_geometry_admission.py)
- [openems_stopping.py](external_engines/openems/openems_stopping.py)
- [openems_validation.py](external_engines/openems/openems_validation.py)
- [openems_validation_evidence.py](external_engines/openems/openems_validation_evidence.py)

### `python/spike_core/solvers/external_engines/openfoam`

[Subgroup guide](external_engines/openfoam/README.md)

- [openfoam.py](external_engines/openfoam/openfoam.py)
- [openfoam_buoyancy.py](external_engines/openfoam/openfoam_buoyancy.py)
- [openfoam_fan_fixture.py](external_engines/openfoam/openfoam_fan_fixture.py)
- [openfoam_flow_diagnostics.py](external_engines/openfoam/openfoam_flow_diagnostics.py)
- [openfoam_flow_energy_validation.py](external_engines/openfoam/openfoam_flow_energy_validation.py)
- [openfoam_materials.py](external_engines/openfoam/openfoam_materials.py)
- [openfoam_mesh_geometry_audit.py](external_engines/openfoam/openfoam_mesh_geometry_audit.py)
- [openfoam_multiregion.py](external_engines/openfoam/openfoam_multiregion.py)
- [openfoam_multiregion_execution.py](external_engines/openfoam/openfoam_multiregion_execution.py)
- [openfoam_multiregion_fixture.py](external_engines/openfoam/openfoam_multiregion_fixture.py)
- [openfoam_multiregion_flow.py](external_engines/openfoam/openfoam_multiregion_flow.py)
- [openfoam_multiregion_render.py](external_engines/openfoam/openfoam_multiregion_render.py)
- [openfoam_multiregion_validation.py](external_engines/openfoam/openfoam_multiregion_validation.py)
- [openfoam_polymesh.py](external_engines/openfoam/openfoam_polymesh.py)
- [openfoam_pressure_work.py](external_engines/openfoam/openfoam_pressure_work.py)
- [openfoam_rectilinear_assembly.py](external_engines/openfoam/openfoam_rectilinear_assembly.py)
- [openfoam_refinement_study.py](external_engines/openfoam/openfoam_refinement_study.py)
- [openfoam_runtime.py](external_engines/openfoam/openfoam_runtime.py)
- [openfoam_streamline_export.py](external_engines/openfoam/openfoam_streamline_export.py)
- [openfoam_turbulence.py](external_engines/openfoam/openfoam_turbulence.py)

### `python/spike_core/solvers/external_engines/sparselizard`

[Subgroup guide](external_engines/sparselizard/README.md)

- [sparselizard_adapter.py](external_engines/sparselizard/sparselizard_adapter.py)
- [sparselizard_process.py](external_engines/sparselizard/sparselizard_process.py)
- [sparselizard_runtime.py](external_engines/sparselizard/sparselizard_runtime.py)
- [sparselizard_validation.py](external_engines/sparselizard/sparselizard_validation.py)

### `python/spike_core/solvers/external_engines/su2`

[Subgroup guide](external_engines/su2/README.md)

- [su2_airflow.py](external_engines/su2/su2_airflow.py)
- [su2_cht.py](external_engines/su2/su2_cht.py)

### `python/spike_core/solvers/geometry_meshing/preparation`

[Subgroup guide](geometry_meshing/preparation/README.md)

- [assembly_thermal_autolink.py](geometry_meshing/preparation/assembly_thermal_autolink.py)
- [assembly_thermal_body_power.py](geometry_meshing/preparation/assembly_thermal_body_power.py)
- [assembly_thermal_cad.py](geometry_meshing/preparation/assembly_thermal_cad.py)
- [assembly_thermal_components.py](geometry_meshing/preparation/assembly_thermal_components.py)
- [assembly_thermal_contact_model.py](geometry_meshing/preparation/assembly_thermal_contact_model.py)
- [assembly_thermal_encapsulation.py](geometry_meshing/preparation/assembly_thermal_encapsulation.py)
- [assembly_thermal_encapsulation_occ.py](geometry_meshing/preparation/assembly_thermal_encapsulation_occ.py)
- [assembly_thermal_joint_geometry.py](geometry_meshing/preparation/assembly_thermal_joint_geometry.py)
- [assembly_thermal_joint_mesh.py](geometry_meshing/preparation/assembly_thermal_joint_mesh.py)
- [assembly_thermal_meshing.py](geometry_meshing/preparation/assembly_thermal_meshing.py)
- [board_mesh_ownership.py](geometry_meshing/preparation/board_mesh_ownership.py)
- [boundary_spatial_index.py](geometry_meshing/preparation/boundary_spatial_index.py)
- [conforming_local_refinement.py](geometry_meshing/preparation/conforming_local_refinement.py)
- [crossboard_mesh.py](geometry_meshing/preparation/crossboard_mesh.py)
- [dynamic_tetra_adaptation.py](geometry_meshing/preparation/dynamic_tetra_adaptation.py)
- [generalized_reference_plane_mesh_quality.py](geometry_meshing/preparation/generalized_reference_plane_mesh_quality.py)
- [generalized_reference_plane_native_handoff.py](geometry_meshing/preparation/generalized_reference_plane_native_handoff.py)
- [geometry.py](geometry_meshing/preparation/geometry.py)
- [gmsh_environment.py](geometry_meshing/preparation/gmsh_environment.py)
- [gmsh_extension_api.py](geometry_meshing/preparation/gmsh_extension_api.py)
- [gmsh_extension_mesh.py](geometry_meshing/preparation/gmsh_extension_mesh.py)
- [gmsh_extension_runtime.py](geometry_meshing/preparation/gmsh_extension_runtime.py)
- [gmsh_occ_mesher.py](geometry_meshing/preparation/gmsh_occ_mesher.py)
- [gmsh_occ_runtime.py](geometry_meshing/preparation/gmsh_occ_runtime.py)
- [hybrid_mesh.py](geometry_meshing/preparation/hybrid_mesh.py)
- [internal_meshing_engine.py](geometry_meshing/preparation/internal_meshing_engine.py)
- [internal_tetra_generation.py](geometry_meshing/preparation/internal_tetra_generation.py)
- [local_mesh_controls.py](geometry_meshing/preparation/local_mesh_controls.py)
- [mesh_ownership.py](geometry_meshing/preparation/mesh_ownership.py)
- [meshing.py](geometry_meshing/preparation/meshing.py)
- [pcb_focus_sizing.py](geometry_meshing/preparation/pcb_focus_sizing.py)
- [pcb_volume_compiler.py](geometry_meshing/preparation/pcb_volume_compiler.py)
- [pcb_volume_mesh.py](geometry_meshing/preparation/pcb_volume_mesh.py)
- [planar_curve_tessellation.py](geometry_meshing/preparation/planar_curve_tessellation.py)
- [planar_polygon_topology.py](geometry_meshing/preparation/planar_polygon_topology.py)
- [reference_plane_antipad_geometry.py](geometry_meshing/preparation/reference_plane_antipad_geometry.py)
- [reference_plane_antipad_geometry_v2.py](geometry_meshing/preparation/reference_plane_antipad_geometry_v2.py)
- [reference_plane_antipad_geometry_v3.py](geometry_meshing/preparation/reference_plane_antipad_geometry_v3.py)
- [reference_plane_antipad_mesh.py](geometry_meshing/preparation/reference_plane_antipad_mesh.py)
- [reference_plane_antipad_mesh_quality.py](geometry_meshing/preparation/reference_plane_antipad_mesh_quality.py)
- [reference_plane_antipad_mesh_v2.py](geometry_meshing/preparation/reference_plane_antipad_mesh_v2.py)
- [reference_plane_antipad_native_handoff.py](geometry_meshing/preparation/reference_plane_antipad_native_handoff.py)
- [reference_plane_mesh_ownership.py](geometry_meshing/preparation/reference_plane_mesh_ownership.py)
- [solver_geometry.py](geometry_meshing/preparation/solver_geometry.py)
- [spatial_sampling.py](geometry_meshing/preparation/spatial_sampling.py)
- [tetra_aabb_candidates.py](geometry_meshing/preparation/tetra_aabb_candidates.py)
- [tetra_mesh_optimization.py](geometry_meshing/preparation/tetra_mesh_optimization.py)
- [tetra_mesh_refinement.py](geometry_meshing/preparation/tetra_mesh_refinement.py)
- [via_transition_geometry.py](geometry_meshing/preparation/via_transition_geometry.py)
- [via_transition_mesh.py](geometry_meshing/preparation/via_transition_mesh.py)
- [via_transition_mesh_quality.py](geometry_meshing/preparation/via_transition_mesh_quality.py)
- [via_transition_native_handoff.py](geometry_meshing/preparation/via_transition_native_handoff.py)

### `python/spike_core/solvers/mechanics/elasticity`

[Subgroup guide](mechanics/elasticity/README.md)

- [assembly_tetra_structural.py](mechanics/elasticity/assembly_tetra_structural.py)
- [assembly_thermomechanical.py](mechanics/elasticity/assembly_thermomechanical.py)

### `python/spike_core/solvers/power_integrity/dc`

[Subgroup guide](power_integrity/dc/README.md)

- [assembly_tetra_electrical.py](power_integrity/dc/assembly_tetra_electrical.py)
- [assembly_tetra_electrical_validation.py](power_integrity/dc/assembly_tetra_electrical_validation.py)
- [benchmarks.py](power_integrity/dc/benchmarks.py)
- [dc_annular_evidence.py](power_integrity/dc/dc_annular_evidence.py)
- [dc_annular_land.py](power_integrity/dc/dc_annular_land.py)
- [dc_annular_land_input.py](power_integrity/dc/dc_annular_land_input.py)
- [dc_annular_source.py](power_integrity/dc/dc_annular_source.py)
- [dc_annular_stack.py](power_integrity/dc/dc_annular_stack.py)
- [dc_annular_stack_input.py](power_integrity/dc/dc_annular_stack_input.py)
- [dc_axial_ownership.py](power_integrity/dc/dc_axial_ownership.py)
- [dc_board_filled.py](power_integrity/dc/dc_board_filled.py)
- [dc_board_partition.py](power_integrity/dc/dc_board_partition.py)
- [dc_board_source.py](power_integrity/dc/dc_board_source.py)
- [dc_board_study.py](power_integrity/dc/dc_board_study.py)
- [dc_board_volume.py](power_integrity/dc/dc_board_volume.py)
- [dc_copper_domain.py](power_integrity/dc/dc_copper_domain.py)
- [dc_land_transition.py](power_integrity/dc/dc_land_transition.py)
- [dc_land_transition_evidence.py](power_integrity/dc/dc_land_transition_evidence.py)
- [dc_land_transition_input.py](power_integrity/dc/dc_land_transition_input.py)
- [dc_port_circuit.py](power_integrity/dc/dc_port_circuit.py)
- [dc_precision_partition.py](power_integrity/dc/dc_precision_partition.py)
- [dc_result_utils.py](power_integrity/dc/dc_result_utils.py)
- [dc_rt0_density.py](power_integrity/dc/dc_rt0_density.py)
- [dc_shifted_rhs.py](power_integrity/dc/dc_shifted_rhs.py)
- [dc_solver.py](power_integrity/dc/dc_solver.py)
- [dc_terminal_validation.py](power_integrity/dc/dc_terminal_validation.py)
- [dc_tetra_density.py](power_integrity/dc/dc_tetra_density.py)
- [dc_tetra_rt0.py](power_integrity/dc/dc_tetra_rt0.py)
- [dc_tetra_rt0_evidence.py](power_integrity/dc/dc_tetra_rt0_evidence.py)
- [dc_tetra_rt0_input.py](power_integrity/dc/dc_tetra_rt0_input.py)
- [dc_tetra_sparse.py](power_integrity/dc/dc_tetra_sparse.py)
- [dc_triangle_partition.py](power_integrity/dc/dc_triangle_partition.py)
- [filled_copper_path.py](power_integrity/dc/filled_copper_path.py)
- [hybrid_dc_solver.py](power_integrity/dc/hybrid_dc_solver.py)
- [hybrid_drilled_roundrect.py](power_integrity/dc/hybrid_drilled_roundrect.py)
- [hybrid_owned_copper.py](power_integrity/dc/hybrid_owned_copper.py)
- [multiboard_volume_electrical_admission.py](power_integrity/dc/multiboard_volume_electrical_admission.py)
- [pi_path.py](power_integrity/dc/pi_path.py)
- [pi_path_circuit.py](power_integrity/dc/pi_path_circuit.py)
- [pi_path_dc.py](power_integrity/dc/pi_path_dc.py)
- [pi_return_path.py](power_integrity/dc/pi_return_path.py)
- [source_current_limits.py](power_integrity/dc/source_current_limits.py)
- [source_filled_boundary.py](power_integrity/dc/source_filled_boundary.py)
- [zone_pad_connection_evidence.py](power_integrity/dc/zone_pad_connection_evidence.py)

### `python/spike_core/solvers/power_integrity/pdn`

[Subgroup guide](power_integrity/pdn/README.md)

- [benchmark_pdn.py](power_integrity/pdn/benchmark_pdn.py)
- [capacitor_placement.py](power_integrity/pdn/capacitor_placement.py)
- [pdn.py](power_integrity/pdn/pdn.py)
- [pdn_admittance_reduction.py](power_integrity/pdn/pdn_admittance_reduction.py)
- [pdn_decap_corners.py](power_integrity/pdn/pdn_decap_corners.py)
- [pdn_decap_selection.py](power_integrity/pdn/pdn_decap_selection.py)
- [pdn_dielectric_ac.py](power_integrity/pdn/pdn_dielectric_ac.py)
- [pdn_dielectric_feedback.py](power_integrity/pdn/pdn_dielectric_feedback.py)
- [pdn_dielectric_thermal.py](power_integrity/pdn/pdn_dielectric_thermal.py)
- [pdn_dielectric_thermomechanical.py](power_integrity/pdn/pdn_dielectric_thermomechanical.py)
- [pdn_electrostatic.py](power_integrity/pdn/pdn_electrostatic.py)
- [pdn_network.py](power_integrity/pdn/pdn_network.py)
- [pdn_series_capacitors.py](power_integrity/pdn/pdn_series_capacitors.py)
- [pdn_shunt_capacitance.py](power_integrity/pdn/pdn_shunt_capacitance.py)
- [quasistatic_capacitance.py](power_integrity/pdn/quasistatic_capacitance.py)
- [quasistatic_copper_area.py](power_integrity/pdn/quasistatic_copper_area.py)

### `python/spike_core/solvers/power_integrity/peec`

[Subgroup guide](power_integrity/peec/README.md)

- [ac_power_integrity.py](power_integrity/peec/ac_power_integrity.py)
- [conductor_ac_loss.py](power_integrity/peec/conductor_ac_loss.py)
- [loop_parasitics.py](power_integrity/peec/loop_parasitics.py)
- [peec_capacitance_dispatch.py](power_integrity/peec/peec_capacitance_dispatch.py)
- [peec_conforming_dc.py](power_integrity/peec/peec_conforming_dc.py)
- [peec_conforming_mesh.py](power_integrity/peec/peec_conforming_mesh.py)
- [peec_field_provider.py](power_integrity/peec/peec_field_provider.py)
- [peec_magnetic_geometry.py](power_integrity/peec/peec_magnetic_geometry.py)
- [peec_matrices.py](power_integrity/peec/peec_matrices.py)
- [peec_native_factory.py](power_integrity/peec/peec_native_factory.py)
- [peec_network.py](power_integrity/peec/peec_network.py)
- [peec_plugin.py](power_integrity/peec/peec_plugin.py)
- [peec_rt0_iterative.py](power_integrity/peec/peec_rt0_iterative.py)
- [peec_spice_export.py](power_integrity/peec/peec_spice_export.py)
- [peec_volume_adapter.py](power_integrity/peec/peec_volume_adapter.py)
- [peec_volume_resistance.py](power_integrity/peec/peec_volume_resistance.py)
- [peec_volume_support.py](power_integrity/peec/peec_volume_support.py)
- [transient_peec.py](power_integrity/peec/transient_peec.py)

### `python/spike_core/solvers/signal_integrity/channels`

[Subgroup guide](signal_integrity/channels/README.md)

- [si_channel.py](signal_integrity/channels/si_channel.py)
- [si_coupled_channel.py](signal_integrity/channels/si_coupled_channel.py)
- [si_frequency_loss.py](signal_integrity/channels/si_frequency_loss.py)
- [si_impedance.py](signal_integrity/channels/si_impedance.py)
- [si_material_scenario.py](signal_integrity/channels/si_material_scenario.py)
- [si_pair_geometry.py](signal_integrity/channels/si_pair_geometry.py)

### `python/spike_core/solvers/signal_integrity/lines`

[Subgroup guide](signal_integrity/lines/README.md)

- [distortionless_line_transient.py](signal_integrity/lines/distortionless_line_transient.py)
- [harness_mtl.py](signal_integrity/lines/harness_mtl.py)
- [harness_pi.py](signal_integrity/lines/harness_pi.py)
- [harness_rlgc_geometry.py](signal_integrity/lines/harness_rlgc_geometry.py)
- [harness_signal.py](signal_integrity/lines/harness_signal.py)
- [lossless_line_transient.py](signal_integrity/lines/lossless_line_transient.py)
- [rlgc_coupled_cascade.py](signal_integrity/lines/rlgc_coupled_cascade.py)
- [rlgc_coupled_pair.py](signal_integrity/lines/rlgc_coupled_pair.py)
- [rlgc_coupled_star.py](signal_integrity/lines/rlgc_coupled_star.py)
- [rlgc_line_cascade.py](signal_integrity/lines/rlgc_line_cascade.py)
- [rlgc_line_fields.py](signal_integrity/lines/rlgc_line_fields.py)
- [rlgc_line_junction.py](signal_integrity/lines/rlgc_line_junction.py)
- [rlgc_line_network.py](signal_integrity/lines/rlgc_line_network.py)
- [rlgc_loaded_cascade.py](signal_integrity/lines/rlgc_loaded_cascade.py)
- [rlgc_loaded_star.py](signal_integrity/lines/rlgc_loaded_star.py)
- [rlgc_reactive_pair.py](signal_integrity/lines/rlgc_reactive_pair.py)
- [rlgc_terminated_pair.py](signal_integrity/lines/rlgc_terminated_pair.py)

### `python/spike_core/solvers/signal_integrity/networks`

[Subgroup guide](signal_integrity/networks/README.md)

- [calibrated_fixture_uq.py](signal_integrity/networks/calibrated_fixture_uq.py)
- [multiport_calibration.py](signal_integrity/networks/multiport_calibration.py)
- [one_port_calibration.py](signal_integrity/networks/one_port_calibration.py)
- [si_candidate_constraints.py](signal_integrity/networks/si_candidate_constraints.py)
- [si_candidate_study.py](signal_integrity/networks/si_candidate_study.py)
- [si_multiboard.py](signal_integrity/networks/si_multiboard.py)
- [si_network_graph.py](signal_integrity/networks/si_network_graph.py)
- [si_network_workflow.py](signal_integrity/networks/si_network_workflow.py)
- [sparameter_capacitive_terminated.py](signal_integrity/networks/sparameter_capacitive_terminated.py)
- [sparameter_crosstalk_timing.py](signal_integrity/networks/sparameter_crosstalk_timing.py)
- [sparameter_deembedding.py](signal_integrity/networks/sparameter_deembedding.py)
- [sparameter_inductive_terminated.py](signal_integrity/networks/sparameter_inductive_terminated.py)
- [sparameter_modes.py](signal_integrity/networks/sparameter_modes.py)
- [sparameter_multi_aggressor.py](signal_integrity/networks/sparameter_multi_aggressor.py)
- [sparameter_multiport_deembedding.py](signal_integrity/networks/sparameter_multiport_deembedding.py)
- [sparameter_rational.py](signal_integrity/networks/sparameter_rational.py)
- [sparameter_reflectometry.py](signal_integrity/networks/sparameter_reflectometry.py)
- [sparameter_rlc_energy.py](signal_integrity/networks/sparameter_rlc_energy.py)
- [sparameter_rlc_initial.py](signal_integrity/networks/sparameter_rlc_initial.py)
- [sparameter_rlc_terminated.py](signal_integrity/networks/sparameter_rlc_terminated.py)
- [sparameter_sampling.py](signal_integrity/networks/sparameter_sampling.py)
- [sparameter_terminated.py](signal_integrity/networks/sparameter_terminated.py)
- [sparameter_transient.py](signal_integrity/networks/sparameter_transient.py)
- [sparameters.py](signal_integrity/networks/sparameters.py)

### `python/spike_core/solvers/signal_integrity/receivers`

[Subgroup guide](signal_integrity/receivers/README.md)

- [ibis_behavioral.py](signal_integrity/receivers/ibis_behavioral.py)
- [ibis_behavioral_execution.py](signal_integrity/receivers/ibis_behavioral_execution.py)
- [ibis_behavioral_tables.py](signal_integrity/receivers/ibis_behavioral_tables.py)
- [si_ami_execution.py](signal_integrity/receivers/si_ami_execution.py)
- [si_ami_inventory.py](signal_integrity/receivers/si_ami_inventory.py)
- [si_clock_recovery.py](signal_integrity/receivers/si_clock_recovery.py)
- [si_crosstalk.py](signal_integrity/receivers/si_crosstalk.py)
- [si_ethernet_qualification.py](signal_integrity/receivers/si_ethernet_qualification.py)
- [si_eye_mask.py](signal_integrity/receivers/si_eye_mask.py)
- [si_eye_mask_profiles.py](signal_integrity/receivers/si_eye_mask_profiles.py)
- [si_ibis.py](signal_integrity/receivers/si_ibis.py)
- [si_pam3.py](signal_integrity/receivers/si_pam3.py)
- [si_pam4_eye.py](signal_integrity/receivers/si_pam4_eye.py)
- [si_passives.py](signal_integrity/receivers/si_passives.py)
- [si_protocol_eye_mask.py](signal_integrity/receivers/si_protocol_eye_mask.py)
- [si_protocol_suites.py](signal_integrity/receivers/si_protocol_suites.py)
- [si_protocol_test_runner.py](signal_integrity/receivers/si_protocol_test_runner.py)
- [si_resonance.py](signal_integrity/receivers/si_resonance.py)
- [si_ringdown.py](signal_integrity/receivers/si_ringdown.py)
- [si_statistical_eye.py](signal_integrity/receivers/si_statistical_eye.py)
- [si_symbol_clock.py](signal_integrity/receivers/si_symbol_clock.py)
- [si_workflow.py](signal_integrity/receivers/si_workflow.py)
- [si_workflow_resonance.py](signal_integrity/receivers/si_workflow_resonance.py)

### `python/spike_core/solvers/thermal_fluid/electrothermal`

[Subgroup guide](thermal_fluid/electrothermal/README.md)

- [assembly_electrothermal.py](thermal_fluid/electrothermal/assembly_electrothermal.py)
- [assembly_electrothermal_setup.py](thermal_fluid/electrothermal/assembly_electrothermal_setup.py)
- [electrical_heat_sources.py](thermal_fluid/electrothermal/electrical_heat_sources.py)
- [energy_balanced_heat.py](thermal_fluid/electrothermal/energy_balanced_heat.py)
- [multiboard_volume_electrothermal.py](thermal_fluid/electrothermal/multiboard_volume_electrothermal.py)
- [multiboard_volume_electrothermal_setup.py](thermal_fluid/electrothermal/multiboard_volume_electrothermal_setup.py)
- [pcb_electrothermal_geometry.py](thermal_fluid/electrothermal/pcb_electrothermal_geometry.py)
- [pwm_electrothermal.py](thermal_fluid/electrothermal/pwm_electrothermal.py)
- [pwm_volume_electrothermal.py](thermal_fluid/electrothermal/pwm_volume_electrothermal.py)
- [structured_electrothermal.py](thermal_fluid/electrothermal/structured_electrothermal.py)
- [transient_resistive_electrothermal.py](thermal_fluid/electrothermal/transient_resistive_electrothermal.py)

### `python/spike_core/solvers/thermal_fluid/flow`

[Subgroup guide](thermal_fluid/flow/README.md)

- [assembly_airflow.py](thermal_fluid/flow/assembly_airflow.py)
- [assembly_airflow_admission.py](thermal_fluid/flow/assembly_airflow_admission.py)
- [assembly_airflow_mesh.py](thermal_fluid/flow/assembly_airflow_mesh.py)
- [assembly_airflow_runtime.py](thermal_fluid/flow/assembly_airflow_runtime.py)
- [assembly_airflow_subdivision.py](thermal_fluid/flow/assembly_airflow_subdivision.py)
- [cfd_reference_correlation.py](thermal_fluid/flow/cfd_reference_correlation.py)
- [cfd_tetra_cht.py](thermal_fluid/flow/cfd_tetra_cht.py)
- [cfd_tetra_energy.py](thermal_fluid/flow/cfd_tetra_energy.py)
- [cfd_tetra_intersections.py](thermal_fluid/flow/cfd_tetra_intersections.py)
- [cfd_tetra_mesh.py](thermal_fluid/flow/cfd_tetra_mesh.py)
- [cfd_tetra_stokes.py](thermal_fluid/flow/cfd_tetra_stokes.py)
- [enclosure_cht.py](thermal_fluid/flow/enclosure_cht.py)
- [enclosure_cht_v2.py](thermal_fluid/flow/enclosure_cht_v2.py)
- [enclosure_energy.py](thermal_fluid/flow/enclosure_energy.py)
- [enclosure_flow_analysis.py](thermal_fluid/flow/enclosure_flow_analysis.py)
- [enclosure_laminar.py](thermal_fluid/flow/enclosure_laminar.py)
- [enclosure_rans_research.py](thermal_fluid/flow/enclosure_rans_research.py)
- [enclosure_rectilinear_momentum.py](thermal_fluid/flow/enclosure_rectilinear_momentum.py)
- [enclosure_refinement.py](thermal_fluid/flow/enclosure_refinement.py)
- [enclosure_rotating_frame.py](thermal_fluid/flow/enclosure_rotating_frame.py)
- [enclosure_sa_transport.py](thermal_fluid/flow/enclosure_sa_transport.py)
- [enclosure_stokes.py](thermal_fluid/flow/enclosure_stokes.py)
- [enclosure_symmetric_stress.py](thermal_fluid/flow/enclosure_symmetric_stress.py)
- [fan_system_operating_point.py](thermal_fluid/flow/fan_system_operating_point.py)
- [internal_airflow.py](thermal_fluid/flow/internal_airflow.py)
- [laminar_channel_cht.py](thermal_fluid/flow/laminar_channel_cht.py)
- [native_airflow.py](thermal_fluid/flow/native_airflow.py)
- [native_cavity_momentum.py](thermal_fluid/flow/native_cavity_momentum.py)
- [native_cht.py](thermal_fluid/flow/native_cht.py)
- [native_cht_result.py](thermal_fluid/flow/native_cht_result.py)

### `python/spike_core/solvers/thermal_fluid/heat`

[Subgroup guide](thermal_fluid/heat/README.md)

- [assembly_tetra_radiation.py](thermal_fluid/heat/assembly_tetra_radiation.py)
- [assembly_tetra_thermal.py](thermal_fluid/heat/assembly_tetra_thermal.py)
- [assembly_tetra_thermal_validation.py](thermal_fluid/heat/assembly_tetra_thermal_validation.py)
- [assembly_tetra_transient.py](thermal_fluid/heat/assembly_tetra_transient.py)
- [assembly_view_factors.py](thermal_fluid/heat/assembly_view_factors.py)
- [board_thermal.py](thermal_fluid/heat/board_thermal.py)
- [component_thermal.py](thermal_fluid/heat/component_thermal.py)
- [layered_board_thermal.py](thermal_fluid/heat/layered_board_thermal.py)
- [multiboard_thermal.py](thermal_fluid/heat/multiboard_thermal.py)
- [multiboard_thermal_parts.py](thermal_fluid/heat/multiboard_thermal_parts.py)
- [multiboard_thermal_scope.py](thermal_fluid/heat/multiboard_thermal_scope.py)
- [retained_thermal_step.py](thermal_fluid/heat/retained_thermal_step.py)
- [structured_solid_thermal.py](thermal_fluid/heat/structured_solid_thermal.py)
- [thermal.py](thermal_fluid/heat/thermal.py)
- [thermal_accuracy.py](thermal_fluid/heat/thermal_accuracy.py)
- [thermal_copper_geometry.py](thermal_fluid/heat/thermal_copper_geometry.py)
- [thermal_field_job.py](thermal_fluid/heat/thermal_field_job.py)
- [thermal_grid.py](thermal_fluid/heat/thermal_grid.py)
- [thermal_network.py](thermal_fluid/heat/thermal_network.py)
- [thermal_relief_boundary_contact.py](thermal_fluid/heat/thermal_relief_boundary_contact.py)
- [thermal_relief_observed_topology.py](thermal_fluid/heat/thermal_relief_observed_topology.py)
- [thermal_spoke_observed_geometry.py](thermal_fluid/heat/thermal_spoke_observed_geometry.py)

### `src/solvers/circuits/spikes`

[Subgroup guide](../../../src/solvers/circuits/spikes/README.md)

- [appcontainer_launcher.cpp](../../../src/solvers/circuits/spikes/appcontainer_launcher.cpp)
- [behavioral_expression.hpp](../../../src/solvers/circuits/spikes/behavioral_expression.hpp)
- [board_library.h](../../../src/solvers/circuits/spikes/board_library.h)
- [board_library.hpp](../../../src/solvers/circuits/spikes/board_library.hpp)
- [board_library_runtime.cpp](../../../src/solvers/circuits/spikes/board_library_runtime.cpp)
- [c_api.cpp](../../../src/solvers/circuits/spikes/c_api.cpp)
- [c_api.h](../../../src/solvers/circuits/spikes/c_api.h)
- [console_dashboard.cpp](../../../src/solvers/circuits/spikes/console_dashboard.cpp)
- [console_dashboard.hpp](../../../src/solvers/circuits/spikes/console_dashboard.hpp)
- [console_main.cpp](../../../src/solvers/circuits/spikes/console_main.cpp)
- [dc_solver.cpp](../../../src/solvers/circuits/spikes/dc_solver.cpp)
- [dc_solver.hpp](../../../src/solvers/circuits/spikes/dc_solver.hpp)
- [digital_kernel.hpp](../../../src/solvers/circuits/spikes/digital_kernel.hpp)
- [io_pad.cpp](../../../src/solvers/circuits/spikes/io_pad.cpp)
- [io_pad.hpp](../../../src/solvers/circuits/spikes/io_pad.hpp)
- [io_pad_events.cpp](../../../src/solvers/circuits/spikes/io_pad_events.cpp)
- [io_pad_events.hpp](../../../src/solvers/circuits/spikes/io_pad_events.hpp)
- [osdi_device.cpp](../../../src/solvers/circuits/spikes/osdi_device.cpp)
- [osdi_device.hpp](../../../src/solvers/circuits/spikes/osdi_device.hpp)
- [osdi_worker_main.cpp](../../../src/solvers/circuits/spikes/osdi_worker_main.cpp)
- [peripheral_c_api.cpp](../../../src/solvers/circuits/spikes/peripheral_c_api.cpp)
- [peripheral_c_api.h](../../../src/solvers/circuits/spikes/peripheral_c_api.h)
- [peripheral_registers.cpp](../../../src/solvers/circuits/spikes/peripheral_registers.cpp)
- [peripheral_registers.hpp](../../../src/solvers/circuits/spikes/peripheral_registers.hpp)
- [peripheral_timing.cpp](../../../src/solvers/circuits/spikes/peripheral_timing.cpp)
- [peripheral_timing.hpp](../../../src/solvers/circuits/spikes/peripheral_timing.hpp)
- [smps_stability.cpp](../../../src/solvers/circuits/spikes/smps_stability.cpp)
- [smps_stability.hpp](../../../src/solvers/circuits/spikes/smps_stability.hpp)
- [tcad_console.cpp](../../../src/solvers/circuits/spikes/tcad_console.cpp)
- [tcad_equilibrium.cpp](../../../src/solvers/circuits/spikes/tcad_equilibrium.cpp)
- [tcad_equilibrium.hpp](../../../src/solvers/circuits/spikes/tcad_equilibrium.hpp)
- [transient_session.cpp](../../../src/solvers/circuits/spikes/transient_session.cpp)
- [transient_session.hpp](../../../src/solvers/circuits/spikes/transient_session.hpp)
- [transient_solver.cpp](../../../src/solvers/circuits/spikes/transient_solver.cpp)
- [transient_solver.hpp](../../../src/solvers/circuits/spikes/transient_solver.hpp)

### `src/solvers/geometry_meshing/geometry`

[Subgroup guide](../../../src/solvers/geometry_meshing/geometry/README.md)

- [constrained_triangulation.cpp](../../../src/solvers/geometry_meshing/geometry/constrained_triangulation.cpp)
- [planar_topology.cpp](../../../src/solvers/geometry_meshing/geometry/planar_topology.cpp)
- [planar_topology.hpp](../../../src/solvers/geometry_meshing/geometry/planar_topology.hpp)

### `src/solvers/power_integrity/peec`

[Subgroup guide](../../../src/solvers/power_integrity/peec/README.md)

- [affine_slab_inductance.cpp](../../../src/solvers/power_integrity/peec/affine_slab_inductance.cpp)
- [affine_slab_inductance.hpp](../../../src/solvers/power_integrity/peec/affine_slab_inductance.hpp)
- [affine_triangle_basis.cpp](../../../src/solvers/power_integrity/peec/affine_triangle_basis.cpp)
- [affine_triangle_basis.hpp](../../../src/solvers/power_integrity/peec/affine_triangle_basis.hpp)
- [annular_inductance.cpp](../../../src/solvers/power_integrity/peec/annular_inductance.cpp)
- [annular_inductance.hpp](../../../src/solvers/power_integrity/peec/annular_inductance.hpp)
- [generalized_reference_plane_mesh_input.cpp](../../../src/solvers/power_integrity/peec/generalized_reference_plane_mesh_input.cpp)
- [generalized_reference_plane_mesh_input.hpp](../../../src/solvers/power_integrity/peec/generalized_reference_plane_mesh_input.hpp)
- [peec_solver.cpp](../../../src/solvers/power_integrity/peec/peec_solver.cpp)
- [peec_solver.hpp](../../../src/solvers/power_integrity/peec/peec_solver.hpp)
- [reference_plane_antipad_mesh_input.cpp](../../../src/solvers/power_integrity/peec/reference_plane_antipad_mesh_input.cpp)
- [reference_plane_antipad_mesh_input.hpp](../../../src/solvers/power_integrity/peec/reference_plane_antipad_mesh_input.hpp)
- [sparse_magnetic_energy.cpp](../../../src/solvers/power_integrity/peec/sparse_magnetic_energy.cpp)
- [sparse_magnetic_energy.hpp](../../../src/solvers/power_integrity/peec/sparse_magnetic_energy.hpp)
- [via_transition_mesh_input.cpp](../../../src/solvers/power_integrity/peec/via_transition_mesh_input.cpp)
- [via_transition_mesh_input.hpp](../../../src/solvers/power_integrity/peec/via_transition_mesh_input.hpp)
- [volume_inductance.cpp](../../../src/solvers/power_integrity/peec/volume_inductance.cpp)
- [volume_inductance.hpp](../../../src/solvers/power_integrity/peec/volume_inductance.hpp)
- [volume_matrix.cpp](../../../src/solvers/power_integrity/peec/volume_matrix.cpp)
- [volume_matrix.hpp](../../../src/solvers/power_integrity/peec/volume_matrix.hpp)

### `src/solvers/signal_integrity/si`

[Subgroup guide](../../../src/solvers/signal_integrity/si/README.md)

- [ami_host_main.cpp](../../../src/solvers/signal_integrity/si/ami_host_main.cpp)
- [transition_pi_cdr.cpp](../../../src/solvers/signal_integrity/si/transition_pi_cdr.cpp)
- [transition_pi_cdr.hpp](../../../src/solvers/signal_integrity/si/transition_pi_cdr.hpp)

### `src/solvers/thermal_fluid/airflow`

[Subgroup guide](../../../src/solvers/thermal_fluid/airflow/README.md)

- [cavity.cpp](../../../src/solvers/thermal_fluid/airflow/cavity.cpp)
- [cavity.hpp](../../../src/solvers/thermal_fluid/airflow/cavity.hpp)
- [cht.cpp](../../../src/solvers/thermal_fluid/airflow/cht.cpp)
- [cht.hpp](../../../src/solvers/thermal_fluid/airflow/cht.hpp)
- [cht_main.cpp](../../../src/solvers/thermal_fluid/airflow/cht_main.cpp)
- [main.cpp](../../../src/solvers/thermal_fluid/airflow/main.cpp)

### `src/solvers/thermal_fluid/thermal`

[Subgroup guide](../../../src/solvers/thermal_fluid/thermal/README.md)

- [thermal_solver.cpp](../../../src/solvers/thermal_fluid/thermal/thermal_solver.cpp)
- [thermal_solver.hpp](../../../src/solvers/thermal_fluid/thermal/thermal_solver.hpp)
