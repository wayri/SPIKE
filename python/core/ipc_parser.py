import xml.etree.ElementTree as ET
from pathlib import Path

class IpcParser:
    """
    Universal IPC-2581 Parser for SPIKE.
    Ingests IPC-2581 XML files and translates them into the internal SPIKE data model.
    """
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        
        # SPIKE Standard Data Structures
        self.layers = {}   
        self.stackup = []
        self.nets = {}     
        self.tracks = []   
        self.vias = []     
        self.pads = []     
        self.zones = []    
        self.drawings = [] 
        self.components = {} 
        self.board_bbox = {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
        
        self.unit_scale = 1.0 # Multiplier to convert to mm
        self.ns = {} # XML Namespace dict
        
        try:
            self.parse()
        except Exception as e:
            print(f"Error reading/parsing IPC-2581 file: {e}")
            import traceback
            traceback.print_exc()

    def parse(self):
        print(f"Parsing IPC-2581 Design ({self.filepath.name})...")
        tree = ET.parse(self.filepath)
        self.root = tree.getroot()
        
        # Handle namespaces (IPC-2581 uses namespaces heavily)
        match = self.root.tag.find('}')
        if match != -1:
            self.ns = {'ipc': self.root.tag[1:match]}
        else:
            self.ns = {'ipc': ''}
            
        self._determine_units()
        self._parse_stackup()
        self._parse_profile()
        self._parse_bom()
        self._parse_netlist()
        self._parse_features()
        print(f"Parsed: {len(self.nets)} nets, {len(self.tracks)} tracks, {len(self.pads)} pads, {len(self.zones)} zones.")

    def _find_all(self, parent, tag):
        """Helper to find all elements considering namespace."""
        if self.ns['ipc']:
            return parent.findall(f"ipc:{tag}", self.ns)
        return parent.findall(tag)

    def _find(self, parent, tag):
        """Helper to find first element considering namespace."""
        if self.ns['ipc']:
            return parent.find(f"ipc:{tag}", self.ns)
        return parent.find(tag)

    def _determine_units(self):
        units_elem = self._find(self.root, 'LogisticHeader/Unit')
        if units_elem is not None:
            u = units_elem.text.upper()
            if u == 'MILLIMETER': self.unit_scale = 1.0
            elif u == 'INCH': self.unit_scale = 25.4
            elif u == 'MILS': self.unit_scale = 0.0254
            else: self.unit_scale = 1.0
        else:
            self.unit_scale = 25.4 # Fallback assumption if missing

    def _parse_stackup(self):
        layer_idx = 0
        layer_elements = self._find_all(self.root, 'Ecad/CadHeader/Layer')
        for layer in layer_elements:
            layer_name = layer.get('name', f"Layer_{layer_idx}")
            layer_type = layer.get('layerFunction', 'UNKNOWN').upper()
            
            if layer_type in ['CONDUCTOR', 'PLANE']:
                self.layers[layer_idx] = {'name': layer_name, 'type': 'copper'}
                self.stackup.append({'name': layer_name, 'type': 'copper', 'thickness': 0.035, 'epsilon_r': 4.5})
                layer_idx += 1
            elif layer_type == 'DIELECTRIC':
                self.stackup.append({'name': layer_name, 'type': 'core', 'thickness': 1.0, 'epsilon_r': 4.5})

    def _parse_profile(self):
        # Very simplified profile extraction (usually in Step/Profile)
        steps = self._find_all(self.root, 'Ecad/CadData/Step')
        if not steps: return
        
        main_step = steps[0]
        profile = self._find(main_step, 'Profile')
        if profile is not None:
            min_x, min_y = 1e9, 1e9
            max_x, max_y = -1e9, -1e9
            
            for poly in self._find_all(profile, 'Polygon/PolyStepSegment'):
                x_elem = self._find(poly, 'x')
                y_elem = self._find(poly, 'y')
                if x_elem is not None and y_elem is not None:
                    x = float(x_elem.text) * self.unit_scale
                    y = float(y_elem.text) * self.unit_scale
                    min_x = min(min_x, x); max_x = max(max_x, x)
                    min_y = min(min_y, y); max_y = max(max_y, y)
                    
            if min_x < max_x:
                self.board_bbox = {'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y}
            else:
                self.board_bbox = {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100}

    def _parse_bom(self):
        bom_elem = self._find(self.root, 'LogisticHeader/Bom')
        if bom_elem is None: return
        
        for item in self._find_all(bom_elem, 'BomItem'):
            ref = self._find(item, 'RefDes')
            pkg = self._find(item, 'Package')
            if ref is not None:
                self.components[ref.text] = {
                    'pkg': pkg.text if pkg is not None else 'UNKNOWN',
                    'pins': {}
                }

    def _parse_netlist(self):
        nets_elem = self._find_all(self.root, 'Ecad/CadData/Net')
        for i, net in enumerate(nets_elem):
            net_name = net.get('name', f"NET_{i}")
            self.nets[i] = net_name
            
            for pin in self._find_all(net, 'PinRef'):
                ref = pin.get('componentRef')
                pin_num = pin.get('pin')
                if ref in self.components:
                    self.components[ref]['pins'][pin_num] = i

    def _parse_features(self):
        # We only parse the primary step for now
        steps = self._find_all(self.root, 'Ecad/CadData/Step')
        if not steps: return
        main_step = steps[0]
        
        layer_features = self._find_all(main_step, 'LayerFeature')
        for lf in layer_features:
            layer_name = lf.get('layerRef')
            
            # Extract features
            for feature in self._find_all(lf, 'Feature'):
                
                # 1. Tracks (Lines)
                line = self._find(feature, 'Line')
                if line is not None:
                    x1 = float(self._find(line, 'StartX').text) * self.unit_scale
                    y1 = float(self._find(line, 'StartY').text) * self.unit_scale
                    x2 = float(self._find(line, 'EndX').text) * self.unit_scale
                    y2 = float(self._find(line, 'EndY').text) * self.unit_scale
                    
                    self.tracks.append({
                        'start': [x1, y1], 'end': [x2, y2],
                        'width': 0.2, # Fallback, needs ProfileRef parsing for true width
                        'layer': layer_name,
                        'net': 0 # Fallback
                    })
                    
                # 2. Polygons (Zones)
                polygon = self._find(feature, 'Polygon')
                if polygon is not None:
                    pts = []
                    for seg in self._find_all(polygon, 'PolyStepSegment'):
                        x = float(self._find(seg, 'x').text) * self.unit_scale
                        y = float(self._find(seg, 'y').text) * self.unit_scale
                        pts.append([x, y])
                        
                    if len(pts) > 2:
                        self.zones.append({
                            'layer': layer_name,
                            'net': 0,
                            'points': pts
                        })
                        
                # 3. Pads (Locations with PadstackRefs)
                pad = self._find(feature, 'Pad')
                if pad is not None:
                    x = float(self._find(pad, 'x').text) * self.unit_scale
                    y = float(self._find(pad, 'y').text) * self.unit_scale
                    
                    self.pads.append({
                        'component': 'UNK', 'component_pad': '1',
                        'at': [x, y], 'net': 0, 'layer': layer_name,
                        'shape': 'circle', 'size': [1.0, 1.0] # Fallback
                    })
