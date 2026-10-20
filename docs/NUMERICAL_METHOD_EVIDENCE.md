<!-- SPDX-License-Identifier: Apache-2.0 -->
# Numerical method evidence policy

The [native particle reference](validation/NATIVE_PARTICLE_REFERENCE_20261021.md)
derives relativistic kinematics, signed electrostatic work, dilute hard-sphere
gas statistics and a distinct stationary-target beam attenuation model.
It records SI constants, separate applicability limits and analytical oracles;
it does not establish charged trajectories, PSF, Brownian, dense-fluid or
SEM/TEM capability. See the [requested development scope](CHARGED_PARTICLE_VACUUM_PLAN.md).

The [native planar optics reference](validation/NATIVE_OPTICS_REFERENCE_20261021.md)
derives fixed-convention E/H continuity, Poynting entry power, depth absorption
and ideal unitary coherent ports independently. Its Release-active analytical
checks do not qualify a material dataset, spatial instrument, emissivity model
or spectral band. The [development plan](OPTICS_PHOTONICS_MATERIALS_PLAN.md)
preserves separate research, data-admission and release gates.

The [annular contact/port record](validation/PI01_ANNULAR_CONTACT_20261021.md)
links independently derived cylindrical RT0 conduction and passive circuit
coupling to reviewed primary foundations, units, quadrature/condition limits,
independent continuum/nodal oracles and executed source-bound evidence. Native
source geometry authentication remains separate from supplied electrode and
material assumptions. All results remain experimental; full PI01-S02 and human
numerical release review stay open.

[Part operating-limit reports](PART_LIMITS.md) use independently authored decimal
comparison and declared reference-to-bound allowance ratios. They do not add a
physics solver, manufacturer rating law or qualification claim. The documented
SI temperature-interval foundation, offset-invariant derivation and independent
scalar/boundary/coverage oracles remain distinct from pending human review.

The [3-D land reference](DC_LAND_TRANSITION.md) derives explicit Cartesian face
bases, exact Ohmic mass, gauge-inclusive conservation and conjugate patch work
from reviewed primary conduction/separation foundations. Its
[verification](validation/PI01_LAND_TRANSITION_20261021.md) retains independent
harmonic fields, SI Gauss integration, cosine-series continuum refinement and
arithmetic/forgery counterexamples. This qualifies a bounded mathematical
reference, not automatic annular/board physics or physical measurements.

The [tetrahedral CAD/open-boundary record](validation/CFD_CAD_OPEN_BOUNDARY_20261021.md)
links independently derived geometry/robust predicates, CR/P0 creeping flow,
and RT0/P0 sensible energy. Actual STEP examples exposed and repaired a rigid
placement/analytic-volume defect; integrated energy qualification is recorded
separately from the mathematical tests. These are bounded in-process research
APIs, not qualified engineering turbulence or turbulent CHT. The
[workflow](CFD_TETRA_WORKFLOW.md) retains prerequisite and transferred
circuit/thermal/airflow work explicitly.

The [PI01 geometry/ownership increment](validation/PI01_GEOMETRY_OWNERSHIP_20261021.md)
records reviewed precision-noding API semantics, independently authored topology
and uncertainty admission, and annular axial conservation/Ohm/Joule derivations.
Clipped gap resistance is checked by a fresh reduced DC solve; old currents are
never relabeled. Land transitions and whole-board density remain unresolved.

The [finite-contact DC benchmark](PI_FINITE_CONTACT_BENCHMARK.md) independently
derives conserved sheet current, area-average terminal resistance and integrated
Joule work from reviewed steady conduction and mixed-flux foundations. Its
[execution record](validation/PI01_FINITE_CONTACT_20261021.md) retains fixed
refinement/error gates, raw ledgers and independent adversarial review. It tests
existing experimental kernels; rotated polygon overlays and board qualification
remain open.

The [coupled mean/SA research record](validation/ENCLOSURE_RANS_RESEARCH_20261021.md)
requires both equations at the same accepted velocity/pressure and updated
closure, preserving molecular-Reynolds admission. Its independent continuum
oracle is supplemented by polynomial/complex-step/covariance checks. The
[field-analysis record](validation/ENCLOSURE_FLOW_ANALYSIS_20261021.md) derives
RT0 normal-flux preservation and exact cell-local traces; these interrogate
supplied fields, not the physical validity of a source solver. The
[21 October review](validation/CFD_CHT_RESEARCH_REVIEW_20261021.md) records recent
journal/preprint candidates separately from adopted methods.

The [symmetric-stress record](validation/ENCLOSURE_SYMMETRIC_STRESS_20261020.md)
derives a positive strain-energy operator with off-component coupling and an
independent wrong-scalar-diffusion control. Its coarse quadratic order failure
is retained separately from the finer asymptotic study. The
[SA-noft2 record](validation/ENCLOSURE_SA_TRANSPORT_20261020.md) specifies the
exact NASA variant/guard and nonlinear fixed-velocity transport balance. The
[rotating-frame record](validation/ENCLOSURE_ROTATING_FRAME_20261020.md) derives
weighted work-free Coriolis coupling and stable centrifugal gauge recovery.
These are research prerequisites, not coupled turbulence or propeller validation;
their [workflow](ENCLOSURE_FLOW_RESEARCH.md) retains those exclusions.

The [refined obstacle momentum ledger](validation/ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md)
derives integrated nonuniform primal/dual fluxes, the pressure adjoint and
weighted kinetic balance from precisely reviewed Veldman sections. The
[v2 execution record](validation/ENCLOSURE_CHT_V2_VALIDATION_20261020.md) retains
independent re-entrant convergence, source-bound coupled results and repaired
dimensional-underflow/derived-NaN counterexamples. Momentum is actually re-solved
after tensor cuts; confined AMR, turbulence and rotating blades remain open.

The [3-D enclosure CHT record](validation/ENCLOSURE_CHT_METHOD_20261020.md)
derives shared sensible-energy fluxes, backward-Euler storage and a positive
constant-vector conditioning diagnostic. It links separately derived staggered
inertial momentum and conservative nested thermal transfer, exact reviewed
source/version scopes, executed mathematical checks and two repaired accuracy
counterexamples. Thermal refinement is not local momentum AMR. Turbulence,
rotors, physical correlation and human numerical release review remain open.

The 20 October 2026 [native CHT evidence](validation/NATIVE_CHT_METHOD_20261020.md) records the
exact DOE/Fourier, NIST finite-volume/upwind and NASA conservation/refinement
sources reviewed, independent discrete derivation, SI scaling, conditioning,
actual native tests and remaining physical limits. The
[surface-exchange record](COUPLED_SURFACE_EXCHANGE.md) derives conservative
overlap loads and their adjoint reverse map, with precise primary-reference
review scope, units/signs, cancellation and representability policy.
Independent review found and the implementation fixed a tiny-area intermediate
underflow; exact counterexamples and overflow/cancellation controls pass.
Actual worker/CLI, malformed-result, interface energy and field-forgery tests
remain distinct from physical validation. All these capabilities remain
experimental and require knowledgeable human numerical review before release.

The 20 October 2026
[owned peripheral timing record](validation/NATIVE_PERIPHERAL_TIMING_20261020.md)
records the reviewed timer/PWM, SPI and I2C sources; independent `ARR+1`,
mode-0 edge and open-drain nine-clock formulations; exact integer-nanosecond
admission; and the causal receiver rule. Timed receivers use the accepted
electrical left limit before event outputs change. Native tests and a bounded
four-test live STM32F407 adapter run establish only the declared fixed-clock,
single-byte polled subset. They do not qualify vendor pads, RCC/reset/IRQ/DMA,
cycle accuracy, whole-protocol compliance or physical SI/PI. See
[ADR 0119](adr/0119-owned-native-peripheral-mmio-and-pads.md); knowledgeable
human numerical and firmware review remains required.

Applies to future physics-affecting implementation and changes across all SPIKE
domains, including compact models, material laws, coupling, postprocessing,
surrogates and acceleration. This implements the user's requirement for
established mathematics/physics, subject knowledge, explicit references and
carefully evaluated frontier research. Existing provenance/validation gaps remain
open; this policy does not retroactively qualify or invent lineage for old code.

Use the [method evidence template](templates/numerical-method-evidence.md),
[solver mathematics map](SOLVER_MATHEMATICS.md),
[reference ledger](SOLVER_REFERENCES.md) and
[clean-room policy](RESEARCH_AND_CLEAN_ROOM_ENGINEERING.md).

## Required chain from claim to evidence

Every numerical feature/change must link:

1. **Physical question and observable.** Domain, supported scales/regimes,
   dimensions, units, frames, geometry/material assumptions and intended outputs.
2. **Governing mathematics and primary references.** Conservation/constitutive
   equations, initial/boundary/interface conditions, approximations and a source
   with author/publisher, title, year/revision, DOI/official URL and reviewed
   equation/section/page. Original derivations still cite their relevant physical
   and mathematical foundations. Distinguish an abstract/scope check from actual
   method/full-text review; unavailable details stay unresolved.
3. **Independent formulation.** Derive strong/weak/discrete forms or compact-model
   equations in project notation, including tensor/shear/sign conventions,
   nondimensionalization/scales, conserved energy/work/charge and dissipation.
   Explain why the method fits the physical regime and what is omitted.
4. **Numerical analysis.** State spaces/operators, nullspaces/constraints,
   nonlinear tangents, conditioning/scaling, time/mesh/frequency controls,
   stability/convergence assumptions, positivity/passivity where applicable,
   stopping tolerances and resource/failure/cancellation limits.
5. **Executable verification.** Independent analytical/manufactured/oracle cases,
   invariant/unit/frame checks, refinement and meaningful adversarial/rejection
   controls. Set observable-specific tolerances before accepting results.
   Tests that merely re-execute the implementation's own formula are insufficient.
6. **Physical validation and uncertainty.** Admitted independent measurements,
   calibration/held-out separation, geometry/load/material matching, measurement
   uncertainty, model-form limits and discrepancy. Synthetic correctness alone
   cannot establish physical predictive accuracy or life qualification.
7. **Traceable delivery.** Bind source, input/mesh/material/model/backend/code
   revisions, raw outputs, logs, references and actual test evidence to the bounded
   claim. Record performance at equal error, including all relevant overhead.

The [NASA NPARC V&V tutorial](https://www.grc.nasa.gov/www/wind/valid/tutorial/tutorial.html)
is a primary guide for distinguishing code/solution verification, convergence
and validation in CFD; adapt the evidence to each domain. Measurement uncertainty
should have a stated treatment, with [NIST TN 1297](https://www.nist.gov/pml/nist-technical-note-1297)
as a reference for expression of measurement uncertainty. Neither document proves
any particular SPIKE result or substitutes for domain-specific requirements.

## Research versus established use

The 19 October 2026 follow-up records separately reviewed foundations,
independent derivations and executed checks for
[signed-flux RT0 density and complete planar support](DC_RT0_DENSITY.md) and
[same-slab affine magnetic integration](validation/PEEC_AFFINE_SLAB_KERNEL_20261019.md).
Both remain experimental. Neither replaces production branch statistics or
qualifies the original EBrake request; unspecified physical contacts, axial
support and full board AC integration remain open. Their primary-source scope,
numerical tolerances and limitations are stated in those method records.

Established governing laws do not automatically validate a new discretization,
closure, constitutive fit or coupling algorithm. A research implementation must
name its candidate status, additional assumptions and comparison reference.
Peer review is useful evidence, not automatic applicability. Preprints stay
explicitly identified. Unproven behavior must remain experimental/unsupported
even when an interface, plot or demonstration runs successfully.

For learned surrogates record training-data generation/rights, leakage controls,
distribution shifts, conservation/stability and uncertainty/abstention behavior.
For differentiation record gradient tests and nonsmooth regimes. For accelerated
or reduced execution record precision, approximation error and complete runtime/
memory against the unchanged problem. Residual size, visual plausibility,
conservation alone or agreement between two codes cannot establish all accuracy.

## Review, references and honest promotion

Subject-matter review must assess physical regime, equations, empirical laws and
failure interpretation; numerical review assesses discretization, conditioning
and error. Record the extent of each review. Agent review is supporting evidence;
knowledgeable human numerical review before release remains mandatory under
CONTRIBUTING.md. This requirement does not block bounded development.

References are attached to precise methods/claims, not presented as a generic
proof by bibliography. Public product pages establish advertised feature scope;
they do not establish numerical correctness. A licensed standard is normative
only after its actual applicable revision/clause has been reviewed. A citation
does not grant copying, dataset/model redistribution or dependency integration
rights. Follow clean-room and licensing rules.

Keep source fact, independently derived result, assumption, computed result and
engineering recommendation distinct. Later-added corroborating references must
not be described as sources used during an earlier implementation. Missing
lineage remains a tracked gap. Existing reference indexing checks recorded links,
not scientific truth or whether a paper was read.

Mark a bounded stage Done only against its declared executed acceptance evidence;
keep broader family gaps and production qualification separate. Update the
mathematics, references and solver-status records together when numerical
capabilities or validity limits change.

## Circular hybrid via barrel geometry - 18 October 2026

Circular hybrid via barrel mesh containment is separately documented in
[the 18 October geometry evidence](validation/VIA_BARREL_DRILL_CONTAINMENT_20261018.md):
reviewed tangent-circle foundation, independent containment derivation,
bounded polygon approximation, unchanged electrical branch area and executed
geometry regressions. This establishes drill-void containment only.

## Native linear Radau IIA3 — 18 October 2026

This is an independently authored, opt-in implementation, not a change to the
legacy BE, trapezoidal or BDF2 defaults. The owner approved a separately named
higher-order method after the frozen ACC01 near-zero waveform budget exposed
startup and ramp-corner error. Historical failed reports remain retained.

**Reviewed primary sources.** Hairer, *Solving Differential Equations on
Manifolds*, June 2011, section V.2, Example 2.2/Table V.1, printed page 44,
[author's lecture](https://www.unige.ch/~hairer/poly-sde-mani.pdf), supplies the
index-one DAE context and two-stage Radau IIA tableau. Betcke, Salles and Smigaj,
*Overresolving in the Laplace Domain for Convolution Quadrature Methods*,
SIAM J. Sci. Comput. 39(1), 2017, DOI
[10.1137/16M106474X](https://doi.org/10.1137/16M106474X), Appendix A (A.3),
[reviewed text](https://discovery.ucl.ac.uk/1522190/1/Betcke_Overresolving_Laplace_domain_VoR.pdf),
corroborates the coefficients only; its convolution-quadrature algorithm is not
implemented here. Ho, Ruehli and Brennan, *The Modified Nodal Approach to Network
Analysis*, IEEE TCAS 22(6), 1975, pages 504–505, section II, equations (1)–(3),
DOI [10.1109/TCS.1975.1084079](https://doi.org/10.1109/TCS.1975.1084079),
[reviewed paper](https://spinningnumbers.org/assets/MNA75.pdf), supplies MNA
context. These specific portions were reviewed on 2026-10-18; no external
implementation code, figures or prose were copied. This record does not repair
unrelated historical provenance gaps.

**Independent derivation and domain.** KCL with i_R=delta_v/R,
i_C=C*d(delta_v)/dt and v_L=L*di_L/dt gives E*x'=b(t)-G*x, with voltages in V,
currents in A and SI component parameters. For independent-source linear RLC
index-one systems, use c=(1/3,1), A=[[5/12,-1/12],[3/4,1/4]], b=(3/4,1/4).
With A^-1=[[3/2,1/2],[-9/2,5/2]], solve the coupled stage blocks
`(delta_ij*G + (A^-1)_ij*E/h)*Y_j = b(t+c_i*h) + sum_j((A^-1)_ij)*E*x_n/h`.
Stiff accuracy gives x_(n+1)=Y_2; capacitor endpoint current is
`C/h*(-4.5*(v_1-v_n)+2.5*(v_2-v_n))`. Consistent stored charge/flux supplies
E*x_n without inventing a zero initial derivative. True source jumps use the
left limit for the ending stage/sample, then the right limit for the next
interval; continuous ramp corners are not jumps. PULSE/PWL identities and
absolute time survive session batching.

The derived stability function is
`R(z)=(1+z/3)/(1-2*z/3+z*z/6)`, tending to zero for large negative z.
`diag(b)*A + transpose(A)*diag(b) - b*transpose(b)` equals
`[[1,-1],[-1,1]]/16`, which is positive semidefinite. Smooth admitted systems
have order three; damping/stability does not imply coarse-step accuracy or
unconditional componentwise positivity. Nonlinear/OSDI/dependent-source and
adaptive execution, capacitor/voltage-source loops, inductor/current-source
cutsets, floating islands and inconsistent capacitor IC loops are rejected.

**Executed verification.** Eight native regression executables passed. An
independent held-out sinusoidal RC check had error ratios 7.92959 and 7.96398
on halving h, consistent with third order. Independent review found a full-duty
PULSE corner defect; the correction and session/batch equivalence were rerun.
The source/binary/input-bound report
The unbundled local `acc01-radau-20261018/report.json` record passed all 42
signed/zero RC/RL runs,
at amplitudes 1, 1e-3 and 1e-6 V and steps 1, 0.5 and 0.25 us. Every accepted
sample uses the unchanged `atol + 5e-6*abs(reference)` budget, with 1e-12 V and
1e-15 A absolute floors. The independent finite-ramp oracle solves
`tau*y'+y=min(t/rise,1)` using
`y=t/rise+(tau/rise)*expm1(-t/tau)` during the ramp, then exact exponential
propagation; RC/RL currents are checked separately. Zero excitation is exact
zero; 1e-6 V is the lowest tested input, not a universal solver floor.

The smallest observed nonzero maximum absolute errors across the retained
matrix are below. These are fixture-specific observations, not guaranteed
roundoff floors or bounds for other circuits; zero-input error was zero in all
four observables.

| Fixture | Voltage error (V) | Current error (A) |
| --- | ---: | ---: |
| RC | 2.146335166228094e-19 | 2.146533689575107e-22 |
| RL | 2.145772683411558e-19 | 2.1462028173300856e-19 |

**Resources and limits.** The stage system has twice the physical MNA order.
Dense stage matrix/factor storage is capped at 64 MiB; the existing factor cache
has its separate 64 MiB limit. Sparse index bounds are checked, but SparseLU
fill is not hard-capped. There is no in-kernel cancellation hook; process-level
cancellation remains necessary. Conditioning, roundoff, arbitrary switching
DAEs, nonlinear accuracy, measured validation and knowledgeable human numerical
release review remain separate gates. This is synthetic numerical verification,
not hardware or whole-suite qualification.
