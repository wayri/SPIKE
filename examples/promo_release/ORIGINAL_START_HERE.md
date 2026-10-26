# SPIKE promo project pack

Prepared 23 October 2026. These are real project/input files with executed results, not slide graphics or video mockups. Open the native projects in a current SPIKE/Studio build. No simulator, compiler, Gmsh or third-party solver executable is bundled.

## Start with these scenes

| Folder | Open/import | Ready behavior | License |
| --- | --- | --- | --- |
| `01-pcb-temperature/01-ebrake-transient/` | `01-ebrake-transient.spike` | Authentic EBrake board, saved layered thermal inputs, 16 actual frames over 600 s; rerun in Thermal workspace | Apache-2.0, owner-authorized board |
| `01-pcb-temperature/02-ebrake-transient-virtual-sink/` | `02-ebrake-transient-virtual-sink.spike` | Same PCB with an explicit mathematical heatsink boundary; compare stored peak 49.280 C versus 43.698 C | Apache-2.0 |
| `02-case-heatsink/` | `case-contact.spike`, then `poor-contact.spike` | Original PCB inside an actual hollow case; 25 computed frames over 120 s, explicit finite contact and case cooling | Apache-2.0, original generic geometry |
| `03-pi-si-arduino-cc-by-sa/` | `arduino-r4-relay-shield.spike` | Two public boards with explicit pin links and fresh reduced PI/SI studies; run from Coupled studies | CAD/derivatives CC BY-SA 4.0; original SPIKE glue Apache-2.0 |
| `04-circuit-and-controller/studio/` | `two_wheeler_dashboard.spksch` in Studio | Embedded C controller driving the native averaged armature circuit/mechanical feedback; throttle/brake | Apache-2.0 |
| `04-circuit-and-controller/studio/` | `02_rc_startup.cir`, `03_rl_startup.cir`, `gate_miller_ringing.cir` | Native circuit transients with voltage/current probes | Apache-2.0 |
| `05-em-machines/` | `planar_solenoid_fem.spike` | Nonlinear supplied B-H, actual stationary magnetic/eddy/thermal transient; final fields and histories | Apache-2.0 |
| `05-em-machines/` | `planar_pm_fem.spike` | Actual prescribed-current planar PM field/motion study; field quantities and angle/torque histories | Apache-2.0 |
| `05-em-machines/` | `motor.spike` | Reduced voltage-driven PM DC motor dynamics and energy ledger | Apache-2.0 |
| `05-em-machines/` | `electromagnet.spike`, `electromagnet-air.spike` | Linear reluctance comparison, supplied mu_r 2000 versus 1 | Apache-2.0 |
| `06-main-viewport-fields/` | Fields → Import field → `native-cavity.field.json` | Actual steady native CFD velocity/pressure; sample points/voxels and velocity arrows | Apache-2.0 |
| `06-main-viewport-fields/` | Fields → Import field → `channel-cht-temperature.field.json` | Actual bounded solid/fluid CHT temperatures in the main viewport | Apache-2.0 |
| `06-main-viewport-fields/` | Fields → Import field → `solenoid-potential-temperature-transient.field.json` | Exact returned nodal A_z and temperature at 0, 1 and 2 ms; scrub three saved states | Apache-2.0 |

`EVIDENCE/` contains requests, raw results, source hashes and numerical/persistence receipts. Keep it with the projects for reproducibility. `LICENSES/` contains the original SPIKE notices and EBrake ownership record. The Arduino directory carries its own notices and complete original CAD source archives; preserve that directory when sharing its derivative project.

## Native UI steps

**PCB temperatures:** File → Open the EBrake project → Thermal workspace → layered Board thermal panel. The request/results are saved. Inspect the four setup steps, rerun from Review and run, then Play or scrub the transient board frames. Main board overlay uses saved board-cell temperatures. Component junction/case table values are steady estimates, not package transient states. Board material values, loads and cooling are illustrative assumptions.

**Case as heat sink:** Open case-contact.spike → Multi-board → Assembly volume field study. The saved mesh, materials, contact, convection boundaries and transient settings are present. Choose SPIKE reference tetrahedral solver, Run transient thermal, then Play in the volume viewer. The case is a real hollow solid with heat capacity, not an ambient-colored decoration. Compare poor-contact.spike with the same power and external cooling: PCB peaks 303.413 K versus 318.876 K. The empty cavity has no solved air model. Native GIF/WebM export in the thermal volume viewer can capture genuine saved frames without slow computer-use tooling.

**PI/SI:** Open the Arduino project → Multi-board → Coupled studies → PI or SI → Run. The retained fresh results and supplied network models are bound to that assembly. Inspect voltages/currents and sampled AC response. This is a reduced-model assembly, not spatial full-board extraction or a PI/SI transient field overlay. The older thermal study in that package was preserved and is not part of this pack's fresh PI/SI execution.

**Controller/motor:** Open the .spksch through Studio File → Open so its dashboard and controller survive. Review embedded source, compile through the normal trusted-controller workflow, attach to Continuous, start the dashboard, send throttle 0.2, then brake. The project uses a native armature R/L circuit plus sampled controller and explicit mechanical/back-EMF feedback. It is not a three-phase BLDC/FOC or a controller-coupled FEM motor. Do not attach this illustrative project to hardware.

**Magnetic projects:** Open .spike → EM → Machines. For planar projects use Geometry field study → Run planar field study. Select B/H/A, temperature or loss and the retained histories as applicable. For reduced motor/electromagnet projects expand Parameter reference models. Current geometry workbench shows final field plus histories; it has no field-frame playback slider. The separate main-viewport import exposes the actual three stored A_z/temperature frames, without converting A_z into invented B vectors. Its 2 ms history is too short for visible playback at the UI's minimum speed: scrub or step it. No timestamps are stretched.

**CFD rerun:** Ctrl+K → Native CFD cavity benchmark → Domain/Conditions: Re100 → Grid & runtime:16×16 → Check / retry runtime → Review and run → Run native CFD → Show fields in main viewport. The request file is a reproducibility record; this panel does not import JSON setup. It is a steady isothermal 2D cavity, unrelated to the PCB case.

**CHT:** The channel temperature field is a native-importable result presentation, with uniform-span extrusion explicitly labeled. The exact channel solver reruns through the existing solve_laminar_channel_cht research API, not through a native setup-file importer. Do not relabel internal-airflow screening as this CHT solve. Arbitrary PCB-case CFD/CHT is not supplied.

For field imports, use a workspace with the main viewport, open Fields → Import field, select the supplied JSON, choose the quantity and point/voxel mode. Imported coordinates belong to the source analysis. They are not aligned or coupled to any unrelated board that happens to be open. Imports are session-only; retain the JSON. Full arrays remain in the files even if the display budget thins the view.

## Requested scenes that remain blocked

- **PCB spiral with and without a core:** no admitted 3D PCB spiral/core geometry model is supplied. The linear electromagnet pair is explicitly a different, reduced model. Do not caption it as a PCB inductor field extraction.
- **Human finger on a PCB touch sensor:** no geometry-resolved finger/electrode/dielectric extraction/readout workflow is ready. No fabricated finger motion/capacitance result is included.
- **Controller driving spatial motor FEM:** the dashboard motor and planar PM FEM are independent examples. No electrical/controller-to-field causal connection is asserted.
- **Transient PI/SI/EM fields over every real PCB:** circuit histories, quasi-static machine histories and thermal board frames have distinct physics. Unsupported spatial arrays are not inferred from imported artwork or interpolated from steady plots.

These gaps need actual model/solver/UI integration and verification before inclusion in a truthful promo. They are not merely recording tasks.

## Recording order

1. EBrake import/orbit and thermal run; play the 600 s history at a faster display speed.
2. Case-contact thermal run/playback; cut to the poor-contact comparison with the contact value visible.
3. Arduino PI and SI reruns; show returned values and actual graphs.
4. Studio circuit transient, then dashboard throttle/brake.
5. Solenoid and PM field solves; quantities and actual histories. Keep their independent scope visible.
6. Native cavity run and Fields inspection; separate bounded CHT field inspection.

Record continuous UI footage, edit waits, and use motion graphics as chapter titles and callouts. Keep actual units, timestamps and experimental/approximate status visible. This pack contains no video and makes no claim of completed desktop interaction.

## Verification and limits

Native packages were read back with current SPIKE APIs; saved request/result identity and board source equality were checked. The circuit/controller and field solvers were executed. Solver residual/conservation gates remain unchanged. Case volumes and capacity/energy balance were independently checked. The Arduino source hashes and source/notice inclusion were checked. Native field datasets passed the actual frontend admission function with exact scalar arrays preserved.

Parameters are illustrative and unmeasured. These executions do not establish hardware accuracy, mesh/time convergence for each promo geometry, production qualification or full application release testing. Use a current source build; an older installed application/worker may lack the relevant controls or contracts.
