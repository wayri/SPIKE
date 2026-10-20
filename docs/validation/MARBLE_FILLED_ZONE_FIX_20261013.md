<!-- SPDX-License-Identifier: Apache-2.0 -->
# Retained Marble filled-zone completeness fix

Task date: 2026-10-13 (Asia/Calcutta). Scope: source-filled planar copper
meshing and conditional zone-pad contact observation; no physics qualification
or whole-program capacity promotion.

## Defect and source evidence

The retained Marble v1.4.4 board is SHA-256
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
The complete board is imported; `AnalysisSpec` selects the complete `+1V0` net
with 122 tracks, seven filled zones, 58 vias and 43 pads. No design objects
are cropped or removed before meshing. The upstream fixture remains under its
recorded CERN-OHL-1.2 license.

The original conductor mesher omitted five zones because it required one
simple boundary. Native filled paths encode cutouts using exactly retraced
bridges. Independent exact-coordinate analysis found valid disjoint loops,
not malformed copper: one outer ring and 10/30/140/159/125 holes in the five
omitted components, respectively. There are 464 retained cutouts in total.
The two other selected components are ordinary simple polygons.

Durable baseline evidence is
the unbundled local `baseline-after-import-fix.json` and its phase,
raw-stack and selected-polygon sidecars. All five actual warnings were
`SPIKE-BE-MESH-W-0002: <source_id> has no usable simple filled copper polygon.`
The baseline returned only two zones, so its 136.705-second mesh timing is a
partial-workload observation, not an equal-completeness performance reference.

The initial rerun also exposed mixed importer diagnostics: legacy strings and
structured arc records coexist. The adapter now selects structured arc records
only from mappings, retains all diagnostic entries, and preserves imported
geometry. The regression reproduced the crash before the fix.

## Implementation and invariants

- Exact dyadic integer topology separates true intersections from proximity.
  A common power-of-two denominator preserves each represented coordinate,
  ordering and orientation sign. Endpoint bounds prune disjoint edge pairs.
  The existing floating area admission gate remains separate.
- Strict filled domains cancel exact reversed bridge edges, validate physical
  closed rings, nonintersection, nesting and winding, and retain every source
  coordinate. Vertical slabs emit convex cell fragments outside the cutouts.
  Only identical supporting edges/clip lines allow adjacent slab coalescing.
- Physical parity/contact tests exclude bridge edges from boundary-distance
  membership. Canonical endpoint ordering preserves reversal consistency.
- Hole-cell nodes remain distinct. Positive shared faces establish graph
  links; a centroid chord that exits copper routes through its real face.
  New hole-domain face/containment tolerance is capped at 1e-10 mm to prevent
  the ordinary contact band from bridging narrow physical voids. Ordinary
  simple-polygon meshing retains its previous tolerances.
- Input and retained hole-cell areas are checked against source copper area
  with tolerance `max(1e-8 mm^2, source_area * 1e-9)`. Admission/work failures
  and area failures return explicit failed issues and clear conductive
  branches; they cannot certify a partial conductor graph.
- Contact-only evidence uses a separate source-boundary view, retains all
  records and hashes, and does not invoke mesh-domain validation. Its existing
  `source_filled_connection_evidence_only` qualification and false
  `physics_ready`/`solver_ready` flags remain unchanged. Strict mesh admission
  recognizes only a validated filled domain.

There are no new dependencies. Implementation, derivation and synthetic test
oracles are original SPIKE work; no external implementation was inspected or
adapted. Interpolated mesh vertices, area gates and electrical discretization
remain floating-point approximations. This is not an exact CAD/FEM solver.

## Admission and conditioning

Source-filled input allows 131,072 vertices per component, matching the existing
native parser, and at most 4,096 holes. Exact predicate and aggregate topology
work budgets bound strict validation. Per-cell slab/fragment limits and the
builder's retained-fragment/RAM admission remain enforced. Ordinary paths with
no retraced bridges bypass the new hole-specific admission limits.

Unrepresentable slab interiors, collapsed clip events, ambiguous physical-edge
multiplicity, genuine crossing/nested unsupported contours, and work exhaustion
fail explicitly. No tolerance inflation, hole filling or arbitrary outline
repair is used to manufacture completeness. Existing separate physics/solver
unsupported states remain applicable.

## Verification

Before the topology fix, targeted long-edge near-miss and short perpendicular
crossing regressions failed in opposite directions. Both now pass. The original
ordinary duplicate-cleanup and admission behavior is retained.

Independent exact oracles covered 250 topology cases, 300 rotated/slanted
hole-cell clips, and 60 bbox-pruning cases. Clipped areas agreed with Fraction
reference areas within 3.3e-16 mm^2. Tests cover reversed source paths, physical
hole-boundary contacts, bridge-only false contacts, unique owning nodes,
connected copper around a hole, narrow-hole protection, explicit work failure,
unchanged provenance and retained report records. The focused hybrid group
passed 52 tests; the existing contact-evidence group passed six tests.

The first integrated run represented all seven selected zones and conserved
their areas, but still failed the overall gate because board-wide contact
evidence unnecessarily invoked the new mesh validator on unrelated roughly
102,000-vertex GND paths. That result is preserved as
the unbundled local `fixed-marble-profile.json` and is not accepted as a
successful benchmark. The separate source-observation view fixes that coupling.

Two complete runs now retain all 122 tracks, seven zones, 58 vias and 43 pads:
`fixed-marble-indexed-stacks.json` (CPython 3.14.2 identified by retained stacks)
and `fixed-marble-project-runtime.json` (explicitly pinned project CPython
3.12.9). Both return 27,170 nodes, 43,653 branches and 31,824 cells, no truncation
or error issues, and identical cell-topology and connectivity hashes. All 464
cutouts remain represented. Maximum retained copper-area error is
`3.292370820418e-10 mm^2`. The existing roundrect bounding-dimension approximation
warning remains.

The isolated project-runtime run took 6.954 seconds to import and 215.794
seconds to mesh (226.161 seconds supervised wall time). Actual worker OS peak
counters through meshing were 1,090,719,744 working-set bytes (1.016 GiB) and
2,117,693,440 private/pagefile bytes (1.972 GiB), under the enforced 4 GiB worker
cap. These are observations from this selected-net workflow, not whole-program
RAM use or a RAM-saving comparison. The 3.14 run took 142.159 seconds to mesh;
different runtimes and partial baseline completeness preclude an equal-workload
speedup claim.

Earlier failures remain retained: `fixed-marble-final-profile.json` exited with
a Windows access violation, and `fixed-marble-indexed-profile.json` reached its
300-second limit. Neither is accepted as successful evidence; the underlying
worker-exit cause remains unknown. Success with and without stack sampling does
not identify sampling as the cause.

The boundary-only warm-query kernel measured a 96.96x median improvement on
200 deterministic queries of one retained 6,367-point component. Construction,
import, full contact reporting and meshing are excluded; see
`boundary-index-microbenchmark.json` and the filled-path derivation. This is
not a whole-board speedup.

Internal failed issues distinguish `FILLED_COPPER_PATH_BUDGET` (reduce requested
resolution/work or review resource admission), `FILLED_COPPER_PATH_MESH_FAILED`
(inspect unsupported or unrepresentable clipping), and
`FILLED_COPPER_PATH_AREA_FAILED` (reject the conductor graph and inspect area
conservation). Each clears conductive branches and retains its failed status.

The concurrent consistency run `fixed-marble-evidence-validation.json` also
completed with the same topology/connectivity hashes and unchanged runtime
source hashes. Its full-board evidence accounts for 14,854 candidate records:
476 contacts, 14,378 no-contact observations, zero unsupported records. All
5,272 pads and 122 source-filled zones were admitted; the canonical report and
record digests are retained. This observation-only report keeps
`physics_ready=false` and `solver_ready=false`.

Architecture/control-standard checks, TypeScript, the high-layer board parser,
assembly handling, workspace lifecycle and multiboard study regressions passed.
Rust host tests passed 54 tests with one ignored. The complete project-runtime
Python suite ran 3,675 tests in 1,070.394 seconds, with 69 skips and zero failures
or errors (`full-python-regression.log`). All pinned runtime source hashes still
match the consistency run. Python compilation and focused diff checks passed.
The 10-20-board / 10 GB available RAM target remains a separate whole-program
acceptance workload; neither the selected-net fixture nor the multiboard
regressions establish that capacity.

## Reproduction

```powershell
.venv\Scripts\python.exe scripts\profile_retained_board_mesher.py `
  --no-faulthandler --timeout-s 300 --process-memory-limit-mb 4096 `
--output "$env:TEMP\spike-fresh-marble-profile.json"
.venv\Scripts\python.exe -m unittest discover -s tests\python -v
.venv\Scripts\python.exe scripts\check_architecture.py
```

The profiler refuses to overwrite evidence and retains full issues, optional
raw stacks, live memory counters, source geometry and runtime source hashes
before and after execution. The compact evidence summary retains all accounting
and qualification fields plus record/full-report digests. A repeat run performed
alongside the regression suite checks consistency and accounting; its timing is
not used for performance comparison.
Knowledgeable human numerical review remains required before release.
