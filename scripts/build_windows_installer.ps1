[CmdletBinding()]
param(
    [ValidateSet("Preview", "Production")]
    [string]$Channel = "Preview",
    [switch]$SkipTests,
    [switch]$SkipWorker,
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$mutexDigest = [System.Security.Cryptography.SHA256]::Create()
$mutexKey = [BitConverter]::ToString($mutexDigest.ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant()))).Replace('-', '')
$mutexDigest.Dispose()
$buildMutex = New-Object System.Threading.Mutex($false, "Local\SPIKEInstaller-$mutexKey")
$ownsBuildMutex = $false
try {
    try { $ownsBuildMutex = $buildMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $ownsBuildMutex = $true }
    if (-not $ownsBuildMutex) { throw "Another SPIKE installer build owns this checkout. Wait for it to finish; do not run overlapping builds." }
. (Join-Path $PSScriptRoot "windows_authenticode.ps1")
. (Join-Path $PSScriptRoot "windows_cms.ps1")
$app = Join-Path $root "app"
$config = Join-Path $app "src-tauri\tauri.conf.json"
$package = Join-Path $app "package.json"
$isProduction = $Channel -eq "Production"
if ($BuildOnly -and $isProduction) { throw "BuildOnly is for preview native-UI verification, not production release packaging." }
$artifactRelative = if ($isProduction) { "artifacts\windows\production-candidate" } else { "artifacts\windows\installer" }
$artifactRoot = [System.IO.Path]::GetFullPath((Join-Path $root $artifactRelative))
$version = (Get-Content -LiteralPath $config -Raw | ConvertFrom-Json).version
$applicationVersion = [string]((Get-Content -LiteralPath $package -Raw | ConvertFrom-Json).version)
if ([string]::IsNullOrWhiteSpace($applicationVersion)) {
    throw "Application package version is missing or empty: $package"
}
$projectPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $projectPython) { $projectPython } else { "python" }

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory)
    Push-Location $WorkingDirectory
    try {
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Executable failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

if ($isProduction) {
    $required = @(
        "SPIKE_COMMERCIAL_EULA_APPROVED",
        "SPIKE_LICENSE_PUBLIC_KEY_B64URL",
        "SPIKE_LICENSE_KEY_ID",
        "SPIKE_WINDOWS_SIGNING_THUMBPRINT",
        "SPIKE_WINDOWS_SIGNING_STORE_SCOPE",
        "SPIKE_WINDOWS_TIMESTAMP_URL",
        "SPIKE_WINDOWS_BUILD_WHEELHOUSE",
        "SPIKE_WINDOWS_RUNTIME_WHEELHOUSE"
    )
    foreach ($name in $required) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ([string]::IsNullOrWhiteSpace($value)) {
            throw "Production packaging is blocked: $name is not configured."
        }
    }
    if ($env:SPIKE_COMMERCIAL_EULA_APPROVED -ne "1") {
        throw "Production packaging is blocked until the commercial EULA is legally approved."
    }
    if (Select-String -LiteralPath (Join-Path $root "licenses\SPIKE-COMMERCIAL-EULA-DRAFT.md") -SimpleMatch "[LEGAL ENTITY NAME]" -Quiet) {
        throw "Production packaging is blocked: the commercial EULA still contains legal placeholders."
    }
    $signingPolicyPath = Join-Path $root "config\windows-signing-policy.json"
    $signingPolicy = Get-Content -LiteralPath $signingPolicyPath -Raw | ConvertFrom-Json
    if ($signingPolicy.schema -ne "spike/windows-signing-policy/v1" -or
        $signingPolicy.digest_algorithm -ne "sha256" -or
        $signingPolicy.timestamp_protocol -ne "rfc3161" -or
        @($signingPolicy.allowed_timestamp_hosts).Count -eq 0) {
        throw "Production packaging is blocked: the Windows signing policy is invalid."
    }
    $storeScope = [string]$env:SPIKE_WINDOWS_SIGNING_STORE_SCOPE
    if ($storeScope -notin @($signingPolicy.allowed_certificate_store_scopes)) {
        throw "Production packaging is blocked: the configured certificate store scope is not approved."
    }
    $signingThumbprint = Normalize-SpikeSigningThumbprint $env:SPIKE_WINDOWS_SIGNING_THUMBPRINT
    $timestampUri = Assert-SpikeTimestampUri $env:SPIKE_WINDOWS_TIMESTAMP_URL @($signingPolicy.allowed_timestamp_hosts)
    $signToolPath = Resolve-SpikeSignTool $env:SPIKE_SIGNTOOL_PATH
    $signingCertificate = Get-SpikeSigningCertificate $signingThumbprint $storeScope
    $licenseKeyId = [string]$env:SPIKE_LICENSE_KEY_ID
    $buildWheelhouse = [System.IO.Path]::GetFullPath([string]$env:SPIKE_WINDOWS_BUILD_WHEELHOUSE)
    $runtimeWheelhouse = [System.IO.Path]::GetFullPath([string]$env:SPIKE_WINDOWS_RUNTIME_WHEELHOUSE)
    if (-not (Test-Path -LiteralPath $buildWheelhouse -PathType Container) -or
        -not (Test-Path -LiteralPath $runtimeWheelhouse -PathType Container)) {
        throw "Production packaging is blocked: the verified build/runtime wheelhouses are missing."
    }
    Invoke-Checked $python @(
        "scripts/check_windows_release_inputs.py",
        "--build-wheel-dir", $buildWheelhouse,
        "--runtime-wheel-dir", $runtimeWheelhouse
    ) $root
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
    $dependencyLockPath = Join-Path $root "dependencies.lock.json"
    $dependencySignaturePath = Join-Path $artifactRoot "dependencies.lock.json.p7s"
    $cmsMetadata = New-SpikeDetachedCmsSignature `
        $dependencyLockPath $dependencySignaturePath $signingCertificate
    if ($cmsMetadata.status -ne "Valid" -or
        $cmsMetadata.digest_algorithm -ne "sha256" -or
        $cmsMetadata.signer_thumbprint -ne $signingThumbprint) {
        throw "Production packaging is blocked: dependency CMS verification did not match the release signer."
    }
} else {
    $previewKeyPath = Join-Path $root "config\license-preview-public.json"
    if (-not (Test-Path -LiteralPath $previewKeyPath)) {
        throw "Preview packaging is blocked: the public preview issuer configuration is missing."
    }
    $previewKey = Get-Content -LiteralPath $previewKeyPath -Raw | ConvertFrom-Json
    if ($previewKey.schema -ne "spike/license-public-key/v1" -or
        [string]::IsNullOrWhiteSpace($previewKey.key_id) -or
        [string]::IsNullOrWhiteSpace($previewKey.public_key_base64url)) {
        throw "Preview packaging is blocked: the public preview issuer configuration is invalid."
    }
    $env:SPIKE_LICENSE_KEY_ID = [string]$previewKey.key_id
    $env:SPIKE_LICENSE_PUBLIC_KEY_B64URL = [string]$previewKey.public_key_base64url
    $licenseKeyId = [string]$previewKey.key_id
}

if (-not $SkipTests) {
    Invoke-Checked $python @("scripts/check_architecture.py") $root
    Invoke-Checked $python @("-m", "unittest", "discover", "-s", "tests/python", "-p", "test_errors.py", "-v") $root
    Invoke-Checked $python @("-m", "unittest", "discover", "-s", "tests/python", "-p", "test_schema_catalog.py", "-v") $root
    Invoke-Checked "npm.cmd" @("run", "build") $app
    Invoke-Checked "cargo" @("test", "--lib") (Join-Path $app "src-tauri")
}

if (-not $SkipWorker) {
    Invoke-Checked $python @("scripts/build_packaged_worker.py") $root
}
if ($isProduction) {
    Invoke-Checked $python @(
        "scripts/stage_windows_release_evidence.py",
        "--artifact-root", $artifactRoot,
        "--dependency-signature", $dependencySignaturePath
    ) $root
    Invoke-Checked "npm.cmd" @(
        "run", "tauri", "build", "--", "--bundles", "nsis,msi",
        "--config", "src-tauri/tauri.production.conf.json"
    ) $app
} else {
    # Rust embeds assets over the duration of compilation. A concurrent Vite
    # build replaces dist and can remove hashed files while they are being read.
    # Keep this preview build's inputs stable without locking frontend work.
    $frontendSnapshotRoot = Join-Path $root ("build\frontend-snapshots\" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $frontendSnapshotRoot -Force | Out-Null
    $frontendSnapshot = Join-Path $frontendSnapshotRoot "dist"
    Copy-Item -LiteralPath (Join-Path $app "dist") -Destination $frontendSnapshot -Recurse -ErrorAction Stop
    if (-not (Test-Path -LiteralPath (Join-Path $frontendSnapshot "index.html"))) {
        throw "Frontend snapshot is missing index.html. Build the frontend before packaging."
    }
    $frontendSnapshotConfig = Join-Path $frontendSnapshotRoot "tauri.snapshot.json"
    # Tauri's FrontendDist accepts URLs before paths. A Windows drive prefix
    # (C:) is parsed as a URL and launches a directory listing instead of the
    # embedded application. Use a forward-slash relative path from src-tauri.
    $snapshotRelativePath = "../../build/frontend-snapshots/$(Split-Path $frontendSnapshotRoot -Leaf)/dist"
    $snapshotJson = @{ build = @{ frontendDist = $snapshotRelativePath } } | ConvertTo-Json -Depth 3
    [System.IO.File]::WriteAllText($frontendSnapshotConfig, $snapshotJson, [System.Text.UTF8Encoding]::new($false))
    Write-Output "Frontend snapshot config: $frontendSnapshotConfig"
    $previewBuildArguments = @("run", "tauri", "build", "--", "--config", $frontendSnapshotConfig)
    if ($BuildOnly) { $previewBuildArguments += "--no-bundle" }
    else { $previewBuildArguments += @("--bundles", "nsis,msi") }
    Invoke-Checked "npm.cmd" $previewBuildArguments $app
}

if ($BuildOnly) {
    Write-Output "Preview executable built for native UI acceptance. No installer was generated."
    return
}

$bundleRoot = Join-Path $app "src-tauri\target\release\bundle"
if (-not (Test-Path -LiteralPath $bundleRoot)) {
    throw "Tauri completed without producing a bundle directory."
}
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
$installers = Get-ChildItem -LiteralPath $bundleRoot -Recurse -File |
    Where-Object {
        $_.Extension -in @(".exe", ".msi") -and
        $_.BaseName.StartsWith("SPIKE_$version`_", [System.StringComparison]::OrdinalIgnoreCase)
    } |
    Sort-Object FullName
if ($installers.Count -eq 0) {
    throw "No NSIS or MSI installer was produced for Windows product version $version."
}
$installerExtensions = @($installers | ForEach-Object { $_.Extension.ToLowerInvariant() } | Sort-Object -Unique)
if (@($installers).Count -ne 2 -or ($installerExtensions -join ',') -ne '.exe,.msi') {
    throw "The Windows candidate must contain exactly one NSIS EXE and one MSI installer."
}

if ($isProduction) {
    foreach ($installer in $installers) {
        Invoke-SpikeAuthenticodeSigning $signToolPath $installer.FullName $signingThumbprint $storeScope $timestampUri
    }
}

$manifestItems = foreach ($installer in $installers) {
    $destination = Join-Path $artifactRoot $installer.Name
    Copy-Item -LiteralPath $installer.FullName -Destination $destination -Force
    if ($isProduction) {
        $authenticode = Get-SpikeAuthenticodeMetadata $signToolPath $destination $signingThumbprint
        [ordered]@{
            file = $installer.Name
            kind = if ($installer.Extension -ieq '.msi') { 'msi' } else { 'nsis' }
            size = (Get-Item -LiteralPath $destination).Length
            sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
            authenticode = $authenticode
        }
    } else {
        [ordered]@{
            file = $installer.Name
            size = (Get-Item -LiteralPath $destination).Length
            sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
            authenticode = (Get-AuthenticodeSignature -LiteralPath $destination).Status.ToString()
        }
    }
}

if ($isProduction) {
    $manifest = [ordered]@{
        contract = "spike/windows-installer-manifest/v2"
        product = "SPIKE"
        version = $version
        application_version = $applicationVersion
        channel = "production-candidate"
        release_state = "production-candidate"
        license_key_id = $licenseKeyId
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        production_qualified = $false
        signing_policy = [ordered]@{
            required = $true
            expected_signer_thumbprint = $signingThumbprint
            digest_algorithm = "sha256"
            timestamp_required = $true
            timestamp_protocol = "rfc3161"
        }
        files = $manifestItems
    }
    $manifestPath = Join-Path $artifactRoot "SPIKE-$version-production-candidate-installers.json"
} else {
    $manifest = [ordered]@{
        contract = "spike/windows-installer-manifest/v1"
        product = "SPIKE"
        version = $version
        application_version = $applicationVersion
        channel = "engineering-preview"
        license_key_id = $licenseKeyId
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        production_qualified = $false
        files = $manifestItems
    }
    $manifestPath = Join-Path $artifactRoot "SPIKE-$version-preview-installers.json"
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8
if ($isProduction) {
    $workerManifestPath = Join-Path $artifactRoot "bundled\spike-worker.manifest.json"
    $workerRoot = Join-Path $root "app\src-tauri\resources\worker\spike-worker"
    $stagedDependencyLock = Join-Path $artifactRoot "dependencies.lock.json"
    $stagedNotices = Join-Path $artifactRoot "THIRD_PARTY_NOTICES.md"
    $stagedInventory = Join-Path $artifactRoot "config\windows-component-inventory.json"
    $stagedApprovals = Join-Path $artifactRoot "licenses\windows-component-approvals.json"
    $sbomPath = Join-Path $artifactRoot "SPIKE-$version-production-candidate.sbom.json"
    $provenancePath = Join-Path $artifactRoot "SPIKE-$version-production-candidate.provenance.json"
    Invoke-Checked $python @(
        "scripts/build_windows_release_provenance.py",
        "--installer-manifest", $manifestPath,
        "--worker-manifest", $workerManifestPath,
        "--worker-root", $workerRoot,
        "--dependencies-lock", $stagedDependencyLock,
        "--notices", $stagedNotices,
        "--component-inventory", $stagedInventory,
        "--component-approvals", $stagedApprovals,
        "--approval-evidence-root", $artifactRoot,
        "--artifact-root", $artifactRoot,
        "--sbom-output", $sbomPath,
        "--provenance-output", $provenancePath
    ) $root
    Invoke-Checked $python @(
        "scripts/verify_windows_release_provenance.py",
        "--provenance", $provenancePath,
        "--sbom", $sbomPath,
        "--artifact-root", $artifactRoot,
        "--worker-root", $workerRoot
    ) $root
}
Write-Output "$(if ($isProduction) { 'Signed production-candidate' } else { 'Engineering-preview' }) installers: $artifactRoot"
Write-Output "Manifest: $manifestPath"
Write-Warning "These installers are not production-qualified; signing alone does not approve release or qualify physics."
}
finally {
    if ($ownsBuildMutex) { $buildMutex.ReleaseMutex() }
    $buildMutex.Dispose()
}
