# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet("windows-ucrt64", "linux-x86_64")][string]$Platform,
    [Parameter(Mandatory)][string]$PetscPrefix,
    [Parameter(Mandatory)][string]$MumpsPrefix,
    [Parameter(Mandatory)][string]$DependencyManifestPath,
    [string]$DependencyManifestSignaturePath,
    [Parameter(Mandatory)][string]$TrustCertificatePath,
    [Parameter(Mandatory)][string]$SigningCertificatePath,
    [SecureString]$SigningCertificatePassword,
    [Parameter(Mandatory)][string]$ReadinessProbePath,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $DependencyManifestSignaturePath) { $DependencyManifestSignaturePath = "$DependencyManifestPath.p7s" }
if (-not $OutputPath) { $OutputPath = Join-Path $repoRoot "runtime\external\petsc-mumps\readiness.json" }

function Get-Certificate([string]$Path, [SecureString]$Password, [bool]$RequirePrivateKey) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Certificate is missing: $Path" }
    $flags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable
    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path -LiteralPath $Path).Path, $Password, $flags)
    if ($RequirePrivateKey -and -not $certificate.HasPrivateKey) { throw "Signing certificate has no private key: $Path" }
    return $certificate
}

function Test-DetachedCmsSignature([string]$ContentPath, [string]$SignaturePath, $TrustedCertificate) {
    if (-not (Test-Path -LiteralPath $ContentPath) -or -not (Test-Path -LiteralPath $SignaturePath)) { throw "Signed manifest and detached signature are required." }
    $content = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ContentPath).Path)
    $signature = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $SignaturePath).Path)
    $cms = [System.Security.Cryptography.Pkcs.SignedCms]::new([System.Security.Cryptography.Pkcs.ContentInfo]::new($content), $true)
    $cms.Decode($signature); $cms.CheckSignature($true)
    if ($cms.SignerInfos.Count -ne 1 -or $cms.SignerInfos[0].Certificate.Thumbprint -ne $TrustedCertificate.Thumbprint) { throw "Manifest signer does not match the pinned release certificate." }
}

function Assert-RelativeArtifact([string]$Prefix, $Artifact) {
    if ($Artifact.root -notin @("petsc", "mumps") -or -not $Artifact.path -or -not $Artifact.sha256) { throw "Dependency artifact entries require root, path, and sha256." }
    $base = if ($Artifact.root -eq "petsc") { $PetscPrefix } else { $MumpsPrefix }
    $root = [System.IO.Path]::GetFullPath($base).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $base $Artifact.path))
    if (-not $candidate.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Dependency artifact escapes its declared prefix: $($Artifact.path)" }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Declared dependency artifact is missing: $candidate" }
    $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Artifact.sha256.ToLowerInvariant()) { throw "Dependency artifact hash mismatch: $($Artifact.path)" }
}

$trusted = Get-Certificate -Path $TrustCertificatePath -Password $null -RequirePrivateKey $false
$signer = Get-Certificate -Path $SigningCertificatePath -Password $SigningCertificatePassword -RequirePrivateKey $true
if ($signer.Thumbprint -ne $trusted.Thumbprint) { throw "Signing certificate must match the pinned release certificate." }
Test-DetachedCmsSignature -ContentPath $DependencyManifestPath -SignaturePath $DependencyManifestSignaturePath -TrustedCertificate $trusted
$dependency = Get-Content -LiteralPath $DependencyManifestPath -Raw | ConvertFrom-Json
if ($dependency.contract -ne "spike/petsc-mumps-dependency/v1" -or $dependency.platform -ne $Platform) { throw "Dependency manifest must be a signed platform-matched PETSc/MUMPS dependency manifest." }
if (-not $dependency.artifacts -or @($dependency.artifacts).Count -eq 0) { throw "Dependency manifest does not enumerate any PETSc/MUMPS artifacts." }
foreach ($artifact in $dependency.artifacts) { Assert-RelativeArtifact -Prefix $PetscPrefix -Artifact $artifact }

if (-not (Test-Path -LiteralPath $ReadinessProbePath -PathType Leaf)) { throw "PETSc/MUMPS readiness probe is missing: $ReadinessProbePath" }
$probeOutput = Join-Path ([System.IO.Path]::GetTempPath()) ("spike-petsc-mumps-" + [Guid]::NewGuid().ToString("N") + ".json")
try {
    & $ReadinessProbePath --spike-petsc-mumps-readiness --output $probeOutput
    if ($LASTEXITCODE -ne 0) { throw "PETSc/MUMPS readiness probe failed with exit code $LASTEXITCODE." }
    if (-not (Test-Path -LiteralPath $probeOutput)) { throw "PETSc/MUMPS readiness probe did not produce its required JSON record." }
    $probe = Get-Content -LiteralPath $probeOutput -Raw | ConvertFrom-Json
    if ($probe.contract -ne "spike/petsc-mumps-probe/v1" -or $probe.platform -ne $Platform -or $probe.status -ne "passed") { throw "PETSc/MUMPS readiness probe did not report a passing platform-matched contract." }
    if (-not $probe.registration.matsolvermumps_registered -or $probe.registration.factorization -ne "MATSOLVERMUMPS" -or -not $probe.registration.solve_verified) {
        throw "Probe must prove PETSc registered MATSOLVERMUMPS and completed a MUMPS-backed solve. Library presence alone is not readiness."
    }
    if (-not $probe.petsc.version -or -not $probe.petsc.scalar_type -or -not $probe.mumps.version -or -not $probe.mpi.implementation) { throw "Probe must report PETSc scalar type, MUMPS version, and MPI implementation." }

    $record = [ordered]@{
        contract = "spike/petsc-mumps-readiness/v1"; status = "passed"; platform = $Platform
        dependency_manifest_sha256 = (Get-FileHash -LiteralPath $DependencyManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        probe_sha256 = (Get-FileHash -LiteralPath $ReadinessProbePath -Algorithm SHA256).Hash.ToLowerInvariant()
        petsc = $probe.petsc; mumps = $probe.mumps; mpi = $probe.mpi; registration = $probe.registration
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    }
    $outputDirectory = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    [System.IO.File]::WriteAllText($OutputPath, ($record | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
    $content = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $OutputPath).Path)
    $cms = [System.Security.Cryptography.Pkcs.SignedCms]::new([System.Security.Cryptography.Pkcs.ContentInfo]::new($content), $true)
    $cmsSigner = [System.Security.Cryptography.Pkcs.CmsSigner]::new($signer)
    $cmsSigner.DigestAlgorithm = [System.Security.Cryptography.Oid]::new("2.16.840.1.101.3.4.2.1")
    $cms.ComputeSignature($cmsSigner)
    [System.IO.File]::WriteAllBytes("$OutputPath.p7s", $cms.Encode())
    Write-Host "Signed PETSc/MUMPS readiness record written to $OutputPath"
} finally {
    Remove-Item -LiteralPath $probeOutput -Force -ErrorAction SilentlyContinue
}
