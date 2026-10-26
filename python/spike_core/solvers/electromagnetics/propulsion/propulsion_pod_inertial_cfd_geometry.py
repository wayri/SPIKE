# SPDX-License-Identifier: Apache-2.0
"""Original graded conforming blade meshes for inertial CFD verification."""
import itertools
import math
import numpy as np


def build_reference_mesh(*,level=0,pitch_rad=.2,domain_radius_m=.08,domain_half_length_m=.08):
    """Closed two-half twisted plate in a faceted coaxial cylindrical vessel.

    Blade dimensions before smooth twisting: x thickness2mm, y span60mm,
    z chord10mm. Actual triangular surface geometry is returned explicitly.
    This is original benchmark geometry, not ENOLA/real-hardware CAD.
    """
    if level not in (0,1,2):raise ValueError('level must be0,1,2')
    B=float(domain_radius_m);L=float(domain_half_length_m)
    if not .06<=B<=.24 or not .05<=L<=.24 or abs(pitch_rad)>.25:raise ValueError('Original domain bounds exceeded')
    if level==0:
        xp=np.array([.001,.002,.006,.02,L]);yp=np.array([0.,.015,.03,.05,B]);zp=np.array([.005,.01,.025,B])
    elif level==1:
        xp=np.array([.001,.0015,.0025,.0045,.008,.016,.032,L]);yp=np.array([0.,.015,.03,.05,B]);zp=np.array([.005,.0075,.0125,.025,B])
    else:
        xp=np.array([.001,.00125,.00175,.0025,.004,.0065,.011,.02,.035,L]);yp=np.array([0.,.005,.01,.015,.02,.025,.03,.04,.055,B]);zp=np.array([.0025,.005,.00625,.00875,.013,.022,.04,B])
    axes=[np.r_[-xp[::-1],xp],np.r_[-yp[:0:-1],yp],np.r_[-zp[::-1],zp]]
    coords=list(itertools.product(*[range(len(a)) for a in axes]));lookup={c:i for i,c in enumerate(coords)}
    original=np.array([[axes[k][c[k]] for k in range(3)] for c in coords]);xyz=original.copy()
    for i,(x,y,z) in enumerate(original):
        # The inner rotor is unaffected by domain-size changes. Outer square
        # becomes an exactly cylindrical continuous map (faceted by mesh).
        radial=max(abs(y),abs(z));blend=max(0.,min(1.,(radial-.032)/(B-.032)))
        fy=math.sqrt(1-z*z/(2*B*B));fz=math.sqrt(1-y*y/(2*B*B))
        yy=y*(1+blend*(fy-1));zz=z*(1+blend*(fz-1))
        # Smooth opposite pitch; compact support keeps physical outer fixed.
        fade=max(0.,1-(x/.04)**2)*max(0.,1-(y/.04)**8)*max(0.,1-(z/.025)**2)
        angle=pitch_rad*math.tanh(y/.008)*fade
        xyz[i]=[x*math.cos(angle)+zz*math.sin(angle),yy,-x*math.sin(angle)+zz*math.cos(angle)]
    cells=[]
    for base in itertools.product(*[range(len(a)-1) for a in axes]):
        mid=np.array([(axes[k][base[k]]+axes[k][base[k]+1])/2 for k in range(3)])
        if abs(mid[0])<.001 and abs(mid[1])<.03 and abs(mid[2])<.005:continue
        for order in itertools.permutations(range(3)):
            p=list(base);c=[lookup[tuple(p)]]
            for k in order:p[k]+=1;c.append(lookup[tuple(p)])
            if np.linalg.det((xyz[c[1:]]-xyz[c[0]]).T)<0:c[0],c[1]=c[1],c[0]
            cells.append(c)
    faces={}
    for cell in cells:
        for face in itertools.combinations(cell,3):face=tuple(sorted(face));faces[face]=faces.get(face,0)+1
    patches={'rotor':[],'stationary':[]}
    for f,count in faces.items():
        if count!=1:continue
        p=original[list(f)];outer=any(np.all(p[:,k]==axes[k][0]) or np.all(p[:,k]==axes[k][-1]) for k in range(3))
        patches['stationary' if outer else 'rotor'].append(list(f))
    used=sorted(set(itertools.chain.from_iterable(cells)));remap={v:i for i,v in enumerate(used)}
    mesh={'contract':'spike/cfd-tetra-mesh/v1','units':'m','vertices':xyz[used].tolist(),'cells':[[remap[v] for v in c] for c in cells],'boundary_patches':{k:[[remap[v] for v in f] for f in fs] for k,fs in patches.items()}}
    return mesh,{'original_geometry':'twisted closed two-half plate in coaxial faceted cylinder','level':level,'pitch_rad':pitch_rad,'domain_radius_m':B,'domain_half_length_m':L,'cells':len(cells),'not_real_hardware':True,'axis_unit':[1,0,0]}
