# Original SPIKE reference for the native client

The native C++ client uses the preserved wxPython implementation as a product
and interaction reference, not as a runtime dependency. The current worker,
DesignIR, analysis, result, and `.spike` v3 contracts remain authoritative.

## Reference sources

- `demo_spike.py`: mature workbench composition, AUI docking, project workflow,
  multi-terminal PI setup, selection synchronization, progress, and domain entry
  points.
- `current_setup_tab.py`: compact source/load/pass-through assignment workflow,
  solver controls, and post-simulation probe layout.
- `python/viz/viewport3d.py` and `python/viz/viewport2d.py`: board interaction,
  layer controls, net/pad picking, highlighting, units, and heatmap behavior.
- `python/ui/analysis_dashboard.py`: probe table, impedance and transient plots,
  observations, and CSV export.
- `python/ui/pre_sim_dialog.py`: readiness checks and bounded resource estimates.
- `python/ui/reports_panel.py`: configurable report sections, static publication
  figures, interactive output, HTML export, and print/PDF workflow.
- `python/ui/si_workspace.py`, `thermal_side_panel.py`, `pdn_health_dialog.py`,
  `net_classifier_dialog.py`, `settings_dialog.py`, and `wizards.py`: useful
  domain-specific workflows and discoverability patterns.

`python/gui/main.py` is an earlier ribbon shell and is useful for intent, but it
contains mostly stubs. The files above are the stronger behavioral baseline.

## Foundations to preserve

| Foundation | Native-port requirement |
| --- | --- |
| Dockable engineering workbench | Keep the ribbon, left design navigator, central 2D/3D workspace, right setup manager, and bottom diagnostics/results independently resizable. |
| Bidirectional selection | Net, layer, component, pad, probe, and viewport selection must remain synchronized and use stable DesignIR identities. |
| Multi-terminal PI setup | Restore bulk pad selection, multiple sources and loads, editable assignments, explicit return paths, pass-through topology, and batch-net setup through current analysis contracts. |
| Layer-aware visualization | Preserve layer visibility, opacity, top/perspective views, zoom-to-fit, highlighting, units, heatmaps, hover data, and persistent probes in VTK. |
| Preflight before execution | Present worker validation, model status, capability gates, mesh/resource estimates, and actionable issues before starting a solver. |
| Results dashboard | Provide probe tables, impedance and transient charts, limit status, observations, CSV export, and traceability from displayed values to result records. |
| Project continuity | Persist setup, terminal assignments, probes, selected views, report configuration, and domain state inside the current `.spike` v3 package rather than the legacy `.spk` ZIP layout. |
| Reports | Retain configurable executive summary, setup/audit, charts, probes, interactive output, offline HTML, and print/PDF. Use VTK for native fields, Plotly for interactive report charts, and worker-side Matplotlib for static publication figures. |
| Progressive disclosure | Keep setup wizards, net classification, PDN health, SI, thermal, and advanced settings available without crowding the primary analysis path. |

## Legacy implementation choices not to copy

- Do not revive the monolithic `demo_spike.py` frame or duplicate parsing and
  solver semantics in the UI.
- Do not call numerical kernels directly from the UI thread or use simulated
  results when the worker is unavailable.
- Do not migrate heuristic readiness, PDN grades, or guessed solver status as
  authoritative engineering results. Route them through versioned worker
  operations with explicit model status and provenance.
- Do not use the legacy `.spk` ad-hoc archive or extract archives without the
  `.spike` v3 verification and resource-admission boundary.
- Do not reparent PyVista/native windows or embed Python/Matplotlib in the C++
  UI process. wxWidgets owns the native window and OpenGL context; VTK renders
  inside it, and static figures are produced by the isolated worker.
- Do not copy broad exception suppression, global path mutation, or theme code
  that overrides native control behavior indiscriminately.

## Reference precedence

When implementations disagree, use this order:

1. Current schemas and worker capability/model-status responses.
2. Current Tauri UI for presently supported product scope and terminology.
3. Original SPIKE sources for proven engineering interaction patterns.
4. Native-platform conventions for accessibility, keyboard navigation, DPI,
   window ownership, and performance.

This preserves the original product insight without carrying forward its
runtime coupling or obsolete data authority.
