# SPDX-License-Identifier: Apache-2.0
"""Compare a local Studio installation to its preserved frozen payload."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'standalone/spikes_project/studio/python'))
from spikes_studio.release_policy import qt_dependencies


def verify(payload, installed):
    payload = Path(payload).resolve(strict=True)
    installed = Path(installed).resolve(strict=True)
    if payload == installed:
        raise ValueError('Independent source payload and installation required')
    expected = sorted(path for path in payload.rglob('*') if path.is_file())
    if not expected or not (payload / 'SPIKES-Studio.exe').is_file():
        raise ValueError('Not a frozen Windows Studio payload')
    mismatches = []
    for source in expected:
        name = source.relative_to(payload)
        target = installed / name
        if not target.is_file() or target.stat().st_size != source.stat().st_size:
            mismatches.append(name.as_posix())
            continue
        with source.open('rb') as stream:
            original = hashlib.file_digest(stream, 'sha256').hexdigest()
        with target.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != original:
            mismatches.append(name.as_posix())
    forbidden = qt_dependencies(path.relative_to(installed).as_posix()
                                for path in installed.rglob('*') if path.is_file())
    return {'contract': 'spikes/local-install-payload-check/v1',
            'passed': not mismatches and not forbidden,
            'payload': str(payload), 'installed': str(installed),
            'files_compared': len(expected), 'mismatches': mismatches,
            'forbidden_qt_files': forbidden,
            'production_qualified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--installed', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.installed.resolve()):
        parser.error('Evidence output must be outside the installation')
    report = verify(args.payload, args.installed)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
