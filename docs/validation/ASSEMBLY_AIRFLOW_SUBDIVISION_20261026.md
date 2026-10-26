<!-- SPDX-License-Identifier: Apache-2.0 -->
# Assembly airflow: conforming CFD subdivision, 26 October 2026

Status: experimental geometry preparation; no continuum, measured-device or
release qualification. This change retains the governing OpenFOAM CHT equations
and every existing mesh/execution/result gate.

## Problem and method

The original five-region ESP32 polygon-prism case passed positive tetrahedron
volume, closure, face addressing and face-tet tests, but failed OpenFOAM v2606
`checkMesh -allRegions -allTopology -allGeometry`. Every rejected solid cell was
also in the native `twoInternalFacesCells` set: board 51, U1 9, U41 16, U61 11.
Air had 148 rejected determinants, including all 142 two-internal-face cells.
This distinguishes insufficient independent internal-face directions from a
malformed tetrahedral mesh. Six additional air cells were poorly conditioned.

The mesher now performs Gmsh 4.15.2 volume-only Netgen optimization. A fail-closed
before/after comparison checks every surface-node coordinate and every surface's
element connectivity. Existing CAD-volume and source/region admission remains.
The admitted tetrahedra are then partitioned into four conforming convex
hexahedra before ordinary polyMesh export. Original vertices stay unchanged;
new shared vertices are edge midpoints and face centroids keyed by sorted source
vertex identities. Each parent has one cell centroid. No cuboid approximation,
boundary projection, coordinate snapping or tolerance relaxation is introduced.

The [independent owner derivation](ASSEMBLY_AIRFLOW_SUBDIVISION_DERIVATION_20261026.md)
derives child i by the barycentric inequalities
lambda_i >= lambda_j. These four closed convex regions cover the parent and
have disjoint interiors. Each contains six flag simplices, each with parent
volume fraction (1/2)(1/3)(1/4)=1/24, so each hex has volume V/4. Each original
face becomes three coplanar quadrilaterals of area A/3. Shared source vertex
keys and canonical summation produce identical interface coordinates from both
regions. This independent derivation was supplied by the integrating reviewer
separately from the implementation and executed checks.

All geometry stays in millimetres until the existing mm-to-m export. Recomputed
parent region volumes continue to control q'''=P/(1e-9 V_mm3), retaining watts.
The final global CFD mesh must satisfy the caller's existing max_cells and
max_vertices: 4N cells, not N, are charged. No automatic budget increase occurs.
Cancellation is checked during subdivision; worker process cancellation and
native execution limits remain owned by the existing runners.

## References and clean-room boundary

- [Gmsh 4.15.2 manual](https://gmsh.info/doc/texinfo/), sections 6.4
  (`gmsh/model/mesh/optimize`, Netgen method) and 10.2 (element ordering), reviewed
  26 October 2026. The installed Python API and DLL are hash-admitted by the
  existing local-development runtime; distribution qualification is unchanged.
- [OpenFOAM mesh description](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.1-mesh-description),
  sections on face ownership, ordering, closed cells and geometry, reviewed
  26 October 2026. Actual acceptance used v2606 build `_481094f-20260618`.

The barycentric derivation, converter, tests and prose are independently
authored. No external implementation, source code, mesh or test fixture was
copied or adapted. References describe API and geometric contracts, not proof
of this implementation's validity. Convexity/partition mathematics does not
guarantee good floating-point conditioning or a passing native mesh.

## Executed evidence

Evidence directory: `artifacts/unified-transient-20261026/exact-cad-review/`.
Large cases are under `D:/SPIKE-unified-transient-20261026-temp/`.

- `original-topology-diagnosis.json`: failed/native topology-set comparison.
- `subdivision-checkMesh.log`: subdivision without Netgen passed all four
  solids, but air still failed two determinants (minimum 0.0007700566454).
- `exact-cad-optimized-subdivision-checkMesh.log`: optimization plus subdivision
  passed all five strict region checks; no failed mesh checks. Air minimum
  determinant 0.005773007742. Solid minima 0.01518584986, 0.03626702244,
  0.09306422669, 0.09771993508. All paired AMI weights were one.
- `optimized-geometry-invariants.json`: all 2,032 original exterior/interface
  triangle coordinate-and-region sets match exactly before/after optimization;
  no triangles added or removed. Region-volume relative changes <=4.22e-15.
  6,160 optimized tets become 24,640 CFD hex cells.
- Five subdivision regression checks independently verify affine/sheared
  tetrahedron child volumes with a convex-hull oracle, barycentric inclusion,
  three equal-area shared interface quads, immutable source/region identities,
  final budgets, cancellation and optimizer surface-corruption rejection.
  Existing three-refinement source-power checks
  retain 3.25 W and 6.5e9 W/m3. The focused four-module suite passed 22 tests.
- `python scripts/check_architecture.py` passed.
- A first CHT attempt retained the original dt=0.02 s and failed after excessive
  Courant numbers (maximum 339.8). `optimized-cht-summary.json` preserves that
  failure. The product case explicitly requests dt=0.0002 s, end=0.02 s and
  50,000 vertices (the final subdivision correctly rejects the old 20,000
  vertex budget). The native solve reached the requested final time and entered
  postprocessing, but a WSL directory-probe timeout prevented a returned result.
  A managed retry timed out at 180 seconds before a completed mesh-check receipt.
  Direct Linux-timeout and PowerShell checks printed all five `Mesh OK` blocks
  and then timed out before normal termination; return 124 remains a failure.
  An explicit `-time 0` strict check subsequently completed with return zero
  and all five region passes, isolating default saved-time scanning overhead.
  All 15 bounded latest-time postprocessing commands then completed with return
  zero. The normal field importer returned `completed`: 24,640 temperature and
  heat-flux samples, 18,920 velocity and pressure samples. The recovery receipt
  is `recovered-product-cht-summary.json`; full fields are
  `D:/SPIKE-unified-transient-20261026-temp/exact-cad-product-case-bounded/recovered-cht-result.json`.
  This is recovered native execution evidence, not an uninterrupted managed
  runner success; the existing runner's saved-time scanning remains unchanged.

These five-region source shapes are the original unsnapped polygon prisms,
including the board chamfers; component heights remain declared proxies. They
must not be described as retained package STEP geometry.

## Actual STEP investigation and remaining limits

`installed-step-provenance.json` pins installed KiCad 10 alternative models.
They are explicitly alternative bytes, not STEP bytes retained by the ESP32
board, which references WRL basenames. Their file headers carry CC-BY-SA 4.0
with the KiCad electronic-design exception. No vendor model is copied into the
repository or bundled release by this work.

U41 SOT-223 SHA-256:
`77ad6dbacc493cb619c728f26d2ddcf461eb0feb6b977b47d01d51e67016f654`.
U61 QFN SHA-256:
`5fa713ea46b36980895812ed853577889b7cb06d275041a39b99bc0be305dc79`.

Both pass one-closed-solid STEP admission. Combined rotation and translation
through existing OCC rotate/translate causes a native access violation during
fragmentation. U41 identity placement and translation-only placement mesh
successfully. Post-placement OCC synchronization does not fix the rotated
case. The available WSL installation has neither a Gmsh executable nor Python
module, so no independent Linux backend comparison was performed or installed.

Translated actual U41 geometry passed CAD-volume admission (mesh 37.61396775 mm3
versus CAD 37.72417469 mm3), but the resulting CFD mesh failed both region gates:
278/325 determinant failures and 168/120 low-interpolation-weight faces. Thin
lead details produce a minimum subdivided edge of 7.5 micrometres and solid
aspect ratio 145.3. Reducing only minimum size from 0.15 to 0.01 mm leaves the
6,375-tet mesh unchanged. This disproves that simple sizing remedy. Actual STEP
CFD execution remains rejected; targeted source-feature sizing or another
separately verified mesh strategy is needed. No true-STEP field is fabricated.

No mesh/time convergence study, measured validation, full energy audit or
knowledgeable human numerical release review is established here. A successful
mesh is necessary but insufficient for a stable or physically accurate solve.
