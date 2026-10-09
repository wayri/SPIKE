# SPDX-License-Identifier: Apache-2.0
"""Package an already built desktop and its CLI as a Flatpak or macOS DMG."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / 'app/package.json').read_text())['version']
OUT = ROOT / 'dist-release'
OUT.mkdir(exist_ok=True)


def run(*args):
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True)


def launcher(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\nset -eu\n' + body + '\n')
    path.chmod(0o755)


if platform.system() == 'Darwin':
    app = ROOT / 'app/src-tauri/target/release/bundle/macos/SPIKE.app'
    launcher(app / 'Contents/MacOS/spike',
             'resource_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../Resources" && pwd)"\n'
             'export SPIKE_HOME="$resource_dir" SPIKE_WORKSPACE="$resource_dir"\n'
             'exec "$resource_dir/bundled/spike-worker/spike-worker" --cli "$@"')
    run('python', 'scripts/verify_packaged_cli.py', '--', app / 'Contents/MacOS/spike')
    run('codesign', '--force', '--deep', '--sign', '-', app)
    run('codesign', '--verify', '--deep', '--strict', app)
    staging = ROOT / 'build/dmg-root'
    staging.mkdir(exist_ok=True)
    shutil.copytree(app, staging / 'SPIKE.app', symlinks=True)
    (staging / 'Applications').symlink_to('/Applications')
    artifact = OUT / f'SPIKE_{VERSION}_macos-{platform.machine()}_EXPERIMENTAL.dmg'
    run('hdiutil', 'create', '-volname', 'SPIKE', '-srcfolder', staging, '-ov', '-format', 'UDZO', artifact)
else:
    deb = next((ROOT / 'app/src-tauri/target/release/bundle/deb').glob('*.deb'))
    unpacked = ROOT / 'build/deb-unpacked'
    run('dpkg-deb', '-x', deb, unpacked)
    resources = next(unpacked.rglob('bundled/spike-worker/spike-worker')).parents[2]
    bundle = ROOT / 'build/flatpak-app'
    run('flatpak', 'build-init', bundle, 'org.spike.integrity', 'org.gnome.Sdk', 'org.gnome.Platform', '50')
    files = bundle / 'files'
    shutil.copytree(resources, files / 'lib/spike')
    (files / 'bin').mkdir(exist_ok=True)
    shutil.copy2(unpacked / 'usr/bin/spike-desktop', files / 'bin/spike-desktop')
    for name, command in [('spike', '/app/lib/spike/bundled/spike-worker/spike-worker --cli'),
                          ('spike-gui', '/app/bin/spike-desktop')]:
        launcher(files / 'bin' / name,
                 'export SPIKE_HOME=/app/lib/spike SPIKE_WORKSPACE=/app/lib/spike\n'
                 f'exec {command} "$@"')
    desktop = files / 'share/applications/org.spike.integrity.desktop'
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=SPIKE\nComment=PCB analysis for KiCad\n'
                       'Exec=spike-gui %f\nIcon=org.spike.integrity\nCategories=Science;Electronics;\n'
                       'MimeType=application/x-spike-project;\nTerminal=false\n')
    icon = files / 'share/icons/hicolor/128x128/apps/org.spike.integrity.png'
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'app/src-tauri/icons/128x128.png', icon)
    mime_icon = files / 'share/icons/hicolor/128x128/mimetypes/application-x-spike-project.png'
    mime_icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'app/src-tauri/icons/128x128.png', mime_icon)
    mime = files / 'share/mime/packages/org.spike.integrity.xml'
    mime.parent.mkdir(parents=True, exist_ok=True)
    mime.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
                    '  <mime-type type="application/x-spike-project">\n'
                    '    <comment>SPIKE project package</comment>\n'
                    '    <glob pattern="*.spike"/>\n'
                    '    <icon name="application-x-spike-project"/>\n'
                    '  </mime-type>\n</mime-info>\n')
    run('flatpak', 'build-finish', bundle, '--command=spike-gui', '--socket=wayland',
        '--socket=fallback-x11', '--share=ipc', '--device=dri', '--share=network', '--filesystem=home')
    repo = ROOT / 'build/flatpak-repo'
    run('flatpak', 'build-export', repo, bundle)
    artifact = OUT / f'SPIKE_{VERSION}_linux-x86_64_EXPERIMENTAL.flatpak'
    run('flatpak', 'build-bundle', '--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo',
        repo, artifact, 'org.spike.integrity')
    run('flatpak', 'install', '--user', '--noninteractive', '--assumeyes', artifact)
    run('python', 'scripts/verify_packaged_cli.py', '--', 'flatpak', 'run', '--command=spike', 'org.spike.integrity')

checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
artifact.with_suffix(artifact.suffix + '.sha256').write_text(f'{checksum}  {artifact.name}\n')
print(artifact)
