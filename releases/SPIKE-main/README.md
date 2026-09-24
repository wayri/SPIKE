# SPIKE-main engineering preview overlay

This directory creates an isolated, full-workbench snapshot of the current
main checkout. It never edits the source `app/` tree. The prepared app is
`releases/SPIKE-main/app` and is built as **SPIKE-main** with
Tauri identifier `org.spike.main`; its Windows application-data location and
NSIS start-menu folder are therefore separate from SPIKE.

`scripts/prepare-spike-main-preview.ps1` copies the current source tree and a
physical local dependency snapshot while excluding generated `dist`, `target`,
and report-preview directories. This avoids Windows Vite/esbuild resolution
through a checkout junction. It applies only
the preview overlay:

- enables Cargo feature `spike-main-preview`;
- makes `require_worker_capability` return success only for that feature;
- keeps signed-entitlement parsing, package signatures, trust bindings, and
  project-manifest verification unchanged;
- changes only licensing-facing Help, About, and Settings text to explain the
  temporary suspension; and
- changes product/install identity and removes the `.spike` association so the
  preview does not take over SPIKE project files.

It is an unsigned engineering preview. It is neither production nor commercial
qualified, and it retains every original and third-party licensing obligation.
Numerical status and validation claims are unchanged.

Use the following from the workspace root after the main UI snapshot is ready:

```powershell
powershell -ExecutionPolicy Bypass -File releases/SPIKE-main/scripts/prepare-spike-main-preview.ps1 -Refresh
powershell -ExecutionPolicy Bypass -File releases/SPIKE-main/scripts/test-spike-main-preview.ps1
powershell -ExecutionPolicy Bypass -File releases/SPIKE-main/scripts/build-spike-main-preview.ps1 -Portable
```

The portable command creates a ZIP in `artifacts/`. A separate `-Bundle`
command creates an NSIS installer when Tauri's pinned NSIS tool is available.
Neither command calls the commercial production-packaging route.

The 2026-09-24 build used `-Portable` because Tauri's NSIS tool was unavailable
locally and its single download attempt timed out. The resulting
`SPIKE-main-portable-0.2.12.zip` contains the release executable and its
complete `bundled/spike-worker` runtime alongside every other configured
Tauri resource. Unpack the complete
directory before launch. The local copy was installed at
`%LOCALAPPDATA%\Programs\SPIKE-main` without changing the existing SPIKE
installation.

The local build artifact is at
`build/spike-main-preview-20260924/artifacts/SPIKE-main-portable-0.2.12.zip`
(SHA-256 `20605A08E545D51FC0AC28630B3951AECBEB5FAB807B3249D000197CE261B1C2`).
The installed copy contains 2,436 files, all 13 configured resources, and a
bundled worker that reports `status: ready`. The app launched and remained
running during a five-second local smoke check. The preview is unsigned and
has not passed a clean-machine or numerical qualification review. Two native
tests that assume the original source-checkout layout do not pass in the
isolated variant; the focused entitlement and package-trust tests pass.
