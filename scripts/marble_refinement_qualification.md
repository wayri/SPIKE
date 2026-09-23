<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Marble finite-volume refinement qualification (2026-09-24)

This is a bounded numerical diagnostic of the isolated
`Net-(C383-Pad1)` copper retained from the public Marble v1.4.4 board. It is
not a measured correlation, a whole-board model, or certification of board
impedance accuracy. The AC comparison uses explicit, connected U37.18/R195.1
pad terminals. The solver remains experimental/approximate.

## Reproduction identity

- Board SHA-256: `3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`
- Native CPython 3.11 module SHA-256: `2f92fe0b3fb53df8e127d82b6b650c75dc0aa2fe57c56826a3b63e3443dadafc`
- AC runner: `scripts/run_public_board_volume_ac.py` (default routed pads)
- Mesh controls: target size and zone cell size are equal; maximum 1,000 zone
  cells, 2,000 conductors, and 512 MiB solver memory.

## Results

| Mesh | Physical bases | Matrix pairs | Routed AC result | Partial L | Starting R |
| --- | ---: | ---: | --- | ---: | ---: |
| 1.0 mm | 45 | 1,035 | completed, approximate | 1.342280298 nH | 4.778865685 mOhm |
| 0.75 mm | 64 | 2,080 | completed, approximate | 1.225217320 nH | 4.377684346 mOhm |
| 0.5 mm | 120 | 7,260 | completed, approximate | 1.263706531 nH | 5.251177243 mOhm |
| 0.25 mm | 431 | 93,096 | not admitted under the 8,192-pair cap | unavailable | DC-only 4.324709769 mOhm |

The three routed AC levels are nonmonotone in both L and R; they do not
establish mesh convergence. The 0.25 mm R value is a separate DC-only audit,
not a native AC result. The 0.25 mm native matrix is outside the bounded
production work budget. Passivity at the admitted meshes is not accuracy.

The separate 0.5 mm matrix-only probe raised the pair ceiling to 8,000 and the
global potential-evaluation ceiling to 300,000,000. It also explicitly used
the production adapter's 2,000,000 potential-evaluation per-pair cap rather
than the native object's 500,000 default. The per-pair error tolerances remained
unchanged (`1e-17 H` absolute, `1e-6` relative). The matrix completed in
52.865 s of extraction (60.241 s end-to-end), consuming 72,259,138 potential
evaluations. Its minimum inductance eigenvalue was `5.354853552e-12 H`, with no
eigenvalue below the `-1e-18 H` passivity tolerance; minimum resistance
eigenvalue was `1.534761945e-4 ohm`. The maximum reported pair error estimate
was `9.112092039e-17 H`. This matrix-only success does not exercise production
AC terminals or return a path QoI. Subsequently, the production adapter's
default cap was raised, boundedly, to 8,192 pairs while retaining the 100M
global evaluation budget. The 0.5 mm explicit routed AC run completed with
the same 72,259,138 pair evaluations and no passivity projection. This does
not establish mesh convergence.

## Evidence and checks

- Machine-readable AC artifacts and logs are under
  `build/marble-volume-20260924/` and `build/marble-refinement-20260924/`.
- Matrix-only artifact:
  `build/marble-refinement-20260924/marble-matrix-probe-0.5mm.json`.
- `python -m unittest tests.python.test_marble_refinement_probe -v`: 3 passed.
- `python -m unittest tests.python.test_peec_volume_resistance -v`: 5 passed,
  including the optional retained-Marble-copper resistance/passivity check.
- Native Release tests `test_volume_matrix` and `test_annular_inductance`: 2
  passed. These focused tests do not override the board-refinement failure.

The initial global-Python attempt lacked `jsonschema`. The installed Python
3.12 native module lacked the finite-volume API; a new 3.12 binary was built
and smoke-tested from its Release path but could not replace the in-use file.
Those pre-solver environment failures are excluded from numerical timing.
