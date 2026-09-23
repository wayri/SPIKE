"""
SPIKE 3D Viewport - PyVista Integration with 2D Fallback
=========================================================

Version: 0.6.0

This module provides the main viewport widget which defaults to a robust 2D 
wxPython renderer but can switch to a 3D PyVista renderer.
Now supports Pads, Zones, and Shapes with STRICT Net ID tracking.
"""

import wx
import sys
import math
import numpy as np
from .viewport2d import Viewport2D

try:
    import pyvista as pv
    import vtk
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False


class Viewport3D(wx.Panel):
    """
    Interactive 3D viewport using PyVista/VTK
    """
    def __init__(self, parent):
        global PYVISTA_AVAILABLE
        super().__init__(parent, style=wx.CLIP_CHILDREN)
        self.filaments = []
        self.meshes = {}
        self.mesh_buffers = {}
        self.full_mesh_cache = {}
        self.results_visible = False
        self.embedded = False
        self.on_net_click_cb = None
        self.on_pad_click_cb = None
        self.on_thermal_click_cb = None
        self.thermal_grid_cache = None
        
        if not PYVISTA_AVAILABLE:
            self._create_fallback_ui()
            return
        
        try:
            self._create_pyvista_ui()
        except Exception as e:
            print(f"3D: Failed to create plotter: {e}")
            PYVISTA_AVAILABLE = False
            self._create_fallback_ui(f"3D Error: {str(e)}")

    def _create_fallback_ui(self, error_msg="PyVista is not installed."):
        sizer = wx.BoxSizer(wx.VERTICAL)
        msg = wx.StaticText(self, label=error_msg, style=wx.ALIGN_CENTER)
        msg.SetForegroundColour(wx.Colour(255, 100, 100))
        sizer.AddStretchSpacer()
        sizer.Add(msg, 0, wx.ALIGN_CENTER)
        sizer.AddStretchSpacer()
        self.SetBackgroundColour(wx.Colour(30, 30, 30))
        self.SetSizer(sizer)

    def _create_pyvista_ui(self):
        self.plotter = pv.Plotter(window_size=[800, 600])
        self.plotter.set_background(color=[30/255, 30/255, 30/255])
        self.plotter.enable_mesh_picking(callback=self.on_mesh_picked, show=False, use_actor=True)
        
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.SetBackgroundColour(wx.Colour(30, 30, 30))
        
        if sys.platform == 'win32':
             wx.CallLater(1000, self._finish_embedding)

    def _finish_embedding(self, attempt=1):
        try:
            import ctypes
            wx_hwnd = self.GetHandle()
            rw = getattr(self.plotter, 'render_window', getattr(self.plotter, 'ren_win', None))
            if rw is None: 
                self.plotter.create_render_window()
                rw = getattr(self.plotter, 'render_window', getattr(self.plotter, 'ren_win', None))
            if rw: rw.Render()
            
            win_id_raw = rw.GetGenericWindowId() if rw else 0
            if win_id_raw:
                # Robust parsing for strings like " 0000000001a006e6 p void"
                win_str = str(win_id_raw).strip().split()[0]
                try:
                    vtk_hwnd = int(win_str, 16) if (len(win_str) > 8 or 'x' in win_str) else int(win_str)
                except:
                    import re
                    m = re.search(r'([0-9a-fA-F]+)', str(win_id_raw))
                    vtk_hwnd = int(m.group(1), 16) if m else 0

                if vtk_hwnd:
                    ctypes.windll.user32.ShowWindow(vtk_hwnd, 0)
                    ctypes.windll.user32.SetParent(vtk_hwnd, wx_hwnd)
                    current_style = ctypes.windll.user32.GetWindowLongA(vtk_hwnd, -16)
                    new_style = (current_style & ~0x80000000 & ~0x00C00000 & ~0x00040000 & ~0x00800000) | 0x40000000
                    ctypes.windll.user32.SetWindowLongA(vtk_hwnd, -16, new_style)
                    self.on_size(None)
                    ctypes.windll.user32.ShowWindow(vtk_hwnd, 5)
                    rw.Render()
                    self.embedded = True
        except Exception as e:
            print(f"3D: Embedding failed: {e}")

    def on_size(self, event):
        if hasattr(self, 'plotter'):
            rw = getattr(self.plotter, 'render_window', getattr(self.plotter, 'ren_win', None))
            if rw:
                w, h = self.GetClientSize()
                if h > 0 and w > 0:
                    rw.SetSize(w, h)
                    rw.Render()

    def on_mesh_picked(self, actor):
        if not actor or not hasattr(self, 'plotter'): return
        picked_pt = self.plotter.pick_position
        if picked_pt is None: return
        
        best_dist = float('inf')
        best_net = None
        best_id = None
        best_pad = None
        
        for layer, items in self.full_mesh_cache.items():
            for it in items:
                dist = 1e9
                if it['type'] == 'mesh': dist = np.linalg.norm(np.array(it['mesh'].center) - np.array(picked_pt))
                elif it['type'] == 'line':
                    mid = (np.array(it['pts'][0]) + np.array(it['pts'][1])) / 2
                    dist = np.linalg.norm(mid - np.array(picked_pt))
                
                if dist < best_dist:
                    best_dist = dist
                    best_net = it.get('net')
                    best_id = it.get('net_id')
                    best_pad = it.get('pad')
        
        if best_net and best_dist < 5.0:
            print(f"3D: Picked -> Net: {best_net} (ID: {best_id})")
            if self.on_pad_click_cb and best_pad: self.on_pad_click_cb(best_net, best_pad)
            elif self.on_net_click_cb: self.on_net_click_cb(best_net, best_id=best_id)

        if hasattr(self, 'thermal_grid_cache') and self.thermal_grid_cache is not None:
            if self.on_thermal_click_cb:
                self.on_thermal_click_cb(picked_pt, best_pad, best_net)

    def _is_valid_net(self, net_name):
        if not net_name: return False
        return str(net_name).strip().upper() not in ["", "0", "NET_0", "NONE", "<NO NET>"]

    def _match_net(self, it, target_id, target_name):
        """Unified matching logic for exclusivity"""
        if not target_name: return False
        it_id = it.get('net_id')
        # 1. Priority: Numeric ID match (must be > 0)
        if it_id is not None and target_id is not None:
            if it_id == target_id and target_id > 0: return True
        # 2. Fallback: Literal name match (avoid generic placeholders)
        it_name = str(it.get('net') or "").strip()
        if it_name == target_name:
            if it_name.upper() not in ["", "0", "NET_0", "NONE", "/"]: return True
        return False

    def highlight_net(self, net_name, net_id=None):
        if not PYVISTA_AVAILABLE: return
        target_id = net_id
        target_name = str(net_name).strip() if net_name else None
        
        # Clear existing highlights
        for name in ["NET_HIGHLIGHT_MAIN", "NET_HIGHLIGHT_ZONE", "PAD_HIGHLIGHT"]:
            if name in self.plotter.actors: self.plotter.remove_actor(name)
            
        # Dim all others
        for actor_name in self.plotter.actors:
            if any(s in actor_name for s in ["_Tracks", "_Pads", "Substrate", "Vias", "TH_Barrels"]):
                self.plotter.actors[actor_name].GetProperty().SetOpacity(
                    0.15 if target_name else (0.3 if "Substrate" in actor_name else 1.0)
                )

        if not target_name: 
            self.plotter.render()
            return

        h_meshes = []
        h_zones = []
        for layer, items in self.full_mesh_cache.items():
            for it in items:
                if self._match_net(it, target_id, target_name):
                    if it['type'] == 'mesh':
                        if it.get('is_zone'): h_zones.append(it['mesh'])
                        else: h_meshes.append(it['mesh'])
                    elif it['type'] == 'line':
                        pd = pv.PolyData(np.array(it['pts']), lines=np.array([[2, 0, 1]]))
                        h_meshes.append(pd.tube(radius=it['w']/1.3, n_sides=8))

        if h_meshes:
            combined = pv.merge(h_meshes).translate([0, 0, 0.4])
            self.plotter.add_mesh(combined, color=[0, 1, 1], name="NET_HIGHLIGHT_MAIN", opacity=1.0) # Cyan
        if h_zones:
            combined = pv.merge(h_zones).translate([0, 0, 0.3])
            self.plotter.add_mesh(combined, color=[0, 1, 1], name="NET_HIGHLIGHT_ZONE", opacity=0.5)
        self.plotter.render()

    def clear_highlight(self):
        self.highlight_net(None)

    def _init_layer_specs(self):
        self.layer_specs = {
            'F.Cu':      {'z': 0.0,    'th': 0.035, 'col': [0.8, 0.1, 0.1]},
            'In1.Cu':    {'z': -0.5,   'th': 0.035, 'col': [0.8, 0.6, 0.1]},
            'In2.Cu':    {'z': -1.0,   'th': 0.035, 'col': [0.8, 0.0, 0.8]},
            'B.Cu':      {'z': -1.6,   'th': 0.035, 'col': [0.1, 0.8, 0.1]},
            'Edge.Cuts': {'z': -0.8,   'th': 1.6,   'col': [0.5, 0.5, 0.5]},
            'Vias':      {'z': -0.8,   'th': 1.6,   'col': [0.7, 0.7, 0.7]},
            'TH_Barrels':{'z': -0.8,   'th': 1.6,   'col': [0.7, 0.7, 0.7]},
            'Default':   {'z': 0.0,    'th': 0.01,  'col': [0.5, 0.5, 0.5]}
        }

    def _get_z(self, layer, item_type='track'):
        if not hasattr(self, 'layer_specs'): self._init_layer_specs()
        spec = self.layer_specs.get(layer, self.layer_specs['Default'])
        z = spec['z']
        if item_type == 'pad': z += 0.01
        elif item_type == 'track': z += 0.005
        return z

    def add_line(self, start, end, width, layer, name=None, net_id=None):
        if layer not in self.mesh_buffers: self.mesh_buffers[layer] = []
        z = self._get_z(layer, 'track')
        self.mesh_buffers[layer].append({'type': 'line', 'pts': [[start[0], start[1], z], [end[0], end[1], z]], 'w': width, 'net': name, 'net_id': net_id})
        self.filaments.append({'type': 'line', 'net_id': net_id})

    def add_pad(self, shape, pos, size, rotation, layer, net_name=None, net_id=None, drill=0, pad_name=None):
        if layer not in self.mesh_buffers: self.mesh_buffers[layer] = []
        z = self._get_z(layer, 'pad')
        w, h = size
        
        # Improved Pad Mesh with Drill Hole
        if shape in ['circle', 'oval'] and drill > 0:
            mesh = pv.Disc(outer=max(w,h)/2, inner=drill/2, resolution=24)
            if shape == 'oval' and w != h: mesh.scale([w/max(w,h), h/max(w,h), 1], inplace=True)
        else:
            mesh = pv.Disc(outer=max(w,h)/2, resolution=24) if shape in ['circle', 'oval'] else pv.Plane(i_size=w, j_size=h)
            if shape == 'oval' and w != h: mesh.scale([w/max(w,h), h/max(w,h), 1], inplace=True)
            
        if rotation: mesh.rotate_z(-rotation, inplace=True)
        mesh.translate([pos[0], pos[1], z], inplace=True)
        self.mesh_buffers[layer].append({'type': 'mesh', 'mesh': mesh, 'net': net_name, 'net_id': net_id, 'pad': pad_name})
        self.filaments.append({'type': 'pad', 'net_id': net_id})
        
        if drill > 0:
            if "TH_Barrels" not in self.mesh_buffers: self.mesh_buffers["TH_Barrels"] = []
            # Make barrel a slightly chunky cylinder for visibility
            b = pv.Cylinder(center=[pos[0], pos[1], -0.8], direction=[0,0,1], radius=drill/2, height=1.6, resolution=24)
            self.mesh_buffers["TH_Barrels"].append({'type': 'mesh', 'mesh': b, 'net': net_name, 'net_id': net_id})

    def add_via(self, x, y, size, drill, net_name=None, net_id=None, z_start=0.0, z_end=-1.6):
        if "Vias" not in self.mesh_buffers: self.mesh_buffers["Vias"] = []
        # Pad Part
        h = abs(z_start - z_end)
        z_center = (z_start + z_end) / 2.0
        pad = pv.Disc(outer=size/2, inner=drill/2, resolution=16).translate([x, y, 0])
        self.mesh_buffers["Vias"].append({'type': 'mesh', 'mesh': pad, 'net': net_name, 'net_id': net_id})
        # Barrel Part
        barrel = pv.Cylinder(center=[x, y, z_center], direction=[0,0,1], radius=drill/2, height=h, resolution=16)
        self.mesh_buffers["Vias"].append({'type': 'mesh', 'mesh': barrel, 'net': net_name, 'net_id': net_id})
        self.filaments.append({'type': 'via', 'net_id': net_id})

    def add_zone(self, points, layer, net_name=None, net_id=None):
        if layer not in self.mesh_buffers: self.mesh_buffers[layer] = []
        z = self._get_z(layer, 'zone')
        pts = np.array([[p[0], p[1], z] for p in points])
        if len(pts) < 3: return
        faces = np.hstack([[len(pts)], np.arange(len(pts))])
        cloud = pv.PolyData(pts, faces=faces)
        self.mesh_buffers[layer].append({'type': 'mesh', 'mesh': cloud.triangulate(), 'net': net_name, 'net_id': net_id, 'is_zone': True})

    def add_circle(self, center, radius, layer, width=0, filled=False, net_name=None, net_id=None):
        if layer not in self.mesh_buffers: self.mesh_buffers[layer] = []
        z = self._get_z(layer)
        mesh = pv.Disc(center=[center[0], center[1], z], inner=0 if filled else radius-width, outer=radius)
        self.mesh_buffers[layer].append({'type': 'mesh', 'mesh': mesh, 'net': net_name, 'net_id': net_id})

    def add_filament(self, start, end, width, thickness, color='copper', name=None, layer=None, net_id=None):
        self.add_line(start, end, width, layer or "Default", name, net_id=net_id)

    def add_arc(self, center, radius, start_angle, end_angle, layer, width=0, net_name=None, net_id=None):
        """Minimal arc support for 3D"""
        if not PYVISTA_AVAILABLE: return
        # Approximate with 10 segments
        z = self._get_z(layer)
        for i in range(10):
            a1 = math.radians(start_angle + (end_angle - start_angle) * i / 10.0)
            a2 = math.radians(start_angle + (end_angle - start_angle) * (i + 1) / 10.0)
            p1 = [center[0] + radius * math.cos(a1), center[1] + radius * math.sin(a1), z]
            p2 = [center[0] + radius * math.cos(a2), center[1] + radius * math.sin(a2), z]
            self.add_line(p1, p2, width, layer, net_name, net_id=net_id)

    def add_text(self, text, pos, rotation, size, layer, thick=0):
        # 3D text is expensive and often fails in VTK/wx embedding
        pass

    def add_board_substrate(self, min_x, max_x, min_y, max_y, thickness=1.6):
        if not PYVISTA_AVAILABLE: return
        box = pv.Box(bounds=[min_x, max_x, min_y, max_y, -thickness, 0])
        self.plotter.add_mesh(box, color=[0.1, 0.3, 0.1], opacity=0.3, pickable=False, name="Substrate")
        self.plotter.set_focus([(min_x+max_x)/2, (min_y+max_y)/2, -thickness/2])

    def render_geometry(self):
        if not PYVISTA_AVAILABLE or not self.mesh_buffers: return
        self._init_layer_specs()
        for layer, items in self.mesh_buffers.items():
            spec = self.layer_specs.get(layer, self.layer_specs['Default'])
            lines = [it for it in items if it['type'] == 'line']
            meshes = [it for it in items if it['type'] == 'mesh']
            if lines:
                pd = pv.PolyData(np.concatenate([it['pts'] for it in lines]), lines=np.array([[2, 2*i, 2*i+1] for i in range(len(lines))]).flatten())
                self.plotter.add_mesh(pd.tube(radius=lines[0]['w']/2, n_sides=6), color=spec['col'], name=f"{layer}_Tracks")
            if meshes:
                combined = pv.merge([it['mesh'] for it in meshes])
                self.plotter.add_mesh(combined, color=spec['col'], name=f"{layer}_Pads")
        self.full_mesh_cache = {l: list(its) for l, its in self.mesh_buffers.items()}
        self.mesh_buffers = {}
        self.plotter.reset_camera()
        self.plotter.render()

    def clear(self):
        if hasattr(self, 'plotter'):
            self.plotter.clear()
            self.mesh_buffers = {}
            self.full_mesh_cache = {}

    def set_on_net_click_cb(self, cb): self.on_net_click_cb = cb
    def set_on_thermal_click_cb(self, cb): self.on_thermal_click_cb = cb
    def set_on_pad_click_cb(self, cb): self.on_pad_click_cb = cb
    def set_layer_visibility(self, layer, visible):
        if not PYVISTA_AVAILABLE: return
        for s in ["_Tracks", "_Pads"]:
            name = f"{layer}{s}"
            if name in self.plotter.actors: self.plotter.actors[name].SetVisibility(visible)
        self.plotter.render()
    def set_layer_opacity(self, layer, opacity):
        if not PYVISTA_AVAILABLE: return
        for suffix in ["_Tracks", "_Pads"]:
            name = f"{layer}{suffix}"
            if name in self.plotter.actors:
                self.plotter.actors[name].GetProperty().SetOpacity(opacity)
        self.plotter.render()

    def zoom_extents(self):
        """Reset the camera to show all rendered geometry."""
        if not PYVISTA_AVAILABLE: return
        self.plotter.reset_camera()
        self.plotter.render()

    def highlight_failed_components(self, failed_pads):
        if not PYVISTA_AVAILABLE: return
        if "THERMAL_FAILURES" in self.plotter.actors:
            self.plotter.remove_actor("THERMAL_FAILURES")
        if not failed_pads:
            self.plotter.render()
            return

        failed_pad_ids = set(failed_pads)
        h_meshes = []
        for items in self.full_mesh_cache.values():
            for item in items:
                if item.get('pad') in failed_pad_ids and item.get('type') == 'mesh':
                    h_meshes.append(item['mesh'])

        if h_meshes:
            combined = pv.merge(h_meshes).translate([0, 0, 0.5])
            self.plotter.add_mesh(combined, color=[1.0, 0.0, 0.0], name="THERMAL_FAILURES", opacity=1.0)
        self.plotter.render()

    def set_electrical_data(self, data):
        """Store electrical data for heatmaps"""
        self.electrical_data = data
        self.units = getattr(self, 'units', 'A/mm²')
        
    def set_units(self, unit_str):
        self.units = unit_str
        if hasattr(self, 'current_heatmap_mode'):
            self.update_heatmap_mode(self.current_heatmap_mode)

    def update_heatmap_mode(self, mode):
        """Switch between Raw, Voltage, Voltage Drop, Current Density"""
        if not PYVISTA_AVAILABLE: return
        self.current_heatmap_mode = mode
        
        # 1. Clean up old heatmaps
        for name in ["ELEC_HEATMAP_POINTS", "ELEC_HEATMAP_LINES", "ELEC_HEATMAP_ZONES"]:
            if name in self.plotter.actors:
                self.plotter.remove_actor(name)
                
        # 2. Toggle Raw Geometry Visibility
        raw_opacity = 0.05 if mode != "Raw Geometry" else 1.0
        for layer, spec in self.layer_specs.items():
            for s in ["_Tracks", "_Pads"]:
                name = f"{layer}{s}"
                if name in self.plotter.actors:
                    self.plotter.actors[name].GetProperty().SetOpacity(raw_opacity)
                    
        if mode == "Raw Geometry" or not hasattr(self, 'electrical_data'):
            self.plotter.render()
            return
            
        data = self.electrical_data
        
        if mode in ["Voltage Map", "Voltage Drop", "AC Impedance"]:
            # Plot Nodal Voltage Field
            pts = np.array([coord for coord, _ in data['nodes'].items()])
            vals = data['V']
            
            if mode == "Voltage Drop":
                vals = (data['v_source'] - vals) * 1000.0 # mV
            
            # Create a point cloud
            cloud = pv.PolyData(pts)
            cloud["Scalars"] = vals
            
            # Triangulate to create a continuous 2D surface across nodes
            surf = cloud.delaunay_2d()
            
            # Map colors
            cmap = "turbo" if mode == "Voltage Map" else "inferno"
            self.plotter.add_mesh(surf, scalars="Scalars", cmap=cmap, opacity=0.85, name="ELEC_HEATMAP_POINTS", show_scalar_bar=True)
            
        elif mode == "Current Density":
            # Plot Branch Currents on Lines
            # We need to map J to the lines
            line_pts = []
            line_lines = []
            j_vals = []
            
            # Apply Unit Conversion
            unit_mult = 1.0
            if self.units == 'A/mil²': unit_mult = 1.0 / 1550.0
            elif self.units == 'mA/mm²': unit_mult = 1000.0
            
            idx = 0
            for i, edge in enumerate(data['edges']):
                n1, n2 = edge
                # Find coords for n1, n2
                # In Python <3.7 dict order isn't guaranteed, but we saved nodes inversely
                # Actually data['nodes'] maps (x,y,z) -> id.
                coord1 = list(data['nodes'].keys())[list(data['nodes'].values()).index(n1)]
                coord2 = list(data['nodes'].keys())[list(data['nodes'].values()).index(n2)]
                
                j = data['filaments'][i]['J'] * unit_mult
                
                line_pts.append(coord1)
                line_pts.append(coord2)
                line_lines.append([2, idx, idx+1])
                j_vals.append(j)
                idx += 2
                
            if line_pts:
                lines_pd = pv.PolyData(np.array(line_pts), lines=np.array(line_lines).flatten())
                # PolyData assigns scalars to points, we have scalar per cell (line)
                lines_pd.cell_data["Current Density"] = j_vals
                tubes = lines_pd.tube(radius=0.1, n_sides=6)
                self.plotter.add_mesh(tubes, scalars="Current Density", cmap="hot", name="ELEC_HEATMAP_LINES", show_scalar_bar=True)
                
        # Draw Capacitor Hotspots if available
        if 'cap_hotspots' in data and data['cap_hotspots']:
            h_pts = []
            h_labels = []
            for idx, h in enumerate(data['cap_hotspots']):
                # Draw at z + 1.0 to hover above the board
                h_pts.append([h['x'], h['y'], h['z'] + 1.0])
                h_labels.append(f"Cap{idx+1}: {h['label']}")
                
            if h_pts:
                pts_array = np.array(h_pts)
                poly = pv.PolyData(pts_array)
                self.plotter.add_mesh(poly, color="cyan", point_size=15, render_points_as_spheres=True, name="CAP_HOTSPOTS_PTS")
                self.plotter.add_point_labels(poly, h_labels, point_size=0, font_size=14, text_color="cyan", name="CAP_HOTSPOTS_LBLS", shape_color="black", shape_opacity=0.7)
                
        self.plotter.render()

    def add_thermal_heatmap(self, T_grid, dx, dy, xmin, ymin):
        if not HAS_PV or self.plotter is None: return
        import pyvista as pv
        import numpy as np
        nz, ny, nx = T_grid.shape
        T_top = T_grid[0]
        x_pts = np.linspace(xmin, xmin + nx*dx, nx)
        y_pts = np.linspace(ymin, ymin + ny*dy, ny)
        x, y = np.meshgrid(x_pts, y_pts)
        z = np.full_like(x, 1.0)
        grid = pv.StructuredGrid(x, y, z)
        grid.point_data["Temperature (C)"] = T_top.flatten()
        self.plotter.add_mesh(grid, scalars="Temperature (C)", cmap="inferno", opacity=0.85, name="THERMAL_HEATMAP", show_scalar_bar=True)
        self.plotter.render()
