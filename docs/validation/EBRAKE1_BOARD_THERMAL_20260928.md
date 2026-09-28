<!-- SPDX-License-Identifier: Apache-2.0 -->

# eBrake1 board gradient and component junction/case temperatures

This record demonstrates a new **experimental SPIKE board-plate thermal
model**. It generates a spatial temperature grid on the imported board's
axis-aligned bounding rectangle and calculates separate board contact, case,
and junction temperatures for assigned components. It is a solved grid, not
an interpolation of part temperatures. The grid is **not** a conforming PCB
thermal field: it does not contain the actual board outline, copper topology,
holes, vias, or component solids.

## Reproduce

The input is the checked-in `app/public/demo/ebrake1.kicad_pcb` with SHA-256
`d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.
The script imports the board through SPIKE's KiCad adapter and checks that
hash and the selected Q1/Q2/Q3 references. From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/run_board_thermal_example.py `
  --input examples/thermal/ebrake1_board_thermal.json `
  --result docs/validation/ebrake1-board-thermal-result.json `
  --figure docs/validation/ebrake1-board-thermal.png
```

The [input](../../examples/thermal/ebrake1_board_thermal.json),
[complete result](ebrake1-board-thermal-result.json), and
[figure](ebrake1-board-thermal.png) are saved here.

![Solved board-plate grid and Q1 Q2 Q3 case and junction temperatures](ebrake1-board-thermal.png)

The figure uses bilinear color interpolation for display. The saved JSON
contains the unchanged solved cell values; display smoothing does not refine
the numerical mesh.

## Explicit example assumptions

- Ambient 25 C; rectangular uniform effective board sheet, 1.6 mm thick,
  20 W/(m K) in-plane conductivity. These are **not** derived from the KiCad
  copper/FR-4 layout or a fabrication certificate.
- Prescribed convection on both large faces, `h = 10 W/(m2 K)` each;
  perimeter edges adiabatic. No airflow, radiation, or enclosure solution.
- Q1/Q2/Q3 dissipate 1.0/0.8/0.6 W, each into an explicit **8 mm square**
  board contact. This contact area stays physically fixed across grids.
- Every watt generated at a junction flows through its case and then the
  assigned board contact; there is no separate case-to-air path. Each part has
  `R_junction-case = 2 K/W` and `R_case-board = 3 K/W`. These resistances and
  power values are illustrative, not device specifications or PI results.
- Steady state only, constant material properties, uniform effective sheet,
  and one board-contact temperature computed as the contact-area weighted
  mean of solved cells. Case and junction temperatures add `P*R` rises.

## Numerical model and checks

For each rectangular cell, conservation is `sum Gij*(Ti-Tj) +
(h_top+h_bottom)*A*(Ti-Tambient) = Pi`. An X neighbor has conductance
`kx*t*dy/dx`, a Y neighbor `ky*t*dx/dy`; this example sets `kx=ky=k`.
Cell faces share equal and opposite conduction flow. Heat is distributed by
exact overlap of the fixed physical contact square with cells, and the overlap
weights must sum to one. The sparse linear system has positive diagonal sink
conductance and symmetric positive lateral links. The solve rejects nonfinite
inputs/results, missing component locations, contacts outside the admitted
rectangle, resource excess, linear residual above `1e-9`, or global energy
error above `1e-8*max(1 W, input power)`.

The 4 mm requested grid has 36 x 21 cells. Its saved result reports 2.4 W
input, 2.4 W outward convection, `-6.75e-14 W` energy residual, and
`2.55e-14` relative linear residual. An independent one-cell fixture checks
`T = Tambient + P/[(h_top+h_bottom)*A]`, with separate `P*R_case-board` and
`P*R_junction-case` rises. A two-cell fixture checks the analytic lateral
conduction solution; symmetric contact and invalid-input cases also pass.

| Part | Power | Board contact | Case | Junction |
| --- | ---: | ---: | ---: | ---: |
| Q1 | 1.0 W | 49.75 C | 52.75 C | 54.75 C |
| Q2 | 0.8 W | 46.61 C | 49.01 C | 50.61 C |
| Q3 | 0.6 W | 47.82 C | 49.62 C | 50.82 C |

| Grid step | Q1 junction | Q2 junction | Q3 junction | Maximum board cell |
| ---: | ---: | ---: | ---: | ---: |
| 4 mm | 54.74768 C | 50.60812 C | 50.81976 C | 50.77514 C |
| 2 mm | 54.72433 C | 50.78425 C | 50.97473 C | 50.96706 C |
| 1.5 mm | 54.74219 C | 50.91899 C | 51.06945 C | 50.99605 C |

The differences are **not yet monotone/converged** for every part. Repeat a
case with `--grid-step-mm 2` or `--grid-step-mm 1.5` and distinct output paths.
This table is a diagnostic, not an uncertainty bound. The implementation and
tests were independently derived from conservation; no external solver code
or data was adapted.

## Capability boundary

The result's `model_status` is `approximate` and
`production_qualified` is false. The physical accuracy depends on reviewed
losses, contact size/resistance, effective in-plane conductivity, board
thickness, cooling coefficients, and geometry. A passing residual proves the
discrete equations were solved, not that those assumptions describe the
fabricated eBrake board. Board outline/cutout masking, multilayer conduction,
copper spreading, package geometry, case-to-air heat transfer, temperature-
dependent properties, transient board storage, airflow, measured correlation,
and release-package review remain open. Numerical changes require
knowledgeable human review before release.
