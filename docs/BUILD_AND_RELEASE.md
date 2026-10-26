# Building SPIKE

The [0.4.2 readiness assessment](validation/RELEASE_0_4_2_READINESS_20261026.md)
records the current candidate's checks and outstanding release gates.

Windows MSI builds validate the effective Tauri/application version before
building, then read the resulting MSI `ProductVersion` through a read-only
database query before signing or copying artifacts. A matching filename alone
does not establish version coherence. Do not retain a stale explicit
`bundle.windows.wix.version`; stable builds normally use Tauri's default mapping.
Windows compares only the first three fields, ignoring a fourth component
([Microsoft ProductVersion](https://learn.microsoft.com/en-us/windows/win32/msi/productversion)).
Prerelease MSI builds require a separately reviewed upgrade-ordering policy;
the current gate refuses to silently collapse them into stable versions. Native
preview `-BuildOnly` remains available without generating an installer.

For an explicitly requested local prerelease such as `0.4.2-beta`, after the
application and effective Tauri configuration already contain that same
version, build only the unsigned engineering-preview NSIS installer:

```powershell
.\scripts\build_windows_installer.ps1 -Channel Preview -Bundles nsis
```

`-Bundles` defaults to `nsis,msi`, preserving the stable packaging workflow.
NSIS-only packaging remains preview-only; production candidates still require
both formats. Selecting MSI (alone or with NSIS) continues through the existing
MSI prerelease rejection and read-only internal `ProductVersion` verification.
This option creates a local preview artifact; it does not publish, sign, install,
or qualify it for production.

The 0.4.0-alpha.1 EMerge/AC/thermal integration is described in
[its source/frozen-worker evidence record](validation/EMERGE_RELEASE_INTEGRATION_20261023.md).
For an isolated verified worker build that preserves the current bundled worker:
`python scripts/build_packaged_worker.py --candidate-root build/<new-candidate>`.
The candidate directory must be fresh and inside build/. Normal release builds
also execute the new co-simulation probe and retain it in the worker manifest.
Building this candidate does not update published installers or qualify a release.

The worker requires both first-party native airflow and native CHT executables.
Build them with `python scripts/build_native_airflow.py`. For an isolated native
build, pass its executable directory to the worker builder using
`--native-kernel-dir build/<native-build>/Release` on Windows (or the executable
directory itself on Linux). Missing kernels fail before existing output is
replaced. Kernel inputs inside the worker output or build scratch tree are
rejected before cleanup, so a build cannot delete its own admitted inputs.
Both are collected into `_internal/native`; the build then executes
the native CHT conduction, incomplete-solve and moving-lid momentum probes.
The moving-lid probe requires the exact-rational independent momentum diagnostic,
nonzero retained flow and unchanged bundled native identity. Archived V1 results
without those diagnostics remain readable, but cannot satisfy fresh qualification.
This does not qualify
general geometry, turbulence or production CHT.

To stage a separately verified worker without replacing the current bundled
copy, `scripts/prepare_release_resources.py` accepts `--worker-root`,
`--stage-root build/<fresh-stage>` and `--config-output build/<config>.json`.
Custom stages must be fresh. Member integrity is checked before and after copy;
safe nested qualification-report paths are preserved. The existing installer
can consume that config with `-SkipWorker` because the worker has already been
built and verified; retain its tests (do not add `-SkipTests`). This is a preview
build workflow, not permission to bypass production signing or qualification.

GitHub Actions builds the Windows x64 installer, Linux x86-64 Flatpak, and macOS
DMGs for Apple Silicon and Intel. Each platform builds on a runner with the
matching operating system and architecture. Linux builds use the GNOME 50
Flatpak runtime.

## Build all packages

Open **Actions → Build and release SPIKE → Run workflow**. Leave **Publish**
unchecked to build and test without creating a release. The four packages and
their SHA-256 files appear under that run's artifacts and are retained for
14 days.

From the command line:

```sh
gh workflow run release.yml --repo wayri/SPIKE --ref main
```

## Publish a new version

Set the new version in `app/package.json`, `app/package-lock.json`,
`app/src/appVersion.ts`, `app/src-tauri/tauri.conf.json`, `app/src-tauri/Cargo.toml`,
the local application entry in `app/src-tauri/Cargo.lock`,
`python/spike_core/__init__.py`, and `CMakeLists.txt`. Commit the change, then
push a matching tag, for example:

```sh
git tag v0.3.2
git push origin main v0.3.2
```

Pushing a `v*` tag starts the complete build and publication chain. The tag must
match the application version. All four packages must pass before publication.
The workflow checks their hashes, uploads them to a draft release, then makes
the release visible. A failed upload leaves the draft unpublished, so the job
can be rerun. Published releases are not overwritten; use a new version for
different binaries.

For a manual release, use **Run workflow**, check **Publish**, and enter the
matching version tag. A new tag is created at the selected commit if necessary.
An existing tag must point to that commit.

## What the chain checks

- Version consistency across the desktop, CLI, and native build.
- Frozen-worker health and existing numerical runtime checks.
- Every CLI command's help, version, board inspection, and structured errors.
- Windows silent installation and its installed CLI launcher.
- Flatpak installation and its installed CLI launcher.
- macOS app signing and CLI launcher.
- Desktop startup, reinstall, and removal on each platform.
- Linux CLI and desktop startup with network access disabled.
- A complete set of four packages with matching SHA-256 checksums.

Source checks also run on pull requests and code changes to `main`, covering
architecture rules, frontend compilation, the board parser, CLI forwarding,
errors, schemas, and release publication failure cases.

The current Windows installer is unsigned. macOS packages are ad-hoc signed
without Apple notarization. Linux and macOS outputs remain experimental.
Optional external engines are installed separately.

## Linux and macOS candidate verification

Run the native Unix workflow on the intended release branch:

```sh
gh workflow run unix-release.yml --repo wayri/SPIKE --ref codex/release-v0.4.1 -f platform=all
```

| Target | Native runner | Package |
| --- | --- | --- |
| Linux x86-64 | Ubuntu 24.04 | Flatpak with GNOME 50 runtime |
| macOS Apple silicon | macOS 15 ARM64 | Experimental DMG |
| macOS Intel | macOS 15 x86-64 | Experimental DMG |

The Unix circuit worker records the actual pip installation transaction and its
SHA-256 instead of naming the Windows dependency lock. This report identifies
what that transaction installed; it is not a complete environment lock.

Before packaging, verify every main-worker and circuit-worker member against
its manifest, execute the supervised circuit smoke case, and verify the bytes
again after execution. macOS also checks the final signed app and the copy
installed from the mounted DMG. Signing must not silently invalidate worker
manifests. The installed CLI, reinstall/removal and desktop process survival
checks run on each native target. Process survival does not establish rendered
frontend readiness or visual acceptance.

Package artifacts and SHA-256 sidecars are retained for 14 days. Separate
`qualification-<runner>` artifacts retain dependency installation, platform,
source-commit and payload-verification evidence for 30 days. Download and retain
both when reviewing a candidate. A successful workflow does not replace the
required knowledgeable human numerical review or desktop visual acceptance.

## Local builds

The GitHub workflows call the same checked-in scripts used for local builds:

- Windows: `scripts/build_windows_ci.ps1`, from an x64 MSVC development shell.
- Linux/macOS: `scripts/build_unix_release.sh`, then `scripts/package_unix_release.py`.

These scripts install build dependencies and prepare resources in a disposable
checkout. Use a clean checkout; resource staging updates its Tauri configuration.
See [platform installation and CLI commands](PLATFORM_PACKAGES.md) for running
the finished packages.


## Stabilizing the Gamma candidate

The public `v0.3.11-gamma.1` installers and the current development checkout
are different source/artifact identities. The original Gamma installers have a
known missing-frontend packaging defect. Local repairs do not replace those
published downloads. Do not relabel that artifact as stable or long-term ready.
A stable candidate requires a frozen source identity, its own version and
checksums, complete regression results, required numerical/dependency reviews,
and actual supported-platform install/offline/upgrade/uninstall acceptance.
See [Windows acceptance](WINDOWS_INSTALLER.md#embedded-frontend-acceptance).

Windows CI now explicitly builds with `custom-protocol` and requires the fixed
inert native panel qualification to finish, with the development server absent.
Process survival alone is not frontend readiness. This check does not run the
normal workspace, a solver, or a clean-machine installer acceptance campaign.
