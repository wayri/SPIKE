# Runnable Studio tutorials

These are deliberately simple analytical/functional fixtures, not hardware measurements or full-system qualification. Open a .cir through Help → Example circuits, review replacement, then F5. All values are SI/SPICE suffix values.

| File | Workflow | Check |
|---|---|---|
| 01_dc_divider | Operating point, part properties, voltage/current probes | V(out)=6 V |
| 02_rc_startup | Transient, stacked plots, cursors, spectra | tau=1 ms; final near 4.966 V |
| 03_rl_startup | Current probes, stored energy | final current near 0.993 A |
| 04_pwl_load | Dynamic ideal electronic load profile | bus droops when load current rises |
| 05_parameter_steps | Run overlays, run-bound cursors | three independently solved runs |
| 06_subcircuit_ports | Hierarchy port mapping and shared definition navigation | mid=4.8 V, out=2.4 V |
| 07_static_diode | .model, nonlinear DC | static forward conduction, no recovery/thermal physics |
| 08_pwm_switch | Switching waveforms | gate-controlled output; not a transistor switching-loss benchmark |
| 09_dc_sweep | DC transfer | output is half input |
| 10_recorded_sensor.csv | File → Import audio sensor into V1 of 02 | channel 0, unit m/s², choose explicit V/(m/s²) gain |

## Workflows using these circuits

- Wiring: W, click terminals/corners; drag routes; Ctrl+Z. Label equality already connects nets, even before drawing a route.
- Plots: open 02 or 05, probe V(out) and I(R1), place/drag cursors, open Cursor window, use wheel/Shift-wheel, right-click for grid, notes and fit.
- Sequences: add an operating-point profile and a transient profile in Simulation Manager; save the schematic, Run All, inspect separate result archives.
- Dashboard: use 02 with the dashboard designer; bind meters/plots to its recorded voltages/currents. Continuous source control is best effort, not hard-real-time HIL.
- Controller: use 02 with the existing Controller workspace default sense=out and drive=V1; compile only trusted C/C++. Read inputs[IN_sense], write outputs[OUT_drive].
- Thermal reporting: provide reviewed thermal_assessment inputs in part metadata, re-run and open Analytics → Thermal margins. Without ratings and temperature evidence the correct result is unavailable.
- Recovery: change an unsaved circuit/draft, wait 60 seconds, then File → Recover autosave as a separate unsaved copy.
- Library/keys: File → Import/Export library package; Edit → Shortcut profiles → Load/Save/Apply. Imports preserve execution limitations.

Not demonstrated as working: complete satellite/EV/solar systems, calibrated battery aging, physical audio I/O, graphical nested subsheets, Verilog co-simulation, manufacturer-library parity, hard-real-time certification, full SPICE analysis parity or physical LED/lamp optics. Those remain outstanding work.
