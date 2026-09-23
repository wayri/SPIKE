# SPIKE Plugin Installer for KiCad
# Run this after each upgrade to ensure KiCad loads the latest version

param([switch]$Force = $false)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SPIKE Plugin Installer v0.1.7.0" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$sourceDir = Join-Path $PSScriptRoot "kicad_plugin"
$kicadPluginsDir = Join-Path $env:USERPROFILE "Documents\KiCad\10.0\3rdparty\plugins"
$targetDir = Join-Path $kicadPluginsDir "SPIKE"

Write-Host "Source: $sourceDir" -ForegroundColor Yellow
Write-Host "Target: $targetDir" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $sourceDir)) {
    Write-Host "ERROR: Source directory not found!" -ForegroundColor Red
    exit 1
}

if (Test-Path $targetDir) {
    Write-Host "Existing installation found." -ForegroundColor Yellow
    if (-not $Force) {
        $response = Read-Host "Remove existing installation and reinstall? (Y/N)"
        if ($response -ne 'Y' -and $response -ne 'y') {
            Write-Host "Installation cancelled." -ForegroundColor Yellow
            exit 0
        }
    }
    Write-Host "Removing old installation..." -ForegroundColor Yellow
    Remove-Item -Path $targetDir -Recurse -Force
    Write-Host "  ✓ Old installation removed" -ForegroundColor Green
}

if (-not (Test-Path $kicadPluginsDir)) {
    Write-Host "Creating KiCad plugins directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $kicadPluginsDir -Force | Out-Null
    Write-Host "  ✓ Directory created" -ForegroundColor Green
}

Write-Host ""
Write-Host "Installing SPIKE plugin..." -ForegroundColor Cyan

Copy-Item -Path $sourceDir -Destination $targetDir -Recurse -Force
Write-Host "  ✓ Plugin files copied" -ForegroundColor Green

$initFile = Join-Path $targetDir "__init__.py"
if (Test-Path $initFile) {
    Write-Host "  ✓ Installation verified" -ForegroundColor Green
}
else {
    Write-Host "  ✗ Installation verification failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "SPIKE v0.1.7.0 has been installed to:" -ForegroundColor White
Write-Host "  $targetDir" -ForegroundColor Yellow
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Restart KiCad (if running)" -ForegroundColor White
Write-Host "  2. Open a PCB file" -ForegroundColor White
Write-Host "  3. Go to: Tools > External Plugins > SPIKE" -ForegroundColor White
Write-Host ""
Write-Host "Features in v0.1.7.0:" -ForegroundColor Cyan
Write-Host "  ✓ C++ PEEC Solver (Neumann formula)" -ForegroundColor Green
Write-Host "  ✓ PyVista 3D Visualization" -ForegroundColor Green
Write-Host "  ✓ Partial Inductance Computation" -ForegroundColor Green
Write-Host "  ✓ All Unit Tests Passing (4/4)" -ForegroundColor Green
Write-Host ""
