<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Solver research, standards and validation references

The [21 October CFD/CHT research review](validation/CFD_CHT_RESEARCH_REVIEW_20261021.md)
pins a 2026 fourth-order sharp-immersed journal candidate, 2025 adaptive/CHT/GCL
work and current-version 2026 entropy-stable-wall preprints. Review scope and
access limitations are explicit. These are candidate evaluations, not imported
implementations or claims that high-order/immersed/ALE methods already execute.

Current research adoption is narrowly recorded in the
[symmetric-stress](validation/ENCLOSURE_SYMMETRIC_STRESS_20261020.md),
[SA-noft2](validation/ENCLOSURE_SA_TRANSPORT_20261020.md) and
[whole-frame rotation](validation/ENCLOSURE_ROTATING_FRAME_20261020.md) ledgers.
They distinguish reviewed equations/variants from unreviewed original texts,
independent derivations from external implementations, and manufactured
verification from physical turbulence or propeller validation. SA's precise
NASA/TMBWG noft2 and modified-vorticity guard are identified; no claim of
novelty, state-of-the-art superiority or general model qualification follows.

The [rectilinear momentum ledger](validation/ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md)
records A. E. P. Veldman's author-hosted CFD notes (2012-2013 cover, January2014
preface), sections1.5.3-1.5.4,2.2-2.3,2.5.1 and exact reviewed pages/equations.
The integrated obstacle closure and original continuum polynomial oracles are
independently derived. The [separate turbulence/rotor review](validation/TURBULENCE_ROTOR_REQUIREMENTS_20261020.md)
records the moved official TMR host and exact SA/SST variants, rotating-frame
and GCL sources, and candidate reference cases; these are requirements, not
implemented or executed turbulence/propeller validation.

The [3-D CHT evidence ledger](validation/ENCLOSURE_CHT_METHOD_20261020.md)
records NIST FiPy4.0.3 mathematical FV/upwind sections, NASA grid-convergence
guidance, Higham's author-written conditioning explanation, and the distinction
between reviewed current SciPy1.18 documentation and executed SciPy1.17.1.
Its independent derivation is linked to the separately scoped MAC/RT0 sources;
no external implementation was adapted and no turbulence/rotor adoption is claimed.

[Resistively loaded coupled pairs](RLGC_TERMINATED_PAIR.md) use D. H. Staelin,
*Electromagnetics and Applications*, MIT OCW text (2011), chapter 8 sections
8.1.1–8.1.2, equations 8.1.1–8.1.16, printed pp. 229–232. Relevant full text
reviewed on 20 October 2026 for Thevenin excitation and resistive reflection.
The sampled multiport feedback, signed source-work split and independent physical
boundary oracle are original derivations; no external implementation or data
was copied. Coupled and lossy line foundations remain separately recorded.

The 20 October 2026 [native CHT source ledger](validation/NATIVE_CHT_METHOD_20261020.md)
records the precise DOE handbook, NIST finite-volume/upwind documentation and
NASA portions reviewed for this increment. The
[surface-exchange ledger](COUPLED_SURFACE_EXCHANGE.md) records its
Farhat/Lesoinne/Le Tallec reference and actual access extent, independent
overlap/adjoint derivation and numerical tests. These records do not supply
missing lineage or qualification for earlier/general CFD/FSI implementations.

[Supplied coupled-pair composition](RLGC_COUPLED_PAIR.md) records Michael
Steer's author-attributed *Microwave and RF Design II: Transmission Lines*,
online sections5.3 equations1–10,18–23 and5.5 equations1–20, reviewed20October2026.
These supply lossless quasi-TEM matrix/even-odd foundations; the lossy orthogonal
composition, power normalization and independent physical-coordinate oracles
are original derivations. Scalar loss provenance remains separately recorded.
No external implementation, example data or figures were copied.

[Finite SI candidate/corner comparison](SI_CANDIDATE_STUDY.md) references D. H.
Staelin, *Electromagnetics and Applications*, MIT OCW online text (2011), chapter
8 §§8.1.1–8.1.2, printed pp.229–232, equations8.1.1–8.1.16. Reviewed relevant
full text on 2026-10-19: telegrapher/traveling-wave and Thevenin loading foundation.
Original ABCD and DC-divider oracles verify the unchanged loaded-line solver;
no external code or test data copied. Sampled synthetic checks establish no
physical board or continuous-band qualification.

The experimental [RT0 density method](DC_RT0_DENSITY.md) records the reviewed
Haus/Melcher section 7.2 and Vohralik (2004), equations (1)-(3), oriented face
basis and independent observable/energy derivation. The experimental
[same-slab magnetic kernel](validation/PEEC_AFFINE_SLAB_KERNEL_20261019.md)
records Reid, arXiv:1708.04666v1, sections I and II-A--C, and the reviewed
Haus/Melcher section 8.1 prose. Exact reviewed portions, original derivations,
executable oracles and unsupported regimes are linked in the method records.
No external implementation was copied; these references do not establish
physical board accuracy, production readiness or human numerical approval.

PI01-S01 [owned pad geometry](OWNED_DRILLED_PAD_DC.md) uses Haus and Melcher,
*Electromagnetic Fields and Energy*, online section 7.2,
[Steady Ohmic Conduction](https://web.mit.edu/6.013_book/www/chapter7/7.2.html).
The steady-current, continuity, insulating-boundary and conductance prose
was reviewed on 19 October 2026; displayed equation GIFs were not transcribed.
Conservative polygon bounds and angular/radial annulus oracles are original
derivations. This is a governing-physics foundation; no external algorithm,
implementation, text or figure was copied. No measured board validation is
established by this reference.

SI02-S06 [supplied RLGC ideal star junctions](RLGC_LINE_JUNCTION.md) use
Staelin, *Electromagnetics and Applications* (2011), section 8.1.2, printed
pages 232 and 234 (multiple-line junctions and interface continuity), and
section 8.3.1, equations (8.3.3)-(8.3.4)/(8.3.16), printed pages 249-251
([official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)),
reviewed 19 October 2026. The multi-leg RMS connection law and independent
physical boundary/quadrature oracles are original derivations. This citation
does not establish physical junction parasitics or measured validation.


SI02-S05 [supplied piecewise RLGC cascade](RLGC_LINE_CASCADE.md) uses
Staelin, *Electromagnetics and Applications* (2011), section 8.1.2, equations
(8.1.14)-(8.1.16) and interface continuity discussion, printed pages 232-234;
section 8.3.1, equations (8.3.3)-(8.3.12)/(8.3.16), printed pages 249-251
([official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)),
reviewed 18 October 2026. The finite wave-connection derivation and original
implementation use these foundations without external code. Ideal electrical
continuity does not model physical fringing/launch/via discontinuities.


SI02-S04 [driven sampled RLGC fields and loss ledger](RLGC_LINE_FIELDS.md)
uses Staelin, *Electromagnetics and Applications* (2011), chapter 8 section
8.3.1, equations (8.3.3)-(8.3.12) and (8.3.16), printed pages 249-251
([official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)),
reviewed 18 October 2026 for phasor propagation and dissipative power. RMS
normalization, coherent two-end constraints and positive analytic spatial
integrals are independently derived and implemented; no external code/data was
used. Circuit storage is not a general dispersive-material energy law, and
electrical loss does not establish thermal ownership or deposition.


SI02-S03 [supplied uniform sampled RLGC networks](RLGC_LINE_NETWORK.md)
uses Staelin, *Electromagnetics and Applications* (2011), chapter 8 section
8.3.1, equations (8.3.3)-(8.3.12), printed pages 249-250
([official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)),
reviewed 18 October 2026 for lossy phasor telegrapher propagation and Heaviside
comparison. The scaled two-port derivation, code, fixtures and tests are original;
no external implementation was used. The source's longitudinal-field/modest-loss
warning limits physical applicability. Sampled passivity is not broadband
causality or measured validation.


Curated 2026-09-20. Read alongside the [solver handbook](SOLVER_HANDBOOK.md)
and [mathematical methods reference](SOLVER_MATHEMATICS.md).
This ledger identifies sources already recorded in the public repository, not
an invented reconstruction of every developer's reading history. The broader
[generated inventory](generated/solver-reference-inventory.json) preserves
recorded links/DOIs with file/line evidence. It includes non-research links and
is not an automatically endorsed bibliography.

The 18 October 2026 [platform assessment](MULTIPHYSICS_PLATFORM_STRATEGY.md) and
[frontier ledger](MULTIPHYSICS_RESEARCH_FRONTIER.md) add **candidate/design
guidance** from current official product descriptions and selected primary
research. They do not change the implemented lineage recorded below.
[Numerical evidence requirements](NUMERICAL_METHOD_EVIDENCE.md) now explicitly
bind future derivations, subject knowledge, precise references and independent
verification/validation; older documented provenance gaps remain open.

**Status vocabulary:** implemented method lineage; design guidance; external
engine/documentation; measurement admission; exploratory comparison; candidate
only. These labels describe use, not correctness or production readiness.
Where exact authors/edition/clause were not recorded, the omission remains
explicit rather than guessed. Older foundational work is retained honestly;
newer publication dates do not retroactively change development provenance.

## Conductor and network methods

SI02-S02 [distortionless distributed line losses](DISTORTIONLESS_LINE_TRANSIENT.md)
record 18 October 2026 review of Staelin (2011), chapter 8 section 8.3.1,
equations (8.3.1)–(8.3.12), printed pages 249–250, for lossy telegrapher laws
and the Heaviside condition; equation (8.3.16), page 251, identifies conductor/
leakage loss in phasor notation. The independent time-domain derivation uses
instantaneous Rp*I²+Gp*V² without a phasor half factor, and local storage/loss
balance. The method records the effective quasi-TEM applicability caveat and
separates mathematical verification from measured/thermal qualification.


SI02-S01 [distributed lossless line transients](LOSSLESS_LINE_TRANSIENT.md)
record 18 October 2026 review of Staelin (2011), chapter 8 section 8.1.1,
equations (8.1.1)–(8.1.12), and section 8.1.2 equations (8.1.14)–(8.1.16) and
reflected-transient discussion on printed pages 232–233. Chapter 7 section
7.1.2 supplies instantaneous power/local energy identities. The method ledger
links official chapters and independently derives two driven-end recursions,
finite causal expansion and signed boundary/probe quantities. This is a supplied
uniform lossless TEM model, not qualified post-layout extraction.


SI07-S10 [network-port reflectometry](NETWORK_REFLECTOMETRY.md) records
18 October 2026 review of Staelin (2011), chapter 7, section 7.1.2,
equations (7.1.6)–(7.1.7)/(7.1.16)–(7.1.18), and section 7.2.2,
equations (7.2.1)–(7.2.8), for instantaneous wave/current/power and time-domain
junction reflection. The method ledger links the official chapter and derives
the fixed-plane apparent ratios and resolution policy independently. Real
instantaneous power is transported energy per time, not automatically heat;
this is not phasor, isolated-S11 or spatial TDR qualification.


SI07-S09 [supplied timing corners](CROSSTALK_TIMING_CORNERS.md) record
18 October 2026 review of Oppenheim, MIT RES.6-007 Lecture 2, PDF pages 1–3
and transparency 2.2, for continuous-time translation, and Freeman, MIT 6.003
Lecture 1 (8 September 2011), PDF pages 14–18, for sampling and PWL signal
reconstruction. The method ledger links official notes and independently derives
clipped endpoint-held waveforms, unchanged-state corner experiments and finite
union envelopes. Parent physical KCL/KVL and linearity remain unchanged.


SI07-S08 [sampled multi-aggressor crosstalk](MULTI_AGGRESSOR_CROSSTALK.md)
records 18 October 2026 review of Agarwal/Lang, MIT 6.002 Lecture 3, PDF pages
3–13 (slides marked Fall 2000, hosted Spring 2007), for linear independent-source
superposition, and Staelin (2011), section 3.4.2 for linear circuit equations.
The method ledger links primary sources and independently derives the biased
common-state decomposition, finite signed-family envelopes and fixed witness
checks. These references do not establish intersample or measured qualification.


SI07-S07 [RLC energy ledgers](RLC_ENERGY_LEDGER.md) record 18 October 2026
review of Van Loan (1978), *Computing Integrals Involving the Matrix Exponential*,
mathematical sections II-III, pp.395-397: block-integral identities and doubling.
The method ledger links the official DOI and actually reviewed published-paper
scan, distinguishes mathematical review from unreviewed external program source
and global error bounds, and records the independently derived covariance/work
formulation. Staelin capacitor/inductor energy and installed SciPy `expm`
documentation support physical/numerical lineage; measured qualification remains
separate.

SI07-S06 [supplied RLC initial states](RLC_INITIAL_STATES.md) record
18 October 2026 review of Staelin (2011), section 3.5.1, equations (3.5.1)-(3.5.15)
and initial-condition selection following (3.5.9), plus SciPy 1.17.0 `expm` API
documentation. The initialized mixed-state and split-run derivations are original.
Analytic free/forced and physical nonzero fitted-memory references include
initial stored energy; generic fitted-state physical energy remains unspecified.

SI07-S05 [combined R/L and shunt-C boundaries](RLC_NETWORK_TRANSIENT.md) record
18 October 2026 review of Staelin's *Electromagnetics and Applications* (2011),
sections 3.1.3, 3.2.1/3.2.3, 3.4.1 and 3.5.1, and installed SciPy 1.17.0 `expm`
API documentation. The method ledger locates the capacitor/inductor laws and
energies, KVL/KCL and RLC damping. Mixed wave/state closure, loaded-RLC and
coupled physical references are independently authored; library algorithm-paper
full-text review and measured qualification are not claimed.

SI07-S04 [shunt-capacitive boundaries](CAPACITIVE_NETWORK_TRANSIENT.md) record
18 October 2026 review of David H. Staelin's *Electromagnetics and Applications*
(copyright 2011; MIT OCW-hosted text), sections 3.1.3/3.4.1/3.5.1–3.5.2:
capacitor law/energy, KCL and parallel RLC equations. The installed SciPy 1.17.0
`expm` API documentation provides the numerical dependency reference. The linked
ledger distinguishes reviewed sections from unreviewed algorithm-paper details;
the mixed formulation and synthetic reference circuits are independently authored.

SI07-S03 [inductive network boundaries](INDUCTIVE_NETWORK_TRANSIENT.md) record
18 October 2026 review of MIT OCW 18.03SC *RLC Circuits* (Fall 2011), pp.1–3,
equations (1)/(3)/(5), and the installed SciPy 1.17.0 `expm` API algorithm
reference. The linked method ledger distinguishes reviewed physics/API guidance
from the unavailable Kurokawa full text and unreviewed Higham paper details.
Its mixed wave algebra, PWL formulation and analytical/reference fixtures are
independently authored; synthetic evidence does not establish measurement parity.

### R1 - PEEC foundation

A. E. Ruehli (1974), *Equivalent Circuit Models for Three-Dimensional
Multiconductor Systems*, IEEE Transactions on Microwave Theory and Techniques,
22(3), 216-221. [DOI:10.1109/TMTT.1974.1128204](https://doi.org/10.1109/TMTT.1974.1128204).
**Recorded method lineage:** explicitly named in
[peec_solver.hpp](../src/peec/peec_solver.hpp). The kernel's partial-element
formulation is not evidence that all retarded, radiation or arbitrary-geometry
variants of PEEC are implemented. The DOI locator was added in this audit;
the original code comment records author/title/year, not a paper access log.

### R2 - Inductance reference

E. B. Rosa and F. W. Grover (1912), *Formulas and tables for the calculation of
mutual and self-inductance (Revised)*, NBS Bulletin 8(1).
[NIST catalog](https://www.nist.gov/nist-research-library/nbs-bulletin-volume-8),
[DOI:10.6028/bulletin.185](https://doi.org/10.6028/bulletin.185).
**Recorded analytical lineage:** [kernel](../src/peec/peec_solver.cpp) and
[benchmark](../python/spike_core/benchmarks.py) name the reference. The benchmark
independently evaluates the admitted rectangular-conductor expression; neither
that formula nor a positive diagonal validates an arbitrary mutual-L matrix.

### R3 - Conductor roughness candidates

Huray et al., *Fundamentals of a 3-D "snowball" model for surface roughness power
losses* (2007), [DOI:10.1109/SPI.2007.4512227](https://doi.org/10.1109/SPI.2007.4512227).
Helmreich et al., *A Physical Surface Roughness Model and Its Applications*
(2017), [DOI:10.1109/TMTT.2017.2695192](https://doi.org/10.1109/TMTT.2017.2695192).
**Candidate/design guidance**, recorded in conductor plan.
The current public adapter admits none/Hammerstad, not these two models.
Hammerstad is an empirical estimate; its exact primary edition is a provenance
gap in the audited record. RMS roughness is not a substitute for Huray parameters.

### R4 - Multiconductor transmission lines

[NASA report 19900004089](https://ntrs.nasa.gov/citations/19900004089) and
[NIST RLGC report, publication 7607](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=7607).
Barth and Iyer (2017), *On the Unique Determination of Modal Multiconductor
Transmission-Line Properties*, [arXiv:1702.01771](https://arxiv.org/abs/1702.01771).
**Recorded formulation guidance:** [geometry-derived SI](GEOMETRY_DERIVED_SI_CHANNEL.md).
Used to distinguish per-unit-length matrices, propagation and modal normalization.
Uniform-line approximations do not validate vias, connectors, discontinuities or
arbitrary 3-D materials. Full bibliographic metadata for the two institutional
reports still needs recording; the report identifiers are preserved exactly.

### R5 - Power waves and reference impedance

K. Kurokawa (1965), *Power Waves and the Scattering Matrix*,
[DOI:10.1109/TMTT.1965.1125964](https://doi.org/10.1109/TMTT.1965.1125964).
[NIST comments on complex-reference network conversions](https://www.nist.gov/publications/comments-conversions-between-s-z-y-h-abcd-and-t-parameters-which-are-valid-complex).
**Recorded convention guidance:** [geometry-derived SI](GEOMETRY_DERIVED_SI_CHANNEL.md)
and [S-parameters](../python/spike_core/sparameters.py). Declare the wave convention
and reference impedances before applying passivity or renormalization criteria.
The four-excitation solve S*A=B is independently derived linear algebra, not
copied implementation or a claimed result from these papers.

### R6 - Via transitions and future rational models

Tang et al. (2024), *A practical ball-grid-array transition modelling methodology
for accurate and fast multi-interposer package simulation*,
[DOI:10.1049/pel2.12667](https://doi.org/10.1049/pel2.12667).
Bradde et al. (2022), *Data-Driven Extraction of Uniformly Stable and Passive
Parameterised Macromodels*, [DOI:10.1109/ACCESS.2022.3147034](https://doi.org/10.1109/ACCESS.2022.3147034).
Carlucci, Bradde and Grivet-Talocia (2023), *Addressing load sensitivity of rational
macromodels*, [DOI:10.1109/TCPMT.2023.3284551](https://doi.org/10.1109/TCPMT.2023.3284551).
**Design guidance / future surrogate constraints**, as explicitly separated in
[the existing research ledger](RESEARCH_AND_CLEAN_ROOM_ENGINEERING.md). No BGA
geometry/error figures are adopted as universal PCB rules; fitting passivity
does not certify geometry accuracy, causality or arbitrary termination behavior.

## Formats and measurement practice

### R7 - IBIS and Touchstone

The [IBIS Open Forum specifications index](https://www.ibis.org/specs/),
[IBIS 7.2](https://ibis.org/~ibisorg/ver7.2/ver7_2.pdf),
[IBIS 8.0](https://ibis.org/ver8.0/ver8_0.pdf) and
[Touchstone 2.1](https://www.ibis.org/touchstone_ver2.1/touchstone_ver2_1.pdf)
are recorded in [SI workflow](SI_WORKFLOW.md) and
[geometry-derived SI](GEOMETRY_DERIVED_SI_CHANNEL.md).
**Format/terminology references**, not blanket implementation declarations.
IBIS inventory/DC-slope/ramp reduction does not implement arbitrary switching
models or AMI. A specification link does not establish Ethernet compliance.

### R8 - De-embedding and measured interconnect practice

[IEEE 370-2020 official record](https://standards.ieee.org/ieee/370/6165/) and
[NIST statistical study of de-embedding applied to eye analysis](https://www.nist.gov/publications/statistical-study-de-embedding-applied-eye-diagram-analysis).
**Recorded measurement/qualification guidance:** [geometry-derived SI](GEOMETRY_DERIVED_SI_CHANNEL.md).
State fixtures, calibration, bandwidth, noise and termination before comparing
an eye or channel. No copyrighted limit table, unreviewed normative clause or
IEEE reference implementation is imported by this documentation.

## Resonance and external fields

### R9 - Resonance terminology and independent ringdown derivation

[MIT 6.101 resonance handout](https://web.mit.edu/6.101/www/s2019/handouts/L02_4.pdf)
is named in [si_resonance.py](../python/spike_core/si_resonance.py).
[Harminv documentation](https://github.com/NanoComp/harminv) is named in
[si_ringdown.py](../python/spike_core/si_ringdown.py) for complex-frequency/Q
terminology. **Convention references:** SPIKE's AR(2) fit/reconstruction is its
own bounded implementation, not Harminv code or the Harminv algorithm. Loaded
decay is not automatically intrinsic Q; an invisible second mode is not excluded
by a good scalar fit.

### R10 - External FDTD and near-to-far conventions

[openEMS documentation](https://docs.openems.de/) and its
[patch-antenna example](https://docs.openems.de/python/openEMS/Tutorials/Simple_Patch_Antenna.html)
are recorded in [external-engine adapter](../python/spike_core/external_engines.py)
and [benchmark adapter](../python/spike_core/openems_benchmarks.py).
[Meep near-to-far documentation](https://meep.readthedocs.io/en/master/Python_User_Interface/#near-to-far-field-spectra)
is cited in [Huygens transform](../python/spike_core/huygens_far_field.py).
**External engine/API or convention references**, not claims of copying those
solvers. Record the installed binary version separately from a moving docs URL.
The 2026-09-20 openEMS documentation landing page advertises a newer revision
than the 0.0.36 runtime used in the retained field evidence.

## Thermal and flow

### R11 - Bounded laminar verification context

[COMSOL plane-flow example documentation](https://doc.comsol.com/6.4/doc/com.comsol.help.models.particle.inertial_focusing/inertial_focusing.html)
and [NASA verification consistency guidance](https://www.grc.nasa.gov/WWW/wind/valid/tutorial/consistency.html)
are recorded in [bounded CHT](BOUNDED_CHT_AND_RADIATION.md).
**Analytical/context references**, not copied code or evidence that COMSOL was
executed. Structured-solid and laminar-channel discretizations are documented
directly in their code; no additional paper-level historical lineage was found
for those implementations in this audit.

### R12 - External CFD configuration references

[OpenFOAM Boussinesq documentation](https://doc.openfoam.com/2212/tools/processing/models/thermophysical/equation-of-state/rtm/Boussinesq/),
[turbulence documentation](https://doc.openfoam.com/2606/tools/processing/models/turbulence/),
and the official API links recorded in [fan/CHT qualification](FAN_CHT_QUALIFICATION.md)
and [flow diagnostics](../python/spike_core/openfoam_flow_diagnostics.py).
**External runtime configuration guidance**. Mixed documentation versions must
not be treated as one pinned solver version. Energy balance, startup energy,
mesh/time-step convergence, buoyancy/turbulence applicability and measurements
remain separate evidence requirements.

## Geometry and meshing

### R13 - Robust predicates

J. R. Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust
Geometric Predicates*; [author's publication index](https://people.eecs.berkeley.edu/~jrs/jrspapers.html),
[author's paper](https://people.eecs.berkeley.edu/~jrs/papers/robustr.pdf).
**Recorded numerical rationale:** [research ledger](RESEARCH_AND_CLEAN_ROOM_ENGINEERING.md)
and [native geometry record](CAD_NEUTRAL_NATIVE_MULTIPHYSICS_FOUNDATION.md).
SPIKE uses independently written fixed-grid exact predicates; it does not claim
to implement Shewchuk's adaptive expansion-arithmetic code. Exact predicates
and engineering clearances are different concepts.

### R14 - Constrained triangulation

Shewchuk, [General-Dimensional Constrained Delaunay Triangulations I](https://people.eecs.berkeley.edu/~jrs/papers/cdtj1.pdf);
Shewchuk and Brown, [Fast Segment Insertion and Incremental Construction of CDTs](https://people.eecs.berkeley.edu/~jrs/papers/segments.pdf);
[CGAL 2D triangulation documentation](https://doc.cgal.org/latest/Triangulation_2/index.html).
**Published geometric principles**, recorded in the same research ledger.
Native code is not CGAL or Triangle code. Exact topology, boundary preservation
and Euler/area checks do not prove tetrahedral element quality or field accuracy.
The CGAL `latest` URL floats: historical notes saying 6.2 need a pinned revision
before an exact-version review; this audit does not silently rewrite that history.

### R15 - CAD meshing and surface spaces

[Gmsh reference manual](https://gmsh.info/doc/texinfo/gmsh.html) and
[Bempp function-space documentation](https://bempp.com/handbook/api/function_spaces.html)
are recorded in [mesh roadmap](ANALYSIS_AND_MESH_ROADMAP.md).
Distinguish that older roadmap's candidate status from later
[OCC integration evidence](OCC_CONFORMING_PCB_MESH.md). A discovered Gmsh runtime
or RWG basis is not a completed native MoM solver. External libraries retain
their own licenses and admission requirements.

### R16 - Future scaling and qualification guidance

[Layered-medium FMM research, arXiv:2507.18491](https://arxiv.org/abs/2507.18491)
is explicitly **candidate only** in the mesh roadmap. Its published performance
must not be reported as SPIKE performance.
[AMD XAPP1392 via guidance](https://docs.amd.com/r/en-US/xapp1392-pcb-chan-design-guidelines/Via-Impedance-Optimization)
and [NIST FEM solution-uncertainty guidance](https://www.nist.gov/publications/finite-element-method-solution-uncertainty-asymptotic-solution-and-new-approach)
are recorded in the research ledger for design context and validation boundaries.
IPC-2228/IPC-2221 revision references in that ledger establish standards scope;
licensed normative requirements and applicable clauses are not reconstructed.

### R17 - Surface-EM reference operators

Retrieved 2026-09-30. S. M. Rao, D. R. Wilton and A. W. Glisson,
*Electromagnetic Scattering by Surfaces of Arbitrary Shape*, IEEE Transactions
on Antennas and Propagation (1982),
[DOI 10.1109/TAP.1982.1142818](https://doi.org/10.1109/TAP.1982.1142818),
is method lineage for a full interior-edge triangular current basis. M. G.
Duffy, *Quadrature Over a Pyramid or Cube of Integrands with a Singularity at a
Vertex*, SIAM Journal on Numerical Analysis (1982),
[DOI 10.1137/0719090](https://doi.org/10.1137/0719090), motivates
singularity-removing coordinate transformations; SPIKE independently derives
its triangular fan Jacobian and exact radial static moment. [MIT radiation
potential notes](https://web.mit.edu/6.013_book/www/chapter12/Backup/12.4.html)
support the outgoing far-field asymptotic. [NIST CODATA 2022](https://physics.nist.gov/cuu/pdf/all.pdf)
provides vacuum constants. The implemented kernel and supplied-current
postprocessor are tested in the [operator evidence](validation/MOM_REFERENCE_OPERATORS_20260930.md);
they are not a MoM current solver or an RCS validation of a scatterer.

[Planewave density interpolation](https://arxiv.org/abs/1910.02046)
(Pérez-Arancibia, Turc, Faria and Sideris, 2019) and
[OSRC EFIE preconditioning](https://arxiv.org/abs/2507.20707)
(Darbas and Fierro-Piccardo, 2025) are research
candidates only. No algorithm, performance result or geometry from those
papers is claimed as implemented. Sources informed the future validation
questions, not SPIKE source code or fixtures.

## Experimental datasets and hardware fixtures

| ID | Primary source | Recorded use and exact limitation |
|---|---|---|
| D1 | Schaich, Molnar, Al Rawi and Payne, experimental wire-line data, [DOI:10.17863/CAM.65674](https://doi.org/10.17863/CAM.65674) | [Cambridge admission](MEASURED_SI_CAMBRIDGE.md): CC BY 4.0 data; selected two-port transfers, not a complete four-port matrix or PCB prediction. |
| D2 | P. P. Viezbicke, NBS Technical Note 688, [DOI:10.6028/NBS.TN.688](https://doi.org/10.6028/NBS.TN.688) | [Yagi comparison](NBS_YAGI_COMPARISON.md): exploratory, with explicit feed/environment/geometry differences; not matched validation. |
| D3 | Driver and Seegmiller (1985), [DOI:10.2514/3.8890](https://doi.org/10.2514/3.8890); [NASA backward step data](https://tmbwg.github.io/turbmodels/backstep_val.html) | [CFD corpus](CFD_PUBLIC_REFERENCE_CORPUS.md): measured data admitted; matching SPIKE prediction not executed. Retain corrected Reynolds-number and normalization notes. |
| D4 | Parker and Smith (2020), [heated plenum dataset](https://digitalcommons.usu.edu/all_datasets/126/), [DOI:10.26078/cad3-j806](https://doi.org/10.26078/cad3-j806) | Selected thermal-flow dataset, not imported or simulated in the recorded evidence. |
| D5 | [FAN-02, Zenodo 17909944](https://zenodo.org/records/17909944) | Candidate only in CFD corpus; complete operating-point/measurement/license admission remains required. |
| D6 | [Berkeley Lab Marble](https://github.com/BerkeleyLab/Marble), [CERN-linked White Rabbit hardware](https://gitlab.com/ohwr/project/wr-switch-hw/) | Pinned board evaluation: hardware-source/import fixtures, NOT measured references. Preserve per-revision CERN OHL notices; no automatic redistribution admission. |

## Verification and provenance gaps

The audit rechecked official IBIS, openEMS, NIST inductance catalog, NASA
backward-step, Utah State dataset, Shewchuk author-index and Barth/Iyer arXiv
landing pages. This checks identity/context, not a full review of every paper.
Some DOI pages (including Cambridge and NBS TN688) could not be fetched by the
browser during this audit; their earlier recorded identifiers and local evidence
remain, but no fresh full-text verification is claimed. Other citations above
are transcribed from existing project references and remain subject to review.

Outstanding provenance work includes precise primary editions for the empirical
Hammerstad/Jensen relations, paper/section attribution for uncited original MNA
and thermal derivations where appropriate, pinned versions for moving manual
links, and availability of books/repositories mentioned in earlier conversations
but not retained in the workspace. An ambient browser tab is not evidence of
algorithm adoption. The private SPIKES research ledger is maintained separately.

Do not equate citation with permission to copy. No paper figures, tables,
publisher text, proprietary models or third-party implementation code are
reproduced here. Follow [clean-room policy](RESEARCH_AND_CLEAN_ROOM_ENGINEERING.md)
and [licensing](../LICENSING.md). New reference records should include author,
title, publication/revision, DOI/official URL, retrieval evidence, status of use,
independent derivation, implementation/test paths and unresolved validation gates.

For the new opt-in linear Radau IIA3 method, the exact reviewed portions of
Hairer's June 2011 lecture, Betcke/Salles/Smigaj (2017) Appendix A and
Ho/Ruehli/Brennan (1975) section II, with DOI/access links, independent
derivation and executed verification, are recorded in
[numerical method evidence](NUMERICAL_METHOD_EVIDENCE.md#native-linear-radau-iia3--18-october-2026).
The later corroborating sources are not asserted as lineage for older kernels.

## SI02-S09 reactive coupled-line endpoint laws

[Method record](RLGC_REACTIVE_PAIR.md) records full-text review on 20 October 2026
of D. H. Staelin, MIT *Electromagnetics and Applications* (2011), chapter 8,
section 8.1.4 pp.237-239 and section 8.3.1 eqs.8.3.1-8.3.9 pp.249-250.
It derives the sampled Norton/wave closure and RMS mean energy identity in
project notation, with exact primary URL, units, numerical assumptions and
clean-room provenance. No measurement or broader solver qualification follows
from this citation.

## SI02-S10 physical coupled-section continuity and loss

[Method/source ledger](RLGC_COUPLED_CASCADE.md) records actual full-text review
of Staelin, MIT *Electromagnetics and Applications* (2011), chapter8 section8.1.2
printedpp232-234 (especially p234 physical continuity), section8.3.1
eqs8.3.1-8.3.9 pp249-250 and eq8.3.16 p251. It independently derives the
common-reference multiport connection, RMS conversion and loss ledger, with
physical spatial-chain/heat-quadrature oracles and explicit clean-room provenance.
Citations establish physics lineage, not measured accuracy or imported code.

## SI02-S11 composed physical endpoints and section fields

[Method/source ledger](RLGC_LOADED_CASCADE.md) derives two-level physical
RLC/coupled-channel closure from independently authored constituent methods.
It records actual MIT Staelin(2011) chapter8 review: junction continuity
section8.1.2 pp232-234, reactive/Thevenin treatment section8.1.4 pp236-237, and
complex line laws/dissipation section8.3.1 eqs8.3.1-8.3.9 pp249-250 plus
eq8.3.16 p251. RMS mean-energy/power identities, units, numerical envelope,
independent oracle and clean-room rights are explicit; no unreviewed lineage,
measurement correlation or thermal qualification is inferred.

## SI02-S12 coupled branch continuity and conservation

[Method/source ledger](RLGC_COUPLED_STAR.md) independently extends physical
continuity and KCL to a symmetric lossless star map for each conductor. It records
actual Staelin, MIT *Electromagnetics and Applications* (2011), chapter 8 review:
section 8.1.2 pp.232–234 and section 8.3.1 eqs.8.3.1–8.3.9 pp.249–250 plus
eq.8.3.16 p.251. The multi-leg projector proof, physical oracle and RMS treatment
are independently authored; no external implementation or geometric junction
validation is inferred.

## SI02-S13 physical branch endpoints and cancellation

[Method/source ledger](RLGC_LOADED_STAR.md) records Staelin's exact reviewed
MIT 2011 line/interface/reactive sections and independently derives the variable-
port physical RLC closure. It additionally records full-text review of Higham,
*The Accuracy of Floating Point Summation*, SIAM JSC 14(4), 783–799 (1993),
model (1.2) p.784 and bound (2.6)/conditioning p.785. Operand-scaled cancellation
analysis does not prove the specific 64*eps implementation factor or full-path
accuracy. No external implementation is adapted or measurement inferred.
