# Download the pinned Windows package and check GitHub's published SHA-256.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$root = Join-Path $project 'artifacts'
$tag = 'v7-preview.21'
$file = 'zluda-windows-eb89ae3.zip'
$expectedHash = 'ebb7e53f2c1f45dc70172fde68ceb83115f1817d7709437e6afeff6fa0b43482'
$archive = Join-Path $root $file
$destination = Join-Path $root "zluda-$tag"
New-Item -ItemType Directory -Force -Path $root | Out-Null

if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    $partial = "$archive.part"
    curl.exe --fail --silent --show-error --location --connect-timeout 10 --max-time 180 `
        --output $partial "https://github.com/vosen/ZLUDA/releases/download/$tag/$file"
    if ($LASTEXITCODE -ne 0) { throw "ZLUDA download failed with exit code $LASTEXITCODE." }
    if ((Get-FileHash -LiteralPath $partial).Hash -ne $expectedHash) {
        throw "Checksum mismatch for $partial."
    }
    Move-Item -LiteralPath $partial -Destination $archive
}
if ((Get-FileHash -LiteralPath $archive).Hash -ne $expectedHash) {
    throw "Checksum mismatch for $archive."
}
if (-not (Test-Path -LiteralPath (Join-Path $destination 'zluda/zluda.exe') -PathType Leaf)) {
    Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
}
Write-Output (Join-Path $destination 'zluda')
