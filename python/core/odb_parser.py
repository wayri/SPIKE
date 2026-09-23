import os
import zipfile
import tempfile
import shutil
import math
from pathlib import Path

class OdbParser:
    """
    Universal ODB++ Parser for SPIKE.
    Ingests ODB++ ZIP archives and translates them into the internal SPIKE data model.
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

        self.temp_dir = None
        self.odb_root = None
        self.step_name = None
        self.unit_scale = 1.0 # Multiplier to convert to mm
        
        try:
            self._extract_archive()
            if self.odb_root:
                self.parse()
        except Exception as e:
            print(f"Error reading/parsing ODB++ file: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._cleanup()

    def _extract_archive(self):
        self.temp_dir = tempfile.mkdtemp(prefix="spike_odb_")
        print(f"Extracting ODB++ to {self.temp_dir}...")
        
        with zipfile.ZipFile(self.filepath, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)
            
        for root, dirs, files in os.walk(self.temp_dir):
            if 'matrix' in dirs and 'steps' in dirs:
                self.odb_root = Path(root)
                break
                
        if not self.odb_root:
            raise ValueError("Invalid ODB++ archive: Missing 'matrix' or 'steps' directories.")
            
        steps_dir = self.odb_root / 'steps'
        step_dirs = [d for d in os.listdir(steps_dir) if (steps_dir / d).is_dir()]
        if 'cad' in step_dirs:
            self.step_name = 'cad'
        elif step_dirs:
            self.step_name = step_dirs[0]
        else:
            raise ValueError("No steps found in ODB++ archive.")

    def _cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except: pass

    def parse(self):
        print(f"Parsing ODB++ Design (Step: {self.step_name})...")
        self._parse_matrix()
        self._determine_units()
        self._parse_profile()
        self._parse_eda()
        self._parse_layers()
        print(f"Parsed: {len(self.nets)} nets, {len(self.tracks)} tracks, {len(self.pads)} pads, {len(self.zones)} zones.")

    def _parse_matrix(self):
        matrix_file = self.odb_root / 'matrix' / 'matrix'
        if not matrix_file.exists(): return
        
        layer_idx = 0
        with open(matrix_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        current_layer = None
        for line in lines:
            parts = line.strip().split('=')
            if len(parts) >= 2:
                if parts[0] == 'LAYER':
                    current_layer = {'name': parts[1], 'type': 'unknown', 'thickness': 0.035, 'epsilon_r': 4.5}
                elif parts[0] == 'TYPE' and current_layer:
                    if parts[1] == 'SIGNAL':
                        current_layer['type'] = 'copper'
                        self.layers[layer_idx] = {'name': current_layer['name'], 'type': 'copper'}
                        layer_idx += 1
                        self.stackup.append(current_layer)
                    elif parts[1] == 'DIELECTRIC':
                        current_layer['type'] = 'core'
                        self.stackup.append(current_layer)

    def _determine_units(self):
        # Look for UNIT header in attrlist or profile
        profile_file = self.odb_root / 'steps' / self.step_name / 'profile'
        if profile_file.exists():
            with open(profile_file, 'r') as f:
                head = f.read(256)
                if 'UNIT=INCH' in head: self.unit_scale = 25.4
                elif 'UNIT=MM' in head: self.unit_scale = 1.0
                elif 'UNIT=MIL' in head: self.unit_scale = 0.0254
                else: self.unit_scale = 25.4 # Default heuristic for ODB++
        else:
            self.unit_scale = 25.4

    def _parse_profile(self):
        profile_file = self.odb_root / 'steps' / self.step_name / 'profile'
        if not profile_file.exists(): return
        
        min_x, min_y = 1e9, 1e9
        max_x, max_y = -1e9, -1e9
        
        with open(profile_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if not parts: continue
                if parts[0] == 'L' and len(parts) >= 5:
                    x1, y1, x2, y2 = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    min_x = min(min_x, x1, x2)
                    max_x = max(max_x, x1, x2)
                    min_y = min(min_y, y1, y2)
                    max_y = max(max_y, y1, y2)
                elif parts[0] in ['OB', 'OS']:
                    x, y = float(parts[1]), float(parts[2])
                    min_x = min(min_x, x); max_x = max(max_x, x)
                    min_y = min(min_y, y); max_y = max(max_y, y)
                
        if min_x < max_x:
            self.board_bbox = {
                'min_x': min_x * self.unit_scale, 
                'max_x': max_x * self.unit_scale, 
                'min_y': min_y * self.unit_scale, 
                'max_y': max_y * self.unit_scale
            }

    def _parse_eda(self):
        eda_file = self.odb_root / 'steps' / self.step_name / 'eda' / 'data'
        if not eda_file.exists(): return
        
        with open(eda_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Parse Nets
        for line in lines:
            parts = line.strip().split()
            if not parts: continue
            if parts[0] == 'NET':
                # Format: NET <name> <id>
                if len(parts) >= 3:
                    net_id = int(parts[2]) if parts[2].isdigit() else len(self.nets)
                    self.nets[net_id] = parts[1]

        # Parse Components
        for line in lines:
            parts = line.strip().split()
            if not parts: continue
            if parts[0] == 'CMP':
                if len(parts) >= 3:
                    ref = parts[1]
                    pkg = parts[2]
                    self.components[ref] = {'pkg': pkg, 'pins': {}}

        # Parse Pins and map to Nets
        current_net = 0
        for line in lines:
            parts = line.strip().split()
            if not parts: continue
            if parts[0] == 'NET':
                current_net = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else current_net + 1
            elif parts[0] == 'PN':
                # PN <ref> <pin>
                if len(parts) >= 3:
                    ref, pin = parts[1], parts[2]
                    if ref in self.components:
                        self.components[ref]['pins'][pin] = current_net

    def _parse_layers(self):
        layers_dir = self.odb_root / 'steps' / self.step_name / 'layers'
        if not layers_dir.exists(): return
        
        name_to_id = {v['name']: k for k, v in self.layers.items()}
        
        for layer_name in os.listdir(layers_dir):
            if layer_name not in name_to_id: continue
            
            features_file = layers_dir / layer_name / 'features'
            if not features_file.exists(): continue
            
            # Dictionary for symbols mapping per layer
            # Format: $ <id> <symbol_name>
            sym_map = {}
            with open(features_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line in lines:
                parts = line.strip().split()
                if not parts: continue
                
                # Header mapping
                if parts[0].startswith('$'):
                    sym_id = parts[0][1:]
                    sym_map[sym_id] = parts[1]
                    continue
                
                # Geometries
                try:
                    # Line: L x1 y1 x2 y2 sym_id polarity dcode net_id
                    if parts[0] == 'L' and len(parts) >= 6:
                        x1, y1 = float(parts[1]) * self.unit_scale, float(parts[2]) * self.unit_scale
                        x2, y2 = float(parts[3]) * self.unit_scale, float(parts[4]) * self.unit_scale
                        sym_id = parts[5]
                        
                        width = 0.2
                        if sym_id in sym_map:
                            sym_name = sym_map[sym_id].lower()
                            if sym_name.startswith('r'): # r20 = round 20 mils
                                try:
                                    width = float(sym_name[1:]) * self.unit_scale
                                except ValueError:
                                    pass
                        
                        self.tracks.append({
                            'start': [x1, y1], 'end': [x2, y2],
                            'width': width, 'layer': layer_name, 'net': 0
                        })
                        
                    # Pad/Flash: P x y sym_id polarity dcode net_id
                    elif parts[0] == 'P' and len(parts) >= 4:
                        x, y = float(parts[1]) * self.unit_scale, float(parts[2]) * self.unit_scale
                        sym_id = parts[3]
                        
                        shape = 'circle'
                        size = [1.0, 1.0]
                        if sym_id in sym_map:
                            sym_name = sym_map[sym_id].lower()
                            if sym_name.startswith('r'):
                                try:
                                    dia = float(sym_name[1:]) * self.unit_scale
                                    size = [dia, dia]
                                except: pass
                            elif sym_name.startswith('s'): # s10x20
                                try:
                                    shape = 'rect'
                                    dims = sym_name[1:].split('x')
                                    if len(dims) == 2:
                                        size = [float(dims[0])*self.unit_scale, float(dims[1])*self.unit_scale]
                                except: pass
                                
                        self.pads.append({
                            'component': 'UNK', 'component_pad': '1',
                            'at': [x, y], 'net': 0, 'layer': layer_name,
                            'shape': shape, 'size': size
                        })
                        
                    # Surface/Polygon: S <polarity> ...
                    elif parts[0] == 'S':
                        # Polygons in ODB++ follow the S tag and are built using contour traces.
                        # For simulation purposes, we extract the bounding points of the surface.
                        # Proper parsing requires iterating following OB/OS tags to build a Path.
                        # We will skip complex hole parsing for Phase 6 approximation and just grab exterior contours.
                        pass
                        
                    # OB/OS (Outline boundary / Segment) - part of S
                    elif parts[0] in ['OB', 'OS']:
                        # Quick heuristic: convert to zone points
                        x, y = float(parts[1]) * self.unit_scale, float(parts[2]) * self.unit_scale
                        if not hasattr(self, '_current_zone'):
                            self._current_zone = []
                        self._current_zone.append([x, y])
                        
                    elif parts[0] == 'OE': # Outline End
                        if hasattr(self, '_current_zone') and len(self._current_zone) > 2:
                            self.zones.append({
                                'layer': layer_name,
                                'net': 0,
                                'points': list(self._current_zone)
                            })
                        self._current_zone = []
                        
                except Exception as ex:
                    # Fail silently for complex unmapped records
                    pass
