# Research provenance and clean-room engineering

SPIKE uses published research, standards, and independently reproducible
physics as design inputs. It does not copy or closely translate source code,
tests, user interfaces, figures, tables, proprietary models, or numerical
recipes from other software. An external program may be used only through its
documented interface as an isolated comparison path unless its provenance,
license, and integration have been reviewed separately.

## Required provenance record

Every physics-affecting research decision records:

- title, author/publisher, DOI or official standards URL, publication/revision
  date, and retrieval date;
- whether the source is a paper, normative licensed standard, public table of
  contents, official documentation, or independent measurement;
- the source fact in a short paraphrase, the SPIKE inference, and limits on
  transferring it to the implemented geometry/material/frequency domain;
- the independently derived equation, contract, test, or validation fixture
  that implements the decision; and
- the evidence still needed for qualification.

Paywalled standards are never reconstructed from summaries or third-party
copies. A public table of contents proves scope only. Numeric requirements are
called normative only when the licensed active revision and applicable clause
have been reviewed.

## Current via-transition research ledger

Retrieved 2026-08-27.

| Source | Design guidance used by SPIKE | Applicability boundary |
|---|---|---|
| Tang et al., *A practical ball-grid-array transition modelling methodology for accurate and fast multi-interposer package simulation*, IET Power Electronics 17(12), 2024, [DOI 10.1049/pel2.12667](https://doi.org/10.1049/pel2.12667) | Define the transition boundary explicitly; retain adjacent material and return-path geometry; extract C and return-loop L separately; validate a reduced model against a parent field solution and measurement over its declared band. | The paper studies BGA/package transitions, not arbitrary PCB vias. Its geometry, fitted dimensions, bandwidth, and error results are not copied or treated as PCB design rules. |
| Bradde et al., *Data-Driven Extraction of Uniformly Stable and Passive Parameterised Macromodels*, IEEE Access, 2022, [DOI 10.1109/ACCESS.2022.3147034](https://doi.org/10.1109/ACCESS.2022.3147034) | A future geometry/material sweep surrogate must remain stable and passive across the admitted parameter domain, including held-out points. | Macromodel stability/passivity does not validate the field discretization, geometry, causality, or measurement accuracy. No implementation is copied. |
| Carlucci, Bradde, and Grivet-Talocia, *Addressing load sensitivity of rational macromodels*, IEEE Transactions on Components, Packaging and Manufacturing Technology, 2023, [DOI 10.1109/TCPMT.2023.3284551](https://doi.org/10.1109/TCPMT.2023.3284551) | Validate future fitted networks under their intended terminations, not only the extraction reference impedance. | General rational-model guidance; it does not prescribe via geometry or a field solver. |
| IPC-2228, *Sectional Design Standard for High Frequency (RF/Microwave) Printed Boards*, original release October 2022, [official IPC table of contents](https://www.ipc.org/TOC/IPC-2228_TOC.pdf) and [revision table](https://www.ipc.org/ipc-document-revision-table) | Track the active revision and use the licensed standard during manufacturability/conformance review. | The public material establishes scope, not numeric via, antipad, or stitching rules. SPIKE currently makes no IPC-2228 conformance claim. |
| IPC-2221C, *Generic Standard on Printed Board Design*, December 2023, [official IPC revision table](https://www.ipc.org/ipc-document-revision-table) | Track generic printed-board design revision/applicability separately from numerical solver qualification. | Numeric normative requirements require licensed text and a declared customer/fabricator applicability profile. |

No reviewed source establishes one universal antipad diameter, return-via
spacing, or radial tessellation. Those inputs therefore remain explicit
parameters. Their acceptance requires source provenance, resource admission,
mesh/domain convergence, and independent or measured validation.

## Independent implementation rules

1. Derive algorithms from governing equations and project requirements in
   SPIKE's own notation, architecture, names, comments, and tests.
2. Do not inspect third-party solver source code for the purpose of reproducing
   its implementation. Do not translate implementation structure between
   languages.
3. Separate `source fact`, `assumption`, `derived formula`, `numerical result`,
   and `engineering decision` in validation records.
4. Use external engines only as process-isolated comparisons unless a distinct
   legal/provenance review authorizes integration. Agreement with one engine
   is supporting evidence, not truth by itself.
5. Reserve validation geometries, frequencies, materials, loads, and measured
   coupons that were not used to tune the implementation.
6. Store input/version, mesh statistics, port and return-path definitions,
   solver tolerances, convergence history, and output digests with every
   qualification record.
7. Require physical invariants appropriate to the model: charge conservation,
   positive stored energy, matrix symmetry/reciprocity where applicable,
   passivity, stability, causality, energy balance, and refinement convergence.
8. Keep capabilities unavailable or experimental when the provenance or
   validation record is incomplete.

## Current Wave 2 application

`spike/pcb-via-transition-geometry/v1` admits only source-proven circular
through, blind, buried, or adjacent-layer microvia geometry with explicit
plating, lands, antipads, and a reference-zone-contained local patch.
`spike/pcb-via-transition-mesh/v1` independently tessellates that geometry with
requested bounded radial resolution. Outer conductor boundaries are
inscribed; drill and antipad void boundaries are circumscribed, so the mesh is
a conservative approximation of the exact circles. The topology audit checks
finite/owned vertices, zero-area and duplicate faces, edge incidence,
orientation, closed-domain signed volume, unused vertices, and exact circular
void exclusion.

The separate mesh-quality report closes bounded geometry integrity and
geometry/domain-convergence gates only. It compares independently derived
conservative polygon measures with exact circular area/volume measures over
fixed doubling radial levels, uses stable translated signed-volume summation,
and records native admission plus conditioning warnings. Runtime verification
regenerates the report from the supplied geometry rather than trusting claimed
metrics or digests. These elementary formulas and contract code were developed
independently; no third-party solver source code is copied.

The report does not calculate electromagnetic fields or establish physical
discretization error. The local patch is not the full reference plane, and
radial geometry refinement is not SI/PI/field-solver convergence. Capacitance,
SI extraction, solver readiness, independent physics comparison, and measured
correlation remain false or pending.

## General full-reference-plane topology and constrained-mesh gate

Retrieved 2026-08-28. Published contracts remain additive: geometry v1 covers
the complete convex straight-edged subset, v2 admits one concave straight-edge
outer ring with proper source cutouts on the exact 1 nm grid, and v3 admits
DesignIR circular arcs through a fixed provenance-bound flattening policy.
V3's sagitta equation and grid-snap allowance were independently derived from
circle geometry; its output is explicitly a bounded approximation rather than
exact curved copper or a conservative copper envelope.

- [CGAL 6.2 2D Triangulations](https://doc.cgal.org/latest/Triangulation_2/index.html)
  is used as a current primary reference for planar straight-line constraints,
  oriented simplicial complexes, and constrained-domain classification. SPIKE
  will not copy CGAL implementation source; it will independently specify its
  own contracts and predicates.
- [Shewchuk, Robust Adaptive Floating-Point Geometric Predicates](https://people.eecs.berkeley.edu/~jrs/papers/robust-predicates.pdf)
  provides the primary numerical rationale for separating robust orientation/
  intersection decisions from manufacturing-clearance policy. A global epsilon
  must not silently repair or reclassify topology.
- [AMD XAPP1392, Via Impedance Optimization](https://docs.amd.com/r/en-US/xapp1392-pcb-chan-design-guidelines/Via-Impedance-Optimization)
  is used only for the physical design premise that antipad geometry affects a
  via transition. It does not validate SPIKE geometry or solver results.
- [NIST, Finite Element Method Solution Uncertainty](https://www.nist.gov/publications/finite-element-method-solution-uncertainty-asymptotic-solution-and-new-approach)
  reinforces that geometry convergence cannot substitute for solver-output
  convergence and accuracy assessment.

The native topology kernel now evaluates fixed-grid orientation exactly and
evaluates the translated incircle determinant with an independently written
signed 256-bit accumulator. The latter is cross-checked against 250
deterministic Python arbitrary-integer oracle cases, including the full
declared coordinate range. Exact scaled-point orientation and doubled-area
accumulation use the same fixed-grid arithmetic. The shared kernel also has an
exact deterministic simple-ring cavity triangulator and a no-Steiner
constrained-domain triangulator. The latter independently revalidates
canonical input, retains every collinear source boundary vertex, recovers all
nonintersecting outer/cutout constraints, applies an exact incircle
legalization rule with a deterministic cocircular tie, and uses exact
rational-centroid winding for hole classification. Independent native and
Python audits verify CCW faces, source/interior edge incidence, Euler counts,
exact doubled area, complete source-vertex use, local constrained-Delaunay
legality, canonical input invariance, and resource caps.

The algorithm and tests were written in SPIKE's own data model and notation.
No CGAL, Triangle, or other third-party mesher source was inspected, copied,
translated, or linked. Published local-facet and exact-predicate principles
guide the proof obligations, while incremental segment-insertion research
motivates treating constraint recovery as a distinct phase. Current primary
references are:

- [CGAL 6.2 2D triangulations](https://doc.cgal.org/latest/Triangulation_2/index.html)
  for the documented distinction between constraints, exact predicates, and
  exact constructions.
- [Shewchuk, General-Dimensional Constrained Delaunay Triangulations I](https://people.eecs.berkeley.edu/~jrs/papers/cdtj1.pdf)
  for the local-facet characterization of constrained Delaunay structure.
- [Shewchuk and Brown, Fast Segment Insertion and Incremental Construction of CDTs](https://people.eecs.berkeley.edu/~jrs/papers/segments.pdf)
  for the published incremental constraint-insertion formulation.

This kernel is not yet the registered generalized mesh and does not claim
refinement or element quality. The next additive mesh contract still requires
exact source-zone identity/digests, complete outer/source-cutout/antipad
constraints, closed oriented extrusion, resource/cancellation accounting,
native loop admission, and byte-stable regeneration. Every physics-readiness
flag remains false until subsequent field-convergence and independent/measured
validation gates pass.
