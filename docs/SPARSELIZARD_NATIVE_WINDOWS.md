# Native sparseLizard Runtime on Windows

## Current State

SPIKE builds sparseLizard as a native Windows process. The supported Windows
path does not use WSL. The reproducible build is owned by
`scripts/install_sparselizard_native.ps1` and the wrapper target is in
`integrations/sparselizard-native/`.

The checked runtime is pinned to upstream sparseLizard commit
`e536ff15905556400909b47c4ff3df405e288b44`. It is built with the MSYS2
UCRT64 C++ toolchain. PETSc, MUMPS, SLEPc, and MPI are administrator-provided,
ABI-matched native dependencies: SPIKE does not download or install them.
Their signed artifact manifest and functional readiness record are required
before a native build. Third-party license obligations apply to distributed
runtime bundles.

## Signed Deployment Inputs

Deployment manifests use detached CMS signatures over their exact UTF-8 bytes.
The release certificate is supplied out of band and pinned by thumbprint. The
scripts reject missing signatures, invalid CMS signatures, multiple signers,
and signers that do not match that certificate. Do not keep the certificate or
private key in this repository or runtime bundle.

The required contracts are:

| Input | Contract | Purpose |
| --- | --- | --- |
| `dependencies.lock.json` plus `.p7s` | `spike/dependencies/v1` | Release dependency policy |
| Administrator PETSc/MUMPS manifest plus `.p7s` | `spike/petsc-mumps-dependency/v1` | Exact platform artifact hashes |
| Readiness record plus `.p7s` | `spike/petsc-mumps-readiness/v1` | PETSc registration and functional-solve evidence |
| Runtime manifest plus `.p7s` | `spike/sparselizard-native-runtime/v2` | Activated executable and self-test |

The PETSc/MUMPS dependency manifest must enumerate every artifact with a
`petsc` or `mumps` root, a relative path, and SHA-256. The registration script
rejects paths that escape either prefix and validates every declared hash.

## PETSc/MUMPS Registration And Readiness

Provision a native Windows UCRT64 or native Linux PETSc/MUMPS/SLEPc/MPI build
outside SPIKE. The Windows build must expose the required UCRT64 `pkg-config`
metadata to the sparseLizard CMake build. Library presence, a package name, or
a `petsc4py` import is not readiness.

The supplied probe must support:

```text
--spike-petsc-mumps-readiness --output <json-path>
```

It must write `spike/petsc-mumps-probe/v1` JSON with `status: passed`, PETSc
scalar type, PETSc/MUMPS/MPI versions, and all of:

- `registration.matsolvermumps_registered: true`
- `registration.factorization: "MATSOLVERMUMPS"`
- `registration.solve_verified: true`

The expected probe creates a PETSc MUMPS factor and completes a bounded solve;
finding standalone MUMPS files does not qualify. Register the external bundle
with PowerShell 7 on native Windows or Linux:

```powershell
pwsh -File scripts/register_petsc_mumps_readiness.ps1 `
  -Platform windows-ucrt64 `
  -PetscPrefix D:\approved\petsc `
  -MumpsPrefix D:\approved\mumps `
  -DependencyManifestPath D:\approved\petsc-mumps.manifest.json `
  -TrustCertificatePath D:\release-keys\spike-release.cer `
  -SigningCertificatePath D:\release-keys\spike-release.pfx `
  -ReadinessProbePath D:\approved\bin\spike-petsc-mumps-probe.exe
```

Use `-Platform linux-x86_64` and Linux prefixes/probe for a native Linux
bundle. This script never invokes a package manager, downloader, or installer.

## Rebuild and Verify

Run the complete explicit installer/build operation from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_sparselizard_native.ps1 `
  -TrustCertificatePath D:\release-keys\spike-release.cer `
  -BundleSigningCertificatePath D:\release-keys\spike-release.pfx `
  -PetscMumpsReadinessPath runtime\external\petsc-mumps\readiness.json
```

After prerequisites and sources already exist, rebuild without downloading:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_sparselizard_native.ps1 `
  -BuildOnly `
  -TrustCertificatePath D:\release-keys\spike-release.cer `
  -BundleSigningCertificatePath D:\release-keys\spike-release.pfx `
  -PetscMumpsReadinessPath runtime\external\petsc-mumps\readiness.json
```

Inspect the integrity-bound runtime state through the normal SPIKE CLI:

```powershell
spike sparselizard-runtime-status
spike external-engines
spike solver-manager
```

The packaged runtime lives under
`runtime/external/sparselizard/native-windows/`. That directory is ignored by
Git because it contains downloaded sources and compiled third-party binaries.
Its signed `manifest.json` binds the executable, the signed release dependency
policy, and the signed PETSc/MUMPS readiness record. Its `self-test.json`
records the bounded test result. The installer stages a complete build, tests
it, signs its v2 manifest, and only then activates it. It retains the previous
signed runtime under `runtime/external/sparselizard/releases/`; use
`-Rollback -TrustCertificatePath <release.cer>` to activate the newest verified
rollback candidate. A failed activation restores the old active directory.

## Verified Scope

A current native runtime may pass one deterministic unit-square DC conduction
fixture. The fixture uses conductivity 0.005 S/m, applies 1 V, and returns the
analytical 200 ohm resistance with zero reported relative error. A passing
runtime self-test proves only that narrow FEM execution. PETSc/MUMPS readiness
is established separately by the signed external probe, not inferred from this
fixture or claimed by this repository.

It does not validate a PCB translation, copper-zone current spreading,
multilayer via physics, RLC extraction, electrothermal coupling, SI, thermal
airflow, or EMI. Those capabilities remain disabled until their adapters,
fixtures, convergence records, and result contracts pass independently.

## Readiness Gates

The solver manager treats these as separate gates:

1. **Runtime**: the executable, manifest digest, dependencies, and bounded
   self-test pass.
2. **Adapter**: a SPIKE case translator and result importer implement the
   declared workflow contract.
3. **Workflow**: the adapter supplies every capability required by the selected
   PI, SI, thermal, or EMI workload.
4. **Validation**: analytical, independent-solver, and measured evidence cover
   the declared geometry and operating range.

A green runtime gate does not make the workflow runnable. SPIKE must never
silently substitute a different formulation or promote an upstream candidate
capability to an implemented capability.

## Backend Limitation

The v2 deployment manifest can record a registered MUMPS backend only after
the signed readiness probe proves it. That registration is a deployment gate,
not circuit-coupling validation. Circuit-coupled sparseLizard RLC work remains
gated until its independent fixtures and validation evidence pass.

## Distribution Boundary

sparseLizard is GPL-2.0-or-later. SPIKE keeps it in a separate process with a
versioned file contract for crash isolation and replaceability. Process
separation does not remove license obligations. A public installer requires a
complete license notice, corresponding-source process, SBOM, signed manifest,
hash verification, and rollback policy before this runtime may be bundled.
