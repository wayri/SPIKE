# SPDX-License-Identifier: Apache-2.0
$ErrorActionPreference = "Stop"
$variantRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$app = Join-Path $variantRoot "app"
$env:CARGO_TARGET_DIR = Join-Path $variantRoot "cargo-target"
$config = Get-Content -LiteralPath (Join-Path $app "src-tauri\\tauri.conf.json") -Raw | ConvertFrom-Json
if ($config.productName -ne "SPIKE-main" -or $config.identifier -ne "org.spike.main") { throw "SPIKE-main identity is not isolated" }
if ($config.bundle.windows.nsis.startMenuFolder -ne "SPIKE-main") { throw "SPIKE-main start-menu folder is not isolated" }
if ($null -ne $config.bundle.fileAssociations) { throw "SPIKE-main must not register the .spike association" }
if ($config.bundle.licenseFile -ne "../../SPIKE-main-PREVIEW-NOTICE.md") { throw "SPIKE-main must ship its truthful preview notice" }
$lib = Get-Content -LiteralPath (Join-Path $app "src-tauri\\src\\lib.rs") -Raw
if ($lib -notmatch '#\[cfg\(feature = "spike-main-preview"\)\]') { throw "Preview capability bypass feature is absent" }
if ($lib -notmatch 'package signatures, trust bindings') { throw "Preview bypass scope is not documented in the native gate" }
$topics = Get-Content -LiteralPath (Join-Path $app "src\\HelpTopics.tsx") -Raw
if ($topics -notmatch 'entitlement capability enforcement is temporarily suspended' -or $topics -notmatch 'Project-package signatures') { throw "Preview help does not disclose the suspension and preserved trust checks" }
$settings = Get-Content -LiteralPath (Join-Path $app "src\\UniversalSettingsModal.tsx") -Raw
if ($settings -notmatch 'suspended in SPIKE-main preview') { throw "Preview settings do not disclose the suspension" }
$about = Get-Content -LiteralPath (Join-Path $app "src\\AboutDialog.tsx") -Raw
if ($about -notmatch 'SPIKE-main engineering preview · access enabled' -or $about -notmatch 'const statusTone = ""') { throw "Preview About status is not truthful" }
$shell = Get-Content -LiteralPath (Join-Path $app "src\\App.tsx") -Raw
if ($shell -notmatch '<b>SPIKE-main</b><small>UNSIGNED ENGINEERING PREVIEW</small>' -or $shell -notmatch 'userType: "engineering-preview"') { throw "Preview in-app identity is incomplete" }
$version = Get-Content -LiteralPath (Join-Path $app "src\\appVersion.ts") -Raw
if ($version -notmatch 'PRODUCT_NAME = "SPIKE-main"') { throw "Preview About identity is incomplete" }
Push-Location $app
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed: $LASTEXITCODE" }
    Push-Location (Join-Path $app "src-tauri")
    try {
        & cargo test --lib entitlement::tests:: --features spike-main-preview
        if ($LASTEXITCODE -ne 0) { throw "Native entitlement test failed: $LASTEXITCODE" }
        & cargo test --lib package_trust::tests:: --features spike-main-preview
        if ($LASTEXITCODE -ne 0) { throw "Native package-trust test failed: $LASTEXITCODE" }
    } finally { Pop-Location }
} finally { Pop-Location }
Write-Output "SPIKE-main preview identity, disclosure, frontend, and native-feature checks passed"
