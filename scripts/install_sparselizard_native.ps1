# SPDX-License-Identifier: Apache-2.0
[CmdletBinding(DefaultParameterSetName = "Install")]
param(
    [Parameter(ParameterSetName = "Install")][switch]$BuildOnly,
    [Parameter(ParameterSetName = "Rollback", Mandatory)][switch]$Rollback,
    [string]$MsysRoot = "C:\msys64",
    [string]$SourceCommit = "e536ff15905556400909b47c4ff3df405e288b44",
    [string]$DependencyManifestPath,
    [string]$DependencyManifestSignaturePath,
    [Parameter(Mandatory)][string]$TrustCertificatePath,
    [Parameter(ParameterSetName = "Install", Mandatory)][string]$BundleSigningCertificatePath,
    [Parameter(ParameterSetName = "Install")][SecureString]$BundleSigningCertificatePassword,
    [Parameter(ParameterSetName = "Install", Mandatory)][string]$PetscMumpsReadinessPath
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $DependencyManifestPath) { $DependencyManifestPath = Join-Path $repoRoot "dependencies.lock.json" }
if (-not $DependencyManifestSignaturePath) { $DependencyManifestSignaturePath = "$DependencyManifestPath.p7s" }
$runtimeRoot = Join-Path $repoRoot "runtime\external\sparselizard"
$releasesRoot = Join-Path $runtimeRoot "releases"
$activeRoot = Join-Path $runtimeRoot "native-windows"
$downloadRoot = Join-Path $repoRoot "runtime\downloads"
$sourceRoot = Join-Path $runtimeRoot "source"
$ucrtBin = Join-Path $MsysRoot "ucrt64\bin"
$cmake = Join-Path $ucrtBin "cmake.exe"
$pacman = Join-Path $MsysRoot "usr\bin\pacman.exe"
$objdump = Join-Path $ucrtBin "objdump.exe"
$runtimeExeName = "spike-sparselizard-runtime.exe"
$msMpiUri = "https://download.microsoft.com/download/7/2/7/72731ebb-b63c-4170-ade7-836966263a8f/msmpisetup.exe"
$msMpiSha256 = "47443829114D8D8670F77AF98939FE876D33ECEB35D0CE4E0E85EFEEC4D87213"

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Required command is unavailable: $Name" }
}

function Assert-FileHash([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
    if ($actual -ne $Expected.ToUpperInvariant()) { throw "SHA256 mismatch for $Path. Expected $Expected, received $actual." }
}

function Get-TrustedCertificate([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Trust certificate is missing: $Path" }
    return [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path -LiteralPath $Path).Path)
}

function Test-DetachedCmsSignature([string]$ContentPath, [string]$SignaturePath, $TrustedCertificate) {
    if (-not (Test-Path -LiteralPath $ContentPath) -or -not (Test-Path -LiteralPath $SignaturePath)) {
        throw "Signed manifest and detached signature are both required: $ContentPath / $SignaturePath"
    }
    $content = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ContentPath).Path)
    $signature = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $SignaturePath).Path)
    $cms = [System.Security.Cryptography.Pkcs.SignedCms]::new([System.Security.Cryptography.Pkcs.ContentInfo]::new($content), $true)
    $cms.Decode($signature)
    $cms.CheckSignature($true)
    if ($cms.SignerInfos.Count -ne 1 -or $cms.SignerInfos[0].Certificate.Thumbprint -ne $TrustedCertificate.Thumbprint) {
        throw "Manifest signer does not match the pinned release certificate."
    }
}

function Write-DetachedCmsSignature([string]$ContentPath, [string]$SignaturePath, [string]$CertificatePath, [SecureString]$Password, $TrustedCertificate) {
    $flags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable
    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path -LiteralPath $CertificatePath).Path, $Password, $flags)
    if (-not $certificate.HasPrivateKey) { throw "Bundle signing certificate has no private key: $CertificatePath" }
    if ($certificate.Thumbprint -ne $TrustedCertificate.Thumbprint) { throw "Bundle signing certificate must match the pinned release certificate." }
    $content = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ContentPath).Path)
    $cms = [System.Security.Cryptography.Pkcs.SignedCms]::new([System.Security.Cryptography.Pkcs.ContentInfo]::new($content), $true)
    $signer = [System.Security.Cryptography.Pkcs.CmsSigner]::new($certificate)
    $signer.DigestAlgorithm = [System.Security.Cryptography.Oid]::new("2.16.840.1.101.3.4.2.1")
    $cms.ComputeSignature($signer)
    [System.IO.File]::WriteAllBytes($SignaturePath, $cms.Encode())
}

function Read-VerifiedJson([string]$Path, [string]$SignaturePath, $TrustedCertificate, [string]$Contract) {
    Test-DetachedCmsSignature -ContentPath $Path -SignaturePath $SignaturePath -TrustedCertificate $TrustedCertificate
    $document = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($document.contract -ne $Contract) { throw "Unexpected manifest contract in ${Path}: $($document.contract)" }
    return $document
}

function Assert-ReadyPetscMumps([string]$Path, $TrustedCertificate) {
    $document = Read-VerifiedJson -Path $Path -SignaturePath "$Path.p7s" -TrustedCertificate $TrustedCertificate -Contract "spike/petsc-mumps-readiness/v1"
    if ($document.platform -ne "windows-ucrt64" -or $document.status -ne "passed" -or -not $document.registration.matsolvermumps_registered) {
        throw "PETSc/MUMPS is not registered and ready for native Windows. Supply a signed, passing readiness record produced by scripts/register_petsc_mumps_readiness.ps1."
    }
    return $document
}

function Activate-Bundle([string]$Candidate, $TrustedCertificate) {
    Read-VerifiedJson -Path (Join-Path $Candidate "manifest.json") -SignaturePath (Join-Path $Candidate "manifest.json.p7s") -TrustedCertificate $TrustedCertificate -Contract "spike/sparselizard-native-runtime/v2" | Out-Null
    New-Item -ItemType Directory -Force -Path $releasesRoot | Out-Null
    $backup = $null
    if (Test-Path -LiteralPath $activeRoot) {
        $backup = Join-Path $releasesRoot ("replaced-" + [DateTimeOffset]::UtcNow.ToString("yyyyMMddHHmmssfff"))
        Move-Item -LiteralPath $activeRoot -Destination $backup
    }
    try {
        Move-Item -LiteralPath $Candidate -Destination $activeRoot
    } catch {
        if ($backup -and (Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $activeRoot)) {
            Move-Item -LiteralPath $backup -Destination $activeRoot
        }
        throw
    }
}

$trustedCertificate = Get-TrustedCertificate $TrustCertificatePath
Read-VerifiedJson -Path $DependencyManifestPath -SignaturePath $DependencyManifestSignaturePath -TrustedCertificate $trustedCertificate -Contract "spike/dependencies/v1" | Out-Null

if ($Rollback) {
    $candidate = Get-ChildItem -LiteralPath $releasesRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "manifest.json.p7s") } |
        Select-Object -First 1
    if (-not $candidate) { throw "No signed sparseLizard release is available for rollback at $releasesRoot." }
    Activate-Bundle -Candidate $candidate.FullName -TrustedCertificate $trustedCertificate
    Write-Host "Rolled back native sparseLizard runtime to $activeRoot"
    exit 0
}

$petscReadiness = Assert-ReadyPetscMumps -Path $PetscMumpsReadinessPath -TrustedCertificate $trustedCertificate
New-Item -ItemType Directory -Force -Path $runtimeRoot, $downloadRoot | Out-Null

if (-not (Test-Path -LiteralPath $pacman)) {
    if ($BuildOnly) { throw "MSYS2 is not installed at $MsysRoot. BuildOnly never bootstraps build dependencies." }
    Assert-Command "winget.exe"
    & winget.exe install --id MSYS2.MSYS2 --exact --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw "MSYS2 installation failed with exit code $LASTEXITCODE." }
}

if (-not $BuildOnly) {
    # PETSc, MUMPS, SLEPc, and MPI are deliberately absent: they must come from the signed readiness record.
    $packages = @("mingw-w64-ucrt-x86_64-gcc", "mingw-w64-ucrt-x86_64-gcc-fortran", "mingw-w64-ucrt-x86_64-cmake", "mingw-w64-ucrt-x86_64-ninja", "mingw-w64-ucrt-x86_64-openblas", "mingw-w64-ucrt-x86_64-metis", "mingw-w64-ucrt-x86_64-gmsh")
    & $pacman -Syu --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "MSYS2 update failed with exit code $LASTEXITCODE." }
    & $pacman -S --needed --noconfirm @packages
    if ($LASTEXITCODE -ne 0) { throw "Non-PETSc native build dependency installation failed with exit code $LASTEXITCODE." }
}

foreach ($required in @($cmake, $objdump)) { if (-not (Test-Path -LiteralPath $required)) { throw "Required native tool is missing: $required" } }
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot ".git"))) {
    if ($BuildOnly) { throw "The sparseLizard source tree is missing at $sourceRoot." }
    Assert-Command "git.exe"
    & git.exe clone https://github.com/halbux/sparselizard.git $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw "sparseLizard clone failed with exit code $LASTEXITCODE." }
}
if ($BuildOnly) {
    $currentCommit = (& git.exe -c "safe.directory=$($sourceRoot.Replace('\', '/'))" -C $sourceRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentCommit -ne $SourceCommit) { throw "BuildOnly requires sparseLizard commit $SourceCommit; found $currentCommit." }
} else {
    & git.exe -c "safe.directory=$($sourceRoot.Replace('\', '/'))" -C $sourceRoot fetch --depth 1 origin $SourceCommit
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch pinned sparseLizard commit $SourceCommit." }
    & git.exe -c "safe.directory=$($sourceRoot.Replace('\', '/'))" -C $sourceRoot checkout --detach $SourceCommit
    if ($LASTEXITCODE -ne 0) { throw "Could not check out pinned sparseLizard commit $SourceCommit." }
}

if (-not (Test-Path -LiteralPath "C:\Windows\System32\msmpi.dll")) {
    if ($BuildOnly) { throw "Microsoft MPI runtime is missing. BuildOnly never installs it." }
    $installer = Join-Path $downloadRoot "msmpisetup-10.1.3.exe"
    Invoke-WebRequest -Uri $msMpiUri -OutFile $installer
    Assert-FileHash $installer $msMpiSha256
    $process = Start-Process -FilePath $installer -ArgumentList @("-unattend", "-full", "-force") -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Microsoft MPI installation failed with exit code $($process.ExitCode)." }
}

$stageRoot = Join-Path $runtimeRoot ("staging\" + [Guid]::NewGuid().ToString("N"))
$bundleRoot = Join-Path $stageRoot "native-windows"
$buildRoot = Join-Path $stageRoot "build"
$binRoot = Join-Path $bundleRoot "bin"
New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
$env:Path = "$ucrtBin;$env:Path"
$env:PKG_CONFIG_PATH = Join-Path $MsysRoot "ucrt64\lib\pkgconfig"
& $cmake -S (Join-Path $repoRoot "integrations\sparselizard-native") -B $buildRoot -G Ninja "-DSPARSELIZARD_SOURCE_DIR=$($sourceRoot.Replace('\', '/'))" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw "Native sparseLizard CMake configuration failed. The signed PETSc/MUMPS bundle must expose the required pkg-config metadata to UCRT64." }
& $cmake --build $buildRoot --parallel ([Math]::Max(1, [Math]::Min(8, [Environment]::ProcessorCount)))
if ($LASTEXITCODE -ne 0) { throw "Native sparseLizard build failed with exit code $LASTEXITCODE." }

$builtExe = Join-Path $buildRoot $runtimeExeName
$selfTest = Join-Path $bundleRoot "self-test.json"
Copy-Item -LiteralPath $builtExe -Destination (Join-Path $binRoot $runtimeExeName) -Force
$systemDlls = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@("KERNEL32.dll", "msmpi.dll") | ForEach-Object { [void]$systemDlls.Add($_) }
$pending = [Collections.Generic.Queue[string]]::new(); $pending.Enqueue((Join-Path $binRoot $runtimeExeName))
$visited = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
while ($pending.Count -gt 0) {
    $binary = $pending.Dequeue(); if (-not $visited.Add($binary)) { continue }
    $dependencies = & $objdump -p $binary | Select-String "DLL Name:" | ForEach-Object { ($_.Line -split "DLL Name:", 2)[1].Trim() }
    foreach ($dependency in $dependencies) {
        if ($systemDlls.Contains($dependency) -or $dependency.StartsWith("api-ms-win-", [StringComparison]::OrdinalIgnoreCase)) { continue }
        $sourceDll = Join-Path $ucrtBin $dependency; $targetDll = Join-Path $binRoot $dependency
        if ((Test-Path -LiteralPath $sourceDll) -and -not (Test-Path -LiteralPath $targetDll)) { Copy-Item -LiteralPath $sourceDll -Destination $targetDll }
        if (Test-Path -LiteralPath $targetDll) { $pending.Enqueue($targetDll) }
    }
}

$mesh = Join-Path $sourceRoot "examples\circuit-coupling-rlc-harmonic\quad.msh"
$savedPath = $env:Path
try {
    $env:Path = "$binRoot;$env:SystemRoot\System32;$env:SystemRoot"
    Push-Location $repoRoot
    try {
        & (Join-Path $binRoot $runtimeExeName) self-test --mesh ($mesh.Substring($repoRoot.Length).TrimStart('\').Replace('\', '/')) --output ($selfTest.Substring($repoRoot.Length).TrimStart('\').Replace('\', '/'))
        if ($LASTEXITCODE -ne 0) { throw "Native sparseLizard self-test failed with exit code $LASTEXITCODE." }
    } finally { Pop-Location }
} finally { $env:Path = $savedPath }
$result = Get-Content -LiteralPath $selfTest -Raw | ConvertFrom-Json
if ($result.contract -ne "spike/sparselizard-runtime-self-test/v1" -or $result.status -ne "passed") { throw "Native sparseLizard self-test did not produce a passing result contract." }

$manifest = [ordered]@{
    contract = "spike/sparselizard-native-runtime/v2"; platform = "windows-ucrt64"
    source = [ordered]@{ repository = "https://github.com/halbux/sparselizard"; commit = $SourceCommit }
    executable = "bin/$runtimeExeName"; executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $binRoot $runtimeExeName)).Hash.ToLowerInvariant()
    dependency_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $DependencyManifestPath).Hash.ToLowerInvariant()
    petsc_mumps_readiness_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PetscMumpsReadinessPath).Hash.ToLowerInvariant()
    self_test = [ordered]@{ path = "self-test.json"; status = $result.status; validation_scope = $result.validation_scope; maximum_relative_error = $result.maximum_relative_error }
    backend = [ordered]@{ linear_solver = $result.linear_solver; mumps_registered = $true; registration_evidence = "signed PETSc/MUMPS readiness record"; circuit_coupling_validated = $false }
}
$manifestPath = Join-Path $bundleRoot "manifest.json"
[System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
Write-DetachedCmsSignature -ContentPath $manifestPath -SignaturePath "$manifestPath.p7s" -CertificatePath $BundleSigningCertificatePath -Password $BundleSigningCertificatePassword -TrustedCertificate $trustedCertificate
Activate-Bundle -Candidate $bundleRoot -TrustedCertificate $trustedCertificate
Write-Host "Signed native sparseLizard runtime activated at $activeRoot"
