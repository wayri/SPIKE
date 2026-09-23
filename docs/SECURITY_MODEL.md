# SPIKE Security Model

## Runtime position

Node.js and npm are build-time tools only. A released desktop installer contains compiled Tauri assets and the local analysis worker/runtime. It does not execute npm, download JavaScript, contact a package registry, or load third-party web pages.

## Desktop shell

- Use Tauri IPC for privileged operations.
- Keep the webview on bundled assets.
- Maintain a restrictive Content Security Policy.
- Do not enable arbitrary filesystem, shell, or process permissions in the frontend.
- Put worker launch and file access behind narrowly scoped Rust commands.
- Validate all paths before passing them to the worker.
- Do not build shell command strings from board paths.
- Treat imported design files as untrusted input.
- Keep WebGL shader creation inside the bundled renderer; imported projects and
  models cannot supply scripts, remote URLs, or custom shader source.

## Local worker

- Prefer a private stdio JSON-line channel or OS-local authenticated channel.
- Never bind the worker to `0.0.0.0` by default.
- Validate request size, contract version, enum values, paths, and numeric ranges.
- Return structured errors without stack traces in the user-facing result.
- Apply cancellation and resource limits to mesh and frequency jobs.
- Keep temporary context and result files in an application-owned directory.
- Bound model-library searches and accept extra roots only after a native folder
  picker returns an explicit user selection.
- Validate model suffix, file size, triangle count, texture dimensions, and
  conversion time before caching an imported model.

## Supply chain

- Commit `app/package-lock.json`.
- Use `npm ci` in reproducible builds.
- Run `npm audit --audit-level=high` and review every exception.
- Pin Rust dependencies through `Cargo.lock` for release builds.
- Generate SBOMs for frontend, Rust, Python, and native solver dependencies.
- Production-candidate Windows SBOM and provenance evidence use the strict
  `spike/windows-release-sbom/v1` and `spike/windows-release-provenance/v1`
  schemas. `check_windows_release_inputs.py`,
  `build_windows_release_provenance.py`, and
  `verify_windows_release_provenance.py` are offline, fail-closed controls;
  `windows_cms.ps1` signs/verifies the SHA-256 detached CMS dependency-lock
  sidecar using an approved release certificate.
- A future production-candidate build creates that CMS sidecar before
  packaging, stages only exact public evidence beside installers through
  `stage_windows_release_evidence.py`, and uses
  `tauri.production.conf.json` to embed the CMS sidecar, review inputs, pinned
  Python locks, signing policy, and draft EULA. Staging is path/digest-bound,
  preserves installer bytes, and never stages signing keys. Post-signing
  SBOM/provenance build and verification bind the staged inputs and an explicit
  packaged-worker root; these are integrity controls, not approval or
  qualification claims.
- Do not bypass incomplete release inputs: the 36-wheel Windows CPython 3.12
  runtime is exact and hash-pinned in
  `requirements-runtime-windows-x64.txt`, with an offline `--require-hashes`
  dry run passing. `config/windows-component-inventory.json` is a present,
  current `spike/windows-component-inventory/v1` record of 474 Windows x64
  lock-derived components (303 `bundled`, 171 `build-only`; 276 Rust, 143 npm,
  55 Python). Its exactly matching
  `licenses/windows-component-approvals.json` has 474 `pending_review`
  decisions, so it is not an approved component inventory. The notice bundle
  remains incomplete. A schema-backed non-decisional reviewer packet now
  deterministically queues all 474 identities (303 bundled / 171 build-only),
  with 39 non-SPDX-shaped declarations and 2 unresolved `LicenseRef` values;
  every entry still requires notice text and legal review. The packet grants
  no approval or redistribution right. The required CMS sidecar is absent; legal
  redistribution approval and notice coverage remain pending. Consequently no
  signed candidate or clean-VM evidence exists; Wave 1 remains incomplete,
  Wave 2 is unopened, and no physics promotion is implied.
- Review licenses before adding dependencies.
- Review solver licenses separately for source use, redistribution, linking,
  hosted execution, and commercial use; "open source" alone is insufficient.
- Build release artifacts in a clean CI environment.
- Sign installers and publish checksums.
- A Windows signed candidate must enumerate exactly one MSI and one NSIS file
  after signing, with final SHA-256 values, expected signer thumbprint, and
  RFC 3161 timestamp-authority identity. Authenticode `Valid` alone is not an
  acceptance or release-qualification claim.
- Keep the Windows Authenticode private key in an approved certificate
  store/HSM or isolated signing service. Do not place PFX files, passwords,
  token PINs, or equivalent private-key material in source control, manifests,
  CI artifacts, environment dumps, or logs.
- Human clean-machine evidence for a signed candidate binds the installer file
  and SHA-256, installer-manifest SHA-256, signer thumbprint, and timestamp
  authority. This prevents evidence transfer to a later rebuild or another
  installer type with the same version.
- Clean-machine harness v2 also binds the returned staged inputs, executing
  runner, pre-install residue, and copied environment attestation. A provider
  label or unsigned attestation is never treated as proof of isolation; all ten
  interaction and pixel checks remain human-reviewed.
- Windows notice candidate collection joins by full PURL plus component
  identity, uses deterministic root-relative locators, bounds candidate text to
  4 MiB, rejects traversal/symlinks/stale locks, and isolates npm and wheel
  subcomponents. Candidate discovery never grants redistribution approval or
  notice completeness.

## Updates and data

- Updates must be signed and rollback-capable.
- Local mode must not upload design data.
- Cloud execution must be explicit, encrypted, retention-controlled, and auditable.
- Logs redact credentials, tokens, and proprietary file contents.
- The integrated dependency manager is inventory-first and offline by default:
  it verifies bundled runtimes and signed manifests but does not mutate global
  Python/Node environments or execute package-manager scripts.
- Optional solver bundles are disabled when absent and are never fetched from
  an untrusted URL by the application.
- Telemetry is opt-in and limited to product health signals.

## Project package trust

- The Python package reader canonicalizes the signed manifest payload and
  validates archive structure, member sizes, SHA-256 digests, and the signature
  envelope contract. Its signature policy is optional; it does not own desktop
  trust decisions.
- Targeted Arrow geometry reads enforce the 256 MiB byte budget against both
  the manifest record and ZIP member before decompression or retention, and
  reject a declared/actual size mismatch. Canonical Arrow bytes are exact-match
  checked without `read_all` or `to_pylist`; the caller caps IPC at 256 MiB and
  rows at 10,000,000, with declared over-limit rows rejected in preflight before
  decode. Targeted source, model, STEP, and selector readers likewise compare
  actual ZIP and manifest sizes before retaining bytes.
- The Tauri host verifies signed `.spike` manifests with `ed25519-dalek` against
  public keys pinned into the desktop build. Signed packages fail closed before
  workspace state is applied when the key is unavailable, untrusted, malformed,
  or the payload/signature has changed. The host binds an approved canonical
  project path to the opened manifest identity; signed identity is derived only
  from the pinned-key-verified signed payload, and targeted model/selector reads
  require that exact binding.
- Build-time package keys are supplied through
  `SPIKE_PACKAGE_TRUSTED_KEYS_JSON`, or the single-key
  `SPIKE_PACKAGE_KEY_ID` and `SPIKE_PACKAGE_PUBLIC_KEY_B64URL` pair.
- Package-signing keys and entitlement issuer keys are separate trust roots.
  Private signing keys must remain in an isolated release-signing service.
- Unsigned projects remain explicitly unsigned and must never be described as
  verified. A future organization policy may require signatures for all opens.
- Renderer manifest verification caps decoded input at 16 MiB. This is a
  resource bound, not an authentication claim for unsigned packages.

## Solver plugins

- Register only manifests using `spike/solver-plugin/v1`.
- Require process entry points to resolve inside their signed plugin directory.
- Launch fixed argument arrays with `shell=false` and a restricted environment.
- Give every job a private temporary directory, wall-clock timeout, result-size
  limit, and future OS-level CPU and memory limits.
- Treat plugin output as untrusted and validate its result contract before
  displaying or saving it.
- Do not pass host credentials, package-manager paths, or unrestricted project
  filesystem access to plugins.

## General extensions

- Discover only strict `spike/extension/v1` manifests.
- Keep unbundled extensions disabled until their exact ID is explicitly trusted.
- Run extension entrypoints as child processes without a shell.
- Resolve entrypoints inside the extension package and reject traversal.
- Pass only context fields allowed by declared permissions.
- Bound execution time and result size and validate
  `spike/extension-result/v1` before accepting output.
- Never inject third-party JavaScript into the Tauri webview; use structured
  results and schema-driven views.
- Treat process separation as an interim boundary. A public extension
  marketplace additionally requires signatures, publisher identity, revocation,
  and platform-native sandboxing.
- The ngspice adapter accepts explicit netlists only and rejects control blocks,
  include/load directives, shell commands, and user initialization files.
- Third-party SPICE models require a separate trust policy because model and
  code-model directives can execute or load content outside a pure circuit
  description.

## Security acceptance tests

- Launch without Node or npm installed.
- Launch without network access.
- Reject a path outside the selected project or approved temporary directory.
- Reject malformed worker requests.
- Verify the worker is not reachable on a public network interface.
- Verify the packaged app contains no development server URL.
- Verify a signed update rejects a tampered artifact.
- Verify signed `.spike` packages open only with a pinned package key and reject
  unknown keys, payload changes, and signature changes.
- Reject an unsigned or modified solver bundle.
- Reject a solver entry point that resolves outside its plugin directory.
- Terminate a solver that exceeds its time or output budget.
- Reject untrusted ngspice control, include, library, and load directives.
