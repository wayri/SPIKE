<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Solver mathematics and numerical methods

This is the central mathematical map of the implemented SPIKE solver families.
It connects equations, units, discrete operators, boundary conditions, solution
methods and acceptance evidence. Detailed derivations already maintained in
domain documents are linked rather than duplicated. Source links identify the
actual implementation; a method described here is not necessarily exposed by
every application route. Read [solver status](SOLVER_STATUS.md) for runtime and
qualification decisions, [the handbook](SOLVER_HANDBOOK.md) for interpretation,
and [research references](SOLVER_REFERENCES.md) for recorded method provenance.

Future numerical work follows the [method evidence policy](NUMERICAL_METHOD_EVIDENCE.md):
governing physics and subject-matter assumptions, independently authored
derivation, primary method references, validity/numerical analysis and executed
independent evidence. [Research candidates](MULTIPHYSICS_RESEARCH_FRONTIER.md)
are distinct from implemented mathematical coverage in this document.

This is a family-level reference, not a claim that every device stamp, empirical
coefficient or external engine algorithm has a complete derivation here. The
coverage and remaining documentation gaps are explicit below. The separate
private SPIKES generic FEM program is not part of this repository's implemented
product physics. Its verification-only handoff must remain distinct from the
public SPIKES circuit and equilibrium semiconductor kernels in `src/spikes`.

## Coverage and navigation

| Family | Mathematical coverage here | Detailed authority and current boundary |
| --- | --- | --- |
| Geometry and mesh | Predicates, topology, ownership and discretization prerequisites | [Geometry](#geometry-is-part-of-the-model); geometry admission is not field accuracy |
| Routed, zone and harness DC | Conductance assembly, terminals, conservation; RT0 probe | [DC](#dc-conduction-and-network-topology); operational approximate network versus experimental probe |
| PEEC 2.5D and finite-volume bases | R/L integrals, network equations, energy tests, BE transient | [PEEC](#peec-partial-elements-and-transient-pi); experimental quasi-static extraction |
| Electrostatics and dielectric AC | P1 tetrahedral weak form, Maxwell C, terminal reduction | [Capacitance](#electrostatics-dielectric-ac-and-pdn-reduction); retained finite-domain reference |
| Uniform/coupled SI and networks | Telegrapher equations, loss, scattering, graph elimination | [SI](#transmission-lines-and-network-composition); bounded quasi-TEM models |
| Waveforms, eyes, resonance | Convolution, statistics, masks, AR(2) decay | [Postprocessing](#waveforms-eyes-and-resonance); finite-record estimates |
| Circuit and switching | MNA, Newton, integration, equation devices, averaged SMPS | [Circuits](#circuit-mna-devices-and-switching); admitted device/language subsets |
| Thermal and electrothermal | FV and tetra P1, boundary integrals, storage, coupling | [Thermal](#thermal-conduction-and-electrothermal-feedback); separate mesh/model gates |
| Magnetic machines | Lumped dynamics, P1 nonlinear magnetics, eddy blocks, stress | [Magnetics](#magnetics-machines-and-actuators); reduced and experimental planar models |
| CFD and CHT | MAC projection, channel momentum/energy, external routes | [Flow](#fluid-flow-and-conjugate-heat-transfer); bounded native cavity/channel |
| EM fields and radiation | External Maxwell path, Huygens transform, RWG groundwork | [EM](#electromagnetic-fields-and-radiation); no native general full-wave/MoM solve |
| Semiconductor equilibrium | Poisson-Boltzmann residual, Jacobian and Gauss law | [TCAD](#semiconductor-equilibrium); equilibrium 1D only |
| Coupling and comparisons | Fixed-point defects, explicit source handoffs and recorded residuals | [Coupling](#coupled-studies-and-recorded-comparisons); no universal multiphysics solver |

## Conventions and acceptance

Unless a boundary explicitly says otherwise, equations use metres, seconds,
amperes, volts, kelvin, watts, ohms, henries and farads. PCB geometry often
arrives in mm and is converted by `1e-3`; area and volume conversions are
squared and cubed. Thermal temperature differences in K equal differences in
degrees C, but absolute radiation temperature must be K. Angular frequency is
`omega=2*pi*f`, not frequency in Hz. Magnetic B is T, H is A/m, conductivity
sigma is S/m, thermal conductivity k is W/(m K), heat capacity rho*cp is
J/(m^3 K), and volumetric heating q is W/m^3.

The symbol A is context dependent: network incidence, element area, magnetic
potential or a state matrix. Each section defines its use. Transpose is `.T`;
complex-conjugate transpose is `.H`. Ports require declared ordering, polarity,
reference impedance and reference plane. Sources, returns, contacts and
grounds are physical model inputs; disconnected components need their own
admitted boundary or gauge. A shared net label does not create a physical bond.

Three errors must be kept separate: the algebraic solve residual, discretization
error, and physical model error. Small residuals or exact conservation do not
bound the latter two. Mesh, timestep, finite-domain and bandwidth convergence
need separate studies. Test links below identify reproducible evidence owners;
they do not assert those tests were rerun when reading this document. Numerical
changes require the gates in [CONTRIBUTING](../CONTRIBUTING.md), including
knowledgeable human review before release.

## Geometry is part of the model

An imported conductor must retain net, layer, source identity, positive area,
thickness, holes and connectivity before any electrical coefficient is formed.
Polygon orientation uses the sign of a 2D cross product; signed area follows
the boundary cross-product sum. Exact-grid predicates decide topology without
substituting an engineering clearance for exact intersection. Constrained
triangulation preserves boundary segments; orientation, area and Euler checks
are geometry invariants, not solver convergence tests.

Owners: [planar topology](../src/geometry/planar_topology.cpp),
[constrained triangulation](../src/geometry/constrained_triangulation.cpp),
[hybrid DC solver](../python/spike_core/hybrid_dc_solver.py), and
[PCB volume compiler](../python/spike_core/pcb_volume_compiler.py).
See [native geometry foundation](CAD_NEUTRAL_NATIVE_MULTIPHYSICS_FOUNDATION.md),
[OCC conforming mesh](OCC_CONFORMING_PCB_MESH.md), and
[focused volume meshing](PCB_FOCUSED_VOLUME_MESHING.md).

Filled-zone contours and their cut/bridge encodings must be interpreted before
meshing. A zero-width traversal joining an outer ring to a hole is not a
finite-width insulating slot. Conversely, discarding a real hole changes current
paths and capacitance. The importer/geometry contract is authoritative for each
route; acceptance by one mesher does not establish acceptance by SI or openEMS.
See [meshing and version-specific diagnostics](MESHING_ENGINE.md) and the
[filled-plane DC regression](../tests/python/test_kicad_filled_plane_dc.py),
which checks imported hole area and keeps branches/result faces out of the void.
Terminal area, via barrel versus land, thermal reliefs, and geometric overlap
must survive transfer. These are prerequisites for all equations below.

## DC conduction and network topology

For a uniform branch of length l and cross-section S,
`R=l/(sigma*S)`, `I=(V_a-V_b)/R`, and `J=I/S`. A plated barrel uses its actual
annular conducting area rather than a solid drill cylinder. Explicit contact
and package resistances add series voltage drop. With node/branch incidence B,
the reduced nodal system is `B G B.T v=j`, where `G=diag(1/R)` and j is signed
current injection. Prescribed source voltages are eliminated into the RHS.
Loop studies pair load extraction with return injection and report supply
drop, return rise and differential loop drop separately.

Zone current spreading discretizes conductive copper into finite volumes.
Face conductance depends on conductivity, thickness, shared face width and
centre distance. This approximates `div(sigma grad V)=0`; insulated boundaries
have zero normal current. Terminal attachment and zone refinement can dominate
error. Never equate coordinate-nearest attachment with exact geometry binding.
See [DC scope and terminal contract](DC_SOLVER.md),
[implementation](../python/spike_core/hybrid_dc_solver.py), and
[analytical benchmarks](../python/spike_core/benchmarks.py).
Authored wires/harnesses use the same resistive laws with explicit pins,
wire lengths, conductor data and contacts; see [harness PI](HARNESS_PI.md).

The separate experimental [RT0 probe](../python/spike_core/peec_conforming_dc.py)
uses a conservative mixed discretization on triangles. For a CCW triangle
of area S and opposite vertex p_i, `w_i(x)=(x-p_i)/(2*S)` has unit integrated
outward flux. For sheet conductance `k=sigma*t`,
`M_ij=integral(w_i dot w_j)/k` is in ohms. Degree-two three-point quadrature is
exact for that quadratic integrand. Signed shared-edge currents q and constant
cell potentials u obey `M q-B.T u=0`, `B q=s`. Normal flux is single-valued and
cell KCL exact. Finite-area pad/via injections use conjugate area-weighted
potentials, not equipotential pad collapse. Diagonal resistance scaling and
sparse solves retain residual/energy rejection. This is not the registered AC
extractor or a resolved 3D contact. Evidence:
[conforming DC tests](../tests/python/test_peec_conforming_dc.py),
[iterative RT0 tests](../tests/python/test_peec_rt0_iterative.py), and
[basis blocker](validation/PEEC_CONFORMING_BASIS_BLOCKER.md).

## PEEC partial elements and transient PI

For current basis f_i normalized so its coefficient is branch current in A,
the quasi-static volume expressions are

```text
R_ij = integral_volume (f_i dot f_j)/sigma dV
L_ij = mu/(4*pi) integral_volume integral_volume
       (f_i(r) dot f_j(r'))/|r-r'| dV dV'
W_m = i.T L i / 2
```

Self and mutual terms must use the same basis. Rectangular volume basis current
density per ampere is direction/(width*thickness); axial via bases retain an
annular cross-section. Overlapping bases produce off-diagonal resistance as
well as inductance. The older filament approximation and rectangular self
formula are not interchangeable with a conforming volume current space.

Owners: [native PEEC](../src/peec/peec_solver.cpp),
[volume integral contract](../src/peec/volume_inductance.hpp),
[volume adapter](../python/spike_core/peec_volume_adapter.py),
[overlap R](../python/spike_core/peec_volume_resistance.py), and
[network assembly](../python/spike_core/peec_network.py).
Finite-volume quadrature records tolerance, resource exhaustion and a posteriori
error estimates; these are not certified bounds on an entire extracted matrix.
Retarded propagation/radiation and general proximity redistribution are absent.

With incidence A, branch impedance `Z=R(omega)+j*omega*L`, and nodal shunt
admittance Y, the frequency equations are `Z i-A.T v=0`, `A i+Y v=j_source`.
Port excitation and return topology determine which impedance is observed;
a diagonal partial L is not itself a loop inductance. The physical L must be
symmetric positive semidefinite to numerical tolerance. Negative-energy modes
fail; PSD projection, diagonal inflation and artificial eigenvalue floors must
not repair the geometry. Valid zero-energy topology modes are retained.
See [PEEC safety policy](PEEC_SAFETY_POLICY.md),
[native tests](../tests/test_peec.cpp),
[volume tests](../tests/test_volume_inductance.cpp), and
[energy admission tests](../tests/python/test_peec_energy_admission.py).

Geometry transient PI solves

```text
R i + L di/dt - A.T v = 0
A i + C dv/dt = j(t)
di/dt ~ (i_new-i_old)/dt; dv/dt ~ (v_new-v_old)/dt
```

Backward Euler gives an implicit linear block solve per step. DC resistance,
mutual L, voltage boundaries and current waveforms are retained; optional C is
distributed stackup shunt capacitance, not a general field-solved multiconductor
matrix. Initial operating point versus zero state, finite edge times and time
resolution change the answer. BE numerical damping is not physical loss.
[Transient PI](TRANSIENT_PI.md) records timestep, residual and memory gates;
[implementation](../python/spike_core/transient_peec.py) and
[tests](../tests/python/test_transient_peec.py) own the executable contract.

## Electrostatics, dielectric AC and PDN reduction

The retained 3D dielectric reference uses affine tetrahedral shape functions N
for `-div(epsilon grad phi)=0`. With gradient rows B and tetra volume V,
`K_e=V*B*epsilon*B.T` has units F. Prescribed electrode potentials are Dirichlet
data; other outer surfaces have zero normal displacement, not an infinite
open boundary. Unit-electrode solutions assembled as columns P give
`C=P.T K P`. Reactions are electrode charge in C and `U=Vports.T C Vports/2`
equals integrated field energy. Reference choice and floating conductor
conditions must be explicit.

See [electrostatic source derivation](../python/spike_core/pdn_electrostatic.py)
and [tests](../tests/python/test_pdn_electrostatic.py). Ideal parallel plates
provide an affine oracle, not general PCB fringing qualification. This retained
tetra route is separate from the approximate PEEC panel potential coefficients
and stackup shunts; their validity cannot be transferred by relabeling C.

[Dielectric AC](../python/spike_core/pdn_dielectric_ac.py) and
[admittance reduction](../python/spike_core/pdn_admittance_reduction.py) retain
explicit frequency/material/terminal contracts. The dielectric operator uses
RMS `exp(+j*omega*t)` phasors and
`gamma=sigma*I+omega*tan(delta)*epsilon+j*omega*epsilon` in
`div(gamma grad phi)=0`. Unit-electrode fields P give `Y=P.H K P`;
the field integral of `E.H gamma E` equals `V.H I`, with no peak-phasor factor
of one half. Conventional complex power is its conjugate. Spatially varying
lossy fields are solved afresh at each frequency.
For a partition into external e and internal i unknowns with declared internal
load admittance Yload, elimination has the Schur form
`Yred=Yee-Yei solve(Yii+Yload,Yie)`. Singular internal systems and incompatible
constraints must not be hidden by an explicit inverse or arbitrary grounding.
Evidence: [dielectric tests](../tests/python/test_pdn_dielectric_ac.py) and
[reduction tests](../tests/python/test_pdn_admittance_reduction.py).

A declared capacitor branch has series
`Zcap=ESR+j*omega*ESL+1/(j*omega*C)` away from DC. Candidate PDN assessment
combines admitted networks and compares impedance to an explicit target, often
`Ztarget=allowed_voltage_change/current_step`. Frequency sweeps and candidate
ranking do not solve placement fields or predict bias/temperature-dependent
parts unless those models are supplied. See [PDN implementation](../python/spike_core/pdn.py),
[network owner](../python/spike_core/pdn_network.py),
[capacitor placement](CAPACITOR_PLACEMENT.md), and
[PDN tests](../tests/python/test_pdn.py).

## Transmission lines and network composition

For per-unit-length R [ohm/m], L [H/m], G [S/m], C [F/m],

```text
dV/dz = -(R+j*omega*L) I = -Z I
dI/dz = -(G+j*omega*C) V = -Y V
gamma = sqrt(Z*Y); Zc = sqrt(Z/Y)             (scalar line)
[V(l); I(l)] = exp(l * [[0,-Z],[-Y,0]]) [V(0); I(0)]
```

The scalar line admits a uniform planar approximation with bounded
Hammerstad/Jensen capacitance and propagation-derived L. The pair uses a sparse
2D electrostatic cross-section solve for vacuum Maxwell C0, then
`C=epsilon_r*C0`, `L=inv(C0)/c0^2` in the homogeneous quasi-TEM approximation.
The lower reference boundary is grounded; conductor potentials are prescribed
and finite outer boundaries are natural. Three cross-section refinement levels
record change but do not automatically satisfy a convergence gate. The state
transition becomes a two- or four-port S matrix with declared positive real
reference impedances. Piecewise planar cascades omit bend discontinuities.

Owners: [single channel](../python/spike_core/si_channel.py),
[coupled channel](../python/spike_core/si_coupled_channel.py),
[geometry derivation and admission](GEOMETRY_DERIVED_SI_CHANNEL.md), and
[channel tests](../tests/python/test_si_channel.py).

Conductor skin depth is `delta=sqrt(2/(omega*mu*sigma))`. The isolated symmetric
slab diffusion model uses `kdiff^2=j*omega*mu*sigma` and
`Zinternal_per_m=kdiff*coth(kdiff*t/2)/(2*sigma*w)` for thickness t and width w.
Its DC limits are `R_per_m=1/(sigma*w*t)` and `Linternal_per_m=mu*t/(12*w)`.
Empirical RMS roughness multiplies real resistance by
`1+(2/pi)*atan(1.4*(RMS/delta)^2)`, leaving smooth-conductor reactance unchanged.
Neither represents general proximity current
redistribution, return-plane loss, or arbitrary broadband material dispersion.
External-only magnetic L must not double count internal reactance. Exact
controls and independent checks are in [high-frequency losses](HIGH_FREQUENCY_LOSSES.md).

For S partitioned into retained and connected ports, with connection matrix Cw,
`Seff=See+Sei solve(I-Cw*Sii,Cw*Sie)`. This follows from internal incident waves
equal to Cw times internal outgoing waves. Use a solve with conditioning checks;
multiple reflections are included, but no connector or return physics is
created. [Network graph](../python/spike_core/si_network_graph.py) and
[tests](../tests/python/test_si_network_graph.py) own the ordering/connection rules.
[S-parameter conversion](../python/spike_core/sparameters.py) owns wave
normalization; finite-band passivity screens apply only to that convention.

## Waveforms, eyes and resonance

The bounded [shunt-capacitive source/load extension](CAPACITIVE_NETWORK_TRANSIENT.md)
uses `Isrc=(Vs-V)/R=Inet+Csh*dV/dt` and `v=V/sqrt(Z0)=a+b` to form mixed
capacitor-voltage/resistor wave rows. It propagates the full stable fitted LTI
state with exact PWL exponentials. Physical supplied resistor heating is
`R Isrc²`, and capacitor storage is `.5 Csh V²`; the source/network current split
is essential to their boundary power balance. The linked derivation and reviewed
primary KCL/parallel-RLC/energy sources define the scope and limitations.

The bounded [series-inductive source/load extension](INDUCTIVE_NETWORK_TRANSIENT.md)
uses `Vs=V+R I+L dI/dt`, mixed resistive/current wave closure and normalized
inductor-current states `q=sqrt(Z0) I`. Its complete stable connected LTI system
is propagated with augmented PWL exponentials. Supplied boundary losses `R I²`
and storage `.5 L I²` are physical component observables; fitted-network state
energy requires a separately qualified realization. The linked derivation records
primary KVL/RLC references and singular/marginal/descriptor limitations.

The loaded SI workflow combines a sampled channel with explicit source/load
models and LTI convolution `y=h*x`. DC coverage, frequency spacing, bandwidth,
windowing and time-grid policies affect the reconstructed waveform. Imported
S data are measurements or network models, not geometry extraction. An IBIS
DC-slope/ramp reduction is not the full IBIS switching or AMI model.
See [SI workflow](SI_WORKFLOW.md) and
[workflow owner](../python/spike_core/si_workflow.py).

Eye samples fold by unit interval and declared phase. PAM4 thresholds, training
DFE and Gaussian BER proxies describe a finite record; tail extrapolation is
not measured BER. Clock recovery has its own bounded implementation in
[clock recovery](SI_CLOCK_RECOVERY.md). Polygon masks test both samples and
segment crossings, including boundaries; partial mask support is not protocol
compliance. See [eye masks](SI_EYE_MASK_TESTING.md) and
[PAM4 owner](../python/spike_core/si_pam4_eye.py).

For an isolated ringdown `u(t)=exp(-alpha*t)*cos(2*pi*f*t+phase)`,
`Q=pi*f/alpha`. A fitted AR(2) recurrence has complex conjugate roots whose
radius gives decay and angle gives sampled frequency. Reconstruction and fit
screens are essential; aliasing, multimode mixtures and forcing violate the
single free-decay interpretation. Half-power/RLC fitting is a separate network
estimate. [Resonance](../python/spike_core/si_resonance.py),
[ringdown](../python/spike_core/si_ringdown.py) and
[ringdown tests](../tests/python/test_si_ringdown.py) retain these boundaries.

## Circuit MNA, devices and switching

Modified nodal analysis augments node voltages with currents needed for ideal
voltage sources and inductive constraints. The general discrete task is
`F(x,t)+dQ(x,t)/dt=0`; linear DC reduces to `K x=b`. KCL uses device current
stamps and source constraints. Newton solves `J(x_k)*delta=-F(x_k)` and must
pass the applicable residual and update checks. A singular circuit is not made
physical by hiding a missing reference. AC linearization uses conductance and
charge Jacobians at the admitted operating point, not a nonlinear transient.

Owners: [native MNA boundary](../python/spike_core/native_mna.py),
[C++ DC core](../src/spikes/dc_solver.cpp), and
[transient core](../src/spikes/transient_solver.cpp).
[Passive model equations](SPIKES_PASSIVE_MODEL_EQUATIONS.md),
[equation devices](SPIKES_EQUATION_DEVICES.md), and
[lumped physics parts](SPIKES_LUMPED_PHYSICS_PARTS.md) document supported
compositions. Paired current/charge equations must retain charge dynamics;
constant package R/L/C do not provide distributed package fields. Generic
device models, sourced catalog identity and manufacturer qualification are
different claims. External ngspice runs remain explicit external execution.

The native transient core admits BE, BDF2 and trapezoidal/hybrid routes under
their controls. For a linear capacitor, stable history-difference forms include
`i_BE=C*(v-vn)/h` and `i_TR=2*C*(v-vn)/h-i_previous`. BDF coefficients satisfying
`a0+a1+a2=0` give `C/h*(a0*(v-vn)+a2*(vprev-vn))`. Inductor flux uses the
corresponding current difference. Adaptive order-two versus BE difference is
an error-control defect, not a rigorous universal LTE bound. Rejected Newton
or LTE steps restore histories; source corners restart history. Symbolic sparse
ordering reuse and numeric-factor reuse have separate validity conditions.
See [adaptive derivation and evidence](SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md)
and [transient controls](INTERNAL_SPICE_TRANSIENT_CONTROLS.md). Mixed-unit
global Newton scaling and device-specific histories retain documented limits.

Ideal CCM SMPS stability is a supplied-parameter averaged model. With
`x=[i,v]`, `A=[[0,-k/L],[k/C,-1/(R*C)]]` and duty column B,
`Gvd=(B_v*s+k*B_i/C)/(s^2+s/(R*C)+k^2/(L*C))`.
Buck uses k=1; boost/buck-boost use k=1-d; flyback uses k=(1-d)/(Ns/Np).
Topology-specific B, DC operating points, right-half-plane zeros and ripple
screens are fully derived in [SMPS stability](SPIKES_SMPS_STABILITY.md).
The compensator is `K/s*product(1+s/wz)/product(1+s/wp)` and closed-loop poles
come from the uncancelled denominator-plus-numerator polynomial of the return
ratio. All resolved crossings, root residuals and unresolved near-axis poles
matter; one phase margin does not certify stability. This is not automatic
switching-circuit linearization or hardware stability qualification.

## Thermal conduction and electrothermal feedback

All solid routes start from `rho*cp*dT/dt=div(k grad T)+q`. Fourier heat flux is
`-k grad T`. Thermal boundaries may prescribe T, inward heat flux, convection
`h*(T-Tambient)` outward, or ambient radiation
`epsilon_surface*sigma_SB*(T^4-Tambient^4)` outward. Radiation emissivity is not
dielectric permittivity. Contact conductance and heating ownership are explicit.

### Structured and layered finite volumes

For neighboring cells with distances d1,d2 to their shared face and face area S,
`Gface=S/(d1/k1+d2/k2)` in W/K. Each internal exchange appears with opposite
sign in the two balances. Backward Euler adds cell capacity `rho*cp*V/dt` to
the diagonal and previous-temperature storage to the RHS. Layered boards retain
physical stack layers and copper occupancy; local refinement must not silently
change the copper material sampling. Package/case/junction nodes and supplied
thermal resistances are reduced models, not reconstructed die fields.

Owners: [structured solid](../python/spike_core/structured_solid_thermal.py),
[layered board](../python/spike_core/layered_board_thermal.py),
[component network](../python/spike_core/component_thermal.py).
See [thermal workflow](THERMAL_WORKFLOW.md),
[component thermal](COMPONENT_THERMAL.md),
[thermal accuracy checks](THERMAL_ACCURACY_CHECKS.md), and
[structured tests](../tests/python/test_structured_solid_thermal.py).

### Retained tetrahedral fields

Affine P1 tetrahedra give `K_e=V*B*k*B.T`, uniform load `f_e=V*q/4`, and
triangular face mass `Mface=S*(I+11.T)/12`. Convection adds `h*Mface`;
matched contact adds `h*[[Mface,-Mface],[-Mface,Mface]]` across paired nodes.
Dirichlet elimination and positive anchoring remove the thermal constant mode.
Sparse CG/conditioning and actual residual checks govern the admitted linear
system; nonlinear ambient radiation has its separate iteration and energy gates.
[Tetra thermal source](../python/spike_core/assembly_tetra_thermal.py) contains
the independent weak-form derivation; [tests](../tests/python/test_assembly_tetra_thermal.py)
cover slab/manufactured and boundary cases. Transient storage and accepted-state
stepping are separately specified in [assembly transient](ASSEMBLY_THERMAL_TRANSIENT.md)
and [retained step](../python/spike_core/retained_thermal_step.py).

Retained electrical tetrahedra use the analogous conductivity weak form for
potential, with `J=-sigma grad V`, bulk `q=J dot E`, and explicit matched
resistive bonds. Temperature feedback uses
`sigma(T)=sigma_ref/(1+alpha*(T-Tref))` within a declared valid envelope.
Fixed-point electrothermal convergence checks unrelaxed temperature defect and
electrical-power change; relaxation must not conceal failure. Every heat source
is deposited once and contact loss splits between declared sides.
See [assembly electrothermal derivation](ASSEMBLY_ELECTROTHERMAL.md),
[volume circuit coupling](MULTIBOARD_VOLUME_ELECTROTHERMAL.md),
[PWM coupling](PWM_VOLUME_ELECTROTHERMAL.md), and
[coupled tests](../tests/python/test_assembly_electrothermal.py).

Device heat may be `sum(Irms^2*R)`, interpolated conduction/switching tables,
or exactly integrated piecewise-linear terminal power minus stored-energy
change. Switching energy times event rate is average watts. Stored electrical
energy and numerical damping must not be counted as dissipative device heat.
Nonoverlap, range, nonnegative dissipation and conservation checks are required.
No loss table establishes a universal semiconductor model.

Optional [CalculiX thermal](CALCULIX_THERMAL.md) executes an external FEM engine
under its own case/result contract. Its internal iteration diagnostics are not
invented by SPIKE. Agreement on one slab does not qualify arbitrary assembly
geometry, cooling, contact physics or transient coupling.

## Magnetics, machines and actuators

The reduced PM machine satisfies
`L di/dt=V-R*i-K*omega`, `J domega/dt=K*i+torque_external-b*omega`,
`dtheta/dt=omega`. Reciprocal K is N m/A = V s/rad. Generator mode includes
explicit load resistance and negative terminal power under the stated sign
convention. Implicit midpoint in energy-scaled coordinates preserves the
discrete power identity; timestep convergence is still required.
The single-path electromagnet has
`reluctance=lcore/(mu0*mur*Acore)+gap/(mu0*Agap)`,
`flux=N*I/reluctance`, `L=N^2/reluctance`, and
`Fclosing=flux^2/(2*mu0*Agap)`. These assume linear material and one uniform gap.
See [machine equations](EM_MACHINES.md),
[owner](../python/spike_core/em_machines.py), and
[tests](../tests/python/test_em_machines.py).

Planar magnetic P1 FEM instead solves Az [Wb/m],
`B=(partial_y Az,-partial_x Az)`, and
`integral curl(v) dot H dS=integral v*Jz dS`.
For triangle curl matrix C, residual is `sum(area*C.T*H)-f` and tangent is
`sum(area*C.T*D*C)`, `D=dH/dB`. Linear remanence uses `H=(B-Br)/mu`.
Monotone B-H data use radial constitutive H and the exact piecewise-linear
energy integral. Newton with a potential-decrease line search must satisfy the
free-node residual criterion; extrapolation beyond supplied B-H data is rejected.
Each connected component needs a prescribed Az/gauge and finite air-box studies
need independent domain-size convergence.

Stationary eddy currents introduce per-region axial offsets Ez so
`E_z=-dAz/dt+Ez` and each isolated axial region has zero integrated induced
current. With conductivity mass M, coupling C and region matrix S, the BE
Newton block is `[K+M/dt,-C/dt; -C.T/dt,S/dt]`.
Exact P1 Joule integration and the balance
`input_work=Delta_magnetic_energy+dt*Joule_power+BE_dissipation`
distinguish heat from numerical damping. Complete tangents, quadrature, source
work conventions, nonlinear tolerances and oracles are in
[magnetic FEM](MAGNETIC_FEM.md),
[source](../python/spike_core/magnetic_fem.py), and
[tests](../tests/python/test_magnetic_fem.py).

Closed air contours integrate vacuum Maxwell stress
`T=(B B.T-|B|^2 I/2)/mu0`; force is stress traction integrated with stack depth,
and torque includes the position cross force arm. Contours must stay in
admitted air elements. Quasi-static mechanics uses bounded damped symplectic
Euler with a new magnetostatic solution at each position. Stationary eddy/thermal
coupling transfers actual Joule watts, but cannot be combined with motion:
motional `v cross B` and conservative remesh-state transfer are absent.
See [machine studies](MAGNETIC_MACHINE_STUDIES.md),
[magnetic thermal](MAGNETIC_THERMAL.md), and
[study tests](../tests/python/test_magnetic_machine_study.py).

## Fluid flow and conjugate heat transfer

The native square-cavity kernel solves nondimensional incompressible
`div u=0`, `du/dt=-div(u tensor u)-grad p+(1/Re)*Laplacian u`.
Reference scales are length L, velocity U, time L/U and pressure rho*U^2;
dynamic viscosity is rho*U*L/Re. MAC staggering places p at cell centres and
velocities on faces. Conservative centered flux differences and second
differences approximate convection/diffusion. Ghost velocities impose no slip;
the lid moves and other walls are stationary.

Incremental projection predicts ustar then solves
`(-D G)*phi=-D*ustar/dt`, updates `u=ustar-dt*G*phi`, `p=p+phi`.
Wall corrections are homogeneous Neumann; pressure has zero mean. CG works in
the zero-mean subspace and rejects incompatible forcing. The timestep is the
minimum of explicit diffusive and advective restrictions. Ten consecutive
accepted velocity-change rates and a divergence gate establish steady
convergence, not independent accuracy. Full derivation, actual residual units,
grid/time bounds and cosine eigenmode/refinement oracles are in
[native CFD](NATIVE_CFD.md); owners are [C++ airflow](../src/airflow/)
and [process adapter](../python/spike_core/native_airflow.py).

The separate developed plane-channel model solves no-slip momentum driven by
constant pressure gradient, then finite-volume conjugate energy across fluid
and two walls. The continuum oracle is parabolic velocity;
`rho*cp*u*dT/dx=div(k grad T)+viscous_heat` under steady developed assumptions.
Shared solid/fluid face conductance, axial conduction and upwind enthalpy
transport preserve energy. Width scales an extruded 2D flow; there are no
entrance momentum, sidewall, turbulence or fan fields. See
[bounded CHT derivation](BOUNDED_CHT_AND_RADIATION.md) and
[channel owner](../python/spike_core/laminar_channel_cht.py).

[SU2 airflow](SU2_AIRFLOW.md), [SU2 CHT](SU2_CHT.md), and
[fan/CHT qualification](FAN_CHT_QUALIFICATION.md) describe distinct external
adapters and reference workflows. External case translation does not make the
native cavity a thermal/enclosure solver. Runtime version, turbulence/buoyancy
model, boundaries and convergence must accompany external results; imported
public measurements alone do not establish a matching prediction.

## Electromagnetic fields and radiation

The optional openEMS route delegates Maxwell FDTD to an installed engine.
The continuum relations include `curl E=-dB/dt`,
`curl H=J+dD/dt`, with declared constitutive materials and excitation ports.
Grid resolution, smallest features, time termination and absorbing boundaries
are independent accuracy controls. SPIKE owns geometry, port and result
admission, not a newly implemented FDTD kernel. With multiple independent
excitations, incident/reflected wave columns satisfy `S*A=B`; normalization
must solve this system instead of dividing each column by only one amplitude.
See [retained assembly EM](RETAINED_ASSEMBLY_EM.md),
[independent retained reference](RETAINED_EM_INDEPENDENT_REFERENCE.md),
[normalization owner](../python/spike_core/multi_excitation_network.py), and
[openEMS reference record](validation/OPENEMS_REFERENCE_VALIDATION.md).

The owned Huygens postprocessor consumes supplied E/H on a closed six-face box.
For peak phasors `exp(+i*omega*t)`, equivalent surface currents are
`Js=n cross H`, `Ms=-n cross E`; midpoint integrals produce amplitude F with
`Efar=F(rhat)*exp(-i*k*r)/r`. Homogeneous lossless exterior, enclosed sources,
field provenance and no PML intersection are required. Angular samples alone
do not establish integrated power or directivity. The exact implementation,
dipole oracle and quadrature convergence are linked from
[closed-box radiation](BOUNDED_CHT_AND_RADIATION.md) and
[Huygens owner](../python/spike_core/huygens_far_field.py).

Surface MoM groundwork includes oriented RWG triangular bases, singular Green
moments and supplied-current far-field/RCS postprocessing. The basis is piecewise
linear with normal-current continuity across its interior edge; singular
integration uses independently derived transformations. These operators do not
assemble/solve the EFIE or determine scatterer currents. See
[surface basis](../python/spike_core/mom_surface_basis.py),
[operator evidence](validation/MOM_REFERENCE_OPERATORS_20260930.md), and
[recorded mathematical lineage](SOLVER_REFERENCES.md#r17---surface-em-reference-operators).
Native `spike.mom_surface` and general `spike.fullwave_3d` remain unavailable.
Elmer discovery and sparseLizard case preparation are not solved PCB fields.

## Semiconductor equilibrium

The native 1D equilibrium Poisson-Boltzmann kernel defines
`Vt=kB*T/q`, `u=phi/Vt`, `n=ni*exp(u)`, `p=ni*exp(-u)`,
`rho=q*(p-n+ND-NA)` and solves `-d(epsilon*dphi/dx)/dx=rho`.
Quasineutral contacts use `u=asinh((ND-NA)/(2*ni))`.
For spacing h, `Ns=max(ni,max(abs(ND-NA)))` and
`a=epsilon*Vt/(q*Ns*h^2)`, the finite-volume residual is
`F_i=a*(2*u_i-u_left-u_right)+(n_i-p_i-(ND-NA)_i)/Ns`.
The Newton tridiagonal has diagonal `2*a+(n+p)/Ns` and off-diagonal `-a`.
Checked O(N) elimination and finite residual-decreasing backtracking retain
explicit failure. Face `E=-(phi_right-phi_left)/h` gives discrete Gauss balance.

Uniform homogeneous material, constant T/ni, full ionization, nondegenerate
Boltzmann carriers and one Fermi level are assumptions. There is no biased
transport, continuity equation, heterointerface or process evolution. Complete
conditioning bounds, manufactured solution and second-order field/potential
refinement are in [TCAD equilibrium](SPIKES_TCAD_EQUILIBRIUM.md), with
[C++ owner](../src/spikes/tcad_equilibrium.cpp). Circuit PDK models are separate.

## Coupled studies and recorded comparisons

Coupling exchanges explicitly declared variables between existing models.
Fixed-point iteration `x_next=F(x)` with optional relaxation must check the
unrelaxed defect `F(x)-x`; small relaxed updates alone are insufficient.
Prescribed heat versus solved dissipation, averaged versus instantaneous power,
and one-way versus iterated feedback must remain visible. See
[field/circuit owner](../python/spike_core/field_circuit_cosim.py),
[staged PEEC/ngspice](PEEC_NGSPICE_HYBRID.md),
[scalar co-simulation and digital twin](COSIMULATION_DIGITAL_TWIN.md), and
[tests](../tests/python/test_cosimulation.py).

Recorded twin comparison computes residuals between supplied observations and
predictions under declared alignment/units. It does not identify a physical
model automatically or establish measurement traceability. Reduced prescribed
current battery models, offline MOSFET curve fitting, passive model synthesis
and waveform reductions are ancillary numerical models, documented in
[battery workflow](SPIKES_POWER_BATTERY_WORKFLOW.md),
[sourced-parts workbench](SPIKES_SOURCED_PARTS_WORKBENCH.md),
[passive equations](SPIKES_PASSIVE_MODEL_EQUATIONS.md), and
[recorded-run analysis](SPIKES_ANALYSIS_PLOTS.md). They must not be promoted to
native coupled field or universally qualified component solvers.

## Remaining derivation and validation work

This map covers the implemented families and identifies their mathematical
owners. It does not close the following gaps:

- A complete stamp-by-stamp reference for every native nonlinear/behavioral
  circuit device, all limiting rules and all solver scaling policies remains
  distributed across source, device documents and tests.
- The exact primary edition/section for empirical Hammerstad/Jensen relations
  and historical provenance for some original MNA/thermal work remains open in
  [the reference ledger](SOLVER_REFERENCES.md). Equations must not be assigned
  invented historical citations.
- General conforming PEEC current spaces, convergent capacitance with arbitrary
  via/antipad geometry, proximity effects and broad independent/measured PCB
  correlation remain numerical capability gates, not documentation tasks alone.
- External engines' complete numerical formulations belong to their pinned
  authoritative manuals. This repository documents the translated problem and
  admitted output, not every upstream algorithm or privately developed kernel.
- Domain documents contain the detailed supported limits and historical checks;
  a family overview cannot replace current source-specific tolerances, actual
  runtime manifests, fixture hashes, mesh/time refinement or human review.

For a new method, add its governing and discrete equations, units/signs,
boundary/gauge policy, nonlinear/linear solution and conditioning checks,
conservation identity, independent oracle and convergence study, source/test
links, provenance, and remaining physical limits here or in a linked domain
derivation. Update [solver status](SOLVER_STATUS.md) only when the required
evidence supports a capability change.
