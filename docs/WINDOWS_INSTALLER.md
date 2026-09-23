# Windows Installer and Release Boundary

## Preview build

From the repository root:

```powershell
.\scripts\build_windows_installer.ps1 -Channel Preview
```

The script runs architecture, error-contract, schema, frontend, and Rust tests;
builds the packaged worker; asks Tauri to produce NSIS and MSI bundles; copies
the installers to `artifacts/windows/installer`; and writes a SHA-256 manifest.
The NSIS installer supports per-user or per-machine installation and registers
the `.spike` project association.

Windows Installer requires a numeric product version, so the current MSI/NSIS
package uses `0.2.1`. The `spike/windows-installer-manifest/v1` manifest records
the separate `application_version` of `0.2.0-alpha.2`. This does not promote the
physics or release qualification state.

Preview installers display `licenses/SPIKE-PREVIEW-NOTICE.md` and include the
repository notice, licensing policy, third-party notices, commercial EULA
draft, troubleshooting guide, and error-code catalog. They are not approved for
sale or production engineering reliance.

Preview packages pin the public key in `config/license-preview-public.json`.
The corresponding private key is external to the repository and bundle. A
preview without a pinned public key is rejected by the packaging script because
it could never activate a signed entitlement.

## r10 package checkpoint

The 2026-08-26 r10 preview build (generated
`2026-08-26T17:42:14.8092609+00:00`) produced and verified:

- `SPIKE_0.2.0_x64_en-US.msi` (123,462,172 bytes), SHA-256
  `c121df2b0817690abb7e28aa7e891ddfc965eedbef8178c04401d76f9efe5ad8`
  (`NotSigned`).
- `SPIKE_0.2.0_x64-setup.exe` (87,187,829 bytes), SHA-256
  `926f2e13fe7fd0054e3c18a86829dc510a91a7b15eeaf6bc98f61e7cd1629508`
  (`NotSigned`).
- An MSI administrative-extraction smoke with 1,549 installed files / 296,190,064
  bytes, including `spike-worker.exe`, its integrity manifest, and packaged
  legal resources.
- A worker launch from the extracted image returning `ready` under
  `spike/worker-health/v1`.
- Integrity verification of all 1,081 worker-manifest members, 15/15 packaged
  worker benchmarks, and 8/8 source/package runtime qualification checks under
  `spike/packaged-worker-manifest/v2`, with runtime digest
  `8db5618aaa8c1e99b6bbfc9ee71887d3ad170f800f9013b5e40a0cf71f0dbd09`.
- A packaged-worker reopen of the two-design, two-STEP-shape, direct-GLB Wave 1
  assembly fixture. See [Wave 1 packaged acceptance](WAVE_1_PACKAGED_ASSEMBLY_ACCEPTANCE.md).
- The r10 packaged worker generated, persisted, and source-verified the typed
  Arrow v4 four-row probe; its artifact SHA-256 is
  `4c34bf4fd9c8029b5403bcf26d884f2c7a6ef88c02002b06fe7edb901260c6ac`.
  Arrow v1-v3 remain compatible; their prior proofs are historical context only.
- The earlier r6 off-screen capture is retained as diagnostic history, not as
  reviewed pixel evidence for this r10 checkpoint.
- `build/wave1-packaged-assembly-acceptance.json` passes all 20/20 automated
  checks. Overall status remains `pending_human`; all 10 human checks remain
  pending.

Both bundles remain unsigned engineering previews. Administrative extraction
does not replace clean-VM install, pixel review, upgrade, file-association,
uninstall, and rollback acceptance. The cold-start `.spike` argument handling
is bounded, canonical, and one-shot; its clean-machine evidence is still
pending. This is intermediate source/package evidence and is superseded as a
release candidate by the later Arrow decode-before-canonical-byte-match security
ordering fix; r10 itself does not claim to contain that fix.

## Historical r12 package checkpoint

The r12 engineering-preview build, generated `2026-08-26T18:27:06.5411639Z`,
includes the Arrow canonical-byte-before-decode fix and loose duplicate typed
sidecar cleanup. It produced:

- `SPIKE_0.2.0_x64_en-US.msi` (123,503,196 bytes), SHA-256
  `5fd60d7dd30d59f8626c4f7a9acbc44d4f0874df2fa8a4148631aae8dc8b1bde`
  (`NotSigned`);
- `SPIKE_0.2.0_x64-setup.exe` (87,219,208 bytes), SHA-256
  `9a2cb66c54c6a0d0d9c1d903bab1ddf5b95d3681ded1cf96bf6d11104c33d770`
  (`NotSigned`);
- MSI administrative extraction with 1,553 files / 296,271,921 bytes, a ready
  worker, 1,081 verified worker-manifest members, 15/15 benchmarks, and 8/8
  source/package parity with digest
  `0537e5dc7cd36cd59ac1be3d510a1df56f1edce77dffe7a7e30e0d682bf37906`;
- a typed Arrow v4 four-row probe with SHA-256
  `931c522ea27c92050f43ccb2f6617447c53d07909856d815ada0a1b25b00f31e`.
  One retained unresolved occurrence is package-bound and excluded from Arrow.

The prior 69 focused and 722-full-with-one-optional-skip evidence remains;
the final r12 focused package/acceptance suite passes 54 tests. The
schema-backed gate passes 20/20 automated checks. Overall status remains `pending_human`:
both installers are unsigned and all 10 human checks remain pending. This is
package and transport evidence only, not a production-physics qualification.
The r10, r11, and r12 checkpoints are historical.

## Historical r13 package checkpoint

The r13 engineering-preview build was generated
`2026-08-26T18:57:31.5575476+00:00` after the IPC-2581 v9 source change.

- `SPIKE_0.2.0_x64_en-US.msi` is 123,523,676 bytes, SHA-256
  `88a924d85f82e91d744d426fdff90a43d9dfe58b7fee4bdbb9a99cbcac0e240e`
  (`NotSigned`).
- `SPIKE_0.2.0_x64-setup.exe` is 87,242,366 bytes, SHA-256
  `22a81620489b6ad59a7198b3bad2a54e0bfab038e74162b19c90cfb985923fd3`
  (`NotSigned`).
- Administrative extraction at
  `artifacts/windows/installer-smoke-20260827-r13/PFiles/SPIKE` contains
  1,553 files / 296,384,688 bytes; its worker contains 1,081 files /
  262,605,455 bytes and reports `ready`.
- The packaged worker passes 15/15 benchmarks and fresh 8/8 source/package
  runtime parity with matching digest
  `0537e5dc7cd36cd59ac1be3d510a1df56f1edce77dffe7a7e30e0d682bf37906`.
  Its Arrow v4 four-row probe passes with artifact SHA-256
  `931c522ea27c92050f43ccb2f6617447c53d07909856d815ada0a1b25b00f31e`;
  one retained unresolved occurrence is package-bound and excluded from Arrow.
- Broad Python evidence is 727 passed with one optional skip; the combined
  focused suite is 70 passed and the architecture check passes. The schema
  gate passes 20/20 automated checks.

r14-r15 are historical. r15 was generated `2026-08-26T23:05:46.0259327+00:00`:
the `NotSigned` MSI is 123,617,980 bytes, SHA-256
`9f396046fa0e392a9daea6f45acbc3b0242a4e0de348ef00ec9a57a0480a1c23`, and the
`NotSigned` NSIS installer is 87,288,223 bytes, SHA-256
`54d834f9813613fde4bc9071b8b754500673e3b04743df9d9063a482ad4365d3`.
Extraction at `artifacts/windows/installer-smoke-20260827-r15/PFiles/SPIKE`
has 1,559 files / 296,548,059 bytes; its 1,081-file / 262,619,732-byte worker
is `ready`. It passes 15/15 benchmarks, embedded/fresh parity 8/8
(`8db5618…` / `0537e5dc…`), and its Arrow v4 four-row probe SHA-256 is
`30c24729efa63187daf3a8d3c26167ebd89b65836cf7f758e86d0e96604bb988`, with one
retained unresolved occurrence excluded from copper. The 23-member fixture and
`build/wave1-packaged-assembly-acceptance-r15.json` automation passes 21/21,
including `worker.fixture_mutation_reopen`: a temp-copy extracted-worker update
persists visibility, 0.625 opacity, and placement-policy-valid translation and
rotation; it chains manifest identities, reparents world-preservingly to the
board frame, leaves model/package-shape artifacts unchanged, canonically
reopens deterministically, and keeps `solver_ready: false`.
That historical checkpoint used IPC-2581 v12. Overall r15 remained `pending_human`: both
installers are unsigned and all 10/10 clean-machine human checks are absent.
Exact hash-bound clean-machine harnesses are staged at
`artifacts/wave1-clean-machine-r15-msi` and
`artifacts/wave1-clean-machine-r15-nsis`; staging neither provisions nor
executes an isolated machine and satisfies no human check.
The historical r16 portable preview used the fixed paths now replaced by r17
and had ZIP SHA-256
`8b497a72c3cd7e844464fdd794df6b705dece609a235c5489b222d1050514588`; its
portable manifest v1 records 1,548 files / 296,380,909 bytes / zero failures,
and bundled-worker health is `ready`. This closes repository-built portable
preview evidence only—not signing, legal, clean-machine, user-pixel, upgrade,
uninstall, production, or Wave 1 requirements.
This is installer/package and transport evidence only; it does not complete
Wave 1 or qualify mesh or production physics.

The r12-r17 package records above are historical. Current unsigned r18 (IPC-2581 v13) was generated `2026-08-27T01:19:52.7158705+00:00`: the `NotSigned` MSI is 123,638,540 bytes, SHA-256 `639758f8170fb81c0e7cd942038ee7d48ca55a197ed46ff6eff279fc9e2085e1`, and the `NotSigned` NSIS installer is 87,310,439 bytes, SHA-256 `ca8f6090cb3dbb0d49463385ad44ab3d732c3e0913e76c418545aff7d99c03dd`.
Extraction at `artifacts/windows/installer-smoke-20260827-r18/PFiles/SPIKE` has 1,564 files / 296,613,533 bytes and a ready 1,081-file / 262,625,391-byte worker; IPC-2581 v13 and the 64 MiB JSON control-plane cap are present. `build/wave1-packaged-assembly-acceptance-r18.json` passes 21/21 automated checks and remains unsigned `pending_human` with 0/10 human evidence. Fresh v2 MSI/NSIS staging at `artifacts/wave1-clean-machine-r18-v2-msi` / `artifacts/wave1-clean-machine-r18-v2-nsis` binds inputs `f90dfbc2502166e06ebaca0187cf902ff22364f83f549c208a772d5c46055310` / `7f8d75f5fc7d652ed33a9dd9f09f12f759877f82cec3959b95eaf872539f3758`; the old r18 staging binds legacy v1 and is nonqualifying. Staging supplies no human evidence. The portable ZIP SHA-256 is `47e59bf365e7d8752af24181911f1f0c238df21d2e3d5d90ae5f0f41ef6d7184`; its manifest verifies 1,551 files / 296,411,495 bytes / zero failures and bundled-worker health is `ready`. No legal/signing/clean-machine/user-pixel/upgrade/uninstall/Linux/macOS/Wave 1/Wave 2/mesh/solver/physics promotion occurs.

## Current local engineering-preview deployment (2026-08-30)

The current tree is released as application `0.2.0-alpha.2`, numeric Windows
package `0.2.1`, and installed for the current user at
`C:\Users\example\AppData\Local\Programs\SPIKE`.

- `SPIKE_0.2.1_x64_en-US.msi`: 123,897,127 bytes, SHA-256
  `0d49e667175c28530f4344f1c3d321bac611257f5e9c3c55d4cd59e21a039822`
  (`NotSigned`).
- `SPIKE_0.2.1_x64-setup.exe`: 87,164,894 bytes, SHA-256
  `126be912c0cf6889a37b3196d539910a1ee37f7ca64b10e41ac9b098e5952b24`
  (`NotSigned`).
- The installed and release `spike-desktop.exe` files have identical SHA-256
  `8297816126d9b162d960dfef125d6b3d5b1ff2ffee2a6885487d95fb6b0279b7`;
  Windows reports file/product version `0.2.1`.
- The current-user Start Menu shortcut resolves to that executable and a bounded
  launch smoke stayed running until the test process was closed. Three obsolete
  preview executables were moved to the recoverable
  `legacy-preview-backup-20260830` install subdirectory.
- The packaged worker reports application `0.2.0-alpha.2`, verifies all 1,084
  declared members, passes 15/15 benchmarks, and passes 8/8 source/package
  runtime checks with matching digest
  `4eb83e6d634eaa4c3c362d61642b953f4ed4721ff0b888ab332d198b7ceea5fa`.
- Installed-image Wave 1 automation passes 21/21 in
  `build/wave1-packaged-assembly-acceptance-alpha2-installed.json`; overall
  status remains `pending_human`.
- The current PI release gate remains fail-closed at 2/8. SI protocol suites are
  configuration-only and geometry-derived SI signoff remains unsupported.

This is an unsigned engineering preview. It does not satisfy production
signing, legal approval, clean-machine/human acceptance, Linux/macOS packaging,
or physics qualification.

## Historical local engineering-preview deployment (2026-08-28)

The current working tree was rebuilt without `-SkipWorker` and deployed to the
current Windows user at
`C:\Users\example\AppData\Local\Programs\SPIKE`. The generated preview manifest
timestamp is `2026-08-28T01:58:00.9517649+05:30`:

- MSI: 123,827,116 bytes, SHA-256
  `159bcaf5429d5b30d66cb7702ebe2ceb637955e96ec12fe077baf8db1965551d`.
- NSIS: 87,393,580 bytes, SHA-256
  `2668c54ef06b28c1999578f610a82e99fb852ad3c21f69e1277b4063c615d344`.
- Both artifacts are `NotSigned`; the manifest remains
  `engineering-preview` with `production_qualified: false`.
- Fresh source/package runtime qualification passes 8/8. Installed-image
  acceptance passes 21/21 automated checks, including all 1,081 packaged-worker
  member hashes, ready health, 15/15 benchmarks, Arrow v4, assembly fixture
  reopen, and transactional mutation/reopen. Overall status remains
  `pending_human`; physics is `not_qualified` and `solver_ready` is false.
- The installed `spike-desktop.exe` SHA-256
  `f488b44dfc630d3d4c8e6292ec85645bf70e52250c146c22cfd29baeaf852101`
  exactly matches the just-built release executable and launches responsively.

The MSI was not installed because Windows Installer correctly returned error
1925 without an administrator token. The same verified candidate's supported
NSIS `/CurrentUser` mode completed without elevation. This is local preview
deployment evidence, not a clean-machine, signing, legal, production, or
physics-qualification gate.

## Production gate

`-Channel Production` intentionally fails while any release gate is incomplete.
It requires a legally approved EULA, a pinned entitlement issuer, Windows code
signing configuration, complete provenance/SBOM/notice evidence, production
qualification, and an explicit Authenticode implementation. Removing that fail
closed behavior is not a valid release procedure.

### Signed production candidates

The immutable preview contract remains `spike/windows-installer-manifest/v1`:
it is an unsigned `engineering-preview` and cannot be promoted by editing its
manifest. A Windows artifact built for release evaluation instead uses
`spike/windows-installer-manifest/v2`. It contains exactly one MSI and one
NSIS installer, after signing, with their final SHA-256 values, byte sizes, and
public Authenticode identity. Both must verify as `Valid`, use SHA-256, match
the configured signer thumbprint, and carry an RFC 3161 timestamp authority.

A v2 artifact is a `production-candidate`, with `production_qualified: false`.
Signing proves the identity and integrity of those exact bytes; it does not
approve commercial distribution, Wave 1, a solver, mesh, or physics. Production
qualification is a separate release decision after all required evidence has
passed.

Clean-machine Wave 1 evidence for a signed candidate uses
`spike/wave1-human-acceptance-evidence/v2`. It binds the reviewed installer
file and final SHA-256 to the exact installer-manifest SHA-256, signer
thumbprint, and RFC 3161 timestamp-authority thumbprint. A report can therefore
not transfer a successful review to a rebuilt installer with the same version.
The resulting `spike/wave1-packaged-acceptance/v2` report still states
`physics: not_qualified` and `solver_ready: false`.

The development issuer private key must remain outside the repository,
installer, logs, and CI artifacts. Production binaries contain only approved
public verification keys. See [License issuance](LICENSE_ISSUANCE.md) for the
isolated issuer workflow.

The Windows Authenticode private key follows the same boundary: it is accessed
through an approved certificate store/HSM or signing service. PFX files,
passwords, token PINs, and private-key material must not enter the repository,
installer, environment dumps, manifest, CI artifact, or build log. Certificate
thumbprints and timestamp-authority thumbprints are public identities and are
recorded only to make verification reproducible.

### Release provenance and SBOM

Wave 1 now has fail-closed, post-signing evidence schemas
`spike/windows-release-sbom/v1` and
`spike/windows-release-provenance/v1`. `scripts/check_windows_release_inputs.py`
checks the approved dependency inventory and pinned build/runtime inputs;
`scripts/build_windows_release_provenance.py` writes deterministic SBOM and
provenance evidence; and `scripts/verify_windows_release_provenance.py`
revalidates the evidence, installer identities, worker inventory, notices, and
dependency signature without network access. `scripts/windows_cms.ps1` creates
and verifies the required SHA-256 detached CMS sidecar using the configured
release certificate. Focused coverage is in
`tests/python/test_windows_release_provenance.py` and
`tests/python/test_windows_signing_contract.py`.

For a future production candidate, `build_windows_installer.ps1` creates the
detached dependency CMS sidecar before packaging, stages exact public evidence
with `scripts/stage_windows_release_evidence.py`, and uses
`app/src-tauri/tauri.production.conf.json`. Staging is safe-relative,
path/digest-bound, preserves installer bytes, and stages only the dependency
lock and CMS sidecar, worker manifest, notices, component inventory/approvals,
and approved public review evidence. After exact MSI and NSIS signing, modern
SBOM/provenance build and verification bind the staged inputs and an explicit
packaged-worker root. The production config embeds the CMS sidecar, component
review inputs, pinned Python locks, signing policy, and draft EULA; none is a
legal-approval or release-qualification assertion.

The 36-wheel Windows CPython 3.12 runtime is now exact and hash-pinned in
`requirements-runtime-windows-x64.txt`; the downloaded wheel set passed an
offline `pip install --dry-run --no-index --require-hashes` resolution check.
The checked-in Windows x64 component inventory is present and current:
`config/windows-component-inventory.json` (`spike/windows-component-inventory/v1`)
contains 474 lock-derived components: 303 `bundled` and 171 `build-only`
(276 Rust, 143 npm, and 55 Python). Its matching
`licenses/windows-component-approvals.json`
(`spike/windows-component-approvals/v1`) has exact coverage for all 474
identities, but all 474 dispositions remain `pending_review`; it is not an
approved release inventory. `THIRD_PARTY_NOTICES.md` remains incomplete, so
human license/redistribution approvals and notice coverage remain legally
pending. `scripts/build_windows_notice_review_packet.py` now emits the
schema-valid, non-decisional `build/windows-notice-review-packet.json` reviewer
queue: all 474 identities are deterministically covered (303 bundled / 171
build-only), all 474 still require notice text and legal review, 39 license
declarations are not SPDX-shaped, and 2 additional `LicenseRef` declarations
remain unresolved. Its SHA-256 is
`6249b41204fbcd0ee17ff42c301a292441be78ae0ea014a8d8491d6c3dab686b`.
It grants no approval or redistribution right and does not modify the release
notice bundle. The required detached CMS sidecar is absent. There is no signed
candidate or clean-VM evidence. Therefore Wave 1 is incomplete, Wave 2 is
unopened, and this work does not promote mesh, solver, or physics qualification.

`scripts/collect_windows_notice_evidence.py` now emits the separate
schema-backed `build/windows-notice-evidence-index.json` candidate-text index.
It is deterministically bound to all 474 inventory PURLs and identities, uses
root-relative source locators, rejects stale lock inputs and unsafe or over-4
MiB archive candidates, and prevents nested npm or vendored-wheel license text
from being attributed to a parent component. The current index SHA-256 is
`9ffa5fbb5ca0de4aa83f0264c2822c93bbbed8907eb4619a41b6d97489ffb616`:
637 candidate records reference 286 content-addressed blobs, while 74
components still have no locally available candidate text. Candidate text is
not a legal decision: all 474 approvals remain `pending_review`, notices remain
incomplete, and the production verifier is unchanged.

Targeted project-package Arrow geometry reads also reject a manifest-declared
or actual ZIP-member size over the 256 MiB budget, and any declared/actual size
mismatch, before decompression and payload retention. This is an imported-data
resource boundary only; it does not affect installer acceptance or qualify
physics.

## Security notes

- A signed local entitlement is bound to one machine and operating-system user.
- Strict one-seat assignment, revocation, and lost-device recovery require the
  licensing service; an offline file cannot enforce issuer-side uniqueness.
- Windows production builds must be Authenticode signed and timestamped. The
  preview manifest records the current signature status for every artifact.
- Tauri uses WebView2 on Windows. The preview uses the download bootstrapper if
  the runtime is absent; an offline WebView2 strategy must be selected and
  tested for an offline production package.
