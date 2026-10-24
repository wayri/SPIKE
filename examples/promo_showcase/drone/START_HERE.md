<!-- SPDX-License-Identifier: Apache-2.0 -->
# PCB drone: supported studies and blocked whole-flight integration

IRIS is a published PCB flight-controller platform with four integrated ESCs,
a 2S battery and four BLDC motors. Source: Eugene109/IRIS, pinned revision
999dd2eb725d550889c1ffe2c09f8de0390d081b,
https://github.com/Eugene109/IRIS/tree/999dd2eb725d550889c1ffe2c09f8de0390d081b .
The upstream README supplies the GPL-3.0 license declaration and the BOM facts.
It describes a separate printed frame; this is a PCB-centric drone, not a
monolithic printed-circuit motor/propeller vehicle.

**This pack does not simulate the complete flying drone.** Current SPIKE
`docs/SOLVER_STATUS.md` and `docs/VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md`
explicitly leave executable controller/propulsion/aerodynamic flight coupling
unfinished. Rotating propellers, rotor/stator interfaces and general propeller
CFD are unsupported. A room-shaped solid, stationary airflow test or animated
CAD assembly cannot establish those capabilities. No flight trajectory or
propeller-flow result is included.

## Open the executed parts

- Open `thermal/iris-steady-thermal.spike` in SPIKE. It retains the original PCB,
  declared heat inputs and actual steady temperature result. See
  `thermal/README.md` for exact assumptions, numerical checks and blocked
  transient evidence. Its imposed power is not derived from a flight run.
- Import `IRIS_SOURCE_GPL3/ProPrj_IRIS.kicad_pcb` and select it. In Tools >
  Python workspace open the `analytics` scripts folder and execute the numbered
  PI/SI templates with Ctrl+Enter. Follow `analytics/README.md`; these are actual
  BOM/connectivity-bound reduced circuits, not whole-board field extraction.
- Follow any Studio project instructions in `analytics/README.md`. Native
  circuit execution does not establish drone firmware execution or flight.
- `IRIS_SOURCE_GPL3/frame_bottom.step` and `pcb_cover.step` are original
  upstream frame parts for geometry inspection. They have not been registered
  to the PCB in an executed airflow or thermal assembly.

The PCB's imported Value fields are blank; scripts use explicit source BOM
reference joins and check connectivity. Upstream warns its EasyEDA-to-KiCad
conversion may have clearance/zone issues. Retained import diagnostics are not
waived. Detailed package/motor/propeller 3D models are not supplied.

## Requested bounded-volume scenario

`flight_volume_mm.stl` is a closed 2 x 2 x 1.5 metre box in millimetres, supplied
only as original geometric context. `flight-scenario.json` records its meaning,
missing physical inputs and missing coupling. It is intentionally not a solver
request. Importing the box does not activate a flight domain or produce airflow.
No initial flight state is invented.

Completing this request needs the GP15 motor/propeller bench, admitted 6-DOF
vehicle/sensor/controller coupling, and rotating aerodynamic methods with
independent derivations, primary references, conservation and refinement checks.
Then motor/thrust data, mass/inertia and battery/controller timing must be bound
to this vehicle. Existing isolated electrical, thermal or FEM examples cannot
be advertised as that combined result.

## Attribution and sharing

Hardware, original frame parts and board-derived projects/data retain GPL-3.0
under upstream's declaration; include the source and license in
`IRIS_SOURCE_GPL3`. Original SPIKE orchestration/documentation is separately
Apache-2.0. Preserve each boundary and modification/assumption notices. No
upstream firmware or native library is redistributed. The upstream full
assembly references third-party motor/propeller models; those rights have not
been established here, so the assembly is excluded. No upstream endorsement.

Suggested caption: “IRIS PCB by Eugene109 and contributors, GPL-3.0; SPIKE
examples by wayri/SPIKE contributors. Reduced PI/SI and imposed-loss steady
board thermal studies. Whole-drone flight and rotor CFD are not implemented.”

Exact executed requests/results, admitted Python views, source hashes and
capability snapshot are in EVIDENCE. Native package readback and ZIP byte hashes
were checked. No interactive GUI recording or whole-flight run was performed.
