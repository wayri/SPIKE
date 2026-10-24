<!-- SPDX-License-Identifier: Apache-2.0 -->
# Portable visual preflight performance - 24 October 2026

Portable JSON project loading validates self-contained GLB artifacts before
materializing them. Its synchronous preflight converted the decoded binary
string through `Uint8Array.from` with a callback for every byte. This generic
string-iterator path is expensive on the UI thread. The visual bundle decoder
already uses a preallocated byte array and an indexed `charCodeAt` loop.

`projectPersistenceArtifacts.ts` now uses that same exact conversion in its
GLB preflight. Metadata, base64 decoding, limits, GLB header/version/length and
JSON chunk checks, external-resource rejection, later SHA-256 validation and
off-thread visual decoding remain unchanged. No validation pass was removed.
Native package transport and physics implementations are unchanged.

The bounded synthetic GLB is 131,164 bytes and includes every binary byte value.
On Node v24.14.0 Windows x64, seven alternating pairs of three calls each gave
median preflight times of **10.6063 ms before and 0.38393 ms after** (27.6x).
This includes base64 decode and the existing GLB JSON/header preflight. Raw
samples, source hash and fixture hash are retained in
`output/performance-20261024/visual-loading/report.json`; the exact pre-change
source is retained beside it. No native board-load or responsiveness stress
test was performed by this small transport benchmark. Whole project loading,
peak memory and native/UI frame-rate improvements are not established here.

The new behavioral test observes the complete converted byte buffer and
compares it byte-for-byte with the independent GLB input. It also verifies
external-URI, invalid metadata and GLB-version rejection. Existing real GLB/SVG
save/restore, hashing, copper policy and disposal tests remain part of the
project-persistence and board-visual test commands.

Reproduce from `app`:

```text
node scripts/test-project-visual-byte-conversion.mjs ../output/performance-20261024/visual-loading/projectPersistenceArtifacts.before.ts ../output/performance-20261024/visual-loading/report.json
npm run test:project-persistence
npm run test:board-visuals
```
