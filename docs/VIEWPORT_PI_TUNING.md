# Viewport PI load tuning

In the PI or Results workspace, configure the internal **DC IR Drop** study with
an assigned source and current sink. Select the retained board occurrence in an
assembly, then press **Tune PI** in the viewport toolbar.

- Hold **Shift** over copper on the study net and scroll up to increase the sink
  current by 0.1 A; scroll down to decrease it. Hold **Alt** as well for 0.01 A.
- With several sinks, select the sink in the toolbar. In 3D, hovering its terminal
  marker also selects that sink. Ambiguous net-level gestures are blocked.
- **Auto run** reruns after scrolling pauses for 500 ms. Turn it off to make
  several edits, then press **Run**. **Undo** restores the current before the
  latest wheel burst; run again to obtain a result for the restored setup.

Each edit marks the project changed and hides the previous overlay. Reruns use
the existing worker transaction, resource admission, preflight, solver and saved
result ingestion. Failed validation is shown in the status bar. Inputs cannot be
wheel-edited during an active solve. An unrelated edit, project switch, board
switch or disabled tuning cancels a pending rerun. A completed result for an old
setup is withheld from the viewport.

Board occurrence identity and net name must both match the retained study. No
source, sink, return path, or link is created by this gesture. Unassigned anchors,
invalid currents and duplicate sink IDs require repair in PI setup. Current is
clamped at zero; source capacity remains a solver admission check. Wheel magnitude
is not a physical quantity: each delivered wheel event is one step.

This convenience applies to internal single-net DC PI in both 2D and 3D,
including a focused retained board within an assembly. It does not rerun batch,
series-path, extension or SI analyses; use their existing setup and run controls.
It does not infer electrical connections from equal net names across boards.
