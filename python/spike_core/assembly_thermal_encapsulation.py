# SPDX-License-Identifier: Apache-2.0
"""Reviewed encapsulation recipes and derived assembly identities (mm).

Original SPIKE implementation. Geometry is constructed by the optional OCC
worker from retained solids; recipes never promote display bounding boxes.
"""
import copy
from .assembly_frames import IDENTITY
from .assembly_field_handoff import text
from .gmsh_occ_mesher import validate_request
from .multiboard_identity import canonical_json_digest


def validate_encapsulation(rows, materials, body_ids, mesh):
    if not isinstance(rows, list) or len(rows) > 8:
        raise ValueError('ENCAPSULATION_CONFIG: expected at most eight recipes')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('ENCAPSULATION_CONFIG: recipe must be an object')
        base = {'id', 'kind', 'material_id'}
        kind = row.get('kind')
        expected = base | ({'body_ids', 'thickness_mm'} if kind == 'coating' else {'fill_region', 'exclusions'})
        if kind not in ('coating', 'potting') or set(row) != expected:
            raise ValueError('ENCAPSULATION_CONFIG: invalid recipe fields')
        rid = text(row['id'])
        if rid in seen or 'encapsulation:'+rid in body_ids:
            raise ValueError('ENCAPSULATION_CONFIG: duplicate or conflicting identity')
        seen.add(rid)
        if row['material_id'] not in materials:
            raise ValueError('ENCAPSULATION_MATERIAL: assign a reviewed material')
        if kind == 'coating':
            ids, thickness = row['body_ids'], row['thickness_mm']
            if (not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or
                    not set(ids) <= set(body_ids)):
                raise ValueError('ENCAPSULATION_BODY: select retained physical bodies')
            if type(thickness) not in (int, float) or not 0 < thickness <= 100:
                raise ValueError('ENCAPSULATION_THICKNESS: finite thickness in (0,100] mm required')
        else:
            exclusions = row['exclusions']
            if not isinstance(exclusions, list) or len(exclusions) > 16:
                raise ValueError('ENCAPSULATION_EXCLUSIONS: at most sixteen regions')
            for shape in [row['fill_region'], *exclusions]:
                if not isinstance(shape, dict) or shape.get('kind') != 'polygon_prism':
                    raise ValueError('ENCAPSULATION_REGION: explicit world-mm polygon prism required')
                validate_request({'contract':'spike/gmsh-occ-mesh/v1', 'mesh':mesh, 'solids':[
                    {'id':'region','material_id':'region','priority':0,'shape':shape}]})
    # Ordering changes material ownership. Keep recipes disjoint by cutting
    # previous encapsulants; require explicit coating-before-potting ordering.
    if any(r['kind']=='coating' for i,r in enumerate(rows) if any(p['kind']=='potting' for p in rows[:i])):
        raise ValueError('ENCAPSULATION_ORDER: coatings must precede potting')
    return copy.deepcopy(rows)


def augment_plan(plan, rows):
    source = canonical_json_digest(plan['assembly'])
    for row in rows:
        oid = 'encapsulation:'+row['id']
        sha = canonical_json_digest({'recipe':row, 'source_assembly':plan['assembly'],
                                     'source_jobs':plan['jobs']})
        reference = 'encapsulation-model:'+sha
        plan['assembly'].setdefault('parts', []).append({'id':oid, 'model_id':reference,
            'part_type':'encapsulation', 'material_id':row['material_id'],
            'frame':{'frame_id':'frame:'+oid, 'transform':list(IDENTITY)},
            'extensions':{'spike.v1.encapsulation':{'recipe':row,'source_assembly_sha256':source}}})
        plan['jobs'].append({'occurrence_id':oid,'reference_id':reference,'source_sha256':sha,
            'material_map':{row['material_id']:row['material_id']}, 'encapsulation':row,
            'representation':'occ_'+row['kind'],
            'approximations':(['Rectilinear box coating with mitered corners; rounded constant-distance edge fillets are not modeled.']
                              if row['kind']=='coating' else [])})
    plan['encapsulation'] = rows
    return plan
