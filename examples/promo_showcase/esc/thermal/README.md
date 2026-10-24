# VESC original-board thermal example and GUI Python template

Native-ready: `vesc-steady-thermal.spike`. File → Open in SPIKE, then Thermal → Saved thermal results / Board temperature to inspect the actual field. Thermal setup retains the exact board request; rerun the steady board model from its controls. The package was written and read through current native services with exact source, request and result equality. Interactive desktop opening was not performed by this subtask.

Python workspace: open `esc_thermal_gui.py` in SPIKE's integrated Python editor after selecting this board. Press Run. The template checks Q1–Q6 exist and calls the registered `spike.analysis.run('run_board_thermal', ...)` API with `spike.design`. It prints the actual result and summary; this template does not fabricate fields or publish a mismatched AnalysisResult overlay. `python-workspace-execution.json` records a successful real child-process `run_python_script` execution of the exact template. The owned simulation implementation is unchanged.

The original pinned board imported directly. Six actual Q1–Q6 MOSFETs carry source value IRFS7530. Source layers are F.Cu, GND, GND2 and B.Cu, nominal board thickness 1.6 mm. Its physical copper/dielectric stackup is absent. The source filename/version family and historical title are not identical: board title says BLDC Driver 4.6, despite the repository source family being described as VESC 4.12. Treat the pinned file/hash, not a product-version assumption, as the identity.

This supported model is a steady **homogeneous plate**, with explicitly illustrative effective conductivity 3 W/(m K), top and bottom convection each 10 W/(m² K), ambient 25°C, lateral grid 3 mm, and six constant 0.5 W MOSFET powers (3 W total). Package junction-to-case 1 K/W and case-to-board 2 K/W are illustrative values, not manufacturer ratings. Actual spatial PCB layout locates pad contacts; detailed four-layer copper spreading, switching loss, motor currents, enclosure, airflow, temperature-dependent losses and package thermal storage are not solved. Peak plate temperature is approximately 137.62°C under these assumed inputs; this is not a characterized VESC operating temperature or a safe operating point.

**Blocked:** requested spatial transient and virtual heatsink variants both fail the existing layered-model admission because the source has no explicit physical stackup. Exact requests and returned blocked evidence are in `blocked-transient-sink.json`. No physical stackup, frame, sink result or source edit was invented. Thus this native ESC project has **no transient animation and no virtual sink comparison**. Existing original synthetic/EBrake projects elsewhere in the pack provide genuine transient examples.

Checks: actual registered Python child execution completed; native save/read retained exact source/request/result; all six source refs/values verified; total power 3 W, outward heat 3 W within 3.5e-14 W, relative linear residual 3.6e-14. These are bounded numerical checks, not mesh refinement, hardware correlation, full-suite validation or production qualification. `verification.json` retains exact source SHA-256, layer inventory, missing-stackup evidence and executed summary.

Attribution: the retained board is derived from Benjamin Vedder's pinned upstream hardware source. Source board/native derivative remain CC BY-SA 4.0; see parent source provenance and license files. Original SPIKE Python glue is Apache-2.0; that does not replace the upstream hardware license. No third-party model binaries are copied or required for this thermal example; native project display disables component models.

Reproduce from repository root:

```
.venv/Scripts/python.exe examples/promo_showcase/esc/thermal/build.py
```
