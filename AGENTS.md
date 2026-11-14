# Revo Metro AMD compatibility

- Target the RX 7900 XT workstation and the installed Windows Revo Metro application. Confirm hardware and software versions when reproducing a result.
- Use the pinned upstream in `upstream/ZLUDA`. Keep the reference checkout clean. Record compatibility changes in `patches/` and preserve upstream licenses and attribution.
- Inspect app dependencies and trace runtime failures. Keep the proprietary application files untouched. Fix demonstrated behavior and add regression coverage for each compatibility change.
- Store build outputs in `artifacts/` and raw diagnostics in `logs/`. Keep proprietary files, captures, machine paths, and personal data out of Git.
- Use matched CPU/GPU scanner runs before making claims about marker recognition, tracking, or accuracy. The user operates the scanner.
- Ask before installing or changing system drivers, changing system configuration, or editing files outside this workspace.
- Update PROGRESS.md after meaningful milestones with exact versions, observed results, remaining uncertainties, and the next experiment.
- Before starting a major project change, read [MILESTONES.md](MILESTONES.md) for the latest handoff. Complete the work and its checks, then append a short entry there using the file's template. Record meaningful partial work and its blocker if the task cannot be finished.
