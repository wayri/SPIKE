<!-- SPDX-License-Identifier: MIT -->

# SPIKE PI reference board and examples

This is an original synthetic KiCad board generated for SPIKE's PI examples.
Copyright (c) 2026 Yawar Badri; the board, generator, example runner, and this
directory's documentation are available under [MIT](LICENSE). No third-party
board file, footprint geometry, screenshot, 3D model, or private project data
is included. This board has not been fabricated or measured.

The board has four nets: `VIN`, `VLOAD`, `VAUX`, and `GND`. `VIN` crosses an
explicit 0.1 ohm R1 series interface to `VLOAD`. The latter contains top and
bottom traces, two plated vias, and one filled zone. `VAUX` is a straight trace
for an independent resistance oracle. C2 is the nominal placed VLOAD capacitor
site; C3 is an unpopulated comparison site. Nominal board copper is 35 um per
side, and the 1.53 mm core uses relative permittivity 4.2 and loss tangent
0.02. These are fixture assumptions, not a fabrication stackup.

Run from a checkout with SPIKE's Python dependencies and native PEEC extension:

```sh
python examples/pi/reference_board/generate_board.py
python examples/pi/reference_board/run.py --output build/pi-reference-evidence.json --html-dir build/pi-reference-html
python examples/pi/reference_board/run_kernel_benchmarks.py --output build/pi-kernel-benchmarks.json
```

The deterministic board UUIDs and SHA-256 in the evidence detect accidental
fixture changes. The runner exercises KiCad import, validation, preflight and
hybrid mesh, DC on three rails, quasi-static AC on three rails, three-level DC
mesh convergence, reviewed R1 series-path AC, board-derived PDN multiport,
placed-C2 versus DNP-C3 capacitor sensitivity, an independent 17-frequency
nodal loading reference, multi-net batch normalization, and JSON/HTML reports.
The runner exits nonzero when any of its executable checks fails.
The separate kernel runner selects exactly ten retained PI references from
the internal benchmark implementations. It fails if any case fails or skips;
its checked [output](validation/pi-kernel-benchmarks.json) records every
measured value, oracle, error, and tolerance. These checks cover straight
trace and plated-via resistance, zone refinement, hybrid connectivity, native
self-inductance, hybrid PEEC, a capacitance limit, AC loss monotonicity,
shared-reference multiport algebra, and independent capacitor loading.

The closed-form VAUX DC oracle is `R = L/(sigma*w*t)` with `L=35 mm`,
`w=0.8 mm`, `t=35 um`, and `sigma=5.8e7 S/m`. The 2% tolerance allows pad
attachment geometry; it is not a global PI solver accuracy claim. DC power
balance is checked within 1%. AC checks require completed, passive sampled
impedance and finite residuals. C2/C3 use the same provisional 47 uF,
8 mOhm ESR, 0.6 nH ESL model and a 50 mOhm target for a *sensitivity study*.
No load profile, regulator, capacitor derating, mounting parasitics, return
impedance, or measured data justifies an operating-board optimum.

The evidence deliberately reports `release_validated: false`. Completing this
synthetic example does not qualify Marble, CERN, or other real-board behavior.
The stage-one release also requires a separate source/package parity gate,
real-board convergence and passivity evidence, clean-machine builds, and
knowledgeable numerical review. Preserve failures rather than changing a
tolerance to turn a blocked result into a pass.
