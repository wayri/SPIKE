import math

class PEECMesher:
    """
    Discretizes KiCad geometry (Zones) into PEEC-compatible Filaments
    using a Cartesian grid approach.
    """
    def __init__(self, grid_mm=0.5):
        self.grid_mm = grid_mm

    def _point_in_polygon(self, x, y, poly):
        """Ray-Casting point in polygon algorithm"""
        n = len(poly)
        if n < 3:
            return False
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

    def mesh_zone(self, zone, z_height, thickness, conductivity=5.8e7):
        """
        Takes a zone dict with 'points' and returns a list of dictionaries 
        representing the generated filaments.
        Returns: [{'start': (x,y,z), 'end': (x,y,z), 'width': w, 'thickness': t, 'cond': c}, ...]
        """
        points = zone.get('points', [])
        if not points or len(points) < 3:
            return []

        # Find bounding box
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Expand bounding box slightly to catch edges
        min_x -= self.grid_mm
        max_x += self.grid_mm
        min_y -= self.grid_mm
        max_y += self.grid_mm

        filaments = []
        
        # Create a grid of nodes
        cols = int(math.ceil((max_x - min_x) / self.grid_mm)) + 1
        rows = int(math.ceil((max_y - min_y) / self.grid_mm)) + 1

        node_inside = [[False for _ in range(rows)] for _ in range(cols)]

        # Determine which nodes are inside the polygon
        for c in range(cols):
            x = min_x + c * self.grid_mm
            for r in range(rows):
                y = min_y + r * self.grid_mm
                if self._point_in_polygon(x, y, points):
                    node_inside[c][r] = True

        # Generate Horizontal X-directed Filaments
        for c in range(cols - 1):
            x1 = min_x + c * self.grid_mm
            x2 = min_x + (c + 1) * self.grid_mm
            for r in range(rows):
                y = min_y + r * self.grid_mm
                if node_inside[c][r] and node_inside[c+1][r]:
                    filaments.append({
                        'start': (x1, y, z_height),
                        'end': (x2, y, z_height),
                        'width': self.grid_mm,
                        'thickness': thickness,
                        'conductivity': conductivity
                    })

        # Generate Vertical Y-directed Filaments
        for c in range(cols):
            x = min_x + c * self.grid_mm
            for r in range(rows - 1):
                y1 = min_y + r * self.grid_mm
                y2 = min_y + (r + 1) * self.grid_mm
                if node_inside[c][r] and node_inside[c][r+1]:
                    filaments.append({
                        'start': (x, y1, z_height),
                        'end': (x, y2, z_height),
                        'width': self.grid_mm,
                        'thickness': thickness,
                        'conductivity': conductivity
                    })

        return filaments
