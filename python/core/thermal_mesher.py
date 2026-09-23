import numpy as np
import scipy.sparse as sp
import math

class ThermalMesher:
    """
    Phase 6: Thermal Homogenization Meshing
    Converts 3D PCB geometry into a 2.5D voxelized thermal resistance grid.
    """
    
    def __init__(self, parser, dx=1.0, dy=1.0):
        self.parser = parser
        self.dx = dx
        self.dy = dy
        
        # Thermal Conductivities (W/m·K)
        self.K_COPPER = 385.0
        self.K_FR4 = 0.25
        
        self._build_grid()

    def _build_grid(self):
        """Discretize the board bounding box."""
        if not hasattr(self.parser, 'board_bbox'):
            # Fallback if bbox not found
            self.xmin, self.ymin = 0.0, 0.0
            self.xmax, self.ymax = 100.0, 100.0
        else:
            bb = self.parser.board_bbox
            self.xmin, self.xmax = bb['min_x'], bb['max_x']
            self.ymin, self.ymax = bb['min_y'], bb['max_y']
            
        # Add a small padding
        pad = 2.0
        self.xmin -= pad; self.xmax += pad
        self.ymin -= pad; self.ymax += pad
        
        self.nx = int(math.ceil((self.xmax - self.xmin) / self.dx))
        self.ny = int(math.ceil((self.ymax - self.ymin) / self.dy))
        
        self.layers = self._extract_layer_order()
        self.nz = len(self.layers)
        
        # Density grids: (nz, ny, nx) mapping 0.0 to 1.0 (copper fraction)
        self.cu_density = np.zeros((self.nz, self.ny, self.nx), dtype=np.float32)
        
    def _extract_layer_order(self):
        """Extract ordered copper layers."""
        layers = []
        layer_table = getattr(self.parser, 'layers', {})
        for _layer_id, item in layer_table.items():
            name = str(item.get('name', '')).strip('"')
            layer_type = str(item.get('type', '')).lower()
            if name.endswith('.Cu') or layer_type in {'signal', 'power', 'mixed', 'jumper'}:
                layers.append(name)
        for item in getattr(self.parser, 'stackup', []):
            name = str(item.get('name', '')).strip('"')
            if (name.endswith('.Cu') or str(item.get('type', '')).lower() == 'copper') and name not in layers:
                layers.append(name)
        return layers or ["F.Cu", "B.Cu"]
        
    def _get_layer_idx(self, layer_name):
        try:
            return self.layers.index(layer_name)
        except ValueError:
            return -1

    def rasterize_geometry(self, progress_cb=None):
        """
        Convert vectors (tracks/vias/pads/zones) into a rasterized copper density map.
        Uses point sampling against shapes for simplicity.
        """
        # Create meshgrid of cell centers
        x_centers = np.linspace(self.xmin + self.dx/2, self.xmax - self.dx/2, self.nx)
        y_centers = np.linspace(self.ymin + self.dy/2, self.ymax - self.dy/2, self.ny)
        X, Y = np.meshgrid(x_centers, y_centers)
        
        total_items = len(self.parser.tracks) + len(self.parser.pads) + len(self.parser.vias) + len(self.parser.zones)
        processed = 0
        
        # 1. Rasterize Tracks
        for track in self.parser.tracks:
            z_idx = self._get_layer_idx(track['layer'])
            if z_idx == -1: continue
            
            x1, y1 = track['start']
            x2, y2 = track['end']
            w2 = (track['width'] / 2.0)**2
            
            # Line segment distance squared
            l2 = (x2-x1)**2 + (y2-y1)**2
            if l2 == 0:
                dist2 = (X-x1)**2 + (Y-y1)**2
            else:
                t = np.clip(((X - x1)*(x2 - x1) + (Y - y1)*(y2 - y1)) / l2, 0, 1)
                px = x1 + t * (x2 - x1)
                py = y1 + t * (y2 - y1)
                dist2 = (X - px)**2 + (Y - py)**2
                
            self.cu_density[z_idx][dist2 <= w2] = 1.0
            
            processed += 1
            if progress_cb and processed % 100 == 0:
                progress_cb(int(processed/total_items * 100))

        # 2. Rasterize Vias (Plated through hole, assumed to impact all layers)
        for via in self.parser.vias:
            vx, vy = via['at']
            r2 = (via['size'] / 2.0)**2
            dist2 = (X - vx)**2 + (Y - vy)**2
            mask = dist2 <= r2
            for z in range(self.nz):
                self.cu_density[z][mask] = 1.0
                
            processed += 1
            if progress_cb and processed % 50 == 0:
                progress_cb(int(processed/total_items * 100))

        # 3. Rasterize Pads
        for pad in self.parser.pads:
            z_idx = self._get_layer_idx(pad['layer'])
            if z_idx == -1: continue
            
            px, py = pad['at']
            sx, sy = pad['size']
            # Simplified to AABB for rasterization (ignoring rotation for speed)
            mask_x = np.abs(X - px) <= sx/2.0
            mask_y = np.abs(Y - py) <= sy/2.0
            self.cu_density[z_idx][mask_x & mask_y] = 1.0
            
            processed += 1
            if progress_cb and processed % 50 == 0:
                progress_cb(int(processed/total_items * 100))

        # 4. Rasterize Zones (Polygons)
        # We'll use matplotlib.path.Path for fast point-in-polygon testing
        try:
            from matplotlib.path import Path
            points = np.column_stack((X.flatten(), Y.flatten()))
            
            for zone in self.parser.zones:
                z_idx = self._get_layer_idx(zone['layer'])
                if z_idx == -1: continue
                
                path = Path(zone['points'])
                mask = path.contains_points(points).reshape(self.ny, self.nx)
                self.cu_density[z_idx][mask] = 1.0
                
                processed += 1
                if progress_cb: progress_cb(int(processed/total_items * 100))
        except ImportError:
            print("matplotlib required for Zone rasterization")
            
        # Optional: Apply Gaussian Blur to Homogenize (Spread the copper)
        # import scipy.ndimage as nd
        # for z in range(self.nz):
        #     self.cu_density[z] = nd.gaussian_filter(self.cu_density[z], sigma=1.0)
        #     self.cu_density[z] = np.clip(self.cu_density[z], 0.0, 1.0)

    def build_thermal_conductance_matrix(self):
        """
        Constructs the sparse thermal conductance matrix [G]
        based on the cu_density grid.
        Returns: G_matrix, NodeList
        """
        total_nodes = self.nx * self.ny * self.nz
        
        # Effective conductivity k_eff = (Cu_Density * K_COPPER) + ((1-Cu_Density) * K_FR4)
        k_eff = (self.cu_density * self.K_COPPER) + ((1.0 - self.cu_density) * self.K_FR4)
        
        # We will use simple 1D resistances between adjacent cell centers.
        # R = L / (k * A). G = 1/R
        # For X-dir: L = dx, A = dy * thickness
        # Assuming 0.035mm (35um) copper thickness per layer
        th_cu = 0.035e-3
        dx_m = self.dx * 1e-3
        dy_m = self.dy * 1e-3
        
        G_x = (k_eff * dy_m * th_cu) / dx_m
        G_y = (k_eff * dx_m * th_cu) / dy_m
        
        # Z-axis Resistance (Dielectric core)
        # Assuming FR4 core is ~1.5mm thick, shared between layers
        dz_m = 1.5e-3 / max(1, (self.nz - 1))
        # Z-conductivity is mostly FR4, unless cu_density is 1.0 on both adjacent layers
        # (Assuming thermal via presence if density is high, but we'll stick to a base K_FR4 for now)
        G_z = (self.K_FR4 * dx_m * dy_m) / dz_m
        
        def to_idx(z, y, x):
            return z * (self.ny * self.nx) + y * self.nx + x
            
        rows = []
        cols = []
        data = []
        
        def add_edge(n1, n2, g):
            rows.extend([n1, n1, n2, n2])
            cols.extend([n1, n2, n1, n2])
            data.extend([g, -g, -g, g])

        # Build connections
        for z in range(self.nz):
            for y in range(self.ny):
                for x in range(self.nx):
                    n = to_idx(z, y, x)
                    
                    # Connect +X
                    if x < self.nx - 1:
                        g = (G_x[z, y, x] + G_x[z, y, x+1]) / 2.0
                        add_edge(n, to_idx(z, y, x+1), g)
                        
                    # Connect +Y
                    if y < self.ny - 1:
                        g = (G_y[z, y, x] + G_y[z, y+1, x]) / 2.0
                        add_edge(n, to_idx(z, y+1, x), g)
                        
                    # Connect +Z (Inter-layer)
                    if z < self.nz - 1:
                        # Enhance G_z if there's high copper overlap (simulating vias)
                        overlap = self.cu_density[z,y,x] * self.cu_density[z+1,y,x]
                        gz_eff = G_z + (overlap * (self.K_COPPER * dx_m * dy_m) / dz_m) * 0.1 # 10% effective via area
                        add_edge(n, to_idx(z+1, y, x), gz_eff)
                        
        # Assemble Sparse Matrix
        G_matrix = sp.coo_matrix((data, (rows, cols)), shape=(total_nodes, total_nodes)).tocsr()
        
        return G_matrix
