import wx
import math

class Viewport2D(wx.Panel):
    """
    Robust 2D PCB Viewer using wx.GraphicsContext
    Functions as a fallback when 3D visualization fails.
    """
    def __init__(self, parent):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(30, 30, 30))
        
        self.filaments = [] 
        self.layers_visible = {} 
        self.layers_opacity = {} 
        self.on_net_click_cb = None # Callback for bi-directional sync
        self.on_pad_click_cb = None
        self.highlighted_net = None # Initialize explicitly
        self.highlighted_net_id = None
        self.highlighted_pad = None
        
        # View State
        self.scale = 10.0 
        self.offset_x = 0
        self.offset_y = 0
        self.is_dragging = False
        self.last_mouse = (0, 0)
        
        # Events
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_zoom)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_mouse_up)
        self.Bind(wx.EVT_MOTION, self.on_mouse_move)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.on_capture_lost)
        
        # Colors - KiCad "Black" Theme Approximate
        self.colors = {
            'F.Cu': wx.Colour(148, 26, 28, 230),      # Dark Red
            'B.Cu': wx.Colour(27, 148, 27, 230),      # Dark Green
            'In1.Cu': wx.Colour(194, 194, 0, 230),    # Yellow
            'In2.Cu': wx.Colour(194, 0, 194, 230),    # Magenta
            'Vias': wx.Colour(180, 180, 180, 255),    # Grey/Silver
            'Edge.Cuts': wx.Colour(255, 255, 100, 255), # Yellow-ish
            'F.Paste': wx.Colour(128, 128, 128, 100), # Grey Translucent
            'B.Paste': wx.Colour(128, 128, 128, 100),
            'F.Mask': wx.Colour(128, 0, 128, 60),     # Purple Translucent
            'B.Mask': wx.Colour(128, 0, 128, 60),
            'F.SilkS': wx.Colour(230, 230, 230, 220), # White
            'B.SilkS': wx.Colour(230, 20, 230, 220),  # Pink/Magenta for back silk?
            'Default': wx.Colour(150, 150, 150, 200)
        }
        
        self.highlight_col = wx.Colour(0, 255, 255, 255) 
        self.mirrored = False

    def set_view(self, view_type):
        if view_type == 'top':
            self.mirrored = False
            self.zoom_extents() # Or just refresh?
        elif view_type == 'bottom':
            self.mirrored = True
            self.zoom_extents()
        # 'iso' ignored in 2D
        self.Refresh()

    def _add_item(self, item):
        self.filaments.append(item)
        layer = item.get('layer', 'Default')
        if layer not in self.layers_visible:
            self.layers_visible[layer] = True

    def add_text(self, text, pos, rotation, size, layer, thick=0):
         self._add_item({
            'type': 'text',
            'text': text,
            'pos': pos, 'rotation': rotation, 'size': size,
            'layer': layer
        })

    def add_line(self, start, end, width, layer, net_name=None, net_id=None):
        self._add_item({
            'type': 'line',
            'start': start, 'end': end, 'width': width,
            'layer': layer, 'name': net_name, 'net_id': net_id
        })

    def add_pad(self, shape, pos, size, rotation, layer, net_name=None, net_id=None, drill=0, pad_name=None):
        self._add_item({
            'type': 'pad',
            'shape': shape,
            'pos': pos, 'size': size, 'rotation': rotation,
            'layer': layer, 'name': net_name, 'net_id': net_id, 'drill': drill, 'pad': pad_name
        })

    def add_via(self, x, y, size, drill, net_name=None, net_id=None, z_start=0.0, z_end=-1.6):
        self.add_circle((x, y), size/2, "Vias", filled=True, net_name=net_name, net_id=net_id)

    def add_zone(self, points, layer, net_name=None, net_id=None):
        self._add_item({
            'type': 'zone',
            'points': points,
            'layer': layer, 'name': net_name, 'net_id': net_id
        })
        
    def add_circle(self, center, radius, layer, width=0, filled=False, net_name=None, net_id=None):
         self._add_item({
            'type': 'circle_shape',
            'center': center, 'radius': radius,
            'width': width, 'filled': filled,
            'layer': layer, 'name': net_name, 'net_id': net_id
        })

    def add_arc(self, center, radius, start_angle, end_angle, layer, width=0, net_name=None, net_id=None):
        self._add_item({
            'type': 'arc',
            'center': center, 'radius': radius,
            'start_angle': start_angle, 'end_angle': end_angle,
            'width': width,
            'layer': layer, 'name': net_name, 'net_id': net_id
        })

    def add_filament(self, start, end, width, thickness, color='copper', name=None, layer=None, net_id=None):
        self.add_line(start, end, width, layer or "Default", name, net_id=net_id)
        if start[0] == end[0] and start[1] == end[1] and layer == 'Vias':
             self.add_circle((start[0], start[1]), width/2, layer, filled=True, net_name=name, net_id=net_id)

    def add_board_substrate(self, min_x, max_x, min_y, max_y, thickness=1.6):
        """Draw board outline in 2D"""
        self._add_item({
            'type': 'zone',
            'points': [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)],
            'layer': 'Edge.Cuts', 'name': 'Substrate'
        })

    def clear(self):
        self.filaments.clear()
        self.Refresh()
        
    def zoom_extents(self):
        if not self.filaments: return
        min_x, min_y, max_x, max_y = 1e9, 1e9, -1e9, -1e9
        valid = False
        for f in self.filaments:
            xs, ys = [], []
            if f['type'] == 'line':
                xs = [f['start'][0], f['end'][0]]
                ys = [f['start'][1], f['end'][1]]
            elif f['type'] == 'pad':
                d = max(f['size']) / 2
                xs = [f['pos'][0]-d, f['pos'][0]+d]
                ys = [f['pos'][1]-d, f['pos'][1]+d]
            elif f['type'] == 'zone' and f['points']:
                xs = [p[0] for p in f['points']]
                ys = [p[1] for p in f['points']]
            elif f['type'] == 'circle_shape' or f['type'] == 'arc':
                r = f['radius']
                xs = [f['center'][0]-r, f['center'][0]+r]
                ys = [f['center'][1]-r, f['center'][1]+r]
            
            if xs and ys:
                valid = True
                min_x = min(min_x, min(xs))
                max_x = max(max_x, max(xs))
                min_y = min(min_y, min(ys))
                max_y = max(max_y, max(ys))

        if not valid or min_x > max_x: return

        w_mm = max_x - min_x
        h_mm = max_y - min_y
        cw, ch = self.GetClientSize()
        if w_mm == 0 or h_mm == 0: self.scale = 20.0
        else: self.scale = min(cw / (w_mm * 1.2), ch / (h_mm * 1.2))
            
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        
        # Center in screen
        if self.mirrored:
             # If mirrored (Scale(-1, 1)), X-coord `x` draws at `-x`.
             # We want `-mid_x` to be at `cw/2`. 
             # ScreenX = (WorldX * -Scale) + OffsetX
             # cw/2 = (mid_x * -Scale) + OffsetX
             # OffsetX = cw/2 + mid_x * Scale
             self.offset_x = (cw / 2) + (mid_x * self.scale)
        else:
             self.offset_x = (cw / 2) - (mid_x * self.scale)
             
        self.offset_y = (ch / 2) - (mid_y * self.scale)
        self.Refresh()

    def set_layer_visibility(self, layer, visible):
        self.layers_visible[layer] = visible
        self.Refresh()
        
    def _match_net(self, it, target_id, target_name):
        """Standardized net matching for all viewports"""
        if not target_name: return False
        
        # Priority 1: Match by numeric net_id (must be > 0)
        it_id = it.get('net_id')
        if it_id is not None and target_id is not None:
            if it_id == target_id and target_id > 0: return True
            
        # Priority 2: Match by name (if not a generic placeholder)
        it_name = str(it.get('name') or it.get('net') or "").strip()
        if it_name == target_name:
            if it_name.upper() not in ["", "0", "NET_0", "NONE", "/"]: return True
        return False

    def highlight_net(self, net_name, net_id=None):
        # Highlight a specific net by name or ID. Strictly exclusive.
        self.highlighted_net = str(net_name).strip() if net_name else None
        self.highlighted_net_id = net_id
        self.highlighted_pad = None # Clear pad selection
        self.Refresh()
        # If ID not provided, try to find it in filaments (best effort)
        if self.highlighted_net_id is None and self.highlighted_net:
            for f in self.filaments:
                if f.get('name') == self.highlighted_net:
                    self.highlighted_net_id = f.get('net_id')
                    break
                    
        self.highlighted_pad = None
        print(f"2D: Highlighting net '{self.highlighted_net}' (ID: {self.highlighted_net_id})")
        self.Refresh()
    
    def highlight_pad(self, net_name, pad_name):
        """Highlight a specific pad on a specific net. Strictly exclusive."""
        if not net_name:
            self.highlighted_net = None
        else:
            self.highlighted_net = str(net_name).strip()
            
        self.highlighted_pad = str(pad_name).strip() if pad_name else None
        print(f"2D: Highlighting pad '{self.highlighted_pad}' on net '{self.highlighted_net}'")
        self.Refresh()

    def clear_highlight(self):
        self.highlighted_net = None
        self.highlighted_net_id = None
        self.highlighted_pad = None
        self.Refresh()

    def set_layer_opacity(self, layer, opacity):
        self.layers_opacity[layer] = opacity
        self.Refresh()

    def _get_draw_order(self, item):
        # 0: Zones (Bottom)
        # 1: Tracks
        # 2: Pads
        # 3: Vias
        # 4: Silk / Drawings (Top)
        t = item['type']
        if t == 'zone': return 0
        if t == 'line': return 1
        if t == 'pad': return 2
        if t == 'circle_shape' and item.get('layer') == 'Vias': return 3
        if t == 'circle_shape' or t == 'arc': return 4
        return 1

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        if not gc: return
        
        gc.Translate(self.offset_x, self.offset_y)
        gc.Scale(self.scale, self.scale)
        if self.mirrored:
            gc.Scale(-1, 1)
        
        # 1. Separate items for Two-Pass Rendering (Absolute Clarity)
        bg_items = []
        fg_items = []
        
        for f in self.filaments:
            # Match visibility
            layer = f.get('layer', 'Default')
            if not self.layers_visible.get(layer, True): continue
            
            # Determine if this item is on the highlighted net
            is_highlight = False
            # HIGH-SPEC EXCLUSIVITY: Match primarily by numeric net_id
            if f['type'] in ['line', 'pad', 'zone', 'circle_shape', 'arc']:
                is_highlight = self._match_net(f, self.highlighted_net_id, self.highlighted_net)
                
            if is_highlight:
                fg_items.append(f)
            else:
                bg_items.append(f)
                
        # 2. Sort both lists by original Z-order
        bg_items.sort(key=self._get_draw_order)
        fg_items.sort(key=self._get_draw_order)
        
        # 3. Draw Background (Subtle Dimming)
        # alpha 40/255 keeps the board clearly visible but distinct from highlights
        bg_alpha = 40 if self.highlighted_net else 180
        
        for f in bg_items:
            self._draw_element(gc, f, dimmed=True, custom_alpha=bg_alpha)
            
        # 4. Draw Foreground (Highlighted - Solid high-vis colors)
        for f in fg_items:
            self._draw_element(gc, f, dimmed=False)
            
        # 5. Draw Fusing Risks and Capacitor Hotspots
        mode = getattr(self, 'current_heatmap_mode', 'Raw Geometry')
        if mode != 'Raw Geometry' and hasattr(self, 'electrical_data'):
            if self.layers_visible.get("Fusing Risk", True):
                self._draw_fusing_risks(gc)
            if self.electrical_data.get('cap_hotspots'):
                self._draw_cap_hotspots(gc)

    def _draw_fusing_risks(self, gc):
        risks = self.electrical_data.get('fusing_risks', [])
        if not risks: return
        
        pen = gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(255, 0, 0, 255)).Width(0.5).Style(wx.PENSTYLE_SOLID))
        gc.SetPen(pen)
        
        # We don't want to fill it, just draw a bounding box/outline
        for risk in risks:
            p1, p2 = risk['p1'], risk['p2']
            x1, y1 = p1[0], p1[1]
            x2, y2 = p2[0], p2[1]
            
            # Simple line with thick stroke for now since it's a filament center
            p = gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(255, 0, 0, 200)).Width(1.0).Style(wx.PENSTYLE_SHORT_DASH))
            gc.SetPen(p)
            gc.StrokeLine(x1, y1, x2, y2)
            
            # Draw a warning circle in the center
            cx, cy = (x1+x2)/2, (y1+y2)/2
            gc.SetBrush(wx.Brush(wx.Colour(255, 0, 0, 100)))
            p_circle = gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(255, 0, 0, 255)).Width(0.2))
            gc.SetPen(p_circle)
            gc.DrawEllipse(cx - 0.5, cy - 0.5, 1.0, 1.0)

    def _draw_cap_hotspots(self, gc):
        hotspots = self.electrical_data.get('cap_hotspots', [])
        if not hotspots: return
        
        gc.SetBrush(wx.Brush(wx.Colour(0, 255, 255, 180))) # Cyan
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(0, 200, 200, 255)).Width(0.2)))
        
        for idx, h in enumerate(hotspots):
            cx, cy = h['x'], h['y']
            
            # Draw marker
            gc.DrawEllipse(cx - 1.0, cy - 1.0, 2.0, 2.0)
            
            # Draw label
            lbl = f"Cap{idx+1}: {h['label']}"
            font = wx.Font(wx.FontInfo(3).Family(wx.FONTFAMILY_SWISS))
            gc.SetFont(font, wx.Colour(0, 255, 255, 255))
            
            # Inverted y for text drawing sometimes depends on coordinate system, 
            # but usually it's fine
            gc.DrawText(lbl, cx + 1.2, cy - 1.5)

    def _draw_element(self, gc, f, dimmed=False, custom_alpha=None):
        layer = f.get('layer', 'Default')
        base_col = self.colors.get(layer, self.colors['Default'])
        
        pad_highlight = False
        if not dimmed:
            # Highlight Color (High-Viz Cyan)
            col = self.highlight_col
            pen_mult = 1.5
            
            # Pad highlighting only inside the active net group
            if f['type'] == 'pad' and self.highlighted_pad:
                 if str(f.get('pad')).strip() == self.highlighted_pad:
                      pad_highlight = True
                      col = wx.Colour(255, 50, 50, 255) # Bright Red
                      pen_mult = 3.0
        else:
            # Background
            alpha = custom_alpha if custom_alpha is not None else 180
            col = wx.Colour(base_col.Red(), base_col.Green(), base_col.Blue(), int(alpha))
            pen_mult = 1.0

        ftype = f['type']
        
        if ftype == 'line':
            pen = gc.CreatePen(wx.GraphicsPenInfo(col).Width(f['width'] * pen_mult))
            gc.SetPen(pen)
            gc.StrokeLine(f['start'][0], f['start'][1], f['end'][0], f['end'][1])

        elif ftype == 'text':
             gc.PushState()
             gc.Translate(f['pos'][0], f['pos'][1])
             if f['rotation']: gc.Rotate(math.radians(-f['rotation']))
             font_size = f['size'][0] * 3
             font = wx.Font(wx.FontInfo(font_size).Family(wx.FONTFAMILY_SWISS))
             gc.SetFont(font, col)
             w, h = gc.GetTextExtent(f['text'])
             gc.DrawText(f['text'], -w/2, -h/2)
             gc.PopState()

        elif ftype == 'pad':
             gc.PushState()
             gc.Translate(f['pos'][0], f['pos'][1])
             if f['rotation']: gc.Rotate(math.radians(-f['rotation']))

             gc.SetBrush(gc.CreateBrush(wx.Brush(col)))
             if not dimmed:
                  # White outline for unmistakable highlight
                  gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.WHITE).Width(0.1 if pad_highlight else 0.05)))
             else:
                  gc.SetPen(wx.NullPen)

             w, h = f['size']
             if f['shape'] in ['circle', 'oval']: gc.DrawEllipse(-w/2, -h/2, w, h)
             else: gc.DrawRectangle(-w/2, -h/2, w, h)
             
             if f.get('drill', 0) > 0:
                 gc.SetBrush(wx.BLACK_BRUSH)
                 dr = f['drill']
                 gc.DrawEllipse(-dr/2, -dr/2, dr, dr)
             gc.PopState()

        elif ftype == 'zone':
             points = f['points']
             if not points: return
             path = gc.CreatePath()
             path.MoveToPoint(points[0][0], points[0][1])
             for p in points[1:]: path.AddLineToPoint(p[0], p[1])
             path.CloseSubpath()
             gc.SetBrush(gc.CreateBrush(wx.Brush(col)))
             gc.SetPen(wx.NullPen)
             gc.FillPath(path)
             if not dimmed:
                  # Selection outline for zones
                  pen_w = 2.0 / self.scale if self.scale > 0 else 0.5
                  gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.WHITE).Width(pen_w)))
                  gc.StrokePath(path)

        elif ftype == 'circle_shape':
             r = f['radius']
             if f['filled']:
                 gc.SetBrush(gc.CreateBrush(wx.Brush(col)))
                 gc.SetPen(wx.NullPen)
                 gc.DrawEllipse(f['center'][0]-r, f['center'][1]-r, 2*r, 2*r)
             else:
                 pen = gc.CreatePen(wx.GraphicsPenInfo(col).Width(f['width'] * pen_mult))
                 gc.SetPen(pen)
                 gc.DrawEllipse(f['center'][0]-r, f['center'][1]-r, 2*r, 2*r)

        elif ftype == 'arc':
             path = gc.CreatePath()
             path.AddArc(f['center'][0], f['center'][1], f['radius'], 
                         math.radians(f['start_angle']), math.radians(f['end_angle']), True)
             pen = gc.CreatePen(wx.GraphicsPenInfo(col).Width(f['width'] * pen_mult))
             gc.SetPen(pen)
             gc.StrokePath(path)

    def on_zoom(self, event):
        x, y = event.GetPosition()
        old_scale = self.scale
        zoom_factor = 1.2 if event.GetWheelRotation() > 0 else 0.8
        self.scale = max(0.1, min(old_scale * zoom_factor, 1000.0))
        
        world_x = (x - self.offset_x) / old_scale
        world_y = (y - self.offset_y) / old_scale
        self.offset_x = x - (world_x * self.scale)
        self.offset_y = y - (world_y * self.scale)
        self.Refresh()

    def _get_world_coords(self, sx, sy):
        wx = (sx - self.offset_x) / self.scale
        wy = (sy - self.offset_y) / self.scale
        if self.mirrored:
            wx = -wx
        return wx, wy

    def _point_in_polygon(self, x, y, poly):
        # Ray casting algorithm
        n = len(poly)
        if n < 3: return False
        inside = False
        p1x, p1y = poly[0]
        for i in range(n + 1):
            p2x, p2y = poly[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def _hit_test(self, wx, wy):
        item = self._hit_test_item(wx, wy)
        return item.get('name') if item else None

    def _hit_test_item(self, wx, wy):
        # Iterate in reverse draw order (top items first)
        # Search radius in World Units (mm)
        search_r = 5.0 / self.scale # 5 screen pixels radius
        
        candidates = []
        
        for f in reversed(self.filaments):
            layer = f.get('layer', 'Default')
            if not self.layers_visible.get(layer, True): continue
            
            ftype = f['type']
            dist = float('inf')
            
            if ftype == 'line':
                # Point to segment distance
                px, py = f['start'][:2]
                ex, ey = f['end'][:2]
                l2 = (ex-px)**2 + (ey-py)**2
                if l2 == 0: dist = math.hypot(wx-px, wy-py)
                else:
                    t = ((wx-px)*(ex-px) + (wy-py)*(ey-py)) / l2
                    t = max(0, min(1, t))
                    proj_x = px + t*(ex-px)
                    proj_y = py + t*(ey-py)
                    dist = math.hypot(wx-proj_x, wy-proj_y)
                    
            elif ftype == 'pad':
                 # Box check
                 cx, cy = f['pos'][:2]
                 w, h = f['size']
                 dist = math.hypot(wx-cx, wy-cy)
                 if dist < max(w, h)/2: dist = 0

            elif ftype == 'zone':
                 if self._point_in_polygon(wx, wy, f['points']):
                     # Make zone hit 'weak' (just inside search_r)
                     dist = search_r * 0.99
            
            elif ftype == 'circle_shape' or ftype == 'text':
                 pos = f.get('center', f.get('pos', (0,0)))
                 cx, cy = pos[:2]
                 dist = math.hypot(wx-cx, wy-cy)
                 
            if dist < search_r:
                candidates.append((dist, f))
                
        if candidates:
            # Sort by distance, then by Z-order descending (Top items first)
            candidates.sort(key=lambda x: (x[0], -self._get_draw_order(x[1])))
            return candidates[0][1] # Return the whole dict
        return None

    def on_mouse_down(self, event):
        self.is_dragging = False
        self.drag_start = event.GetPosition()
        self.last_mouse = event.GetPosition()
        if not self.HasCapture(): self.CaptureMouse()

    def on_mouse_up(self, event):
        if self.HasCapture(): self.ReleaseMouse()
        
        pos = event.GetPosition()
        dx = abs(pos[0] - self.drag_start[0])
        dy = abs(pos[1] - self.drag_start[1])
        
        if dx < 5 and dy < 5:
            # Click
            wx_coord, wy_coord = self._get_world_coords(pos[0], pos[1])
            hit_item = self._hit_test_item(wx_coord, wy_coord)
            
            if hit_item:
                net = hit_item.get('name')
                pad = hit_item.get('pad') if hit_item['type'] == 'pad' else None
                net_id = hit_item.get('net_id')
                
                print(f"DEBUG: Click -> Net: {net} (ID: {net_id}), Pad: {pad}")
                
                self.highlight_net(net, net_id=net_id)
                if pad: self.highlight_pad(net, pad)
                
                if pad and self.on_pad_click_cb:
                    self.on_pad_click_cb(net, pad)
                elif net and self.on_net_click_cb:
                    self.on_net_click_cb(net, best_id=net_id)
            else:
                self.clear_highlight()
                if self.on_net_click_cb:
                    self.on_net_click_cb(None)
                
        self.is_dragging = False

    def on_capture_lost(self, event):
        self.is_dragging = False

    def on_mouse_move(self, event):
        if event.Dragging() and event.LeftIsDown():
            self.is_dragging = True
            x, y = event.GetPosition()
            dx = x - self.last_mouse[0]
            dy = y - self.last_mouse[1]
            self.offset_x += dx
            self.offset_y += dy
            self.last_mouse = (x, y)
            self.Refresh()
            
    def on_size(self, event):
        self.Refresh()
        event.Skip()

    def set_electrical_data(self, data):
        """Store electrical data for heatmaps"""
        self.electrical_data = data
        self.units = getattr(self, 'units', 'A/mm²')
        
    def set_units(self, unit_str):
        self.units = unit_str
        self.Refresh()

    def update_heatmap_mode(self, mode):
        """Switch between Raw, Voltage, Voltage Drop, Current Density"""
        self.current_heatmap_mode = mode
        self.Refresh()
