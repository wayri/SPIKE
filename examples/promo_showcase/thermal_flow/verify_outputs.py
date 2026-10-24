# SPDX-License-Identifier: Apache-2.0
"""Independent volume/capacity energy arithmetic for the promo thermal outputs."""
from pathlib import Path
import json,numpy as np
ROOT=Path(__file__).resolve().parents[3];out=ROOT/'output/promo-showcase-20261023/thermal_flow';checks=[]
for name in ['case-contact','poor-contact']:
 read=lambda suffix:json.loads((out/f'{name}.{suffix}.json').read_text())
 r,s,t=read('request'),read('result'),read('transient');temp=np.asarray(s['field_result']['node_temperatures_k']);stored=0.;volume={};offset=0
 cap={m['material_id']:m['density_kg_m3']*m['specific_heat_j_kgk'] for m in t['material_heat_capacity']}
 for b in r['bodies']:
  xyz=np.asarray(b['mesh']['vertices'])*.001;total=0.
  for c in b['mesh']['cells']:
   ids=c['vertices'];v=abs(np.linalg.det((xyz[ids[1:]]-xyz[ids[0]]).T))/6;total+=v
   stored+=v*cap[b['material_map'][c['material_id']]]*(temp[np.asarray(ids)+offset].mean()-300)
  volume[b['occurrence_id']]=total;offset+=len(xyz)
 energy=s['field_result']['energy_balance'];error=abs(stored-(24-energy['convection_outward_j']))
 assert abs(volume['board']-6.4e-7)<1e-18
 assert abs(volume['case']-(28*28*12-24*24*8)*1e-9)<1e-17
 assert error<1e-7
 checks.append({'case':name,'tetra_integrated_volume_m3':volume,'independent_stored_energy_j':stored,'input_energy_j':24,'reported_convection_energy_j':energy['convection_outward_j'],'independent_energy_error_j':error})
(out/'independent-checks.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2)+'\n')
print('Independent volume and global capacity/energy checks passed')
