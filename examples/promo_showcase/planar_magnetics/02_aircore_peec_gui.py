# SPDX-License-Identifier: Apache-2.0
import spike,json
SPEC={'mode': 'ac', 'solver_id': 'spike.peec_2_5d', 'formulation': 'peec_2_5d', 'net_names': ['AIRCORE_WINDING'], 'sources': [{'id': 'winding-0', 'net': 'AIRCORE_WINDING', 'position_mm': [-17.0, -1.27], 'layer': 'F.Cu'}], 'loads': [{'id': 'winding-1', 'net': 'AIRCORE_WINDING', 'position_mm': [-17.0, 1.27], 'layer': 'B.Cu'}], 'frequency_start_hz': 1000, 'frequency_stop_hz': 100000, 'frequency_points': 5, 'mesh': {'target_size_mm': 3.0, 'max_preview_cells': 1200}, 'options': {'conductor_models': {'skin_effect': True, 'surface_roughness_model': 'none'}}}
assert spike.design and spike.design['design_id']=='kicad-c4489150f05a0b2486be11a2', "Open the original aircore_inductor board"
result=spike.analysis.run('run_analysis',{'design':spike.design,'spec':SPEC})
print('RESULT_JSON='+json.dumps(result))
if result['status']=='completed':
    spike.publish_table('Actual air-core PEEC extraction',['Quantity','Value'],
      [[key,json.dumps(value)] for key,value in result['summary'].items()],
      provenance='Registered native PEEC, explicit F.Cu entry and B.Cu exit; partial inductance, no ferrite core')
