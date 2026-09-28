# SPIKE Project Package v3

## Scope

`spike-project-package/v3` is the open SPIKE project container format. A v3
file uses the `.spike` extension and is a ZIP64 archive. It provides portable
projects, design exchange, and result bundles while retaining source
provenance, canonical design semantics, audit information, and regenerable
caches separately.

This is the current reader/writer contract implemented by
`python/spike_core/project_package.py`. It does not promise lossless
write-back to proprietary CAD sources or guarantee that every optional member
is emitted by every workflow.

Related documents: [CAD_NEUTRAL_NATIVE_MULTIPHYSICS_FOUNDATION.md](CAD_NEUTRAL_NATIVE_MULTIPHYSICS_FOUNDATION.md),
[PROJECT_FORMAT.md](PROJECT_FORMAT.md), [IMPORTER_ARCHITECTURE.md](IMPORTER_ARCHITECTURE.md),
and [SECURITY_MODEL.md](SECURITY_MODEL.md).

## Identity and profiles

| Field | Value |
|---|---|
| File extension | `.spike` |
| Container | ZIP64 with deflated members |
| Manifest format | `spike-project-package/v3` |
| Manifest contract | `spike/project-package/v3` |
| Canonical design contract | `spike/design-ir/v2` |
| Optional assembly contract | `spike/assembly-ir/v1` |
| Optional retained assembly design set | `spike/assembly-designs/v1` |
| Assembly placement policy | `spike/assembly-placement-policy/v1` |
| Optional assembly package shapes | `spike/assembly-package-shapes/v1` |
| Model index contract | `spike/model-index/v1` |
| Hash | SHA-256 per member and manifest payload |

| Profile | Intended use | Minimum content |
|---|---|---|
| `portable_project` | Reopen an editable local SPIKE project | project metadata and DesignIR v2; source artifacts are recommended |
| `design_exchange` | Exchange canonical design semantics without result caches | project metadata and DesignIR v2 |
| `result_bundle` | Deliver auditable results and reports tied to a design identity | project metadata, DesignIR v2, result metadata, audit data |

Profiles communicate intent. They do not bypass validation, integrity checks,
or solver validity requirements. The writer and reader enforce profile
semantics in addition to the manifest enum:

- `portable_project` may contain editable workspace, analysis, result, report,
  and cache state.
- `design_exchange` rejects populated result/report indexes and generated
  result/report artifacts instead of silently discarding them.
- `result_bundle` requires populated result metadata, at least one audit event,
  and a canonical DesignIR design identity.

## Member layout

Since 0.2.10, desktop saves also include `state/artifacts/<sha256>.json` for
complete simulation payloads and `visuals/artifacts/<sha256>.glb|svg` for imported
board, component, and layer visuals. References carry contract, member path,
SHA-256, and byte size. `extensions.board_visuals` retains role/layer mapping,
source digest, quality, view box, and the native-copper rendering policy.
These packages declare minimum reader 0.2.10.

Save retains every result record, including meshes, fields, waveforms and future
result fields; duplicates share an artifact. Open restores saved result display,
probes, playback/field controls and workspace view. ODB++ canonical geometry and
source provenance survive reopening without the original job archive. Imported
PCB visual files reopen without running KiCad or resolving source model paths.
Save As retains existing verified extension/model artifacts.

Desktop study definitions are retained in the frontend snapshot under
`studies` (inside the v3 legacy-extension projection). Each versioned study
contains ordered PI, SI, thermal, or EM cases. A case keeps its own scenario
description, setup snapshot, and optional captured result. Repeating a type
creates a separate case with independent settings. Loading a case applies its
setup to the matching workspace; execution still uses that workspace's solver
controls and validity gates. **Save project copy without results** removes
captured study results while keeping study and case setups.

The transport limit is 96 MiB per result artifact and 96 MiB for the visual input
of one save. Exceeding a limit fails explicitly before replacing the saved file.
Standalone Save results emits `spike/result-package/v2` JSON with the embedded
design and desktop state; Load results also accepts older v1 result exports when
their source board is open. Use `.spike` for complete multi-board/MCAD portability.

The desktop File and Project manager actions offer **Save with results** and
**Save project copy without results**. The latter writes a separate v3 package,
removes PI/SI, EMI, and thermal result payloads and unreferenced result
artifacts, and retains board links, assembly placements, solver setups, and
view settings. It leaves the active project and its current results untouched.
**Save results file** writes a `.spike-results.json` v2 snapshot; **Open project**
accepts that file directly and restores its embedded design and results. The
v3 contract is extended additively, so existing v3 readers and older project
migration remain applicable.

```text
manifest.json
project/project.json
sources/<sha256><source extension>
design/design-ir.json
design/assembly-ir.json                 optional
design/assembly-designs.json            optional retained DesignIR set (1-20)
design/assembly-package-shapes.json     optional exact-shape ownership index
geometry/index.json
geometry/<table>.arrow                  optional Apache Arrow IPC tables
geometry/package-shapes/<id>.spkshape   optional exact topology artifact
geometry/package-shapes/<id>.spkselect.glb optional exact-selector visual aid
models/index.json
models/artifacts/<artifact>             optional 3D, SPICE, IBIS, material data
workspace/state.json                    optional exact UI workspace recall
analyses/index.json
results/index.json
reports/index.json
reports/artifacts/<artifact>            optional HTML, PDF, CSV and similar
audit/events.jsonl                      optional newline-delimited JSON records
extensions/index.json
```

`manifest.json`, `project/project.json`, and `design/design-ir.json` are
required. Other logical indexes are currently emitted even when their data is
empty. `design/assembly-ir.json` is present only when an assembly is supplied.
`design/assembly-package-shapes.json` is present only when every indexed shape
has a digest-matching exact topology artifact and retained STEP owner.

`design/assembly-designs.json` uses `spike/assembly-designs/v1`. It retains up
to 20 complete canonical DesignIR v2 records, identifies the exact active
`design/design-ir.json` record, rejects duplicate or mismatched identities, and
requires every AssemblyIR board-instance `design_id` to resolve. Packages that
omit it remain backward-compatible single-design packages. A verified-manifest
structure transaction may replace board, harness, connector-mapping, and
rigid/flex-link arrays while preserving every retained design and all other
assembly records; new cross-design references fail until their DesignIR is
retained. Desktop open/save/undo state retains this set explicitly, and the
structure editor offers only retained DesignIR identities for board assignment.

`workspace/state.json` uses `spike/workspace-state/v1`. It is optional because
design-exchange and result-bundle profiles do not require an application
layout. A portable desktop project should include it when an exact workspace
has been established.

`sources/` stores immutable original inputs. Source names are
content-addressed from SHA-256 and retain safe filename suffixes. `design/`
holds editable canonical semantics. Geometry, results, and generated reports
are regenerable outputs and must not replace source provenance or DesignIR
authority. `extensions/` stores namespaced vendor data or migrated unknown
fields; readers must preserve it where practical.

## Manifest

The manifest contains archive identity, compatibility policy, schema versions,
audit identity, and a complete inventory of non-manifest members.

```json
{
  "format": "spike-project-package/v3",
  "contract": "spike/project-package/v3",
  "profile": "portable_project",
  "package_id": "canonical-project-id",
  "created_at": "2026-08-13T00:00:00.000Z",
  "application": {"name": "SPIKE", "version": "0.2.0-alpha.1"},
  "compatibility": {"minimum_reader": "0.2.0", "unknown_extensions": "preserve"},
  "schemas": {"design_ir": "spike/design-ir/v2", "assembly_ir": "spike/assembly-ir/v1", "assembly_placement_policy": "spike/assembly-placement-policy/v1", "assembly_package_shapes": "spike/assembly-package-shapes/v1", "model_index": "spike/model-index/v1", "workspace": "spike/workspace-state/v1"},
  "audit_identity": {"project_id": "canonical-project-id", "design_id": "canonical-design-id"},
  "members": [{"path": "design/design-ir.json", "sha256": "64 lowercase hexadecimal characters", "size": 0, "media_type": "application/json", "role": "design"}],
  "manifest_payload_sha256": "64 lowercase hexadecimal characters",
  "signature": {
    "contract": "spike/manifest-signature/v1",
    "algorithm": "ed25519",
    "key_id": "organization-or-release-key-id",
    "signed_payload_sha256": "64 lowercase hexadecimal characters",
    "signature_base64url": "base64url-without-padding"
  }
}
```

`manifest_payload_sha256` is the SHA-256 of canonical UTF-8 JSON for the
manifest without that field. It detects accidental manifest modification. It is
not a digital signature and does not identify an author.

The optional `signature` covers the canonical UTF-8 manifest bytes including
`manifest_payload_sha256` and excluding `signature`. Version 1 permits
Ed25519 only. The package layer accepts a signing callback so private keys are
held by a release service, organizational signing tool, or native secure host,
never embedded in the Python worker. Readers report signatures as present but
unverified unless a trusted verifier is supplied. A caller can require a valid
signature; missing signatures, missing trust configuration, malformed
envelopes, digest changes, and failed verification then fail closed. Merely
having a `signature` object never grants trust.

The desktop open path adds a second, native trust boundary. The worker returns
the exact canonical signed bytes as base64url plus the signature envelope; the
Tauri host verifies both with `ed25519-dalek` against public keys pinned into
the desktop build. A signed package is not applied to the workspace unless
native verification succeeds. Unsigned packages remain readable and are
reported as unsigned; they are never promoted to trusted state.

Release builds configure the public-key registry at compile time with either:

- `SPIKE_PACKAGE_TRUSTED_KEYS_JSON`, an array of `key_id` and
  `public_key_base64url` records; or
- `SPIKE_PACKAGE_KEY_ID` and `SPIKE_PACKAGE_PUBLIC_KEY_B64URL` for a single
  pinned key.

Private package-signing keys are not stored in the repository or desktop
application.

The machine-readable manifest schema is
[`../schemas/spike-project-package-v3.schema.json`](../schemas/spike-project-package-v3.schema.json).

## Integrity and safe reading

Before returning package content, the v3 reader:

1. opens the archive without extracting members to the filesystem;
2. rejects unsafe absolute, traversal, empty, duplicate, or over-deep paths;
3. enforces archive member, per-member, total expanded-size, compression-ratio,
   manifest-size, and path-depth limits;
4. verifies the manifest self-digest;
5. verifies that every archive member other than `manifest.json` is declared;
6. verifies every declared member's byte length and SHA-256 digest;
7. requires `project/project.json` and `design/design-ir.json`;
8. verifies that the canonical design declares `spike/design-ir/v2`;
9. validates the optional AssemblyIR and the model index, including each
   indexed artifact's package presence and declared SHA-256 digest; and
10. validates optional signed-manifest metadata and, when configured, verifies
   it through a trusted Ed25519 verifier.

Member integrity is verified in bounded 1 MiB chunks. Canonical JSON indexes
and the audit stream are retained for parsing, while source, Arrow, model, and
report artifacts are not expanded into memory unless the caller explicitly
requests `include_members=True` for lossless resave or artifact access.

| Limit | Default |
|---|---:|
| Members | 100,000 |
| Maximum member bytes | 2 GiB |
| Maximum expanded archive bytes | 16 GiB |
| Maximum compression ratio | 200:1 |
| Maximum path depth | 12 |
| Maximum manifest bytes | 16 MiB |

These limits protect loading. They are not a statement that every solver can
process a 16 GiB project. Solver and mesh resource limits remain independent.

## Design, assembly, and models

`design/design-ir.json` is the authoritative canonical board record. It uses
canonical UUIDs and preserves source-native IDs and source digests for stable
probes, terminals, cross-selection, revision comparison, and re-import audit.

DesignIR v2 also canonically retains KiCad thermal-connection declarations:
zone defaults and fill/thermal settings; component/footprint overrides; and
pad overrides, optional pad spoke angle, and reserved per-layer override map.
An omitted zone default is `thermal`; omitted footprint/pad overrides are
`inherit`. KiCad numeric footprint/pad values are preserved as the typed mapping
`0/1/2/3 = none/thermal/solid/tht_thermal`. Unsupported modes, invalid or
non-finite dimensions, an angle outside `[0, 360)`, and layer-specific padstack
settings that lack typed retention fail closed with invalid/`unknown` state and
diagnostics. Zone records retain whether their copper is `source_filled` and
the source-filled identity, rather than inferring a fill from an outline.
Package retention and schema round-trip are covered by the focused four-test
KiCad thermal-connection fixture suite, including the `ebrake1` and
`MODULAR-BUS-NIB` source-filled-zone/override census. This package fact does
not regenerate thermal spokes or make thermal/solver/field-convergence claims.
The registered `spike/zone-pad-connection-evidence/v1` sidecar supplies bounded,
digest-bound source-filled pad-zone observations: literal pad-layer, pad,
footprint, then zone-default precedence; required canonical-layer expansion for
through-hole pads; and exact contact/disjoint/unsupported observation. It is
fail closed for tampering, stale identities/digests, policy/net/layer mismatch,
unsupported geometry, cancellation, resource/schema violations, or promoted
readiness. A mesh `pad_zone_attachment` requires admitted evidence and retains
its `evidence_id`; explicit `none` forbids overlap-only attachment. This is not
thermal-spoke regeneration or a topology, native-overlay, field, physics, or
solver claim: `topology_state` is `not_regenerated` and those qualification
flags remain false.

The packaged DesignIR v2 zone projection also preserves bounded source-filled
component membership per original zone and canonical copper layer. Admitted
records retain a source ordinal, exact source-path digest, group identity and
member count, and an order-independent group snapshot digest. Incomplete,
non-finite, or over-bound groups are diagnostic and unqualified rather than
partially trusted. KiCad's flat `filled_polygon` path is stored as exactly that;
the package does not infer hole/negative-space roles, component connectivity,
or thermal spokes. `thermal_topology_eligible` is fixed false until a separate
qualified topology extractor can consume an unambiguous source representation.

The registered `spike/thermal-relief-boundary-contact-evidence/v1` sidecar can
bind the packaged DesignIR v2 digest and its validated IN-0229 evidence digest.
For every effective thermal candidate it records bounded partial/full/absent or
unsupported source-filled contact intervals on a polygonal pad boundary. This
does not alter package geometry or mesh attachments and cannot assert a spoke,
refill, mesh, field, solver, or physics claim. The two bundled boards currently
provide no source-contact candidate resolving to thermal, so the checked
boundary-contact result is qualified by controlled fixtures only.

`spike/thermal-relief-observed-topology/v1` can additionally bind the packaged
design and both prerequisite evidence digests for the fixed controlled
four-cardinal rectilinear-reservoir fixture profile. Four disjoint source
components must independently satisfy open-edge contact, effective width,
full-gap centered cross-sections, continuous centerline, outer-reservoir, and
angle checks. The artifact is deterministic under component source ordering
and fail closed for ambiguity, tampering, cancellation, and resource excess.
It remains observed fixture geometry, not general KiCad extraction or refill
provenance, and it is not consumed by a mesh or solver.

The package can carry optional Apache Arrow IPC files under `geometry/`.
Arrow tables are a transport/cache facility; a design does not become invalid
because it has no Arrow table. Canonical desktop saves now generate one
deterministic Arrow IPC file, `geometry/copper_geometry.arrow`, from DesignIR v2
tracks, arcs, zones, pads, and vias. Rows are sorted by kind and canonical ID,
use explicit nullable field types and millimetre coordinates, and carry schema
metadata binding the table to `design_id`, canonical DesignIR SHA-256, and frame.
Typed manufacturing-drill records are retained in canonical DesignIR and package
round-trips as provenance; they are not copper-geometry Arrow rows and do not
create copper, barrels, or mesh voids.
The uncompressed Arrow file is decoded and exactly compared to DesignIR before
write. Canonical reads first require an exact byte match with SPIKE's
deterministic uncompressed projection before decoding, preventing alternate
compressed IPC layouts from expanding before semantic validation. This
canonical-byte-before-decode ordering fix is included in the historical r12
package checkpoint. r12 also removes the loose duplicate typed sidecar: one
typed authoritative package representation remains, and the v1 projection
reconstructs metadata rather than retaining duplicate metadata. The IPC-2581
v9 retained negative-plane nonregular thermal user-primitive slice changed
source after r12. The historical r13 engineering-preview manifest generated
`2026-08-26T18:57:31.5575476+00:00` passes 20/20 automated acceptance checks,
with 8/8 fresh runtime parity (digest
`0537e5dc7cd36cd59ac1be3d510a1df56f1edce77dffe7a7e30e0d682bf37906`) and
the passed four-row Arrow v4 probe
`931c522ea27c92050f43ccb2f6617447c53d07909856d815ada0a1b25b00f31e`.
The section-box source slice changed after r13, so r13 and r14 are historical.
Historical r15 (`2026-08-26T23:05:46.0259327+00:00`) has `NotSigned` MSI
123,617,980 bytes, SHA-256
`9f396046fa0e392a9daea6f45acbc3b0242a4e0de348ef00ec9a57a0480a1c23`, and
`NotSigned` NSIS 87,288,223 bytes, SHA-256
`54d834f9813613fde4bc9071b8b754500673e3b04743df9d9063a482ad4365d3`.
Extraction at `artifacts/windows/installer-smoke-20260827-r15/PFiles/SPIKE`
has 1,559 files / 296,548,059 bytes and a ready 1,081-file / 262,619,732-byte
worker. It passes 15/15 benchmarks, embedded/fresh parity 8/8
(`8db5618…` / `0537e5dc…`), and Arrow v4 four-row probe
`30c24729efa63187daf3a8d3c26167ebd89b65836cf7f758e86d0e96604bb988` with one
retained unresolved occurrence excluded as copper. Its 23-member fixture and
`build/wave1-packaged-assembly-acceptance-r15.json` passes 21/21 automation,
including `worker.fixture_mutation_reopen`: a temp-copy extracted-worker update
persists visibility, 0.625 opacity, and placement-policy-valid translation and
rotation; it chains manifest identities, reparents world-preservingly to the
board frame, leaves model/package-shape artifacts unchanged, canonically
reopens deterministically, and keeps `solver_ready: false`.
Its source is IPC-2581 v12. Its status remains unsigned `pending_human`
with all 10/10 human checks absent. Exact hash-bound clean-machine harnesses
are staged at `artifacts/wave1-clean-machine-r15-msi` and
`artifacts/wave1-clean-machine-r15-nsis`; staging neither provisions nor
executes an isolated machine and satisfies no human check. It does not establish
mesh, solver, Wave 1 completion, or production-physics readiness.
The historical r16 portable preview used the fixed paths now replaced by r17
and had SHA-256
`8b497a72c3cd7e844464fdd794df6b705dece609a235c5489b222d1050514588`; its
portable manifest v1 records 1,548 files / 296,380,909 bytes / zero failures,
and bundled-worker health is `ready`. This closes repository-built portable
preview evidence only—not signing, legal, clean-machine, user-pixel, upgrade,
uninstall, production, or Wave 1 requirements.

The r12-r17 package records are historical. Current r18 (IPC-2581 v13, generated `2026-08-27T01:19:52.7158705+00:00`) is unsigned: `NotSigned` MSI 123,638,540 bytes, SHA-256 `639758f8170fb81c0e7cd942038ee7d48ca55a197ed46ff6eff279fc9e2085e1`; `NotSigned` NSIS 87,310,439 bytes, SHA-256 `ca8f6090cb3dbb0d49463385ad44ab3d732c3e0913e76c418545aff7d99c03dd`. Its `artifacts/windows/installer-smoke-20260827-r18/PFiles/SPIKE` extraction has 1,564 files / 296,613,533 bytes and a ready 1,081-file / 262,625,391-byte worker, with IPC-2581 v13 and the 64 MiB JSON cap present. `build/wave1-packaged-assembly-acceptance-r18.json` passes 21/21; status is `pending_human` 0/10. r18 harnesses bind `f149a969bf14d0b3f6f3ed0d0fb759e6c2890a19e8f31ac71d23e5c87d544790` / `67d2c80a727b110939083c10860f2836d7b2ab42123585920186799ccb75d8c6` but give no human evidence. The portable ZIP SHA-256 is `47e59bf365e7d8752af24181911f1f0c238df21d2e3d5d90ae5f0f41ef6d7184`; manifest v1 verifies 1,551 files / 296,411,495 bytes / zero failures and worker health `ready`. After the notice-review slice, the full suite passes 796 with 0 failures/errors and one expected external KiCad skip; focused combined 67, Rust 24/24, architecture, and TypeScript/Vite production build pass. No Wave 1/Wave 2/mesh/solver/physics promotion occurs.
The temporary visual-only six-plane section box uses a shared clipping builder
for glTF/GLB visuals and exact-selector previews; invalid, non-finite, or
inverted bounds disable clipping. It is not persisted to AssemblyIR/package and
does not establish topology, mesh, solver, or physics semantics.

`geometry/index.json` uses the registered `spike/geometry-index/v1` contract.
Generated records include path, encoding, member SHA-256, row count, design ID,
and DesignIR digest. Pathless designs retain the byte-compatible
`spike/copper-geometry-arrow/v1` projection; typed-path designs remain
byte-compatible with `spike/copper-geometry-arrow/v2`, whose additional nullable
columns preserve parent path, step index/count, end-cap, and join semantics.
Designs with exact conductor-boundary rings use
`spike/copper-geometry-arrow/v3`, which deterministically retains both those
path columns and the ordered exact boundary rings. The compatible
`spike/copper-geometry-arrow/v4` additionally retains exact per-layer
heterogeneous land profiles. Neither version samples or tessellates curves or
profiles, exposes them in the frontend, or establishes mesh or solver readiness;
`LAND_PROFILE_MESHING_PENDING` and `ZONE_CURVE_MESHING_PENDING` remain explicit.
The bounded `ipc2581-conductor-primitives-v13` qualification retains all
39,094/39,094 declared true-copper source records from the unchanged official
Rev C Full SHA-256 `6c10fea08943ca7261505bd531a8724bc1dffe8f9fec9e53a2f22d52bc83d347`,
with residual zero. Retained contour contract v2 preserves optional profile
`Xform` and bounded `xOffset`/`yOffset`/`rotation`/`mirror`/`faceUp`/`scale` raw
and normalized facts without applying or composing them. Its 98 occurrences are
32 declared-layer matches and 66 mismatches, all source-only. DesignIR v2 now
retains them in a closed typed envelope with
`semantic_state: unapplied_normative_semantics_missing` and
`projection: forbidden`. Normative composition and TOP-to-BOTTOM semantics
remain unproven, so this envelope creates no Pad, Via, connectivity, Arrow,
mesh, solver, or physics geometry. Typed zone/pad/via/drill totals remain
1/1,611/1,690/1,859; every readiness flag remains false; and
`build/ipc2581-testcase10-revc-v13-qualification.json` is
`passed_with_declared_gaps`; the focused IPC/package slice passes 74 tests, the
pinned-venv suite passes 796 with 0 failures/errors and one expected external
KiCad skip; the focused combined suite passes 67, Rust passes 24/24,
architecture passes, and the TypeScript/Vite production build passes.
This does not establish mesh, solver, or production-physics readiness.
Write and reopen reject duplicate, missing, orphan, unsafe, unsupported, or stale
claims. A targeted reader requires the opened manifest identity, enforces a
byte budget against both the manifest record and actual ZIP entry before
retention, bounds the package manifest before retention, reads only the
DesignIR/index/requested table, verifies its digest, then byte-matches,
decodes, and compares it to canonical DesignIR. Canonical Arrow comparison is
an exact byte match without `read_all` or `to_pylist`; callers cap Arrow IPC at
256 MiB and decoded rows at 10,000,000, with preflight rejection before decode
when the declared row count exceeds that limit. Targeted source, model, STEP,
and selector readers compare actual ZIP and manifest sizes before retention.
Caller-supplied legacy Arrow
tables remain preservable as digest-bound opaque caches but are not presented as
the canonical generated schema.

The optional `design/assembly-ir.json` can describe up to 20 boards,
transforms, harnesses, connector mappings, rigid-flex links, enclosure and
thermal parts, material records, thermal contacts, and electrical bonds. The
writer and reader rehydrate this member through the typed
AssemblyIR contract, fail closed on invalid limits or identities, preserve
unknown extension data, and emit canonical content. Save/reopen tests cover a
populated two-board assembly, non-identity transforms, source-native IDs,
connector mapping, harness, rigid-flex link, assembly part, and explicit
contact/bond physical fields. The worker open
and Save As path preserves the same contract even when a migrated legacy UI
snapshot is projected. This does not imply that a multi-board solver is
available.

The desktop save result returns the canonical `design/design-ir.json`
`design_id`, and project open reads the same identity from the verified
canonical payload. Assembly resource admission supplies the active design only
when that identity exactly matches the sole retained board reference. Empty
board lists remain valid for MCAD-only estimates; mismatched or multi-board
references fail closed until every referenced design is available. PI,
thermal-case, and openEMS execution boundaries recheck admission against the
persisted memory policy. This is capacity admission only and does not qualify
the solver, geometry, convergence, or physics.

The desktop applies a separate solver-semantics gate before that admission.
Current active-board PI and SPICE routes may coexist with visual-only MCAD
parts, but retained multi-board coupling, harnesses, connector mappings,
assembly rigid-flex links, or electrical bonds block execution. Thermal also
blocks retained assembly parts/material/contact semantics, and openEMS blocks
field-affecting MCAD parts, because those current adapters consume only the
active DesignIR. This desktop gate prevents an implicit coupled claim; it is
not yet a worker/CLI-wide scope contract or result-provenance binding.

Source artifacts should be copied to `sources/` when portability is required.
A source path outside the archive is metadata only and must not be trusted for
reopen.

`models/index.json` uses `spike/model-index/v1`. The current v1 contract admits
embedded `package:models/artifacts/<safe-leaf-name>` URIs only. Each model
record has a unique identity, an allowlisted `step`, `gltf`, or `glb` type, a
matching filename extension, a SHA-256 digest, an empty implicit-identity or
16-value finite transform, and namespaced extension data. Package reads and
writes fail closed when an indexed artifact is missing or its bytes do not
match the declared digest. Distinct model records may instance the same
artifact with different transforms when their URI, digest, and model type
claims agree; inconsistent shared-artifact claims are rejected.

`design/assembly-package-shapes.json` uses
`spike/assembly-package-shapes/v1`. It is a strict sibling of AssemblyIR, not
an untyped extension. Each shape is bound to one AssemblyIR part, one retained
STEP model, the exact model URI/digest and transform digest, a canonical shape
identity, an immutable kernel identity/version, and one safe
`package:geometry/package-shapes/<id>.spkshape` artifact URI/digest. Its
bounded selector inventory owns canonical solid, shell, face, edge, axis, and
vertex identities. Constraint references and thermal-contact/electrical-bond
bindings must resolve the declared part, shape, topology identity, and kind;
legacy endpoint strings, GLB triangles, and section planes cannot satisfy the
contract. Missing, corrupt, foreign-part, wrong-kind, stale-source, duplicate,
non-finite, and unindexed topology claims fail package write or reopen.

The bounded exact STEP-to-`.spkshape` path is implemented as a separate
manifest-bound transaction. It reads only the retained digest-verified STEP
owner, runs a fixed FreeCAD/OCC helper with source/output/report/entity,
time, memory, and stream limits, writes the raw OCC BREP plus deterministic
selector inventory and validated local-mm analytic descriptors, and independently rechecks report, source, artifact,
kernel, and selector identities before package mutation. Re-extraction replaces
only the same canonical shape and removes its superseded unindexed artifact.
The result is `topology_ready: true` and `solver_ready: false`: it enables
source-owned topology addressing and bounded exact placement inputs, not
contact/bond physics, meshing, material regions, or a qualified solver geometry.

An exact shape may optionally own one
`spike/package-shape-selector-preview/v1` record and `.spkselect.glb` member.
The record binds the visual aid to the retained STEP digest, exact BREP digest,
and canonical selector-inventory digest, with exact face/edge/axis counts and
`visual_only: true`, `solver_ready: false`. A separate bounded FreeCAD
operation reconstructs previewable selectors from the retained BREP before
emitting one GLB node per owned face, edge, or axis. Package write/reopen rejects
unsafe, missing, corrupt, duplicate, or unindexed preview members. A targeted
reader requires the verified-open manifest identity and revalidates the package
indexes, GLB structure, and node-to-selector bijection; it never exposes the
preview through ModelIndex. The desktop loads these nodes into a dedicated
selector group, resolves them again against canonical package-shape references,
and supports face/edge/axis raycast selection and highlighting without adding
them to ordinary board pickables. The preview remains ineligible for geometric
math even when its selected topology reference drives an exact descriptor-backed
operation. Packaged human/pixel acceptance remains a separate gate.

The desktop retains this index in its open/save projection and exposes a
bounded searchable exact-selector list. A dedicated verified-manifest
transaction may replace only `constraints`, `thermal_contact_bindings`, and
`electrical_bond_bindings`; shapes, model ownership, artifacts, index metadata,
and extensions remain immutable through that operation and the full canonical
validator runs before write. Thermal bindings accept owned faces only;
electrical bindings accept owned faces, edges, or vertices. A second
`apply_assembly_geometric_constraint_in_project` transaction applies exactly
one persisted two-reference definition with an explicit moving part. It rejects
old descriptor-free indexes, stale manifests, ambiguous/same-part references,
unsupported analytic types, non-rigid transforms, placement-policy violations,
and residual failures without writing. It never reads selector-preview triangles,
never changes exact artifacts, and never infers contacts, bonds, collision state,
or solver readiness; it is not a constraint-graph solve.

The bounded MCAD attachment worker persists STEP/STP, embedded glTF 2.x, and
GLB inputs together with deterministic AssemblyIR/model identities and an
audit event. Native `.kicad_pcb` import retains the approved source path while
building the visual payload, which permits `${KIPRJMOD}` and project-local
models to resolve before self-contained visual bytes enter application state;
the package itself remains path-neutral and does not persist an ambient host
directory capability. The desktop viewport resolves referenced glTF/GLB artifacts only
through an approved project path and a targeted 64 MiB aggregate reader. That
reader requires the exact manifest payload identity established during project
open, validates the archive directory and manifest, then verifies only the
model index and selected members rather than streaming unrelated package
content. Selected bytes pass their recorded size/SHA-256 checks and glTF/GLB
self-containment validation before base64 transport; external resource URIs
are rejected. The operation participates in the native heavy-worker admission
and cancellation path, and object URLs are revoked when the project/model set
changes. Package retention is not solver qualification. A bounded optional
FreeCAD adapter can transactionally derive an independently validated,
visual-only GLB from a retained STEP model, preserve the original STEP model
and member, switch only the selected part's visual model reference, and record
the source/derived digests plus `solver_ready: false`. The exact-shape worker
can operate before or after this visual derivation because it resolves the
retained STEP source identity rather than treating GLB triangles as topology.
A bounded root/board/part frame hierarchy can focus the
existing MCAD-part editor. A selected visual glTF/GLB part can be translated or
rotated with one viewport gizmo using millimetre grid and angular-increment
snapping. Preview motion is not authoritative: mouse-up converts the
assembly-world matrix to the current parent-local matrix and commits exactly
once through the verified-manifest update transaction. The worker rejects
projective, scaled, sheared, and reflected placement matrices. Board/harness/
multi-design structure editing and the bounded exact single-constraint snap are
implemented; packaged pixel/transform/reparent acceptance and future graph,
collision, contact, and multi-constraint solving remain pending. This
hierarchy is a UI projection, while tessellation adds ordinary indexed model
and audit data without changing the package schema. Exact extraction is the
only current STEP package-shape ownership path; the hierarchy, tessellated GLB,
and section planes do not provide topology or geometry/physics inference,
and no materials, contacts, bonds,
boundary conditions, regions, or physics are inferred. Direct-child numeric
placement, nested placement relative to an unchanged parent frame, bounded
translate/rotate gizmo placement with persisted grid/angle increments, and explicit
material/contact/bond setup edits are bound to the opened manifest identity
and appended to the audit stream; they remain input
data rather than geometry or physics qualification. Model licensing and
suitability remain separate engineering decisions. Optional per-part
`spike.visual` visibility/opacity settings are likewise validated and retained
as presentation metadata. Isolation and cross-section planes are temporary
viewport controls and are not authoritative package geometry.

The desktop Assembly hierarchy also shows a transient per-part viewport result:
pending, ready, failed, hidden, unavailable, or STEP awaiting tessellation.
The renderer supplies ready/failed only after its retry-bounded glTF/GLB load;
the remaining states preserve the package/model boundary honestly. This status
is UI session state, is not written into the project package, and cannot be used
as evidence of exact topology, mesh ownership, solver readiness, or physics.

An AssemblyIR part may contain `spike/assembly-placement-policy/v1` with
nullable `translation_snap_mm` and `rotation_snap_deg` increments. Numeric
values are finite and positive, rotation is at most 180 degrees, and null
means unrestricted movement for that dimension. The worker evaluates
translation in the current parent frame and the principal relative rotation
against the previously persisted local transform. Policy replacement is a
dedicated manifest-bound transaction that leaves the frame unchanged; the
ordinary part update cannot replace policy and move simultaneously. This
contract does not define or imply geometry, topology, collision, clearance,
contact, or solver semantics.

Part reparenting uses `spike/mcad-part-reparent-result/v1` and requires the
opened manifest identity. It preserves the old assembly-world transform by
persisting a compensated local transform under the new parent, while leaving
the part/frame/model identities and model artifacts unchanged. Invalid parent
chains, descendants, non-affine/singular transforms, and attempts to reparent
through the ordinary placement update fail closed.

Package-backed analysis must declare `spike/assembly-analysis-scope/v1` when
an AssemblyIR is present. The current executable mode is `active_board_only`:
one stable board instance and its canonical design identity are selected, the
verified manifest digest is carried when available, and every excluded board,
harness, connector mapping, rigid-flex link, MCAD part, thermal contact, and
electrical bond is listed in provenance. `assembly_coupled` is rejected until
a qualified solver consumes those entities. Prepared OpenFOAM/openEMS cases
are bound to the normalized scope and cannot be run under a different scope.

Multi-board PI/SI planning uses the separate public
`spike/multiboard-analysis-request/v1` and
`spike/multiboard-analysis-plan/v1` contracts. A plan resolves up to 20 retained
board instances and their virtual harnesses into deterministic board namespaces
and a digest-bound connectivity graph. Per-board admission is limited to 32
copper layers, a 1,000 mm by 1,000 mm declared or derived envelope, 20,000
components, and 100,000 nets, with workload memory charged per board instance.
The plan is derived execution metadata and is not persisted as authoritative
design geometry. Admitted independent SI jobs may execute sequentially through
`spike/multiboard-si-independent-batch-request/v1`; each job consumes the exact
retained DesignIR v2 for one board and excludes harness/cross-board coupling.
Aggregate board, lane, frequency, and numeric-output limits apply in addition
to each child job's limits. Explicit harness-conductor R/L and optional
reference-bound C/G values may compile through
`spike/multiboard-harness-compile-request/v1` into an inspectable circuit
fragment. Material names and AWG never imply electrical values. Coupled PI/SI
remains rejected until qualified board-port, connector, return-path, and solver
adapters consume that fragment; harness visualization remains presentation.

Per-workload solver choices are retained in `analysis.solver_selections`. They
are project intent, not solver evidence: the worker resolves each explicit
choice against the live catalog without fallback, and each application route
still enforces geometry, runtime, validation, and resource gates.

## Analyses, results, reports, and audit

Analysis definitions, result indexes, and report indexes are distinct from
design records. Results must preserve solver identity, formulation, mesh,
resource usage, convergence, assumptions, warnings, validation tier, and
source design identity. A `result_bundle` is auditable only when that link is
present and its member hashes verify.

`audit/events.jsonl` is newline-delimited JSON so append-oriented audit
records remain inspectable. It is optional in the current writer. Absence of
audit data must be reported by a workflow that claims an auditable release.

## Workspace recall

Workspace state is presentation state, not design or solver state. Version 1
records the active viewport mode, dock visibility/pinning/sizes, active bottom
dock, exact 3D camera position/target/up, and exact 2D view box. Readers must
validate and bound this data before applying it. Invalid optional workspace
data does not invalidate sound design content; the application reports the
fallback and fits the active design instead. The schema is
[`../schemas/workspace-state-v1.schema.json`](../schemas/workspace-state-v1.schema.json).

## Migration and compatibility

Legacy `spike-project-package/v1` and `spike-project-package/v2` JSON files
are read and migrated in memory. Migration validates the legacy revision,
derives or preserves a project ID, converts compatible design data to DesignIR
v2, preserves the full legacy payload under `extensions.legacy`, records
migration provenance, and emits v3 only on a later explicit save.
When the desktop opens a migrated `.spike` project, it offers **Upgrade now**
or **Later**. Upgrade now uses Save As with a suggested `-upgraded.spike` name,
requires a path different from the source, and opens the new v3 package after
writing it. Later leaves the project open; its next explicit save emits v3.

Unknown extension fields should be retained where possible. Unsupported
revisions fail visibly. Migration does not upgrade solver accuracy, create
missing source artifacts, repair incomplete geometry, or make old results
validated.

## Writer behaviour and conformance

The writer uses canonical sorted UTF-8 JSON, sorted paths, and fixed ZIP
timestamps. It writes to a temporary sibling file and replaces the target only
after the archive is complete. Native desktop save paths are separately
approved by the host; archive content cannot choose an arbitrary output path.

Conformance coverage must include all profiles, v1/v2 migration and unknown
extension preservation, unsafe/malformed archives, hash failures, limits,
DesignIR/AssemblyIR contract identity, source digest preservation, and clean
reopen on Windows and Linux.

Current focused tests cover all three profile semantics, basic write/read,
tamper detection, legacy migration, lossless verified-member resave, streamed
large-artifact verification, optional signed manifests, and package worker/CLI
paths. They also cover typed AssemblyIR validation, deterministic populated
assembly member output, fail-closed invalid assemblies, and desktop-worker
identity preservation. Model-index tests cover safe package URIs, type/extension
and finite-transform validation, namespaced extensions, shared-artifact
instancing, inconsistent claims, missing artifacts, and digest mismatches. The
public schema is
[`../schemas/model-index-v1.schema.json`](../schemas/model-index-v1.schema.json).
Native pinned-key verification is covered by Rust tests for valid,
untrusted-key, tampered-payload, and tampered-signature cases. Production key
provisioning/signing and cross-platform packaged-process conformance remain
pending.
