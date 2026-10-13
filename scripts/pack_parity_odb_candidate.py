# SPDX-License-Identifier: Apache-2.0
"""Deterministically package the original ODB candidate (not a native export)."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def pack(source: Path, target: Path) -> None:
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(p for p in source.rglob('*') if p.is_file()):
            member = zipfile.ZipInfo('job/' + path.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
            member.external_attr = 0o100644 << 16
            archive.writestr(member, path.read_bytes())


if __name__ == '__main__':
    pack(ROOT / 'benchmarks/parity-import/odb-candidate', ROOT / 'benchmarks/parity-import/odb-candidate.zip')
