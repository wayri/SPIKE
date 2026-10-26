# Local SPIKE 0.4.2-beta delivery, 25 October 2026

Status: built, installed and locally verified. This is an unsigned local
engineering preview, not a published or production-qualified release.

## Scope and source

The requested delivery includes current desktop source, multi-board/harness and
mechanical assembly interfaces, bundled examples, and the internal chat
**Create SPIKE UI promo media**. The unrelated KiWay promo chat was excluded.
The live checkout remains at its existing version; a dedicated source snapshot
at `D:/SPIKE-0.4.2-beta-20261025` carries `0.4.2-beta` consistently across the
desktop and Python packages (CMake uses numeric core `0.4.2`). The snapshot's
`RELEASE_SOURCE_MANIFEST.json` records original and transformed source hashes.
Builds use the existing pinned Python 3.12.9/PyInstaller 6.21.0 environment.

The NSIS-only preview option preserves the default NSIS+MSI workflow and the
existing MSI prerelease rejection. No numerical kernel was modified or
requalified. Existing first-party native binaries were reused and exercised by
the frozen worker's gates. No release was signed, tagged, pushed or published.

## Simulation and promo evidence

The curated artifact root is `artifacts/showcase-042-20261025`; its
`INTEGRATION_MANIFEST.json`, `summary.json` and adjacent requests/results retain
the evidence. Installed resources are staged at `examples/showcase-042-beta`.

- Native laminar cavity, Re=100, 32x32: converged in 8,441 steps.
- Bounded channel CHT energy residual: -3.39e-13 W.
- openEMS: 64,296 cells; E/H samples at three frequencies. Raw Gaussian-pulse
  Fourier amplitudes remain unvalidated and uncalibrated as steady-state fields.
- Synthetic compiled-controller/P1-motor/hover-BEM coupling: 2,500 steps and
  500 controller ticks; retained numerical payload reproduced exactly, excluding
  executable identity and elapsed-time metadata.
- Latest real OpenMotor/ENOLA/VESC project: portable embedded geometry and
  source files with notices. Its actual motor/CFD/thermal loop remains incomplete.
  It must not be presented as the completed synthetic reference's result.

The three native `.spike` packages passed package readback. The companion retains
all 185 inventoried KiCad source files and the third-party licences. Native GUI
inspection and installed-resource verification are recorded below when executed.

## Executed checks

- Installer script: 13 focused tests passed in the live checkout; the installer
  worker also reported MSI/signing regression tests and PowerShell parser checks.
- Isolated beta frontend: parser, all 28 work examples/56 assets, MCAD and harness
  engineering test groups passed.
- Both frozen workers built and passed their builder verification.
- Main worker source/frozen runtime qualification: 8/8 checks passed with equal
  source and packaged snapshot digests.
- Main worker permanent benchmark suite: 15/15 passed.
- Architecture, public schema/error checks, TypeScript/Vite production build and
  native host checks passed: 81 Rust tests passed, 1 ignored, 0 failed.
- Existing per-user installation at
  `C:/Users/yawar/AppData/Local/Programs/SPIKE` upgraded from `0.4.0-alpha.1`;
  NSIS exited zero and installed PE/CLI versions report `0.4.2-beta`.
- Final installed integrity check passed: 5,051 staged resources and both native
  executables matched byte-for-byte; frozen source coherence passed; all three
  native showcase projects passed package readback.
- Installed SI fixture transport/provenance checks and native airflow/CHT
  packaging probes passed. The SI probe did not execute a native IBIS solver.
- Native electric-field plane and corrected motor/board geometry rendered.
  Screenshots and machine-readable installed checks are retained in
  `artifacts/beta-install-042-20261025`. Desktop input contention complicated
  camera control; the final assembly was opened through the supported native
  startup-project argument. This was not an exhaustive GUI test of every tool.

## Repairs found by actual packaging and native inspection

The first NSIS build succeeded, but artifact finalization exposed a strict-mode
PowerShell scalar `.Count` error. Installer collection and manifest items now
retain array shape for a single installer. A PowerShell execution regression
checks zero, one and duplicate artifacts. Its sandbox attempt hit temporary-file
ACL errors; the unchanged test passed outside that sandbox. The existing built
setup was finalized using the corrected collection/manifest section after all
build checks had already passed.

Native opening exposed an oversized motor display artifact: 74,320,540 bytes
exceeded the existing 64 MiB viewport budget. The curated project now uses exact
byte-identical POSITION deduplication and index remapping. Motor bytes dropped
to 57,999,024; motor plus propeller total 59,715,369. All 4,130,334 triangle
positions remain bitwise identical in sequence. The production visual-artifact
reader admitted both model IDs together. No viewport cap, physics, original STEP
or source geometry was changed. The original oversized package remains local
audit evidence and is excluded from installed examples.

Five repaired example resources were synchronized into the installation and
release stage. NSIS was regenerated from the unchanged verified executables and
workers; final installed file comparison was then repeated successfully. The
initial installed setup is preserved at `build/initial-installed-preview` in
the D-drive snapshot.

Final installer:
`D:/SPIKE-0.4.2-beta-20261025/artifacts/windows/installer/SPIKE_0.4.2-beta_x64-setup.exe`
(148,772,365 bytes), SHA-256
`f5418e78a15bdb429f116c28989b3fc4b0c9b4fcc7708f15c57c59f6785edd0d`.

## Qualification limits

Clean-machine/offline installation and uninstall qualification were not
performed. This local upgrade is not a substitute for those release gates.
The installer is unsigned. Numerical and real-hardware qualification limitations
remain as recorded above and in each example's evidence; installation success
does not qualify their physics.
