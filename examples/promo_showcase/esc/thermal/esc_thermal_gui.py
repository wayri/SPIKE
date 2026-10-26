# SPDX-License-Identifier: Apache-2.0
"""Run in SPIKE Python workspace with the actual VESC board selected.
Physical inputs below are illustrative, not measured manufacturer losses.
"""
import json
import spike
REQUEST = {'ambient_temperature_c':25.,'board':{'model':'plate','conductivity_w_mk':3.,'thickness_mm':1.6,'grid_step_mm':3.,'convection_top_w_m2k':10.,'convection_bottom_w_m2k':10.},'components':[{'component_ref':'Q'+str(i),'power_w':.5,'contact_mode':'pads','r_junction_case_k_w':1.,'r_case_board_k_w':2.} for i in range(1,7)]}
if not spike.design:
    raise ValueError('Select the imported VESC BLDC_4 board first.')
refs={c.get('reference') for c in spike.components.list()}
if not {'Q1','Q2','Q3','Q4','Q5','Q6'}<=refs:
    raise ValueError('Expected actual Q1-Q6 references are missing; use the pinned VESC example.')
result=spike.analysis.run('run_board_thermal',{'design':spike.design,'request':REQUEST})
if result.get('status')!='completed':
    raise RuntimeError(json.dumps(result))
print('SPIKE_ESC_THERMAL_RESULT='+json.dumps(result,allow_nan=False))
print('Actual registered run_board_thermal completed; steady homogeneous plate only.')
