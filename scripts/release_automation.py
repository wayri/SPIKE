# SPDX-License-Identifier: Apache-2.0
"""Check release versions and publish a complete set of verified packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def version(root: Path) -> str:
    app = json.loads((root / 'app/package.json').read_text())['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', app):
        raise ValueError('Application version must be a semantic version.')
    lock = json.loads((root / 'app/package-lock.json').read_text())
    values = {
        'package-lock': lock['version'],
        'package-lock root': lock['packages']['']['version'],
        'Tauri': json.loads((root / 'app/src-tauri/tauri.conf.json').read_text())['version'],
        'Cargo': tomllib.loads((root / 'app/src-tauri/Cargo.toml').read_text())['package']['version'],
        'Python': re.search(r'__version__\s*=\s*[\'"]([^\'"]+)',
                            (root / 'python/spike_core/__init__.py').read_text())[1],
    }
    for label, value in values.items():
        if value != app:
            raise ValueError(f'{label} version {value} differs from app version {app}.')
    ui = (root / 'app/src/appVersion.ts').read_text()
    if 'export const APP_VERSION = packageMetadata.version;' not in ui:
        literal = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)", ui)
        if literal is None or literal[1] != app:
            raise ValueError('UI version differs from app version.')
    native = re.search(r'project\(SPIKE VERSION ([^ ]+)', (root / 'CMakeLists.txt').read_text())[1]
    if native != app.split('-')[0]:
        raise ValueError('CMake version differs from the application version.')
    return app


def gh(*args: str, allow_missing: bool = False) -> str | None:
    result = subprocess.run(['gh', *args], text=True, capture_output=True)
    if result.returncode:
        if allow_missing and '404' in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip() or 'GitHub command failed.')
    return result.stdout


def tag_commit(repo: str, tag: str) -> str | None:
    raw = gh('api', f'repos/{repo}/git/ref/tags/{tag}', allow_missing=True)
    if raw is None:
        return None
    obj = json.loads(raw)['object']
    while obj['type'] == 'tag':
        obj = json.loads(gh('api', f'repos/{repo}/git/tags/{obj["sha"]}'))['object']
    if obj['type'] != 'commit':
        raise ValueError('Release tag does not identify a commit.')
    return obj['sha']


def check(root: Path = ROOT) -> dict[str, str]:
    release_version = version(root)
    tag = os.environ.get('RELEASE_TAG') or f'v{release_version}'
    if tag != f'v{release_version}':
        raise ValueError(f'Release tag must be v{release_version}; got {tag}.')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if os.environ.get('RELEASE_PUBLISH') == 'true':
        repo = os.environ['GITHUB_REPOSITORY']
        existing = tag_commit(repo, tag)
        if existing is not None and existing != commit:
            raise ValueError('The release tag points to another commit. Use a new version and tag.')
    result = {'version': release_version, 'tag': tag, 'commit': commit}
    if output := os.environ.get('GITHUB_OUTPUT'):
        with Path(output).open('a') as stream:
            stream.writelines(f'{key}={value}\n' for key, value in result.items())
    return result


def packages(folder: Path, release_version: str) -> list[Path]:
    names = [f'SPIKE_{release_version}_x64-setup.exe',
             f'SPIKE_{release_version}_linux-x86_64_EXPERIMENTAL.flatpak',
             f'SPIKE_{release_version}_macos-arm64_EXPERIMENTAL.dmg',
             f'SPIKE_{release_version}_macos-x86_64_EXPERIMENTAL.dmg']
    expected = {name for package in names for name in (package, package + '.sha256')}
    actual = {file.name for file in folder.iterdir() if file.is_file()}
    if actual != expected:
        raise ValueError(f'Incomplete package set: missing {sorted(expected-actual)}, unexpected {sorted(actual-expected)}')
    assets = []
    for name in names:
        file = folder / name
        checksum = folder / (name + '.sha256')
        digest, recorded_name = checksum.read_text().strip().split(maxsplit=1)
        with file.open('rb') as stream:
            actual_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if recorded_name != name or digest != actual_digest:
            raise ValueError(f'Checksum verification failed for {name}.')
        assets.extend([file, checksum])
    return assets


def publish(root: Path = ROOT) -> None:
    release_version = version(root)
    tag = os.environ['RELEASE_TAG']
    commit = os.environ['RELEASE_COMMIT']
    repo = os.environ['GITHUB_REPOSITORY']
    if tag != f'v{release_version}':
        raise ValueError('Release tag and application version differ.')
    assets = packages(root / 'dist-release', release_version)
    existing_commit = tag_commit(repo, tag)
    if existing_commit is not None and existing_commit != commit:
        raise ValueError('Release tag changed during the build.')
    releases = [item for page in json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/releases')) for item in page]
    existing = next((item for item in releases if item['tag_name'] == tag), None)
    if existing and not existing['draft']:
        raise ValueError('This release is already published. Create a new version to publish different binaries.')
    notes = (f'SPIKE {release_version} is a community preview for PCB power, signal, thermal, and electromagnetic analysis.\n\n'
             'Development is largely LLM-driven under human review. SPIKE is at a very early release stage '
             'and may have instabilities, bugs and incomplete behavior. The community is invited to test and provide feedback.\n\n'
             'Downloads include a Windows x64 installer, an experimental Linux x86-64 Flatpak, '
             'and experimental macOS DMGs for Apple Silicon and Intel. Each package includes the local analysis worker and command-line interface.\n\n'
             'The Windows installer is unsigned. macOS builds are ad-hoc signed without Apple notarization. '
             'Optional external solver engines are installed separately.\n\n'
             f'[Installation and CLI commands](https://github.com/{repo}/blob/{tag}/docs/PLATFORM_PACKAGES.md) '
             f'· [ESP32 walkthrough](https://github.com/{repo}/blob/{tag}/docs/ESP32_QUICKSTART.md)\n\n'
             'SHA-256 checksums are attached. SPIKE is a work in progress, provided AS IS without warranty or guarantee.\n')
    release_notes = root / 'docs' / 'releases' / f'v{release_version}.md'
    if release_notes.is_file():
        notes = release_notes.read_text(encoding='utf-8')
        # GitHub release text needs repository links rather than local doc paths.
        notes = re.sub(r'\]\((\.\.?/[^)]+)\)', lambda match:
                       '](' + f'https://github.com/{repo}/blob/{tag}/' +
                       str((release_notes.parent / match.group(1)).resolve().relative_to(root.resolve())).replace('\\', '/') + ')', notes)
    with tempfile.TemporaryDirectory() as directory:
        notes_path = Path(directory) / 'notes.md'
        notes_path.write_text(notes)
        if not existing:
            gh('release', 'create', tag, '--repo', repo, '--target', commit,
               '--draft', '--prerelease', '--title', f'SPIKE {release_version}', '--notes-file', str(notes_path))
        gh('release', 'upload', tag, '--repo', repo, *map(str, assets), '--clobber')
        gh('release', 'edit', tag, '--repo', repo, '--draft=false', '--prerelease', '--notes-file', str(notes_path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'verify', 'publish'])
    args = parser.parse_args()
    if args.command == 'check':
        print(json.dumps(check(), indent=2))
    elif args.command == 'verify':
        print(json.dumps([file.name for file in packages(ROOT / 'dist-release', version(ROOT))], indent=2))
    else:
        publish()
