# SPDX-License-Identifier: Apache-2.0

Set-StrictMode -Version Latest

function Normalize-SpikeSigningThumbprint {
    param([Parameter(Mandatory = $true)][string]$Thumbprint)
    $normalized = ($Thumbprint -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()
    if ($normalized -notmatch '^[0-9A-F]{40}$') {
        throw "The Authenticode certificate thumbprint must contain exactly 40 hexadecimal characters."
    }
    return $normalized
}

function Resolve-SpikeSignTool {
    param([string]$ExplicitPath)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $resolved = Resolve-Path -LiteralPath $ExplicitPath -ErrorAction Stop
        if (-not (Test-Path -LiteralPath $resolved.Path -PathType Leaf) -or
            [System.IO.Path]::GetFileName($resolved.Path) -ine 'signtool.exe') {
            throw "SPIKE_SIGNTOOL_PATH must identify a signtool.exe file."
        }
        return $resolved.Path
    }

    $kitsRoot = $null
    foreach ($registryPath in @(
        'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows Kits\Installed Roots'
    )) {
        if (Test-Path -LiteralPath $registryPath) {
            $candidate = (Get-ItemProperty -LiteralPath $registryPath -Name KitsRoot10 -ErrorAction SilentlyContinue).KitsRoot10
            if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                $kitsRoot = [System.IO.Path]::GetFullPath($candidate)
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($kitsRoot)) {
        throw "Windows SDK KitsRoot10 is unavailable; set SPIKE_SIGNTOOL_PATH to an approved SDK signtool.exe."
    }
    $binRoot = Join-Path $kitsRoot 'bin'
    $candidates = @(Get-ChildItem -LiteralPath $binRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
        Sort-Object { [version]$_.Name } -Descending |
        ForEach-Object { Join-Path $_.FullName 'x64\signtool.exe' } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    if ($candidates.Count -eq 0) {
        throw "No x64 signtool.exe was found in the registered Windows 10/11 SDK."
    }
    return [System.IO.Path]::GetFullPath($candidates[0])
}

function Assert-SpikeTimestampUri {
    param(
        [Parameter(Mandatory = $true)][string]$TimestampUrl,
        [Parameter(Mandatory = $true)][string[]]$AllowedHosts
    )
    $uri = $null
    if (-not [System.Uri]::TryCreate($TimestampUrl, [System.UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or
        -not [string]::IsNullOrEmpty($uri.UserInfo) -or
        $uri.IsDefaultPort -eq $false -or
        $uri.AbsolutePath -notin @('', '/')) {
        throw "The RFC 3161 timestamp URL must be an HTTPS origin without credentials, a custom port, path, query, or fragment."
    }
    $allowed = @($AllowedHosts | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Where-Object { $_ })
    if ($uri.DnsSafeHost.ToLowerInvariant() -notin $allowed) {
        throw "The RFC 3161 timestamp host is not approved by config/windows-signing-policy.json."
    }
    return $uri
}

function Get-SpikeSigningCertificate {
    param(
        [Parameter(Mandatory = $true)][string]$Thumbprint,
        [Parameter(Mandatory = $true)][ValidateSet('CurrentUser', 'LocalMachine')][string]$StoreScope
    )
    $normalized = Normalize-SpikeSigningThumbprint $Thumbprint
    $storePath = "Cert:\$StoreScope\My"
    $matches = @(Get-ChildItem -LiteralPath $storePath -ErrorAction Stop | Where-Object {
        (([string]$_.Thumbprint -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()) -eq $normalized
    })
    if ($matches.Count -ne 1) {
        throw "Exactly one certificate with the configured thumbprint must exist in $storePath."
    }
    $certificate = $matches[0]
    $now = [DateTimeOffset]::UtcNow
    if (-not $certificate.HasPrivateKey) {
        throw "The configured Authenticode certificate has no accessible private key."
    }
    if ($now -lt [DateTimeOffset]$certificate.NotBefore -or $now -gt [DateTimeOffset]$certificate.NotAfter) {
        throw "The configured Authenticode certificate is outside its validity window."
    }
    $codeSigningOid = '1.3.6.1.5.5.7.3.3'
    if (-not @($certificate.EnhancedKeyUsageList | ForEach-Object { $_.ObjectId.Value }).Contains($codeSigningOid)) {
        throw "The configured certificate does not permit code signing."
    }
    return $certificate
}

function Invoke-SpikeAuthenticodeSigning {
    param(
        [Parameter(Mandatory = $true)][string]$SignToolPath,
        [Parameter(Mandatory = $true)][string]$InstallerPath,
        [Parameter(Mandatory = $true)][string]$Thumbprint,
        [Parameter(Mandatory = $true)][ValidateSet('CurrentUser', 'LocalMachine')][string]$StoreScope,
        [Parameter(Mandatory = $true)][System.Uri]$TimestampUri
    )
    $arguments = @('sign', '/sha1', $Thumbprint, '/s', 'My')
    if ($StoreScope -eq 'LocalMachine') { $arguments += '/sm' }
    $arguments += @('/fd', 'SHA256', '/tr', $TimestampUri.AbsoluteUri, '/td', 'SHA256', $InstallerPath)
    & $SignToolPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed for $([System.IO.Path]::GetFileName($InstallerPath))."
    }
}

function Get-SpikeAuthenticodeMetadata {
    param(
        [Parameter(Mandatory = $true)][string]$SignToolPath,
        [Parameter(Mandatory = $true)][string]$InstallerPath,
        [Parameter(Mandatory = $true)][string]$ExpectedThumbprint
    )
    & $SignToolPath verify /pa /all /v $InstallerPath
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode policy verification failed for $([System.IO.Path]::GetFileName($InstallerPath))."
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $InstallerPath
    $actualThumbprint = if ($signature.SignerCertificate) {
        Normalize-SpikeSigningThumbprint ([string]$signature.SignerCertificate.Thumbprint)
    } else { '' }
    $expected = Normalize-SpikeSigningThumbprint $ExpectedThumbprint
    if ($signature.Status -ne 'Valid' -or $actualThumbprint -ne $expected) {
        throw "The verified Authenticode signer does not match the configured certificate."
    }
    if (-not $signature.TimeStamperCertificate) {
        throw "The Authenticode signature has no verified RFC 3161 timestamp certificate."
    }
    return [ordered]@{
        status = 'Valid'
        file_digest_algorithm = 'sha256'
        signer_thumbprint = $actualThumbprint
        signer_subject = [string]$signature.SignerCertificate.Subject
        timestamp_protocol = 'rfc3161'
        timestamp_authority_thumbprint = Normalize-SpikeSigningThumbprint ([string]$signature.TimeStamperCertificate.Thumbprint)
        timestamp_authority_subject = [string]$signature.TimeStamperCertificate.Subject
    }
}
