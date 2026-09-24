# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param([switch]$Refresh)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $PSCommandPath
$variantRoot = Split-Path -Parent $scriptRoot
$root = [System.IO.Path]::GetFullPath((Join-Path $variantRoot "..\\.."))
$sourceApp = Join-Path $root "app"
$variantApp = Join-Path $variantRoot "app"
$resolvedVariantRoot = [System.IO.Path]::GetFullPath($variantRoot).TrimEnd('\')
$resolvedVariantApp = [System.IO.Path]::GetFullPath($variantApp)
if (-not $resolvedVariantApp.StartsWith($resolvedVariantRoot + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
    -not $resolvedVariantRoot.StartsWith($root.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to replace variant outside the SPIKE workspace: $resolvedVariantApp"
}

if (-not (Test-Path -LiteralPath $sourceApp -PathType Container)) { throw "Main app source is missing: $sourceApp" }
if (Test-Path -LiteralPath $variantApp) {
    if (-not $Refresh) { throw "Variant already exists. Re-run with -Refresh to replace only its isolated copy: $variantApp" }
    Remove-Item -LiteralPath $variantApp -Recurse -Force
}
New-Item -ItemType Directory -Path $variantApp -Force | Out-Null
& robocopy $sourceApp $variantApp /E /XD node_modules dist .report-preview target .tmp .pytest_cache build
if ($LASTEXITCODE -gt 7) { throw "robocopy failed while preparing the variant (exit $LASTEXITCODE)" }

$sourceModules = Join-Path $sourceApp "node_modules"
if (-not (Test-Path -LiteralPath $sourceModules -PathType Container)) { throw "Main app dependencies are missing: $sourceModules" }
# Keep a physical dependency copy. Vite/esbuild resolves configuration through a
# junction to the main checkout inconsistently on Windows, which makes the
# preview build non-reproducible even though source files are isolated.
& robocopy $sourceModules (Join-Path $variantApp "node_modules") /E /XD .cache
if ($LASTEXITCODE -gt 7) { throw "robocopy failed while copying preview dependencies (exit $LASTEXITCODE)" }

function Replace-Once([string]$Path, [string]$Old, [string]$New) {
    $text = [System.IO.File]::ReadAllText($Path).Replace("`r`n", "`n")
    $Old = $Old.Replace("`r`n", "`n")
    $New = $New.Replace("`r`n", "`n")
    $count = ([regex]::Matches($text, [regex]::Escape($Old))).Count
    if ($count -ne 1) { throw "Expected one overlay target in $Path; found $count" }
    [System.IO.File]::WriteAllText($Path, $text.Replace($Old, $New), [System.Text.UTF8Encoding]::new($false))
}

$cargoPath = Join-Path $variantApp "src-tauri\\Cargo.toml"
Replace-Once $cargoPath 'custom-protocol = ["tauri/custom-protocol"]' "custom-protocol = [`"tauri/custom-protocol`"]`nspike-main-preview = []"

$libPath = Join-Path $variantApp "src-tauri\\src\\lib.rs"
$originalGate = @'
fn require_worker_capability(
    app: &tauri::AppHandle,
    request: &serde_json::Value,
) -> Result<(), String> {
    let capability = entitlement::capability_for_worker(request);
    if capability == "project.read" {
        return Ok(());
    }
    let license = entitlement::status(app);
    if license.permits(capability) {
        Ok(())
    } else {
        Err(format!(
            "SPIKE-BE-SECURITY-E-0006: a valid license with capability '{capability}' is required ({})",
            license.message.as_deref().unwrap_or("license unavailable")
        ))
    }
}
'@
$previewGate = @'
fn require_worker_capability(
    app: &tauri::AppHandle,
    request: &serde_json::Value,
) -> Result<(), String> {
    let capability = entitlement::capability_for_worker(request);
    #[cfg(feature = "spike-main-preview")]
    {
        // Isolated unsigned engineering-preview build only. License parsing,
        // package signatures, trust bindings, and every default SPIKE build
        // remain unchanged; this feature suspends entitlement capability denial.
        let _ = (app, request, capability);
        return Ok(());
    }
    #[cfg(not(feature = "spike-main-preview"))]
    {
        if capability == "project.read" {
            return Ok(());
        }
        let license = entitlement::status(app);
        if license.permits(capability) {
            Ok(())
        } else {
            Err(format!(
                "SPIKE-BE-SECURITY-E-0006: a valid license with capability '{capability}' is required ({})",
                license.message.as_deref().unwrap_or("license unavailable")
            ))
        }
    }
}
'@
Replace-Once $libPath $originalGate $previewGate

$configPath = Join-Path $variantApp "src-tauri\\tauri.conf.json"
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$config.productName = "SPIKE-main"
$config.identifier = "org.spike.main"
$config.app.windows[0].title = "SPIKE-main | Electronic Systems Integrity Workbench"
$config.bundle.shortDescription = "SPIKE-main unsigned engineering preview"
$config.bundle.longDescription = "Full SPIKE engineering workbench preview. Entitlement enforcement is temporarily suspended; numerical validation and third-party license obligations remain unchanged."
$config.bundle.licenseFile = "../../SPIKE-main-PREVIEW-NOTICE.md"
$config.bundle.PSObject.Properties.Remove("fileAssociations")
$config.bundle.windows.nsis.startMenuFolder = "SPIKE-main"
$resources = [ordered]@{}
foreach ($property in $config.bundle.resources.PSObject.Properties) {
    $key = if ($property.Name.StartsWith("../../")) { "../../../../" + $property.Name.Substring(6) } else { $property.Name }
    $resources[$key] = $property.Value
}
$resources.Remove("../../../../licenses/SPIKE-PREVIEW-NOTICE.md")
$resources["../../SPIKE-main-PREVIEW-NOTICE.md"] = "legal/SPIKE-main-PREVIEW-NOTICE.md"
$config.bundle.resources = $resources
[System.IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 12), [System.Text.UTF8Encoding]::new($false))

$topicsPath = Join-Path $variantApp "src\\HelpTopics.tsx"
$topics = [System.IO.File]::ReadAllText($topicsPath)
$licensingPattern = '(?s)\{ id: "licensing",.*?\},\s*(?=\{ id: )'
$previewTopic = @'
{ id: "licensing", title: "SPIKE-main engineering preview", keywords: "preview entitlement suspended license signature trust", body: <><p>SPIKE-main is an unsigned engineering preview whose native entitlement capability enforcement is temporarily suspended. This applies only to this separately identified preview build; default SPIKE release builds retain signed-entitlement enforcement.</p><p>Project-package signatures, trust bindings, importer approval, and other security checks remain active. Signed entitlement files may still be inspected or managed, but they do not control feature access in this preview. This suspension does not change solver validation, result status, third-party licenses, or the package's non-commercial preview status.</p></> },

'@
if ([regex]::Matches($topics, $licensingPattern).Count -ne 1) { throw "Could not locate exactly one licensing topic in $topicsPath" }
[System.IO.File]::WriteAllText($topicsPath, [regex]::Replace($topics, $licensingPattern, $previewTopic), [System.Text.UTF8Encoding]::new($false))

$aboutPath = Join-Path $variantApp "src\\AboutDialog.tsx"
Replace-Once $aboutPath 'const statusTone = license.status === "active" ? "" : license.status === "expired" ? "warn" : "error";' 'const statusTone = ""; // Preview access is enabled independently of entitlement state.'
Replace-Once $aboutPath '<p className="about-note"><b>Numerical validity:</b>' '<p className="about-note"><b>SPIKE-main preview:</b> entitlement capability enforcement is temporarily suspended in this separately identified unsigned engineering build. Project trust and package-signature checks remain active.</p><p className="about-note"><b>Numerical validity:</b>'
Replace-Once $aboutPath '<b>{license.tier.charAt(0).toUpperCase() + license.tier.slice(1)} tier · {license.status}</b>' '<b>SPIKE-main engineering preview · access enabled</b>'
Replace-Once $aboutPath '<span>{license.status === "active" ? `${license.licensee} · ${formatExpiry(license.expiresAt)}${license.licenseType ? ` · ${license.licenseType}` : ""}` : (license.message ?? "No entitlement is installed")}</span>' '<span>Entitlement capability enforcement is suspended. License state remains available for management and inspection: {license.status}.</span>'

$settingsPath = Join-Path $variantApp "src\\UniversalSettingsModal.tsx"
Replace-Once $settingsPath '<SettingsSection title="Signed entitlement">' '<SettingsSection title="Licensing (suspended in SPIKE-main preview)"><p className="settings-note">This unsigned engineering preview temporarily suspends native entitlement capability enforcement. Signed entitlement management remains available, while project trust, package signatures, third-party terms, and numerical validation status remain unchanged.</p>'
Replace-Once $settingsPath 'setLicenseNotice("License removed. SPIKE is now read-only.");' 'setLicenseNotice("License removed. SPIKE-main preview access remains enabled; no entitlement record is installed.");'

$appPath = Join-Path $variantApp "src\\App.tsx"
Replace-Once $appPath 'displayName: license.status === "active" ? license.licensee : current.profile.displayName,' 'displayName: "SPIKE-main preview",'
Replace-Once $appPath 'initials: license.status === "active" ? license.licensee.split(/\s+/).map(part => part[0]).join("").slice(0, 3).toUpperCase() || "USR" : "USR",' 'initials: "PRE",'
Replace-Once $appPath 'userType: license.tier === "developer" ? "developer" : license.status === "active" ? "engineer" : "viewer",' 'userType: "engineering-preview",'
Replace-Once $appPath '<b>SPIKE</b><small>ELECTRONIC SYSTEMS INTEGRITY WORKBENCH</small>' '<b>SPIKE-main</b><small>UNSIGNED ENGINEERING PREVIEW</small>'

$settingsModelPath = Join-Path $variantApp "src\\appSettings.ts"
Replace-Once $settingsModelPath 'export type UserType = "viewer" | "engineer" | "administrator" | "developer";' 'export type UserType = "viewer" | "engineer" | "administrator" | "developer" | "engineering-preview";'

$versionPath = Join-Path $variantApp "src\\appVersion.ts"
Replace-Once $versionPath 'export const PRODUCT_NAME = "SPIKE";' 'export const PRODUCT_NAME = "SPIKE-main";'

$indexPath = Join-Path $variantApp "index.html"
Replace-Once $indexPath '<title>SPIKE | Electronic Systems Integrity Workbench</title>' '<title>SPIKE-main | Unsigned Engineering Preview</title>'

$packagePath = Join-Path $variantApp "package.json"
$package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
$package.scripts.build = "tsc && vite build --configLoader runner"
[System.IO.File]::WriteAllText($packagePath, ($package | ConvertTo-Json -Depth 12), [System.Text.UTF8Encoding]::new($false))

$noticePath = Join-Path $variantRoot "SPIKE-main-PREVIEW-NOTICE.md"
@'
# SPIKE-main unsigned engineering preview notice

This isolated SPIKE-main build is an unsigned engineering preview. Its native
entitlement capability requirement is temporarily suspended only when compiled
with the `spike-main-preview` Cargo feature. The default SPIKE source and
release builds are not changed by this overlay.

Do not treat the suspension as a commercial license grant, production release,
or numerical validation. Preserve `LICENSE`, `LICENSING.md`, and
`THIRD_PARTY_NOTICES.md`; project signatures, trust bindings, and other
non-entitlement security checks remain enabled.
'@ | Set-Content -LiteralPath $noticePath -NoNewline -Encoding utf8

Write-Output "Prepared isolated SPIKE-main preview: $variantApp"
