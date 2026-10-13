# SPIKES Studio and board simulation

Open the circuit workbench from the existing PI/SI circuit workflow. The Board
circuit page extracts component centers, rotations, board side and pad-to-net
connectivity from the currently loaded board. It keeps component placement and
uses orthogonal drawing routes guided by copper orientation. Dense or obstructed
connections use net labels. Display crossings never create electrical junctions.
This is a connectivity drawing, not an impedance or compact-model extraction.

Select a drawn part to select the same board object. Assign an existing model,
review its values and physical-pad pin map under Parts & pins, then confirm it.
Model changes invalidate the confirmation. Unreviewed components remain inert
context in the Studio handoff. Open SPIKES Studio stages a bounded JSON handoff
and launches the local first-party Studio; Prepare Studio file stages without
launching. A missing local Studio runtime is reported as unavailable.

## Feedback setup

The Feedback page composes the current assigned circuit with the selected
steady-state or transient analysis. Each dissipative resistor requires explicit
board, thermal and model bindings. Supply heat capacity in J/K, thermal resistance
to ambient in K/W, reference/initial/valid-range temperatures in K, and TCR in
1/K. These inputs are not inferred from the BoM or enclosure. The current UI
creates one thermal node per resistor with an ambient path; the worker contract
also supports explicit inter-node thermal links.

Optional conductor geometry uses length, width and thickness in m, resistivity
in ohm m and isotropic expansion in 1/K. The reference geometry resistance must
agree with the composed circuit. Expansion changes dimensions and resistance;
it is not a structural deformation or contact/motion solver.

Native electrical stepping and thermal feedback iterate within communication
windows. Only converged windows are accepted. The worker retains the current
board revision, supplied request and convergence/loss ledger. Live accepted
frames feed temperature, resistance, heating-power and current plots; Stop
cancels the owned worker. Changing the board or workspace cancels the active
run and invalidates its displayed results. Setup is saved in the circuit
workspace; Save results exports the supplied setup and result record.

Coverage is explicitly limited to supplied linear R/L/C and ideal sources (constant, continuous PWL and finite-rise/fall PULSE) with
resistor dissipation. Unmodeled semiconductor, switching, magnetic, dielectric
and radiation losses are not inferred. The result is an approximate lumped
model and is not a spatial board thermal field. Numerical implementation needs
knowledgeable human review before release. Native launch and installed payload
verification are separate from source and headless checks.

## Ownership and contracts

- `app/src/studioBoardCircuit.ts`: inert placement/connectivity extraction.
- `app/src/BoardCircuitStudioPanel.tsx`: board selection, assignments and handoff.
- `app/src/studioFeedback.ts`, `StudioFeedbackPanel.tsx`: supplied feedback setup,
  typed worker requests, cancellation and accepted-result plots.
- `python/spike_core/studio_board_coupling*.py`: coupled execution and admission.
- `standalone/spikes_project/studio/python/spikes_studio/studio_handoff.py`:
  bounded inert handoff import into the existing Studio document.

See [SPICE workspace](SPICE_WORKSPACE.md), [solver status](SOLVER_STATUS.md) and
[Studio coupling](STUDIO_BOARD_COSIMULATION.md) for model applicability and
numerical validation details.
