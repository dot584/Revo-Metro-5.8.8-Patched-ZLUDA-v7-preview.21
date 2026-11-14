param(
    [string]$Source = (Join-Path (Split-Path -Parent $PSScriptRoot) 'upstream/ZLUDA')
)

$ErrorActionPreference = 'Stop'
foreach ($program in 'git', 'cargo', 'rustc', 'cmake') {
    if (-not (Get-Command $program -ErrorAction SilentlyContinue)) {
        throw "Missing $program on PATH. See docs/WORKFLOW.md for build prerequisites."
    }
}
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
if (-not (Test-Path -LiteralPath (Join-Path $sourcePath 'ext/llvm-project/llvm/CMakeLists.txt')) -or
    -not (Test-Path -LiteralPath (Join-Path $sourcePath 'ext/HiGHS/CMakeLists.txt'))) {
    throw 'Required submodules are missing. Run git submodule update --init --recursive in the source checkout.'
}
Push-Location -LiteralPath $sourcePath
try {
    cargo xtask --release
    if ($LASTEXITCODE -ne 0) { throw "ZLUDA source build failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}
