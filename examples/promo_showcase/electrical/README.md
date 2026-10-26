# Runnable electrical and magnetic showcase

Original SPIKE examples, Apache-2.0; see LICENSE, NOTICE and source-provenance.json. No third-party PCB/CAD or program is copied. All physical/material/controller parameters are illustrative. No production qualification or hardware correlation is implied.

## Open native projects

**SPIKE Studio:** File > Open `studio/two_wheeler_dashboard.spksch`. Use File > Open rather than netlist import so the controller and dashboard survive. Controller: review embedded C and assumptions, approve trusted execution, Compile, enable attachment to Continuous, Run closed loop. Dashboard: Run mode, Throttle 0.2 then Send; apply Brake to observe negative current. Pause/resume/stop use normal controls. Source C is embedded in the project; the matching `ev_current_controller.c` and `ev_motor_plant.cir` are also included for inspection/rebuilding. A working C compiler is required. Never attach to hardware.

The actual native armature R/L circuit is coupled to a sampled C current controller and explicit mechanical integration/back-EMF source. This is an averaged DC drive, not three-phase FOC, a BLDC/PMSM inverter or FEM field/circuit coupling. Temperature is a lumped estimate. Wall-clock execution can be slower than virtual time.

**Studio circuit decks:** import/open `studio/02_rc_startup.cir`, `03_rl_startup.cir`, or `gate_miller_ringing.cir`, then run the native transient. Probe V(out) for RC, inductor current for RL, or V(gate)/V(drain)/I(Lpackage) for ringing. Ringing is a linear RLC/capacitive-injection demonstration, not a nonlinear manufacturer transistor prediction. These are supported native netlist inputs, not saved dashboard projects.

**SPIKE EM projects:** File > Open any `magnetics/*.spike`, then **EM > Machines**. Each real portable v3 package retains its request and freshly executed result in the existing EM study persistence. No PCB is required or included: these are generated machine workspaces. The package readback and exact frontend state projection were verified; interactive UI opening has not been performed in this pack task.

- `planar_pm_fem.spike`: Geometry field study, actual 2D PM rotor FEM and prescribed-current quasi-static motion. Run planar field study repeats it. Select B/H/A and inspect motion/torque histories. No voltage drive, controller feedback, sliding interface, moving eddy currents or 3D CAD. Torque is not mesh-accuracy-converged.
- `planar_solenoid_fem.spike`: Geometry field study, nonlinear supplied B-H curve, actual stationary eddy/thermal transient. Run planar field study repeats it. Select final B/H/A/temperature/Joule loss and inspect histories. Extra winding heat is supplied J²/sigma, not circuit solved; no hysteresis/core loss or motion during transient.
- `motor.spike`: expand Parameter reference models; actual constant-parameter PM DC electromechanical ODE solve and power/energy ledger. No spatial fields.
- `electromagnet.spike` versus `electromagnet-air.spike`: expand Parameter reference models, Linear single-gap electromagnet. Identical parameters except supplied relative permeability 2000 versus 1. Retained solved inductance is approximately 2.928 mH versus 49.441 uH. This compares a linear reluctance model; it is not a PCB spiral coil or a 3D magnetic core field solve.

Matching plain JSON requests are included. For the planar FEM JSON, the supported alternate UI workflow is EM > Machines > Geometry field study > Advanced request JSON, paste the exact request, commit edit, Run planar field study. Reduced-model JSON has no standalone file-import button; use the corresponding native .spike or enter its parameters. Browser previews inspect retained results but cannot execute the desktop worker. The magnetic workbench currently displays final field plus histories, without a field playback slider.

## Reproduce checks from repository root

```powershell
.venv/Scripts/python.exe examples/promo_showcase/electrical/verify.py
.venv/Scripts/python.exe examples/promo_showcase/electrical/package_studies.py
```

Raw executed results/checks are under `output/promo-showcase-20261023/electrical/`. Verification executes three owned C++ transient decks, three reduced machine cases, two actual planar FEM studies, then the exact copied controller project through the owned native interactive circuit engine. It checks positive throttle current/acceleration and negative brake current. It uses a repository-local temporary directory for trusted controller compilation. Native runtime path/hash are recorded; no DLL or compiler is redistributed here. Package builder retains these actual results and verifies authenticated readback and frontend projection.

## Arduino native board PI and SI

Run `package_arduino.py` from this directory through the repository Python runtime to rebuild from the existing cached Arduino source. The output is `output/promo-showcase-20261023/electrical/arduino-cc-by-sa/arduino-r4-relay-shield.spike`. That folder is deliberately separate: Arduino CAD/source archives and derived native board project retain CC BY-SA 4.0, while the original SPIKE simulation/package glue is Apache-2.0. Source URLs, hashes, license notices and full original CAD archives accompany it.

Open the native Arduino project, choose Multi-board, inspect Boards/Mechanics and Links, then Coupled studies > PI or SI > Run. Both cases were freshly executed from the saved physical-assembly-bound setup and persisted with current manifest guards; reopened/hydrated results were validated and compared exactly with the new runs. Raw request/result files and verification accompany the project. PI is a supplied reduced operating-point network; SI is a supplied 17-frequency reduced AC circuit. Neither is spatial full-board extraction, detailed digital channel margin, transient current-density playback or full-wave EM. Older thermal state inherited from the copied project is explicitly not a fresh run in this electrical task.

No finger/PCB touch field example, PCB air/core spiral model, controller-driven FEM motor or board PI/SI qualification is introduced by this pack. Those missing physics are not replaced by animated surrogates.
