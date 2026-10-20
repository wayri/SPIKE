# Internal CFD and cross-solver transfer examples

These examples run the experimental native steady cavity/solid CHT problem.
They are not imported enclosure/aircraft models. The liquid-like and air-like
properties are illustrative constant inputs, not certified material records.

Build from the repository root (omit the generator on other platforms):

```powershell
python scripts/build_native_airflow.py --build-dir build/native-cht-20261020 --generator "Visual Studio 18 2026"
$env:SPIKE_NATIVE_CHT_EXECUTABLE=(Resolve-Path build/native-cht-20261020/Release/spike_native_cht.exe).Path
python scripts/run_cfd.py --engine native-cht --request examples/internal_cfd/native-cht-conduction.json --output build/cht-conduction.json
python examples/internal_cfd/run_examples.py --output build/internal-cfd-examples-NEW
```

The batch requires a new output folder and preserves every request/result plus
a source/binary-bound `report.json`. Six real CHT runs cover conduction, two
different supplied material/flow sets, and moving-flow 8/16/32 refinement.
Eleven checks cover execution, the independent series-resistance heat rate,
decreasing successive heat changes and conservative split-patch handoffs.
Heat-transfer refinement is not a measured accuracy estimate.

Inputs select SI density, viscosity, heat capacity, fluid/solid conductivity,
length, span, lid speed and boundary temperatures. A stationary fluid has
actual Reynolds zero; a reference speed is used only for nondimensional units.
Moving cases require Reynolds 1..400, reference Peclet <=5000, and solid/fluid
conductivity ratio .01..1e5. Extreme admissible ratios may fail the iteration
cap. Software limits do not validate the entire envelope. Only a square fluid
with two quarter-height solid strips is implemented; no turbulence or buoyancy.

In each accepted result:

- `fields.thermal` contains physical cell coordinates, region IDs and K.
- `fields.fluid` contains velocity in m/s and **gauge** pressure in Pa.
- `interfaces.bottom/top` contain continuous interface temperature, explicit
  face area and conductive heat flux positive in the global +y direction.
- `diagnostics` contains raw heat balance in W, interface heat flow, flow and
  thermal residuals and an independently recomputed local energy residual.
- `provenance` binds the actual executable, normalized request and raw result.

The batch maps the hot-solid interface to an explicitly split destination
surface. The source outward normal is +y; the destination outward normal is
-y. Destination outward heat is therefore negative when heat enters it.
`*.exchange.request.json` binds the supplied rectangular partition and
`*.exchange.result.json` reports its integrated W and adjoint diagnostic.
This second interface **does not execute another thermal PDE solver**.

Replay a generated exchange through the same public service/CLI:

```powershell
python scripts/run_cfd.py --engine surface-exchange --request build/internal-cfd-examples-NEW/native-cht-air-like.exchange.request.json --output build/surface-handoff.json
python -m unittest tests.python.test_native_cht tests.python.test_internal_cfd_contracts tests.python.test_coupled_surface_exchange -v
```

The worker methods are `run_native_cht` and `run_coupled_surface_exchange`,
each accepting exactly `{"request": {...}}`. No executable, shell command or
runtime directory is accepted in worker JSON. Trusted host environment config
selects the native binary. The CLI has a 64 KiB request limit; the direct surface
API has its separately bounded 8 MiB control limit. Native execution reuses the
OS process supervisor with a timeout, 512 MiB memory and 8 MiB per-stream limits.
Failure/timeout/cancellation never installs partial accepted fields.

Native CHT is not automatically included in an existing installed/frozen
application. Runtime discovery reports unavailable until its executable is
built or explicitly provided. New UI/installer qualification is separate.

See [native method and evidence](../../docs/validation/NATIVE_CHT_METHOD_20261020.md),
[surface exchange](../../docs/COUPLED_SURFACE_EXCHANGE.md), and the
[enclosure/aerodynamics/rotor/FSI stages](../../docs/INTERNAL_CFD_AND_FSI_PLAN.md).
