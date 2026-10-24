# Separate motor field reference

This chapter reruns the original SPIKE `examples/em_machines/planar_pm_fem.json` fixture unchanged. It is an actual **prescribed-current synthetic planar FEM reference**, deliberately separate from the physical propulsion-pod assembly, electrical bus starter and controller. No rotor, winding, magnet, controller or load identity is mapped to the pod.

Open `prescribed-current-planar-reference.spike` in SPIKE, then **EM > Machines > Geometry field study**. The real native project retains the exact request and freshly executed final field/motion result. Inspect returned B/H/A, initial summary, final-position field and motion/torque histories. **Run planar field study** repeats the existing desktop-worker route. The matching `request.json` can instead be pasted into Advanced request JSON. No PCB is required. Browser preview cannot execute the desktop worker.

The current UI displays the final field and motion-history curves; it does **not** provide field-frame playback. Actual per-position field frames are retained separately in the raw output for inspection or future supported playback integration. No UI session/recording or playback control was added here.

## What actually ran

The unchanged original fixture uses generated PM rotor/stator geometry, 2 mm mesh edge, 20 mm extrusion depth, supplied steel relative permeability 1000, supplied 1 T remanence, 1e6 A/m² winding current density and initial angle 0.2 rad. It runs two 1 ms steps of bounded quasi-static motion with a fresh magnetostatic solve at each accepted position.

| Time | Actual accepted rotor angle | Actual returned torque |
| --- | --- | --- |
| 0 ms | 0.2000000000 rad | -0.0469412494 N·m |
| 1 ms | 0.1999531056 rad | -0.0469428443 N·m |
| 2 ms | 0.1998593622 rad | -0.0469460366 N·m |

All three actual field solves converged; each has 6777 nodes and 13310 triangles. The final captured field matches the native result exactly. Native package readback and its real frontend-state projection preserve the exact request and JSON-canonical result. No torque-accuracy or physical-pod validation is inferred from convergence: the established machine documentation explicitly leaves mesh-accuracy qualification open.

The source fixture holds winding current density fixed. It does not solve voltage-driven windings, ESC/commutation, back-EMF drive feedback, moving-conductor eddy loss, sliding interfaces, 3D end fields, core hysteresis/loss, thermal feedback or a propeller/thrust load. Geometry/material numbers are synthetic demonstration inputs, not characterized hardware.

## Raw evidence and rerun

From repository root:

```powershell
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/electrical/motor_reference/run_reference.py
```

Outputs are under `output/promo-propulsion-pod-20261023/electrical/motor_reference/`:

- `request.json`: exact executed request, also supplied beside this README.
- `result.json`: actual established machine-study output, including the final spatial field and accepted motion histories.
- `actual-field-history.json`: each actual magnetostatic input mesh/material/boundary request, unchanged solved field, accepted time/position/velocity and corresponding torque.
- `verification.json`: frame convergence/counts, final-field equality and native project/frontend readback checks.

The observation-only wrapper calls the existing magnetostatic solver exactly once per accepted position, retains its input/output and returns the result unchanged. It temporarily observes the module in that process and restores it in `finally`; no solver implementation or physics was modified. The native project stores the established supported final-field result; the separate frame sidecar is not passed off as existing UI playback support.

Firstparty Apache-2.0 example/glue, covered by the electrical parent LICENSE. `source-provenance.json` hashes the exact original fixture, solver/geometry/package sources, this runner and native project. No third-party code or CAD is copied. Primary local scope references: `docs/MAGNETIC_MACHINE_STUDIES.md` and `docs/MAGNETIC_FEM.md`.
