# Quick SI usability target

User reference reviewed 2026-09-20:
`C:/Users/yawar/Documents/agws/KiCAD_plugins/kiWay/signal_integrity_advisor_plugin/ReadMe.md`.
Only user-facing documentation was reviewed; no implementation, screenshots,
numerical code or fixture was copied into SPIKE.

The useful comparison is workflow clarity, not a claim of field-solver parity.
WayriCAD documents a selected net/source-pad/receiver-pad workflow, explicit edge
and termination assumptions, route review, optional illustrative eye/step plots,
and report export. Its documentation expressly limits those results to screening.

## SPIKE acceptance sequence

1. Select board, net, source pad and sink pad; show the chosen route and return
   reference. Reject unresolved/disconnected paths rather than analyzing a
   different inferred net or hiding the unresolved state.
2. Show editable driver edge, source/load impedance and channel-model basis in
   one concise setup. Distinguish measured Touchstone, extracted geometry and
   assumed uniform-line models. No model silently replaces another.
3. Run through the worker. Retain explicit errors, progress, cancellation and
   the previous result's identity. Changing inputs marks results stale.
4. Open waveform, S-parameter, TDR and eye plots when their data is actually
   returned; unavailable plots explain why. Charts can expand into an in-app
   subwindow without hiding the setup permanently. Native detached windows
   are a later host integration, not assumed available.
5. Read real X/Y cursor values, compare traces, and export results and reports
   with inputs, units, solver/model limits and identifiers. Never label an
   illustrative eye as protocol compliance or BER qualification.

Existing `SiWorkflowWorkbench.tsx` and `SiWorkflowPlots.tsx` already consume
loaded transfer, waveform/eye, network and TDR results. The gap is an easily
discoverable end-to-end board workflow and chart interaction, not absence of
all SI calculations. CLI fixture success does not establish GUI acceptance.

## Required evidence before calling this workflow usable

- One bundled real-board route selected by pad identity and solved without
  manual JSON editing, plus a deliberately disconnected negative case.
- Explicit assumptions visible in setup and exported evidence.
- Plot cursor tests on nonuniform sample spacing and empty traces.
- Chart expansion/close/Escape and focus recovery at supported window sizes.
- Save/reopen setup and results without losing board/endpoint identity.
- Human interaction verification remains required; this CLI-first task does
  not substitute screenshots or browser rendering for tests it has not run.
