# KiCad schematic import contract

SPIKE renders original modern `.kicad_sch` files through an installed
`kicad-cli`. The Python adapter keeps KiCad rendering and compiled connectivity
outside the webview, then returns inert SVG pages, original UTF-8 hierarchy
members, source symbol UUIDs, approximate symbol pick regions, and XML-netlist
connectivity. It does not reconstruct or redraw the source schematic.

The worker method is `import_kicad_schematic_view` with parameters `path` and an
optional `timeout_seconds` from 5 through 300. Its result contract is
`spike/kicad-schematic-view/v1`. Each page has an explicit `id`, `sheet_path`,
`source_file`, `view_box`, and sanitized self-contained `svg`. Symbols use the
same page ID and retain `source_uuid`, reference, value, library ID, millimetre
anchor, pin UUIDs, and compiled net names. Reused-sheet occurrence IDs append
the hierarchical sheet path while retaining the original UUID separately.
Net nodes carry reference, pin, matched symbol occurrence IDs, and source pin
UUIDs for cross-selection.

Hierarchy members are limited to the selected root directory and reject
absolute paths, traversal, cycles, missing files, malformed syntax, and
oversized inputs. The aggregate retained source limit is 32 MiB. Generated SVG
is limited to 80 MiB across at most 128 pages and rejects active elements,
event handlers, entities, external references, and external styles. Netlist XML
rejects DTD and entity declarations and has bounded node counts. Native process
execution uses a fixed argument vector, no shell, no stdin, a timeout, and
bounded diagnostics. Missing KiCad or failed exports return an error; partial
pages are never admitted.

Symbol hit boxes are stable 10 mm source-anchor envelopes because KiCad's SVG
export does not expose symbol-level bounds. Page artwork is correlated with
source objects through explicit page, sheet, source-file, reference, and UUID
metadata. This is sufficient for deterministic cross-selection but is not a
claim of exact graphical symbol bounds.

## Connectivity-only sources

The `import_connectivity_view` worker method accepts a path, optional
`format_hint`, and optional ODB++ `step`. It supports KiCad XML netlists,
legacy KiCad s-expression `.net` exports, and ODB++ folders or bounded source
archives. ODB++ uses the existing source-package importer and exact toeprint
net indices; multi-step jobs require an explicit step. Archive containment,
member count, expansion, compression ratio, and processing time remain bounded
by that importer.

Connectivity-only sources return the same view contract with
`source.presentation=generated_connectivity`. The single self-contained page
uses generic component boxes, explicit pin numbers, and net labels. Its
coordinates are labelled `diagram`; they are not source millimetres. The
result preserves source references and exact pin-to-net assignments but makes
no claim that generated placement, symbols, or artwork match an original
schematic. Original UTF-8 XML and `.net` inputs are retained in `source_files`;
ODB++ binary/package input is represented by its authenticated digest while
the normalized connectivity makes the saved view self-contained.

Duplicate references, unknown component nodes, empty pins or net names, and a
pin assigned to conflicting nets fail the complete import. XML DTD/entity
declarations and malformed s-expressions fail before diagram generation.
Generic SPICE and behavioral netlists remain unsupported because they do not
provide one unambiguous cross-selection identity contract across subcircuits,
models, and generated devices.


## Desktop workflow

Choose Schematic on the viewport toolbar (or find KiCad schematic viewer with
Ctrl+K). The separate native window can be moved outside SPIKE. Import the root
.kicad_sch file; KiCad renders its sheets and compiles the netlist locally.
Select a sheet, pan with a left drag, zoom with the wheel or toolbar, and use
Fit to restore the full sheet. Part and net search stays beside the drawing.

Choose Link active board to explicitly associate the schematic with the loaded
board. Selecting a schematic part selects the unique matching board reference.
Selecting a net resolves its component pins to the board net; missing or
conflicting pin mappings do not select a guessed net. Board selections update
the schematic highlights. Net selection highlights connected symbols; it does
not claim wire-segment-level connectivity picking. Symbol pick rectangles are
approximate regions around saved source anchors, not native per-symbol bounds.

Save the SPIKE project to retain the original hierarchical sources, rendered
sheets, compiled connectivity and explicit board binding. Retained views can be
opened without rerunning KiCad. Changing board source invalidates its binding;
use Link active board again after review. Native windows use the OS close
button. Original schematic import requires installed KiCad. Netlist and ODB++ connectivity import do not require KiCad. File picking requires the updated native desktop build.

## Trace values and saved graphs

With a result displayed, select a trace to show its compact saved-value card in
2D or 3D. View > Panels > Hide/Show trace values and mini graphs toggles the cards.
Saved voltage/current samples and transient histories keep their units and
actual timestamps. Exact trace identity and bounded nearby samples are labelled
separately. Missing values or histories remain unavailable. Assembly cards need
an explicit result occurrence binding and are withheld without it.

This adapter and UI are original SPIKE implementation. No Pocket KiVi source
or unrelated application capabilities are bundled or relicensed.


The viewer uses a per-session authenticated same-origin local channel for
snapshots and a small allowlist of actions. It has no worker execution or file
access bridge of its own. The child requires no native event permissions; compatibility with an already-running older development shell does not
require broadening all-window permissions. Closing the viewer disposes its
channel and parent session. Import failures retain the previous drawing.


In an assembly containing repeated boards, select the specific occurrence of
its active design before linking. Cross-selection remains scoped to that
occurrence. Changing the source or removing that occurrence invalidates the
link; the viewer never chooses another board with the same reference names.
