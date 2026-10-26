<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent tetrahedron partition derivation

Integrating-reviewer derivation, 26 October 2026. This argument was derived
separately from the converter implementation, then supplied to its author.
It establishes geometric partition identities, not CFD accuracy or release
qualification. Execution evidence is in
[the implementation record](ASSEMBLY_AIRFLOW_SUBDIVISION_20261026.md).

For a nondegenerate tetrahedron with vertices v0,...,v3, let lambda0,...,lambda3
be its affine barycentric coordinates. Define child Hi by lambda_i >= lambda_j
for every j. These are intersections of convex half-spaces with the parent.
Every point has a maximum coordinate, so the children cover the parent; their
interiors are disjoint, with ties confined to planes of zero volume.

Hi has eight corners: vi, its three incident edge midpoints, its three incident
face centroids, and the parent centroid. Its six planar faces therefore bound
a convex hexahedron. For distinct i,j,k,l, the flag simplex
[vi,(vi+vj)/2,(vi+vj+vk)/3,(vi+vj+vk+vl)/4] has volume V/24: an affine map to
the reference tetrahedron gives determinant (1/2)(1/3)(1/4). The six orderings
of j,k,l partition Hi, giving child volume V/4. This proof is invariant under
any nonsingular affine transformation, including shears.

Each original triangular face is partitioned into three coplanar corner
quadrilaterals. Each comprises two flag triangles of area A/6, hence area A/3.
The internal face shared by Hi and Hj is the quadrilateral consisting of their
edge midpoint, the two incident face centroids and the parent centroid. It lies
in lambda_i=lambda_j; the adjacent cells require opposite outward normals.

Conforming assembly requires globally canonical edge and face identities,
including across region boundaries. Sorted original vertex IDs and an identical
summation order produce the same floating-point coordinates on both sides.
Parent centroids are local to their parent cells. New points are convex
combinations, so no point leaves the parent and no solid exclusion boundary
is displaced. This is subdivision, not geometry healing or approximation.

Four children consume four cells of the caller's final budget. A conservative
preallocation bound for N parents is original vertices +11N new vertices and
18N faces before shared-entity deduplication. Existing resource limits must
reject excessive final meshes rather than silently increasing themselves.

Coordinates stay in millimetres before export. Volume conversion to cubic
metres multiplies by 1e-9. A region's constant volumetric heating remains
q'''=P/(V_mm3*1e-9) W/m3, because subdivision preserves its volume and region
membership; summing q''' times child volume retains source watts.

These identities assume exact arithmetic and nondegenerate parents. They do
not promise acceptable aspect ratios, interpolation weights, determinant
quality or numerical conditioning. Floating-point checks, optimizer surface
invariance, signed-volume checks and strict native mesh admission remain
necessary. The observed two failed air cells without optimization, and failed
thin STEP lead cells, are counterexamples to any universal quality claim.

Independent verification oracles include an affine/sheared reference parent
with child volume V/4, oriented-face/divergence volume, unchanged boundary
coordinate sets, paired interface orientation and total source power. The
converter cannot validate itself by comparing two copies of its own output.

Primary context: [Gmsh 4.15.2 manual](https://gmsh.info/doc/texinfo/gmsh.html),
mesh optimization API (Netgen) and element ordering, and the
[OpenFOAM mesh description](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.1-mesh-description).
The latter's indexed excerpts were available; direct retrieval was denied.
No external implementation was copied. These references establish API and
mesh contracts; the partition proof above is independently authored. Actual
execution used OpenFOAM v2606, as recorded in the implementation evidence.
