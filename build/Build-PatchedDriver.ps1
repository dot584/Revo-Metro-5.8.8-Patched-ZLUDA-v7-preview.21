param(
    [string]$Source = (Join-Path (Split-Path -Parent $PSScriptRoot) 'upstream/ZLUDA'),
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$env:RUSTUP_HOME = Join-Path $project 'artifacts/toolchain/rustup'
$env:CARGO_HOME = Join-Path $project 'artifacts/toolchain/cargo'
$env:CARGO_TARGET_DIR = Join-Path $project 'artifacts/target'
$env:TEMP = (New-Item -ItemType Directory -Force (Join-Path $project 'artifacts/build-temp')).FullName
$env:TMP = $env:TEMP
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Install the Visual Studio x64 C++ build tools and Windows SDK.' }
Import-Module "$vs/Common7/Tools/Microsoft.VisualStudio.DevShell.dll"
Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
$cmake = "$vs/Common7/IDE/CommonExtensions/Microsoft/CMake"
$env:Path = "$env:CARGO_HOME/bin;$cmake/CMake/bin;$cmake/Ninja;$env:Path"
$env:CARGO_BUILD_JOBS = '8'
$env:CMAKE_BUILD_PARALLEL_LEVEL = '8'
$cargo = Join-Path $env:CARGO_HOME 'bin/cargo.exe'
if (-not (Test-Path -LiteralPath $cargo -PathType Leaf)) {
    throw 'The workspace Rust toolchain is missing. See docs/WORKFLOW.md.'
}
$flags = @()
if ($Offline) { $flags += '--offline' }
$logDir = (New-Item -ItemType Directory -Force (Join-Path $project 'logs')).FullName

Push-Location -LiteralPath $Source
try {
    # Use source-derived cache identity even when building uncommitted changes.
    $sourceFiles = @(
        'ptx_parser/src/lib.rs', 'ptx_parser/src/ast.rs', 'ptx/src/lib.rs',
        'ptx/src/pass/mod.rs', 'ptx/src/pass/llvm/emit.rs',
        'ptx/src/pass/remove_unreachable_basic_blocks.rs', 'llvm_zluda/src/utils.rs',
        'ptx/src/pass/instruction_mode_to_global_mode/mod.rs',
        'zluda/src/impl/module.rs', 'zluda_common/src/lib.rs'
    )
    $hashes = (Get-FileHash -LiteralPath $sourceFiles).Hash -join ''
    $hashBytes = [Text.Encoding]::ASCII.GetBytes($hashes)
    $env:VERGEN_GIT_SHA = 'revo-' + [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData($hashBytes)
    ).ToLowerInvariant()
    & $cargo build @flags --locked --release -p zluda -p zluda_trace 2>&1 |
        Tee-Object -FilePath (Join-Path $logDir 'patched-build.txt')
    if ($LASTEXITCODE -ne 0) { throw "ZLUDA build failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}
