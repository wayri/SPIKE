# SPDX-License-Identifier: Apache-2.0
"""Execute the same Python Workspace child/runtime used by SPIKE and retain it."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod import DEFAULT_REQUEST
from python.spike_core.script_runtime import run_python_script
from python.spike_core.kicad_importer import import_kicad_design

HERE = Path(__file__).parent
OUT = ROOT / 'output/promo-propulsion-pod-20261023/coupled'
BOARD = ROOT / 'output/promo-esc-20261023/source/bldc-hardware-f1c65014d0caab5d99d888fc3025377861ac6ae2/design/BLDC_4.kicad_pcb'

def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    scratch = OUT / '.tmp'
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch.resolve())
    params = {'request': copy.deepcopy(DEFAULT_REQUEST)}
    save(HERE / 'worker-params.json', params)
    save(OUT / 'worker-params.json', params)
    result_path = OUT / 'actual-coupled-result-views-fixed.json'
    if result_path.exists():
        raise ValueError('Retain existing result: choose a fresh output directory before rerunning this evidence capture')
    code = (HERE / '01_run_coupled_pod.py').read_text()
    # Set workspace inputs, not result values. The exact guarded GUI runner then
    # invokes the actual registered worker, compiled C process and field/flow.
    code = code.replace("REQUEST_FILE = Path('worker-params.json')", 'REQUEST_FILE = Path('+repr(str((OUT / 'worker-params.json').resolve()))+')')
    code = code.replace('RESULT_FILE = None  # Optional NEW file; existing data is never overwritten.',
                        'RESULT_FILE = Path('+repr(str(result_path.resolve()))+')')
    # The isolated script has its own interpreter/temp cache. Use a writable
    # harness-local scratch folder; this does not alter the solver or its data.
    code = 'import tempfile\ntempfile.tempdir = '+repr(str(scratch.resolve()))+'\n'+code
    execution = run_python_script({'code': code, 'design': import_kicad_design(str(BOARD)).to_dict(),
        'working_directory': str(HERE.resolve()), 'filename': '01_run_coupled_pod.py', 'timeout_seconds': 180})
    save(OUT / 'python-workspace-execution.json', execution)
    if execution['status'] != 'completed':
        raise RuntimeError(json.dumps(execution)[:2000])
    marker = 'SPIKE_COUPLED_POD_SUMMARY='
    summary = json.loads(next(line[len(marker):] for line in execution['stdout'].splitlines() if line.startswith(marker)))
    summary['GUI_interactive_recording_executed'] = False
    summary['execution_path'] = 'registered worker via actual Python Workspace child runtime'
    summary['source_board_sha256'] = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    summary['result_sha256'] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    summary['data_views_returned'] = len(execution.get('views', []))
    save(OUT / 'verification.json', summary)
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
