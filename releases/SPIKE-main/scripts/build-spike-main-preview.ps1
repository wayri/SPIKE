# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param([switch]$Bundle, [switch]$Portable)
$ErrorActionPreference = "Stop"
$variantRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$root = [System.IO.Path]::GetFullPath((Join-Path $variantRoot "..\\.."))
$app = Join-Path $variantRoot "app"
$env:CARGO_TARGET_DIR = Join-Path $variantRoot "cargo-target"
if (-not (Test-Path -LiteralPath $app)) { throw "Prepare the isolated SPIKE-main preview first." }
& (Join-Path (Split-Path -Parent $PSCommandPath) "test-spike-main-preview.ps1")
if ($LASTEXITCODE -ne 0) { throw "Preview checks failed" }
Push-Location $app
try {
    $args = @("run", "tauri", "build", "--", "--features", "spike-main-preview")
    if ($Bundle) { $args += @("--bundles", "nsis") } else { $args += "--no-bundle" }
    & npm.cmd @args
    if ($LASTEXITCODE -ne 0) { throw "Tauri SPIKE-main preview build failed: $LASTEXITCODE" }
} finally { Pop-Location }
if ($Bundle) {
    $artifactRoot = Join-Path $variantRoot "artifacts"
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
    $installers = Get-ChildItem -LiteralPath (Join-Path $env:CARGO_TARGET_DIR "release\\bundle\\nsis") -Filter "*.exe" -File
    if ($installers.Count -ne 1) { throw "Expected one SPIKE-main NSIS installer; found $($installers.Count)" }
    Copy-Item -LiteralPath $installers[0].FullName -Destination (Join-Path $artifactRoot $installers[0].Name) -Force
    Get-FileHash -LiteralPath (Join-Path $artifactRoot $installers[0].Name) -Algorithm SHA256 | Format-List | Out-String | Set-Content -LiteralPath (Join-Path $artifactRoot "$($installers[0].Name).sha256.txt")
}
if ($Portable) {
    $artifactRoot = [System.IO.Path]::GetFullPath((Join-Path $variantRoot "artifacts"))
    New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
    $portableRoot = [System.IO.Path]::GetFullPath((Join-Path $artifactRoot "SPIKE-main-portable"))
    $artifactPrefix = $artifactRoot.TrimEnd("\\", "/") + [System.IO.Path]::DirectorySeparatorChar
    if (-not $portableRoot.StartsWith($artifactPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove portable path outside this variant's artifacts directory: $portableRoot"
    }
    if (Test-Path -LiteralPath $portableRoot) { Remove-Item -LiteralPath $portableRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $portableRoot | Out-Null
    Copy-Item -LiteralPath (Join-Path $env:CARGO_TARGET_DIR "release\\spike-desktop.exe") -Destination (Join-Path $portableRoot "SPIKE-main.exe") -Force
    $config = Get-Content -LiteralPath (Join-Path $app "src-tauri\\tauri.conf.json") -Raw | ConvertFrom-Json
    $portableResourceAudit = @()
    foreach ($entry in $config.bundle.resources.PSObject.Properties) {
        $sourceKey = $entry.Name
        $destination = Join-Path $portableRoot $entry.Value
        if ($sourceKey.StartsWith("resources/")) {
            $source = Join-Path $app (Join-Path "src-tauri" $sourceKey)
        } elseif ($sourceKey.StartsWith("../../../../")) {
            $source = Join-Path $root $sourceKey.Substring("../../../../".Length)
        } elseif ($sourceKey.StartsWith("../../")) {
            $source = Join-Path $variantRoot $sourceKey.Substring("../../".Length)
        } else {
            throw "Unsupported Tauri resource source: $sourceKey"
        }
        if (-not (Test-Path -LiteralPath $source)) { throw "Configured Tauri resource is missing: $source" }
        if (Test-Path -LiteralPath $source -PathType Container) {
            New-Item -ItemType Directory -Force -Path $destination | Out-Null
            & robocopy $source $destination /E /NFL /NDL /NJH /NJS /NC /NS | Out-Null
            if ($LASTEXITCODE -gt 7) { throw "Portable resource copy failed for ${sourceKey}: $LASTEXITCODE" }
            $portableResourceAudit += [pscustomobject]@{ source = $sourceKey; destination = $entry.Value; kind = "directory" }
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
            Copy-Item -LiteralPath $source -Destination $destination -Force
            $portableResourceAudit += [pscustomobject]@{ source = $sourceKey; destination = $entry.Value; kind = "file" }
        }
    }
    $missingResources = @($config.bundle.resources.PSObject.Properties | Where-Object { -not (Test-Path -LiteralPath (Join-Path $portableRoot $_.Value)) })
    if ($missingResources.Count) { throw "Portable package is missing configured resources: $($missingResources.Name -join ', ')" }
    @'
# SPIKE-main portable engineering preview

Unpack this complete directory and start `SPIKE-main.exe`. Keep the bundled
worker runtime under `bundled\\spike-worker` beside the executable.
This unsigned preview suspends native entitlement capability enforcement only;
project trust and package-signature checks remain active.
'@ | Set-Content -LiteralPath (Join-Path $portableRoot "PORTABLE-README.md") -NoNewline -Encoding utf8
    $archive = Join-Path $artifactRoot "SPIKE-main-portable-0.2.12.zip"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Compress-Archive -Path $portableRoot -DestinationPath $archive -CompressionLevel Fastest
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($entry in $portableResourceAudit) {
            $zipPrefix = "SPIKE-main-portable/" + $entry.destination.Replace("\\", "/")
            $entry | Add-Member -NotePropertyName zip_present -NotePropertyValue ($(if ($entry.kind -eq "directory") { @($zip.Entries | Where-Object { $_.FullName.StartsWith($zipPrefix + "/", [System.StringComparison]::Ordinal) }).Count -gt 0 } else { $zip.Entries.FullName -contains $zipPrefix }))
        }
    } finally { $zip.Dispose() }
    $failedZipAudit = @($portableResourceAudit | Where-Object { -not $_.zip_present })
    if ($failedZipAudit.Count) { throw "Portable ZIP is missing configured resources: $($failedZipAudit.destination -join ', ')" }
    $portableResourceAudit | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $artifactRoot "SPIKE-main-portable-resource-audit.json") -Encoding utf8
    Get-FileHash -LiteralPath $archive -Algorithm SHA256 | Format-List | Out-String | Set-Content -LiteralPath "$archive.sha256.txt"
}
Write-Output "SPIKE-main preview build completed"
