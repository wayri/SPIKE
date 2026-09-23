# Recovery, subcircuits and programmable pins

## Recovery autosave

Every 60 seconds a changed schematic and its unapplied Circuit text draft are saved atomically to `%LOCALAPPDATA%/SPIKES Studio/recovery`. This never overwrites the project file. Each application session/project has a separate snapshot; unchanged snapshots are not rewritten. File → Recover autosave opens one as an unsaved copy, retaining invalid or incomplete netlist text separately from the last valid circuit. Save explicitly after reviewing recovery.

Snapshots are retained, including after normal close, and can contain private circuit data. No automatic pruning or cloud upload is performed. Maximum snapshot size is 32 MiB. This pass does not recover unsaved IDE code, open property-dialog fields or dashboard-editor drafts until those edits are applied to the document.

## Native hierarchy

Edit → Create subsheet creates a SPICE `.subckt`, an X instance and explicit ordered hierarchy pins mapped to parent nodes. Enter the subcircuit contents using those pin names. Names and the full resulting deck are validated before the undoable transaction. The current editor supports simple definitions without nested definitions/includes; the broader netlist parser remains separate.

Double-click a flattened subcircuit component to jump to the shared definition in Circuit text. The `.subckt` header defines its ordered hierarchy pins. Edits affect every instance; validate/apply before simulation. This is real native electrical hierarchy with a text editor, NOT a nested schematic drawing workspace. Collapsed sheet blocks, visible hierarchical pin placement, parent/child graphical navigation, automatic port renaming and repeated-sheet layout remain pending.

## C/C++ block pins

The Controller workspace's Pin properties button opens a grid for pin name, AI/DI/AO/DO mode, node, reference, voltage-source binding and logic supply. Add/remove rows and Apply validates all pins. Read inputs with `inputs[IN_sense]` and assign `outputs[OUT_drive]` for pins named sense and drive. Changed pin configurations require recompilation; old compiled configurations are rejected on attachment. Compilation remains explicit and trusted-code-only.

Verilog remains in the separate HDL IDE; defining Verilog co-simulation pins and connecting arbitrary compiled blocks inside nested schematic sheets are not implemented here. The installed beta.2 has not automatically acquired these development changes.
