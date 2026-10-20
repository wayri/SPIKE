<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Large retained-PCB mesher profile

Date: 2026-10-12. Status: bounded diagnostic failure; no production change is
recommended from this run.

## Scope and fixture

The profile used the retained BerkeleyLab Marble v1.4.4 native KiCad board at
`build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb`.
The file is 44,993,740 bytes and has SHA-256
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
The retained source is licensed under CERN-OHL-1.2. No upstream source code or
example implementation was read or copied for this work.

The working-tree mesher was
`python/spike_core/hybrid_mesh.py`, SHA-256
`c60b6d5e45e808db406ad53cd77a6e8293fbce77339e82a370bcbac0fcc0764c`,
with Git HEAD `537023f84e70ed0d45915c7ef2b5cdb858d18228`. The SHA identifies
the working-tree source and is more specific than Git HEAD in this dirty tree.

A separate selection scan imported the complete board and found 37,380 tracks,
5,272 pads, 3,664 vias, and 124 zones. The selected `+1V0` net contains 122
tracks, 43 pads, 58 vias, and 7 zones. All seven selected zone polygons passed
the current polygon-normalization precheck. This scan establishes the requested
input scope only; it does not establish that the timed mesher represented every
object.

## Configuration and resource bounds

`scripts/profile_retained_board_mesher.py` passes the complete imported design
to `build_hybrid_mesh`; it does not crop or mutate board geometry. Net selection
is performed by `AnalysisSpec(mode="dc", net_names=["+1V0"])` with:

| Setting | Value |
| --- | ---: |
| Track target | 2.0 mm |
| Zone target | 2.0 mm |
| `max_zone_cells` | 50,000 |
| `max_pad_cells` | 10,000 |
| `max_conductors` | 300,000 |
| Solver branch-admission memory | 2 GiB |
| Supervised process-tree memory limit | 4,096 MiB |
| Supervised wall-time limit | 180 s |

The fixture was copied byte-for-byte to a temporary directory under the
repository because canonical path traversal of the retained `build/` path was
denied inside the managed bounded worker. Both the original and staged copy
were checked against the pinned SHA before import, the basename remained
`Marble.kicad_pcb`, and the temporary copy was removed after the worker exited.
The exact cause of the path denial was not established.

The worker times import and `build_hybrid_mesh` without instrumentation.
During meshing, Python `faulthandler` writes all active Python stacks every five
seconds to an independent diagnostic log. A phase marker is atomically replaced
after import and after meshing. This is a wall-stack occupancy sample, not a
CPU-time profile; native calls that hold the GIL may be under-observed.

## Observed result

The changed diagnostic completed in 159.5923583 s, before its 180-second
deadline. Import completed in 8.1749705 s. The actual worker reported:

| Counter | Bytes | Approximate display |
| --- | ---: | ---: |
| Current working set after import | 300,814,336 | 286.88 MiB |
| Current working set after mesh | 327,458,816 | 312.29 MiB |
| Cumulative peak working set | 786,718,720 | 750.27 MiB |
| Current private usage after import | 1,327,792,128 | 1.237 GiB |
| Current private usage after mesh | 1,354,301,440 | 1.261 GiB |
| Cumulative peak pagefile usage | 1,821,466,624 | 1.696 GiB |

The peak counters are cumulative from worker start. The two current-memory
samples do not isolate parser allocation from interpreter, library, or mesher
allocation and must not be subtracted to claim a mesher-memory delta. The peak
remained below the 4,096 MiB process-tree limit.

The worker returned a mesh, but the run correctly reported `status=failed`:

| Geometry kind | Requested on `+1V0` | Meshed |
| --- | ---: | ---: |
| Track | 122 | 122 |
| Zone | 7 | 2 |
| Via | 58 | 58 |
| Pad | 43 | 43 |

The missing zone source IDs are `zone-13:F.Cu:1`, `zone-39:In2.Cu:1`,
`zone-43:In4.Cu:1`, `zone-57:In5.Cu:1`, and `zone-61:In6.Cu:1`.
Consequently the result is not a complete requested-geometry mesh and its
partial topology must not be used as an exact-output oracle, solver input, or
capacity result. The precheck that normalized seven raw imported polygons did
not prove the later typed evidence/mesher path would retain them.

The stack log contains 39,666 bytes with SHA-256
`76b072cab5d63c9c9f0f36fe64fa6736797077342efa78f13888049e950f7ab4`.
It contains at least 20 five-second samples. Retained inclusive frame counts
include:

| Frame | Samples |
| --- | ---: |
| `zone_pad_connection_evidence.py:99`, `_observes_contact` | 10 |
| `hybrid_mesh.py:417`, second `_polygon_is_simple` validation in `_normalize_filled_zone_polygon` | 9 |
| `hybrid_mesh.py:196`, `_point_in_polygon` | 7 |
| `hybrid_mesh.py:395`, first `_polygon_is_simple` validation in `_normalize_filled_zone_polygon` | 7 |
| `hybrid_mesh.py:197`, tolerance-distance generator in `_point_in_polygon` | 5 |

Counts are inclusive wall-stack observations and are not additive CPU
percentages. The two normalization call sites feed the quadratic edge-pair
loop in `_polygon_is_simple` (`hybrid_mesh.py:1114-1126`). The contact evidence
path is a second measured area, but the sample does not justify changing its
topology policy or source binding.

An earlier cProfile attempt reached its separate 300-second deadline after a
12.723-second import marker and returned no function table. It is retained only
as failed-method evidence. An earlier 86-second exploratory command combined
board import, per-net counting, and normalization of all selected polygons. It
did different work; neither value is comparable with the 8.175-second import
timing above.

## Retained evidence

The final diagnostic identified itself at `2026-10-12T16:46:35Z`. Its
structured result and raw stack log were written beneath the command's sandbox
temporary directory. Neither file survived that temporary-directory lifecycle;
a targeted exact-name search found no retained copy. The raw log's 39,666-byte
length and SHA-256 above come from the returned structured summary and cannot
now be independently rehashed. Exact partial-mesh node, branch, and cell counts
that appeared only in truncated console output are deliberately not
reconstructed.

The unbundled local `marble-profile/evidence-status.json` record documents this
artifact absence and the known run identifiers. The adjacent `manifest.json`
binds the retained status, this report, and the profiler source to SHA-256
values. There is no file presented as the missing final result or raw stack
log.

| Artifact | Retained SHA-256 or status |
| --- | --- |
| `scripts/profile_retained_board_mesher.py` | `1ef270d0e7f759a713d8bb9cc066ccb5e193dee48fdd7edb42aa11f824af10e2` |
| Unbundled local `marble-profile/evidence-status.json` | `cc839990277d30e19ccf112bc4f2541ad1242f2b068f2b40b6a32bad7ed96603` |
| Final structured JSON | Not retained; no hash available |
| Raw stack log | Not retained; returned summary reported `76b072cab5d63c9c9f0f36fe64fa6736797077342efa78f13888049e950f7ab4` |

Because a document cannot contain its own stable digest, `manifest.json`
records this report's digest after the report is finalized.

One overwrite-guard probe had a roughly 42-second tool-cell lifetime. Its exact
UTC start and end were not retained and cannot be recovered from unrelated file
timestamps. The probe created an existing output sentinel before invoking the
CLI. The CLI raised at its output-exists check before `_controller`, so it did
not stage the board, spawn a worker, import KiCad data, or mesh. Thus even if
the shell lifetime overlapped another benchmark, it did not run the Marble
workload. The unexplained delay is not attributed to a particular subsystem.

## Recommendation before implementation

Do not change production meshing yet. Geometry completeness is already false
on the chosen real-board scope, and a speed change must not hide that failure.

The smallest performance candidate is a local broad-phase rejection inside
`_polygon_is_simple`: precompute immutable edge bounds once, then call the
existing `_segment_intersection_points` only for edge pairs that cannot be
proven disjoint. This targets the sampled normalization stack while preserving
the established intersection predicate and pair order.

That candidate is numerically conditional, not ready to implement. A raw AABB
test can reject a pair that the legacy floating-point ratio calculation admits
under severe cancellation, near-parallel geometry, or tolerance-extended
endpoints. Any optimization must derive a conservative bound from the existing
rounded deltas, segment lengths, tolerance, and floating-point error. It must
fall back to the unchanged predicate for non-finite, poorly scaled,
near-parallel, or boundary-close pairs. A per-build memo for byte-identical
immutable polygons is safer, but this run does not show enough repeated
identical normalization work to expect a material benefit.

Before production use, compare the candidate directly with the original
predicate over seeded extreme-scale, cancellation, degenerate, intersecting,
and non-intersecting segments and simple/self-intersecting polygons. Then
require canonical equality of the complete zone-pad evidence report. The
full-board gate remains equality of requested and meshed geometry counts and
source IDs, an untruncated mesh, identical serialized topology/issues hashes,
and focused electrical conservation. No optimization should be promoted until
the five missing Marble zones are resolved or explicitly fail admission before
partial mesh output. This evidence does not establish the 10 GB or 32 GB
whole-program goals.

## Reproduction

The bounded command is:

```powershell
.venv\Scripts\python.exe scripts\profile_retained_board_mesher.py `
  --output "$env:TEMP\spike-large-pcb-profile-20261012.json"
```

The script refuses to overwrite an existing output, validates finite sizes and
resource limits plus the hexadecimal source hash, and preserves phase and
wall-stack summaries for bounded timeout and worker-failure results. The
evidence above came from one wall-stack run; it was not repeated.

## Subsequent correction

The [2026-10-13 filled-zone correction](MARBLE_FILLED_ZONE_FIX_20261013.md)
resolves the five omitted source-filled components and retains all 464 cutouts.
Three complete runs agree on cell topology and connectivity; board-wide contact
evidence accounts for every candidate record. The newer profiler persists
evidence under the repository root, adds live worker-memory counters, and records
runtime/source hashes. Use the newer report's reproduction command. This older
partial workload remains diagnostic history, not a complete timing baseline.
