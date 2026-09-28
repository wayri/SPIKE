<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Enclosure runtime and qualification increment

This increment extends the optional OpenFOAM 2606 process adapter. It is not
native SPIKES qualification or an arbitrary-enclosure production approval.

## Startup conservation

The energy auditor can now include time zero through
`include_startup=True, startup_baseline=<report.json>`. The baseline is obtained
by the installed solver's time-zero postprocessing in a new input-only clone.
Input, command and diagnostic hashes are checked; no enthalpy reference is
guessed to make a result pass.

The original constant-density case with pressure-time work enabled fails the
first-step criterion: 0.00610493 relative defect against the unchanged 0.001
limit. Four and sixteen outer correctors give effectively the same failure.
About 99.3% of that first-step discrepancy comes from the pressure-storage
contribution. This is consistent with pressure/energy startup coupling, not
proof of an independently corrected pressure equation.

An explicit new `environment.dpdt_enabled=false` selects the separate
`constant_density_no_dpdt` thermal model. It is admitted only for a
constant-density fluid at zero gravity, without a buoyancy density model.
Omission preserves existing behavior. This is a model choice, not an invisible
postprocessing correction or a relaxed tolerance.

Actual normal-API runs over 0–0.05 s passed the same startup-inclusive energy
checks: first-step relative defects 7.27e-10 and 6.30e-10 for four/sixteen
correctors. See `build/fan-startup-no-dpdt-normal-api-20260907/report.json`.
Original failures remain at
`build/fan-startup-corrector-probe-20260907/report.json`.

```powershell
python scripts/probe_fan_startup_correctors.py --output build/new-startup-no-dpdt --dpdt-disabled
```

## Non-cuboidal geometry

The mesh audit computes volume/face centroids, convex-cell validity, face
planarity and internal/boundary nonorthogonality for bounded linear tetrahedra
and planar-faced convex hexahedra. It does not prove global intersection
freedom or construct arbitrary CAD automatically.

A 26.565-degree sheared two-region duct executed through 1 s with 64 fluid
and 64 solid cells. Temperatures were 298.1501136–298.5253188 K. Evidence:
`build/skew-fan-executed-20260907/`. The prior unconditional orthogonal-energy
assumption is removed: this skewed case explicitly disables that diagnostic.
Conservative nonorthogonal open-boundary energy flux remains unqualified.

## Buoyancy and turbulence

Fluid materials may explicitly request `density_model.type="Boussinesq"`
with rho0, T0, beta and a valid temperature interval. Density departure is
limited to 10% over that interval. This uses OpenFOAM's variable-density CHT
equations; it is not advertised as the classical incompressible Boussinesq
system. Initial/boundary temperatures and every-step runtime temperature/
density observations are admitted before field results are accepted.

Three dynamic controls compare isothermal gravity, heated zero gravity and
heated gravity. The failed initial 0.1 s contrast test is retained. At 1 s,
the heated-gravity speed was 2.40844e-4 m/s versus 1.73735e-5 m/s without
gravity (13.86 ratio). Zero-gravity expansion is physical in the chosen
variable-density equations; it must not be artificially frozen. The first
1 s run records concurrent source changes and is not source-stable release
evidence. The subsequent repeat at
`build/buoyancy-controls-stable-final-20260907/report.json` completed all three
cases with unchanged source hashes and the same 13.862788 ratio, passing the
predeclared 10x functional contrast. Each of its 1,000 timesteps passed
temperature/density-envelope checks. This is functional model evidence,
not mesh-converged or experimental accuracy qualification.

[Forced-flow SST implementation and executed controls](SST_RUNTIME_INCREMENT.md)
add explicit k/omega/Prt settings and yPlus observations. The tested wall
resolution is not accuracy-qualified. Combined buoyancy/turbulence is not yet
admitted. RAS disables the laminar energy audit; exported heat flux is labeled
molecular conduction only, not total turbulent heat flux.

## Public measured evidence

[The public reference corpus](CFD_PUBLIC_REFERENCE_CORPUS.md) records an
admitted NASA measured Cf dataset and the selected Utah State heated-plenum
reference. A digest-checked comparator is implemented. No synthetic duct
result is compared against a different experimental geometry or presented
as measured correlation. Matching case reconstruction and solver prediction
remain to be completed.

## Remaining before general enclosure deployment

The final focused suite passed 82 Python tests with warnings treated as errors;
the architecture guard also passed. New implementation files use MIT/SigHarmonic
notices. Existing user edits and prior failed evidence were preserved.

- Arbitrary CAD-to-fluid/solid material partitions and obstructed enclosure
  mesh/time convergence, not just a sheared-duct smoke test.
- Conservative nonorthogonal and turbulent energy-flux accounting.
- Pressure-work-enabled startup closure and combined buoyancy/turbulence
  qualification.
- Resolved wall treatment, independent numerical benchmarks and actual
  matched experimental predictions with uncertainty.
- Clean-machine/native-platform and release qualification.
