[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CertificatePath,
    [switch]$LocalMachine,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "This script must be run on Windows."
}

$resolvedPath = (Resolve-Path -LiteralPath $CertificatePath).Path
$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($resolvedPath)

if ($certificate.HasPrivateKey) {
    throw "Refusing to trust a certificate file that contains a private key. Copy tls.crt only."
}

$storeLocation = if ($LocalMachine) { "Cert:\LocalMachine\Root" } else { "Cert:\CurrentUser\Root" }
$message = "Trust '$($certificate.Subject)' ($($certificate.Thumbprint)) in $storeLocation?"

if (-not $Force -and -not $PSCmdlet.ShouldContinue($message, "Install development root certificate")) {
    Write-Host "Cancelled."
    exit 0
}

$result = Import-Certificate -FilePath $resolvedPath -CertStoreLocation $storeLocation
Write-Host "Trusted certificate: $($result.Thumbprint)"
Write-Host "Remove it later with: Remove-Item '$storeLocation\$($result.Thumbprint)'"
