# SPDX-License-Identifier: MIT

Set-StrictMode -Version Latest

function New-SpikeDetachedCmsSignature {
    param(
        [Parameter(Mandatory = $true)][string]$ContentPath,
        [Parameter(Mandatory = $true)][string]$SignaturePath,
        [Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )
    if (-not (Test-Path -LiteralPath $ContentPath -PathType Leaf)) {
        throw "CMS content file does not exist: $ContentPath"
    }
    if (-not $Certificate.HasPrivateKey) {
        throw "The CMS signing certificate has no accessible private key."
    }
    Add-Type -AssemblyName System.Security
    $content = [System.IO.File]::ReadAllBytes([System.IO.Path]::GetFullPath($ContentPath))
    $signedCms = [System.Security.Cryptography.Pkcs.SignedCms]::new(
        [System.Security.Cryptography.Pkcs.ContentInfo]::new($content), $true
    )
    $signer = [System.Security.Cryptography.Pkcs.CmsSigner]::new($Certificate)
    $signer.IncludeOption = [System.Security.Cryptography.X509Certificates.X509IncludeOption]::EndCertOnly
    $signer.DigestAlgorithm = [System.Security.Cryptography.Oid]::new('2.16.840.1.101.3.4.2.1')
    $signedCms.ComputeSignature($signer, $false)
    $destination = [System.IO.Path]::GetFullPath($SignaturePath)
    $parent = [System.IO.Path]::GetDirectoryName($destination)
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::WriteAllBytes($destination, $signedCms.Encode())
    return Get-SpikeDetachedCmsMetadata $ContentPath $destination $Certificate.Thumbprint
}

function Get-SpikeDetachedCmsMetadata {
    param(
        [Parameter(Mandatory = $true)][string]$ContentPath,
        [Parameter(Mandatory = $true)][string]$SignaturePath,
        [Parameter(Mandatory = $true)][string]$ExpectedThumbprint
    )
    if (-not (Test-Path -LiteralPath $ContentPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SignaturePath -PathType Leaf)) {
        throw "Detached CMS verification requires both content and signature files."
    }
    Add-Type -AssemblyName System.Security
    $content = [System.IO.File]::ReadAllBytes([System.IO.Path]::GetFullPath($ContentPath))
    $encoded = [System.IO.File]::ReadAllBytes([System.IO.Path]::GetFullPath($SignaturePath))
    $signedCms = [System.Security.Cryptography.Pkcs.SignedCms]::new(
        [System.Security.Cryptography.Pkcs.ContentInfo]::new($content), $true
    )
    try {
        $signedCms.Decode($encoded)
        $signedCms.CheckSignature($true)
    }
    catch {
        throw "Detached CMS signature verification failed: $($_.Exception.Message)"
    }
    if ($signedCms.Detached -ne $true -or $signedCms.SignerInfos.Count -ne 1) {
        throw "Detached CMS evidence must contain exactly one signer."
    }
    $signer = $signedCms.SignerInfos[0]
    $actual = (($signer.Certificate.Thumbprint -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
    $expected = (($ExpectedThumbprint -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
    if ($expected -notmatch '^[0-9A-F]{40}$' -or $actual -ne $expected) {
        throw "Detached CMS signer does not match the expected release certificate."
    }
    if ($signer.DigestAlgorithm.Value -ne '2.16.840.1.101.3.4.2.1') {
        throw "Detached CMS signature must use SHA-256."
    }
    return [ordered]@{
        contract = 'spike/detached-cms-metadata/v1'
        status = 'Valid'
        detached = $true
        digest_algorithm = 'sha256'
        signer_thumbprint = $actual
        signer_subject = [string]$signer.Certificate.Subject
        signature_sha256 = (Get-FileHash -LiteralPath $SignaturePath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
