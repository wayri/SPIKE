# Restrained propulsion pod — working coupled reference

The new `coupled/` project executes an actual compiled SPIKES C controller,
terminal-current/flux/backEMF/torque P1 FEM motor, shaft and geometry-derived
hover-BEM propeller reaction in one feedback loop. The native project retains
2,500 accepted steps, 500 controller ticks, 26 field states and eight admitted
data views. Exact KiCad sources and four original tessellated STEP parts accompany it.

This is a synthetic two-phase, linear-PM, averaged-drive and quasi-steady BEM
benchmark. It is not a calibrated VESC three-phase motor/firmware simulation or
blade-resolved CFD. Board thermal and the earlier reference examples remain
separate; their losses/temperatures are not fed into the new loop.

## Run the working loop first

1. Use the current SPIKE source desktop with its `.venv` worker and optional
   SPIKES Studio C compiler runtime. Previously built/frozen workers do not
   automatically acquire the new service. Restart the source desktop after updating.
2. Open `coupled/restrained-propulsion-pod-coupled.spike`. Its board, high-axis
   stand, motor regions, shaft and 300 mm two-blade visual geometry share saved
   assembly coordinates. CAD is original nominal geometry, not measured construction.
3. Open `coupled/01_run_coupled_pod.py` in Python Workspace and select its folder
   as working directory. Run it with the adjacent `worker-params.json`. It calls
   the actual coupled worker, compiles the fixed original C controller and
   publishes computed speed/current/torque/thrust/flux histories plus final
   motor B and BEM disk inflow views. Allow up to 180 s for the workspace run.
4. Alternatively select **Run controller / FEM / propeller loop** in the Python
   template library; set REQUEST_FILE to the reviewed `worker-params.json` and
   optional RESULT_FILE to a new path. The template defaults to doing nothing.
5. To inspect another computed field state without solving again, select
   **Review saved coupled motor field frame**, point RESULT_FILE at
   `coupled/actual-coupled-result-views-fixed.json` and choose FRAME_INDEX 0–25.
   The selected saved time is printed. This is frame review, not an automatic
   animation or a real-time solving claim.

See `coupled/README.md` for numerical meaning, actual run evidence, native
save/reopen checks and reproduction. Interactive desktop visual acceptance and
screen recording remain separate checks; the actual Python Workspace child
execution and returned data-view admission passed.

## Earlier separate studies retained

1. Open `assembly/restrained-propulsion-pod.spike` in SPIKE. Show the actual
   unchanged VESC PCB, original stand and nominal motor envelope. Both STEP
   parts have retained tessellations. Component manufacturer 3D models are
   excluded; the envelope is not electromagnetic winding geometry.
2. Open `electrical/pod_bus_startup.spksch` in internal SPIKES Studio. Run the
   supplied transient and inspect the saved bus-voltage/current scopes. It is
   an illustrative 48 V source and prescribed load pulse, not a physical motor
   demand or a qualification of the VESC board at that operating point.
3. Open `electrical/current_sensing.spksch`. Run and inspect shunt/ideal amplifier
   histories. See the electrical README for model limits and runtime selection.
4. Use the separate `electrical/motor_reference` chapter if present: actual
   planar FEM with supplied drive/motion, not controller-driven pod FEM. Its
   own README describes exactly what ran.
5. Open `thermal_geometry/pod-supplied-5w.spike`. Use the assembly volume field
   study and transient solid thermal controls to inspect 25 computed frames
   over 120 s. Heat is an imposed 5 W, not extracted winding/controller loss.
   The matching field-study import is included.
6. `board_thermal/vesc-steady-thermal.spike` retains the earlier separate VESC
   supplied-loss plate study: six MOSFET sites at 0.5 W each. Missing physical
   stackup still prevents claiming its transient or case-sink solution.

Play computed histories smoothly, and identify accelerated playback. UI
recording and native interactive visual acceptance have not been performed in
this build; the retained checks cover actual native document/package APIs,
solver execution, source identity, geometry and bounded reference checks.

## KiCad and source identity

Every PCB-based `.spike` has the exact embedded `.kicad_pcb` beside it and the
available full native project under adjacent `KiCad/BLDC_4/`: legacy `.pro`,
root/hierarchical `.sch`, symbol libraries, footprint libraries and tables.
Sources are unchanged. Per-project `.sources.json` and
`KICAD_SOURCE_INVENTORY.json` retain hashes and availability. Original KiCad
legacy files remain original; no converted schematic or clean ERC is claimed.
The stand-only thermal project has no KiCad geometry input and declares that.
The unchanged legacy board produced 964 KiCad 10 DRC findings (538 errors and
426 warnings), with zero reported unconnected items. The full report is in
`kicad_checks`; modern library/rule and clearance findings are retained rather
than suppressed. This is an imported simulation source, not a clean fabrication
release. The native front-copper/outline/silkscreen plot was exported and inspected.

VESC hardware is Benjamin Vedder and upstream contributors' CC BY-SA 4.0 work,
pinned to `f1c65014d0caab5d99d888fc3025377861ac6ae2` at
https://github.com/vedderb/bldc-hardware. Notices and license accompany the CAD.
Original SPIKE scripts, reference circuits and stand geometry are Apache-2.0.
No firmware, external motor/propeller CAD, supplier compact models or native
solver binaries are redistributed. This folder's aggregation does not change
the individual source licenses.

## Integration contract and next gates

`assembly/integration-draft.json` is a source-bound inventory and requirements
record, explicitly not an executable solver request. It identifies the real
VESC input, three motor terminals and Hall/temperature connector by board
occurrence, component, pin, pad and net identities. Active motor bindings are
empty until physical winding data and a supported solver adapter exist.

The solver chat was asked to implement current-driven moving motor FEM,
reciprocal backEMF/controller closure, conservative losses and later rotating
propeller flow/thrust. The multiboard chat was asked to implement native setup,
explicit saved bindings, guarded in-app runners and real field/history replay.
Dispatch is recorded in `coordination.json`; it does not establish delivery.

Before calling this a physical VESC/drone propulsion simulation, select an adequately
documented motor/propeller and bind its actual winding/magnet/material/geometry,
controller and reference data. Then establish electrical-to-field-to-shaft
closure, energy accounting, mesh/time refinement and reference comparisons.
Follow `examples/promo_showcase/FLAGSHIP_SYSTEM.md` for progression to four
motors, bounded flight and EM chamber studies. The separate 48 V to 1.8 V
planar-converter pack retains its own operating point and evidence.

## Reproduce in the SPIKE source workspace

Run the included source scripts from the repository root, using the existing
local dependencies recorded in their verification files:

```powershell
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/electrical/run_examples.py
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/thermal_geometry/build.py
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/build_assembly.py
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/check_kicad.py
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/package.py
```

The magnetic-reference chapter includes its separate rerun command. Rebuilding
needs the pinned VESC source cache and existing solver/runtime dependencies;
the ZIP is a ready-to-open project pack, not a standalone SPIKE installation.
