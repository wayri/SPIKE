# Localized board-volume partition

Primary API provenance reviewed 24 October 2026: Shapely 2.1.2
[`STRtree`](https://shapely.readthedocs.io/en/2.1.2/strtree.html), construction and
`query` index/2D bounding-box semantics, and
[`constrained_delaunay_triangles`](https://shapely.readthedocs.io/en/2.1.2/reference/shapely.constrained_delaunay_triangles.html),
polygon-edge constraints and GEOS requirements. Public APIs are used; external
implementation source, examples and fixtures were not copied or translated.
The geometric ownership/coverage derivation below and tests are independently
authored. Exact subject-matter conductor assumptions remain in the RT0 method.

`dc_board_partition.partition_board_volumes` is an experimental geometry-only
preparation step for the supplied tetrahedral DC model. Coordinates and target
lengths are millimetres. It does not infer copper, contacts, materials, nets,
barrels, or source identities.

The legacy board-volume compiler constructs one planar arrangement from every
selected footprint and tests every arrangement atom against every volume. That
is conservative but makes unrelated layers and disconnected islands share the
same planar and axial cuts. The localized method first explodes supplied
Polygon and MultiPolygon footprints into retained components. An exact spatial
query links only components that require a common mesh:

* a positive-area horizontal interface at an equal authored z endpoint; or
* a positive-length lateral interface over a positive z overlap.

Different nets at either interface are rejected. Positive-volume overlap is
also rejected. Connected interface components are then noded and polygonized
independently. Finite contact boundaries join only the one supplied component
that completely covers them. An STRtree limits ownership checks to footprints
whose bounds meet each arrangement atom; exact `covers` and intersection tests
still decide ownership.

Each local atom is triangulated with Shapely's constrained Delaunay operation.
The established common-edge midpoint refinement is applied to the resulting
straight triangles. Every triangle retains the exact source-volume owner set.
Each conforming component uses the union of its owners' authored endpoints and
target-spaced interior z planes, so lateral interfaces receive identical axial
cuts. Triangular prisms are emitted only where that triangle's owner occupies
the interval. A downstream compiler can use the established consistent
three-tetrahedron prism split.

Every triangle also retains the contact identifiers of every complete contact
atom. This lets a volume compiler select finite exterior faces from the
arrangement's authored classification instead of repeating a binary64
polygon-on-triangle predicate after triangulation.

For contact atoms, “complete” is an area-support statement. Polygonization can
interpolate a boundary vertex one binary64 unit onto the exterior side even
when the atom interior and its entire positive area belong to the contact. The
classifier therefore requires an interior representative point covered by the
contact and an exactly zero directional outside area. It uses no distance or
area tolerance. A positive-area straddle is rejected, and the reconstructed
whole contact still passes the topology and symmetric-difference audit below.

For source footprint \(P_i\), the method reconstructs
\(\widehat P_i=\bigcup_{i\in s_k}T_k\) from triangles whose signature contains
owner \(i\). Admission requires equal component and hole counts, a positive
counterpart for every component, and

\[
  |P_i\mathbin{\triangle}\widehat P_i|\le
  128\epsilon\max(|P_i|,\operatorname{span}(P_i)^2).
\]

Directional omitted and excess areas and the admitted bound are returned for
audit. No geometry repair, coordinate rounding, buffer operation, sliver
removal, component dropping, or tolerance-based welding is performed.

Work is bounded before solver allocation: at most 4,096 volumes and contacts,
10,000 polygon components, four million interface and ownership checks, and
the caller's tetrahedron budget. The default profile retains the 5,000-cell and
100,000-boundary-vertex ceilings. Only `scalable=True` admits an explicitly
requested maximum through 50,000 cells and 250,000 boundary vertices; both
profiles also limit boundary vertices to 40 times the requested cell budget.
A budget failure returns no partial mesh. The helper remains experimental and does not
establish full-board completeness, contact equipotentiality, AC behavior,
thermal ownership, or production qualification.
