# SPIKE power-integrity user guide

This guide covers the desktop application, board inspection, project files, power-integrity (PI) setup, meshing, solving, results, and reporting. It describes the controls and the evidence a user should check; it does not certify a board or a solver. A browser preview can show the interface and imported geometry, but a native desktop worker is required to run an analysis and use native file dialogs.

For current numerical capability and validation limits, see [Solver status](SOLVER_STATUS.md). For every issued diagnostic, see the [error-code catalog](ERROR_CODE_CATALOG.md). Keep the code, operation ID, selected solver, application and worker versions, resource limits, and a sanitized input when reporting a failure.

## Before starting

- Use the installed desktop application and a supported KiCad `.kicad_pcb` board. Keep a copy of the original board; editing analysis settings does not repair source-board geometry.
- Know the intended power rail, return conductor, source, loads, operating voltage and currents. Exact source/load pad locations matter. Guessing from proximity can produce a plausible-looking but invalid result.
- Check that the imported stackup contains the copper thickness and, for AC work, the dielectric properties needed by the selected model. Missing material data must remain missing rather than silently guessed.
- Decide whether the task is one continuous copper net, an explicit series path across nets and reviewed components, or independent analyses of several nets. Select the matching workflow in PI setup.
- Save a working `.spike` project before a long operation. Save again after changing terminals, mesh settings, probes or results.

## Read the application window

| Area | What it is for | What to verify |
| --- | --- | --- |
| Title and project controls | Show the active project and open its management actions. | Confirm the expected project before importing, saving or reopening. |
| File, Edit, View and Quick menus | Project commands, viewport controls and direct access to PI setup, mesh, Run and results. | A command may open a setup panel; opening it is not a solver run. |
| Home ribbon | Import, open, save and design-readiness actions. | Import Quality and issues after loading a board. |
| PI ribbon | DC and AC setup, series paths, independent net batches, source/load tools, validation, Run PI and PI results. | Selected workflow, rail, source/load anchors and return path. |
| Mesh ribbon | Mesh configuration, stackup and managed nets. | Mesh geometry, cell count, resource admission and convergence status. |
| Solve ribbon | Review setup, open run controls, stop an active operation, inspect results and console. | Operation state and final result status. |
| Probes, Results and Reports | Place or inspect probes, change field views and export a report. | Quantity, units, active result identity and model status. |
| Settings | Interface, resources, extensions, shortcuts and dependency information. | Preferences are not a substitute for valid board geometry or a solver. |
| Scene Navigator | Find boards, nets, components, copper, vias, layers, probes and saved results. | Counts and selected object identity agree with the source board. |
| Board viewport | 2D/3D geometry, selection, camera and result overlays. | Correct side, layer, units, orientation and physical alignment. |
| Analysis Setup and lower dock | Analysis controls, issues, probe table, power tree and console. | Blocking diagnostics before Run; warnings and provenance afterward. |

Use **Fit** after an import or camera change. In 2D, pan and zoom to examine a layer. In 3D, orbit to inspect the board and models. Choose a selection filter before clicking: a part, a copper object and an entire connected net have different meanings. The object inspector should show the selected ID, layer, net and location before that object becomes a terminal or probe anchor. For shortcut details, use the application’s Shortcut manager.

## Import and inspect Marble

The pictured example is the public Berkeley Lab **Marble v1.4.4** KiCad board. Its pinned revision, license notice and screenshot provenance are recorded in [Marble evaluation](CERN_MARBLE_EVALUATION_20260920.md) and [help maintenance](HELP_MAINTENANCE.md). Obtain the board from the upstream project under its own terms; a documentation image is not a substitute for its KiCad source.

1. Choose **File → New project**, then **Import board** and select `Marble.kicad_pcb` through the native file dialog.
2. Wait for parsing and each visual stage to finish. Large-board layout, board model and component-model stages may complete at different times. A visible board does not mean every stage succeeded.
3. Open Import Quality and Issues. Compare the normalized net, track, pad, via, zone and component counts with the source review. Record recoverable diagnostics rather than treating a green percentage as proof of complete geometry.
4. In Scene Navigator, select a net, then a track, via, pad and zone on that net. Confirm IDs, layers and connectivity. If a source object is absent, repair or re-export the source before analysis.
5. Switch between 2D and 3D, use **Fit**, and open the Layer manager. Toggle one layer at a time, then All copper. Check that a hidden layer stays hidden, transparency is respected and the board frame does not shift. Visual layer visibility does not disconnect copper in the solver.
6. Save the project to a new `.spike` file using the native dialog. Close and reopen it; verify board identity, layer visibility, source geometry, models and warnings before proceeding.

![Marble v1.4.4 in the SPIKE workspace](../app/public/help/marble-workspace-3d.png)

*Real SPIKE 0.2.12 browser capture of the imported Marble board. Component bodies are procedural; this picture does not show a native solver run.*

![Marble copper layer and layer controls](../app/public/help/marble-layout-layers.png)

*Real imported 2D geometry with the Layer manager open. This is not a result field.*

![Marble front-copper net names](../app/public/help/marble-net-names.png)

*Real F.Cu view at high zoom. Fine-trace labels appear as the view is enlarged.*

The recorded Marble import contains 1,374 nets and 29 stackup rows but still has recoverable importer diagnostics. An earlier full-rail preflight was blocked by connection-evidence size and a configured branch limit; this guide does not present a solved Marble rail. The converted CERN White Rabbit core has additional import diagnostics and no extracted stackup, so it can demonstrate import review but must not be used as a solved AC example without corrected geometry and materials.

## Configure a single-net DC analysis

1. Choose **PI → DC drop** or **Quick → DC PI setup**. Select the named power net. Use the Net manager to verify that the intended source and loads belong to it.
2. Select **Direct net** for electrically continuous copper. If the path crosses a resistor, ferrite or another series part, use the reviewed **Series path** workflow instead; Direct net does not cross that component.
3. Add at least one voltage source and one current sink. Use the exact source-board pad or conductor location and confirm its net and copper layer. Enter voltage in V and current in A. Review contact and package resistance rather than assuming ideal terminals are physically accurate.
4. Select the return-path policy. If an explicit ground/return is used, identify its net and paired source/load return terminals. Check isolation boundaries and the source-to-load direction.
5. Enter engineering limits, such as maximum drop in mV and current density in A/mm². Limits flag results; changing a limit does not improve the electrical design.
6. Save the setup and inspect the displayed solver and formulation. A solver entry being visible does not establish availability or validation.

If a terminal cannot map to connected copper, stop and correct the anchor. If a load is disconnected, inspect the selected net and reviewed series bridges. Do not bridge missing connectivity by merely changing a mesh size.

## Preview mesh and run convergence

1. Open **Mesh** or the Mesh stage of PI setup. Review conductor representation, target size, zone cell size, via model and cell/resource limits.
2. Run the mesh preview and preflight. Inspect source ownership, net scope, zone-pad connectivity, through-via and pad-barrel handling, mapped terminals, warnings and admitted cell count.
3. Correct blocking geometry or mapping diagnostics at the source. A truncated preview is a display/resource signal, not evidence that the omitted copper was solved.
4. For an engineering comparison, run at least coarse, medium and fine meshes with identical terminals, materials and solver controls. Compare voltage drop, current density, probe values, residuals and mesh counts against a stated tolerance.
5. Preserve the convergence table with the result. A passing preflight only says the request is admissible; it does not show numerical convergence.

The desktop should show a separate indication for **not run**, **blocked**, **failed**, **completed approximate**, and any validated result. Do not infer a field or a value from an empty or decimated preview.

## Run and review DC

1. Choose **Quick → Run active PI**, the PI ribbon’s **Run PI**, or **Solve → Run controls**. Confirm the net, terminals, return, solver and mesh in the run panel.
2. Start **Run DC** and watch operation status in the console. Use Stop only for an active cancellable operation. A button press is not completion evidence.
3. Confirm that the worker returned a completed analysis with an analysis ID, solver/formulation, assumptions, model status and warnings. Keep a failed or unsupported result visibly distinct from a completed one.
4. In Results, inspect voltage, drop, branch current and current density where supplied. Confirm units, net, layer, mesh/result alignment and color scale before interpreting hotspots. Compare probes only when they map to the solved conductor.
5. Inspect the highest-drop path and current-density warnings, then compare against the limits and the mesh-convergence record. Save the result and project.

The Copper Geometry DC solver includes tracks, pads, polygonal zones and through vias, with explicit contact/package resistance when supplied. Its zone-spreading result remains approximate until a suitable convergence and independent comparison are recorded. See [Solver status](SOLVER_STATUS.md#copper-geometry-dc-spikerouted_dc).

## Run AC impedance and review capacitor candidates

1. Choose **PI → AC sweep**. Verify the explicit power/return scope, stackup and frequency range in Hz. Use a bounded frequency grid before increasing resolution.
2. Preview the hybrid trace, zone, pad and via mesh, then run preflight. Check memory admission and the quasi-static validity notice.
3. Run the eligible AC/PEEC solver. Inspect the complex impedance sweep, magnitude/phase, port definitions, solver/model status and frequency-by-frequency warnings.
4. For capacitor review, supply explicit candidate values and ESR/ESL or a labeled sensitivity range. Compare existing and proposed locations through reviewed candidate ports and target impedance. Record the same assumptions for every candidate.
5. Do not describe a minimum impedance from a direct-port approximation as an optimal physical placement. The current multiport and placement-review contracts provide screening evidence; measured-board or independently correlated extraction is still needed for a physical optimum.

## Series paths and independent net batches

For a **series path**, create an ordered source-to-load chain in the Power Tree. Review each intervening component, exact input/output pads, model value and net transition. PI setup must preflight each copper segment at its reviewed anchors. The composed result must retain every segment’s network, endpoint mapping and component-model provenance; it must not invent a circuit-wide spatial field from a lumped path result. Only select a path formulation that the current PI release actually supports.

For an **independent batch**, assign DC, AC or Skip to each managed net. Verify per-net terminals, solver eligibility and resource limits. Run one bounded job at a time or use the UI’s admitted batch control. Inspect each status and result identity separately; one completed rail does not validate another. Export a batch report only after checking that failed and skipped jobs remain visible.

## Layer manager and large results

The Layer manager changes presentation. It must not silently change the selected result, net, field units or solver topology. To diagnose a missing or misaligned field, first check the active result ID, view side, layer visibility, opacity, selected net and whether that result contains the requested quantity. Use **Fit** and compare a known pad/via coordinate with its source-board position.

On a large board, reduce visible model or overlay detail for interaction, but retain the complete result and its decimation/provenance flags for export. If the renderer fails, record whether parsing, board visuals, result import, geometry preparation or GPU drawing failed. A blank viewport is not an empty analysis. Save the underlying result before retrying presentation changes.

## Save, reopen and export without losing evidence

1. Save the `.spike` project through a native file dialog. Record the destination and wait for completion; do not infer success from a dismissed dialog.
2. Close and reopen that file. Confirm board hash or identity, stackup, managed nets, terminals, mesh settings, probes, result count, selected run, warnings and display settings. Compare a few numerical values and units with the saved report.
3. Use a result export when a separate portable analysis artifact is needed. Open it in a fresh session and verify its design context and provenance. A report export is a communication artifact; it is not a substitute for an editable project.
4. In Reports, review the banner and analysis status, then export the chosen format. Reopen the exported file offline and compare its values, units, warnings and model status with the application.

![Marble report preview marked analysis not run](../app/public/help/marble-report-preview.png)

*Real SPIKE browser capture. Its **ANALYSIS NOT RUN** banner makes it a setup/report-layout example, not solved PI evidence.*

## Recover from a failure

Search the complete code in [Error Code Catalog](ERROR_CODE_CATALOG.md). These examples are especially relevant to this guide:

| Code | Meaning | First action |
| --- | --- | --- |
| `SPIKE-FE-IPC-E-0001` | Local worker unavailable | Check the native desktop worker, then restart the application. |
| `SPIKE-FE-VIEW-P-0001` | Viewport performance degraded | Reduce visible detail and inspect renderer diagnostics; preserve solver data. |
| `SPIKE-FE-PROJECT-E-0001` | Project open failed | Check the selected file and package integrity. |
| `SPIKE-BE-IMPORT-W-0001` | Import quality warning | Review object-level diagnostics before analysis. |
| `SPIKE-BE-IMPORT-E-0001` | Design import failed | Check the board file and importer diagnostics. |
| `SPIKE-BE-MESH-W-0002` | Unusable copper polygon | Repair or refill the named source zone and re-import. |
| `SPIKE-BE-MESH-E-0018` | Zone-pad connection evidence failed | Repair retained connection evidence; do not infer missing spokes. |
| `SPIKE-BE-MESH-P-0001` | Mesh resource budget exceeded | Reduce validated mesh scope or adjust an approved resource budget. |
| `SPIKE-BE-SOLVER-E-0002` | Solver failed to converge | Inspect connectivity, conditioning and mesh convergence before changing limits. |
| `SPIKE-BE-PI-E-0001` | Terminal not mapped to copper | Assign an exact anchor on the analyzed net. |
| `SPIKE-BE-PI-E-0005` | Load disconnected from source | Review net connectivity and explicit series bridges. |
| `SPIKE-BE-PI-W-0004` | Copper discretization needs review | Run the configured coarse-to-fine study. |
| `SPIKE-BE-PACKAGE-E-0001` | Project package invalid | Open a verified backup or re-import the source board. |
| `SPIKE-BE-PACKAGE-E-0002` | Project package write failed | Choose a writable approved destination and inspect the reported cause. |

Keep the full diagnostic envelope and a sanitized reproduction. Do not paste local account names, workstation paths, private addresses or proprietary board contents into public issues or screenshots. Retry after changing the stated input, capability or resource condition; repeated identical retries add no evidence.

## Documentation evidence still required

The existing Marble images document import, layers, net names and an unsolved report. The PI release guide still needs **native desktop** captures of: import progress and quality diagnostics; exact terminal placement; mesh/preflight and convergence; a completed DC result; an eligible AC result; candidate-capacitor comparison; batch status; layer/result alignment; a save/reopen round trip; and an error code opened in Help. Each capture must record the board revision, application/worker/solver versions, operation ID where applicable, input assumptions, final status, and whether the image shows actual solver output. Until these captures and their underlying tests exist, the text above is workflow guidance rather than proof that every path works on Marble or White Rabbit.
