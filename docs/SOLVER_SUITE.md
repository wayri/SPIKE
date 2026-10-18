<!-- SPDX-License-Identifier: Apache-2.0 -->

<img src="../app/public/spike-solver-suite.png" alt="SPIKE solver suite S mark" width="96">
# Solver manager and capability navigation

The desktop Solver manager groups current source workflows across circuits and
SPIKES Studio, PI, SI, thermal/airflow, EM, structural mechanics and execution/coupling.
Internal solvers/models, external adapters, supporting tools and planned work
have separate groups and a provider/role filter. Search matches friendly names,
stable IDs, scope, limitations, evidence paths and extension identities. Domain and
status filters combine with the search. Clear filters restores the full list;
an empty search result supplies recovery guidance. Planned capabilities have
no executable route.

The manager is a navigation index. Its worker-registry section displays the
existing worker catalog supplied by the application, including unknown future
entries, exact IDs, reported state and model status. A missing/failed catalog
probe is explicitly identified; fallback entries do not establish availability.
Registry rows use search/provider filters; domain and capability-status filters
apply to workflow cards. Loading the registry does not run a
solver, admit input geometry, grant extension trust or qualify a model. Each
opened workflow retains its existing worker/runtime/model admission. Read
SOLVER_STATUS.md and the evidence reference on each card for bounded validation.
External adapters retain their experimental or unqualified physics limits.

Studio-specific authoring entries open the circuit workspace and its Studio
handoff; the card does not assert those editors exist inside the React panel.
PDK, ASIC, TCAD and scalar co-simulation entries identify their CLI/Python or
native console workflows and link to the existing Python workspace entry.
Full TCAD and owned arbitrary-PCB full-wave remain unavailable.

## Ownership and extension

`app/src/solverSuiteCatalog.ts` owns this presentation index: stable capability
identity, domain, status, concise scope/limits, checked-in evidence/source paths,
workspace action, and optional extension identity. This is not a substitute for
the backend capability registry or solver selection policy. A new entry must
identify actual source and scope evidence; do not infer support from a menu or
installed executable. Source-only capabilities must name their real entry path.

`app/src/SolverSuitePanel.tsx` owns search/filter state and accessible cards.
`app/src/solverManagerModel.ts` owns display names and mappings to existing
registry identities. Naming never creates a new executable solver ID or changes
saved project requests. Capabilities exposed through Python or worker methods
retain their source paths and entry instructions rather than invented plugin IDs.
`onOpenWorkflow(action, extensionId?, capabilityId?)` delegates navigation to the composition
root. It must open configuration rather than run numerical work. Existing
worker and extension detection remain authoritative. The panel uses shared
button tokens and responsive cards, including narrow one-column filtering.

Run `node scripts/test-solver-suite.mjs` from `app` for identity, evidence path,
extension manifest, status/route, search and rendered admission-state checks.
These checks establish presentation behavior and catalog consistency, not solver
accuracy. Run the shared button guard and TypeScript checks for UI changes;
verify the integrated desktop at wide and narrow sizes before visual acceptance.

## Integrated desktop entry

Open Solver manager from the application command search. Its stable workspace
actions open the existing configuration surfaces; optional extension IDs select
the declared extension route. Circuit entries reach Parts & pins, native circuit
setup and the explicit SPIKES Studio handoff. Adaptive stepping, model builders
and SMPS tools remain in their documented Studio/CLI locations. Python actions
open the workspace without injecting or executing code. This index covers the
listed implemented capability families and explicit pending foundations; it is
not an exhaustive enumeration of every solver primitive or native API.


Capability results in universal search open a prefiltered suite card. Named PDN,
Touchstone, eye-mask and PI routes open their specific setup panel. PDN setup is
saved in the existing power-tree request field. Finite-dielectric and sampled-port
foundations retain their documented Python/API entry; opening Python executes
nothing automatically.

2026-10-16 integration checks: browser preview observed capability search,
filtered card and direct PDN setup navigation. The worker service reported local
source Studio preparation/launch prerequisites available; this was discovery,
not a standalone GUI launch or solver qualification. Native screenshot acceptance
remains outstanding after the native verification helper could not activate the
development host window. Installed/public Gamma was not replaced.

## Internal names and scope

| Display name | Existing identity or implementation |
| --- | --- |
| SPIKE DC PI | `spike.routed_dc`; reduced DC conductor network |
| SPIKE 2.5D PI | `spike.peec_2_5d`; quasi-static PEEC RLCG |
| SPIKE PI Transient | `spike.peec_rl_transient`; geometry-derived RLC network |
| SPIKE 3D PI - DC conduction | `assembly_tetra_electrical.py`; bounded scalar tetra DC, not full-wave |
| SPIKE PDN and Filters | `pdn_network.py`; explicit circuit network |
| SPIKE 3D Capacitance / Dielectric AC / Port Reduction | Retained-dielectric and sampled-network APIs |
| SPIKE SI Networks / SI Channels / SI Eye and Protocol Screens | Sampled networks, bounded quasi-TEM extraction and deterministic screening |
| SPIKE Board Thermal / 3D Solid Thermal | Layered board and retained tetra solid heat transfer |
| SPIKE Assembly Electrothermal / PWM Electrothermal | Explicit conservative loss/temperature coupling |
| SPIKE Channel Airflow / 2D CFD | Channel approximation and isothermal cavity reference |
| SPIKE 2D Magnetic FEM / Lumped EM Machines | Planar fields and supplied-parameter machines |
| SPIKE 3D Structural / Thermoelastic | Experimental static isotropic tetra mechanics and same-mesh thermal coupling |
| SPIKES Circuit MNA / Adaptive Transient | Reviewed circuit and native transient workflows |
| SPIKES I/Q Device Models / Lumped Physics Models | Explicit supplied equations and composition |
| SPIKES SMPS Stability / Battery Reference | Bounded averaged control plants and prescribed-current battery study |
| SPIKES Passive and Digital Models / 1D Equilibrium TCAD | Functional component models and equilibrium semiconductor electrostatics |
| SPIKE Scalar Co-simulation | Fixed-grid replay/gain orchestration |

SPIKE Surface MoM and SPIKE 3D Full-wave remain planned/unavailable declarations.
Display names convey organization, not qualification; every card retains its
specific evidence and unsupported physics. No solver equations changed.
