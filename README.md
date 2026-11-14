# Revo Metro AMD GPU Compatibility (Patched ZLUDA)

Run **Revopoint Revo Metro** with CUDA GPU acceleration on **AMD Radeon GPUs** on Windows using a patched build of [ZLUDA](https://github.com/vosen/ZLUDA), **without modifying any proprietary Revo Metro files**.

> **Tested & Verified On**
> - **GPU:** AMD Radeon RX 7900 XT (`gfx1100`)
> - **Software:** Revo Metro `5.8.8.460` (Windows)
> - **Scanner:** Revopoint MetroY Pro
> - **ZLUDA Baseline:** `v7-preview.21` (`eb89ae3`) + 5 compatibility patches (`patches/0001`–`0005`)

---

## AMD GPU & Scanner Compatibility

### Supported AMD GPUs
- **AMD Radeon RX 7000 series (RDNA 3)** — tested on RX 7900 XT
- **AMD Radeon RX 6000 series (RDNA 2)** — supported by AMD's Windows HIP runtime
- **Newer discrete Radeon GPUs (RDNA 4 / RX 9000 series)** — expected to work with current Adrenalin / HIP drivers (untested here)

### AMD GPUs That Will NOT Work
ZLUDA on Windows relies on AMD's modern HIP/ROCm runtime. The following GPUs are **not supported** and will fail or fall back to CPU:
- **RX 5000 series (RDNA 1)** — e.g., RX 5500 XT, RX 5600 XT, RX 5700 / 5700 XT (lacks official Windows HIP runtime support)
- **Vega GPUs** — Radeon Vega 56, Vega 64, Radeon VII, and older Vega APUs
- **Polaris & older GCN GPUs** — RX 400 / RX 500 series (RX 470, 480, 570, 580, 590), R9 / R7 / HD series
- **Integrated Graphics (APUs)** — e.g., Radeon 680M / 780M / Vega iGPUs (not supported out of the box on Windows HIP SDK)

### Revopoint Scanners & Scan Modes
- **Scanners:** Tested with **MetroY Pro** on Revo Metro `5.8.8.460`. Other Revopoint scanners running through Revo Metro's CUDA pipeline (`RPAGPUAlgorithm.dll`) should use the same GPU path, though other models have not been directly tested.
- **Laser-Line Modes (Single Line / Cross Line):** Fully accelerated on GPU (~2.5 ms/frame on RX 7900 XT).
- **Blue Light (Full-Field) Mode:** Only 2D preprocessing/Steger extraction runs on CUDA; the rest remains on CPU.
- **Fusion & Meshing:** Run **100% on CPU, system RAM, and disk** (not GPU).
- **Marker Tracking:** Runs on CPU using camera frames.

---

## Quick Start (Prebuilt Release ZIP)

1. **Install the latest AMD Adrenalin driver** for your Radeon GPU (and ensure Revo Metro is installed at `C:\Program Files\Revo Metro\RevoMetro.exe`).
2. **Download** `RevoMetro-ZLUDA-AMD-win64.zip` from the **Releases** page and extract it anywhere (for example, `C:\Tools\RevoMetro-ZLUDA\`).
   - Make sure the extracted folder contains `Launch Revo Metro (GPU).cmd` alongside the `zluda\` subfolder.
3. **Double-click `Launch Revo Metro (GPU).cmd`** to start Revo Metro with AMD GPU acceleration.
4. In Revo Metro **Settings**, enable **GPU Acceleration** (if it asks to restart, close Revo Metro and launch it again using `Launch Revo Metro (GPU).cmd`).

> **Note:** If you installed Revo Metro to a custom path, set the `REVO_METRO_EXE` environment variable to your `RevoMetro.exe` path before running the launcher.

---

## Building From Source

If you prefer to build the patched ZLUDA binaries yourself instead of downloading the Release ZIP:

1. **Prerequisites:** Rust toolchain, LLVM/Clang, Visual Studio C++ Build Tools, PowerShell, and Python 3.12+.
2. **Fetch / build / stage ZLUDA with patches:**
   - Check `setup/Get-ZludaRelease.ps1` and `build/Build-PatchedDriver.ps1` / `build/Stage-PatchedDriver.ps1`.
   - The patches in `patches/` (`0001`–`0005`) are applied on top of `vosen/ZLUDA` (`eb89ae3`) and staged into `artifacts/zluda-patched-<timestamp>/`.
3. **Run the GPU smoke test:**
   ```powershell
   python tests/gpu_smoke.py
   ```
4. **Launch Revo Metro:** Double-click `Launch Revo Metro (GPU).cmd` — it automatically finds the newest `artifacts\zluda-patched-*\` build.

---

## Troubleshooting & Debug Mode

- **Always use `Launch Revo Metro (GPU).cmd` for normal scanning.**
- Only use `Launch Revo Metro (GPU Debug Trace).cmd` when troubleshooting a crash or bug. Debug mode logs every CUDA Driver API call synchronously to `logs\revo-trace-YYYYMMDD-HHmmSS\`, which writes gigabytes of text and **severely reduces live scanning frame rate** (which can cause tracking drift if used for real scans).
- **ZLUDA Community:** Upstream ZLUDA is maintained at [vosen/ZLUDA](https://github.com/vosen/ZLUDA) ([Discussions](https://github.com/vosen/ZLUDA/discussions)).

---

## License & Attribution

- Local patches and scripts in this repository preserve upstream [ZLUDA](https://github.com/vosen/ZLUDA) licenses (Apache-2.0 / MIT).
- No proprietary Revopoint / Revo Metro files are included or modified.
