# Geometry to basic PI

This is a UI handoff to the existing approximate PCB copper DC workflow.
It adds no numerical method and does not turn arbitrary MCAD solids into a PDN.

1. Import a supported PCB design and check normalized copper, stackup and materials.
2. Open the top-center search and choose **Geometry -> basic PI**. The command is
   unavailable without a loaded board. It selects DC IR Drop, SPIKE Copper Geometry
   DC (`spike.routed_dc`) and the existing `resistive_network` formulation.
3. Review the supply/return nets, explicit source/load terminals, loads, copper
   assumptions and mesh. Resolve preflight errors and approve the actual setup.
4. Run. The existing worker owns preflight, admission, execution and validity.
   Inspect its retained geometry-linked voltage, voltage drop, current, current
   density and power-loss results in the normal result viewport.

The adapter passes `spike/analysis-request/v1` to `run_preflighted_analysis` and
requires a `spike/preflighted-analysis/v1` transaction. Only a completed DC result
with the existing `spike/result-visualization/v1` mesh and scalar fields is exposed
by its visualization accessor. Missing fields remain unavailable. Existing
unsupported/approximate states are preserved; no substitute fields are fabricated.

Tracks, zones, pads and vias use the released normalized-conductor model and its
material assumptions. STEP enclosure or package geometry alone does not provide
conductivity, current terminals, electrical connectivity or a qualified solver mesh.
AC/full-wave PI and new geometry extraction are outside 0.4.3.
