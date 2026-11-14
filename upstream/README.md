# Upstream ZLUDA

The Windows baseline tracks [v7-preview.21](https://github.com/vosen/ZLUDA/releases/tag/v7-preview.21),
commit `eb89ae3b23b2abaf8480e496fdd5d51f0651d330`. This was also the upstream
`master` head when verified on November 13, 2026. GitHub's latest stable
release was [v6](https://github.com/vosen/ZLUDA/releases/tag/v6).

```powershell
git clone --depth 1 --branch v7-preview.21 https://github.com/vosen/ZLUDA.git upstream/ZLUDA
git -C upstream/ZLUDA rev-parse HEAD
```

Upstream provides MIT and Apache 2.0 license texts in `LICENSE-MIT` and
`LICENSE-APACHE`. The checkout preserves both and includes the individual
dependency notices. Leave the checkout at the pin for baseline tests.
