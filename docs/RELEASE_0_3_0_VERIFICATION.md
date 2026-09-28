# SPIKE 0.3.0 engineering preview candidate verification

## Current source check: 2026-09-29

The 2026-09-28 installer hashes below describe an earlier local candidate.
They do **not** identify the current source snapshot. The current-source
community preview is an **unsigned MSI only**; NSIS could not be rebuilt in
this environment. The owner stated on 2026-09-29 that they reviewed the beta
and authorized a community testing release. This does not promote any solver
to validated or production-qualified status.

Checks run against the current tree:

- `git diff --check` and `scripts/check_architecture.py`: passed.
- `npm run test:help`: passed with the project virtual environment on `PATH`
  (1,491 control sites, 94 CLI pages, 80 diagnostics).
- `npm run build`: passed outside the restricted filesystem sandbox. The
  bundle reported large-chunk warnings but no build error.
- `cargo test --locked --offline --lib`: 34 passed, one live OS counter test
  ignored.
- Focused board import, project package, shared simulation workspace,
  PI series handoff, SI channel/plot, thermal UI, EM radiation viewport,
  result viewport, parser, and viewport policy checks passed. The shared
  workspace test was updated to assert the current EMerge-aware Ports route.
- `scripts/build_windows_installer.ps1 -Channel Preview` passed its
  architecture, error/schema, frontend, Rust, packaged-worker build, and
  worker-integrity steps. It compiled `spike-desktop.exe`, then failed during
  NSIS bundling: the local NSIS cache was incomplete and Tauri's attempted
  download timed out. Its two-installer manifest was not produced.
- `npm run tauri -- build --bundles msi` succeeded. An MSI administrative
  extraction (`msiexec /a`) succeeded and contained `legal/LICENSE`,
  `legal/NOTICE`, `legal/LICENSING.md`, `legal/THIRD_PARTY_NOTICES.md`,
  `legal/licenses/MIT.txt`, the desktop executable, and the packaged worker.
  The extracted worker executable SHA-256 matched the verified source-build
  worker executable exactly. This checks package contents, not clean-machine
  installation or operation.
- `scripts/check_windows_release_inputs.py` rejected the production inputs:
  no exact wheel bytes match `jsonschema==4.25.1`.
- The PI release-qualification command still reports `blocked`: two of eight
  checks passed; six required native workflow promotions remain blocked.
- `.venv\Scripts\python.exe -m unittest discover -s tests/python -q`:
  2,132 run, six skipped, no failures (1,118.860 seconds).
- CMake source-build validation could not start in this shell because no C++
  compiler is available.

Current MSI: `artifacts/windows/community-preview-20260929/SPIKE_0.3.0_x64_en-US.msi`
(144,814,585 bytes; SHA-256
`f38f9f42c71c10d8ef29f4fa5a14ed98913f76f88495c8088bb8e8f253ad1e68`;
Authenticode `NotSigned`). The community release must state that this MSI
requests all-user privileges and that source-independent numerical review,
clean-machine installation/upgrade/uninstall checks, artifact-specific
dependency notices, and trusted signing have not been recorded. The PI gate
remains blocked. Do not use the older candidate's hashes for this MSI or
present the community preview as qualified engineering software.

Date: 2026-09-28. This is a local installer candidate, not a published release.
The candidate scope excludes `integrations/freecad/` and its workbench assets.
It also excludes the independently versioned SPIKES circuit engine and the
separate `spike-solvers` repository.

## Checks completed

- `npm run check:architecture`: passed.
- `npm exec tsc -- --noEmit`: passed.
- `npm run test:parser`: passed (32 copper / 35 total layers).
- `npm run build`: passed after rerunning outside the restricted filesystem
  sandbox. Vite reported large bundle chunks; it did not fail the build.
- `npm run test:bug-report`: passed for the metadata allowlist and issue-form URL.
- `npm run test:help`: passed after regenerating the control inventory for the
  new Help menu command (1,427 controls, 94 CLI pages, 80 diagnostics).
- `cargo check --locked --offline`: passed after adding the scoped Tauri
  external-link opener.
- `cargo test --locked --offline`: 29 passed, one live OS counter test ignored.
- `powershell -ExecutionPolicy Bypass -File scripts/build_windows_installer.ps1 -Channel Preview`: passed. It ran architecture, error-contract, schema, frontend, Rust, packaged-worker, NSIS, and MSI build steps. The bundled worker integrity manifest was verified by the build script.
- `python -m unittest tests.python.test_marble_contact_loss_probe -q`: three passed in the Python 3.12 virtual environment.
- `python -m unittest tests.python.test_windows_signing_contract -q`: seven passed after installer packaging released the checkout mutex.
- `.venv\Scripts\python.exe -m unittest discover -s tests/python -q`: 2,106 tests passed, six skipped, after the preview build released the checkout mutex.
- Both 0.3.0 installer sizes and SHA-256 digests were independently recomputed and match the manifest below.
- `python scripts/check_solver_qualification_environment.py` in the local
  Python 3.12 virtual environment: dependency/native API inventory passed.
  This inventory does not qualify numerical results.
- `scripts/run_board_thermal_example.py` completed on the checked-in eBrake1
  example. The 36 × 21 grid remained `approximate`; the saved summary exactly
  matched `docs/validation/ebrake1-board-thermal-result.json` (2.4 W applied,
  2.4 W outward, `-6.75e-14 W` balance error, `2.55e-14` relative residual).
  These are discrete-system checks with assumed inputs, not measured accuracy.

## Open failures and release gates

- The initial full Python suite ran 2,105 tests with 1 failure, 18 errors,
  and 26 skips. The 18 errors were missing-Shapely imports. Shapely 2.1.2
  is now recorded in the Windows runtime lock. The Marble difference was
  Python-version-sensitive accumulation in the mesh polygon area. A bounded
  compatibility fix preserved the established diagnostic graph, expected
  value, and tolerance. Focused Marble tests pass under Python 3.11 and 3.12;
  this is reproducibility evidence, not physical accuracy signoff. Earlier,
  the Python suite was rerun with Shapely: 2,106 tests, one failure,
  six skips. That single failure was the production-packaging test encountering a checkout
  installer mutex held by another build instead of reaching its expected
  release-input rejection. The affected seven-test signing-contract module and
  the fresh full suite pass after the preview build released the mutex.
- The separate `spike-solvers` source check passed (102 files). Its Python
  source suite passed 46 tests with three native-dependent skips. It has not
  been updated with the current SPIKE numerical changes or qualified for a
  binary release.
- `scripts/check_windows_release_inputs.py` rejects the current package inputs
  because the exact `jsonschema==4.25.1` runtime wheel bytes are not in its
  configured wheel directory. The newly added Shapely and Tauri opener
  dependencies also require fresh component inventory, license approvals, and
  artifact-specific notices. The dependency and notice gate is therefore open.
- The original preview installers are unsigned. Self-signed copies are recorded
  below, but their certificate is untrusted and they have no RFC 3161 timestamp.
  An installed-worker test, clean-machine test, artifact-specific SBOM/notice
  bundle, trusted production-signing record, and knowledgeable human numerical
  review have not been recorded for this candidate.
- `docs/PI_RELEASE_QUALIFICATION.md` still records the deployable PI gate as
  blocked. A current invocation reported 2 passing checks and six blocked
  required workflows. `docs/PUBLIC_RELEASE_READINESS.md` separately records the SPIKES
  engine public gate as blocked on external evidence. No production or
  validated-physics claim follows from these source checks.

Do not publish or tag this candidate as a qualified release until the open
release gates are resolved and the applicable evidence is reviewed.

## Local 0.3.0 preview installers

Manifest: `artifacts/windows/installer/SPIKE-0.3.0-preview-installers.json`.
Its contract marks `engineering-preview` and `production_qualified: false`.

| Installer | Bytes | SHA-256 | Signing |
| --- | ---: | --- | --- |
| `SPIKE_0.3.0_x64_en-US.msi` | 144,490,643 | `9a88d4bfd381b93b2e7b5cb489092756a2515599339cd0c66d249fd3a47c8af0` | NotSigned |
| `SPIKE_0.3.0_x64-setup.exe` | 102,628,061 | `9d851cf1af2cb0a701035298458baa9e0285db0f0d15b2d7a0a6e44d9159e488` | NotSigned |

The desktop/CLI product version is `0.3.0`. The separately versioned SPIKES
engine remains `0.3.0-beta.1`; its public-release gate is separate and blocked.

## Yawar B self-signed preview copies

The user requested self-signed preview signatures. A non-exportable RSA 3072-bit
code-signing key was created in `Cert:\CurrentUser\My` with public subject
`CN=Yawar B, O=wayri` and thumbprint
`7B6F3CD5DF329B9D03EF4DF7F84754D6DD6894C2`. Only its public certificate
was exported. SignTool successfully signed copies in
`artifacts/windows/signed-preview`; the original unsigned files and manifest
remain intact. The public certificate and a hash manifest are in that folder.

| Signed copy | Bytes | SHA-256 |
| --- | ---: | --- |
| `SPIKE_0.3.0_x64_en-US.msi` | 144,494,592 | `2045f10ad0988237e6adb2b21da39bef9fc57e5f31f87aef32310f288d9773a3` |
| `SPIKE_0.3.0_x64-setup.exe` | 102,629,872 | `f5ba328684db2c60dd9ac8fd8445e29a1ea13a6714f1f2a27cf48c6618725bca` |

`Get-AuthenticodeSignature` finds the expected signer on both files. Windows
reports `UnknownError` because the self-signed root is untrusted. SignTool
rejected the configured HTTPS timestamp URL before signing, so these copies
were signed without a timestamp. Their signatures cannot serve as a trusted
production signing record and will not remain valid beyond the certificate's
2027-09-28 expiry.
