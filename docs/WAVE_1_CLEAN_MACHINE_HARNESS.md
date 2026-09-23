# Wave 1 Clean Windows Evidence Harness

This repository-owned harness stages a named installer and the fixed Wave 1
fixture with SHA-256 identities, then collects reproducible mechanical evidence
on a target Windows machine. It is evidence preparation only: it cannot certify
pixels, usability, or the cleanliness of a machine by itself.

## Run boundary

Prepare inputs on the build machine:

```powershell
python scripts/prepare_wave1_clean_machine_harness.py `
  --installer-manifest artifacts/windows/installer/SPIKE-0.2.0-preview-installers.json `
  --artifact-dir artifacts/windows/installer `
  --installer SPIKE_0.2.0_x64_en-US.msi `
  --output build/wave1-clean-machine-stage
```

Transfer that complete directory to a clean Windows target. Do not place a
development checkout, Python, or Node on the target `PATH`. Run the harness
there first to install and launch the candidate. After the reviewer has
performed and saved the required UI changes, run it again with `-SkipInstall`
and the saved project to collect the final hash-bound record:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_wave1_clean_machine_harness.ps1 `
  -StagingRoot C:\Wave1Stage -Provider external-clean-vm `
  -EnvironmentAttestationPath C:\Evidence\environment-attestation.json `
  -AfterProject C:\Evidence\wave1-after.spike
```

`windows-sandbox`, `hyperv-vm`, `external-clean-vm`, and
`physical-clean-machine` identify the operator-provided target. The harness
does not create those targets. When Windows Sandbox or Hyper-V is unavailable
on the build host, stage the inputs and use an external clean VM or physical
machine. `not-isolated` is recorded but is categorically ineligible for Wave 1
human-review evidence.

Provider labels are not evidence of isolation. To be eligible for human review,
the harness also needs a structurally bound
`spike/wave1-environment-attestation/v1` JSON record with the exact provider,
run ID, and staged-input hash. The harness copies and hashes that record, but
marks it only `supplied_for_human_review`: it is a review input, never
cryptographic proof that a machine is clean or isolated. Without it, or with
`not-isolated`, the returned record remains `unattested` and ineligible.

The script verifies staged installer/fixture hashes, records OS/GPU/WebView2
and display information, runs the selected installer unless `-SkipInstall` is
used, records installer exit/logs, installed-product/association data, starts
the installed application when it can locate it, and saves a hash ledger plus
the before/after project manifest identities. Verify returned evidence before
attaching it:

```powershell
python scripts/verify_wave1_clean_machine_harness.py `
  C:\Wave1Stage\run-<run-id>\harness-run.json
```

## Human boundary

Attach exactly one returned `harness-run.json` as a hashed artifact in the
existing human evidence JSON. Its installer and before/after manifest digests
must equal the top-level human-evidence values; the acceptance validator rejects
legacy v1, missing/unattested, non-isolated, or mismatched records.

The v2 record also returns the exact `inputs.json`, the executing runner, the
environment attestation, pre-install SPIKE residue, and their SHA-256 ledger.
The verifier rejects duplicate ledger paths, invalid timezone-bearing
attestation timestamps, or any difference between the copied attestation and
the summarized attestation fields. These checks prevent evidence transfer and
tampering; they still do not prove isolation or replace reviewer judgment.

The current unsigned r18 installers have fresh v2-only staging directories at
`artifacts/wave1-clean-machine-r18-v2-msi` and
`artifacts/wave1-clean-machine-r18-v2-nsis`. Their `inputs.json` SHA-256 values
are `f90dfbc2502166e06ebaca0187cf902ff22364f83f549c208a772d5c46055310`
and `7f8d75f5fc7d652ed33a9dd9f09f12f759877f82cec3959b95eaf872539f3758`.
The older r18 staging directories bind the legacy runner and are diagnostic
history only. No staged directory has been executed on an attested target.

The reviewer must still explicitly pass all ten Wave 1 checks. In particular,
the harness does not decide whether the viewport is responsive; whether a
warning/console window is visible; navigator/editor claims are truthful;
fixed-camera screenshots are free of clipping/depth/transform defects; gizmo
and reparenting behavior are correct; exact topology and cancellation semantics
are valid; or repair/upgrade/uninstall user experience is acceptable.

Screenshots and logs are review inputs, never a pixel-pass oracle. The harness
does not claim Wave 1 completion, solver readiness, or physics qualification.
