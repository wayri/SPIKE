# SPDX-License-Identifier: Apache-2.0
"""Neutral routed copper polygons to complete, explicitly assigned OCC solids.

All material and plating values are supplied study inputs. Curved source shapes
must already be polygonized with recorded precision by their source adapter.
No board bounds, net names or unspecified manufacturer defaults create solids.
"""
import copy
import math

from .gmsh_occ_mesher import validate_request
from .multiboard_identity import canonical_json_digest


def _require(test, reason):
    if not test:
        raise ValueError('ROUTED_BOARD_EM: '+reason)


def _positive(value, label):
    _require(type(value) in (int, float) and math.isfinite(value) and value > 0,
             'finite positive '+label+' required')
    return value


def prepare_routed_board_volume(snapshot, stack, *, coarse_size_mm=2., max_cells=100000):
    """Prepare a complete typed OCC job from an admitted planar source snapshot.

    ``stack`` supplies contiguous layers (id, z_min_mm, z_max_mm, material_id),
    copper_layer_spans keyed by source layer, copper/air material identifiers,
    plated_hole_wall_mm, and nonempty provenance. Circular via drills become
    bounded polygonal circles. Slots retain their supplied contours. Through
    barrels occupy drill.buffer(plating)-drill; pad diameters never imply wall
    thickness. OCC fragment priorities resolve layer, copper and drill volumes.
    """
    from shapely.geometry import Point, Polygon, box
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    _require(isinstance(snapshot, dict) and snapshot.get('contract') == 'spike/routed-board-polygons/v1'
             and snapshot.get('units') == 'mm', 'neutral millimetre polygon snapshot required')
    _require(isinstance(stack, dict) and set(stack) == {'layers', 'copper_layer_spans',
             'copper_material_id', 'air_material_id', 'plated_hole_wall_mm', 'provenance'},
             'explicit complete study stack assignment required')
    _require(isinstance(stack['provenance'], str) and bool(stack['provenance'].strip()),
             'stack/material assumption provenance required')
    wall = _positive(stack['plated_hole_wall_mm'], 'plated hole wall in mm')
    error = _positive(snapshot.get('chord_error_mm'), 'source chord error in mm')
    _positive(coarse_size_mm, 'coarse mesh size')
    _require(type(max_cells) is int and 4 <= max_cells <= 100000, 'cell budget outside [4,100000]')
    _require(len(snapshot.get('board', [])) == 1, 'one closed actual board outline required')
    points = 0

    def polygon(row):
        nonlocal points
        _require(isinstance(row, dict) and set(row) == {'outer_mm', 'holes_mm'}, 'invalid polygon fields')
        for ring in [row['outer_mm'], *row['holes_mm']]:
            _require(isinstance(ring, list) and len(ring) >= 3, 'closed polygon needs three vertices')
            points += len(ring)
            _require(points <= 131072, 'input point budget exceeded')
            _require(all(isinstance(p, list) and len(p) == 2 and all(type(x) in (int, float)
                         and math.isfinite(x) and abs(x) <= 1e6 for x in p) for p in ring),
                     'invalid finite planar coordinates')
        value = Polygon(row['outer_mm'], row['holes_mm'])
        _require(value.is_valid and not value.is_empty and value.area > 0, 'invalid polygon topology')
        return value

    board = polygon(snapshot['board'][0])
    layers = stack['layers']
    _require(isinstance(layers, list) and 1 <= len(layers) <= 32, 'bounded physical layer list required')
    previous = None
    layer_ids = set()
    for layer in layers:
        _require(set(layer) == {'id', 'z_min_mm', 'z_max_mm', 'material_id'}, 'invalid physical layer fields')
        low, high = layer['z_min_mm'], layer['z_max_mm']
        _require(all(type(x) in (int,float) and math.isfinite(x) for x in (low,high)) and high > low,
                 'layer elevations must be finite with positive thickness')
        _require(previous is None or previous == low, 'physical layers must be exactly contiguous')
        _require(layer['id'] not in layer_ids, 'duplicate physical layer')
        layer_ids.add(layer['id']); previous = high
    low, high = layers[0]['z_min_mm'], layers[-1]['z_max_mm']
    spans = stack['copper_layer_spans']
    _require(set(spans) == set(snapshot['layers']), 'every source copper layer needs an explicit span')
    for span in spans.values():
        _require(isinstance(span,list) and len(span)==2 and all(type(x) in (int,float) and
                 math.isfinite(x) for x in span) and low <= span[0] < span[1] <= high,
                 'invalid copper span')
    solids, metadata, groups, ownership = [], {}, {}, {}

    def emit(identity, material, priority, geometry, z0, z1, data):
        pieces = list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]
        pending=pieces; pieces=[]
        while pending:
            piece=pending.pop()
            if len(piece.interiors)>128:
                x0,y0,x1,y1=piece.bounds
                if x1-x0 >= y1-y0:
                    split=(box(x0,y0,(x0+x1)/2,y1),box((x0+x1)/2,y0,x1,y1))
                else:
                    split=(box(x0,y0,x1,(y0+y1)/2),box(x0,(y0+y1)/2,x1,y1))
                for half in split:
                    clipped=piece.intersection(half)
                    pending.extend(list(clipped.geoms) if clipped.geom_type=='MultiPolygon' else [clipped])
                _require(len(pending)+len(pieces)<10000,'polygon partition budget exceeded')
            else:
                pieces.append(piece)
        for i, piece in enumerate(pieces):
            _require(piece.geom_type == 'Polygon' and piece.is_valid and piece.area > 0,
                     'unresolved polygon geometry')
            sid = identity+':'+str(i)
            _require(sid not in metadata, 'duplicate source identity')
            solids.append({'id':sid, 'material_id':material, 'priority':priority, 'shape': {
                'kind':'polygon_prism', 'outer_mm':[list(p) for p in list(piece.exterior.coords)[:-1]],
                'holes_mm':[[list(p) for p in list(r.coords)[:-1]] for r in piece.interiors],
                'z_min_mm':z0, 'z_max_mm':z1}})
            metadata[sid] = data

    for layer in layers:
        emit('layer:'+layer['id'], layer['material_id'], 0, board,
             layer['z_min_mm'],layer['z_max_mm'], {'kind':'board_layer','layer':layer['id']})
    for item in snapshot.get('copper', []):
        _require(item.get('layer') in spans and isinstance(item.get('id'),str), 'invalid copper ownership')
        _require(item.get('kind') in {'track','pad','via_land','filled_zone','board_graphic','footprint_graphic'},
                 'unsupported copper source kind')
        rows = item.get('polygons')
        _require(isinstance(rows,list) and rows, 'source copper object has no geometry: '+item['id'])
        net = item.get('net') or '__unassigned__:'+item['id']
        key = (item['layer'], net)
        for row in rows:
            shape = polygon(row)
            _require(board.covers(shape), 'copper extends outside actual board outline: '+item['id'])
            groups.setdefault(key,[]).append(shape)
        ownership.setdefault(key,[]).append(item['id'])
    _require(groups, 'routed copper is absent')
    holes, barrels = [], []
    for drill in snapshot.get('drills',[]):
        _require(drill.get('start_layer') in spans and drill.get('end_layer') in spans,
                 'drill layer span is missing')
        if 'polygons' in drill:
            shape = unary_union([polygon(p) for p in drill['polygons']])
        else:
            diameter = _positive(drill.get('diameter_mm'), 'drill diameter')
            radius = diameter/2
            # Sagitta r(1-cos(pi/n)) <= error; at least 16 sides.
            n = max(16, math.ceil(math.pi/math.acos(max(-1.,1-min(error,radius)/radius))))
            _require(n <= 4096, 'drill polygon work budget exceeded')
            shape = Point(drill['center_mm']).buffer(radius, quad_segs=math.ceil(n/4))
        _require(board.covers(shape), 'drill extends outside board; castellations unsupported')
        z0 = min(spans[drill['start_layer']][0],spans[drill['end_layer']][0])
        z1 = max(spans[drill['start_layer']][1],spans[drill['end_layer']][1])
        _require(type(drill.get('plated')) is bool, 'explicit drill plating flag required')
        holes.append((shape,z0,z1,drill['id']))
        if drill['plated']:
            shell = shape.buffer(wall, join_style='mitre').difference(shape)
            _require(board.covers(shell), 'plated hole extends outside board')
            barrels.append((shell,z0,z1,drill.get('net') or '__unassigned__:'+drill['id'],drill['id'],shape))
    conductors=[]
    for (layer,net), shapes in groups.items():
        shape = unary_union(shapes)
        uncut=shape
        z0,z1 = spans[layer]
        cuts = [p for p,a,b,_ in holes if a <= z0 and b >= z1]
        if cuts:
            shape = shape.difference(unary_union(cuts))
        _require(not shape.is_empty, 'copper source erased by drills')
        sid='copper:'+str(len(conductors))
        emit(sid,stack['copper_material_id'],10,uncut,z0,z1,{'kind':'copper','net':net,'layer':layer})
        conductors.append((shape,z0,z1,net,sid))
    for shape,z0,z1,net,sid,hole in barrels:
        # Priority-20 drill solids cut the priority-10 copper. Emitting the
        # pre-cut ring also makes OCC fragment coincident hole sidewalls,
        # which is avoidable and crashes some admitted OCC runtimes.
        emit('barrel:'+sid,stack['copper_material_id'],10,shape.union(hole),z0,z1,{'kind':'via_barrel','net':net})
        conductors.append((shape,z0,z1,net,sid))
    tree=STRtree([row[0] for row in conductors]); checks=0; unassigned_contacts=0
    for i,(shape,a,b,net,sid) in enumerate(conductors):
        for j in tree.query(shape):
            if j <= i: continue
            other,c,d,foreign,oid=conductors[j]
            if net == foreign or b<c or d<a: continue
            checks+=1
            _require(checks <= 1000000,'cross-net work budget exceeded')
            if shape.intersects(other):
                if net.startswith('__unassigned__:') or foreign.startswith('__unassigned__:'):
                    # Physical copper stays present. Missing electrical net
                    # metadata must not turn a connected solid into a gap.
                    unassigned_contacts+=1
                else:
                    raise ValueError('ROUTED_BOARD_EM: cross-net conductor contact: '+sid+' / '+oid)
    for shape,z0,z1,sid in holes:
        emit('drill:'+sid,stack['air_material_id'],20,shape,z0,z1,{'kind':'drill'})
    job={'contract':'spike/gmsh-occ-mesh/v2','solids':solids,'object_metadata':metadata,
         'focus':{'contract':'spike/pcb-focus-sizing/v1','net_names':[],'source_ids':[solids[0]['id']],
                  'fine_size_mm':coarse_size_mm,'coarse_size_mm':coarse_size_mm,
                  'halo_mm':0.,'growth_rate':1.,'regions':[]},
         'mesh':{'min_size_mm':1e-6,'max_size_mm':coarse_size_mm,
                 'max_cells':max_cells,'max_vertices':100000}}
    validate_request(job)
    return {'job':job,'stack_binding':{'id':'routed-stack','source_sha256':canonical_json_digest(stack)},
            'source_sha256':snapshot['source_sha256'], 'snapshot_sha256':canonical_json_digest(snapshot),
            'copper_source_groups':[{'layer':layer,'net':net,'source_ids':sources}
                                    for (layer,net),sources in ownership.items()],
            'study_parameters':copy.deepcopy(stack), 'production_qualified':False,
            'evidence':{'source_copper_objects':len(snapshot['copper']), 'drills':len(holes),
                        'solids':len(solids),'copper_groups':len(groups),'roi_cropping':False,
                        'unassigned_copper_contacts':unassigned_contacts,
                        'connectivity_inferred':False}}
