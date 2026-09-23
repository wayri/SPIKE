[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$StagingRoot,
    [ValidateSet("windows-sandbox", "hyperv-vm", "external-clean-vm", "physical-clean-machine", "not-isolated")]
    [string]$Provider = "not-isolated",
    [string]$AfterProject,
    [string]$EnvironmentAttestationPath,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
$staging = [IO.Path]::GetFullPath($StagingRoot)
$inputsPath = Join-Path $staging "inputs.json"
$inputsDigestPath = Join-Path $staging "inputs.sha256"
if (-not (Test-Path -LiteralPath $inputsPath -PathType Leaf) -or -not (Test-Path -LiteralPath $inputsDigestPath -PathType Leaf)) {
    throw "Staging is missing inputs.json or inputs.sha256."
}
$expectedInputsDigest = ((Get-Content -LiteralPath $inputsDigestPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($expectedInputsDigest -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $inputsPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedInputsDigest) {
    throw "inputs.json does not match its staged SHA-256."
}
$inputs = Get-Content -LiteralPath $inputsPath -Raw | ConvertFrom-Json
$run = Join-Path $staging ("run-" + $inputs.run_id)
New-Item -ItemType Directory -Force -Path $run | Out-Null

function Get-Sha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-Json([string]$Path, $Value) { $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding utf8 }
function Resolve-StagedInput([string]$RelativePath) {
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains('..') -or $RelativePath.Contains(':')) {
        throw "Staged input path is unsafe."
    }
    $resolved = [IO.Path]::GetFullPath((Join-Path $staging $RelativePath))
    $prefix = $staging.TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Staged input escapes the staging root." }
    return $resolved
}
function Get-PackageManifestDigest([string]$Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entry = $archive.GetEntry("manifest.json")
        if ($null -eq $entry) { throw "SPIKE package has no manifest.json" }
        $reader = New-Object IO.StreamReader($entry.Open())
        try { return ((ConvertFrom-Json -InputObject $reader.ReadToEnd()).manifest_payload_sha256).ToString().ToLowerInvariant() }
        finally { $reader.Dispose() }
    } finally { $archive.Dispose() }
}

$installer = Resolve-StagedInput ([string]$inputs.installer.path)
$fixture = Resolve-StagedInput ([string]$inputs.fixture.path)
$fixtureSummary = Resolve-StagedInput ([string]$inputs.fixture_summary.path)
$installerManifest = Resolve-StagedInput ([string]$inputs.installer_manifest.path)
$runner = Resolve-StagedInput ([string]$inputs.runner.path)
foreach ($record in @(
    @($installer, [string]$inputs.installer.sha256),
    @($fixture, [string]$inputs.fixture.sha256),
    @($fixtureSummary, [string]$inputs.fixture_summary.sha256),
    @($installerManifest, [string]$inputs.installer_manifest.sha256),
    @($runner, [string]$inputs.runner.sha256)
)) {
    if (-not (Test-Path -LiteralPath $record[0] -PathType Leaf) -or (Get-Sha256 $record[0]) -ne $record[1]) {
        throw "A staged harness input does not match inputs.json."
    }
}
$executingRunner = [IO.Path]::GetFullPath($PSCommandPath)
if (-not (Test-Path -LiteralPath $executingRunner -PathType Leaf) -or (Get-Sha256 $executingRunner) -ne [string]$inputs.runner.sha256) {
    throw "The executing runner does not match the staged runner SHA-256."
}
Copy-Item -LiteralPath $inputsPath -Destination (Join-Path $run "inputs.json") -Force
Copy-Item -LiteralPath $executingRunner -Destination (Join-Path $run "executing-runner.ps1") -Force
$existingUninstall = @(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "SPIKE*" } | Select-Object DisplayName, DisplayVersion, InstallLocation, UninstallString)
$existingExtension = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.spike\UserChoice" -ErrorAction SilentlyContinue
$existingClass = Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\.spike" -ErrorAction SilentlyContinue
$residuePaths = @("${env:ProgramFiles}\SPIKE", "${env:LOCALAPPDATA}\Programs\SPIKE") | Where-Object { Test-Path -LiteralPath $_ }
$preflight = [ordered]@{
    provider = $Provider
    os = Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber
    gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion)
    webview2_version = ((Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\*" -ErrorAction SilentlyContinue | Where-Object { $_.name -match "WebView" } | Select-Object -First 1).pv)
    display_scale_percent = [Math]::Round(((Get-ItemProperty 'HKCU:\Control Panel\Desktop\WindowMetrics' -Name AppliedDPI -ErrorAction SilentlyContinue).AppliedDPI / 96.0) * 100, 2)
    process_path_entries = @($env:Path -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
    pre_install_spike_residue = [ordered]@{
        uninstall_products = $existingUninstall
        install_paths = @($residuePaths)
        file_association = [ordered]@{ user_progid = $existingExtension.ProgId; registered_progid = $existingClass."(default)" }
    }
}
Write-Json (Join-Path $run "preflight.json") $preflight

$isolatedProviders = @("windows-sandbox", "hyperv-vm", "external-clean-vm", "physical-clean-machine")
$environmentAttestation = [ordered]@{
    status = "unattested"; cryptographically_verified = $false; eligible_for_human_review = $false
    note = "No structurally bound environment attestation was supplied; this harness does not prove that the machine is clean or isolated."
}
if (-not [string]::IsNullOrWhiteSpace($EnvironmentAttestationPath)) {
    $attestationSource = [IO.Path]::GetFullPath($EnvironmentAttestationPath)
    if (-not (Test-Path -LiteralPath $attestationSource -PathType Leaf)) { throw "EnvironmentAttestationPath does not name a readable file." }
    try { $suppliedAttestation = Get-Content -LiteralPath $attestationSource -Raw | ConvertFrom-Json } catch { throw "Environment attestation is not valid JSON." }
    $attestationFields = @("contract", "provider", "run_id", "inputs_sha256", "attestor", "issued_at", "environment_id", "isolation_claim")
    $actualAttestationFields = @($suppliedAttestation.PSObject.Properties.Name)
    if ($suppliedAttestation.contract -ne "spike/wave1-environment-attestation/v1" -or @($attestationFields | Where-Object { [string]::IsNullOrWhiteSpace([string]$suppliedAttestation.$_) }).Count -ne 0 -or $actualAttestationFields.Count -ne $attestationFields.Count -or @($actualAttestationFields | Where-Object { $_ -notin $attestationFields }).Count -ne 0) {
        throw "Environment attestation does not satisfy the bounded v1 contract."
    }
    if ([string]$suppliedAttestation.provider -ne $Provider -or [string]$suppliedAttestation.run_id -ne [string]$inputs.run_id -or [string]$suppliedAttestation.inputs_sha256.ToLowerInvariant() -ne (Get-Sha256 $inputsPath)) {
        throw "Environment attestation provider, run_id, or inputs SHA-256 does not bind this run."
    }
    if ([string]$suppliedAttestation.inputs_sha256 -notmatch '^[0-9a-fA-F]{64}$' -or [string]$suppliedAttestation.attestor.Length -gt 256 -or [string]$suppliedAttestation.environment_id.Length -gt 256 -or [string]$suppliedAttestation.isolation_claim.Length -gt 1024) {
        throw "Environment attestation has invalid bounded fields."
    }
    if ([string]$suppliedAttestation.issued_at.Length -gt 64 -or -not ([string]$suppliedAttestation.issued_at -match '(Z|[+-]\d\d:\d\d)$')) { throw "Environment attestation issued_at must include a bounded RFC 3339 timezone." }
    try { $issuedAt = [DateTimeOffset]::Parse([string]$suppliedAttestation.issued_at) } catch { throw "Environment attestation issued_at must be an RFC 3339 timestamp with timezone." }
    $attestationCopy = Join-Path $run "environment-attestation.json"
    Copy-Item -LiteralPath $attestationSource -Destination $attestationCopy -Force
    if ($Provider -in $isolatedProviders) {
        $environmentAttestation = [ordered]@{
            status = "supplied_for_human_review"; cryptographically_verified = $false; eligible_for_human_review = $true
            note = "Structurally bound attestation supplied for human review only; it is not cryptographic proof that the machine is clean or isolated."
            contract = $suppliedAttestation.contract; provider = $suppliedAttestation.provider; run_id = $suppliedAttestation.run_id; inputs_sha256 = $suppliedAttestation.inputs_sha256.ToLowerInvariant()
            attestor = $suppliedAttestation.attestor; issued_at = $suppliedAttestation.issued_at; environment_id = $suppliedAttestation.environment_id; isolation_claim = $suppliedAttestation.isolation_claim
            artifact = [ordered]@{ path = "environment-attestation.json"; sha256 = Get-Sha256 $attestationCopy }
        }
    } else {
        $environmentAttestation.note = "An attestation was copied, but provider not-isolated is never eligible for human review and does not prove a clean machine."
    }
}

$installLog = Join-Path $run "install.log"
$mechanics = [ordered]@{ staged_hashes_verified = $true; installer_started = $false; installer_exit_code = $null; installed_product = $null; spike_association = $null; launched_process_id = $null; after_project_supplied = $false }
if (-not $SkipInstall) {
    $mechanics.installer_started = $true
    if ([IO.Path]::GetExtension($installer).ToLowerInvariant() -eq ".msi") {
        $process = Start-Process msiexec.exe -ArgumentList @("/i", $installer, "/qn", "/norestart", "/L*v", $installLog) -Wait -PassThru
    } else {
        $process = Start-Process $installer -ArgumentList @("/S") -Wait -PassThru -RedirectStandardOutput $installLog
    }
    $mechanics.installer_exit_code = $process.ExitCode
    if ($process.ExitCode -ne 0) { throw "Installer exited with code $($process.ExitCode)." }
}
$uninstall = @(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "SPIKE*" } | Select-Object DisplayName, DisplayVersion, InstallLocation, UninstallString)
$mechanics.installed_product = $uninstall
$extension = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.spike\UserChoice" -ErrorAction SilentlyContinue
$classRegistration = Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\.spike" -ErrorAction SilentlyContinue
$progressiveId = if (-not [string]::IsNullOrWhiteSpace($extension.ProgId)) { [string]$extension.ProgId } else { [string]$classRegistration."(default)" }
$associationCommand = if (-not [string]::IsNullOrWhiteSpace($progressiveId)) {
    (Get-ItemProperty ("Registry::HKEY_CLASSES_ROOT\" + $progressiveId + "\shell\open\command") -ErrorAction SilentlyContinue)."(default)"
} else { $null }
$mechanics.spike_association = [ordered]@{ user_progid = $extension.ProgId; registered_progid = $progressiveId; command = $associationCommand }
$applicationCandidates = @()
foreach ($product in $uninstall) {
    if (-not [string]::IsNullOrWhiteSpace($product.InstallLocation)) {
        $applicationCandidates += Join-Path $product.InstallLocation "spike-desktop.exe"
    }
}
$applicationCandidates += "${env:ProgramFiles}\SPIKE\spike-desktop.exe"
$applicationCandidates += "${env:LOCALAPPDATA}\Programs\SPIKE\spike-desktop.exe"
$app = Get-Item -LiteralPath @($applicationCandidates | Sort-Object -Unique) -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $app) {
    $process = Start-Process $app.FullName -ArgumentList @($fixture) -PassThru
    Start-Sleep -Seconds 3
    $mechanics.launched_process_id = $process.Id
}
$after = if ([string]::IsNullOrWhiteSpace($AfterProject)) { $fixture } else { [IO.Path]::GetFullPath($AfterProject) }
if (-not (Test-Path -LiteralPath $after)) { throw "AfterProject does not exist." }
Copy-Item -LiteralPath $after -Destination (Join-Path $run "after-project.spike") -Force
$mechanics.after_project_supplied = -not [string]::IsNullOrWhiteSpace($AfterProject)
$beforeManifestDigest = [string]$inputs.fixture.manifest_payload_sha256
$afterManifestDigest = Get-PackageManifestDigest (Join-Path $run "after-project.spike")
if ($mechanics.after_project_supplied -and $afterManifestDigest -eq $beforeManifestDigest) {
    throw "The reviewed persistence run did not produce a changed project manifest identity."
}
Write-Json (Join-Path $run "mechanics.json") $mechanics
Write-Json (Join-Path $run "review-required.json") ([ordered]@{ contract = "spike/wave1-clean-machine-review-required/v1"; status = "pending_human"; required_checks = @("install_launch", "file_association", "assembly_hierarchy", "pixel_views", "placement_persistence", "reparent_world_pose", "topology_snap", "structure_persistence", "operation_cancellation", "upgrade_uninstall"); note = "This harness records mechanics only. A reviewer must inspect the UI and pixels and create the human acceptance evidence." })

$files = Get-ChildItem -LiteralPath $run -File | Where-Object { $_.Name -ne "harness-run.json" } | Sort-Object Name
$ledger = @($files | ForEach-Object { [ordered]@{ path = $_.Name; sha256 = Get-Sha256 $_.FullName } })
$record = [ordered]@{
    contract = "spike/wave1-clean-machine-harness/v2"; run_id = $inputs.run_id; provider = $Provider
    eligible_for_human_review = ($Provider -in $isolatedProviders -and $environmentAttestation.status -eq "supplied_for_human_review" -and $environmentAttestation.eligible_for_human_review -eq $true)
    inputs_sha256 = Get-Sha256 $inputsPath; installer_sha256 = Get-Sha256 $installer
    before_manifest_payload_sha256 = $beforeManifestDigest
    after_manifest_payload_sha256 = $afterManifestDigest
    environment = $preflight; mechanics = $mechanics; environment_attestation = $environmentAttestation; artifacts = $ledger
}
Write-Json (Join-Path $run "harness-run.json") $record
Write-Output (Join-Path $run "harness-run.json")
