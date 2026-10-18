# SPDX-License-Identifier: Apache-2.0
"""Original synthetic one-metre slab: actual AC loss and steady temperature."""
import argparse
import copy
import itertools
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from python.spike_core.pdn_dielectric_thermal import run_pdn_dielectric_thermal


def setup(n=4):
    xyz=[[i/n,j/n,k/n] for i,j,k in itertools.product(range(n+1),repeat=3)]
    index={tuple(p):i for i,p in enumerate(xyz)}
    cells=[]
    for start in itertools.product(range(n),repeat=3):
        for axes in itertools.permutations(range(3)):
            p=list(start); vertices=[index[tuple(v/n for v in p)]]
            for axis in axes:
                p[axis]+=1;vertices.append(index[tuple(v/n for v in p)])
            points=np.array([xyz[i] for i in vertices])
            if np.linalg.det((points[1:]-points[0]).T)<0:vertices[1],vertices[2]=vertices[2],vertices[1]
            cells.append({'id':str(len(cells)),'kind':'tetrahedron','vertices':vertices,
                          'material_id':'bulk','source_object_ids':['synthetic-slab']})
    mesh={'contract':'spike/solver-mesh/v1','units':'m','coordinate_system':'right_handed_xyz',
          'vertices':xyz,'cells':cells,'counts':{'vertices':len(xyz),'cells':len(cells)},
          'object_map':{'synthetic-slab':{'kind':'solid'}}}
    faces={}
    for cell in cells:
        for face in itertools.combinations(cell['vertices'],3):
            key=tuple(sorted(face));faces[key]=faces.get(key,0)+1
    boundaries=[{'id':'face-'+str(i),'type':'temperature','vertices':list(face),'temperature_k':300.}
        for i,(face,count) in enumerate(faces.items()) if count==1
        and any(all(xyz[v][0]==side for v in face) for side in (0.,1.))]
    electrical={'contract':'spike/pdn-dielectric-ac-request/v1','mesh':mesh,
        'materials':[{'id':'bulk','permittivity_f_m':1e-6,'conductivity_s_m':.5,'loss_tangent':.05}],
        'electrodes':[{'id':label,'node':label,'vertices':[i for i,p in enumerate(xyz) if p[0]==side]}
                      for label,side in (('return',0.),('signal',1.))],
        'reference_electrode':'return','outer_boundary':'insulating','context_digest':'c'*64,'frequencies_hz':[1000.]}
    thermal={'contract':'spike/assembly-tetra-thermal-request/v1','mesh':copy.deepcopy(mesh),
        'materials':[{'id':'bulk','thermal_conductivity_w_mk':1.}], 'boundaries':boundaries}
    return {'contract':'spike/pdn-dielectric-thermal-request/v1','electrical_request':electrical,
        'drive':{'frequency_hz':1000.,'voltages_v':{'signal':{'real':10.,'imag':0.}}},'thermal_request':thermal}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plot',action='store_true')
    args=parser.parse_args(); request=setup(); result=run_pdn_dielectric_thermal(request)
    output=ROOT/'build/pdn-dielectric-thermal-example';output.mkdir(parents=True,exist_ok=True)
    for name,data in (('request',request),('result',result)):
        (output/(name+'.json')).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temperature=np.array(result['thermal_result']['node_temperatures_k'])
    print(json.dumps({'port_power_w':result['port_power_w'],'cell_power_w':result['total_dielectric_power_w'],
        'peak_temperature_k':float(temperature.max()),'coupling_mode':result['coupling_mode'],
        'result_path':str(output/'result.json')}))
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        points=np.array(request['electrical_request']['mesh']['vertices'])
        fig=plt.figure(figsize=(11.5,5),layout='constrained')
        left=fig.add_subplot(121,projection='3d')
        dots=left.scatter(*points.T,c=temperature,cmap='inferno',s=24)
        left.set(xlabel='x (m)',ylabel='y (m)',zlabel='z (m)',title='Computed retained-node temperature')
        fig.colorbar(dots,ax=left,label='Temperature (K)',shrink=.65,location='left',pad=.08)
        right=fig.add_subplot(122);x=np.linspace(0,1,200)
        q=result['total_dielectric_power_w'] # One cubic metre; uniform reference source.
        right.plot(x,300+q*x*(1-x)/2,'k--',label='Independent uniform-slab reference')
        right.scatter(points[:,0],temperature,s=14,label='Actual P1 thermal nodes')
        right.set(xlabel='x (m)',ylabel='Temperature (K)',title=f'Port power = heat: {q:.4f} W')
        right.legend(fontsize=8)
        fig.suptitle('Synthetic dielectric AC → heat → steady temperature | one-way, experimental')
        fig.savefig(output/'temperature.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
