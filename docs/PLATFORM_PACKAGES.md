# Platform installation and command line

## Windows Gamma preview

The current Windows x64 Gamma prerelease is
[0.3.12-gamma.1](https://github.com/wayri/SPIKE/releases/tag/v0.3.12-gamma.1).
Use the attached EXE or MSI and verify its SHA-256 checksum. It is unsigned;
numerical human review and clean-machine qualification remain pending. Save and
close your work before installing. This release does not refresh Linux or macOS.

## Earlier experimental Linux and macOS packages

The experimental platform packages include the desktop app, Python runtime,
native kernels, and command-line interface. A separate Python installation is
not needed.

## Linux: Flatpak

Download the `.flatpak` file from the [0.3.5 release](https://github.com/wayri/SPIKE/releases/tag/v0.3.5).
With Flatpak installed, run:

```sh
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user ./SPIKE_0.3.5_linux-x86_64_EXPERIMENTAL.flatpak
flatpak run org.spike.integrity
```

The package is for x86-64 Linux. Flatpak downloads
the runtime on first installation. SPIKE can then run locally without a network
connection. The app can read and write your home directory and uses the network
for configured local model services and extensions.

## macOS: DMG

Use the earlier 0.3.5 `macos-arm64` package for Apple Silicon. Intel macOS
packaging is held; no verified Intel package is claimed. Open the DMG and drag
SPIKE into Applications. The recorded build baseline is macOS 15; earlier
versions have not been tested.

These experimental builds are ad-hoc signed, without Apple notarization.
macOS may block the first launch. If you trust the downloaded file, use
**System Settings → Privacy & Security → Open Anyway** after attempting to open it.

## Command line

Linux:

```sh
flatpak run --command=spike org.spike.integrity --help
flatpak run --command=spike org.spike.integrity import ~/boards/example.kicad_pcb
```

macOS:

```sh
/Applications/SPIKE.app/Contents/MacOS/spike --help
/Applications/SPIKE.app/Contents/MacOS/spike import ~/boards/example.kicad_pcb
```

Both launchers use the same command parser and analysis backend as the source
CLI. See the [CLI guide](CLI.md) for analysis, reports, studies, and automation.
Build checks compare every command's help, version, board inspection, and error
output with the source CLI.

Optional external solvers are separate installations. Their availability depends
on the operating system and their own dependencies. Flatpak isolates SPIKE from
host executables: a solver installed on the host is not automatically available
inside the sandbox. This restriction also applies to CLI extension commands.

## Building

The [automated build and release chain](BUILD_AND_RELEASE.md) generates the
Windows installer and experimental Unix packages. Gamma tags are excluded from
the automatic multi-platform publication chain; their platform-specific build
evidence must be recorded separately. The general chain runs on other version tags or from
**Actions - Build and release SPIKE - Run workflow**. The resulting packages
and SHA-256 files are stored in `dist-release`.
