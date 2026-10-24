<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0138: Reviewed links to saved CAD source files

Date: 2026-10-24. Status: accepted for source development; installed acceptance open.

## Decision

Store explicit target-kind/identity, local source path and SHA-256 fingerprint
under project analyses `linked_sources`, mirrored in the legacy presentation
snapshot for lossless desktop persistence. A target is a retained canonical
board design or model, not an individual occurrence. One shared source refresh
therefore updates all instances; independent copies remain separate targets.

Python owns bounded file admission, stable reads, adapter invocation, removed
entity checks, source artifact retention and compare-and-swap package writes.
Existing importers remain authoritative. The TypeScript Project manager offers
target search, opt-in status checks, reviewed fingerprint application and
recovery messages. The thin Rust host admits only opened manifest-bound project
operations; linking requires a chooser-approved file. Status and refresh resolve
saved paths in Python, never caller path overrides. The generic worker route
rejects these methods. No new dependency or implementation language is added.

Changes are pulled from saved files only. There is no source writeback or
unsaved-editor IPC. A source revision must initially match retained bytes. Apply
requires the current reviewed SHA-256 and explicit result invalidation; changed
source or package identities reject the transaction. Occurrence and model
placements remain. Stale constrained topology and removed referenced entities
block updates; no name-based identity remapping is performed. STEP-derived
visuals must be regenerated when their source changes.

## Verification and limits

The focused Python suite covers actual KiCad placement/routing changes, model
artifact replacement, retained placements/setup, removed references, stale
hashes, package identities, no-op byte preservation and topology handling.
Frontend interaction checks cover project-target routing, failed-apply recovery,
review fingerprints, dirty locks, unlink and stale asynchronous responses.
Native host tests cover chooser grants, manifest trust and generic-route bypass.
See [the user workflow](../LINKED_CAD_SOURCES.md).

Installed desktop save/check/review/apply acceptance remains a separate gate.
Links are local paths and require relocation on another machine. Files are
bounded to 64 MiB; dependency graphs, external libraries, external glTF resources
and bidirectional ECAD/MCAD editing are outside this contract. Geometry updates
require setup review and new solver runs, not inherited result validity.
