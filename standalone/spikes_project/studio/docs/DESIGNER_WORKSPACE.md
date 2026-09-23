# Schematic-first workspace

The development workbench no longer uses a main workspace tab strip. Use the workspace selector or View menu to open tools; Split view places the schematic beside stacked waveform plots with a movable divider. This is not yet a fully dockable multi-document window manager.

## Schematic editing

Designer and workflow actions now use distinct theme-aware icons with hover tooltips. W arms wiring: click a terminal, optional grid-snapped corners, then a destination terminal. A dashed preview follows the pointer. Escape discards the unfinished route. Drag a wire away from component bodies to move its route with a live preview; the endpoint pin identities stay fixed and the operation is undoable. Manual routes do not automatically avoid intervening symbols.

Filled dots mark multiple wires sharing a terminal. Crossings alone are not electrical connections. Arbitrary mid-wire junction insertion, branch splitting, dangling wires and individual-segment drag handles are still pending.

The left designer offers Select, Lasso, Wire, Rotate, Mirror X and Mirror Y. Drag empty canvas for a visible selection outline; Ctrl adds to the selection. Selection uses component centers. Drag selected components to move them. Wire connects two clicked terminals; Escape cancels. Mirroring and rotation retain electrical terminal identities.

Drag a component or analysis from the designer tree, or double-click to arm placement. Components open the existing pin/value insertion review. Analysis blocks open the directive editor for review, not immediate execution; backend analysis limitations still apply. Right-click the canvas for selection, mirroring, annotations, probes and directives.

Notes, rectangles and ellipses are saved schematic annotations, not executable statements. Drag them to move, double-click to edit text, or right-click to edit/delete. Changes are undoable. Shape resize handles and arbitrary vector drawing are not implemented here.

## Waveforms

## Keyboard defaults

Ctrl+E opens component properties; E remains available. Ctrl+R rotates; Space remains available. Ctrl+A selects all components. Ctrl+Z undoes; Ctrl+Y or Ctrl+Shift+Z redoes. Ctrl+N/O/S create/open/save. Ctrl+Shift+E exports. Ctrl+1/2/3 open schematic/plots/circuit text. F5 runs, F6 pauses/resumes, Shift+F5 stops, and Ctrl+F5 starts continuous simulation.

Ctrl+C on the canvas currently copies the **entire schematic**, including model context, not a selected-part fragment. Ctrl+V opens the existing import review before replacing a sheet. Additive component copy/paste and cut/delete with dependency remapping are not implemented by these bindings. Text editors keep native selection, copy, cut, paste and undo behavior.

Edit → Keyboard shortcuts loads/saves editable profiles; existing custom profiles are preserved, so select SPIKES defaults to adopt new bindings. LTspice-inspired maps Ctrl+R to Run and Ctrl+Shift+R to Rotate. Menus show current assigned keys.

## Waveform interaction

Click a waveform to place a cursor. Drag an existing vertical cursor line to move it while retaining its original run and signal binding. Cursor window lists signal, run, time and sampled value; its relative math accepts a, b and dt. Measurements use original samples, not decimated display data.

Wheel over a plot or its bottom axis to zoom time; wheel over the left axis, or Shift-wheel inside, to zoom amplitude. Stacked time axes stay linked. Right-click for cursor readings, fit, pan, rectangle zoom, grid, legends and notes. Plot notes currently last only for the session and appear in image exports.

View provides a simulation diagnostic snapshot from actual engine results. It is not a complete SPICE console log or a substitute for compiler logs and the simulation manager.

## Verification

Actual-window regressions on 2026-09-06 used native stepped RC simulation and an analytical wired divider. Evidence under the repository's artifacts directory:

- studio-no-tabs-editor-v2-20260906/checks.json: 11 passed checks.
- studio-no-tabs-workspace-20260906/checks.json: 27 passed checks.
- Those folders contain actual application screenshots, including the selection outline and cursor window. No synthetic waveform data were substituted.

Launch current source with `python scripts/launch_spikes_studio.py` from the repository. Previously installed packages do not automatically acquire these changes.
