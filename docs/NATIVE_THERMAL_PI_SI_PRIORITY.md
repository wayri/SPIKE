# Native thermal, PI and SI delivery priorities

Updated 2026-09-20 following the user's scope change. EMI expansion is deferred;
preserve existing functionality without spending this workstream on new EMI features.

## Direction

Use the owned solid-thermal implementation as the first native thermal route.
OpenFOAM is optional comparison/advanced-CFD infrastructure, not a prerequisite
for native solid conduction. This is a delivery direction, not a change to solver
qualification or permission to route unsupported cases silently.

Current inspected implementations:

- `structured_solid_thermal.py`: regular-grid finite volumes, anisotropic
  conduction, material-interface resistance, implicit transient integration,
  prescribed convection and ambient surface radiation. Sparse-direct admission
  is currently 16,384 cells; the larger schema ceiling is not execution capacity.
- `structured_electrothermal.py`: steady resistor-network coupling with explicit
  conservative heat/temperature bindings; at most 2,048 cells and 128 elements.
- `pdn.py`: target review and candidate-bank ranking using port-shunt, explicit
  connection-path or supplied two-port impedance models.
- Reviewed PI path composition exists for explicit linear series components;
  it is not general nonlinear regulator or arbitrary return-field extraction.

## Checkable delivery sequence

1. **Reliable PI foundation:** close the real-board transient filament failure;
   preserve finite contact resistance and explicit return connections; validate
   DC and AC/transient against independent circuits, energy/passivity checks
   and mesh/time refinement. Never lift branch limits without resource evidence.
2. **PI/PDN guided workflow:** select rail and return, source/load tables,
   source impedance and load profile, reviewed series components, target drop
   and impedance, sweep/time settings, preview and solve, then results/report.
   Every wizard step must round-trip through native project persistence and CLI.
   Missing return, disconnected endpoints and unsupported components need
   actionable errors at setup rather than an unexplained failed solve.
3. **Decoupling and placement:** show baseline and loaded impedance, resonance
   peaks, target violations and candidate tradeoffs. Rank only explicit feasible
   board sites with mounting/via/return connectivity and extracted transfer
   impedance. Account for capacitor ESR/ESL, count and footprint constraints.
   Report “best among evaluated candidates,” not unrestricted/global optimum.
   Validate ranking on a known circuit and an independently correlated board.
4. **Native thermal workflow:** expose the existing reference solver through a
   supervised service/CLI adapter; translate board/assembly materials, copper,
   sources and contacts into an auditable grid. Reject missing mappings and
   retain discretization assumptions. Add temperature/flux plots, energy ledger,
   transient probes, save/reopen and domain-specific reports. Validate slab,
   layered/contact, heated-board and electro-thermal fixtures with refinement.
   Large boards need bounded iterative solving and geometry-convergence evidence
   before raising current capacity. Prescribed convection does not solve airflow;
   ambient radiation does not implement arbitrary enclosure view factors/CHT.
5. **SI basics:** an explicit board net/source/sink/return workflow with driver
   edge and termination setup; delay and impedance, loaded step/pulse response,
   reflections/TDR, S-parameter import/export and available crosstalk/eye plots.
   Expose assumptions, units, cursors and stale-result state. Verify a real route,
   a disconnected route, model import and save/reopen. Keep illustrative eyes
   separate from statistical BER, DDR timing or protocol compliance claims.

## Acceptance across all three domains

Resizable tabular inputs, explicit units, actionable validation, cancellation,
resource limits, source/mesh/result identity, cross-highlighting where coordinates
exist, plots and tailored reports, and lossless project save/reopen are required.
CLI tests establish numerical/contract behavior; interactive workflow checks are
still required before claiming usable desktop completion. Numerical release
changes require the project's knowledgeable human review.

## Current evidence, not completion

2026-09-20: 46 focused tests passed across structured solid thermal,
structured electrothermal, PDN, PI path and PI path circuit modules. This confirms
the inspected foundation, not arbitrary-board thermal translation, optimal
placement, completed wizards, or production qualification. No solver selection,
release gate or installer was changed by this assessment.
