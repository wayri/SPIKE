# SPDX-License-Identifier: Apache-2.0
"""Explicit near-planar triangulation repair for simulation surface preparation.

No tetrahedron is deleted or admitted by this helper. A new boundary surface
with unchanged vertices is remeshed and must pass the original geometry gates.
"""
import hashlib,itertools,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree,ConvexHull
from .propulsion_pod_inertial_cfd_coarsen import _triangles, _quality


def flip_coplanar_sliver_quads(surface,raw_volume_npz,output_dir):
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
    src=Path(surface);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    reader=vtk.vtkSTLReader();reader.SetFileName(str(src));reader.MergingOn();reader.Update();poly=reader.GetOutput();xyz,faces=_triangles(poly);faces=faces.copy();original_faces=faces.copy();before=_quality(xyz,faces);tree=cKDTree(xyz)
    raw=np.load(raw_volume_npz);v=raw['vertices_m'];cells=raw['tetrahedra'];matrix=(v[cells[:,1:]]-v[cells[:,0,None]]).transpose(0,2,1);cond=np.linalg.cond(matrix);bad=np.flatnonzero(cond>1e6);rotor={tuple(sorted(map(int,t))) for t in raw['rotor_triangles']};repairs=[]
    for index in bad:
        cell=cells[index];old=[f for f in itertools.combinations(map(int,cell),3) if tuple(sorted(f)) in rotor]
        if len(old)!=2:raise ValueError('Repair only admits two-boundary-face near-planar quadrilateral slivers')
        distance,mapped=tree.query(v[cell]*1000)
        if max(distance)>1e-7:raise ValueError('Sliver vertices do not match unchanged surface coordinates')
        mapping=dict(zip(map(int,cell),map(int,mapped)));old=[tuple(mapping[i] for i in f) for f in old];common=set(old[0])&set(old[1]);opposite=list((set(old[0])|set(old[1]))-common);common=list(common)
        if len(common)!=2 or len(opposite)!=2:raise ValueError('Not a single quadrilateral edge')
        ids=np.array([*common,*opposite]);points=xyz[ids];centre=points.mean(0);_,_,axes=np.linalg.svd(points-centre);height=(points-centre)@axes[2];bound=float(np.ptp(height));projected=(points-centre)@axes[:2].T;hull=ConvexHull(projected)
        if len(hull.vertices)!=4 or bound>1e-4:raise ValueError('Not a convex almost-planar quad; general geometry repair unsupported')
        lookup={tuple(sorted(map(int,f))):i for i,f in enumerate(faces)}
        old_indices=[lookup[tuple(sorted(f))] for f in old];old_norm=sum(np.cross(xyz[faces[i,1]]-xyz[faces[i,0]],xyz[faces[i,2]]-xyz[faces[i,0]]) for i in old_indices)
        new=[[*opposite,common[0]],[opposite[1],opposite[0],common[1]]]
        for f in new:
            n=np.cross(xyz[f[1]]-xyz[f[0]],xyz[f[2]]-xyz[f[0]])
            if n@old_norm<0:f[0],f[1]=f[1],f[0]
        for i,f in zip(old_indices,new):faces[i]=f
        repairs.append({'volume_cell_id':int(index),'rejected_condition':float(cond[index]),'old_surface_face_ids':old_indices,'same_vertex_ids':ids.tolist(),'quad_plane_height_range_mm':bound,'geometric_bound_reason':'Both diagonal triangulations project onto same convex quad; pointwise normal-height range bounds bidirectional surface distance'})
    after=_quality(xyz,faces)
    if any(after[k] for k in ('non_two_owner_edges','incoherent_oriented_edges','zero_area_triangles')) or after['euler_characteristic']!=before['euler_characteristic']:raise ValueError('Repair did not preserve closed oriented topology')
    points=vtk.vtkPoints();points.SetData(numpy_to_vtk(xyz,deep=True));polys=vtk.vtkCellArray();polys.SetCells(len(faces),numpy_to_vtkIdTypeArray(np.c_[np.full(len(faces),3),faces].ravel(),deep=True));result=vtk.vtkPolyData();result.SetPoints(points);result.SetPolys(polys)
    destination=out/'casalino-simulation-surface.stl';writer=vtk.vtkSTLWriter();writer.SetFileName(str(destination));writer.SetInputData(result);writer.SetFileTypeToBinary();writer.Write();check=vtk.vtkSTLReader();check.SetFileName(str(destination));check.Update();rx,rf=_triangles(check.GetOutput())
    if set(map(tuple,rx))!=set(map(tuple,xyz)):raise ValueError('Native STL write changed coordinates; independent distance recheck required')
    evidence={'input_surface_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_surface_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'source_vertices_unchanged':True,'boundary_only_edge_flips':repairs,'before':before,'after':after,'bidirectional_surface_change_bound_mm':float(sum(r['quad_plane_height_range_mm'] for r in repairs)),'floating_geometry_margin_required':True,'new_volume_mesh_and_original_condition_gate_still_required':True,'no_tetrahedron_deleted_or_admitted':True,'license':'ENOLA DOI10.5281/zenodo.20111572 v1 CC-BY-SA4.0; explicit simulation surface edge flips, no endorsement'}
    (out/'near-planar-repair-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');return evidence


def regularize_roundoff_hub_quad(surface,raw_volume_npz,output_dir,*,offset_mm=.001):
    """Explicit bounded convex regularisation of roundoff-scale hub facets.

    The supplied micron offset is simulation geometry, never original CAD.
    It is unrelated to the admission condition threshold. A fresh tetra mesh
    and the unchanged geometry gates remain mandatory after this operation.
    """
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
    if type(offset_mm) not in (int,float) or not .0005<=offset_mm<=.005:raise ValueError('Explicit hub surface regularisation0.5..5micrometres required')
    src=Path(surface);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True);reader=vtk.vtkSTLReader();reader.SetFileName(str(src));reader.MergingOn();reader.Update();xyz,faces=_triangles(reader.GetOutput());before=_quality(xyz,faces);tree=cKDTree(xyz);points=xyz.tolist();rows=faces.tolist();removed=set();records=[]
    raw=np.load(raw_volume_npz);v=raw['vertices_m'];cells=raw['tetrahedra'];condition=np.linalg.cond((v[cells[:,1:]]-v[cells[:,0,None]]).transpose(0,2,1));boundary={tuple(sorted(map(int,t))) for t in raw['rotor_triangles']};lookup={tuple(sorted(map(int,f))):i for i,f in enumerate(faces)}
    for index in np.flatnonzero(condition>1e6):
        cell=cells[index];old=[f for f in itertools.combinations(map(int,cell),3) if tuple(sorted(f)) in boundary]
        if len(old)!=2:raise ValueError('Only proven near-planar two-face hub quad regularisation supported')
        distance,ids=tree.query(v[cell]*1000)
        if max(distance)>1e-7:raise ValueError('Facet does not match retained source vertices')
        patch=xyz[ids];centre=patch.mean(0);_,_,axes=np.linalg.svd(patch-centre);height=(patch-centre)@axes[2];height_range=float(np.ptp(height));projected=(patch-centre)@axes[:2].T;hull=ConvexHull(projected)
        if len(hull.vertices)!=4 or height_range>1e-4 or np.max(np.linalg.norm(patch[:,[0,2]],axis=1))>15:raise ValueError('Not a roundoff-scale planar hub patch')
        mapping=dict(zip(map(int,cell),map(int,ids)));old_ids=[lookup[tuple(sorted(mapping[v] for v in f))] for f in old]
        if any(i in removed for i in old_ids):continue
        normal=sum(np.cross(xyz[faces[i,1]]-xyz[faces[i,0]],xyz[faces[i,2]]-xyz[faces[i,0]]) for i in old_ids);normal/=np.linalg.norm(normal)
        centre=centre+offset_mm*normal;centre_id=len(points);points.append(centre.tolist());corners=ids[hull.vertices]
        fan=[]
        for a,b in zip(corners,np.roll(corners,-1)):
            f=[int(a),int(b),centre_id]
            if np.cross(np.array(points[f[1]])-points[f[0]],centre-np.array(points[f[0]]))@normal<0:f[0],f[1]=f[1],f[0]
            fan.append(f)
        rows.extend(fan);removed.update(old_ids);records.append({'rejected_native_cell_id':int(index),'old_surface_face_ids':old_ids,'quad_roundoff_height_range_mm':height_range,'supplied_outward_convex_offset_mm':offset_mm,'local_bidirectional_surface_change_bound_mm':offset_mm+height_range,'new_centre_mm':centre.tolist()})
    if not records:raise ValueError('No admitted roundoff-scale hub patch found')
    xyz=np.array(points);faces=np.array([f for i,f in enumerate(rows) if i not in removed]);after=_quality(xyz,faces)
    if any(after[k] for k in ('non_two_owner_edges','incoherent_oriented_edges','zero_area_triangles')) or after['euler_characteristic']!=before['euler_characteristic']:raise ValueError('Regularisation failed topology/orientation checks')
    vp=vtk.vtkPoints();vp.SetData(numpy_to_vtk(xyz,deep=True));polys=vtk.vtkCellArray();polys.SetCells(len(faces),numpy_to_vtkIdTypeArray(np.c_[np.full(len(faces),3),faces].ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(vp);poly.SetPolys(polys);destination=out/'casalino-simulation-surface.stl';writer=vtk.vtkSTLWriter();writer.SetFileName(str(destination));writer.SetInputData(poly);writer.SetFileTypeToBinary();writer.Write()
    e={'input_surface_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_surface_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'explicit_simulation_geometry_regularisation':True,'not_original_supplier_CAD':True,'patches':records,'before':before,'after':after,'all_original_corners_preserved':True,'new_vertices':len(records),'no_tetrahedron_deleted_or_admitted':True,'independent_whole_surface_distance_recheck_required':True,'license':'ENOLA DOI10.5281/zenodo.20111572 v1 CC-BY-SA4.0; marked simulation-only micron hub regularisation, no endorsement'}
    (out/'micron-hub-regularisation-evidence.json').write_text(json.dumps(e,indent=2)+'\n');return e


def regularize_roundoff_hub_vertex(surface,raw_volume_npz,output_dir,*,offset_mm=.001):
    """Explicit micron hub-shape perturbation, not a tetra admission repair.

    Some nearly planar four-corner slivers have no boundary triangle because
    the native hub facet contains intermediate boundary vertices. Alter one
    original hub vertex along the almost-plane normal, retaining connectivity.
    The same affine triangle correspondence bounds surface change by the
    maximum vertex displacement. A new mesh and all original gates are required.
    """
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
    if type(offset_mm) not in (int,float) or not .0005<=offset_mm<=.005:raise ValueError('Explicit0.5..5micrometre simulation hub offset required')
    src=Path(surface);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    reader=vtk.vtkSTLReader();reader.SetFileName(str(src));reader.MergingOn();reader.Update();xyz,faces=_triangles(reader.GetOutput());original=xyz.copy();before=_quality(xyz,faces);tree=cKDTree(xyz)
    raw=np.load(raw_volume_npz);v=raw['vertices_m'];cells=raw['tetrahedra'];condition=np.linalg.cond((v[cells[:,1:]]-v[cells[:,0,None]]).transpose(0,2,1));records=[];moved=set()
    for index in np.flatnonzero(condition>1e6):
        distance,ids=tree.query(v[cells[index]]*1000)
        if max(distance)>1e-7:raise ValueError('Only all-boundary-vertex roundoff hub cells supported')
        patch=original[ids];centre=patch.mean(0);_,_,axes=np.linalg.svd(patch-centre);normal=axes[2];height_range=float(np.ptp((patch-centre)@normal))
        if height_range>1e-4 or np.max(np.linalg.norm(patch[:,[0,2]],axis=1))>15:raise ValueError('Not a roundoff-scale almost-planar hub quartet')
        candidates=[int(i) for i in ids if int(i) not in moved]
        if not candidates:raise ValueError('Overlapping quartet needs a separately reviewed geometry preparation')
        vertex=candidates[0];adjacent=faces[np.any(faces==vertex,axis=1)]
        oldnormal=np.cross(original[adjacent[:,1]]-original[adjacent[:,0]],original[adjacent[:,2]]-original[adjacent[:,0]])
        if normal@oldnormal.sum(0)<0:normal=-normal
        xyz[vertex]=original[vertex]+offset_mm*normal;moved.add(vertex)
        newnormal=np.cross(xyz[adjacent[:,1]]-xyz[adjacent[:,0]],xyz[adjacent[:,2]]-xyz[adjacent[:,0]])
        if np.any(np.einsum('ij,ij->i',oldnormal,newnormal)<=0):raise ValueError('Micron offset flips an adjacent facet')
        records.append({'native_rejected_cell_id':int(index),'original_condition':float(condition[index]),'quartet_surface_vertex_ids':ids.tolist(),'quartet_height_range_mm':height_range,'moved_surface_vertex':vertex,'offset_mm':offset_mm,'direction':normal.tolist()})
    if not records:raise ValueError('No roundoff-scale rejected hub quartet')
    after=_quality(xyz,faces)
    if any(after[k] for k in ('non_two_owner_edges','incoherent_oriented_edges','zero_area_triangles')) or after['euler_characteristic']!=before['euler_characteristic']:raise ValueError('Hub geometry preparation failed topology/orientation screen')
    vp=vtk.vtkPoints();vp.SetData(numpy_to_vtk(xyz,deep=True));polys=vtk.vtkCellArray();polys.SetCells(len(faces),numpy_to_vtkIdTypeArray(np.c_[np.full(len(faces),3),faces].ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(vp);poly.SetPolys(polys)
    destination=out/'casalino-simulation-surface.stl';writer=vtk.vtkSTLWriter();writer.SetFileName(str(destination));writer.SetInputData(poly);writer.SetFileTypeToBinary();writer.Write()
    evidence={'input_surface_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_surface_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'explicit_simulation_hub_shape_perturbation':True,'not_supplier_CAD':True,'unchanged_face_connectivity':True,'maximum_vertex_displacement_mm':float(np.max(np.linalg.norm(xyz-original,axis=1))),'surface_bound_reason':'Same-connectivity affine triangle correspondence: norm of barycentric displacement bounded by largest vertex displacement; add STL floating readback margin','patches':records,'before':before,'after':after,'no_cell_deleted_or_admitted':True,'independent_source_distance_and_new_mesh_required':True,'license':'ENOLA DOI10.5281/zenodo.20111572 v1 CC-BY-SA4.0; simulation-only micron hub shape perturbation, no endorsement'}
    (out/'micron-hub-vertex-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');return evidence


def clean_micron_hub_duplicates(surface,output_dir,*,tolerance_mm=.001):
    """Native VTK simulation-surface edge collapse, restricted by audited region.

    The native cleaner operates on the surface only. Every changed input
    vertex must lie within15mm shaft radius, with bounded displacement. Closed
    oriented topology/Euler and a new whole-source distance/volume mesh check
    remain required. No tetrahedron, pressure dof or equation is discarded.
    """
    import vtk
    if type(tolerance_mm) not in (int,float) or not .0005<=tolerance_mm<=.005:raise ValueError('Explicit0.5..5micrometre hub merge tolerance required')
    src=Path(surface);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    reader=vtk.vtkSTLReader();reader.SetFileName(str(src));reader.MergingOn();reader.Update();original=reader.GetOutput();xyz,faces=_triangles(original);before=_quality(xyz,faces)
    cleaner=vtk.vtkCleanPolyData();cleaner.SetInputData(original);cleaner.PointMergingOn();cleaner.ToleranceIsAbsoluteOn();cleaner.SetAbsoluteTolerance(tolerance_mm);cleaner.ConvertPolysToLinesOn();cleaner.Update()
    triangulate=vtk.vtkTriangleFilter();triangulate.SetInputConnection(cleaner.GetOutputPort());triangulate.PassLinesOff();triangulate.PassVertsOff();triangulate.Update();result=triangulate.GetOutput();rx,rf=_triangles(result)
    distance,mapping=cKDTree(rx).query(xyz);changed=np.flatnonzero(distance>1e-9)
    if not len(changed):raise ValueError('No micron hub duplicate vertices were merged')
    if np.max(distance)>tolerance_mm+1e-7 or np.any(np.linalg.norm(xyz[changed][:,[0,2]],axis=1)>15):raise ValueError('Native merge affects geometry outside declared micron hub region')
    if not set(map(tuple,rx)).issubset(set(map(tuple,xyz))):raise ValueError('Cleaner moved vertices rather than selecting retained corners')
    after=_quality(rx,rf)
    if any(after[k] for k in ('non_two_owner_edges','incoherent_oriented_edges','zero_area_triangles')) or after['euler_characteristic']!=before['euler_characteristic']:raise ValueError('Hub cleanup failed closed oriented topology/Euler screen')
    mapped=mapping[faces];nondegenerate=np.array([len(set(row))==3 for row in mapped]);mapped_valid=mapped[nondegenerate]
    if set(map(lambda f:tuple(sorted(f)),mapped_valid))!=set(map(lambda f:tuple(sorted(f)),rf)):raise ValueError('Native cleanup changed faces beyond declared edge collapses')
    oldnormal=np.cross(xyz[faces[nondegenerate,1]]-xyz[faces[nondegenerate,0]],xyz[faces[nondegenerate,2]]-xyz[faces[nondegenerate,0]])
    newnormal=np.cross(rx[mapped_valid[:,1]]-rx[mapped_valid[:,0]],rx[mapped_valid[:,2]]-rx[mapped_valid[:,0]])
    cosine=np.einsum('ij,ij->i',oldnormal,newnormal)/(np.linalg.norm(oldnormal,axis=1)*np.linalg.norm(newnormal,axis=1))
    if np.any(cosine<=0):raise ValueError('Native hub merge flips an uncollapsed surface face')
    normal_change=float(np.degrees(np.arccos(np.clip(cosine,-1,1))).max())
    destination=out/'casalino-simulation-surface.stl';writer=vtk.vtkSTLWriter();writer.SetFileName(str(destination));writer.SetInputData(result);writer.SetFileTypeToBinary();writer.Write()
    evidence={'input_surface_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_surface_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'native_method':'VTK vtkCleanPolyData absolute tolerance plus vtkTriangleFilter, lines/verts excluded','tolerance_mm':tolerance_mm,'simulation_geometry_preparation_not_supplier_CAD':True,'changed_input_vertex_ids':changed.tolist(),'changed_input_vertices_mm':xyz[changed].tolist(),'retained_corner_ids':mapping[changed].tolist(),'merge_distances_mm':distance[changed].tolist(),'before':before,'after':after,'all_merged_vertices_within15mm_shaft_radius':True,'new_whole_source_distance_mesh_and_pressure_kernel_checks_required':True,'no_tetrahedron_or_pressure_equation_deleted':True,'license':'ENOLA DOI10.5281/zenodo.20111572 v1 CC-BY-SA4.0; declared simulation-only micron hub cleanup, no endorsement'}
    evidence.update(collapsed_degenerate_surface_faces=int(sum(~nondegenerate)),maximum_uncollapsed_face_normal_change_deg=normal_change,all_uncollapsed_face_normals_preserve_orientation=True,unchanged_bbox=before['bbox_mm']==after['bbox_mm'])
    (out/'micron-hub-cleanup-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');return evidence
