<!-- SPDX-License-Identifier: Apache-2.0 -->
# Probe results table

`app/src/ProbeResultsTable.tsx` presents solver-returned probe measurements and user-defined calculated rows. The parent owns `calculatedRows` and persists them as UI/project state; the table never changes solver results.

Formulas use stable probe IDs and field names: `P1.voltage`, `P1.drop`, `P1.current`, `P1.power`, `P1.density`, and `P1.impedance`. The parent can persist friendly aliases such as `P1` through `probeReferenceIds`; otherwise the table derives a stable parser-safe identifier from each board object ID. Calculated rows expose only `.value`, for example `C1.value`. Operators `+`, `-`, `*`, `/`, parentheses, and `abs`, `min`, and `max` are supported. Addition, subtraction, `min`, and `max` require matching units. Supported derived relations include `V / A = ohm` and `V * A = W`.

The parser does not execute JavaScript. Missing or unmapped measurements, incompatible dimensions, duplicate IDs, cycles, division by zero, and non-finite results remain visible as row errors and export to CSV. A zero solver value remains a valid measurement.

Open **Probe table**, then **Add formula**. For example, use `P1.voltage-P2.voltage` for voltage difference, `P1.voltage/P1.current` for resistance, or `C1.value*2` to reuse a calculated row. Formula definitions and stable aliases are saved in the project under `probe_table.calculated_rows` and `probe_table.reference_ids`, and included in project snapshots. Removing a probe does not silently retarget its alias; dependent formulas show a missing-reference error. CSV export includes calculated values, units, expressions, and errors.

**Detach probe table** opens a separate native window. Edits return to the main workspace and use the same evaluator and project persistence as the docked table. Closing or redocking the window retains the formulas. See `DETACHED_TOOL_WINDOWS.md` for window and payload limits.
