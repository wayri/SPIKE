# SPDX-License-Identifier: Apache-2.0
"""Construct physical encapsulants by OCC extrusion and boolean subtraction.

Coating currently admits proven box solids in their retained source frame with mitered corners.
Curved/non-box sources explicitly block; bounds alone never admit a box.
Potting is the reviewed fill region minus actual retained bodies, exclusions,
and prior encapsulants. These are CAD volumes, never viewport proxies.
"""
import numpy as np
from .assembly_frames import IDENTITY
from .assembly_thermal_joint_geometry import capture_joint_source_boundaries, source_world_transform


def rigid_place(occ, entity, transform):
    """Preserve analytic OCC surfaces under a rigid placement."""
    from scipy.spatial.transform import Rotation
    rotation = Rotation.from_matrix(transform[:3,:3]).as_rotvec()
    angle = float(np.linalg.norm(rotation))
    if angle > 0:
        occ.rotate([entity],0,0,0,*(rotation/angle).tolist(),angle)
    translation = transform[:3,3]
    if np.any(translation):
        occ.translate([entity],*translation.tolist())


def subtract(occ, objects, tools):
    """Use fragment ancestry for difference; preserve all original tool solids."""
    copies = occ.copy(tools)
    occ.synchronize()
    fragments, mapping = occ.fragment(objects, copies)
    object_tags = set(e for group in mapping[:len(objects)] for e in group)
    tool_tags = set(e for group in mapping[len(objects):] for e in group)
    keep = [e for e in fragments if e[0] == 3 and e in object_tags and e not in tool_tags]
    remove = [e for e in fragments if e not in keep]
    if remove:
        occ.remove(remove, recursive=True)
    return keep


def construct_encapsulation(gmsh, rows, solids, entities, source_geometry):
    from .gmsh_occ_mesher import _solid
    occ = gmsh.model.occ
    additions, records, exports = [], [], []
    for row in rows:
        generated = []
        if row['kind'] == 'potting':
            generated = [(3, _solid(occ, row['fill_region']))]
            excludes = [(3, _solid(occ, s)) for s in row['exclusions']]
        else:
            excludes = []
            occ.synchronize()
            for solid, entity in zip(solids, entities):
                if solid['occurrence_id'] not in row['body_ids']:
                    continue
                faces = gmsh.model.getBoundary([entity], oriented=False)
                if len(faces) != 6 or any(gmsh.model.getType(d,t).lower() != 'plane' for d,t in faces):
                    raise ValueError('ENCAPSULATION_COATING_UNSUPPORTED: automatic coating currently requires rectilinear box solids')
                vertices = gmsh.model.getBoundary([entity], recursive=True, oriented=False)
                xyz = np.asarray([gmsh.model.getValue(0,t,[]) for d,t in vertices if d==0])
                if len(xyz) != 8:
                    raise ValueError('ENCAPSULATION_COATING_UNSUPPORTED: expected eight exact source vertices')
                transform = source_world_transform(solid)
                xyz = (xyz-transform[:3,3]) @ transform[:3,:3]
                low, high = xyz.min(axis=0), xyz.max(axis=0)
                error = np.minimum(np.abs(xyz-low),np.abs(xyz-high))
                if np.max(error) > 1e-10 or not np.isclose(
                        occ.getMass(3,entity[1]),np.prod(high-low),rtol=1e-12,atol=1e-12):
                    raise ValueError('ENCAPSULATION_COATING_UNSUPPORTED: source must prove an box in its retained frame, never inferred bounds')
                thickness = row['thickness_mm']
                expanded = (3,occ.addBox(*(low-thickness).tolist(),*(high-low+2*thickness).tolist()))
                rigid_place(occ,expanded,transform)
                generated.append(expanded)
            if len(generated)>1:
                generated,_=occ.fuse(generated[:1],generated[1:])
        tools = entities + additions + excludes
        generated = subtract(occ, generated, tools)
        if excludes:
            occ.remove(excludes,recursive=True)
        generated = [e for e in generated if e[0]==3]
        if len(generated) != 1:
            raise ValueError('ENCAPSULATION_EMPTY: recipe produced no bounded physical volume')
        oid = 'encapsulation:'+row['id']
        new_solids = []
        for i, entity in enumerate(generated):
            sid = oid+':'+str(i)
            new_solids.append({'id':sid,'material_id':row['material_id'],'priority':0,
                'occurrence_id':oid,'transform':list(IDENTITY),'shape':{'kind':row['kind']}})
        captured, owners = capture_joint_source_boundaries(gmsh,new_solids,generated)
        source_geometry[0].update(captured);source_geometry[1].update(owners)
        occ.synchronize()
        gmsh.option.setNumber('Geometry.OCCExportOnlyVisible',1)
        gmsh.model.setVisibility(gmsh.model.getEntities(),0,recursive=True)
        gmsh.model.setVisibility(generated,1,recursive=True)
        filename = 'encapsulation-'+str(len(exports))+'.step'
        gmsh.write(filename)
        gmsh.model.setVisibility(gmsh.model.getEntities(),1,recursive=True)
        gmsh.option.setNumber('Geometry.OCCExportOnlyVisible',0)
        from pathlib import Path
        from hashlib import sha256
        exports.append({'occurrence_id':oid,'file':filename,'sha256':sha256(Path(filename).read_bytes()).hexdigest()})
        additions.extend(generated); records.extend(new_solids)
    return solids+records, entities+additions, exports
