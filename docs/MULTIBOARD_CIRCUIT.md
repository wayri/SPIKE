# Coupled multi-board reduced circuits

`python/spike_core/solvers/circuits/models/multiboard_circuit.py` executes one linear modified nodal
analysis system containing every retained board occurrence and every retained
harness/mate pin. This is an experimental approximate circuit capability,
not a geometry extraction or cross-board electromagnetic field solver.

## Request and retained identity

The contract is `spike/multiboard-circuit-request/v1`, defined by
`schemas/multiboard-circuit-request-v1.schema.json`. Supply `assembly`, `domain`
(`pi` or `si`), `board_models`, `link_models`, `ground`, and native `analysis`.
Each board model has `board_id` and native MNA `elements`. Every board occurrence
requires exactly one model, even if multiple occurrences use the same layout.
Every retained harness and direct mate requires exactly one link model;
every retained pin pair requires explicit electrical properties. Board terminal
node names are `connector_id:pin`, for example `J1:2`.

All local nodes and element IDs are namespaced by occurrence using encoded
tuples, avoiding collisions in IDs containing colons. Local `0` is an ordinary
local node. `ground: {board_id, node}` selects exactly one potential datum.
Returns between boards must be explicitly authored; no ground shorts, name-based
net connections, or proximity connections are inferred. Unknown link fields,
mutual coupling and rigid-flex links are rejected. Native
singular or floating circuit failures remain failed results without traces.

## Mechanical structures and chassis bonds

Every physical part requires `part_models: [{part_id, elements}]` with passive
native R/L/C elements. Model-less subassembly containers are explicitly excluded.
Part nodes and element IDs are separate from board nodes, including local `0`.
The ground and pi-shunt reference can instead use `{part_id,node}`; no casing
becomes ground automatically.

Supply one `electrical_bond_models` row per retained assembly electrical bond:
`bond_id`, `endpoint_a`, `endpoint_b`, `resistance_ohm`, `inductance_h`.
Endpoints use exactly one of `{board_id,node}` or `{part_id,node}` and must match
the retained bond owner. A local node mapping is explicit. Bond R/L stamp the
same native series equations as connector paths; zero R/L is an ideal branch.
One board plus one physical part is admitted when explicit links/bonds connect
the circuit. Results retain `part_node_map`, `part_element_map` and
`electrical_bonds`. STEP/material metadata does not infer these values.

`test_multiboard_circuit_parts.py` independently compares the complex transfer
of a loaded board with a series R/L/C chassis branch against parallel impedance
algebra, including bond resistance sensitivity and isolated local-zero identity.

## Connector model and units

Each `link_models` entry has `link_id`, `kind` (`harness` or `mate`), and `pins`.
Each pin has `source_pin`, `target_pin`, `resistance_ohm`, `inductance_h` and
optional `capacitance_f`. Optional `contact_a_resistance_ohm`,
`contact_b_resistance_ohm`, `contact_a_inductance_h`, and
`contact_b_inductance_h` represent contacts separately from the conductor.
Contacts sum into series R/L and their individual authored values remain in
result provenance. All values are finite and nonnegative in ohms, henries, farads.
Zero R/L creates an explicit ideal zero-voltage branch rather than merging nodes.

A positive capacitance requires `reference: {board_id, node}`. A symmetric pi
model places C/2 from each end of that pin to this explicit reference. The
reference is an existing circuit node, not an automatically grounded node.
This model cannot represent a mutual capacitance matrix or distributed cable
delay. Model parameters must come from measured or independently extracted data.

## Execution and output

PI accepts `analysis.mode: operating_point` or `ac`; SI requires `ac` with
`start_hz`, `stop_hz`, `points`, and optional `scale` (`linear` or `log`).
Independent sources require an explicit `dc_value`/`value` for operating_point,
or `ac_magnitude` for AC, including zero for an inactive excitation.
Transient waveforms are unsupported. Limits
are 4096 compiled elements, 10000 frequency points, and 2 million estimated
stored sample values. Sparse native MNA performs the shared solve.

`spike/multiboard-circuit-result/v1` retains `node_map`, `element_map`, and `links`
with compiled IDs, authored properties, total series R/L. `native_result` has
native diagnostics and data: DC `node_voltage_v` and `element_current_a` are
scalar dictionaries; AC traces contain `real`, `imaginary`, `magnitude`, and
`phase_deg` with a shared `frequency_hz` axis. `assembly_digest` binds canonical
assembly physics (excluding saved multiboard studies), while `request_digest`
binds the complete authored request. `production_qualified` remains false.

Completed DC results additionally report each link pin's signed `current_a`
(source to target), `conductor_loss_w`, `contact_a_loss_w`, `contact_b_loss_w`,
and `total_loss_w`. Each resistive loss is I²R using the actual series branch
current. Ideal branches and inductors have zero DC dissipation. These values
can be explicitly assigned as thermal node heat inputs; they are not injected
into a thermal model automatically. Failed or AC results omit these DC scalar
fields. AC connector heating requires an explicit excitation and frequency
power interpretation, beyond this DC handoff.

## Numerical evidence and validity

`tests/python/test_multiboard_circuit.py` compares a two-board resistor loop
against KVL: I = Vs / (Rload + Rfeed + Rreturn), Vload = I Rload,
Plink = I²(Rfeed + Rreturn), and total signed element power equals zero.
Increasing a contact resistance must change the shared operating point.
An independent AC oracle uses Vload/Vs = Rload /
(Rload + Rfeed + Rreturn + j 2πf L), checked at three frequencies.
The pi-capacitance oracle uses Zload = 1/(1/Rload + j2πf C/2) and
Vload/Vs = Zload/(Rfeed + Zload) with explicit ideal return. Residual checks,
separate occurrence/local-zero identity, missing coverage, unknown mutual
properties, negative values, and floating subcircuits are tested.

These linear algebra reference checks do not qualify physical parameter
extraction, high-frequency model validity, full PCB fields, nonlinear driver
behavior, eye diagrams, radiation, or EMI compliance. Knowledgeable human
review of numerical code and actual hardware comparison are required before
release qualification.
