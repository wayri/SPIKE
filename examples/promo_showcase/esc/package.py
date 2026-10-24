# SPDX-License-Identifier: Apache-2.0
"""Assemble the inspected ESC examples, source notices and retained evidence."""
from pathlib import Path
import hashlib, json, shutil, zipfile, sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from examples.promo_showcase.colocate_kicad_sources import colocate_tree
HERE = Path(__file__).parent
OUT = ROOT / 'output/promo-esc-20261023'
PACK = OUT / 'READY_TO_OPEN'
REV = 'f1c65014d0caab5d99d888fc3025377861ac6ae2'
SOURCE = OUT / 'source' / ('bldc-hardware-' + REV)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

def main():
    PACK.mkdir(parents=True, exist_ok=True)
    for area in ('studio', 'analytics', 'thermal'):
        assert (OUT / area / 'verification.json').exists(), area
        for p in (HERE / area).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                copy(p, PACK / area / p.relative_to(HERE / area))
        for p in (OUT / area).rglob('*'):
            if p.is_file() and not any(x.startswith('.') or x == '__pycache__' for x in p.relative_to(OUT / area).parts):
                copy(p, PACK / 'EVIDENCE' / area / p.relative_to(OUT / area))
                if p.suffix == '.spike':
                    copy(p, PACK / 'thermal' / p.relative_to(OUT / area))
    # Preserve the hardware license boundary; exclude unneeded third-party 3D libraries.
    for p in (SOURCE / 'design').iterdir():
        if p.is_file() and p.suffix in ('.sch', '.net', '.kicad_pcb', '.lib', '.pro', '.ods', '.pdf'):
            copy(p, PACK / 'VESC_HARDWARE_CC_BY_SA' / p.name)
    copy(SOURCE / 'README.md', PACK / 'VESC_HARDWARE_CC_BY_SA' / 'UPSTREAM_README.md')
    copy(OUT / 'source/CC-BY-SA-4.0.txt', PACK / 'VESC_HARDWARE_CC_BY_SA/CC-BY-SA-4.0.txt')
    copy(ROOT / 'LICENSE', PACK / 'LICENSES/SPIKE-Apache-2.0.txt')
    copy(ROOT / 'NOTICE', PACK / 'LICENSES/SPIKE-NOTICE.txt')
    for name in ('START_HERE.md', 'ATTRIBUTION.md'):
        copy(HERE / name, PACK / name)
    provenance = {'source': 'https://github.com/vedderb/bldc-hardware', 'revision': REV,
                  'owner': 'Benjamin Vedder and upstream contributors', 'license': 'CC-BY-SA-4.0',
                  'upstream_archive_sha256': sha(OUT / 'source/vesc-hardware.zip'),
                  'source_board_sha256': sha(SOURCE / 'design/BLDC_4.kicad_pcb'),
                  'license_basis': 'Pinned upstream README explicitly licenses VESC Hardware under CC BY-SA 4.0.',
                  'excluded': ['upstream firmware', 'external 3D model libraries', 'native solver binaries'],
                  'production_qualified': False, 'gui_recorded': False}
    (PACK / 'source-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    colocate_tree(PACK)
    files = [{'path': p.relative_to(PACK).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}
             for p in sorted(PACK.rglob('*')) if p.is_file() and p.name != 'SHA256.json']
    (PACK / 'SHA256.json').write_text(json.dumps(files, indent=2)+'\n')
    archive = OUT / 'SPIKE-ESC-Studio-examples-20261023.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PACK.rglob('*')):
            if p.is_file(): z.write(p, p.relative_to(PACK).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for item in files:
            assert hashlib.sha256(z.read(item['path'])).hexdigest() == item['sha256']
    print(json.dumps({'archive': str(archive), 'files': len(files), 'bytes': archive.stat().st_size,
                      'archive_sha256': sha(archive), 'archive_integrity': 'passed'}))

if __name__ == '__main__': main()
