# Scoped net labels: source-authoritative foundation

Labels attach to an existing component terminal or drawn wire. They describe
and, in the admitted root-sheet case, rename real native SPICE nets. A label
is not an independent electrical graph, arbitrary text annotation, or a claim
of complete KiCad hierarchy support.

## Workflow

Use the schematic's **Label here** action on a pin or route. Choose an electrical
name and Local, Global, or Hierarchical scope. The dialog shows the exact sheet
instance, currently attached native net, and eligible declared ports. Applying
the label validates native Circuit text before committing one undoable edit.
Save/reopen and Undo/Redo retain label IDs and stable terminal attachments.

- Local labels use the exact instance path, including nested instances. `inner`
  in `X1` resolves to `x1:inner`; the same label in `X2` resolves to `x2:inner`.
  Existing formal ports and native globals retain their actual source bindings;
  a Local marker does not disconnect those explicitly connected nets.
- Global labels require node `0` or a real `.global` declaration. A new root-only
  global label inserts `.global NAME` into Circuit text. In a hierarchical deck,
  add/review the declaration explicitly before placing a marker: declaring a
  global can affect every instance of a shared definition.
- Hierarchical labels must name an already declared formal port in the exact
  attached instance. Native elaboration's ordered port mapping supplies the
  parent net. Invented ports and mismatching attachments are rejected.

On root-only decks, changing a Local label's name renames the complete native
net, including all its pins. Reusing an existing name merges the nets when the
native parser admits the resulting circuit. Known voltage probes, expression
lists, instrument/dashboard expressions, junction nets, and wire capacitance
reference nets migrate in that transaction. Ground node `0` cannot be renamed.
Removing a marker leaves the native name and `.global` declaration intact; use
Undo to reverse the complete placement/rename transaction.

## Limits and recovery

No graphical shared-subsheet editor or new port authoring is added here. Labels
inside hierarchy can describe existing connections but cannot rename internal
nodes or modify shared definitions. This prevents an edit on `X1` from quietly
altering `X2`. Use Circuit text for such edits and review each affected instance.

Source rewriting rejects hierarchy, includes, library/control blocks, node
directives, and source voltage-reference expressions. Root-only nonglobal nets
can merge into an existing declared global, retaining its `.global` declaration;
renaming an already declared-global net requires explicit Circuit text review.
Controller, analytics, and power-tree bindings also block renaming because they
need explicit reference review. Existing labels on unchanged actual nets remain
usable in these decks. Parser rejection leaves source, metadata, and undo
history unchanged. Unsupported source edits are not silently approximated.

Wire labels use a stable wire ID and terminal identity; drawing recomputes a
position on that route. Geometry never establishes net identity. Source or
route replacements that invalidate a label require the host to remove/review
the marker or reject the transaction, not retain a misleading name. Results
acquired before a source change remain historical data and are not relabeled.

## Developer API and evidence

`spikes_studio.net_labels` owns:

- `attach(document, kind, name, attachment, label_id=None)` for atomic add/edit;
  returns the admitted label dictionary. Attachment is `[component_id, index]`
  or the canvas dictionary `{part_id, pin_index, wire_id?, attach_point?}`.
- `remove(document, id)` for presentation-only removal.
- `validate(data)` for schema and native-source binding admission;
  `reconcile(data)` returns only still-valid labels so callers can explicitly
  report/reject removed bindings during source or route replacement.
- `defaults(data, attachment)`, `show(owner, attachment, label_id=None)`, and
  `draw(canvas, dc, palette)` for the native editor integration.

The optional `labels` list contains `{id, kind, name, terminal, sheet_path, net,
wire_id?}`. Names/nets are canonical lowercase; instance paths are uppercase.
`terminal` is a stable component-ID/pin-ordinal pair, not a coordinate or a
definition-local reference. `Document.commit(mutator)` remains transaction and
undo authority. The native parser remains the net/port/global authority.

Reproduce the headless behavior checks from the repository root:

```text
python -m unittest discover -s standalone/spikes_project/tests/python -p test_net_labels.py -v
```

The suite verifies repeated and nested instance locality, declared global
connectivity, ordered formal-port binding, rejection/rollback, root net merges,
probe migration, stable IDs, save/reopen, wire attachment, and undo/redo. These
parser/contract checks do not establish visual GUI acceptance or full editor
parity; native-window verification is a separate integration gate.
