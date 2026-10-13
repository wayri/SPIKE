# SPDX-License-Identifier: Apache-2.0
"""Original planar material-priority extraction and closed-prism tetrahedra.

This is exclusively an EM solid-surface representation for Cartesian FDTD.
Each homogeneous polygon prism has a conforming interior, but adjoining
different material regions may use different surface triangulations. It is
not a globally conforming FEM/thermal mesh and must never enter those solvers.
"""
from collections import defaultdict
import itertools
import math

from .gmsh_occ_mesher import validate_request
from .tetra_mesh_refinement import _det, _validate


def _require(value, message):
    if not value:
        raise ValueError('EM_PLANAR_MESH: '+message)


def _polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    _require(geometry.geom_type == 'MultiPolygon', 'nonpolygon material remainder')
    return list(geometry.geoms)


def partition_material_prisms(job, *, precision_mm=1e-6):
    """Resolve priorities independently in every exact source z interval.

    The caller supplies already polygonized geometry. A 1 nm XY precision grid
    removes floating Boolean slivers; topology changes or movement beyond the
    grid diagonal are rejected for every source. Source net identity never
    changes the material priority. No ROI, board-box replacement or contour
    simplification is performed. All source solids are retained in provenance.
    """
    from shapely import set_precision, union_all
    from shapely.geometry import Polygon
    validate_request(job)
    _require(type(precision_mm) in (int,float) and math.isfinite(precision_mm)
             and 1e-9 <= precision_mm <= 1e-6,'precision must lie in [1e-9,1e-6] mm')
    rows=[]; elevations=set(); max_change=0.
    for solid in job['solids']:
        shape=solid['shape']
        _require(shape['kind']=='polygon_prism','planar polygon prisms only; analytic/STEP solids unsupported')
        original=Polygon(shape['outer_mm'],shape['holes_mm'])
        polygon=set_precision(original,precision_mm)
        _require(polygon.geom_type=='Polygon' and not polygon.is_empty and
                 len(polygon.interiors)==len(original.interiors),
                 'source topology changes at the declared precision: '+solid['id'])
        _require(original.hausdorff_distance(polygon) <= 1.415*precision_mm,
                 'precision displacement exceeds the grid diagonal')
        max_change=max(max_change,original.symmetric_difference(polygon).area)
        rows.append((solid,polygon,shape['z_min_mm'],shape['z_max_mm']))
        elevations.update((shape['z_min_mm'],shape['z_max_mm']))
    levels=sorted(elevations)
    _require(len(levels)<=65,'z interval work budget exceeded')
    regions=[]; expected_volumes=defaultdict(float)
    for low,high in zip(levels[:-1],levels[1:]):
        active=[(s,p) for s,p,a,b in rows if a<=low and high<=b]
        groups=defaultdict(list); sources=defaultdict(list)
        for solid,polygon in active:
            key=(solid['priority'],solid['material_id'])
            groups[key].append(polygon);sources[key].append(solid['id'])
        combined={key:union_all(polygons,grid_size=precision_mm) for key,polygons in groups.items()}
        occupied=None
        for priority in sorted({p for p,m in groups},reverse=True):
            keys=sorted(k for k in groups if k[0]==priority)
            for a,b in itertools.combinations(keys,2):
                _require(combined[a].intersection(combined[b]).area==0,
                         'overlapping equal-priority materials')
            for key in keys:
                region=combined[key] if occupied is None else combined[key].difference(occupied)
                for piece in _polygons(region):
                    _require(piece.is_valid and piece.area>0,'invalid priority material partition')
                    identity='region:'+str(len(regions))
                    regions.append({'id':identity,'material_id':key[1],'polygon':piece,
                                    'z_min_mm':low,'z_max_mm':high,'source_ids':sources[key]})
                    expected_volumes[key[1]]+=piece.area*(high-low)
            batch=union_all([combined[key] for key in keys],grid_size=precision_mm)
            occupied=batch if occupied is None else union_all([occupied,batch],grid_size=precision_mm)
        union_area=union_all([p for _,p in active],grid_size=precision_mm).area if active else 0.
        total_area=sum(r['polygon'].area for r in regions if r['z_min_mm']==low)
        _require(abs(total_area-union_area)<=max(1e-9,union_area*1e-11),
                 'priority partition does not conserve total cross-section area')
        _require(len(regions)<=10000,'material region budget exceeded')
    return regions,{'precision_mm':precision_mm,'max_source_symmetric_difference_mm2':max_change,
        'source_solids':len(rows),'material_regions':len(regions),'z_intervals':len(levels)-1,
        'expected_material_volume_mm3':dict(expected_volumes),'source_coverage':sorted(s['id'] for s,_,_,_ in rows),
        'representation':'closed_material_prisms_for_em_only','globally_conforming_fem':False}


def mesh_material_prisms(job, *, max_cells=100000, max_vertices=100000, precision_mm=1e-6):
    """Triangulate each complete material polygon and split each prism into 3 tets.

    Sorting XY node indices gives one diagonal convention on every shared
    vertical rectangle within a region. Positive scalar triple products orient
    tets. The independent oracle is polygon area times exact source interval
    thickness, evaluated for every region and accumulated for each material.
    """
    from shapely import constrained_delaunay_triangles, union_all, set_precision
    _require(type(max_cells) is int and 1<=max_cells<=600000 and
             type(max_vertices) is int and 4<=max_vertices<=400000,'retained mesh budget outside supported range')
    regions,evidence=partition_material_prisms(job,precision_mm=precision_mm)
    plans=[]; predicted=0
    for region in regions:
        geometry=region['polygon']
        triangles=list(constrained_delaunay_triangles(geometry).geoms)
        _require(triangles and all(t.geom_type=='Polygon' and len(t.exterior.coords)==4 and
                 geometry.covers(t) for t in triangles),'triangulator escaped material polygon')
        # Disable the precision *operation mode* for this independent oracle.
        # Coordinates stay unchanged; re-snapping triangulation diagonals
        # during a Boolean comparison would create new artificial slivers.
        reconstructed=union_all([set_precision(t,0) for t in triangles])
        _require(reconstructed.symmetric_difference(set_precision(geometry,0)).area <= max(1e-12,geometry.area*1e-11),
                 'triangulation lost polygon area or holes')
        _require(abs(sum(t.area for t in triangles)-geometry.area)<=max(1e-12,geometry.area*1e-11),
                 'triangulation contains overlapping area')
        predicted+=3*len(triangles)
        plans.append((region,triangles))
    evidence['predicted_cells']=predicted
    _require(predicted<=max_cells,'complete geometry needs '+str(predicted)+' tetrahedra; budget '+str(max_cells))
    mesh={'contract':'spike/solver-mesh/v1','units':'mm','coordinate_system':'right_handed_xyz',
          'vertices':[],'cells':[],'counts':{},'object_map':{}}
    nodes={}; face_owners=defaultdict(list); volumes=defaultdict(float); trace=[]
    def vertex(x,y,z):
        point=(x,y,z)
        if point not in nodes:
            _require(len(nodes)<max_vertices,'vertex budget exceeded')
            nodes[point]=len(mesh['vertices']);mesh['vertices'].append(list(point))
        return nodes[point]
    for region,triangles in plans:
        rid=region['id'];mid=region['material_id'];low=region['z_min_mm'];high=region['z_max_mm']
        mesh['object_map'][rid]={'kind':'em_material_region'}
        reference=region['polygon'].area*(high-low);volume=0.
        for triangle in triangles:
            xy=sorted(tuple(p) for p in list(triangle.exterior.coords)[:-1])
            a,b,c=[vertex(x,y,low) for x,y in xy];A,B,C=[vertex(x,y,high) for x,y in xy]
            for ids in ([a,b,c,C],[a,b,B,C],[a,A,B,C]):
                determinant=_det(mesh['vertices'],ids)
                if determinant<0: ids[0],ids[1]=ids[1],ids[0];determinant=-determinant
                _require(math.isfinite(determinant) and determinant>0,'degenerate prism tetrahedron')
                cell={'id':str(len(mesh['cells'])),'kind':'tetrahedron','vertices':ids,
                      'material_id':mid,'source_object_ids':[rid]}
                mesh['cells'].append(cell);volume+=determinant/6
                p,q,r,s=ids
                for face in ([q,r,s],[p,s,r],[p,q,s],[p,r,q]):
                    face_owners[tuple(sorted(face))].append(face)
        _require(abs(volume-reference)<=max(1e-12,reference*1e-9),'tetrahedron region volume mismatch')
        volumes[mid]+=volume
        trace.append({'region_id':rid,'material_id':mid,'candidate_source_ids':region['source_ids'],
                      'polygon_area_mm2':region['polygon'].area,'z_min_mm':low,'z_max_mm':high,
                      'tetrahedral_volume_mm3':volume})
    _require(all(1<=len(faces)<=2 for faces in face_owners.values()),'nonmanifold mesh incidence')
    boundary=[{'id':'face:'+str(i),'vertices':faces[0]} for i,faces in enumerate(face_owners.values()) if len(faces)==1]
    mesh['counts']={'vertices':len(mesh['vertices']),'cells':len(mesh['cells'])}
    _validate(mesh,[{'vertices':f['vertices'],'label':f['id']} for f in boundary],max_cells,max_vertices)
    return {'mesh':mesh,'boundary_faces':boundary,'material_map':{m:m for m in volumes},
            'evidence':{**evidence,'tetrahedral_material_volume_mm3':dict(volumes)},
            'region_traceability':trace,'production_qualified':False}
