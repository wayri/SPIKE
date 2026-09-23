# build_kernel.ps1
# Build script for SPIKE C++ Kernel via CMake and nanobind

$ErrorActionPreference = "Stop"

Write-Host "SPIKE Simulation Kernel Builder" -ForegroundColor Cyan
Write-Host "===============================" -ForegroundColor Cyan

# 1. Activate Python Environment to locate nanobind
$python_exe = ".\aether_env\Scripts\python.exe"
if (-not (Test-Path $python_exe)) {
    Write-Host "ERROR: Virtual environment not found at .\aether_env" -ForegroundColor Red
    exit 1
}

$nanobind_dir = & $python_exe -c "import nanobind; print(nanobind.cmake_dir())"
Write-Host "Found nanobind at: $nanobind_dir" -ForegroundColor Green

# 2. Configure CMake
if (-not (Test-Path "build")) {
    New-Item -ItemType Directory -Path "build" | Out-Null
}
Set-Location "build"

Write-Host "`nConfiguring CMake..." -ForegroundColor Yellow
cmake .. -DCMAKE_PREFIX_PATH="$nanobind_dir" -DBUILD_PYTHON_BINDINGS=ON -DBUILD_TESTING=OFF -DPython_EXECUTABLE="C:\Program Files\KiCad\10.0\bin\python.exe"

if ($LASTEXITCODE -ne 0) {
    Write-Host "CMake configuration failed." -ForegroundColor Red
    Set-Location ..
    exit 1
}

# 3. Build
Write-Host "`nBuilding C++ Kernel (Release)..." -ForegroundColor Yellow
cmake --build . --config Release -j 4

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSUCCESS: C++ Kernel Built successfully!" -ForegroundColor Green
    Write-Host "The spike_core module is now located in the python/ directory." -ForegroundColor Green
} else {
    Write-Host "`nERROR: Build failed." -ForegroundColor Red
}

Set-Location ..
