# Platform installation and command line

## 0.4.0-alpha.1 experimental release

SPIKE 0.4.0-alpha.1 is an experimental four-platform preview built from source
candidate `4f550c0f`. The earlier all-platform candidate run
[`39572252308`](https://github.com/wayri/SPIKE/actions/runs/39572252308)
passed. The [publication workflow](https://github.com/wayri/SPIKE/actions/runs/39584567090)
records the final package checks and publication outcome. The
[release page](https://github.com/wayri/SPIKE/releases/tag/v0.4.0-alpha.1)
is authoritative for the available attachments.

> [!WARNING]
> Knowledgeable human numerical and firmware review remains pending. Package
> availability, checksums, and passing automation do not qualify a solver,
> method, model, result, or platform for production engineering use.

The packages include the desktop app, Python runtime, native kernels, and
command-line interface. A separate Python installation is not needed.

| Platform | Release package | SHA-256 |
| --- | --- | --- |
| Windows x64 | [`SPIKE_0.4.0-alpha.1_x64-setup.exe`](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_x64-setup.exe) | [checksum](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_x64-setup.exe.sha256) |
| Linux x86-64 | [`SPIKE_0.4.0-alpha.1_linux-x86_64_EXPERIMENTAL.flatpak`](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_linux-x86_64_EXPERIMENTAL.flatpak) | [checksum](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_linux-x86_64_EXPERIMENTAL.flatpak.sha256) |
| macOS Apple silicon | [`SPIKE_0.4.0-alpha.1_macos-arm64_EXPERIMENTAL.dmg`](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_macos-arm64_EXPERIMENTAL.dmg) | [checksum](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_macos-arm64_EXPERIMENTAL.dmg.sha256) |
| macOS Intel | [`SPIKE_0.4.0-alpha.1_macos-x86_64_EXPERIMENTAL.dmg`](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_macos-x86_64_EXPERIMENTAL.dmg) | [checksum](https://github.com/wayri/SPIKE/releases/download/v0.4.0-alpha.1/SPIKE_0.4.0-alpha.1_macos-x86_64_EXPERIMENTAL.dmg.sha256) |

Verify the adjacent SHA-256 file before installing. Save and close open work
before an install or update.

## Windows x64

Run `SPIKE_0.4.0-alpha.1_x64-setup.exe` and choose the installer scope. The
standard per-user installation places the command launcher at:

```text
%LOCALAPPDATA%\Programs\SPIKE\spike.cmd
```

From PowerShell:

```powershell
& "$env:LOCALAPPDATA\Programs\SPIKE\spike.cmd" --help
& "$env:LOCALAPPDATA\Programs\SPIKE\spike.cmd" import C:\boards\example.kicad_pcb
```

If you select another install scope or directory, run `spike.cmd` from that
installation root. The Windows installer is **unsigned**; Windows may show an
unrecognized-app warning. Verify the checksum and publisher context before
continuing.

## Linux x86-64: Flatpak

With Flatpak installed, download the 0.4.0-alpha.1 package and run:

```sh
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user ./SPIKE_0.4.0-alpha.1_linux-x86_64_EXPERIMENTAL.flatpak
flatpak run org.spike.integrity
```

Flatpak downloads the runtime during the first installation. SPIKE can then run
locally without a network connection. The app can read and write your home
directory and uses the network for configured local model services and
extensions.

Run the packaged CLI with:

```sh
flatpak run --command=spike org.spike.integrity --help
flatpak run --command=spike org.spike.integrity import ~/boards/example.kicad_pcb
```

Optional external solvers remain separate installations. Flatpak isolates SPIKE
from host executables, so openEMS, EMerge, FreeCAD, OpenFOAM, SU2, ngspice, and
other engines installed on the host are not automatically available inside the
sandbox. Their availability depends on their own operating-system dependencies
and an admitted integration path. The same restriction applies to CLI extension
commands.

## macOS: Apple silicon or Intel

Choose the package that matches **About This Mac**:

| Mac hardware | Package |
| --- | --- |
| Apple M-series | `SPIKE_0.4.0-alpha.1_macos-arm64_EXPERIMENTAL.dmg` |
| Intel processor | `SPIKE_0.4.0-alpha.1_macos-x86_64_EXPERIMENTAL.dmg` |

Open the DMG and drag SPIKE into Applications. Both experimental packages are
built with a macOS 15 baseline; earlier macOS versions have not been tested.
They are ad-hoc signed and **not Apple-notarized**, so macOS may block the first
launch. After verifying the checksum, if you trust the package, attempt to open
it and then use **System Settings -> Privacy & Security -> Open Anyway**.

Run the packaged CLI with:

```sh
/Applications/SPIKE.app/Contents/MacOS/spike --help
/Applications/SPIKE.app/Contents/MacOS/spike import ~/boards/example.kicad_pcb
```

## Command-line behavior

The installed launchers use the same command parser and analysis backend as the
source CLI. See the [CLI guide](CLI.md) for analysis, reports, studies, and
automation. Package checks compare command help, version, board inspection, and
error behavior with the source CLI.

## Historical packages

Windows Gamma releases and 0.3.5 Linux/macOS packages are older artifacts from
different source identities. They do not contain the 0.4.0-alpha.1 candidate and
must not be relabeled as current four-platform packages. Use an older artifact
only when deliberately reproducing its recorded behavior and retain its original
version, checksum, and limitations.

## Building

The [automated build and release chain](BUILD_AND_RELEASE.md) generates the
Windows x64 installer, Linux x86-64 Flatpak, and macOS Apple silicon and Intel
DMGs. It runs from a matching version tag or from
**Actions -> Build and release SPIKE -> Run workflow**. All four packages and
their SHA-256 files must pass verification before publication; outputs are
stored in `dist-release`.
