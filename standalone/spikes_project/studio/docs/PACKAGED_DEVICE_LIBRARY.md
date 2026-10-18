<!-- SPDX-License-Identifier: Apache-2.0 -->
# Packaged generic transistor models

## Scope and workflow

The Component library contains two opt-in **Physics models** records:
`physics.packaged.nmos4` and `physics.packaged.npn4`. Each record combines one
existing generic four-terminal lumped transistor core with the existing generic
constant package-parasitic composer. Select a record, review every SI coefficient
and the generated source, map all four ordered terminals, then use **Insert /
multiple**. The browser never infers a ground, package pin number, vendor part,
or package value.

The editable package inputs are a uniform active-lead series resistance in ohms,
a uniform active-lead series inductance in henries, and one package shunt
capacitance in farads. The initial `0.01 ohm` and `1 nH` values are illustrative
inputs reused as an unqualified editing starting point; they are not estimates
for a real package. The shunt capacitance starts at zero to avoid silently adding
to the core's existing capacitances. Zero package R/L/C is supported and compiles
to exact zero-volt links with no package R, L, or C elements.

Placement parses the complete core-plus-wrapper source before mutation. An
accepted placement writes the edited record, exact pin order, core and package
builder identities, `generic_unqualified` status, and compiled-source SHA-256 to
`metadata.packaged_device_models` in the same undoable document transaction as
the source and flattened schematic components. Save/open, undo, and redo retain
that evidence.

## Exact topology and terminals

| Record | Ordered terminals | Uniform series R/L | Package shunt C | Exact link |
| --- | --- | --- | --- | --- |
| `physics.packaged.nmos4` | D, G, S, B | D, G, S | G-S | B |
| `physics.packaged.npn4` | C, B, E, SUB | C, B, E | B-E | SUB |

For each active lead, the composer places package R then package L before the
private core terminal when both values are nonzero. It omits each zero element.
The fourth terminal is joined to its private core terminal by an exact zero-volt
link. The package capacitance joins the two named private core terminals, after
the series lead networks. Mutual inductance is deliberately absent because the
owned parser/native runner does not execute `K` elements. The displayed terminal
positions preserve the core builder order; they are not manufacturer package pin
numbers.

## Source-method provenance and limits

`spikes_studio.packaged_device_library` is only a strict catalog and composition
adapter. The transistor equations and numerical bounds remain in
`python/spikes/lumped_physics_parts.py`, documented in
[Lumped multi-terminal physics parts](../../../../docs/SPIKES_LUMPED_PHYSICS_PARTS.md).
The package topology, passivity checks, zero-element behavior, and parser/backend
limits remain in `python/spikes/device_parasitics.py`, documented in
[User-defined semiconductors and package parasitics](../../../../docs/SPIKES_EQUATION_DEVICES.md).
The source-method execution record is
[Equation-device and package-parasitic validation](../../../../docs/validation/SPIKES_EQUATION_PARASITICS_20261013.md).
The adapter concatenates the trusted generated core and wrapper subcircuits; it
does not add an equation, solver, numerical method, or vendor model.

Both records remain generic reduced-order, `generic_unqualified` models. They do
not represent a named package, process, geometry extraction, distributed RF
network, mutual lead coupling, self-heating, thermal feedback, reverse recovery,
avalanche, aging, or manufacturing spread. Users must avoid double counting
capacitances already present in the core. The declared native analyses are
operating point, backward-Euler transient, and BDF2 transient. Convergence,
timestep choice, biasing, return paths, physical applicability, and comparison
to measured data remain review responsibilities.

## Verification

`standalone/spikes_project/tests/python/test_packaged_device_library.py` checks
the opt-in catalog boundary, JSON schema, strict builder identity, primary-value
indexing, source composition, exact topology and pin order, zero-package links,
malformed-input atomicity, saved provenance, and undo/redo. With
`SPIKES_TEST_LIBRARY` set to the current native DLL, it also compares the
zero-package NMOS against its direct core behavior and verifies that a nonzero
package resistance produces the expected native solved voltage drop while
nonzero package L and C are present in the parsed executable circuit.
