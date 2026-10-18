<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lumped physics parts in the Studio library

## Workflow

The Component library includes five opt-in **Physics models** records: four-terminal
NMOS, four-terminal NPN, three-terminal substrate resistor, three-terminal
feedthrough capacitor, and four-terminal Kelvin shunt. Select a record to inspect
its ordered terminal preview, edit its labeled SI coefficients, and review the
generated SPICE source. **Insert / multiple** requires an explicit net for every
terminal. No terminal is grounded or shorted by the browser.

Placement compiles the edited coefficients through
`python.spikes.lumped_physics_parts.build`. The insertion preview is parsed before
the document changes. Accepting the placement adds the subcircuit, instances,
canvas components, recent-item state, and a reviewed-model record in one document
transaction. The saved record contains the exact edited coefficients, ordered
pins, `generic_unqualified` status, and SHA-256 digest of the compiled source.
Undo and redo cover that whole transaction; ordinary project save/open preserves
the evidence under `metadata.lumped_physics_models`.

The existing schematic lowering displays expanded primitives. Use **Insert /
multiple** for repeated model instances; selected-fragment duplication currently
rejects flattened hierarchical children.

## Contracts and provenance

`spikes_studio.lumped_physics_library` is an adapter. It owns catalog metadata,
primary-parameter indexing, UI pin descriptions, and strict dispatch. It does not
own equations or topology. All five sources come from the established original
builders in `python/spikes/lumped_physics_parts.py`, which compose existing native
R, L, C, diode, Level-1 NMOS, Ebers-Moll NPN, and exact 0 V link primitives.
Builder input validation remains authoritative for finite SI values and numerical
admission bounds. No vendor data, package inference, or new numerical method is
introduced by the Studio adapter.

The default `component_catalog.catalog()` result remains the established 5,000
grid records. `include_lumped_physics=True` adds exactly five records; it can be
combined with `include_passives=True`. The Studio browser opts in to both internal
libraries. Each physics record declares one `primary_parameter` for numeric
filtering and sorting, while every builder coefficient remains editable.

## Exact terminal order and limits

| Record | Ordered terminals | Primary parameter |
| --- | --- | --- |
| `physics.lumped.nmos4` | D, G, S, B | threshold voltage (V) |
| `physics.lumped.npn4` | C, B, E, SUB | forward beta (dimensionless) |
| `physics.lumped.resistor3` | P, N, SUB | resistance (ohm) |
| `physics.lumped.feedthrough_capacitor3` | IN, OUT, GND | capacitance (F) |
| `physics.lumped.kelvin_shunt4` | FP, FN, SP, SN | resistance (ohm) |

The preview numbers are builder terminal positions, not manufacturer package pin
numbers. These parts are generic, unqualified lumped approximations. They are not
vendor compact models, process extraction, TCAD, distributed field models, RF
package models, self-heating models, or hardware qualification. The declared
backend is native, and the supported analyses are operating point, backward-Euler
transient, and BDF2 transient. Backend metadata does not select a solver. The
Equation bench intentionally refuses these records because it would create a
second behavior definition outside the established builders.

NMOS and NPN behavior retains the exact limits documented in
`docs/SPIKES_LUMPED_PHYSICS_PARTS.md`. Constant capacitances omit nonlinear
depletion and recovery behavior. The transistor cores omit production process
effects and thermal feedback. The substrate resistor and feedthrough capacitor
remain lumped. The Kelvin shunt omits self-heating and thermoelectric offset.
External biasing, return paths, timestep choice, convergence review, and
conditioning remain the user's responsibility.

## Verification

`standalone/spikes_project/tests/python/test_lumped_physics_library.py` checks the
opt-in count, strict record schema, primary indexing, exact pin order, UI SI field
units, parser admission, edited-source regeneration, malformed-input atomicity,
placement order, saved provenance, and single-step undo/redo. When
`SPIKES_TEST_LIBRARY` or `SPIKES_TEST_NATIVE_LIBRARY` names the current native
library, it also executes all five catalog recipes through a native operating
point smoke check. The deeper analytical oracles remain in
`tests/python/test_spikes_lumped_physics_parts.py`.
