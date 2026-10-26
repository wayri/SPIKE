# SPDX-License-Identifier: Apache-2.0
"""Independent conforming structured fluid mesh around an original two-blade plate.

No CAD Boolean or installed mesher is required. The explicit boundary triangles
are the actual faceted blade geometry, not a BEM load or actuator body force.
"""
import itertools
import math
import numpy as np


def build_blade_mesh(*, pitch_rad=.2, refinement=1):
    """Two opposite twisted plate halves, closed stationary rectangular vessel.

    Shaft+x. Rotor |x|<=1mm, |y|<=30mm, |z|<=5mm before smooth
    pitch deformation. No supplier airfoil or hub approximation is implied.
    Whole vessel is stationary; this is an instantaneous laboratory Stokes
    snapshot, not a rotating-frame or steady inertial-air calculation.
    """
    if type(refinement) is not int or refinement not in (1,2):raise ValueError('refinement must be 1 or 2')
    if type(pitch_rad) not in (int,float) or not math.isfinite(pitch_rad) or abs(pitch_rad)>.25:raise ValueError('pitch outside original fixture range')
    axes=[np.array([-.04,-.001,.001,.04]),np.array([-.06,-.03,0,.03,.06]),np.array([-.04,-.005,.005,.04])]
    if refinement==2:
        axes=[np.sort(np.r_[a,(a[:-1]+a[1:])/2]) for a in axes]
    coords=list(itertools.product(*[range(len(a)) for a in axes]));lookup={c:i for i,c in enumerate(coords)}
    original=np.array([[axes[k][c[k]] for k in range(3)] for c in coords]);xyz=original.copy()
    for i,(x,y,z) in enumerate(original):
        # Exactly fixed container; smooth opposite blade pitch with a neck at y=0.
        fade=(1-(x/.04)**2)*(1-(y/.06)**8)*(1-(z/.04)**2)
        angle=pitch_rad*math.tanh(y/.008)*fade
        xyz[i,0]=x*math.cos(angle)+z*math.sin(angle)
        xyz[i,2]=-x*math.sin(angle)+z*math.cos(angle)
    cells=[]
    for base in itertools.product(*[range(len(a)-1) for a in axes]):
        middle=np.array([(axes[k][base[k]]+axes[k][base[k]+1])/2 for k in range(3)])
        if abs(middle[0])<.001 and abs(middle[1])<.03 and abs(middle[2])<.005:continue
        for order in itertools.permutations(range(3)):
            pos=list(base);cell=[lookup[tuple(pos)]]
            for k in order:pos[k]+=1;cell.append(lookup[tuple(pos)])
            d=np.linalg.det((xyz[cell[1:]]-xyz[cell[0]]).T)
            if d<0:cell[0],cell[1]=cell[1],cell[0]
            if abs(d)<1e-18:raise ValueError('Degenerate original mesh')
            cells.append(cell)
    faces={}
    for c in cells:
        for f in itertools.combinations(c,3):
            key=tuple(sorted(f));faces[key]=faces.get(key,0)+1
    patches={'rotor':[],'stationary':[]}
    for face,count in faces.items():
        if count!=1:continue
        p=original[list(face)]
        outer=any(np.all(p[:,k]==axes[k][0]) or np.all(p[:,k]==axes[k][-1]) for k in range(3))
        patches['stationary' if outer else 'rotor'].append(list(face))
    used=sorted(set(itertools.chain.from_iterable(cells)));remap={v:i for i,v in enumerate(used)}
    mesh={'contract':'spike/cfd-tetra-mesh/v1','units':'m','vertices':xyz[used].tolist(),'cells':[[remap[v] for v in c] for c in cells],'boundary_patches':{k:[[remap[v] for v in f] for f in fs] for k,fs in patches.items()}}
    return mesh,{'original_geometry':'smoothly twisted two-half rectangular plate in closed rectangular stationary vessel','pitch_parameter_rad':pitch_rad,'refinement':refinement,'tetrahedra':len(cells),'rotor_boundary_triangles':len(patches['rotor']),'stationary_boundary_triangles':len(patches['stationary']),'units':'m','not_supplier_airfoil':True,'not_BEM_default_geometry':True}
