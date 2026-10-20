<!-- SPDX-License-Identifier: Apache-2.0 -->
# Gamma viewport optimization, 2026-10-18

## Scope and source

This pass targets the current `0.3.12-gamma.1` workspace, verified against
`app/package.json`, the Tauri configuration and the compiled gamma host log.
It changes presentation work and resource ownership, not physics, source
geometry, analysis qualification, saved fields or undo depth. Existing unrelated
working-tree edits were preserved. No release was installed or published.

## Changes and evidence

### Warm exact picking

`BoardViewport.tsx` formerly concatenated both complete picking arrays before
checking whether its spatial index was current. Large indexed queries now read
the two lengths and concatenate only when rebuilding the index. Candidate
construction, bounds, revision invalidation and final exact raycasts are
unchanged. Small-scene fallback preserves every object in its original order.

`test-viewport-pick-allocation.mjs` extracts and executes the actual production
closure with 20,000 Three.js objects. Across 60 warm queries, the retained
pre-change source traversed the source arrays 120 additional times (1,200,000
object references); the new source performs zero warm source traversals. Tests
also move an object, increment the revision, verify refreshed bounds and exercise
the complete small-scene fallback. The before source fails this regression
(`actual=122`, `expected=2` total array traversals); the current source passes.
This measures repeated source work, not whole-app RAM or event latency.

### Assembly 2D navigation

`AssemblyLayoutViewport.tsx` memoizes the parsed artwork, exact net hit targets
and component hit targets. Per-occurrence source/layer presentation is prepared
independently of the camera viewBox, and focus callbacks/empty defaults remain
stable. Camera updates can therefore reuse those trees. Layers, opacity, source
alignment, occurrence/source identity, linked nets, filters, vias and callbacks
still invalidate the relevant presentation. Selection dimming/order and
view-dependent net labels remain outside these memo boundaries.

Existing rendered-markup tests pass for source alignment/fallback, transforms,
per-occurrence net identity, source layers, picking and Fit/Focus. Independent
read-only review found no omitted input or stale callback in this delta.
The new browser fixture `scripts/viewport-pan-preview.html` bundles and type
checks, but its incremental 20-board run remains **unexecuted** because UI
automation stopped. No measured 2D speedup or frame-rate claim follows from it.

### Imported scene lifetime

`sceneResourceCache.ts` now discovers textures inside shader uniforms and
uniform groups, including aliased containers, plus background/environment
textures in nested Scenes. Independent cloned materials retain shared source
texture references, and accounting/disposal includes those resources. A
source/destination pair guard preserves aliases while terminating cycles.

The synthetic 64-occurrence test retains 64 independent shader materials and
one shared shader texture object. Three tracked textures, including a nested
Scene texture, are accounted for and disposed exactly once after final release.
The fixture accounts for 140 decoded texture bytes. Three.js may still allocate
transient texture clones before references are restored; zero clone allocation
is not claimed. Existing LRU, late-load, cancellation and sibling-lifetime tests
remain passing.

## Validation

Focused exact-picking, large-scene, assembly layout/handling, workspace lifecycle,
multiboard study and parser checks passed. TypeScript, architecture/control
standards, the gamma frontend production build and the native gamma development
build passed. Cargo reported 70 passed and one ignored. The production build
still reports its existing large-chunk warning; this pass does not qualify cold
startup time. The optional browser fixture also passes its separate strict
TypeScript check; its runtime results remain pending.

Full Python discovery ran 4,102 tests in 852.955 seconds, with 69 skips and one
failure, zero errors (`python-tests.log`). The failure was
`test_parity_backlog.test_current_coverage_and_pinned_fixture`: the running test's
loaded expectation ended at `SI07-S06`, while the ledger included `SI07-S07`.
The on-disk test now includes `SI07-S07`; its focused group passes all 14 tests
(`parity-recheck.log`). The traceback's refreshed source line and its loaded
expected value differ, consistent with the test/ledger changing during this
long run. Neither file was edited by this viewport pass. Do not report the full
run as green or silently replace its failure with the focused recheck.

Implementation source hashes remain unchanged from
`source-provenance.json`, which records the gamma versions and Three.js 0.171.0.

Logs and retained before-source snapshots are under
the unbundled local `viewport-optimization-20261018` run. See the
[release evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

## Native acceptance remains pending

The initially available installed host displayed version 0.3.9 and was excluded
from gamma acceptance. A new development host was built from gamma sources.
Computer Use then ended with: "could not determine the current browser URL on
Windows with enough confidence to enforce policy." No further UI automation
was performed. The SPIKE UI skill requires "Use actual native SPIKE screenshots
for visual acceptance" (`C:/Users/yawar/.codex/skills/spike-ui/SKILL.md`);
headless checks do not replace that evidence.

Wide/narrow native interaction, real 2D/3D assembly views, per-board managers,
connector mappings, GPU recovery, frame/event traces and repeated memory-cycle
acceptance remain pending. Neither the synthetic fixture nor the cache tests
establish the 10 GB available-RAM / 10–20-real-board whole-program target.

## Reproduction

From `app`:

```powershell
node scripts/test-viewport-pick-allocation.mjs
npm.cmd run test:large-scene
npm.cmd run test:assembly-layout
npm.cmd run test:assembly-handling
npm.cmd run test:assembly-structure-studies
npm.cmd run test:assembly-workspace
npm.cmd run test:parser
npm.cmd run check:architecture
npm.cmd run build
```

For the pending browser regression, serve the current app with Vite and open
`/scripts/viewport-pan-preview.html`, then run its zoom regression. It uses
synthetic geometry (20 occurrences of 1,200 tracks and 80 pads each). It asserts
view changes, retained hit-target DOM identities and no source-coordinate reads
during camera updates. Its two-RAF gesture timings include browser scheduling
and are not native event-latency measurements. The optional `?baseline` route
requires the separately captured pre-change module under `app/.tmp/`.


## Follow-up: appearance, drill geometry and depth

Workspace Light + Teal is independent from the viewport's Light, Graphite and
AMOLED backgrounds. Settings > Interface, viewport Appearance commands and
universal search expose these choices. Settings changes persist; scoped views
receive the same viewport preferences. Geometry and result palettes are not
changed by a background selection. Panel scale reserves space for the full
65%-150% label and native select arrow, including narrow dock headers.

Procedural substrate and mask previews now remove safe round/rotated-slot
through-drills. Copper pad cutouts use the same slot profile and include its
shape/dimensions in the geometry cache key. Blind/buried via bores do not cut
the complete laminate. Intersecting drills/cutouts requiring polygon booleans
are diagnosed rather than supplied to triangulation as overlapping rings.
Full blind-hole cavity solids and intersecting drill unions remain outside
this display fallback; authoritative source geometry remains preferred.

A retained SH-RPi fixture (540 pads, 364 vias) admitted 452 drill openings with
zero diagnostics. A synthetic 5,000-hole case checks that no count cap silently
removes drills. Import classification also recognizes blue/red exporter masks
instead of accepting only green. The retained source has 18,585 board meshes
and 555,279 triangles; two previously unclassified blue masks are now addressed.
These figures are geometry evidence, not a new GPU throughput benchmark.

Perspective rendering uses conventional depth with a conservative near plane
inside the visible bounding sphere and a tighter near plane in the provably
empty foreground outside it. This preserves polygon bias on overlapping PCB
skins. The installed Three.js logarithmic-depth shader writes fragment depth;
its raster polygon bias did not provide the intended separation. Reverse depth
was tested and rejected on the local WebView: the retained scene disappeared
except for sparse points. Conventional depth restored the two-board fixture.
No source coordinates or solver mesh coordinates are moved by this change.
MSAA remains requested, with actual admission recorded in viewport telemetry.

Browser acceptance used the retained two-occurrence, 168-component-per-board,
four-copper-layer fixture (about 1.55 million submitted triangles). Both boards
and models rendered with conventional depth. The test does not establish
universal GPU support or a speedup; local render time remained tens of ms.
Further work includes larger assembly/harness benchmarks, the remaining stray
preview primitives, and native close-up reproduction of the reported surface
streaks. Do not describe this pass as a complete rendering qualification.

The hybrid via mesh drill-containment correction is separately documented in
[VIA_BARREL_DRILL_CONTAINMENT_20261018.md](VIA_BARREL_DRILL_CONTAINMENT_20261018.md).
It passed geometry tests and independent code review; knowledgeable human
numerical review is still required before release.
