[CmdletBinding()]
param(
    [string]$DnsName = "localhost",
    [int]$Days = 825
)

$ErrorActionPreference = "Stop"
$certificateDirectory = Join-Path $PSScriptRoot "..\.certs"
New-Item -ItemType Directory -Force -Path $certificateDirectory | Out-Null

docker run --rm `
    -v "${certificateDirectory}:/certs" `
    alpine/openssl req -x509 -newkey rsa:2048 -nodes `
    -keyout /certs/tls.key -out /certs/tls.crt -days $Days `
    -subj "/CN=$DnsName" -addext "subjectAltName=DNS:$DnsName"

if ($LASTEXITCODE -ne 0) {
    throw "Certificate generation failed."
}

Write-Host "Created .certs/tls.crt and .certs/tls.key for $DnsName"

