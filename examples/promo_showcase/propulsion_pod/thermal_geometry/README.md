# Original single-motor stand and imposed-loss thermal starter

All authored geometry, scripts and example outputs in this subpack are original SPIKE material, Apache-2.0; see included LICENSE. No manufacturer motor CAD, propeller data or third-party geometry is copied. The existing admitted OCC/Gmsh authoring runtime is used; its binaries are not redistributed.

## Geometry and assembly coordinates

STEP units are millimetres. Coordinates are already assembly-located; do not scale them.

- `original-pod-stand.step`: one fused nominal solid. Base120×100×6mm, x±60,y±50,z0..6. Two3mm side walls atx−60..−57 and57..60; back wall y47..50; walls rise z6..90, leaving front(y−50) and top open. A20×20×30mm pedestal atx/y±10,z6..36 supports the motor envelope.
- `original-motor-case-envelope.step`: one40×40×30mm box atx/y±20,z36..66. This is an illustrative **thermal/mechanical motor-case envelope**, not the stator, rotor, windings, magnet or measured housing of a real motor.
- `original-single-motor-stand-assembly.step`: stand, motor-case envelope and separate nominal shaft cylinder. Shaft starts(20,0,51), points+x, length20mm, radius3mm. No propeller is included. Three closed solids survive STEP reimport with the expected total volume.

These are conceptual geometry inputs for a restrained single-motor station. No bolt, clamp, guard impact strength, shaft restraint, vibration, stress or fastener capacity is calculated. The open-front/top U-shaped surround is geometry, not a rated protective enclosure or aerodynamic chamber. Any VESC board integrated by the parent project is an additional assembly object, not automatically coupled to these thermal bodies.

## Actual supported thermal project

`pod-supplied-5w.spike` is a separate native two-body thermal study. Open in SPIKE, choose Assembly volume field study and Transient solid thermal. The retained `.fieldstudy.json` also imports through Open volume study in a saved project. Playback uses25 real saved temperature frames spanning0..120s; solver time step2s and saved output interval5s. Native package API save/read must report current with saved result; see verification.json. Interactive desktop recording was not performed here.

The exact original rectilinear stand/envelope volumes are meshed with tetrahedra and coupled over the actual20×20mm pedestal/case interface. Explicit illustrative constants for both bodies: conductivity150W/(mK), density2700kg/m³, cp900J/(kgK). These are supplied teaching values, not characterized motor or stand properties. Contact conductance500W/(m²K) over400mm² corresponds to5K/W. All other thermal faces use prescribed convection10W/(m²K) to298.15K ambient; initial temperature298.15K. The separate shaft is display-only and excluded from thermal mesh/capacity. Empty chamber air has no mesh or flow/energy participant.

A constant **supplied5W total** heat load is uniformly deposited in the motor-case envelope. It is not calculated from VESC current, commutation, winding resistance, torque, controller duty or core loss. Native execution uses the established `run_assembly_field_transient` owner; no solver/app code or constitutive law is added. No propeller CFD, thrust, torque-speed map, motor electromagnetic model, controller-to-thermal feedback or whole propulsion-system co-simulation is implied. No temperature-dependent properties, radiation, phase change or airflow is solved.

## Checks and reproducibility

`geometry-verification.json` checks analytic rectangular stand volume, motor-envelope volume,3 closed assembly solids, and STEP reimport total volume. `verification.json` retains physical-time frame count, native study readback, actual temperature ranges and source hash. It also independently integrates tetrahedral volume and volumetric capacity to compare input600J minus reported convection energy with stored energy, alongside the unchanged solver energy gate. No spatial/time refinement, mechanical load qualification, motor characterization or hardware correlation is performed. Mesh source hashes remain caller declarations: original STEP and mesh share nominal authored dimensions, without an independent automatic CAD/mesh authentication claim.

Reproduce from repository root:

```
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/thermal_geometry/build.py
```

This requires the same admitted local OCC/Gmsh runtime used by the existing original thermal examples. Capability boundaries remain those of `docs/SOLVER_STATUS.md` and `docs/PROPULSION_MACHINES_FLUID_POWER_PLAN.md`. The starter is not production qualification or evidence of actual thrust.
