import hashlib
import json
import re
import math
from pathlib import Path
from .filled_polygon_offset import inflate_filled_simple_polygon_round_inside_v1
from .simple_polygon_union import (
    is_simple_polygon, polygon_contains_polygon, union_simple_polygons,
    union_two_simple_polygons,
)

MAX_SOURCE_FILL_COMPONENTS_PER_GROUP = 65_536
MAX_SOURCE_FILL_VERTICES_PER_COMPONENT = 65_536
MAX_SOURCE_FILL_VERTICES_PER_GROUP = 1_048_576
MAX_SOURCE_ZONE_OUTLINE_PATHS = 256
MAX_SOURCE_ZONE_OUTLINE_VERTICES_PER_PATH = 65_536
MAX_SOURCE_ZONE_OUTLINE_VERTICES = 1_048_576

class KicadParser:
    """
    Robust S-Expression Parser for KiCad PCB files.
    Handles hierarchy (Footprints/Modules) and coordinate transformations.
    """
    def __init__(self, filepath, strict=True):
        self.filepath = Path(filepath)
        self.content = ""
        self.strict = strict
        self.diagnostics = []
        
        # Data Structures
        self.layers = {}   
        self.nets = {}     
        self.tracks = []   
        self.vias = []     
        self.pads = []     
        self.footprints = []
        self.zones = []    
        self.drawings = [] 
        self.outline = []
        self.stackup = []
        self.technology = 'rigid'
        self.regions = []
        self.bends = []
        self.board_bbox = {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100}

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.content = f.read()
            if self.content:
                self.parse()
        except Exception as e:
            message = f"Error reading/parsing {self.filepath}: {e}"
            self.diagnostics.append(message)
            if self.strict:
                raise RuntimeError(message) from e
            print(message)

    def tokenize(self, text):
        """Ultra-robust S-Exp tokenizer handling escaped quotes and complex nesting"""
        tokens = []
        current = []
        quoted = False
        escaped = False
        
        for char in text:
            if escaped:
                current.append(char)
                escaped = False
                continue
            
            if char == '\\':
                if quoted: escaped = True
                else: current.append(char)
                continue
                
            if char == '"':
                quoted = not quoted
                current.append(char)
                continue
                
            if quoted:
                current.append(char)
            else:
                if char in '()':
                    if current:
                        tokens.append("".join(current))
                        current = []
                    tokens.append(char)
                elif char.isspace():
                    if current:
                        tokens.append("".join(current))
                        current = []
                else:
                    current.append(char)
        
        if quoted:
            raise ValueError("Unterminated quoted string in KiCad S-expression")
        if current: tokens.append("".join(current))
        return tokens

    def parse_sexp(self, tokens):
        """Parse tokens into nested lists"""
        stack = [[]]
        for token in tokens:
            if token == '(':
                sub = []
                stack[-1].append(sub)
                stack.append(sub)
            elif token == ')':
                if len(stack) == 1:
                    raise ValueError("Unexpected closing parenthesis in KiCad S-expression")
                stack.pop()
            else:
                stack[-1].append(token)
        if len(stack) != 1:
            raise ValueError("Unclosed parenthesis in KiCad S-expression")
        return stack[0][0] if stack[0] else []

    def parse(self):
        print(f"Parsing {self.filepath.name} with S-Exp parser...")
        tokens = self.tokenize(self.content)
        sexp = self.parse_sexp(tokens)
        
        # Root should be 'kicad_pcb'
        if not sexp or sexp[0] != 'kicad_pcb':
            raise ValueError("Invalid or unrecognized KiCad PCB file format")

        for item in sexp:
            if not isinstance(item, list) or not item: continue
            
            head = item[0]
            if head == 'layers':
                self._parse_layers_node(item)
            elif head == 'net':
                self._parse_net_node(item)
            elif head == 'segment':
                self._parse_segment(item)
            elif head == 'arc':
                self._parse_arc(item)
            elif head == 'via':
                self._parse_via(item)
            elif head == 'zone':
                self._parse_zone(item)
            elif head in ['gr_line', 'gr_circle', 'gr_arc', 'gr_rect', 'gr_text', 'gr_poly']:
                self._parse_drawing(item)
            elif head in ['footprint', 'module']:
                self._parse_footprint(item)
            elif head == 'setup':
                self._parse_setup_node(item)
                
        self.calculate_outline()
        self.calculate_rigid_flex()
        print(f"Parsed: {len(self.nets)} nets, {len(self.tracks)} tracks, {len(self.pads)} pads, {len(self.zones)} zones. Board: {self.board_bbox['max_x']-self.board_bbox['min_x']:.1f}x{self.board_bbox['max_y']-self.board_bbox['min_y']:.1f}mm")

    def calculate_outline(self):
        """Find board extents from Edge.Cuts or fallback to copper extents."""
        min_x, min_y = 1e9, 1e9
        max_x, max_y = -1e9, -1e9
        found_edge = False
        
        # 1. Try Edge.Cuts
        for d in self.drawings:
            if d.get('layer') == 'Edge.Cuts':
                if d['type'] == 'line':
                    for p in [d['start'], d['end']]:
                        min_x = min(min_x, p[0]); max_x = max(max_x, p[0])
                        min_y = min(min_y, p[1]); max_y = max(max_y, p[1])
                        found_edge = True
                elif d['type'] == 'circle':
                    c = d['center']; r = d['radius']
                    min_x = min(min_x, c[0]-r); max_x = max(max_x, c[0]+r)
                    min_y = min(min_y, c[1]-r); max_y = max(max_y, c[1]+r)
                    found_edge = True

        # 2. Fallback to copper if no Edge.Cuts
        if not found_edge:
            for t in self.tracks:
                for p in [t['start'], t['end']]:
                    min_x = min(min_x, p[0]); max_x = max(max_x, p[0])
                    min_y = min(min_y, p[1]); max_y = max(max_y, p[1])
            for p in self.pads:
                at = p['at']
                min_x = min(min_x, at[0]); max_x = max(max_x, at[0])
                min_y = min(min_y, at[1]); max_y = max(max_y, at[1])
            
            # Add margin
            min_x -= 5; max_x += 5; min_y -= 5; max_y += 5

        if min_x < max_x:
            self.board_bbox = {'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y}

    @staticmethod
    def _region_kind(label):
        normalized = str(label or '').strip().lower()
        if re.search(r'rigid[ ._-]*flex', normalized):
            return None
        for kind in ('bend', 'stiffener', 'transition', 'flex', 'rigid'):
            if re.search(rf'(^|[ ._-]){kind}(?:ible)?(?:[ ._-]*(?:region|outline|area))?(?:[ ._-]|\d|$)', normalized):
                return kind
        return None

    @staticmethod
    def _polygon_area(points):
        if len(points) < 3:
            return 0.0
        closed = points if points[0] == points[-1] else [*points, points[0]]
        return abs(sum(closed[index][0] * closed[index + 1][1] - closed[index + 1][0] * closed[index][1] for index in range(len(closed) - 1)) / 2)

    def _closed_drawing_loops(self, layer_name):
        tolerance = 0.015
        complete = []
        open_paths = []
        for drawing in self.drawings:
            if drawing.get('layer') != layer_name:
                continue
            points = list(drawing.get('points', []))
            if not points and drawing.get('type') == 'line':
                points = [drawing.get('start'), drawing.get('end')]
            points = [tuple(point) for point in points if point is not None]
            if len(points) > 2 and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) <= tolerance:
                complete.append(points)
            elif len(points) > 1:
                open_paths.append(points)
        while open_paths:
            path = open_paths.pop(0)
            extended = True
            while extended and math.hypot(path[0][0] - path[-1][0], path[0][1] - path[-1][1]) > tolerance:
                extended = False
                for index, candidate in enumerate(open_paths):
                    pairs = [
                        (path[-1], candidate[0], False, False),
                        (path[-1], candidate[-1], False, True),
                        (path[0], candidate[-1], True, False),
                        (path[0], candidate[0], True, True),
                    ]
                    match = next((pair_index for pair_index, pair in enumerate(pairs) if math.hypot(pair[0][0] - pair[1][0], pair[0][1] - pair[1][1]) <= tolerance), None)
                    if match is None:
                        continue
                    if match == 0:
                        path.extend(candidate[1:])
                    elif match == 1:
                        path.extend(reversed(candidate[:-1]))
                    elif match == 2:
                        path[:0] = candidate[:-1]
                    else:
                        path[:0] = reversed(candidate[1:])
                    open_paths.pop(index)
                    extended = True
                    break
            if len(path) > 2 and math.hypot(path[0][0] - path[-1][0], path[0][1] - path[-1][1]) <= tolerance:
                path[-1] = path[0]
                complete.append(path)
        return sorted(complete, key=self._polygon_area, reverse=True)

    def calculate_rigid_flex(self):
        explicit = []
        bends = []
        for layer_id, layer in self.layers.items():
            label = f"{layer.get('name', '')} {layer.get('user_name', '')}".strip()
            kind = self._region_kind(label)
            if not kind:
                continue
            if kind == 'bend':
                radius_match = re.search(r'(?:^|[ _.-])(?:r|radius)\s*=?\s*(-?\d+(?:\.\d+)?)\s*(?:mm)?(?:$|[ _.-])', label, re.I)
                angle_match = re.search(r'(?:^|[ _.-])(?:a|angle)\s*=?\s*(-?\d+(?:\.\d+)?)\s*(?:deg)?(?:$|[ _.-])', label, re.I)
                for index, drawing in enumerate(item for item in self.drawings if item.get('layer') == layer.get('name')):
                    points = drawing.get('points') or [drawing.get('start'), drawing.get('end')]
                    points = [list(point) for point in points if point is not None]
                    if len(points) >= 2:
                        bends.append({
                            'id': f'bend:{layer_id}:{index}', 'name': f'{label} {index + 1}',
                            'points': points, 'source_layer': layer.get('name', ''),
                            'radius_mm': float(radius_match.group(1)) if radius_match else None,
                            'angle_deg': float(angle_match.group(1)) if angle_match else None,
                        })
                continue
            for index, outline in enumerate(self._closed_drawing_loops(layer.get('name', ''))):
                explicit.append({
                    'id': f'region:{layer_id}:{index}', 'name': f'{label} {index + 1}',
                    'kind': kind, 'outline': [list(point) for point in outline],
                    'source_layer': layer.get('name', ''), 'source': 'kicad-user-layer',
                })
        board_area = max((self.board_bbox['max_x'] - self.board_bbox['min_x']) * (self.board_bbox['max_y'] - self.board_bbox['min_y']), 0)
        flex_area = sum(self._polygon_area(region['outline']) for region in explicit if region['kind'] == 'flex')
        has_rigid = any(region['kind'] == 'rigid' for region in explicit)
        self.technology = 'flex' if flex_area and not has_rigid and board_area and flex_area >= board_area * 0.92 else 'rigid-flex' if flex_area else 'rigid'
        self.regions = explicit
        self.bends = bends

    def _get_node(self, list_node, key):
        """Find strictly immediate sub-node starting with key"""
        for item in list_node:
            if isinstance(item, list) and item and item[0] == key:
                return item
        return None

    def _get_value(self, list_node, key, index=1):
        """Get value from (key val)"""
        node = self._get_node(list_node, key)
        if node and len(node) > index:
            return node[index]
        return None

    def _source_native_id(self, list_node):
        """Return KiCad's persistent object identity without inventing one."""
        for key in ('uuid', 'tstamp'):
            value = self._get_value(list_node, key)
            if value is not None:
                identity = str(value).replace('"', '').strip()
                if identity:
                    return identity
        return ''

    def _parse_layers_node(self, node):
        for layer in node[1:]:
            if isinstance(layer, list) and len(layer) >= 3:
                # (0 F.Cu signal)
                try:
                    lid = int(layer[0])
                    name = layer[1]
                    ltype = layer[2]
                    self.layers[lid] = {
                        'name': name.replace('"', ''),
                        'type': ltype.replace('"', ''),
                        'user_name': layer[3].replace('"', '') if len(layer) > 3 and isinstance(layer[3], str) else '',
                    }
                except: pass

    def _parse_setup_node(self, node):
        stackup_node = self._get_node(node, 'stackup')
        if not stackup_node: return
        
        for item in stackup_node[1:]:
            if isinstance(item, list) and item and item[0] == 'layer':
                # (layer "F.Cu" (type "copper") (thickness 0.035))
                # (layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5))
                layer_data = {'name': item[1].replace('"', '')}
                for sub in item[2:]:
                    if isinstance(sub, list) and len(sub) >= 2:
                        key = sub[0]
                        val = sub[1].replace('"', '') if isinstance(sub[1], str) else sub[1]
                        try:
                            layer_data[key] = float(val) if key in ['thickness', 'epsilon_r', 'loss_tangent'] else val
                        except ValueError:
                            layer_data[key] = val
                self.stackup.append(layer_data)

    def _get_net_info(self, net_n):
        """Robustly extract net_id and net_name from a (net ...) node for KiCad 10 compatibility"""
        nid = 0
        name = ""
        if net_n and len(net_n) > 1:
            try:
                nid = int(net_n[1])
                if len(net_n) > 2:
                    name = net_n[2].replace('"', '')
            except ValueError:
                name = net_n[1].replace('"', '')
        
        if not name and nid in self.nets:
            name = self.nets[nid]

        # Root-level KiCad net declarations carry both the numeric code and the
        # canonical schematic name. Persist that mapping before segments and
        # vias, whose local `(net N)` references contain only the code.
        if name and nid > 0:
            self.nets[nid] = name
            
        if name and nid == 0:
            for k, v in self.nets.items():
                if v == name:
                    nid = k
                    break
            if nid == 0:
                nid = max(list(self.nets.keys()) + [0]) + 1
                self.nets[nid] = name
                
        if not name and nid > 0:
            name = f"Net_{nid}"
            self.nets[nid] = name
            
        return nid, name

    def _parse_net_node(self, node):
        # (net 0 "") or (net "GND")
        self._get_net_info(node)

    def _parse_segment(self, node):
        # (segment (start X Y) (end X Y) (width W) (layer L) (net N))
        try:
            start = self._get_node(node, 'start')
            end = self._get_node(node, 'end')
            width_n = self._get_node(node, 'width')
            layer_n = self._get_node(node, 'layer')
            net_n = self._get_node(node, 'net')
            
            if start and end:
                nid, net_name = self._get_net_info(net_n)
                
                source_id = self._source_native_id(node)
                track = {
                    'start': (float(start[1]), float(start[2])),
                    'end': (float(end[1]), float(end[2])),
                    'width': float(width_n[1]) if width_n else 0.2,
                    'layer': layer_n[1].replace('"', '') if layer_n else 'F.Cu',
                    'net_id': nid,
                    'net_name': net_name
                }
                if source_id:
                    track.update({'id': source_id, 'uuid': source_id})
                self.tracks.append(track)
        except: pass

    def _parse_arc(self, node):
        # (arc (start X Y) (mid X Y) (end X Y) (width W) (layer L) (net N))
        try:
            start = self._get_node(node, 'start')
            mid = self._get_node(node, 'mid')
            end = self._get_node(node, 'end')
            width_n = self._get_node(node, 'width')
            layer_n = self._get_node(node, 'layer')
            net_n = self._get_node(node, 'net')
            
            if start and mid and end:
                nid, net_name = self._get_net_info(net_n)
                layer = layer_n[1].replace('"', '') if layer_n else 'F.Cu'
                width = float(width_n[1]) if width_n else 0.2
                source_id = self._source_native_id(node)
                
                import math
                x1, y1 = float(start[1]), float(start[2])
                xm, ym = float(mid[1]), float(mid[2])
                x2, y2 = float(end[1]), float(end[2])
                
                # Calculate circumcenter (Ux, Uy)
                D = 2 * (x1 * (ym - y2) + xm * (y2 - y1) + x2 * (y1 - ym))
                if abs(D) < 1e-6:
                    # Collinear or extremely small, just use a straight line
                    track = {'start': (x1, y1), 'end': (x2, y2), 'width': width, 'layer': layer, 'net_id': nid, 'net_name': net_name}
                    if source_id:
                        track.update({'id': source_id, 'uuid': source_id, 'source_parent_id': source_id})
                    self.tracks.append(track)
                else:
                    Ux = ((x1**2 + y1**2) * (ym - y2) + (xm**2 + ym**2) * (y2 - y1) + (x2**2 + y2**2) * (y1 - ym)) / D
                    Uy = ((x1**2 + y1**2) * (x2 - xm) + (xm**2 + ym**2) * (x1 - x2) + (x2**2 + y2**2) * (xm - x1)) / D
                    
                    R = math.hypot(x1 - Ux, y1 - Uy)
                    
                    ang1 = math.atan2(y1 - Uy, x1 - Ux)
                    angm = math.atan2(ym - Uy, xm - Ux)
                    ang2 = math.atan2(y2 - Uy, x2 - Ux)
                    
                    # Normalize angles to [0, 2pi)
                    if ang1 < 0: ang1 += 2*math.pi
                    if angm < 0: angm += 2*math.pi
                    if ang2 < 0: ang2 += 2*math.pi
                    
                    # Determine sweep direction
                    # We must pass through angm
                    diff_m1 = (angm - ang1) % (2*math.pi)
                    diff_21 = (ang2 - ang1) % (2*math.pi)
                    
                    if diff_m1 < diff_21:
                        # CCW sweep from ang1 to ang2
                        sweep = diff_21
                    else:
                        # CW sweep from ang1 to ang2
                        sweep = diff_21 - 2*math.pi
                        
                    steps = 8
                    d_ang = sweep / steps
                    
                    prev_x, prev_y = x1, y1
                    for i in range(1, steps + 1):
                        a = ang1 + i * d_ang
                        cur_x = Ux + R * math.cos(a)
                        cur_y = Uy + R * math.sin(a)
                        
                        track = {
                            'start': (prev_x, prev_y),
                            'end': (cur_x, cur_y),
                            'width': width, 'layer': layer, 'net_id': nid, 'net_name': net_name
                        }
                        if source_id:
                            segment_id = f'{source_id}:segment:{i}'
                            track.update({'id': segment_id, 'uuid': segment_id, 'source_parent_id': source_id})
                        self.tracks.append(track)
                        prev_x, prev_y = cur_x, cur_y
        except: pass

    def _parse_via(self, node):
        # KiCad writes the class as an optional atom after `via`, for example
        # `(via blind ...)` and `(via micro ...)`.  `blind` is KiCad's shared
        # blind/buried class; its layer span distinguishes the two physical
        # forms.  Never fill in a missing span here: downstream consumers must
        # not mistake an assumed through-via for source-backed geometry.
        try:
            at = self._get_node(node, 'at')
            size = self._get_node(node, 'size')
            drill_n = self._get_node(node, 'drill')
            layers_n = self._get_node(node, 'layers')
            net_n = self._get_node(node, 'net')
            source_id = self._source_native_id(node)

            if not at:
                self._diagnose_via(source_id, "missing required (at X Y) location")
                return

            via_layers = self._via_layer_span(layers_n, source_id)
            if via_layers is None:
                return
            via_type = self._via_type(node, via_layers, source_id)
            if via_type is None:
                return

            nid, net_name = self._get_net_info(net_n)
            via = {
                'at': (float(at[1]), float(at[2])),
                'size': float(size[1]) if size else 0.6,
                'drill': float(drill_n[1]) if drill_n else 0.3,
                'layers': via_layers,
                'start_layer': via_layers[0],
                'end_layer': via_layers[1],
                'type': via_type,
                'net_id': nid,
                'net_name': net_name,
            }
            if source_id:
                via.update({'id': source_id, 'uuid': source_id})
            self.vias.append(via)
        except (IndexError, TypeError, ValueError) as error:
            self._diagnose_via(self._source_native_id(node), str(error))

    def _diagnose_via(self, source_id, message):
        label = f" {source_id}" if source_id else ""
        self.diagnostics.append(f"Unable to parse via{label}: {message}")

    def _copper_layer_order(self):
        """Return the physical copper order supplied by KiCad's layer table."""
        return [
            layer.get('name', '')
            for _layer_id, layer in self.layers.items()
            if layer.get('name', '').endswith('.Cu')
            or layer.get('type', '').lower() in {'signal', 'power', 'mixed', 'jumper'}
        ]

    def _via_layer_span(self, layers_node, source_id):
        if not layers_node or len(layers_node) != 3:
            self._diagnose_via(source_id, "required layer span must contain exactly two layers")
            return None
        start, end = (str(value).replace('"', '').strip() for value in layers_node[1:])
        if not start or not end or start == end:
            self._diagnose_via(source_id, "layer span must contain two distinct non-empty layers")
            return None
        copper_layers = self._copper_layer_order()
        if len(copper_layers) < 2:
            self._diagnose_via(source_id, "cannot validate layer span without at least two declared copper layers")
            return None
        if start not in copper_layers or end not in copper_layers:
            self._diagnose_via(source_id, f"layer span {start!r} to {end!r} references undeclared copper layers")
            return None
        return (start, end)

    def _via_type(self, node, via_layers, source_id):
        type_atoms = [item for item in node[1:] if isinstance(item, str)]
        if len(type_atoms) > 1:
            self._diagnose_via(source_id, f"unknown via type sequence {type_atoms!r}")
            return None
        declared_type = type_atoms[0].replace('"', '').strip().lower() if type_atoms else 'through'
        # KiCad's PCB syntax has no atom for a through via (the atom is absent)
        # and uses `blind` for the blind/buried class.  Do not accept friendly
        # spellings here: this is a source parser, not a semantic repairer.
        aliases = {'through': 'through', 'blind': 'blind', 'micro': 'microvia'}
        if declared_type not in aliases:
            self._diagnose_via(source_id, f"unknown via type {declared_type!r}")
            return None

        copper_layers = self._copper_layer_order()
        start, end = via_layers
        start_index, end_index = copper_layers.index(start), copper_layers.index(end)
        outer = {copper_layers[0], copper_layers[-1]}
        touches_outer = (start in outer) + (end in outer)
        via_type = aliases[declared_type]

        if via_type == 'through':
            if {start, end} != outer:
                self._diagnose_via(source_id, "through via span must connect the two outer copper layers")
                return None
            return via_type
        if via_type == 'blind':
            if touches_outer == 1:
                return via_type
            if touches_outer == 0:
                # KiCad serializes blind and buried vias with the same `blind`
                # marker.  The internal-only span proves this is buried.
                return 'buried'
            self._diagnose_via(source_id, "blind via span cannot connect both outer copper layers")
            return None
        # KiCad microvias are laser vias from an outside copper layer to its
        # directly adjacent copper layer.  Both constraints are checkable from
        # the source layer table, so reject anything not proven by it.
        if touches_outer != 1 or abs(start_index - end_index) != 1:
            self._diagnose_via(source_id, "microvia span must join an outer copper layer to its adjacent layer")
            return None
        return via_type

    @staticmethod
    def _zone_connection_mode(value, *, inherited=False):
        if value is None:
            return "inherit" if inherited else "thermal"
        normalized = str(value).replace('"', '').strip().lower()
        aliases = {
            "0": "none", "1": "thermal", "2": "solid", "3": "tht_thermal",
            "no": "none", "none": "none", "yes": "solid", "full": "solid",
            "thru_hole_only": "tht_thermal",
        }
        return aliases.get(normalized, "unknown")

    def _thermal_number(self, node, key, owner, *, angle=False):
        item = self._get_node(node, key) if node else None
        if item is None:
            return None, True
        try:
            value = float(item[1])
        except (IndexError, TypeError, ValueError):
            self.diagnostics.append(f"{owner} has an invalid {key} value; thermal connectivity is unresolved.")
            return None, False
        valid = math.isfinite(value) and (0 <= value < 360 if angle else value >= 0)
        if not valid:
            self.diagnostics.append(f"{owner} has an invalid {key} value; thermal connectivity is unresolved.")
            return None, False
        return value, True

    def _connection_override(self, node, owner):
        declared_node = self._get_node(node, 'zone_connect') if node else None
        declared = declared_node is not None
        raw_value = declared_node[1] if declared_node and len(declared_node) > 1 else None
        mode = self._zone_connection_mode(raw_value, inherited=True) if declared else "inherit"
        valid = mode != "unknown"
        if not valid:
            self.diagnostics.append(f"{owner} has an unsupported zone_connect value; thermal connectivity is unresolved.")
        gap, gap_valid = self._thermal_number(node, 'thermal_gap', owner)
        width, width_valid = self._thermal_number(node, 'thermal_bridge_width', owner)
        angle, angle_valid = self._thermal_number(node, 'thermal_bridge_angle', owner, angle=True)
        return {
            "mode": mode, "declared": declared, "thermal_gap_mm": gap,
            "thermal_spoke_width_mm": width, "thermal_spoke_angle_deg": angle,
            "valid": valid and gap_valid and width_valid and angle_valid,
        }

    @staticmethod
    def _contains_nested_node(node, key):
        return any(
            isinstance(item, list) and item and (
                item[0] == key or KicadParser._contains_nested_node(item, key)
            )
            for item in (node or [])
        )

    def _parse_zone(self, node):
        """
        Parse KiCad's filled copper per layer.

        A multi-layer zone contains one design outline plus one filled_polygon for
        each layer.  Treating all of those records as copper on the zone's first
        layer duplicates the plane and corrupts both meshing and solver results.
        """
        try:
            # 1. Resolve Layer
            # Could be (layer "L") or (layers "L1" "L2" ...)
            layer_n = self._get_node(node, 'layer')
            if not layer_n:
                 layer_n = self._get_node(node, 'layers')
            
            layer = "F.Cu"
            if layer_n and len(layer_n) > 1:
                layer = layer_n[1].replace('"', '')

            # 2. Resolve Net
            net_n = self._get_node(node, 'net')
            net_name_n = self._get_node(node, 'net_name')
            
            # Use robust net parser
            net_id, resolved_net_name = self._get_net_info(net_n)
                 
            if (not resolved_net_name or resolved_net_name.startswith("Net_")) and net_name_n:
                # Use explicit string name if ID resolution is generic
                resolved_net_name = net_name_n[1].replace('"', '')

            zone_uuid_n = self._get_node(node, 'uuid')
            zone_uuid = zone_uuid_n[1].replace('"', '') if zone_uuid_n and len(zone_uuid_n) > 1 else ''
            source_zone_id = zone_uuid or f"zone-{len(self.zones) + 1}"
            if self._get_node(node, 'keepout') is not None:
                self.diagnostics.append(
                    f"KiCad keepout zone {source_zone_id} is excluded from conductive zone geometry pending typed keepout regions."
                )
                return
            connect_pads = self._get_node(node, 'connect_pads')
            connection_declared = connect_pads is not None
            connection_atom = None
            if connect_pads:
                connection_atom = next((item for item in connect_pads[1:] if not isinstance(item, list)), None)
            connection_default = self._zone_connection_mode(connection_atom)
            connection_valid = connection_default != "unknown"
            if not connection_valid:
                self.diagnostics.append(
                    f"KiCad zone {source_zone_id} has an unsupported connect_pads value; thermal connectivity is unresolved."
                )
            fill_node = self._get_node(node, 'fill')
            clearance, clearance_valid = self._thermal_number(
                connect_pads if connect_pads else node, 'clearance', f"KiCad zone {source_zone_id}"
            )
            thermal_gap, gap_valid = self._thermal_number(fill_node, 'thermal_gap', f"KiCad zone {source_zone_id}")
            thermal_width, width_valid = self._thermal_number(
                fill_node, 'thermal_bridge_width', f"KiCad zone {source_zone_id}"
            )
            fill_mode_node = self._get_node(fill_node, 'mode') if fill_node else None
            fill_mode = (
                "hatched" if fill_mode_node and len(fill_mode_node) > 1 and str(fill_mode_node[1]).lower() == "hatch"
                else "solid" if fill_node else "unknown"
            )
            thermal_settings_valid = connection_valid and clearance_valid and gap_valid and width_valid
            filled = [
                item for item in node
                if isinstance(item, list) and item and item[0] == 'filled_polygon'
            ]
            outlines = [
                item for item in node
                if isinstance(item, list) and item and item[0] == 'polygon'
            ]
            fallback_layers = []
            if layer_n and layer_n[0] == 'layers':
                fallback_layers = [str(value).replace('"', '') for value in layer_n[1:]]
            if not fallback_layers:
                fallback_layers = [layer]
            source_outline_paths = []
            rejected_outline_paths = 0
            for outline_index, outline in enumerate(outlines):
                pts_node = self._get_node(outline, 'pts')
                try:
                    outline_points = [
                        (float(point[1]), float(point[2]))
                        for point in (pts_node[1:] if pts_node else [])
                        if isinstance(point, list) and len(point) > 2 and point[0] == 'xy'
                    ]
                except (TypeError, ValueError):
                    outline_points = []
                if (
                    len(outline_points) < 3
                    or len(outline_points) > MAX_SOURCE_ZONE_OUTLINE_VERTICES_PER_PATH
                    or not all(math.isfinite(value) for point in outline_points for value in point)
                ):
                    rejected_outline_paths += 1
                    self.diagnostics.append(
                        f"KiCad zone {source_zone_id} source outline {outline_index + 1} is malformed or over-bound."
                    )
                    continue
                if (
                    len(source_outline_paths) >= MAX_SOURCE_ZONE_OUTLINE_PATHS
                    or sum(len(path) for path in source_outline_paths) + len(outline_points)
                    > MAX_SOURCE_ZONE_OUTLINE_VERTICES
                ):
                    rejected_outline_paths += 1
                    self.diagnostics.append(
                        f"KiCad zone {source_zone_id} source outline exceeds bounded path or vertex limits."
                    )
                    continue
                source_outline_paths.append(outline_points)
            if not outlines:
                source_outline_state = 'none'
            elif source_outline_paths and not rejected_outline_paths:
                source_outline_state = 'complete' if len(source_outline_paths) == 1 else 'noncanonical'
            elif source_outline_paths:
                source_outline_state = 'partial'
            else:
                source_outline_state = 'unsupported'
            source_outline_complete = source_outline_state in {'complete', 'noncanonical'}
            source_outline_sha256 = hashlib.sha256(json.dumps(
                {
                    "layer_ids": fallback_layers,
                    "paths_mm": [[[x, y] for x, y in path] for path in source_outline_paths],
                },
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")).hexdigest() if source_outline_complete else ''
            outline_metadata = {
                'source_zone_outline_id': f'{source_zone_id}:outline' if source_outline_complete else '',
                'source_zone_outline_sha256': source_outline_sha256,
                'source_zone_outline_paths_mm': source_outline_paths if source_outline_complete else [],
                'source_zone_outline_layer_ids': fallback_layers if outlines else [],
                'source_zone_outline_path_count': len(source_outline_paths) if source_outline_complete else 0,
                'source_zone_outline_vertex_count': sum(len(path) for path in source_outline_paths) if source_outline_complete else 0,
                'source_zone_outline_rejected_path_count': rejected_outline_paths,
                'source_zone_outline_representation': 'flat_polygon_paths' if source_outline_complete else 'none',
                'source_zone_outline_state': source_outline_state,
                'source_zone_outline_provenance_complete': source_outline_complete,
                'parametric_refill_eligible': False,
            }

            parsed_polygons = []
            incomplete_fill_layers = set()
            for polygon_index, item in enumerate(filled):
                item_layer_n = self._get_node(item, 'layer')
                item_layers = [
                    item_layer_n[1].replace('"', '')
                ] if item_layer_n and len(item_layer_n) > 1 else fallback_layers
                pts_node = self._get_node(item, 'pts')
                points = [
                    (float(point[1]), float(point[2]))
                    for point in (pts_node[1:] if pts_node else [])
                    if isinstance(point, list) and len(point) > 2 and point[0] == 'xy'
                ]
                if len(points) < 3:
                    self.diagnostics.append(
                        f"KiCad zone {source_zone_id} polygon {polygon_index + 1} has fewer than three points and was excluded."
                    )
                    incomplete_fill_layers.update(
                        value for value in item_layers if value.endswith('.Cu')
                    )
                    continue
                if not all(math.isfinite(value) for point in points for value in point):
                    self.diagnostics.append(
                        f"KiCad zone {source_zone_id} polygon {polygon_index + 1} has non-finite coordinates and was excluded."
                    )
                    incomplete_fill_layers.update(
                        value for value in item_layers if value.endswith('.Cu')
                    )
                    continue
                for polygon_layer in item_layers:
                    if not polygon_layer.endswith('.Cu'):
                        continue
                    parsed_polygons.append((polygon_index, polygon_layer, points))

            layer_component_digests = {}
            for _, polygon_layer, points in parsed_polygons:
                payload = json.dumps(
                    {"layer": polygon_layer, "points_mm": [[x, y] for x, y in points]},
                    sort_keys=True, separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")
                layer_component_digests.setdefault(polygon_layer, []).append(
                    hashlib.sha256(payload).hexdigest()
                )
            layer_group_digests = {
                polygon_layer: hashlib.sha256(json.dumps(
                    sorted(digests), separators=(",", ":")
                ).encode("utf-8")).hexdigest()
                for polygon_layer, digests in layer_component_digests.items()
            }
            layer_group_admitted = {}
            for polygon_layer, digests in layer_component_digests.items():
                members = [points for _, layer_value, points in parsed_polygons if layer_value == polygon_layer]
                admitted = (
                    polygon_layer not in incomplete_fill_layers
                    and len(digests) <= MAX_SOURCE_FILL_COMPONENTS_PER_GROUP
                    and all(len(points) <= MAX_SOURCE_FILL_VERTICES_PER_COMPONENT for points in members)
                    and sum(len(points) for points in members) <= MAX_SOURCE_FILL_VERTICES_PER_GROUP
                )
                layer_group_admitted[polygon_layer] = admitted
                if not admitted:
                    self.diagnostics.append(
                        f"KiCad zone {source_zone_id} layer {polygon_layer} source-fill provenance exceeds bounds or is incomplete."
                    )
            layer_ordinals = {polygon_layer: 0 for polygon_layer in layer_component_digests}

            if not filled and outlines:
                self.zones.append({
                    'id': f'{source_zone_id}:intent', 'layer': fallback_layers[0],
                    'layers': fallback_layers, 'net_id': net_id, 'net_name': resolved_net_name,
                    'points': [], 'source_kind': 'zone_outline_intent', 'zone_uuid': zone_uuid,
                    'source_zone_id': source_zone_id, 'filled_copper_id': '', **outline_metadata,
                    'source_fill_group_id': '', 'source_fill_group_sha256': '',
                    'source_fill_component_ordinal': 0, 'source_fill_component_count': 0,
                    'source_fill_component_sha256': '', 'source_fill_representation': 'none',
                    'source_fill_provenance_complete': False, 'thermal_topology_eligible': False,
                    'zone_kind': 'copper', 'filled_copper_state': 'none',
                    'zone_connection_default': connection_default,
                    'zone_connection_declared': connection_declared, 'clearance_mm': clearance,
                    'thermal_gap_mm': thermal_gap, 'thermal_spoke_width_mm': thermal_width,
                    'fill_mode': fill_mode, 'thermal_settings_valid': thermal_settings_valid,
                })
                return

            for polygon_index, polygon_layer, points in parsed_polygons:
                layer_ordinals[polygon_layer] += 1
                component_ordinal = layer_ordinals[polygon_layer]
                provenance_complete = bool(filled and layer_group_admitted.get(polygon_layer, False))
                source_id = ':'.join(filter(None, (
                    source_zone_id,
                    polygon_layer,
                    str(polygon_index + 1),
                )))
                self.zones.append({
                        'id': source_id,
                        'layer': polygon_layer,
                        'net_id': net_id,
                        'net_name': resolved_net_name,
                        'points': points,
                        'source_kind': 'filled_zone' if filled else 'zone_outline_fallback',
                        'zone_uuid': zone_uuid,
                        'source_zone_id': source_zone_id,
                        'filled_copper_id': source_id if filled else '',
                        **outline_metadata,
                        'source_fill_group_id': f'{source_zone_id}:{polygon_layer}' if provenance_complete else '',
                        'source_fill_group_sha256': layer_group_digests.get(polygon_layer, '') if provenance_complete else '',
                        'source_fill_component_ordinal': component_ordinal if provenance_complete else 0,
                        'source_fill_component_count': len(layer_component_digests.get(polygon_layer, ())) if provenance_complete else 0,
                        'source_fill_component_sha256': (
                            layer_component_digests[polygon_layer][component_ordinal - 1] if provenance_complete else ''
                        ),
                        'source_fill_representation': 'flat_polygon_path' if provenance_complete else 'none',
                        'source_fill_provenance_complete': provenance_complete,
                        'thermal_topology_eligible': False,
                        'zone_kind': 'copper',
                        'filled_copper_state': 'source_filled' if filled else 'outline_fallback',
                        'zone_connection_default': connection_default,
                        'zone_connection_declared': connection_declared,
                        'clearance_mm': clearance,
                        'thermal_gap_mm': thermal_gap,
                        'thermal_spoke_width_mm': thermal_width,
                        'fill_mode': fill_mode,
                        'thermal_settings_valid': thermal_settings_valid,
                })
        except Exception as e:
            print(f"Error parsing zone: {e}")

    def _parse_text(self, node, mod_pos=None, mod_rot=0, mirrored=False):
        # (fp_text reference "Ref" (at X Y R) (layer "L") ...)
        # (gr_text "Text" (at X Y R) (layer "L") ...)
        try:
            # Simple text extraction if possible
            text = node[2] if len(node) > 2 else ""
            text = text.replace('"', '')

            at = self._get_node(node, 'at')
            px, py, prot = 0, 0, 0
            if at:
                px = float(at[1])
                py = float(at[2])
                if len(at) > 3: prot = float(at[3])
            
            # Transform
            final_pos = (px, py)
            final_rot = prot
            if mod_pos:
                final_pos = self._apply_transform((px, py), mod_pos, mod_rot, mirrored)
                final_rot = prot + mod_rot

            layer_n = self._get_node(node, 'layer')
            layer = layer_n[1].replace('"', '') if layer_n else "F.SilkS"
            
            effects = self._get_node(node, 'effects')
            size = (1, 1) # default size mm
            thickness = 0.15
            if effects:
                font = self._get_node(effects, 'font')
                if font:
                    sz = self._get_node(font, 'size')
                    if sz: size = (float(sz[1]), float(sz[2]))
                    th = self._get_node(font, 'thickness')
                    if th: thickness = float(th[1])

            self.drawings.append({
                'type': 'text',
                'text': text,
                'pos': final_pos,
                'rotation': final_rot,
                'size': size,
                'thickness': thickness,
                'layer': layer
            })
        except: pass

    def _apply_transform(self, pos, offset, angle, mirrored=False):
        """
        pos: (x, y)
        offset: (ox, oy)
        angle: degrees
        mirrored: bool (flip X before rotation)
        """
        px, py = pos
        ox, oy = offset
        
        if mirrored:
            px = -px
            
        if angle != 0:
            # KiCad Y-down: Positive angle is CCW (X -> -Y).
            # Standard math: Positive angle is CCW (X -> Y).
            # In Y-down, standard rotation matrix rotates CW visual.
            # So we negate angle to get CCW visual.
            rad = math.radians(-angle)
            c = math.cos(rad)
            s = math.sin(rad)
            rx = px * c - py * s
            ry = px * s + py * c
            px, py = rx, ry
            
        return (px + ox, py + oy)

    def _parse_footprint(self, node):
        # (footprint "Lib:Name" (layer "F.Cu") (at X Y R) ...)
        try:
            at = self._get_node(node, 'at')
            mod_x, mod_y = 0, 0
            mod_rot = 0
            if at:
                mod_x = float(at[1])
                mod_y = float(at[2])
                if len(at) > 3: mod_rot = float(at[3])
            
            layer_n = self._get_node(node, 'layer')
            layer = layer_n[1].replace('"', '') if layer_n else "F.Cu"
            mirrored = layer.startswith("B.") or layer.startswith("Back")

            # Capture Reference (RefDes)
            ref = "U?"
            properties = {}
            legacy_value = ""
            property_reference = ""
            for item in node:
                if isinstance(item, list) and len(item) > 2:
                    head = str(item[0]).replace('"', '')
                    if head == 'fp_text':
                        type_str = str(item[1]).replace('"', '')
                        if type_str == 'reference':
                            ref = str(item[2]).replace('"', '')
                        elif type_str == 'value':
                            legacy_value = str(item[2]).replace('"', '')

                    elif head == 'property':
                        prop_name = str(item[1]).replace('"', '')
                        properties[prop_name] = str(item[2]).replace('"', '')
                        if prop_name in ['Reference', 'reference']:
                            property_reference = str(item[2]).replace('"', '')
            ref = property_reference or ref

            model_path = ""
            model_node = self._get_node(node, 'model')
            if model_node and len(model_node) > 1:
                model_path = str(model_node[1]).replace('"', '')
            source_id = self._source_native_id(node)
            footprint_thermal = self._connection_override(node, f"KiCad footprint {ref}")
            footprint = {
                'reference': ref,
                'library': str(node[1]).replace('"', '') if len(node) > 1 else "",
                'at': (mod_x, mod_y),
                'rotation': mod_rot,
                'layer': layer,
                'model_path': model_path,
                'properties': properties,
                'value': properties.get('Value', legacy_value),
                'zone_connection_override': footprint_thermal['mode'],
                'zone_connection_declared': footprint_thermal['declared'],
                'thermal_gap_override_mm': footprint_thermal['thermal_gap_mm'],
                'thermal_spoke_width_override_mm': footprint_thermal['thermal_spoke_width_mm'],
                'thermal_settings_valid': footprint_thermal['valid'],
            }
            if source_id:
                footprint.update({'id': source_id, 'uuid': source_id})
            self.footprints.append(footprint)

            # Finds Pads and Drawings inside
            for item in node:
                if not isinstance(item, list) or not item: continue
                head = item[0]
                
                if head == 'pad':
                    self._parse_pad(
                        item, (mod_x, mod_y), mod_rot, mirrored=mirrored, ref=ref,
                        footprint_thermal=footprint_thermal,
                    )
                elif head == 'fp_text':
                     # Text is also usually explicit in position
                     self._parse_text(item, (mod_x, mod_y), mod_rot, mirrored=mirrored)
                elif head in ['fp_line', 'fp_circle', 'fp_arc', 'fp_poly']:
                    # Footprint graphics
                    # Assuming they are also explicit or library-linked in a way that 'mirrored' logic is redundant/harmful
                    self._parse_fp_graphic(item, (mod_x, mod_y), mod_rot, mirrored=mirrored)
        except: pass

    def _custom_pad_drill_rejection(self, node, size, pad_type):
        """Return a reason when a custom-pad drill is outside the admitted subset."""

        drill = self._get_node(node, 'drill')
        if not drill:
            return ""
        if str(pad_type).lower() != 'thru_hole':
            return "custom_drill_requires_plated_through_hole"
        if self._get_node(drill, 'offset') is not None:
            return "offset_custom_drill"
        try:
            if str(drill[1]).lower() == 'oval':
                if len(drill) < 4:
                    return "invalid_custom_drill"
                drill_size = (float(drill[2]), float(drill[3]))
            else:
                diameter = float(drill[1])
                drill_size = (diameter, diameter)
        except (TypeError, ValueError, IndexError):
            return "invalid_custom_drill"
        if (any(not math.isfinite(value) or value <= 0 for value in drill_size)
                or drill_size[0] >= size[0] or drill_size[1] >= size[1]):
            return "custom_drill_not_within_anchor"
        return ""

    def _parse_custom_pad_primitive_union(self, node, mirrored, size, drilled, items):
        """Admit a bounded filled polygon/circle compound as one resolved ring."""

        if not 1 <= len(items) <= 16:
            return {"status": "unsupported", "reason": "custom_primitive_count"}
        options = self._get_node(node, 'options')
        anchor = self._get_node(options, 'anchor') if options else None
        anchor_kind = str(anchor[1]).lower() if anchor and len(anchor) > 1 else 'rect'
        if anchor_kind != 'rect':
            return {"status": "unsupported", "reason": f"anchor_{anchor_kind}_union_pending"}
        polygons = [[
            (-size[0] / 2, -size[1] / 2), (size[0] / 2, -size[1] / 2),
            (size[0] / 2, size[1] / 2), (-size[0] / 2, size[1] / 2),
        ]]
        circle_count = 0
        circle_segments = 0
        maximum_sagitta = 0.0
        stroke_evidence = None
        for primitive in items:
            fill = self._get_node(primitive, 'fill')
            width = self._get_node(primitive, 'width')
            if not fill or len(fill) < 2 or str(fill[1]).lower() != 'yes':
                return {"status": "unsupported", "reason": "unfilled_custom_primitive"}
            try:
                if not width or len(width) < 2:
                    return {"status": "unsupported", "reason": "invalid_custom_primitive_width"}
                primitive_width = float(width[1])
                if not math.isfinite(primitive_width) or primitive_width < 0:
                    return {"status": "unsupported", "reason": "invalid_custom_primitive_width"}
            except (TypeError, ValueError):
                return {"status": "unsupported", "reason": "invalid_custom_primitive_width"}
            if primitive[0] == 'gr_poly':
                points_node = self._get_node(primitive, 'pts')
                raw_points = [item for item in (points_node[1:] if points_node else [])
                              if isinstance(item, list) and len(item) >= 3 and item[0] == 'xy']
                try:
                    polygon = [[float(item[1]), float(item[2])] for item in raw_points]
                except (TypeError, ValueError):
                    return {"status": "unsupported", "reason": "invalid_polygon_coordinate"}
                if (not 3 <= len(polygon) <= 4096
                        or any(not math.isfinite(value) or abs(value) > 1_000_000
                               for point in polygon for value in point)
                        or not is_simple_polygon(polygon)):
                    return {"status": "unsupported", "reason": "non_simple_polygon"}
                if primitive_width > 1e-12:
                    if len(items) != 1:
                        return {"status": "unsupported", "reason": "stroked_polygon_mixed_primitives"}
                    if not polygon_contains_polygon(polygon, polygons[0]):
                        return {"status": "unsupported", "reason": "stroke_anchor_not_contained"}
                    inflated, stroke_evidence = inflate_filled_simple_polygon_round_inside_v1(
                        polygon, primitive_width,
                    )
                    if not inflated:
                        return {"status": "unsupported", "reason": "stroke_topology_unsupported"}
                    polygons.append(inflated)
                else:
                    polygons.append(polygon)
                continue
            if primitive_width > 1e-12:
                return {"status": "unsupported", "reason": "stroked_custom_primitive"}
            if primitive[0] != 'gr_circle':
                return {"status": "unsupported", "reason": f"primitive_{str(primitive[0])[:64]}"}
            center_node = self._get_node(primitive, 'center')
            end_node = self._get_node(primitive, 'end')
            try:
                center = (float(center_node[1]), float(center_node[2]))
                end = (float(end_node[1]), float(end_node[2]))
            except (TypeError, ValueError, IndexError):
                return {"status": "unsupported", "reason": "invalid_circle_geometry"}
            if any(not math.isfinite(value) or abs(value) > 1_000_000 for value in (*center, *end)):
                return {"status": "unsupported", "reason": "invalid_circle_geometry"}
            radius = math.hypot(end[0] - center[0], end[1] - center[1])
            grid = 1e-8
            rounding_bound = grid / math.sqrt(2)
            if radius <= rounding_bound:
                return {"status": "unsupported", "reason": "circle_flattening_limit"}
            effective_radius = radius - rounding_bound
            count = 12
            while count <= 256:
                bound = radius - effective_radius * math.cos(math.pi / count) + rounding_bound
                if bound <= 0.001 and 2 * math.pi * radius / count <= 0.25:
                    break
                count += 1
            if count > 256:
                return {"status": "unsupported", "reason": "circle_flattening_limit"}
            start_angle = math.atan2(end[1] - center[1], end[0] - center[0])
            polygon = [[
                round(center[0] + effective_radius * math.cos(start_angle + 2 * math.pi * index / count), 8),
                round(center[1] + effective_radius * math.sin(start_angle + 2 * math.pi * index / count), 8),
            ] for index in range(count)]
            if not is_simple_polygon(polygon):
                return {"status": "unsupported", "reason": "circle_flattening_invalid"}
            polygons.append(polygon)
            circle_count += 1
            circle_segments += count
            maximum_sagitta = max(maximum_sagitta, bound)
        if sum(len(polygon) for polygon in polygons) > 4096:
            return {"status": "unsupported", "reason": "custom_primitive_vertex_budget"}
        resolved = union_simple_polygons(polygons)
        if not 3 <= len(resolved) <= 4096 or not is_simple_polygon(resolved):
            return {"status": "unsupported", "reason": "primitive_union_not_single_simple"}
        geometry = {
            "status": "supported", "coordinate_space": "pad_local_mm",
            "mirror_x": bool(mirrored), "positive_filled_polygon": resolved,
        }
        if circle_count:
            geometry["curve_approximation"] = {
                "method": "inscribed_equal_angle_v1",
                "maximum_sagitta_mm": maximum_sagitta,
                "source_circle_count": circle_count,
                "flattened_segment_count": circle_segments,
                "conservative_source_containment": True,
            }
        if stroke_evidence:
            geometry["stroke_approximation"] = stroke_evidence
        return geometry

    def _parse_custom_pad_geometry(self, node, mirrored, size, drilled, pad_type):
        """Resolve an admitted undrilled custom-pad boundary or fail closed."""

        if drilled:
            rejection = self._custom_pad_drill_rejection(node, size, pad_type)
            if rejection:
                return {"status": "unsupported", "reason": rejection}
        primitives = self._get_node(node, 'primitives')
        items = [item for item in (primitives[1:] if primitives else []) if isinstance(item, list) and item]
        width = self._get_node(items[0], 'width') if len(items) == 1 else None
        try:
            has_stroke = bool(width and len(width) > 1 and abs(float(width[1])) > 1e-12)
        except (TypeError, ValueError):
            has_stroke = True
        if len(items) != 1 or (items and items[0][0] == 'gr_circle') or has_stroke:
            return self._parse_custom_pad_primitive_union(node, mirrored, size, drilled, items)
        if len(items) != 1:
            return {"status": "unsupported", "reason": "multiple_or_missing_primitives"}
        primitive = items[0]
        if primitive[0] != 'gr_poly':
            return {"status": "unsupported", "reason": f"primitive_{str(primitive[0])[:64]}"}
        fill = self._get_node(primitive, 'fill')
        width = self._get_node(primitive, 'width')
        if not fill or len(fill) < 2 or str(fill[1]).lower() != 'yes':
            return {"status": "unsupported", "reason": "unfilled_polygon"}
        try:
            if width and abs(float(width[1])) > 1e-12:
                return {"status": "unsupported", "reason": "stroked_polygon"}
        except (TypeError, ValueError, IndexError):
            return {"status": "unsupported", "reason": "invalid_polygon_width"}
        points_node = self._get_node(primitive, 'pts')
        raw_points = [item for item in (points_node[1:] if points_node else [])
                      if isinstance(item, list) and len(item) >= 3 and item[0] == 'xy']
        try:
            points = [(float(item[1]), float(item[2])) for item in raw_points]
        except (TypeError, ValueError):
            return {"status": "unsupported", "reason": "invalid_polygon_coordinate"}
        if (not 3 <= len(points) <= 4096
                or any(not math.isfinite(value) or abs(value) > 1_000_000
                       for point in points for value in point)):
            return {"status": "unsupported", "reason": "invalid_polygon_coordinate"}

        def orientation(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        def on_segment(a, b, point):
            scale = max(*(abs(value) for item in (a, b, point) for value in item), 1.0)
            tolerance = 1e-12 * scale * scale
            return (abs(orientation(a, b, point)) <= tolerance
                    and min(a[0], b[0]) - tolerance <= point[0] <= max(a[0], b[0]) + tolerance
                    and min(a[1], b[1]) - tolerance <= point[1] <= max(a[1], b[1]) + tolerance)

        def intersects(a, b, c, d):
            values = (orientation(a, b, c), orientation(a, b, d),
                      orientation(c, d, a), orientation(c, d, b))
            scale = max(*(abs(value) for item in (a, b, c, d) for value in item), 1.0)
            tolerance = 1e-12 * scale * scale
            if (((values[0] > tolerance and values[1] < -tolerance)
                    or (values[0] < -tolerance and values[1] > tolerance))
                    and ((values[2] > tolerance and values[3] < -tolerance)
                    or (values[2] < -tolerance and values[3] > tolerance))):
                return True
            return ((abs(values[0]) <= tolerance and on_segment(a, b, c))
                    or (abs(values[1]) <= tolerance and on_segment(a, b, d))
                    or (abs(values[2]) <= tolerance and on_segment(c, d, a))
                    or (abs(values[3]) <= tolerance and on_segment(c, d, b)))

        area = sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, [*points[1:], points[0]]))
        edges = list(zip(points, [*points[1:], points[0]]))
        simple = abs(area) > 1e-18 and not any(
            (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 <= 1e-24
            for a, b in edges
        )
        for left, (a, b) in enumerate(edges):
            for right in range(left + 1, len(edges)):
                if right == left + 1 or (left == 0 and right == len(edges) - 1):
                    continue
                c, d = edges[right]
                if intersects(a, b, c, d):
                    simple = False
        if not simple:
            return {"status": "unsupported", "reason": "non_simple_polygon"}

        def contains(point):
            inside = False
            for first, second in edges:
                cross = orientation(first, second, point)
                if (abs(cross) <= 1e-12 and min(first[0], second[0]) <= point[0] <= max(first[0], second[0])
                        and min(first[1], second[1]) <= point[1] <= max(first[1], second[1])):
                    return True
                if (first[1] > point[1]) != (second[1] > point[1]):
                    crossing = first[0] + (second[0] - first[0]) * (point[1] - first[1]) / (second[1] - first[1])
                    if crossing > point[0]:
                        inside = not inside
            return inside

        options = self._get_node(node, 'options')
        anchor = self._get_node(options, 'anchor') if options else None
        anchor_kind = str(anchor[1]).lower() if anchor and len(anchor) > 1 else 'rect'
        if anchor_kind != 'rect':
            return {"status": "unsupported", "reason": f"anchor_{anchor_kind}_union_pending"}
        anchor_polygon = [
            (-size[0] / 2, -size[1] / 2), (size[0] / 2, -size[1] / 2),
            (size[0] / 2, size[1] / 2), (-size[0] / 2, size[1] / 2),
        ]
        resolved = union_two_simple_polygons(points, anchor_polygon)
        if len(resolved) < 3:
            return {"status": "unsupported", "reason": "anchor_polygon_union_invalid"}
        return {
            "status": "supported", "coordinate_space": "pad_local_mm",
            "mirror_x": bool(mirrored),
            "positive_filled_polygon": resolved,
        }

    def _parse_pad(self, node, mod_pos, mod_rot, mirrored=False, ref="U?", footprint_thermal=None):
        # (pad "1" smd rect (at X Y R) (size W H) (layers "F.Cu" ...) (net ...))
        try:
            name = node[1].replace('"', '')
            full_name = f"{ref}.{name}"
            ptype = node[2]
            shape = node[3]
            
            at = self._get_node(node, 'at')
            px, py, prot = 0, 0, 0
            if at:
                px = float(at[1])
                py = float(at[2])
                if len(at) > 3: prot = float(at[3])
                
            final_pos = self._apply_transform((px, py), mod_pos, mod_rot, mirrored)
            final_rot = prot + mod_rot
            
            size_n = self._get_node(node, 'size')
            size = (float(size_n[1]), float(size_n[2])) if size_n else (1, 1)
            
            layers_n = self._get_node(node, 'layers')
            layers = layers_n[1:] if layers_n else ["F.Cu"]
            layers = [l.replace('"', '') for l in layers]
            
            net_n = self._get_node(node, 'net')
            net_id, net_name = self._get_net_info(net_n)
            source_id = self._source_native_id(node)
            pad_thermal = self._connection_override(node, f"KiCad pad {source_id or full_name}")
            layer_overrides = {}
            padstack = self._get_node(node, 'padstack')
            if padstack is not None and self._contains_nested_node(padstack, 'zone_connect'):
                pad_thermal['valid'] = False
                self.diagnostics.append(
                    f"KiCad pad {source_id or full_name} has layer-specific zone connectivity pending typed layer retention."
                )

            # Preserve both the compatibility scalar and the authoritative
            # two-axis drill geometry. KiCad represents slotted holes as
            # ``(drill oval width height)``; discarding those dimensions turns
            # a through-hole pad into solid copper in downstream meshes.
            drill_n = self._get_node(node, 'drill')
            drill = 0
            drill_size = (0.0, 0.0)
            drill_shape = "none"
            if drill_n and len(drill_n) > 1:
                try:
                    if str(drill_n[1]).lower() == 'oval' and len(drill_n) > 3:
                        drill_size = (float(drill_n[2]), float(drill_n[3]))
                        drill_shape = "oval"
                        # Legacy consumers accept one diameter. The smaller
                        # slot axis is the conservative barrel aperture while
                        # drill_size remains authoritative for meshing.
                        drill = min(drill_size)
                    else:
                        drill = float(drill_n[1])
                        drill_size = (drill, drill)
                        drill_shape = "circle"
                except (TypeError, ValueError):
                    drill = 0
                    drill_size = (0.0, 0.0)
                    drill_shape = "none"
            
            pad = {
                'name': name,
                'component': ref,
                'component_pad': full_name,
                'type': ptype, 'shape': shape,
                'at': final_pos, 'rotation': final_rot,
                'size': size, 'layers': layers, 
                'layer': layers[0], # Primary layer
                'net_id': net_id, 'net_name': net_name,
                'drill': drill,
                'drill_size': drill_size,
                'drill_shape': drill_shape,
                'pad_kind': str(ptype).lower() if str(ptype).lower() in {'smd', 'thru_hole', 'np_thru_hole', 'connect'} else 'unknown',
                'zone_connection_override': pad_thermal['mode'],
                'zone_connection_declared': pad_thermal['declared'],
                'zone_connection_layer_overrides': layer_overrides,
                'thermal_gap_override_mm': pad_thermal['thermal_gap_mm'],
                'thermal_spoke_width_override_mm': pad_thermal['thermal_spoke_width_mm'],
                'thermal_spoke_angle_deg': pad_thermal['thermal_spoke_angle_deg'],
                'thermal_settings_valid': pad_thermal['valid'],
            }
            if source_id:
                pad.update({'id': source_id, 'uuid': source_id})
            # Preserve authoritative rounded/chamfered pad parameters. Missing
            # or malformed values must not become an invented square outline.
            for token in ('roundrect_rratio', 'chamfer_ratio'):
                shape_parameter = self._get_node(node, token)
                if shape_parameter is not None:
                    try:
                        value = float(shape_parameter[1])
                        if not math.isfinite(value) or not 0 <= value <= 1:
                            raise ValueError('invalid shape ratio')
                        pad[token] = value
                    except (IndexError, TypeError, ValueError):
                        pad[token] = None
                        self.diagnostics.append(f"Pad {source_id or full_name} has invalid {token}.")
            chamfer = self._get_node(node, 'chamfer')
            if chamfer is not None:
                pad['chamfer'] = [str(value) for value in chamfer[1:]]
            if str(shape).lower() == 'custom':
                custom_geometry = self._parse_custom_pad_geometry(
                    node, mirrored, size, drill_shape != "none", ptype,
                )
                pad['custom_geometry'] = custom_geometry
                if custom_geometry.get('status') != 'supported':
                    self.diagnostics.append(
                        f"Custom pad {source_id or full_name} is retained but solver-blocked: "
                        f"{custom_geometry.get('reason', 'unsupported_custom_geometry')}"
                    )
            self.pads.append(pad)
        except Exception as e:
            pass

    def _parse_drawing(self, node):
        # Global drawings: gr_line, gr_circle, gr_arc, gr_poly
        head = node[0]
        try:
            layer_n = self._get_node(node, 'layer')
            width_n = self._get_node(node, 'width')
            layer = layer_n[1].replace('"', '') if layer_n else "Eco1.User"
            width = float(width_n[1]) if width_n else 0.1
            
            if head == 'gr_line':
                start = self._get_node(node, 'start')
                end = self._get_node(node, 'end')
                if start and end:
                    self.drawings.append({
                        'type': 'line',
                        'start': (float(start[1]), float(start[2])),
                        'end': (float(end[1]), float(end[2])),
                        'layer': layer, 'width': width
                    })
            elif head == 'gr_circle':
                center = self._get_node(node, 'center')
                end = self._get_node(node, 'end')
                if center and end:
                    cx, cy = float(center[1]), float(center[2])
                    ex, ey = float(end[1]), float(end[2])
                    radius = math.hypot(ex-cx, ey-cy)
                    self.drawings.append({
                        'type': 'circle',
                        'center': (cx, cy), 'radius': radius,
                        'layer': layer, 'width': width
                    })
            elif head == 'gr_arc':
                # (gr_arc (start X Y) (mid X Y) (end X Y) ...)
                start = self._get_node(node, 'start')
                mid = self._get_node(node, 'mid')
                end = self._get_node(node, 'end')
                if start and mid and end:
                     self.drawings.append({
                        'type': 'arc_3pt',
                        'start': (float(start[1]), float(start[2])),
                        'mid': (float(mid[1]), float(mid[2])),
                        'end': (float(end[1]), float(end[2])),
                        'layer': layer, 'width': width
                    })
            elif head == 'gr_rect':
                start = self._get_node(node, 'start')
                end = self._get_node(node, 'end')
                if start and end:
                    x1, y1, x2, y2 = float(start[1]), float(start[2]), float(end[1]), float(end[2])
                    self.drawings.append({
                        'type': 'rect',
                        'points': [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)],
                        'layer': layer, 'width': width,
                    })
            elif head == 'gr_poly':
                points_node = self._get_node(node, 'pts')
                points = []
                for point in points_node[1:] if points_node else []:
                    if isinstance(point, list) and len(point) > 2 and point[0] == 'xy':
                        points.append((float(point[1]), float(point[2])))
                if len(points) >= 3:
                    if points[0] != points[-1]:
                        points.append(points[0])
                    if layer.endswith('.Cu'):
                        net_id, net_name = self._get_net_info(self._get_node(node, 'net'))
                        self.zones.append({
                            'id': self._source_native_id(node) or f'graphic-polygon-{len(self.zones)}',
                            'layer': layer,
                            'points': points,
                            'net_id': net_id,
                            'net_name': net_name,
                            'source_kind': 'graphic_polygon',
                        })
                    else:
                        self.drawings.append({'type': 'poly', 'points': points, 'layer': layer, 'width': width})
        except Exception as error:
            self.diagnostics.append(f"Unable to parse {head} drawing: {error}")

    def _parse_fp_graphic(self, node, mod_pos, mod_rot, mirrored=False):
        # Footprint graphics: fp_line, fp_circle, fp_arc, fp_poly
        head = node[0]
        try:
            # Not all graphics have start/end.
            layer_n = self._get_node(node, 'layer')
            width_n = self._get_node(node, 'width') # Or stroke > width
            
            # Layer usually "F.SilkS" or "F.CrtYd"
            layer = layer_n[1].replace('"', '') if layer_n else "F.SilkS"
            width = float(width_n[1]) if width_n else 0.1
            
            if head == 'fp_line':
                start = self._get_node(node, 'start')
                end = self._get_node(node, 'end')
                if start and end:
                    p1 = (float(start[1]), float(start[2]))
                    p2 = (float(end[1]), float(end[2]))
                    
                    t_p1 = self._apply_transform(p1, mod_pos, mod_rot, mirrored)
                    t_p2 = self._apply_transform(p2, mod_pos, mod_rot, mirrored)
                    
                    self.drawings.append({
                        'type': 'line',
                        'start': t_p1, 'end': t_p2,
                        'layer': layer, 'width': width
                    })
            elif head == 'fp_circle':
                center = self._get_node(node, 'center')
                end = self._get_node(node, 'end')
                if center and end:
                    p_c = (float(center[1]), float(center[2]))
                    p_e = (float(end[1]), float(end[2]))
                    
                    t_c = self._apply_transform(p_c, mod_pos, mod_rot, mirrored)
                    # Radius is distance, scaling not supported yet (KiCad doesn't scale usually)
                    radius = math.hypot(p_e[0]-p_c[0], p_e[1]-p_c[1])
                    
                    self.drawings.append({
                        'type': 'circle',
                        'center': t_c, 'radius': radius,
                        'layer': layer, 'width': width
                    })
            elif head == 'fp_arc':
                start = self._get_node(node, 'start')
                mid = self._get_node(node, 'mid')
                end = self._get_node(node, 'end')
                if start and mid and end:
                    p_s = (float(start[1]), float(start[2]))
                    p_m = (float(mid[1]), float(mid[2]))
                    p_e = (float(end[1]), float(end[2]))

                    t_s = self._apply_transform(p_s, mod_pos, mod_rot, mirrored)
                    t_m = self._apply_transform(p_m, mod_pos, mod_rot, mirrored)
                    t_e = self._apply_transform(p_e, mod_pos, mod_rot, mirrored)
                    
                    self.drawings.append({
                        'type': 'arc_3pt',
                        'start': t_s, 'mid': t_m, 'end': t_e,
                        'layer': layer, 'width': width
                    })

            elif head == 'fp_poly':
                pts_node = self._get_node(node, 'pts')
                if pts_node:
                    points = []
                    for pt in pts_node[1:]:
                        if pt[0] == 'xy':
                             lx, ly = float(pt[1]), float(pt[2])
                             tx, ty = self._apply_transform((lx, ly), mod_pos, mod_rot, mirrored)
                             points.append((tx, ty))
                    
                    if points:
                        # Polygons in footprints can be filled or outline? 
                        # usually filled if width=0, or outline if width > 0? 
                        # KiCad fp_poly usually just geometry. 
                        # We'll treat as 'zone' type for filled, or series of lines?
                        # Usually fp_poly is filled shape on Silk or Mask.
                        if layer.endswith('.Cu'):
                            self.zones.append({
                                'id': self._source_native_id(node) or f'footprint-polygon-{len(self.zones)}',
                                'layer': layer, 'net_id': 0, 'net_name': "",
                                'points': points, 'source_kind': 'footprint_graphic_polygon',
                            })
                        else:
                            self.drawings.append({'type': 'poly', 'points': points, 'layer': layer, 'width': width})

        except Exception as e:
            pass
