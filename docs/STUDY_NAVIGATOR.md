# Studies and retained results

Open File > Simulation studies, or choose Studies beside Scene in the left
navigator. The navigator can float inside the workspace and dock back to the
left sidebar. Resize a dock with the existing sidebar divider; resize the
floating panel from its corner. Manage studies opens the full editor.

The tree groups studies, simulation cases, saved case results and recorded
run captures. Project results contains retained solver history and the latest
SI, thermal and EM results stored outside cases. Expand/collapse each branch,
search names and result metadata, or include archived studies.

Click a case to load its saved setup and result. Click a saved result or
recorded run to restore that capture's setup and payload. Double clicking
activates once. Arrow keys navigate and expand/collapse the tree; Enter or
Space activates the focused entry. The workspace clears stale selection,
isolation and preview state, restores the matching analysis controls and
available result viewer/overlay, and fits the viewport. No solver is started.
Unsupported spatial fields are not synthesized from network-only results.

Design identity and board-file guards remain in force. Stop an active run
before selecting another study. External result references without embedded
payloads open the file chooser; cancellation leaves the saved history intact.
Run captures retain their recorded settings, scenario, payload and provenance.
Loading a capture does not establish that it is current or physically validated.
Only results actually retained in the project are available; discarded runs
cannot be reconstructed by the tree.

## Thermal information cards

Use the card's Hide temperature info button (x) to hide it without clearing the
selected sample. Temperature info restores it; probing another colored thermal
cell also reopens it. This controls the information card, not the thermal field.
The field visibility control remains separate.

## Implementation and checks

StudyNavigator.tsx owns the tree; App.tsx owns admission and domain restoration.
The existing project study/result contracts are unchanged. Focused checks are
app/scripts/test-study-navigator.mjs and test-study-result-activation.mjs.
Loading timing is described in [project loading ETA](PROJECT_LOADING_ETA.md).

Browser development checks exercise dock/float, tree selection, keyboard
navigation, long labels and the thermal card. They do not establish installed
Windows runtime or native project-package reopen acceptance.
