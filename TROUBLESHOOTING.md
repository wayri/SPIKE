# SPIKE Troubleshooting

This guide covers the active Tauri/React desktop, local worker, CLI, project
packages, and isolated CAD import adapters. For an exact
`SPIKE-ORIGIN-DOMAIN-CLASS-NNNN` diagnostic, start with the
[error-code catalog](docs/ERROR_CODE_CATALOG.md). Numerical status is separate
from software failure: `approximate`, `unsupported`, and
`failed_to_converge` results must be handled according to their validity
notices even when no application error occurred.

## Triage sequence

1. Record the exact error code, operation ID, command or UI action, desktop
   version, worker version, operating system, and result model status.
2. Save the project if the UI remains responsive. Do not overwrite the only
   copy of a suspect package.
3. Open the Console and Issues docks and preserve their bounded diagnostics.
4. Retry once only when the catalog marks the condition retryable and the
   underlying input or runtime condition has changed.
5. Reproduce through the CLI or direct worker to identify whether the failure
   belongs to the UI/native bridge or Python/solver boundary.
6. Minimize the design or request without removing the failing condition.

Do not attach raw project files, model libraries, paths, or logs containing
confidential data unless they have been reviewed for disclosure.

## Symptom index

| Symptom | Start here | Common code/domain |
|---|---|---|
| Desktop opens but analysis commands fail | [Worker unavailable](#worker-unavailable-or-busy) | `FE-IPC`, `BE-IPC` |
| Browser preview cannot open files or run a solver | [Browser preview limitations](#browser-preview-limitations) | Expected development limitation |
| Board will not import or looks incomplete | [Import failures](#import-fails-or-import-quality-is-low) | `BE-IMPORT` |
| Project will not open or save | [Project/package recovery](#project-will-not-open-or-save) | `FE-PROJECT`, `BE-PACKAGE` |
| Solver cannot be selected | [Solver unavailable](#solver-is-unavailable) | `BE-SOLVER-E-0001` |
| Mesh is blocked or too large | [Mesh failures](#mesh-warning-or-resource-budget-failure) | `BE-MESH` |
| Solve stops, times out, or does not converge | [Solver execution](#solver-fails-to-converge-or-exceeds-a-budget) | `BE-SOLVER` |
| Viewport is slow or blank | [Viewport recovery](#viewport-is-slow-blank-or-misaligned) | `FE-VIEW` or WebGL/runtime issue |
| SPICE setup is rejected | [SPICE recovery](#spice-workspace-or-model-is-rejected) | `FE-SPICE`, `BE-SPICE` |
| External engine is rejected | [External engines](#external-engine-cannot-run) | `BE-EXT` |
| Report export fails | [Report recovery](#report-generation-or-export-fails) | `BE-REPORT`, `BE-PACKAGE` |
| License activation or capability is rejected | [License recovery](#license-activation-or-capability-is-rejected) | `FE-SECURITY`, `BE-SECURITY` |

## Application operation fails

For `SPIKE-FE-APP-E-0001`, keep the current project state and inspect the
operation detail before retrying.

1. Record the command, operation ID, and safe detail shown in Console.
2. Correct the highlighted input or incomplete workflow state.
3. Retry once. If the same operation fails again, reproduce it through the CLI
   or direct worker where an equivalent command exists.
4. If the failure becomes `SPIKE-FE-APP-C-9999`, stop retrying and follow
   [Unexpected critical failure](#unexpected-critical-failure).

## Worker unavailable or busy

`SPIKE-FE-IPC-E-0001` means the desktop could not communicate with the local
worker. A busy rejection can also include the active operation ID.

1. Wait for the active operation to complete if the Console reports that the
   worker is busy. Starting another heavy operation does not cancel it.
2. Close and restart the desktop if no operation is active.
3. From the repository root, test the source worker directly:

   ```powershell
   '{"id":"manual-health","method":"health","params":{}}' |
     python -m python.spike_core.service
   ```

4. If direct health succeeds but the desktop fails, verify `SPIKE_WORKSPACE`
   and `SPIKE_PYTHON`, then run the native desktop from `app` with
   `npm.cmd run tauri dev`.
5. If direct health fails, use the traceback only in the local development
   environment to repair the Python environment. Do not replace the packaged
   release worker with an arbitrary system interpreter.

A malformed response (`SPIKE-FE-IPC-E-0002`) or unknown method
(`SPIKE-BE-IPC-E-0002`) usually indicates frontend/worker version drift. Keep
the diagnostic and restore a matched build rather than repeatedly retrying.

## Browser preview limitations

`npm.cmd run dev` serves the React interface without the Tauri host. Native
file dialogs, approved file writes, process supervision, and the local worker
are therefore unavailable or preview-only.

1. Confirm the command was started from `app`.
2. Use the preview only for frontend rendering and state work.
3. Run `npm.cmd run tauri dev` for import, save, solver, report-file, and native
   runtime testing.

This is expected behavior and should not be reported as solver availability.

## Import fails or import quality is low

1. Confirm the input is a readable KiCad `.kicad_pcb` file. KiCad is the only
   implemented native EDA importer; other formats remain planned adapters.
2. Re-run the import through the CLI to separate UI selection from parsing:

   ```powershell
   .\spike.cmd --output design.json import path\to\board.kicad_pcb
   ```

3. For `SPIKE-BE-IMPORT-E-0001`, inspect the source path, syntax, format hint,
   and importer diagnostic. The existing open project remains authoritative
   until a new import succeeds.
4. For `SPIKE-BE-IMPORT-W-0001`, inspect the Import Quality and Issues panes.
   Missing or ambiguous source data is not silently promoted to complete.
5. Check layer order, units, stackup, tracks, vias, pads, zones, components,
   and unsupported objects before defining terminals.

## Project will not open or save

1. For `SPIKE-FE-PROJECT-E-0001` or `SPIKE-BE-PACKAGE-E-0001`, keep the
   current project open, if possible, and inspect the package with:

   ```powershell
   .\spike.cmd project-inspect path\to\project.spike
   ```

2. Open a verified backup or re-import the source board if package integrity
   fails. Do not hand-edit a package to bypass validation.
3. For `SPIKE-BE-PACKAGE-E-0002`, choose a destination through the native Save
   dialog and verify that the destination is writable and has free space.
4. If a legacy project needs migration, inspect it first and supply a distinct
   destination to the explicit migration command:

   ```powershell
   .\spike.cmd project-migrate legacy-project.json migrated-project.spike
   ```

   Do not overwrite the only source copy.

## Solver is unavailable

1. Run `.\spike.cmd solvers` and `.\spike.cmd capabilities`.
2. Compare the requested mode, geometry, frequency range, and model-status
   policy with the solver descriptor.
3. Open Solver Manager for optional external engines. A discovered or
   registered executable is not necessarily workflow-ready or validated.
4. For `SPIKE-BE-SOLVER-E-0001`, select an eligible installed solver or revise
   the request to a capability that actually exists. There is no silent
   fallback for unavailable physics.
5. Consult `docs/SOLVER_STATUS.md` before interpreting any result.

## Mesh warning or resource budget failure

1. Open mesh preview and inspect whether terminals map to connected copper.
2. Review geometry/import issues before changing mesh controls.
3. For `SPIKE-BE-MESH-W-0001`, refine the affected geometry or settings and
   repeat preflight.
4. For `SPIKE-BE-MESH-P-0001`, use a coarser policy only if it remains valid
   for the analysis, or increase an approved resource budget.
5. Run a convergence study for publishable DC work. A passing preflight does
   not establish mesh convergence.

## Solver fails to converge or exceeds a budget

1. Preserve the request, solver descriptor, operation ID, conditioning and
   convergence diagnostics, mesh settings, and resource limits.
2. For `SPIKE-BE-SOLVER-E-0002`, review connectivity, terminal placement,
   conditioning, and mesh quality before increasing iteration limits.
3. For `SPIKE-BE-SOLVER-P-0004`, reduce validated model complexity or increase
   the approved wall-time budget.
4. For `SPIKE-BE-SOLVER-E-0003`, review partial diagnostics but do not treat
   partial fields as a completed result; run again when ready.
5. Compare at least three mesh sizes where the workflow requires convergence
   evidence. Never relabel failed convergence as approximate success.

## PI candidate and loop extraction fails

1. For `SPIKE-BE-PI-E-0100`, review every candidate value, endpoint mapping,
   frequency sample, and extraction source before resubmitting.
2. For `SPIKE-BE-PI-E-0102`, map source, observation, and candidate terminals
   to explicit mesh locations on connected copper.
3. For `SPIKE-BE-PI-P-0103`, reduce the candidate set, run bounded batches, or
   increase the approved limit only up to the documented hard maximum.
4. For loop codes `E-0200`, `E-0201`, and `E-0204`, correct the request shape,
   select distinct connected forward/return pad endpoints, and review component
   pins and any operating-point linearization.
5. Keep `W-0101`, `W-0202`, `W-0203`, `W-0205`, and `W-0206` attached to the
   result. They identify screening assumptions, reference mismatch, excluded
   shunt behavior, or nonlinear linearization and are not cleared by a
   successful software run.

## Viewport is slow, blank, or misaligned

1. Switch between 2D and 3D. If 2D works and 3D is blank, record GPU, driver,
   WebView2, and WebGL details.
2. Use Fit to restore the active design framing. Reduce visible layers,
   models, vectors, mesh, and result detail for
   `SPIKE-FE-VIEW-P-0001`.
3. Reopen the project to test saved camera/workspace-state restoration.
4. Verify top/bottom orientation and model/result alignment against the source
   board before reporting a transform defect.
5. Restart the desktop after a suspected WebGL context loss. Automatic context
   recovery is still listed as architecture debt.

## SPICE workspace or model is rejected

1. Correct highlighted model, pin, and analysis fields for
   `SPIKE-FE-SPICE-E-0001`.
2. Validate the workspace and map every required model pin to an explicit
   design anchor.
3. Remove includes, libraries, shell commands, or control blocks rejected by
   `SPIKE-BE-SPICE-S-0001`; do not weaken the parser or trust policy.
4. Review parasitic endpoint mapping, units, and provenance. An unvalidated
   parasitic warning permits screening only where its validity notice says so.
5. Reduce duration, step size, saved outputs, or resource use for transient
   budget failures.

## External engine cannot run

1. Open Solver Manager and distinguish discovery, registration, runtime
   verification, adapter readiness, workflow readiness, and validation.
2. `Register` records an existing absolute path; it does not install or trust
   the engine.
3. For `SPIKE-BE-EXT-E-0001`, preserve process diagnostics and re-run the
   bounded engine/runtime probe.
4. For `SPIKE-BE-EXT-S-0001`, stop. Restore the expected signed installation
   or reviewed integrity record before execution.
5. Use the engine-specific document under `docs` for remaining qualification
   gates. Do not infer PCB readiness from executable discovery.

## License activation or capability is rejected

1. Open Settings and copy the native device request. Confirm that the request
   was generated by the desktop, not the browser preview.
2. `SPIKE-BE-SECURITY-S-0001` means the build has no trusted issuer public key.
   Install an official or correctly configured development build; never paste a
   private issuer key into the application.
3. `S-0002` or `S-0003` means the envelope or signature is invalid. Reject the
   file and obtain a newly signed entitlement from the authorized issuer.
4. `S-0004` means the entitlement belongs to another machine or operating-system
   user. Deactivate/reissue the seat; do not edit the signed claims.
5. `E-0002` or `E-0003` means product compatibility or the validity period was
   rejected. Use an entitlement for this product major version and verify the
   trusted system clock before renewal.
6. `E-0004` means local entitlement storage failed. Check per-user app-data
   permissions, disk space, and endpoint-security quarantine.
7. `E-0005` leaves SPIKE in viewer/recovery mode because no entitlement is
   installed. `E-0006` means the installed entitlement does not grant the
   requested capability.

The local entitlement is signed and bound to one machine/user pair. Strictly
preventing a second activation for the same commercial order requires the
licensing service; offline verification alone cannot enforce issuer-side seat
uniqueness.

## Report generation or export fails

1. Open report preview before export and inspect warnings, model status,
   provenance, and whether a numerical result is attached.
2. A report marked `ANALYSIS NOT RUN` is a setup/design record, not a solved
   engineering result.
3. For `SPIKE-BE-REPORT-E-0001`, preserve the report diagnostic and retry from
   a valid project/result state.
4. For a write failure, choose a writable destination with sufficient space
   through the native dialog.
5. Verify the exported HTML opens offline and retains the same validity and
   warning state shown in preview.

## Unexpected critical failure

For `SPIKE-FE-APP-C-9999` or `SPIKE-BE-APP-C-9999`:

1. Preserve the diagnostic record and operation metadata.
2. Restart the affected desktop or worker.
3. Reproduce with the smallest reviewed input.
4. Add a failing automated fixture before changing recovery behavior.
5. Verify that saved project files were not modified by UI recovery.

See `docs/STABILITY_AND_RECOVERY.md` for process-boundary protections and the
maintainer incident workflow.

## Diagnostic record checklist

- Exact error code, title, operation ID, and timestamp.
- SPIKE desktop, worker, solver, and optional-engine versions.
- Operating system, CPU/memory pressure, and GPU/WebView details when relevant.
- Command or UI task sequence and whether the failure reproduces in the CLI.
- Input/result sizes, request settings, mesh policy, and configured budgets.
- Model status, warnings, convergence state, and solver provenance.
- Sanitized minimal fixture or project hash, never unreviewed confidential data.
