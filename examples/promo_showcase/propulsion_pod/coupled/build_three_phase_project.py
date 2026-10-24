# SPDX-License-Identifier: Apache-2.0
"""Retain the computed three-phase study with exact adjacent KiCad sources."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from python.spike_core.project_package import read_project, write_spike_package
from examples.promo_showcase.colocate_kicad_sources import colocate_tree


def main():
    base = ROOT / 'output/promo-propulsion-pod-20261023'
    folder = base / 'three_phase'
    result_path = folder / 'compiled-controller-fem-thermal-bem-result.json'
    result_bytes = result_path.read_bytes()
    result = json.loads(result_bytes)
    assert result['status'] == 'completed'
    original = read_project(base / 'coupled/restrained-propulsion-pod-coupled.spike', include_members=True)
    payload = original.payload
    payload['project']['name'] = 'Three-phase synthetic FEM / compiled C / electrothermal / hover BEM'
    payload.setdefault('extensions', {}).pop('spike.propulsion-pod-coupled-study', None)
    payload.setdefault('analysis', {})['propulsion_pod_three_phase'] = {
        'contract': 'spike/propulsion-pod-ui-study/v1', 'request': result['request'], 'result': result}
    payload['extensions']['spike.propulsion-pod-three-phase-study'] = {
        'contract': 'spike/propulsion-pod-three-phase-saved-study/v1',
        'request': result['request'], 'request_sha256': result['request_sha256'],
        'result_member': 'reports/artifacts/three-phase-result.json',
        'result_sha256': hashlib.sha256(result_bytes).hexdigest(),
        'state': 'completed_reference_benchmark',
        'scope': result['limitations'],
        'geometry_scope': 'Inherited synthetic envelope/context only; field mesh in result defines the winding regions.',
    }
    project = folder / 'restrained-pod-three-phase-electrothermal.spike'
    write_spike_package(project, payload, preserved_members=original.members,
                        report_artifacts={'three-phase-result.json': result_bytes}, application_version='source')
    reopened = read_project(project, include_members=True)
    assert reopened.members['reports/artifacts/three-phase-result.json'] == result_bytes
    colocate_tree(folder)
    assert project.with_suffix('.kicad_pcb').is_file() or any(folder.glob('*.kicad_pcb'))
    print(project)


if __name__ == '__main__':
    main()
