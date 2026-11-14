@echo off
setlocal
set "ZLUDA_DIR="
if exist "%~dp0zluda\zluda.exe" (
    set "ZLUDA_DIR=%~dp0zluda"
) else (
    for /f "delims=" %%D in ('dir /b /ad /o-n "%~dp0artifacts\zluda-patched-*" 2^>nul') do (
        if not defined ZLUDA_DIR if exist "%~dp0artifacts\%%D\zluda.exe" set "ZLUDA_DIR=%~dp0artifacts\%%D"
    )
)

set "REVO_EXE=%REVO_METRO_EXE%"
if not defined REVO_EXE set "REVO_EXE=C:\Program Files\Revo Metro\RevoMetro.exe"
for %%F in ("%REVO_EXE%") do set "REVO_DIR=%%~dpF"
set "REVO_DIR=%REVO_DIR:~0,-1%"

if not defined ZLUDA_DIR (
    echo Patched ZLUDA not found.
    echo Place a prebuilt release in "%~dp0zluda\" or build one into "%~dp0artifacts\zluda-patched-*\".
    pause
    exit /b 1
)
if not exist "%REVO_EXE%" (
    echo Revo Metro not found at "%REVO_EXE%".
    echo Install Revo Metro or set REVO_METRO_EXE before running this launcher.
    pause
    exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%I"
set "ZLUDA_LOG_DIR=%~dp0logs\revo-trace-%STAMP%"
set "ZLUDA_CUDA_LIB=%ZLUDA_DIR%\nvcuda.dll"
mkdir "%ZLUDA_LOG_DIR%" >nul 2>&1

echo Using ZLUDA: "%ZLUDA_DIR%"
echo Tracing CUDA Driver API calls to: "%ZLUDA_LOG_DIR%"
echo Note: Debug tracing writes large logs and reduces live frame rate.
start "" /D "%REVO_DIR%" "%ZLUDA_DIR%\zluda.exe" --nvcuda "%ZLUDA_DIR%\trace\nvcuda.dll" --cufft11 "%ZLUDA_DIR%\cufft64_11.dll" -- "%REVO_EXE%"
