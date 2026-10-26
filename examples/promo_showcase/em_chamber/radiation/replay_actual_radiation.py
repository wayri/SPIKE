# SPDX-License-Identifier: Apache-2.0
"""Replay the retained real EMerge result in the GUI; does not run a new solve."""
import json
import math
from pathlib import Path
import spike

# Run with the repository root as working directory; select the exact antenna fixture.
root=Path.cwd()
path=root/'output/promo-em-chamber-20261023/radiation/admitted-result.json'
result=json.loads(path.read_text(encoding='utf-8'))
assert spike.design['design_id']==result['provenance']['design_id'], 'Select the original antenna_example board.'
result['provenance']['script_upstream_extension_id']='spike.emerge-suite'
spike.publish_result(result)
network=result['networks']['s_parameters'];radiation=result['fields']['radiation']
s11=[20*math.log10(max(math.hypot(*m[0][0]),1e-30)) for m in network['values']]
spike.publish_plot('Actual EMerge antenna result: port reflection',[f/1e9 for f in network['frequencies_hz']],
    [{'name':'S11','values':s11}],x_label='Frequency',x_unit='GHz',y_label='Port reflection',y_unit='dB',
    provenance='Replay of freshly executed23Oct2026 EMerge3.0.0a19 result; unvalidated')
cut=radiation['cuts'][0]
spike.publish_plot('Actual normalized radiation cut:3GHz',cut['angles_deg'],
    [{'name':'Relative E amplitude','values':cut['relative_amplitude_db']}],x_label='Theta',x_unit='deg',y_label='Relative amplitude',y_unit='dB',
    provenance='Actual solver angular samples; normalized to peak, not calibrated gain/emissions')
spike.publish_table('EM chamber / radiation scope',['Item','State'],
    [['Solver result',result['model_status']],['EM chamber','Visual test setup only'],['Pattern','Relative normalized amplitude; no calibrated gain/power'],
     ['Omissions','Chamber reflections/absorbers/receiver transfer, physical RI and EMI compliance'],
     ['Warnings',', '.join(x['code'] for x in result['issues'])]],
    provenance='Retained exact original antenna fixture; no chamber-EM solve')
print('Replayed retained real EMerge result; no new solve. Model status:',result['model_status'])
