<!-- SPDX-License-Identifier: Apache-2.0 -->
# Simulation studies

Simulation studies organize saved workspace setups, recorded result snapshots, and supplied datasets. A study is a project artifact, not a solver or scheduler. Activating a case loads its saved setup into the matching workspace; solver readiness and execution remain controlled by that workspace.

## Workflow

Open **Simulation studies**, create a study, and add one or more cases. A case records its analysis domain, mode, scenario, notes, and a copy of the workspace settings saved for it. The active marker means that the case setup is loaded in the workspace. It does not mean that a solver is running, that a result is current, or that a model is validated.

Use tags to find related studies. Archiving removes a study from the default navigator while retaining it in the project. Search covers study and case names, notes, tags, domains, modes, and dataset metadata. Study and case names are committed on blur or Enter so spaces can be typed normally; Escape restores the saved name.

The details pane has four views:

- **Setup** edits the selected case and activates or saves its workspace setup. **Record snapshot** is available only for the active case.
- **Recorded runs** lists immutable workspace captures and exposes their reported result contract, status, model status, design binding, units, and raw JSON. The capture timestamp records when SPIKE copied the workspace state. It is not proof of the solver's execution time, inputs, convergence, or qualification.
- **Datasets** attaches bounded JSON or CSV source data and links it to the selected case. Unlinking a dataset does not delete other cases. Dataset units and provenance remain explicit; SPIKE does not infer missing units.
- **Compare** checks result contract, design binding, and units before presenting runs together. Compatibility only permits side-by-side presentation. Numerical comparison and engineering interpretation remain with the relevant domain workflow.

Deletion always uses an inline confirmation. Deleting a run removes only that recorded snapshot. Deleting a case does not remove sibling cases. Deleting a study removes that study and the evidence stored inside it.

## Import, export, and limits

Study export writes the complete study JSON through the native save dialog in the desktop shell. Browser builds request a download. Dataset and individual run exports preserve the stored payload, units, status, model status, and provenance without converting values.

Complete study documents are limited to 256 MiB on both import and export, and export uses compact JSON so every legal export can be reimported. Individual attached JSON/CSV datasets remain limited to 2 MiB. CSV admission also bounds row and column counts. The model checks total embedded study data before accepting an attachment and rejects unsupported, cyclic, non-finite, malformed, or oversized values. A failed import leaves the project unchanged and reports a recoverable status message.

Imported studies are normalized through the versioned `simulationStudies.ts` contract. A future schema version is rejected so an older application cannot overwrite information it does not understand. Recorded result snapshots use a separate aggregate project limit and preserve source datasets when project result data is removed.

## Data contract and limitations

`app/src/simulationStudies.ts` owns normalization and immutable study operations. `app/src/studyWorkspaceModel.ts` owns bounded dataset preparation/export, capture admission, search, and comparison compatibility. `StudyManager.tsx` is presentation only; `App.tsx` remains project-state and persistence authority.

Recorded facts are copied from the result payload. Missing status, units, design identity, or model status stay missing and appear as not recorded. A completed status is not a validation claim. Studies do not infer a running state, compliance result, convergence, accuracy, or solver capability from UI availability.

The desktop currently compares retained facts and raw payloads. Domain-specific curve alignment, interpolation, unit conversion, statistical analysis, and acceptance limits must be implemented and validated by the owning analysis workflow before they can be presented as numerical comparisons.
