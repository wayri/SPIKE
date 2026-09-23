# SPIKE Community Edition: Proprietary IP Protection Strategy

This document outlines the strategic approach to releasing a "reduced feature" version of SPIKE to the public/open-source community while completely safeguarding the proprietary, highly valuable intellectual property (IP) inherent in the simulation engines.

## 1. Architectural Separation (Client vs. Engine)

To protect the core IP, the repository must be strictly partitioned into an open-source UI Client and a closed-source Simulation Engine.

### Open-Source Elements (Community Repo)
- `demo_spike.py` and the `python/ui/` framework (Ribbon menus, AUI docks, wizards).
- Basic board geometry parsers (`python/core/board_parser.py`).
- 3D rendering pipeline using PyVista (`python/viz/`).
- Basic reporting templates (HTML generation without the advanced AI analytics).

### Closed-Source / Protected Elements (Proprietary Repo)
- **`spike_core.pyd` / `spike_core.so`:** The C++ multi-threaded PEEC solver, RLC extraction matrix generators, and memory-optimized sparse solvers.
- **`python/core/thermal_mesher.py`:** The advanced copper homogenization algorithm and isometric resistance mesh builder.
- **AI/NLP Data Scrapers:** Any automated datasheet component parameter extraction logic.

## 2. Release Mechanisms for the Protected Engine

Since the open-source client requires *some* solver to function, we have two secure release pathways for the Community Edition:

### Approach A: Pre-Compiled "Black Box" Binaries
Distribute the solver strictly as stripped, compiled binaries (e.g., a `.pyd` Python extension compiled via Nanobind).
- **Protection:** Stripped symbols prevent easy reverse engineering. It is a "black box" that accepts board matrices and returns heatmaps.
- **Limitation:** Hardcode a node-count limit within the C++ layer (e.g., maximum 5,000 nodes). If a user imports a complex board requiring more nodes, the solver aborts with a message prompting an Enterprise upgrade.

### Approach B: Cloud-Tethered Evaluation (SaaS Primer)
Instead of providing the solver locally, the open-source client uploads the extracted board matrix (a sanitized JSON/Binary payload containing no actual routing, just the mathematical RLC matrices) to your SaaS backend.
- **Protection:** 100% secure. The solver code never touches the user's machine.
- **Limitation:** Rate limit computations to 3 simulations per day, or restrict the mesh resolution significantly.

## 3. Reduced Feature Set (Freemium Constraints)

The Community Edition should intentionally lack the depth of the Enterprise version to drive conversion:
- **Power Integrity (PI):** Restrict to simple DC IR-Drop. Disable AC Impedance analysis, frequency sweeps, and transient load-stepping.
- **Thermal:** Restrict to basic steady-state conduction. Disable forced airflow convection modeling, virtual heatsink attachments, and transient thermal modeling.
- **Reporting:** Disable native PDF Dossier generation or apply heavy watermarking.
- **Batch Processing:** Disable the Batch Manager and automated multi-net optimizations.

## 4. Execution Steps Before Release
1. **Repository Split:** Move `src/` (C++ code) and `thermal_mesher.py` out of the public repo into a private GitLab/GitHub repo.
2. **Build Pipeline:** Setup a CI/CD pipeline in the private repo that compiles `spike_core.pyd`, heavily obfuscates/strips it, and injects the node-limit license checks.
3. **Artifact Injection:** The CI/CD pipeline pushes the resulting `.pyd` back into the public repo's release assets as a pre-compiled dependency.
