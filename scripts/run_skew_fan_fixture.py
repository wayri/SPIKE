# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Execute a non-cuboidal sheared CHT fixture; no energy qualification claimed."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core import openfoam_fan_fixture as fixture_module
from python.spike_core.openfoam_mesh_geometry_audit import audit_mesh_geometry
from python.spike_core.openfoam_multiregion_execution import run_multiregion_case
from python.spike_core.sparselizard_process import run_adapter_process
from scripts.fan_wsl_scratch import ScratchRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')
    args = parser.parse_args()
    audits = {}
    # Local fixture interception only; original generator is restored immediately.
    # Existing fan code classifies x=0/10 sides BEFORE the transform, so capture
    # the neutral mesh at write time instead of changing its side selection.
    original_write = fixture_module.write_polymesh
    def write_sheared(neutral, destination):
        for point in neutral['mesh']['vertices']:
            point[0] += .5*point[2]
        neutral['mesh_evidence']['sha256'] = fixture_module._digest(neutral['mesh'])
        audits[neutral['region_id']] = audit_mesh_geometry(neutral['mesh'])
        return original_write(neutral,destination)
    with patch.object(fixture_module,'write_polymesh',side_effect=write_sheared):
        fixture = fixture_module.build_fan_heated_fixture(args.output,divisions=4,delta_t_s=.001,
                                                          end_time_s=1,write_interval_steps=1000)
    args.output.joinpath('fixture.json').write_text(json.dumps(fixture,indent=2),encoding='utf-8')
    args.output.joinpath('geometry-audit.json').write_text(json.dumps(audits,indent=2),encoding='utf-8')
    diagnostic = json.loads((args.output/'case/constant/geometryDiagnostic.json').read_text())
    if diagnostic['orthogonal_constant_k_diagnostic_enabled']:
        raise RuntimeError('Skew geometry incorrectly admitted as orthogonal')
    if args.prepare_only:
        print(json.dumps({'status':'prepared','audits':audits}))
        return 0
    count = 0
    def runner(command,**kwargs):
        nonlocal count
        count += 1
        kwargs['stream_limit_bytes'] = 128*1024**2
        result = run_adapter_process(command,**kwargs)
        (args.output/f'command-{count:02d}.json').write_text(json.dumps({'argv':command,**result}),encoding='utf-8')
        return result
    active = ScratchRunner(args.output/'case',runner)
    result = run_multiregion_case(args.output/'case',timeout_s=900,runner=active)
    result['geometry_diagnostics'] = audits
    result['retained_linux_scratch'] = active.remote
    result['open_flow_energy_qualified'] = False
    (args.output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    hashes = {str(p.relative_to(args.output)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(args.output.rglob('*')) if p.is_file()}
    (args.output/'artifact-sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'summary':result.get('summary'),'audits':audits}))
    return 0 if result['status']=='completed' else 1


if __name__=='__main__': raise SystemExit(main())
