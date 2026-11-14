# Reproducing the Revo Metro baseline

Run the commands from the project root in PowerShell 7.3 or later. The
GPU tests use 64-bit Python 3 and the existing AMD driver and HIP SDK.
The baseline on this workstation used the installed HIP SDK 6.2 and AMD
Software 26.10.1. AMD lists the RX 7900 XT as `gfx1100` for its
[Windows HIP SDK](https://rocm.docs.amd.com/projects/install-on-windows/en/latest/reference/system-requirements.html).

## GPU compute

```powershell
$zluda = & ./setup/Get-ZludaRelease.ps1
python ./tests/gpu_smoke.py $zluda
```

The setup script verifies the Windows ZIP against SHA-256 from the
[GitHub release API](https://api.github.com/repos/vosen/ZLUDA/releases/tags/v7-preview.21).
The probe loads the specified CUDA driver by absolute path, selects the
RX 7900 XT by name, and checks output from a translated PTX kernel and a
complex 2D transform using the three cuFFT functions imported by the
scanning GPU module. Any mismatch or CUDA error fails the probe.

Upstream also supplies a library initialization check:

```powershell
./diagnostics/Start-RevoTrace.ps1 -CheckLibraries
```

This checks only the CUDA Driver and cuFFT 11. An unrestricted
`cuda_check.exe` run also probes cuDNN and can show a missing
`MIOpen.dll` dialog with the official AMD HIP SDK. The upstream check's
exit code can be zero alongside individual library errors. Read the
per-library results.

## Scanner runs

1. Confirm the scanner model shown by Revo Metro or its label. Set up the
   marked reference object and leave lighting, exposure, scan mode, and
   marker placement fixed across the runs.
2. Open Revo Metro normally and explicitly select CPU acceleration. Run
   a short laser scan and record whether markers are recognized, tracking
   holds, and a point cloud is generated. Record the scanner model, mode,
   marker count if available, and any exact status message. Export the
   point cloud to the project's ignored `logs/` folder if possible.
3. Close Revo Metro completely. Launch the untraced GPU run:

   ```powershell
   ./diagnostics/Start-RevoTrace.ps1 -NoTrace
   ```

   Select the ZLUDA RX 7900 XT in Revo Metro and repeat the scan. Record
   whether the GPU appears, whether marker recognition succeeds, and
   the first exact error and approximate time if it fails. Close Revo
   Metro when the run is complete.
4. If the GPU run fails, repeat with the CUDA Driver API trace:

   ```powershell
   ./diagnostics/Start-RevoTrace.ps1
   ```

   The script prints a new session directory under `logs/`. Reproduce
   once and close Revo Metro so diagnostics can flush. Report the session
   folder name, scan mode, exact status message, and whether the behavior
   matched the untraced GPU run. Leave the trace files in the project.

The trace routes `nvcuda.dll` through ZLUDA's CUDA Driver API logger and
routes `cufft64_11.dll` to the regular ZLUDA FFT library. Full library
tracing in this release panicked in the synthetic `cufftExecC2C` test.
The driver trace can record module loads, kernel dispatch, copies,
synchronization, and driver status codes. It does not log cuFFT entry
points. An empty trace calls for checking launcher output and loaded
modules. Keep raw traces private because they can contain application
kernel dumps and machine paths.

Correlate the first visible scanning failure with module load, launch, and
synchronization results. Failed feature probes and shutdown errors may
be expected, so confirm any suspected failure with a minimal reproducer.
If modules load and kernels finish successfully, compare known inputs and
outputs before changing CUDA behavior.

## Accuracy after GPU scanning works

Run repeated CPU and GPU scans of the same measured object, with the same
mode, capture duration, and export settings. Record tracking dropouts,
frame rate, GPU compute utilization, and point count. Apply the same
alignment to both exports. Compare dimensions against the measured object,
surface deviation on the same regions, alignment residuals, and missing
areas. Record reference dimensions, measurement uncertainty, and scan
settings with the results. Test other scanner modes independently.

## Source builds

Follow the pinned checkout recipe in [upstream/README.md](../upstream/README.md).
Use Git LFS, current Rust and Cargo for `x86_64-pc-windows-msvc`, Python 3,
CMake, MSVC C++ Build Tools with Windows SDK, and Ninja if available.
Use a Visual Studio Developer PowerShell to expose the installed MSVC
and bundled CMake. Keep any toolchain installation subject to user
approval when it would write outside the project.

```powershell
git -C upstream/ZLUDA lfs pull
git -C upstream/ZLUDA submodule update --init --recursive
./build/Build-Zluda.ps1
python ./tests/gpu_smoke.py ./upstream/ZLUDA/target/release
```

The [upstream build instructions](https://zluda.readthedocs.io/latest/building.html)
use `cargo xtask --release`. The two pinned submodules supply LLVM and
HiGHS. The release archive is the reference until a source build has been
tested against the same probe.

## Patched Windows driver

The patched driver build uses the x64 MSVC tools and Rust under
`artifacts/toolchain`. To provision Rust locally, use the official x64
Windows `rustup-init.exe` with `RUSTUP_HOME` and `CARGO_HOME` pointing to
`artifacts/toolchain/rustup` and `artifacts/toolchain/cargo`. Pass
`--no-modify-path --profile minimal`. Fetch the pinned Git LFS and
submodule contents before the first build.

Apply the patch series in numeric order to the pinned checkout. Build
with PowerShell 7 and stage a separate copy of the verified release
package with the rebuilt CUDA driver and trace DLLs.

```powershell
./build/Build-PatchedDriver.ps1
$patched = ./build/Stage-PatchedDriver.ps1
python ./tests/gpu_smoke.py $patched --atomic-reduction ./tests/atomic_reduction.ptx
python ./tests/fatbin_lookup.py $patched
```

The fatbin test checks lookup across two members, a repeated weak
kernel, and an actual cross-image device call. After both probes pass,
use `./diagnostics/Start-RevoTrace.ps1 -ZludaDir $patched` for the scanner
retest. The launcher uses the installed Revo Metro executable and the
DLLs in the staged project package.

For a silent access violation, add `-CaptureCrash` to that command.
The launcher uses Microsoft-signed [ProcDump](https://learn.microsoft.com/en-us/sysinternals/downloads/procdump)
at `artifacts/procdump/procdump64.exe` and captures one unhandled
exception. The minidump and CUDA trace share the printed session folder.
Keep the dump local and report the session folder name.
