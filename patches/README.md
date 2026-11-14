# Compatibility patches

These candidate patches target ZLUDA v7-preview.21
(`eb89ae3b23b2abaf8480e496fdd5d51f0651d330`).

- `0001-ptx-unsigned-atomic-reduction.patch` adds scalar `red.add.u32`
  via the existing atomic memory operation and discards the old value.
  Exercise it with the `--atomic-reduction` GPU probe.
- `0002-distinguish-fatbin-submodule-dumps.patch` gives each fatbin
  submodule and image its own trace filename. Exercise it with the
  two-image fatbin probe under CUDA Driver API tracing.

Both patches pass `git apply --check`. Compilation and patched GPU tests
are pending. The multi-image kernel lookup failure is still open and
has its own reproducer in `tests/fatbin_lookup.py`.

Apply the patches to a development checkout and commit them there
before compiling. The ZLUDA module cache key includes the checkout's
commit SHA, so the new commit avoids reusing cached release translations.
