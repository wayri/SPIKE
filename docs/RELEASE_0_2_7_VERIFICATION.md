# SPIKE desktop 0.2.7 installed verification

Date: 2026-09-05. Channel: unsigned engineering preview, not production/signoff
qualified. The local installation was upgraded from 0.2.5 using the verified
current-user NSIS installer after the old application closed normally without
an unsaved-work prompt. No project files were overwritten by the installer.

## Exact delivered image

Installed desktop: `C:/Users/yawar/AppData/Local/Programs/SPIKE/spike-desktop.exe`.
File version is 0.2.7 and its SHA-256 matches the built desktop:
`7ccbe9f8be609b02e63904f3ef2cae413e6cc5b34b1f300116a7163c0db6e614`.

Installed bundled worker SHA-256:
`0431e40809132e3dfff186d59f72ff164ce1975fdddf6efb215a472936728a23`.

Archive: `artifacts/windows/releases/0.2.7-integrated-20260905/`.

| Installer | SHA-256 |
|---|---|
| SPIKE_0.2.7_x64-setup.exe | `24e0192809d612526daccb16a8721d9d6cf29654a275629ac37a706c0cee9967` |
| SPIKE_0.2.7_x64_en-US.msi | `ff9403ac00893ae9ac18ce9faf0d070eff9139b899af95655af3affe24c52899` |

Both installers are `NotSigned`. The prior installed-image backup remains in
`artifacts/windows/rollback-pre-0.2.6/`; the immutable 0.2.6 archive is unchanged.

## Verification boundaries

- Full CPython 3.12 Python discovery: 1,375 tests, one skipped, no failures/errors.
- Frontend: 43 test scripts plus TypeScript, all passed after help regeneration.
- Native desktop host: 29 tests passed; production frontend/Rust builds passed.
- Packaged runtime parity: 8/8; packaged benchmark smoke: 15/15; native/Arrow and
  ODB++/harness execution probes passed. These are bounded fixture results.
- Final source identity: 888 packaged-source inputs unchanged across final build.
  Generated `python/build` test fixtures are excluded from source identity.
- Two public-board import/save/Save As/reopen checks passed (OLED and RP2040).
- Exact installed worker: **21/21 automated package acceptance checks passed**.
  Report: `build/installed-0.2.7-acceptance.json`.

Overall packaged acceptance remains `pending_human`. Computer Use was stopped
with physical Escape during launch verification. No completed interactive
viewport acceptance or high-density frame-rate qualification is claimed.

The archive contains the source snapshot, test logs, installer/worker manifests
and runtime qualification. This post-install record is repository evidence;
it was produced after the installer was built. Subsequent source developments
are not automatically part of the installed 0.2.7 image.
