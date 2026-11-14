param(
    [string]$RevoExe = (Join-Path $env:ProgramFiles 'Revo Metro/RevoMetro.exe'),
    [string]$ZludaDir = (Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts/zluda-v7-preview.21/zluda'),
    [switch]$NoTrace,
    [switch]$CheckLibraries,
    [switch]$CaptureCrash
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion -lt [version]'7.3') {
    throw 'Use PowerShell 7.3 or newer so ZLUDA receives the quoted executable path intact.'
}
$project = Split-Path -Parent $PSScriptRoot
if ($CaptureCrash -and $CheckLibraries) {
    throw 'Crash capture targets Revo Metro. Run the library check separately.'
}
$zluda = (Resolve-Path -LiteralPath (Join-Path $ZludaDir 'zluda.exe')).Path
$ZludaDir = Split-Path -Parent $zluda
$target = if ($CheckLibraries) { Join-Path $ZludaDir 'cuda_check.exe' } else { $RevoExe }
$exe = (Resolve-Path -LiteralPath $target).Path
$image = [IO.Path]::GetFileName($exe)
if (Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($exe)) -ErrorAction SilentlyContinue) {
    throw 'Close all Revo Metro windows before starting the traced run.'
}
$mode = if ($NoTrace) { 'gpu' } else { 'trace' }
$prefix = if ($CheckLibraries) { 'library-check' } else { 'revo' }
$runName = "$prefix-$mode-" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
$run = (New-Item -ItemType Directory -Path (Join-Path $project "logs/$runName") -Force).FullName
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldLogDir = $env:ZLUDA_LOG_DIR
$oldCudaLib = $env:ZLUDA_CUDA_LIB
$PSNativeCommandArgumentPassing = 'Standard'
# This ZLUDA release concatenates child arguments without adding quotes.
$quotedExe = '"' + $exe + '"'
$version = (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion
@("Started: $(Get-Date -Format o)", "Mode: $mode", "Executable: $([IO.Path]::GetFileName($exe)) $version",
    "ZLUDA launcher SHA-256: $((Get-FileHash -LiteralPath $zluda).Hash)") |
    Set-Content -LiteralPath (Join-Path $run 'session.txt')
Write-Host "Trace folder: $run"

$monitor = $null
Push-Location -LiteralPath (Split-Path -Parent $exe)
try {
    $env:TEMP = $run
    $env:TMP = $run
    if ($CaptureCrash) {
        $procDump = Join-Path $project 'artifacts/procdump/procdump64.exe'
        if (-not (Test-Path -LiteralPath $procDump -PathType Leaf)) {
            throw "Microsoft ProcDump is missing at $procDump."
        }
        $dump = Join-Path $run 'RevoMetro-crash.dmp'
        # Wait for the ZLUDA-launched process and capture its unhandled exception.
        $monitor = Start-Process -FilePath $procDump -WindowStyle Hidden -PassThru `
            -ArgumentList "-accepteula -mm -e -w `"$image`" `"$dump`"" `
            -RedirectStandardOutput (Join-Path $run 'procdump.txt') `
            -RedirectStandardError (Join-Path $run 'procdump-errors.txt')
        Start-Sleep -Milliseconds 750
        if ($monitor.HasExited) { throw "ProcDump exited before launch. See $run\procdump.txt." }
        Write-Host "Native crash capture armed: $dump"
    }
    $launcherArgs = @()
    if (-not $NoTrace) {
        # Full tracing can fail within cufftExecC2C. Trace the Driver API
        # while retaining the normal ZLUDA libraries for everything else.
        $env:ZLUDA_LOG_DIR = $run
        $env:ZLUDA_CUDA_LIB = Join-Path $ZludaDir 'nvcuda.dll'
        $launcherArgs += @('--nvcuda', (Join-Path $ZludaDir 'trace/nvcuda.dll'))
        $launcherArgs += @('--cufft11', (Join-Path $ZludaDir 'cufft64_11.dll'))
    }
    $childArgs = if ($CheckLibraries) { @('--nvcuda', '--cufft11', '--driver-first') }
    & $zluda @launcherArgs -- $quotedExe @childArgs 2>&1 | Tee-Object -FilePath (Join-Path $run 'launcher.txt')
    $result = $LASTEXITCODE
    "Exit code: $result" | Add-Content -LiteralPath (Join-Path $run 'session.txt')
}
finally {
    if ($monitor -and -not $monitor.WaitForExit(10000)) {
        $monitor.Kill()
        $monitor.WaitForExit()
    }
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:ZLUDA_LOG_DIR = $oldLogDir
    $env:ZLUDA_CUDA_LIB = $oldCudaLib
    Pop-Location
}

if ($CaptureCrash) {
    if (Test-Path -LiteralPath $dump -PathType Leaf) {
        Write-Host "Native crash dump: $dump"
    } else {
        Write-Warning "ProcDump did not produce a dump. See $run\procdump.txt."
    }
}

$traces = Get-ChildItem -LiteralPath $run -Filter 'log.txt' -Recurse -File
$traces | ForEach-Object { Write-Host "CUDA trace: $($_.FullName)" }
if ($result -ne 0) { throw "The launched process exited with code $result. See $run." }
if (-not $NoTrace -and -not $traces) { Write-Warning "No CUDA call log was created. See $run\launcher.txt." }
