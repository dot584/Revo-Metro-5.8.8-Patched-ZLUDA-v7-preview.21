# Compatibility patches

These patches target ZLUDA v7-preview.21
(`eb89ae3b23b2abaf8480e496fdd5d51f0651d330`).

- `0001-ptx-unsigned-atomic-reduction.patch` adds scalar `red.add.u32`
  via the existing atomic memory operation and discards the old value.
  Exercise it with the `--atomic-reduction` GPU probe.
- `0002-distinguish-fatbin-submodule-dumps.patch` gives each fatbin
  submodule and image its own trace filename. Exercise it with the
  two-image fatbin probe under CUDA Driver API tracing.
- `0003-link-fatbin-members.patch` selects PTX per member and links the
  resulting LLVM modules together. The GPU test checks symbol lookup,
  duplicate weak definitions, and a cross-member device function call.
- `0004-windows-cargo-build.patch` handles the new Cargo build directory
  layout, preserves LLVM include paths with spaces, and disables LLVM's
  optional Windows DIA SDK dependency.
- `0005-normalize-legacy-stream-handle.patch` maps CUDA's explicit
  `CU_STREAM_LEGACY` (`0x1`) handle to HIP's null/default stream (`0x0`)
  when converting `CUstream` to `hipStream_t`, avoiding HIP 6.2's
  invalid dereference of `0x1` while preserving legacy default-stream
  synchronization semantics. Exercise it with `tests/gpu_smoke.py`.

Apply the patches in numeric order to a development checkout, then
build using [the project workflow](../docs/WORKFLOW.md#patched-windows-driver).
The build script derives a cache version from the patched compiler and
driver sources to keep their translated modules distinct from the
reference release.
