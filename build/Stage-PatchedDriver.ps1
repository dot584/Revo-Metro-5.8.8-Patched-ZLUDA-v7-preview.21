$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$baseline = Join-Path $project 'artifacts/zluda-v7-preview.21/zluda'
$release = Join-Path $project 'artifacts/target/release'
foreach ($file in 'nvcuda.dll', 'zluda_trace.dll') {
    if (-not (Test-Path -LiteralPath (Join-Path $release $file) -PathType Leaf)) {
        throw "Missing built DLL $file. Run Build-PatchedDriver.ps1 first."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $baseline 'zluda.exe') -PathType Leaf)) {
    throw 'Missing verified reference package. Run setup/Get-ZludaRelease.ps1 first.'
}
$tag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$package = Join-Path $project "artifacts/zluda-patched-$tag"
Copy-Item -LiteralPath $baseline -Destination $package -Recurse
Copy-Item -LiteralPath (Join-Path $release 'nvcuda.dll') -Destination $package -Force
Copy-Item -LiteralPath (Join-Path $release 'zluda_trace.dll') -Destination (Join-Path $package 'trace/nvcuda.dll') -Force
Copy-Item -LiteralPath (Join-Path $project 'upstream/ZLUDA/LICENSE-MIT'),(Join-Path $project 'upstream/ZLUDA/LICENSE-APACHE') -Destination $package
Get-FileHash -LiteralPath (Join-Path $package 'nvcuda.dll'),(Join-Path $package 'trace/nvcuda.dll') |
    ForEach-Object { "$($_.Hash)  $([IO.Path]::GetRelativePath($package, $_.Path))" } |
    Set-Content -LiteralPath (Join-Path $package 'SHA256SUMS.txt')
$package
