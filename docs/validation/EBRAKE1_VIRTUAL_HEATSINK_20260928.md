<!-- SPDX-License-Identifier: Apache-2.0 -->

# eBrake1 virtual board heatsink diagnostic (2026-09-28)

This record adds one **mathematical** heatsink to the approximate layered
eBrake1 board case. The pinned [input](../../examples/thermal/ebrake1_layered_virtual_heatsink.json)
uses the same board, Q1/Q2/Q3 hypothetical losses, material values, and
convection as the [no-sink baseline](EBRAKE1_LAYERED_THERMAL_20260928.md).
`HS-Q1` is a 16 × 16 mm rectangle on the top face, centered at KiCad
(95.01, 105.025) mm, with 1 K/W interface and 8 K/W sink-to-ambient
resistance. These values are illustrative, not derived from a fin model,
datasheet, or measurement.

The [1.5 mm result JSON](ebrake1-layered-virtual-heatsink-result.json) and
[temperature/coverage figure](ebrake1-layered-virtual-heatsink.png) are retained:

![Board result with dashed virtual heatsink footprint](ebrake1-layered-virtual-heatsink.png)

| Quantity | Baseline, no sink | With virtual sink |
| --- | ---: | ---: |
| Q1 junction | 54.03 °C | 41.12 °C |
| Q2 junction | 51.88 °C | 47.53 °C |
| Q3 junction | 50.67 °C | 45.37 °C |
| Maximum board cell | 50.06 °C | 44.52 °C |
| Convection outward | 2.40 W | 1.50049 W |
| Virtual sink outward | 0 W | 0.89951 W |
| Total outward | 2.40 W | 2.400000000001266 W |

## Numerical method and independent oracle

Each overlapping surface cell connects to a shared isothermal sink node. If
contact area `A_i` overlaps a cell and `w_i = A_i/A_contact`, its series
resistance to that node is

```text
R_cell_to_sink_i = layer_thickness/(2 × k_i × A_i) + R_interface/w_i
G_cell_to_sink_i = 1/R_cell_to_sink_i
G_sink_to_ambient = 1/R_sink_to_ambient
```

Thickness is m, conductivity W/(m·K), area m², and every resistance is K/W.
Contact overlap weights sum to one; the sink-to-ambient conductance is stamped
**once** at the shared node. This avoids creating an independent full
sink-to-ambient path in every cell. Equal-and-opposite cell/sink heat terms
preserve conservation. The top/bottom convection and sink paths are both
included in `outward_heat_w`.

The [one-column regression](../../tests/python/test_layered_board_thermal.py)
provides a separate resistance-network oracle: top-to-bottom plus bottom-air
is 1009.5 K/W, while top-center to sink to air is 12.5 K/W under that test's
material and dimensions. For 0.1 W, the top rise is
`0.1 / (1/1009.5 + 1/12.5)` K. The solver matches the top, sink, and outward
heat terms within `1e-9` in this bounded oracle. Zero sink-to-ambient
resistance, outside-board footprints, and use with the 2D plate are rejected.

Positive conductivity, finite contact area, positive sink-to-ambient
resistance, and at least one positive convection coefficient keep the conductance
system physically anchored. Copper/dielectric contrast and very small
resistances can still make the sparse system poorly scaled; the solver checks
finite temperatures, relative linear residual `≤ 1e-9`, and global heat
balance `≤ 1e-8 × max(1 W, input power)` rather than silently accepting a
numerical failure.

## Grid sensitivity

Three requested X/Y steps with the same physical sink footprint and inputs
give:

| Step | X/Y cells × depth rows | Q1 junction | Q2 junction | Q3 junction | Sink heat |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 3.0 mm | 48 × 28 × 7 | 41.17 °C | 46.90 °C | 44.61 °C | 0.90089 W |
| 1.5 mm | 96 × 56 × 7 | 41.12 °C | 47.53 °C | 45.37 °C | 0.89951 W |
| 1.25 mm | 116 × 67 × 7 | 41.51 °C | 47.48 °C | 45.64 °C | 0.89913 W |

The heat split is relatively stable in these runs, but Q1/Q3 temperatures
are **not converged**. These differences are neither error bars nor a
fabricated-board correlation. The model still uses a bounding rectangle, one
depth cell per stackup row, sampled copper, and no resolved package or sink
body. Fins, airflow, radiation, mechanical pressure, and interface-area
nonuniformity are absent. The result remains `model_status: approximate` and
`provenance.production_qualified: false`.

## Reproduce

From the repository root with the project's Python environment:

```powershell
.\.venv\Scripts\python.exe scripts/run_board_thermal_example.py `
  --input examples/thermal/ebrake1_layered_virtual_heatsink.json `
  --result build/ebrake1-virtual-heatsink-1p5.json `
  --figure build/ebrake1-virtual-heatsink-1p5.png
```

Repeat with `--grid-step-mm 3` and `--grid-step-mm 1.25`, using distinct
result/figure paths. The source board hash is checked by the script. The
derivation, code, and oracle were written for SPIKE without adapting another
solver's implementation. Knowledgeable human review of this numerical change
is required before release.
