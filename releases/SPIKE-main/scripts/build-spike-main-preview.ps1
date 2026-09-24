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
    $artifactRoot = Join-Path $variantRoot "artifacts"
    $portableRoot = Join-Path $artifactRoot "SPIKE-main-portable"
    $resourceRoot = Join-Path $portableRoot "resources"
    New-Item -ItemType Directory -Force -Path (Join-Path $resourceRoot "bundled"), (Join-Path $resourceRoot "legal"), (Join-Path $resourceRoot "docs") | Out-Null
    Copy-Item -LiteralPath (Join-Path $env:CARGO_TARGET_DIR "release\\spike-desktop.exe") -Destination (Join-Path $portableRoot "SPIKE-main.exe") -Force
    & robocopy (Join-Path $app "src-tauri\\resources\\worker") (Join-Path $resourceRoot "bundled") /E /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Portable worker copy failed: $LASTEXITCODE" }
    Copy-Item -LiteralPath (Join-Path $variantRoot "SPIKE-main-PREVIEW-NOTICE.md") -Destination (Join-Path $resourceRoot "legal\\SPIKE-main-PREVIEW-NOTICE.md") -Force
    Copy-Item -LiteralPath (Join-Path $root "LICENSE"), (Join-Path $root "LICENSING.md"), (Join-Path $root "THIRD_PARTY_NOTICES.md") -Destination (Join-Path $resourceRoot "legal") -Force
    Copy-Item -LiteralPath (Join-Path $root "docs\\ERROR_CODE_CATALOG.md"), (Join-Path $root "TROUBLESHOOTING.md") -Destination (Join-Path $resourceRoot "docs") -Force
    @'
# SPIKE-main portable engineering preview

Unpack this complete directory and start `SPIKE-main.exe`. Keep the bundled
worker runtime under `resources\\bundled\\spike-worker` beside the executable.
This unsigned preview suspends native entitlement capability enforcement only;
project trust and package-signature checks remain active.
'@ | Set-Content -LiteralPath (Join-Path $portableRoot "README.md") -NoNewline -Encoding utf8
    $archive = Join-Path $artifactRoot "SPIKE-main-portable-0.2.12.zip"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Compress-Archive -Path $portableRoot -DestinationPath $archive -CompressionLevel Fastest
    Get-FileHash -LiteralPath $archive -Algorithm SHA256 | Format-List | Out-String | Set-Content -LiteralPath "$archive.sha256.txt"
}
Write-Output "SPIKE-main preview build completed"
