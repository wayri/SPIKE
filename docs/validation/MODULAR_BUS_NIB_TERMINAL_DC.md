# MODULAR-BUS-NIB source-to-load DC terminal check

The reproducible input is `app/public/demo/MODULAR-BUS-NIB.kicad_pcb`
(SHA-256 `37639b58aa75c11265ecf7867c2d358942b70c9e0011a10da99f524e767c2f07`).
`tests/python/test_hybrid_dc_terminal_validation.py` imports that board, selects
`/12Vout`, anchors the 12 V source to R19.3, and anchors three 3.333333333 A
loads to J14.2, J20.2, and J15.2. The test resolves each pad's imported ID
before the solve and requires exact terminal geometry. It uses a 1 mm zone
cell target and ideal contact/package resistances from the existing DC request.

| Solved load terminal | Supply drop at 1 mm |
| --- | ---: |
| J14.2 | 2.7843 mV |
| J20.2 | 2.8439 mV |
| J15.2 | 2.6721 mV |

The source boundary is 12 V. The three reported drops equal source boundary
voltage minus solved load boundary voltage, including the distributed terminal
boundary nodes. Total load is 10 A. The scaled linear residual was
`7.53e-17`, and source/load current balance met the `1e-7 A` test tolerance.
Missing or wrong geometry anchors and ambiguous source assignments fail closed.
An explicit supply/return synthetic circuit also checks signed differential
voltage and loop drop.

This is a terminal mapping and conservation check on a real imported board.
The DC model remains `approximate`: mesh convergence, terminal contact area,
contact/package resistance, and an independent measured voltage comparison
are still needed for a board accuracy or release claim.
