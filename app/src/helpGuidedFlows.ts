// SPDX-License-Identifier: Apache-2.0
export interface HelpGuideReference { topic: string; label: string; anchor?: string }
export interface HelpGuideImage {
  src: string; alt: string; caption: string;
  highlight: { x: number; y: number; width: number; height: number; label: string };
}
export interface HelpGuideStep {
  title: string; action: string; expected: string; recovery: string; image: HelpGuideImage;
  references: HelpGuideReference[];
}
export interface HelpGuidedFlow {
  id: string; title: string; summary: string; outcome: string; prerequisites: string[]; steps: HelpGuideStep[];
}
const reference = (file: string, label: string): HelpGuideReference => ({ topic: `doc:docs/${file}.md`, label });
// Percentages refer to the unchanged 1707 x 960 browser captures, not the panel size.
const captureBounds: Record<string, [number, number, number, number]> = {
  "gerber-source": [0.5, 22, 55, 46], "gerber-stack": [0.5, 23, 55, 32],
  "layer-grid": [0.5, 7.5, 38, 25.5], "viewport-fields": [10.4, 12, 20, 36],
  "mechanical-measure": [74, 13, 24, 67], "mechanical-section": [74, 13, 24, 51],
  "layers-expanded": [0.3, 10, 38.5, 29],
  "pi-geometry": [62.5, 29, 37, 34], "pi-terminals": [63, 44, 36, 46], "pi-review": [63, 45, 36, 18],
  "thermal-setup": [63, 25, 36, 40], "si-setup": [63, 33, 36, 64],
  "section-help": [39, 12, 40, 80],
};
const current = (file: string, alt: string, label: string, x: number, y: number, width: number, height: number, mechanical = false): HelpGuideImage => ({
  src: `/help/guides-current/${file}.jpg`, alt,
  caption: `Actual SPIKE ${["pi-geometry", "pi-terminals", "pi-review", "thermal-setup", "si-setup", "layers-expanded"].includes(file) ? "full workbench browser" : "browser component"} capture, 23 October 2026. ${mechanical ? "Authored glTF test solids with the retained EBrake board; visual geometry tools only." : "Visible controls and setup state only."} No native worker or numerical solve is demonstrated.`,
  highlight: { x: captureBounds[file]?.[0] ?? x, y: captureBounds[file]?.[1] ?? y, width: captureBounds[file]?.[2] ?? width, height: captureBounds[file]?.[3] ?? height, label },
});
const workspace = (search: boolean): HelpGuideImage => ({
  src: `/help/guides-current/${search ? "command-search" : "workbench-overview"}.jpg`,
  alt: search ? "SPIKE search expanded with PI command categories and setup routes" : "Current SPIKE workbench with the retained EBrake board and two command rows",
  caption: "Actual full workbench browser capture, 23 October 2026. Retained EBrake board and visible controls; no numerical solve or native desktop acceptance is demonstrated.",
  highlight: search ? { x: 27.7, y: 9, width: 44.5, height: 71, label: "Search results and command categories" } : { x: 0.4, y: 0.4, width: 99, height: 8.4, label: "Project and viewport command rows" },
});
const gerberRef = reference("EMERGE_GERBER", "Gerber source and execution limits");
const mechanicalRef = reference("MECHANICAL_VIEWPORT_TOOLS", "Mechanical controls and units");
const fieldsRef = reference("FIELD_VISUALIZATION", "Field formats and display limits");

export const helpGuidedFlows: HelpGuidedFlow[] = [
  {
    id: "pi-setup", title: "Prepare a DC PI study", summary: "Select copper, assign terminals and review before running.",
    outcome: "A reviewed PI request with explicit sources, loads, mesh and model assumptions.",
    prerequisites: ["A loaded board with a continuous power net or a reviewed series path.", "Reviewed source voltage, sink current, terminal locations and return model."],
    steps: [
      { title: "Choose the copper domain", action: "Press Ctrl+K, search DC PI setup and open it. In Geometry and domain choose Direct net for continuous copper, or a reviewed Series path when crossing supported series parts.", expected: "The selected net and workflow match your intended source-to-load path. The picture shows 24Vaux as an example, not a recommended rail.", recovery: "If the required net is missing, inspect import diagnostics and board selection. Equal names on different boards do not connect them.", image: current("pi-geometry", "Current PI geometry and domain step beside the EBrake board", "Domain and analysis path", 63, 29, 36, 34), references: [reference("SOLVER_SETUP_FLOWS", "PI setup steps")] },
      { title: "Assign sources, loads and mesh", action: "Choose Sources and loads. Add source and sink terminals on actual copper; enter reviewed voltage, current and return settings. Then choose Mesh and solver to inspect representation and resolution.", expected: "Terminal locations and quantities match the intended circuit. This picture intentionally has zero terminals: fill these before running.", recovery: "Use exact point picking or current selection where eligible. Do not invent electrical ratings from footprint geometry; correct diagnostics before continuing.", image: current("pi-terminals", "PI sources and loads step with empty source and sink lists", "Source and sink editors", 63, 44, 36, 46), references: [reference("PI_PATH_ANALYSIS", "PI path and terminal assumptions")] },
      { title: "Review before execution", action: "Choose Review and run. Check source/sink counts, mesh target and convergence status. Preview and correct diagnostics, then run only with complete reviewed inputs and an available worker. Inspect returned status before interpreting results.", expected: "The request describes your intended study. The picture has zero terminals and MESH CONVERGENCE NOT RUN; it is not a solved example.", recovery: "Return to the numbered step that owns the missing input. Preserve failed-run diagnostics; an empty or incomplete result is never a pass.", image: current("pi-review", "PI review with zero terminals and mesh convergence not run", "Review counts and convergence warning", 63, 45, 36, 18), references: [reference("SOLVER_STATUS", "Model scope and result evidence"), { topic: "results", label: "Inspect results and probes" }] },
    ],
  },
  {
    id: "si-setup", title: "Prepare an SI request", summary: "Declare the band, signal and reference before opening setup.",
    outcome: "Explicit reviewed inputs for the existing SI setup route; no solver runs in this review panel.",
    prerequisites: ["An imported board and known signal/reference nets.", "Frequency range, rise time and reference impedance appropriate to the intended channel model."],
    steps: [
      { title: "Find the SI input review", action: "Press Ctrl+K and search Review signal integrity setup. Open the matching Workspace request action and read the model limits.", expected: "The Signal integrity request panel explains which inputs are still needed. This is a review assistant before the solver editor.", recovery: "Search the full action name when short terms match unrelated controls. Use the solver setup guide if your required model is not supported.", image: current("si-setup", "Signal integrity request assistant with missing required inputs", "Reviewed SI input form", 63, 33, 36, 64), references: [reference("SI_USER_GUIDE", "SI models and workflow")] },
      { title: "Enter band and reference", action: "Supply start/stop frequency, rise time and reference impedance. Choose the signal and return/reference net. The geometry-derived SI route requires a start of 0 Hz; review eligibility in SI setup.", expected: "Details still needed updates as required values are supplied. The picture shows missing values and does not prescribe a channel configuration.", recovery: "Check units (Hz, seconds and ohms) and the selected board. A power net name is not evidence of a valid signal reference.", image: current("si-setup", "SI frequency, impedance, signal and reference input requirements", "Frequency and net requirements", 63, 33, 36, 64), references: [reference("SI_WORKFLOW", "SI preparation and execution")] },
      { title: "Open setup and verify", action: "When the required details are complete, choose Apply reviewed inputs and open setup. Review ports, reference, model eligibility and runtime there before running. Inspect returned status, S-parameters or supported eye output after execution.", expected: "The existing setup receives reviewed inputs. In the pictured incomplete state the Apply button is disabled; no solver output exists.", recovery: "Read Details still needed, correct those inputs and review again. Do not treat a configured eye screen as protocol compliance or BER evidence.", image: current("si-setup", "SI missing-details checkpoint before applying reviewed inputs", "Missing-details checkpoint", 63, 33, 36, 64), references: [reference("SI_USER_GUIDE", "SI result interpretation"), reference("SOLVER_STATUS", "Supported SI boundaries")] },
    ],
  },
  {
    id: "thermal-setup", title: "Prepare a thermal study", summary: "Choose the model, define heat paths and inspect evidence.",
    outcome: "A thermal setup whose model, powers, environment and heat paths are explicit.",
    prerequisites: ["A loaded board or object inventory and justified material properties.", "Power dissipation and heat paths; transient object runs also require heat capacity."],
    steps: [
      { title: "Choose the intended model", action: "Press Ctrl+K and open Thermal and airflow setup. Read the distinction between the lumped object network, the board plate/layered model and a retained-solid volume study.", expected: "The panel identifies the approximate model. Visible environment geometry and fan markers are setup context, not solved airflow.", recovery: "Choose the model appropriate to your question. A prescribed cooling coefficient cannot establish an enclosure CFD result.", image: current("thermal-setup", "Current Thermal setup with Inputs, Object-network run and Review stages", "Thermal stages and environment", 63, 25, 36, 40), references: [reference("THERMAL_USER_GUIDE", "Thermal model choices")] },
      { title: "Define heat and boundaries", action: "Enter justified power, thermal resistance, exposed areas and cooling assumptions. Review ambient/environment values. For the board model follow Board and materials, Heat and contacts, then Grid and time.", expected: "Heat allocation and paths are explicit for the chosen model. Transient heat capacity and time controls are supplied where required.", recovery: "Correct missing powers, material units or heat paths. Applying a scenario is a boundary preset and must be reviewed before execution.", image: current("thermal-setup", "Thermal environment values and approximate boundary scenario", "Environment and boundary assumptions", 63, 25, 36, 40), references: [reference("THERMAL_WORKFLOW", "Thermal preparation sequence")] },
      { title: "Run and inspect returned evidence", action: "Save the setup and review runtime readiness. Run the admitted model only after inputs pass its checks. Inspect returned temperatures, status and warnings; compare resolution and energy evidence where supplied.", expected: "A completed compatible result reports its actual temperatures and limits. The screenshot says Not run and demonstrates setup only.", recovery: "If the worker is unavailable, resolve the runtime diagnostic. Missing temperatures remain unavailable; use the analysis gallery for separately computed reference examples.", image: current("thermal-setup", "Thermal setup before any object-network or board thermal run", "Setup and model status", 63, 25, 36, 40), references: [reference("ANALYSIS_GALLERY", "Computed reference examples"), reference("SOLVER_STATUS", "Thermal validity limits")] },
    ],
  },
  {
    id: "gerber-source", title: "Load a Gerber study", summary: "Choose artwork, review the stack and retain the source.",
    outcome: "A retained Gerber source setup ready for runtime and mesh checks.",
    prerequisites: ["Original copper Gerber files in top-to-bottom order, or an exported .spike-gerber.json source package.", "Known board bounds and dielectric gaps in millimetres; declared port positions."],
    steps: [
      { title: "Choose the source", action: "Open the EMerge setup and choose Native Gerber study. Add the original copper files, or use Open source package to restore a retained setup.", expected: "The source editor lists the admitted files and the board setup. Gerber artwork does not supply inferred nets or pads.", recovery: "If a file is rejected, retain the diagnostic and check the supported source format before adding it again.", image: current("gerber-source", "Native Gerber study source editor with source file controls expanded", "Source file controls", 3, 8, 94, 35), references: [gerberRef] },
      { title: "Review the stack", action: "Order copper from top to bottom. Enter each dielectric gap and board bounds in millimetres, then review the manual vertical port planes.", expected: "Layer order, dimensions and port settings agree with your source documentation. Values remain explicit rather than inferred from artwork.", recovery: "Correct missing layers or invalid dimensions before loading the study. Check the units against the fabrication stackup.", image: current("gerber-stack", "Native Gerber stack editor showing layer and dielectric settings", "Stack and dimension fields", 3, 16, 94, 63), references: [gerberRef] },
      { title: "Load and inspect", action: "Choose Load Gerber study. Inspect the declared substrate extent and any import diagnostics before continuing.", expected: "The source snapshot retains the artwork and declared stack. Copper display requires native mesh preparation; an empty canonical track list is intentional.", recovery: "If loading is blocked, use the displayed diagnostic. Retained Excellon sources and missing optional dependencies can block execution.", image: current("gerber-stack", "Gerber study editor with explicit stack and load controls", "Review stack before loading", 3, 16, 94, 70), references: [gerberRef] },
      { title: "Keep a recoverable source", action: "Use Export source package to keep the artwork and settings, or save the SPIKE project. Next, check the EMerge runtime and prepare the native Gerber mesh before attempting an RF solve.", expected: "You have a source package or saved project. A loaded source setup establishes neither mesh contact nor a successful solve.", recovery: "If runtime readiness fails, follow the runtime diagnostic and verify the installed compatible engine before preparing the mesh.", image: current("gerber-source", "Gerber source package editor with source retention controls", "Source package controls", 3, 8, 94, 35), references: [gerberRef, reference("SOLVER_STATUS", "Validated solver capabilities")] },
    ],
  },
  {
    id: "layers", title: "Find the right board layer", summary: "Open the layer grid, isolate copper and restore context.",
    outcome: "An intentional layer view with the board identity and display settings checked.",
    prerequisites: ["A loaded board with an imported layer inventory.", "Select the intended board occurrence when inspecting an assembly."],
    steps: [
      { title: "Open the layer choices", action: "Open the layer pull icon at the upper-left viewport edge. Select exactly one board occurrence; the selector hides for multiple selected boards. Use the layer grid to inspect the available layers for the active board.", expected: "The expanded selector names the available layers and current display choice.", recovery: "If the inventory is empty, confirm the active board and review import diagnostics. Restore the main assembly view if you selected the wrong scoped tab.", image: current("layers-expanded", "Expanded viewport layer grid with named board layers", "Layer grid", 2, 8, 73, 70), references: [reference("UI_NAVIGATION", "Viewport navigation")] },
      { title: "Inspect one layer", action: "Choose the copper layer you need. Switch to 2D for layer-focused inspection and use Fit if the board is outside the view.", expected: "The active layer name matches the copper you intended to inspect. Zoom in before expecting fine trace labels to be legible.", recovery: "Check layer visibility and opacity if the view appears empty. A hidden layer is a display setting, not missing source evidence.", image: current("layers-expanded", "Board layer selector showing individual copper choices", "Choose a named layer", 2, 8, 73, 70), references: [reference("USER_TASK_SEQUENCES", "Layout inspection sequence")] },
      { title: "Adjust opacity and net names", action: "Scroll upward on a layer button to increase opacity and downward to decrease it. The button briefly shows 0–100, returning to its layer name one second after scrolling stops. Scrolling All applies its opacity to all layers. Expand Net names downward to show or hide labels.", expected: "The selected board's layer appearance changes without modifying its source geometry. The expanded Net names switch is visible in the picture.", recovery: "If labels remain hard to read, check zoom and layer visibility. Use Reset view for defaults; do not adjust another board's layers by accident.", image: current("layers-expanded", "Expanded board layer grid with downward Net names controls", "Layers, opacity and Net names", 0.3, 10, 38.5, 29), references: [reference("UI_NAVIGATION", "Layer display and selection context")] },
      { title: "Restore board context", action: "Choose All when you need the full layer context. Recheck the selected object, layer and board occurrence before using a selection as an analysis anchor.", expected: "The layer choice and visible scene agree. Display choices do not create connectivity between board occurrences.", recovery: "Use Fit, restore hidden layers and confirm the selected board. Review the source import if expected geometry is still absent.", image: current("layers-expanded", "Expanded layer grid used to restore the board layer context", "Layer visibility choices", 2, 8, 73, 70), references: [reference("USER_TASK_SEQUENCES", "Selection and assembly context")] },
    ],
  },
  {
    id: "mechanical", title: "Measure and section an assembly", summary: "Enter exact coordinates and inspect a visual cut.",
    outcome: "A coordinate measurement and an explicit visual section with known limitations.",
    prerequisites: ["A loaded project containing mechanical parts with renderable geometry.", "Assembly coordinates in millimetres; identify the intended part occurrence."],
    steps: [
      { title: "Open Measure", action: "Click Mechanical objects, sections and dimensions at the upper-right of the viewport to pin its controls. Choose Measure.", expected: "The Measure tab exposes point A and point B. Switching tabs retains the current inputs.", recovery: "If the control is absent, confirm the project contains mechanical parts. A listed part still needs renderable geometry to appear.", image: current("mechanical-measure", "Mechanical controls open on Measure with point A and B coordinate fields", "Measure and coordinate fields", 56, 8, 42, 78, true), references: [mechanicalRef] },
      { title: "Set both endpoints", action: "Enter XYZ coordinates for A and B in assembly millimetres, or select an object and use Set A/B from selection to capture its transformed occurrence origin.", expected: "The panel displays distance and signed differences B minus A. The viewport shows the endpoint markers and connecting line.", recovery: "Check coordinate units and occurrence transforms if the distance is unexpected. Origin capture is not face snapping or minimum-clearance measurement. Use Clear to start again.", image: current("mechanical-measure", "Mechanical measurement panel displaying exact endpoint entries and distance controls", "Endpoint entries and measurement", 56, 8, 42, 78, true), references: [mechanicalRef] },
      { title: "Apply a visual section", action: "Choose Section, select XY, XZ or YZ, set the signed offset in millimetres and enable the section. Flip retained side changes the kept half-space.", expected: "The visible geometry is clipped by the selected plane. The visual cut is uncapped and does not create a closed section solid or solver mesh.", recovery: "Disable the section to restore the full view. Check the plane direction, offset and retained side when the entire object disappears.", image: current("mechanical-section", "Mechanical Section tab showing explicit section plane and offset controls", "Section plane controls", 56, 8, 42, 78, true), references: [mechanicalRef] },
    ],
  },
  {
    id: "fields", title: "Inspect field display controls", summary: "Locate fields, choose a quantity and check its source.",
    outcome: "A field display whose dataset, units and status you can identify.",
    prerequisites: ["An admitted exported field dataset, or a completed compatible result that provides fields.", "Dataset provenance, units and run status available for review."],
    steps: [
      { title: "Open Fields", action: "Click the compact Fields control in the viewport toolbar. Import a supported field JSON file, or use Show fields in main viewport from a compatible CFD result.", expected: "The expanded field controls describe the available display settings. The pictured controls do not establish that a numerical result exists.", recovery: "If a file is rejected, check its declared contract and the field format reference. A screenshot or board import cannot supply missing result data.", image: current("viewport-fields", "Expanded Fields controls in the SPIKE viewport", "Fields display controls", 45, 8, 53, 76), references: [fieldsRef] },
      { title: "Choose the quantity", action: "With an admitted dataset loaded, select an available quantity and Points or Voxels. Review units and opacity; voxels require supplied cell dimensions.", expected: "Only quantities supplied by the dataset are available. Board geometry remains visible enough to check spatial alignment.", recovery: "If a quantity is unavailable, inspect the dataset contents and solver capability. Do not interpret an unavailable quantity as zero.", image: current("viewport-fields", "Field display settings expanded for quantity and rendering choices", "Quantity and display settings", 45, 8, 53, 76), references: [fieldsRef, { topic: "results", label: "Results and probes" }] },
      { title: "Check evidence before interpreting", action: "Review the dataset source, result status, units and warnings. Use saved playback only when the dataset supplies frames, and export field data when you need to retain the admitted cells and frames.", expected: "Your interpretation names the actual dataset and its limits. Playback reviews saved frames; it does not run a transient solver.", recovery: "For an empty display, check the selected quantity, cut and opacity. Return to the source result for failed or incomplete runs.", image: current("viewport-fields", "Expanded viewport Fields settings for inspecting data display choices", "Review field display state", 45, 8, 53, 76), references: [fieldsRef, reference("RESULT_VISUALIZATION_AND_LIMITS", "Result interpretation and limits")] },
    ],
  },
  {
    id: "commands", title: "Find a command or its help", summary: "Search the interface and follow a focused reference.",
    outcome: "The intended command located, with prerequisites and recovery guidance in reach.",
    prerequisites: ["The SPIKE workspace is open. Some commands require a selected board, object or compatible runtime."],
    steps: [
      { title: "Search by task", action: "Press Ctrl+K and type part of a task, command, part or net name. Read the matching action and its context before choosing it.", expected: "Search offers available matching destinations and actions. The screenshot records command discovery, not solver setup.", recovery: "Try a shorter term or use Menu search and All actions. Check your active workspace if the intended action is unavailable.", image: workspace(true), references: [reference("COMMAND_ACCESS", "Command access routes")] },
      { title: "Check the destination", action: "Use Tab to complete the highlighted suggestion and Enter to choose it. Review the opened tool and complete its prerequisites before using its action buttons.", expected: "The destination corresponds to your chosen command. A disabled control keeps its existing selection, input or runtime requirements.", recovery: "Use Back or Escape in Menu to return one level. Restore a hidden editor through Show hidden tools or command search.", image: workspace(false), references: [reference("UI_NAVIGATION", "Navigation and panel recovery")] },
      { title: "Read the focused help", action: "Use a tool's contextual help control when available. In Help, follow the workflow reference or search a control label or full diagnostic code.", expected: "Help explains the current task, expected output and recovery. The picture shows the Help reader open on Gerber source instructions. Return to the tool to perform the action; reading Help does not execute it.", recovery: "If a command remains blocked, retain the complete diagnostic code and review its prescribed recovery before retrying.", image: current("section-help", "SPIKE Help reader displaying Gerber source, stack and review instructions", "Workflow instructions in Help", 39, 12, 40, 80), references: [reference("HELP_FAQ", "FAQ and recovery"), reference("ERROR_CODE_CATALOG", "Diagnostic codes")] },
    ],
  },
];

export interface HelpGuideState { flowId: string | null; step: number }
export type HelpGuideAction = { type: "choose"; flowId: string } | { type: "home" } | { type: "next" | "back" } | { type: "step"; index: number };
export const initialHelpGuideState: HelpGuideState = { flowId: null, step: 0 };
export function helpGuideReducer(state: HelpGuideState, action: HelpGuideAction): HelpGuideState {
  if (action.type === "home") return initialHelpGuideState;
  if (action.type === "choose") return helpGuidedFlows.some(flow => flow.id === action.flowId) ? { flowId: action.flowId, step: 0 } : state;
  const flow = helpGuidedFlows.find(item => item.id === state.flowId);
  if (!flow) return initialHelpGuideState;
  const index = action.type === "step" ? action.index : state.step + (action.type === "next" ? 1 : -1);
  if (!Number.isInteger(index)) return state;
  return { flowId: flow.id, step: Math.max(0, Math.min(index, flow.steps.length - 1)) };
}
