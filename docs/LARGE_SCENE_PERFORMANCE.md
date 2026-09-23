# Large board and assembly performance

Implemented in the desktop source on 2026-09-07. These are rendering and
allocation improvements; they do not qualify new solver physics or increase
the supported board/part admission envelope.

## Implemented

- Imported static meshes with repeated geometry and material use instancing.
  Buffers contain at most 2,048 occurrences. Transparent meshes retain their
  separate sorting; mirrored, skinned and morphing meshes do not enter this
  instancing path. Independent component picking proxies remain intact.
- Procedural component bodies, end caps and markers also use instancing,
  grouped by appearance, mount type and board side. Each instance retains its
  reference, selection/hover color and layer-separation transform. Missing-model
  updates hide only references replaced by imported geometry. A 20,000-body
  regression stays within 12 batches. In the actual Marble visual-bundle preview,
  total scene draw calls fell from 2,610 to 164 after restoring all missing-part
  placeholders. This is draw-call evidence, not a GPU frame-rate benchmark.
- Assembly occurrences share decoded geometry and textures, with independent
  materials for opacity, clipping and selection. The LRU source cache targets
  256 MiB of estimated decoded storage and 24 entries. Active occurrences pin
  their sources; active storage can exceed this retention budget. Releasing
  the last occurrence permits eviction and disposes resources exactly once.
- Model preparation admits three concurrent jobs, yields after time slices,
  and stops dispatching obsolete generations. Partial selector failures clean
  up successful siblings rather than leaking their resources.
- Assembly projections build a frame lookup once and cache composed parent
  transforms within that projection. New projections observe edited frames.
  Hierarchy construction and flattening are iterative. The navigator retains
  all hierarchy rows and mounts a small scrolling window instead of truncating
  the hierarchy at 121 entries.
- Layer-manager SMD/THT counts are memoized linear passes over pads and parts.
  Scene search indexes the first object of each net once, delays search work
  until needed, and stops after collecting the visible match limit.
- Result hover searches at most four local grid rings before an exact search
  of occupied buckets with distance pruning. Large gaps between boards and
  collinear harness samples cannot trigger unbounded empty-grid traversal.
- Result playback retains at most four materialized frames with a combined
  250,000 sample-unit budget (vectors cost two units). A single oversized
  current frame is retained for repeat paints. Original solver values and
  unselected fields remain intact.
- Saving result artifacts serializes repeated in-memory result identities
  once and avoids deep-copying dense result trees before externalization.

## Layer and import recovery (2026-09-20)

The 2D viewport now renders parsed board geometry when plotted layer assets are
absent or fail to load. Copper pads, tracks, filled zones and vias follow their
physical layers; technical-layer pads and drawing strokes are also available
in this fallback. Zone holes remain empty. Canonical imports recover outlines
from outline drawings and retain footprint placement and side information.

Use the layer manager to hide or show individual layers. A manager change
clears the local 2D copper focus so it cannot silently override the manager.
The vias control works independently, including the show-only-vias preset.
Hiding vias uses native copper geometry because exported SVGs bake vias into
their images. In 3D, hiding copper layers exposes the interior by hiding the
opaque substrate. SMD/THT filters retain imported component models and filter
their classified batches. Repeated meshes remain batched by mount and side.
Dense-board fallback pads, tracks and vias retain their physical sizes instead
of being enlarged to fixed scene dimensions.

A failed board mesh no longer discards a successful component model load.
Model lookup recognizes installed KiCad versions and legacy model aliases.
Open the source board by its native path when models use project-relative
paths; source text alone cannot recover the original project directory.
Missing model files still require installing or locating their libraries.
When an imported component scene is only partially resolved, each placeholder
group retains its component reference and mount category. This prevents a
hidden parent group from suppressing missing-part placeholders after the
successfully resolved models load. The navigator counts source assignments,
not successfully loaded model files; the viewport reports missing-model gaps.
Fallback bodies, solder mask and unsupported custom pad/text geometry do not
have the same fidelity as successfully exported KiCad assets. Demo visual
bundles attach to imports only when source content matches, avoiding stale
geometry for edited boards that reuse a demo filename.

Debug desktop builds in this source checkout use its current Python worker
ahead of a stale frozen worker. Release builds continue to prefer the packaged
worker and require the normal packaging qualification. To create the local
executable, run `npm run build` followed by
`npm run tauri -- build --debug --no-bundle` from `app`. The executable is
`app/src-tauri/target/debug/spike-desktop.exe` and depends on this checkout and
its Python environment. Building it does not update an installed release.

Regression coverage is in `test:viewport`, `test:normalized-board`,
`test:board-visuals`, `test:layer-inventory`, `test:large-scene`, and the Python
staged visual import tests. Rendered-component checks verify layer visibility;
interactive checks at supported window sizes remain required before release.

## Package and import limits

Desktop project selection and startup opening now admit files up to 16 GiB.
ZIP64 projects are passed by approved path to the existing streaming verifier.
Legacy JSON remains limited to 256 MiB, including a bounded read before parsing.
The format remains `spike-project-package/v3`; no migration is required.

This aligns the host with the container's existing scale, but does not make
all project operations stream in bounded memory. The following limits and
remaining work are material:

| Boundary | Current behavior |
|---|---|
| Package reader | 100,000 members; 2 GiB/member; 16 GiB expanded aggregate; 64 MiB/control JSON; existing ratio and integrity checks |
| Worker messages | 256 MiB request and response |
| Saved visual transport | 96 MiB aggregate; base64 JSON transport |
| Saved result artifact | 96 MiB per result |
| KiCad visual-export source | 64 MiB |
| Assembly exchange ZIP | 256 MiB/asset, 512 MiB total |
| Project modifications | Several services still retain all preserved artifact bytes before rewriting |

Larger visual imports need chunked/binary artifact transport and incremental
save/rewrite, not just larger constants. Out-of-core model residency, spatial
tiling, GPU timing/adaptive quality, and full-scale multi-board EMI/SI solver
qualification remain separate work. The current model cache bounds retained
idle sources, not the complete active assembly.

## Reproducible checks

From `app`:

```text
npm run test:large-scene
npm run test:mcad
npm run test:result-performance
npm run test:project-persistence
npm run test:harness-visualization
npm run build
```

From the repository root, with the project Python environment:

```text
.venv/Scripts/python.exe -m unittest tests.python.test_project_package_v3 tests.python.test_project_state_artifacts -q
python scripts/check_architecture.py
```

From `app/src-tauri`: `cargo test --offline --lib`.

Local deterministic stress fixtures verified:

| Fixture | Measured/verified result |
|---|---|
| 20,000 repeated tessellated parts | 10 draw batches; 1,303,712 geometry/matrix bytes versus 474,240,000 bytes for expanded geometry; exact occurrence transforms retained |
| 10,000 shared assembly occurrences | One decoded geometry; independent materials; safe sibling disposal, eviction and cancellation |
| 20,000 nested assembly frames | Exact composition and all 20,001 hierarchy rows, without recursive overflow; edits invalidate projection results |
| 120,000 result points | Local hover inspects four samples; sparse-gap and collinear queries match exact nearest results |
| Dense EMI time frames | Weighted eviction, active-frame reuse, original field values retained |
| Repeated 100,000-value saved result | One serialization across 31 references, without copying the full result tree |

The tessellated-part preparation measured roughly 96–154 ms locally. These
tests exercise CPU scene construction and buffer accounting; they do not
measure GPU frame rates, total application memory, or certify a 16 GiB project
through an entire edit/simulate/save workflow.


## Marble import and net-name display (2026-09-20)

The pinned Marble v1.4.4 source described in `MARBLE_CLI_QUALIFICATION_PLAN.md`
was rechecked through the current staged source worker. The 44,993,740-byte
board produced all 30 plotted layers (38,595,179 bytes), a lightweight board
mesh (716,764 bytes), and a component mesh (2,318,784 bytes). The frontend
parser retained 37,380 tracks, 5,272 pads, 3,664 vias, 1,006 footprint records,
140 displayed filled-zone polygons, and 12 copper layers. Footprint records
and displayed polygons are not interchangeable with uniquely referenced
components or source zone declarations.

The production payload materializer verified all stage digests and all SVG
coordinate frames. Three.js loaded and prepared the actual GLBs with unchanged
bounds: 234 board meshes became one batch; 4,014 component meshes became 59
batches. These are loading/preparation checks, not interactive frame-rate tests.
Marble references a CERN component-model library absent from the pinned source
checkout and installed library paths. Missing assignments remain explicit;
no similarly named model is silently invented to replace those parts.

The online BerkeleyLab/Marble main branch and v1.4.4 resolve to the same pinned
commit. The current tree, fetched branch/tag history, and v1.4.4 fabrication ZIP
contain no STEP/WRL component models. A whole-board `Marble.step` is attached to
the older v1.1 release; it is not used as v1.4.4 component geometry. The official
CERN library also excludes vendor-owned 3D files. Local investigations are
recorded in `artifacts/validation/marble-visual-2026-09-20/` as
`marble-online-model-investigation.json` and `cern-model-investigation.json`.
The staged export reports 919 unresolved component references. Its available
component GLB loads successfully, while the missing parts remain placeholders.

Choose **View > Show net names** or **Layer manager > Scene > Net names**.
Names follow visible copper traces and zones in the 2D layout, rotate with
traces while remaining upright, and are hidden with their layers. Fine traces
need sufficient zoom for readable text. The label pass clips to the view,
checks zone holes and concavity, suppresses overlaps and caps visible labels
at 400. It changes presentation only. The setting participates in project
save/reopen and undo; older projects default to labels off.

ODB++ archives and extracted jobs are available through **File > Import ODB++
archive** and **File > Import ODB++ folder** in the desktop app. The import
quality report is retained for review. Copper membership comes from the
imported conductor inventory, so non-KiCad names such as `TOP` and `SIGNAL1`
remain renderable and appear in the copper group. Unsupported manufacturing
features and missing stackup/model inputs must still be resolved according
to the import report before analysis.

Large normalized sources use authenticated compressed transport during project
save/reopen. Compact reopen sends the canonical design once and restores it
before display or analysis; exact archived solver zones are hydrated before
solver submission. The real Marble ODB++ response was exercised through the
frontend decoder with 122 solver zones, 12 copper layers and 45 drawable layers.
The decoder rejects missing canonical data, corrupt checksums and decompression
beyond the declared size. This reduces duplicate transport data without raising
the 256 MiB desktop response limit or relaxing import-quality requirements.

Current public PCB reference imagery uses the pinned Marble source with
attribution in `THIRD_PARTY_NOTICES.md`. The front-copper SVG is actual exported
geometry; the reference top image is an upstream board render. Fresh application
captures show the browser preview's procedural component fallback, layer manager,
net names and unsolved report. Interactive checks at 900x620 and 1440x920 verified
all-off, single-copper visibility and label visibility. Single visible copper
keeps full contrast; deeper zoom now permits readable fine-trace names (checked
at 4441% on Marble). These checks do not certify installed-desktop GPU performance
or missing CERN component models.

The same browser session exercised every one of Marble's 30 listed 2D layers
independently. Each toggle removed only its named native geometry while the
other populated layers remained present; the machine-readable record is
`artifacts/validation/marble-visual-2026-09-20/layer-toggle-ui.json`. Layers
whose source geometry byte count is zero still completed the toggle check but
cannot demonstrate visible content. A separate 3D check hid front mask and
front silkscreen while front copper remained visible, then restored them;
hiding copper did not remove those technical layers.

The procedural 3D substrate previously extended through the outer conductor
centres, so its opaque mesh could occlude enabled copper even though layer
visibility was correct. Display construction now extrudes the substrate only
between the outer copper centres with a clearance and no bevel. The focused
viewport test builds real Three.js `ExtrudeGeometry` and checks its Z bounds
against two-layer, Marble-like 12-layer, 32-layer, single-copper, and empty
stacks. These checks cover display geometry only and do not change solver
physical geometry.
