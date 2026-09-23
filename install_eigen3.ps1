# SPIKE v0.1.7.0 - Eigen3 Quick Install Script
# This script installs Eigen3 using vcpkg on Windows

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  SPIKE v0.1.7.0 - Eigen3 Installation via vcpkg" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

$VCPKG_ROOT = "C:\vcpkg"
$EIGEN_PACKAGE = "eigen3:x64-windows"

# Check if vcpkg is already installed
if (Test-Path "$VCPKG_ROOT\vcpkg.exe") {
    Write-Host "[OK] vcpkg found at: $VCPKG_ROOT" -ForegroundColor Green
} else {
    Write-Host "[INFO] vcpkg not found. Installing..." -ForegroundColor Yellow
    
    # Check if git is available
    $gitPath = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitPath) {
        Write-Host "[ERROR] git is not installed. Please install git first:" -ForegroundColor Red
        Write-Host "  https://git-scm.com/download/win" -ForegroundColor Yellow
        exit 1
    }
    
    # Clone vcpkg
    Write-Host "[INFO] Cloning vcpkg repository..." -ForegroundColor Cyan
    Push-Location C:\
    git clone https://github.com/Microsoft/vcpkg.git
    Pop-Location
    
    if (-not (Test-Path "$VCPKG_ROOT\vcpkg.exe")) {
        # Bootstrap vcpkg
        Write-Host "[INFO] Bootstrapping vcpkg..." -ForegroundColor Cyan
        Push-Location $VCPKG_ROOT
        .\bootstrap-vcpkg.bat
        Pop-Location
    }
    
    if (Test-Path "$VCPKG_ROOT\vcpkg.exe") {
        Write-Host "[OK] vcpkg installed successfully!" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] vcpkg installation failed" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# Check if Eigen3 is already installed
Write-Host "[INFO] Checking for Eigen3..." -ForegroundColor Cyan
$eigenInstalled = & "$VCPKG_ROOT\vcpkg.exe" list | Select-String "eigen3:x64-windows"

if ($eigenInstalled) {
    Write-Host "[OK] Eigen3 is already installed!" -ForegroundColor Green
    Write-Host "     $eigenInstalled" -ForegroundColor Gray
} else {
    Write-Host "[INFO] Installing Eigen3 (this may take a few minutes)..." -ForegroundColor Yellow
    
    Push-Location $VCPKG_ROOT
    .\vcpkg.exe install $EIGEN_PACKAGE
    Pop-Location
    
    # Verify installation
    $eigenInstalled = & "$VCPKG_ROOT\vcpkg.exe" list | Select-String "eigen3:x64-windows"
    if ($eigenInstalled) {
        Write-Host "[OK] Eigen3 installed successfully!" -ForegroundColor Green
        Write-Host "     $eigenInstalled" -ForegroundColor Gray
    } else {
        Write-Host "[ERROR] Eigen3 installation failed" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# Integrate with Visual Studio (optional)
Write-Host "[INFO] Integrating vcpkg with build system..." -ForegroundColor Cyan
Push-Location $VCPKG_ROOT
.\vcpkg.exe integrate install
Pop-Location

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Eigen3 Installation Complete!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Build SPIKE C++ kernel:" -ForegroundColor White
Write-Host "     cd build" -ForegroundColor Gray
Write-Host "     cmake .." -ForegroundColor Gray
Write-Host "     cmake --build . --config Release" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. vcpkg location: $VCPKG_ROOT" -ForegroundColor White
Write-Host "  3. Eigen3 headers: $VCPKG_ROOT\installed\x64-windows\include\eigen3" -ForegroundColor White
Write-Host ""
