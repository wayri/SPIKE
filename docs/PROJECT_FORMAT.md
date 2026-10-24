# SPIKE Project Package

> **Historical v1/v2 document.** The supported package direction is the
> ZIP64-based `spike-project-package/v3` described in
> [SPIKE_PROJECT_PACKAGE_V3.md](SPIKE_PROJECT_PACKAGE_V3.md). This page remains
> for legacy JSON compatibility context and should not be used as the v3
> implementation specification.

## Current implementation

The supported writer emits `spike-project-package/v3`, a ZIP64 `.spike`
container with SHA-256 integrity per member. The authoritative specification is
[SPIKE_PROJECT_PACKAGE_V3.md](SPIKE_PROJECT_PACKAGE_V3.md). Legacy v1 and v2
JSON projects are accepted, migrated in memory, and emitted as v3 only after an
explicit save.

Workspace recall is a first-class v3 package member at
`workspace/state.json`. It records the active 2D/3D mode, dock visibility,
pinning and dimensions, active bottom tab, exact 3D camera position/target/up,
and exact 2D view box. Loading normalizes bounded dock dimensions and rejects
malformed camera or view-box data; an absent or invalid active view falls back
to fit-to-design. Workspace state never carries solver state or numerical
validity claims. Its public schema is
[`../schemas/workspace-state-v1.schema.json`](../schemas/workspace-state-v1.schema.json).

## Purpose

The legacy desktop project extension is `.spike`. v1/v2 files are UTF-8 JSON;
v3 uses the ZIP64 container described above.

Current identifiers:

- Format: `spike-project-package/v2`
- Contract: `spike/project/v2`
- MIME type: `application/vnd.spike.project+json`
- Extension: `.spike`

Legacy `spike-project-package/v1` and `spike-project-package/v2` JSON files are
accepted and migrated in memory. The next explicit save emits v3.

## Contents

```text
manifest
  application identity and source checksum
project
  stable project id and user-facing name
design
  source format, source file name, embedded source board
  imported stackup, 3D model assignments, PI/SI topology
analysis
  mode, solver, formulation, terminals, returns, limits
  mesh and frequency settings, layer and viewport state
  active result, result history, selected-net geometry
emi
  versioned setup, staged preflight, screening result
thermal
  scenario and future result references
probes
  persistent measurement definitions
selection
  optional restored selection context
```

The embedded design is required for portable packages. Large immutable artifacts such as native mesh databases, STEP models, and animation frames should move to a ZIP-based v3 container only after content-addressing, size limits, and streaming access are defined. Renaming a ZIP file to `.spike` without those controls is not acceptable.

## Integrity

Coupled multi-board setups live in AssemblyIR extensions under
`spike.multiboard-studies`, keyed by PI/SI/thermal/EM domain. Complete results
use the existing verified state artifacts. Result-free copies retain those
setups and omit their outputs. Physical assembly and exact request digests
prevent recalling results against changed placements or connection properties.
Standalone study files also open directly in the coupled study panel. See
[coupled study persistence](MULTIBOARD_COUPLED_ANALYSIS.md).

The v2 manifest records an FNV-1a checksum of the embedded design source. This detects accidental damage and inconsistent saves; it is not a cryptographic signature. Production trust requires a separate signed manifest using an asymmetric signature verified by the native host.

## Desktop File Safety

The native host follows an approved-path model:

1. Open and Save dialogs return a path chosen by the user.
2. The native process registers that path for the current process lifetime.
3. Save may overwrite only a registered path.
4. Project JSON cannot supply an arbitrary write destination.
5. Browser preview uses an explicit download fallback and has no native path identity.

This prevents untrusted project content from turning Save into an arbitrary filesystem write.

## Compatibility Rules

- Unknown top-level fields must be preserved by migration where practical.
- Required fields are `format`, `contract`, `project`, `design`, and `analysis`.
- Unsupported format revisions must fail visibly rather than load partially.
- Numerical results retain their own result contract and provenance.
- EMI setup, preflight, and screening retain their separate contracts and
  screening-only validity boundary.
- Unsupported solver data must not be promoted to a validated result during migration.
- EDA source paths are metadata only; the embedded source is authoritative for portable recall.


### Occurrence net-name display preferences

`analysis.assembly_net_name_visibility` is an optional map from board occurrence
ID to a boolean. An explicit entry overrides `analysis.show_net_names` for that
occurrence. An absent map or entry uses the existing global preference, preserving
older projects. These are display preferences and do not change electrical net
identity, geometry or solver inputs. The viewport layer selector updates only
its selected occurrence; global net-name commands clear occurrence overrides.

## Copper-zone display preferences

The optional analysis fields `zone_display` (`filled`, `transparent`, `outline`)
and `assembly_zone_display` (board-occurrence ID to mode) retain presentation
preferences. Missing or unrecognized values use `filled`. They accompany existing
`layer_opacity` / `assembly_layer_opacity` values (0–1), survive copies without
results, and never change imported geometry, materials or analysis inputs.
