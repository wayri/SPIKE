[CmdletBinding()]
param(
    [ValidateSet("x64")]
    [string]$Architecture = "x64"
)

$ErrorActionPreference = "Stop"

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$release = Join-Path $root "app\src-tauri\target\release"
$configPath = Join-Path $root "app\src-tauri\tauri.conf.json"
$artifactsRoot = [System.IO.Path]::GetFullPath((Join-Path $root "artifacts\windows"))
$version = (Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json).version
$packageName = "SPIKE-$version-windows-$Architecture-portable"
$packageDir = [System.IO.Path]::GetFullPath((Join-Path $artifactsRoot $packageName))
$zipPath = [System.IO.Path]::GetFullPath((Join-Path $artifactsRoot "$packageName.zip"))

function Assert-ChildPath {
    param([string]$Candidate, [string]$Parent)
    $prefix = $Parent.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $Candidate.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify path outside $Parent`: $Candidate"
    }
}

Assert-ChildPath -Candidate $packageDir -Parent $artifactsRoot
Assert-ChildPath -Candidate $zipPath -Parent $artifactsRoot

$required = @(
    (Join-Path $release "spike-desktop.exe"),
    (Join-Path $release "dependencies.lock.json"),
    (Join-Path $release "README.md"),
    (Join-Path $release "bundled"),
    (Join-Path $release "python")
)
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing release resource: $path. Run the packaged-worker and Tauri release builds first."
    }
}

New-Item -ItemType Directory -Path $artifactsRoot -Force | Out-Null
if (Test-Path -LiteralPath $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
New-Item -ItemType Directory -Path $packageDir | Out-Null

Copy-Item -LiteralPath (Join-Path $release "spike-desktop.exe") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $release "dependencies.lock.json") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $release "README.md") -Destination (Join-Path $packageDir "RUNTIME-README.md")
Copy-Item -LiteralPath (Join-Path $release "bundled") -Destination $packageDir -Recurse
Copy-Item -LiteralPath (Join-Path $release "python") -Destination $packageDir -Recurse
Copy-Item -LiteralPath (Join-Path $root "docs\PORTABLE_WINDOWS.md") -Destination (Join-Path $packageDir "README.md")

$files = Get-ChildItem -LiteralPath $packageDir -Recurse -File | Sort-Object FullName
$manifestFiles = foreach ($file in $files) {
    Assert-ChildPath -Candidate $file.FullName -Parent $packageDir
    $relativePath = $file.FullName.Substring($packageDir.Length).TrimStart([char[]]@('\', '/')).Replace([char]'\', [char]'/')
    [ordered]@{
        path = $relativePath
        size = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest = [ordered]@{
    contract = "spike/portable-manifest/v1"
    product = "SPIKE"
    version = $version
    architecture = $Architecture
    generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    files = $manifestFiles
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $packageDir "portable.manifest.json") -Encoding utf8

Compress-Archive -LiteralPath $packageDir -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "Portable directory: $packageDir"
Write-Output "Portable archive: $zipPath"
Write-Output "Archive SHA-256: $zipHash"
