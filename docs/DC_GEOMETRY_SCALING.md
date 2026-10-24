# Batched retained-tetrahedron geometry admission

Primary mathematical cross-check reviewed 24 October 2026, after the batch
implementation and scalar-equivalence tests were independently authored:
David Eberly, [*Intersection of Convex Objects: The Method of Separating Axes*](https://www.geometrictools.com/Documentation/MethodOfSeparatingAxes.pdf),
revision 20 June 2022, section 2 projection/translation discussion and the
opening mathematical statement of section 4 on face normals and cross-products
of edges from distinct convex polyhedra. Implementation listings were not used
to author, copy or translate this change. The numerical tolerance below is an
existing SPIKE admission policy, not an error guarantee supplied by that source.

The scalable tetrahedral DC profile still passes through the shared independent
solid-geometry validator. Compiler provenance does not bypass this audit. The
validator retains the existing AABB hierarchy, hierarchy-visit limit, exact
candidate count, comparison limit, separating-axis theorem, local projection
origin, tolerance, hanging-node audit, face-manifold checks, and ownership
topology checks.

For a candidate pair of tetrahedra, the separating-axis test uses the same 44
axes as the original scalar implementation: four face normals from each solid
and all 36 pairwise edge cross-products. Zero axes remain excluded. Projections
subtract the first tetrahedron's local origin before multiplication. A pair is
admitted only when at least one nonzero axis has overlap no greater than

\[
10^{-11}\max(\operatorname{span}(T_i),\operatorname{span}(T_j)).
\]

The performance change groups at most 4,096 already-enumerated candidates and
evaluates those identical axes with bounded NumPy arrays. It neither changes
the hierarchy nor prunes a candidate. The existing four-million candidate and
eight-million hierarchy-visit limits remain authoritative. A batch consumes
less than roughly 32 MiB for axes, projections, masks, and pair indices, within
the existing 512 MiB workspace ceiling; no persistent all-pairs array is formed.

On the retained reviewed-Marble target-4 mm request (28,758 tetrahedra), the
audit enumerated 677,226 SAT candidates and 2,264,632 hanging-node candidates.
The batched SAT phase took 22.45 seconds and the unchanged hanging-node phase
5.62 seconds on the review host. The prior scalar SAT phase had not completed
after 150 seconds on the same request. These are diagnostic timings, not a
portable runtime guarantee.

Independent tests compare the batched result and candidate counter against a
frozen scalar calculation for conforming grids and seeded translated/rotated
tetrahedron pairs. They also retain positive-overlap, comparison-budget, and
hanging-node rejection. This optimization does not establish mesh convergence,
full-board feasibility, electromagnetic accuracy, or production qualification.
The current projected-extrusion partition's cell requirement is not a proof of
the minimum tetrahedron count achievable by a different conforming 3-D method.
