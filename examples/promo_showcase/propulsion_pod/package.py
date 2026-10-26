# SPDX-License-Identifier: Apache-2.0
"""Package the first pod build with native sources and truthful study evidence."""
from pathlib import Path
import hashlib, json, shutil, sys, zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from examples.promo_showcase.colocate_kicad_sources import colocate_tree
from python.spike_core.project_package import read_project

HERE = Path(__file__).parent
OUT = ROOT / 'output/promo-propulsion-pod-20261023'
PACK = OUT / 'READY_TO_OPEN'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

def tree(source, target):
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if path.is_file() and not any(part.startswith('.') or part == '__pycache__' for part in relative.parts):
            copy(path, target / relative)

def main():
    PACK.mkdir(parents=True, exist_ok=True)
    for area in ('assembly', 'electrical', 'thermal_geometry', 'kicad_checks', 'coupled', 'coupled_geometry'):
        assert (OUT / area / 'verification.json').is_file(), area
        tree(OUT / area, PACK / area)
    tree(HERE / 'electrical', PACK / 'electrical')
    tree(HERE / 'thermal_geometry', PACK / 'thermal_geometry')
    tree(HERE / 'coupled', PACK / 'coupled')
    for name in ('PROPULSION_POD_FIELD_DERIVATION_20261023.md',
                 'PROPULSION_POD_PROPELLER_DERIVATION_20261023.md',
                 'PROPULSION_POD_COUPLING_DERIVATION_20261023.md'):
        copy(ROOT / 'docs/validation' / name, PACK / 'EVIDENCE/numerical-methods' / name)
    for name in ('propulsion_pod.py', 'propulsion_pod_field.py', 'propulsion_pod_propeller.py',
                 'propulsion_pod_controller.py', 'service_propulsion_pod.py'):
        copy(ROOT / 'python/spike_core' / name, PACK / 'SOURCE/solver' / name)
    for name in ('build_assembly.py', 'check_kicad.py', 'package.py', 'START_HERE.md'):
        copy(HERE / name, PACK / name)
    previous = ROOT / 'output/promo-esc-20261023/thermal'
    copy(previous / 'vesc-steady-thermal.spike', PACK / 'board_thermal/vesc-steady-thermal.spike')
    for name in ('request.json', 'result.json', 'verification.json', 'blocked-transient-sink.json'):
        copy(previous / name, PACK / 'board_thermal/EVIDENCE' / name)
    copy(ROOT / 'examples/promo_showcase/esc/thermal/esc_thermal_gui.py', PACK / 'board_thermal/esc_thermal_gui.py')
    copy(ROOT / 'LICENSE', PACK / 'LICENSES/SPIKE-Apache-2.0.txt')
    copy(ROOT / 'NOTICE', PACK / 'LICENSES/SPIKE-NOTICE.txt')
    copy(ROOT / 'examples/promo_showcase/FLAGSHIP_SYSTEM.md', PACK / 'FLAGSHIP_SYSTEM.md')
    coordination = {'date': '2026-10-23', 'status': 'root implemented and independently reviewed actual C/FEM/BEM reference loop; app integration coordinated separately',
        'solver': {'title': 'Build modern SPIKE solver suite', 'thread_id': '019ffc9a-c85d-7250-818c-8f349f0821c6',
                   'requested': ['controller/current/FEM/torque/speed/backEMF closure', 'conservative loss coupling', 'rotating propeller and flight progression']},
        'multiboard': {'title': 'Add multi-board analysis support', 'thread_id': '01a0e89d-245b-7a62-ba36-12913d1c9f46',
                       'requested': ['native saved terminal bindings', 'guarded in-app runners', 'real fields/history and persistence']},
        'closed_loop_reference_benchmark_completed': True,
        'real_VESC_blade_CFD_pod_completed': False, 'whole_drone_completed': False}
    (PACK / 'coordination.json').write_text(json.dumps(coordination, indent=2) + '\n')
    colocate_tree(PACK)
    projects = []
    for path in sorted(PACK.rglob('*.spike')):
        opened = read_project(path, include_members=True)
        sidecar = json.loads(path.with_suffix('.sources.json').read_text())
        for member, data in opened.members.items():
            if member.endswith('.kicad_pcb'):
                assert any(candidate.read_bytes() == data for candidate in path.parent.glob('*.kicad_pcb'))
        projects.append({'path': path.relative_to(PACK).as_posix(), 'sha256': sha(path), 'native_readback': True,
                         'source_sidecar_present': bool(sidecar)})
    summary = {'native_projects': projects, 'source_colocation_checked': True,
        'assembly': json.loads((OUT / 'assembly/verification.json').read_text()),
        'electrical': json.loads((OUT / 'electrical/verification.json').read_text()),
        'thermal': json.loads((OUT / 'thermal_geometry/verification.json').read_text()),
        'kicad': json.loads((OUT / 'kicad_checks/verification.json').read_text()),
        'coupled': json.loads((OUT / 'coupled/verification.json').read_text()),
        'coupled_native_project': json.loads((OUT / 'coupled/native-project-verification.json').read_text()),
        'GUI_recording_executed': False, 'coupled_reference_benchmark_executed': True,
        'real_VESC_blade_CFD_propulsion_executed': False}
    (PACK / 'BUILD_VERIFICATION.json').write_text(json.dumps(summary, indent=2) + '\n')
    files = [{'path': path.relative_to(PACK).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size}
        for path in sorted(PACK.rglob('*')) if path.is_file() and path.name != 'SHA256.json']
    (PACK / 'SHA256.json').write_text(json.dumps(files, indent=2) + '\n')
    archive = OUT / 'SPIKE-restrained-propulsion-pod-coupled-benchmark-20261023.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(PACK.rglob('*')):
            if path.is_file():
                zipped.write(path, path.relative_to(PACK).as_posix())
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        for item in files:
            assert hashlib.sha256(zipped.read(item['path'])).hexdigest() == item['sha256']
    print(json.dumps({'archive': str(archive), 'files': len(files), 'bytes': archive.stat().st_size,
                      'sha256': sha(archive), 'integrity': 'passed', 'native_projects': len(projects)}))

if __name__ == '__main__':
    main()
