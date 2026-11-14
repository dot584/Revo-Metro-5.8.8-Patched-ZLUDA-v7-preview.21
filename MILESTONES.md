# Project milestone log

## Instructions for agents

1. Before making a major project change, read this log, starting with the latest entry. Open `PROGRESS.md` and any files referenced in that entry as needed.
2. Do the work and verify it. After a major change or milestone, append one short entry at the bottom. Keep earlier entries as history.
3. Use the next sequential milestone number and the local date in YYYY-MM-DD format. Use the four fields below in order. Include the exact version, commit, command, or artifact when it helps the next agent reproduce the result. Clearly state what remains unverified or blocked.
4. Keep proprietary binaries, raw captures, and personal data out of the log. Link to tracked project files and identify local artifacts by project-relative path.

Use this format:

```markdown
### MNNN | YYYY-MM-DD | Short milestone title

- **Change** — What changed and why.
- **Verification** — Checks run and observed results.
- **References** — Relevant commits, project files, or artifacts.
- **Next** — Specific follow-up, blocker, or pending user test.
```

## Entries

### M001 | 2026-11-13 | Established the AMD compute baseline

- **Change** — Pinned ZLUDA `v7-preview.21` and added a GPU probe and a Revo Metro diagnostic launcher.
- **Verification** — On the RX 7900 XT, the probe matched all 257 PTX outputs and all 32 cuFFT outputs. An untraced Revo Metro 5.8.8.460 launch exited silently. CUDA Driver API tracing opened the app and loaded the workspace CUDA and cuFFT DLLs.
- **References** — Commits `20fc663` and `7d84828`. [Workflow](docs/WORKFLOW.md)
- **Next** — Capture the scan-start path. The reason for the launch difference remains unverified.

### M002 | 2026-11-13 | Reproduced the scan-start failure

- **Change** — Traced the crash after saving a new scan project. Added standalone reproductions for fatbin member lookup and unsigned PTX atomic reductions.
- **Verification** — The app returned `CUDA_ERROR_NOT_FOUND` for a Thrust kernel before exiting with `0xC0000005`. The release exposed only one member in a two-member synthetic fatbin. The missing app kernel was present in a different PTX member of the installed GPU library.
- **References** — Commit `eacb854`. [Progress](PROGRESS.md)
- **Next** — Build and test per-member PTX selection and linking.

### M003 | 2026-11-13 | Built and tested the patched ZLUDA driver

- **Change** — Linked 64-bit PTX fatbin members and added unsigned atomic reductions and distinct trace filenames.
- **Verification** — All 25 parser tests passed. The RX 7900 XT passed PTX, cuFFT, atomic reductions, and cross-member GPU execution. The rebuilt DLL resolved the previously missing Thrust kernel in a read-only test of Revo Metro's installed GPU library.
- **References** — Commit `1bdac7a`. Local package `artifacts/zluda-patched-20261113-213650-891`. [Patched driver workflow](docs/WORKFLOW.md#patched-windows-driver)
- **Next** — Repeat the new-project Save and laser scan with the patched launcher. Marker recognition, tracking, and accuracy await a physical scanner test.

### M004 | 2026-11-13 | Established the agent handoff log

- **Change** — Added this running log with a uniform entry format and linked the read-before-work and append-after-verification steps from `AGENTS.md`.
- **Verification** — Backfilled the three engineering milestones from the tracked progress notes and Git history.
- **References** — [Agent instructions](AGENTS.md) and [Progress](PROGRESS.md)
- **Next** — Record the patched scanner retest here when results are available.

### M005 | 2026-11-13 | Created the AMDGPUScan skill

- **Change** — Captured the verified launch, tracing, patch validation, and scanner handoff procedures in a reusable Codex skill.
- **Verification** — The skill validator passed for both the project source and the installed copy.
- **References** — [AMDGPUScan skill](skills/amdgpuscan/SKILL.md)
- **Next** — Use the skill to resume the patched scanner retest and record its results.

### M006 | 2026-11-13 | Confirmed patched startup advances past kernel lookup

- **Change** — Ran the patched package in Revo Metro with CUDA Driver API tracing. The user saw scanning startup progress further into loading.
- **Verification** — The previously missing Thrust kernel returned `CUDA_SUCCESS` with a non-null handle. The process still exited with access violation `0xC0000005`. The lookup was the last completed call in the trace and no kernel launch completed afterward. Windows application events and the user crash-dump directory yielded no matching crash record.
- **References** — Local trace `logs/revo-trace-20261113-214614-994`. [Progress](PROGRESS.md)
- **Next** — Capture a native exception stack during the next scanner reproduction to identify the faulting module and instruction.

### M007 | 2026-11-13 | Armed native crash capture

- **Change** — Added `-CaptureCrash` to the patched launcher. Project-local Microsoft ProcDump waits for the app and writes one unhandled-exception minidump alongside the CUDA trace.
- **Verification** — Verified Microsoft's signature and ran the same launcher against a throwaway x64 program. The resulting dump contained a native exception stream with code `0xC0000005`.
- **References** — [Diagnostic launcher](diagnostics/Start-RevoTrace.ps1). Local tool `artifacts/procdump/procdump64.exe`.
- **Next** — Repeat the scanner startup with `-CaptureCrash` and inspect the resulting dump and trace together.

### M008 | 2026-11-13 | Isolated the native legacy-stream crash

- **Change** — Inspected the newest minidump, mapped the faulting instruction to the installed HIP runtime, and isolated it with a synthetic CUDA launch.
- **Verification** — Revo Metro resolved the Thrust kernel, then HIP 6.2 faulted at `amdhip64_6.dll+0x2F8960`, reading address `0x271` from `RCX=1` plus offset `0x270`. Passing the CUDA legacy-stream handle `1` to the patched driver’s existing PTX launch probe reproduced the same invalid read. The original default-stream probe passed.
- **References** — Local dump and trace `logs/revo-trace-20261113-215041-514`. [GPU probe](tests/gpu_smoke.py)
- **Next** — Preserve CUDA legacy default-stream semantics when forwarding HIP launches and add a regression covering explicit legacy and per-thread handles before another scanner run.

### M009 | 2026-11-13 | Normalized explicit legacy stream handles for HIP launches

- **Change** — Traced `CUstream` conversion in `zluda_common` and disassembled HIP 6.2 (`amdhip64_6.dll`) stream handling. Normalized `CU_STREAM_LEGACY` (`0x1`) to the null `hipStream_t` (`0x0`) in `FromCuda<'a, CUstream, E> for hipStream_t` while preserving `0x0`, `CU_STREAM_PER_THREAD` (`0x2`), created streams, and pointer conversions. Added a unit test and a GPU stream regression, then rebuilt and staged `artifacts/zluda-patched-20261113-222905-143`.
- **Verification** — Disassembly confirmed HIP 6.2 routes `hipStream_t(0)` and `hipStreamLegacy` (`0x1`) to the same `Device::GetNullStream(wait = true)` synchronization path, while `STREAM_CAPTURE`, `ihipGetStreamDeviceId`, and `ihipStreamSynchronize` dereference `0x1` unless normalized to `0x0`. The `zluda_common` unit test, PTX probe (257/257), stream regression (null, `0x1`, `0x2`, blocking, non-blocking, and bidirectional legacy default-stream ordering), cuFFT 11 (32/32), atomic reduction (`16640`), fatbin lookup (`79`), and traced stream execution all passed on the RX 7900 XT (`gfx1100`).
- **References** — [Legacy stream patch](patches/0005-normalize-legacy-stream-handle.patch), [Patch series](patches/README.md), [GPU probe](tests/gpu_smoke.py), [Progress](PROGRESS.md). Local package `artifacts/zluda-patched-20261113-222905-143`.
- **Next** — Run Revo Metro 5.8.8.460 with `diagnostics/Start-RevoTrace.ps1 -ZludaDir artifacts/zluda-patched-20261113-222905-143 -CaptureCrash` and verify whether scan startup progresses past the Thrust kernel launch into physical scanner operation.

### M010 | 2026-11-14 | Verified full Stage 1–3 kernel pipeline and matched untraced CPU vs. GPU scan

- **Change** — Verified Revo Metro's Stage 1, Stage 2, and Stage 3 CUDA kernels and `cufft64_11.dll` directly on the RX 7900 XT (`gfx1100`), and compared a matched untraced ZLUDA GPU scan (`4fb8956c-50ea-4e9a-8aff-aa9339da89c5`) against a CPU scan (`43f56096-edaa-4143-8013-6911c8b62473`) in `Test Scan 1`.
- **Verification** — Traced run `logs/revo-trace-20261113-223643-315` exited cleanly (`0`) with 103,454 `cuLaunchKernel` calls returning `CUDA_SUCCESS`, but synchronous `trace/nvcuda.dll` logging (467,499 lines / 59.56 MB) throttled frame rate. In the untraced `Test Scan 1`, GPU produced 202,219 finite 3D points (`vf_count=1,705`, 75 markers) vs. CPU's 216,959 points (`vf_count=2,012`, 74 markers), with `process.log` recording `Error: Matrix4x4::operator = right matrix is empty` on dropped tracking frames. On the RX 7900 XT, `RemapKernel`, FFT-domain filtering (`cufftPlan2d` row-major 2D DFT), `AdaptiveThreshIntegralKernel`, `ErodeKernel`, `GetGrayMaxInRowKernel` (`red.global.add.u32`), `StegerKernel` (vertical, horizontal, and 45-degree diagonal), `GatherKernel`, `InterpolateKernel`, `SearchMapKernelH`, `PointToPointSecondMatchKernelH` (indirect `.const`), `ArrangeAndCombineSecondMatchKernel` (`6480`-byte `.local`), and `800x600` `32x32`-block CCL (`40/40`) all passed, with `1600x1200` kernels running in 0.019–0.648 ms each.
- **References** — [Progress](PROGRESS.md), [Matched scan project](Test%20Scan%201/Test%20Scan%201/Test%20Scan%201.revo). Local trace `logs/revo-trace-20261113-223643-315`.
- **Next** — Investigate why intermittent pose/tracking loss (`Matrix4x4::operator = right matrix is empty`) occurs more easily under ZLUDA than CPU (e.g., WDDM `cuCtxSynchronize`/OpenGL viewport contention or subtle numerical/threshold differences on low-contrast turntable frames).
