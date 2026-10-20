<!-- SPDX-License-Identifier: Apache-2.0 -->
# CFD/CHT method-candidate review, 21 October 2026

Purpose: translate the authorized [capability target](../CFD_CHT_CAPABILITY_TARGET.md)
into a traceable research queue. This bounded primary-source scan is not a
systematic literature review, a citation ranking or proof that a method is the
latest/best in its field. Candidate status is not implementation or validation.
No dependencies, external code, figures, meshes or measurements were imported.

## Established verification and governing baseline

- [NASA/TMBWG resource](https://tmbwg.github.io/turbmodels/), current home page,
  purpose, model list and verification/validation distinction reviewed. The
  [official NASA migration notice](https://www.nasa.gov/nasa-turbulence-modeling-resource/)
  confirms the new host. Exact SA-noft2 mathematics already reviewed/adopted
  are scoped in the [transport ledger](ENCLOSURE_SA_TRANSPORT_20261020.md), not
  implicitly extended to every listed model.
- [Flat-plate verification introduction](https://tmbwg.github.io/turbmodels/flatplate.html):
  nested-grid, matched-model and BC requirements reviewed. It is a future
  engineering-regime verification target, not a case the present closed-box
  molecular-Re <=20 research solver can claim to execute.
- [NASA wall-mounted hump](https://tmbwg.github.io/turbmodels/nasahump_val.html):
  case introduction and separation/reattachment/model limitations reviewed.
  Candidate validation beyond a flat plate; no dataset downloaded or correlated.
- [UIUC propeller database](https://m-selig.web.engr.illinois.edu/props/propDB.html):
  current description, volumes, coefficient conventions, measurement methods
  and geometry links reviewed. Later validation must pin a matched geometry,
  operating point, data version and rights. No raw propeller data was ingested.
- Existing finite-volume, pressure-adjoint, kinetic/thermal balance and sensible
  energy derivations remain in the [momentum](ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md),
  [stress](ENCLOSURE_SYMMETRIC_STRESS_20261020.md) and
  [CHT](ENCLOSURE_CHT_METHOD_20261020.md) records. Novel schemes must preserve
  these invariants or supply a separately justified replacement.

## Recent journal candidates: scope review, not adoption

| Publication and exact identity | Review actually performed | Candidate question / required comparison |
| --- | --- | --- |
| Ji, Shen and van Rees, *A fourth order sharp immersed method for the incompressible Navier-Stokes equations with stationary and moving boundaries and interfaces*, JCP556 (2026), 114806, online24 February2026; [DOI](https://doi.org/10.1016/j.jcp.2026.114806), [author-hosted paper](https://bpb-us-e1.wpmucdn.com/sites.mit.edu/dist/1/2096/files/2026/03/ji-2026.pdf) | Printed pp.1-2: abstract, introduction and method-outline scope only. Not a full algorithm/proof review. | Compare pressure as well as velocity error at equal cost near curved boundaries, then conjugate interfaces. The stated moving-boundary scope is one-way coupled; it does not establish general two-way FSI. No fourth-order method is implemented here. |
| *Time integration of cut-cell surfaces for geometric conservation, applied to scalar transport with moving interfaces*, Computers & Fluids 295 (15 June 2025), 106627; [DOI](https://doi.org/10.1016/j.compfluid.2025.106627) | Publisher search-index abstract/metadata. Direct page returned HTTP403; full method/proof not reviewed. | Does time-centering cut-face geometry improve moving-interface scalar/thermal conservation at equal work? Independently derive GCL, use manufactured moving-volume and heat-diffusion cases before adopting. |
| Yang, Scovazzi, Krishnamurthy and Ganapathysubramanian, *Simulating incompressible flows over complex geometries using the shifted boundary method with incomplete adaptive octree meshes*, JCP, [DOI](https://doi.org/10.1016/j.jcp.2025.114334); author preprint [2411.00272v3](https://arxiv.org/abs/2411.00272v3), 11 December 2024 | Journal search metadata and author-preprint abstract; no full numerical method review. | Compare boundary-error, shear/traction accuracy and scalability with body-fitted/cut-cell baselines. Shifted boundaries are not geometrically exact cut cells. |
| Koponen, Bhalla, Sprinkle, Wu and Tilton, *A direct forcing, immersed boundary method for conjugate heat transport*, JCP 538 (1 October 2025), 114135; [DOI](https://doi.org/10.1016/j.jcp.2025.114135) | Publisher search-index abstract/metadata only; full method not reviewed. | Evaluate discontinuous/contact/Robin interface treatment against analytical conjugate conduction and circular-Couette heat-transfer references. Immersed geometry alone does not prove conservative coupling. |

These are peer-reviewed method candidates, not existing SPIKE implementations.
Full mathematical review and independently authored derivation precede any
implementation. Publisher access limitations are recorded rather than implying
that an abstract supplied enough detail to reproduce a method.

## Current 2026 preprints: experimental candidates only

1. Galimberti, Nuca, Dalcin, Guardone and Parsani, *Entropy-stable moving-wall
   boundary conditions for the ALE formulation of the compressible Navier-Stokes
   equations*, [2608.25146v1](https://arxiv.org/abs/2608.25146v1), 25 August 2026.
   Reviewed abstract, HTML section outline, section2.5 balance and theorem4.1
   moving-wall reflection statement. Full proof/discretization not reviewed;
   appendices are not implementation inputs. Candidate for future compressible
   moving-boundary work, not a plug-in formula for the present incompressible
   MAC solver. Must independently verify metric/GCL identities, relative-wall
   energy flux, positivity, time integration and interface conservation.
2. Sayyari and Yamaleev, *High-order entropy-stable isothermal wall boundary
   condition for the compressible Navier-Stokes equations*,
   [2610.09249v2](https://arxiv.org/abs/2610.09249v2), revised16 October2026.
   Reviewed abstract, HTML section outline, section3 penalty/ballistic-energy
   statements and the stated thermodynamic positivity assumptions. Not a full
   proof audit. Candidate for a future compressible thermal-wall formulation;
   prescribed wall temperature is not by itself conjugate fluid-solid coupling.

Neither preprint is labeled peer-reviewed here. Their author-reported stability
and numerical results are research claims, not independently reproduced SPIKE
evidence. No entropy-stable/ALE implementation or performance claim is made.

## Adoption and evidence policy

Before selecting a candidate: pin version/sections/equations, separate physical
assumptions from discretization, independently derive SI conservation and
stability requirements, and predeclare analytical/refinement/independent/physical
acceptance. Compare total time and peak memory at matched error, not different
mesh accuracy. Keep model-form uncertainty distinct from algebraic convergence.

The present clean-room implementation work uses established equations and
SPIKE's own verified operators. No research implementation is copied,
translated or mechanically adapted. Physical engineering validation and
knowledgeable human numerical release review remain required.
