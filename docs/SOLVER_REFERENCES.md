<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Solver research, standards and validation references

Curated 2026-09-20. Read alongside the [solver handbook](SOLVER_HANDBOOK.md).
This ledger identifies sources already recorded in the public repository, not
an invented reconstruction of every developer's reading history. The broader
[generated inventory](generated/solver-reference-inventory.json) preserves
recorded links/DOIs with file/line evidence. It includes non-research links and
is not an automatically endorsed bibliography.

**Status vocabulary:** implemented method lineage; design guidance; external
engine/documentation; measurement admission; exploratory comparison; candidate
only. These labels describe use, not correctness or production readiness.
Where exact authors/edition/clause were not recorded, the omission remains
explicit rather than guessed. Older foundational work is retained honestly;
newer publication dates do not retroactively change development provenance.

## Conductor and network methods

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
**Candidate/design guidance**, recorded in [conductor plan](AC_CONDUCTOR_MODEL_PLAN.md).
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

## Experimental datasets and hardware fixtures

| ID | Primary source | Recorded use and exact limitation |
|---|---|---|
| D1 | Schaich, Molnar, Al Rawi and Payne, experimental wire-line data, [DOI:10.17863/CAM.65674](https://doi.org/10.17863/CAM.65674) | [Cambridge admission](MEASURED_SI_CAMBRIDGE.md): CC BY 4.0 data; selected two-port transfers, not a complete four-port matrix or PCB prediction. |
| D2 | P. P. Viezbicke, NBS Technical Note 688, [DOI:10.6028/NBS.TN.688](https://doi.org/10.6028/NBS.TN.688) | [Yagi comparison](NBS_YAGI_COMPARISON.md): exploratory, with explicit feed/environment/geometry differences; not matched validation. |
| D3 | Driver and Seegmiller (1985), [DOI:10.2514/3.8890](https://doi.org/10.2514/3.8890); [NASA backward step data](https://tmbwg.github.io/turbmodels/backstep_val.html) | [CFD corpus](CFD_PUBLIC_REFERENCE_CORPUS.md): measured data admitted; matching SPIKE prediction not executed. Retain corrected Reynolds-number and normalization notes. |
| D4 | Parker and Smith (2020), [heated plenum dataset](https://digitalcommons.usu.edu/all_datasets/126/), [DOI:10.26078/cad3-j806](https://doi.org/10.26078/cad3-j806) | Selected thermal-flow dataset, not imported or simulated in the recorded evidence. |
| D5 | [FAN-02, Zenodo 17909944](https://zenodo.org/records/17909944) | Candidate only in CFD corpus; complete operating-point/measurement/license admission remains required. |
| D6 | [Berkeley Lab Marble](https://github.com/BerkeleyLab/Marble), [CERN-linked White Rabbit hardware](https://gitlab.com/ohwr/project/wr-switch-hw/) | [Pinned board evaluation](CERN_MARBLE_EVALUATION_20260920.md): hardware-source/import fixtures, NOT measured references. Preserve per-revision CERN OHL notices; no automatic redistribution admission. |

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
