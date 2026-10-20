<!-- SPDX-License-Identifier: Apache-2.0 -->
# Guided 3-D enclosure CHT numerical examples

These independently authored numerical fixtures are generated from checked-in
Python source, not downloaded boards or measured enclosures. They demonstrate
the [experimental scope](../../docs/ENCLOSURE_CHT_3D.md), not engineering sign-off.

## 1. Generate, solve and retain the reference cases

From the repository root, select a fresh output directory:

```powershell
.venv-emerge3\Scripts\python.exe scripts\benchmark_enclosure_cht.py `
  --output build\my-enclosure-verification
```

The runner refuses to overwrite an existing directory. It actually solves each
case, checks independently derived expected quantities, and writes request,
result and SHA-256/source-bound `receipt.json` only after acceptance. An assertion
failure is a failed verification, not an accepted partial result.

## 2. Inspect solid/fluid conduction and refine a selected region

Open `layered-coarse.request.json`: six x-cells hold a left solid, four fluid
cells and a right solid, with conductivities 2, 0.5 and 4 W/m/K. End temperatures
are 310 and 300 K; transverse faces are adiabatic; flow is zero.
The analytical series resistance predicts heat `0.457142857142857 W` through
the 0.04 m2 cross-section. Both solid/fluid interface temperatures must agree
from the left and right, not just give a small global residual.

Compare `layered-refined.request.json`. Its user-selected bounds and split factor
insert thermal cuts near the chosen region, while retaining the original coarse
flow grid. Inspect `grid.axes_m`, `grid.shape` and
`grid.momentum_locally_refined=false` in the result. Cuts propagate complete
tensor planes; this example must not be interpreted as local momentum AMR.

## 3. Solve an exported request through the actual process interface

```powershell
.venv-emerge3\Scripts\python.exe scripts\run_cfd.py --engine enclosure-cht `
  --request build\my-enclosure-verification\source-flux.request.json `
  --output build\my-enclosure-verification\source-flux-process.json
```

The supplied solid heater generates 0.4 W while creeping 3-D circulation
transports heat in surrounding fluid. Inspect the wrapped `result.status`,
`energy_diagnostics.generated_heat_w`, six signed `outward_heat_w` entries,
`raw_energy_balance_w`, and `transfer_diagnostics.maximum_fine_divergence_s_inv`.
Do not count opposite-sign interface fluxes twice as exterior heat.

## 4. Check accuracy, not only successful execution

- `inertial-mms-{4,8,12}` solve a fully three-component manufactured inertial
  flow with independent pressure and continuous forcing. These are momentum
  contracts, not CHT CLI inputs; the runner executes the separate laminar API.
- `thermal-spatial-mms-{4,8,12}` compare against a smooth continuous 3-D sine
  temperature, so observed conduction error/order is measurable rather than
  identically zero as in the piecewise-linear layered case.
- `transient-be-{8,16,32}` compare a convectively cooling cell against its
  independent exponential solution. Inspect temperature error and observed
  first-order time convergence in the receipt, plus actual storage/heat history.
- `coupled-advection-mms-{4,8,12}` use a non-tangent temperature with nonzero
  analytical advective transport. The retained earlier tangent diagnostic did
  not pass its order gate; it is not relabelled as qualified.
- `embedded-inertial-solid-source` puts a moving inertial rectangular fluid
  region inside conducting walls with a 2.5 W solid heater and selected thermal
  cuts. Inspect nonlinear iterations, actual nonzero velocities, interface
  temperature continuity and heat balance together. This is not obstacle inertia.

All temperatures are absolute K; material/source/force arrays are indexed
`[x][y][z]`. These constant-property fixtures do not validate real air/water,
fan-driven enclosures, turbulence, propellers, buoyancy, radiation, general
obstacle inertia, or physical measurement correlation. Never replace missing
geometry or material data with these reference properties in a real study.
