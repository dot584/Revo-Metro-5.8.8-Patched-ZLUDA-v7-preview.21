# Revo Metro AMD compatibility progress

## November 13, 2026

- Confirmed Windows 11 Home 26H2 (26300.9974), Ryzen 7 5800X3D, about
  32 GiB RAM, and AMD Radeon RX 7900 XT. AMD Software is 26.10.1 and
  the active display driver is 32.0.32015.7029. HIP `hipInfo` reports
  `gfx1100` and 19.98 GB VRAM. The exact scanner model awaits physical
  confirmation.
- Confirmed Revo Metro 5.8.8.460 from its executable and uninstall entry.
  Static PE import inspection found `RPAGPUAlgorithm.dll` imports CUDA
  Runtime 12 and cuFFT 11 (`cufftPlan2d`, `cufftExecC2C`, `cufftDestroy`).
  `RPAParallel.dll` also imports CUDA Runtime 12. Runtime library loads
  and the application's behavior at marker detection still need a trace.
- Pinned official ZLUDA v7-preview.21, also upstream master at
  `eb89ae3b23b2abaf8480e496fdd5d51f0651d330`. GitHub lists v6 as the
  latest stable release. Preserved the MIT and Apache 2.0 notices in the
  independent upstream Git checkout. Verified the official Windows ZIP
  against its GitHub SHA-256.
- Installed tools include Git 2.49, Python 3.12.7, Visual Studio Build
  Tools 2022, MSVC 14.43, and bundled CMake 3.30.5 and Ninja. The source
  build preflight stopped at missing Cargo. LLVM and HiGHS submodules
  are still pending. This baseline uses the official binary release.
- `cuda_check.exe` reported CUDA and cuFFT 11 initialized using AMD HIP
  SDK 6.2 libraries. cuBLAS, cuBLASLt, and cuDNN initialization failed.
  The NVAPI entry reported that its check is unimplemented. None of
  those failed libraries appeared in Revo Metro's static CUDA imports.
  The all-library check can display a missing `MIOpen.dll` dialog
  while probing cuDNN. The project workflow now restricts the check to
  `nvcuda` and `cufft11`.
- Synthetic CUDA Driver API PTX compute passed on the RX 7900 XT,
  matching 257/257 expected integers. An out-of-place complex 2D forward
  cuFFT transform passed 32/32 outputs within absolute error 1e-5.
- Full ZLUDA tracing passed PTX but panicked after `cufftPlan2d` when
  calling `cufftExecC2C` (`RefCell already borrowed`,
  `zluda_trace/src/lib.rs:1015`). With CUDA Driver API-only tracing and
  regular ZLUDA cuFFT, both tests passed and the trace recorded the PTX
  load, launch, completion, and device-to-host copy. This is a synthetic
  tracing bug. The Revo Metro marker failure still needs reproduction.

Next action is to run matching CPU and untraced GPU laser scans and
capture the CUDA Driver API trace if the GPU scan fails. Use
[the scanner workflow](docs/WORKFLOW.md#scanner-runs). No scanner mode,
tracking, point-cloud performance, or dimensional-accuracy claim has
been validated.

### First scanner crash

- Revo Metro 5.8.8.460 opened with the CUDA Driver API trace. The process
  loaded the workspace's ZLUDA driver and cuFFT 11. Clicking Save on a
  new scan project triggered scanning startup and exit `0xC0000005`.
  The last failed call was `cuModuleGetFunction` for a Thrust
  `uninitialized_fill` kernel, with `CUDA_ERROR_NOT_FOUND`.
- ZLUDA flattens architecture variants from all members of a version 2
  fatbin wrapper and compiles a single PTX image. Read-only inspection
  found the requested kernel in a different PTX image in the installed
  GPU algorithm DLL. A synthetic two-image CUDA library on the RX 7900
  XT exposed only the second kernel, while both kernels were found
  when loaded as standalone images. Implement selection per fatbin
  member and preserve cross-member symbol resolution before retesting.
- The same capture showed parse failures for scalar unsigned atomic
  reductions (`red.shared.add.u32` and `red.global.add.u32`) in another
  image. A synthetic probe reproduced the missing-kernel result.
  The equivalent returning `atom.add.u32` form passed on the RX 7900 XT
  with the expected total of 16,640. Added a candidate ZLUDA parser and
  lowering patch for those instructions.
- The tracer attempted to write different fatbin members to identical
  filenames. Added a candidate patch to number members and their images
  independently. Both patches apply cleanly at the upstream pin.
  Patched builds and scanner retest are pending.

The current release remains suitable for the synthetic compute baseline.
Use the regular Revo Metro shortcut and CPU mode for scanning while
the two CUDA gaps are being addressed.
