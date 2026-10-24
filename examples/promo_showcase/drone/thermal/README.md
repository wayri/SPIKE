# IRIS drone-controller PCB thermal example

Native project: `iris-steady-thermal.spike`. Open in SPIKE, choose Thermal and inspect saved board temperature. Its exact steady request is retained for rerun. In the integrated Python workspace open `drone_thermal_gui.py` with the IRIS board selected and press Run. The template checks actual U33/U9/U15 references, calls `spike.analysis.run('run_board_thermal', ...)`, and prints the registered solver's actual output. `python-workspace-execution.json` records a real child-process Run of that exact template. No custom solver, synthetic animation or result injection is used.

Source is the unchanged `ProPrj_IRIS.kicad_pcb` from Eugene109/IRIS pinned commit `999dd2eb725d550889c1ffe2c09f8de0390d081b`. The board directly imports as native KiCad10 source. It has F.Cu/In1.Cu/In2.Cu/B.Cu and nominal1.6mm thickness, but no explicit physical copper/dielectric stackup. Source component Value properties are blank: U33 is identified only by its actual LQFP100 footprint, U9 and U15 by actual LQFP32 footprints. The pinned upstream BOM joins U33 to STM32H743VIT6 and U9/U15 to STM32F303K8T6 by exact designator; `bom-identity.json` retains source rows and BOM SHA-256. PCB Value fields remain unchanged. No electrical loss is inferred from part identity.

Explicit illustrative assumptions: U33 dissipates0.6W, U9 and U15 each0.2W (total1W); homogeneous effective PCB conductivity3W/(mK), thickness1.6mm, lateral grid3mm, top/bottom prescribed convection10W/(m²K), ambient25°C; junction-to-case2K/W and case-to-board5K/W. These are supplied teaching inputs, not measured IRIS material, operating loss or manufacturer ratings. Actual footprint pads locate the thermal contacts. This is a steady homogeneous plate model, not detailed four-layer copper spreading or whole-drone operation.

The unchanged import retains12 recoverable custom-pad diagnostics (`anchor_circle_union_pending`). They remain retained and solver-blocked for applicable electrical geometry; no missing copper was invented. The existing thermal owner admits this bounded plate calculation with the selected normal footprint contacts. See `import-design.json` for original diagnostics and geometry. No spatial CFD, rotor flow, aircraft flight, frame contact or motor heating is solved. Any STEP frame supplied elsewhere is context only.

**Transient and virtual heatsink remain blocked:** both exact requested layered-model cases and returned admission failures are retained in `blocked-transient-sink.json`. The source has no physical stackup; no stackup or saved time frame was invented. This native project therefore has no transient thermal animation or heatsink comparison.

`verification.json` records actual registered Python execution, exact native request/result/source readback, actual footprint identities, source SHA-256, layer inventory, absent stackup, and executed solver balance/residual checks. These checks are not mesh convergence, hardware correlation, whole-drone co-simulation or production qualification. Native package API opening was checked; interactive desktop operation was not performed in this subtask.

License: upstream IRIS PCB and its native derived representation retain GPL-3.0 terms; preserve the parent pack's complete pinned source, upstream license and attribution. Original SPIKE Python glue is Apache-2.0; it does not replace the PCB's upstream license. Source board unchanged; simulation requests/results are additions with assumptions above. No third-party component model binary is copied or required; native project display disables component models.

Reproduce from repository root:

```
.venv/Scripts/python.exe examples/promo_showcase/drone/thermal/build.py
```
