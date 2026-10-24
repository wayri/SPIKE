# SPDX-License-Identifier: Apache-2.0
"""Optional installed-VTK simulation surface preparation; never a flow solver.

Adapted ENOLA surfaces retain their source CC-BY-SA4.0 obligations. Original
geometry remains unchanged beside the independently marked simulation mesh.
"""
import hashlib
import json
import math
from pathlib import Path
import numpy as np


def _triangles(poly):
    from vtk.util.numpy_support import vtk_to_numpy
    xyz=vtk_to_numpy(poly.GetPoints().GetData()).astype(float)
    raw=vtk_to_numpy(poly.GetPolys().GetData()).reshape(-1,4)
    if not np.all(raw[:,0]==3):raise ValueError('Triangular surface required')
    return xyz,raw[:,1:].astype(np.int64)


def _quality(xyz,faces):
    tri=xyz[faces];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(normal,axis=1)/2
    oriented=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]);edge=np.sort(oriented,axis=1);unique,inv,count=np.unique(edge,axis=0,return_inverse=True,return_counts=True);sign=np.where(oriented[:,0]<oriented[:,1],1,-1);balance=np.bincount(inv,weights=sign)
    return {'vertices':len(xyz),'triangles':len(faces),'non_two_owner_edges':int(np.sum(count!=2)),'incoherent_oriented_edges':int(np.sum(balance!=0)),'zero_area_triangles':int(np.sum(area<=0)),'euler_characteristic':int(len(xyz)-len(unique)+len(faces)),'signed_volume_mm3':float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6),'bbox_mm':[xyz.min(0).tolist(),xyz.max(0).tolist()]}


def _point_to_triangle_upper(points,triangle):
    """Distances to explicitly constructed points in one convex target triangle.

    Every candidate is a convex combination, so even an inaccurate plane
    projection is a conservative distance upper bound. No barycentric inside
    predicate can accidentally admit a point outside the triangle.
    """
    a,b,c=triangle;e=b-a;f=c-a;d=points-a
    candidates=[]
    gram=np.array([[e@e,e@f],[e@f,f@f]])
    if np.linalg.det(gram)>0:
        uv=np.linalg.solve(gram,np.c_[d@e,d@f].T).T
        bary=np.c_[1-uv.sum(axis=1),uv];bary=np.maximum(bary,0);bary/=bary.sum(axis=1)[:,None]
        candidates.append(np.linalg.norm(points-bary@triangle,axis=1))
    for left,right in ((a,b),(b,c),(c,a)):
        edge=right-left;den=edge@edge
        t=np.clip(((points-left)@edge)/den,0,1) if den>0 else np.zeros(len(points))
        candidates.append(np.linalg.norm(points-(left+t[:,None]*edge),axis=1))
    return np.min(candidates,axis=0)


def _continuous_distance_bound(source,target,tolerance_mm,*,max_queries=4000000):
    """Conservative whole-triangle bound from nearest-distance 1-Lipschitzness.

    Every queried triangle centroid covers that full triangle within its max
    vertex radius. If d(centroid)+radius <= tolerance, the whole triangle is
    admitted. Otherwise split into four. A sampled violation fails immediately;
    query budget exhaustion fails instead of claiming a sampled Hausdorff proof.
    VTK nearest-distance calculations use floating arithmetic, with explicit
    1e-7mm numerical margin; this is not an interval-arithmetic certification.
    """
    import vtk
    distance=vtk.vtkImplicitPolyDataDistance();distance.SetInput(target)
    locator=vtk.vtkStaticCellLocator();locator.SetDataSet(target);locator.BuildLocator();target_xyz,target_faces=_triangles(target)
    closest=[0.,0.,0.];cell_id=vtk.mutable(0);sub_id=vtk.mutable(0);dist2=vtk.mutable(0.)
    xyz,faces=_triangles(source);stack=[t for t in xyz[faces]];queries=0;maximum_sample=0.;maximum_accepted=0.;margin=1e-7
    while stack:
        if queries>=max_queries:return {'passed':False,'reason':'continuous_distance_query_budget_exhausted','maximum_sample_mm':maximum_sample,'queries':queries}
        tri=stack.pop();centre=tri.mean(0);value=abs(float(distance.EvaluateFunction(centre)))+margin;radius=float(np.linalg.norm(tri-centre,axis=1).max());queries+=1;maximum_sample=max(maximum_sample,value)
        if not math.isfinite(value):raise ValueError('Nonfinite native surface distance')
        if value>tolerance_mm:return {'passed':False,'reason':'sampled_distance_exceeds_bound','maximum_sample_mm':maximum_sample,'queries':queries}
        locator.FindClosestPoint(centre,closest,cell_id,sub_id,dist2)
        convex_bound=float(_point_to_triangle_upper(tri,target_xyz[target_faces[int(cell_id)]]).max())+margin
        upper=min(value+radius,convex_bound)
        if upper<=tolerance_mm:maximum_accepted=max(maximum_accepted,upper);continue
        if queries>=max_queries:return {'passed':False,'reason':'continuous_distance_query_budget_exhausted','maximum_sample_mm':maximum_sample,'queries':queries}
        a,b,c=tri;ab=(a+b)/2;bc=(b+c)/2;ca=(c+a)/2
        stack.extend([np.array([a,ab,ca]),np.array([ab,b,bc]),np.array([ca,bc,c]),np.array([ab,bc,ca])])
    return {'passed':True,'continuous_upper_bound_mm':maximum_accepted,'maximum_sample_mm':maximum_sample,'queries':queries,'method':'convex target-triangle vertex upper bounds plus1-Lipschitz centroid-cover, recursive subdivision','floating_distance_margin_mm':margin}


def coarsen_stl(source,output_dir,*,target_reduction=.85,native_error_mm=.05,distance_bound_mm=.3,check_distance=True):
    import vtk
    if not 0<target_reduction<.98 or not 0<native_error_mm<=distance_bound_mm<=1.:raise ValueError('Explicit bounded mm coarsening controls required')
    src=Path(source).resolve();out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    reader=vtk.vtkSTLReader();reader.SetFileName(str(src));reader.MergingOn();reader.Update();original=reader.GetOutput()
    decimator=vtk.vtkDecimatePro();decimator.SetInputData(original);decimator.SetTargetReduction(target_reduction);decimator.PreserveTopologyOn();decimator.SplittingOff();decimator.BoundaryVertexDeletionOff();decimator.SetFeatureAngle(30.);decimator.SetErrorIsAbsolute(1);decimator.SetAbsoluteError(native_error_mm);decimator.AccumulateErrorOn();decimator.Update();adapted=decimator.GetOutput()
    before=_quality(*_triangles(original));after=_quality(*_triangles(adapted));quality=all(after[k]==0 for k in ('non_two_owner_edges','incoherent_oriented_edges','zero_area_triangles')) and after['euler_characteristic']==before['euler_characteristic'] and before['signed_volume_mm3']*after['signed_volume_mm3']>0
    volume_change=abs(after['signed_volume_mm3']/before['signed_volume_mm3']-1);quality=quality and volume_change<.01
    destination=out/'casalino-simulation-surface.stl';writer=vtk.vtkSTLWriter();writer.SetFileName(str(destination));writer.SetInputData(adapted);writer.SetFileTypeToBinary();writer.Write()
    record={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'simulation_surface_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'tool':'installed VTK vtkDecimatePro','vtk_version':vtk.vtkVersion.GetVTKVersion(),'source_units':'mm','target_reduction':target_reduction,'native_error_control_mm':native_error_mm,'native_error_is_NOT_Hausdorff_certificate':True,'preserve_topology':True,'splitting':False,'feature_angle_deg':30.,'before':before,'after':after,'absolute_volume_change_fraction':volume_change,'topology_orientation_volume_screen_passed':quality,'global_self_intersection_qualified':False,'load_convergence_proven':False,'license_notice':'Adapted ENOLA Universidad Politecnica de Valencia geometry, DOI10.5281/zenodo.20111572 v1, CC-BY-SA4.0; mark this as simulation coarsening, preserve attribution/license, no endorsement.'}
    if check_distance and quality:
        record['original_to_adapted']=_continuous_distance_bound(original,adapted,distance_bound_mm);record['adapted_to_original']=_continuous_distance_bound(adapted,original,distance_bound_mm)
    else:record['distance_check_not_executed']=True
    (out/'coarsening-evidence.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    return record
