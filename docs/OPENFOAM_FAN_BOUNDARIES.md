<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Prescribed-volume fan boundary preparation

Follow-up: [executed conservation, refinement and multiboard evidence](FAN_CHT_QUALIFICATION.md)
supersedes the earlier pending-validation checkpoint below for its stated scope.

The existing multi-region OpenFOAM preparation route now emits a physically
compatible inlet/outlet boundary set for prescribed-volume inflow. Previously
fan inflow existed but all other velocity patches were no-slip walls and the
inlet temperature was unspecified (zero gradient).

The heated-duct example now executes, but is **not production CFD qualification**. The focused tests
use clearly synthetic polyMesh stubs to inspect dictionaries. Those stubs are
not valid numerical meshes and must never be offered as engineering evidence.

A separate real-topology fixture is now provided by
`openfoam_fan_fixture.build_fan_heated_fixture(output_root, divisions=4)`.
It generates two hexahedral polyMesh regions (64 cells each), a mapped thermal
interface, a 0.1 W board cell-zone source and Q=1e-5 m3/s air inflow at 298.15 K.
All other exterior walls are adiabatic. It is a synthetic heated duct, not a
general enclosure CAD model. The original preparation is preserved at
`build/fan-heated-fixture-20260906T225626/case`. Preparation metadata deliberately
keeps `executed_cfd=false`; execution evidence is a separate record. For a steady
run, a rough expected bulk outlet rise is P/(rho Q cp) = 8.2836 K only if
negligible inlet conduction and net kinetic/mechanical energy effects are
demonstrated; it is not an exact temperature acceptance target.

Runtime checkpoint: the sandboxed discovery initially returned unavailable.
An escalated read-only probe subsequently found Ubuntu/WSL and returned
OpenFOAM API version `2606`. The owner subsequently authorized this optional
Linux/WSL worker. The discovery failure was access denial, not missing software.

## Actual execution checkpoint

The fresh case `build/fan-heated-pressure-boundaries-20260907/case` completed
10,000 steps to 10 s using OpenFOAM 2606 in Ubuntu/WSL. Both regions passed
`checkMesh -allRegions -allTopology -allGeometry`, and all six field-export
commands succeeded. The 128 imported cell temperatures range from 298.1505234
to 301.8409191 K. Execution plus export took 158.391 s. The source hashes were
unchanged throughout. Full bounded command logs and the structured result are
in `build/fan-cht-run-20260906T184848.827020Z/report.json` and its adjacent logs.
Independent snapshot checks in `scripts/verify_fan_cht_fields.py` passed at
10 s: inlet -1.2e-5 kg/s, exhaust 1.19999999995e-5 kg/s, relative mismatch
4.17e-11, and expected flow direction on every inlet/outlet face. Hashed field
evidence is `build/fan-field-verification-20260907.json`. Temperature and speed
bounds are sanity checks, not analytical or measured correlation.

Two failed runs are preserved: zero-valued initial pressure boundaries created
a spurious atmospheric pressure jump and rapid divergence. Correcting only the
internal pressure did not resolve it; both internal and boundary p_rgh values
must start consistently. The renderer and regression assertions now cover
this zero-gravity atmospheric fixture. Nonzero-gravity hydrostatic startup is
not qualified by this test. All 37 related unit tests and architecture checks
passed after the correction.

Reproduce the bounded execution with:

```powershell
python scripts/run_fan_cht_example.py build/fan-heated-pressure-boundaries-20260907/case
```

Prefer preparing a new empty fixture directory before subsequent runs so prior
evidence remains intact. This is transient laminar constant-density CHT, not
steady-state qualification: integrated advected enthalpy, inlet conduction,
storage balance, mesh/time convergence and independent correlation remain open.

In an existing `spike/openfoam-multiregion-request/v1`, set enclosure to `open`
or `vented_cabinet`, supply positive `fans[].flow_rate_m3_s`, and give each fan
an exactly owned `boundary_patch` (`fan:<id>`). Optional `inlet_temperature_k`
defaults to ambient temperature. Add to `environment`:

```json
"pressure_outlets": [{
  "fluid_region_id": "air",
  "boundary_patch": "exhaust",
  "static_pressure_pa": 101325,
  "backflow_temperature_k": 298.15
}]
```

The exhaust ownership is `external:pressure_outlet`. Each fan-driven region
needs at least one outlet; mass conservation determines exhaust flux rather
than specifying an incompatible second velocity. Static pressure is absolute
Pa, converted to hydrostatic-reduced pressure by `prghPressure`. Temperature
uses specified inlet conditions and a backflow value at the outlet.

| Boundary | U | p_rgh | T |
| --- | --- | --- | --- |
| Fan inlet | flowRateInletVelocity | fixedFluxPressure | fixedValue |
| Pressure outlet | pressureInletOutletVelocity | prghPressure | inletOutlet |
| Ordinary impermeable wall | noSlip | fixedFluxPressure | existing thermal condition |

Prescribed fans in sealed enclosures, orphan/duplicate fan ownership, missing
outlets, invalid pressures/temperatures and unsupported fan properties are
rejected. This does not implement internal fan pressure jumps, operating-point
curves, rotors or turbulence. The current fluid thermodynamics are constant
density: do not interpret nonzero gravity as thermal buoyancy support.

The exporter accepts materialized OpenFOAM polyMesh topology rather than being
restricted to cuboids, but a geometry generator, patch/interface correctness,
mesh quality checks and a working engine still need to supply verified inputs.
Actual runtime qualification needs OpenCFD v2606, checkMesh and a real heated
vented-enclosure mesh; inspect mass flux, energy including advected enthalpy,
time-step/mesh convergence and independent correlation. The existing wall-flux
thermal checks alone cannot qualify open-flow energy conservation.

Boundary semantics are checked against official OpenFOAM documentation:
[v2606 inletOutlet](https://api.openfoam.com/2606/classFoam_1_1inletOutletFvPatchField.html),
[flowRateInletVelocity](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/derived/inlet/flowRateInletVelocity/),
[prghPressure](https://api.openfoam.com/2506/classFoam_1_1prghPressureFvPatchScalarField.html),
[pressureInletOutletVelocity](https://api.openfoam.com/2412/classFoam_1_1pressureInletOutletVelocityFvPatchVectorField.html).
The v2606 class pages for the latter conditions returned HTTP 403 during this
audit; compatibility of the emitted boundary subset has now been exercised by
the actual 10-second run, not inferred from a URL.
