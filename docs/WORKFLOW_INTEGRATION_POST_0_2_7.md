# Post-0.2.7 workflow integration

These changes are in development source, not the installed 0.2.7 archive.

## Compact PI source and load setup

Open PI analysis setup and select Direct net, Series path, or Independent batch.
Sources and sinks now use one editable row per terminal under the selected net.
Explicit return references and paired returns use the same table layout.

1. Set name, X/Y, copper connection, source voltage or sink current, and contact
   and package resistance in the row. Scroll horizontally in narrow dock layouts.
2. Select **Pads / details** to locate a physical pad. Only one detail editor
   per table is mounted; opening another closes the previous editor.
3. For transient runs, select **Edit waveform** to open the existing waveform
   editor. The ordinary DC/AC value is not silently substituted for that waveform.
4. Existing Add, Pick exact point and Use current selection actions still apply.
   Editing X/Y explicitly detaches the previous pad anchor; layer changes retain
   the existing connection semantics. Paired-return current remains read-only.

The canonical PI setup is unchanged and continues to save in the native project.
PI setup and SPICE workspace edits now explicitly activate unsaved-project
protection; this does not create expensive full-board undo snapshots per keypress.

## Owned SPIKES circuit integration

The SPICE model assistant's Validate & run page now offers the release-owned
SPIKES engine alongside native MNA, PEEC/MNA and external ngspice. It submits a
structured, reviewed workspace to the existing validator and runs only after
validation succeeds. Enter one probe descriptor per line, such as `V(out)`,
`V(plus,minus)`, `I(V1)` or `P(V1)`. Differential commas are preserved; descriptors
are validated by the owned parser. **Export owned result** saves the complete
JSON result, including samples and provenance, not just the on-screen summary.

Results remain circuit quantities with netlist identity and qualification
metadata, not fabricated board fields. Engine admission, bounded result sizes,
and existing assembly scope remain enforced. The standalone structured thermal
reference is not integrated into this workflow, and this change does not qualify
arbitrary PCB, multiboard, SI compliance or electrothermal field execution.

New owned-engine probe selections/results are session-local in this slice;
native project persistence of that run configuration is a follow-up requirement.
The underlying models, assignments, parasitics and analysis workspace continue
to use existing project persistence.

## Evidence and remaining checks

- `app/scripts/test-terminal-table.mjs`: actual rendered table and event handlers,
  100 collapsed records with no detail render, single expanded editor, direct and
  batch/return wiring, value and coordinate edits, transient and empty states.
- `app/scripts/test-unsaved-project.mjs`: PI/SPICE mutation hooks participate in
  the existing save/discard/cancel flow.
- Owned workspace backend tests exercise release-owned execution, probe aliases,
  strict validation, result provenance and malformed-result rejection.
- Integrated frontend regression: all 45 `test:*` scripts passed; 10 focused
  Python workspace/owned-engine tests passed. Generated help was refreshed.

Native pixel/layout acceptance, fully interactive circuit plots, project-bound
probe/results persistence, long-run process supervision and large-assembly
performance qualification remain pending. Do not infer them from rendered-markup
tests or from the prior installed package checks.
