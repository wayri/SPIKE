# SPDX-License-Identifier: Apache-2.0
"""Launch the registered EMerge radiation contribution from the GUI workspace."""
import json
from pathlib import Path
import spike
root=Path.cwd()
config=json.loads((root/'examples/emerge/antenna_run.json').read_text())
assert spike.design['name']=='antenna_example', 'Import and select the original antenna_example.kicad_pcb.'
parameters={**config['parameters'],'python_executable':str((root/'.venv-emerge3/Scripts/python.exe').resolve())}
assert Path(parameters['python_executable']).is_file(), 'Set python_executable to your installed supported EMerge interpreter.'
# Trust the bundled EMerge Suite in Extension Manager before running; no trust bypass.
envelope=spike.invoke_extension('spike.emerge-suite','emerge-radiation',parameters)
result=envelope['data']['analysis_result']
print('Fresh registered EMerge radiation execution:',result['status'],result['model_status'])
print('Chamber is visual only; this result is unvalidated relative normalized antenna radiation, not EMI/RI qualification.')
