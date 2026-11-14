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

### Patched driver ready for a scanner retest

- Built the patched Windows CUDA driver and CUDA Driver API tracer using
  workspace-local Rust 1.100.0 and the pinned ZLUDA, LLVM, and HiGHS sources.
  The four patches reproduced the build source when applied to clean
  upstream files.
- The driver selects one PTX variant per fatbin member and links the
  lowered members together. The implementation covers 64-bit PTX
  libraries. The existing single-image path also remains available for
  32-bit PTX.
- All 25 PTX parser tests passed. On the RX 7900 XT, the patched build
  passed the vector, cuFFT 11, and shared/global atomic-add probes.
  The two-member regression found both kernels, resolved a repeated
  weak kernel, and ran a cross-member device call that returned 79.
  The same regression passed through the rebuilt tracer and produced
  separate PTX files for both members.
- A local read-only probe loaded the six CUDA images from
  Revo Metro 5.8.8.460's installed GPU algorithm DLL through the CUDA
  library API. Both the CUB EmptyKernel and the previously missing
  Thrust uninitialized-fill kernel resolved with the patched DLL. The
  probe lives in ignored build artifacts and reads the vendor DLL in
  place.
- The verified package is `artifacts/zluda-patched-20261113-213650-891`.
  Launch it via `Start-RevoTrace.ps1 -ZludaDir` and repeat the same
  new-project Save and scanner-start sequence. Physical scanning,
  tracking, and accuracy remain to be tested.

### Patched scanner retest

- Revo Metro advanced further into loading on the patched build.
  The previously missing Thrust lookup returned `CUDA_SUCCESS` with a
  non-null handle. The trace ended there and the app exited with
  `0xC0000005`. The trace records completed calls, so a fault during
  the next call or in the application remains possible.
- The run produced 20 distinct PTX dumps and 20 ELF dumps. No matching
  Windows application event or user crash dump surfaced. Next capture
  the first-chance native access violation and inspect its stack before
  selecting another compatibility change.

### Explicit legacy stream handle normalization

- A native crash dump from the next Revo Metro 5.8.8.460 startup run
  (`logs/revo-trace-20261113-215041-514`) recorded an access violation in
  AMD HIP 6.2 at `amdhip64_6.dll+0x2F8960` (`mov eax, [rcx+0x270]` with
  `RCX=0x1`, reading `0x271`). Passing the explicit CUDA legacy default
  stream sentinel `CU_STREAM_LEGACY` (`0x1`) to `cuLaunchKernel` on the
  RX 7900 XT reproduced the same invalid read.
- Disassembly of `amdhip64_6.dll` showed that while `hip::getStream`
  routes both `nullptr` (`0x0`) and `hipStreamLegacy` (`0x1`) to
  `Device::GetNullStream(wait = true)` (which synchronizes bidirectionally
  with blocking streams via `Device::AddSafeStreams`), HIP 6.2's
  `STREAM_CAPTURE` prologue in `hipModuleLaunchKernel`,
  `ihipGetStreamDeviceId` in `ihipModuleLaunchKernel`, and
  `ihipStreamSynchronize` omit the `stream != hipStreamLegacy` guard and
  dereference `0x1` as a `hip::Stream*` pointer. `ihipStreamSynchronize`
  also checks `stream == nullptr` when deciding whether to drain blocking
  streams.
- Added `patches/0005-normalize-legacy-stream-handle.patch` in
  `zluda_common/src/lib.rs` so `FromCuda<'a, CUstream, E> for hipStream_t`
  normalizes `CU_STREAM_LEGACY` (`0x1`) to `hipStream_t(ptr::null_mut())`
  (`0x0`) while preserving `0x0`, `CU_STREAM_PER_THREAD` (`0x2`), and
  explicit `hipStream_t` pointers, and retaining pointer conversions via
  `from_cuda_transmute_ptr!(CUstream => hipStream_t)`.
- Extended `tests/gpu_smoke.py` with a stream regression covering
  `cuLaunchKernel`, `cuLaunchKernelEx`, async HtoD/DtoH copies,
  `cuMemsetD32Async`, `cuEventRecord`, `cuStreamWaitEvent`,
  `cuStreamSynchronize`, and `cuStreamQuery` across null (`0x0`),
  explicit legacy (`0x1`), per-thread (`0x2`), blocking, and non-blocking
  streams, plus bidirectional legacy default-stream synchronization with
  blocking streams.
- Rebuilt and staged `artifacts/zluda-patched-20261113-222905-143`.
  `zluda_common` unit tests, the PTX compute probe (257/257), the stream
  and legacy-synchronization regression, cuFFT 11 (32/32), shared/global
  unsigned atomic reduction (16,640), fatbin multi-member lookup and
  cross-member device call (79), and traced stream execution all passed on
  the RX 7900 XT (`gfx1100`).
- Next experiment is to launch Revo Metro 5.8.8.460 against
  `artifacts/zluda-patched-20261113-222905-143` with
  `diagnostics/Start-RevoTrace.ps1 -CaptureCrash` and test whether
  scanning startup completes past the Thrust kernel launch. Marker
  recognition, sustained tracking, and CPU/GPU accuracy remain untested
  until physical scanner runs complete.

### First physical scan on patched driver (no crash; tracking/surface gap)

- Launched Revo Metro 5.8.8.460 with `diagnostics/Start-RevoTrace.ps1`
  against `artifacts/zluda-patched-20261113-222905-143`
  (`logs/revo-trace-20261113-223643-315`). Project loading and scan
  startup succeeded with zero crashes (`RevoMetro.exe` exited cleanly with
  code `0`; no `RevoMetro-crash.dmp` generated).
- Observed in the physical scan: Revo Metro detected reflective dots,
  struggled with tracking, and recorded only small bits of noise instead
  of scanning the object surface. The user also noted GPU utilization
  remained around 25%.
- Trace analysis of `logs/revo-trace-20261113-223643-315/RevoMetro.exe/log.txt`
  (62.4 MB, 467,499 lines) showed:
  - `cuLibraryLoadData` compiled the 5-member fatbin cleanly.
  - All 103,452 `cuLaunchKernel` calls across 1,815 stereo frames
    (3,630 images) returned `CUDA_SUCCESS`, with zero post-init CUDA errors.
  - Stage 3 (`GpuStereoMatch`) returned 57 to 18,194 3D points per frame
    (median 5,709 points/frame via `cuMemcpyDtoHAsync_v2` on `0x3089c0000`),
    indicating the pipeline is producing point output rather than failing
    with zero points.
- Direct RX 7900 XT verification of extracted kernels (from the 5-member
  fatbin in `log.txt`) passed for `DeviceRadixSortSingleTileKernel` (8 and
  268 items), the Connected Components Labeling pipeline, `.const` symbol
  updates (`k_camera_q`), `FailedResultMatchKernelH`, Thrust
  `__fill7functor<FailedGroup>`, `StatGroupsKernel`, and
  `FindMajorIdKernel`.
- Read-only inspection of `RPAGPUAlgorithm.dll` showed:
  - `Impl::Run2` executes Stage 1 (`GpuPreprocess`), Stage 2
    (`GpuExtractFeature`), and Stage 3 (`GpuStereoMatch`) sequentially and
    copies `3 * count` floats back to host.
  - `RPAGPUAlgorithm.dll` also includes a built-in Vulkan backend
    (`ComputeBackend == 2` alongside CUDA `== 1`) and built-in stage
    debug dump hooks.
  - `cuModuleGetGlobal_v2` resolves `.const` symbol buffers
    (`c_steger_kernel`, `c_gather_steger_kernel`, `k_segment_param_left`,
    `k_segment_param_right`, `k_camera_pl`, `k_camera_pr`, `k_camera_q`).
- Note on tracing overhead: running `Start-RevoTrace.ps1` without
  `-NoTrace` logs ~260 synchronous Driver API calls per stereo frame to
  `log.txt` (467,499 lines / 59.56 MB in `logs/revo-trace-20261113-223643-315`),
  throttling GPU throughput (~25% GPU utilization) and real-time frame rate.
- Stage 1 / 2 / 3 RX 7900 XT kernel verification against `artifacts/zluda-patched-20261113-222905-143`:
  - Stage 1: `RemapKernel`, `real2complex` + `fftshift2D` + `applyFilter` +
    `ifftshift2D` + `extractReal` + `normalizeKernel`, `ErodeKernel`,
    `ComputeIntegralRowKernel` + `ComputeIntegralColKernel` +
    `AdaptiveThreshIntegralKernel`, `GetGrayMaxInRowKernel` (`red.global.add.u32`),
    and `cufft64_11.dll` `cufftPlan2d(1200, 1600, CUFFT_C2C)` roundtrip all
    passed against CPU reference expectations.
  - Stage 2: `StegerKernel` (`c_steger_kernel` `.const` update) and
    `GatherKernel` (`atom.global.add.u32`) passed.
  - Stage 3: `SearchMapKernelH`, `PointToPointSecondMatchKernelH` (with
    register-indirect `.const` `k_segment_param_left` / `k_segment_param_right`
    loads), and `ArrangeAndCombineSecondMatchKernel` (`6480`-byte `.local`
    frame + `st.local.v2`) all passed.
- Next step: run a physical scan with `diagnostics/Start-RevoTrace.ps1 -NoTrace`
  (removing `trace/nvcuda.dll` synchronous per-call file I/O) to see whether
  marker tracking and surface capture work cleanly at full frame rate, or if
  an issue remains when untraced.

## Matched untraced CPU vs GPU scan (`Test Scan 1`)

- User ran an untraced ZLUDA GPU scan (`4fb8956c-50ea-4e9a-8aff-aa9339da89c5`)
  and a matched CPU scan (`43f56096-edaa-4143-8013-6911c8b62473`) in
  `Test Scan 1/Test Scan 1/data/`.
- Comparison of the two scans:
  - `raw_preview.ply`: **202,219** finite vertices (0 NaN/Inf/zero) on GPU vs
    **216,959** on CPU. Both reconstructed the vase and turntable geometry.
  - `property.rvproj`: `vf_count` **1,705** (GPU) vs **2,012** (CPU).
  - `marker_framework.mkf`: **75** markers (GPU) vs **74** markers (CPU).
  - `preview.png`: GPU scan has sparser/missing patches on the flat
    turntable around the base of the vase and slightly more stray outliers.
  - `process.log`: GPU logged `Error: Matrix4x4::operator = right matrix is empty`
    (CPU `process.log` is empty), indicating intermittent tracking-pose loss.
- Additional RX 7900 XT checks:
  - `cufftPlan2d(12, 16, CUFFT_C2C)` forward DFT matched exact row-major 2D
    DFT peaks; `800x600` CCL with `32x32` (1024-thread) blocks returned exact
    component count (`40 / 40`).
  - `1600x1200` kernel timings (`RemapKernel` 0.067 ms, `applyFilter` 0.372 ms,
    `StegerKernel` 0.032 ms, `ArrangeAndCombineSecondMatchKernel` 0.648 ms)
    plus `alloc+memset+4xcufft+sync` (1.09 ms/frame) show raw GPU compute is
    not the bottleneck.
  - `StegerKernel` passed across vertical (`1234` hits), horizontal (`1234`
    hits), and 45-degree diagonal (`1336` hits) Gaussian stripes, and the
    end-to-end `1600x1200` FFT bandpass pipeline matched bright (`220`) and
    dim (`40`) stripe profiles.
- High-quality fusion and meshing on `Test Scan 1` (`logs/revo-trace-mesh`):
  - Only `4` startup `cuLaunchKernel` calls appeared in
    `logs/revo-trace-mesh/RevoMetro.exe/log.txt` (76 KB), confirming fusion
    and meshing do not use CUDA.
  - GPU scan fused/meshed cleanly (`fuse.ply`: 787,509 points at 0.24 mm
    pitch; `fuse_mesh.ply`: 1,171,098 vertices / 2,307,092 faces; `mark.ply`:
    83 markers) alongside CPU (`fuse.ply`: 260,808 points at 0.51 mm pitch;
    `fuse_mesh.ply`: 497,616 vertices / 977,994 faces; `mark.ply`: 84 markers).
- VRAM & per-frame GPU/WDDM overhead audit:
  - `cuDeviceTotalMem_v2` reports `21,458,059,264` bytes (~20 GB) to `RevoMetro.exe`,
    so the RX 7900 XT VRAM is detected properly.
  - Cumulative `cuMemAlloc_v2` across 1,815 traced frames was `866.9 MB` (single
    stereo frame buffers + small 140–1,409 B per-frame scratch allocations);
    Revo Metro copies 3D points back to host RAM per frame and runs fusion/meshing
    on CPU/RAM/disk, so 20 GB VRAM does not increase maximum fused/meshed scan size.
  - Realistic 6,000-point Stage 3 kernel timings on RX 7900 XT:
    `SearchMapKernelH` (`0.152 ms` left + `0.175 ms` right),
    `PointToPointSecondMatchKernelH` (`0.014 ms`),
    `ArrangeAndCombineSecondMatchKernel` (`0.622 ms`).
  - Per-frame ZLUDA/WDDM API overhead replay (`2x cuMemAlloc_v2(140)+cuMemFree_v2`:
    `0.134 ms`, `5x cuMemcpyDtoH_v2(4B)`: `0.220 ms`, `8x cuCtxSynchronize`: `0.003 ms`,
    `4x cuStreamSynchronize`: `0.001 ms`, `42x cuMemsetD8_v2(1.92 MB)`: `0.158 ms`)
    totals `0.517 ms/frame`. Combined with Stage 1–3 kernels and 4x `cufftExecC2C`,
    total GPU pipeline time is ~2.5 ms/frame (~400 FPS theoretical), so ZLUDA/GPU
    compute is not bottlenecking scanner frame rate.
