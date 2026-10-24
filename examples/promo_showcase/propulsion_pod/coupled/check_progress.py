# SPDX-License-Identifier: Apache-2.0
"""Capture real worker admission evidence without claiming a coupled solve."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from python.spike_core.automation import SpikeAutomation, SpikeAutomationError
from python.spike_core.project_package import read_project

OUT = ROOT / 'output/promo-propulsion-pod-20261023/coupled'
PROJECT = ROOT / 'output/promo-propulsion-pod-20261023/assembly/restrained-propulsion-pod.spike'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    api = SpikeAutomation()
    before = sha(PROJECT)
    catalog = api.call('cfd_capabilities')
    # A negative admission probe on the existing public route, not a proposed
    # future API or an attempt to pass a prescribed-current run off as coupled.
    request = json.loads((ROOT / 'examples/em_machines/planar_pm_fem.json').read_text())
    request['controller'] = {'purpose': 'admission probe only; not a model'}
    try:
        value = api.call_response('run_magnetic_machine', {'request': copy.deepcopy(request)})
        drive_probe = {'request': request, 'unexpected_acceptance': True, 'response': value}
    except SpikeAutomationError as exc:
        drive_probe = {'request': request, 'rejected': True, 'response': exc.response, 'message': str(exc)}
    opened = read_project(PROJECT, include_members=True)
    inventory = opened.payload['extensions']['spike.promo-propulsion-pod']
    assert sha(PROJECT) == before
    files = ['python/spike_core/magnetic_machine_study.py', 'python/spike_core/magnetic_fem.py',
             'python/spike_core/machine_geometry.py', 'python/spike_core/service_simulation_handlers.py',
             'python/spike_core/service_cfd.py', 'python/spike_core/enclosure_rotating_frame.py']
    coupled = api.call('propulsion_pod_capabilities')
    current_evidence = OUT / 'verification.json'
    evidence = json.loads(current_evidence.read_text()) if current_evidence.is_file() else None
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'coupled_reference_worker_implemented',
        'complete_simulation_executed_by_this_probe': False,
        'new_coupled_worker': coupled,
        'separate_executed_coupled_evidence': evidence,
        'motor_drive_admission_probe': drive_probe, 'actual_worker_cfd_catalog': catalog,
        'source_snapshot': [{'path': name, 'sha256': sha(ROOT / name)} for name in files],
        'project_sha256': before, 'project_unchanged': True,
        'active_motor_bindings': inventory['active_motor_terminal_bindings'],
        'physical_motor_winding_dataset_present': inventory['motor_winding_geometry'] is not None,
        'physical_propeller_dataset_present': inventory['propeller_geometry_and_reference_data'] is not None,
        'remaining_scope': ['real VESC three-phase winding/controller data and switching model',
            'blade-resolved CFD/rotor-stationary interface', 'temperature and enclosure/flight integration'],
        'scope': 'Legacy route rejection remains correct but does not describe the new coupled benchmark route. This probe checks admission and source state only.'}
    (OUT / 'progress.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'drive_probe_rejected': drive_probe.get('rejected', False),
                      'project_unchanged': report['project_unchanged'], 'report': str(OUT / 'progress.json')}))

if __name__ == '__main__':
    main()
