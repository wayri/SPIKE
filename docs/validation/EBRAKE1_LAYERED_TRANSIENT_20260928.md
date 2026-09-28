<!-- SPDX-License-Identifier: Apache-2.0 -->

# eBrake1 layered board transient diagnostic (2026-09-28)

The [input](../../examples/thermal/ebrake1_layered_transient.json) extends the
approximate [layered eBrake1 case](EBRAKE1_LAYERED_THERMAL_20260928.md) with
constant Q1/Q2/Q3 power totaling 2.4 W, an initially ambient 25 °C board,
assumed copper and dielectric volumetric heat capacities of 3.45 and 1.4
MJ/(m³·K), a 600 s duration, and 20 s implicit time steps. These material and
cooling inputs are illustrative; eBrake1 is a bundled development fixture, not
a measured thermal reference.

The [saved result](ebrake1-layered-transient-result.json), [final frame](ebrake1-layered-transient-final.png),
and [seven-frame animation](ebrake1-layered-transient.gif) retain the actual
solved layer temperatures. The animation keeps one color scale across frames.

![Transient layered board temperature animation](ebrake1-layered-transient.gif)

| Time | Maximum board cell |
| ---: | ---: |
| 0 s | 25.000 °C |
| 100 s | 42.920 °C |
| 200 s | 46.738 °C |
| 300 s | 48.253 °C |
| 400 s | 48.909 °C |
| 500 s | 49.204 °C |
| 600 s | 49.341 °C |

The separately solved steady peak is 49.460 °C. The final stored heat above
ambient is 292.313 J. The maximum discrete energy-balance error across the
time steps is 1.64e-13 W; the maximum linear relative residual is 1.38e-13.
These checks establish numerical consistency for the stated discrete system,
not physical accuracy of the assumed board properties.

## Method and time-step sensitivity

Each physical stackup row has its own sampled copper fraction and cell heat
capacity. The solver uses backward Euler on `C dT/dt + A(T - Tambient) = P`,
where `A` is the same lateral, vertical, convection, and optional virtual-sink
conductance network as the steady layered solve. It factors `A + C/dt` once
for constant inputs. Heat storage is calculated from the temperature change
and checked against applied power minus outward heat at every step. The
initial state is ambient throughout; supplied power is constant in time.

With the same 3 mm X/Y grid (48 × 28 × 7 rows), saving every 100 s:

| Time step | Peak at 100 s | Peak at 600 s | Stored heat at 600 s |
| ---: | ---: | ---: | ---: |
| 20 s | 42.920 °C | 49.341 °C | 292.313 J |
| 10 s | 43.228 °C | 49.360 °C | 292.830 J |
| 5 s | 43.389 °C | 49.368 °C | 293.075 J |

The 20-to-5 s difference at 600 s is 0.028 °C in this case; early-time
differences are larger. This is a time-step check only. The existing steady
[grid-refinement record](EBRAKE1_LAYERED_THERMAL_20260928.md) is incomplete,
and no transient spatial-refinement or measured-board correlation is claimed.

## Reproduce

From the repository root with the project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts/run_board_thermal_example.py `
  --input examples/thermal/ebrake1_layered_transient.json `
  --result build/ebrake1-transient.json `
  --figure build/ebrake1-transient-final.png `
  --animation build/ebrake1-transient.gif
```

Repeat with `--time-step-s 10 --output-stride 10` and then
`--time-step-s 5 --output-stride 20`, using distinct output paths. The input
source-board hash is checked by the runner. The result remains
`model_status: approximate`, with `production_qualified: false`. Part case and
junction temperatures in the layered result are steady resistance-chain
estimates; this board-field transient does not solve a 3D package or its
transient junction temperature. Knowledgeable human review of numerical code
is required before release.
