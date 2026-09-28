# SPIKE: Legacy Program State Tracker (Historical Only)

> **Retired authority:** This May 2026 wxPython/PyVista tracker is preserved for
> history and is not the current product state. The authoritative trackers are
> `codex_migration/USER_REQUEST_TRACKER.md`,
> `docs/WAVE_0_CAPABILITY_MATRIX.md`, and the machine-readable native
> capability ledger. Do not use this file to make release or solver-validity
> claims.

**Last Updated:** May 2026
**Project Type:** High-Performance Signal/Power Integrity & Thermal Simulation Suite (Originally a KiCad Plugin, transitioning to Enterprise SaaS)
**Tech Stack (Current):** Python 3.11, wxPython (AGW AUI / Ribbon), PyVista (VTK 3D), SciPy/NumPy (Solvers), KiCad `pcbnew` Python API.

---

## 1. System Architecture Overview

SPIKE (Signal & Power Integrity KiCad Environment) is a professional-grade simulation suite designed to rival tools like HyperLynx and FloTHERM.

### Key Modules
- **`demo_spike.py`:** The main entry point and UI orchestrator. Uses advanced `wx.lib.agw.aui` for dockable, professional engineering workspaces (Left: Nets, Center: Viewport/Reports, Right: Analysis/Thermal Panels, Bottom: Console).
- **`python/viz/viewport3d.py`:** The core 3D WebGL/PyVista rendering engine. Handles raw geometry visualization, thermal heatmaps, interactive probing (mesh picking), and transient video rendering.
- **`python/core/odb_parser.py` & `ipc_parser.py`:** Manufacturing data ingestion pipelines. Bypasses KiCad's limitations by directly parsing ODB++ and IPC-2581 into a unified simulation-agnostic internal dictionary format.
- **`python/core/thermal_mesher.py`:** Converts vector board geometry into a 2.5D voxelized sparse conductance matrix ($\mathbf{G}_{th}$). Calculates $k_{eff}$ based on copper homogenization.
- **`python/core/thermal_solver.py`:** The heavy-lifting sparse matrix solver. Handles Steady-State ($\mathbf{G}\mathbf{T}=\mathbf{P}$) and Transient (Implicit Euler) modes, including Virtual Heatsink attachment.
- **`python/core/electro_thermal.py`:** The "Killer Feature" orchestrator. Iteratively couples the PI (IR-Drop) solver and the Thermal solver, updating copper resistivity $\rho(T)$ until thermal equilibrium is reached.

---

## 2. Execution History: Completed Phases

### Phases 1-5: Foundation & UI Modernization
- **UI Overhaul:** Stripped legacy Tkinter/basic-wx themes. Implemented a dark-mode, dockable AGW AUI interface with a Microsoft Ribbon-style toolbar for premium B2B aesthetics.
- **BoM / Part Management:** Integrated robust BoM parsing (`bom_manager.py`) with cross-vendor part validation.
- **Electrical Foundation:** Scaffolded the Power Integrity (PI) solvers (`peec_mesher.py`) and Signal Integrity (SI) workspaces. Built the `PDNHealthDialog` and Interactive Reporting engine.

### Phase 6: Thermal Engine & Manufacturing Pipelines
- **Data Ingestion:** Replaced basic KiCad PCB API calls with robust ODB++ and IPC-2581 native parsers to ensure manufacturing-grade trace/polygon accuracy.
- **Rasterization:** Implemented `ThermalMesher` for highly optimized 2.5D copper/FR4 voxelization.

### Phase 7: Advanced Thermal Solver & UI
- **Thermal UI:** Added `ThermalSidePanel` to the main window. Included `ComponentWizard` (assigns $P$, $T_j$, $\theta_{JC}$, and Transient CSV profiles) and `HeatsinkManagerWizard`.
- **Solver Engine:** Completed `thermal_solver.py` integrating `scipy.sparse.linalg.spsolve` for massive node grids.
- **Integration:** Wired the solver output to `Viewport3D` via `add_thermal_heatmap`.

### Phase 8: Interactive Analytics & Commercial Features
- **Electro-Thermal Co-Sim:** Created `electro_thermal.py` to loop $I^2R$ power outputs back into the thermal grid.
- **Interactive Probing:** Implemented `on_thermal_click` in `Viewport3D`—clicking the board extracts the temperature scalar and logs it in the Analysis Dashboard probe table.
- **Transient Video:** Implemented `render_thermal_video()` using PyVista's `open_movie` to save time-dependent thermal propagation to MP4, bypassing heavy RAM caching limitations.
- **View Toggles:** Added "Pure Thermal View" to isolate the scalar grid from the board geometry.

---

## 3. Current State & Immediate Focus (Real-Time)

The application is currently stable locally as a desktop Python application. The UI layout is locked, the thermal simulation pipeline works end-to-end, and the architecture is primed for the next major commercial features.

**Immediate Work to Execute (Phase 9):**
1. **MTBF / Reliability Engine:** Implement Arrhenius equation calculations inside `thermal_solver.py` to output projected IC lifespan based on simulated $T_j$.
2. **Auto-Heatsink Advisor:** Add algorithmic logic to suggest required $R_{th,ja}$ values to keep components below $T_{max}$.
3. **HTML Report Generation:** Embed thermal heatmap screenshots, $T_j(t)$ plots, and pass/fail metrics into the automated HTML dossier.

---

## 4. Long-Term Roadmap: SaaS Cloud Migration

Per the generated `CLOUD_MIGRATION_PLAN.md` and `SAAS_TRANSITION_PLAN.md`:

- **Architecture Shift:** The Python C++ PEEC/Thermal solvers (`python/core/*`) will be extracted into a **Dockerized FastAPI backend** running on AWS/GCP (Celery + Redis queue).
- **Frontend Shift:** The `wxPython` interface will be deprecated in favor of a **React/Next.js** browser application. The `Viewport3D` (PyVista) will be replaced with **VTK.js** or Three.js.
- **Desktop Client:** The existing codebase will pivot into a "thin client plugin" inside KiCad that merely extracts the `.kicad_pcb` data, POSTs it to the Cloud API, and renders the returned results locally for engineers who refuse to leave the CAD environment.
- **Business Model:** Usage-based compute API + Tiered enterprise subscriptions (Team workspaces, RBAC, ISO audit logging).

## Notes for Future AI Agents / Developers
- **File Modifying Rule:** When modifying `demo_spike.py` or `viewport3d.py`, be highly cautious of wxPython event loop bindings (`wx.CallAfter`) and thread safety, as PyVista/VTK rendering can crash the main loop if accessed from solver daemon threads.
- **UI Aesthetics:** The user strictly mandates *modern, premium, glassmorphic, enterprise-grade* aesthetics. Do not use generic Tkinter or default Windows 98 button styles.
- **Verbosity:** Keep outputs and tool execution completely silent. Output only final results or critical blockers. DO NOT output status phrases or internal narration.
