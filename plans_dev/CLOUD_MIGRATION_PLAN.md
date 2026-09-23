# SPIKE Cloud Migration Architecture

> **This document is CONFIDENTIAL — not for open-source distribution.**
> It describes the full cloud migration path from the current desktop/KiCad-plugin implementation to a commercial SaaS platform.

---

## The Core Problem

The current stack is **monolithic and desktop-bound**:
- **UI:** wxPython (desktop only, Windows-focused)
- **Solvers:** Python/scipy/numpy (CPU-bound, single machine)
- **Data:** Local `.kicad_pcb`, ODB++, IPC-2581 files

The target state is a **cloud-native, multi-tenant SaaS** where:
- **UI:** Browser-based, works on any OS
- **Solvers:** Run on scalable cloud compute
- **Data:** Stored securely per-workspace in the cloud

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SPIKE CLOUD                             │
│                                                             │
│  ┌─────────────┐     ┌──────────────────────────────────┐  │
│  │  WEB FRONT  │     │         BACKEND SERVICES          │  │
│  │  (Browser)  │────▶│                                  │  │
│  │             │     │  ┌─────────┐   ┌──────────────┐  │  │
│  │  React/     │     │  │ FastAPI │   │ Solver Queue │  │  │
│  │  Next.js    │◀────│  │ Gateway │──▶│  (Celery/    │  │  │
│  │             │     │  │         │   │   Redis)     │  │  │
│  │  VTK.js /   │     │  └─────────┘   └──────┬───────┘  │  │
│  │  Three.js   │     │                        │           │  │
│  │  (3D render)│     │              ┌─────────▼─────────┐ │  │
│  └─────────────┘     │              │  Python Solver     │ │  │
│                       │              │  Workers (Docker)  │ │  │
│  ┌─────────────┐     │              │                   │ │  │
│  │  DESKTOP    │     │              │  thermal_solver   │ │  │
│  │  CLIENT     │────▶│              │  peec_mesher      │ │  │
│  │  (thin app, │     │              │  electro_thermal  │ │  │
│  │  KiCad     │     │              │  si_engine        │ │  │
│  │  plugin)   │     │              └───────────────────┘ │  │
│  └─────────────┘     └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: API-ify the Solvers (Now → 6 months)

**Goal:** Keep the wxPython UI, but move heavy compute to a cloud API.

This is the lowest-risk first step. The UI does not change yet.

### What to build
1. **FastAPI Gateway** (`solver_api.py`)
   - `POST /solve/thermal` — accepts mesher parameters + component data, returns `T_grid`
   - `POST /solve/pi` — accepts netlist + current sources, returns `V_vector, J_vector`
   - `POST /solve/electro_thermal` — orchestrates both iteratively
   - `GET /job/{id}/status` — polling endpoint for async jobs
   - `GET /job/{id}/results` — fetch compressed result arrays

2. **Celery Task Queue** for async solver execution
   - Each solve is a queued task with a job ID returned immediately to the client
   - The desktop wxPython client polls `GET /job/{id}/status` and shows a progress bar

3. **Docker Containers**
   - Package `python/core/` (thermal_solver, thermal_mesher, electro_thermal, peec_mesher) into a Docker image
   - Deploy to AWS Fargate / Google Cloud Run (scale-to-zero, pay per compute second)

### What the desktop client sends
```json
{
  "board_data": { "tracks": [...], "zones": [...], "components": [...] },
  "thermal_params": { "ambient_C": 25.0, "parts": { "U1": { "power_W": 2.5 } } },
  "mesh_resolution_mm": 0.5,
  "license_token": "JWT..."
}
```

### Tech Stack
- **Backend:** Python 3.11, FastAPI, Celery, Redis, NumPy, SciPy
- **Deploy:** Docker → AWS ECS / Fargate or GCP Cloud Run
- **Auth:** JWT tokens, license tier embedded in payload

---

## Phase 2: Web Frontend (6–18 months)

**Goal:** Replace wxPython with a browser-based UI. Desktop app becomes optional.

### Frontend Technology Recommendation

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **React + Next.js** | Massive ecosystem, SSR, easy hire | Verbose boilerplate | ✅ **Recommended** |
| **Vue + Nuxt** | Simpler syntax, good for dashboards | Smaller ecosystem | ✅ Good alternative |
| **Svelte/SvelteKit** | Tiny bundle, very fast | Less mature ecosystem | 🟡 Consider for v2 |
| **Electron (keep Python UI)** | Minimal rewrite | Not web-native, large bundle | ❌ Avoid for SaaS |

**Recommendation: React + Next.js + TypeScript**
- Best long-term hire-ability
- Next.js supports SSR for login/billing pages and SPA for the simulation workspace
- Strong TypeScript ecosystem for complex state management

### Key UI Components to Build
1. **Board Geometry Viewer** — `VTK.js` or `Three.js` WebGL renderer to replace `Viewport3D`
   - VTK.js is the direct web equivalent of PyVista, with identical API concepts
   - Supports point picking, heatmap scalar coloring, and structured grids
2. **Simulation Control Panel** — React sidebar replacing `AnalysisPanel`
3. **Report Viewer** — Reuse the existing HTML Report template, render inline
4. **File Upload** — Drag-and-drop `.kicad_pcb`, ODB++ zip, IPC-2581 XML

### State Management
- **Zustand** or **Redux Toolkit** for simulation state
- Board geometry → stored in browser memory / IndexedDB for fast re-render
- Results (T_grid, V_vector) → fetched lazily from the API per analysis type

---

## Phase 3: Hybrid Mode (Desktop + Cloud)

For users who need KiCad integration (the plugin use case), maintain a **thin Python desktop client** that:
1. Extracts board geometry from KiCad's Python API directly
2. Uploads it to the cloud API
3. Renders results back inside KiCad's own PCB canvas (using KiCad's `pcbnew` drawing APIs)

This is actually **easier than the full web UI** and targets the hardcore EE market who lives in KiCad.

---

## Data Flow Summary

```
Desktop/KiCad Plugin             Cloud Backend              Web UI
─────────────────────            ─────────────              ──────
Parse .kicad_pcb/ODB++  ──────▶  FastAPI receives  ──────▶  Job ID returned
Extract geometry dict             Validates license          Poll GET /job/status
POST /solve/thermal               Queue Celery task          Show progress bar
                                  Solver container runs       
                                  T_grid computed             
                                  Result stored (S3/GCS)     
                                  Job status = DONE           
                            ◀─────────────────────────────  GET /job/results
                                                             Render heatmap (VTK.js)
```

---

## IP Protection in Cloud Architecture

| Layer | Protection Method |
|---|---|
| Solver Core (`thermal_solver`, `peec_mesher`) | Runs server-side only, never sent to client |
| Licensing | JWT signed server-side with tier embedded |
| Board data | Encrypted at rest (AES-256), per-tenant isolation |
| Results | Signed URLs (S3 presigned), expire after 1 hour |
| Open-source client | Parser + basic mesh only, no solver logic |

---

## Recommended Migration Sequence

```
[TODAY]  Desktop monolith (wxPython + local solvers)
    ↓
[Month 1-3]  Extract solvers → FastAPI endpoints (local Docker first)
    ↓
[Month 3-6]  Deploy FastAPI to Cloud Run, update wxPython client to POST to API
    ↓
[Month 6-12] Build Next.js web frontend (VTK.js viewer, React panels)
    ↓
[Month 12-18] Full web SaaS launch, desktop becomes "thin KiCad plugin"
    ↓
[Month 18+]  AI Assistant, MTBF engine, multi-board analysis in cloud
```

---

## Open Questions for Decision

> [!IMPORTANT]
> 1. **Auth provider:** Use Auth0 / Clerk / Supabase Auth, or build custom? Auth0 is fastest to market.
> 2. **Cloud provider preference:** AWS, GCP, or Azure? GCP has strong Python/ML ecosystem; AWS has broadest market trust for enterprise.
> 3. **Pricing model:** Per-simulation-minute (usage-based) or flat tiered subscription? Usage-based is more SaaS-friendly but harder to predict revenue.
> 4. **KiCad plugin preservation:** Should the KiCad plugin remain a first-class product, or become a "gateway drug" to the web SaaS?
