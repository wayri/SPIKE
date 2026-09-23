# SPIKES workflow acceptance criteria

SPIKES should adopt familiar engineering interactions, not copy a competitor's
appearance or claim superiority without measurements. This is a development
target, not a declaration that the features below are complete.

## Reference workflows

- [PLECS schematic and library workflow](https://docs.plexim.com/plecs/5.0/using-plecs/):
  browse, place, connect, edit parameters, organize subsystems, configure and run.
- [PLECS Scope](https://docs.plexim.com/plecs/latest/using-plecs/using-scope/):
  multiple plots, accessible zoom tools, cursor data and numerical cursor entry.
- [LTspice waveform workflow](https://analogdevicesinc.github.io/ltspice-reference/ai_ref/WAVEFORM-VIEWER-GUIDE.html):
  probe from the schematic, inspect traces and organize waveform panes.
- [QSPICE development workflow](https://www.qorvo.com/design-hub/videos/2024-qspice-accelerate-your-development-with-new-features):
  model/netlist assistance and fast tuning/resimulation.
- [PSIM integration](https://web.altair.com/academic-hub-psim): power-electronics,
  waveform post-processing and co-simulation are important reference use cases.

No single application is the best reference for every job. The primary user
journey must stay consistent: **Place → Connect → Configure → Run → Probe → Compare**.
Advanced tools should be discoverable without overwhelming that journey.

## Release gates

1. A new user creates and solves a divider without editing a netlist. Rotation,
   wiring, properties, undo, save/reopen and analytical output are tested together.
2. A real manufacturer component carries manufacturer, exact part number, model
   source/version, licensing status, pin mapping, supported analyses and a
   qualification circuit. Generic presets never count toward this gate.
3. Zoom reveals original simulation samples; rendering reduction must not change
   measurements. Fit, trace visibility, stacked panes and cursor arithmetic must
   have end-to-end tests, including unequal sampling and stepped runs.
4. Continuous dashboards explicitly show simulation time, wall time, capture mode,
   pause state and dropped samples. SIL/PIL/HIL labels require actual interfaces
   and timing qualification; best-effort desktop operation is not hard real time.
5. Reference benchmarks use equal models, tolerances and recorded platform data;
   report accuracy, convergence, cold/warm runtime and peak memory, including
   failures. No speed or capability superiority claim before passing these gates.

## SPIKES-specific direction

Keep one probe identity across schematic readouts, waveform panes, rolling event
capture and dashboards. Preserve model provenance and validity limits with each
part. Make replayable interaction scripts and reusable circuit/control blocks
first-class project objects. These are roadmap goals, not completed capabilities.
