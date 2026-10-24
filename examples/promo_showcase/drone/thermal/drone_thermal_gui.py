# SPDX-License-Identifier: Apache-2.0
"""Run in SPIKE Python workspace with the actual IRIS board selected.
Physical inputs below are illustrative, not measured manufacturer losses.
"""
import json
import spike
REQUEST = {'ambient_temperature_c':25.,'board':{'model':'plate','conductivity_w_mk':3.,'thickness_mm':1.6,'grid_step_mm':3.,'convection_top_w_m2k':10.,'convection_bottom_w_m2k':10.},'components':[{'component_ref':ref,'power_w':power,'contact_mode':'pads','r_junction_case_k_w':2.,'r_case_board_k_w':5.} for ref,power in [('U33',.6),('U9',.2),('U15',.2)]]}
if not spike.design:
    raise ValueError('Select the imported IRIS board first.')
refs={c.get('reference') for c in spike.components.list()}
if not {'U33','U9','U15'}<=refs:
    raise ValueError('Expected actual U33/U9/U15 references are missing; use the pinned IRIS example.')
result=spike.analysis.run('run_board_thermal',{'design':spike.design,'request':REQUEST})
if result.get('status')!='completed':
    raise RuntimeError(json.dumps(result))
print('SPIKE_DRONE_THERMAL_RESULT='+json.dumps(result,allow_nan=False))
print('Actual registered run_board_thermal completed; steady homogeneous plate only.')

