# Experimental forced-flow SST runtime

SPDX-License-Identifier: MIT  
Copyright (c) 2026 SigHarmonic

The existing multi-region OpenCFD 2606 process can now execute explicitly
requested `environment.turbulence_model` settings. Omission preserves laminar
behavior. This is original typed integration code, not a copied turbulence
implementation: the installed OpenFOAM runtime evaluates its maintained
[kOmegaSST model](https://doc.openfoam.com/2606/tools/processing/models/turbulence/ras/linear-evm/rtm/kOmegaSST/).

Required fields are `type: "kOmegaSST"`, `initial_k_m2_s2`, `inlet_k_m2_s2`,
`initial_omega_per_s`, `inlet_omega_per_s`, and `turbulent_prandtl`. No inlet
intensity or length-scale assumptions are inferred. Current admission requires
forced inlet fans in every fluid region, constant density and zero gravity.
Combining buoyancy and turbulence is not admitted by this increment.

The adapter writes k, omega, nut and alphat fields, explicit inlet/backflow
values, kqR/omega/nutk wall functions and the documented
[compressible alphat wall function](https://doc.openfoam.com/2606/tools/processing/boundary-conditions/rtm/derived/thermal/alphatWallFunction/).
RAS transport dictionaries, bounded upwind transport schemes, scalar solver
settings and yPlus observations are generated before manifest hashing.

Important limits:

- RAS disables the laminar open-flow energy diagnostic; turbulent effective
  conductivity cannot be substituted by molecular conductivity.
- Exported `heat_flux_w_m2` is explicitly labeled `molecular_conduction_only`,
  not total turbulent heat flux.
- Wall-function resolution, mesh/time independence, turbulence correlation,
  measured comparison and deployment qualification remain unestablished.
- yPlus is an observation, not an automatic pass criterion.

## Executed evidence

`build/sst-fan-smoke-20260907` contains the actual 2606 SST execution and all
input/output artifact hashes. The synthetic fixture has 64 fluid and 64 solid
cells, a 0.001 m³/s inlet, a 0.02 s horizon and 10 µs timestep. Initial/inlet
k = 0.1 m²/s², omega = 1000 s⁻¹ and Prt = 0.85 were explicit inputs.

SST execution completed, with temperatures 298.1493217–298.1575075 K. Both
transport equations executed and all retained k, omega, nut and alphat values
were positive finite. The retained constitutive ratio rho·nut/alphat agrees
with Prt to a maximum absolute error of 3.33e-10. The independent audit script
checks artifact hashes and records this algebraic identity; this is not an
independent validation of the turbulence closure itself.

Observed wall yPlus ranged from 12.7945 to 17.4217. These coarse buffer-layer
values are not evidence of wall-resolved or accurate wall-function prediction.
The matched laminar control also completed at
`build/sst-fan-laminar-control-20260907`; it reached
298.1494241–298.1575075 K. The short-horizon comparison demonstrates distinct
model execution, not improved thermal accuracy.

```powershell
python scripts/run_sst_fan_fixture.py --output build/new-sst-run
python scripts/run_sst_fan_fixture.py --output build/new-laminar-run --laminar-control
python scripts/evaluate_sst_fan_smoke.py --input build/new-sst-run --output build/new-sst-run/field-audit.json
python -W error -m unittest tests.python.test_openfoam_turbulence tests.python.test_openfoam_mesh_geometry_audit -q
```

Eleven focused tests passed, including typed parameter rejection, field units,
boundary configuration, actual prepared dictionaries and the nonorthogonal
geometry diagnostic guard. No production capability flag was enabled.
