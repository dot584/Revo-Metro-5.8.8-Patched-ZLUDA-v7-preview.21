param(
    [string]$RevoExe = (Join-Path $env:ProgramFiles 'Revo Metro/RevoMetro.exe'),
    [string]$ZludaDir = (Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts/zluda-v7-preview.21/zluda'),
    [switch]$NoTrace
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion -lt [version]'7.3') {
    throw 'Use PowerShell 7.3 or newer so ZLUDA receives the quoted executable path intact.'
}
$project = Split-Path -Parent $PSScriptRoot
$exe = (Resolve-Path -LiteralPath $RevoExe).Path
$zluda = (Resolve-Path -LiteralPath (Join-Path $ZludaDir 'zluda.exe')).Path
$ZludaDir = Split-Path -Parent $zluda
if (Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($exe)) -ErrorAction SilentlyContinue) {
    throw 'Close all Revo Metro windows before starting the traced run.'
}
$mode = if ($NoTrace) { 'gpu' } else { 'trace' }
$runName = "revo-$mode-" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
$run = (New-Item -ItemType Directory -Path (Join-Path $project "logs/$runName") -Force).FullName
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldLogDir = $env:ZLUDA_LOG_DIR
$oldCudaLib = $env:ZLUDA_CUDA_LIB
$PSNativeCommandArgumentPassing = 'Standard'
# This ZLUDA release concatenates child arguments without adding quotes.
$quotedExe = '"' + $exe + '"'
$version = (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion
@("Started: $(Get-Date -Format o)", "Mode: $mode", "Revo Metro: $version",
    "ZLUDA launcher SHA-256: $((Get-FileHash -LiteralPath $zluda).Hash)") |
    Set-Content -LiteralPath (Join-Path $run 'session.txt')
Write-Host "Trace folder: $run"

Push-Location -LiteralPath (Split-Path -Parent $exe)
try {
    $env:TEMP = $run
    $env:TMP = $run
    $launcherArgs = @()
    if (-not $NoTrace) {
        # Full tracing can fail within cufftExecC2C. Trace the Driver API
        # while retaining the normal ZLUDA libraries for everything else.
        $env:ZLUDA_LOG_DIR = $run
        $env:ZLUDA_CUDA_LIB = Join-Path $ZludaDir 'nvcuda.dll'
        $launcherArgs += @('--nvcuda', (Join-Path $ZludaDir 'trace/nvcuda.dll'))
        $launcherArgs += @('--cufft11', (Join-Path $ZludaDir 'cufft64_11.dll'))
    }
    & $zluda @launcherArgs -- $quotedExe 2>&1 | Tee-Object -FilePath (Join-Path $run 'launcher.txt')
    $result = $LASTEXITCODE
    "Exit code: $result" | Add-Content -LiteralPath (Join-Path $run 'session.txt')
}
finally {
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:ZLUDA_LOG_DIR = $oldLogDir
    $env:ZLUDA_CUDA_LIB = $oldCudaLib
    Pop-Location
}

$traces = Get-ChildItem -LiteralPath $run -Filter 'log.txt' -Recurse -File
$traces | ForEach-Object { Write-Host "CUDA trace: $($_.FullName)" }
if ($result -ne 0) { throw "ZLUDA/Revo Metro exited with code $result. See $run." }
if (-not $NoTrace -and -not $traces) { Write-Warning "No CUDA call log was created. See $run\launcher.txt." }
