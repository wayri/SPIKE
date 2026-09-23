# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Run real openEMS and preserve an explicitly imperfect measured comparison."""
import argparse
import hashlib
import json
import os
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.external_engines import _run_isolated_python
from python.spike_core.runtime_locations import openems_python, openems_install_root
from python.spike_core.antenna_measured_comparison import compare_forward_gain, evaluate_temporal_admission

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mesh-mm',type=float,choices=[10,15,20],default=20)
    args=parser.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).with_name('nbs_yagi_openems_worker.py').read_bytes()
    env=os.environ.copy(); env['OPENEMS_INSTALL_PATH']=openems_install_root()
    try:
        result=_run_isolated_python(openems_python(),source,[str(out),str(args.mesh_mm)],cwd=out,
            environment=env,log_path=out/'solver.log',output_root=out,timeout_seconds=900,output_limit_bytes=1024**3)
    except Exception as error:
        result={'returncode':-1,'status':'execution_failed','error_type':type(error).__name__,
                'error':str(error),'process_tree_cleanup_verified':False}
    result.update(contract='spike/nbs-yagi-exploratory-comparison/v1',
        primary_source='https://doi.org/10.6028/NBS.TN.688', source_table='Table 1, 0.4 wavelength antenna',
        worker_sha256=hashlib.sha256(source).hexdigest(),
        runtime_sha256=hashlib.sha256(Path(openems_python()).read_bytes()).hexdigest(),
        measured_qualification=False, note='Real FDTD comparison; simplified feed/range prevents matched-geometry qualification')
    if (out/'solver-result.json').exists():
        result['analysis']=json.loads((out/'solver-result.json').read_text())
        a=result['analysis']
        result['power_definition_check']=compare_forward_gain(
            radiation_intensity_w_sr=10**(a['forward_directivity_dbi']/10)*a['radiated_power_w']/(4*math.pi),
            accepted_power_w=a['accepted_power_w'],radiated_power_w=a['radiated_power_w'],
            measured_gain_dbd=7.1,dbd_to_dbi_db=2.16,measurement_accuracy_db=.5)
        result['numerical_admission']=evaluate_temporal_admission((out/'solver.log').read_text(errors='replace'),
            a['radiated_to_accepted_ratio'])
    result['artifact_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in out.rglob('*') if p.is_file()}
    (out/'comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({key:result.get(key) for key in ['returncode','timed_out','analysis']}))
    return 0 if result['returncode']==0 and result.get('numerical_admission',{}).get('status')=='exploratory_only' else 1

if __name__=='__main__':
    raise SystemExit(main())
