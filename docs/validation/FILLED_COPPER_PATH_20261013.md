# Filled copper path handling — 2026-10-13

## Scope

This note records the bounded handling of imported filled-copper paths that
encode holes by walking a connector to a hole, tracing the hole, and retracing
the connector in reverse. Exact reverse-edge cancellation removes those
connectors from the physical boundary without moving a source coordinate.

The retained Marble `+1V0` selection exposed five such paths. They encode 10,
30, 140, 159, and 125 holes, for 464 retained copper cutouts. Two other selected
zones follow the established ordinary-polygon path. These fixture observations
are diagnostic evidence for the selected source revision; they do not establish
whole-program board-size capacity.

## Two deliberately separate representations

`SourceFilledBoundary` supports source/contact evidence. It retains the original
coordinate sequence and exposes physical edges after exact bridge cancellation.
Its even-odd containment and tolerance checks consider physical edges only. The
type does not expose cell fragments and does not claim that a source is a valid
mesh domain. This lets contact-only evidence inspect imported paths that the
older normalizer also accepted without adding a new mesh-validity requirement
to unrequested full-board zones.

`FilledCopperPath` is the stricter meshing domain. It additionally requires
closed one-in/one-out physical rings, exact nonintersection, one containing
outer ring, opposing hole orientation, no nested holes, and representable
clockwise convex cell fragments. Invalid or over-budget topology fails closed;
no hole is silently filled and no positive fragment is intentionally dropped.

Both types are immutable sequences for source hashing and provenance. The
strict type is admitted only by the strict builder. Ordinary paths with no
exact reversed edge return `None` before the new source caps and continue
through the established simple-polygon path.

## Candidate indexes

`BoundarySpatialIndex` caches one canonical endpoint order per physical edge
for containment arithmetic while retaining each original directed edge for
contact predicates. It supplies conservative candidates only:

- A one-dimensional interval tree returns every edge whose raw closed y-range
  can contain the query ray. The unchanged strict y test and crossing
  expression decide parity.
- A balanced bounding-box tree covers both raw edge bounds and the derived
  range of every rounded nearest point
  `fl(a + fl(ratio * fl(b-a)))`, with `ratio` in `[0, 1]`. Non-finite rounded
  deltas or bounds use an unbounded axis.
- Tolerance query boxes use `nextafter(tolerance, +inf)` and outward-rounded
  `point ± radius` bounds. Every candidate still passes through the original
  distance predicate.
- A separate x-sorted index covers all original source vertices, including
  canceled bridge vertices, for contact evidence that explicitly queries source
  points.

The indexes have linear retained storage. They improve candidate selection but
do not establish a RAM reduction or a full-board runtime claim.

A warm same-process microbenchmark used the largest selected retained polygon
(`zone-57:In5.Cu:1`, 6,367 source points and 6,049 physical edges) and 200
seeded point queries at zero tolerance. Six alternating samples gave median
times of 0.2333579 s for the copied canonical linear predicate and 0.00240665 s
for the indexed predicate, or 96.96x for this candidate-query kernel. The full
200-result vectors matched before timing. Index construction, import, complete
contact evidence, meshing, solver work, and process-memory effects were excluded.
Raw configuration, samples, source hashes, fixture provenance, and qualification
are retained in
the unbundled local `boundary-index-microbenchmark.json` record. See the
[release evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

## Declared bounds

- Source vertices per component: 131,072, matching the existing parser limit.
- Holes in one strict domain: 4,096.
- Aggregate strict topology work: 134,217,728 active-list, nested-pair, and
  exact-ray point visits.
- Exact topology intersection predicates: 2,000,000.
- Cell-fragment work: 2,000,000 edge/slab visits.
- Returned fragments from one cell query: 65,536.
- Spatial-index edges and original points: 131,072 each.

The aggregate topology ceiling makes worst-case quadratic source geometry
explicitly bounded. Crossing, ambiguous repeated cancellation, duplicate
physical-edge multiplicity, open incidence, and resource exhaustion raise
typed errors rather than returning partial geometry.

## Verification

Focused tests cover square and slanted annuli, multiple holes, global reversal
and translation, bridge points inside copper and inside a hole, physical-edge
contacts, malformed crossings, nested holes, source and work budgets,
unrepresentable adjacent-float slabs, and area conservation through clipped
fragments.

An independent exact-area oracle checked 300 rotated-hole cell clips; all
matched, with maximum observed area error `3.269e-16 mm²`. Independent spatial
index review checked 10,800 indexed containment results against copied linear
predicates and 52,716 accepted-distance candidate supersets across 180 arbitrary
contours, finite exponents from -1074 through 1023, endpoints, random queries,
and threshold/`nextafter` tolerances. No mismatch was observed in those bounded
checks.

The retained-board profiler pins hashes for the filled-path, source-boundary,
spatial-index, hybrid ownership, topology, importer, zone-contact evidence, and
parser sources before and after each worker run. It can disable Python wall-stack
sampling independently and writes a bounded five-second heartbeat containing
the actual worker's Windows process-memory counters. Each result also records
the worker's resolved Python executable, full version, implementation, cache
tag, and platform; failed runs identify that provenance from the exact
`sys.executable` used to launch the worker. The earlier native access
violation remains cause-unknown; stack sampling is not identified as its cause.
The compact mesh result retains the complete connection-evidence accounting,
resource, and qualification sections while omitting the potentially large raw
record list. It binds that omission with canonical SHA-256 digests of both the
record list and the complete report.

## Dependencies and qualification

The implementation uses only the Python standard library and existing SPIKE
exact-dyadic topology helpers. No third-party source or examples were copied.
The retained fixture remains governed by its recorded CERN-OHL-1.2 provenance;
the new Python files use the repository's Apache-2.0 SPDX convention.

These paths remain bounded internal meshing and evidence helpers. They do not
change solver validation status, establish whole-program 10 GB or 32 GB board
capacity, or replace the required knowledgeable human review before release.
