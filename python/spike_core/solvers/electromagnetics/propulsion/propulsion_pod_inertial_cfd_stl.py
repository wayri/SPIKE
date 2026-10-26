# SPDX-License-Identifier: Apache-2.0
"""Local optional Gmsh discrete STL fluid-volume investigation (no solver claim)."""
import ctypes.util
import hashlib
import importlib.util
import math
import os
import json
import numpy as np
from pathlib import Path
from unittest.mock import patch
from ...geometry_meshing.preparation import gmsh_occ_runtime as runtime


def inspect_stl_meshing(path,*,generate=False,output_dir=None,volume_algorithm=1,bulk_mesh_size_mm=60.):
    """Import unchanged source surface, create outer cylindrical boundary.

    Current source Casalino STL dimensions are mm, shaft +y, radial z±150mm.
    Axis orientation is a supplied geometry interpretation, not a motor datum.
    No simplification, silent rescaling or BEM forcing is permitted.
    """
    if volume_algorithm not in (1,10):raise ValueError("Only declared native Delaunay1 or HXT10 admitted")
    if type(bulk_mesh_size_mm) not in (int,float) or not 20<=bulk_mesh_size_mm<=300:raise ValueError('Explicit bulk mesh size20..300mm required')
    p=Path(path).resolve()
    with os.add_dll_directory(str(runtime.DLL.parent)):
        original=ctypes.util.find_library
        with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
            spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
        g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
        try:
            g.option.setNumber('General.Terminal',1);g.option.setNumber('General.NumThreads',2);g.merge(str(p))
            inner=[tag for dim,tag in g.model.getEntities(2)]
            # Existing closed discrete surface mesh is retained unchanged.
            # Outer polygon-cylinder uses elementary geometry only, avoiding OCC.
            N=16;R=450.;L=450.;centre_y=10.;point=[[],[]]
            for k,y in enumerate((centre_y-L,centre_y+L)):
                for j in range(N):
                    t=j*2*math.pi/N;point[k].append(g.model.geo.addPoint(R*math.cos(t),y,R*math.sin(t),60.))
            ring=[[],[]];vertical=[]
            for k in range(2):
                for j in range(N):ring[k].append(g.model.geo.addLine(point[k][j],point[k][(j+1)%N]))
            for j in range(N):vertical.append(g.model.geo.addLine(point[0][j],point[1][j]))
            surfaces=[]
            surfaces.append(g.model.geo.addPlaneSurface([g.model.geo.addCurveLoop(ring[0])]))
            surfaces.append(g.model.geo.addPlaneSurface([g.model.geo.addCurveLoop(ring[1])]))
            for j in range(N):
                lines=[ring[0][j],vertical[(j+1)%N],-ring[1][j],-vertical[j]]
                surfaces.append(g.model.geo.addPlaneSurface([g.model.geo.addCurveLoop(lines)]))
            outer=g.model.geo.addSurfaceLoop(surfaces);hole=g.model.geo.addSurfaceLoop(inner)
            volume=g.model.geo.addVolume([outer,hole]);g.model.geo.synchronize()
            evidence={'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'imported_discrete_surfaces':inner,'outer_surfaces':len(surfaces),'fluid_volume_tag':volume,'source_units':'mm','solver_units_conversion':'m=mm/1000','actual_volume_mesh_generated':False,'native_volume_algorithm':volume_algorithm,'bulk_mesh_size_mm':bulk_mesh_size_mm}
            if generate:
                g.option.setNumber('Mesh.MeshSizeMax',bulk_mesh_size_mm);g.option.setNumber('Mesh.MeshSizeExtendFromBoundary',0);g.option.setNumber('Mesh.MeshSizeFromPoints',0);g.option.setNumber('Mesh.MeshSizeFromCurvature',0);g.option.setNumber('Mesh.MeshSizeMin',1.);g.option.setNumber('Mesh.Algorithm3D',volume_algorithm);g.model.mesh.generate(3)
                types,tags,nodes=g.model.mesh.getElements(3);evidence['element_counts']={int(t):len(a) for t,a in zip(types,tags)};evidence['actual_volume_mesh_generated']=True
                nt,xyz,_=g.model.mesh.getNodes();xyz=np.asarray(xyz).reshape(-1,3)/1000;lookup={int(v):i for i,v in enumerate(nt)}
                cells=np.array([[lookup[int(v)] for v in row] for typ,array in zip(types,nodes) if int(typ)==4 for row in np.asarray(array).reshape(-1,4)],dtype=np.int64)
                edge=xyz[cells[:,1:]]-xyz[cells[:,0,None]];matrix=edge.transpose(0,2,1);det=np.linalg.det(matrix);condition=np.linalg.cond(matrix)
                evidence['quality']={'nonpositive_tetrahedra':int(np.sum(det<=0)),'maximum_cell_condition':float(condition.max()) if np.isfinite(condition).all() else None,'nonfinite_condition_cells':int(np.sum(~np.isfinite(condition))),'cells_above_existing_condition1e6':int(np.sum(condition>1e6)),'minimum_signed_volume_m3':float(det.min()/6),'maximum_signed_volume_m3':float(det.max()/6),'total_signed_volume_m3':float(det.sum()/6)}
                evidence['admitted_solver_mesh']=False
                evidence['admission_blockers']=[]
                if len(cells)>65536:evidence['admission_blockers'].append('Actual cell count exceeds explicit65536 admission resource ceiling; no solver run')
                if np.any(det<=0) or np.any(condition>1e6):evidence['admission_blockers'].append('Actual tetra geometry fails unchanged positive-volume/condition gate')
                evidence['admission_blockers'].extend(['Full topology/manifold/intersection admission pending solver construction','Nearwall/traction/domain/physical-regime convergence not qualified'])
                if output_dir is not None:
                    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True);g.write(str(out/'casalino-source-surface-fluid.msh'))
                    boundary={}
                    for label,entities in [('rotor',inner),('stationary',surfaces)]:
                        rows=[]
                        for tag in entities:
                            tt,_,nn=g.model.mesh.getElements(2,tag)
                            rows.extend([[lookup[int(v)] for v in row] for typ,array in zip(tt,nn) if int(typ)==2 for row in np.asarray(array).reshape(-1,3)])
                        boundary[label]=np.array(rows,dtype=np.int64)
                    np.savez_compressed(out/'casalino-fluid-raw-si.npz',vertices_m=xyz,tetrahedra=cells,rotor_triangles=boundary['rotor'],stationary_triangles=boundary['stationary'])
                    evidence['retained_files']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['casalino-source-surface-fluid.msh','casalino-fluid-raw-si.npz']}
                    (out/'casalino-meshing-evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n')
            return evidence
        finally:g.finalize()
