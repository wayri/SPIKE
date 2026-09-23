# Wave 1 Packaged Assembly Acceptance

This is the release gate for the CAD-neutral assembly foundation. Passing it
qualifies installed interaction and persistence only. It does not qualify a
mesh, contact solve, or any PI/SI/thermal/EMI physics.

## r10 package checkpoint

The r10 engineering-preview build generated at
`2026-08-26T17:42:14.8092609+00:00` is recorded by
`artifacts/windows/installer/SPIKE-0.2.0-preview-installers.json`:

| Artifact | SHA-256 | Qualification |
|---|---|---|
| `SPIKE_0.2.0_x64_en-US.msi` (123,462,172 bytes) | `c121df2b0817690abb7e28aa7e891ddfc965eedbef8178c04401d76f9efe5ad8` | `NotSigned` r10 preview |
| `SPIKE_0.2.0_x64-setup.exe` (87,187,829 bytes) | `926f2e13fe7fd0054e3c18a86829dc510a91a7b15eeaf6bc98f61e7cd1629508` | `NotSigned` r10 preview |

The `spike/windows-installer-manifest/v1` manifest records application version
`0.2.0-alpha.1` separately from numeric MSI version `0.2.0`.

Automated r10 evidence passed under the schema v1 probe:

- 720 Python tests with one optional fixture skipped, 101 focused tests,
  architecture, 35 root integration
  tests, 17 Rust tests, all 30 frontend contract scripts, TypeScript, architecture, and the
  production frontend build;
- MSI administrative extraction with 1,549 files / 296,190,064 bytes;
- SHA-256 and size verification of all 1,081 packaged-worker members;
- extracted-worker `spike/worker-health/v1` status `ready`, with a
  `spike/packaged-worker-manifest/v2` benchmark summary of 15/15 and fresh
  source/package runtime parity of 8/8 with digest
  `8db5618aaa8c1e99b6bbfc9ee71887d3ad170f800f9013b5e40a0cf71f0dbd09`;
- a frozen-worker package write that generates a canonical typed Arrow v4
  four-row table, followed by manifest-bound source-side read and exact decode;
  artifact SHA-256: `4c34bf4fd9c8029b5403bcf26d884f2c7a6ef88c02002b06fe7edb901260c6ac`;
- packaged-worker reopen of the 23-member acceptance project described below.
- the earlier r6 local off-screen render remains diagnostic history only; it is
  not reviewed pixel evidence for this r10 checkpoint.

`scripts/qualify_wave1_packaged_assembly.py` writes
`build/wave1-packaged-assembly-acceptance.json`. The rebuilt r10 typed-profile
Arrow v4 gate passes all 20/20 automated checks. Its overall result remains
`pending_human` because both installers are unsigned and all 10 human checks
are still pending. Arrow v1-v3 compatibility is retained; their evidence is
historical only.
The report and reviewed-evidence formats are published as
`schemas/wave1-packaged-acceptance-v1.schema.json` and
`schemas/wave1-human-acceptance-evidence-v1.schema.json`.

The local render is diagnostic evidence only; these checks do not replace an
installed clean-machine interaction and reviewed pixel pass.

This r10 checkpoint is intermediate source/package evidence, not the current
release candidate: it predates the later Arrow decode-before-canonical-byte-match
security ordering fix and must not be represented as containing that fix.

## Historical r12 package checkpoint

The r12 engineering-preview build generated at `2026-08-26T18:27:06.5411639Z`
includes the Arrow canonical-byte-before-decode fix and removes the loose
duplicate typed sidecar: there is one typed authoritative package representation
and the v1 projection reconstructs its metadata.

| Artifact | SHA-256 | Qualification |
|---|---|---|
| `SPIKE_0.2.0_x64_en-US.msi` (123,503,196 bytes) | `5fd60d7dd30d59f8626c4f7a9acbc44d4f0874df2fa8a4148631aae8dc8b1bde` | `NotSigned` r12 preview |
| `SPIKE_0.2.0_x64-setup.exe` (87,219,208 bytes) | `9a2cb66c54c6a0d0d9c1d903bab1ddf5b95d3681ded1cf96bf6d11104c33d770` | `NotSigned` r12 preview |

Automated r12 evidence retains the 69 focused tests, 722 full Python tests with
one optional skip, and architecture pass; its final package/acceptance-focused
suite passes 54 tests. MSI extraction yields 1,553 files / 296,271,921 bytes; its worker is
ready, all 1,081 worker members verify, benchmarks pass 15/15, and source/package
parity passes 8/8 with digest
`0537e5dc7cd36cd59ac1be3d510a1df56f1edce77dffe7a7e30e0d682bf37906`.
The Arrow v4 four-row probe SHA-256 is
`931c522ea27c92050f43ccb2f6617447c53d07909856d815ada0a1b25b00f31e`; one
retained unresolved occurrence is package-bound and excluded from Arrow.
The schema-backed gate passes 20/20 automated checks. Overall result remains
`pending_human`: the installers are unsigned and 10 human checks remain pending.
This qualifies installed package persistence and transport only, never mesh or
physics readiness. r10, r11, and r12 are historical checkpoints.

## Historical r13 package checkpoint

The r13 engineering-preview manifest was generated
`2026-08-26T18:57:31.5575476+00:00` after the IPC-2581 v9 source change:

| Artifact | SHA-256 | Qualification |
|---|---|---|
| `SPIKE_0.2.0_x64_en-US.msi` (123,523,676 bytes) | `88a924d85f82e91d744d426fdff90a43d9dfe58b7fee4bdbb9a99cbcac0e240e` | `NotSigned` r13 preview |
| `SPIKE_0.2.0_x64-setup.exe` (87,242,366 bytes) | `22a81620489b6ad59a7198b3bad2a54e0bfab038e74162b19c90cfb985923fd3` | `NotSigned` r13 preview |

The MSI extraction at `artifacts/windows/installer-smoke-20260827-r13/PFiles/SPIKE`
has 1,553 files / 296,384,688 bytes; the bundled worker has 1,081 files /
262,605,455 bytes and reports `ready`. It passes all 15 benchmarks and the
fresh source/package runtime parity gate 8/8 with matching digest
`0537e5dc7cd36cd59ac1be3d510a1df56f1edce77dffe7a7e30e0d682bf37906`.
The Arrow v4 four-row probe passes with SHA-256
`931c522ea27c92050f43ccb2f6617447c53d07909856d815ada0a1b25b00f31e`;
one retained unresolved occurrence is package-bound and excluded from Arrow.
Broad Python evidence is 727 passed with one optional skip, the combined
focused suite is 70 passed, and architecture passes. The schema-backed gate
passes 20/20 automated checks.

The r12-r17 package records are historical. Current r18, generated
`2026-08-27T01:19:52.7158705+00:00`, has `NotSigned` MSI 123,638,540 bytes
(`639758f8170fb81c0e7cd942038ee7d48ca55a197ed46ff6eff279fc9e2085e1`) and
`NotSigned` NSIS 87,310,439 bytes
(`ca8f6090cb3dbb0d49463385ad44ab3d732c3e0913e76c418545aff7d99c03dd`). Its
extraction at `artifacts/windows/installer-smoke-20260827-r18/PFiles/SPIKE`
has 1,564 files / 296,613,533 bytes and a ready 1,081-file / 262,625,391-byte
worker with IPC-2581 v13 and the 64 MiB JSON cap present.
`build/wave1-packaged-assembly-acceptance-r18.json` passes 21/21 automated
checks. The result is unsigned `pending_human` with 0/10 human evidence.
Staged r18 MSI/NSIS harnesses bind inputs
`f149a969bf14d0b3f6f3ed0d0fb759e6c2890a19e8f31ac71d23e5c87d544790` and
`67d2c80a727b110939083c10860f2836d7b2ab42123585920186799ccb75d8c6`, but
supply no human evidence. This preserves all Wave 1, Wave 2, mesh, solver,
physics, legal, signing, Linux/macOS, upgrade, uninstall, and user-pixel gates.
The repository-built portable engineering preview at
`artifacts/windows/SPIKE-0.2.0-windows-x64-portable` with ZIP
`artifacts/windows/SPIKE-0.2.0-windows-x64-portable.zip` has SHA-256
`47e59bf365e7d8752af24181911f1f0c238df21d2e3d5d90ae5f0f41ef6d7184`; its
portable manifest v1 records 1,551 files / 296,411,495 bytes / zero failures,
and bundled-worker health is `ready`. This closes repository-built portable
preview evidence only—not signing, legal, clean-machine, user-pixel, upgrade,
uninstall, production, or Wave 1 requirements.

## Bounded temporary section box

The implemented six-plane MCAD section box is a temporary visual-only viewport
control. One shared clipping builder applies it to glTF/GLB visuals and to
exact-selector previews. Invalid, non-finite, or inverted bounds disable
clipping. The state is not persisted to AssemblyIR or the package, and it has
no topology, mesh, solver, or physics semantics.

## Acceptance fixture

Build or refresh the fixture from repository-owned demo boards, a locked
FreeCAD runtime, and a reviewed self-contained GLB:

```powershell
python scripts/build_wave1_assembly_acceptance_fixture.py
```

Open `artifacts/wave1-assembly-acceptance/wave1-assembly-acceptance.spike`.
Its sibling JSON records the exact manifest, design, part, and shape identities.
The fixture contains:

- two complete retained DesignIR v2 boards and one board-to-board harness;
- connector mapping and rigid/flex structure records;
- two retained STEP parts with exact OCC BREP shapes, analytic selectors,
  selector previews, and derived visual-only GLBs;
- one directly attached self-contained GLB;
- explicit `topology_ready: true`, `visual_only: true`, and
  `solver_ready: false` qualification.

## Clean Windows acceptance procedure

Use a clean supported Windows VM and record OS, GPU, WebView2, display scale,
installer hash, and SPIKE version with the evidence.

Use the repository-owned [clean-machine harness](WAVE_1_CLEAN_MACHINE_HARNESS.md)
to stage hash-bound inputs and collect objective installation/package evidence.
Only its v2 record is qualification-eligible: a provider label by itself is
insufficient, and a structurally bound environment attestation remains a human
review input rather than proof. It does not replace any of the following human
checks or reviewed pixel pass.

1. Verify the chosen installer SHA-256 against the manifest. Install it without
   a development checkout or Python/Node environment on `PATH`.
2. Launch from the Start menu and by double-clicking the canonical acceptance
   `.spike` fixture. The cold-start file argument must be bounded, canonical,
   and handled once only. Require one application window, no console window, a
   responsive viewport, and no remote-content or missing-worker warning.
3. Confirm the assembly navigator and MCAD editor expose two board instances,
   three parts, the harness, two retained design choices, and honest STEP/GLB
   status. No control may claim solver readiness.
4. Capture fixed-camera top, bottom, oblique, isolated-part, and X/Y/Z section
   views. Require visible board and MCAD geometry, stable depth ordering, no
   clipping streaks or unexpected pixels, and matching part transforms.
5. Translate and rotate the lid with numeric controls and the 3D gizmo using
   its persisted increments. Save and reopen; require the exact matrix,
   visibility, opacity, isolation reset, and section-state behavior documented
   by the UI.
6. Reparent the lid between the assembly root, a board, and the enclosure.
   Require its assembly-world pose to remain unchanged after each transaction
   and after reopen. A self/descendant target must not be offered.
7. Select one exact planar face on each STEP-derived part, save a compatible
   coincident or distance definition, and apply B to A. Require one rigid move,
   checked residual success, unchanged STEP/BREP/preview digests, and the same
   placement after reopen. Ordinary GLB triangles and section planes must never
   appear as topology references.
8. Change the second board transform and choose its retained DesignIR from the
   selector. Edit harness length/pin map, connector mapping, and rigid/flex
   data. Save and reopen; require all identities and values to persist while
   coupled PI/SI/thermal remains rejected.
9. Exercise STEP attachment, tessellation, exact extraction, and selector
   preview generation once from the installed UI. Cancel one long operation
   and confirm the project remains readable and unchanged.
10. Verify `.spike` file association, same-version repair/upgrade behavior,
    uninstall, and user-project preservation. Repeat the install/launch/open
    smoke with the NSIS artifact if MSI was primary.

## Pass record

Record the ten required checks with contract
`spike/wave1-human-acceptance-evidence/v1`, hashed relative artifacts, reviewer,
timestamp, installer digest, and before/after manifest digests. Then run:

```powershell
python scripts/qualify_wave1_packaged_assembly.py `
  --extracted-root artifacts/windows/installer-smoke-20260827-r18/PFiles/SPIKE `
  --human-evidence <evidence.json> `
  --require-human
```

The gate passes only when the installer hash, environment record, action log,
before/after package manifests, and reviewed screenshots are attached, every
step above passes, and no open severity-1/2 visual or persistence defect remains.
Until then Wave 1 stays open and Wave 2 must not advance. Clean-machine,
pixel-review, upgrade, and uninstall evidence remains pending.
