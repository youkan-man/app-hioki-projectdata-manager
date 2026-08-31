[CmdletBinding()]
param(
    [string]$IpAddress,
    [string[]]$DnsName = @("localhost"),
    [int]$Days = 825
)

$ErrorActionPreference = "Stop"
$certificateDirectory = Join-Path $PSScriptRoot "..\.certs"
New-Item -ItemType Directory -Force -Path $certificateDirectory | Out-Null

$sanEntries = @()
if ($IpAddress) {
    $parsedAddress = $null
    if (-not [System.Net.IPAddress]::TryParse($IpAddress, [ref]$parsedAddress)) {
        throw "Invalid IP address: $IpAddress"
    }
    $sanEntries += "IP:$IpAddress"
}
$sanEntries += $DnsName | Where-Object { $_ } | ForEach-Object { "DNS:$_" }
if ($sanEntries.Count -eq 0) {
    throw "Specify -IpAddress or at least one -DnsName."
}
$commonName = if ($IpAddress) { $IpAddress } else { $DnsName[0] }
$subjectAlternativeName = $sanEntries -join ","

docker run --rm `
    -v "${certificateDirectory}:/certs" `
    alpine/openssl req -x509 -newkey rsa:2048 -nodes `
    -keyout /certs/tls.key -out /certs/tls.crt -days $Days `
    -subj "/CN=$commonName" -addext "subjectAltName=$subjectAlternativeName"

if ($LASTEXITCODE -ne 0) {
    throw "Certificate generation failed."
}

Write-Host "Created .certs/tls.crt and .certs/tls.key for $subjectAlternativeName"
