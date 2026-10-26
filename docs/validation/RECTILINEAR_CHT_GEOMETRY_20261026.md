<!-- SPDX-License-Identifier: Apache-2.0 -->
# Declared cuboid CHT geometry and native streamline export

This is a post-implementation independent topology review of the new geometry
adapter, not a new fluid or thermal discretization. The existing OpenFOAM case
writer and OpenCFD v2606 CHT solver remain responsible for the governing solve.
No third-party implementation was copied or translated. Source geometry,
package heights, materials and powers remain declared approximations.

## Independently derived geometry and source invariants

Let strictly increasing planes X_i, Y_j and Z_k include every declared solid
boundary. Their Cartesian intervals partition the surrounding domain into
cells C_ijk. Because each solid face lies on one of these planes, a cell cannot
straddle a declared solid face. Its interior therefore has one solid owner or
belongs to air. Reject overlapping solid interiors. Shared boundary planes have
zero volume and do not create duplicate physical volume.

For each cell, V = dx*dy*dz. Input lengths in mm require V_m3 = V_mm3*1e-9.
The sum of all cell volumes must equal the domain volume; the sum over a solid
must equal its declared cuboid volume. Fluid and solid ownership sets are
disjoint. This proves geometric exclusion for the declared proxies, not for an
unavailable or simplified CAD surface.

Two adjacent cells of the same owner produce one internal face with opposite
outward normals. Cells with different owners produce paired region-boundary
faces using the same vertices and opposite orientation. Exterior faces occur
once. These are the required cancellation/closure invariants for the existing
finite-volume writer. A digest establishes identity, not physical validity;
the adapter's legacy `qualified` evidence flags refer only to admitted mesh
topology/provenance and must not become production qualification.

For prescribed solid power P W, use q''' = P/V_m3 W/m3 in the selected source
zone. Then sum(q'''*V_cell) = P for a complete partition. This exact source
integral is independent of refinement. It does not prove the transient energy
balance of the subsequent solver run. The new adapter does not change the
existing continuity, momentum, fluid-energy or solid-conduction operators.
Interfaces retain the existing perfect thermal contact assumption: matched
temperature and opposite outward conductive heat flux. Finite contact
resistance, radiation and fan-blade rotation are not added here.

Thin one-cell passages can fail the solver's stricter geometric quality checks
despite positive cell volumes. Positive volumes alone are insufficient. Require
one successful `checkMesh -allRegions -allTopology -allGeometry` result per
region and reject any reported nonzero failed-check count, even if the utility
returns exit code zero. The executed example retained these gates and refined
its air grid before obtaining five successful region checks.

## Streamline and playback boundary

At each actually written U/T time, the native OpenFOAM `streamLine` function
samples the frozen velocity field and temperature along its own mesh-aware
tracks. SPIKE converts returned positions from m to mm and computes speed as
sqrt(Ux^2+Uy^2+Uz^2), retaining K and m/s scalars. It does not reconstruct a
complete Cartesian fluid grid across obstacles. VTP array lengths, offsets,
connectivity, finite values and output budgets are admission boundaries.

Moving viewport markers parameterize these saved curves by display arc length.
Their speed is presentation speed. They are not transient particle trajectories,
and the source-frame time remains separately visible in the shared player.

## Reviewed primary references and evidence scope

- OpenCFD user guide, section 4.1.2, [polyMesh description](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.1-mesh-description): face/owner/neighbour representation.
- OpenCFD v2306 documentation, [streamLine](https://doc.openfoam.com/2306/tools/post-processing/function-objects/field/streamLine/): native velocity-driven tracking and requested-field sampling.
- OpenCFD user guide, [standard solvers](https://www.openfoam.com/documentation/user-guide/a-reference/a.1-standard-solvers): the existing multi-region CHT solver's role.

The indexed official documentation excerpts were reviewed on 26 October 2026;
direct page fetches returned HTTP 403. No source-code guide was opened. The
documentation version above is not represented as v2606 source inspection.
Compatibility evidence comes from the actually executed v2606 utility and CHT
runs, retained in `artifacts/unified-transient-20261026/cfd`.

Focused tests cover region volume/ownership, interface pairing, source power,
resource bounds, immutable inputs, failed mesh admission, malformed VTP data,
and inlet-seed orientation. The obstacle and baseline runs passed their mesh
gates and returned native fields/curves. Their different meshes confound any
quantitative attribution of the comparison to obstacles alone. No mesh/time
convergence campaign, experimental correlation or full transient energy audit
was performed. Exact retained-STEP tetrahedra remain rejected by the observed
determinant checks. Knowledgeable human numerical review and production
qualification remain open.
