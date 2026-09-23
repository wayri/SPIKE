# MODULAR-BUS-NIB source-to-load DC terminal check

The exact-pad terminal measure is corrected, but this real-board DC result
remains `approximate` and **not converged**. Terminal current conservation does
not establish board accuracy or permit sign-off.

## Pinned inputs and terminal repair

- Board: `app/public/demo/MODULAR-BUS-NIB.kicad_pcb`
  (SHA-256 `37639b58aa75c11265ecf7867c2d358942b70c9e0011a10da99f524e767c2f07`).
- Request: `docs/validation/modular-bus-nib-12vout-dcir-request.json`
  (SHA-256 `5f133d60414a52fc592e012559491abba690782a00c69d340debbce34687bad8`).
- Physical pad-cell ownership: commit `4d2f29423d5c5d1df3701495720028dcd2c6ad83`.
- Terminal area stamping: commit `7a53d98700eb40392929f1e7311be33e635f8488`.

The source is 12 V at R19.3 on `/12Vout`; loads at J14.2, J20.2, and J15.2
draw 3.333333333, 3.333333333, and 3.333333334 A, respectively. All terminals
have exact imported pad IDs, `F.Cu` single-layer scope, and ideal contact and
package resistance. The run uses the service importer and the repository's
Python 3.12 environment, with a 4 GiB solver admission budget. Pad IDs and
full-precision scalar results are recorded in the
[compact evidence](modular-bus-nib-terminal-area-dc-evidence.json).

Before the repair, a pad boundary included pad attachment endpoints, including
some zone nodes outside the pad, and assigned equal weight to each node. The
repair uses physical pad-cell areas: a load injects `I_i = I A_i/sum(A)`, and
its reported voltage is `sum(A_i V_i)/sum(A)`. For assigned contact resistance
`R`, branch resistance is `R_i = R sum(A)/A_i`. These independently derived
relations preserve total current, parallel contact conductance, and terminal
power under subdivision. An ideal source fixes physical pad-cell potentials.
Missing ownership and malformed, nonfinite, or degenerate pad areas fail
closed. This change applies to explicitly required exact pad anchors;
exploratory coordinate-only and non-pad terminal policies are unchanged.

## Corrected three-level diagnostic

`h` below is `target_size_mm`; the zone cell is `h/2`. These are three distinct
mesh settings, so a statement of only "1 mm" is insufficient to identify a run.

| h / zone cell (mm) | J14.2 drop (mV) | J20.2 drop (mV) | J15.2 drop (mV) | Copper loss (mW) |
| --- | ---: | ---: | ---: | ---: |
| 2 / 1 | 3.042241 | 3.097365 | 2.900951 | 30.135189 |
| 1 / 0.5 | 3.415096 | 1.890454 | 1.862311 | 23.892869 |
| 0.5 / 0.25 | 1.686140 | 1.689621 | 1.950538 | 17.754327 |

For the same three settings, the pre-repair maximum load drops were
2.843671, 3.194219, and 1.754471 mV, with copper losses of 27.663552,
22.122007, and 16.284120 mW. The corrected terminal formulation **does not
resolve refinement instability**: the maximum drop changes about 42.9% and
copper loss about 25.7% between the last two levels. No 0.125 mm zone-cell
result is included in this record.

All three corrected solves completed with a total load of 10 A. Their maximum
absolute source/load current imbalance is `1.55e-8 A`; scaled linear residuals
are below `1.01e-16`. Because contacts are ideal, copper dissipation must equal
`sum(I_load * supply_drop)`. This independent power check agrees within
`7.22e-12 W` at every level. These are conservation checks, not accuracy claims.

R19.3 retains 4.41025 mm2 of physical terminal area while its pad-cell count
changes from 2 to 6 to 18. Each load retains 0.363511534 mm2 and 24 pad cells.
Copper attachment topology still changes: for example, J14.2 has 1, 0, and 2
`pad_attachment` branches, respectively. Constant load area therefore does
not remove the remaining topology and spreading-resistance uncertainty.

The diagnostic uses the same anchored inputs as
`scripts/verify_modular_bus_pi_convergence.py`, restricted to factors
`(2.0, 1.0, 0.5)` with `stop_when_converged=False`; its normal four-level run
also requests a finer level that is outside this evidence. Reproduction of
these historical numbers requires the pinned repair revision and input hashes,
since later mesh corrections can change results.

## Historical pre-repair terminal test

The earlier version of this document reported J14.2/J20.2/J15.2 drops of
2.7843/2.8439/2.6721 mV, scaled residual `7.53e-17`, and current balance within
`1e-7 A`. Those were **pre-repair** test results at the default 1 mm general
target and a 1 mm zone cell, using the old distributed boundary-node measure.
They are retained only as historical evidence and are not the corrected
three-level results above.

`tests/python/test_hybrid_dc_terminal_validation.py` now checks exact board
terminal mapping, fail-closed anchors, synthetic explicit return voltages,
nonuniform pad-area subdivision, contact versus copper loss, and the
power-conjugate terminal voltage. The terminal/core/PI-path suite passed
59 tests after the repair; architecture and whitespace checks passed.
Board qualification still requires resolved mesh convergence, applicable
contact/package data, and an independent measured or reference voltage
comparison. Knowledgeable human review remains required before release.
