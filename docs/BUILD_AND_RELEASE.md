# Building SPIKE

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
gh workflow run release.yml --repo wayri/SPIKE-Main --ref main
```

## Publish a new version

Set the new version in `app/package.json`, `app/package-lock.json`,
`app/src-tauri/tauri.conf.json`, `app/src-tauri/Cargo.toml`,
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

## Local builds

The GitHub workflows call the same checked-in scripts used for local builds:

- Windows: `scripts/build_windows_ci.ps1`, from an x64 MSVC development shell.
- Linux/macOS: `scripts/build_unix_release.sh`, then `scripts/package_unix_release.py`.

These scripts install build dependencies and prepare resources in a disposable
checkout. Use a clean checkout; resource staging updates its Tauri configuration.
See [platform installation and CLI commands](PLATFORM_PACKAGES.md) for running
the finished packages.
