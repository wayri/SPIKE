# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$app = Join-Path $root "app"
$python = (Get-Command python -ErrorAction Stop).Source

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )
    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "$FilePath failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Remove-OwnedDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = [System.IO.Path]::GetFullPath($Path)
    $expectedParent = [System.IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($expectedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a directory outside the repository: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

$version = [string]((Get-Content -LiteralPath (Join-Path $app "package.json") -Raw | ConvertFrom-Json).version)
if ([string]::IsNullOrWhiteSpace($version)) {
    throw "app/package.json does not define a release version."
}

$profileRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUTF8 = "1"
$env:CARGO_PROFILE_RELEASE_STRIP = "symbols"
$env:RUSTFLAGS = "--remap-path-prefix=$root=C:\build\spike --remap-path-prefix=$profileRoot=C:\build\user"
$env:CL = "/pathmap:$root=C:\build\spike /pathmap:$profileRoot=C:\build\user"

Invoke-Checked $python @("-m", "unittest", "tests.python.test_windows_desktop_path", "-v") $root

# Install runtime wheels before the hash-locked build tooling. The packaged-worker
# builder checks every Windows build-tool version against this lock.
Invoke-Checked $python @(
    "-m", "pip", "install", "--disable-pip-version-check",
    "numpy", "scipy", "shapely", "matplotlib", "mplcursors", "reportlab",
    "nanobind", "jsonschema==4.25.1"
) $root
Invoke-Checked $python @(
    "-m", "pip", "install", "--disable-pip-version-check", "--require-hashes",
    "-r", "requirements-build-windows-x64.txt"
) $root

$eigenSource = Join-Path $root "build\eigen-source"
$eigenBuild = Join-Path $root "build\eigen-config"
$eigenInstall = Join-Path $root "build\eigen"
$eigenCommit = "3147391d946bb4b6c68edd901f2add6ac1f31f8c"
Remove-OwnedDirectory $eigenSource
Remove-OwnedDirectory $eigenBuild
Remove-OwnedDirectory $eigenInstall
Invoke-Checked "git" @(
    "clone", "--depth", "1", "--branch", "3.4.0",
    "https://gitlab.com/libeigen/eigen.git", $eigenSource
) $root
$actualEigenCommit = (& git -C $eigenSource rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualEigenCommit -ne $eigenCommit) {
    throw "Eigen 3.4.0 resolved to $actualEigenCommit instead of pinned commit $eigenCommit."
}
Invoke-Checked "cmake" @(
    "-S", $eigenSource, "-B", $eigenBuild, "-G", "Ninja",
    "-DBUILD_TESTING=OFF", "-DEIGEN_BUILD_DOC=OFF",
    "-DCMAKE_Fortran_COMPILER=NOTFOUND",
    "-DCMAKE_INSTALL_PREFIX=$eigenInstall"
) $root
Invoke-Checked "cmake" @("--install", $eigenBuild) $root

$nativeBuild = Join-Path $root "build-spikes-hybrid"
Remove-OwnedDirectory $nativeBuild
$nanobindDir = (& $python -m nanobind --cmake_dir).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($nanobindDir)) {
    throw "Could not resolve the installed nanobind CMake directory."
}
Invoke-Checked "cmake" @(
    "-S", $root, "-B", $nativeBuild, "-G", "Ninja",
    "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_PYTHON_BINDINGS=ON",
    "-DSPIKE_PORTABLE_BUILD=ON", "-DCMAKE_PREFIX_PATH=$eigenInstall",
    "-DPython_EXECUTABLE=$python", "-Dnanobind_DIR=$nanobindDir"
) $root
Invoke-Checked "cmake" @(
    "--build", $nativeBuild, "--target", "spike_peec_native", "spikes_c_api",
    "--parallel", "2"
) $root

Invoke-Checked $python @("scripts/build_packaged_worker.py") $root
Invoke-Checked "cargo" @("test", "--manifest-path", "app/src-tauri/Cargo.toml", "--lib") $root
$frozenWorker = Join-Path $root "app\src-tauri\resources\worker\spike-worker\spike-worker.exe"
if (-not (Test-Path -LiteralPath $frozenWorker -PathType Leaf)) {
    throw "The packaged worker was not produced at $frozenWorker"
}
Invoke-Checked $python @("scripts/verify_packaged_cli.py", "--", $frozenWorker, "--cli") $root

Invoke-Checked "npm.cmd" @("ci") $app
Invoke-Checked "npm.cmd" @("run", "build") $app
Invoke-Checked $python @("scripts/prepare_release_resources.py", "--config-output", "build/tauri.release.json") $root
# --config merges resource maps, which would reintroduce unstaged source trees.
# Replace the base config only for bundling and restore its exact source bytes.
$tauriConfig = Join-Path $app "src-tauri\tauri.conf.json"
$sourceConfigBytes = [System.IO.File]::ReadAllBytes($tauriConfig)
try {
    Copy-Item -LiteralPath (Join-Path $root "build\tauri.release.json") -Destination $tauriConfig -Force
    Invoke-Checked "npm.cmd" @("run", "tauri", "build", "--", "--bundles", "nsis") $app
}
finally {
    [System.IO.File]::WriteAllBytes($tauriConfig, $sourceConfigBytes)
}

$bundleRoot = Join-Path $app "src-tauri\target\release\bundle\nsis"
$installers = @(Get-ChildItem -LiteralPath $bundleRoot -Filter "*.exe" -File)
if ($installers.Count -ne 1) {
    throw "Expected exactly one NSIS installer in $bundleRoot; found $($installers.Count)."
}

# NSIS MultiUser resets /D during initialization. Test its supported per-user
# install mode and discover the actual location recorded by the installer.
$installerProcess = Start-Process -FilePath $installers[0].FullName `
    -ArgumentList @("/S", "/CurrentUser", "/NS") -WindowStyle Hidden -Wait -PassThru
if ($installerProcess.ExitCode -ne 0) {
    throw "Silent NSIS installation failed with exit code $($installerProcess.ExitCode)."
}
$installedEntries = @(Get-ChildItem -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" |
    Get-ItemProperty | Where-Object {
        $_.PSObject.Properties["DisplayName"] -and $_.DisplayName -eq "SPIKE" -and
        $_.PSObject.Properties["DisplayVersion"] -and $_.DisplayVersion -eq $version
    })
if ($installedEntries.Count -ne 1) {
    throw "Expected one registered SPIKE $version installation; found $($installedEntries.Count)."
}
$installRoot = [System.IO.Path]::GetFullPath($installedEntries[0].InstallLocation.Trim('"'))
Write-Output "Checking installed package at $installRoot"

# Reinstall the same candidate to exercise the installer update path.
$reinstall = Start-Process -FilePath $installers[0].FullName `
    -ArgumentList @("/S", "/CurrentUser", "/NS") -WindowStyle Hidden -Wait -PassThru
if ($reinstall.ExitCode -ne 0) {
    throw "NSIS reinstall failed with exit code $($reinstall.ExitCode)."
}

$installedLauncher = Join-Path $installRoot "spike.cmd"
if (-not (Test-Path -LiteralPath $installedLauncher -PathType Leaf)) {
    throw "The installed SPIKE CLI launcher is missing: $installedLauncher"
}
Invoke-Checked $python @(
    "scripts/verify_packaged_cli.py", "--", "cmd.exe", "/d", "/c", $installedLauncher
) $root

Invoke-Checked $python @(
    "scripts/verify_installed_python_runtime.py",
    "--installed-root", $installRoot,
    "--worker", (Join-Path $installRoot "bundled\spike-worker\spike-worker.exe"),
    "--python-executable", $python
) $root

. (Join-Path $PSScriptRoot "windows_desktop_path.ps1")
$desktopPath = Get-SpikeInstalledDesktopPath -InstallRoot $installRoot
$desktop = Start-Process -FilePath $desktopPath -WindowStyle Hidden -PassThru
try {
    Start-Sleep -Seconds 10
    if ($desktop.HasExited) {
        throw "Installed SPIKE desktop exited during the 10-second startup smoke check (exit code $($desktop.ExitCode))."
    }
    # Exercise the real title-bar close path. A forced stop cannot qualify shutdown.
    if (-not $desktop.CloseMainWindow()) {
        throw "Installed SPIKE did not accept its native main-window close request."
    }
    if (-not $desktop.WaitForExit(10000)) {
        throw "Installed SPIKE remained running more than 10 seconds after closing its main window."
    }
    if ($desktop.ExitCode -ne 0) {
        throw "Installed SPIKE close failed with exit code $($desktop.ExitCode)."
    }
}
finally {
    if (-not $desktop.HasExited) {
        Stop-Process -Id $desktop.Id -Force
        $desktop.WaitForExit()
    }
}

$uninstaller = Join-Path $installRoot "uninstall.exe"
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/S", "/CurrentUser") `
    -WindowStyle Hidden -Wait -PassThru
if ($uninstall.ExitCode -ne 0) {
    throw "NSIS uninstall failed with exit code $($uninstall.ExitCode)."
}
# NSIS runs its uninstaller from a temporary copy, so wait for its child cleanup.
$uninstallDeadline = [DateTime]::UtcNow.AddSeconds(30)
while ((Test-Path -LiteralPath $installedLauncher) -and [DateTime]::UtcNow -lt $uninstallDeadline) {
    Start-Sleep -Seconds 1
}
if (Test-Path -LiteralPath $installedLauncher) {
    throw "The CLI launcher remains after uninstall."
}

$output = Join-Path $root "dist-release"
if (Test-Path -LiteralPath $output) {
    Remove-OwnedDirectory $output
}
New-Item -ItemType Directory -Path $output -Force | Out-Null
$artifact = Join-Path $output "SPIKE_${version}_x64-setup.exe"
Copy-Item -LiteralPath $installers[0].FullName -Destination $artifact
$digest = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText(
    "$artifact.sha256", "$digest  $([System.IO.Path]::GetFileName($artifact))`n",
    [System.Text.UTF8Encoding]::new($false)
)
Write-Output "Verified Windows installer: $artifact"
