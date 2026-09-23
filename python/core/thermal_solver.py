import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import time

class ThermalSolver:
    """
    Phase 7: Advanced Thermal Solver Engine
    Handles both Steady-State and Transient thermal simulations.
    """
    def __init__(self, mesher):
        self.mesher = mesher
        self.G_th = None
        self.C_th = None
        self.nodes_count = mesher.nx * mesher.ny * mesher.nz
        
        # Default physical constants
        self.rho_cu = 8960.0 # kg/m^3
        self.cp_cu = 385.0   # J/(kg*K)
        self.rho_fr4 = 1850.0
        self.cp_fr4 = 950.0
        
        # Convection boundaries
        self.h_top = 10.0 # W/(m^2*K) (Free convection)
        self.h_bot = 10.0
        self.T_ambient = 25.0
        
        # Dynamic inputs
        self.power_injections = {} # node_id -> Watts
        self.heatsinks = {}        # node_id -> {'R_th': 5.0, 'T_amb': 25.0}

    def prepare_matrices(self):
        """Construct G_th and optionally C_th."""
        print("[ThermalSolver] Constructing base conductance matrix...")
        G_base = self.mesher.build_thermal_conductance_matrix()
        
        # 1. Add Convection Boundaries to Top and Bottom Layers
        # G_conv = h * A
        A_cell = (self.mesher.dx * 1e-3) * (self.mesher.dy * 1e-3)
        g_conv_top = self.h_top * A_cell
        g_conv_bot = self.h_bot * A_cell
        
        diags = np.zeros(self.nodes_count)
        
        # Top layer nodes (z=0)
        top_slice = slice(0, self.mesher.ny * self.mesher.nx)
        diags[top_slice] += g_conv_top
        
        # Bottom layer nodes (z=nz-1)
        bot_offset = (self.mesher.nz - 1) * (self.mesher.ny * self.mesher.nx)
        bot_slice = slice(bot_offset, bot_offset + (self.mesher.ny * self.mesher.nx))
        diags[bot_slice] += g_conv_bot
        
        # 2. Add Virtual Heatsinks
        for node, hs in self.heatsinks.items():
            if 0 <= node < self.nodes_count:
                g_hs = 1.0 / hs['R_th']
                diags[node] += g_hs
                
        # Modify G matrix diagonally
        G_bound = sp.diags(diags)
        self.G_th = G_base + G_bound
        
        # 3. Build RHS Vector (Power + Ambient Convection loads)
        self.P_vector = np.zeros(self.nodes_count)
        
        # Ambient Convection Load (P = G * T_amb)
        self.P_vector[top_slice] += g_conv_top * self.T_ambient
        self.P_vector[bot_slice] += g_conv_bot * self.T_ambient
        
        # Heatsink Ambient Loads
        for node, hs in self.heatsinks.items():
            if 0 <= node < self.nodes_count:
                self.P_vector[node] += (1.0 / hs['R_th']) * hs.get('T_amb', self.T_ambient)

    def inject_power(self, node_id, watts):
        """Inject steady-state power into a specific node."""
        if 0 <= node_id < self.nodes_count:
            self.power_injections[node_id] = watts

    def solve_steady_state(self):
        """Solve G*T = P"""
        if self.G_th is None:
            self.prepare_matrices()
            
        P_total = self.P_vector.copy()
        for node, w in self.power_injections.items():
            P_total[node] += w
            
        print("[ThermalSolver] Solving Steady-State System...")
        t0 = time.time()
        # Direct solve
        T = spla.spsolve(self.G_th.tocsc(), P_total)
        print(f"[ThermalSolver] Solved in {time.time()-t0:.3f}s")
        
        # Reshape to 3D Grid (Z, Y, X)
        T_grid = T.reshape((self.mesher.nz, self.mesher.ny, self.mesher.nx))
        return T_grid

    def _build_capacitance_matrix(self):
        """Build the diagonal thermal capacitance matrix for transient."""
        V_cell = (self.mesher.dx * 1e-3) * (self.mesher.dy * 1e-3) * (0.035e-3) # simplified Cu thickness vol
        
        # C_th = Volume * rho * Cp
        # Mix based on copper density
        C_eff = self.mesher.cu_density * (self.rho_cu * self.cp_cu) + (1.0 - self.mesher.cu_density) * (self.rho_fr4 * self.cp_fr4)
        C_eff = C_eff * V_cell
        
        self.C_th = sp.diags(C_eff.flatten())

    def solve_transient(self, t_end, dt, power_profiles):
        """
        Solve transient using Implicit Euler:
        (C/dt + G) * T_{n+1} = (C/dt) * T_n + P_{n+1}
        """
        if self.G_th is None:
            self.prepare_matrices()
        if self.C_th is None:
            self._build_capacitance_matrix()
            
        num_steps = int(t_end / dt)
        
        # Initial condition (Start at ambient)
        T_current = np.full(self.nodes_count, self.T_ambient)
        
        # LHS Matrix: A = (C / dt) + G
        C_dt = self.C_th / dt
        A = (C_dt + self.G_th).tocsc()
        
        # Factorize once for fast solving
        solver = spla.factorized(A)
        
        results = [T_current.copy()]
        
        print(f"[ThermalSolver] Running Transient: {num_steps} steps...")
        
        for step in range(1, num_steps + 1):
            t = step * dt
            
            # P vector for current time step
            P_step = self.P_vector.copy()
            for node, prof in power_profiles.items():
                # Simple interpolation or lookup for prof(t)
                P_step[node] += self._eval_profile(prof, t)
                
            # RHS: b = (C / dt) * T_n + P_{n+1}
            b = C_dt.dot(T_current) + P_step
            
            # Solve T_{n+1}
            T_current = solver(b)
            results.append(T_current.copy())
            
        return np.array(results)

    def _eval_profile(self, profile, t):
        """Evaluate a time-varying power profile (list of [time, power] pairs)"""
        if not profile: return 0.0
        # If single value
        if isinstance(profile, (int, float)): return float(profile)
        
        # Linear interpolation
        times = [p[0] for p in profile]
        powers = [p[1] for p in profile]
        return np.interp(t, times, powers)
