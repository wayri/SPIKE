import { completedScriptViewportRun, type ScriptViewportRun } from "./scriptViewportImport";
import { cloneImportedStudies, prepareStudyDataset, preflightStudyRunCapture, preflightStudyDatasetUpdate } from "./studyWorkspaceModel";
import { ownsKeyboardInput } from "./shortcutContext";
import AssemblyQuickBar from "./AssemblyQuickBar";
import ViewportNotifications from "./ViewportNotifications";
import CommandStrip from "./CommandStrip";
import ToolRestoreShelf, { type ToolRestoreItem } from "./ToolRestoreShelf";
import { minimizeTool, removeMinimizedTool } from "./minimizedTools";
import AssemblyToolHost from "./AssemblyToolHost";
import { focusAssemblyToolWindow } from "./assemblyToolWindows";
import type { AssemblyToolAction, AssemblyToolKind, AssemblyToolSnapshot } from "./assemblyToolWindowModel";
import ModelResolverPanel from "./ModelResolverPanel";
import { assemblyNetHighlight, type AssemblyHighlightSeed } from "./assemblyNetHighlight";
import DataTable from "./DataTable";
import { placeAssemblyBoard } from "./BoardPlacementTool";
import { useAssemblyBoardVisuals } from "./useAssemblyBoardVisuals";
import { assemblyExplodeOffsets, assemblyDisplayHarnesses } from "./assemblyDisplayState";
import { extractAssemblySnapTargets, snapOccurrenceTransform, type AssemblySnapTarget } from "./assemblySnapTargets";
import { normalizeAssemblyResultOverlays } from "./assemblyResultOverlays";
import { useAssemblySavedResultOverlays } from "./useAssemblySavedResultOverlays";
import { openDetachedToolWindow, updateDetachedToolWindow, closeDetachedToolWindow, closeAllDetachedToolWindows, type DetachedToolAction, type ToolWindowKind } from "./detachedToolWindows";
import { buildDetachedProbeSnapshot, buildDetachedResultsSnapshot, buildDetachedTraceSnapshot } from "./resultsToolSnapshots";
import ProbeResultsTable from "./ProbeResultsTable";
import { evaluateProbeFormulas, probeResultsCsv, type ProbeFormulaRow } from "./probeCalculations";
import { buildProbeRows } from "./probeCalculations";
import { normalizeProbeTableState, assignProbeReferenceIds } from "./probeTableState";
import BoardImportPanel from "./BoardImportPanel";
import { analysisFailure } from "./analysisFailure";
import { workspaceIssues } from "./workspaceIssues";
import { createResultPackage, mergeProjectSnapshot, readResultPackage, retainOpaqueResultState, isSupportedSavedResult, withoutSavedResults } from "./projectSnapshotState";
import StudyManager from "./StudyManager";
import McpBridgePanel from "./McpBridgePanel";
import { createMcpAnalysisConversation, type McpLoadedContext } from "./mcpAnalysisConversation";
import "./mcpBridgePanel.css";
import { listenMcpBridge, respondMcpBridge, type McpBridgeRequest } from "./workerBridge";
import { addStudyCase, createStudy, duplicateStudyCase, moveStudyCase, normalizeStudies, removeStudy, removeStudyCase, updateStudy, updateStudyCase, type SimulationStudy, type SimulationStudyCase, type StudyJsonObject } from "./simulationStudies";
import { resultSolvedForPresentation } from "./resultAdmission";
import { hydrateProjectArtifacts, restoreBoardVisuals, serializeBoardVisuals } from "./projectPersistenceArtifacts";
import { useBoardVisualImport } from "./useBoardVisualImport";
import WorkflowSchematic from "./WorkflowSchematic";
import { thermalSchematic } from "./workflowSchematics";
import type { Group } from "three";
import { disposeEmiGeometry } from "./emiChamber";
import { EmiChamberWorkspace } from "./EmiChamberWorkspace";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import {
  Activity, AlertTriangle, ArrowDown, ArrowLeft, ArrowRight, ArrowRightLeft, ArrowUp, AudioWaveform,
  BadgeAlert, BadgeCheck, BarChart3, BatteryCharging, Bell, Binary, Blend, BookOpen, BookOpenCheck, Box,
  Boxes, Cable, ChartArea, ChartColumnIncreasing, ChartNetwork, ChartNoAxesColumnIncreasing, ChartNoAxesCombined, ChartScatter,
  ChartSpline, CheckCircle2, ChevronDown, CircleHelp, CircuitBoard, Clipboard, ClipboardCheck, CloudSun,
  Component, Copy, CopyPlus, Cpu, Crosshair, Cuboid, Download, Eye, EyeOff, Fan, FileArchive,
  FileChartColumn, FileCog, FileInput, FileOutput, FilePlus, FileSpreadsheet, Flame, Focus, FolderOpen,
  GalleryVertical, Gauge, GitCompareArrows, Grid3X3, Hand, Keyboard, Layers2, Layers3, LayoutDashboard,
  LibraryBig, ListChecks, ListTree, Magnet, MapPinPlus, MemoryStick, Microchip, MousePointer2,
  Move3D, MoveUpRight, Network, Omega, Orbit, PackageOpen, PackageSearch, PanelBottom, PanelLeft,
  PanelRight, PanelTop, Pause, Pin, PinOff, Play, Plug, PlugZap, Plus, Printer, Puzzle, Radar, RadioTower,
  Redo2, RefreshCw, Route, RouteOff, SatelliteDish, Save, ScanEye, ScanLine, ScanSearch, Search,
  ServerCog, Settings2, ShieldAlert, ShieldCheck, SlidersHorizontal, Spline, Split, SquareTerminal,
  Table2, TableProperties, Thermometer, ThermometerSun, Trash2, TrendingDown, Undo2, Upload, Waves,
  Waypoints, Wind, Workflow, X, XCircle, Zap, ZoomIn, ZoomOut, Axis3D, Combine
} from "./icons";
import BoardViewport, { AnalysisTerminalMarker, BoardObject, ModelLoadStatus, previewViewportTarget, RenderTelemetry, SelectionFilter, ViewportContextRequest } from "./BoardViewport";
import { ParsedBoard, ParsedLayerDefinition, ParsedPad, ParsedStackupLayer } from "./boardParser";
import { parseDesignSourceOffThread } from "./boardImport";
import { normalizedDesignSnapshot, normalizedSolverDesign } from "./normalizedBoard";
import { hydrateNormalizedSnapshot, compressNormalizedSnapshot } from "./normalizedSnapshotTransport";
import HarnessDocumentEditor from "./HarnessDocumentEditor";
import ImportSourceDialog from "./ImportSourceDialog";
import { classifyOpenSource, type ImportSourceKind, type PreparedSource } from "./importSourceRouting";
import { readApprovedSourceFile, selectNativeWorkbenchFile, type NativeSelectedFile } from "./workerBridge";
import TetraMeshPanel from "./TetraMeshPanel";
import ExtensionWorkspacePanel from "./ExtensionWorkspacePanel";
import { extensionWorkspaceRoutes, type ExtensionWorkspace } from "./ExtensionWorkspaceRoutes";
import { OpenEMSSetupForm, defaultOpenEMSSetup, openEMSParameters } from "./OpenEMSExtension";
import { ExtensionArtifacts, McadOptions } from "./ExtensionArtifacts";
import { defaultEMergeSetup, EMergeResultPlot, EMergeSetupForm, EMergeScriptPreview, EMergeCapabilityInventory, emergeParameters, type EMergeSetup } from "./EMergeExtension";
import EMergeGerberImport from "./EMergeGerberImport";
import { activeGerberSource, type EMergeGerberSource } from "./emergeGerberSource";
import { normalizeOpenEMSSetup, normalizeEMergeSetup } from "./extensionWorkflowSettings";
import { ACPowerIntegrityEffects } from "./ACPowerIntegrityEffects";
import EMViewportResultManager from "./EMViewportResultManager";
import { buildEMViewportData, availableEMQuantities, emResultFrequencies, emViewportPayload, defaultEMViewportSettings, type EMViewportSettings, type EMViewportRecord } from "./emViewportResults";
import { OptycalSetupForm, OptycalScriptPreview, OptycalResultPlot } from "./OptycalExtension";
import { defaultOptycalSetup, optycalParameters, admitOptycalSource, type OptycalSetup } from "./optycalStudy";
import AnalysisGuide, { type GuideDestination } from "./AnalysisGuide";
import { selectNativeImportFile } from "./workerBridge";
import { configureBundledVisuals, configureKnownVisuals } from "./boardVisualBundles";
import { extractNetGeometry } from "./netGeometry";
import { emptyProcessResources, ProcessResources, sampleProcessResources, systemMemoryPercent } from "./resourceMonitor";
import { planResourceCapacity, ResourceCapacityPlan } from "./resourceCapacity";
import { assemblyAdmissionParams, assemblyAnalysisScope, requireAdmittedAssembly, requireSupportedAssemblyPhysics, type AssemblyAnalysisScope, type AssemblyWorkload } from "./assemblyAdmission";
import { cancelLocalWorker, cancelLocalWorkerCleanup, closeDesktopWindow, isDesktopShell, openNativeTextFile, readApprovedResultFile, runLocalWorker, runNativeProjectWorker, saveNativeTextFile, selectNativeProjectSavePath, subscribeDesktopCloseRequested, takeStartupProject, verifyNativeProjectManifestSignature, WorkerActivity } from "./workerBridge";
import { emptyTopology, extractTopologyFromBoard, PowerTreeAnalysisPlan, TopologyDomain, TopologyModel, TopologyNode } from "./powerTree";
import { compilePiPaths, compilePiSeriesSolveHandoff, PiPathTerminalAnchor } from "./piPath";
import { attachPiPathComponentBridges, combinePiPathPreflights, combinePiPathSegmentExtractions, createPiPathSegmentExtractionRequests, PiPathAnalysisRequest } from "./piPathCircuit";
import { stackupBandHeight, stackupColor } from "./stackupVisual";
import { applyStackupToSpiDeR } from "./designStackup";
import LayerManager from "./LayerManager";
import FlexBoardManager from "./FlexBoardManager";
import EMergeRuntimeUpdater from "./EMergeRuntimeUpdater";
import { useEMergeRuntimeUpdates } from "./useEMergeRuntimeUpdates";
import { resolveBoardCopperLayers } from "./copperLayerSelection";
import { captureViewport, encodeGif } from "./gifExport";
import { openReportPreviewWindow, closeReportPreviewWindow, focusReportPreviewWindow } from "./reportPreviewWindow";
import BenchmarkCenter from "./BenchmarkCenter";
const HelpCenter = lazy(() => import("./HelpCenter"));
import AboutDialog from "./AboutDialog";
import { APP_VERSION } from "./appVersion";
import ProjectManager, { RecentProject } from "./ProjectManager";
import ProjectUpgradeDialog from "./ProjectUpgradeDialog";
import SpiceWorkbench from "./SpiceWorkbench";
import { admitContextScript, CONTEXT_SCRIPT_EVENT, openContextScript, type ContextScript } from "./contextScript";
const ScriptResultViewport = lazy(() => import("./ScriptResultViewport"));
const PythonWorkspace = lazy(() => import("./PythonWorkspace"));
import { admittedPythonUiActions, pythonBoardNets, pythonWorkspaceContext, type PythonUiAction } from "./pythonWorkspaceContext";
import { defaultSpiceWorkspace, normalizeSpiceWorkspace, SpiceWorkspace } from "./spiceWorkspace";
import UniversalSettingsModal from "./UniversalSettingsModal";
import IconGallery from "./IconGallery";
import UniversalSearch, { UniversalSearchItem } from "./UniversalSearch";
import SceneNavigator, { SceneNavigatorAction } from "./SceneNavigator";
import McadAttachmentPanel from "./McadAttachmentPanel";
import FreecadCollaboration from "./FreecadCollaboration";
import { assemblyPartViewportStates as initialAssemblyPartViewportStates, createAssemblySceneModels, createAssemblySelectorPreviewModels, DEFAULT_ASSEMBLY_SECTION, normalizeAssemblyDesigns, normalizeAssemblyIr, normalizeModelIndex, visualModelIds } from "./mcadAssembly";
import type { AssemblyDesigns, AssemblyIr, AssemblyPartViewportLoadState, AssemblySceneModel, AssemblySection, AssemblySelectorPreviewModel, ModelIndex } from "./mcadAssembly";
import { netOccurrences } from "./assemblyBoardManagerModel";
import { buildVirtualBoardVisualization, buildVirtualHarnessVisualization } from "./harnessVisualization";
import type { VirtualBoardVisual, VirtualHarnessVisual } from "./harnessVisualization";
import { normalizeAssemblyPackageShapes } from "./assemblyPackageShapes";
import type { AssemblyPackageShapesIndex, TopologyReference } from "./assemblyPackageShapes";
import type { AccelerationCatalogEntry, ExternalCaseState, ExternalEngineCatalogEntry, SolverManagerCatalog } from "./ExternalEngineCenter";
import {
  defaultEmiSetup, EmiDashboard, EmiFieldResult, EmiPreflight, EmiScreening, EmiSetup, EmiSetupPanel, EmiSetupSection,
  normalizeEmiFieldResult, normalizeEmiSetup,
} from "./EmiWorkbench";
import { AppSettings, loadAppSettings, saveAppSettings, translate } from "./appSettings";
import { createProjectPackage, parseProjectPackage, projectFileName } from "./projectPackage";
import { DockTabId, normalizeWorkspaceState, Viewport2DState, Viewport3DCameraState, ViewportRestoreCommand, WorkspaceState } from "./workspaceState";
import BondManager, { BondRecord, BondValidationResult } from "./BondManager";
import { bondsForSolver, inferComponentBonds, validateComponentBonds } from "./componentBonding";
import {
  defaultResultVisualization, normalizeSolverResult, PdnCandidateRequest, PdnReview, resultAtFrame, resultModeAvailable, ResultViewMode, ResultVisualization, SolverResultBundle, ViaModel,
} from "./analysisResults";
import { extensionAnalysisResult } from "./extensionAnalysisResult";
import { emergeRadiationPatterns, savedEmergeRadiationPreview } from "./emergeRadiationView";
import { availableViewportResultModes, resultHasExtractedNetworks, viewportContextLabel } from "./viewportContext";
import { asThermalScenario, defaultThermalSceneVisibility, ThermalFan, ThermalHeatsink, ThermalSceneVisibility } from "./thermalScene";
import { thermalFieldResultPreview } from "./thermalResultFields";
import ThermalAssemblyEditor from "./ThermalAssemblyEditor";
import ThermalBoundaryEditor from "./ThermalBoundaryEditor";
import ThermalInputImport from "./ThermalInputImport";
import BoardThermalPanel, { validBoardThermalResult, type BoardThermalRequest } from "./BoardThermalPanel";
import ThermalTransientOverlay from "./ThermalTransientOverlay";
import ThermalHardwareEditor from "./ThermalHardwareEditor";
import ThermalEnvironmentPanel from "./ThermalEnvironmentPanel";
import type { ThermalEnvironmentId } from "./thermalEnvironments";
import { normalizeThermalFans, normalizeThermalHeatsinks } from "./thermalHardware";
import { normalizeThermalElements, normalizeThermalLinks, screenThermalElements, thermalAssemblyIssues, thermalMaterials, thermalSurfaceFinishes, ThermalElement, ThermalLink } from "./thermalAssembly";
import { nativeThermalInputs, normalizeThermalBoundaries, type ThermalBoundary } from "./thermalBoundaries";
import { numericExtent, numericMaximum, numericMinimum } from "./numericRange";
import TransientWaveformEditor from "./TransientWaveformEditor";
import PiSiTerminalEditor from "./PiSiTerminalEditor";
import {
  formatEngineering, parsePwlPoints, parseSpiceNumber, TransientWaveformKind, tryParseSpiceNumber,
} from "./transientWaveform";
import {
  defaultShortcuts, fixedShortcuts, normalizedShortcutKey, ShortcutAction, shortcutGroups, shortcutLabels,
} from "./shortcutCatalog";
import { validateSiProtocolSuite, type SiProtocolSuite } from "./siProtocolSuites";
import { throughHoleComponentRefs, uniqueViewportNets } from "./viewportPerformance";
import SimulationWorkspace from "./SimulationWorkspace";
import type { SimulationDomain } from "./sharedSimulationWorkspace";
import { openBugReport } from "./bugReport";

const TopologyEditor = lazy(() => import("./TopologyEditor"));
const NetManager = lazy(() => import("./NetManager"));
const TraceResultsWorkbench = lazy(() => import("./TraceResultsWorkbench"));
const ResultVisualizationPanel = lazy(() => import("./ResultVisualizationPanel"));
const SParameterWorkbench = lazy(() => import("./SParameterWorkbench"));
const ExternalEngineCenter = lazy(() => import("./ExternalEngineCenter"));
const SiProtocolSuiteWorkbench = lazy(() => import("./SiProtocolSuiteWorkbench"));

type RibbonTab = "Home" | "Mesh" | "Solve" | "PI" | "HF / SI" | "EM" | "Thermal" | "Probes" | "Results" | "Reports" | "Extensions" | "Settings";
type DockTab = DockTabId;
type ActivityLevel = "info" | "success" | "warning" | "error";
type ActivityEntry = {
  id: number;
  timestamp: string;
  level: ActivityLevel;
  source: string;
  message: string;
};
type ResultRecord = { id: string; label: string; bundle: SolverResultBundle };
type DiagnosticIssue = {
  code?: string;
  severity: string;
  message: string;
  path?: string;
  suggestion?: string;
  status?: string;
};
type LayerName = string;
type SolverCatalogEntry = {
  id: string;
  name: string;
  state: string;
  analyses: string[];
  formulations: string[];
  capabilities?: string[];
  candidate_capabilities?: string[];
  model_status: string;
  reason?: string;
  runnable?: boolean;
};
type ExtensionCatalogEntry = {
  id: string;
  name: string;
  version: string;
  provider: string;
  description: string;
  license: string;
  state: string;
  trusted: boolean;
  bundled: boolean;
  managed?: boolean;
  can_remove?: boolean;
  install_state?: string;
  permissions: string[];
  ui?: { menu_bar?: boolean; title_bar?: boolean; menu_items?: string[] };
  contributes: Record<string, { id: string; name: string; description?: string; definition?: unknown; input_schema?: Record<string, any>; output_contract?: string }[]>;
};
type TerminalProfile = TransientWaveformKind;
type PiTerminal = {
  id: string;
  name: string;
  x: string;
  y: string;
  layer: string;
  layers: string[];
  anchorId: string;
  anchorType: string;
  net: string;
  value: string;
  profile: TerminalProfile;
  profileData: string;
  profileInitial: string;
  profileDelayS: string;
  profileRiseS: string;
  profileWidthS: string;
  profileFallS: string;
  profilePeriodS: string;
  contactResistance: string;
  packageResistance: string;
};
type BatchAnalysisMode = "dc" | "ac" | "transient" | "skip";
type ReturnPathMode = "implicit" | "explicit" | "isolated_secondary";
type ReturnPathSetup = {
  mode: ReturnPathMode;
  net: string;
  domainId: string;
  sources: PiTerminal[];
  loads: PiTerminal[];
};
type CouplingScope = "adjacent" | "radius" | "all_board";
type CouplingSetup = {
  enabled: boolean;
  electricField: boolean;
  magneticField: boolean;
  scope: CouplingScope;
  radiusMm: string;
  includeTraces: boolean;
  includePlanes: boolean;
  includeZones: boolean;
  crossLayer: boolean;
};
type BatchNetJob = {
  id: string;
  net: string;
  mode: BatchAnalysisMode;
  solverId: string;
  sources: PiTerminal[];
  loads: PiTerminal[];
  coupling: CouplingSetup;
};
export type LoopExtractionSetup = {
  id: string;
  name: string;
  forwardNet: string;
  returnNet: string;
  forwardStartPadId: string;
  forwardEndPadId: string;
  returnStartPadId: string;
  returnEndPadId: string;
  pathGroupId: string;
};
type PiSetup = {
  net: string;
  powerPathId: string;
  sources: PiTerminal[];
  loads: PiTerminal[];
  returnPath: ReturnPathSetup;
  meshDimension: "surface_2_5d" | "volume_3d";
  meshTargetMm: string;
  zoneCellMm: string;
  maxPreviewCells: string;
  viaModel: "extracted" | "plated_cylinder";
  viaPlatingMm: string;
  frequencyStart: string;
  frequencyStop: string;
  frequencyPoints: string;
  transientStopS: string;
  transientTimeStepS: string;
  transientTimeStepMode: "auto" | "manual";
  transientOutputDecimation: string;
  transientOutputDecimationMode: "auto" | "manual";
  transientPlaybackFps: string;
  transientInitialCondition: "zero" | "operating_point";
  transientMaxSolverTimeS: string;
  transientMemoryBudgetMb: string;
  transientCapacitanceModel: "auto" | "stackup_shunt" | "none";
  transientVisualSampleLimit: string;
  skinEffect: boolean;
  proximityEffect: boolean;
  roughnessModel: "none" | "hammerstad" | "huray" | "gradient";
  roughnessUm: string;
  hurayNoduleRadiusUm: string;
  huraySurfaceRatio: string;
  batchJobs: BatchNetJob[];
  loopExtractions: LoopExtractionSetup[];
};
type AnalysisSummary = { maxDropMv: number; maxDensity: number; status: string; modelStatus: string } | null;
type BatchResult = { net: string; mode: Exclude<BatchAnalysisMode, "skip">; status: string; modelStatus: string; detail: string; bundle?: SolverResultBundle };
type ConvergenceReport = {
  status: "passed" | "failed_to_converge" | "failed";
  can_sign_off: boolean;
  levels: { factor: number; target_size_mm: number; status: string; node_count?: number; edge_count?: number }[];
  comparisons: { metric: string; relative_delta: number | null; absolute_delta?: number | null; tolerance: number; absolute_tolerance?: number | null; pass_basis?: "relative" | "absolute" | "none"; status: string; required?: boolean; meaning?: string }[];
  result?: unknown;
};
type OperationKind = "preview" | "convergence" | "dc" | "ac" | "transient" | "batch";
type OperationDisplay = { label: string; elapsedSeconds: number; estimateSeconds?: number } | null;
type OperationTiming = {
  kind: OperationKind;
  label: string;
  startedAt: number;
  estimateSeconds: number;
  meshCells: number;
  jobs: number;
};
type PiPanelDock = "left" | "right" | "bottom" | "float";
type PiPanelFrame = { x: number; y: number; width: number; height: number };
type RevisionComparison = {
  baselineName: string;
  candidateName: string;
  status: "pass" | "regression";
  tolerancePercent: number;
  metrics: { key: string; label: string; unit: string; baseline: number; candidate: number; changePercent: number; status: "pass" | "improved" | "regression" }[];
};
const formatRunDuration = (seconds: number) => {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
};
const timingStorageKey = (kind: OperationKind) => `spike.operation-timing.${kind}`;
const estimateOperationSeconds = (kind: OperationKind, meshCells: number, jobs = 1) => {
  const cells = Math.max(100, Number.isFinite(meshCells) ? meshCells : 10000);
  try {
    const previous = JSON.parse(localStorage.getItem(timingStorageKey(kind)) ?? "null") as { seconds?: number; meshCells?: number; jobs?: number } | null;
    if (previous?.seconds && previous.meshCells && previous.jobs) {
      const scale = Math.max(0.25, Math.min(4, (cells * jobs) / (previous.meshCells * previous.jobs)));
      return Math.max(1, Math.round(previous.seconds * (0.35 + 0.65 * scale)));
    }
  } catch { /* A blocked local store only disables calibrated estimates. */ }
  const model: Record<OperationKind, { base: number; secondsPer10k: number }> = {
    preview: { base: 2, secondsPer10k: 2 },
    convergence: { base: 8, secondsPer10k: 10 },
    dc: { base: 3, secondsPer10k: 4 },
    ac: { base: 8, secondsPer10k: 18 },
    transient: { base: 10, secondsPer10k: 24 },
    batch: { base: 4, secondsPer10k: 5 },
  };
  return Math.max(1, Math.round((model[kind].base + model[kind].secondsPer10k * cells / 10000) * Math.max(1, jobs)));
};
const recordOperationTiming = (kind: OperationKind, seconds: number, meshCells: number, jobs = 1) => {
  try {
    localStorage.setItem(timingStorageKey(kind), JSON.stringify({ seconds, meshCells: Math.max(100, meshCells), jobs: Math.max(1, jobs), recordedAt: new Date().toISOString() }));
  } catch { /* Timing history is optional. */ }
};
const tabs: { name: RibbonTab; icon: typeof Activity }[] = [
  { name: "Home", icon: FolderOpen }, { name: "Mesh", icon: Grid3X3 }, { name: "Solve", icon: Play },
  { name: "PI", icon: BatteryCharging }, { name: "HF / SI", icon: AudioWaveform },
  { name: "EM", icon: SatelliteDish }, { name: "Thermal", icon: ThermometerSun }, { name: "Probes", icon: Crosshair },
  { name: "Results", icon: ChartArea }, { name: "Reports", icon: FileChartColumn }, { name: "Extensions", icon: Puzzle }, { name: "Settings", icon: Settings2 }
];
const initialLayers: Record<LayerName, boolean> = { "Board body": true, "F.Cu": true, "In1.Cu": true, "In2.Cu": true, "In3.Cu": true, "B.Cu": true };
const fallbackSolverCatalog: SolverCatalogEntry[] = [
  { id: "spike.routed_dc", name: "SPIKE Copper Geometry DC", state: "available", analyses: ["dc"], formulations: ["resistive_network"], capabilities: ["dc_resistance", "tracks", "through_vias", "pads", "copper_zones", "package_resistance", "contact_resistance", "explicit_return_path", "isolated_power_domain"], model_status: "approximate" },
  { id: "spike.peec_rl_transient", name: "SPIKE Geometry PEEC RLC Transient", state: "experimental", analyses: ["transient"], formulations: ["peec_rl_transient"], capabilities: ["transient_waveforms", "geometry_transient", "partial_inductance", "distributed_capacitance", "voltage_drop", "current_density", "tracks", "through_vias", "pads", "copper_zones", "package_resistance", "contact_resistance", "explicit_return_path", "isolated_power_domain"], model_status: "approximate" },
  { id: "spike.peec_2_5d", name: "SPIKE Quasi-static PEEC 2.5D", state: "experimental", analyses: ["ac", "broadband_hf"], formulations: ["peec_2_5d"], capabilities: ["rl_extraction", "rlcg_extraction", "partial_inductance", "capacitance_extraction", "dielectric_loss", "frequency_dependent_impedance", "skin_effect", "surface_roughness", "tracks", "through_vias", "pads", "copper_zones", "hybrid_mesh"], model_status: "approximate" },
  { id: "spike.native_mna_workspace", name: "SPIKE Native MNA Workspace", state: "workspace_only", analyses: ["spice", "dc_operating_point", "ac", "transient"], formulations: ["modified_nodal_analysis"], capabilities: ["reviewed_linear_workspace", "dc_operating_point", "ac_linear_circuit", "transient_linear_circuit", "independent_sources", "dependent_sources", "explicit_netlist"], model_status: "experimental", runnable: false, reason: "Available only from the SPICE Workspace after explicit composition and validation. It supports reviewed linear R/L/C circuits and independent/dependent sources; nonlinear semiconductor models, arbitrary subcircuits, and general board PI solving remain outside this route." },
  { id: "spike.field_circuit_cosimulation", name: "SPIKE PEEC + Native MNA Co-simulation", state: "workspace_only", analyses: ["spice", "dc_operating_point", "ac", "transient"], formulations: ["fixed_point_field_circuit"], capabilities: ["reviewed_peec_rlcg", "explicit_topology", "field_circuit_iteration", "circuit_field_feedback", "explicit_netlist"], model_status: "experimental", runnable: false, reason: "Available only from the SPICE Workspace when one reviewed PEEC extraction supplies explicit endpoint mappings. Fixed-point coupling is experimental; it does not support inferred topology changes, nonlinear device solving, or validated general PCB PI co-simulation." },
];
const workspaceOnlySolverCatalog = fallbackSolverCatalog.filter((solver) => solver.state === "workspace_only");
const mergeSolverCatalog = (runtimeCatalog: SolverCatalogEntry[]) => {
  const runtimeIds = new Set(runtimeCatalog.map((solver) => solver.id));
  return [...runtimeCatalog, ...workspaceOnlySolverCatalog.filter((solver) => !runtimeIds.has(solver.id))];
};
const fallbackExtensionCatalog: ExtensionCatalogEntry[] = [{
  id: "spike.example.net-inventory",
  name: "Net Inventory",
  version: "1.0.0",
  provider: "SPIKE SDK",
  description: "Example general-purpose extension that summarizes normalized design nets.",
  license: "MIT",
  state: "available",
  trusted: true,
  bundled: true,
  permissions: ["design.read"],
  contributes: {
    applications: [{ id: "net-inventory-app", name: "Net Inventory" }],
    commands: [{ id: "summarize-nets", name: "Summarize nets" }],
    reports: [{ id: "net-inventory-report", name: "Net inventory report" }],
  },
}];
const fallbackExternalEngines: ExternalEngineCatalogEntry[] = [{
  id: "external.openems",
  name: "openEMS FDTD",
  role: "PCB full-wave setup, single-excitation S-parameters, and opt-in NF2FF far-field execution",
  license: "GPL-3.0-or-later; SPIKE adapter Apache-2.0",
  homepage: "https://docs.openems.de/",
  executable: "",
  version: "",
  state: "unavailable",
  interface: "python_process",
  capabilities: ["fdtd_3d_experimental", "pcb_conductor_export", "dielectric_slab_export", "explicit_lumped_ports", "single_excitation_s_parameters", "csxcad_setup", "nf2ff_far_field"],
  actions: ["detect", "prepare"],
  reason: "Use the packaged desktop worker to detect a configured local openEMS installation.",
  adapter_version: "1.1.0",
}];
const fallbackAccelerators: AccelerationCatalogEntry[] = [
  { id: "numpy", name: "NumPy vectorized assembly", kind: "assembly", state: "not_detected", version: "", provider: "NumPy", capabilities: ["graph_laplacian_assembly", "vectorized_geometry_kernels"], reason: "Use the packaged desktop worker to detect the installed NumPy runtime.", license: "BSD-3-Clause" },
  { id: "numba", name: "Numba CPU JIT", kind: "assembly", state: "unavailable", version: "", provider: "Numba", capabilities: ["graph_laplacian_assembly", "compiled_cpu_kernel", "persistent_jit_cache"], reason: "Numba is not installed in the SPIKE worker runtime.", license: "BSD-2-Clause" },
  { id: "scipy-superlu", name: "SciPy SuperLU", kind: "sparse_direct", state: "not_detected", version: "", provider: "SciPy / SuperLU", capabilities: ["real_sparse", "complex_sparse", "single_process", "pivoting"], reason: "Use the packaged desktop worker to detect the installed SciPy runtime.", license: "BSD-3-Clause / BSD-style" },
  { id: "petsc-mumps", name: "PETSc MUMPS", kind: "sparse_direct", state: "unavailable", version: "", provider: "PETSc / MUMPS", capabilities: ["real_sparse", "multifrontal", "single_process_adapter"], reason: "petsc4py is not installed in the SPIKE worker runtime.", license: "PETSc: BSD-2-Clause; MUMPS: CeCILL-C" },
];
const fallbackSolverManager: SolverManagerCatalog = {
  contract: "spike/solver-manager/v1",
  selection_policy: "capability_then_validity_then_declared_priority",
  installation: { managed_downloads: false, reason: "Managed installation requires the packaged desktop worker plus signed manifests, hashes, SBOMs, license notices, and rollback.", register_local_paths: true, remove_behavior: "forget_registration_only" },
  registrations: {},
  tuning_profiles: [
    { target_id: "native.sparse", parameters: [
      { key: "assembly_backend", type: "enum", values: ["auto", "numpy", "numba"], value: "auto" },
      { key: "linear_backend", type: "enum", values: ["auto", "superlu", "mumps"], value: "auto" },
      { key: "thread_count", type: "integer", minimum: 1, maximum: 256, value: 1 },
      { key: "direct_solver_threshold", type: "integer", minimum: 100, maximum: 10_000_000, value: 5_000 },
    ] },
    { target_id: "external.openems", parameters: [
      { key: "mesh_resolution_mm", type: "number", minimum: 0.01, maximum: 10, value: 0.5 },
      { key: "boundary_padding_cells", type: "integer", minimum: 2, maximum: 40, value: 8 },
      { key: "end_criteria", type: "number", minimum: 1e-8, maximum: 0.01, value: 1e-5 },
      { key: "thread_count", type: "integer", minimum: 1, maximum: 256, value: 1 },
      { key: "max_solver_time_s", type: "integer", minimum: 10, maximum: 604_800, value: 3_600 },
    ] },
    { target_id: "external.openfoam", parameters: [
      { key: "parallel_ranks", type: "integer", minimum: 1, maximum: 256, value: 1 },
      { key: "max_iterations", type: "integer", minimum: 10, maximum: 1_000_000, value: 2_000 },
      { key: "residual_target", type: "number", minimum: 1e-12, maximum: 0.01, value: 1e-6 },
    ] },
  ],
  workloads: [
    { id: "dc_pi", name: "DC power integrity", domain: "pi", status: "approximate", required: ["voltage_drop", "current_density"], recommended: { id: "spike.routed_dc", name: "SPIKE Copper Geometry DC", state: "available", model_status: "approximate", reason: "Desktop worker validation is required before execution." }, candidates: [{ id: "spike.routed_dc", name: "SPIKE Copper Geometry DC", state: "available", eligible: true, missing: [], reason: "Desktop worker validation is required before execution." }] },
    { id: "quasistatic_ac_pi", name: "Quasi-static AC power integrity", domain: "pi", status: "approximate", required: ["frequency_dependent_impedance"], recommended: { id: "spike.peec_2_5d", name: "SPIKE Quasi-static PEEC 2.5D", state: "experimental", model_status: "approximate", reason: "External correlation remains required." }, candidates: [{ id: "spike.peec_2_5d", name: "SPIKE Quasi-static PEEC 2.5D", state: "experimental", eligible: true, missing: [], reason: "External correlation remains required." }] },
    { id: "geometry_transient", name: "Geometry-derived PI transient", domain: "pi", status: "approximate", required: ["transient_waveforms"], recommended: null, candidates: [] },
    { id: "native_mna_workspace", name: "Linear circuit workspace", domain: "pi", status: "experimental", required: ["explicit_netlist", "reviewed_linear_workspace"], recommended: { id: "spike.native_mna_workspace", name: "SPIKE Native MNA Workspace", state: "workspace_only", model_status: "experimental", reason: "Run only from the SPICE Workspace after composition and validation; it is limited to reviewed linear R/L/C circuits with independent and dependent sources." }, candidates: [{ id: "spike.native_mna_workspace", name: "SPIKE Native MNA Workspace", state: "workspace_only", eligible: true, missing: [], reason: "Workspace-only route. It is not a general PCB PI solver or a validated nonlinear circuit engine." }] },
    { id: "field_circuit_cosimulation", name: "Field-circuit co-simulation", domain: "pi", status: "experimental", required: ["explicit_netlist", "reviewed_peec_rlcg", "explicit_endpoint_mapping"], recommended: { id: "spike.field_circuit_cosimulation", name: "SPIKE PEEC + Native MNA Co-simulation", state: "workspace_only", model_status: "experimental", reason: "Run only from the SPICE Workspace with one reviewed PEEC extraction and explicit endpoint mappings." }, candidates: [{ id: "spike.field_circuit_cosimulation", name: "SPIKE PEEC + Native MNA Co-simulation", state: "workspace_only", eligible: true, missing: [], reason: "Experimental fixed-point coupling. It excludes inferred topology changes, nonlinear device solving, and validated general PCB PI co-simulation." }] },
    { id: "fullwave_comparison", name: "Full-wave field comparison", domain: "si", status: "unavailable", required: ["fdtd_3d_experimental"], recommended: null, candidates: [] },
    { id: "thermal_airflow", name: "Conjugate thermal and airflow", domain: "thermal", status: "unavailable", required: ["airflow"], recommended: null, candidates: [] },
    { id: "emi_radiation", name: "PCB EMI radiation and far field", domain: "emi", status: "unavailable", required: ["far_field", "ports"], recommended: null, candidates: [] },
  ],
  emi_pipeline: { state: "capability_gated", stages: [
    { id: "pi_si_prepass", state: "available_approximate", detail: "Native PI metrics may be used for screening." },
    { id: "net_screening", state: "available_screening_only", detail: "Ranks supplied pre-pass metrics; it does not predict compliance." },
    { id: "closed_loop_spice", state: "unavailable", detail: "Geometry/device coupling is incomplete." },
    { id: "fullwave_fields", state: "unavailable", detail: "A validated local full-wave adapter is required." },
    { id: "far_field_dashboard", state: "worker_required", detail: "The desktop worker must verify a version-matched openEMS runtime and reference fixture before NF2FF execution is enabled." },
  ] },
};
const terminal = (kind: "source" | "load", index: number): PiTerminal => ({
  id: `${kind}-${index + 1}`,
  name: `${kind === "source" ? "Source" : "Load"} ${index + 1}`,
  x: "",
  y: "",
  layer: "auto",
  layers: [],
  anchorId: "",
  anchorType: "coordinate",
  net: "",
  value: kind === "source" ? "12" : "1",
  profile: "constant",
  profileData: "",
  profileInitial: "0",
  profileDelayS: "0",
  profileRiseS: "0.000001",
  profileWidthS: "0.0001",
  profileFallS: "0.000001",
  profilePeriodS: "0.0002",
  contactResistance: "0",
  packageResistance: "0",
});
const defaultReturnPath = (): ReturnPathSetup => ({
  mode: "implicit",
  net: "GND",
  domainId: "main",
  sources: [{ ...terminal("source", 0), id: "return-source-1", name: "Source return", value: "0" }],
  loads: [{ ...terminal("load", 0), id: "return-load-1", name: "Load return", value: "1" }],
});
const defaultCouplingSetup = (): CouplingSetup => ({
  enabled: false,
  electricField: true,
  magneticField: true,
  scope: "adjacent",
  radiusMm: "5",
  includeTraces: true,
  includePlanes: true,
  includeZones: true,
  crossLayer: true,
});
const batchJob = (net: string, mode: BatchAnalysisMode = "skip"): BatchNetJob => ({
  id: `batch-${net.replace(/[^a-z0-9]+/gi, "-").toLowerCase() || "net"}`,
  net,
  mode,
  solverId: "auto",
  sources: [terminal("source", 0)],
  loads: [terminal("load", 0)],
  coupling: defaultCouplingSetup(),
});
const topologyTerminal = (
  board: ParsedBoard | null,
  node: TopologyNode | undefined,
  net: string,
  kind: "source" | "load",
  index: number,
  value: number,
): PiTerminal => {
  const result = { ...terminal(kind, index), name: node?.ref || node?.label || `${kind === "source" ? "Source" : "Load"} ${index + 1}`, net, value: String(Math.max(0, value)) };
  if (!board || !node?.ref) return result;
  const pads = board.pads.filter(pad => pad.ref === node.ref && pad.net === net).sort((left, right) => left.name.localeCompare(right.name, undefined, { numeric: true }));
  const pad = pads.find(item => item.id === node.terminalPadId) ?? pads[0];
  if (!pad) return result;
  const layers = pad.layers.some(layer => layer === "*.Cu" || layer === "F&B.Cu")
    ? [...board.layers]
    : pad.layers.filter(layer => board.layers.includes(layer));
  return { ...result, x: pad.at[0].toFixed(4), y: pad.at[1].toFixed(4), layer: "auto", layers, anchorId: pad.id, anchorType: "pad" };
};
const topologyBatchJobs = (board: ParsedBoard | null, topology: TopologyModel, plan: PowerTreeAnalysisPlan): BatchNetJob[] => {
  const nodes = new Map(topology.nodes.map(node => [node.id, node]));
  return plan.jobs.map(job => {
    const sources = (job.sourceNodeIds.length ? job.sourceNodeIds : [""]).map((id, index) =>
      topologyTerminal(board, nodes.get(id), job.net, "source", index, nodes.get(id)?.voltageV ?? job.voltageV ?? 0));
    const loadShare = job.loadNodeIds.length ? job.totalCurrentA / job.loadNodeIds.length : job.totalCurrentA;
    const loads = (job.loadNodeIds.length ? job.loadNodeIds : [""]).map((id, index) =>
      topologyTerminal(board, nodes.get(id), job.net, "load", index, plan.budget.nodes[id]?.currentA ?? loadShare));
    return { id: job.id, net: job.net, mode: "dc", solverId: "auto", sources, loads, coupling: defaultCouplingSetup() };
  });
};
const defaultPiSetup = (): PiSetup => ({
  net: "+1V8_CORE",
  powerPathId: "",
  sources: [terminal("source", 0)],
  loads: [terminal("load", 0)],
  returnPath: defaultReturnPath(),
  meshDimension: "surface_2_5d",
  meshTargetMm: "1",
  zoneCellMm: "1",
  maxPreviewCells: "25000",
  viaModel: "extracted",
  viaPlatingMm: "0.025",
  frequencyStart: "10000",
  frequencyStop: "10000000",
  frequencyPoints: "101",
  transientStopS: "1ms",
  transientTimeStepS: "1us",
  transientTimeStepMode: "auto",
  transientOutputDecimation: "10",
  transientOutputDecimationMode: "auto",
  transientPlaybackFps: "20",
  transientInitialCondition: "operating_point",
  transientMaxSolverTimeS: "120s",
  transientMemoryBudgetMb: "2048",
  transientCapacitanceModel: "auto",
  transientVisualSampleLimit: "12000",
  skinEffect: true,
  proximityEffect: false,
  roughnessModel: "hammerstad",
  roughnessUm: "0.4",
  hurayNoduleRadiusUm: "0.5",
  huraySurfaceRatio: "2.0",
  batchJobs: [],
  loopExtractions: [],
});
const normalizeTerminal = (value: Partial<PiTerminal>, kind: "source" | "load", index: number): PiTerminal => ({
  ...terminal(kind, index),
  ...value,
  layers: Array.isArray(value.layers) ? value.layers : [],
});
const normalizePiSetup = (value?: Partial<PiSetup>): PiSetup => {
  const defaults = defaultPiSetup();
  const returnDefaults = defaultReturnPath();
  const returnValue = value?.returnPath;
  return {
    ...defaults,
    ...(value ?? {}),
    sources: (value?.sources ?? defaults.sources).map((item, index) => normalizeTerminal(item, "source", index)),
    loads: (value?.loads ?? defaults.loads).map((item, index) => normalizeTerminal(item, "load", index)),
    returnPath: {
      ...returnDefaults,
      ...(returnValue ?? {}),
      sources: (returnValue?.sources ?? returnDefaults.sources).map((item, index) => normalizeTerminal(item, "source", index)),
      loads: (returnValue?.loads ?? returnDefaults.loads).map((item, index) => normalizeTerminal(item, "load", index)),
    },
    batchJobs: (value?.batchJobs ?? []).map(job => ({
      ...job,
      solverId: job.solverId ?? "auto",
      sources: (job.sources ?? []).map((item, index) => normalizeTerminal(item, "source", index)),
      loads: (job.loads ?? []).map((item, index) => normalizeTerminal(item, "load", index)),
      coupling: { ...defaultCouplingSetup(), ...(job.coupling ?? {}) },
    })),
    loopExtractions: (value?.loopExtractions ?? []).map((item, index) => ({
      id: item.id || `loop-${index + 1}`,
      name: item.name || `Power loop ${index + 1}`,
      forwardNet: item.forwardNet || "",
      returnNet: item.returnNet || "",
      forwardStartPadId: item.forwardStartPadId || "",
      forwardEndPadId: item.forwardEndPadId || "",
      returnStartPadId: item.returnStartPadId || "",
      returnEndPadId: item.returnEndPadId || "",
      pathGroupId: item.pathGroupId || "",
    })),
  };
};
const emiPhaseCenter = (board: ParsedBoard, netNames: string[]): [number, number, number] => {
  const selected = new Set(netNames);
  const points: Array<[number, number]> = [];
  board.tracks.filter(item => item.net && selected.has(item.net)).forEach(item => points.push(item.start, item.end));
  board.vias.filter(item => item.net && selected.has(item.net)).forEach(item => points.push(item.at));
  board.pads.filter(item => item.net && selected.has(item.net)).forEach(item => points.push(item.at));
  board.zones.filter(item => item.net && selected.has(item.net)).forEach(item => points.push(...item.points));
  if (!points.length) return [(board.bounds.minX + board.bounds.maxX) / 2, (board.bounds.minY + board.bounds.maxY) / 2, 0];
  const xs = points.map(point => point[0]);
  const ys = points.map(point => point[1]);
  const minX = numericMinimum(xs) ?? board.bounds.minX;
  const maxX = numericMaximum(xs) ?? board.bounds.maxX;
  const minY = numericMinimum(ys) ?? board.bounds.minY;
  const maxY = numericMaximum(ys) ?? board.bounds.maxY;
  return [(minX + maxX) / 2, (minY + maxY) / 2, 0];
};
const emiFarFieldFrequencies = (startHz: number, stopHz: number) => {
  if (!(startHz > 0) || !(stopHz > startHz)) return [startHz].filter(value => value > 0);
  return [startHz, Math.sqrt(startHz * stopHz), stopHz];
};
type ProjectSnapshot = { studies: SimulationStudy[]; probes: BoardObject[]; probeFormulaRows: ProbeFormulaRow[]; probeReferenceIds: Record<string, string>; boardFile: string; frequency: string; solverId: string; formulation: string; solverSelections: Record<string, string>; piSetup: PiSetup; piTopology: TopologyModel; siTopology: TopologyModel; selectedSiSuite: SiProtocolSuite | null; siChannelResult: Record<string, unknown> | null; spiceWorkspace: SpiceWorkspace; emiSetup: EmiSetup; emiPreflight: EmiPreflight | null; emiScreening: EmiScreening | null; emiFieldResult: EmiFieldResult | null; thermalScenario: Record<string, unknown> | null; componentBonds: BondRecord[]; visibleLayers: Record<LayerName, boolean>; assemblyLayerVisibility?: Record<string, Record<string, boolean>>; assemblyLayerOpacity?: Record<string, Record<string, number>>; assemblyBoardVisibility?: Record<string, boolean>; assemblyExplodedDistanceMm?: number; layerOpacity: Record<LayerName, number>; layerSeparation: number; showVias: boolean; showNetNames: boolean; showAxes: boolean; selected: BoardObject | null; selectionFilter: SelectionFilter; isolatedNet: string | null; modelAssignments: Record<string, string>; assemblyModelAssignments?: Record<string, Record<string, string>>; assemblyIr: AssemblyIr | null; assemblyDesigns: AssemblyDesigns | null; assemblyPackageShapes: AssemblyPackageShapesIndex | null; modelIndex: ModelIndex; showModels: boolean; showSmdModels: boolean; showThtModels: boolean; navigationInertia: boolean; viewMode: "2D" | "3D"; resultVisualization: ResultVisualization; analysisResult: SolverResultBundle | null; pdnReview: PdnReview | null; pdnReviewSourceId: string | null; workspace?: WorkspaceState };

function decodeBase64Buffer(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}
const defaultLayerVisible = (name: string) =>
  name === "Board body" || name.endsWith(".Cu") || name.endsWith(".Mask") || name.endsWith(".SilkS") || name === "Edge.Cuts";
const visibilityForBoard = (board: ParsedBoard, stored?: Record<string, boolean>) => {
  const rigidFlexLayers = new Set([...(board.regions ?? []).map(region => region.sourceLayer), ...(board.bendLines ?? []).map(bend => bend.sourceLayer)]);
  return Object.fromEntries([{ name: "Board body" }, ...board.layerDefinitions].map(({ name }) => [
    name,
    stored && Object.prototype.hasOwnProperty.call(stored, name) ? stored[name] : defaultLayerVisible(name) || board.layers.includes(name) || rigidFlexLayers.has(name),
  ]));
};
const preferredPowerNet = (board: ParsedBoard) => {
  const nets = [...new Set(Object.values(board.nets).filter(Boolean))].filter(net => !/^Net-\(|^unconnected-/i.test(net));
  return nets.find(net => !/gnd|vss/i.test(net) && /(^|[/_])(vcc|vdd|vin|vbat|pwr|\d+v\d*|[+-]\d+)/i.test(net))
    ?? nets.find(net => !/gnd|vss/i.test(net))
    ?? "";
};
// Ribbon commands use one stable pictogram per engineering action. Keeping the
// vocabulary here prevents unrelated commands from drifting back to generic
// waveform, network, layer, and gauge icons as ribbon groups evolve.
const toolIconByLabel: Record<string, typeof Activity> = {
  Open: FolderOpen,
  Manager: FileArchive,
  Save,
  Validate: ShieldCheck,
  Stackup: Layers3,
  Issues: BadgeAlert,
  Layers: GalleryVertical,
  "3D models": Boxes,
  Bonds: Cable,
  "Power tree": Workflow,
  "DC drop": BatteryCharging,
  "Bulk nets": Waypoints,
  "AC sweep": ChartSpline,
  Transient: AudioWaveform,
  "Batch nets": ListChecks,
  Terminals: PlugZap,
  Probes: Crosshair,
  "Run PI": Play,
  "Running...": Play,
  "PI results": ChartArea,
  "PI report": FileChartColumn,
  "Export data": Download,
  "Save results": Save,
  "Load results": FolderOpen,
  "Channel tree": ChartNetwork,
  Impedance: Omega,
  Parasitics: Component,
  "Coupling risk": Magnet,
  "S-parameters": ChartSpline,
  "NEXT / FEXT": Split,
  "Eye diagram": Eye,
  PAM4: Binary,
  "Layer view": GalleryVertical,
  Ports: Plug,
  Touchstone: FileInput,
  "SPICE model": Microchip,
  "External engines": Cpu,
  "Net domain": Route,
  Preflight: ClipboardCheck,
  "Risk screen": Radar,
  Screening: Radar,
  "PI transient": AudioWaveform,
  SPICE: Microchip,
  "Domain mesh": Grid3X3,
  "Prepare case": FileCog,
  "Run solver": Play,
  "Solver manager": ServerCog,
  Dashboard: LayoutDashboard,
  "Near field": ScanLine,
  "Far field": SatelliteDish,
  "EMI report": FileChartColumn,
  "Bounding volume": Box,
  "Board stack": Layers3,
  "Heat sources": Flame,
  "Flow channels": Wind,
  "Fan placement": Fan,
  Ambient: CloudSun,
  Scenario: ListTree,
  "Solver console": SquareTerminal,
  Temperature: ThermometerSun,
  Report: FileChartColumn,
  "Hover probe": ScanSearch,
  "Place probe": MapPinPlus,
  "Probe table": TableProperties,
  Duplicate: CopyPlus,
  Voltage: Zap,
  Current: ArrowRightLeft,
  Compare: GitCompareArrows,
  "Cross-layer": Layers2,
  "Export CSV": FileSpreadsheet,
  Console: SquareTerminal,
  Fields: ChartScatter,
  "Voltage / current": ChartSpline,
  Mesh: Grid3X3,
  "Probe overlay": Crosshair,
  Limits: BadgeCheck,
  Preview: BookOpenCheck,
  "Print / PDF": Printer,
  Analytics: ChartNoAxesCombined,
  "Probe CSV": FileSpreadsheet,
  STEP: Cuboid,
  "Result bundle": FileArchive,
  "Save instance": CopyPlus,
  Settings: Settings2,
  Extensions: Puzzle,
  Dependencies: PackageSearch,
  Verification: BadgeCheck,
  "3D library": LibraryBig,
  Models: Boxes,
  Shortcuts: Keyboard,
  Resources: MemoryStick,
  "User guide": BookOpenCheck,
  "Icon gallery": GalleryVertical,
};

function Tool({ icon: Icon, label, onClick, active = false, disabled = false, guideTarget }: { icon: typeof Activity; label: string; onClick?: () => void; active?: boolean; disabled?: boolean; guideTarget?: string }) {
  const SemanticIcon = toolIconByLabel[label] ?? Icon;
  return <button className={`tool ${active ? "active" : ""}`} data-guide={guideTarget} disabled={disabled} onClick={onClick} title={disabled ? `${label} is not validated yet` : label}><SemanticIcon size={18} strokeWidth={1.8} /><span>{label}</span></button>;
}
function ToolGroup({ label, priority, children }: { label: string; priority: "primary" | "secondary" | "tertiary" | "quaternary"; children: React.ReactNode }) {
  return <div className={`tool-group ribbon-group ${priority}`}><label>{label}</label><div className="tool-row">{children}</div></div>;
}

function BoardViewRibbon({
  viewMode, modelsVisible, translucent, onViewMode, onLayers, onFit, onCamera, onToggleModels, onToggleTranslucent,
}: {
  viewMode: "2D" | "3D";
  modelsVisible: boolean;
  translucent: boolean;
  onViewMode: (mode: "2D" | "3D") => void;
  onLayers: () => void;
  onFit: () => void;
  onCamera: (camera: string) => void;
  onToggleModels: () => void;
  onToggleTranslucent: () => void;
}) {
  const controls: Array<{ id: string; label: string; icon: typeof Activity; active?: boolean; disabled?: boolean; run: () => void }> = [
    { id: "2d", label: "2D layout", icon: MapPinPlus, active: viewMode === "2D", run: () => onViewMode("2D") },
    { id: "3d", label: "3D board", icon: Cuboid, active: viewMode === "3D", run: () => onViewMode("3D") },
    { id: "layers", label: "Layer manager", icon: GalleryVertical, run: onLayers },
    { id: "models", label: modelsVisible ? "Hide 3D component models" : "Show 3D component models", icon: Boxes, active: modelsVisible, disabled: viewMode === "2D", run: onToggleModels },
    { id: "translucent", label: translucent ? "Restore opaque board" : "Show translucent board", icon: Blend, active: translucent, run: onToggleTranslucent },
    { id: "fit", label: "Fit active scene", icon: Focus, run: onFit },
    { id: "top", label: "Top view", icon: PanelTop, disabled: viewMode === "2D", run: () => onCamera("view-top") },
    { id: "bottom", label: "Bottom view", icon: PanelBottom, disabled: viewMode === "2D", run: () => onCamera("view-bottom") },
    { id: "iso", label: "Isometric view", icon: Axis3D, disabled: viewMode === "2D", run: () => onCamera("view-iso") },
  ];
  return <div className="tool-group persistent-board-view"><label>BOARD VIEW</label><div className="ribbon-view-row">{controls.map(({ id, label, icon: Icon, active, disabled, run }) => <button key={id} className={active ? "active" : ""} disabled={disabled} title={label} aria-label={label} onClick={run}><Icon size={15} /><span>{id === "2d" ? "2D" : id === "3d" ? "3D" : ""}</span></button>)}</div></div>;
}
function Issue({ kind, title, detail }: { kind: "error" | "warning" | "ok" | "info"; title: string; detail: string }) {
  const Icon = kind === "error" ? XCircle : kind === "warning" ? AlertTriangle : kind === "info" ? BookOpen : CheckCircle2;
  return <div className={`issue ${kind}`}><Icon size={16} /><div><strong>{title}</strong><p>{detail}</p></div></div>;
}
function activityLevel(message: string): ActivityLevel {
  if (/\b(error|failed|failure|invalid|blocked|cannot|unavailable)\b/i.test(message)) return "error";
  if (/\b(warn|warning|approximate|incomplete|unsupported|requires)\b/i.test(message)) return "warning";
  if (/\b(completed|passed|ready|saved|loaded|imported|verified|exported|valid)\b/i.test(message)) return "success";
  return "info";
}
function ActivityConsole({ entries, onClear }: { entries: ActivityEntry[]; onClear: () => void }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [entries]);
  const copyLog = async () => {
    const text = entries.map(entry => `${entry.timestamp} [${entry.level.toUpperCase()}] ${entry.source}: ${entry.message}`).join("\n");
    try { await navigator.clipboard.writeText(text); } catch { /* Clipboard permission is surfaced by the browser. */ }
  };
  return <div className="activity-console">
    <div className="activity-console-toolbar"><span>{entries.length} events</span><button onClick={() => void copyLog()}><Copy size={13} /> Copy</button><button onClick={onClear}><Trash2 size={13} /> Clear</button></div>
    <div className="activity-console-log" role="log" aria-live="polite" aria-label="Application activity console">
      {entries.length ? entries.map(entry => <div className={`activity-entry ${entry.level}`} key={entry.id}><time>{entry.timestamp}</time><i>{entry.level}</i><b>{entry.source}</b><span>{entry.message}</span></div>) : <div className="activity-console-empty"><Activity size={15} /> No activity has been recorded.</div>}
      <div ref={endRef} />
    </div>
  </div>;
}
function MenuButton({ label, open, onClick, children }: { label: string; open: boolean; onClick: () => void; children: React.ReactNode }) {
  return <div className="menu-entry"><button className={open ? "menu-button selected" : "menu-button"} onClick={onClick}>{label}</button>{open && <div className="menu-dropdown">{children}</div>}</div>;
}
function MenuItem({ icon: Icon, label, shortcut, onClick }: { icon: typeof Activity; label: string; shortcut?: string; onClick: () => void }) {
  return <button className="menu-item" onClick={onClick}><Icon size={14} /><span>{label}</span>{shortcut && <small>{shortcut}</small>}</button>;
}

function DiagnosticItem({ issue, onHelp }: { issue: DiagnosticIssue; onHelp?: (code: string) => void }) {
  const code = issue.code || (issue.severity === "error" ? "SPIKE-FE-APP-E-0001" : "SPIKE-FE-APP-W-0001");
  return <div className={`diagnostic-item ${issue.severity || "warning"}`}>
    <div><code>{code}</code><span>{issue.message}</span>{onHelp && <button type="button" className="diagnostic-help" onClick={() => onHelp(code)} title={`Open troubleshooting for ${code}`}><CircleHelp size={13} /> Help</button>}</div>
    {issue.path && <small><b>Object</b> {issue.path}</small>}
    {issue.suggestion && <small><b>Resolution</b> {issue.suggestion}</small>}
  </div>;
}


function resultRecord(bundle: SolverResultBundle, fallbackIndex = 0): ResultRecord {
  const nets = [...new Set([
    ...Object.values(bundle.scalar_fields).flatMap(samples => samples.map(sample => sample.net).filter((net): net is string => Boolean(net))),
    ...bundle.mesh.map(cell => cell.net).filter((net): net is string => Boolean(net)),
  ])];
  const label = nets.length ? nets.join(", ") : `${bundle.mode.toUpperCase()} result ${fallbackIndex + 1}`;
  return { id: bundle.analysis_id || `${bundle.mode}:${label}`, label, bundle };
}

/** Give results.read extensions useful evidence without sending unbounded field data. */
function extensionResultsContext(result: SolverResultBundle | null): Record<string, unknown> | null {
  if (!result) return null;
  const contract = "spike/results-context/v1";
  if (JSON.stringify(result).length <= 250_000) return { contract, complete: true, result };
  const primitiveMetadata = (value: Record<string, unknown>) => Object.fromEntries(Object.entries(value)
    .filter(([, item]) => ["string", "number", "boolean"].includes(typeof item))
    .slice(0, 64).map(([key, item]) => [key, typeof item === "string" ? item.slice(0, 512) : item]));
  const preview = {
    contract, complete: false, analysis_id: result.analysis_id, status: result.status, mode: result.mode,
    model_status: result.model_status, summary: primitiveMetadata(result.summary ?? {}), provenance: primitiveMetadata(result.provenance ?? {}),
    field_counts: Object.fromEntries(Object.entries(result.scalar_fields).map(([key, samples]) => [key, samples.length])),
    scalar_fields: Object.fromEntries(Object.entries(result.scalar_fields).map(([key, samples]) => [key, samples.slice(0, 64)])),
    mesh_count: result.mesh.length, mesh: result.mesh.slice(0, 32),
    parasitic_count: result.parasitics.length, parasitics: result.parasitics.slice(0, 32),
    issues: result.issues.slice(0, 32),
  };
  if (JSON.stringify(preview).length <= 250_000) return preview;
  return { contract, complete: false, analysis_id: result.analysis_id, status: result.status, mode: result.mode,
    model_status: result.model_status, summary: primitiveMetadata(result.summary ?? {}), provenance: primitiveMetadata(result.provenance ?? {}),
    field_counts: preview.field_counts, mesh_count: result.mesh.length, parasitic_count: result.parasitics.length };
}

function boundedResultRecords(records: ResultRecord[]) {
  return [...new Map(records.map(record => [record.id, record])).values()];
}

function mergeResultBundles(records: ResultRecord[]): SolverResultBundle | null {
  if (!records.length) return null;
  const latest = records[records.length - 1].bundle;
  const mergeScalar = (key: keyof SolverResultBundle["scalar_fields"]) => records.flatMap(record => record.bundle.scalar_fields[key]);
  const mergeVector = (key: keyof SolverResultBundle["vector_fields"]) => records.flatMap(record => record.bundle.vector_fields[key]);
  return {
    ...latest,
    analysis_id: records.map(record => record.id).join("+"),
    summary: { ...latest.summary, displayed_result_count: records.length },
    scalar_fields: {
      voltage_v: mergeScalar("voltage_v"),
      voltage_drop_v: mergeScalar("voltage_drop_v"),
      current_a: mergeScalar("current_a"),
      operating_point_impedance_ohm: mergeScalar("operating_point_impedance_ohm"),
      current_density_a_mm2: mergeScalar("current_density_a_mm2"),
      power_loss_w: mergeScalar("power_loss_w"),
      via_current_density_a_mm2: mergeScalar("via_current_density_a_mm2"),
    },
    vector_fields: {
      current_density: mergeVector("current_density"),
      electric_field: mergeVector("electric_field"),
      magnetic_field: mergeVector("magnetic_field"),
    },
    mesh: records.flatMap(record => record.bundle.mesh),
    parasitics: records.flatMap(record => record.bundle.parasitics),
    coupling_risks: records.flatMap(record => record.bundle.coupling_risks),
    component_stress: records.flatMap(record => record.bundle.component_stress),
    probes: records.flatMap(record => record.bundle.probes),
    issues: records.flatMap(record => record.bundle.issues),
  };
}
export default function App() {
  const [tab, setTab] = useState<RibbonTab>("Home");
  const [simulationDomain, setSimulationDomain] = useState<SimulationDomain>("pi");
  const [dock, setDock] = useState<DockTab>("Issues");
  const [viewMode, setViewMode] = useState<"2D" | "3D">("3D");
  const [navigationMode, setNavigationMode] = useState<"orbit" | "pan">("orbit");
  const [navigationInertia, setNavigationInertia] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [sidePanelsPinned, setSidePanelsPinned] = useState(true);
  const [bottomOpen, setBottomOpen] = useState(true);
  const [bottomPinned, setBottomPinned] = useState(true);
  const [leftPanelWidth, setLeftPanelWidth] = useState(() => Number(localStorage.getItem("spike.panel.left")) || 224);
  const [rightPanelWidth, setRightPanelWidth] = useState(() => Number(localStorage.getItem("spike.panel.right")) || 272);
  const [bottomPanelHeight, setBottomPanelHeight] = useState(() => Number(localStorage.getItem("spike.panel.bottom")) || 178);
  const [layersOpen, setLayersOpen] = useState(false);
  const [stackupOpen, setStackupOpen] = useState(false);
  const [flexBoardOpen, setFlexBoardOpen] = useState(false);
  const [thermalOpen, setThermalOpen] = useState(false);
  const [studyManagerOpen, setStudyManagerOpen] = useState(false);
  const [mcpBridgePanelOpen, setMcpBridgePanelOpen] = useState(false);
  const [mcpAnalysisOutput, setMcpAnalysisOutput] = useState<Record<string, unknown> | null>(null);
  const mcpAnalysisCallbacks = useRef({
    getContext: (): McpLoadedContext => ({ design: null }),
    admitScope: async (_kind: string, _parameters: Record<string, unknown>): Promise<unknown> => { throw new Error("SPIKE UI is starting"); },
    publishResult: async (_result: Record<string, unknown>, _meta: { kind: string; caseId: string; jobId: string; scope: string; parameters: Record<string, unknown> }): Promise<void> => { throw new Error("SPIKE UI is starting"); },
    resultAction: async (_command: string, _args: Record<string, unknown>): Promise<unknown> => { throw new Error("SPIKE UI is starting"); },
  });
  const mcpAnalysisConversation = useRef<ReturnType<typeof createMcpAnalysisConversation> | null>(null);
  if (!mcpAnalysisConversation.current) mcpAnalysisConversation.current = createMcpAnalysisConversation({
    callWorker: request => runLocalWorker(request),
    getContext: () => mcpAnalysisCallbacks.current.getContext(),
    admitScope: (kind, parameters) => mcpAnalysisCallbacks.current.admitScope(kind, parameters),
    publishResult: (result, meta) => mcpAnalysisCallbacks.current.publishResult(result, meta),
  });
  const mcpRequestHandler = useRef<(request: McpBridgeRequest) => unknown>(() => { throw new Error("SPIKE UI is starting"); });
  const [studies, setStudies] = useState<SimulationStudy[]>([]);
  const [activeStudyCaseId, setActiveStudyCaseId] = useState<string | null>(null);
  const [dcRunOpen, setDcRunOpen] = useState(false);
  const [sparameterOpen, setSparameterOpen] = useState(false);
  const [sparameterActivated, setSparameterActivated] = useState(false);
  useEffect(() => { if (sparameterOpen) setSparameterActivated(true); }, [sparameterOpen]);
  const [siWorkbenchIntent, setSiWorkbenchIntent] = useState<{ view: "workflow" | "geometry"; focus: "channel" | "crosstalk" | "eye" | "pam4" | "impedance" | "ports"; token: number }>({ view: "workflow", focus: "channel", token: 0 });
  const [frequency, setFrequency] = useState("10 MHz");
  const [analysisMode, setAnalysisMode] = useState("DC IR Drop");
  const [solverId, setSolverId] = useState("auto");
  const [formulation, setFormulation] = useState("auto");
  const [solverCatalog, setSolverCatalog] = useState<SolverCatalogEntry[]>(fallbackSolverCatalog);
  const desktopShell = isDesktopShell();
  const [workerHealth, setWorkerHealth] = useState<"browser" | "starting" | "ready" | "degraded">(desktopShell ? "starting" : "browser");
  const workerAvailable = workerHealth === "ready";
  const solverSupports = (...capabilities: string[]) => solverCatalog.some(solver =>
    ["available", "experimental"].includes(solver.state)
    && capabilities.every(capability => solver.capabilities?.includes(capability)),
  );
  const [powerNets, setPowerNets] = useState(["+1V8_CORE", "GND"]);
  const [piSetup, setPiSetup] = useState<PiSetup>(defaultPiSetup);
  const [emiSetup, setEmiSetup] = useState<EmiSetup>(() => defaultEmiSetup(["+1V8_CORE", "GND"]));
  const [emiPreflight, setEmiPreflight] = useState<EmiPreflight | null>(null);
  const [emiScreening, setEmiScreening] = useState<EmiScreening | null>(null);
  const [emiFieldResult, setEmiFieldResult] = useState<EmiFieldResult | null>(null);
  const [emiSection, setEmiSection] = useState<EmiSetupSection>("domain");
  const [emiDashboardOpen, setEmiDashboardOpen] = useState(false);
  const [emiChamberOpen, setEmiChamberOpen] = useState(true);
  const [emiScene, setEmiScene] = useState<Group | null>(null);
  const emiSceneRef = useRef<Group | null>(null);
  const handleEmiScene = useCallback((scene: Group) => {
    if (emiSceneRef.current) disposeEmiGeometry(emiSceneRef.current);
    emiSceneRef.current = scene;
    setEmiScene(scene);
  }, []);
  useEffect(() => () => { if (emiSceneRef.current) disposeEmiGeometry(emiSceneRef.current); }, []);
  const [emiBusy, setEmiBusy] = useState(false);
  const [emiPreparedSetupKey, setEmiPreparedSetupKey] = useState("");
  const [analysisSummary, setAnalysisSummary] = useState<AnalysisSummary>(null);
  const [analysisResult, setAnalysisResult] = useState<SolverResultBundle | null>(null);
  const [resultRecords, setResultRecords] = useState<ResultRecord[]>([]);
  const [emResultManagerOpen, setEmResultManagerOpen] = useState(false);
  const [emViewportSettings, setEmViewportSettings] = useState<EMViewportSettings>(defaultEMViewportSettings);
  const [reportPreview, setReportPreview] = useState<{ fileName: string; html: string } | null>(null);
  const [resultDisplay, setResultDisplay] = useState<"all" | "none" | string>("none");
  const [pdnReview, setPdnReview] = useState<PdnReview | null>(null);
  const [pdnReviewSourceId, setPdnReviewSourceId] = useState<string | null>(null);
  const [resultVisualization, setResultVisualization] = useState<ResultVisualization>(defaultResultVisualization);
  const [resultVisualizerOpen, setResultVisualizerOpen] = useState(false);
  const [tracePlotsOpen, setTracePlotsOpen] = useState(false);
  const [detachedTools, setDetachedTools] = useState<Partial<Record<ToolWindowKind, boolean>>>({});
  const detachedActionRef = useRef<(action: DetachedToolAction) => void>(() => {});
  const [resultVisualizerDomain, setResultVisualizerDomain] = useState<"pi" | "si">("pi");
  const [probes, setProbes] = useState<BoardObject[]>([]);
  const [probeFormulaRows, setProbeFormulaRows] = useState<ProbeFormulaRow[]>([]);
  const [savedProbeReferenceIds, setSavedProbeReferenceIds] = useState<Record<string, string>>({});
  const probeReferenceIds = useMemo(() => assignProbeReferenceIds(probes.map(probe => probe.id), savedProbeReferenceIds, probeFormulaRows),
    [probes, savedProbeReferenceIds, probeFormulaRows]);
  useEffect(() => {
    if (Object.keys(probeReferenceIds).length !== Object.keys(savedProbeReferenceIds).length) setSavedProbeReferenceIds(probeReferenceIds);
  }, [probeReferenceIds, savedProbeReferenceIds]);
  const [probeMode, setProbeMode] = useState<"off" | "hover" | "temporary" | "bulk">("off");
  const [probeKind, setProbeKind] = useState<NonNullable<BoardObject["probeKind"]>>("universal");
  const [showProbes, setShowProbes] = useState(true);
  const [limits, setLimits] = useState({ drop: "50", density: "100" });
  const [visibleLayers, setVisibleLayers] = useState<Record<LayerName, boolean>>(initialLayers);
  const [assemblyLayerVisibility, setAssemblyLayerVisibility] = useState<Record<string, Record<string, boolean>>>({});
  const [assemblyLayerOpacity, setAssemblyLayerOpacity] = useState<Record<string, Record<string, number>>>({});
  const [layerOpacity, setLayerOpacity] = useState<Record<LayerName, number>>({});
  const [layerSeparation, setLayerSeparation] = useState(0);
  const [showVias, setShowVias] = useState(true);
  const [showNetNames, setShowNetNames] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [selected, setSelected] = useState<BoardObject | null>(null);
  const [selectionFilter, setSelectionFilter] = useState<SelectionFilter>("all");
  const [viewportContext, setViewportContext] = useState<ViewportContextRequest | null>(null);
  const [isolatedNet, setIsolatedNet] = useState<string | null>(null);
  const [modelAssignments, setModelAssignments] = useState<Record<string, string>>({});
  const [assemblyModelAssignments, setAssemblyModelAssignments] = useState<Record<string, Record<string, string>>>({});
  const [modelLibraryOpen, setModelLibraryOpen] = useState(false);
  const [modelResolverTarget, setModelResolverTarget] = useState<{ designId?: string; componentRef?: string }>({});
  const [assemblyIr, setAssemblyIr] = useState<AssemblyIr | null>(null);
  const [assemblyDesigns, setAssemblyDesigns] = useState<AssemblyDesigns | null>(null);
  const [canonicalSpiDeR, setCanonicalSpiDeR] = useState<Record<string, unknown> | null>(null);
  const [assemblyPackageShapes, setAssemblyPackageShapes] = useState<AssemblyPackageShapesIndex | null>(null);
  const [activeDesignId, setActiveDesignId] = useState<string | null>(null);
  const [modelIndex, setModelIndex] = useState<ModelIndex>(() => normalizeModelIndex(null));
  const [assemblySceneModels, setAssemblySceneModels] = useState<AssemblySceneModel[]>([]);
  const [selectedHarnessId, setSelectedHarnessId] = useState<string | null>(null);
  const [selectedBoardInstanceId, setSelectedBoardInstanceId] = useState<string | null>(null);
  const [assemblyBoardVisibility, setAssemblyBoardVisibility] = useState<Record<string, boolean>>({});
  const [assemblyExplodedDistanceMm, setAssemblyExplodedDistanceMm] = useState(0);
  const [assemblySnapMode, setAssemblySnapMode] = useState<"off" | "hole" | "edge">("off");
  const [assemblyMoveMode, setAssemblyMoveMode] = useState<"translate" | "rotate" | null>(null);
  const [assemblySnapGapMm, setAssemblySnapGapMm] = useState(0);
  const [assemblySnapSource, setAssemblySnapSource] = useState<AssemblySnapTarget | null>(null);
  useEffect(() => setAssemblySnapSource(null), [assemblyIr, assemblySnapMode]);
  const assemblyHandlingRef = useRef<HTMLDivElement>(null);
  const [assemblyHandlingHeight, setAssemblyHandlingHeight] = useState(0);
  const [assemblyHandlingExpanded, setAssemblyHandlingExpanded] = useState(false);
  const [assemblyToolDraftOwner, setAssemblyToolDraftOwner] = useState<AssemblyToolKind | null>(null);
  const assemblyToolDraftOwnerRef = useRef<AssemblyToolKind | null>(null);
  assemblyToolDraftOwnerRef.current = assemblyToolDraftOwner;
  useEffect(() => {
    const slot = assemblyHandlingRef.current;
    if (!slot) { setAssemblyHandlingHeight(0); return; }
    const observer = new ResizeObserver(() => setAssemblyHandlingHeight(slot.getBoundingClientRect().height));
    observer.observe(slot);
    return () => observer.disconnect();
  }, [assemblyIr?.boards.length]);
  const [linkedAssemblyNets, setLinkedAssemblyNets] = useState<Record<string, string[]>>({});
  const [assemblyHighlightSeed, setAssemblyHighlightSeed] = useState<AssemblyHighlightSeed | null>(null);
  const [passThroughHighlight, setPassThroughHighlight] = useState(false);
  const linkedSelectionGeneration = useRef(0);
  useEffect(() => { linkedSelectionGeneration.current++; setAssemblyHighlightSeed(null); setLinkedAssemblyNets({}); }, [assemblyDesigns]);
  const [assemblySelectorPreviews, setAssemblySelectorPreviews] = useState<AssemblySelectorPreviewModel[]>([]);
  const [assemblyPartViewportStates, setAssemblyPartViewportStates] = useState<Record<string, AssemblyPartViewportLoadState>>({});
  const [assemblyModelReadReady, setAssemblyModelReadReady] = useState(false);
  const [selectedTopologyReference, setSelectedTopologyReference] = useState<TopologyReference | null>(null);
  const [mcadAttachmentOpen, setMcadAttachmentOpen] = useState(false);
  const [freecadCollaborationOpen, setFreecadCollaborationOpen] = useState(false);
  const [mcadImportSource, setMcadImportSource] = useState<NativeSelectedFile | null>(null);
  const [sourceImport, setSourceImport] = useState<{ source?: NativeSelectedFile; kind: ImportSourceKind } | null>(null);
  const [harnessEditorOpen, setHarnessEditorOpen] = useState(false);
  const [tetraMeshOpen, setTetraMeshOpen] = useState(false);
  const [mcadFocusedPartId, setMcadFocusedPartId] = useState<string | null>(null);
  const [isolatedAssemblyPartId, setIsolatedAssemblyPartId] = useState<string | null>(null);
  const [assemblySection, setAssemblySection] = useState<AssemblySection>({ ...DEFAULT_ASSEMBLY_SECTION });
  const [bondManagerOpen, setBondManagerOpen] = useState(false);
  const [componentBonds, setComponentBonds] = useState<BondRecord[]>([]);
  const [bondValidation, setBondValidation] = useState<BondValidationResult[]>([]);
  const [status, setStatusState] = useState("Ready for design validation");
  const [activityLog, setActivityLog] = useState<ActivityEntry[]>([{
    id: 1,
    timestamp: new Date().toLocaleTimeString([], { hour12: false }),
    level: "success",
    source: "System",
    message: "SPIKE workspace initialized",
  }]);
  const [activityUnread, setActivityUnread] = useState(0);
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [activeWorkerOperation, setActiveWorkerOperation] = useState<{ id: string; method: string; cancelling: boolean } | null>(null);
  const universalRunning = analysisRunning || Boolean(activeWorkerOperation);
  const [operationDisplay, setOperationDisplay] = useState<OperationDisplay>(null);
  const [boardFile, setBoardFile] = useState("board_power_review.kicad_pcb");
  const [projectName, setProjectName] = useState("board_power_review.spike");
  const [boardData, setBoardData] = useState<ParsedBoard | null>(null);
  const [boardSource, setBoardSource] = useState("");
  const [deferredBoardVisual, setDeferredBoardVisual] = useState<{ board: ParsedBoard; sourceFile: string; source: string } | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false);
  const [showModels, setShowModels] = useState(true);
  const [showSmdModels, setShowSmdModels] = useState(true);
  const [showThtModels, setShowThtModels] = useState(true);
  const [analysisSetupWorkflow, setAnalysisSetupWorkflow] = useState<"single" | "path" | "batch">("single");
  const [cameraCommand, setCameraCommand] = useState("");
  const camera3DRef = useRef<Viewport3DCameraState>();
  const layout2DRef = useRef<Viewport2DState>();
  const [viewportRestore, setViewportRestore] = useState<ViewportRestoreCommand | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [iconGalleryOpen, setIconGalleryOpen] = useState(false);
  const [projectManagerOpen, setProjectManagerOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [helpDiagnosticCode, setHelpDiagnosticCode] = useState<string>();
  const [aboutOpen, setAboutOpen] = useState(false);
  const [benchmarkOpen, setBenchmarkOpen] = useState(false);
  const [spiceOpen, setSpiceOpen] = useState(false);
  const [pythonOpen, setPythonOpen] = useState(false);
  const [scriptViewport, setScriptViewport] = useState<ScriptViewportRun | null>(null);
  const showScriptViewport = (result: unknown, label: string, keepEditorOpen = false) => {
    try { setScriptViewport(completedScriptViewportRun(result, label)); setPythonOpen(keepEditorOpen); setStatus(`${label}: simulation output shown in viewport.`); }
    catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
  };
  const [contextScriptDraft, setContextScriptDraft] = useState<ContextScript | null>(null);
  useEffect(() => {
    const open = (event: Event) => { const draft = admitContextScript((event as CustomEvent).detail); if (!draft) return;
      setContextScriptDraft(draft); setPythonOpen(true); setStatus("Context opened as an unsaved Python draft. Review it before running."); };
    window.addEventListener(CONTEXT_SCRIPT_EVENT, open);
    return () => window.removeEventListener(CONTEXT_SCRIPT_EVENT, open);
  }, []);
  const [spiceWorkspace, setSpiceWorkspace] = useState<SpiceWorkspace>(() => defaultSpiceWorkspace("pi"));
  const [projectPath, setProjectPath] = useState<string | null>(null);
  const [projectManifestDigest, setProjectManifestDigest] = useState<string | null>(null);
  const [projectDirty, setProjectDirty] = useState(false);
  const [projectUpgradeOffer, setProjectUpgradeOffer] = useState<{ fileName: string; sourceFormat: string } | null>(null);
  const [unsavedPrompt, setUnsavedPrompt] = useState<{
    actionLabel: string;
    action: (() => void | Promise<void>) | null;
    closeWindow: boolean;
    onCancel?: () => void;
    preserveDirtyUntilApplied?: boolean;
  } | null>(null);
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>(() => {
    try { return JSON.parse(localStorage.getItem("spike.recent-projects.v1") ?? "[]") as RecentProject[]; }
    catch { return []; }
  });
  const [appSettings, setAppSettings] = useState<AppSettings>(loadAppSettings);
  const [extensionsOpen, setExtensionsOpen] = useState(false);
  const [selectedToolbarExtensionId, setSelectedToolbarExtensionId] = useState("");
  const [extensionCatalog, setExtensionCatalog] = useState<ExtensionCatalogEntry[]>(fallbackExtensionCatalog);
  useEffect(() => {
    if (!workerAvailable) return;
    let active = true;
    void runLocalWorker({ method: "list_extensions", params: {} }).then(response => {
      if (active && response.ok && Array.isArray(response.result?.extensions))
        setExtensionCatalog(response.result.extensions as ExtensionCatalogEntry[]);
    });
    return () => { active = false; };
  }, [workerAvailable]);
  const [extensionSelectedId, setExtensionSelectedId] = useState("");
  const [extensionSelectedContributionId, setExtensionSelectedContributionId] = useState("");
  const [extensionTrusting, setExtensionTrusting] = useState<string | null>(null);
  const [extensionTrustError, setExtensionTrustError] = useState("");
  const [harnessDocument, setHarnessDocument] = useState<Record<string, any> | null>(null);
  const [extensionResult, setExtensionResult] = useState<Record<string, unknown> | null>(null);
  const [emergeViewportBoardSource, setEmergeViewportBoardSource] = useState<string | null>(null);
  const [emergeEmiOpen, setEmergeEmiOpen] = useState(false);
  const [emergeSiOpen, setEmergeSiOpen] = useState(false);
  const [siSParameterSolver, setSiSParameterSolver] = useState<"internal" | "emerge">("internal");
  const [emergePatternIndex, setEmergePatternIndex] = useState(0);
  const [emergeEmiSetup, setEmergeEmiSetup] = useState<EMergeSetup>(() => defaultEMergeSetup(emiSetup.selected_nets[0] ?? ""));
  const [gerberImportOpen, setGerberImportOpen] = useState(false);
  const gerberSource = useMemo(() => activeGerberSource(boardSource, boardData?.stackup), [boardSource, boardData?.stackup]);
  const [emergeEmiRuntime, setEmergeEmiRuntime] = useState<Record<string, unknown> | null>(null);
  const emergeUpdates = useEMergeRuntimeUpdates(runLocalWorker);
  const [emergeEmiOperationBusy, setEmergeEmiBusy] = useState(false);
  const emergeEmiBusy = emergeEmiOperationBusy || emergeUpdates.running;
  const gerberRunBlocked = Boolean(gerberSource) && (emergeEmiRuntime?.gerber_available !== true || Boolean(gerberSource?.drills?.length));
  const [emergeScriptPreview, setEmergeScriptPreview] = useState<Record<string, unknown> | null>(null);
  const [optycalSource, setOptycalSource] = useState<Record<string, unknown> | null>(null);
  const [optycalPreview, setOptycalPreview] = useState<Record<string, unknown> | null>(null);
  const optycalGenerationRef = useRef(0);
  const invalidateOptycalPreview = () => { optycalGenerationRef.current += 1; setOptycalPreview(null); };
  useEffect(() => { if (admitOptycalSource(extensionResult)) { setOptycalSource(extensionResult); invalidateOptycalPreview(); } }, [extensionResult]);
  useEffect(() => { setOptycalSource(null); invalidateOptycalPreview(); }, [boardSource]);
  const emergePreviewGenerationRef = useRef(0);
  const invalidateEMergePreview = () => { emergePreviewGenerationRef.current += 1; setEmergeScriptPreview(null); };
  useEffect(() => { invalidateEMergePreview(); }, [boardSource]);
  const [emergeEmiError, setEmergeEmiError] = useState("");
  const emergeProbePathRef = useRef(emergeEmiSetup.python_executable);
  useEffect(() => {
    if (!emergeUpdates.state.operation_id || !["succeeded", "failed"].includes(emergeUpdates.state.status)) return;
    invalidateEMergePreview();
    const runtime = emergeUpdates.state.compatibility;
    if (typeof runtime?.available === "boolean" && (!emergeEmiSetup.python_executable.trim() || emergeUpdates.state.python_executable === emergeEmiSetup.python_executable.trim())) setEmergeEmiRuntime(runtime);
    else setEmergeEmiRuntime(null);
  }, [emergeUpdates.state.operation_id, emergeUpdates.state.status]);
  const savedEmergeInputRef = useRef<HTMLInputElement>(null);
  const savedBoardThermalInputRef = useRef<HTMLInputElement>(null);
  const emergeEmiExtension = extensionCatalog.find(item => item.id === "spike.emerge-suite");
  const emergeEmiCapabilities = Array.isArray(emergeEmiRuntime?.capabilities) ? emergeEmiRuntime.capabilities : [];
  const emergeSiAvailable = Boolean(emergeEmiExtension?.trusted && emergeEmiExtension.state !== "disabled"
    && emergeEmiExtension.contributes.analyses?.some(item => item.id === "emerge-si")
    && emergeEmiRuntime?.available === true && emergeEmiCapabilities.includes("si_s_parameters"));
  const [siProtocolSuitesOpen, setSiProtocolSuitesOpen] = useState(false);
  const [selectedSiSuite, setSelectedSiSuite] = useState<SiProtocolSuite | null>(null);
  const [siChannelResult, setSiChannelResult] = useState<Record<string, unknown> | null>(null);
  const extensionProtocolSuites = useMemo(() => extensionCatalog.flatMap(extension =>
    (extension.contributes.protocol_suites ?? [])
      .map(contribution => contribution.definition)
      .filter(definition => validateSiProtocolSuite(definition).length === 0) as SiProtocolSuite[]
  ), [extensionCatalog]);
  const [externalEnginesOpen, setExternalEnginesOpen] = useState(false);
  const [externalEngineCatalog, setExternalEngineCatalog] = useState<ExternalEngineCatalogEntry[]>(fallbackExternalEngines);
  const [accelerationCatalog, setAccelerationCatalog] = useState<AccelerationCatalogEntry[]>(fallbackAccelerators);
  const [solverManager, setSolverManager] = useState<SolverManagerCatalog>(fallbackSolverManager);
  const [solverSelections, setSolverSelections] = useState<Record<string, string>>({});
  const [workspaceOpenEMSSetup, setWorkspaceOpenEMSSetup] = useState(defaultOpenEMSSetup);
  const [acEffectsOpen, setAcEffectsOpen] = useState(false);
  const [acEffectsRequest, setAcEffectsRequest] = useState<Record<string, unknown> | null>(null);
  const [acEffectsResult, setAcEffectsResult] = useState<Record<string, unknown> | null>(null);
  const [extensionMesh, setExtensionMesh] = useState<Record<string, unknown> | null>(null);
  const [extensionWorkflowBusy, setExtensionWorkflowBusy] = useState(false);
  const extensionWorkflowDesignRef = useRef({ boardData, boardSource });
  extensionWorkflowDesignRef.current = { boardData, boardSource };
  useEffect(() => { setExtensionMesh(null); }, [boardData, boardSource]);
  const [externalCase, setExternalCase] = useState<ExternalCaseState | null>(null);
  const [externalEngineBusy, setExternalEngineBusy] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [resourceOpen, setResourceOpen] = useState(false);
  const notificationsOpen = dock === "Notifications" && bottomOpen;
  const [viewportQualityHost, setViewportQualityHost] = useState<HTMLSpanElement | null>(null);
  const [modelLoadStatus, setModelLoadStatus] = useState<ModelLoadStatus>({ board: "none", components: "none", assembly: "none", missingCount: 0, missingRefs: [], metrics: "" });
  const [revisionComparison, setRevisionComparison] = useState<RevisionComparison | null>(null);
  const [topologyEditor, setTopologyEditor] = useState<TopologyDomain | null>(null);
  const [netManagerOpen, setNetManagerOpen] = useState(false);
  const [assemblyLinksOpen, setAssemblyLinksOpen] = useState(false);
  const [assemblyWorkspaceOpen, setAssemblyWorkspaceOpen] = useState(false);
  const focusAssemblyTool = (kind: AssemblyToolKind) => {
    void focusAssemblyToolWindow(kind).catch(error => setStatus(`Could not focus assembly window: ${error instanceof Error ? error.message : String(error)}`));
  };
  const openAssemblyWorkspace = () => { setAssemblyWorkspaceOpen(true); focusAssemblyTool("workspace"); };
  const openAssemblyPlacement = () => { setAssemblyHandlingExpanded(true); focusAssemblyTool("placement"); };
  const openBoardManager = (tab: "layers" | "nets" | "links") => {
    if (assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1) {
      setLayersOpen(tab === "layers"); setNetManagerOpen(tab === "nets"); setAssemblyLinksOpen(tab === "links");
      focusAssemblyTool("managers");
    } else if (tab === "layers") setLayersOpen(true);
    else if (tab === "nets") setNetManagerOpen(true);
    else setAssemblyLinksOpen(true);
  };
  const [piTopology, setPiTopology] = useState<TopologyModel>(() => emptyTopology("pi"));
  const [siTopology, setSiTopology] = useState<TopologyModel>(() => emptyTopology("si"));
  const [thermalScenario, setThermalScenario] = useState<Record<string, unknown> | null>(null);
  const [thermalPreview, setThermalPreview] = useState<Record<string, unknown> | null>(null);
  const [thermalVisibility, setThermalVisibility] = useState<ThermalSceneVisibility>(defaultThermalSceneVisibility);
  const [renderTelemetry, setRenderTelemetry] = useState<RenderTelemetry>({ fps: 0, frameTimeMs: 0, drawCalls: 0, triangles: 0, geometries: 0, textures: 0, pixelRatio: 1 });
  const [processResources, setProcessResources] = useState<ProcessResources>({ source: "browser", cpuPercent: null, capacityCpuPercent: null, memoryBytes: null, hostMemoryBytes: null, totalMemoryBytes: null, logicalCpus: navigator.hardwareConcurrency || null, processCount: null, workerActive: false });
  const [shortcuts, setShortcuts] = useState<Record<ShortcutAction, string>>(() => {
    try {
      return { ...defaultShortcuts, ...JSON.parse(localStorage.getItem("spike.shortcuts") ?? "{}") };
    } catch {
      return defaultShortcuts;
    }
  });
  const projectInputRef = useRef<HTMLInputElement>(null);
  const browserBoardInputRef = useRef<HTMLInputElement>(null);
  const resultInputRef = useRef<HTMLInputElement>(null);
  const retainedProjectSnapshot = useRef<Record<string, any> | null>(null);
  const savedVisualDisposer = useRef<(() => void) | null>(null);
  const projectGeneration = useRef(0);
  const projectEditRevision = useRef(0);
  const comparisonInputRef = useRef<HTMLInputElement>(null);
  const historyRef = useRef<ProjectSnapshot[]>([]);
  const redoRef = useRef<ProjectSnapshot[]>([]);
  const projectDirtyRef = useRef(false);
  const allowWindowCloseRef = useRef(false);
  const startupProjectConsumedRef = useRef(false);
  const responsiveTierRef = useRef("");
  const activityIdRef = useRef(2);
  const externalNetSelection = useMemo(() => Array.from(new Set([
    selected?.net,
    isolatedNet,
    piSetup.net,
    ...emiSetup.selected_nets,
    ...emiSetup.return_nets,
    ...powerNets,
  ].filter((name): name is string => Boolean(name && name !== "No net")))), [selected?.net, isolatedNet, piSetup.net, emiSetup.selected_nets, emiSetup.return_nets, powerNets]);
  const harnessProjection = useMemo(() => buildVirtualHarnessVisualization(assemblyIr), [assemblyIr]);
  const virtualBoardProjection = useMemo(() => buildVirtualBoardVisualization(assemblyIr, assemblyDesigns), [assemblyIr, assemblyDesigns]);
  const assemblyOffsets = useMemo(() => assemblyExplodeOffsets(virtualBoardProjection.visuals, assemblyExplodedDistanceMm), [virtualBoardProjection.visuals, assemblyExplodedDistanceMm]);
  const displayHarnesses = useMemo(() => assemblyDisplayHarnesses(harnessProjection.visuals, assemblyBoardVisibility, assemblyOffsets), [harnessProjection.visuals, assemblyBoardVisibility, assemblyOffsets]);
  const selectedBoardInstance = useMemo(() => selectedBoardInstanceId
    ? virtualBoardProjection.visuals.find(board => board.id === selectedBoardInstanceId) ?? null
    : null, [selectedBoardInstanceId, virtualBoardProjection.visuals]);
  const selectedHarness = useMemo(() => selectedHarnessId
    ? harnessProjection.visuals.find(harness => harness.id === selectedHarnessId) ?? null
    : null, [harnessProjection.visuals, selectedHarnessId]);
  useEffect(() => {
    if (selectedHarnessId && !selectedHarness) setSelectedHarnessId(null);
  }, [selectedHarness, selectedHarnessId]);
  useEffect(() => {
    if (selectedBoardInstanceId && !selectedBoardInstance) setSelectedBoardInstanceId(null);
  }, [selectedBoardInstance, selectedBoardInstanceId]);

  const appendActivity = useCallback((message: string, source = "Application", level = activityLevel(message)) => {
    const normalized = message.replace(/\s+/g, " ").trim();
    if (!normalized) return;
    const issuedCode = normalized.match(/SPIKE-(?:FE|BE)-(?:APP|PROJECT|PACKAGE|IMPORT|VIEW|PI|SI|THERMAL|EMI|SPICE|SOLVER|MESH|PROBE|REPORT|EXT|IPC|SECURITY)-(?:I|W|P|E|C|S)-\d{4}/)?.[0]
      ?? source.match(/SPIKE-(?:FE|BE)-(?:APP|PROJECT|PACKAGE|IMPORT|VIEW|PI|SI|THERMAL|EMI|SPICE|SOLVER|MESH|PROBE|REPORT|EXT|IPC|SECURITY)-(?:I|W|P|E|C|S)-\d{4}/)?.[0]
      ?? (level === "error" ? "SPIKE-FE-APP-E-0001" : level === "warning" ? "SPIKE-FE-APP-W-0001" : "SPIKE-FE-APP-I-0001");
    const entry: ActivityEntry = {
      id: activityIdRef.current++,
      timestamp: new Date().toLocaleTimeString([], { hour12: false }),
      level,
      source: `${source} | ${issuedCode}`,
      message: normalized,
    };
    setActivityLog(current => [...current.slice(-399), entry]);
    setActivityUnread(current => Math.min(999, current + 1));
  }, []);
  const setStatus = useCallback((message: string) => {
    setStatusState(message);
    appendActivity(message);
  }, [appendActivity]);
  const boardImport = useBoardVisualImport(visual => setBoardData(current => current ? {
    ...current,
    fullModelUrl: undefined,
    boardModelUrl: visual.boardModelUrl,
    boardModelIncludesCopper: visual.boardModelIncludesCopper,
    componentModelUrl: visual.componentModelUrl,
    layoutLayerUrls: visual.layoutLayerUrls,
    layoutViewBox: visual.layoutViewBox,
    modelManifestUrl: visual.modelManifestUrl,
  } : current), setStatus);
  const prepareVisualBundleForBoard = boardImport.prepare;
  const assemblyBoardVisuals = useAssemblyBoardVisuals(assemblyDesigns, boardData, projectPath, projectManifestDigest, boardImport.whenReady, assemblyModelAssignments);
  const occurrenceHighlightBoards = useMemo(() => {
    const result: Record<string, ParsedBoard> = {};
    for (const visual of virtualBoardProjection.visuals) {
      const source = assemblyBoardVisuals.boards[visual.designId];
      const design = assemblyDesigns?.designs.find(row => row.design_id === visual.designId);
      if (source && design) result[visual.id] = { ...source, nets: Object.fromEntries(((design.nets ?? []) as Array<{ id: string; name: string }>).map(net => [net.id, net.name])) };
    }
    return result;
  }, [virtualBoardProjection, assemblyBoardVisuals.boards, assemblyDesigns]);
  const normalPassThroughNets = useMemo(() => {
    if (!passThroughHighlight || !boardData || selected?.type !== "component") return [];
    try { return assemblyNetHighlight({ boards: {normal: boardData}, assembly: {}, seed: {kind: "component", boardId: "normal", componentId: selected.id} }).nets.map(net => net.netName); }
    catch { return []; }
  }, [passThroughHighlight, boardData, selected]);
  useEffect(() => {
    if (!assemblyIr || !assemblyHighlightSeed || assemblyHighlightSeed.kind === "component" && !passThroughHighlight) { setLinkedAssemblyNets({}); return; }
    try {
      const highlight = assemblyNetHighlight({ boards: occurrenceHighlightBoards, assembly: assemblyIr, seed: assemblyHighlightSeed });
      setLinkedAssemblyNets(highlight.netsByBoard);
      setStatus(`${highlight.nets.length} scoped nets highlighted across ${Object.keys(highlight.netsByBoard).length} boards through explicit pin links${assemblyHighlightSeed.kind === "component" ? `; stops at ${highlight.componentBoundaries.length} boundary components; ground excluded` : ""}${highlight.unresolvedPinLinks.length ? `; ${highlight.unresolvedPinLinks.length} unresolved pin links` : ""}`);
    } catch (error) { setLinkedAssemblyNets({}); setStatus(error instanceof Error ? error.message : String(error)); }
  }, [assemblyIr, occurrenceHighlightBoards, assemblyHighlightSeed, passThroughHighlight]);
  const resolverBoards = useMemo(() => {
    if (assemblyDesigns) return assemblyDesigns.designs.flatMap(design => {
      const board = assemblyBoardVisuals.boards[design.design_id];
      return board ? [{id: design.design_id, name: design.name ?? design.design_id, board}] : [];
    });
    return boardData ? [{id: activeDesignId ?? "active", name: boardFile, board: boardData}] : [];
  }, [assemblyDesigns, assemblyBoardVisuals.boards, boardData, activeDesignId, boardFile]);
  const applyResolvedComponentModel = async (designId: string, componentRef: string, path: string, remember: boolean) => {
    const source = resolverBoards.find(row => row.id === designId)?.board;
    const component = source?.components.find(row => row.ref === componentRef);
    if (!component) throw new Error("Choose a component belonging to the retained board design.");
    const isActive = !assemblyDesigns || designId === assemblyDesigns.active_design_id;
    const previous = isActive ? modelAssignments : assemblyModelAssignments[designId] ?? {};
    const next = { ...previous, [componentRef]: path };
    const generation = projectGeneration.current;
    if (isActive) {
      if (!boardData) throw new Error("The active board is not loaded.");
      await boardImport.prepareComponents(boardData, boardFile, boardSource, next);
      if (generation !== projectGeneration.current) throw new Error("The project changed while the model was being prepared.");
      recordChange(); setModelAssignments(next);
    } else {
      if (!projectPath || !projectManifestDigest) throw new Error("Save the assembly as a native SPIKE package before resolving retained boards.");
      await boardImport.whenReady();
      const prepared = await runNativeProjectWorker({method: "prepare_assembly_design_visual_bundle", params: {project_path: projectPath, expected_manifest_payload_sha256: projectManifestDigest, design_id: designId, stage: "components", component_model_overrides: next}});
      if (!prepared.ok) throw new Error(prepared.error_detail?.detail ?? prepared.error ?? "Could not prepare component geometry.");
      const missing = (prepared.result?.quality as {missing_references?: string[]} | undefined)?.missing_references ?? [];
      if (missing.includes(componentRef)) throw new Error("The selected replacement could not be converted by KiCad; choose another model.");
      if (generation !== projectGeneration.current) throw new Error("The project changed while the model was being prepared.");
      recordChange(); setAssemblyModelAssignments(current => ({ ...current, [designId]: next }));
    }
    if (remember) {
      const saved = await runLocalWorker({method: "remember_3d_model", params: {footprint: component.library, path}});
      if (!saved.ok) throw new Error(saved.error_detail?.detail ?? saved.error ?? "Model applied, but the library mapping could not be remembered.");
    }
    setShowModels(true);
    setStatus(`${componentRef} uses a local 3D replacement; verify package placement. The display assignment is retained in the SPIKE project.`);
  };
  const assemblyOverlayState = useAssemblySavedResultOverlays(assemblyIr, boardImport.whenReady);
  const assemblySnapTargets = useMemo(() => {
    if (assemblySnapMode === "off") return [];
    return virtualBoardProjection.visuals.filter(visual => assemblyBoardVisibility[visual.id] !== false).flatMap(visual => {
      const source = assemblyBoardVisuals.boards[visual.designId];
      if (!source) return [];
      try { return extractAssemblySnapTargets(visual, source).filter(target => target.kind === assemblySnapMode); } catch { return []; }
    });
  }, [assemblySnapMode, virtualBoardProjection.visuals, assemblyBoardVisuals.boards, assemblyBoardVisibility]);
  const resetPreparedVisualBundle = () => {
    projectGeneration.current++;
    boardImport.reset();
    savedVisualDisposer.current?.(); savedVisualDisposer.current = null;
  };
  useEffect(() => () => savedVisualDisposer.current?.(), []);
  const tr = useCallback((key: string) => translate(appSettings.language, key), [appSettings.language]);
  const rememberProject = useCallback((name: string, path: string | null) => {
    const next = [{ name, path, openedAt: new Date().toISOString() }, ...recentProjects.filter(item => item.path ? item.path !== path : item.name !== name)].slice(0, 12);
    setRecentProjects(next);
    localStorage.setItem("spike.recent-projects.v1", JSON.stringify(next));
  }, [recentProjects]);
  const setProjectClean = useCallback(() => {
    projectDirtyRef.current = false;
    setProjectDirty(false);
  }, []);
  const markProjectDirty = useCallback(() => {
    projectEditRevision.current++;
    projectDirtyRef.current = true;
    setProjectDirty(true);
  }, []);

  useEffect(() => {
    document.documentElement.lang = appSettings.language;
    document.documentElement.dataset.theme = appSettings.theme;
    document.documentElement.dataset.renderQuality = appSettings.renderQuality;
    setNavigationInertia(appSettings.navigationInertia);
  }, [appSettings.language, appSettings.theme, appSettings.renderQuality, appSettings.navigationInertia]);

  useEffect(() => {
    if (dock === "Console" && bottomOpen) setActivityUnread(0);
  }, [dock, bottomOpen, activityLog.length]);

  useEffect(() => {
    const onCommand = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("button") : null;
      if (!(target instanceof HTMLButtonElement) || target.disabled || target.closest(".activity-console") || target.dataset.commandLog === "false") return;
      const label = target.getAttribute("aria-label") ?? target.getAttribute("title") ?? target.textContent ?? "";
      const normalized = label.replace(/\s+/g, " ").trim();
      if (normalized) {
        setStatusState(`Command: ${normalized}`);
        appendActivity(normalized, "Command", "info");
      }
    };
    const onError = (event: ErrorEvent) => appendActivity(event.message || "Unhandled browser error", "Runtime", "error");
    const onRejection = (event: PromiseRejectionEvent) => appendActivity(event.reason instanceof Error ? event.reason.message : String(event.reason), "Runtime", "error");
    const onWorkerActivity = (event: Event) => {
      const activity = (event as CustomEvent<WorkerActivity>).detail;
      if (!activity) return;
      const duration = activity.durationMs === undefined ? "" : ` in ${(activity.durationMs / 1000).toFixed(2)} s`;
      const level = activity.phase === "failed" || activity.phase === "rejected" ? "error" : "info";
      if (activity.heavy) {
        if (activity.phase === "started") setActiveWorkerOperation({ id: activity.operationId, method: activity.method, cancelling: false });
        else if (activity.phase === "cancelling") setActiveWorkerOperation(current => current?.id === activity.operationId ? { ...current, cancelling: true } : current);
        else if (["completed", "failed", "cancelled"].includes(activity.phase)) setActiveWorkerOperation(current => current?.id === activity.operationId ? null : current);
      }
      if (activity.phase === "cancelling") setStatusState(`Cancelling ${activity.method}...`);
      if (activity.phase === "cancelled") setStatusState(`[${activity.errorCode ?? "SPIKE-BE-SOLVER-E-0003"}] ${activity.message ?? `${activity.method} cancelled.`}`);
      if (activity.phase === "failed" || activity.phase === "rejected") {
        setStatusState(`[${activity.errorCode ?? "SPIKE-FE-APP-E-0001"}] ${activity.message ?? `${activity.method} failed.`}`);
      }
      appendActivity(
        activity.message ?? `${activity.method} ${activity.phase}${duration}`,
        `Worker | ${activity.errorCode ?? activity.operationId.slice(0, 8)}`,
        level,
      );
    };
    document.addEventListener("click", onCommand, true);
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    window.addEventListener("spike-worker-activity", onWorkerActivity);
    return () => {
      document.removeEventListener("click", onCommand, true);
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
      window.removeEventListener("spike-worker-activity", onWorkerActivity);
    };
  }, [appendActivity]);

  useEffect(() => {
    localStorage.setItem("spike.panel.left", String(leftPanelWidth));
    localStorage.setItem("spike.panel.right", String(rightPanelWidth));
    localStorage.setItem("spike.panel.bottom", String(bottomPanelHeight));
  }, [leftPanelWidth, rightPanelWidth, bottomPanelHeight]);

  useEffect(() => {
    let panel: HTMLElement | null = null;
    let offsetX = 0;
    let offsetY = 0;
    let minimizedSequence = 0;
    const minimizedPanels = new Map<string, { panel: HTMLElement; presentation: HTMLElement }>();
    const onPointerDown = (event: PointerEvent) => {
      const targetPanel = event.target instanceof Element ? event.target.closest(".floating-panel") : null;
      document.querySelectorAll<HTMLElement>(".floating-panel.panel-active").forEach(activePanel => {
        if (activePanel !== targetPanel) activePanel.classList.remove("panel-active");
      });
      if (targetPanel instanceof HTMLElement) targetPanel.classList.add("panel-active");
      const heading = event.target instanceof Element ? event.target.closest(".floating-heading") : null;
      if (!(heading instanceof HTMLElement) || event.target instanceof Element && event.target.closest("button, input, select, textarea")) return;
      const candidate = heading.closest(".floating-panel");
      if (!(candidate instanceof HTMLElement) || candidate.dataset.managedDock === "true") return;
      panel = candidate;
      const rect = panel.getBoundingClientRect();
      offsetX = event.clientX - rect.left;
      offsetY = event.clientY - rect.top;
      panel.classList.add("panel-free", "panel-moving");
      panel.classList.remove("panel-snap-left", "panel-snap-right", "panel-snap-bottom");
      Object.assign(panel.style, { left: `${rect.left}px`, top: `${rect.top}px`, right: "auto", bottom: "auto", transform: "none" });
      heading.setPointerCapture(event.pointerId);
      event.preventDefault();
    };
    const onPointerMove = (event: PointerEvent) => {
      if (!panel) return;
      const rect = panel.getBoundingClientRect();
      panel.style.left = `${Math.max(4, Math.min(window.innerWidth - rect.width - 4, event.clientX - offsetX))}px`;
      panel.style.top = `${Math.max(4, Math.min(Math.max(4, window.innerHeight - rect.height - 4), event.clientY - offsetY))}px`;
    };
    const onPointerUp = (event: PointerEvent) => {
      if (!panel) return;
      panel.classList.remove("panel-moving");
      if (event.clientY > window.innerHeight - 70) panel.classList.add("panel-snap-bottom");
      else if (event.clientX < 70) panel.classList.add("panel-snap-left");
      else if (event.clientX > window.innerWidth - 70) panel.classList.add("panel-snap-right");
      panel = null;
    };
    const onDoubleClick = (event: MouseEvent) => {
      const heading = event.target instanceof Element ? event.target.closest(".floating-heading") : null;
      if (!(heading instanceof HTMLElement) || event.target instanceof Element && event.target.closest("button")) return;
      const candidate = heading.closest(".floating-panel");
      if (!(candidate instanceof HTMLElement) || candidate.dataset.managedDock === "true" || candidate.dataset.minimizedToolId) return;
      const presentation = candidate.closest<HTMLElement>(".modal-shade, .modal-backdrop") ?? candidate;
      const id = `floating-panel-${++minimizedSequence}`;
      const label = heading.querySelector("b, strong, h1, h2, h3")?.textContent?.trim() || candidate.getAttribute("aria-label") || "Tool window";
      const closeControl = heading.querySelector<HTMLButtonElement>('button[aria-label^="Close"], button[title^="Close"]');
      const release = () => {
        presentation.classList.remove("workspace-tool-minimized");
        delete candidate.dataset.minimizedToolId;
        minimizedPanels.delete(id);
        removeMinimizedTool(id);
      };
      candidate.dataset.minimizedToolId = id;
      presentation.classList.add("workspace-tool-minimized");
      minimizedPanels.set(id, { panel: candidate, presentation });
      const registered = minimizeTool({
        id, label,
        restore: () => { release(); requestAnimationFrame(() => (heading.querySelector<HTMLElement>("button, [tabindex]") ?? heading).focus()); },
        ...(closeControl && !closeControl.disabled ? { close: () => { release(); closeControl.click(); } } : {}),
      });
      if (!registered) release();
    };
    const activatePanel = (candidate: HTMLElement) => {
      document.querySelectorAll<HTMLElement>(".floating-panel.panel-active").forEach(activePanel => {
        if (activePanel !== candidate) activePanel.classList.remove("panel-active");
      });
      candidate.classList.add("panel-active");
    };
    const panelObserver = new MutationObserver(records => {
      const addedPanels: HTMLElement[] = [];
      records.forEach(record => {
        record.addedNodes.forEach(node => {
          if (!(node instanceof HTMLElement)) return;
          if (node.matches(".floating-panel")) addedPanels.push(node);
          node.querySelectorAll<HTMLElement>(".floating-panel").forEach(candidate => addedPanels.push(candidate));
        });
        record.removedNodes.forEach(node => {
          if (!(node instanceof HTMLElement)) return;
          const removed = [node, ...node.querySelectorAll<HTMLElement>("[data-minimized-tool-id]")];
          removed.forEach(candidate => {
            const id = candidate.dataset.minimizedToolId;
            if (id) { minimizedPanels.delete(id); removeMinimizedTool(id); }
          });
        });
      });
      const newest = addedPanels[addedPanels.length - 1];
      if (newest) activatePanel(newest);
    });
    panelObserver.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
    document.addEventListener("dblclick", onDoubleClick);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("dblclick", onDoubleClick);
      panelObserver.disconnect();
      minimizedPanels.forEach(({ panel: candidate, presentation }, id) => {
        presentation.classList.remove("workspace-tool-minimized");
        delete candidate.dataset.minimizedToolId;
        removeMinimizedTool(id);
      });
    };
  }, []);

  const beginDockResize = (panel: "left" | "right" | "bottom") => (event: ReactPointerEvent<HTMLElement>) => {
    event.preventDefault();
    const handle = event.currentTarget;
    const pointerId = event.pointerId;
    handle.setPointerCapture(pointerId);
    handle.classList.add("is-resizing");
    const workspace = handle.closest(".workspace")?.getBoundingClientRect();
    let stopped = false;
    const move = (pointer: PointerEvent) => {
      if (pointer.pointerId !== pointerId) return;
      if (panel === "left" && workspace) setLeftPanelWidth(Math.max(170, Math.min(560, pointer.clientX - workspace.left)));
      if (panel === "right" && workspace) setRightPanelWidth(Math.max(210, Math.min(620, workspace.right - pointer.clientX)));
      if (panel === "bottom") setBottomPanelHeight(Math.max(72, Math.min(440, window.innerHeight - pointer.clientY - 25)));
    };
    const stop = () => {
      if (stopped) return;
      stopped = true;
      handle.classList.remove("is-resizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
      handle.removeEventListener("lostpointercapture", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    window.addEventListener("pointercancel", stop, { once: true });
    window.addEventListener("blur", stop, { once: true });
    handle.addEventListener("lostpointercapture", stop, { once: true });
  };

  const workspaceState = (): WorkspaceState => ({
    contract: "spike/workspace-state/v1",
    viewMode,
    docks: {
      leftOpen, rightOpen, bottomOpen, sidePanelsPinned, bottomPinned,
      leftWidthPx: leftPanelWidth, rightWidthPx: rightPanelWidth, bottomHeightPx: bottomPanelHeight,
      activeBottomDock: dock,
    },
    viewports: { threeD: camera3DRef.current, twoD: layout2DRef.current },
  });
  const restoreWorkspaceState = (value: unknown): boolean => {
    const restored = normalizeWorkspaceState(value);
    if (!restored) return false;
    setViewMode(restored.viewMode);
    setLeftOpen(restored.docks.leftOpen); setRightOpen(restored.docks.rightOpen); setBottomOpen(restored.docks.bottomOpen);
    setSidePanelsPinned(restored.docks.sidePanelsPinned); setBottomPinned(restored.docks.bottomPinned);
    setLeftPanelWidth(restored.docks.leftWidthPx); setRightPanelWidth(restored.docks.rightWidthPx); setBottomPanelHeight(restored.docks.bottomHeightPx);
    setDock(restored.docks.activeBottomDock);
    camera3DRef.current = restored.viewports.threeD;
    layout2DRef.current = restored.viewports.twoD;
    setViewportRestore({ token: Date.now(), ...restored.viewports });
    return restored.viewMode === "2D" ? Boolean(restored.viewports.twoD) : Boolean(restored.viewports.threeD);
  };
  const snapshot = (): ProjectSnapshot => ({ studies: structuredClone(studies), probes: structuredClone(probes), probeFormulaRows: structuredClone(probeFormulaRows), probeReferenceIds: { ...probeReferenceIds }, boardFile, frequency, solverId, formulation, solverSelections: { ...solverSelections }, piSetup: structuredClone(piSetup), piTopology: structuredClone(piTopology), siTopology: structuredClone(siTopology), selectedSiSuite: structuredClone(selectedSiSuite), siChannelResult: structuredClone(siChannelResult), spiceWorkspace: structuredClone(spiceWorkspace), emiSetup: structuredClone(emiSetup), emiPreflight: structuredClone(emiPreflight), emiScreening: structuredClone(emiScreening), emiFieldResult: structuredClone(emiFieldResult), thermalScenario: structuredClone(thermalScenario), componentBonds: structuredClone(componentBonds), visibleLayers: { ...visibleLayers }, assemblyLayerVisibility: structuredClone(assemblyLayerVisibility), assemblyLayerOpacity: structuredClone(assemblyLayerOpacity), assemblyBoardVisibility: { ...assemblyBoardVisibility }, assemblyExplodedDistanceMm, layerOpacity: { ...layerOpacity }, layerSeparation, showVias, showNetNames, showAxes, selected, selectionFilter, isolatedNet, modelAssignments: { ...modelAssignments }, assemblyModelAssignments: structuredClone(assemblyModelAssignments), assemblyIr: structuredClone(assemblyIr), assemblyDesigns: structuredClone(assemblyDesigns), assemblyPackageShapes: structuredClone(assemblyPackageShapes), modelIndex: structuredClone(modelIndex), showModels, showSmdModels, showThtModels, navigationInertia, viewMode, resultVisualization: { ...resultVisualization }, analysisResult, pdnReview: structuredClone(pdnReview), pdnReviewSourceId, workspace: workspaceState() });
  const restoreSnapshot = (next: ProjectSnapshot) => {
    setStudies(normalizeStudies(next.studies));
    setProbes(next.probes ?? []); setProbeFormulaRows(next.probeFormulaRows ?? []); setSavedProbeReferenceIds(next.probeReferenceIds ?? {});
    setBoardFile(next.boardFile); setFrequency(next.frequency); setSolverId(next.solverId ?? "auto"); setFormulation(next.formulation ?? "auto"); setVisibleLayers(next.visibleLayers); setAssemblyLayerVisibility(next.assemblyLayerVisibility ?? {}); setAssemblyLayerOpacity(next.assemblyLayerOpacity ?? {}); setAssemblyBoardVisibility(next.assemblyBoardVisibility ?? {}); setAssemblyExplodedDistanceMm(next.assemblyExplodedDistanceMm ?? 0);
    setSolverSelections(next.solverSelections ?? {});
    setPiSetup(normalizePiSetup(next.piSetup));
    setPiTopology(next.piTopology ?? emptyTopology("pi"));
    setSiTopology(next.siTopology ?? emptyTopology("si"));
    setSelectedSiSuite(next.selectedSiSuite ?? null);
    setSiChannelResult(next.siChannelResult ?? null);
    setSpiceWorkspace(normalizeSpiceWorkspace(next.spiceWorkspace));
    setEmiSetup(normalizeEmiSetup(next.emiSetup));
    setEmiPreflight(next.emiPreflight ?? null);
    setEmiScreening(next.emiScreening ?? null);
    setEmiFieldResult(normalizeEmiFieldResult(next.emiFieldResult));
    setThermalScenario(next.thermalScenario ?? null);
    setComponentBonds(next.componentBonds ?? []);
    setAssemblyIr(normalizeAssemblyIr(next.assemblyIr));
    setAssemblyDesigns(normalizeAssemblyDesigns(next.assemblyDesigns));
    setAssemblyPackageShapes(normalizeAssemblyPackageShapes(next.assemblyPackageShapes));
    setModelIndex(normalizeModelIndex(next.modelIndex));
    setBondValidation([]);
    setLayerOpacity(next.layerOpacity ?? {});
    setLayerSeparation(next.layerSeparation ?? 0); setShowVias(next.showVias ?? true); setShowNetNames(next.showNetNames ?? true); setShowAxes(next.showAxes ?? true); setNavigationInertia(next.navigationInertia ?? false);
    setSelected(next.selected); setSelectionFilter(next.selectionFilter ?? "all"); setIsolatedNet(next.isolatedNet ?? null); setModelAssignments(next.modelAssignments ?? {}); setAssemblyModelAssignments(next.assemblyModelAssignments ?? {}); setShowModels(next.showModels); setShowSmdModels(next.showSmdModels ?? true); setShowThtModels(next.showThtModels ?? true); setViewMode(next.viewMode);
    if (boardData && boardSource.trimStart().startsWith("(kicad_pcb") && JSON.stringify(next.modelAssignments ?? {}) !== JSON.stringify(modelAssignments)) {
      void boardImport.prepareComponents(boardData, boardFile, boardSource, next.modelAssignments ?? {}).catch(error => setStatus(`Restoring model assignments: ${error instanceof Error ? error.message : String(error)}`));
    }
    setResultVisualization({ ...defaultResultVisualization(), ...(next.resultVisualization ?? {}) }); setAnalysisResult(next.analysisResult ?? null); setPdnReview(next.pdnReview ?? null); setPdnReviewSourceId(next.pdnReviewSourceId ?? null);
    restoreWorkspaceState(next.workspace);
  };
  const recordChange = () => { historyRef.current = [...historyRef.current.slice(-49), snapshot()]; redoRef.current = []; markProjectDirty(); };
  const studyTypeForTab = (): string => tab === "HF / SI" || (tab === "Solve" && simulationDomain === "si") ? "si" : tab === "EM" ? "em" : tab === "Thermal" ? "thermal" : "pi";
  const studyObject = (value: unknown): StudyJsonObject => JSON.parse(JSON.stringify(value)) as StudyJsonObject;
  const studyEMergeSetup = (value: unknown): EMergeSetup => {
    const defaults = defaultEMergeSetup();
    if (!value || typeof value !== "object" || Array.isArray(value)) return defaults;
    const saved = value as Record<string, unknown>;
    return Object.fromEntries(Object.entries(defaults).map(([key, fallback]) => [key, typeof saved[key] === typeof fallback ? saved[key] : fallback])) as EMergeSetup;
  };
  const currentStudySettings = (type: string): StudyJsonObject => {
    if (type === "pi") return studyObject({ boardFile, designId: activeDesignId, mode: analysisMode, solverId, formulation, powerNets, piSetup, limits, frequency });
    if (type === "si") return studyObject({ boardFile, designId: activeDesignId, siSParameterSolver, selectedSiSuite, siTopology, emergeEmiSetup });
    if (type === "em") return studyObject({ boardFile, designId: activeDesignId, emiSetup, emergeEmiSetup });
    if (type === "thermal") {
      const scenario = { ...(thermalScenario ?? {}) };
      for (const key of ["result", "field_result", "board_thermal_result"]) delete scenario[key];
      return studyObject({ boardFile, designId: activeDesignId, scenario });
    }
    return studyObject({ boardFile, designId: activeDesignId });
  };
  const currentStudyResult = (type: string): unknown => {
    if (type === "pi") return analysisResult;
    if (type === "si") return siSParameterSolver === "emerge" && (extensionResult?.data as Record<string, unknown> | undefined)?.analysis_result
      ? { provider: "emerge", extensionResult } : siChannelResult;
    if (type === "em") return extensionResult && emergeRadiationPatterns(extensionResult).length && emergeViewportBoardSource === boardSource
      ? { provider: "emerge", extensionResult } : emiFieldResult ? { provider: "openems", fieldResult: emiFieldResult } : null;
    if (type === "thermal") {
      const scenario = thermalScenario ?? {};
      return Object.fromEntries(["result", "field_result", "board_thermal_result", "board_thermal_request"].filter(key => scenario[key] !== undefined).map(key => [key, scenario[key]]));
    }
    return null;
  };
  const attachStudyDataset = (name: string, payload: unknown): string => {
    const dataset = prepareStudyDataset(JSON.stringify(payload), { name, format: "json", provenance: "Published Python analysis result", resultDerived: true });
    const target = studies.find(study => study.cases.some(item => item.id === activeStudyCaseId) && !study.archived) ?? studies.find(study => !study.archived);
    const checked = preflightStudyDatasetUpdate([...(target?.datasets ?? []), dataset], target);
    if (!checked.ok) throw new Error(checked.error);
    recordChange();
    if (target) setStudies(current => updateStudy(current, target.id, { datasets: [...target.datasets, dataset] }).map(study => study.id === target.id && activeStudyCaseId ? updateStudyCase(study, activeStudyCaseId, { datasetIds: [...(study.cases.find(item => item.id === activeStudyCaseId)?.datasetIds ?? []), dataset.id] }) : study));
    else { const added = createStudy("Python datasets"); added.datasets = [dataset]; setStudies(current => [...current, added]); }
    const message = name + " attached to the project study. Save the project to retain it.";
    setStatus(message); setStudyManagerOpen(true); return message;
  };
  const editStudyCase = (studyId: string, caseId: string, patch: Partial<SimulationStudyCase>) => {
    try { const updated = studies.map(study => study.id === studyId ? updateStudyCase(study, caseId, patch) : study); recordChange(); setStudies(updated); return true; }
    catch (error) { setStatus(`Study update rejected: ${error instanceof Error ? error.message : String(error)}`); return false; }
  };
  const activateStudyCase = (studyId: string, item: SimulationStudyCase) => {
    if (!["pi", "si", "em", "thermal"].includes(item.type)) { setStatus(`Simulation type ${item.type} is not supported by this workspace.`); return; }
    if (item.settings.boardFile && item.settings.boardFile !== boardFile) { setStatus(`Case ${item.name} belongs to ${item.settings.boardFile}; load that board before activating it.`); return; }
    if (item.settings.designId && activeDesignId && item.settings.designId !== activeDesignId) { setStatus(`Case ${item.name} belongs to another design. Load that design before activating it.`); return; }
    recordChange();
    const settings = item.settings as Record<string, any>;
    const result = item.resultSnapshot;
    if (item.type === "pi") {
      setAnalysisResult(null); setResultDisplay("none");
      setAnalysisMode(typeof settings.mode === "string" ? settings.mode : item.mode || "DC IR Drop");
      setSolverId(typeof settings.solverId === "string" ? settings.solverId : "auto");
      setFormulation(typeof settings.formulation === "string" ? settings.formulation : "auto");
      if (Array.isArray(settings.powerNets)) setPowerNets(settings.powerNets.filter((net: unknown): net is string => typeof net === "string"));
      if (settings.piSetup) setPiSetup(normalizePiSetup(settings.piSetup));
      if (settings.limits) setLimits(settings.limits);
      if (typeof settings.frequency === "string") setFrequency(settings.frequency);
      if (result && isSupportedSavedResult(result)) {
        const bundle = normalizeSolverResult(result as SolverResultBundle);
        if (bundle) {
          setAnalysisResult(bundle);
          setResultRecords(current => boundedResultRecords([...current.filter(record => record.id !== bundle.analysis_id), resultRecord(bundle, current.length)]));
          setResultDisplay(bundle.analysis_id);
          setResultVisualization(current => ({ ...current, visible: true }));
        }
      }
      setSimulationDomain("pi"); setTab("PI");
    } else if (item.type === "si") {
      setSiChannelResult(null);
      setSiSParameterSolver(settings.siSParameterSolver === "emerge" ? "emerge" : "internal");
      if (settings.selectedSiSuite && validateSiProtocolSuite(settings.selectedSiSuite).length === 0) setSelectedSiSuite(settings.selectedSiSuite as SiProtocolSuite);
      if (settings.siTopology?.contract === "spike/topology/v1" && Array.isArray(settings.siTopology.nodes) && Array.isArray(settings.siTopology.edges)) setSiTopology(settings.siTopology as TopologyModel);
      if (settings.emergeEmiSetup) setEmergeEmiSetup(studyEMergeSetup(settings.emergeEmiSetup));
      if (result && typeof result === "object" && (result as Record<string, unknown>).provider === "emerge") {
        const saved = (result as Record<string, any>).extensionResult;
        if (saved && typeof saved === "object" && !Array.isArray(saved)) setExtensionResult(saved as Record<string, unknown>);
      } else if (result && typeof result === "object" && ["spike/si-channel-result/v1", "spike/si-workflow-result/v1"].includes(String((result as Record<string, unknown>).contract))) setSiChannelResult(result as Record<string, unknown>);
      setSimulationDomain("si"); setTab("HF / SI");
    } else if (item.type === "em") {
      setEmiFieldResult(null);
      if (settings.emiSetup) setEmiSetup(normalizeEmiSetup(settings.emiSetup));
      if (settings.emergeEmiSetup) setEmergeEmiSetup(studyEMergeSetup(settings.emergeEmiSetup));
      setEmiPreflight(null); setExternalCase(null);
      setExtensionResult(null); setEmergeViewportBoardSource(null);
      if (result && typeof result === "object" && (result as Record<string, unknown>).provider === "emerge") {
        const saved = (result as Record<string, any>).extensionResult;
        if (saved && typeof saved === "object" && !Array.isArray(saved) && emergeRadiationPatterns(saved as Record<string, unknown>).length) {
          setExtensionResult(saved as Record<string, unknown>);
          setEmergeViewportBoardSource(boardSource); setEmergePatternIndex(0); setEmiChamberOpen(true);
        }
      } else if (result) setEmiFieldResult(normalizeEmiFieldResult((result as Record<string, any>).fieldResult ?? result));
      setTab("EM"); setEmiSection("solver");
    } else {
      const scenario = settings.scenario && typeof settings.scenario === "object" ? settings.scenario : {};
      setThermalScenario({ ...scenario, ...(result && typeof result === "object" ? result as Record<string, unknown> : {}) });
      setTab("Thermal");
    }
    setActiveStudyCaseId(item.id); setStudyManagerOpen(false);
    setStatus(`${item.name} activated from study. Review setup, run the analysis, then capture its result.`);
  };
  const addCaseToStudy = (studyId: string, type: string) => {
    const useWorkspace = type === studyTypeForTab();
    const settings = useWorkspace ? currentStudySettings(type) : studyObject({ boardFile });
    const mode = type === "pi" ? useWorkspace ? analysisMode : "DC IR Drop" : type === "thermal" ? String(thermalScenario?.mode ?? "") : "";
    recordChange();
    setStudies(current => current.map(study => study.id === studyId ? addStudyCase(study, type, undefined, { label: "" }, settings, mode) : study));
    setStatus(`${type.toUpperCase()} case added. Activate it to configure its simulation.`);
  };
  const saveCaseSetup = (studyId: string, item: SimulationStudyCase) => {
    if (activeStudyCaseId !== item.id) { setStatus(`Activate ${item.name} before saving its setup.`); return; }
    const settings = currentStudySettings(item.type);
    const mode = item.type === "pi" ? analysisMode : item.type === "thermal" ? String(thermalScenario?.mode ?? "") : item.mode;
    if (!editStudyCase(studyId, item.id, { settings, mode })) return;
    setStatus(`${item.name} setup saved in its study.`);
  };
  const captureCaseResult = (studyId: string, item: SimulationStudyCase) => {
    if (activeStudyCaseId !== item.id) { setStatus(`Activate ${item.name} before capturing a result.`); return; }
    const result = currentStudyResult(item.type);
    if (!result || (item.type === "thermal" && !["result", "field_result", "board_thermal_result"].some(key => (result as Record<string, unknown>)[key] != null))) { setStatus(`No ${item.type.toUpperCase()} result is available to capture for ${item.name}.`); return; }
    const captureCheck = preflightStudyRunCapture(result, studies.find(study => study.id === studyId), item);
    if (!captureCheck.ok) { setStatus(captureCheck.error); return; }
    const capturedMode = item.type === "pi" ? analysisMode : item.type === "thermal" ? String(thermalScenario?.mode ?? "") : item.mode;
    if (!editStudyCase(studyId, item.id, { mode: capturedMode, settings: currentStudySettings(item.type), resultSnapshot: JSON.parse(JSON.stringify(result)) as SimulationStudyCase["resultSnapshot"] })) return;
    setStatus(`${item.name} result captured in its study. Save the project to keep it.`);
  };
  mcpRequestHandler.current = ({ command, args }) => {
    if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("Command arguments must be an object");
    if (["analysis_view_result", "analysis_generate_report"].includes(command)) return mcpAnalysisCallbacks.current.resultAction(command, args);
    if (["analysis_context", "analysis_describe", "analysis_prepare", "analysis_patch", "analysis_preflight", "analysis_run", "analysis_job", "analysis_evidence"].includes(command)) return mcpAnalysisConversation.current!.handle(command, args);
    if (command === "status") return {
      workspace: tab, viewMode, projectName, boardFile, boardLoaded: Boolean(boardData),
      studyCount: studies.length, activeStudyCaseId, workerAvailable,
    };
    if (command === "select_workspace") {
      const workspace = args.workspace === "SI" ? "HF / SI" : args.workspace;
      if (!["PI", "HF / SI", "EM", "Thermal", "Results", "Reports"].includes(String(workspace))) throw new Error("Unsupported workspace");
      setTab(workspace as RibbonTab);
      setStatus(`${workspace} workspace selected by local MCP client`);
      return { workspace };
    }
    if (command === "set_view_mode") {
      if (args.mode !== "2D" && args.mode !== "3D") throw new Error("View mode must be 2D or 3D");
      setViewMode(args.mode);
      if (args.mode === "2D") setNavigationMode("pan");
      return { viewMode: args.mode };
    }
    if (command === "list_studies") return studies.map(study => ({
      id: study.id, name: study.name, notes: study.notes,
      cases: study.cases.map(item => ({ id: item.id, name: item.name, type: item.type, mode: item.mode, hasResult: item.resultSnapshot !== undefined })),
    }));
    if (command === "create_study") {
      if (typeof args.name !== "string" || !args.name.trim() || args.name.length > 120) throw new Error("Study name must be 1–120 characters");
      recordChange();
      const study = createStudy(args.name);
      setStudies(current => [...current, study]);
      setStatus(`${study.name} created by local MCP client; save the project to keep it`);
      return { id: study.id, name: study.name };
    }
    if (command === "add_study_case") {
      const studyId = args.studyId;
      const type = args.type;
      if (typeof studyId !== "string" || !studies.some(study => study.id === studyId)) throw new Error("Study was not found");
      if (!["pi", "si", "em", "thermal"].includes(String(type))) throw new Error("Unsupported simulation type");
      const settings = type === studyTypeForTab() ? currentStudySettings(type as string) : studyObject({ boardFile });
      const study = studies.find(row => row.id === studyId)!;
      const updated = addStudyCase(study, type as string, undefined, { label: "" }, settings);
      const added = updated.cases[updated.cases.length - 1];
      recordChange();
      setStudies(current => current.map(row => row.id === studyId ? updated : row));
      setStatus(`${added.name} added by local MCP client; save the project to keep it`);
      return { studyId, caseId: added.id, type: added.type, name: added.name };
    }
    if (command === "activate_study_case") {
      const study = studies.find(row => row.id === args.studyId);
      const item = study?.cases.find(row => row.id === args.caseId);
      if (!study || !item) throw new Error("Study case was not found");
      if (item.settings.boardFile && item.settings.boardFile !== boardFile) throw new Error("Load the case's board before activating it");
      if (item.settings.designId && activeDesignId && item.settings.designId !== activeDesignId) throw new Error("Load the case's design before activating it");
      activateStudyCase(study.id, item);
      return { studyId: study.id, caseId: item.id, workspace: item.type };
    }
    if (command === "open_run_controls") {
      if (tab === "PI" || (tab === "Solve" && simulationDomain === "pi")) setDcRunOpen(true);
      else if (tab === "HF / SI" || (tab === "Solve" && simulationDomain === "si")) openSiWorkbench("geometry", "channel");
      else if (tab === "EM") { setRightOpen(true); setEmiSection("solver"); }
      else if (tab === "Thermal") setThermalOpen(true);
      else throw new Error("Select a PI, SI, EM, or Thermal workspace first");
      return { workspace: tab, opened: true };
    }
    throw new Error("Unsupported desktop command");
  };
  useEffect(() => {
    if (!desktopShell) return;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    void listenMcpBridge(async request => {
      try {
        const result = await mcpRequestHandler.current(request);
        void respondMcpBridge(request.requestId, result).catch(cause => setStatus(`MCP reply failed: ${String(cause)}`));
      } catch (cause) {
        void respondMcpBridge(request.requestId, undefined, cause instanceof Error ? cause.message : String(cause))
          .catch(replyCause => setStatus(`MCP reply failed: ${String(replyCause)}`));
      }
    }).then(stop => { if (disposed) stop(); else unlisten = stop; }).catch(cause => setStatus(`MCP listener unavailable: ${String(cause)}`));
    return () => { disposed = true; unlisten?.(); };
  }, [desktopShell]);
  const undo = () => { const previous = historyRef.current.pop(); if (!previous) { setStatus("Nothing to undo"); return; } redoRef.current.push(snapshot()); restoreSnapshot(previous); markProjectDirty(); setStatus("Change undone"); };
  const redo = () => { const next = redoRef.current.pop(); if (!next) { setStatus("Nothing to redo"); return; } historyRef.current.push(snapshot()); restoreSnapshot(next); markProjectDirty(); setStatus("Change redone"); };
  const download = (name: string, content: string, type = "application/json") => { const url = URL.createObjectURL(new Blob([content], { type })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1500); };
  const downloadBlob = (name: string, blob: Blob) => { const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); };
  const projectData = () => createProjectPackage(mergeProjectSnapshot(retainedProjectSnapshot.current, { board_visuals: null, harness: harnessDocument, project: { name: projectName }, studies, design: { canonical_design: canonicalSpiDeR, source_file: boardFile, source_format: boardFile.endsWith(".spike-design.json") ? "spike-normalized" : "kicad_pcb", source_board: boardSource, stackup: boardData?.stackup ?? [], technology: boardData?.technology ?? "rigid", regions: boardData?.regions ?? [], bend_lines: boardData?.bendLines ?? [], model_assignments: modelAssignments, component_bonds: componentBonds, topologies: { pi: piTopology, si: siTopology } }, assembly_ir: assemblyIr, assembly_designs: assemblyDesigns, assembly_package_shapes: assemblyPackageShapes, models: modelIndex, analysis: retainOpaqueResultState(retainedProjectSnapshot.current?.analysis, { mode: analysisMode, solver_id: solverId, formulation, solver_selections: solverSelections, extension_workflows: { openems_setup: workspaceOpenEMSSetup, emerge_setup: emergeEmiSetup }, ac_power_integrity: { request: acEffectsRequest, result: acEffectsResult }, power_nets: powerNets, pi_setup: piSetup, si: { suite: selectedSiSuite, latest_channel_result: siChannelResult }, limits, frequency, visible_layers: visibleLayers, assembly_layer_visibility: assemblyLayerVisibility, assembly_layer_opacity: assemblyLayerOpacity, assembly_model_assignments: assemblyModelAssignments, assembly_display: { visibility: assemblyBoardVisibility, exploded_distance_mm: assemblyExplodedDistanceMm, presentation_only: true }, layer_opacity: layerOpacity, layer_separation_mm: layerSeparation, show_vias: showVias, show_net_names: showNetNames, show_axes: showAxes, show_models: showModels, show_smd_models: showSmdModels, show_tht_models: showThtModels, navigation_inertia: navigationInertia, view_mode: viewMode, selection_filter: selectionFilter, isolated_net: isolatedNet, result_visualization: resultVisualization, em_viewport_settings: emViewportSettings, result_display: resultDisplay, latest_result: analysisResult, result_history: resultRecords.map(record => ({ id: record.id, label: record.label, bundle: record.bundle })), pdn_review: pdnReview, pdn_review_source_id: pdnReviewSourceId, selected_net_geometry: boardData && isolatedNet ? extractNetGeometry(boardData, isolatedNet) : null }, isSupportedSavedResult), spice: { workspace: spiceWorkspace }, emi: { setup: emiSetup, preflight: emiPreflight, screening: emiScreening, field_result: emiFieldResult }, thermal: { scenario: thermalScenario, component_bonds: componentBonds }, workspace: workspaceState(), probes, probe_table: { calculated_rows: probeFormulaRows, reference_ids: probeReferenceIds }, selection: selected }));
  const performNewProject = () => { setHarnessDocument(null); setProjectUpgradeOffer(null);
    retainedProjectSnapshot.current = null;
    resetPreparedVisualBundle();
    setDeferredBoardVisual(null);
    historyRef.current = []; redoRef.current = []; setStudies([]); setActiveStudyCaseId(null); setStudyManagerOpen(false); setProjectName("untitled.spike"); setProjectPath(null); setProjectManifestDigest(null); setActiveDesignId(null); setCanonicalSpiDeR(null); setBoardFile("untitled.kicad_pcb"); setBoardSource(""); setBoardData(null); setSelected(null); setSolverSelections({}); setPiSetup(defaultPiSetup()); setPiTopology(emptyTopology("pi")); setSiTopology(emptyTopology("si")); setSelectedSiSuite(null); setSiChannelResult(null); setSpiceWorkspace(defaultSpiceWorkspace("pi")); setEmiSetup(defaultEmiSetup()); setEmiPreflight(null); setEmiScreening(null); setEmiFieldResult(null); setThermalScenario(null); setComponentBonds([]); setAssemblyIr(null); setAssemblyDesigns(null); setAssemblyLayerVisibility({}); setAssemblyLayerOpacity({}); setAssemblyBoardVisibility({}); setAssemblyExplodedDistanceMm(0); setAssemblySnapMode("off"); setAssemblyPackageShapes(null); setModelIndex(normalizeModelIndex(null)); setBondValidation([]); setProbes([]); setProbeFormulaRows([]); setSavedProbeReferenceIds({}); setAnalysisResult(null); setPdnReview(null); setPdnReviewSourceId(null); setResultRecords([]); setResultDisplay("none"); setAnalysisSummary(null); setProjectManagerOpen(false); setProjectClean(); setStatus("New SPIKE project created");
  };
  const requestUnsavedAction = (actionLabel: string, action: () => void | Promise<void>) => {
    if (assemblyToolDraftOwnerRef.current) { setStatus(`Finish or discard the assembly ${assemblyToolDraftOwnerRef.current} draft before you ${actionLabel}.`); return; }
    if (!projectDirtyRef.current) { void action(); return; }
    setUnsavedPrompt({ actionLabel, action, closeWindow: false });
  };
  const newProject = () => requestUnsavedAction("create a new project", performNewProject);
  const saveProject = async (name = projectFileName(projectName), forceSaveAs = false, markCurrentClean = true, includeResults = true, adoptSavedFile = true, preserveSourcePath = false): Promise<boolean> => {
    if (assemblyToolDraftOwnerRef.current) { setStatus(`Save or discard edits in the assembly ${assemblyToolDraftOwnerRef.current} tool before saving the main project.`); return false; }
    const generation = projectGeneration.current;
    const editRevision = projectEditRevision.current;
    let snapshot = projectData();
    try {
      if (snapshot.design.source_format === "spike-normalized") {
        setStatus("Preparing lossless normalized project source");
        snapshot = createProjectPackage({ ...snapshot, design: { ...snapshot.design, canonical_design: null, source_board: await compressNormalizedSnapshot(snapshot.design.source_board) } });
      }
      if (boardImport.progress?.busy) setStatus("Waiting for imported models and layers before saving");
      const prepared = await boardImport.whenReady();
      const visuals = await serializeBoardVisuals(prepared ?? boardData, setStatus);
      if (generation !== projectGeneration.current) throw new Error("The active project changed during save preparation. Save the current project again.");
      if (desktopShell) {
        const path = projectPath && !forceSaveAs ? projectPath : await selectNativeProjectSavePath(name);
        if (!path) { setStatus("Project save cancelled"); return false; }
        if (!adoptSavedFile && projectPath && path.toLowerCase() === projectPath.toLowerCase()) throw new Error("Choose a different path for the result-free project copy.");
        if (preserveSourcePath && projectPath && path.toLowerCase() === projectPath.toLowerCase()) throw new Error("Choose a new path so the original older-format project is preserved.");
        if (generation !== projectGeneration.current) throw new Error("The active project changed while choosing a save path.");
        const response = await runNativeProjectWorker({ method: "write_project_package", params: { path, snapshot, visuals, profile: "portable_project", base_package_path: projectPath, include_results: includeResults } });
        if (!response.ok) throw new Error(response.error ?? "The project package worker rejected the save.");
        if (generation !== projectGeneration.current) return true; // The saved snapshot must not replace a newly opened project's identity.
        const manifestDigest = (response.result as any)?.manifest?.manifest_payload_sha256;
        if (typeof manifestDigest !== "string" || !/^[0-9a-f]{64}$/.test(manifestDigest)) throw new Error("The project package worker did not return a valid manifest identity.");
        const designId = String((response.result as any)?.design_id ?? "").trim();
        if (!designId) throw new Error("The project package worker did not return a canonical design identity.");
        const savedDesign = (response.result as any)?.design_ir;
        if (adoptSavedFile) {
          setCanonicalSpiDeR(savedDesign?.contract === "spike/design-ir/v2" ? savedDesign : null);
          setProjectPath(path); setProjectManifestDigest(manifestDigest); setActiveDesignId(designId); rememberProject(projectName, path);
          setProjectUpgradeOffer(null);
        }
        setStatus(`Project package saved ${includeResults ? "with" : "without"} results: ${path}`);
      } else {
        const content = JSON.stringify({ ...(includeResults ? snapshot : withoutSavedResults(snapshot)), board_visuals: visuals }, null, 2);
        download(name.replace(/\.spike$/i, ".spike.json"), content, "application/vnd.spike.legacy-project+json"); if (adoptSavedFile) rememberProject(projectName, null); setStatus("Browser preview exported a legacy JSON snapshot; canonical .spike v3 packages require the desktop shell");
      }
      if (adoptSavedFile) retainedProjectSnapshot.current = snapshot;
      if (adoptSavedFile && markCurrentClean && editRevision === projectEditRevision.current) setProjectClean();
      return true;
    } catch (error) { setStatus(error instanceof Error ? `Project save failed: ${error.message}` : "Project save failed"); return false; }
  };
  const saveInstance = () => {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    void saveProject(`${projectName.replace(/\.spike$/i, "")}-${stamp}.spike`, true, false);
  };
  const applyProjectPackage = async (text: string, fileName: string, path: string | null, manifestDigest: string | null = null, canonicalDesignId: string | null = null, canonicalDesign: Record<string, unknown> | null = null) => {
    setProjectUpgradeOffer(null);
    const { project: data, migrated } = parseProjectPackage(text);
    const loadedStudies = normalizeStudies(data.studies);
    setHarnessDocument(data.harness?.contract === "spike/harness/v1" ? data.harness : null);
    const analysis = data.analysis ?? {};
    let source = data.design?.source_board ?? "";
    const sourceFile = data.design?.source_file ?? data.design?.board_file ?? data.board ?? fileName;
    if (source && (sourceFile.endsWith(".spike-design.json") || data.design?.source_format === "spike-normalized")) source = await hydrateNormalizedSnapshot(source, canonicalDesign);
    let parsed = source ? await parseDesignSourceOffThread(sourceFile, source, String(data.design?.source_format ?? "kicad")) : null;
    let knownVisuals = parsed ? await configureKnownVisuals(parsed, sourceFile, source) : false;
    let restoredVisuals: Awaited<ReturnType<typeof restoreBoardVisuals>> | null = null;
    if (parsed && data.board_visuals) {
      restoredVisuals = await restoreBoardVisuals(parsed, data.board_visuals, path && manifestDigest ? async stage => {
        const response = await runNativeProjectWorker({ method: "read_project_visual_bundle", params: {
          path, stage, index: data.board_visuals, expected_manifest_payload_sha256: manifestDigest,
        } });
        if (!response.ok) throw new Error(response.error ?? "Could not restore saved visuals.");
        return response.result;
      } : undefined, setStatus);
      parsed = restoredVisuals.board;
      knownVisuals = true;
    }
    resetPreparedVisualBundle();
    savedVisualDisposer.current = restoredVisuals?.dispose ?? null;
    retainedProjectSnapshot.current = data;
    setStudies(loadedStudies); setActiveStudyCaseId(null);
    canonicalDesign ??= data.design?.canonical_design ?? null;
    const nextName = data.project?.name ?? fileName.replace(/\.spike(?:\.json)?$/i, ".spike");
    setProjectName(nextName); setProjectPath(path); setProjectManifestDigest(manifestDigest); setActiveDesignId(canonicalDesignId ?? (typeof data.design?.design_id === "string" ? data.design.design_id : null)); setCanonicalSpiDeR(canonicalDesign?.contract === "spike/design-ir/v2" ? canonicalDesign : null); setBoardFile(data.design?.source_file ?? data.design?.board_file ?? data.board ?? fileName);
    setBoardSource(source); setBoardData(parsed); setModelAssignments(data.design?.model_assignments ?? {});
    const indexedVisualModels = Array.isArray(data.models?.models)
      && data.models.models.some((model: any) => model?.model_type === "gltf" || model?.model_type === "glb");
    // Verified package model reads have priority over a derived footprint scene;
    // both are heavy operations and must not race the identity-gated artifact API.
    if (parsed && !knownVisuals && indexedVisualModels) {
      setAssemblyModelReadReady(false);
      setDeferredBoardVisual({ board: parsed, sourceFile, source });
    } else {
      setDeferredBoardVisual(null);
      if (parsed && !knownVisuals && !sourceFile.endsWith(".spike-design.json")) void prepareVisualBundleForBoard(parsed, sourceFile, source, undefined, data.design?.model_assignments ?? {});
    }
    setAssemblyIr(normalizeAssemblyIr(data.assembly_ir));
    setAssemblyDesigns(normalizeAssemblyDesigns(data.assembly_designs));
    setAssemblyPackageShapes(normalizeAssemblyPackageShapes(data.assembly_package_shapes));
    setModelIndex(normalizeModelIndex(data.models));
    setComponentBonds(Array.isArray(data.design?.component_bonds) ? data.design.component_bonds : []);
    setBondValidation([]);
    setPiTopology(data.design?.topologies?.pi ?? (parsed ? extractTopologyFromBoard(parsed, "pi") : emptyTopology("pi")));
    setSiTopology(data.design?.topologies?.si ?? (parsed ? extractTopologyFromBoard(parsed, "si") : emptyTopology("si")));
    const loadedSiSuite = analysis.si?.suite;
    setSelectedSiSuite(loadedSiSuite && validateSiProtocolSuite(loadedSiSuite).length === 0 ? loadedSiSuite as SiProtocolSuite : null);
    const loadedSiResult = analysis.si?.latest_channel_result;
    setSiChannelResult(["spike/si-channel-result/v1", "spike/si-workflow-result/v1"].includes(String(loadedSiResult?.contract)) ? loadedSiResult as Record<string, unknown> : null);
    setSolverSelections(analysis.solver_selections && typeof analysis.solver_selections === "object" && !Array.isArray(analysis.solver_selections)
      ? Object.fromEntries(Object.entries(analysis.solver_selections).filter((entry): entry is [string, string] => typeof entry[1] === "string"))
      : {});
    const workflowSettings = analysis.extension_workflows;
    setWorkspaceOpenEMSSetup(normalizeOpenEMSSetup(workflowSettings?.openems_setup));
    setEmergeEmiSetup(normalizeEMergeSetup(workflowSettings?.emerge_setup));
    setAcEffectsRequest(analysis.ac_power_integrity?.request?.contract === "spike/ac-pi-request/v1" ? analysis.ac_power_integrity.request : null);
    setAcEffectsResult(analysis.ac_power_integrity?.result?.contract === "spike/ac-pi-result/v1" && Array.isArray(analysis.ac_power_integrity.result.samples) ? analysis.ac_power_integrity.result : null);
    setSpiceWorkspace(normalizeSpiceWorkspace(data.spice?.workspace, parsed));
    setEmiSetup(normalizeEmiSetup(data.emi?.setup, parsed ? Object.values(parsed.nets) : []));
    setEmiPreflight(data.emi?.preflight ?? null);
    setEmiScreening(data.emi?.screening ?? null);
    setEmiFieldResult(normalizeEmiFieldResult(data.emi?.field_result));
    setThermalScenario(data.thermal?.scenario ?? null);
    setAnalysisMode(analysis.mode ?? "DC IR Drop"); setSolverId(analysis.solver_id ?? "auto"); setFormulation(analysis.formulation ?? "auto");
    setPowerNets(analysis.power_nets ?? ["+1V8_CORE", "GND"]); setPiSetup(normalizePiSetup(analysis.pi_setup)); setLimits(analysis.limits ?? { drop: "50", density: "100" }); setFrequency(analysis.frequency ?? "10 MHz");
    setVisibleLayers(parsed ? visibilityForBoard(parsed, analysis.visible_layers) : analysis.visible_layers ?? initialLayers); setAssemblyLayerVisibility(analysis.assembly_layer_visibility ?? {}); setAssemblyLayerOpacity(analysis.assembly_layer_opacity ?? {}); setAssemblyModelAssignments(analysis.assembly_model_assignments ?? {}); setAssemblyBoardVisibility(analysis.assembly_display?.visibility ?? {}); setAssemblyExplodedDistanceMm(Math.max(0, Number(analysis.assembly_display?.exploded_distance_mm) || 0)); setAssemblySnapMode("off"); setLayerOpacity(analysis.layer_opacity ?? {}); setLayerSeparation(Math.max(0, Number(analysis.layer_separation_mm) || 0));
    setShowVias(analysis.show_vias ?? true); setShowNetNames(analysis.show_net_names === true); setShowAxes(analysis.show_axes ?? true); setShowModels(analysis.show_models ?? true); setShowSmdModels(analysis.show_smd_models ?? true); setShowThtModels(analysis.show_tht_models ?? true); setNavigationInertia(analysis.navigation_inertia ?? false); setViewMode(analysis.view_mode === "2D" ? "2D" : "3D"); setSelectionFilter(["all", "part", "net"].includes(analysis.selection_filter) ? analysis.selection_filter : "all"); setIsolatedNet(analysis.isolated_net ?? null);
    const savedEmSettings = analysis.em_viewport_settings && typeof analysis.em_viewport_settings === "object" ? analysis.em_viewport_settings : {};
    setEmViewportSettings({ ...defaultEMViewportSettings, ...Object.fromEntries(Object.entries(defaultEMViewportSettings).filter(([key, value]) => typeof savedEmSettings[key] === typeof value).map(([key]) => [key, savedEmSettings[key]])) });
    const loadedResult = isSupportedSavedResult(analysis.latest_result) ? normalizeSolverResult(analysis.latest_result) : null;
    const loadedRecords: ResultRecord[] = (analysis.result_history ?? []).flatMap((record: any, index: number) => { const bundle = isSupportedSavedResult(record.bundle) ? normalizeSolverResult(record.bundle) : null; return bundle ? [{ id: String(record.id ?? index), label: String(record.label ?? `Result ${index + 1}`), bundle }] : []; });
    if (loadedResult && (loadedResult.em_fields || loadedResult.em_networks) && !loadedRecords.some(row => row.bundle.analysis_id === loadedResult.analysis_id)) loadedRecords.push(resultRecord(loadedResult, loadedRecords.length));
    setEmResultManagerOpen(Boolean(loadedResult?.em_fields || loadedResult?.em_networks || loadedRecords.some(row => row.bundle.em_fields)));
    if (loadedRecords.some(row => row.bundle.em_fields)) setEmiChamberOpen(false);
    const loadedPdnReview = analysis.pdn_review?.contract === "spike/pdn-review/v1" ? analysis.pdn_review as PdnReview : null;
    const boundedRecords = boundedResultRecords(loadedRecords);
    const persistedDisplay = String(analysis.result_display ?? "");
    const restoredDisplay = persistedDisplay === "none" || persistedDisplay === "all" || boundedRecords.some(record => record.id === persistedDisplay)
      ? persistedDisplay
      : boundedRecords[boundedRecords.length - 1]?.id ?? (loadedResult ? "all" : "none");
    setResultVisualization({ ...defaultResultVisualization(), ...(analysis.result_visualization ?? {}) }); setAnalysisResult(loadedResult); setPdnReview(loadedPdnReview); setPdnReviewSourceId(typeof analysis.pdn_review_source_id === "string" ? analysis.pdn_review_source_id : null); setResultRecords(boundedRecords); setResultDisplay(restoredDisplay); setProbes(data.probes ?? []);
    const loadedProbeTable = normalizeProbeTableState(data.probe_table);
    setProbeFormulaRows(loadedProbeTable.calculatedRows); setSavedProbeReferenceIds(loadedProbeTable.referenceIds); setSelected(data.selection ?? null); setAnalysisSummary(null);
    if (!restoreWorkspaceState(data.workspace)) setCameraCommand(`fit-project-${Date.now()}`);
    historyRef.current = []; redoRef.current = []; setProjectClean(); rememberProject(nextName, path); setStatus(`Project package loaded from ${fileName}${migrated ? " and migrated to v2" : ""}`);
  };
  const loadNativeProjectFromApprovedPath = async (path: string, fileName: string) => {
    setStatus("Opening project and verifying saved artifacts");
    const response = await runNativeProjectWorker({ method: "read_project_package", params: { path, defer_artifacts: true, compact_normalized_source: true } });
    if (!response.ok) throw new Error(response.error ?? "The project package worker rejected the file.");
    const result = response.result as any;
    const signature = result.manifest?.signature;
    if (result.manifest_signature?.present) {
      const signedPayload = result.manifest_signature?.signed_payload_base64url;
      if (!signature || typeof signedPayload !== "string" || !signedPayload) {
        throw new Error("SPIKE-BE-PACKAGE-S-0001: signed project is missing native verification data.");
      }
      const trust = await verifyNativeProjectManifestSignature(signedPayload, signature);
      if (!trust.verified) throw new Error("SPIKE-BE-PACKAGE-S-0003: project signature was not verified.");
    }
    const manifestDigest = result.migrated ? null : result.manifest?.manifest_payload_sha256;
    if (!result.migrated && (typeof manifestDigest !== "string" || !/^[0-9a-f]{64}$/.test(manifestDigest))) {
      throw new Error("SPIKE-BE-PACKAGE-S-0001: project manifest identity is missing or malformed.");
    }
    const canonicalDesignId = typeof result.canonical?.design_ir?.design_id === "string" ? result.canonical.design_ir.design_id : null;
    if (!result.migrated && !canonicalDesignId) throw new Error("SPIKE-BE-PACKAGE-S-0001: canonical design identity is missing.");
    const hydrated = await hydrateProjectArtifacts(result.project, async reference => {
      const response = await runNativeProjectWorker({ method: "read_project_state_artifact", params: {
        path, reference, expected_manifest_payload_sha256: manifestDigest,
      } });
      if (!response.ok) throw new Error(response.error ?? "Could not restore a saved simulation result.");
      return (response.result as any).value;
    }, (done, total) => { if (total) setStatus(`Restoring simulation results ${done}/${total}`); });
    await applyProjectPackage(JSON.stringify(hydrated), fileName, path, manifestDigest, canonicalDesignId, result.canonical.design_ir);
    if (result.migrated) {
      setProjectUpgradeOffer({ fileName, sourceFormat: String(result.source_format ?? "an older SPIKE format") });
      setStatus(`Older project loaded from ${fileName}; upgrade to .spike v3 is available`);
    }
  };
  useEffect(() => {
    if (!desktopShell || startupProjectConsumedRef.current) return;
    startupProjectConsumedRef.current = true;
    void takeStartupProject()
      .then(file => file ? loadNativeProjectFromApprovedPath(file.path, file.fileName) : undefined)
      .catch(error => {
        setStatus(error instanceof Error ? `Startup project open failed: ${error.message}` : "Startup project open failed");
      });
  }, [desktopShell]);
  const performOpenProject = async () => {
    if (!desktopShell) { projectInputRef.current?.click(); return; }
    try {
      const file = await selectNativeWorkbenchFile();
      if (file) {
        let kind = classifyOpenSource(file.fileName);
        if (kind === "unknown" && file.fileName.toLowerCase().endsWith(".json")) {
          const text = await readApprovedSourceFile(file.path);
          kind = classifyOpenSource(file.fileName, JSON.parse(text.contents));
        }
        if (kind === "unknown") throw new Error("Unrecognized source. Use Import project / CAD to choose its format explicitly.");
        if (kind === "project" || kind === "results") requestUnsavedAction("open another project", async () => {
          try {
            if (kind === "results") { const result = await readApprovedResultFile(file.path); await applyResultFile(result.contents, result.fileName); }
            else await loadNativeProjectFromApprovedPath(file.path, file.fileName);
          } catch (error) { setStatus(error instanceof Error ? `Project open failed: ${error.message}` : "Project open failed"); }
        });
        else setSourceImport({ source: file, kind });
      }
      else setStatus("Project open cancelled");
    } catch (error) { setStatus(error instanceof Error ? `Project open failed: ${error.message}` : "Project open failed"); }
  };
  const openProject = () => { void performOpenProject(); };
  const loadProject = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    event.target.value = "";
    requestUnsavedAction("open another project", async () => {
      try { const contents = await file.text(); if (file.name.toLowerCase().endsWith(".spike-results.json")) await applyResultFile(contents, file.name); else await applyProjectPackage(contents, file.name, null); }
      catch (error) { setStatus(error instanceof Error ? `Project load failed: ${error.message}` : "Project load failed: invalid SPIKE project package"); }
    });
  };
  const handleAssemblyPartViewportStatus = useCallback((next: Record<string, AssemblyPartViewportLoadState>) => {
    setAssemblyPartViewportStates(current => ({ ...current, ...next }));
  }, []);
  useEffect(() => {
    setAssemblyPartViewportStates(initialAssemblyPartViewportStates(assemblyIr, modelIndex));
  }, [assemblyIr, modelIndex]);
  useEffect(() => {
    const requestedIds = visualModelIds(assemblyIr, modelIndex);
    setAssemblyModelReadReady(false);
    if (!desktopShell || !projectPath || !projectManifestDigest || requestedIds.length === 0) {
      setAssemblySceneModels([]);
      setAssemblyModelReadReady(true);
      return;
    }
    let cancelled = false;
    let settled = false;
    const objectUrls: string[] = [];
    const requestId = globalThis.crypto?.randomUUID?.() ?? `mcad-models-${Date.now()}`;
    void (async () => {
      try {
        const response = await runNativeProjectWorker({
          id: requestId,
          method: "read_project_model_artifacts",
          params: {
            path: projectPath,
            model_ids: requestedIds,
            expected_manifest_payload_sha256: projectManifestDigest,
          },
        });
        if (!response.ok) throw new Error(response.error ?? "The package worker rejected the visual model request.");
        const result = response.result as any;
        if (result?.contract !== "spike/project-model-artifacts/v1" || !Array.isArray(result.artifacts)) {
          throw new Error("The package worker returned an invalid visual model response.");
        }
        const requested = new Set(requestedIds);
        const urls = new Map<string, string>();
        for (const artifact of result.artifacts) {
          const modelIds = Array.isArray(artifact?.model_ids) ? artifact.model_ids : [artifact?.model_id];
          const modelType = artifact?.model_type;
          if (!modelIds.length || modelIds.some((modelId: unknown) => typeof modelId !== "string" || !requested.has(modelId)) || (modelType !== "gltf" && modelType !== "glb") || typeof artifact?.artifact_base64 !== "string") {
            throw new Error("The package worker returned malformed visual model metadata.");
          }
          const mediaType = modelType === "glb" ? "model/gltf-binary" : "model/gltf+json";
          const url = URL.createObjectURL(new Blob([decodeBase64Buffer(artifact.artifact_base64)], { type: mediaType }));
          objectUrls.push(url);
          modelIds.forEach((modelId: string) => urls.set(modelId, url));
        }
        if (urls.size !== requested.size) throw new Error("The package worker omitted a requested visual model artifact.");
        if (cancelled) {
          objectUrls.forEach(url => URL.revokeObjectURL(url));
          return;
        }
        setAssemblySceneModels(createAssemblySceneModels(assemblyIr, modelIndex, urls));
      } catch (error) {
        objectUrls.forEach(url => URL.revokeObjectURL(url));
        if (!cancelled) {
          setAssemblySceneModels([]);
          const requested = new Set(requestedIds);
          setAssemblyPartViewportStates(current => Object.fromEntries(Object.entries(current).map(([partId, state]) => {
            const part = assemblyIr?.parts.find(item => item.id === partId);
            return [partId, state === "pending" && part && requested.has(part.model_id) ? "failed" : state];
          })) as Record<string, AssemblyPartViewportLoadState>);
          setStatus(error instanceof Error ? `MCAD viewport unavailable: ${error.message}` : "MCAD viewport unavailable");
        }
      } finally {
        settled = true;
        if (!cancelled) setAssemblyModelReadReady(true);
      }
    })();
    return () => {
      cancelled = true;
      if (!settled) void cancelLocalWorkerCleanup(requestId);
      objectUrls.forEach(url => URL.revokeObjectURL(url));
    };
  }, [assemblyIr, desktopShell, modelIndex, projectManifestDigest, projectPath]);
  useEffect(() => {
    const previewShapes = assemblyPackageShapes?.shapes.filter(shape => Boolean(shape.selector_preview)) ?? [];
    const requestedIds = previewShapes.map(shape => shape.shape_id);
    if (!desktopShell || !projectPath || !projectManifestDigest || !assemblyIr || requestedIds.length === 0) {
      setAssemblySelectorPreviews([]);
      return;
    }
    if (!assemblyModelReadReady) return;
    let cancelled = false;
    let settled = false;
    const objectUrls: string[] = [];
    const requestId = globalThis.crypto?.randomUUID?.() ?? `mcad-selector-previews-${Date.now()}`;
    void (async () => {
      try {
        const response = await runNativeProjectWorker({
          id: requestId,
          method: "read_project_package_shape_selector_previews",
          params: { path: projectPath, shape_ids: requestedIds, expected_manifest_payload_sha256: projectManifestDigest },
        });
        if (!response.ok) throw new Error(response.error ?? "The package worker rejected the selector-preview request.");
        const result = response.result as any;
        if (result?.contract !== "spike/project-package-shape-selector-previews/v1" || !Array.isArray(result.artifacts)) {
          throw new Error("The package worker returned an invalid selector-preview response.");
        }
        const expected = new Map(previewShapes.map(shape => [shape.shape_id, shape]));
        const urls = new Map<string, string>();
        for (const artifact of result.artifacts) {
          const shape = expected.get(artifact?.shape_id);
          const preview = shape?.selector_preview;
          if (!shape || !preview || urls.has(shape.shape_id)
            || artifact?.part_id !== shape.part_id
            || artifact?.artifact_sha256 !== preview.artifact_sha256
            || artifact?.source_sha256 !== preview.source_sha256
            || artifact?.topology_artifact_sha256 !== preview.topology_artifact_sha256
            || artifact?.selector_inventory_sha256 !== preview.selector_inventory_sha256
            || typeof artifact?.artifact_base64 !== "string") {
            throw new Error("The package worker returned malformed or mismatched selector-preview metadata.");
          }
          const url = URL.createObjectURL(new Blob([decodeBase64Buffer(artifact.artifact_base64)], { type: "model/gltf-binary" }));
          objectUrls.push(url);
          urls.set(shape.shape_id, url);
        }
        if (urls.size !== expected.size) throw new Error("The package worker omitted a requested selector preview.");
        if (cancelled) { objectUrls.forEach(url => URL.revokeObjectURL(url)); return; }
        setAssemblySelectorPreviews(createAssemblySelectorPreviewModels(assemblyIr, modelIndex, assemblyPackageShapes, urls));
      } catch (error) {
        objectUrls.forEach(url => URL.revokeObjectURL(url));
        if (!cancelled) {
          setAssemblySelectorPreviews([]);
          setStatus(error instanceof Error ? `Exact-selector viewport unavailable: ${error.message}` : "Exact-selector viewport unavailable");
        }
      } finally {
        settled = true;
      }
    })();
    return () => {
      cancelled = true;
      if (!settled) void cancelLocalWorkerCleanup(requestId);
      objectUrls.forEach(url => URL.revokeObjectURL(url));
    };
  }, [assemblyIr, assemblyModelReadReady, assemblyPackageShapes, desktopShell, modelIndex, projectManifestDigest, projectPath]);
  useEffect(() => {
    if (!deferredBoardVisual || !assemblyModelReadReady) return;
    const pending = deferredBoardVisual;
    setDeferredBoardVisual(null);
    void prepareVisualBundleForBoard(pending.board, pending.sourceFile, pending.source, undefined, modelAssignments);
  }, [assemblyModelReadReady, deferredBoardVisual, prepareVisualBundleForBoard, modelAssignments]);
  useEffect(() => {
    setIsolatedAssemblyPartId(null);
    setAssemblySection({ ...DEFAULT_ASSEMBLY_SECTION });
  }, [projectPath]);
  const resolveUnsavedPrompt = async (choice: "save" | "discard" | "cancel") => {
    const pending = unsavedPrompt;
    if (!pending) return;
    if (choice === "cancel") { pending.onCancel?.(); setUnsavedPrompt(null); setStatus(`${pending.actionLabel} cancelled; project remains open`); return; }
    if (choice === "save" && !await saveProject()) return;
    if (choice === "discard" && !pending.preserveDirtyUntilApplied) setProjectClean();
    setUnsavedPrompt(null);
    if (pending.closeWindow) {
      allowWindowCloseRef.current = true;
      try {
        await closeDesktopWindow();
      } catch (error) {
        allowWindowCloseRef.current = false;
        setStatus(`Could not close SPIKE: ${error instanceof Error ? error.message : String(error)}`);
      }
      return;
    }
    await pending.action?.();
  };
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if ((!projectDirtyRef.current && !assemblyToolDraftOwnerRef.current) || allowWindowCloseRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    let disposed = false;
    let unlisten: (() => void) | undefined;
    if (desktopShell) void subscribeDesktopCloseRequested(preventDefault => {
      if (disposed) return;
      if (assemblyToolDraftOwnerRef.current) { preventDefault(); setStatus(`Save or discard the assembly ${assemblyToolDraftOwnerRef.current} tool draft before closing SPIKE.`); return; }
      if (!projectDirtyRef.current || allowWindowCloseRef.current) return;
      preventDefault();
      setUnsavedPrompt({ actionLabel: "close SPIKE", action: null, closeWindow: true });
    }).then(closeListener => {
      if (disposed) closeListener();
      else unlisten = closeListener;
    });
    return () => { disposed = true; unlisten?.(); window.removeEventListener("beforeunload", onBeforeUnload); };
  }, [desktopShell]);
  const loadComparisonBaseline = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    file.text().then(text => {
      try {
        if (!analysisResult) throw new Error("Run or load a candidate analysis before comparing revisions.");
        const data = JSON.parse(text) as Record<string, any>;
        const baseline = normalizeSolverResult(data.analysis?.latest_result ?? data.result ?? data);
        if (!baseline) throw new Error("The selected file does not contain a SPIKE AnalysisResult.");
        if (baseline.mode !== analysisResult.mode) throw new Error(`Cannot compare ${baseline.mode} against ${analysisResult.mode}.`);
        const tolerancePercent = 1;
        const definitions = [
          ["max_voltage_drop_v", "Maximum voltage drop", "V"],
          ["max_current_density_a_mm2", "Maximum current density", "A/mm2"],
          ["total_copper_loss_w", "Total copper loss", "W"],
          ["effective_path_resistance_ohm", "Effective path resistance", "ohm"],
          ["resistance_start_ohm", "AC resistance at start", "ohm"],
          ["resistance_stop_ohm", "AC resistance at stop", "ohm"],
          ["partial_inductance_h", "Partial inductance", "H"],
        ] as const;
        const metricValue = (result: SolverResultBundle, key: string) => {
          const direct = Number(result.summary[key]);
          if (Number.isFinite(direct)) return direct;
          if (key === "effective_path_resistance_ohm") {
            const loss = Number(result.summary.total_copper_loss_w);
            const current = Number(result.summary.total_load_current_a);
            if (Number.isFinite(loss) && Number.isFinite(current) && current > 0) return loss / (current * current);
          }
          return null;
        };
        const metrics = definitions.flatMap(([key, label, unit]) => {
          const before = metricValue(baseline, key);
          const after = metricValue(analysisResult, key);
          if (before === null || after === null) return [];
          const changePercent = before === 0 ? (after === 0 ? 0 : Number.POSITIVE_INFINITY) : (after - before) / Math.abs(before) * 100;
          return [{ key, label, unit, baseline: before, candidate: after, changePercent, status: changePercent > tolerancePercent ? "regression" as const : changePercent < -tolerancePercent ? "improved" as const : "pass" as const }];
        });
        if (!metrics.length) throw new Error("The two results do not share comparable PI metrics.");
        const comparison: RevisionComparison = {
          baselineName: data.project?.name ?? file.name,
          candidateName: projectName,
          status: metrics.some(metric => metric.status === "regression") ? "regression" : "pass",
          tolerancePercent,
          metrics,
        };
        setRevisionComparison(comparison);
        setStatus(`Revision comparison ${comparison.status}: ${metrics.length} shared PI metrics evaluated`);
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Revision comparison failed.");
      }
    });
    event.target.value = "";
  };
  const copySelection = async () => { const payload = JSON.stringify(selected ?? projectData(), null, 2); try { await navigator.clipboard.writeText(payload); setStatus("Selection context copied to clipboard"); } catch { setStatus("Clipboard access is unavailable"); } };
  const pasteSelection = async () => { try { const data = JSON.parse(await navigator.clipboard.readText()) as BoardObject; if (data?.id && data?.type) { recordChange(); setSelected(data); setStatus("Selection context pasted"); } else setStatus("Clipboard does not contain a SPIKE selection"); } catch { setStatus("Clipboard does not contain valid SPIKE JSON"); } };
  const generateReport = async () => {
    const result = activeAnalysisResult;
    const reportDomain = tab === "Thermal" ? "thermal" : tab === "HF / SI" ? "si" : tab === "EM" ? "emi"
      : tab === "Reports" || tab === "Results" ? resultVisualizerDomain : "pi";
    const reportName = `${projectName.replace(/\.spike$/i, "").replace(/[^a-z0-9._-]+/gi, "-")}-engineering-report.html`;
    setStatus("Preparing the offline engineering report...");
    const { buildEngineeringReport } = await import("./engineeringReport");
    const reportHtml = buildEngineeringReport({
      projectName,
      boardFile,
      analysisMode,
      domain: reportDomain,
      board: boardData,
      result,
      results: resultRecords,
      setup: piSetup,
      limits,
      probes,
      fusingSettings: {
        ambientTemperatureC: resultVisualization.fusingAmbientC,
        faultDurationS: resultVisualization.fusingDurationS,
      },
      modelAssignmentCount: Object.keys(modelAssignments).length,
      pdnReview: reportDomain === "pi" && result && resultSolvedForPresentation(result)
        && pdnReviewSourceId === result.analysis_id ? pdnReview : null,
      emi: { setup: emiSetup, preflight: emiPreflight, screening: emiScreening, fieldResult: emiFieldResult },
      emerge: (extensionResult?.data as Record<string, unknown> | undefined)?.analysis_result
        && ((extensionResult?.data as Record<string, unknown>).analysis_result as Record<string, unknown>).analysis_id === result?.analysis_id
        ? extensionResult : null,
      si: { channelResult: siChannelResult, suite: selectedSiSuite },
      thermal: { scenario: thermalScenario },
      projectPayload: projectData(),
    });
    setReportPreview({ fileName: reportName, html: reportHtml });
    setStatus(result || resultRecords.length ? "Engineering report preview ready with results, probes, and run details" : "Report preview ready without a completed analysis result");
  };
  const exportPreparedReport = async () => {
    if (!reportPreview) return;
    try {
      if (desktopShell) {
        const path = await saveNativeTextFile(reportPreview.fileName, reportPreview.html, "report");
        setStatus(path ? `Engineering report exported: ${path}` : "Report export cancelled");
      } else {
        download(reportPreview.fileName, reportPreview.html, "text/html");
        setStatus(`Engineering report downloaded: ${reportPreview.fileName}`);
      }
    } catch (error) { setStatus(error instanceof Error ? `Report export failed: ${error.message}` : "Report export failed"); }
  };
  useEffect(() => {
    if (!reportPreview) return;
    void openReportPreviewWindow(reportPreview, async action => {
      if (action.type === "export") await exportPreparedReport();
      else if (action.type === "close") {
        await closeReportPreviewWindow();
        setReportPreview(null);
      } else if (action.type === "closed") setReportPreview(null);
    }).catch(error => {
      setReportPreview(null);
      setStatus(error instanceof Error ? error.message : "Could not open the report preview window");
    });
  }, [reportPreview]);
  useEffect(() => () => { void closeReportPreviewWindow(); }, []);
  const exportStep = async () => {
    if (!boardSource) { setStatus("STEP export requires an imported KiCad board"); return; }
    if (!workerAvailable) { setStatus("STEP export requires the SPIKE desktop worker and an installed KiCad CLI"); return; }
    setAnalysisRunning(true); setOperationDisplay({ label: "Exporting STEP", elapsedSeconds: 0, estimateSeconds: 60 });
    try {
      const response = await runLocalWorker({ method: "export_step", params: { source_board: boardSource, source_file: boardFile, options: { timeout_seconds: 600, board_only: false } } });
      if (!response.ok) throw new Error(response.error ?? "KiCad STEP export failed");
      const content = String(response.result?.content ?? "");
      const name = String(response.result?.file_name ?? `${boardFile.replace(/\.kicad_pcb$/i, "")}.step`);
      if (!content) throw new Error("KiCad returned an empty STEP model");
      const path = await saveNativeTextFile(name, content, "step");
      setStatus(path ? `STEP model exported: ${path}` : "STEP export save cancelled");
    } catch (error) { setStatus(error instanceof Error ? `STEP export failed: ${error.message}` : "STEP export failed"); }
    finally { setAnalysisRunning(false); setOperationDisplay(null); }
  };
  const exportProbeCsv = () => {
    const rows = buildProbeRows(probes, activeAnalysisResult, probeReferenceIds);
    const references = Object.fromEntries(rows.map(row => [row.id, row.values]));
    const csv = probeResultsCsv(rows, evaluateProbeFormulas(probeFormulaRows, references));
    download(`${projectName.replace(/\.spike$/i, "")}-probes.csv`, csv, "text/csv");
    setStatus(`Probe table exported with ${probes.length} probes and ${probeFormulaRows.length} calculated rows`);
  };

  const exportResultAnimation = async () => {
    const frameCount = analysisResult?.time_series.frames.length ?? 0;
    if (!analysisResult || frameCount < 2) {
      setStatus("GIF export requires a solver result with at least two time frames");
      return;
    }
    const originalFrame = resultVisualization.animationFrame;
    const originalPlaying = resultVisualization.animationPlaying;
    const stride = Math.max(1, Math.ceil(frameCount / 180));
    const captured: ImageData[] = [];
    setStatus(`Capturing ${Math.ceil(frameCount / stride)} viewport frames offline...`);
    try {
      for (let frame = 0; frame < frameCount; frame += stride) {
        setResultVisualization(current => ({ ...current, visible: true, animationPlaying: false, animationFrame: frame }));
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        captured.push(await captureViewport());
      }
      const delay = Math.max(2, Math.round(100 * stride / Math.max(1, resultVisualization.animationFps)));
      downloadBlob(`${projectName.replace(/\.spike$/, "")}-${viewMode.toLowerCase()}-results.gif`, encodeGif(captured, delay));
      setStatus(`Animated ${viewMode} result exported as an offline GIF with ${captured.length} frames`);
    } catch (error) {
      setStatus(`GIF export failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setResultVisualization(current => ({ ...current, animationFrame: originalFrame, animationPlaying: originalPlaying }));
    }
  };

  const selectNetForAnalysis = useCallback((net: string, source: "viewport" | "analysis" = "analysis") => {
    if (!net) return;
    setPiSetup(current => ({ ...current, net }));
    if (source === "analysis" && boardData) {
      const track = boardData.tracks.find(item => item.net === net);
      const via = boardData.vias.find(item => item.net === net);
      const pad = boardData.pads.find(item => item.net === net);
      const zone = boardData.zones.find(item => item.net === net);
      const object: BoardObject | null = track
        ? { id: track.id, type: "trace", name: net, net, layer: track.layer }
        : via ? { id: via.id, type: "via", name: net, net, layer: "through" }
          : pad ? { id: pad.id, type: "pad", name: `${pad.ref ?? ""}.${pad.name}`.replace(/^\./, ""), ref: pad.ref, net, layer: pad.layer }
            : zone ? { id: zone.id, type: "zone", name: net, net, layer: zone.layer }
              : null;
      if (object) {
        setSelected(object);
      }
    }
    setRightOpen(true);
    setStatus(`${net} selected for ${analysisMode}`);
  }, [boardData, analysisMode]);

  const focusManagedNet = useCallback((net: string) => {
    if (!boardData || !net) return;
    const track = boardData.tracks.find(item => item.net === net);
    const via = boardData.vias.find(item => item.net === net);
    const pad = boardData.pads.find(item => item.net === net);
    const zone = boardData.zones.find(item => item.net === net);
    const object: BoardObject | null = track
      ? { id: track.id, type: "trace", name: net, net, layer: track.layer }
      : via ? { id: via.id, type: "via", name: net, net, layer: "through" }
        : pad ? { id: pad.id, type: "pad", name: `${pad.ref ?? ""}.${pad.name}`.replace(/^\./, ""), ref: pad.ref, net, layer: pad.layer }
          : zone ? { id: zone.id, type: "zone", name: net, net, layer: zone.layer }
            : null;
    if (object) setSelected(object);
    setStatus(`${net} focused from PI Net Manager`);
  }, [boardData]);

  const handleSelect = useCallback((object: BoardObject) => {
    recordChange();
    setSelectedHarnessId(null);
    setSelectedBoardInstanceId(null);
    setSelected(object);
    setAssemblyHighlightSeed(null);
    if (probeMode === "temporary") {
      setProbes([{ ...object, id: `temporary-${object.id}`, name: `Temporary | ${object.name}`, probeKind }]);
      setDock("Probe table");
    }
    if (probeMode === "bulk") setProbes(current => current.some(probe => probe.id === object.id) ? current : [...current, object]);
    if (object.net) selectNetForAnalysis(object.net, "viewport");
    setStatus(`${object.type} ${object.name} selected`);
    window.dispatchEvent(new CustomEvent("spike-selection", { detail: { source: "desktop", object } }));
  }, [boardFile, frequency, visibleLayers, selected, showModels, viewMode, selectNetForAnalysis, probeMode, probeKind]);
  const handleHarnessSelect = useCallback((harness: VirtualHarnessVisual) => {
    setSelected(null);
    setSelectedBoardInstanceId(null);
    setSelectedHarnessId(harness.id);
    setRightOpen(true);
    setStatus(`Virtual harness ${harness.name} selected: ${harness.endpointA.boardId}::${harness.endpointA.connectorId} to ${harness.endpointB.boardId}::${harness.endpointB.connectorId}`);
  }, []);
  const handleBoardInstanceSelect = useCallback((board: VirtualBoardVisual) => {
    setSelected(null);
    setSelectedHarnessId(null);
    setAssemblyHighlightSeed(null);
    setSelectedBoardInstanceId(board.id);
    setRightOpen(true);
    setStatus(`Assembly board ${board.name} selected: ${board.designId} · ${metadataNumber(board.widthMm)} × ${metadataNumber(board.heightMm)} mm`);
  }, []);
  const handleAssemblyNetSelect = (boardId: string, netId: string) => {
    setSelected(null); setSelectedHarnessId(null); setSelectedBoardInstanceId(boardId);
    setAssemblyHighlightSeed({ kind: "net", boardId, netId });
    const netName = assemblyIr && assemblyDesigns ? netOccurrences(assemblyIr, assemblyDesigns).find(net => net.boardId === boardId && net.netId === netId)?.name : undefined;
    const boardName = assemblyIr?.boards.find(board => board.id === boardId)?.name;
    setStatus(`Selected net ${netName ?? "Unnamed net"}${boardName ? ` on ${boardName}` : ""}; explicit inter-board links are highlighted`);
  };
  const handleAssemblyComponentSelect = (boardId: string, componentId: string) => {
    setSelectedBoardInstanceId(boardId);
    setAssemblyHighlightSeed({ kind: "component", boardId, componentId });
    if (!passThroughHighlight) setStatus("Component selected; enable Pass through component to highlight its outgoing non-ground branches");
  };
  const commitAssemblyBoardPlacement = (boardId: string, world: number[]) => {
    if (!assemblyIr) return;
    if (assemblyToolDraftOwner) { setStatus(`Finish or discard the assembly ${assemblyToolDraftOwner} draft before moving a board.`); return; }
    try {
      const next = placeAssemblyBoard(assemblyIr, boardId, world);
      recordChange(); setAssemblyIr(next);
      setStatus("Board placement updated; saved routes and analysis results require geometry review");
    } catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
  };
  useEffect(() => {
    const partId = `board:${selectedBoardInstanceId ?? ""}`;
    window.dispatchEvent(new CustomEvent("spike-mcad-gizmo-config", { detail: { partId, enabled: Boolean(selectedBoardInstanceId && assemblyMoveMode && assemblyBoardVisibility[selectedBoardInstanceId] !== false), mode: assemblyMoveMode ?? "translate", translationSnapMm: 0, rotationSnapDeg: 0 } }));
    return () => { window.dispatchEvent(new CustomEvent("spike-mcad-gizmo-config", { detail: { partId, enabled: false } })); };
  }, [selectedBoardInstanceId, assemblyMoveMode, assemblyBoardVisibility]);
  useEffect(() => {
    const commit = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (selectedBoardInstanceId && detail?.partId === `board:${selectedBoardInstanceId}` && Array.isArray(detail.assemblyTransform)) commitAssemblyBoardPlacement(selectedBoardInstanceId, detail.assemblyTransform);
    };
    window.addEventListener("spike-mcad-transform-commit", commit);
    return () => window.removeEventListener("spike-mcad-transform-commit", commit);
  }, [assemblyIr, selectedBoardInstanceId]);
  const handleAssemblySnapTarget = (target: AssemblySnapTarget) => {
    if (!assemblySnapSource) {
      const visual = virtualBoardProjection.visuals.find(board => board.id === target.occurrenceId);
      if (visual) handleBoardInstanceSelect(visual);
      setAssemblySnapSource(target); setStatus(`Moving ${target.occurrenceId}: ${target.sourceId}. Click a ${target.kind} on the target board.`); return;
    }
    try {
      const moving = virtualBoardProjection.visuals.find(board => board.id === assemblySnapSource.occurrenceId);
      if (!moving) throw new Error("Moving board is no longer available");
      const transform = snapOccurrenceTransform(moving.transform, assemblySnapSource, target, { gapMm: assemblySnapGapMm, edgeAngle: "align", edgeDirection: "antiparallel" });
      commitAssemblyBoardPlacement(moving.id, transform); setAssemblySnapSource(null); setAssemblySnapMode("off");
    } catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
  };
  const loadAssemblyOverlayStudy = async () => {
    if (!assemblyIr) return;
    const sourceAssembly = assemblyIr;
    try {
      const file = await openNativeTextFile("result"); if (!file) return;
      if (file.contents.length > 8 * 1024 * 1024) throw new Error("Study file exceeds 8 MiB");
      const value = JSON.parse(file.contents);
      if (value.contract !== "spike/multiboard-study-file/v1" || !["pi", "si", "thermal", "emi"].includes(value.domain) || !value.result) throw new Error("Choose a coupled study file containing its setup and results.");
      const checked = await runLocalWorker({ method: "validate_multiboard_study_result", params: { assembly: sourceAssembly, domain: value.domain, request: value.request, result: value.result } });
      if (!checked.ok) throw new Error(checked.error ?? "Result binding failed");
      if (!normalizeAssemblyResultOverlays([value.result]).length) throw new Error("This result has no supported board overlay values");
      recordChange(); setAssemblyIr(current => {
        if (current !== sourceAssembly) return current;
        const extensions = current.extensions as Record<string, any> | undefined;
        return { ...current, extensions: { ...extensions, "spike.multiboard-studies": { ...extensions?.["spike.multiboard-studies"], [value.domain]: value } } };
      });
      setStatus("Coupled result overlay loaded with physical assembly binding and original model status");
    } catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
  };
  const exportAssemblyDiagram = async () => {
    try {
      const frame = await captureViewport(1600, 1000);
      const canvas = document.createElement("canvas"); canvas.width = frame.width; canvas.height = frame.height + 40;
      const context = canvas.getContext("2d"); if (!context) throw new Error("Diagram capture unavailable");
      context.putImageData(frame, 0, 0); context.fillStyle = "#101e27"; context.fillRect(0, frame.height, frame.width, 40);
      context.fillStyle = "#d9ebef"; context.font = "16px system-ui";
      context.fillText(`${projectName} | Exploded spacing ${assemblyExplodedDistanceMm} mm | Presentation view; physical geometry unchanged`, 12, frame.height + 26);
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("Diagram image export failed");
      const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "spike-assembly-diagram.png"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000); setStatus("Assembly diagram exported with visible result overlays");
    } catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
  };
  const changeSelectionFilter = (filter: SelectionFilter) => {
    setSelectionFilter(filter);
    if (selected && (filter === "part" && selected.type !== "component" || filter === "net" && (!selected.net || selected.type === "component"))) setSelected(null);
    setStatus(`${filter === "all" ? "All objects" : filter === "part" ? "Components" : "Electrical nets"} selection filter active`);
  };
  useEffect(() => {
    if (!viewportContext) return;
    const close = (event: PointerEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest(".viewport-context-menu")) setViewportContext(null);
    };
    const closeOnKey = (event: KeyboardEvent) => { if (event.key === "Escape") setViewportContext(null); };
    const closeMenu = () => setViewportContext(null);
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", closeOnKey);
    window.addEventListener("resize", closeMenu);
    window.addEventListener("blur", closeMenu);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", closeOnKey);
      window.removeEventListener("resize", closeMenu);
      window.removeEventListener("blur", closeMenu);
    };
  }, [viewportContext]);
  const handleCamera = useCallback((camera: Viewport3DCameraState) => { camera3DRef.current = camera; }, []);
  const handleLayoutView = useCallback((view: Viewport2DState) => { layout2DRef.current = view; }, []);
  const handleTelemetry = useCallback((telemetry: RenderTelemetry) => setRenderTelemetry(telemetry), []);
  const handleViewportTopologySelect = useCallback((reference: TopologyReference) => {
    setSelectedTopologyReference(reference);
    setMcadFocusedPartId(reference.part_id);
    setStatus(`Selected exact ${reference.topology_kind} ${reference.topology_id}. This is a BREP-owned selector visual aid, not a visual-model triangle or solver geometry.`);
  }, []);
  const handleViewportOrbitCenter = useCallback((position: [number, number, number]) => {
    setStatus(`Orbit center set to ${position.map(value => value.toFixed(2)).join(", ")}`);
  }, []);
  const viewportThermalScenario = useMemo(
    () => tab === "Thermal" ? asThermalScenario(thermalPreview ?? thermalScenario) : null,
    [tab, thermalPreview, thermalScenario],
  );
  const commandCamera = (command: string) => setCameraCommand(`${command}-${Date.now()}`);
  const handleSceneNavigatorAction = (action: SceneNavigatorAction) => {
    switch (action) {
      case "board":
        commandCamera("fit");
        setStatus(`${boardFile} fitted in the active viewport`);
        break;
      case "assembly":
        openAssemblyWorkspace();
        setStatus("Assembly board-instance and harness editor opened; coupled analysis remains capability-gated.");
        break;
      case "stackup":
        setStackupOpen(true);
        break;
      case "flex":
        setFlexBoardOpen(true);
        break;
      case "layers":
        openBoardManager("layers");
        break;
      case "nets":
        openBoardManager("nets");
        break;
      case "components":
        setSearchQuery("component");
        setStatus("Showing all components in the scene navigator; select a row to inspect it.");
        break;
      case "models":
        setModelLibraryOpen(true);
        break;
      case "mcad":
        setMcadAttachmentOpen(true);
        break;
      case "bonds":
        setBondManagerOpen(true);
        break;
      case "thermal":
        setTab("Thermal");
        setThermalOpen(true);
        break;
      case "probes":
        setTab("Probes");
        setBottomOpen(true);
        setDock("Probe table");
        break;
      case "power-paths":
        setTab("PI");
        setBottomOpen(true);
        setDock("Power tree");
        setTopologyEditor("pi");
        break;
      case "results":
        setTab("Results");
        setResultVisualizerOpen(true);
        break;
    }
  };
  const toggleRibbonVisibility = () => {
    setAppSettings(current => {
      const next = { ...current, ribbonVisible: !current.ribbonVisible };
      saveAppSettings(next);
      setStatus(next.ribbonVisible ? "Command ribbon shown" : "Command ribbon minimized; workspace tabs remain visible");
      return next;
    });
    setMenu(null);
  };
  const assignShortcut = (action: ShortcutAction, key: string) => {
    setShortcuts(current => {
      const next = { ...current };
      const conflict = (Object.keys(current) as ShortcutAction[]).find(item => item !== action && current[item] === key);
      if (conflict) next[conflict] = current[action];
      next[action] = key;
      return next;
    });
  };
  const loadDemoBoard = async () => {
    const generation = projectGeneration.current;
    try {
      const source = await fetch("/demo/ebrake1.kicad_pcb").then(response => response.text());
      const parsed = await parseDesignSourceOffThread("ebrake1.kicad_pcb", source);
      if (projectGeneration.current !== generation) return;
      resetPreparedVisualBundle();
      retainedProjectSnapshot.current = null;
      setDeferredBoardVisual(null);
      configureBundledVisuals(parsed);
      const firstNet = preferredPowerNet(parsed);
      setBoardFile("ebrake1.kicad_pcb");
      setProjectName("ebrake1.spike");
      setBoardSource(source);
      setBoardData(parsed);
      setActiveDesignId(null);
      setCanonicalSpiDeR(null);
      setPiTopology(extractTopologyFromBoard(parsed, "pi"));
      setSiTopology(extractTopologyFromBoard(parsed, "si"));
      setSpiceWorkspace(defaultSpiceWorkspace("pi", parsed));
      setVisibleLayers(visibilityForBoard(parsed));
      setLayerOpacity({});
      setLayerSeparation(0);
      setShowVias(true);
      setSelected(null);
      setIsolatedNet(null);
      setAnalysisSummary(null);
      setAnalysisResult(null);
      setPdnReview(null); setPdnReviewSourceId(null);
      setResultRecords([]);
      setResultDisplay("none");
      setEmiSetup(defaultEmiSetup(Object.values(parsed.nets)));
      setEmiPreflight(null);
      setEmiScreening(null);
      setEmiFieldResult(null);
      setPiSetup(current => ({ ...current, net: parsed.nets ? firstNet : current.net }));
      setPowerNets([firstNet, "GND"].filter(Boolean));
      setStatus(`E-brake demo loaded: ${parsed.tracks.length} tracks, ${parsed.vias.length} vias, ${parsed.components.length} components`);
    } catch {
      setStatus("Unable to load the bundled demo board.");
    }
  };
  useEffect(() => {
    const onAnalysisNet = (event: Event) => {
      const net = (event as CustomEvent<{ net?: string }>).detail?.net;
      if (net) selectNetForAnalysis(net, "analysis");
    };
    window.addEventListener("spike-analysis-net-selected", onAnalysisNet);
    return () => window.removeEventListener("spike-analysis-net-selected", onAnalysisNet);
  }, [selectNetForAnalysis]);
  useEffect(() => {
    const onResult = (event: Event) => {
      const result = normalizeSolverResult((event as CustomEvent<unknown>).detail);
      if (!result) return;
      const record = resultRecord(result, resultRecords.length);
      setAnalysisResult(result);
      setPdnReview(null); setPdnReviewSourceId(null);
      setResultRecords(current => boundedResultRecords([...current.filter(item => item.id !== record.id), record]));
      setResultDisplay(record.id);
      setResultVisualization(current => ({
        ...current,
        visible: true,
        animationPlaying: false,
        animationFrame: 0,
        animationFps: Number.isFinite(Number(result.summary.playback_fps))
          ? Math.max(1, Math.min(30, Number(result.summary.playback_fps)))
          : current.animationFps,
        mode: result.scalar_fields.voltage_drop_v.length ? "voltage_drop" : result.mesh.length ? "mesh" : current.mode,
      }));
      setResultVisualizerDomain(result.mode === "si" ? "si" : "pi");
      setResultVisualizerOpen(result.status !== "preview");
      if (result.em_fields || result.em_networks) {
        setResultVisualizerOpen(false); setEmResultManagerOpen(true); setEmiChamberOpen(false); setEmiDashboardOpen(false); setViewMode("3D");
        setTab(result.mode === "si" ? "HF / SI" : "EM");
        const quantities = availableEMQuantities({ id: record.id, label: record.label, result: emViewportPayload(result) });
        setEmViewportSettings(current => ({ ...current, visible: true, frequencyIndex: 0, selectedSample: 0, quantity: quantities[0]?.id ?? "far_e" }));
      }
      if (result.status !== "preview") {
        // A published solver result is terminal for the UI run lifecycle. The
        // dialog clock also stops itself, but clearing here prevents a queued
        // timer tick from leaving the workspace in a stale Running state.
        setAnalysisRunning(false);
        setOperationDisplay(null);
      }
    };
    const onBatchResults = (event: Event) => {
      const bundles = ((event as CustomEvent<unknown[]>).detail ?? []).map(normalizeSolverResult).filter((item): item is SolverResultBundle => Boolean(item));
      if (!bundles.length) return;
      const records = bundles.map((bundle, index) => resultRecord(bundle, index));
      setResultRecords(current => {
        const ids = new Set(records.map(record => record.id));
        return boundedResultRecords([...current.filter(record => !ids.has(record.id)), ...records]);
      });
      setResultDisplay("all");
      setAnalysisRunning(false);
      setOperationDisplay(null);
    };
    window.addEventListener("spike-analysis-result", onResult);
    window.addEventListener("spike-analysis-batch-complete", onBatchResults);
    return () => {
      window.removeEventListener("spike-analysis-result", onResult);
      window.removeEventListener("spike-analysis-batch-complete", onBatchResults);
    };
  }, [resultRecords.length]);
  useEffect(() => {
    const openSearch = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setMenu(null);
        setGlobalSearchOpen(true);
      }
    };
    window.addEventListener("keydown", openSearch);
    return () => window.removeEventListener("keydown", openSearch);
  }, []);
  useEffect(() => { if (boardData) window.dispatchEvent(new CustomEvent("spike-board-imported", { detail: boardData })); }, [boardData]);
  useEffect(() => {
    if (!desktopShell) {
      setWorkerHealth("browser");
      return;
    }
    let cancelled = false;
    void (async () => {
      const health = await runLocalWorker({ method: "health", params: {} });
      if (cancelled) return;
      if (!health.ok || health.result?.status !== "ready") {
        setWorkerHealth("degraded");
        setStatus(health.error ? `Desktop worker unavailable: ${health.error}` : "Desktop worker health check failed");
        return;
      }
      setWorkerHealth("ready");
      const response = await runLocalWorker({ method: "list_solvers", params: {} });
      if (cancelled) return;
      const solvers = response.result?.solvers;
      if (response.ok && Array.isArray(solvers)) setSolverCatalog(mergeSolverCatalog(solvers as SolverCatalogEntry[]));
      else setStatus(response.error ? `Solver catalog unavailable: ${response.error}` : "Solver catalog unavailable");
    })();
    return () => { cancelled = true; };
  }, [desktopShell, setStatus]);
  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    const sample = async () => {
      try {
        const result = await sampleProcessResources();
        if (!cancelled) setProcessResources(result);
      } catch {
        if (!cancelled) setProcessResources(emptyProcessResources(desktopShell ? "desktop" : "browser"));
      } finally {
        if (!cancelled) timer = window.setTimeout(sample, 1500);
      }
    };
    void sample();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);
  useEffect(() => {
    const left = document.querySelector(".side-panel.left");
    const right = document.querySelector(".side-panel.right");
    const bottom = document.querySelector(".bottom-dock");
    const closeLeft = () => { if (!sidePanelsPinned) setLeftOpen(false); };
    const closeRight = () => { if (!sidePanelsPinned) setRightOpen(false); };
    const closeBottom = () => { if (!bottomPinned) setBottomOpen(false); };
    left?.addEventListener("mouseleave", closeLeft);
    right?.addEventListener("mouseleave", closeRight);
    bottom?.addEventListener("mouseleave", closeBottom);
    return () => {
      left?.removeEventListener("mouseleave", closeLeft);
      right?.removeEventListener("mouseleave", closeRight);
      bottom?.removeEventListener("mouseleave", closeBottom);
    };
  }, [sidePanelsPinned, bottomPinned, leftOpen, rightOpen, bottomOpen]);
  useEffect(() => {
    // Fast Refresh reruns mount effects; never replace an open project with
    // startup demo geometry while keeping its assembly metadata.
    if (boardData || projectPath) return;
    const demo = new URLSearchParams(window.location.search).get("demo");
    if (demo === "ebrake1") {
      void loadDemoBoard();
      return;
    }
    const developmentBuild = (import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV;
    if (developmentBuild && "__TAURI_INTERNALS__" in window) void loadDemoBoard();
  }, []);
  useEffect(() => {
    const adaptWorkspace = () => {
      const tier = window.innerWidth < 920 ? "compact" : window.innerWidth < 1180 ? "medium" : "wide";
      if (responsiveTierRef.current === tier) return;
      responsiveTierRef.current = tier;
      if (tier === "wide") {
        setLeftOpen(true);
        setRightOpen(true);
      } else if (tier === "medium") {
        setLeftOpen(false);
        setRightOpen(true);
      } else {
        setLeftOpen(false);
        setRightOpen(false);
      }
    };
    adaptWorkspace();
    window.addEventListener("resize", adaptWorkspace);
    return () => window.removeEventListener("resize", adaptWorkspace);
  }, []);
  const importQuality = useMemo(() => {
    if (!boardData) return 0;
    return (boardData.outlineLoops.length ? 25 : 0)
      + (boardData.layers.length ? 15 : 0)
      + (Object.keys(boardData.nets).length ? 20 : 0)
      + (boardData.components.length ? 20 : 0)
      + (boardData.pads.length ? 20 : 0);
  }, [boardData]);
  const componentMountCounts = useMemo(() => {
    if (!boardData) return { smd: 0, tht: 0 };
    const throughHole = throughHoleComponentRefs(boardData.pads);
    let tht = 0;
    for (const component of boardData.components) if (throughHole.has(component.ref)) tht += 1;
    return { smd: boardData.components.length - tht, tht };
  }, [boardData]);
  const layerEntries = useMemo(() => Object.keys(visibleLayers) as LayerName[], [visibleLayers]);
  const terminalMarkers = useMemo<AnalysisTerminalMarker[]>(() => {
    const marker = (item: PiTerminal, role: AnalysisTerminalMarker["role"], net: string): AnalysisTerminalMarker | null => {
      const x = Number(item.x);
      const y = Number(item.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      return {
        id: item.id,
        name: item.name,
        role,
        position: [x, y],
        net: item.net || net,
        layer: item.layer,
        layers: item.layers ?? [],
        value: item.value,
        anchorType: item.anchorType,
      };
    };
    const positive = [
      ...piSetup.sources.map(item => marker(item, "source", piSetup.net)),
      ...piSetup.loads.map(item => marker(item, "load", piSetup.net)),
    ];
    const returns = piSetup.returnPath.mode === "implicit" ? [] : [
      ...piSetup.returnPath.sources.map(item => marker(item, "source_return", piSetup.returnPath.net)),
      ...piSetup.returnPath.loads.map(item => marker(item, "load_return", piSetup.returnPath.net)),
    ];
    return [...positive, ...returns].filter((item): item is AnalysisTerminalMarker => Boolean(item));
  }, [piSetup]);
  const activeResultVisualization = useMemo<ResultVisualization>(() => {
    const base = resultVisualization.visible
      ? resultVisualization
      : { ...resultVisualization, mode: "geometry" as const, analysisOnly: false };
    return tab === "EM"
      ? {
        ...base,
        visible: true,
        mode: "geometry",
        analysisOnly: emiSetup.viewport.analysis_nets_only,
        translucentScene: emiSetup.viewport.translucent_board,
        sceneMode: emiSetup.viewport.analysis_nets_only ? "analysis_only" : emiSetup.viewport.translucent_board ? "translucent" : "opaque",
      }
      : base;
  }, [resultVisualization, tab, emiSetup.viewport.analysis_nets_only, emiSetup.viewport.translucent_board]);
  const displayedResult = useMemo(() => {
    if (resultDisplay === "none") return null;
    const records = resultDisplay === "all" ? resultRecords : resultRecords.filter(record => record.id === resultDisplay);
    return mergeResultBundles(records);
  }, [resultDisplay, resultRecords]);
  const frameFieldSelection = useMemo(() => {
    const scalarFields: string[] = [];
    const vectorFields: string[] = [];
    switch (activeResultVisualization.mode) {
      case "voltage": scalarFields.push("voltage_v"); break;
      case "voltage_drop": scalarFields.push("voltage_drop_v"); break;
      case "current": scalarFields.push("current_a"); vectorFields.push("current_density"); break;
      case "current_density": scalarFields.push("current_density_a_mm2"); vectorFields.push("current_density"); break;
      case "power_loss": scalarFields.push("power_loss_w"); break;
      case "via_stress": scalarFields.push("via_current_density_a_mm2"); break;
      case "impedance": scalarFields.push("operating_point_impedance_ohm"); break;
      case "electric_field": vectorFields.push("electric_field"); break;
      case "magnetic_field": vectorFields.push("magnetic_field"); break;
    }
    if (probeMode === "hover") {
      for (const field of ["voltage_v", "voltage_drop_v", "current_a", "current_density_a_mm2", "power_loss_w", "operating_point_impedance_ohm"]) {
        if (!scalarFields.includes(field)) scalarFields.push(field);
      }
    }
    return { scalarFields, vectorFields };
  }, [activeResultVisualization.mode, probeMode]);
  const activeAnalysisResult = useMemo(
    () => resultAtFrame(displayedResult ?? (resultRecords.length ? null : analysisResult), resultVisualization.animationFrame, frameFieldSelection),
    [analysisResult, displayedResult, resultRecords.length, resultVisualization.animationFrame, frameFieldSelection],
  );
  const activePdnReview = resultVisualizerDomain === "pi" && activeAnalysisResult?.analysis_id
    && activeAnalysisResult.analysis_id === analysisResult?.analysis_id && pdnReviewSourceId === analysisResult?.analysis_id ? pdnReview : null;
  const detachedProbeSnapshot = useMemo(() => buildDetachedProbeSnapshot(probes, activeAnalysisResult, probeFormulaRows, probeReferenceIds),
    [probes, activeAnalysisResult, probeFormulaRows, probeReferenceIds]);
  const detachedResultsSnapshot = useMemo(() => buildDetachedResultsSnapshot(activeAnalysisResult,
    { ...resultVisualization, viewMode, dataCursor: probeMode === "hover" }, resultVisualizerDomain),
    [activeAnalysisResult, resultVisualization, viewMode, probeMode, resultVisualizerDomain]);
  detachedActionRef.current = action => {
    if (action.type === "redock" || action.type === "closed") {
      if (action.type === "redock") void closeDetachedToolWindow(action.kind);
      setDetachedTools(current => ({ ...current, [action.kind]: false }));
      if (action.kind === "results") setResultVisualizerOpen(true);
      if (action.kind === "trace-plots") setTracePlotsOpen(true);
      if (action.kind === "probes") { setDock("Probe table"); setBottomOpen(true); }
      return;
    }
    if (action.kind === "probes") {
      if (action.type === "control-change" && action.controlId === "export-csv") { exportProbeCsv(); return; }
      if (action.type === "control-change" && action.controlId === "add-formula") {
        let index = 1;
        while (probeFormulaRows.some(row => row.id === `C${index}`) || Object.values(probeReferenceIds).includes(`C${index}`)) index++;
        recordChange(); setProbeFormulaRows(rows => [...rows, { id: `C${index}`, name: `Calculation C${index}`, formula: "" }]);
        return;
      }
      const id = action.rowId ?? null;
      if (action.type !== "row-action" || !id) return;
      if (action.actionId === "delete-probe") { recordChange(); setProbes(rows => rows.filter(row => row.id !== id)); }
      if (action.actionId === "rename-probe" && typeof action.value === "string") {
        markProjectDirty(); setProbes(rows => rows.map(row => row.id === id ? { ...row, name: String(action.value) } : row));
      }
      if (action.actionId === "delete-formula") { recordChange(); setProbeFormulaRows(rows => rows.filter(row => row.id !== id)); }
      if (["rename-formula", "edit-formula"].includes(action.actionId ?? "") && typeof action.value === "string") {
        markProjectDirty(); setProbeFormulaRows(rows => rows.map(row => row.id === id
          ? { ...row, [action.actionId === "rename-formula" ? "name" : "formula"]: String(action.value) } : row));
      }
      return;
    }
    if (action.kind !== "results" || action.type !== "control-change") return;
    const control = detachedResultsSnapshot.controls?.find(control => control.id === action.controlId);
    if (!control || control.disabled || control.kind === "select" && !control.options?.some(option => option.value === action.value)) return;
    if (control.id === "view" && (action.value === "2D" || action.value === "3D")) { setViewMode(action.value); return; }
    if (control.id === "data-cursor") { setProbeMode(action.value ? "hover" : "off"); return; }
    markProjectDirty();
    const value = String(action.value);
    if (control.id === "field") setResultVisualization(current => ({ ...current, visible: true, mode: value as ResultVisualization["mode"] }));
    if (control.id === "scene") setResultVisualization(current => ({ ...current, sceneMode: value as ResultVisualization["sceneMode"], translucentScene: value === "translucent" }));
    if (control.id === "plot") setResultVisualization(current => ({ ...current, plotStyle: value as ResultVisualization["plotStyle"] }));
    if (control.id === "style") setResultVisualization(current => ({ ...current, fieldStyle: value as ResultVisualization["fieldStyle"] }));
    if (control.id === "layer") setResultVisualization(current => ({ ...current, visibleResultLayers: value ? [value] : [] }));
  };
  const detachTool = async (kind: ToolWindowKind, propagateFailure = false) => {
    try {
      await openDetachedToolWindow(kind, kind === "probes" ? detachedProbeSnapshot : kind === "trace-plots"
        ? buildDetachedTraceSnapshot(activeAnalysisResult, resultVisualizerDomain, activePdnReview) : detachedResultsSnapshot,
        action => detachedActionRef.current(action));
      setDetachedTools(current => ({ ...current, [kind]: true }));
      if (kind === "results") setResultVisualizerOpen(false);
      if (kind === "trace-plots") setTracePlotsOpen(false);
    } catch (error) {
      setStatus(`[SPIKE-FE-APP-E-0001] Could not open tool window: ${error instanceof Error ? error.message : String(error)}. Retry from the bottom bar.`);
      if (propagateFailure) throw error;
    }
  };
  const openProbeTable = () => {
    setDock("Probe table"); setBottomOpen(true);
    setBottomPanelHeight(current => Math.max(current, Math.min(360, window.innerHeight * 0.5)));
    if (detachedTools.probes) void detachTool("probes");
  };
  const toggleBottomDock = (target: DockTab) => {
    if (dock === target && bottomOpen) { setBottomOpen(false); return; }
    if (target === "Probe table") { openProbeTable(); return; }
    setDock(target); setBottomOpen(true);
  };
  useEffect(() => {
    if (detachedTools.probes) void updateDetachedToolWindow("probes", detachedProbeSnapshot).catch(error => setStatus(String(error)));
  }, [detachedTools.probes, detachedProbeSnapshot]);
  useEffect(() => {
    if (detachedTools.results) void updateDetachedToolWindow("results", detachedResultsSnapshot).catch(error => setStatus(String(error)));
  }, [detachedTools.results, detachedResultsSnapshot]);
  useEffect(() => {
    if (detachedTools["trace-plots"]) void updateDetachedToolWindow("trace-plots", buildDetachedTraceSnapshot(activeAnalysisResult, resultVisualizerDomain, activePdnReview)).catch(error => setStatus(String(error)));
  }, [detachedTools["trace-plots"], activeAnalysisResult, resultVisualizerDomain, activePdnReview]);
  useEffect(() => () => { void closeAllDetachedToolWindows(); }, []);
  const activeResultNets = useMemo(() => activeAnalysisResult ? [...new Set([
    ...Object.values(activeAnalysisResult.scalar_fields).flatMap(samples => samples.map(sample => sample.net).filter((net): net is string => Boolean(net))),
    ...activeAnalysisResult.mesh.map(cell => cell.net).filter((net): net is string => Boolean(net)),
  ])] : [], [activeAnalysisResult]);
  // Telemetry and resource samples update App frequently. Keep this identity
  // stable so unchanged result overlays are not destroyed and rebuilt merely
  // because a parent status widget rendered again.
  const viewportAnalysisNets = useMemo(() => uniqueViewportNets([
    ...activeResultNets,
    ...(tab === "EM" ? [...emiSetup.selected_nets, ...emiSetup.return_nets] : []),
    selected?.net,
    piSetup.net,
    isolatedNet,
  ]), [activeResultNets, tab, emiSetup.selected_nets, emiSetup.return_nets, selected?.net, piSetup.net, isolatedNet]);
  const availableResultModes = useMemo(() => new Set(availableViewportResultModes(activeAnalysisResult)), [activeAnalysisResult]);
  const hasStoredResults = Boolean(resultRecords.length || analysisResult);
  const hasExtractedNetworks = resultHasExtractedNetworks(activeAnalysisResult);
  const hasVectorResult = Boolean(activeAnalysisResult && (
    activeAnalysisResult.vector_fields.current_density.length
    || activeAnalysisResult.vector_fields.electric_field.length
    || activeAnalysisResult.vector_fields.magnetic_field.length
  ));
  const contextualToolbarLabel = viewportContextLabel({
    tab,
    analysisMode,
    hasBoard: Boolean(boardData),
    hasSelection: Boolean(selected),
    hasSelectedNet: Boolean(selected?.net || piSetup.net),
    hasStoredResults,
    hasActiveResult: Boolean(activeAnalysisResult),
  });
  const selectViewportResult = (mode: ResultViewMode) => {
    const modeIsAvailable = mode === "impedance"
      ? Boolean(activeAnalysisResult?.scalar_fields.operating_point_impedance_ohm.length)
      : resultModeAvailable(activeAnalysisResult, mode);
    if (mode === "geometry" || modeIsAvailable) {
      setResultVisualization(current => ({
        ...current,
        visible: true,
        mode,
        sceneMode: mode === "geometry" && current.sceneMode === "results_only" ? "opaque"
          : mode !== "geometry" && current.sceneMode === "opaque" ? "translucent" : current.sceneMode,
        translucentScene: mode !== "geometry" && current.sceneMode === "opaque" ? true : current.translucentScene,
      }));
      setStatus(mode === "geometry" ? "Native board geometry view restored" : `${mode.replace(/_/g, " ")} overlay selected`);
      return;
    }
    if (mode === "impedance") {
      setAnalysisMode("DC IR Drop");
      setDcRunOpen(true);
      setStatus("Configure and run DC PI to generate the operating-point |V/I| field");
      return;
    }
    setAnalysisMode("DC IR Drop");
    setDcRunOpen(true);
    setStatus(`Configure and run DC PI to generate the ${mode.replace(/_/g, " ")} field`);
  };
  const openParasiticWorkbench = () => {
    setResultVisualization(current => ({ ...current, visible: true, mode: "impedance" }));
    setResultVisualizerDomain("si");
    setResultVisualizerOpen(true);
    if (!activeAnalysisResult?.parasitics.length) runParasitics(resultVisualization.viaModel);
    else setStatus("Extracted R/L/C/G network opened; inspect per-port quality and validity metadata");
  };
  useEffect(() => {
    const frameCount = analysisResult?.time_series.frames.length ?? 0;
    if (!resultVisualization.animationPlaying || frameCount < 2) return;
    const timer = window.setInterval(() => {
      setResultVisualization(current => ({
        ...current,
        animationFrame: (current.animationFrame + 1) % frameCount,
      }));
    }, 1000 / Math.max(1, resultVisualization.animationFps));
    return () => window.clearInterval(timer);
  }, [analysisResult, resultVisualization.animationPlaying, resultVisualization.animationFps]);
  const viewportResultScale = useMemo(() => {
    if (!activeAnalysisResult || !resultVisualization.visible) return null;
    const mode = resultVisualization.mode;
    const samples = mode === "voltage" ? activeAnalysisResult.scalar_fields.voltage_v
      : mode === "voltage_drop" ? activeAnalysisResult.scalar_fields.voltage_drop_v
        : mode === "current" ? activeAnalysisResult.scalar_fields.current_a
          : mode === "current_density" ? activeAnalysisResult.scalar_fields.current_density_a_mm2
            : mode === "power_loss" ? activeAnalysisResult.scalar_fields.power_loss_w
              : mode === "via_stress" ? activeAnalysisResult.scalar_fields.via_current_density_a_mm2
                : mode === "impedance" ? activeAnalysisResult.scalar_fields.operating_point_impedance_ohm : [];
    if (!samples.length) return null;
    const values = samples.map(sample => sample.value).filter(Number.isFinite);
    if (!values.length) return null;
    const fieldKey = mode === "voltage" ? "voltage_v"
      : mode === "voltage_drop" ? "voltage_drop_v"
        : mode === "current" ? "current_a"
          : mode === "current_density" ? "current_density_a_mm2"
            : mode === "power_loss" ? "power_loss_w"
              : mode === "impedance" ? "operating_point_impedance_ohm" : "via_current_density_a_mm2";
    const savedRanges = activeAnalysisResult.summary.visualization_ranges as Record<string, { minimum?: number; maximum?: number }> | undefined;
    const extent = numericExtent(values);
    const rangeMinimum = Number.isFinite(savedRanges?.[fieldKey]?.minimum) ? Number(savedRanges?.[fieldKey]?.minimum) : extent.minimum;
    const rangeMaximum = Number.isFinite(savedRanges?.[fieldKey]?.maximum) ? Number(savedRanges?.[fieldKey]?.maximum) : extent.maximum;
    const multiplier = mode === "voltage_drop" ? 1000 : 1;
    return {
      label: mode === "voltage" ? "ABSOLUTE VOLTAGE"
        : mode === "voltage_drop" ? "VOLTAGE DROP"
          : mode === "current" ? "CURRENT"
            : mode === "power_loss" ? "COPPER LOSS"
              : mode === "via_stress" ? "VIA STRESS"
                : mode === "impedance" ? "OPERATING-POINT V/I" : "CURRENT DENSITY",
      unit: mode === "voltage_drop" ? "mV" : mode === "voltage" ? "V" : mode === "current" ? "A" : mode === "power_loss" ? "W" : mode === "impedance" ? "ohm" : "A/mm²",
      minimum: rangeMinimum * multiplier,
      maximum: rangeMaximum * multiplier,
    };
  }, [activeAnalysisResult, resultVisualization]);
  const missingStackupCopperLayers = boardData?.layers.filter(name => !boardData.stackup.some(layer => layer.name === name && Number(layer.thickness) > 0)) ?? [];
  const stackupDielectrics = boardData?.stackup.filter(layer => /core|prepreg|dielectric/i.test(`${layer.type} ${layer.name}`)) ?? [];
  const stackupComplete = Boolean(
    boardData?.layers.length
    && missingStackupCopperLayers.length === 0
    && stackupDielectrics.length >= Math.max(boardData.layers.length - 1, 1)
    && stackupDielectrics.every(layer => Number(layer.thickness) > 0 && Number(layer.epsilonR) > 1 && Number(layer.lossTangent) >= 0),
  );
  const activeWorkspaceIssues = workspaceIssues({ hasBoard: Boolean(boardData), workspace: tab, mode: analysisMode,
    stackupComplete, components: boardData?.components.length ?? 0, nets: Object.keys(boardData?.nets ?? {}).length,
    copperLayers: boardData?.layers.length ?? 0, stackRows: boardData?.stackup.length ?? 0,
    convergence: analysisResult?.summary.mesh_convergence_status, convergenceLevels: analysisResult?.summary.mesh_convergence_levels });
  const workspaceWarningCount = activeWorkspaceIssues.filter(issue => issue.kind === "warning").length;
  const resolveSimulationSetup = () => {
    if (!boardData) {
      setStatus("Import a board before resolving the simulation setup");
      return;
    }
    const net = piSetup.net && Object.values(boardData.nets).includes(piSetup.net)
      ? piSetup.net
      : selected?.net && Object.values(boardData.nets).includes(selected.net) ? selected.net : preferredPowerNet(boardData);
    if (!net) {
      setStatus("Setup could not be resolved: no connected power net was found");
      return;
    }
    const pads = boardData.pads.filter(pad => pad.net === net).sort((left, right) => left.at[0] + left.at[1] - right.at[0] - right.at[1]);
    const tracks = boardData.tracks.filter(track => track.net === net);
    const anchor = (kind: "source" | "load", existing: PiTerminal | undefined, useEnd: boolean): PiTerminal | null => {
      const pad = pads[useEnd ? pads.length - 1 : 0];
      if (pad) {
        const layers = pad.layers.filter(layer => layer.endsWith(".Cu"));
        return {
          ...(existing ?? terminal(kind, 0)),
          net,
          x: String(pad.at[0]),
          y: String(pad.at[1]),
          layer: "auto",
          layers,
          anchorId: pad.id,
          anchorType: "pad",
        };
      }
      const track = tracks[useEnd ? tracks.length - 1 : 0];
      if (!track) return null;
      const point = useEnd ? track.end : track.start;
      return {
        ...(existing ?? terminal(kind, 0)),
        net,
        x: String(point[0]),
        y: String(point[1]),
        layer: track.layer,
        layers: [track.layer],
        anchorId: track.id,
        anchorType: "track-coordinate",
      };
    };
    const terminalValid = (item: PiTerminal | undefined) => Boolean(item
      && item.net === net
      && Number.isFinite(Number(item.x))
      && Number.isFinite(Number(item.y))
      && (item.anchorId || item.anchorType === "coordinate"));
    const source = terminalValid(piSetup.sources[0]) ? piSetup.sources[0] : anchor("source", piSetup.sources[0], false);
    const load = terminalValid(piSetup.loads[0]) ? piSetup.loads[0] : anchor("load", piSetup.loads[0], true);
    if (!source || !load) {
      setStatus(`Setup could not be resolved: ${net} has no routed copper or pads for terminal placement`);
      return;
    }
    const returnNet = piSetup.returnPath.net && Object.values(boardData.nets).includes(piSetup.returnPath.net)
      ? piSetup.returnPath.net
      : Object.values(boardData.nets).find(candidate => /(^|[/_])(gnd|vss|0v)([/_]|$)/i.test(candidate)) ?? "";
    const minimumWidth = numericMinimum(tracks.map(track => track.width).filter(width => width > 0), 1);
    const targetMm = String(Math.max(0.05, Math.min(0.5, minimumWidth / 2)));
    recordChange();
    setPiSetup(current => ({
      ...current,
      net,
      sources: [source, ...current.sources.slice(1).filter(item => terminalValid(item))],
      loads: [load, ...current.loads.slice(1).filter(item => terminalValid(item))],
      returnPath: { ...current.returnPath, net: returnNet || current.returnPath.net, mode: returnNet ? current.returnPath.mode : "implicit" },
      meshTargetMm: current.meshTargetMm && Number(current.meshTargetMm) > 0 ? current.meshTargetMm : targetMm,
      zoneCellMm: current.zoneCellMm && Number(current.zoneCellMm) > 0 ? current.zoneCellMm : targetMm,
      maxPreviewCells: String(Math.max(100, Number(current.maxPreviewCells) || 100000)),
    }));
    setPowerNets([net, ...(returnNet ? [returnNet] : [])]);
    setSolverId("auto");
    setFormulation("auto");
    setDock("Issues");
    setStatus(`Simulation setup resolved for ${net}: source and load anchored, ${returnNet ? `return ${returnNet} assigned` : "implicit return retained"}, mesh defaults bounded`);
  };
  const toggleLayer = (layer: LayerName) => { recordChange(); setVisibleLayers(current => ({ ...current, [layer]: current[layer] === false })); };
  const setLayersVisible = (layers: LayerName[], visible: boolean) => { recordChange(); setVisibleLayers(current => ({ ...current, ...Object.fromEntries(layers.map(layer => [layer, visible])) })); };
  const showOnlyLayer = (layer: LayerName) => { recordChange(); setVisibleLayers(Object.fromEntries(layerEntries.map(name => [name, name === layer])) as Record<LayerName, boolean>); };
  const showOnlyVias = () => { recordChange(); setVisibleLayers(Object.fromEntries(layerEntries.map(layer => [layer, false]))); setShowVias(true); };
  const changeLayerOpacity = (layer: LayerName, opacity: number) => {
    setLayerOpacity(current => ({ ...current, [layer]: Math.max(0.05, Math.min(1, opacity)) }));
  };
  const restoreLayerDefaults = () => { recordChange(); setVisibleLayers(Object.fromEntries(layerEntries.map(layer => [layer, defaultLayerVisible(layer) || Boolean(boardData?.layers.includes(layer))]))); setLayerOpacity({}); setLayerSeparation(0); setShowVias(true); };
  const openAnalysisSetup = (mode?: string, workflow: "single" | "path" | "batch" = "single") => {
    if (mode && mode !== analysisMode) {
      setAnalysisMode(mode);
      setSolverId("auto");
      setFormulation("auto");
    }
    setAnalysisSetupWorkflow(workflow);
    setSelected(null);
    setRightOpen(true);
    setDcRunOpen(true);
  };
  const openSharedWorkspace = (next: "Mesh" | "Solve", domain: SimulationDomain = "pi") => {
    setSimulationDomain(domain);
    setTab(next);
    setStatus(`${next} workspace selected for ${domain === "pi" ? "power" : "signal"} integrity`);
  };
  const saveProjectWithoutResults = () => void saveProject(projectFileName(projectName).replace(/\.spike$/i, "-without-results.spike"), true, false, false, false);
  const upgradeProjectNow = () => void saveProject(projectFileName(projectName).replace(/\.spike$/i, "-upgraded.spike"), true, true, true, true, true);
  const openSiWorkbench = (view: "workflow" | "geometry" = "geometry", focus: "channel" | "crosstalk" | "eye" | "pam4" | "impedance" | "ports" = "channel", preserveSuite = false) => {
    setSimulationDomain("si");
    if (!preserveSuite) setSelectedSiSuite(null);
    setSiWorkbenchIntent(current => ({ view, focus, token: current.token + 1 }));
    setSparameterOpen(true);
  };
  const addProbe = (object: BoardObject | null) => {
    if (!object) { setStatus("Select a board object before placing a probe"); return; }
    const track = boardData?.tracks.find(item => item.id === object.id);
    const position = object.position ?? boardData?.pads.find(item => item.id === object.id)?.at ?? boardData?.vias.find(item => item.id === object.id)?.at ?? boardData?.components.find(item => item.id === object.id)?.at ?? (track ? [(track.start[0] + track.end[0]) / 2, (track.start[1] + track.end[1]) / 2] as [number, number] : undefined);
    const placed = { ...object, position, probeKind };
    setProbes(current => current.some(probe => probe.id === object.id)
      ? current.map(probe => probe.id === object.id ? { ...probe, ...placed } : probe)
      : [...current, placed]);
    setDock("Probe table");
    setStatus(`${object.name} added as a ${probeKind} probe`);
  };
  const validateDesign = () => {
    setDock("Issues");
    if (!boardData) { setStatus("Validation failed: import a design first"); return; }
    const issues = [
      !boardData.outlineLoops.length ? "board outline" : "",
      !boardData.layers.length ? "copper layers" : "",
      !Object.keys(boardData.nets).length ? "net assignments" : "",
      !boardData.stackup.length ? "stackup" : "",
    ].filter(Boolean);
    setStatus(issues.length ? `Validation found missing ${issues.join(", ")}` : `Validation passed: ${boardData.layers.length} copper layers and ${Object.keys(boardData.nets).length} nets`);
  };
  const checkDependencies = async () => {
    const response = await runLocalWorker({ method: "dependencies", params: {} });
    setDock("Console");
    setStatus(response.ok ? "Dependency manifest verified by the local worker" : response.error ?? "Dependency status requires the packaged desktop app");
  };
  const openExtensionManager = async (extensionId?: string, contributionId?: string) => {
    setExtensionSelectedId(extensionId ?? "");
    setExtensionSelectedContributionId(contributionId ?? "");
    setExtensionsOpen(true);
    const response = await runLocalWorker({ method: "list_extensions", params: {} });
    const extensions = response.result?.extensions;
    if (response.ok && Array.isArray(extensions)) setExtensionCatalog(extensions as ExtensionCatalogEntry[]);
  };
  const navigateAnalysisGuide = (destination: GuideDestination) => {
    setMenu(null);
    if (destination === "emerge") {
      setExtensionSelectedId("spike.emerge-suite");
      if (!extensionsOpen) void openExtensionManager("spike.emerge-suite");
      return;
    }
    if (destination === "board-import") {
      setTab("Home");
      if (!appSettings.ribbonVisible) setAppSettings(current => {
        const next = { ...current, ribbonVisible: true };
        saveAppSettings(next);
        return next;
      });
      return;
    }
    if (destination === "emerge-emi") { setTab("EM"); setEmergeEmiOpen(true); return; }
    if (destination === "emerge-em-result") { setTab("EM"); setEmergeEmiOpen(false); setEmiChamberOpen(true); setEmiDashboardOpen(true); return; }
    if (destination === "pi") { setTab("PI"); setRightOpen(true); return; }
    if (destination === "si") { setTab("HF / SI"); setRightOpen(true); return; }
    if (destination === "emi") { setTab("EM"); setRightOpen(true); return; }
    if (destination === "thermal") { setTab("Thermal"); if (boardData) setThermalOpen(true); return; }
    if (destination === "circuit") { setTab("PI"); setSpiceOpen(true); return; }
    if (destination === "results") { setTab("Results"); setResultVisualizerOpen(true); }
  };
  const extensionUiVisible = (extension: ExtensionCatalogEntry, part: "menuBar" | "titleBar") =>
    appSettings.extensionUiVisibility?.[extension.id]?.[part] ?? true;
  const toggleExtensionUi = (extensionId: string, part: "menuBar" | "titleBar") => {
    const extension = extensionCatalog.find(item => item.id === extensionId);
    if (!extension) return;
    setAppSettings(current => {
      const next = { ...current, extensionUiVisibility: {
        ...current.extensionUiVisibility,
        [extensionId]: { menuBar: part === "menuBar" ? !(current.extensionUiVisibility?.[extensionId]?.menuBar ?? true) : (current.extensionUiVisibility?.[extensionId]?.menuBar ?? true),
          titleBar: part === "titleBar" ? !(current.extensionUiVisibility?.[extensionId]?.titleBar ?? true) : (current.extensionUiVisibility?.[extensionId]?.titleBar ?? true) },
      } };
      saveAppSettings(next);
      return next;
    });
  };
  const trustExtension = async (extensionId: string) => {
    setExtensionTrusting(extensionId); setExtensionTrustError("");
    try {
      const response = await runLocalWorker({ method: "trust_extension", params: { extension_id: extensionId } });
      if (!response.ok) throw new Error(response.error ?? "Extension trust request failed.");
      await openExtensionManager();
      setStatus(`Trusted ${extensionId} for this session`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Extension trust request failed.";
      setExtensionTrustError(message); setStatus(message);
    } finally { setExtensionTrusting(null); }
  };
  const invokeExtension = async (extensionId: string, contributionId: string, parameters: Record<string, any> = {}) => {
    const invocationDesign = extensionWorkflowDesignRef.current;
    if (extensionId === "spike.optycal-suite") invalidateOptycalPreview();
    const optycalGeneration = optycalGenerationRef.current;
    let preparingEMerge = extensionId === "spike.emerge-suite" && ["emerge-preview", "emerge-radiation", "emerge-si", "emerge-mesh", "emerge-mesh-preview"].includes(contributionId);
    if (preparingEMerge) invalidateEMergePreview();
    const previewGeneration = emergePreviewGenerationRef.current;
    try {
    const extension = extensionCatalog.find(item => item.id === extensionId);
    const contributionEntry = Object.entries(extension?.contributes ?? {}).flatMap(([point, entries]) => entries.map(item => ({ point, item }))).find(entry => entry.item.id === contributionId);
    const contribution = contributionEntry?.item;
    if (extension?.contributes.importers?.some(item => item.id === contributionId) && contribution?.output_contract === "spike/v1") {
      const file = await selectNativeImportFile("board", Boolean(parameters.directory));
      if (!file) { setStatus("CAD import cancelled"); return; }
      if (extensionId === "spike.odb-import" || contributionId === "ipc2581-design") {
        setSourceImport({ source: file, kind: extensionId === "spike.odb-import" ? "odb++" : "ipc2581" });
        setExtensionsOpen(false); return;
      }
      const { directory: _directory, ...options } = parameters;
      setStatus(`Importing ${file.fileName} with ${contribution.name}…`);
      const response = await runLocalWorker({ method: "import_design_v2", params: { path: file.path, format_hint: contributionId, options, include_snapshot: true } });
      if (!response.ok || !response.result?.snapshot) throw new Error(response.error ?? "CAD import returned no design snapshot.");
      await applyImportedBoard(`${file.fileName}.spike-design.json`, JSON.stringify(response.result.snapshot));
      setExtensionResult({ title: "CAD import quality report", data: response.result.report });
      return;
    }
    if (contributionId === "harness-import" && !parameters.path) {
      const file = await selectNativeImportFile("harness");
      if (!file) { setStatus("Harness import cancelled"); return; }
      parameters = { ...parameters, path: file.path };
    }
    const design = designForExchange();
    if (contributionEntry?.point === "analyses" && !design) throw new Error("Import a board before running an extension analysis.");
    if (extensionId === "spike.openems-suite" && !design) throw new Error("Import a board before running OpenEMS PI or SI.");
    const extensionDesign = design;
    const permissions = extensionCatalog.find(extension => extension.id === extensionId)?.permissions ?? [];
    const selectedResult = resultRecords.find(record => record.id === resultDisplay)?.bundle ?? analysisResult;
    const context = {
      ...(permissions.includes("design.read") && extensionDesign ? { design: extensionDesign } : {}),
      ...(permissions.includes("project.read") ? { project: { name: projectName,
        ...(extensionId === "spike.mcad" && assemblyIr ? { assembly_ir: assemblyIr, ...(assemblyDesigns ? { assembly_designs: assemblyDesigns } : {}) } : {}),
        ...(extensionId === "spike.mcad" && boardSource && !boardFile.endsWith(".spike-design.json") ? { source_board: boardSource, source_format: "kicad" } : {}) } } : {}),
      ...(permissions.includes("selection.read") ? { selection: selected } : {}),
      ...(permissions.includes("harness.read") && harnessDocument ? { harness: harnessDocument } : {}),
      ...(permissions.includes("results.read") ? { results: extensionResultsContext(selectedResult) } : {}),
      parameters,
    };
    if (extensionId === "spike.emerge-suite" && ["emerge-radiation", "emerge-si", "emerge-mesh"].includes(contributionId)) {
      const prepared = await runLocalWorker({ method: "invoke_extension", params: { extension_id: extensionId, contribution_id: contributionId === "emerge-mesh" ? "emerge-mesh-preview" : "emerge-preview", context: { ...context, parameters: { ...parameters, preview_radiation: contributionId === "emerge-radiation" } } } });
      if (previewGeneration !== emergePreviewGenerationRef.current) { setStatus("EMerge setup changed during preparation; run again with the current setup"); return; }
      const preview = prepared.result?.data as Record<string, unknown> | undefined;
      if (!prepared.ok || typeof preview?.script !== "string" || !/^[a-f0-9]{64}$/.test(String(preview.script_sha256 ?? "")) || !/^[a-f0-9]{64}$/.test(String(preview.case_sha256 ?? ""))) {
        setEmergeEmiError(prepared.error ?? "EMerge preparation returned no verifiable generated script.");
        setStatus("EMerge preparation failed; previous solved results preserved"); return;
      }
      const scriptDigest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(preview.script))), byte => byte.toString(16).padStart(2, "0")).join("");
      if (previewGeneration !== emergePreviewGenerationRef.current) { setStatus("EMerge setup changed during preparation; run again with the current setup"); return; }
      if (scriptDigest !== preview.script_sha256) { setEmergeEmiError("EMerge generated script failed its source digest check."); setStatus("EMerge preparation failed; previous solved results preserved"); return; }
      setEmergeScriptPreview(preview);
      context.parameters = { ...parameters, expected_generated_script_sha256: scriptDigest };
      preparingEMerge = false;
    }
    if (extensionId === "spike.optycal-suite" && contributionId === "optycal-radiation") {
      const prepared = await runLocalWorker({ method: "invoke_extension", params: { extension_id: extensionId, contribution_id: "optycal-preview", context } });
      if (optycalGeneration !== optycalGenerationRef.current) throw new Error("Optycal setup changed during preparation; run again.");
      const preview = prepared.result?.data as Record<string, unknown> | undefined;
      if (!prepared.ok || typeof preview?.script !== "string") throw new Error(prepared.error ?? "Optycal returned no prepared Python script.");
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(preview.script))), byte => byte.toString(16).padStart(2, "0")).join("");
      if (optycalGeneration !== optycalGenerationRef.current || digest !== preview.script_sha256) throw new Error("Optycal script or setup changed during preparation.");
      setOptycalPreview(preview);
      context.parameters = { ...parameters, expected_generated_script_sha256: digest, expected_structure_source_sha256: preview.structure_source_sha256 };
    }
    const response = await runLocalWorker({ method: "invoke_extension", params: { extension_id: extensionId, contribution_id: contributionId, context } });
    if (!response.ok) {
      const message = response.error ?? "Extension execution failed";
      if (extensionId === "spike.emerge-suite" && !preparingEMerge) setExtensionResult({ status: "failed", title: "EMerge run failed", data: { error: message } });
      if (preparingEMerge) setEmergeEmiError(message);
      setStatus(message); return;
    }
    if (extensionId === "spike.emerge-suite" && previewGeneration !== emergePreviewGenerationRef.current) throw new Error("EMerge setup changed during execution; run the current case again.");
    if (invocationDesign.boardData !== extensionWorkflowDesignRef.current.boardData || invocationDesign.boardSource !== extensionWorkflowDesignRef.current.boardSource) throw new Error("The board changed during the extension job; prepare the current board again.");
    const title = String(response.result?.title ?? contributionId);
    const data = response.result?.data as Record<string, unknown> | undefined;
    if (data?.mesh_result && typeof data.mesh_result === "object") {
      setExtensionMesh(data.mesh_result as Record<string, unknown>); setExtensionResult(response.result ?? null);
      setViewMode("3D"); setEmiChamberOpen(false); setEmiDashboardOpen(false);
      setStatus(`${title}: completed unsolved mesh · ${(data.mesh_result as Record<string, unknown>).model_status}`); return;
    }
    if (extensionId === "spike.optycal-suite" && contributionId === "optycal-preview") {
      if (optycalGeneration === optycalGenerationRef.current) setOptycalPreview(data ?? null);
      setStatus("Optycal structure study prepared for review"); return;
    }
    if (extensionId === "spike.emerge-suite" && ["emerge-preview", "emerge-mesh-preview"].includes(contributionId)) {
      if (previewGeneration !== emergePreviewGenerationRef.current) return;
      if (typeof data?.script !== "string") throw new Error("EMerge preview returned no generated script.");
      setEmergeScriptPreview(data); setStatus("EMerge generated script ready for review"); return;
    }
    if (contributionEntry?.point === "analyses" && contribution?.output_contract === "spike/v1") {
      const result = extensionAnalysisResult(contributionEntry.point, contribution.output_contract, data);
      if (!result) throw new Error("Extension analysis returned no admitted, design-bound SPIKE result.");
      setExtensionResult(response.result ?? null);
      recordChange();
      window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: result }));
      if (!["spike.emerge-suite", "spike.optycal-suite"].includes(extensionId)) setExtensionsOpen(false);
      setDock("Console");
      if (["spike.emerge-suite", "spike.optycal-suite"].includes(extensionId) && ["emerge-radiation", "optycal-radiation"].includes(contributionId)) {
        if (emergeRadiationPatterns(response.result).length > 0) {
          setEmergeViewportBoardSource(boardSource);
          setTab("EM");
          setViewMode("3D");
          setEmergeEmiOpen(false);
          setExtensionsOpen(false);
          setEmiChamberOpen(false);
          setEmiDashboardOpen(false); setEmResultManagerOpen(true);
          setEmergePatternIndex(0);
          setStatus(`${title} completed: radiation pattern open in EM · ${result.model_status}`);
          return;
        }
      }
      setStatus(`${title} completed: ${result.status} · ${result.model_status}`);
      return;
    }
    setExtensionResult(response.result ?? null);
    if (contributionId === "harness-import" && data?.contract === "spike/harness/v1") { recordChange(); setHarnessDocument(data); }
    if (contributionId === "harness-export" && typeof data?.text === "string") {
      if (desktopShell) await saveNativeTextFile("harness.spike-harness.json", data.text, "result");
      else download("harness.spike-harness.json", data.text);
    }
    setDock("Console");
    setStatus(`${title} completed${data?.net_count !== undefined ? `: ${data.net_count} nets` : ""}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Extension execution failed";
      if (extensionId === "spike.emerge-suite" && !preparingEMerge) setExtensionResult({ status: "failed", title: "EMerge run failed", data: { error: message } });
      if (preparingEMerge) setEmergeEmiError(message);
      setStatus(message);
    }
  };
  const openEmiEmerge = () => {
    invalidateEMergePreview();
    setTab("EM");
    setEmergeSiOpen(false);
    setEmergeEmiSetup(current => current.signal_net ? current : { ...current, signal_net: emiSetup.selected_nets[0] ?? selected?.net ?? "" });
    setEmergePatternIndex(0);
    setEmergeEmiError("");
    setEmergeEmiOpen(true);
  };
  const openSiEmerge = () => {
    invalidateEMergePreview();
    setTab("HF / SI");
    setEmergeEmiOpen(false);
    setEmergeEmiSetup(current => current.signal_net ? current : { ...current, signal_net: selected?.net ?? "" });
    setEmergePatternIndex(0);
    setEmergeEmiError("");
    setEmergeSiOpen(true);
  };
  const openSelectedSParameters = () => {
    if (solverSelections.extension_si) { setTab("HF / SI"); setRightOpen(true); setStatus("Configure and run the selected SI extension in the workspace setup dock."); return; }
    if (siSParameterSolver === "emerge" && emergeSiAvailable) openSiEmerge();
    else openSiWorkbench("geometry", "channel");
  };
  const probeEmiEmerge = async () => {
    const extension = extensionCatalog.find(item => item.id === "spike.emerge-suite");
    if (!extension || !extension.trusted || extension.state === "disabled") {
      setEmergeEmiError("EMerge Suite is unavailable or untrusted. Open Extension manager to inspect it.");
      return;
    }
    setEmergeEmiBusy(true); setEmergeEmiError(""); setEmergeEmiRuntime(null);
    const probePath = emergeEmiSetup.python_executable.trim();
    emergeProbePathRef.current = probePath;
    try {
      const parameters = probePath ? { python_executable: probePath } : {};
      const response = await runLocalWorker({ method: "invoke_extension", params: {
        extension_id: "spike.emerge-suite", contribution_id: "emerge-probe", context: { parameters },
      } });
      if (!response.ok) throw new Error(response.error ?? "EMerge runtime probe failed.");
      const data = response.result?.data;
      if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("EMerge runtime probe returned no capability data.");
      if (emergeProbePathRef.current === probePath) setEmergeEmiRuntime(data as Record<string, unknown>);
    } catch (error) { if (emergeProbePathRef.current === probePath) setEmergeEmiError(error instanceof Error ? error.message : "EMerge runtime probe failed."); }
    finally { setEmergeEmiBusy(false); }
  };
  useEffect(() => {
    if (tab !== "HF / SI" || !emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled"
      || !emergeEmiExtension.contributes.analyses?.some(item => item.id === "emerge-si")
      || emergeEmiRuntime !== null || emergeEmiBusy || emergeEmiError) return;
    void probeEmiEmerge();
  }, [tab, emergeEmiExtension?.trusted, emergeEmiExtension?.state, emergeEmiSetup.python_executable, emergeEmiRuntime, emergeEmiBusy, emergeEmiError]);
  useEffect(() => {
    if (siSParameterSolver === "emerge" && (!emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled"
      || (emergeEmiRuntime?.available === false)
      || (emergeEmiRuntime?.available === true && !emergeEmiCapabilities.includes("si_s_parameters")))) {
      setSiSParameterSolver("internal");
    }
  }, [siSParameterSolver, emergeEmiExtension?.trusted, emergeEmiExtension?.state, emergeEmiRuntime]);
  const runEmiEmerge = async (contributionId: "emerge-radiation" | "emerge-si") => {
    if (gerberRunBlocked) { setEmergeEmiError("Check the native Gerber runtime and install its optional Gerber dependency before running this source."); return; }
    const capability = contributionId === "emerge-radiation" ? "radiation_pattern" : "si_s_parameters";
    const capabilities = Array.isArray(emergeEmiRuntime?.capabilities) ? emergeEmiRuntime.capabilities : [];
    if (emergeEmiRuntime?.available !== true || !capabilities.includes(capability)) {
      setEmergeEmiError(`The selected EMerge runtime does not expose ${capability}.`); return;
    }
    try {
      const parameters = emergeParameters(emergeEmiSetup, gerberSource ? "gerber" : "board");
      setEmergeEmiBusy(true); setEmergeEmiError(""); setExtensionResult(null); setEmergePatternIndex(0);
      await invokeExtension("spike.emerge-suite", contributionId, parameters);
    } catch (error) { setEmergeEmiError(error instanceof Error ? error.message : "EMerge setup is incomplete."); }
    finally { setEmergeEmiBusy(false); }
  };
  const boardSourceSha256 = async () => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(boardSource))))
    .map(byte => byte.toString(16).padStart(2, "0")).join("");
  const showSavedEmergeRadiation = async (raw: unknown) => {
    try {
      if (!boardData || !boardSource) throw new Error("Import the source board before opening its EMerge result.");
      const sourceDesignId = activeDesignId ?? (boardFile.toLowerCase().endsWith(".kicad_pcb")
        ? `kicad-${(await boardSourceSha256()).slice(0, 24)}` : "");
      const preview = savedEmergeRadiationPreview(raw, sourceDesignId);
      if (!preview) throw new Error("The file has no completed EMerge radiation grid for this board or its disclosed two-conductor surrogate.");
      setExtensionResult(preview.envelope);
      setEmergeViewportBoardSource(boardSource);
      setTab("EM"); setViewMode("3D"); setEmergeEmiOpen(false); setEmiChamberOpen(false); setEmiDashboardOpen(false); setEmergePatternIndex(0);
      const result = normalizeSolverResult((preview.envelope.data as Record<string, unknown>)?.analysis_result);
      if (result) window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: result }));
      setStatus(`${preview.envelope.title} opened in EM as an unvalidated saved-result preview${preview.surrogate ? "; source board geometry was simplified for the solve" : ""}`);
    } catch (error) { setEmergeEmiError(error instanceof Error ? error.message : "Unable to open the saved radiation result."); }
  };
  const openSavedEmergeRadiation = async () => {
    if (!desktopShell) { savedEmergeInputRef.current?.click(); return; }
    try {
      const file = await openNativeTextFile("result");
      if (file) await showSavedEmergeRadiation(JSON.parse(file.contents));
    } catch (error) { setEmergeEmiError(error instanceof Error ? error.message : "Unable to open the saved radiation result."); }
  };
  const showSavedBoardThermal = async (raw: unknown) => {
    try {
      if (!boardData || !boardSource) throw new Error("Import the source board before opening its thermal result.");
      if (!raw || typeof raw !== "object") throw new Error("Invalid board thermal view bundle.");
      const bundle = raw as Record<string, unknown>;
      if (bundle.contract !== "spike/board-thermal-view-bundle/v1"
          || typeof bundle.source_board_sha256 !== "string"
          || bundle.source_board_sha256 !== await boardSourceSha256()) throw new Error("The saved thermal result does not match this board source.");
      const request = bundle.request as BoardThermalRequest | undefined;
      if (!request || typeof request !== "object" || !request.board || !Array.isArray(request.components)
          || !validBoardThermalResult(bundle.result, request) || (bundle.result as { status: string }).status !== "completed") {
        throw new Error("The saved board thermal request or completed result is invalid.");
      }
      recordChange();
      setThermalScenario(current => ({ ...current, board_thermal_request: request, board_thermal_result: bundle.result }));
      setThermalVisibility(current => ({ ...current, field: true }));
      setTab("Thermal"); setViewMode("3D"); setThermalOpen(false);
      setStatus("Saved board thermal cells opened in the 3D viewport; Thermal setup shows the temperature grids and X/Y/Z cuts. Model status: approximate.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Unable to open the saved board thermal result."); }
  };
  const openSavedBoardThermal = async () => {
    if (!desktopShell) { savedBoardThermalInputRef.current?.click(); return; }
    try {
      const file = await openNativeTextFile("result");
      if (file) await showSavedBoardThermal(JSON.parse(file.contents));
    } catch (error) { setStatus(error instanceof Error ? error.message : "Unable to open the saved board thermal result."); }
  };
  const runAnalysis = () => {
    if (!boardData) { setStatus("Import a KiCad board before configuring an analysis"); return; }
    if (solverSelections.extension_pi) { setTab("PI"); setRightOpen(true); setStatus("Configure and run the selected extension engine in the workspace setup dock."); return; }
    if (!["DC IR Drop", "Bulk Net Analysis", "AC Impedance Sweep", "Transient PI"].includes(analysisMode)) {
      setStatus(`${analysisMode} remains capability-gated`);
      return;
    }
    openSharedWorkspace("Solve", "pi");
    setDcRunOpen(true);
  };
  const cancelActiveAnalysis = async () => {
    setStatus("Cancelling the active solver operation...");
    setOperationDisplay(current => current
      ? { ...current, label: "Cancelling solver operation" }
      : { label: "Cancelling solver operation", elapsedSeconds: 0 });
    const cancelled = await cancelLocalWorker(activeWorkerOperation?.id);
    if (!cancelled) {
      setAnalysisRunning(false);
      setOperationDisplay(null);
      setStatus("[SPIKE-FE-APP-E-0001] No cancellable worker operation was active.");
    }
  };
  const designForSolver = () => boardData && boardFile.endsWith(".spike-design.json")
    ? { ...normalizedSolverDesign(boardSource), stackup: boardData.stackup, component_bonds: bondsForSolver(componentBonds) }
    : boardData ? {
    contract: "spike/v1",
    name: boardFile,
    source_format: "kicad",
    layers: boardData.layers.map(name => ({ name })),
    nets: Object.entries(boardData.nets).map(([id, name]) => ({ id, name })),
    tracks: boardData.tracks.map(track => ({ ...track, net_name: track.net })),
    vias: boardData.vias.map(via => ({ ...via, net_name: via.net })),
    pads: boardData.pads.map(pad => ({ ...pad, net_name: pad.net })),
    zones: [...boardData.zones.map(zone => ({ ...zone, net_name: zone.net })),
      ...boardData.drawings.filter(drawing => drawing.layer.endsWith(".Cu") && drawing.type === "poly" && drawing.filled)
        .map(drawing => ({ id: drawing.id, layer: drawing.layer, points: drawing.points, net_name: "",
          source_kind: "footprint_graphic_polygon" }))],
    components: boardData.components,
    stackup: boardData.stackup,
    technology: boardData.technology ?? "rigid",
    regions: boardData.regions ?? [],
    bends: boardData.bendLines ?? [],
    component_bonds: bondsForSolver(componentBonds),
  } : null;
  const designForExchange = () => {
    const design = designForSolver();
    return design ? {
      ...design,
      design_id: String((design as Record<string, unknown>).design_id ?? activeDesignId ?? boardFile),
      units: "mm",
      issues: Array.isArray((design as Record<string, unknown>).issues) ? (design as Record<string, unknown>).issues : [],
      metadata: (design as Record<string, unknown>).metadata ?? {},
    } : null;
  };
  const requireAssemblyAdmission = async (workload: AssemblyWorkload): Promise<AssemblyAnalysisScope | null> => {
    requireSupportedAssemblyPhysics(assemblyIr, workload, activeDesignId, selectedBoardInstanceId);
    const scope = assemblyAnalysisScope(assemblyIr, activeDesignId, projectManifestDigest, selectedBoardInstanceId);
    const params = assemblyAdmissionParams(assemblyIr, designForSolver(), activeDesignId, workload, appSettings.solverMemoryLimitGb, assemblyDesigns);
    if (!params) return scope;
    if (!workerAvailable) throw new Error("Assembly resource admission requires the local desktop worker.");
    const response = await runLocalWorker({ method: "estimate_assembly_resources", params });
    if (!response.ok || !response.result) throw new Error(response.error ?? "Assembly resource admission returned no result.");
    requireAdmittedAssembly(response.result, workload);
    return scope;
  };
  // Callbacks are refreshed after all referenced setup and admission functions exist.
  mcpAnalysisCallbacks.current = {
    getContext: () => {
      let scope: AssemblyAnalysisScope | null = null;
      try { scope = assemblyAnalysisScope(assemblyIr, activeDesignId, projectManifestDigest, selectedBoardInstanceId); } catch { /* Ambiguous scope stays blocked during admission; discovery still works. */ }
      return { design: designForExchange(), canonicalDesign: canonicalSpiDeR, assembly: assemblyIr, assemblyDesigns,
        assemblyScope: scope, boardFile, activeDesignId, sourceKiCadPcb: boardFile.toLowerCase().endsWith(".kicad_pcb") ? boardSource : undefined, boardBoundsMm: boardData ? [boardData.bounds.minX, boardData.bounds.minY, boardData.bounds.maxX, boardData.bounds.maxY] : undefined, extensions: extensionCatalog,
        results: [...resultRecords.map(row => row.bundle), ...(siChannelResult ? [siChannelResult] : []), ...(emiScreening ? [emiScreening] : []), ...(thermalScenario?.result ? [thermalScenario.result] : []), ...(thermalScenario?.board_thermal_result ? [thermalScenario.board_thermal_result] : [])] };
    },
    admitScope: async (kind, parameters) => {
      if (!workerAvailable) throw new Error("Loaded-board analysis requires the local desktop worker.");
      if (kind.startsWith("multiboard_")) return null;
      const workload: AssemblyWorkload = kind === "thermal" || kind === "board_thermal" ? "thermal"
        : kind === "si" || kind === "si_workflow" || kind === "em" || kind === "extension" ? "full_wave"
        : ["dc", "dc_ir_drop", "bulk_net", "DC IR Drop", "Bulk Net Analysis"].includes(String((parameters.spec as Record<string, unknown> | undefined)?.mode)) ? "pi_dc" : "pi_ac";
      return requireAssemblyAdmission(workload);
    },
    publishResult: async (raw, meta) => {
      const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
      const data = object(raw.data), payload = object(data.analysis_result ?? raw.analysis_result ?? raw);
      setMcpAnalysisOutput({ ...raw, mcp: meta });
      if (meta.kind === "ac_pi" && payload.contract === "spike/ac-pi-result/v1") {
        setAcEffectsRequest(object(meta.parameters.request)); setAcEffectsResult(payload); setAcEffectsOpen(true); setTab("PI"); markProjectDirty();
      } else if (payload.contract === "spike/v1" && payload.analysis_id) {
        const result = normalizeSolverResult(payload);
        if (!result) throw new Error("Returned result cannot be admitted into SPIKE result history.");
        if (meta.kind === "extension") setExtensionResult(raw);
        window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: result }));
      } else if (["spike/si-channel-result/v1", "spike/si-workflow-result/v1"].includes(String(payload.contract))) {
        setSiChannelResult(payload); setTab("HF / SI");
      } else if (payload.contract === "spike/thermal-result/v1") {
        setThermalScenario(current => ({ ...current, ...(meta.parameters.scenario as Record<string, unknown> | undefined), result: payload })); setTab("Thermal");
      } else if (payload.contract === "spike/board-thermal-result/v1") {
        const request = meta.parameters.request as BoardThermalRequest;
        if (!validBoardThermalResult(payload, request)) throw new Error("Returned board thermal result is invalid for its bound request.");
        setThermalScenario(current => ({ ...current, board_thermal_request: request, board_thermal_result: payload })); setTab("Thermal");
      } else if (meta.kind === "em" && payload.status === "completed_screening_only") {
        setEmiScreening(payload as unknown as EmiScreening); setTab("EM");
      }
      setStatus(`MCP ${meta.kind} evidence returned: ${String(payload.status ?? "unknown")} · ${String(payload.model_status ?? "qualification in evidence")}`);
    },
    resultAction: async (command, args) => {
      if (command === "analysis_generate_report") {
        if (Object.keys(args).length) throw new Error("Report generation takes no arguments; select a result first.");
        if (!boardData) throw new Error("Load a board before generating its engineering report.");
        await generateReport(); return { status: "report_preview_ready", saved: false, message: "Offline engineering report preview opened. Export HTML or print from SPIKE." };
      }
      if (Object.keys(args).some(key => !["resultId", "frequencyIndex", "quantity", "sampleIndex"].includes(key))) throw new Error("Unknown result view argument.");
      const record = resultRecords.find(row => row.id === args.resultId);
      if (!record) throw new Error("Choose a retained result ID from analysis_context.");
      const emRecord = { id: record.id, label: record.label, result: emViewportPayload(record.bundle) };
      if (record.bundle.em_fields || record.bundle.em_networks) {
        const quantities = availableEMQuantities(emRecord), frequencyIndex = args.frequencyIndex ?? 0;
        if (!Number.isInteger(frequencyIndex) || Number(frequencyIndex) < 0 || Number(frequencyIndex) >= emResultFrequencies(emRecord).length) throw new Error("Choose an available result frequencyIndex.");
        if (!quantities.length) {
          if (args.quantity !== undefined || args.sampleIndex !== undefined) throw new Error("This network result has no EM field sample grid.");
          setEmViewportSettings(current => ({ ...current, frequencyIndex: Number(frequencyIndex), visible: true }));
          setEmResultManagerOpen(true); setViewMode("3D"); setEmiChamberOpen(false); setEmiDashboardOpen(false); setResultDisplay(record.id);
          return { status: "result_graphs_opened", resultId: record.id };
        }
        const quantity = args.quantity ?? quantities[0]?.id;
        if (!quantities.some(row => row.id === quantity)) throw new Error("Choose an available result quantity.");
        const settings = { ...emViewportSettings, visible: true, frequencyIndex: Number(frequencyIndex), quantity: String(quantity), selectedSample: Number(args.sampleIndex ?? 0) };
        const data = buildEMViewportData(emRecord, settings);
        if (!Number.isInteger(settings.selectedSample) || settings.selectedSample < 0 || !data || settings.selectedSample >= data.values.length || data.values[settings.selectedSample] === null) throw new Error("Choose an actual available result sampleIndex.");
        setEmViewportSettings(settings); setEmResultManagerOpen(true); setViewMode("3D"); setEmiChamberOpen(false); setEmiDashboardOpen(false); setTab(record.bundle.mode === "si" ? "HF / SI" : "EM");
      } else {
        if (args.frequencyIndex !== undefined || args.quantity !== undefined || args.sampleIndex !== undefined) throw new Error("This result has no EM sample grid; use its standard result visualizer.");
        setResultVisualizerOpen(true); setResultVisualizerDomain(record.bundle.mode === "si" ? "si" : "pi");
      }
      setResultDisplay(record.id); return { status: "result_view_opened", resultId: record.id };
    },
  };
  const requestEmiPreflight = async () => {
    const design = designForSolver();
    if (!design) throw new Error("Import a design before configuring an EMI workflow");
    if (!workerAvailable) throw new Error("EMI preflight requires the local desktop worker");
    const assemblyScope = await requireAssemblyAdmission("full_wave");
    const response = await runLocalWorker({ method: "emi_preflight", params: { design, setup: emiSetup, assembly_scope: assemblyScope } });
    if (!response.ok || !response.result) throw new Error(response.error ?? "EMI preflight failed");
    const result = response.result as unknown as EmiPreflight;
    setEmiPreflight(result);
    return result;
  };
  const validateEmi = async () => {
    setEmiBusy(true);
    try {
      const result = await requestEmiPreflight();
      setDock("Console");
      setStatus(result.counts.errors
        ? `EMI preflight blocked by ${result.counts.errors} setup error${result.counts.errors === 1 ? "" : "s"}`
        : `EMI preflight ${result.status.replace(/_/g, " ")}: ${result.counts.warnings} warning${result.counts.warnings === 1 ? "" : "s"}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "EMI preflight failed");
    } finally {
      setEmiBusy(false);
    }
  };
  const runEmiScreening = async () => {
    const design = designForSolver();
    if (!design) { setStatus("Import a design before running EMI screening"); return; }
    if (!workerAvailable) { setStatus("EMI screening requires the local desktop worker"); return; }
    setEmiBusy(true);
    setStatus("Running traceable EMI pre-pass screening");
    try {
      const assemblyScope = await requireAssemblyAdmission("full_wave");
      const response = await runLocalWorker({ method: "emi_screen", params: { design, setup: emiSetup, assembly_scope: assemblyScope } });
      if (!response.ok || !response.result) throw new Error(response.error ?? "EMI screening failed");
      const result = response.result as unknown as EmiScreening;
      setEmiScreening(result);
      setEmiPreflight(result.preflight);
      setDock("Console");
      if (!result.screening) {
        setStatus(result.message ?? "EMI screening is blocked by incomplete pre-pass inputs");
        return;
      }
      const top = result.screening.recommended_nets[0];
      setEmiDashboardOpen(true);
      setStatus(top ? `EMI screening complete: ${top.net} ranked first for full-wave review` : "EMI screening completed without ranked nets");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "EMI screening failed");
    } finally {
      setEmiBusy(false);
    }
  };
  const refreshExternalEngines = async () => {
    setExternalEngineBusy(true);
    try {
      const [engineResponse, acceleratorResponse, managerResponse] = await Promise.all([
        runLocalWorker({ method: "list_external_engines", params: { refresh: true } }),
        runLocalWorker({ method: "list_accelerators", params: {} }),
        runLocalWorker({ method: "solver_manager", params: { refresh: true } }),
      ]);
      const engines = engineResponse.result?.engines;
      const accelerators = acceleratorResponse.result?.backends;
      if (engineResponse.ok && Array.isArray(engines)) setExternalEngineCatalog(engines as ExternalEngineCatalogEntry[]);
      if (acceleratorResponse.ok && Array.isArray(accelerators)) setAccelerationCatalog(accelerators as AccelerationCatalogEntry[]);
      if (managerResponse.ok && managerResponse.result?.contract === "spike/solver-manager/v1") setSolverManager(managerResponse.result as unknown as SolverManagerCatalog);
      setStatus(engineResponse.ok && acceleratorResponse.ok && managerResponse.ok
        ? "External engines, acceleration, and solver recommendations refreshed"
        : engineResponse.error ?? acceleratorResponse.error ?? managerResponse.error ?? "External engine detection requires the desktop worker");
    } finally {
      setExternalEngineBusy(false);
    }
  };
  const openExternalEngineCenter = async () => {
    setExternalEnginesOpen(true);
    await refreshExternalEngines();
  };
  const registerExternalSolver = async (engineId: string, path: string) => {
    setExternalEngineBusy(true);
    try {
      const response = await runLocalWorker({ method: "register_external_solver", params: { engine_id: engineId, path } });
      if (!response.ok) { setStatus(response.error ?? "Solver registration failed"); return; }
      const catalog = response.result?.catalog;
      if (catalog && typeof catalog === "object") setSolverManager(catalog as unknown as SolverManagerCatalog);
      setStatus(`${engineId} registered locally; no files were installed or executed`);
    } finally {
      setExternalEngineBusy(false);
    }
    await refreshExternalEngines();
  };
  const unregisterExternalSolver = async (engineId: string) => {
    setExternalEngineBusy(true);
    try {
      const response = await runLocalWorker({ method: "unregister_external_solver", params: { engine_id: engineId } });
      if (!response.ok) { setStatus(response.error ?? "Solver registration could not be removed"); return; }
      const catalog = response.result?.catalog;
      if (catalog && typeof catalog === "object") setSolverManager(catalog as unknown as SolverManagerCatalog);
      setStatus(`${engineId} registration forgotten; third-party files were not deleted`);
    } finally {
      setExternalEngineBusy(false);
    }
    await refreshExternalEngines();
  };
  const tuneManagedSolver = async (targetId: string, values: Record<string, string | number | boolean>) => {
    setExternalEngineBusy(true);
    try {
      const response = await runLocalWorker({ method: "tune_solver", params: { target_id: targetId, values } });
      if (!response.ok) { setStatus(response.error ?? "Solver tuning was rejected"); return; }
      const catalog = response.result?.catalog;
      if (catalog && typeof catalog === "object") setSolverManager(catalog as unknown as SolverManagerCatalog);
      setStatus(`${targetId} tuning saved after schema and range validation`);
    } finally {
      setExternalEngineBusy(false);
    }
  };
  const selectManagedSolver = async (workloadId: string, selectedSolverId: string) => {
    setExternalEngineBusy(true);
    try {
      const response = await runLocalWorker({ method: "select_solver", params: { workload_id: workloadId, solver_id: selectedSolverId, refresh: true } });
      if (!response.ok || !response.result) { setStatus(response.error ?? "Solver selection was rejected"); return; }
      if (response.result.status !== "selected") { setStatus(`Solver selection blocked: ${String(response.result.reason ?? "capability or runtime gate failed")}`); return; }
      recordChange();
      setSolverSelections(current => ({ ...current, [workloadId]: selectedSolverId }));
      if (workloadId === "owned_circuit_workspace" && selectedSolverId === "spike.owned_spice_workspace") {
        setExternalEnginesOpen(false);
        setSpiceOpen(true);
        setStatus("SPIKES backend selected. Configure and validate the structured circuit workspace before running; no simulation has been started.");
        return;
      }
      setStatus(`${selectedSolverId} selected for ${workloadId}; no fallback will be substituted and execution remains application-gated`);
    } finally {
      setExternalEngineBusy(false);
    }
  };
  const prepareExternalEngine = async (engineId: string) => {
    const design = designForSolver();
    if (!design) { setStatus("Import a design before preparing an external-engine case"); return; }
    if (engineId !== "external.openems") { setStatus(`${engineId} case preparation remains adapter-gated`); return; }
    if (!externalNetSelection.length) { setStatus("Select at least one complete net for openEMS export"); return; }
    setExternalEngineBusy(true);
    setStatus("Validating geometry and preparing an inspectable openEMS case");
    try {
      const assemblyScope = await requireAssemblyAdmission("full_wave");
      const response = await runLocalWorker({
        method: "prepare_openems_case",
        params: {
          assembly_scope: assemblyScope,
          design,
          spec: {
            contract: "spike/v1",
            analysis_id: `openems-${Date.now()}`,
            mode: "broadband_hf",
            solver_id: "external.openems",
            formulation: "fdtd_3d",
            net_names: externalNetSelection,
            frequency_start_hz: Math.max(Number(piSetup.frequencyStart) || 1e6, 1),
            frequency_stop_hz: Math.max(Number(piSetup.frequencyStop) || 1e9, 2),
            frequency_points: Math.max(Number(piSetup.frequencyPoints) || 101, 2),
            mesh: { target_size_mm: Number(piSetup.meshTargetMm) || 1 },
            options: { ports: [] },
          },
          options: {
            mesh_resolution_mm: Math.max(Math.min(Number(piSetup.meshTargetMm) || 0.5, 5), 0.01),
            max_solver_time_s: Math.max(tryParseSpiceNumber(piSetup.transientMaxSolverTimeS, 3600), 10),
          },
        },
      });
      if (!response.ok || !response.result) { setStatus(response.error ?? "openEMS case preparation failed"); return; }
      const result = response.result;
      const validation = (result.validation ?? {}) as Record<string, unknown>;
      const messages = (value: unknown) => Array.isArray(value) ? value.map(item => {
        if (item && typeof item === "object" && "message" in item) return String((item as { message: unknown }).message);
        return String(item);
      }) : [];
      const nextCase: ExternalCaseState = {
        status: String(result.status ?? "prepared_review_required"),
        caseDir: String(result.case_dir ?? ""),
        canRun: Boolean(validation.can_run),
        errors: messages(validation.errors),
        warnings: messages(validation.warnings),
      };
      setExternalCase(nextCase);
      setDock("Console");
      setStatus(nextCase.caseDir
        ? `openEMS case prepared at ${nextCase.caseDir}${nextCase.canRun ? "" : "; review warnings and define explicit ports before solving"}`
        : nextCase.errors[0] ?? "openEMS preflight blocked case generation");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "openEMS case preparation failed");
    } finally {
      setExternalEngineBusy(false);
    }
  };
  const prepareEmiCase = async () => {
    const design = designForSolver();
    if (!design) { setStatus("Import a design before preparing an EMI field case"); return; }
    setEmiBusy(true);
    setExternalEngineBusy(true);
    setStatus("Validating EMI setup and preparing an inspectable openEMS case");
    try {
      const assemblyScope = await requireAssemblyAdmission("full_wave");
      const preflight = await requestEmiPreflight();
      if (!preflight.can_prepare) {
        setEmiDashboardOpen(true);
        setStatus("EMI case preparation is blocked; review the preflight issues");
        return;
      }
      const netNames = [...new Set([...emiSetup.selected_nets, ...emiSetup.return_nets])];
      const farFieldRequested = emiSetup.requested_analyses.includes("far_field");
      const farFieldRequest = farFieldRequested && boardData ? {
        contract: "spike/openems-far-field-request/v1",
        frequencies_hz: emiFarFieldFrequencies(emiSetup.frequency.start_hz, emiSetup.frequency.stop_hz),
        theta: { start_deg: 0, stop_deg: 180, points: 37 },
        phi: { start_deg: -180, stop_deg: 180, points: 73 },
        radius_m: emiSetup.chamber.distance_m,
        center_mm: emiPhaseCenter(boardData, netNames),
      } : undefined;
      const response = await runLocalWorker({
        method: "prepare_openems_case",
        params: {
          assembly_scope: assemblyScope,
          design,
          spec: {
            contract: "spike/v1",
            analysis_id: `emi-openems-${Date.now()}`,
            mode: "emi_emc",
            solver_id: "external.openems",
            formulation: "fdtd_3d",
            required_capabilities: ["explicit_lumped_ports", "lossy_dielectrics", ...(farFieldRequested ? ["far_field"] : [])],
            net_names: netNames,
            frequency_start_hz: emiSetup.frequency.start_hz,
            frequency_stop_hz: emiSetup.frequency.stop_hz,
            frequency_points: emiSetup.frequency.points,
            mesh: { target_size_mm: emiSetup.mesh.resolution_mm },
            options: {
              ports: emiSetup.excitation.mode === "explicit_ports" ? emiSetup.excitation.ports : [],
              environment: emiSetup.environment,
              chamber_preview: { ...emiSetup.chamber, physics: "visual_only", distance_reference: "dut_edge" },
              requested_analyses: emiSetup.requested_analyses,
              boundary_padding_cells: emiSetup.mesh.padding_cells,
              ...(farFieldRequest ? { far_field: farFieldRequest } : {}),
            },
          },
          options: {
            mesh_resolution_mm: emiSetup.mesh.resolution_mm,
            max_solver_time_s: emiSetup.max_solver_time_s,
            max_far_field_samples: 250000,
          },
        },
      });
      if (!response.ok || !response.result) throw new Error(response.error ?? "openEMS EMI case preparation failed");
      const validation = (response.result.validation ?? {}) as Record<string, unknown>;
      const messages = (value: unknown) => Array.isArray(value) ? value.map(item => item && typeof item === "object" && "message" in item ? String((item as { message: unknown }).message) : String(item)) : [];
      const nextCase: ExternalCaseState = {
        status: String(response.result.status ?? "prepared_review_required"),
        caseDir: String(response.result.case_dir ?? ""),
        canRun: Boolean(validation.can_run),
        errors: messages(validation.errors),
        warnings: messages(validation.warnings),
      };
      setExternalCase(nextCase);
      setEmiPreparedSetupKey(JSON.stringify(emiSetup));
      setEmiFieldResult(null);
      setDock("Console");
      setStatus(nextCase.caseDir
        ? `EMI openEMS case prepared at ${nextCase.caseDir}${nextCase.canRun ? "; solver execution is available after review" : "; field solving remains gated"}`
        : nextCase.errors[0] ?? "EMI case preparation did not produce a job directory");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "EMI case preparation failed");
    } finally {
      setEmiBusy(false);
      setExternalEngineBusy(false);
    }
  };
  const runExternalEngine = async (engineId: string, setupOnly: boolean) => {
    if (engineId === "external.openems" && tab === "EM" && emiPreparedSetupKey !== JSON.stringify(emiSetup)) { setStatus("EMI setup changed. Prepare a new field scan before running."); return; }
    if (engineId !== "external.openems" || !externalCase?.caseDir) { setStatus("Prepare an openEMS case before execution"); return; }
    setExternalEngineBusy(true);
    setStatus(setupOnly ? "Building the openEMS CSXCAD setup" : "Running openEMS in an isolated local job directory");
    try {
      const assemblyScope = await requireAssemblyAdmission("full_wave");
      const response = await runLocalWorker({
        method: "run_openems_case",
        params: { case_dir: externalCase.caseDir, setup_only: setupOnly, timeout_seconds: 86400, assembly_scope: assemblyScope },
      });
      const result = response.result;
      if (!response.ok || !result) { setStatus(response.error ?? "openEMS execution failed"); return; }
      const nextStatus = String(result.status ?? "failed");
      const fieldResult = setupOnly ? null : normalizeEmiFieldResult(result);
      setExternalCase(current => current ? {
        ...current,
        status: nextStatus,
        errors: nextStatus === "failed" || nextStatus === "blocked" || nextStatus === "solver_unavailable"
          ? [String(result.message ?? "openEMS did not complete")]
          : current.errors,
      } : current);
      if (fieldResult) {
        setEmiFieldResult(fieldResult);
        if (fieldResult.far_field) setEmiDashboardOpen(true);
      }
      setDock("Console");
      setStatus(fieldResult?.far_field
        ? `openEMS NF2FF complete: ${fieldResult.far_field.frequencies_hz.length} frequencies, ${fieldResult.far_field.shape[1] * fieldResult.far_field.shape[2]} angular samples each; board result remains ${fieldResult.far_field.validation_status.replace(/_/g, " ")}`
        : `${setupOnly ? "openEMS setup" : "openEMS run"}: ${String(result.message ?? nextStatus)}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "openEMS execution failed");
    } finally {
      setExternalEngineBusy(false);
    }
  };
  const runCapabilityAnalysis = async (mode: string, nets: string[], capabilities: string[], options: Record<string, unknown>) => {
    const design = designForSolver();
    if (!design || !nets.length) { setStatus("Select at least one net before running this analysis"); return; }
    setAnalysisRunning(true);
    try {
      const assemblyScope = await requireAssemblyAdmission("pi_ac");
      const response = await runLocalWorker({
        method: "run_analysis",
        params: {
          contract: "spike/analysis-request/v1",
          assembly_scope: assemblyScope,
          design,
          spec: {
            contract: "spike/v1",
            analysis_id: `${mode}-${Date.now()}`,
            mode,
            solver_id: "auto",
            formulation: "auto",
            required_capabilities: capabilities,
            net_names: nets,
            frequency_start_hz: Number(piSetup.frequencyStart),
            frequency_stop_hz: Number(piSetup.frequencyStop),
            frequency_points: Number(piSetup.frequencyPoints),
            options,
          },
        },
      });
      const result = normalizeSolverResult(response.result);
      if (result) {
        const record = resultRecord(result, resultRecords.length);
        setAnalysisResult(result);
        setPdnReview(null); setPdnReviewSourceId(null);
        setResultRecords(current => boundedResultRecords([...current.filter(item => item.id !== record.id), record]));
        setResultDisplay(record.id);
        if (mode === "broadband_hf") {
          const firstFrequency = result.parasitics.flatMap(item => item.impedance ?? [])[0]?.frequency_hz ?? null;
          setResultVisualization(current => ({
            ...current,
            visible: true,
            // A network Z(f) sweep is graph data, not a spatial board field.
            // Keep the viewport truthful unless the solver published explicit
            // local operating-point impedance samples.
            mode: result.scalar_fields.operating_point_impedance_ohm.length ? "impedance" : "geometry",
            animationPlaying: false,
            animationFrame: 0,
            impedanceFrequencyHz: firstFrequency,
          }));
          setResultVisualizerDomain("pi");
          setResultVisualizerOpen(true);
        }
      }
      const firstIssue = result?.issues[0]?.message;
      setStatus(result?.status === "completed"
        ? mode === "broadband_hf"
          ? `Impedance extraction completed for ${nets.join(", ")}: ${result.parasitics.reduce((sum, item) => sum + (item.impedance?.length ?? 0), 0)} frequency points loaded`
          : `${mode} completed for ${nets.join(", ")}`
        : firstIssue ?? response.error ?? `${mode} requires a compatible installed solver plugin`);
      setDock("Console");
    } finally {
      setAnalysisRunning(false);
    }
  };
  function runParasitics(viaModel: ViaModel) {
    void runCapabilityAnalysis(
      "broadband_hf",
      [selected?.net ?? piSetup.net].filter(Boolean),
      ["partial_inductance", "frequency_dependent_impedance"],
      { extraction: "rlcg", via_model: viaModel, include_dielectric: true, capacitance_model: "auto", return_visualization: true, network_contract: "spike/rlgc-network/v1" },
    );
  }
  const runPdnReview = async (targetOhm: number, candidate: PdnCandidateRequest) => {
    if (!analysisResult || !resultSolvedForPresentation(analysisResult)) { setStatus("Run a completed AC impedance extraction before PDN review"); return; }
    const sourceId = analysisResult.analysis_id;
    setPdnReview(null); setPdnReviewSourceId(null);
    setAnalysisRunning(true);
    try {
      const response = await runLocalWorker({
        method: "pdn_review",
        params: { result: analysisResult, target_ohm: targetOhm, net: selected?.net ?? piSetup.net, candidates: [candidate] },
      });
      const review = response.result as PdnReview | undefined;
      if (review?.contract === "spike/pdn-review/v1") {
        setPdnReview(review);
        setPdnReviewSourceId(sourceId);
        setStatus(review.status === "pass" ? "PDN impedance target passed" : `${review.violation_count} PDN impedance points exceed the target`);
      } else {
        setStatus(response.error ?? "PDN review failed");
      }
    } finally {
      setAnalysisRunning(false);
    }
  };
  const runSiRisk = (victims: string[], aggressors: string[]) => void runCapabilityAnalysis(
    "si",
    [...new Set([...victims, ...aggressors])],
    ["coupled_line_extraction", "electric_field_coupling", "magnetic_field_coupling"],
    { risk_analysis: { victims, aggressors, electric_field: true, magnetic_field: true, cross_layer: true }, return_visualization: true },
  );
  const applyImportedBoard = async (fileName: string, source: string, sourcePath?: string | null) => {
    boardImport.begin(fileName);
    try {
      if (fileName.endsWith(".spike-design.json")) source = await hydrateNormalizedSnapshot(source);
      const parsed = await parseDesignSourceOffThread(fileName, source);
      const normalized = fileName.endsWith(".spike-design.json") ? normalizedDesignSnapshot(source) : null;
      const knownVisuals = await configureKnownVisuals(parsed, fileName, source);
      recordChange();
      resetPreparedVisualBundle();
      setDeferredBoardVisual(null);
      setBoardFile(fileName);
      setProjectName(`${fileName.replace(/\.[^.]+$/i, "")}.spike`);
      // An imported board starts a new package.  In particular, it must not
      // retain the previously opened package as a lossless Save As base.
      retainedProjectSnapshot.current = null;
      setProjectPath(null);
      setProjectManifestDigest(null);
      setBoardSource(source);
      setBoardData(parsed);
      setHarnessDocument(null);
      setStudies([]); setActiveStudyCaseId(null);
      setModelAssignments({}); setAssemblyModelAssignments({});
      setActiveDesignId(normalized?.canonical_design?.design_id ?? null);
      setCanonicalSpiDeR(normalized?.canonical_design ?? null);
      setSelected(null);
      setSelectedHarnessId(null);
      setSelectedBoardInstanceId(null);
      setSelectedTopologyReference(null);
      setMcadFocusedPartId(null);
      setAssemblyIr(null);
      setAssemblyDesigns(null);
      setAssemblyPackageShapes(null);
      setModelIndex(normalizeModelIndex(null));
      setAssemblySceneModels([]);
      setAssemblySelectorPreviews([]);
      setAssemblyPartViewportStates({});
      setAssemblyModelReadReady(false);
      setComponentBonds([]);
      setBondValidation([]);
      setIsolatedNet(null);
      setProbes([]); setProbeFormulaRows([]); setSavedProbeReferenceIds({});
      setAnalysisSummary(null);
      setAnalysisResult(null);
      setPdnReview(null); setPdnReviewSourceId(null);
      setResultRecords([]);
      setResultDisplay("none");
      setSelectedSiSuite(null);
      setSiChannelResult(null);
      setThermalScenario(null);
      setThermalPreview(null);
      const firstNet = preferredPowerNet(parsed);
      const available = [...new Set(Object.values(parsed.nets).filter(Boolean))];
      const returnNet = available.find(net => /(^|[/_.+-])(gnd|agnd|dgnd|pgnd|vss)(?:$|[/_.+-])/i.test(net)) ?? "";
      const nextSetup = defaultPiSetup();
      nextSetup.net = firstNet;
      nextSetup.returnPath.net = returnNet;
      setPiSetup(nextSetup);
      setEmiSetup(defaultEmiSetup(available));
      setEmiPreflight(null);
      setEmiScreening(null);
      setEmiFieldResult(null);
      setPowerNets([firstNet, returnNet].filter(Boolean));
      setPiTopology(extractTopologyFromBoard(parsed, "pi"));
      setSiTopology(extractTopologyFromBoard(parsed, "si"));
      setSpiceWorkspace(defaultSpiceWorkspace("pi", parsed));
      setVisibleLayers(visibilityForBoard(parsed));
      setLayerOpacity({});
      setLayerSeparation(0);
      setShowVias(true);
      window.dispatchEvent(new CustomEvent("spike-board-imported", { detail: parsed }));
      setStatus(`Imported ${fileName}: ${parsed.tracks.length} tracks, ${parsed.vias.length} vias, ${parsed.components.length} components, ${parsed.layers.length} copper / ${parsed.layerDefinitions.length} drawable layers`);
      if (!knownVisuals && !normalized) void prepareVisualBundleForBoard(parsed, fileName, source, sourcePath);
      else boardImport.finishBasic();
    } catch (error) {
      boardImport.fail(error instanceof Error ? error.message : "Import failed");
      setStatus(error instanceof Error ? `Import failed: ${error.message}` : "Import failed");
      throw error;
    }
  };
  const openNativeGerber = (pythonExecutable: string) => {
    if (emergeEmiBusy || universalRunning) { setStatus("Wait for the current operation before changing the Gerber source."); return; }
    if (pythonExecutable !== emergeEmiSetup.python_executable) { setEmergeEmiSetup(current => ({ ...current, python_executable: pythonExecutable })); setEmergeEmiRuntime(null); emergeProbePathRef.current = pythonExecutable.trim(); }
    setEmergeEmiOpen(false); setEmergeSiOpen(false); setExtensionsOpen(false); setGerberImportOpen(true);
  };
  const importNativeGerber = async (source: EMergeGerberSource) => {
    if (!workerAvailable || emergeEmiBusy || universalRunning) throw new Error("Wait for the current operation before loading a Gerber study.");
    if (!emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled") throw new Error("Enable the trusted EMerge engine before loading Gerber sources.");
    if (assemblyToolDraftOwnerRef.current) throw new Error(`Save or discard the assembly ${assemblyToolDraftOwnerRef.current} draft before importing.`);
    setEmergeEmiBusy(true); invalidateEMergePreview();
    try {
      const response = await runLocalWorker({ method: "invoke_extension", params: { extension_id: "spike.emerge-suite", contribution_id: "emerge-gerber-import", context: { parameters: { source, python_executable: emergeEmiSetup.python_executable.trim() || undefined } } } });
      if (!response.ok) throw new Error(response.error ?? "Native Gerber source preparation failed.");
      const data = response.result?.data as Record<string, unknown> | undefined, snapshot = data?.snapshot;
      if (!snapshot || typeof snapshot !== "object" || !activeGerberSource(JSON.stringify(snapshot))) throw new Error("EMerge returned no valid retained Gerber source snapshot.");
      const commit = async () => {
        await applyImportedBoard("native-gerber.spike-design.json", JSON.stringify(snapshot));
        setEmergeEmiSetup(current => ({ ...current, geometry_source: "gerber", geometry_backend: "emerge", field_excited_port: "1" }));
        if (data?.runtime && typeof data.runtime === "object" && !Array.isArray(data.runtime)) setEmergeEmiRuntime(data.runtime as Record<string, unknown>);
        setEmergeEmiError(""); setTab("EM"); setEmergeEmiOpen(true); setEmergeSiOpen(false);
        setStatus("Gerber sources loaded. Prepare the native EMerge mesh and inspect the explicit port planes before solving.");
      };
      if (projectDirtyRef.current) await new Promise<void>((resolve, reject) => setUnsavedPrompt({ actionLabel: "replace the active design with the Gerber study", closeWindow: false, preserveDirtyUntilApplied: true,
        onCancel: () => reject(new Error("Gerber loading cancelled. The current project and source setup are retained.")), action: async () => { try { await commit(); resolve(); } catch (error) { reject(error); } } }));
      else await commit();
    } finally { setEmergeEmiBusy(false); }
  };
  const applySourceImport = async (source: PreparedSource) => {
    const commit = async () => {
      if (source.kind === "board") {
        await applyImportedBoard(source.fileName, source.source, source.sourcePath);
      } else if (source.kind === "harness") {
        recordChange(); setHarnessDocument(source.document); setHarnessEditorOpen(true);
        setStatus("Harness connections imported; review connectivity in the harness editor.");
      } else {
        if (projectDirtyRef.current || !projectPath) {
          if (!await saveProject()) throw new Error("Save the current project before attaching this mechanical model.");
        }
        setMcadImportSource({ path: source.path, fileName: source.fileName }); setMcadAttachmentOpen(true);
        setStatus(`Mechanical source selected: ${source.fileName}`);
      }
      setSourceImport(null);
    };
    if (assemblyToolDraftOwnerRef.current) throw new Error(`Save or discard the assembly ${assemblyToolDraftOwnerRef.current} draft before importing.`);
    if (source.kind === "board" && projectDirtyRef.current) {
      await new Promise<void>((resolve, reject) => setUnsavedPrompt({ actionLabel: "replace the board with an imported project", closeWindow: false, preserveDirtyUntilApplied: true,
        onCancel: resolve, action: async () => { try { await commit(); resolve(); } catch (error) { reject(error); } },
      }));
    } else await commit();
  };
  const importOdbBoard = async (directory = false) => {
    if (!desktopShell) { setStatus("ODB++ archive and folder import requires the desktop app."); return; }
    try {
      const file = await selectNativeImportFile("board", directory);
      if (!file) { setStatus("ODB++ import cancelled"); return; }
      setSourceImport({ source: file, kind: "odb++" });
    } catch (error) { setStatus(error instanceof Error ? `ODB++ import failed: ${error.message}` : "ODB++ import failed"); }
  };
  const importNativeBoard = async () => {
    if (!desktopShell) { browserBoardInputRef.current?.click(); return; }
    setSourceImport({ kind: "kicad" });
  };
  const importBoard = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    event.target.value = "";
    requestUnsavedAction("import another board", async () => {
      try { await applyImportedBoard(file.name, await file.text()); }
      catch (error) { setStatus(error instanceof Error ? `Import failed: ${error.message}` : "Import failed"); }
    });
  };
  const exportReport = async () => {
    const name = `${projectName.replace(/\.spike$/i, "")}-results.spike-results.json`;
    try {
      const prepared = await boardImport.whenReady();
      const visuals = await serializeBoardVisuals(prepared ?? boardData, setStatus);
      const content = JSON.stringify(createResultPackage(projectData(), visuals));
      if (desktopShell) {
        const path = await saveNativeTextFile(name, content, "result");
        setStatus(path ? `Result bundle exported: ${path}` : "Result export cancelled");
      } else { download(name, content); setStatus(`Result bundle downloaded: ${name}`); }
    } catch (error) { setStatus(error instanceof Error ? `Result export failed: ${error.message}` : "Result export failed"); }
  };
  const applyResultFile = async (text: string, name: string) => {
    const loaded = readResultPackage(text);
    if (loaded.snapshot) {
      await applyProjectPackage(JSON.stringify({ ...loaded.snapshot, board_visuals: loaded.visuals }), name, null);
    } else {
      if (!boardData) throw new Error("This older result file has no embedded design. Open its original board first.");
      const savedFile = loaded.results.saved_project?.source_file;
      if (savedFile && savedFile !== boardFile) throw new Error(`Open ${savedFile} before loading these older results.`);
      const latest = normalizeSolverResult(loaded.results.latest_result);
      const records = boundedResultRecords((loaded.results.result_history ?? []).flatMap((record: any, index: number) => {
        const bundle = normalizeSolverResult(record.bundle ?? record);
        return bundle ? [{ id: String(record.id ?? bundle.analysis_id ?? index), label: String(record.label ?? `Result ${index + 1}`), bundle }] : [];
      }));
      if (!latest && !records.length) throw new Error("The result file contains no supported simulation results.");
      setAnalysisResult(latest ?? records[records.length - 1].bundle); setResultRecords(records);
      setResultDisplay(records[records.length - 1]?.id ?? "all");
      setResultVisualization(current => ({ ...current, visible: true }));
      if (loaded.results.probes) setProbes(loaded.results.probes);
      if (loaded.results.emi) {
        setEmiSetup(normalizeEmiSetup(loaded.results.emi.setup));
        setEmiScreening(loaded.results.emi.screening ?? null); setEmiPreflight(loaded.results.emi.preflight ?? null);
      }
    }
    markProjectDirty(); setBottomOpen(true); setDock("Console");
    const emiOnly = loaded.snapshot?.emi?.field_result && !loaded.results.latest_result && !loaded.results.result_history?.length;
    if (emiOnly) setEmiDashboardOpen(true);
    else {
      setResultVisualizerDomain(loaded.results.si?.latest_channel_result && !loaded.results.latest_result ? "si" : "pi");
      const emResult = loaded.results.latest_result && normalizeSolverResult(loaded.results.latest_result);
      setResultVisualizerOpen(!emResult?.em_fields);
      if (emResult?.em_fields) { setEmResultManagerOpen(true); setViewMode("3D"); setEmiChamberOpen(false); }
    }
    setStatus(`Simulation results loaded: ${name}`);
  };
  const loadResults = () => requestUnsavedAction("load simulation results", async () => {
    if (!desktopShell) { resultInputRef.current?.click(); return; }
    try {
      const file = await openNativeTextFile("result");
      if (file) await applyResultFile(file.contents, file.fileName);
    } catch (error) { setStatus(`Result load failed: ${error instanceof Error ? error.message : String(error)}`); }
  });
  const loadResultInput = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    try { await applyResultFile(await file.text(), file.name); }
    catch (error) { setStatus(`Result load failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.altKey || ownsKeyboardInput(event.target)) return;
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (event.shiftKey && key !== "z" && key !== "s") return;
      if (key === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); }
      else if (key === "y") { event.preventDefault(); redo(); }
      else if (key === "n") { event.preventDefault(); newProject(); }
      else if (key === "s") { event.preventDefault(); void (event.shiftKey ? saveProject(projectFileName(projectName), true) : saveProject()); }
      else if (key === "o") { event.preventDefault(); void openProject(); }
      else if (key === "c") { event.preventDefault(); void copySelection(); }
      else if (key === "v") { event.preventDefault(); void pasteSelection(); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  useEffect(() => {
    try { localStorage.setItem("spike.shortcuts", JSON.stringify(shortcuts)); } catch { /* Local storage may be unavailable in hardened previews. */ }
  }, [shortcuts]);
  useEffect(() => {
    const onNavigationKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing) return;
      if (shortcutsOpen) {
        if (event.key === "Escape") setShortcutsOpen(false);
        return;
      }
      if (ownsKeyboardInput(event.target)) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setViewportContext(null);
        setSelected(null);
        setStatus("Selection cleared");
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const key = normalizedShortcutKey(event.key);
      const action = (Object.keys(shortcuts) as ShortcutAction[]).find(item => shortcuts[item] === key);
      if (!action) return;
      event.preventDefault();
      if (action === "fit") commandCamera("fit");
      if (action === "zoomIn") commandCamera("zoom-in");
      if (action === "zoomOut") commandCamera("zoom-out");
      if (action === "panMode") { setNavigationMode("pan"); setStatus("Left-drag pan mode enabled"); }
      if (action === "orbitMode") { setNavigationMode("orbit"); setStatus("Left-drag orbit mode enabled"); }
      if (action === "panLeft") commandCamera("pan-left");
      if (action === "panRight") commandCamera("pan-right");
      if (action === "panUp") commandCamera("pan-up");
      if (action === "panDown") commandCamera("pan-down");
      if (action === "viewTop") { setViewMode("3D"); commandCamera("view-top"); }
      if (action === "viewBottom") { setViewMode("3D"); commandCamera("view-bottom"); }
      if (action === "viewIso") { setViewMode("3D"); commandCamera("view-iso"); }
      if (action === "toggleView") setViewMode(current => {
        const next = current === "3D" ? "2D" : "3D";
        if (next === "2D") setNavigationMode("pan");
        setStatus(`${next} board view selected`);
        return next;
      });
      if (action === "toggleRibbon") toggleRibbonVisibility();
      if (action === "layerManager") setLayersOpen(current => !current);
      if (action === "toggleNavigator") setLeftOpen(current => !current);
      if (action === "toggleAnalysisPanel") setRightOpen(current => !current);
      if (action === "toggleResultsDock") setBottomOpen(current => !current);
      if (action === "toggleModels") setShowModels(current => !current);
      if (action === "openMeshWorkspace") openSharedWorkspace("Mesh", tab === "HF / SI" ? "si" : simulationDomain);
      if (action === "openSolveWorkspace") openSharedWorkspace("Solve", tab === "HF / SI" ? "si" : simulationDomain);
      if (action === "shortcutWindow") setShortcutsOpen(true);
    };
    document.addEventListener("keydown", onNavigationKey);
    return () => document.removeEventListener("keydown", onNavigationKey);
  }, [shortcuts, shortcutsOpen]);

  const emViewportRecords = useMemo<EMViewportRecord[]>(() => resultRecords.filter(row => row.bundle.em_fields || row.bundle.em_networks).map(row => ({ id: row.id, label: row.label, result: emViewportPayload(row.bundle) })), [resultRecords]);
  const extensionWorkspace: ExtensionWorkspace | null = tab === "Mesh" ? "mesh" : tab === "HF / SI" ? "si" : tab === "EM" ? "em" : tab === "Thermal" ? "thermal" : tab === "PI" || tab === "Solve" ? simulationDomain : null;
  const workspaceExtensionRoutes = extensionWorkspace ? extensionWorkspaceRoutes(extensionCatalog, extensionWorkspace) : [];
  const workspaceExtensionRoute = workspaceExtensionRoutes.find(route => route.key === solverSelections[`extension_${extensionWorkspace}`]);
  let workspaceExtensionParameters: Record<string, unknown> | undefined;
  let workspaceExtensionInputError = "";
  try {
    if (workspaceExtensionRoute?.extensionId === "spike.emerge-suite") workspaceExtensionParameters = emergeParameters(emergeEmiSetup, gerberSource ? "gerber" : "board");
    if (workspaceExtensionRoute?.extensionId === "spike.openems-suite") workspaceExtensionParameters = openEMSParameters(workspaceOpenEMSSetup, extensionWorkspace === "pi" || extensionWorkspace === "si" ? extensionWorkspace : "em", workspaceExtensionRoute.operation === "mesh" ? "prepare" : "run");
  } catch (cause) { workspaceExtensionInputError = cause instanceof Error ? cause.message : String(cause); }
  const runExtensionWorkflow = async (extensionId: string, contributionId: string, parameters: Record<string, unknown>) => {
    const designSnapshot = extensionWorkflowDesignRef.current;
    setExtensionWorkflowBusy(true);
    try {
      await invokeExtension(extensionId, contributionId, parameters);
      if (designSnapshot.boardData !== extensionWorkflowDesignRef.current.boardData || designSnapshot.boardSource !== extensionWorkflowDesignRef.current.boardSource) {
        setExtensionMesh(null); throw new Error("The board changed during the extension job. Prepare the current board again.");
      }
    } finally { setExtensionWorkflowBusy(false); }
  };
  const configureWorkspaceExtension = (extensionId: string, contributionId: string) => {
    if (["spike.emerge-suite", "spike.openems-suite"].includes(extensionId)) { setRightOpen(true); setStatus("Configure this engine's nets, materials, mesh and ports in the workspace setup dock."); }
    else void openExtensionManager(extensionId, contributionId);
  };
  const emViewportRecord = emViewportRecords.find(row => row.id === resultDisplay) ?? (resultDisplay === "all" ? emViewportRecords[emViewportRecords.length - 1] : undefined);
  const emViewportData = useMemo(() => emViewportRecord ? buildEMViewportData(emViewportRecord, emViewportSettings) : null, [emViewportRecord, emViewportSettings]);
  const emViewportOverlay = useMemo(() => emViewportData ? { data: emViewportData, settings: emViewportSettings } : null, [emViewportData, emViewportSettings]);
  const emergePatterns = emergeRadiationPatterns(extensionResult);
  const emergeViewportPattern = tab === "EM" && boardSource && boardSource === emergeViewportBoardSource
    ? emergePatterns[emergePatternIndex] ?? null : null;
  const emergeAnalysis = (extensionResult?.data as Record<string, unknown> | undefined)?.analysis_result as Record<string, unknown> | undefined;
  const emergeProvenance = emergeAnalysis?.provenance as Record<string, unknown> | undefined;
  const emergeViewportSurrogate = String(emergeProvenance?.design_id ?? "").endsWith("-rf-two-conductor");
  const siViewportCrosstalk = (() => {
    if (tab !== "HF / SI" || !boardData || !activeDesignId || !canonicalSpiDeR
        || siChannelResult?.contract !== "spike/si-channel-result/v1" || siChannelResult.status !== "completed") return null;
    const extraction = siChannelResult.extraction as Record<string, unknown> | undefined;
    const geometry = extraction?.geometry as Record<string, unknown> | undefined;
    const provenance = siChannelResult.provenance as Record<string, unknown> | undefined;
    const resultDesignId = String(provenance?.design_id ?? geometry?.design_id ?? "");
    const sourceDesignId = resultDesignId.startsWith(`${activeDesignId}-si-crosstalk-`) ? activeDesignId : resultDesignId;
    const aggressorNetId = String(geometry?.signal_net_id ?? "");
    const victimNetId = String(geometry?.victim_net_id ?? "");
    const nets = Array.isArray(canonicalSpiDeR.nets) ? canonicalSpiDeR.nets as Record<string, unknown>[] : [];
    const aggressor = nets.find(net => net.id === aggressorNetId);
    const victim = nets.find(net => net.id === victimNetId);
    if (!aggressor || !victim || typeof aggressor.name !== "string" || typeof victim.name !== "string") return null;
    const crosstalk = siChannelResult.crosstalk as Record<string, unknown> | undefined;
    const next = crosstalk?.next as Record<string, unknown> | undefined;
    const fext = crosstalk?.fext as Record<string, unknown> | undefined;
    const loaded = (crosstalk?.loaded as Record<string, unknown> | undefined)?.time_domain as Record<string, unknown> | undefined;
    const metric = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : undefined;
    return {
      binding: { sourceDesignId, activeDesignId, aggressorNetId, victimNetId,
        boardAggressorNetId: String(aggressor.id), boardVictimNetId: String(victim.id) },
      aggressorNet: aggressor.name, victimNet: victim.name,
      nextDb: metric(next?.worst_transfer_db), fextDb: metric(fext?.worst_transfer_db),
      peakNextV: metric(loaded?.peak_abs_next_v), peakFextV: metric(loaded?.peak_abs_fext_v),
      modelStatus: String(siChannelResult.model_status ?? "experimental"), sourceLabel: "SI channel NEXT/FEXT",
    };
  })();
  const toolbarExtensions = extensionCatalog.filter(extension => extensionUiVisible(extension, "titleBar") && extension.state !== "disabled");
  const activeToolbarExtension = toolbarExtensions.find(extension => extension.id === selectedToolbarExtensionId) ?? toolbarExtensions[0];
  const toolbarContributions = activeToolbarExtension
    ? Object.entries(activeToolbarExtension.contributes).flatMap(([point, entries]) => entries.map(entry => ({ ...entry, point })))
    : [];
  const ribbonContent = (() => {
    switch (tab) {
      case "Home":
        if (desktopShell) {
          return <><ToolGroup label="PROJECT" priority="primary"><Tool icon={Boxes} label="Multi-board" active={assemblyWorkspaceOpen} disabled={!boardData} onClick={() => openAssemblyWorkspace()} /><Tool icon={Upload} label="Import" guideTarget="board-import" onClick={() => void importNativeBoard()} /><Tool icon={FolderOpen} label="Open" onClick={() => void openProject()} /><Tool icon={FileArchive} label="Manager" onClick={() => setProjectManagerOpen(true)} /><Tool icon={Save} label="Save" onClick={() => void saveProject()} /></ToolGroup><ToolGroup label="DESIGN READINESS" priority="secondary"><Tool icon={ShieldAlert} label="Validate" active onClick={validateDesign} /><Tool icon={Layers3} label="Stackup" onClick={() => setStackupOpen(true)} /><Tool icon={Activity} label="Issues" onClick={() => setDock("Issues")} /></ToolGroup><ToolGroup label="WORKSPACE" priority="tertiary"><Tool icon={Layers3} label="Layers" active={layersOpen} onClick={() => assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1 ? openBoardManager("layers") : setLayersOpen(!layersOpen)} /><Tool icon={Eye} label="3D models" active={showModels} onClick={() => setShowModels(!showModels)} /><Tool icon={PackageSearch} label="Model resolver" disabled={!boardData} onClick={() => setModelLibraryOpen(true)} /><Tool icon={Cable} label="Bonds" active={bondManagerOpen} onClick={() => setBondManagerOpen(true)} /><Tool icon={Network} label="Power tree" onClick={() => { setDock("Power tree"); setTopologyEditor("pi"); }} /></ToolGroup></>;
        }
        return <><ToolGroup label="PROJECT" priority="primary"><label className="file-picker tool" data-guide="board-import"><Upload size={18} /><span>Import</span><input type="file" accept=".kicad_pcb,.spike-design.json" onChange={importBoard} /></label><Tool icon={FolderOpen} label="Open" onClick={() => void openProject()} /><Tool icon={FileArchive} label="Manager" onClick={() => setProjectManagerOpen(true)} /><Tool icon={Save} label="Save" onClick={() => void saveProject()} /></ToolGroup><ToolGroup label="DESIGN READINESS" priority="secondary"><Tool icon={ShieldAlert} label="Validate" active onClick={validateDesign} /><Tool icon={Layers3} label="Stackup" onClick={() => setStackupOpen(true)} /><Tool icon={Activity} label="Issues" onClick={() => setDock("Issues")} /></ToolGroup><ToolGroup label="WORKSPACE" priority="tertiary"><Tool icon={Layers3} label="Layers" active={layersOpen} onClick={() => assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1 ? openBoardManager("layers") : setLayersOpen(!layersOpen)} /><Tool icon={Eye} label="3D models" active={showModels} onClick={() => setShowModels(!showModels)} /><Tool icon={Cable} label="Bonds" active={bondManagerOpen} onClick={() => setBondManagerOpen(true)} /><Tool icon={Network} label="Power tree" onClick={() => { setDock("Power tree"); setTopologyEditor("pi"); }} /></ToolGroup></>;
      case "PI":
        return <><ToolGroup label="POWER ANALYSES" priority="primary"><Tool icon={Gauge} label="DC drop" active={analysisMode === "DC IR Drop" && analysisSetupWorkflow === "single"} onClick={() => openAnalysisSetup("DC IR Drop")} /><Tool icon={Route} label="Series path" active={analysisMode === "DC IR Drop" && analysisSetupWorkflow === "path"} onClick={() => openAnalysisSetup("DC IR Drop", "path")} /><Tool icon={Network} label="Bulk nets" active={analysisMode === "Bulk Net Analysis" && analysisSetupWorkflow !== "batch"} onClick={() => openAnalysisSetup("Bulk Net Analysis")} /><Tool icon={Waves} label="AC sweep" active={analysisMode === "AC Impedance Sweep"} onClick={() => openAnalysisSetup("AC Impedance Sweep")} /><Tool icon={Waves} label="AC effects" active={acEffectsOpen} onClick={() => setAcEffectsOpen(true)} /><Tool icon={Activity} label="Transient" active={analysisMode === "Transient PI"} onClick={() => openAnalysisSetup("Transient PI")} /><Tool icon={Table2} label="Batch nets" active={analysisSetupWorkflow === "batch"} onClick={() => openAnalysisSetup("Bulk Net Analysis", "batch")} /></ToolGroup><ToolGroup label="SOURCES AND LOADS" priority="secondary"><Tool icon={ListTree} label="Net manager" active={netManagerOpen} onClick={() => openBoardManager("nets")} /><Tool icon={SlidersHorizontal} label="Terminals" onClick={() => openAnalysisSetup()} /><Tool icon={Network} label="Power paths" active={topologyEditor === "pi"} onClick={() => { setDock("Power tree"); setTopologyEditor("pi"); }} /><Tool icon={Microchip} label="SPICE models" active={spiceOpen} onClick={() => setSpiceOpen(true)} /><Tool icon={RadioTower} label="Probes" onClick={openProbeTable} /></ToolGroup><ToolGroup label="CHECK AND RUN" priority="tertiary"><Tool icon={ShieldAlert} label="Validate" onClick={validateDesign} /><Tool icon={Play} label={analysisRunning ? "Running..." : "Run PI"} onClick={runAnalysis} /><Tool icon={BarChart3} label="PI results" onClick={() => { setResultVisualizerDomain("pi"); setResultVisualizerOpen(true); }} /></ToolGroup><ToolGroup label="OUTPUT" priority="quaternary"><Tool icon={FileOutput} label="PI report" onClick={generateReport} /><Tool icon={Save} label="Save results" onClick={exportReport} /><Tool icon={FolderOpen} label="Load results" onClick={loadResults} /></ToolGroup></>;
      case "HF / SI":
        return <>
          <ToolGroup label="PROTOCOL WORKSPACES" priority="primary"><Tool icon={Boxes} label="Protocol suites" active={siProtocolSuitesOpen} onClick={() => setSiProtocolSuitesOpen(true)} /><Tool icon={Network} label="Channel tree" active={topologyEditor === "si"} onClick={() => setTopologyEditor("si")} /><Tool icon={Waves} label="Impedance" onClick={() => openSiWorkbench("geometry", "impedance")} /><Tool icon={Activity} label="Coupling risk" onClick={() => openSiWorkbench("geometry", "crosstalk")} /></ToolGroup>
          <ToolGroup label="SIGNAL ANALYSES" priority="secondary"><Tool icon={Waves} label="S-parameters" guideTarget="si-sparameters" onClick={openSelectedSParameters} /><Tool icon={Waves} label="NEXT / FEXT" onClick={() => openSiWorkbench("geometry", "crosstalk")} /><Tool icon={BarChart3} label="Eye diagram" onClick={() => openSiWorkbench("geometry", "eye")} /><Tool icon={Gauge} label="PAM4" onClick={() => openSiWorkbench("geometry", "pam4")} /></ToolGroup>
          <ToolGroup label="S-PARAMETER SOLVER" priority="tertiary"><label className="extension-ribbon-picker" data-guide="si-sparameter-solver">Solver<select aria-label="S-parameter solver" value={siSParameterSolver} onChange={event => setSiSParameterSolver(event.target.value as "internal" | "emerge")}><option value="internal">SPIKE internal</option><option value="emerge" disabled={!emergeSiAvailable}>EMerge{emergeEmiRuntime?.available === true ? ` ${String(emergeEmiRuntime.version ?? "")}` : " (unavailable)"}</option></select></label><Tool icon={Activity} label="Check EMerge" guideTarget="si-check-emerge" disabled={!emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled" || emergeEmiBusy} onClick={() => void probeEmiEmerge()} /></ToolGroup>
          <ToolGroup label="CHANNEL MODEL" priority="quaternary"><Tool icon={Layers3} label="Stackup" onClick={() => setStackupOpen(true)} /><Tool icon={Layers3} label="Layer view" onClick={() => openBoardManager("layers")} /><Tool icon={RadioTower} label="Ports" guideTarget="si-ports" onClick={() => siSParameterSolver === "emerge" && emergeSiAvailable ? openSiEmerge() : openSiWorkbench("workflow", "ports")} /></ToolGroup>
          <ToolGroup label="INTERCHANGE" priority="quaternary"><Tool icon={Upload} label="Touchstone" onClick={() => openSiWorkbench("workflow", "channel")} /><Tool icon={Puzzle} label="Suite builder" onClick={() => setSiProtocolSuitesOpen(true)} /><Tool icon={CircuitBoard} label="External engines" onClick={() => void openExternalEngineCenter()} /></ToolGroup>
        </>;
      case "Mesh":
        return <><ToolGroup label="SHARED DOMAIN" priority="primary"><Tool icon={BatteryCharging} label="PI mesh" active={simulationDomain === "pi"} onClick={() => setSimulationDomain("pi")} /><Tool icon={AudioWaveform} label="SI mesh" active={simulationDomain === "si"} onClick={() => setSimulationDomain("si")} /></ToolGroup><ToolGroup label="MESH INPUTS" priority="secondary"><Tool icon={Grid3X3} label="Mesh settings" onClick={() => simulationDomain === "pi" ? openAnalysisSetup() : openSiWorkbench("geometry", "channel")} /><Tool icon={Layers3} label="Stackup" onClick={() => setStackupOpen(true)} /><Tool icon={ListTree} label="Nets" onClick={() => simulationDomain === "pi" ? openBoardManager("nets") : openSiWorkbench("geometry", "channel")} /></ToolGroup><ToolGroup label="NEXT" priority="tertiary"><Tool icon={Play} label="Solve workspace" onClick={() => openSharedWorkspace("Solve", simulationDomain)} /></ToolGroup></>;
      case "Solve":
        return <><ToolGroup label="SHARED DOMAIN" priority="primary"><Tool icon={BatteryCharging} label="PI solve" active={simulationDomain === "pi"} onClick={() => setSimulationDomain("pi")} /><Tool icon={AudioWaveform} label="SI solve" active={simulationDomain === "si"} onClick={() => setSimulationDomain("si")} /></ToolGroup><ToolGroup label="EXECUTION" priority="secondary"><Tool icon={SlidersHorizontal} label="Review setup" onClick={() => simulationDomain === "pi" ? openAnalysisSetup() : openSiWorkbench("geometry", "channel")} /><Tool icon={Play} label={simulationDomain === "si" ? "Run SI channel" : universalRunning ? "Running..." : "Run controls"} onClick={() => simulationDomain === "pi" ? runAnalysis() : openSiWorkbench("geometry", "channel")} /><Tool icon={X} label={activeWorkerOperation?.cancelling ? "Stopping..." : "Stop"} disabled={!universalRunning || activeWorkerOperation?.cancelling} onClick={() => void cancelActiveAnalysis()} /></ToolGroup><ToolGroup label="REVIEW" priority="tertiary"><Tool icon={BarChart3} label="Results" onClick={() => { if (simulationDomain === "si") openSiWorkbench(siChannelResult?.contract === "spike/si-workflow-result/v1" ? "workflow" : "geometry", "channel"); else { setResultVisualizerDomain("pi"); setResultVisualizerOpen(true); } }} /><Tool icon={Activity} label="Console" onClick={() => setDock("Console")} /></ToolGroup></>;
      case "EM":
        return <><ToolGroup label="SCREENING" priority="primary"><Tool icon={Network} label="Net domain" active={rightOpen && emiSection === "domain"} onClick={() => { setRightOpen(true); setEmiSection("domain"); setSelectionFilter("net"); setStatus("Select candidate and return nets in the EM setup dock"); }} /><Tool icon={ShieldAlert} label="Preflight" active={Boolean(emiPreflight && !emiPreflight.counts.errors)} onClick={() => { setRightOpen(true); setEmiSection("prepass"); void validateEmi(); }} /><Tool icon={Gauge} label={emiBusy ? "Screening" : "Risk screen"} active={Boolean(emiScreening?.screening)} disabled={emiBusy} onClick={() => { setRightOpen(true); setEmiSection("prepass"); void runEmiScreening(); }} /></ToolGroup><ToolGroup label="EXCITATION" priority="secondary"><Tool icon={RadioTower} label="Ports" active={rightOpen && emiSection === "excitation"} onClick={() => { setRightOpen(true); setEmiSection("excitation"); setStatus("Configure explicit conductor-to-conductor ports in the EM setup dock"); }} /><Tool icon={Cable} label="Bonds" active={bondManagerOpen} onClick={() => setBondManagerOpen(true)} /><Tool icon={Activity} label="PI transient" onClick={() => openAnalysisSetup("Transient PI")} /><Tool icon={CircuitBoard} label="SPICE" onClick={() => setSpiceOpen(true)} /></ToolGroup><ToolGroup label="FULL-WAVE" priority="tertiary"><Tool icon={Layers3} label="Domain mesh" active={rightOpen && emiSection === "solver"} onClick={() => { setRightOpen(true); setEmiSection("solver"); setStatus("Configure frequency, boundary, and mesh controls in the EM setup dock"); }} /><Tool icon={CircuitBoard} label="Prepare case" active={Boolean(externalCase?.caseDir)} disabled={emiBusy || !boardData} onClick={() => { setRightOpen(true); setEmiSection("solver"); void prepareEmiCase(); }} /><Tool icon={Play} label="Run solver" disabled={emiBusy || !emiPreflight?.can_run || !externalCase?.canRun} onClick={() => void runExternalEngine("external.openems", false)} /><Tool icon={SatelliteDish} label="EMerge" active={emergeEmiOpen} onClick={openEmiEmerge} /><Tool icon={SlidersHorizontal} label="Solver manager" onClick={() => void openExternalEngineCenter()} /></ToolGroup><ToolGroup label="REVIEW" priority="quaternary"><Tool icon={BarChart3} label="Dashboard" active={emiDashboardOpen} disabled={!emiPreflight && !emiScreening && !emiFieldResult && !emergePatterns.length} onClick={() => { setEmiDashboardOpen(true); if (emergePatterns.length) setEmiChamberOpen(true); }} /><Tool icon={Waves} label="Near field" disabled onClick={() => setStatus("Near-field visualization requires a completed compatible field result")} /><Tool icon={RadioTower} label="Far field" active={Boolean(emiFieldResult?.far_field || emergePatterns.length)} disabled={!emiFieldResult?.far_field && !emergePatterns.length} onClick={() => { setEmiDashboardOpen(true); if (emergePatterns.length) { setEmiChamberOpen(true); setStatus("Showing the EMerge radiation pattern in EM"); } else setStatus("Showing the completed openEMS NF2FF radiation result"); }} /><Tool icon={FileOutput} label="EMI report" onClick={generateReport} /></ToolGroup></>;
      case "Thermal":
        return <><ToolGroup label="SIMULATION DOMAIN" priority="primary"><Tool icon={Thermometer} label="Bounding volume" onClick={() => setThermalOpen(true)} /><Tool icon={Layers3} label="Board stack" onClick={() => setStackupOpen(true)} /><Tool icon={Activity} label="Heat sources" onClick={() => setThermalOpen(true)} /><Tool icon={Cable} label="Bonds" active={bondManagerOpen} onClick={() => setBondManagerOpen(true)} /></ToolGroup><ToolGroup label="AIRFLOW" priority="secondary"><Tool icon={Wind} label="Flow channels" onClick={() => setThermalOpen(true)} /><Tool icon={Fan} label="Fan placement" onClick={() => setThermalOpen(true)} /><Tool icon={Gauge} label="Ambient" onClick={() => setThermalOpen(true)} /></ToolGroup><ToolGroup label="OPTIONAL CFD" priority="tertiary"><Tool icon={SlidersHorizontal} label="Scenario" onClick={() => setThermalOpen(true)} /><Tool icon={Play} label="Prepare case" onClick={() => setThermalOpen(true)} /><Tool icon={Activity} label="Solver console" onClick={() => setDock("Console")} /></ToolGroup><ToolGroup label="THERMAL RESULTS" priority="quaternary"><Tool icon={BarChart3} label="Temperature" onClick={() => setThermalOpen(true)} /><Tool icon={FileOutput} label="Report" onClick={generateReport} /></ToolGroup></>;
      case "Probes":
        return <><ToolGroup label="PROBE TOOLS" priority="primary"><Tool icon={ScanSearch} label="Hover probe" active={probeMode === "hover"} onClick={() => setProbeMode(current => { const next = current === "hover" ? "off" : "hover"; setStatus(next === "hover" ? "Hover probe active: move across the board for live measurements" : "Hover probe disabled"); return next; })} /><Tool icon={RadioTower} label="Place probe" onClick={() => addProbe(selected)} /><Tool icon={Table2} label="Probe table" active={dock === "Probe table"} onClick={openProbeTable} /><Tool icon={Copy} label="Duplicate" onClick={() => selected ? addProbe({ ...selected, id: `${selected.id}-copy`, name: `${selected.name} copy` }) : setStatus("Select a probe location before duplicating")} /></ToolGroup><ToolGroup label="MEASUREMENTS" priority="secondary"><Tool icon={Gauge} label="Voltage" onClick={() => { setProbeKind("voltage"); setStatus("Voltage probe measurement selected"); }} /><Tool icon={Activity} label="Current" onClick={() => { setProbeKind("current"); setStatus("Current-density probe measurement selected"); }} /><Tool icon={Waves} label="Impedance" onClick={() => { setProbeKind("impedance"); setStatus("Impedance hover requires an AC or parasitic result"); }} /></ToolGroup><ToolGroup label="COMPARE AND EXPORT" priority="tertiary"><Tool icon={BarChart3} label="Compare" onClick={openProbeTable} /><Tool icon={Layers3} label="Cross-layer" onClick={() => openBoardManager("layers")} /><Tool icon={FileOutput} label="Export CSV" onClick={exportProbeCsv} /></ToolGroup></>;
      case "Results":
        return <><ToolGroup label="RESULT VIEWS" priority="primary"><Tool icon={ShieldAlert} label="Issues" active={dock === "Issues"} onClick={() => setDock("Issues")} /><Tool icon={Table2} label="Probe table" active={dock === "Probe table"} onClick={openProbeTable} /><Tool icon={Network} label="Power tree" active={dock === "Power tree"} onClick={() => setDock("Power tree")} /><Tool icon={Activity} label="Console" active={dock === "Console"} onClick={() => setDock("Console")} /></ToolGroup><ToolGroup label="VISUALIZATION" priority="secondary"><Tool icon={Eye} label="Fields" active={resultVisualizerOpen} onClick={() => setResultVisualizerOpen(true)} /><Tool icon={BarChart3} label="Voltage / current" onClick={() => setResultVisualizerOpen(true)} /><Tool icon={Layers3} label="Mesh" onClick={() => setResultVisualizerOpen(true)} /><Tool icon={RadioTower} label="Probe overlay" onClick={openProbeTable} /></ToolGroup><ToolGroup label="REVISION REVIEW" priority="tertiary"><Tool icon={Copy} label="Compare" onClick={() => comparisonInputRef.current?.click()} /><Tool icon={ShieldAlert} label="Limits" onClick={() => setRightOpen(true)} /><Tool icon={FileOutput} label="Report" onClick={generateReport} /></ToolGroup></>;
      case "Reports":
        return <><ToolGroup label="REPORT" priority="primary"><Tool icon={BookOpen} label="Preview" onClick={generateReport} /><Tool icon={FileOutput} label="Print / PDF" onClick={() => { generateReport(); setStatus("Report preview ready; choose Print for printer or PDF output"); }} /><Tool icon={BarChart3} label="Analytics" onClick={generateReport} /></ToolGroup><ToolGroup label="DATA EXPORT" priority="secondary"><Tool icon={Table2} label="Probe CSV" onClick={exportProbeCsv} /><Tool icon={Waves} label="Touchstone" onClick={() => openSiWorkbench("workflow", "channel")} /><Tool icon={CircuitBoard} label="SPICE" onClick={() => setSpiceOpen(true)} /></ToolGroup><ToolGroup label="CAD AND PACKAGE" priority="tertiary"><Tool icon={CircuitBoard} label="STEP" onClick={() => void exportStep()} /><Tool icon={Save} label="Save results" onClick={exportReport} /><Tool icon={FolderOpen} label="Load results" onClick={loadResults} /><Tool icon={Copy} label="Save instance" onClick={saveInstance} /></ToolGroup></>;
      case "Extensions":
        return <><ToolGroup label="BROWSE" priority="primary"><Tool icon={Puzzle} label="Extension manager" onClick={() => void openExtensionManager()} /><Tool icon={Activity} label="Refresh" onClick={() => void openExtensionManager()} /></ToolGroup>
          <ToolGroup label="SELECT EXTENSION" priority="secondary"><label className="extension-ribbon-picker">Extension<select aria-label="Select extension toolbar" value={activeToolbarExtension?.id ?? ""} onChange={event => setSelectedToolbarExtensionId(event.target.value)}>{toolbarExtensions.length ? toolbarExtensions.map(extension => <option key={extension.id} value={extension.id}>{extension.name}</option>) : <option value="">No extensions available</option>}</select></label>{activeToolbarExtension && <Tool icon={Settings2} label="Manage" onClick={() => void openExtensionManager(activeToolbarExtension.id)} />}</ToolGroup>
          <ToolGroup label="AVAILABLE CAPABILITIES" priority="tertiary">{activeToolbarExtension ? toolbarContributions.slice(0, 8).map(entry => <Tool key={`${entry.point}-${entry.id}`} icon={entry.point === "analyses" ? Waves : entry.point === "reports" ? FileOutput : Puzzle} label={entry.name} disabled={!activeToolbarExtension.trusted} onClick={() => void openExtensionManager(activeToolbarExtension.id, entry.id)} />) : <small>Browse and install an extension to show its tools here.</small>}</ToolGroup>
          {toolbarContributions.length > 8 && <ToolGroup label="MORE" priority="quaternary"><Tool icon={ListTree} label={`${toolbarContributions.length - 8} more capabilities`} onClick={() => void openExtensionManager(activeToolbarExtension?.id)} /></ToolGroup>}
        </>;
      case "Settings":
        return <><ToolGroup label="APPLICATION" priority="primary"><Tool icon={Settings2} label="Settings" onClick={() => setPreferencesOpen(true)} /><Tool icon={SquareTerminal} label="Python" active={pythonOpen} onClick={() => setPythonOpen(true)} /><Tool icon={Network} label="Extensions" onClick={() => void openExtensionManager()} /><Tool icon={CircuitBoard} label="External engines" onClick={() => void openExternalEngineCenter()} /><Tool icon={SlidersHorizontal} label="Dependencies" onClick={() => void checkDependencies()} /><Tool icon={Gauge} label="Verification" onClick={() => setBenchmarkOpen(true)} /></ToolGroup><ToolGroup label="LOCAL AUTOMATION" priority="secondary"><Tool icon={ServerCog} label="LLM / MCP" active={mcpBridgePanelOpen} disabled={!desktopShell} onClick={() => setMcpBridgePanelOpen(true)} /></ToolGroup><ToolGroup label="DESIGN LIBRARIES" priority="secondary"><Tool icon={Layers3} label="Stackup" onClick={() => setStackupOpen(true)} /><Tool icon={BookOpen} label="3D library" onClick={() => setModelLibraryOpen(true)} /><Tool icon={Eye} label="Models" active={showModels} onClick={() => setShowModels(!showModels)} /></ToolGroup><ToolGroup label="INTERFACE" priority="tertiary"><Tool icon={Keyboard} label="Shortcuts" onClick={() => setShortcutsOpen(true)} /><Tool icon={GalleryVertical} label="Icon gallery" onClick={() => setIconGalleryOpen(true)} /><Tool icon={Activity} label="Resources" onClick={() => setResourceOpen(true)} /><Tool icon={BookOpen} label="User guide" onClick={() => setHelpOpen(true)} /></ToolGroup></>;
    }
  })();

  const universalSearchItems: UniversalSearchItem[] = [
    ...tabs.map(({ name, icon }) => ({
      id: `workspace:${name}`,
      label: `${name} workspace`,
      category: "Workspace",
      description: `Open the ${name} command ribbon and workflow`,
      keywords: `tab ribbon ${name}${name === "EM" ? " electromagnetics radiation emi emc" : ""}`,
      icon,
      run: () => { setTab(name); setStatus(`${name} workspace selected from universal search`); },
    })),
    { id: "project:new", label: "New project", category: "Project", description: "Create an empty SPIKE project", icon: FilePlus, run: newProject },
    { id: "project:open", label: "Open file or project", category: "Project", description: "Open SPIKE projects, boards, ODB++, harness connections or MCAD models", keywords: "load recall file", icon: FolderOpen, run: () => void openProject() },
    { id: "project:save", label: "Save project", category: "Project", description: "Save the current project package", icon: Save, run: () => void saveProject() },
    { id: "project:manager", label: "Project manager", category: "Project", description: "Browse recent projects and project metadata", icon: FileArchive, run: () => setProjectManagerOpen(true) },
    { id: "analysis:dc", label: "DC voltage-drop analysis", category: "PI analysis", description: "Configure sources, loads, return path, mesh, and DC solver", keywords: "dcir ir drop", icon: BatteryCharging, run: () => { setAnalysisMode("DC IR Drop"); setAnalysisSetupWorkflow("single"); openSharedWorkspace("Mesh", "pi"); } },
    { id: "analysis:ac", label: "AC impedance sweep", category: "PI analysis", description: "Configure frequency-dependent PEEC impedance extraction", keywords: "acir skin effect rlc pdn", icon: ChartSpline, run: () => { setAnalysisMode("AC Impedance Sweep"); openSharedWorkspace("Mesh", "pi"); } },
    { id: "analysis:transient", label: "Transient PI analysis", category: "PI analysis", description: "Configure pulse, step, PWL, timing, and transient output controls", keywords: "time pulse step spice", icon: AudioWaveform, run: () => { setAnalysisMode("Transient PI"); openSharedWorkspace("Mesh", "pi"); } },
    { id: "analysis:batch", label: "Batch net analysis", category: "PI analysis", description: "Assign DC, AC, or skip independently to managed nets", keywords: "multiple nets", icon: TableProperties, run: () => { setAnalysisMode("Bulk Net Analysis"); setAnalysisSetupWorkflow("batch"); openSharedWorkspace("Mesh", "pi"); } },
    { id: "analysis:run", label: "Run active PI analysis", category: "PI analysis", description: "Validate and execute the current PI request", icon: Play, disabled: !boardData || analysisRunning, run: () => void runAnalysis() },
    { id: "analysis:validate", label: "Validate design", category: "Analysis", description: "Run import, stackup, geometry, and setup checks", icon: ShieldCheck, run: validateDesign },
    { id: "manager:assembly", label: "Multi-board workspace", category: "Design", description: "Import and duplicate boards, edit connector links, harnesses and coupled studies", keywords: "assembly stack shields multiboard", icon: Boxes, disabled: !boardData, run: () => openAssemblyWorkspace() },
    { id: "manager:nets", label: "Net manager", category: "Design", description: "Manage linked nets, path groups, and loop extraction endpoints", icon: ListTree, disabled: !boardData, run: () => openBoardManager("nets") },
    { id: "manager:power-tree", label: "Power-path workbench", category: "Design", description: "Edit component-level source-to-load topology and models", keywords: "power tree ptree topology", icon: ChartNetwork, disabled: !boardData, run: () => { setTab("PI"); setDock("Power tree"); setTopologyEditor("pi"); } },
    { id: "manager:bonds", label: "Component bond manager", category: "Design", description: "Review electrical and thermal pad-to-copper contacts", keywords: "solder conduction connection", icon: Cable, disabled: !boardData, run: () => setBondManagerOpen(true) },
    { id: "manager:stackup", label: "Stackup manager", category: "Design", description: "Edit copper, dielectric, core, prepreg, and material properties", icon: Layers3, disabled: !boardData, run: () => setStackupOpen(true) },
    { id: "manager:layers", label: "Layer manager", category: "View", description: "Control layer visibility, opacity, models, vias, and separation", icon: Layers2, disabled: !boardData, run: () => openBoardManager("layers") },
    { id: "manager:models", label: "3D model library", category: "Design", description: "Browse and assign local STEP, WRL, and glTF models", keywords: "component package", icon: LibraryBig, disabled: !boardData, run: () => setModelLibraryOpen(true) },
    { id: "analysis:spice", label: "SPICE model assistant", category: "Simulation", description: "Assign models, pins, ratings, and explicit circuit netlists", keywords: "ngspice circuit", icon: CircuitBoard, run: () => setSpiceOpen(true) },
    { id: "analysis:sparameter", label: "S-parameter workbench", category: "HF / SI", description: "Run the selected S-parameter solver or inspect Touchstone data", keywords: "touchstone port emerge", icon: Waves, run: () => { setTab("HF / SI"); openSelectedSParameters(); } },
    { id: "analysis:emi", label: "EM workspace setup", category: "EM", description: "Configure domains, ports, preflight, full-wave case, and dashboard", keywords: "emi emc electromagnetics openems far field lisn", icon: SatelliteDish, run: () => { setTab("EM"); setRightOpen(true); setEmiSection("domain"); } },
    { id: "analysis:thermal", label: "Thermal and airflow setup", category: "Thermal", description: "Configure environment, volume, heat sources, fans, and flow channels", keywords: "openfoam temperature", icon: ThermometerSun, run: () => { setTab("Thermal"); setThermalOpen(true); } },
    { id: "results:viewer", label: "Analysis result viewer", category: "Results", description: "Review voltage, current, density, mesh, loss, probes, and impedance", icon: ChartArea, run: () => { setTab("Results"); setResultVisualizerOpen(true); } },
    { id: "results:report", label: "Preview engineering report", category: "Reports", description: "Generate the traceable interactive report preview", keywords: "pdf print html analytics", icon: FileChartColumn, run: generateReport },
    { id: "view:2d", label: "Switch to 2D layout", category: "View", description: "Use the planar layout viewport and pan controls", icon: MapPinPlus, run: () => { setViewMode("2D"); setNavigationMode("pan"); } },
    { id: "view:3d", label: "Switch to 3D board view", category: "View", description: "Use the native Three.js board scene", icon: Cuboid, run: () => setViewMode("3D") },
    { id: "view:fit", label: "Fit board to viewport", category: "View", description: "Frame the active board or analysis geometry", keywords: "zoom all", icon: Focus, run: () => commandCamera("fit") },
    { id: "view:ribbon", label: appSettings.ribbonVisible ? "Minimize command ribbon" : "Expand command ribbon", category: "View", description: "Minimize ribbon options while keeping all workspace tabs visible", icon: PanelTop, run: toggleRibbonVisibility },
    { id: "view:navigator", label: leftOpen ? "Hide design navigator" : "Show design navigator", category: "View", icon: PanelLeft, run: () => setLeftOpen(current => !current) },
    { id: "view:analysis", label: rightOpen ? "Hide analysis setup" : "Show analysis setup", category: "View", icon: PanelRight, run: () => setRightOpen(current => !current) },
    { id: "view:console", label: "Open application console", category: "View", description: "Show commands, warnings, errors, and operation status", icon: SquareTerminal, run: () => { setBottomOpen(true); setDock("Console"); } },
    { id: "settings:general", label: "Application settings", category: "Settings", description: "Configure interface, units, language, rendering, and resources", keywords: "preferences ram memory locale", icon: Settings2, run: () => setPreferencesOpen(true) },
    { id: "tools:python", label: "Python workspace", category: "Tools", description: "Edit and run Python scripts in the desktop worker", keywords: "script automation ide", icon: SquareTerminal, run: () => setPythonOpen(true) },
    { id: "settings:shortcuts", label: "Keyboard shortcuts", category: "Settings", description: "Review and customize viewport and application bindings", icon: Keyboard, run: () => setShortcutsOpen(true) },
    { id: "settings:resources", label: "Resource monitor", category: "Settings", description: "Inspect CPU, memory, rendering, and capacity information", icon: MemoryStick, run: () => setResourceOpen(true) },
    { id: "settings:engines", label: "Solver manager", category: "Settings", description: "Configure available internal and external solvers", keywords: "openems openfoam ngspice", icon: ServerCog, run: () => void openExternalEngineCenter() },
    { id: "settings:extensions", label: "Extension manager", category: "Settings", description: "Inspect and run trusted SPIKE extensions", keywords: "plugins modules", icon: Puzzle, run: () => void openExtensionManager() },
    { id: "help:guide", label: "Help and user guide", category: "Help", description: "Search workflows, validity rules, diagnostics, and error codes", icon: CircleHelp, run: () => setHelpOpen(true) },
    ...(globalSearchOpen && boardData ? [
      ...Array.from(new Set(Object.values(boardData.nets))).filter(Boolean).map(net => ({
        id: `net:${net}`, label: net, category: "Net", description: "Select this complete electrical net for analysis", keywords: "copper power signal return", icon: Route,
        run: () => { setTab("PI"); setSelectionFilter("net"); selectNetForAnalysis(net, "analysis"); },
      })),
      ...boardData.components.map(component => ({
        id: `component:${component.id}`, label: component.ref, category: "Component", description: `${component.value || "Unspecified value"} · ${component.layer}`, keywords: component.value, icon: Microchip,
        run: () => handleSelect({ id: component.id, type: "component", name: component.ref, ref: component.ref, layer: component.layer, position: component.at, model: Boolean(component.model) }),
      })),
      ...boardData.pads.map(pad => ({
        id: `pad:${pad.id}`, label: `${pad.ref ?? "?"}.${pad.name}`, category: "Pad", description: `${pad.net ?? "No net"} · ${pad.layers.join(" / ") || pad.layer}`, keywords: `${pad.ref ?? ""} ${pad.net ?? ""} ${pad.layer}`, icon: Crosshair,
        run: () => handleSelect({ id: pad.id, type: "pad", name: `${pad.ref ?? "?"}.${pad.name}`, ref: pad.ref, net: pad.net, layer: pad.layer, layers: pad.layers, position: pad.at }),
      })),
      ...boardData.vias.map(via => ({
        id: `via:${via.id}`, label: via.id, category: "Via", description: `${via.net ?? "No net"} · ${via.layers.join(" / ")}`, keywords: `${via.net ?? ""} plated drill`, icon: Combine,
        run: () => handleSelect({ id: via.id, type: "via", name: via.id, net: via.net, layer: "through", layers: via.layers, position: via.at }),
      })),
      ...layerEntries.map(layer => ({
        id: `layer:${layer}`, label: layer, category: "Layer", description: "Show this layer and open its visibility controls", keywords: "stackup copper mask silkscreen", icon: Layers3,
        run: () => { showOnlyLayer(layer); openBoardManager("layers"); setStatus(`${layer} shown from universal search`); },
      })),
    ] : []),
  ];

  const shellStyle = {
    "--left-panel-width": `${leftPanelWidth}px`,
    "--right-panel-width": `${rightPanelWidth}px`,
    "--bottom-panel-height": `${bottomPanelHeight}px`,
  } as CSSProperties;

  const modelNotice = modelLoadStatus.board === "loading" || modelLoadStatus.components === "loading" || modelLoadStatus.assembly === "loading"
    ? { level: "loading", title: "Loading verified 3D models", detail: "Resolved KiCad and attached MCAD assets load asynchronously; the viewport remains interactive." }
    : modelLoadStatus.board === "failed" || modelLoadStatus.components === "failed" || modelLoadStatus.assembly === "failed"
      ? { level: "error", title: "3D model scene incomplete", detail: `${modelLoadStatus.error ? `${modelLoadStatus.error.slice(0, 1000)} ` : "One or more KiCad or attached MCAD model scenes could not be loaded. "}Placeholder models are approximate, not source-accurate geometry.` }
      : modelLoadStatus.missingCount > 0
        ? { level: "warning", title: `${modelLoadStatus.missingCount} unresolved 3D model assignment${modelLoadStatus.missingCount === 1 ? "" : "s"}`, detail: `${modelLoadStatus.missingRefs.slice(0, 4).join(", ")}${modelLoadStatus.missingRefs.length > 4 ? ` and ${modelLoadStatus.missingRefs.length - 4} more` : ""}` }
        : null;

  const boardDisplayDiagnostics = virtualBoardProjection.visuals.length > 1
    ? virtualBoardProjection.visuals.map(board => ({ name: board.name, designId: board.designId, modelsAvailable: Boolean(assemblyBoardVisuals.boards[board.designId]), detail: assemblyBoardVisuals.diagnostics[board.designId] ?? (assemblyBoardVisuals.boards[board.designId] ? "Imported layout geometry loaded." : "Loading retained board source.") }))
    : [];
  const boardDisplaySummary = boardDisplayDiagnostics.length
    ? `${virtualBoardProjection.visuals.filter(board => assemblyBoardVisuals.boards[board.designId]).length}/${boardDisplayDiagnostics.length} board layouts loaded`
    : undefined;
  const retryViewportModels = () => { setStatus("Retrying authoritative 3D model scenes"); window.dispatchEvent(new Event("spike-retry-model-scene")); };
  const openNotificationModels = (designId?: string) => {
    setModelResolverTarget({ designId: designId ?? assemblyDesigns?.active_design_id ?? activeDesignId ?? "active", componentRef: designId ? undefined : modelLoadStatus.missingRefs[0] });
    setModelLibraryOpen(true);
  };
  const importReviewCount = (boardImport.progress?.warnings.length ?? 0) + (boardImport.progress?.problems.length ?? 0);


  const siWorkspace = tab === "HF / SI" || ((tab === "Mesh" || tab === "Solve") && simulationDomain === "si");
  const emergeSiAnalysis = analysisResult?.mode === "si" && String((analysisResult.provenance as Record<string, unknown> | undefined)?.solver ?? "").startsWith("EMerge/") ? analysisResult : null;
  const emergeSiPanelResult = emergeSiAnalysis ? { status: "completed", title: "EMerge SI port sweep", data: { analysis_result: emergeSiAnalysis } } : null;
  useEffect(() => {
    if (tab === "HF / SI") setSimulationDomain("si");
    if (tab === "PI") setSimulationDomain("pi");
  }, [tab]);

  const assemblyToolRevision = useMemo(() => crypto.randomUUID(), [projectPath, projectManifestDigest, assemblyIr]);
  const selectAssemblyMoveMode = (mode: "translate" | "rotate") => {
    if (assemblyToolDraftOwner) { setStatus(`Finish or discard the assembly ${assemblyToolDraftOwner} draft before moving a board.`); return; }
    setAssemblySnapMode("off"); setAssemblyExplodedDistanceMm(0);
    setAssemblyMoveMode(current => current === mode ? null : mode);
    setViewMode("3D");
  };
  const assemblyToolSnapshot = useMemo<AssemblyToolSnapshot>(() => ({
    revision: assemblyToolRevision, assembly: assemblyIr, designs: assemblyDesigns,
    // Tool windows need readiness and diagnostics, not GPU buffers or source SVGs.
    visuals: Object.fromEntries(Object.entries(assemblyBoardVisuals.boards).map(([id, board]) => [id, { boardModelUrl: board.boardModelUrl, componentModelUrl: board.componentModelUrl }])),
    diagnostics: assemblyBoardVisuals.diagnostics, projectPath, manifestDigest: projectManifestDigest, projectDirty,
    desktop: desktopShell, boardAvailable: Boolean(boardData), selectedBoardId: selectedBoardInstanceId,
    visibility: assemblyBoardVisibility,
    layerVisibility: Object.fromEntries(virtualBoardProjection.visuals.map(board => [board.id, assemblyLayerVisibility[board.id] ?? visibleLayers])),
    layerOpacity: Object.fromEntries(virtualBoardProjection.visuals.map(board => [board.id, assemblyLayerOpacity[board.id] ?? layerOpacity])),
    explodedDistanceMm: assemblyExplodedDistanceMm, moveMode: assemblyMoveMode, snapMode: assemblySnapMode, snapGapMm: assemblySnapGapMm,
    snapSourceLabel: assemblySnapSource ? `${assemblySnapSource.occurrenceId}: ${assemblySnapSource.sourceId}` : undefined,
    passThroughHighlight, overlayMessages: [...assemblyOverlayState.diagnostics, ...assemblyOverlayState.overlays.map(row => `${row.boardOccurrenceId}: ${row.metrics.map(metric => `${metric.name}: ${metric.value?.toPrecision(5) ?? "channel"} ${metric.unit ?? ""}`).join("; ")} (occurrence summary, not a spatial field)`) ],
    managerTab: assemblyLinksOpen ? "links" : netManagerOpen ? "nets" : "layers",
    draftOwner: assemblyToolDraftOwner,
  }), [assemblyToolRevision, assemblyIr, assemblyDesigns, assemblyBoardVisuals.boards, assemblyBoardVisuals.diagnostics, projectPath, projectManifestDigest, projectDirty, desktopShell, boardData, selectedBoardInstanceId, assemblyBoardVisibility, virtualBoardProjection.visuals, assemblyLayerVisibility, visibleLayers, assemblyLayerOpacity, layerOpacity, assemblyExplodedDistanceMm, assemblyMoveMode, assemblySnapMode, assemblySnapGapMm, assemblySnapSource, passThroughHighlight, assemblyOverlayState, assemblyLinksOpen, netManagerOpen, assemblyToolDraftOwner]);
  const assemblyToolAction = async (kind: AssemblyToolKind, action: AssemblyToolAction) => {
    if (assemblyToolDraftOwner && (action.type === "placement" || action.type === "move-mode" || ((action.type === "save" || action.type === "reload" || action.type === "update-assembly") && assemblyToolDraftOwner !== kind))) throw new Error(`Finish or discard the assembly ${assemblyToolDraftOwner} draft first.`);
    const boardId = action.boardId;
    if (boardId && !virtualBoardProjection.visuals.some(board => board.id === boardId)) throw new Error("The selected board is no longer in this assembly.");
    switch (action.type) {
      case "draft-dirty": setAssemblyToolDraftOwner(current => action.value === true ? kind : current === kind ? null : current); return;
      case "save": return saveProject();
      case "reload": if (projectPath) await loadNativeProjectFromApprovedPath(projectPath, projectName); return;
      case "status": setStatus(String(action.value ?? "")); return;
      case "collaboration": if (action.mode === "freecad") setFreecadCollaborationOpen(true); else if (action.mode === "attachments") setMcadAttachmentOpen(true); return;
      case "select-board": { const board = virtualBoardProjection.visuals.find(board => board.id === boardId); if (board) handleBoardInstanceSelect(board); return; }
      case "view": { const board = virtualBoardProjection.visuals.find(board => board.id === boardId); if (board) handleBoardInstanceSelect(board); setViewMode(action.mode === "2D" ? "2D" : "3D"); setBottomOpen(false); commandCamera("fit"); return; }
      case "manager": setSelectedBoardInstanceId(boardId ?? null); if (action.mode === "layers" || action.mode === "nets" || action.mode === "links") openBoardManager(action.mode); return;
      case "visibility": if (boardId) { recordChange(); setAssemblyBoardVisibility(current => ({ ...current, [boardId]: action.value === true })); } return;
      case "placement": if (boardId && action.transform) commitAssemblyBoardPlacement(boardId, action.transform); return;
      case "move-mode": if (action.mode === "translate" || action.mode === "rotate") selectAssemblyMoveMode(action.mode); return;
      case "explode": if (typeof action.value === "number" && action.value >= 0) { recordChange(); setAssemblyMoveMode(null); setAssemblyExplodedDistanceMm(action.value); } return;
      case "snap-gap": if (typeof action.value === "number" && action.value >= 0) setAssemblySnapGapMm(action.value); return;
      case "snap-mode": if (action.mode === "off" || action.mode === "hole" || action.mode === "edge") { setAssemblyMoveMode(null); setAssemblySnapMode(action.mode); if (action.mode !== "off") setAssemblyExplodedDistanceMm(0); setStatus(action.mode === "off" ? "Assembly alignment snap off" : `Click a ${action.mode} on the moving board, then a ${action.mode} on the target board`); } return;
      case "pass-through": setPassThroughHighlight(action.value === true); return;
      case "export-diagram": await exportAssemblyDiagram(); return;
      case "load-overlay": await loadAssemblyOverlayStudy(); return;
      case "layer-visibility": if (boardId && action.layer) { const layer = action.layer; recordChange(); setAssemblyLayerVisibility(current => ({ ...current, [boardId]: { ...(current[boardId] ?? visibleLayers), [layer]: action.value === true } })); } return;
      case "layer-opacity": if (boardId && action.layer && typeof action.value === "number" && action.value >= 0 && action.value <= 1) { const layer = action.layer, value = action.value; recordChange(); setAssemblyLayerOpacity(current => ({ ...current, [boardId]: { ...(current[boardId] ?? layerOpacity), [layer]: value } })); } return;
      case "layer-state": if (boardId && action.layerVisibility) {
        recordChange(); const visibility = action.layerVisibility, opacity = action.layerOpacity;
        setAssemblyLayerVisibility(current => ({ ...current, [boardId]: { ...(current[boardId] ?? visibleLayers), ...visibility } }));
        if (opacity) setAssemblyLayerOpacity(current => ({ ...current, [boardId]: { ...(current[boardId] ?? layerOpacity), ...opacity } }));
      } return;
      case "select-net": if (boardId && action.netId) { setSelectedBoardInstanceId(boardId); await handleAssemblyNetSelect(boardId, action.netId); } return;
      case "update-assembly": if (action.assembly && assemblyIr && action.assembly.assembly_id === assemblyIr.assembly_id) { recordChange(); linkedSelectionGeneration.current += 1; setAssemblyIr(action.assembly); setLinkedAssemblyNets({}); } return;
    }
  };

  const openNotificationDock = () => { setDock("Notifications"); setBottomOpen(true); };
  const notificationCount = Number(Boolean(modelNotice)) + Number(boardDisplayDiagnostics.length > 0 || harnessProjection.diagnostics.length > 0) + Number(importReviewCount > 0);
  const notificationProps = {
    notice: modelNotice, metrics: modelLoadStatus.metrics, boards: boardDisplayDiagnostics,
    harnessDiagnostics: harnessProjection.diagnostics.map(issue => issue.message), open: notificationsOpen,
    onToggle: () => toggleBottomDock("Notifications"), onClose: () => setBottomOpen(false),
    onRetry: retryViewportModels, canResolveModels: resolverBoards.length > 0, onResolveModels: openNotificationModels,
    importReview: importReviewCount ? { label: boardImport.progress!.label, issueCount: importReviewCount } : undefined,
    onReviewImport: openNotificationDock,
    onReviewLinks: () => { setLayersOpen(false); setNetManagerOpen(false); openBoardManager("links"); },
    onReviewIssues: () => { setDock("Issues"); setBottomOpen(true); },
  };
  const viewportSetupAction = siWorkspace ? <button className="resolve-setup-button" onClick={() => openSiWorkbench("geometry", "channel")} title="Configure SI channel geometry and run settings"><SlidersHorizontal size={14} /> <span>Configure SI</span></button>
              : tab === "EM" ? <button className="resolve-setup-button" onClick={() => { setRightOpen(true); setEmiSection("solver"); }} title="Configure EM excitation and solver"><SlidersHorizontal size={14} /> <span>Configure EM</span></button>
              : tab === "Thermal" ? <button className="resolve-setup-button" onClick={() => setThermalOpen(true)} title="Configure thermal analysis"><SlidersHorizontal size={14} /> <span>Thermal setup</span></button>
              : <button className="resolve-setup-button" onClick={resolveSimulationSetup} title="Resolve net, terminals, return path, solver selection, and mesh defaults"><ShieldAlert size={14} /> <span>Resolve setup</span></button>;
  const toolRestoreItems: ToolRestoreItem[] = [];
  const detachedToolLabels: Record<ToolWindowKind, string> = { results: "Results window", probes: "Probe window", "trace-plots": "Trace plots" };
  (Object.keys(detachedToolLabels) as ToolWindowKind[]).forEach(kind => {
    if (!detachedTools[kind]) return;
    toolRestoreItems.push({
      id: `detached-${kind}`,
      label: detachedToolLabels[kind],
      restore: () => detachTool(kind, true),
      close: async () => { await closeDetachedToolWindow(kind); setDetachedTools(current => ({ ...current, [kind]: false })); },
    });
  });
  const restoreAssemblyWindow = async (kind: AssemblyToolKind) => {
    if (!await focusAssemblyToolWindow(kind)) throw new Error("Window is no longer open");
  };
  const pythonContext = useMemo(() => pythonWorkspaceContext(canonicalSpiDeR ?? designForExchange(), assemblyIr, assemblyDesigns, selectedBoardInstanceId), [canonicalSpiDeR, boardData, boardFile, activeDesignId, assemblyIr, assemblyDesigns, selectedBoardInstanceId, componentBonds]);
  const handlePythonUiAction = (candidate: PythonUiAction) => {
    const action = admittedPythonUiActions([candidate], pythonContext)[0];
    if (action.action === "select_net") {
      if (assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1) handleAssemblyNetSelect(action.board_id, String(action.net_id));
      else { const net = pythonBoardNets(pythonContext).find(net => net.boardId === action.board_id && net.id === action.net_id); if (net) focusManagedNet(net.name); }
    } else if (action.action === "focus_board") { setSelectedBoardInstanceId(assemblyIr ? action.board_id : null); setSelected(null); requestAnimationFrame(() => commandCamera(assemblyIr && assemblyIr.boards.length > 1 ? "focus-selection" : "fit")); }
    else if (action.panel === "layers" || action.panel === "nets") openBoardManager(action.panel);
    else if (action.panel === "connector_links") openBoardManager("links");
    else if (action.panel === "issues") setDock("Issues");
    else { setResultVisualizerOpen(true); }
  };
  if (assemblyWorkspaceOpen) toolRestoreItems.push({ id: "assembly-workspace-window", label: "Multi-board window", restore: () => restoreAssemblyWindow("workspace") });
  if (assemblyHandlingExpanded) toolRestoreItems.push({ id: "assembly-placement-window", label: "Board placement window", restore: () => restoreAssemblyWindow("placement") });
  if (assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1 && (layersOpen || netManagerOpen || assemblyLinksOpen)) {
    toolRestoreItems.push({ id: "assembly-managers-window", label: "Board managers window", restore: () => restoreAssemblyWindow("managers") });
  }
  if (reportPreview) toolRestoreItems.push({
    id: "report-preview-window", label: "Report preview",
    restore: async () => { if (!await focusReportPreviewWindow()) throw new Error("Report preview is no longer open. Generate the report again"); },
    close: async () => { await closeReportPreviewWindow(); setReportPreview(null); },
  });
  const notificationWorkspaceTools = <div className="notification-workspace-tools">
            {tab === "Probes" && <div className="probe-mode-bar" aria-label="Probe placement mode">
              <select value={probeKind} onChange={event => setProbeKind(event.target.value as NonNullable<BoardObject["probeKind"]>)} title="Probe measurement type" aria-label="Probe measurement type">
                <option value="universal">Universal V/I/P/Z</option>
                <option value="voltage">Voltage</option>
                <option value="current">Current</option>
                <option value="power">Power</option>
                <option value="impedance">Impedance</option>
              </select>
              <button className={probeMode === "hover" ? "selected" : ""} onClick={() => setProbeMode(current => current === "hover" ? "off" : "hover")} title="Measure the nearest available solved values continuously under the cursor"><ScanSearch size={14} /> Hover probe</button>
              <button className={probeMode === "temporary" ? "selected" : ""} onClick={() => setProbeMode(current => current === "temporary" ? "off" : "temporary")} title="Click to measure one location; the next click replaces it"><Crosshair size={14} /> Click measure</button>
              <button className={probeMode === "bulk" ? "selected" : ""} onClick={() => setProbeMode(current => current === "bulk" ? "off" : "bulk")} title="Place persistent probes at multiple board locations"><MapPinPlus size={14} /> Place many</button>
              <button className={showProbes ? "selected" : ""} onClick={() => setShowProbes(current => !current)} title={showProbes ? "Hide probe markers" : "Show probe markers"}>{showProbes ? <Eye size={14} /> : <EyeOff size={14} />}</button>
              <button onClick={() => setProbes([])} title="Clear all probes"><Trash2 size={14} /></button>
            </div>}
            {tab === "Thermal" && (thermalPreview || thermalScenario) && <div className="thermal-scene-bar" aria-label="Thermal scene visibility">
              <button className={thermalVisibility.field ? "selected" : ""} onClick={() => setThermalVisibility(current => ({ ...current, field: !current.field }))} title="Show saved board thermal cells for temperature probing"><Thermometer size={14} /> Field</button>
              {Boolean(thermalScenario?.board_thermal_result) && <button onClick={() => setThermalOpen(true)} title="Open saved board temperature grids and X/Y/Z cuts"><BarChart3 size={14} /> Plots</button>}
              <button onClick={() => void openSavedBoardThermal()} title="Load a source-bound board thermal view bundle"><FolderOpen size={14} /> Open saved</button>
              <button className={thermalVisibility.volume ? "selected" : ""} onClick={() => setThermalVisibility(current => ({ ...current, volume: !current.volume }))} title="Show thermal bounding volume"><Box size={14} /> Domain</button>
              <button className={thermalVisibility.heatSources ? "selected" : ""} onClick={() => setThermalVisibility(current => ({ ...current, heatSources: !current.heatSources }))} title="Show heat source regions"><Flame size={14} /> Sources</button>
              <button className={thermalVisibility.airflow ? "selected" : ""} onClick={() => setThermalVisibility(current => ({ ...current, airflow: !current.airflow }))} title="Show airflow paths"><Wind size={14} /> Airflow</button>
              <button className={thermalVisibility.hardware ? "selected" : ""} onClick={() => setThermalVisibility(current => ({ ...current, hardware: !current.hardware }))} title="Show fans, openings, and virtual heatsinks"><Fan size={14} /> Hardware</button>
              <button onClick={() => setThermalVisibility(current => {
                const anyVisible = Object.values(current).some(Boolean);
                return { volume: !anyVisible, heatSources: !anyVisible, airflow: !anyVisible, hardware: !anyVisible, field: !anyVisible };
              })} title="Show or hide the complete thermal scene">{Object.values(thermalVisibility).some(Boolean) ? <EyeOff size={14} /> : <Eye size={14} />}</button>
            </div>}
            {tab === "Thermal" && boardData && !thermalPreview && !thermalScenario && <div className="thermal-scene-bar" aria-label="Saved thermal result controls"><button onClick={() => void openSavedBoardThermal()} title="Load a source-bound board thermal view bundle"><FolderOpen size={14} /> Open saved thermal</button></div>}
            <input ref={savedBoardThermalInputRef} type="file" accept=".json" style={{ display: "none" }} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void file.text().then(text => showSavedBoardThermal(JSON.parse(text))).catch(error => setStatus(String(error))); }} />
            {tab === "EM" && <div className="emi-viewport-bar" aria-label="EM viewport controls">
              {emergeViewportPattern && <button className={!emiChamberOpen ? "selected" : ""} onClick={() => { setEmiChamberOpen(false); setViewMode("3D"); }} title="Rotate and probe the radiation pattern beside the source board"><CircuitBoard size={14} /> Board + pattern</button>}
              {emergeViewportPattern && emergePatterns.length > 1 && <label className="setup-sublabel">Frequency <select className="select-control" aria-label="Board radiation frequency" value={emergePatternIndex} onChange={event => setEmergePatternIndex(Number(event.target.value))}>{emergePatterns.map((pattern, index) => <option value={index} key={`${pattern.frequency_hz}-${index}`}>{(pattern.frequency_hz / 1e9).toFixed(3)} GHz</option>)}</select></label>}
              <button className={emiChamberOpen ? "selected" : ""} onClick={() => setEmiChamberOpen(true)}>Chamber</button>
              <button onClick={openEmiEmerge} title="Configure EMerge SI and radiation analysis"><SatelliteDish size={14} /> EMerge</button>
              <button className={emiSetup.viewport.translucent_board ? "selected" : ""} onClick={() => setEmiSetup(current => ({ ...current, viewport: { ...current.viewport, translucent_board: !current.viewport.translucent_board } }))} title="Keep the board and component models visible as a translucent spatial reference"><Blend size={14} /> Translucent</button>
              <button className={emiSetup.viewport.analysis_nets_only ? "selected" : ""} onClick={() => setEmiSetup(current => ({ ...current, viewport: { ...current.viewport, analysis_nets_only: !current.viewport.analysis_nets_only } }))} title="Show only EMI candidate and return nets"><RouteOff size={14} /> Nets only</button>
              <button onClick={() => void validateEmi()} disabled={emiBusy}><ClipboardCheck size={14} /> Preflight</button>
              <button onClick={() => void runEmiScreening()} disabled={emiBusy}><Radar size={14} /> Screen</button>
            </div>}
          </div>;

  return <div className={`app-shell ${bottomOpen ? "bottom-open" : "bottom-closed"} ${appSettings.ribbonVisible ? "ribbon-visible" : "ribbon-hidden"}`} style={shellStyle}>
    <header className="topbar"><div className="brand-mark"><img src="/spike-mark.svg" alt="SPIKE" /><div><b>SPIKE</b><small>ELECTRONIC SYSTEMS INTEGRITY WORKBENCH</small></div></div><button className="project-path" onClick={() => setProjectManagerOpen(true)} title={`Open project manager: ${projectName}`}><span>Project</span><b>{projectName}</b><ChevronDown size={15} /></button><div className="top-actions"><button className={`icon-btn universal-search-trigger ${globalSearchOpen ? "active" : ""}`} title="Universal search (Ctrl+K)" aria-label="Open universal search" aria-keyshortcuts="Control+K Meta+K" aria-expanded={globalSearchOpen} onClick={() => { setMenu(null); setGlobalSearchOpen(true); }}><Search size={17} /><span>Search</span><kbd>Ctrl K</kbd></button><ViewportNotifications {...notificationProps} mode="button" /><button className="icon-btn" title="Help and user guide" onClick={() => setHelpOpen(true)}><CircleHelp size={17} /></button><button className="avatar" title={appSettings.profile.displayName} onClick={() => setPreferencesOpen(true)}>{appSettings.profile.initials}</button></div></header>
    <nav className="menu-bar" aria-label="Application menu">
      <MenuButton label={tr("File")} open={menu === "File"} onClick={() => setMenu(menu === "File" ? null : "File")}>
        <MenuItem icon={FilePlus} label="New project" shortcut="Ctrl+N" onClick={() => { newProject(); setMenu(null); }} />
        <MenuItem icon={FileArchive} label="Project manager" onClick={() => { setProjectManagerOpen(true); setMenu(null); }} />
        <MenuItem icon={ListTree} label="Simulation studies" onClick={() => { setStudyManagerOpen(true); setMenu(null); }} />
        <MenuItem icon={FolderOpen} label="Open file or project" shortcut="Ctrl+O" onClick={() => { void openProject(); setMenu(null); }} />
        <MenuItem icon={Save} label="Save project" shortcut="Ctrl+S" onClick={() => { void saveProject(); setMenu(null); }} />
        <MenuItem icon={Save} label="Save as" shortcut="Ctrl+Shift+S" onClick={() => { void saveProject(projectFileName(projectName), true); setMenu(null); }} />
        <MenuItem icon={Save} label="Save project copy without results" onClick={() => { saveProjectWithoutResults(); setMenu(null); }} />
        <MenuItem icon={Save} label="Save results file" onClick={() => { void exportReport(); setMenu(null); }} />
        <MenuItem icon={FolderOpen} label="Open results file" onClick={() => { loadResults(); setMenu(null); }} />
        <MenuItem icon={Upload} label="Import project / CAD" onClick={() => { void importNativeBoard(); setMenu(null); }} />
        <MenuItem icon={Upload} label="Import ODB++ archive" onClick={() => { void importOdbBoard(); setMenu(null); }} />
        <MenuItem icon={FolderOpen} label="Import ODB++ folder" onClick={() => { void importOdbBoard(true); setMenu(null); }} />
        <MenuItem icon={Copy} label="Save instance" onClick={() => { saveInstance(); setMenu(null); }} />
        <MenuItem icon={FileOutput} label="Preview report" onClick={() => { generateReport(); setMenu(null); }} />
        <MenuItem icon={CircuitBoard} label="Export STEP" onClick={() => { void exportStep(); setMenu(null); }} />
      </MenuButton>
      <MenuButton label={tr("Edit")} open={menu === "Edit"} onClick={() => setMenu(menu === "Edit" ? null : "Edit")}>
        <MenuItem icon={Undo2} label="Undo" shortcut="Ctrl+Z" onClick={() => { undo(); setMenu(null); }} />
        <MenuItem icon={Redo2} label="Redo" shortcut="Ctrl+Y" onClick={() => { redo(); setMenu(null); }} />
        <MenuItem icon={Copy} label="Copy context" shortcut="Ctrl+C" onClick={() => { void copySelection(); setMenu(null); }} />
        <MenuItem icon={Clipboard} label="Paste context" shortcut="Ctrl+V" onClick={() => { void pasteSelection(); setMenu(null); }} />
      </MenuButton>
      <MenuButton label={tr("View")} open={menu === "View"} onClick={() => setMenu(menu === "View" ? null : "View")}>
        <MenuItem icon={PanelTop} label={appSettings.ribbonVisible ? "Minimize command ribbon" : "Expand command ribbon"} shortcut={shortcuts.toggleRibbon} onClick={toggleRibbonVisibility} />
        <MenuItem icon={Layers3} label="Layer manager" onClick={() => { openBoardManager("layers"); setMenu(null); }} />
        <MenuItem icon={Spline} label="Flex PCB manager" onClick={() => { setFlexBoardOpen(true); setMenu(null); }} />
        <MenuItem icon={Eye} label="3D board view" onClick={() => { setViewMode("3D"); setMenu(null); }} />
        <MenuItem icon={Route} label={showNetNames ? "Hide net names" : "Show net names"} onClick={() => { recordChange(); setShowNetNames(!showNetNames); setMenu(null); }} />
        <MenuItem icon={EyeOff} label="2D layout view" onClick={() => { setViewMode("2D"); setMenu(null); }} />
        <MenuItem icon={PanelLeft} label="Design navigator" onClick={() => { setLeftOpen(current => !current); setMenu(null); }} />
        <MenuItem icon={PanelRight} label="Analysis panel" onClick={() => { setRightOpen(current => !current); setMenu(null); }} />
        <MenuItem icon={PanelBottom} label="Results and console" onClick={() => { setBottomOpen(current => !current); setMenu(null); }} />
      </MenuButton>
      <MenuButton label="Analysis" open={menu === "Analysis"} onClick={() => setMenu(menu === "Analysis" ? null : "Analysis")}>
        <MenuItem icon={Gauge} label="DC PI setup" onClick={() => { openAnalysisSetup("DC IR Drop"); setMenu(null); }} />
        <MenuItem icon={Waves} label="AC impedance setup" onClick={() => { openAnalysisSetup("AC Impedance Sweep"); setMenu(null); }} />
        <MenuItem icon={Activity} label="Transient PI setup" onClick={() => { openAnalysisSetup("Transient PI"); setMenu(null); }} />
        <MenuItem icon={RadioTower} label="EM workspace" onClick={() => { setTab("EM"); setRightOpen(true); setMenu(null); }} />
        <MenuItem icon={CircuitBoard} label="SPICE workbench" onClick={() => { setSpiceOpen(true); setMenu(null); }} />
        <MenuItem icon={BarChart3} label="Result visualization" onClick={() => { setResultVisualizerOpen(true); setMenu(null); }} />
      </MenuButton>
      <MenuButton label={tr("Reports")} open={menu === "Reports"} onClick={() => setMenu(menu === "Reports" ? null : "Reports")}>
        <MenuItem icon={BookOpen} label="Engineering report preview" onClick={() => { generateReport(); setMenu(null); }} />
        <MenuItem icon={FileOutput} label="Print or export report" onClick={() => { generateReport(); setStatus("Report preview ready; choose Print or Export HTML"); setMenu(null); }} />
        <MenuItem icon={Table2} label="Export probe table" onClick={() => { exportProbeCsv(); setMenu(null); }} />
      </MenuButton>
      <MenuButton label={tr("Project")} open={menu === "Project"} onClick={() => setMenu(menu === "Project" ? null : "Project")}>
        <MenuItem icon={Boxes} label="Multi-board workspace" onClick={() => { openAssemblyWorkspace(); setMenu(null); }} />
        <MenuItem icon={ShieldAlert} label="Validate design" onClick={() => { validateDesign(); setMenu(null); }} />
        <MenuItem icon={Network} label="Power tree" onClick={() => { setTopologyEditor("pi"); setMenu(null); }} />
        <MenuItem icon={Settings2} label="Project and application settings" onClick={() => { setPreferencesOpen(true); setMenu(null); }} />
      </MenuButton>
      <MenuButton label="Tools" open={menu === "Tools"} onClick={() => setMenu(menu === "Tools" ? null : "Tools")}>
        <MenuItem icon={SquareTerminal} label="Python workspace" onClick={() => { setPythonOpen(true); setMenu(null); }} />
        <MenuItem icon={Gauge} label="Solver verification" onClick={() => { setBenchmarkOpen(true); setMenu(null); }} />
        <MenuItem icon={ShieldAlert} label="Dependency status" onClick={() => { void checkDependencies(); setMenu(null); }} />
        <MenuItem icon={Keyboard} label="Shortcut manager" onClick={() => { setShortcutsOpen(true); setMenu(null); }} />
      </MenuButton>
      <MenuButton label="Extensions" open={menu === "Extensions"} onClick={() => setMenu(menu === "Extensions" ? null : "Extensions")}>
        <MenuItem icon={Puzzle} label="Browse and manage extensions" onClick={() => { void openExtensionManager(); setMenu(null); }} />
        {extensionCatalog.filter(extension => extensionUiVisible(extension, "menuBar") && extension.state !== "disabled").map(extension => <MenuItem key={extension.id} icon={Puzzle} label={`${extension.name}${extension.trusted ? "" : " · trust required"}`} onClick={() => { void openExtensionManager(extension.id); setMenu(null); }} />)}
      </MenuButton>
      <MenuButton label={tr("Help")} open={menu === "Help"} onClick={() => setMenu(menu === "Help" ? null : "Help")}>
        <MenuItem icon={BookOpen} label="Help and user guide" onClick={() => { setHelpOpen(true); setMenu(null); }} />
        <MenuItem icon={Focus} label="Interactive analysis guide" onClick={() => { setGuideOpen(true); setMenu(null); }} />
        <MenuItem icon={Gauge} label="Accuracy and validation" onClick={() => { setBenchmarkOpen(true); setMenu(null); }} />
        <MenuItem icon={BadgeAlert} label="Report bug" onClick={() => { setMenu(null); void openBugReport(tab).catch(() => setStatus("Could not open the bug report. Visit github.com/wayri/SPIKE-Main/issues/new")); }} />
        <MenuItem icon={CircleHelp} label="About SPIKE" onClick={() => { setAboutOpen(true); setMenu(null); }} />
      </MenuButton>
    </nav>
    <>
      <CommandStrip className="ribbon-tabs" label="Analysis tools" as="nav" trailing={<button className="ribbon-tab ribbon-toggle" onClick={toggleRibbonVisibility} aria-expanded={appSettings.ribbonVisible} aria-controls="workspace-ribbon-tools" title={appSettings.ribbonVisible ? "Minimize command ribbon" : "Expand command ribbon"}><PanelTop size={16} />{appSettings.ribbonVisible ? "Minimize" : "Expand"}</button>}>{tabs.map(({ name, icon: Icon }) => <button key={name} data-guide={name === "PI" ? "pi-run" : name === "HF / SI" ? "si-setup" : name === "EM" ? "emi-setup" : name === "Thermal" ? "thermal-setup" : name === "Results" ? "results" : undefined} className={tab === name ? "ribbon-tab selected" : "ribbon-tab"} title={name === "EM" ? "Electromagnetics workspace" : undefined} onClick={() => { setTab(name); setStatus(`${name} workspace selected`); }}><Icon size={16} />{name}</button>)}</CommandStrip>
      {appSettings.ribbonVisible && <CommandStrip id="workspace-ribbon-tools" label="Ribbon" className={`ribbon-tools ribbon-${tab.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
        <BoardViewRibbon
          viewMode={viewMode}
          modelsVisible={showModels && resultVisualization.showComponentModels}
          translucent={tab === "EM" ? emiSetup.viewport.translucent_board : resultVisualization.sceneMode === "translucent"}
          onViewMode={mode => { setViewMode(mode); if (mode === "2D") setNavigationMode("pan"); }}
          onLayers={() => openBoardManager("layers")}
          onFit={() => commandCamera("fit")}
          onCamera={commandCamera}
          onToggleModels={() => {
            const visible = !(showModels && resultVisualization.showComponentModels);
            setShowModels(visible);
            setResultVisualization(current => ({ ...current, showComponentModels: visible }));
            setStatus(`${visible ? "Showing" : "Hiding"} all 3D component models`);
          }}
          onToggleTranslucent={() => {
            const translucent = tab === "EM" ? !emiSetup.viewport.translucent_board : resultVisualization.sceneMode !== "translucent";
            setResultVisualization(current => ({
              ...current,
              visible: true,
              sceneMode: translucent ? "translucent" : "opaque",
              translucentScene: translucent,
            }));
            setEmiSetup(current => ({
              ...current,
              viewport: { ...current.viewport, translucent_board: translucent },
            }));
            setStatus(translucent ? "Translucent board view enabled" : "Opaque board view restored");
          }}
        />
        {ribbonContent}
        <div className={`ribbon-status ${workerAvailable ? "" : "preview"}`}><span className="status-dot" /> {workerHealth === "ready" ? "Desktop worker ready" : workerHealth === "starting" ? "Checking desktop worker" : workerHealth === "degraded" ? "Desktop worker unavailable" : "Preview only - desktop worker required"}<small>spike/v1</small></div>
      </CommandStrip>}
    </>
    {universalRunning && <>
      <div className="global-progress" role="progressbar" aria-label={operationDisplay?.label ?? status} aria-valuetext={operationDisplay ? `${formatRunDuration(operationDisplay.elapsedSeconds)} elapsed${operationDisplay.estimateSeconds ? `, estimated ${formatRunDuration(operationDisplay.estimateSeconds)}` : ""}` : undefined}><span /></div>
    </>}

    <main className={`workspace ${leftOpen ? "left-open" : "left-closed"} ${rightOpen ? "right-open" : "right-closed"}`}>
      <aside className={leftOpen ? "side-panel left" : "side-panel left collapsed"}>
        <div className="panel-heading"><button className="panel-title-toggle" onClick={() => setLeftOpen(current => !current)} aria-expanded={leftOpen} title={leftOpen ? "Collapse scene navigator" : "Expand scene navigator"}>SCENE NAVIGATOR</button><button onClick={() => setLeftOpen(current => !current)} className="collapse-btn" title={leftOpen ? "Collapse scene navigator" : "Expand scene navigator"} aria-label={leftOpen ? "Collapse scene navigator" : "Expand scene navigator"}>{leftOpen ? <PanelLeft size={15} /> : <PanelRight size={17} />}</button></div>
        {leftOpen && <SceneNavigator
          onObjectContext={setViewportContext}
          board={boardData}
          boardName={boardFile}
          query={searchQuery}
          onQuery={setSearchQuery}
          probes={probes}
          modelAssignments={modelAssignments}
          assemblyIr={assemblyIr}
          modelIndex={modelIndex}
          assemblyPartViewportStates={assemblyPartViewportStates}
          bondCount={componentBonds.length}
          sourceCount={piSetup.sources.length + piSetup.loads.length}
          powerPathCount={compilePiPaths(piTopology).length}
          resultCount={resultRecords.length + (analysisResult ? 1 : 0)}
          thermalScenario={thermalPreview ?? thermalScenario}
          importQuality={importQuality}
          onSelect={handleSelect}
          onAssemblyPart={partId => { setMcadFocusedPartId(partId); setMcadAttachmentOpen(true); setStatus("Opening the selected AssemblyIR part in the hierarchy editor"); }}
          onAction={handleSceneNavigatorAction}
        />}
      </aside>

      <section className="canvas-area">
        <CommandStrip className="canvas-toolbar" label="Viewport">
          <div className="view-toggle"><button className={viewMode === "2D" ? "selected" : ""} onClick={() => { setViewMode("2D"); setNavigationMode("pan"); }}>2D</button><button className={viewMode === "3D" ? "selected" : ""} onClick={() => setViewMode("3D")}>3D</button></div>
          <span className="divider" />
          <div className="selection-filter" aria-label="Selection filter">
            <button className={selectionFilter === "all" ? "selected" : ""} onClick={() => changeSelectionFilter("all")} title="Select components or electrical geometry"><MousePointer2 size={14} /><span>All</span></button>
            <button className={selectionFilter === "part" ? "selected" : ""} onClick={() => changeSelectionFilter("part")} title="Select components only"><Component size={14} /><span>Part</span></button>
            <button className={selectionFilter === "net" ? "selected" : ""} onClick={() => changeSelectionFilter("net")} title="Select complete electrical nets through traces, zones, pads, or vias"><Route size={14} /><span>Net</span></button>
          </div>
          <span className="divider" />
          <button className="plain-btn" onClick={() => openBoardManager("layers")} title="Open layer visibility and stack controls"><GalleryVertical size={15} /> Layers</button>
          <button className="plain-btn" title={`Fit board (${shortcuts.fit})`} onClick={() => commandCamera("fit")}><Focus size={15} /> Fit</button>
          <button className="plain-btn" disabled={(!selected && !(viewMode === "2D" && selectedBoardInstanceId)) || (tab === "EM" && emiChamberOpen)} title="Center and zoom to the selected board object" onClick={() => commandCamera("focus-selection")}><Crosshair size={15} /> Focus selected</button>
          {selected?.net && <button className={`plain-btn ${isolatedNet ? "active" : ""}`} onClick={() => { recordChange(); setIsolatedNet(isolatedNet ? null : selected.net ?? null); setStatus(isolatedNet ? "Complete board restored" : `${selected.net} isolated across all copper layers`); }}><RouteOff size={15} /> {isolatedNet ? "Exit isolate" : "Isolate net"}</button>}
          <span className="canvas-spacer" />
          <select className="camera-view-select" aria-label="Camera view" title="Select a board viewing side" defaultValue="" disabled={viewMode === "2D"} onChange={event => { commandCamera(`view-${event.currentTarget.value}`); event.currentTarget.value = ""; }}><option value="" disabled>VIEW</option><option value="top">Top</option><option value="bottom">Bottom</option><option value="front">Front</option><option value="back">Back</option><option value="left">Left</option><option value="right">Right</option><option value="iso">Isometric</option></select>
          <div className="navigation-mode" aria-label="Pointer navigation mode">
            <button className={`canvas-icon ${navigationMode === "orbit" ? "active" : ""}`} title={`Orbit with left drag (${shortcuts.orbitMode})`} disabled={viewMode === "2D"} onClick={() => setNavigationMode("orbit")}><Orbit size={15} /></button>
            <button className={`canvas-icon ${navigationMode === "pan" ? "active" : ""}`} title={`Pan with left drag (${shortcuts.panMode})`} onClick={() => setNavigationMode("pan")}><Hand size={15} /></button>
            <button className={`canvas-icon ${navigationInertia ? "active" : ""}`} title={navigationInertia ? "Disable camera inertia" : "Enable camera inertia"} onClick={() => setNavigationInertia(current => !current)}><Move3D size={15} /></button>
            <button className={`canvas-icon ${showAxes ? "active" : ""}`} title={showAxes ? "Hide measurement axes and background grid" : "Show measurement axes and background grid"} onClick={() => setShowAxes(current => !current)}><Axis3D size={15} /></button>
          </div>
          <div className="pan-pad" aria-label="Pan view">
            <button className="canvas-icon pan-up" title={`Pan up (${shortcuts.panUp})`} onClick={() => commandCamera("pan-up")}><ArrowUp size={13} /></button>
            <button className="canvas-icon pan-left" title={`Pan left (${shortcuts.panLeft})`} onClick={() => commandCamera("pan-left")}><ArrowLeft size={13} /></button>
            <button className="canvas-icon pan-right" title={`Pan right (${shortcuts.panRight})`} onClick={() => commandCamera("pan-right")}><ArrowRight size={13} /></button>
            <button className="canvas-icon pan-down" title={`Pan down (${shortcuts.panDown})`} onClick={() => commandCamera("pan-down")}><ArrowDown size={13} /></button>
          </div>
          <button className="canvas-icon" title={`Zoom in (${shortcuts.zoomIn})`} onClick={() => commandCamera("zoom-in")}><ZoomIn size={15} /></button>
          <button className="canvas-icon" title={`Zoom out (${shortcuts.zoomOut})`} onClick={() => commandCamera("zoom-out")}><ZoomOut size={15} /></button>
          <button className="canvas-icon" title={`Return to isometric view (${shortcuts.viewIso})`} disabled={viewMode === "2D"} onClick={() => commandCamera("view-iso")}><Axis3D size={15} /></button>
          <button className="canvas-icon" title={`Keyboard shortcuts (${shortcuts.shortcutWindow})`} onClick={() => setShortcutsOpen(true)}><Keyboard size={15} /></button>
          {emViewportRecords.length > 0 && <button className={`canvas-icon ${emResultManagerOpen ? "active" : ""}`} title="EM results manager: PCB/assembly overlays and linked graphs" onClick={() => { setEmResultManagerOpen(value => !value); setEmiChamberOpen(false); setViewMode("3D"); }}><RadioTower size={15} /></button>}
          <button className={`canvas-icon ${resultVisualization.mode !== "geometry" ? "active" : ""}`} title="Analysis visualization" onClick={() => { setResultVisualizerDomain(tab === "HF / SI" || tab === "EM" ? "si" : "pi"); setResultVisualizerOpen(true); }}><LayoutDashboard size={15} /></button>
          {(analysisResult?.time_series.frames.length ?? 0) > 1 && <button className={`canvas-icon ${resultVisualization.animationPlaying ? "active" : ""}`} title={resultVisualization.animationPlaying ? "Pause result animation" : "Animate transient result"} onClick={() => setResultVisualization(current => ({ ...current, animationPlaying: !current.animationPlaying }))}>{resultVisualization.animationPlaying ? <Pause size={15} /> : <Play size={15} />}</button>}
          <span className="divider" />
          <div className="workspace-dock-controls" aria-label="Workspace dock controls">
            <button className={`canvas-icon ${leftOpen ? "active" : ""}`} title="Toggle design navigator" onClick={() => setLeftOpen(!leftOpen)}><PanelLeft size={15} /></button>
            <button className={`canvas-icon ${bottomOpen ? "active" : ""}`} title="Toggle bottom results dock" onClick={() => setBottomOpen(!bottomOpen)}><PanelBottom size={15} /></button>
            <button className={`canvas-icon ${rightOpen ? "active" : ""}`} title="Toggle analysis setup" onClick={() => setRightOpen(!rightOpen)}><PanelRight size={15} /></button>
            <button className={`canvas-icon ${sidePanelsPinned && bottomPinned ? "active" : ""}`} title={sidePanelsPinned && bottomPinned ? "Unpin docks for auto-hide" : "Pin all workspace docks"} onClick={() => { const next = !(sidePanelsPinned && bottomPinned); setSidePanelsPinned(next); setBottomPinned(next); if (next) { setLeftOpen(true); setRightOpen(true); setBottomOpen(true); } }}>{sidePanelsPinned && bottomPinned ? <Pin size={14} /> : <PinOff size={14} />}</button>
          </div>
          {boardData?.technology && boardData.technology !== "rigid" && <button className="board-technology" onClick={() => setFlexBoardOpen(true)} title="Review flex regions and bend definitions">{boardData.technology === "rigid-flex" ? "RIGID-FLEX" : "FLEX"}</button>}
          <span className="coordinate">{isolatedNet ? `ISOLATED · ${isolatedNet}` : selected ? `${selected.type.toUpperCase()} · ${selected.name}` : navigationMode.toUpperCase()}</span>
        </CommandStrip>
        <CommandStrip className="result-mode-toolbar contextual" label="Contextual viewport">
          <span title={`Viewport context: ${contextualToolbarLabel}`}>{contextualToolbarLabel}</span>
          <button onClick={() => openAssemblyWorkspace()} title="Import boards, connect pins and configure coupled assembly studies"><Boxes size={14} /> Multi-board</button>
          {assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1 && <button onClick={() => openBoardManager("links")} title="Link explicit connector pins between board occurrences"><Cable size={14} /> Connector links</button>}
          {hasStoredResults && <select className="result-filter" value={resultDisplay} onChange={event => { const value = event.target.value; setResultDisplay(value); if (value === "none") setResultVisualization(current => ({ ...current, sceneMode: current.sceneMode === "results_only" ? "opaque" : current.sceneMode })); setStatus(value === "all" ? "Showing all solved batch nets" : value === "none" ? "Result overlays hidden" : `Showing ${resultRecords.find(record => record.id === value)?.label ?? "selected result"}`); }} title="Choose all, one, or no solved results" aria-label="Displayed analysis result">
            <option value="none">No result</option>
            {resultRecords.length > 1 && <option value="all">All results</option>}
            {resultRecords.map(record => <option key={record.id} value={record.id}>{record.label}</option>)}
          </select>}

          {!activeAnalysisResult && boardData && tab === "PI" && <div className="viewport-context-group" aria-label="PI setup commands">
            <button onClick={() => openAnalysisSetup()} title={`Configure ${analysisMode}`}><SlidersHorizontal size={14} /> Configure</button>
            {!(assemblyIr && assemblyIr.boards.length > 1) && <label className="assembly-highlight-mode"><input type="checkbox" checked={passThroughHighlight} onChange={event => setPassThroughHighlight(event.target.checked)}/> Part branches</label>}
            <button onClick={() => openBoardManager("nets")} title="Manage single-net, linked-net, and batch analysis domains"><ListTree size={14} /> Nets</button>
            {(selected?.net || piSetup.net) && <button className="extract" onClick={() => runParasitics(resultVisualization.viaModel)} disabled={analysisRunning} title="Extract R/L/C/G and Z(f) for the active net"><Cpu size={14} /> Extract RLC</button>}
            <button onClick={runAnalysis} disabled={analysisRunning} title={`Open ${analysisMode} preflight and run controls`}><Play size={14} /> {analysisRunning ? "Running" : "Run"}</button>
          </div>}
          {!activeAnalysisResult && boardData && tab === "HF / SI" && <div className="viewport-context-group" aria-label="SI extraction commands">
            {(selected?.net || piSetup.net) && <button className="extract" onClick={() => runParasitics(resultVisualization.viaModel)} disabled={analysisRunning} title="Extract the selected net's R/L/C/G and Z(f)"><Cpu size={14} /> Extract RLC</button>}
            <button onClick={openSelectedSParameters} title="Open the selected S-parameter solver"><Waves size={14} /> S-parameters</button>
            <button onClick={() => setStackupOpen(true)} title="Inspect dielectric and conductor stackup inputs"><Layers3 size={14} /> Stackup</button>
          </div>}
          {!activeAnalysisResult && boardData && tab === "Thermal" && <div className="viewport-context-group" aria-label="Thermal setup commands">
            <button onClick={() => setThermalOpen(true)} title="Configure thermal domain, materials, heat sources, airflow, and solver"><ThermometerSun size={14} /> Thermal setup</button>
            <button onClick={() => setBondManagerOpen(true)} title="Configure electrical and thermal component bonds"><Cable size={14} /> Bonds</button>
          </div>}
          {!activeAnalysisResult && boardData && tab === "EM" && <div className="viewport-context-group" aria-label="EM setup commands">
            <button onClick={() => { setRightOpen(true); setEmiSection("domain"); }} title="Configure candidate nets, return paths, and the EMI domain"><SatelliteDish size={14} /> Domain</button>
            <button onClick={() => { setRightOpen(true); setEmiSection("excitation"); }} title="Configure field-solver ports and excitation"><RadioTower size={14} /> Ports</button>
            <button onClick={() => void validateEmi()} disabled={emiBusy} title="Run EMI setup preflight"><ShieldAlert size={14} /> Preflight</button>
          </div>}
          {!activeAnalysisResult && boardData && selected && <div className="viewport-context-group selection-actions" aria-label="Selection commands">
            <button onClick={() => addProbe(selected)} title={`Add a ${probeKind} probe at ${selected.name}`}><MapPinPlus size={14} /> Probe</button>
            {selected.net && <button className={isolatedNet === selected.net ? "selected" : ""} onClick={() => { recordChange(); setIsolatedNet(isolatedNet === selected.net ? null : selected.net ?? null); }} title="Show only the complete selected net across connected layers"><RouteOff size={14} /> Isolate</button>}
          </div>}

          {activeAnalysisResult && <div className="viewport-context-group result-fields" aria-label="Available result fields">
            <button className={resultVisualization.mode === "geometry" ? "selected" : ""} onClick={() => selectViewportResult("geometry")} title="Show native board geometry without a result overlay"><Layers3 size={14} /> Geometry</button>
            {availableResultModes.has("voltage") && <button className={resultVisualization.mode === "voltage" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("voltage")} title="Show absolute voltage on the solved conductor"><Zap size={14} /> Voltage</button>}
            {availableResultModes.has("voltage_drop") && <button className={resultVisualization.mode === "voltage_drop" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("voltage_drop")} title="Show voltage drop relative to the configured source"><TrendingDown size={14} /> Drop</button>}
            {availableResultModes.has("current") && <button className={resultVisualization.mode === "current" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("current")} title="Show solved conductor current"><ArrowRightLeft size={14} /> Current</button>}
            {availableResultModes.has("current_density") && <button className={resultVisualization.mode === "current_density" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("current_density")} title="Show current density and direction vectors"><ChartNoAxesColumnIncreasing size={14} /> Density</button>}
            {availableResultModes.has("power_loss") && <button className={resultVisualization.mode === "power_loss" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("power_loss")} title="Show spatial copper power loss"><Flame size={14} /> Loss</button>}
            {availableResultModes.has("via_stress") && <button className={resultVisualization.mode === "via_stress" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("via_stress")} title="Show via current-density stress"><BadgeAlert size={14} /> Via stress</button>}
            {availableResultModes.has("impedance") && <button className={resultVisualization.mode === "impedance" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("impedance")} title="Show solved DC operating-point impedance as |V/I|"><Omega size={14} /> Impedance</button>}
            {availableResultModes.has("mesh") && <button className={resultVisualization.mode === "mesh" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("mesh")} title="Show the solver mesh used for this result"><Grid3X3 size={14} /> Mesh</button>}
            {availableResultModes.has("electric_field") && <button className={resultVisualization.mode === "electric_field" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("electric_field")} title="Show solved electric-field vectors"><Zap size={14} /> E field</button>}
            {availableResultModes.has("magnetic_field") && <button className={resultVisualization.mode === "magnetic_field" && resultVisualization.visible ? "selected" : ""} onClick={() => selectViewportResult("magnetic_field")} title="Show solved magnetic-field vectors"><Magnet size={14} /> H field</button>}
            {hasExtractedNetworks && <button className={resultVisualization.mode === "impedance" && resultVisualizerOpen ? "selected" : ""} onClick={openParasiticWorkbench} title="Inspect resistance, partial inductance, capacitance availability, and Z(f)"><Component size={14} /> RLC</button>}
          </div>}
          <span className="result-toolbar-spacer" />
          {activeAnalysisResult && <div className="viewport-context-group result-display" aria-label="Result display commands">
            <button className={resultVisualization.visible ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, visible: !current.visible }))} title={resultVisualization.visible ? "Hide the active result layer" : "Show the active result layer"}>{resultVisualization.visible ? <ScanEye size={14} /> : <EyeOff size={14} />} Overlay</button>
            <button className={resultVisualization.sceneMode === "translucent" ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, sceneMode: current.sceneMode === "translucent" ? "opaque" : "translucent", translucentScene: current.sceneMode !== "translucent" }))} title="Toggle board translucency while preserving aligned result geometry"><Blend size={14} /> Translucent</button>
            {activeResultNets.length > 0 && <button className={resultVisualization.sceneMode === "analysis_only" ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, sceneMode: current.sceneMode === "analysis_only" ? "opaque" : "analysis_only", translucentScene: false }))} title="Show only analyzed conductor geometry and the selected result"><RouteOff size={14} /> Nets only</button>}
            {resultVisualization.mode !== "geometry" && <button className={resultVisualization.sceneMode === "results_only" ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, sceneMode: current.sceneMode === "results_only" ? "opaque" : "results_only", translucentScene: false, visible: true }))} title="Hide the complete board scene and show only the active analysis result"><ScanLine size={14} /> Analysis only</button>}
            <button className={resultVisualization.showComponentModels ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, showComponentModels: !current.showComponentModels }))} title="Show or hide component models while viewing results"><Boxes size={14} /> Models</button>
            {viewMode === "3D" && viewportResultScale && <button className={resultVisualization.plotStyle === "height" ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, plotStyle: current.plotStyle === "height" ? "flat" : "height" }))} title="Raise raw scalar samples into a 3D diagnostic height map"><ChartColumnIncreasing size={14} /> Raw height</button>}
            {viewMode === "3D" && viewportResultScale && <button className={resultVisualization.plotStyle === "contour" ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, plotStyle: current.plotStyle === "contour" ? "flat" : "contour" }))} title="Show a continuous, layer-aware 3D scalar surface with contour lines"><Spline size={14} /> Contour</button>}
            {viewportResultScale && resultVisualization.plotStyle !== "contour" && <button className={resultVisualization.fieldStyle === "smooth" ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, fieldStyle: current.fieldStyle === "smooth" ? "cells" : "smooth" }))} title={resultVisualization.fieldStyle === "smooth" ? "Show raw solver sample cells" : "Show a derived smooth field overlay"}><Combine size={14} /> Smooth field</button>}
            {hasVectorResult && ["current", "current_density", "electric_field", "magnetic_field"].includes(resultVisualization.mode) && <button className={resultVisualization.showVectors ? "selected" : ""} onClick={() => setResultVisualization(current => ({ ...current, showVectors: !current.showVectors }))} title={resultVisualization.showVectors ? "Hide result direction arrows" : "Show result direction arrows"}><MoveUpRight size={14} /> Arrows</button>}
          </div>}
        </CommandStrip>
        {(tab === "Mesh" || tab === "Solve") && <SimulationWorkspace
          tab={tab} domain={simulationDomain}
          analysisMode={simulationDomain === "pi" ? analysisMode : "SI channel analysis"}
          net={simulationDomain === "pi" ? piSetup.net : selected?.net ?? ""}
          meshSummary={simulationDomain === "pi" ? `${piSetup.meshTargetMm || "-"} mm target` : "Configured in SI channel setup"}
          solverName={solverCatalog.find(item => item.id === solverId)?.name ?? (solverId === "auto" ? "Automatic eligible solver" : solverId)}
          running={universalRunning} hasBoard={Boolean(boardData)} canExtract={Boolean(selected?.net || piSetup.net)}
          onDomain={setSimulationDomain}
          onConfigure={() => simulationDomain === "pi" ? openAnalysisSetup() : openSiWorkbench("geometry", "channel")}
          onNets={() => simulationDomain === "pi" ? openBoardManager("nets") : openSiWorkbench("geometry", "channel")}
          onStackup={() => setStackupOpen(true)}
          onExtract={() => simulationDomain === "pi" ? runParasitics(resultVisualization.viaModel) : openSiWorkbench("geometry", "channel")}
          onRun={() => simulationDomain === "pi" ? runAnalysis() : openSiWorkbench("geometry", "channel")}
          onStop={() => void cancelActiveAnalysis()}
          onHarness={() => setHarnessEditorOpen(true)}
          onTetraMesh={() => setTetraMeshOpen(true)}
        />}
        <div style={{ "--assembly-handling-height": `${assemblyHandlingHeight}px` } as React.CSSProperties} className={`board-canvas ${assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1 ? "has-assembly-handling " : ""}is-${viewMode.toLowerCase()}${viewportResultScale ? " has-result-scale" : ""}`}>

          {assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1 && <div ref={assemblyHandlingRef} className="assembly-handling-slot">
            <AssemblyQuickBar boards={virtualBoardProjection.visuals} selectedId={selectedBoardInstanceId} visibility={assemblyBoardVisibility} expanded={assemblyHandlingExpanded}
              onSelect={id => { const visual = virtualBoardProjection.visuals.find(board => board.id === id); if (visual) handleBoardInstanceSelect(visual); }}
              onVisibility={(id, value) => { recordChange(); setAssemblyBoardVisibility(current => ({ ...current, [id]: value })); }}
              moveMode={assemblyMoveMode} onMoveMode={selectAssemblyMoveMode}
              onExpand={() => openAssemblyPlacement()} onWorkspace={() => openAssemblyWorkspace()}
              onLayers={() => openBoardManager("layers")} onNets={() => openBoardManager("nets")} onLinks={() => openBoardManager("links")} />
          </div>}
          {scriptViewport && <div className="main-script-result-surface"><Suspense fallback={<div role="status">Loading simulation results…</div>}><ScriptResultViewport views={scriptViewport.views} runLabel={scriptViewport.label} onClose={() => setScriptViewport(null)}/></Suspense></div>}
          {!scriptViewport && <BoardViewport
            qualityTarget={viewportQualityHost}
            onEmiScene={tab === "EM" ? handleEmiScene : undefined}
            board={boardData}
            viewMode={tab === "EM" && emiChamberOpen ? "3D" : viewMode}
            visibleLayers={visibleLayers}
            layerOpacity={layerOpacity}
            layerSeparation={layerSeparation}
            showVias={showVias}
            showNetNames={showNetNames}
            showModels={showModels}
            showSmdModels={showSmdModels}
            showThtModels={showThtModels}
            assemblyModels={assemblySceneModels}
            assemblySelectorPreviews={assemblySelectorPreviews}
            virtualBoards={virtualBoardProjection.visuals}
            assemblyBoardDesigns={assemblyBoardVisuals.boards}
            assemblyLayerVisibility={assemblyLayerVisibility}
            assemblyLayerOpacity={assemblyLayerOpacity}
            assemblyBoardVisibility={assemblyBoardVisibility}
            assemblyExplodeOffsets={assemblyOffsets}
            assemblySnapTargets={assemblySnapTargets}
            selectedAssemblySnapTargetId={assemblySnapSource?.id ?? null}
            onAssemblySnapTarget={handleAssemblySnapTarget}
            assemblyResultOverlays={assemblyOverlayState.overlays}
            selectedBoardInstanceId={selectedBoardInstanceId}
            onBoardInstanceSelect={handleBoardInstanceSelect}
            onAssemblyNetSelect={handleAssemblyNetSelect}
            onAssemblyComponentSelect={handleAssemblyComponentSelect}
            onShowAllAssemblyBoards={() => setSelectedBoardInstanceId(null)}
            linkedAssemblyNets={linkedAssemblyNets}
            virtualHarnesses={displayHarnesses}
            selectedHarnessId={selectedHarnessId}
            onHarnessSelect={handleHarnessSelect}
            topologySelectorActive={mcadAttachmentOpen}
            selectedTopologyId={selectedTopologyReference?.topology_id ?? null}
            onTopologySelect={handleViewportTopologySelect}
            isolatedAssemblyPartId={isolatedAssemblyPartId}
            assemblySection={assemblySection}
            navigationMode={navigationMode}
            navigationInertia={navigationInertia}
            showAxes={showAxes}
            selectionBlink={appSettings.selectionBlink}
            cameraCommand={cameraCommand}
            viewportRestore={viewportRestore}
            selectionFilter={selectionFilter}
            selectedId={selected?.id ?? null}
            selectedPosition={selected?.position}
            selectedNet={selected?.net ?? null}
            highlightedNets={normalPassThroughNets}
            isolatedNet={isolatedNet}
            analysisResult={activeAnalysisResult}
            resultVisualization={activeResultVisualization}
            analysisNets={viewportAnalysisNets}
            probes={probes}
            showProbes={showProbes}
            hoverProbeEnabled={probeMode === "hover"}
            hoverProbeKind={probeKind}
            terminalMarkers={terminalMarkers}
            thermalScenario={viewportThermalScenario}
            thermalVisibility={thermalVisibility}
            emOverlay={emViewportOverlay}
            extensionMesh={extensionMesh}
            onEmSample={index => setEmViewportSettings(current => ({ ...current, selectedSample: index }))}
            emRadiation={!emViewportData && emergeViewportPattern ? { pattern: emergeViewportPattern, surrogate: emergeViewportSurrogate, sourceLabel: String(extensionResult?.title ?? "EMerge result") } : null}
            siCrosstalk={siViewportCrosstalk}
            onSelect={handleSelect}
            onContextMenu={setViewportContext}
            onOrbitCenter={handleViewportOrbitCenter}
            onCamera={handleCamera}
            onLayoutView={handleLayoutView}
            onTelemetry={handleTelemetry}
            onModelStatus={setModelLoadStatus}
            onAssemblyPartViewportStatus={handleAssemblyPartViewportStatus}
          />}
          {emResultManagerOpen && emViewportRecords.length > 0 && <EMViewportResultManager records={emViewportRecords} activeRecordId={emViewportRecord?.id ?? ""} settings={emViewportSettings} data={emViewportData} onSelectRecord={id => { setResultDisplay(id); setEmViewportSettings(current => ({ ...current, visible: true, frequencyIndex: 0, selectedSample: 0, quantity: availableEMQuantities(emViewportRecords.find(row => row.id === id)!)[0]?.id ?? "far_e" })); setViewMode("3D"); setEmiChamberOpen(false); }} onSettingsChange={setEmViewportSettings} onClose={() => setEmResultManagerOpen(false)} />}
          {tab === "EM" && emiChamberOpen && <EmiChamberWorkspace
            source={emiScene} setup={emiSetup.chamber} hasBoard={Boolean(boardData)}
            emergePatterns={emergePatterns} emergeFrequencyIndex={emergePatternIndex} onEmergeFrequencyIndexChange={setEmergePatternIndex}
            cameraCommand={cameraCommand}
            navigationMode={navigationMode} onNavigationModeChange={setNavigationMode}
            sourceNote={[modelNotice ? `${modelNotice.title}: ${modelNotice.detail}` : "", ...Object.entries(assemblyBoardVisuals.diagnostics).map(([id, message]) => `${id}: ${message}`)].filter(Boolean).join(" ")}
            onChange={chamber => { setEmiSetup(current => ({ ...current, chamber })); setExternalCase(null); setEmiPreflight(null); }}
            reviewOpen={emiDashboardOpen} onReview={setEmiDashboardOpen}
            onSetup={() => { setEmiChamberOpen(false); setRightOpen(true); setEmiSection("excitation"); }}
            onPrepare={() => void prepareEmiCase()} onRun={() => void runExternalEngine("external.openems", false)}
            busy={emiBusy || externalEngineBusy} canRun={Boolean(emiPreflight?.can_run && externalCase?.canRun && emiPreparedSetupKey === JSON.stringify(emiSetup))}
            dashboard={<>{emergePatterns.length > 0 && <div data-guide="emerge-em-result" style={{ padding: 12 }}><EMergeResultPlot result={extensionResult} frequencyIndex={emergePatternIndex} onFrequencyIndexChange={setEmergePatternIndex} /></div>}<EmiDashboard embedded preflight={emiPreflight} screening={emiScreening} fieldResult={emiFieldResult} onClose={() => setEmiDashboardOpen(false)} onScreen={() => void runEmiScreening()} onPrepare={() => void prepareEmiCase()} onSolverManager={() => void openExternalEngineCenter()} /></>}
          />}
          {viewportResultScale && <div className="viewport-colorbar" role="img" aria-label={`${viewportResultScale.label} from ${viewportResultScale.minimum} to ${viewportResultScale.maximum} ${viewportResultScale.unit}`}>
            <b>{viewportResultScale.label}</b>
            <div><span>{viewportResultScale.minimum.toPrecision(5)}</span><i /><span>{viewportResultScale.maximum.toPrecision(5)}</span></div>
            <small>{viewportResultScale.unit}</small>
          </div>}

        </div>
        {tab === "Mesh" ? <div className="results-strip">
          <div><span className="eyebrow">ACTIVE WORKSPACE</span><b>{simulationDomain === "si" ? "SI mesh" : "PI mesh"}</b></div>
          <div className="metric"><span>NEXT STEP</span><strong>Review mesh</strong></div>
          <button className="run-btn" onClick={() => { if (workspaceExtensionRoute) { setRightOpen(true); return; } simulationDomain === "si" ? openSiWorkbench("geometry", "channel") : openAnalysisSetup(); }}><SlidersHorizontal size={15} /> Mesh controls</button>
        </div> : siWorkspace ? <div className="results-strip">
          <div><span className="eyebrow">ACTIVE ANALYSIS</span><b>Signal integrity</b></div>
          <div className="metric"><span>SI RESULT</span><strong>{siSParameterSolver === "emerge" ? (emergeSiAnalysis ? String(emergeSiAnalysis.status ?? "saved") : "Not run") : (siChannelResult ? String(siChannelResult.status ?? "saved") : "Not run")}</strong></div>
          <div className="metric"><span>MODEL STATUS</span><strong className="amber">{siSParameterSolver === "emerge" ? "Unvalidated" : "Experimental"}</strong></div>
          <button className="plain-btn" onClick={() => siSParameterSolver === "emerge" && emergeSiAvailable ? openSiEmerge() : openSiWorkbench(siChannelResult?.contract === "spike/si-workflow-result/v1" ? "workflow" : "geometry", "channel")}><LayoutDashboard size={15} /> SI results</button>
          <button className="run-btn" onClick={openSelectedSParameters}><Play size={15} /> {siSParameterSolver === "emerge" && emergeSiAvailable ? "Configure EMerge SI" : "Configure SI run"}</button>
        </div> : tab === "EM" ? <div className="results-strip">
          <div><span className="eyebrow">ACTIVE ANALYSIS</span><b>{emergePatterns.length ? "EMerge radiation" : "Electromagnetics"}</b></div>
          <div className="metric"><span>EM RESULT</span><strong>{emergePatterns.length ? "Saved pattern" : emiFieldResult?.far_field ? "Far field" : "Not run"}</strong></div>
          <div className="metric"><span>MODEL STATUS</span><strong className="amber">{emergePatterns.length ? "Unvalidated" : emiPreflight?.can_run ? "Preflight ready" : "Setup needed"}</strong></div>
          <button className="run-btn" disabled={emiBusy || externalEngineBusy} onClick={() => {
            if (solverSelections.extension_em) { setRightOpen(true); setStatus("Configure and run the selected EM extension in the workspace setup dock."); return; }
            if (emiPreflight?.can_run && externalCase?.canRun && emiPreparedSetupKey === JSON.stringify(emiSetup)) void runExternalEngine("external.openems", false);
            else { setRightOpen(true); setEmiSection("solver"); setStatus("Review the EM setup and prepare an eligible solver case before running."); }
          }}><Play size={15} /> {emiBusy || externalEngineBusy ? "Running EM" : emiPreflight?.can_run && externalCase?.canRun && emiPreparedSetupKey === JSON.stringify(emiSetup) ? "Run openEMS" : "Set up EM run"}</button>
        </div> : tab === "Thermal" ? <div className="results-strip">
          <div><span className="eyebrow">ACTIVE ANALYSIS</span><b>Board thermal</b></div>
          <div className="metric"><span>BOARD RESULT</span><strong>{thermalScenario?.board_thermal_result ? "Saved field" : "Not run"}</strong></div>
          <div className="metric"><span>MODEL STATUS</span><strong className="amber">Approximate</strong></div>
          <button className="run-btn" onClick={() => setThermalOpen(true)}><Play size={15} /> Set up thermal run</button>
        </div> : tab === "PI" || tab === "Solve" ? <div className="results-strip">
          <div><span className="eyebrow">ACTIVE ANALYSIS</span><b>{analysisMode}</b></div>
          <div className="metric"><span>MAX DROP</span><strong>{analysisSummary ? analysisSummary.maxDropMv.toFixed(2) : "—"}</strong><small>mV</small></div>
          <div className="metric"><span>MAX CURRENT DENSITY</span><strong>{analysisSummary ? analysisSummary.maxDensity.toFixed(2) : "—"}</strong><small>A/mm²</small></div>
          <div className="metric"><span>MODEL STATUS</span><strong className="amber">{analysisSummary?.modelStatus ?? (analysisMode === "AC Impedance Sweep" ? "Unsupported" : "Approximate")}</strong></div>
          {activeAnalysisResult && <button className="plain-btn" onClick={() => { if (detachedTools.results) void detachTool("results"); else setResultVisualizerOpen(true); }} title={detachedTools.results ? "Bring the detached results manager to the front" : "Open the floating results manager"}><LayoutDashboard size={15} /> Results manager</button>}
          <button className={`run-btn ${analysisRunning ? "stop" : ""}`} onClick={analysisRunning ? () => void cancelActiveAnalysis() : runAnalysis}>{analysisRunning ? <X size={15} /> : <Play size={15} fill="currentColor" />} {analysisRunning && operationDisplay ? `Stop · ${formatRunDuration(operationDisplay.elapsedSeconds)}` : analysisRunning ? "Stop" : analysisSetupWorkflow === "path" ? "Run series path" : analysisSetupWorkflow === "batch" ? "Run batch nets" : analysisMode === "AC Impedance Sweep" ? "Configure AC" : analysisMode === "Transient PI" ? "Run transient" : analysisMode === "Bulk Net Analysis" ? "Run bulk nets" : "Run DC"}</button>
        </div> : <div className="results-strip results-strip--summary"><div><span className="eyebrow">ACTIVE WORKSPACE</span><b>{tab}</b></div></div>}
      </section>

      <aside className={rightOpen ? "side-panel right" : "side-panel right collapsed"}>
        <div className="panel-heading">
          <button className="panel-title-toggle" onClick={() => setRightOpen(current => !current)} aria-expanded={rightOpen} title={rightOpen ? "Collapse analysis setup" : "Expand analysis setup"}>{tab === "EM" ? "EM SETUP" : siWorkspace ? "SI SETUP" : selected || selectedHarness || selectedBoardInstance ? "SELECTION INSPECTOR" : "ANALYSIS SETUP"}</button>
          <button onClick={() => setRightOpen(current => !current)} className="collapse-btn" title={rightOpen ? "Collapse analysis setup" : "Expand analysis setup"} aria-label={rightOpen ? "Collapse analysis setup" : "Expand analysis setup"}>{rightOpen ? <PanelRight size={15} /> : <PanelLeft size={17} />}</button>
        </div>
        {rightOpen && extensionWorkspace && <ExtensionWorkspacePanel extensions={extensionCatalog} workspace={extensionWorkspace} selectedRouteId={solverSelections[`extension_${extensionWorkspace}`]} boardLoaded={Boolean(boardData)} busy={extensionWorkflowBusy} onSelectRoute={key => { markProjectDirty(); setSolverSelections(current => ({ ...current, [`extension_${extensionWorkspace}`]: key })); setExtensionResult(null); invalidateEMergePreview(); }} onConfigure={configureWorkspaceExtension} parameters={workspaceExtensionParameters} onPreview={(extensionId, contributionId, parameters) => runExtensionWorkflow(extensionId, contributionId, extensionId === "spike.openems-suite" ? { ...parameters, operation: "preflight" } : { ...parameters, preview_radiation: extensionWorkspace === "em" })} onRun={runExtensionWorkflow} renderSetup={workspaceExtensionRoute && ["spike.emerge-suite", "spike.openems-suite"].includes(workspaceExtensionRoute.extensionId) ? route => <><fieldset disabled={extensionWorkflowBusy} style={{ border: 0, padding: 0, minWidth: 0 }}>
          {route.extensionId === "spike.emerge-suite" ? <EMergeSetupForm gerberSource={gerberSource} gerberRuntime={emergeEmiRuntime} onOpenGerber={openNativeGerber} value={emergeEmiSetup} onChange={value => { if (value.python_executable !== emergeEmiSetup.python_executable) { emergeProbePathRef.current = value.python_executable.trim(); setEmergeEmiRuntime(null); } setEmergeEmiSetup(value); invalidateEMergePreview(); markProjectDirty(); }} netOptions={[...new Set(Object.values(boardData?.nets ?? {}))].sort()} padOptions={(boardData?.pads ?? []).map(pad => pad.id).sort()} boardPads={boardData?.pads} copperLayerOrder={boardData?.stackup.filter(layer => layer.name.endsWith(".Cu")).map(layer => layer.name)} boardBounds={boardData?.bounds} /> : route.extensionId === "spike.openems-suite" ? <OpenEMSSetupForm value={workspaceOpenEMSSetup} onChange={value => { setWorkspaceOpenEMSSetup(value); markProjectDirty(); }} netOptions={[...new Set(Object.values(boardData?.nets ?? {}))].sort()} disabled={extensionWorkflowBusy} /> : <p>Use the declared extension GUI for its structured setup.</p>}</fieldset>
          {workspaceExtensionInputError && <p role="status">{workspaceExtensionInputError}</p>}
          {route.extensionId === "spike.emerge-suite" && <EMergeScriptPreview data={emergeScriptPreview} />}
          {route.extensionId === "spike.openems-suite" && typeof (extensionResult?.data as Record<string, unknown> | undefined)?.script === "string" && <details><summary>Prepared openEMS adapter source</summary><p>Read-only adapter body; the execution snapshot also includes authenticated geometry and run context.</p><textarea aria-label="Prepared openEMS adapter source" readOnly rows={10} value={String((extensionResult!.data as Record<string, unknown>).script)} /></details>}
          {extensionMesh && extensionWorkspace === "mesh" && <div role="status"><b>{String(extensionMesh.contract)} · unsolved · {String(extensionMesh.model_status)}</b><p>Mesh drawn over the PCB. The viewport uses a bounded display subset; full topology remains with this mesh result.</p><button onClick={() => { const targetDomain: ExtensionWorkspace = simulationDomain === "si" ? "si" : "em"; const target = extensionWorkspaceRoutes(extensionCatalog, targetDomain, "solve").find(candidate => candidate.extensionId === route.extensionId); if (!target) { setStatus("This engine has no declared solve route for the selected domain."); return; } setSolverSelections(current => ({ ...current, [`extension_${targetDomain}`]: target.key })); setTab(targetDomain === "si" ? "HF / SI" : "EM"); setStatus("Review the same engine's solve setup. Its solver prepares its own mesh from the reviewed case."); }}>Configure solve with this engine</button><button onClick={() => setExtensionMesh(null)}>Hide mesh</button></div>}
        </> : undefined} />}
        {rightOpen && !workspaceExtensionRoute && (tab === "EM"
          ? <EmiSetupPanel board={boardData} selected={selected} setup={emiSetup} setSetup={setEmiSetup} preflight={emiPreflight} screening={emiScreening} section={emiSection} setSection={setEmiSection} busy={emiBusy || externalEngineBusy} canExecutePreparedCase={Boolean(externalCase?.canRun)} onValidate={() => void validateEmi()} onScreen={() => void runEmiScreening()} onPrepare={() => void prepareEmiCase()} onRun={() => void runExternalEngine("external.openems", false)} onDashboard={() => setEmiDashboardOpen(true)} onSolverManager={() => void openExternalEngineCenter()} onStatus={setStatus} />
          : siWorkspace
            ? <div className="inspector shared-mesh-inspector"><div className="setup-block"><label>SIGNAL CHANNEL</label><b>Experimental SI analysis</b><small>Configure an explicit channel and reference. Geometry-derived NEXT/FEXT needs a separate victim net; loaded studies use assigned channel ports.</small><button className="secondary-btn" onClick={() => openSiWorkbench("geometry", "channel")}>S-parameters and eye</button><button className="secondary-btn" onClick={() => openSiWorkbench("geometry", "crosstalk")}>NEXT / FEXT setup</button><button className="secondary-btn" onClick={() => openSiWorkbench("workflow", "ports")}>Source / receiver ports</button><button className="secondary-btn" onClick={() => openSiWorkbench("workflow", "channel")}>Loaded channel workflow</button>{siChannelResult && <small>Latest SI result: {String(siChannelResult.status ?? "saved")}. Open SI results to review limitations and traces.</small>}</div></div>
          : tab === "Mesh" && !selected
            ? <div className="inspector shared-mesh-inspector"><div className="setup-block"><label>MESH WORKSPACE</label><b>{simulationDomain === "pi" ? `${piSetup.meshTargetMm} mm target` : "Loaded SI channel setup"}</b><small>Solver selection and execution are available in the Solve tab.</small><button className="secondary-btn" onClick={() => simulationDomain === "pi" ? openAnalysisSetup() : openSiWorkbench("geometry", "channel")}>Open mesh controls</button></div></div>
          : selected
            ? <Inspector board={boardData} object={selected} selectionFilter={selectionFilter} isolated={Boolean(isolatedNet)} assignedModel={selected.ref ? modelAssignments[selected.ref] : undefined} onClear={() => setSelected(null)} onProbe={() => addProbe(selected)} onModelLibrary={() => setModelLibraryOpen(true)} onIsolate={() => { recordChange(); setIsolatedNet(isolatedNet ? null : selected.net ?? null); setStatus(isolatedNet ? "Complete board restored" : `${selected.net} isolated for PI/SI extraction`); }} />
            : selectedHarness
              ? <HarnessInspector harness={selectedHarness} onClear={() => setSelectedHarnessId(null)} />
            : selectedBoardInstance
              ? <><BoardInstanceInspector board={selectedBoardInstance} onClear={() => setSelectedBoardInstanceId(null)} /><div className="panel-block"><strong>Board placement</strong><p>Use the assembly handling bar for move, rotation, numeric angles, and hole or edge alignment. Display explosion keeps physical placement unchanged.</p></div></>
            : <SetupPanel analysisMode={analysisMode} setAnalysisMode={setAnalysisMode} solverId={solverId} setSolverId={setSolverId} formulation={formulation} setFormulation={setFormulation} solverCatalog={solverCatalog} powerNets={powerNets} limits={limits} setLimits={setLimits} piSetup={piSetup} onNetManager={() => openBoardManager("nets")} onConfigure={() => setDcRunOpen(true)} onStackup={() => setStackupOpen(true)} />)}
      </aside>
{dcRunOpen && <PiRunDialog importedDesign={boardFile.endsWith(".spike-design.json") ? designForSolver() : null} board={boardData} selected={selected} analysisMode={analysisMode} initialWorkflow={analysisSetupWorkflow} sharedStage={tab === "Mesh" ? "Mesh" : "Solve"} onSharedStage={stage => openSharedWorkspace(stage, "pi")} setup={piSetup} setSetup={next => { markProjectDirty(); setPiSetup(next); }} topology={piTopology} limits={limits} solverId={solverId} formulation={formulation} solverCatalog={solverCatalog} probes={probes} resources={processResources} appSettings={appSettings} onRequireAdmission={requireAssemblyAdmission} onOpenPowerPaths={() => { setDcRunOpen(false); setDock("Power tree"); setTopologyEditor("pi"); }} onOpenSpice={() => { setDcRunOpen(false); setSpiceOpen(true); }} onDiagnosticHelp={code => { setHelpDiagnosticCode(code); setHelpOpen(true); }} onClose={() => setDcRunOpen(false)} onRunState={(running, progress) => { setAnalysisRunning(running); setOperationDisplay(running ? progress ?? { label: "Running analysis", elapsedSeconds: 0 } : null); }} onResult={(message, summary) => { setAnalysisRunning(false); setOperationDisplay(null); setStatus(message); if (summary) setAnalysisSummary(summary); }} />}
      {leftOpen && <div className="dock-resizer left" role="separator" aria-orientation="vertical" onPointerDown={beginDockResize("left")} title="Drag to resize the design navigator" aria-label="Resize design navigator" />}
      {rightOpen && <div className="dock-resizer right" role="separator" aria-orientation="vertical" onPointerDown={beginDockResize("right")} title="Drag to resize the selection inspector" aria-label="Resize selection inspector" />}
      {bottomOpen && <div className="dock-resizer bottom" role="separator" aria-orientation="horizontal" onPointerDown={beginDockResize("bottom")} title="Drag to resize the bottom panel" aria-label="Resize bottom panel" />}
    </main>

    <section className="bottom-dock"><CommandStrip className="dock-tabs" label="Results dock"><button className={dock === "Issues" ? "selected" : ""} aria-expanded={dock === "Issues" && bottomOpen} onClick={() => toggleBottomDock("Issues")} title={dock === "Issues" && bottomOpen ? "Hide Issues dock" : "Show Issues dock"}><ShieldAlert size={14} /> Issues <b>{workspaceWarningCount || ""}</b></button><button className={dock === "Probe table" ? "selected" : ""} aria-expanded={dock === "Probe table" && bottomOpen} onClick={() => toggleBottomDock("Probe table")} title={dock === "Probe table" && bottomOpen ? "Hide Probe table dock" : "Show Probe table dock"}><Table2 size={14} /> Probe table <b>{probes.length || ""}</b></button><button className={dock === "Power tree" ? "selected" : ""} aria-expanded={dock === "Power tree" && bottomOpen} onClick={() => toggleBottomDock("Power tree")} title={dock === "Power tree" && bottomOpen ? "Hide Power tree dock" : "Show Power tree dock"}><Network size={14} /> Power tree</button><button className={dock === "Console" ? "selected" : ""} aria-expanded={dock === "Console" && bottomOpen} onClick={() => toggleBottomDock("Console")} title={dock === "Console" && bottomOpen ? "Hide Console dock" : "Show Console dock"}><Activity size={14} /> Console {activityUnread > 0 && <b>{activityUnread}</b>}</button><button className={dock === "Notifications" ? "selected" : ""} aria-expanded={notificationsOpen} aria-controls="workbench-notification-content" onClick={() => toggleBottomDock("Notifications")} title={notificationsOpen ? "Collapse notifications and view tools" : "Open notifications and view tools"}><Bell size={14} /> Notifications {notificationCount > 0 && <b>{notificationCount}</b>}</button><ToolRestoreShelf items={toolRestoreItems} onError={setStatus} /><span className="dock-spacer" />{viewportSetupAction}{boardImport.progress && <button className="board-import-status" onClick={openNotificationDock} title={boardImport.progress.label} aria-label={`Open import details: ${boardImport.progress.label}`}>{boardImport.progress.busy ? `Import ${boardImport.progress.percent}%` : importReviewCount ? "Import needs review" : "Import details"}</button>}<span ref={setViewportQualityHost} className="viewport-quality-host" /><span className="dock-notice-summary" title={modelNotice?.title ?? boardDisplaySummary}>{modelNotice?.title ?? boardDisplaySummary}</span><span className="validation"><BookOpen size={14} /> {boardData ? "Design loaded · validate analysis before solving" : "No design loaded"}</span></CommandStrip>{dock === "Notifications" ? <div id="workbench-notification-content" className="notification-dock-content" aria-label="Notifications and view tools">
      {notificationWorkspaceTools}
      <ViewportNotifications {...notificationProps} mode="dock" />
      {boardImport.progress && <BoardImportPanel embedded progress={boardImport.progress} onHide={() => setBottomOpen(false)} onCancel={() => void boardImport.cancel()} onLocate={source => void boardImport.locate(source)} onRetry={() => void boardImport.retry()} />}
      <div className="viewport-legend"><span><i className="legend-copper" /> Copper</span><span><i className="legend-current" /> Selected net</span><span><i className="legend-hot" /> Issue hotspot</span></div>
    </div> : dock === "Issues" ? <div className="issue-list">{activeWorkspaceIssues.map(issue => <Issue key={issue.title} {...issue} />)}</div> : dock === "Probe table" ? <div className="empty-dock"><Table2 size={16} /><span>{probes.length} probes · {probeFormulaRows.length} calculated rows</span>{detachedTools.probes && <button className="secondary-btn" onClick={() => void detachTool("probes")}>Show probe window</button>}</div> : dock === "Power tree" ? <div className="power-tree-dock"><b>{piSetup.net || "No power net selected"}</b><span>{piSetup.sources.length} source{piSetup.sources.length === 1 ? "" : "s"}</span><ArrowRight size={14} /><span>{piSetup.loads.length} sink{piSetup.loads.length === 1 ? "" : "s"}</span><button className="secondary-btn" onClick={() => openAnalysisSetup()}>Edit terminals</button></div> : <ActivityConsole entries={activityLog} onClear={() => { setActivityLog([]); setActivityUnread(0); }} />}</section>
    {bottomOpen && dock === "Probe table" && !detachedTools.probes && <div className="probe-results-overlay"><div className="probe-window-actions"><button onClick={() => void detachTool("probes")}>Detach probe table</button><button onClick={() => setBottomOpen(false)}>Close table</button></div><ProbeResultsTable probes={probes} result={activeAnalysisResult}
      calculatedRows={probeFormulaRows} probeReferenceIds={probeReferenceIds}
      onCalculatedRowsChange={rows => { markProjectDirty(); setProbeFormulaRows(rows); }}
      onRemoveProbe={id => { recordChange(); setProbes(current => current.filter(probe => probe.id !== id)); }}
      onRenameProbe={(id, name) => { markProjectDirty(); setProbes(current => current.map(probe => probe.id === id ? { ...probe, name } : probe)); }}
      onExportCsv={() => exportProbeCsv()} /></div>}
    <footer className="statusbar">
      <span className="offline-status"><span className="status-dot" /> Offline mode</span>
      <span
        className={`selection-status ${selected ? "active" : "empty"}`}
        title={selected
          ? [selected.type, selected.ref ?? selected.name, selected.net, selected.layers?.length ? selected.layers.join(" / ") : selected.layer, selected.position ? `${selected.position[0].toFixed(4)}, ${selected.position[1].toFixed(4)} mm` : null].filter(Boolean).join(" | ")
          : "Nothing is selected in the board viewport"}
      >
        <MousePointer2 size={12} />
        {selected ? <>
          <b>{selected.type.toUpperCase()}</b>
          <span className="selection-name">{selected.ref ?? selected.name}</span>
          {selected.net && <span className="selection-net">{selected.net}</span>}
          <span className="selection-layer">{selected.layers?.length
            ? selected.layers.length <= 2 ? selected.layers.join(" / ") : `${selected.layers[0]} +${selected.layers.length - 1}`
            : selected.layer ?? "unlayered"}</span>
        </> : <span className="selection-name">No selection</span>}
      </span>
      <button className={`status-current ${analysisRunning ? "busy" : activityLevel(status)}`} onClick={() => { setDock("Console"); setBottomOpen(true); }} title="Open activity console"><Activity size={12} /><span className="status-message" aria-live="polite">{analysisRunning && operationDisplay ? `${operationDisplay.label} · ${formatRunDuration(operationDisplay.elapsedSeconds)} elapsed${operationDisplay.estimateSeconds ? ` · estimate ~${formatRunDuration(operationDisplay.estimateSeconds)}` : ""}` : analysisRunning ? `Working: ${status}` : status}</span></button>
      {universalRunning && <button className="statusbar-stop" onClick={() => void cancelActiveAnalysis()} disabled={activeWorkerOperation?.cancelling} title="Cancel the active mesh or solver operation"><X size={12} /> {activeWorkerOperation?.cancelling ? "Stopping…" : "Stop"}</button>}
      <ResourceMonitor open={resourceOpen} setOpen={setResourceOpen} resources={processResources} render={renderTelemetry} board={boardData} />
      <button className="status-export" onClick={generateReport} title="Generate engineering report"><FileOutput size={12} /><span>Report</span></button>
      <span className="status-version">v{APP_VERSION}</span>
    </footer>
    <Suspense fallback={null}>
    {netManagerOpen && !(assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1) && <NetManager board={boardData} selectedNet={selected?.net} selectedObject={selected ?? undefined} managedNets={powerNets} setManagedNets={nets => { setPowerNets(nets); if (nets[0]) setPiSetup(current => ({ ...current, net: nets[0] })); }} loopExtractions={piSetup.loopExtractions} setLoopExtractions={loopExtractions => setPiSetup(current => ({ ...current, loopExtractions }))} pathGroups={[...new Map(piTopology.nodes.filter(node => node.pathGroupId).map(node => [node.pathGroupId!, node.pathGroupLabel || node.pathGroupId!])).entries()].map(([id, label]) => ({ id, label }))} onSelectNet={focusManagedNet} onOpenPowerPaths={() => { setNetManagerOpen(false); setDock("Power tree"); setTopologyEditor("pi"); }} onOpenSeriesAnalysis={() => { setNetManagerOpen(false); openAnalysisSetup("DC IR Drop", "path"); }} onStatus={setStatus} onClose={() => { previewViewportTarget(null); setNetManagerOpen(false); }} />}
    {topologyEditor && <TopologyEditor domain={topologyEditor} board={boardData} model={topologyEditor === "pi" ? piTopology : siTopology} onUndo={undo} onRedo={redo} setModel={(next, record = true) => { if (record) recordChange(); topologyEditor === "pi" ? setPiTopology(next) : setSiTopology(next); }} onClose={() => setTopologyEditor(null)} onUseForAnalysis={(next, scenarioId, plan) => { if (next.domain === "pi") { const jobs = topologyBatchJobs(boardData, next, plan); const first = jobs[0]; const paths = compilePiPaths(next); const reviewedPath = paths.find(path => path.issues.length === 0) ?? paths[0]; const sourceNode = next.nodes.find(node => node.pathGroupId === reviewedPath?.id && node.kind === "source"); const loadNode = next.nodes.find(node => node.pathGroupId === reviewedPath?.id && node.kind === "load"); const pathSource = reviewedPath ? topologyTerminal(boardData, sourceNode, reviewedPath.source_terminal.net, "source", 0, sourceNode?.voltageV ?? 0) : null; const pathLoad = reviewedPath ? topologyTerminal(boardData, loadNode, reviewedPath.load_terminal.net, "load", 0, loadNode ? plan.budget.nodes[loadNode.id]?.currentA ?? loadNode.loadCurrentA ?? 0 : 0) : null; const unresolved = reviewedPath ? [pathSource, pathLoad].filter(item => !item?.anchorId).length : jobs.flatMap(job => [...job.sources, ...job.loads]).filter(item => !item.anchorId).length; setPiTopology(next); if (reviewedPath && pathSource && pathLoad) setPiSetup(current => ({ ...current, powerPathId: reviewedPath.id, net: reviewedPath.source_terminal.net, sources: [pathSource], loads: [pathLoad], batchJobs: jobs })); else if (first) setPiSetup(current => ({ ...current, powerPathId: "", net: first.net, sources: first.sources, loads: first.loads, batchJobs: jobs })); setAnalysisMode(reviewedPath ? "DC IR Drop" : jobs.length > 1 ? "Bulk Net Analysis" : "DC IR Drop"); setTab("PI"); setDock("Power tree"); setAnalysisSetupWorkflow(reviewedPath ? "path" : jobs.length > 1 ? "batch" : "single"); setRightOpen(true); setDcRunOpen(true); setStatus(reviewedPath ? `Power path ${reviewedPath.label} attached: ${reviewedPath.segments.length} net segments, ${reviewedPath.transitions.length} series interfaces; ${unresolved} terminal${unresolved === 1 ? "" : "s"} require placement review` : `Power tree ${scenarioId} case attached: ${jobs.length} PI job${jobs.length === 1 ? "" : "s"}; ${unresolved} terminal${unresolved === 1 ? "" : "s"} require placement review`); } else { setSiTopology(next); setTab("HF / SI"); setStatus(`SI channel topology saved: ${next.nodes.length} elements, ${next.edges.length} connections`); } setTopologyEditor(null); }} onStatus={setStatus} />}
    {layersOpen && !(assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1) && <LayerManager definitions={boardData?.layerDefinitions ?? layerEntries.map((name, id) => ({ id, name, kind: name.endsWith(".Cu") ? "signal" : "user" }))} stackup={boardData?.stackup ?? []} layers={visibleLayers} opacity={layerOpacity} viaCount={boardData?.vias.length ?? 0} showNetNames={showNetNames} setShowNetNames={setShowNetNames} showVias={showVias} setShowVias={setShowVias} showOnlyVias={showOnlyVias} layerSeparation={layerSeparation} setLayerSeparation={setLayerSeparation} toggleLayer={toggleLayer} setLayersVisible={setLayersVisible} showOnlyLayer={showOnlyLayer} changeOpacity={changeLayerOpacity} beginOpacityChange={recordChange} restoreDefaults={restoreLayerDefaults} showModels={showModels} setShowModels={setShowModels} showSmdModels={showSmdModels} setShowSmdModels={setShowSmdModels} showThtModels={showThtModels} setShowThtModels={setShowThtModels} smdCount={componentMountCounts.smd} thtCount={componentMountCounts.tht} onClose={() => setLayersOpen(false)} />}
    {stackupOpen && <EditableStackupManager stackup={boardData?.stackup ?? []} copperLayers={boardData?.layers ?? []} onSave={stackup => { recordChange(); setBoardData(current => current ? { ...current, stackup } : current); setCanonicalSpiDeR(current => applyStackupToSpiDeR(current, stackup)); setStatus("Project-local stackup updated; solver validity will be re-evaluated"); }} onClose={() => setStackupOpen(false)} />}
    {flexBoardOpen && <FlexBoardManager board={boardData} onClose={() => setFlexBoardOpen(false)} onStatus={setStatus} onShowLayers={layers => { setLayersVisible(layers, true); commandCamera("fit"); }} />}
    {modelLibraryOpen && <ModelResolverPanel boards={resolverBoards} initialBoardId={modelResolverTarget.designId} initialComponentRef={modelResolverTarget.componentRef} assignedPaths={{ ...assemblyModelAssignments, [assemblyDesigns?.active_design_id ?? activeDesignId ?? "active"]: modelAssignments }} onApplied={applyResolvedComponentModel} onClose={() => { setModelLibraryOpen(false); setModelResolverTarget({}); }} />}

    {assemblyWorkspaceOpen && <AssemblyToolHost kind="workspace" snapshot={assemblyToolSnapshot} onAction={action => assemblyToolAction("workspace", action)} onClose={() => { setAssemblyWorkspaceOpen(false); setAssemblyToolDraftOwner(current => current === "workspace" ? null : current); }}/>}
    {freecadCollaborationOpen && <div className="modal-shade"><section className="floating-panel" role="dialog" aria-modal="true" aria-label="ECAD–MCAD collaboration" style={{ width: "min(960px, calc(100vw - 32px))", maxHeight: "calc(100vh - 40px)", overflow: "auto" }}><header className="floating-panel-title"><strong>ECAD–MCAD collaboration</strong><button type="button" aria-label="Close ECAD–MCAD collaboration" onClick={() => setFreecadCollaborationOpen(false)}><X size={16}/></button></header><FreecadCollaboration projectPath={projectPath} manifestDigest={projectManifestDigest} disabled={!desktopShell || projectDirty || Boolean(assemblyToolDraftOwner)} onUpdated={async () => { if (projectPath) await loadNativeProjectFromApprovedPath(projectPath, projectName); }} onStatus={setStatus}/></section></div>}
    {assemblyHandlingExpanded && <AssemblyToolHost kind="placement" snapshot={assemblyToolSnapshot} onAction={action => assemblyToolAction("placement", action)} onClose={() => setAssemblyHandlingExpanded(false)}/>}
    {assemblyIr && assemblyDesigns && assemblyIr.boards.length > 1 && (layersOpen || netManagerOpen || assemblyLinksOpen) && <AssemblyToolHost kind="managers" snapshot={assemblyToolSnapshot} onAction={action => assemblyToolAction("managers", action)} onClose={() => { setLayersOpen(false); setNetManagerOpen(false); setAssemblyLinksOpen(false); setAssemblyToolDraftOwner(current => current === "managers" ? null : current); }}/>}
    {sourceImport && <ImportSourceDialog initialSource={sourceImport.source} initialKind={sourceImport.kind} onApply={applySourceImport} onClose={() => setSourceImport(null)} />}
    {mcadAttachmentOpen && <McadAttachmentPanel initialSource={mcadImportSource} projectPath={projectPath} projectManifestDigest={projectManifestDigest} assemblyIr={assemblyIr} assemblyDesigns={assemblyDesigns} assemblyPackageShapes={assemblyPackageShapes} onOpenAssemblyWorkspace={openAssemblyWorkspace} focusedPartId={mcadFocusedPartId} focusedTopologyReference={selectedTopologyReference} desktopShell={desktopShell} isolatedPartId={isolatedAssemblyPartId} section={assemblySection} onIsolatedPart={partId => { setIsolatedAssemblyPartId(partId); setStatus(partId ? "Assembly part isolated temporarily" : "Complete assembly restored"); }} onSection={setAssemblySection} onAttached={async () => {
      if (!projectPath) throw new Error("Save the project before attaching MCAD.");
      await loadNativeProjectFromApprovedPath(projectPath, projectName);
    }} onStatus={setStatus} onOpenHarnessEditor={() => { setMcadAttachmentOpen(false); setMcadFocusedPartId(null); setHarnessEditorOpen(true); }} onClose={() => { setMcadAttachmentOpen(false); setMcadFocusedPartId(null); setMcadImportSource(null); }} />}
    {harnessEditorOpen && <div className="modal-shade" role="presentation" onKeyDown={event => { if (event.key === "Escape") setHarnessEditorOpen(false); }}>
      <section className="floating-panel harness-editor-modal" role="dialog" aria-modal="true" aria-labelledby="harness-editor-title" tabIndex={-1}>
        <div className="floating-heading"><div><b id="harness-editor-title">HARNESS PI</b><small>Portable harness connectivity and explicit DC screening</small></div><button autoFocus onClick={() => setHarnessEditorOpen(false)} aria-label="Close Harness PI editor"><X size={15} /></button></div>
        <HarnessDocumentEditor value={harnessDocument} onChange={next => { recordChange(); setHarnessDocument(next); }} />
        <div className="extension-footer"><span>Saved with the project harness document. AssemblyIR harness links remain a separate placed-assembly view.</span><button className="secondary-btn" onClick={() => setHarnessEditorOpen(false)}>Close</button></div>
      </section>
    </div>}
    {tetraMeshOpen && <TetraMeshPanel onClose={() => setTetraMeshOpen(false)} onStatus={setStatus} />}
    {thermalOpen && <ThermalWizard initialScenario={thermalScenario} componentBonds={componentBonds} board={boardData} design={designForSolver()} boardSource={boardFile.toLowerCase().endsWith(".kicad_pcb") ? boardSource : null} workerAvailable={workerAvailable} onRequireAdmission={requireAssemblyAdmission} onClose={() => { setThermalOpen(false); setThermalPreview(null); }} onStatus={setStatus} onPreview={setThermalPreview} onScenario={scenario => { recordChange(); setThermalScenario(current => ({ ...current, ...scenario })); setThermalPreview(current => ({ ...current, ...scenario })); }} />}
    {tracePlotsOpen && <div className="modal-shade"><div style={{ width: "min(1400px, 94vw)", height: "88vh", background: "#101c25", overflow: "auto" }}><TraceResultsWorkbench result={activeAnalysisResult} domain={resultVisualizerDomain} targetNet={activePdnReview?.net} targetOhm={activePdnReview?.target_ohm}
      onClose={() => setTracePlotsOpen(false)} onDetach={() => void detachTool("trace-plots")} /></div></div>}
    {resultVisualizerOpen && <ResultVisualizationPanel onTracePlots={() => setTracePlotsOpen(true)} onDetach={() => void detachTool("results")} domain={resultVisualizerDomain} board={boardData} selectedNet={selected?.net ?? piSetup.net ?? null} result={activeAnalysisResult} sourceResult={analysisResult} visualization={resultVisualization} workerAvailable={workerAvailable} parasiticsAvailable={solverSupports("partial_inductance", "frequency_dependent_impedance")} riskAvailable={solverSupports("coupled_line_extraction", "electric_field_coupling", "magnetic_field_coupling")} pdnReview={activePdnReview} pdnReviewSourceId={pdnReviewSourceId} dropLimitMv={Number.isFinite(Number(limits.drop)) && Number(limits.drop) > 0 ? Number(limits.drop) : null} densityLimitAMm2={Number.isFinite(Number(limits.density)) && Number(limits.density) > 0 ? Number(limits.density) : null} onVisualization={setResultVisualization} onConfigure={() => { setResultVisualizerOpen(false); setDcRunOpen(true); }} onRunParasitics={runParasitics} onRunRisk={runSiRisk} onRunPdn={(target, candidate) => void runPdnReview(target, candidate)} onExportAnimation={() => void exportResultAnimation()} onClose={() => setResultVisualizerOpen(false)} />}
    {(sparameterOpen || sparameterActivated) && <div hidden={!sparameterOpen}><SParameterWorkbench assemblyDesigns={assemblyDesigns} canonicalDesign={canonicalSpiDeR} suite={selectedSiSuite} initialResult={siChannelResult} initialView={siWorkbenchIntent.view} initialFocus={siWorkbenchIntent.focus} intentToken={siWorkbenchIntent.token} onClose={() => setSparameterOpen(false)} onStatus={setStatus} onResult={result => { recordChange(); setSiChannelResult(result); }} /></div>}
    </Suspense>
    {emiDashboardOpen && tab === "EM" && !emiChamberOpen && <EmiDashboard preflight={emiPreflight} screening={emiScreening} fieldResult={emiFieldResult} onClose={() => setEmiDashboardOpen(false)} onScreen={() => void runEmiScreening()} onPrepare={() => void prepareEmiCase()} onSolverManager={() => void openExternalEngineCenter()} />}
    {acEffectsOpen && <div className="modal-backdrop"><div className="floating-panel" role="dialog" aria-modal="true" aria-label="AC power integrity effects" style={{ width: "min(1100px, 95vw)", maxHeight: "90vh", overflow: "auto" }}><button className="secondary-btn" onClick={() => setAcEffectsOpen(false)}>Close AC effects</button><button className="secondary-btn" disabled={!acEffectsResult} onClick={async () => { if (!acEffectsResult) return; const { buildAcPowerIntegrityReport } = await import("./acPowerIntegrityReport"); setReportPreview({ fileName: "ac-power-integrity.html", html: buildAcPowerIntegrityReport(projectName, acEffectsRequest, acEffectsResult) }); }}>AC report</button><ACPowerIntegrityEffects callWorker={runLocalWorker} onStatus={setStatus} initialRequest={acEffectsRequest} initialResult={acEffectsResult} onResult={(result, request) => { markProjectDirty(); setAcEffectsRequest(request); setAcEffectsResult(result); }} /></div></div>}
    {unsavedPrompt && <div className="modal-backdrop unsaved-project-backdrop" role="presentation">
      <section className="modal unsaved-project-dialog" role="alertdialog" aria-modal="true" aria-labelledby="unsaved-project-title" aria-describedby="unsaved-project-description">
        <header><div><small>UNSAVED PROJECT</small><h2 id="unsaved-project-title">Save changes before you {unsavedPrompt.actionLabel}?</h2></div><AlertTriangle size={22} /></header>
        <div className="unsaved-project-content"><p id="unsaved-project-description">Changes to <b>{projectName}</b> have not been saved. Saving writes the current project package before continuing.</p><small>Cancel keeps the project open. Discard continues without saving these changes.</small></div>
        <footer><button className="secondary-btn" onClick={() => void resolveUnsavedPrompt("cancel")}>Cancel</button><button className="danger-btn" onClick={() => void resolveUnsavedPrompt("discard")}>Discard changes</button><button className="run-btn" autoFocus onClick={() => void resolveUnsavedPrompt("save")}><Save size={14} /> Save and continue</button></footer>
      </section>
    </div>}
    {projectUpgradeOffer && !unsavedPrompt && <ProjectUpgradeDialog fileName={projectUpgradeOffer.fileName} sourceFormat={projectUpgradeOffer.sourceFormat} onUpgrade={upgradeProjectNow} onLater={() => setProjectUpgradeOffer(null)} />}
    <input ref={projectInputRef} className="hidden-input" type="file" accept=".spike,.spike.json,.spike-results.json,.json" onChange={loadProject} />
    <input ref={browserBoardInputRef} className="hidden-input" type="file" accept=".kicad_pcb,.spike-design.json" onChange={importBoard} />
    <input ref={resultInputRef} className="hidden-input" type="file" accept=".spike-results.json,.json" onChange={loadResultInput} />
    <input ref={comparisonInputRef} className="hidden-input" type="file" accept=".spike.json,.json" onChange={loadComparisonBaseline} />
    {revisionComparison && <RevisionComparisonDialog comparison={revisionComparison} onClose={() => setRevisionComparison(null)} />}
    {projectManagerOpen && <ProjectManager projectName={projectName} projectPath={projectPath} boardFile={boardFile} counts={{ layers: boardData?.layers.length ?? 0, nets: Object.keys(boardData?.nets ?? {}).length, components: boardData?.components.length ?? 0, results: resultRecords.length + (analysisResult ? 1 : 0) + (siChannelResult ? 1 : 0) + (emiFieldResult ? 1 : 0) + (emiScreening ? 1 : 0) + (thermalScenario?.result || thermalScenario?.field_result ? 1 : 0) }} recent={recentProjects} onNew={newProject} onOpen={() => { setProjectManagerOpen(false); void openProject(); }} onImport={() => { setProjectManagerOpen(false); void importNativeBoard(); }} onSave={() => { setProjectManagerOpen(false); void saveProject(); }} onSaveAs={() => { setProjectManagerOpen(false); void saveProject(projectFileName(projectName), true); }} onSaveWithoutResults={() => { setProjectManagerOpen(false); saveProjectWithoutResults(); }} onSaveResultsFile={() => { setProjectManagerOpen(false); void exportReport(); }} onStudies={() => { setProjectManagerOpen(false); setStudyManagerOpen(true); }} onClose={() => setProjectManagerOpen(false)} />}
    {studyManagerOpen && <StudyManager studies={studies} currentType={studyTypeForTab()} activeCaseId={activeStudyCaseId}
      onCreateStudy={() => { recordChange(); const study = createStudy(`Study ${studies.length + 1}`); setStudies(current => [...current, study]); setStatus(`${study.name} created`); return study.id; }}
      onImportStudies={items => { const imported = cloneImportedStudies(items); recordChange(); setStudies(current => [...current, ...imported]); }}
      onOpenResult={(run, item) => { const study = studies.find(row => row.cases.some(saved => saved.id === item.id)); if (study) activateStudyCase(study.id, { ...item, type: run.caseType || item.type, mode: run.mode, settings: run.settings, scenario: run.scenario, resultSnapshot: run.resultSnapshot, resultRef: run.resultRef }); }}
      onUpdateStudy={(studyId, patch) => { recordChange(); setStudies(current => updateStudy(current, studyId, patch)); }}
      onRemoveStudy={studyId => { recordChange(); setStudies(current => removeStudy(current, studyId)); setActiveStudyCaseId(null); }}
      onAddCase={addCaseToStudy}
      onUpdateCase={editStudyCase}
      onDuplicateCase={(studyId, caseId) => { recordChange(); setStudies(current => current.map(study => study.id === studyId ? duplicateStudyCase(study, caseId) : study)); }}
      onRemoveCase={(studyId, caseId) => { recordChange(); setStudies(current => current.map(study => study.id === studyId ? removeStudyCase(study, caseId) : study)); if (activeStudyCaseId === caseId) setActiveStudyCaseId(null); }}
      onMoveCase={(studyId, caseId, destination) => { recordChange(); setStudies(current => current.map(study => study.id === studyId ? moveStudyCase(study, caseId, destination) : study)); }}
      onActivateCase={activateStudyCase} onSaveCaseSetup={saveCaseSetup} onCaptureCaseResult={captureCaseResult} onClose={() => setStudyManagerOpen(false)} />}
    {mcpBridgePanelOpen && desktopShell && <McpBridgePanel onClose={() => setMcpBridgePanelOpen(false)} latestEvidence={mcpAnalysisOutput} />}
    {preferencesOpen && <UniversalSettingsModal settings={appSettings} onClose={() => setPreferencesOpen(false)} onSave={next => { setAppSettings(next); saveAppSettings(next); setNavigationInertia(next.navigationInertia); setPreferencesOpen(false); setStatus("Application settings saved locally"); }} />}
    {iconGalleryOpen && <IconGallery onClose={() => setIconGalleryOpen(false)} />}
    {helpOpen && <Suspense fallback={<div className="modal-shade" role="status">Loading help…</div>}><HelpCenter context={tab} diagnosticCode={helpDiagnosticCode} onClose={() => { setHelpOpen(false); setHelpDiagnosticCode(undefined); }} /></Suspense>}
    {guideOpen && <AnalysisGuide boardLoaded={Boolean(boardData)} resultAvailable={Boolean(analysisResult || resultRecords.length)} onNavigate={navigateAnalysisGuide} onClose={() => setGuideOpen(false)} />}
    {aboutOpen && <AboutDialog onClose={() => setAboutOpen(false)} onOpenGuide={() => { setAboutOpen(false); setHelpOpen(true); }} onOpenValidation={() => { setAboutOpen(false); setBenchmarkOpen(true); }} />}
    {benchmarkOpen && <BenchmarkCenter onClose={() => setBenchmarkOpen(false)} onStatus={setStatus} />}
    {spiceOpen && <SpiceWorkbench initialEngine={solverSelections.owned_circuit_workspace === "spike.owned_spice_workspace" ? "owned_spice" : "native_mna"} design={designForSolver()} board={boardData} selection={selected} workspace={spiceWorkspace} setWorkspace={next => { markProjectDirty(); setSpiceWorkspace(next); }} analysisResult={analysisResult} onRequireAdmission={requireAssemblyAdmission} onClose={() => setSpiceOpen(false)} onStatus={setStatus} onResult={result => { setAnalysisResult(result); setPdnReview(null); setPdnReviewSourceId(null); setResultRecords(current => boundedResultRecords([...current.filter(record => record.id !== result.analysis_id), resultRecord(result, current.length)])); setResultDisplay(result.analysis_id); setResultVisualization(current => ({ ...current, visible: true, mode: resultModeAvailable(result, "voltage") ? "voltage" : "geometry" })); setDock("Console"); }} />}
    {pythonOpen && <Suspense fallback={<div className="modal-shade" role="status">Loading Python editor…</div>}><PythonWorkspace onShowViewport={showScriptViewport} initialScript={contextScriptDraft ?? undefined} workspace={pythonContext} onUiAction={handlePythonUiAction} onAttachDataset={attachStudyDataset} design={pythonContext.boards.find(board => board.id === pythonContext.selected_board_id)?.design ?? designForExchange()} results={extensionResultsContext(activeAnalysisResult)} onClose={() => { setPythonOpen(false); setContextScriptDraft(null); }} onStatus={setStatus} /></Suspense>}
    {bondManagerOpen && <BondManager
      bonds={componentBonds}
      validation={bondValidation}
      onBondsChange={setComponentBonds}
      onAutoConnect={searchDistanceMm => {
        if (!boardData) { setStatus("Import a board before inferring component bonds"); return; }
        recordChange();
        const inferred = inferComponentBonds(boardData, searchDistanceMm);
        setComponentBonds(inferred);
        const validation = validateComponentBonds(inferred, boardData);
        setBondValidation(validation);
        setStatus(`Component bond inference produced ${inferred.length} terminal-to-copper records from ${boardData.components.length} components`);
      }}
      onValidate={() => {
        const validation = validateComponentBonds(componentBonds, boardData);
        setBondValidation(validation);
        const failures = validation.filter(result => result.status === "invalid").length;
        setStatus(failures ? `Component bond validation found ${failures} invalid record${failures === 1 ? "" : "s"}` : `Component bond validation passed for ${componentBonds.filter(bond => bond.enabled).length} enabled records`);
      }}
      onBondAdd={bond => {
        recordChange();
        if (!selected) return;
        const pad = selected.type === "pad" ? boardData?.pads.find(item => item.id === selected.id) : undefined;
        const component = boardData?.components.find(item => item.id === selected.id || item.ref === selected.ref || item.ref === pad?.ref);
        setComponentBonds(current => current.map(item => item.id === bond.id ? {
          ...item,
          componentId: component?.id,
          padId: pad?.id,
          position: pad?.at ?? selected.position,
          connectedLayers: pad?.layers.filter(layer => layer.endsWith(".Cu")) ?? selected.layers?.filter(layer => layer.endsWith(".Cu")) ?? [],
          part: component?.value ?? selected.name,
          reference: component?.ref ?? pad?.ref ?? selected.ref ?? "",
          pad: pad?.name ?? "",
          net: pad?.net ?? selected.net ?? "",
          surface: (pad?.layers.filter(layer => layer.endsWith(".Cu")) ?? selected.layers ?? [selected.layer].filter(Boolean)).join(" / "),
        } : item));
      }}
      onBondDelete={() => recordChange()}
      onHoverBond={bond => previewViewportTarget(bond ? { kind: "object", id: bond.padId, type: "pad", net: bond.net, ref: bond.reference, layer: bond.connectedLayers[0], position: bond.position, label: `${bond.reference}.${bond.pad} bond` } : null)}
      onClose={() => { previewViewportTarget(null); setBondManagerOpen(false); }}
    />}
    {gerberImportOpen && <EMergeGerberImport source={gerberSource} runtime={emergeEmiRuntime} disabled={!workerAvailable || emergeEmiBusy || universalRunning} onImport={importNativeGerber} onClose={() => setGerberImportOpen(false)}/> }
    {extensionsOpen && <ExtensionManager gerberSource={gerberSource} onOpenGerber={openNativeGerber} extensions={extensionCatalog} board={boardData} preferredId={extensionSelectedId} preferredContributionId={extensionSelectedContributionId} defaultNet={selected?.net ?? ""} uiVisible={extensionUiVisible} onToggleUi={toggleExtensionUi} result={extensionResult} emergePreview={emergeScriptPreview} optycalSource={optycalSource} optycalPreview={optycalPreview} onInvalidateOptycalPreview={invalidateOptycalPreview} onInvalidatePreview={() => invalidateEMergePreview()} harness={harnessDocument} trustBusy={extensionTrusting} trustError={extensionTrustError} onTrust={extensionId => void trustExtension(extensionId)} onHarnessChange={value => { recordChange(); setHarnessDocument(value); }} onClose={() => { invalidateEMergePreview(); invalidateOptycalPreview(); setExtensionsOpen(false); }} onRefresh={() => void openExtensionManager()} onRun={(extensionId, contributionId, parameters) => invokeExtension(extensionId, contributionId, parameters)} />}
    {(emergeEmiOpen || emergeSiOpen) && <div className="modal-shade"><div className="floating-panel extension-manager" style={{ gridTemplateRows: "48px minmax(0, 1fr) 45px" }} role="dialog" aria-label={emergeSiOpen ? "EMerge SI analysis" : "EMerge EMI analysis"}>
      <div className="floating-heading"><div><b>{emergeSiOpen ? "EMERGE SI / S-PARAMETERS" : "EMERGE IN EM"}</b><small>{emergeSiOpen ? "Board-bound two-port frequency sweep" : "Board-bound SI and relative radiation analysis"}</small></div><button onClick={() => { invalidateEMergePreview(); setEmergeEmiOpen(false); setEmergeSiOpen(false); }} aria-label="Close EMerge analysis"><X size={15} /></button></div>
      <div className="extension-detail">
        <p>Choose an imported 2–16 copper-layer board and aligned signal/return pads on adjacent layers. EMerge results remain unvalidated{emergeSiOpen ? "." : " and do not predict EMI compliance."}</p>
        {!emergeEmiExtension && <div className="stack-warning">EMerge Suite is not installed or has not loaded. Check Extension manager.</div>}
        {emergeEmiExtension && !emergeEmiExtension.trusted && <div className="stack-warning">EMerge Suite needs session trust before its local runtime can run.</div>}
        <fieldset className="emerge-update-setup" disabled={emergeUpdates.running}><div data-guide="emerge-emi-setup"><EMergeSetupForm gerberSource={gerberSource} gerberRuntime={emergeEmiRuntime} onOpenGerber={openNativeGerber} value={emergeEmiSetup} onChange={value => { if (value.python_executable !== emergeEmiSetup.python_executable) { emergeProbePathRef.current = value.python_executable.trim(); setEmergeEmiRuntime(null); } setEmergeEmiSetup(value); invalidateEMergePreview(); setEmergeEmiError(""); }} netOptions={[...new Set(Object.values(boardData?.nets ?? {}))].sort()} padOptions={(boardData?.pads ?? []).map(pad => pad.id).filter(Boolean).sort()} boardPads={boardData?.pads} copperLayerOrder={boardData?.stackup.filter(layer => layer.name.endsWith(".Cu")).map(layer => layer.name)} boardBounds={boardData?.bounds} /></div></fieldset>
        <EMergeRuntimeUpdater controller={emergeUpdates.controller} state={emergeUpdates.state} python={emergeEmiSetup.python_executable} disabled={!workerAvailable || universalRunning || emergeEmiOperationBusy} running={emergeUpdates.running}/>
        <div className="wizard-actions">
          <button className="secondary-btn" data-guide="emerge-emi-probe" disabled={emergeEmiBusy || !emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled"} onClick={() => void probeEmiEmerge()}><Activity size={14} /> {emergeEmiBusy ? "Checking or running…" : "Check EMerge runtime"}</button>
          {!emergeSiOpen && <><button className="secondary-btn" disabled={!boardData || emergeEmiBusy} onClick={() => void openSavedEmergeRadiation()}>Open saved radiation result</button><input ref={savedEmergeInputRef} type="file" accept=".json" style={{ display: "none" }} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void file.text().then(text => showSavedEmergeRadiation(JSON.parse(text))).catch(error => setEmergeEmiError(String(error))); }} /></>}
          <button className="secondary-btn" onClick={() => { invalidateEMergePreview(); setEmergeEmiOpen(false); setEmergeSiOpen(false); void openExtensionManager("spike.emerge-suite"); }}><Puzzle size={14} /> Extension manager</button>
        </div>
        <button className="secondary-btn" disabled={!boardData || emergeEmiBusy || !emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled"} onClick={() => { setEmergeEmiBusy(true); invalidateEMergePreview(); try { const parameters = { ...emergeParameters(emergeEmiSetup, gerberSource ? "gerber" : "board"), preview_radiation: !emergeSiOpen }; void invokeExtension("spike.emerge-suite", "emerge-preview", parameters).finally(() => setEmergeEmiBusy(false)); } catch (error) { setEmergeEmiError(String(error)); setEmergeEmiBusy(false); } }}>{emergeSiOpen ? "Preview SI Python" : "Preview radiation Python"}</button>
        {gerberSource && <button className="secondary-btn" disabled={emergeEmiBusy || gerberRunBlocked || !workerAvailable} title="Generate a native EMerge mesh and inspect the original Gerber copper and explicit ports" onClick={() => { setEmergeEmiBusy(true); try { void invokeExtension("spike.emerge-suite", "emerge-mesh", emergeParameters(emergeEmiSetup, "gerber")).finally(() => setEmergeEmiBusy(false)); } catch (error) { setEmergeEmiError(String(error)); setEmergeEmiBusy(false); } }}><Layers3 size={15}/>Prepare native Gerber mesh</button>}
        <EMergeScriptPreview data={emergeScriptPreview} />
        <EMergeCapabilityInventory rows={emergeEmiRuntime?.feature_inventory ?? emergeScriptPreview?.capabilities} />
        {emergeEmiRuntime && <div className="extension-output"><div className="extension-output-title"><b>{emergeEmiRuntime.available === true ? `EMerge ${String(emergeEmiRuntime.version ?? "")} ready` : "EMerge runtime unavailable"}</b></div><small>{emergeEmiRuntime.available === true ? `Available: ${emergeEmiCapabilities.join(", ") || "none"}` : String(emergeEmiRuntime.reason ?? "Runtime check failed.")}</small></div>}
        {emergeEmiError && <p role="alert">{emergeEmiError}</p>}
        <div className="extension-contributions"><label>AVAILABLE EMERGE ANALYSES</label>
          {!emergeSiOpen && <div><span><b>Radiation pattern</b><small>3D relative far field, angular cut, and S-parameters</small></span><button data-guide="emerge-emi-run-radiation" disabled={emergeEmiBusy || gerberRunBlocked || !boardData || !emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled" || emergeEmiRuntime?.available !== true || !emergeEmiCapabilities.includes("radiation_pattern")} onClick={() => void runEmiEmerge("emerge-radiation")}><Play size={12} /> Run</button></div>}
          <div><span><b>SI / S-parameters</b><small>Frequency-domain port sweep and phase</small></span><button data-guide="emerge-si-run" disabled={emergeEmiBusy || gerberRunBlocked || !boardData || !emergeEmiExtension?.trusted || emergeEmiExtension.state === "disabled" || emergeEmiRuntime?.available !== true || !emergeEmiCapabilities.includes("si_s_parameters")} onClick={() => void runEmiEmerge("emerge-si")}><Play size={12} /> Run</button></div>
        </div>
        {extensionResult?.status === "failed" && <p role="alert">{String((extensionResult.data as Record<string, unknown> | undefined)?.error ?? "EMerge run failed.")}</p>}
        {(emergeSiOpen ? Boolean(emergeSiPanelResult) : Boolean((extensionResult?.data as Record<string, unknown> | undefined)?.analysis_result)) && <div data-guide={emergeSiOpen ? "emerge-si-result" : "emerge-emi-result"}><EMergeResultPlot result={emergeSiOpen ? emergeSiPanelResult : extensionResult} frequencyIndex={emergePatternIndex} onFrequencyIndexChange={setEmergePatternIndex} />{!emergeSiOpen && emergePatterns.length > 0 && <button className="secondary-btn" onClick={() => { setEmergeEmiOpen(false); setEmiChamberOpen(true); setEmiDashboardOpen(false); }}>View radiation on bench</button>}</div>}
      </div>
      <div className="extension-footer"><span>Only capabilities reported by the selected EMerge runtime are enabled.</span><button className="secondary-btn" onClick={() => { setEmergeEmiOpen(false); setEmergeSiOpen(false); }}>Close</button></div>
    </div></div>}
    {siProtocolSuitesOpen && <Suspense fallback={null}><SiProtocolSuiteWorkbench
      extensionSuites={extensionProtocolSuites}
      onClose={() => setSiProtocolSuitesOpen(false)}
      onStatus={setStatus}
      onOpenTopology={() => { setSiProtocolSuitesOpen(false); setTopologyEditor("si"); }}
      onOpenNetwork={suite => { setSelectedSiSuite(suite); setSiProtocolSuitesOpen(false); openSiWorkbench("geometry", "channel", true); }}
      onOpenExtensions={() => { setSiProtocolSuitesOpen(false); void openExtensionManager(); }}
    /></Suspense>}
    {externalEnginesOpen && <Suspense fallback={<div className="modal-backdrop"><div className="modal-loading">Loading external-engine catalog...</div></div>}><ExternalEngineCenter extensionWorkflows={<><h3>Extension meshing and solving</h3><p>Choose a declared engine workflow to configure it directly in the SPIKE workspace. Runtime detection and mesh completion retain their own qualification status.</p>{(["mesh", "pi", "si", "em", "thermal"] as ExtensionWorkspace[]).flatMap(workspace => extensionWorkspaceRoutes(extensionCatalog, workspace).map(route => <p key={route.key}><button className="secondary-btn" onClick={() => { setSolverSelections(current => ({ ...current, [`extension_${workspace}`]: route.key })); setTab(workspace === "mesh" ? "Mesh" : workspace === "si" ? "HF / SI" : workspace === "em" ? "EM" : workspace === "thermal" ? "Thermal" : "PI"); setRightOpen(true); setExternalEnginesOpen(false); markProjectDirty(); }}>{workspace.toUpperCase()} · {route.extensionName} · {route.label}</button><small> {route.modelStatus} · {route.trusted ? "trusted" : "trust required"}</small></p>))}</>} engines={externalEngineCatalog} accelerators={accelerationCatalog} manager={solverManager} solverSelections={solverSelections} selectedNets={externalNetSelection} designAvailable={Boolean(boardData)} caseState={externalCase} busy={externalEngineBusy} onClose={() => setExternalEnginesOpen(false)} onRefresh={() => void refreshExternalEngines()} onPrepare={engineId => void prepareExternalEngine(engineId)} onRun={(engineId, setupOnly) => void runExternalEngine(engineId, setupOnly)} onRegister={(engineId, path) => void registerExternalSolver(engineId, path)} onUnregister={engineId => void unregisterExternalSolver(engineId)} onTune={(targetId, values) => void tuneManagedSolver(targetId, values)} onSelectSolver={(workloadId, selectedSolverId) => void selectManagedSolver(workloadId, selectedSolverId)} /></Suspense>}
    {shortcutsOpen && <ShortcutWindow shortcuts={shortcuts} onAssign={assignShortcut} onReset={() => setShortcuts(defaultShortcuts)} onClose={() => setShortcutsOpen(false)} />}
    <UniversalSearch open={globalSearchOpen} items={universalSearchItems} onClose={() => setGlobalSearchOpen(false)} />
    {searchQuery && <SearchPanel query={searchQuery} board={boardData} onClose={() => setSearchQuery("")} onSelect={handleSelect} />}
    {viewportContext && <ViewportContextMenu
      request={viewportContext}
      tab={tab}
      viewMode={viewMode}
      isolated={Boolean(isolatedNet)}
      onClose={() => setViewportContext(null)}
      onFit={() => commandCamera("fit")}
      onCenterOrbit={() => {
        const point = viewportContext.focusPoint;
        if (!point) return;
        setCameraCommand(`orbit-target:${point.join(",")}:${Date.now()}`);
      }}
      onToggleView={() => setViewMode(current => current === "2D" ? "3D" : "2D")}
      onLayers={() => openBoardManager("layers")}
      onCopy={() => void Promise.resolve().then(() => navigator.clipboard.writeText(JSON.stringify(viewportContext.object, null, 2))).catch(error => setStatus(`Copy failed: ${String(error)}`))}
      onOpenScript={() => { try { openContextScript({ kind: "selection", title: viewportContext.object?.name ?? "Viewport", payload: { object: viewportContext.object, board: boardFile, board_instance_id: selectedBoardInstanceId, object_position_units: "mm", scene_focus_point: viewportContext.focusPoint, scene_focus_frame: "Centered, Y-inverted and render-scaled viewport coordinates; not source board coordinates" } }); } catch (error) { setStatus(String(error)); } }}
      onClear={() => setSelected(null)}
      onProbe={() => viewportContext.object && addProbe(viewportContext.object)}
      onAddPowerNet={() => { const net = viewportContext.object?.net; if (net && !powerNets.includes(net)) setPowerNets(current => [...current, net]); if (net) focusManagedNet(net); openBoardManager("nets"); }}
      onIsolate={() => { const net = viewportContext.object?.net; if (!net) return; recordChange(); setIsolatedNet(isolatedNet ? null : net); setStatus(isolatedNet ? "Complete board restored" : `${net} isolated across all copper layers`); }}
      onWorkspace={() => {
        const object = viewportContext.object;
        if (object?.net) selectNetForAnalysis(object.net, "viewport");
        if (tab === "PI") openAnalysisSetup();
        else if (tab === "HF / SI") { setResultVisualizerDomain("si"); setResultVisualizerOpen(true); }
        else if (tab === "EM") { setRightOpen(true); if (object?.net && !emiSetup.selected_nets.includes(object.net)) setEmiSetup(current => ({ ...current, selected_nets: [...current.selected_nets, object.net!], net_metrics: [...current.net_metrics, { net: object.net!, source: "unassigned", dv_dt_v_per_s: 0, di_dt_a_per_s: 0, peak_current_a: 0, loop_area_mm2: 0, return_discontinuities: 0 }] })); setStatus(object?.net ? `${object.net} added to the EMI test domain` : "EMI test setup opened"); }
        else if (tab === "Thermal") setThermalOpen(true);
        else if (tab === "Probes") { if (object) addProbe(object); setDock("Probe table"); }
        else if (tab === "Results") setResultVisualizerOpen(true);
        else if (tab === "Reports") generateReport();
        else if (tab === "Settings") setPreferencesOpen(true);
        else validateDesign();
      }}
    />}
  </div>;
}

function RevisionComparisonDialog({ comparison, onClose }: { comparison: RevisionComparison; onClose: () => void }) {
  return <div className="modal-backdrop"><div className="revision-comparison-modal">
    <div className="modal-heading"><div><b>PI REVISION COMPARISON</b><small>{comparison.baselineName} to {comparison.candidateName}</small></div><button className="icon-btn" onClick={onClose} title="Close comparison"><X size={16} /></button></div>
    <div className={`comparison-verdict ${comparison.status}`}><ShieldAlert size={18} /><div><b>{comparison.status === "pass" ? "NO REGRESSION DETECTED" : "PI REGRESSION DETECTED"}</b><small>Candidate changes above {comparison.tolerancePercent.toFixed(1)}% are regressions. Lower PI loss/drop values are improvements.</small></div></div>
    <div className="comparison-table"><div className="comparison-header"><b>Metric</b><b>Baseline</b><b>Candidate</b><b>Change</b></div>{comparison.metrics.map(metric => <div key={metric.key} className={metric.status}><span>{metric.label}<small>{metric.unit}</small></span><b>{metric.baseline.toExponential(5)}</b><b>{metric.candidate.toExponential(5)}</b><strong>{Number.isFinite(metric.changePercent) ? `${metric.changePercent >= 0 ? "+" : ""}${metric.changePercent.toFixed(3)}%` : "+inf"}</strong></div>)}</div>
    <div className="wizard-actions"><button className="run-btn" onClick={onClose}>Close</button></div>
  </div></div>;
}

function ResourceMonitor({ open, setOpen, resources, render, board }: { open: boolean; setOpen: (value: boolean) => void; resources: ProcessResources; render: RenderTelemetry; board: ParsedBoard | null }) {
  const megabytes = (bytes: number | null) => bytes === null ? "--" : `${(bytes / 1024 ** 2).toFixed(bytes >= 1024 ** 3 ? 0 : 1)} MiB`;
  const memoryPercent = systemMemoryPercent(resources);
  const percentage = (value: number | null | undefined) => value == null ? "--" : `${value.toFixed(1)}%`;
  const stressed = (resources.cpuPercent ?? 0) >= 80 || (resources.capacityCpuPercent ?? 0) >= 80 || (memoryPercent ?? 0) >= 80 || render.frameTimeMs >= 25;
  return <div className="resource-monitor">
    <button className={stressed ? "resource-summary stressed" : "resource-summary"} onClick={() => setOpen(!open)} title="Open resource monitor" aria-label="Resource monitor" aria-expanded={open}>
      <Activity size={12} />
      <span>CPU {resources.cpuPercent === null ? "--" : `${resources.cpuPercent.toFixed(0)}%`}</span>
      <span>{resources.source === "desktop" ? "RAM system" : "HEAP"} {percentage(memoryPercent)}</span>
      <span>GPU {percentage(resources.gpu?.processPercent)}</span>
      <span>{render.fps ? `${render.fps.toFixed(0)} FPS` : "FPS --"}</span>
    </button>
    {open && <div className="resource-popover">
      <div><b>RESOURCE MONITOR</b><span>{resources.source === "desktop" ? `SPIKE process tree${resources.workerActive ? " · worker active" : ""}` : "Browser preview"}</span></div>
      <dl>
        <dt>SPIKE CPU / machine capacity</dt><dd>{percentage(resources.cpuPercent)}</dd>
        <dt>System CPU</dt><dd>{percentage(resources.systemCpuPercent)}</dd>
        <dt>CPU allocation</dt><dd>{resources.workerThreads ?? "--"} worker threads / {resources.logicalCpus ?? "?"} logical CPUs</dd>
        <dt>{resources.source === "desktop" ? resources.memoryKind === "private-resident" ? "SPIKE private resident RAM" : "Summed working sets (shared pages repeat)" : "JavaScript heap"}</dt><dd>{megabytes(resources.memoryBytes)}</dd>
        {resources.source === "desktop" && <><dt>Desktop host RSS</dt><dd>{megabytes(resources.hostMemoryBytes)}</dd><dt>Tracked processes</dt><dd>{resources.processCount ?? "--"}</dd></>}
        <dt>Frame CPU work</dt><dd>{render.frameTimeMs ? `${render.frameTimeMs.toFixed(1)} ms` : "--"}</dd>
        <dt>Renderer</dt><dd>{render.drawCalls} calls | {render.triangles.toLocaleString()} triangles</dd>
        <dt>GPU objects</dt><dd>{render.geometries} geometry | {render.textures} textures</dd>
        <dt>{resources.source === "desktop" ? "System RAM" : "JS heap"}</dt><dd>{megabytes(resources.source === "desktop" ? resources.systemUsedMemoryBytes ?? null : resources.memoryBytes)} / {megabytes(resources.totalMemoryBytes)}</dd>
        <dt>GPU busy engine · SPIKE</dt><dd>{percentage(resources.gpu?.processPercent)}</dd>
        <dt>GPU busy engine · system</dt><dd>{percentage(resources.gpu?.systemPercent)}</dd>
        <dt>GPU dedicated memory · process sum</dt><dd>{megabytes(resources.gpu?.dedicatedMemoryBytes ?? null)}</dd>
        <dt>GPU shared memory · process sum</dt><dd>{megabytes(resources.gpu?.sharedMemoryBytes ?? null)}</dd>
        <dt>GPU counter status</dt><dd>{resources.gpu?.status?.replace(/_/g, " ") ?? "Unavailable on this runtime"}</dd>
        <dt>Scene input</dt><dd>{board ? `${board.tracks.length} tracks | ${board.vias.length} vias | ${board.components.length} parts` : "No board"}</dd>
        <dt>Render scale</dt><dd>{render.pixelRatio.toFixed(2)}x adaptive</dd>
      </dl>
      {resources.source === "browser" ? <p>CPU and full process RSS are exposed by the packaged desktop host.</p> : <p>GPU memory sums SPIKE process counters; allocations shared between processes can be counted more than once.</p>}
    </div>}
  </div>;
}

function SetupPanel({ analysisMode, setAnalysisMode, solverId, setSolverId, formulation, setFormulation, solverCatalog, powerNets, limits, setLimits, piSetup, onNetManager, onConfigure, onStackup }: { analysisMode: string; setAnalysisMode: (value: string) => void; solverId: string; setSolverId: (value: string) => void; formulation: string; setFormulation: (value: string) => void; solverCatalog: SolverCatalogEntry[]; powerNets: string[]; limits: { drop: string; density: string }; setLimits: (value: { drop: string; density: string }) => void; piSetup: PiSetup; onNetManager: () => void; onConfigure: () => void; onStackup: () => void }) {
  const selectNet = (net: string) => window.dispatchEvent(new CustomEvent("spike-analysis-net-selected", { detail: { net } }));
  const requestedAnalysis = analysisMode === "AC Impedance Sweep" ? "ac" : analysisMode === "Transient PI" ? "transient" : "dc";
  const executable = (solver: SolverCatalogEntry) => solver.runnable !== false && ["available", "experimental"].includes(solver.state);
  const compatible = (solver: SolverCatalogEntry) => solver.analyses.includes(requestedAnalysis);
  const solverOptions = solverCatalog.filter(solver => (executable(solver) && compatible(solver)) || solver.id === solverId);
  const formulationOptions = Array.from(new Set(solverOptions.filter(executable).flatMap(solver => solver.formulations))).map(value => ({
    value,
    enabled: solverCatalog.some(solver => executable(solver) && compatible(solver) && solver.formulations.includes(value)),
  }));
  const formulationName = (value: string) => ({
    resistive_network: "Resistive network",
    peec_2_5d: "PEEC 2.5D",
    peec_rl_transient: "PEEC RLC transient",
    modified_nodal_analysis: "Modified nodal analysis",
    mom_surface: "Surface MoM",
    fem_3d: "FEM 3D",
    fdtd_3d: "FDTD 3D",
    volume_rl_extraction: "3D conductor R/L extraction",
  }[value] ?? value);
  const solverStateLabel = (solver: SolverCatalogEntry) => {
    if (solver.state === "available") return "";
    if (solver.state === "runtime_verified_adapter_pending") return " - runtime ready; PCB adapter pending";
    if (solver.state.includes("adapter_pending")) return " - PCB adapter pending";
    return ` - ${solver.state.replace(/_/g, " ")}`;
  };
  const selectedSolver = solverCatalog.find(solver => solver.id === solverId);
  return <>
    <div className="setup-block"><label>ANALYSIS MODE</label><select className="select-control" value={analysisMode} onChange={event => { setAnalysisMode(event.target.value); setSolverId("auto"); setFormulation("auto"); }}><option>DC IR Drop</option><option>Bulk Net Analysis</option><option>AC Impedance Sweep</option><option>Transient PI</option></select></div>
    <div className="setup-block"><label>SOLVER ENGINE</label><select className="select-control" value={solverId} onChange={event => { setSolverId(event.target.value); setFormulation("auto"); }}><option value="auto">Auto-select compatible engine</option>{solverOptions.map(solver => <option key={solver.id} value={solver.id} disabled={!executable(solver) || !compatible(solver)} title={solver.reason}>{solver.name}{solverStateLabel(solver)}</option>)}</select><label className="setup-sublabel">FORMULATION</label><select className="select-control" value={formulation} onChange={event => setFormulation(event.target.value)}><option value="auto">Automatic formulation</option>{formulationOptions.map(option => <option key={option.value} value={option.value} disabled={!option.enabled}>{formulationName(option.value)}</option>)}</select>{selectedSolver?.reason && <div className="range-note"><ShieldAlert size={13} /> {selectedSolver.reason}</div>}</div>
    <div className="setup-block"><label>MANAGED NETS</label>{powerNets.slice(0, 4).map((net, index) => <div className={`selected-net selectable ${piSetup.net === net ? "active" : ""}`} key={net} role="button" tabIndex={0} onMouseEnter={() => previewViewportTarget({ kind: "net", net, label: net })} onMouseLeave={() => previewViewportTarget(null)} onClick={() => selectNet(net)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") selectNet(net); }}><span className={`net-swatch ${index === 0 ? "red" : "blue"}`} />{net}<b>{index === 0 ? "Source" : /(^|[\/_-])(gnd|ground|return|0v)([\/_-]|$)/i.test(net) ? "Return" : "Series"}</b></div>)}{powerNets.length > 4 && <div className="range-note">+{powerNets.length - 4} additional managed nets</div>}<button className="secondary-btn compact-manager-button" onClick={onNetManager}><ListTree size={15} /> Open Net Manager</button><div className="range-note"><Network size={13} /> Open the Power Tree from Net Manager for cross-net series diagrams.</div></div>
    <div className="setup-block"><label>TERMINALS</label><button className="select-control terminal-summary" onClick={onConfigure}><span>{piSetup.sources.length} source{piSetup.sources.length === 1 ? "" : "s"} · {piSetup.loads.length} sink{piSetup.loads.length === 1 ? "" : "s"}</span><SlidersHorizontal size={15} /></button></div>
    {requestedAnalysis === "ac" ? <div className="setup-block"><label>FREQUENCY SWEEP</label><button className="select-control terminal-summary" onClick={onConfigure}><span>{piSetup.frequencyStart} Hz to {piSetup.frequencyStop} Hz | {piSetup.frequencyPoints} points</span><SlidersHorizontal size={15} /></button><div className="range-note"><Activity size={13} /> Skin effect {piSetup.skinEffect ? "enabled" : "disabled"}; conductor corrections are passed to the selected PEEC engine</div></div> : requestedAnalysis === "transient" ? <div className="setup-block"><label>TIME WINDOW</label><button className="select-control terminal-summary" onClick={onConfigure}><span>{piSetup.transientStopS} | step {piSetup.transientTimeStepS}</span><Activity size={15} /></button><div className="range-note"><Activity size={13} /> Geometry-derived experimental PEEC RLC transient</div></div> : null}
    <div className="setup-block"><label>LIMITS</label><div className="limit-row"><span>Max voltage drop</span><input value={limits.drop} onChange={event => setLimits({ ...limits, drop: event.target.value })} /><small>mV</small></div><div className="limit-row"><span>Max current density</span><input value={limits.density} onChange={event => setLimits({ ...limits, density: event.target.value })} /><small>A/mm²</small></div></div>
    <div className="setup-footer"><Issue kind="warning" title={requestedAnalysis === "transient" ? "Experimental RLC transient" : requestedAnalysis === "ac" ? "Experimental PEEC extraction" : "Approximate engine"} detail={requestedAnalysis === "transient" ? "Time-domain resistance and partial inductance are solved on extracted geometry. Optional stackup capacitance is a single-reference approximation; via capacitance, dielectric loss, full-wave propagation, and nonlinear devices remain unsupported." : requestedAnalysis === "ac" ? "The native quasi-static PEEC engine extracts conductor R/partial-L and adds validity-bounded single-reference C/G where stackup data permits. Proximity effect, via/antipad capacitance, and multiconductor electrostatics remain unsupported." : "Every result records the selected engine, formulation, assumptions, and geometry handoff contract."} /><button className="secondary-btn" onClick={onStackup}><Settings2 size={15} /> Edit stackup</button></div>
  </>;
}
/* Legacy setup body retained below until the full source-net editor is migrated. */
function LegacySetupPanel({ frequency, setFrequency, onStackup }: { frequency: string; setFrequency: (value: string) => void; onStackup: () => void }) {
  return <><div className="setup-block"><label>ANALYSIS MODE</label><button className="select-control">DC IR Drop <ChevronDown size={15} /></button></div><div className="setup-block"><label>POWER NETS</label><div className="selected-net"><span className="net-swatch red" />+1V8_CORE <b>Source</b><XCircle size={14} /></div><div className="selected-net"><span className="net-swatch blue" />GND <b>Return</b><XCircle size={14} /></div><button className="add-btn"><Plus size={13} /> Add net</button></div><div className="setup-block"><label>FREQUENCY RANGE</label><div className="input-pair"><input value="10 kHz" readOnly /><span>to</span><select value={frequency} onChange={e => setFrequency(e.target.value)}><option>10 MHz</option><option>100 MHz</option><option>1 GHz</option></select></div><div className="range-note"><Activity size={13} /> HF modes are pipeline-only</div></div><div className="setup-block"><label>LIMITS</label><div className="limit-row"><span>Max voltage drop</span><input value="50" readOnly /><small>mV</small></div><div className="limit-row"><span>Max current density</span><input value="100" readOnly /><small>A/mm²</small></div></div><div className="setup-footer"><Issue kind="error" title="Stackup incomplete" detail="AC validity is limited until dielectric data is supplied." /><button className="secondary-btn" onClick={onStackup}><Settings2 size={15} /> Edit stackup</button></div></>;
}
const metadataNumber = (value: number, digits = 3) => Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : "--";
const polygonArea = (points: [number, number][]) => Math.abs(points.reduce((sum, point, index) => {
  const next = points[(index + 1) % points.length];
  return sum + point[0] * next[1] - next[0] * point[1];
}, 0) / 2);
function MetadataSection({ title, rows }: { title: string; rows: [string, string][] }) {
  if (!rows.length) return null;
  return <section className="metadata-section"><h4>{title}</h4><div className="property-grid">{rows.map(([label, value]) => <div className="property-row" key={`${title}-${label}`}><span>{label}</span><b title={value}>{value}</b></div>)}</div></section>;
}
function Inspector({ board, object, selectionFilter, isolated, assignedModel, onClear, onProbe, onIsolate, onModelLibrary }: { board: ParsedBoard | null; object: BoardObject; selectionFilter: SelectionFilter; isolated: boolean; assignedModel?: string; onClear: () => void; onProbe: () => void; onIsolate: () => void; onModelLibrary: () => void }) {
  const component = board?.components.find(item => item.id === object.id || item.ref === object.ref);
  const pad = board?.pads.find(item => item.id === object.id);
  const via = board?.vias.find(item => item.id === object.id);
  const track = board?.tracks.find(item => item.id === object.id);
  const zone = board?.zones.find(item => item.id === object.id);
  const componentPads = component && board ? board.pads.filter(item => item.ref === component.ref) : [];
  const componentNets = [...new Set(componentPads.map(item => item.net).filter((value): value is string => Boolean(value)))];
  const objectRows: [string, string][] = [
    ["Object", object.type],
    ["ID", object.id],
    ...(object.position ? [["Coordinate", `${metadataNumber(object.position[0], 4)}, ${metadataNumber(object.position[1], 4)} mm`] as [string, string]] : []),
    ...(object.layer ? [["Picked layer", object.layer] as [string, string]] : []),
  ];
  if (component) objectRows.push(
    ["Reference", component.ref], ["Value", component.value || "Not assigned"], ["Footprint", component.library || "Not assigned"],
    ["Origin", `${metadataNumber(component.at[0], 4)}, ${metadataNumber(component.at[1], 4)} mm`], ["Side", component.layer], ["Rotation", `${metadataNumber(component.rotation, 2)} deg`],
    ["Envelope", `${metadataNumber(component.width)} x ${metadataNumber(component.height)} mm`],
    ["Mount", componentPads.some(item => item.drill > 0) ? "Through-hole" : "Surface-mount"],
    ["Pads", String(componentPads.length)], ["Connected nets", componentNets.length ? componentNets.join(", ") : "None resolved"],
    ["3D model", assignedModel?.split(/[\\/]/).pop() || component.modelPath?.split(/[\\/]/).pop() || (component.model ? "Resolved in imported scene" : "Not assigned")],
  );
  if (pad) objectRows.push(["Pad", `${pad.ref ?? "?"}.${pad.name}`], ["Shape", pad.shape], ["Size", `${metadataNumber(pad.width)} x ${metadataNumber(pad.height)} mm`], ["Drill", pad.drill > 0 ? `${metadataNumber(pad.drill)} mm` : "None"], ["Layers", pad.layers.join(", ")]);
  if (via) objectRows.push(["Diameter", `${metadataNumber(via.size)} mm`], ["Drill", `${metadataNumber(via.drill)} mm`], ["Span", via.layers.join(" to ")]);
  if (track) objectRows.push(["Width", `${metadataNumber(track.width)} mm`], ["Length", `${metadataNumber(Math.hypot(track.end[0] - track.start[0], track.end[1] - track.start[1]), 4)} mm`], ["Start", `${metadataNumber(track.start[0], 4)}, ${metadataNumber(track.start[1], 4)} mm`], ["End", `${metadataNumber(track.end[0], 4)}, ${metadataNumber(track.end[1], 4)} mm`]);
  if (zone) objectRows.push(["Vertices", String(zone.points.length)], ["Polygon area", `${metadataNumber(polygonArea(zone.points), 4)} mm2`]);

  const net = object.net;
  const netTracks = board && net ? board.tracks.filter(item => item.net === net) : [];
  const netVias = board && net ? board.vias.filter(item => item.net === net) : [];
  const netPads = board && net ? board.pads.filter(item => item.net === net) : [];
  const netZones = board && net ? board.zones.filter(item => item.net === net) : [];
  const netLayers = [...new Set([
    ...netTracks.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], [item.layer])),
    ...netZones.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], [item.layer])),
    ...netPads.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], item.layers)),
    ...netVias.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], item.layers)),
  ])];
  const routeLength = netTracks.reduce((sum, item) => sum + Math.hypot(item.end[0] - item.start[0], item.end[1] - item.start[1]), 0);
  const widths = netTracks.map(item => item.width);
  const connectedParts = [...new Set(netPads.map(item => item.ref).filter((value): value is string => Boolean(value)))];
  const netRows: [string, string][] = net ? [
    ["Name", net], ["Copper layers", netLayers.length ? netLayers.join(", ") : "None resolved"],
    ["Routed segments", String(netTracks.length)], ["Route length", `${metadataNumber(routeLength, 4)} mm`],
    ["Trace width", widths.length ? `${metadataNumber(numericMinimum(widths))} / ${metadataNumber(widths.reduce((sum, value) => sum + value, 0) / widths.length)} / ${metadataNumber(numericMaximum(widths))} mm (min/avg/max)` : "No routed segments"],
    ["Vias", String(netVias.length)], ["Pads", String(netPads.length)], ["Copper zones", String(netZones.length)],
    ["Zone polygon area", `${metadataNumber(netZones.reduce((sum, item) => sum + polygonArea(item.points), 0), 4)} mm2`],
    ["Connected parts", connectedParts.length ? connectedParts.join(", ") : "None resolved"],
  ] : [];
  const primaryType = selectionFilter === "net" && net ? "NET" : object.type.toUpperCase();
  const title = selectionFilter === "net" && net ? net : component ? `${component.ref} ${component.value}`.trim() : object.name;
  return <div className="inspector"><div className="selection-badge"><span className="status-dot" /> {primaryType}<button onClick={onClear} title="Clear selection"><X size={14} /></button></div><h3>{title}</h3><MetadataSection title={component ? "COMPONENT" : "SELECTED OBJECT"} rows={objectRows} /><MetadataSection title="COMPLETE NET" rows={netRows} /><div className="inspector-actions"><button className="secondary-btn" onClick={onProbe}><RadioTower size={15} /> Add probe</button>{net && <button className={`secondary-btn ${isolated ? "selected" : ""}`} onClick={onIsolate}><Focus size={15} /> {isolated ? "Exit net isolation" : "Isolate complete net"}</button>}{object.type === "component" && <button className="secondary-btn" onClick={onModelLibrary}><FolderOpen size={15} /> Browse global model library</button>}</div></div>;
}

function HarnessInspector({ harness, onClear }: { harness: VirtualHarnessVisual; onClear: () => void }) {
  const rows: [string, string][] = [
    ["Harness ID", harness.id],
    ["Endpoint A", `${harness.endpointA.boardId}::${harness.endpointA.connectorId}`],
    ["Endpoint B", `${harness.endpointB.boardId}::${harness.endpointB.connectorId}`],
    ["Length", harness.lengthMm > 0 ? `${metadataNumber(harness.lengthMm)} mm` : "Not specified"],
    ["Viewport status", "Virtual visual only; no PI/SI coupling is inferred"],
  ];
  return <div className="inspector"><div className="selection-badge"><span className="status-dot" /> HARNESS<button onClick={onClear} title="Clear harness selection"><X size={14} /></button></div><h3>{harness.name}</h3><MetadataSection title="VIRTUAL HARNESS" rows={rows} /></div>;
}

function BoardInstanceInspector({ board, onClear }: { board: VirtualBoardVisual; onClear: () => void }) {
  const rows: [string, string][] = [
    ["Board instance ID", board.id],
    ["Retained design ID", board.designId],
    ["Envelope", `${metadataNumber(board.widthMm)} × ${metadataNumber(board.heightMm)} mm`],
    ["Scene detail", "Retained geometry with available KiCad models; missing models use placeholders"],
    ["Physics status", "Placement visual only; no cross-board PI/SI coupling is inferred"],
  ];
  return <div className="inspector"><div className="selection-badge"><span className="status-dot" /> BOARD<button onClick={onClear} title="Clear board selection"><X size={14} /></button></div><h3>{board.name}</h3><MetadataSection title="ASSEMBLY BOARD" rows={rows} /></div>;
}

function ViewportContextMenu({ request, tab, viewMode, isolated, onClose, onFit, onCenterOrbit, onToggleView, onLayers, onCopy, onOpenScript, onClear, onProbe, onAddPowerNet, onIsolate, onWorkspace }: { request: ViewportContextRequest; tab: RibbonTab; viewMode: "2D" | "3D"; isolated: boolean; onClose: () => void; onFit: () => void; onCenterOrbit: () => void; onToggleView: () => void; onLayers: () => void; onCopy: () => void; onOpenScript: () => void; onClear: () => void; onProbe: () => void; onAddPowerNet: () => void; onIsolate: () => void; onWorkspace: () => void }) {
  const menu = useRef<HTMLDivElement>(null);
  const returnFocus = useRef(document.activeElement as HTMLElement | null);
  useEffect(() => {
    const element = menu.current; if (!element) return;
    const bounds = element.getBoundingClientRect();
    element.style.left = `${Math.max(8, Math.min(request.clientX, window.innerWidth - bounds.width - 8))}px`;
    element.style.top = `${Math.max(8, Math.min(request.clientY, window.innerHeight - bounds.height - 8))}px`;
    element.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus({ preventScroll: true });
  }, [request.clientX, request.clientY, request.object, tab, viewMode]);
  const object = request.object;
  const action = (callback: () => void) => () => { callback(); onClose(); };
  const taskLabel: Record<RibbonTab, string> = {
    Home: "Validate design context", PI: "Configure PI analysis", "HF / SI": "Open channel extraction", Mesh: "Open shared mesh controls", Solve: "Open shared solve controls", EM: "Add net to EM test domain", Thermal: "Configure thermal scenario",
    Probes: "Add measurement probe", Results: "Open result visualization", Reports: "Generate engineering report", Extensions: "Browse extension capabilities", Settings: "Open preferences",
  };
  const left = Math.max(8, Math.min(request.clientX, window.innerWidth - 260));
  const top = Math.max(8, Math.min(request.clientY, window.innerHeight - (object ? 410 : 250)));
  return <div ref={menu} className="viewport-context-menu" role="menu" aria-label="Viewport context menu" style={{ left, top, maxHeight: "calc(100vh - 16px)", overflowY: "auto" }} onPointerDown={event => event.stopPropagation()} onKeyDown={event => {
      event.stopPropagation();
      if (event.key === "Escape" || event.key === "Tab") { event.preventDefault(); onClose(); returnFocus.current?.focus({ preventScroll: true }); return; }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")], index = items.indexOf(document.activeElement as HTMLButtonElement);
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length]?.focus();
    }}>
    <div className="context-heading"><span>{object ? object.name : "Viewport"}</span><small>{object ? object.type : `${viewMode} view`}</small></div>
    <div className="context-group"><label>VIEW</label><button role="menuitem" onClick={action(onFit)}><Focus size={15} /> Fit board</button>{viewMode === "3D" && request.focusPoint && <button role="menuitem" onClick={action(onCenterOrbit)}><Crosshair size={15} /> Set orbit center here</button>}<button role="menuitem" onClick={action(onToggleView)}><Orbit size={15} /> Switch to {viewMode === "2D" ? "3D" : "2D"}</button><button role="menuitem" onClick={action(onLayers)}><Layers3 size={15} /> Layer manager</button></div>
    {object && <div className="context-group"><label>SELECTION</label><button role="menuitem" onClick={action(onCopy)}><Copy size={15} /> Copy metadata</button><button role="menuitem" title="Open selection metadata in an unsaved Python tab; no script is executed" onClick={action(onOpenScript)}><SquareTerminal size={15}/> Open in script</button><button role="menuitem" onClick={action(onProbe)}><RadioTower size={15} /> Add probe here</button>{tab === "PI" && object.net && <button role="menuitem" onClick={action(onAddPowerNet)}><ListTree size={15} /> Add to PI Net Manager</button>}{object.net && <button role="menuitem" onClick={action(onIsolate)}><Focus size={15} /> {isolated ? "Exit net isolation" : "Isolate complete net"}</button>}<button role="menuitem" onClick={action(onClear)}><X size={15} /> Clear selection</button></div>}
    <div className="context-group task"><label>{tab.toUpperCase()}</label><button role="menuitem" onClick={action(onWorkspace)}><Play size={15} /> {taskLabel[tab]}</button></div>
  </div>;
}
function StackupManager({ stackup, onClose }: { stackup: ParsedStackupLayer[]; onClose: () => void }) {
  const complete = stackup.some(layer => layer.name.endsWith(".Cu") && Boolean(layer.thickness))
    && stackup.some(layer => !layer.name.endsWith(".Cu") && Boolean(layer.thickness) && Boolean(layer.epsilonR));
  return <div className="modal-shade"><div className="floating-panel stackup-manager"><div className="floating-heading"><b>STACKUP MANAGER</b><button onClick={onClose}><X size={15} /></button></div><p className="modal-note">Imported KiCad material and dielectric data controls AC/HF validity.</p>{stackup.length ? stackup.map((row, index) => <div className="stack-row" key={`${row.name}-${index}`}><b>{row.name}</b><span>{row.thickness ? `${(row.thickness * 1000).toFixed(row.thickness < 0.1 ? 0 : 1)} µm` : "Not specified"}</span><em>{row.material || row.type}{row.epsilonR ? ` · εr ${row.epsilonR}` : ""}{row.lossTangent !== undefined ? ` · tanδ ${row.lossTangent}` : ""}</em>{row.thickness ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}</div>) : <div className="stack-warning"><AlertTriangle size={15} /> No stackup section was found in the imported design.</div>}{complete ? <div className="stack-valid"><CheckCircle2 size={15} /> Copper thickness and dielectric properties imported from KiCad.</div> : <div className="stack-warning"><AlertTriangle size={15} /> Complete dielectric thickness, permittivity, and loss tangent before broadband extraction.</div>}<button className="run-btn" onClick={onClose}>Close</button></div></div>;
}

function EditableStackupManager({ stackup, copperLayers, onSave, onClose }: { stackup: ParsedStackupLayer[]; copperLayers: string[]; onSave: (rows: ParsedStackupLayer[]) => void; onClose: () => void }) {
  const normalizedType = (row: ParsedStackupLayer) => {
    const identity = `${row.type} ${row.name}`.toLowerCase();
    if (row.name.endsWith(".Cu") || identity.includes("copper")) return "copper";
    if (identity.includes("prepreg")) return "prepreg";
    if (identity.includes("core") || identity.includes("dielectric")) return "core";
    if (identity.includes("solder mask") || identity.includes("soldermask") || row.name.endsWith(".Mask")) return "soldermask";
    if (identity.includes("silk") || row.name.endsWith(".SilkS")) return "silkscreen";
    if (identity.includes("paste") || row.name.endsWith(".Paste")) return "paste";
    return "other";
  };
  const [rows, setRows] = useState<ParsedStackupLayer[]>(() => {
    const imported = stackup.map(row => ({ ...row, type: normalizedType(row) }));
    const existing = new Set(imported.map(row => row.name));
    copperLayers.forEach((name, copperIndex) => {
      if (existing.has(name)) return;
      const nextName = copperLayers.slice(copperIndex + 1).find(candidate => existing.has(candidate));
      const nextIndex = nextName ? imported.findIndex(row => row.name === nextName) : -1;
      const unresolved: ParsedStackupLayer = { name, type: "copper" };
      if (nextIndex >= 0) imported.splice(nextIndex, 0, unresolved);
      else imported.push(unresolved);
      existing.add(name);
    });
    return imported;
  });
  const rowKeys = useRef(rows.map((_, index) => `layer-${index}`));
  const nextRowKey = useRef(rows.length);
  const patchRow = (index: number, patch: Partial<ParsedStackupLayer>) => setRows(current => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
  const isDielectric = (row: ParsedStackupLayer) => !row.name.endsWith(".Cu") && /core|prepreg|dielectric/i.test(`${row.type} ${row.name}`);
  const invalidIndexes = new Set(rows.map((row, index) => ({ row, index })).filter(({ row }) => row.name.endsWith(".Cu") ? !(Number(row.thickness) > 0) : isDielectric(row) && (!(Number(row.thickness) > 0) || !(Number(row.epsilonR) > 1) || !(Number(row.lossTangent) >= 0))).map(({ index }) => index));
  const complete = rows.some(row => row.name.endsWith(".Cu")) && rows.some(isDielectric) && invalidIndexes.size === 0;
  return <div className="modal-shade"><div className="floating-panel stackup-manager editable"><div className="floating-heading"><b>PHYSICAL STACKUP</b><button onClick={onClose} aria-label="Close stackup"><X size={15} /></button></div><p className="modal-note">Front → back · {rows.length} layers. Colors distinguish copper, brown substrate, solder mask and silkscreen. Edits are stored in this project.</p><div className="stackup-cross-section" aria-label="Physical board stackup">{rows.map((row, index) => <div className="stackup-cross-row" key={`${row.name}-${index}`}><strong>{row.name}</strong><div className="stackup-cross-band" style={{ backgroundColor: stackupColor(row), height: stackupBandHeight(row) }} title={`${row.name}: ${row.material ?? row.type}`} /><span>{row.thickness === undefined ? "—" : `${Number(row.thickness).toFixed(3)} mm`}</span></div>)}</div><div className="stack-table-body"><DataTable label="Physical stackup" className="stackup-entry-table" searchable={false}><thead><tr><th>Layer</th><th>Type</th><th>Thickness (um)</th><th>Material</th><th>Er</th><th>Loss tangent</th><th>Actions</th></tr></thead><tbody>{rows.map((row, index) => <tr className={invalidIndexes.has(index) ? "invalid" : ""} key={rowKeys.current[index]}><td><input value={row.name} onChange={event => patchRow(index, { name: event.target.value })} aria-label={`Layer ${index + 1} name`} /></td><td><select aria-label={`Layer ${index + 1} type`} value={row.type} onChange={event => patchRow(index, { type: event.target.value })}><option value="copper">Copper</option><option value="core">Core</option><option value="prepreg">Prepreg</option><option value="soldermask">Solder mask</option><option value="silkscreen">Silkscreen</option><option value="paste">Paste</option><option value="other">Other</option></select></td><td><input aria-label={`Layer ${index + 1} thickness (um)`} type="number" min="0" step="1" value={row.thickness === undefined ? "" : row.thickness * 1000} onChange={event => patchRow(index, { thickness: event.target.value === "" ? undefined : Number(event.target.value) / 1000 })} /></td><td><input aria-label={`Layer ${index + 1} material`} value={row.material ?? ""} onChange={event => patchRow(index, { material: event.target.value })} /></td><td><input aria-label={`Layer ${index + 1} relative permittivity`} type="number" min="1" step="0.01" disabled={!isDielectric(row)} value={row.epsilonR ?? ""} onChange={event => patchRow(index, { epsilonR: event.target.value === "" ? undefined : Number(event.target.value) })} /></td><td><input aria-label={`Layer ${index + 1} loss tangent`} type="number" min="0" step="0.001" disabled={!isDielectric(row)} value={row.lossTangent ?? ""} onChange={event => patchRow(index, { lossTangent: event.target.value === "" ? undefined : Number(event.target.value) })} /></td><td><button onClick={() => { rowKeys.current.splice(index, 1); setRows(current => current.filter((_, rowIndex) => rowIndex !== index)); }} title={`Delete ${row.name}`}><Trash2 size={13} /></button></td></tr>)}</tbody></DataTable></div><button className="secondary-btn stack-add" onClick={() => { rowKeys.current.push(`layer-${nextRowKey.current++}`); setRows(current => [...current, { name: `dielectric ${current.length + 1}`, type: "core", thickness: 0.1, material: "FR4", epsilonR: 4.2, lossTangent: 0.02 }]); }}><Plus size={14} /> Add layer</button>{complete ? <div className="stack-valid"><CheckCircle2 size={15} /> Stackup is complete for quasi-static AC/HF setup.</div> : <div className="stack-warning"><AlertTriangle size={15} /> {invalidIndexes.size} conductive or dielectric layer{invalidIndexes.size === 1 ? "" : "s"} require thickness, Er, and non-negative loss tangent.</div>}<div className="stack-actions"><button className="secondary-btn" onClick={onClose}>Cancel</button><button className="run-btn" disabled={!complete} onClick={() => { onSave(rows); onClose(); }}>Apply to project</button></div></div></div>;
}

function LegacyStackupManager({ onClose }: { onClose: () => void }) {
  const rows = [["F.Cu", "35 µm", "Copper"], ["Prepreg 1", "100 µm", "FR-4 · εr 4.2"], ["In1.Cu", "35 µm", "Copper"], ["Core", "800 µm", "FR-4 · εr 4.1"], ["In2.Cu", "35 µm", "Copper"], ["B.Cu", "35 µm", "Copper"]];
  return <div className="modal-shade"><div className="floating-panel stackup-manager"><div className="floating-heading"><b>STACKUP MANAGER</b><button onClick={onClose}><X size={15} /></button></div><p className="modal-note">Layer material and dielectric data controls AC/HF validity.</p>{rows.map(row => <div className="stack-row" key={row[0]}><b>{row[0]}</b><span>{row[1]}</span><em>{row[2]}</em><CheckCircle2 size={14} /></div>)}<div className="stack-warning"><AlertTriangle size={15} /> Add solder mask and loss tangent to unlock higher-frequency models.</div><button className="run-btn" onClick={onClose}>Save stackup</button></div></div>;
}

function ThermalWizard({ initialScenario, componentBonds, board, design, boardSource, workerAvailable, onRequireAdmission, onClose, onStatus, onPreview, onScenario }: { initialScenario: Record<string, unknown> | null; componentBonds: BondRecord[]; board: ParsedBoard | null; design: Record<string, unknown> | null; boardSource?: string | null; workerAvailable: boolean; onRequireAdmission: (workload: AssemblyWorkload) => Promise<AssemblyAnalysisScope | null>; onClose: () => void; onStatus: (value: string) => void; onPreview: (value: Record<string, unknown>) => void; onScenario: (value: Record<string, unknown>) => void }) {
  const initial = asThermalScenario(initialScenario);
  const [volume, setVolume] = useState({ x: String(initial?.bounding_volume_mm?.x ?? 160), y: String(initial?.bounding_volume_mm?.y ?? 100), z: String(initial?.bounding_volume_mm?.z ?? 60) });
  const [ambient, setAmbient] = useState(String(initial?.ambient_temperature_c ?? 25));
  const [power, setPower] = useState(String(initialScenario?.board_fallback_power_w ?? initial?.heat_sources?.[0]?.power_w ?? 8));
  const [thermalElements, setThermalElements] = useState<ThermalElement[]>(() => normalizeThermalElements(initial?.thermal_elements));
  const [thermalLinks, setThermalLinks] = useState<ThermalLink[]>(() => normalizeThermalLinks(initial?.thermal_links));
  const [thermalBoundaries, setThermalBoundaries] = useState<ThermalBoundary[]>(() => normalizeThermalBoundaries(initial?.thermal_boundaries));
  const [boardTopRth, setBoardTopRth] = useState(String(initial?.heat_sources?.[0]?.theta_top_c_per_w ?? 25));
  const [boardBottomRth, setBoardBottomRth] = useState(String(initial?.heat_sources?.[0]?.theta_bottom_c_per_w ?? 25));
  const [thermalCapacitance, setThermalCapacitance] = useState(String(initial?.heat_sources?.[0]?.thermal_capacitance_j_per_c ?? 20));
  const [mode, setMode] = useState<"steady_state" | "transient">((initialScenario?.mode as "steady_state" | "transient") ?? "steady_state");
  const [environment, setEnvironment] = useState(String(initialScenario?.application_environment ?? "industrial"));
  const [medium, setMedium] = useState<"air" | "vacuum" | "potting">((initial?.medium as "air" | "vacuum" | "potting") ?? "air");
  const [enclosure, setEnclosure] = useState<"open" | "sealed" | "vented_cabinet">((initial?.enclosure as "open" | "sealed" | "vented_cabinet") ?? "open");
  const [convection, setConvection] = useState<"none" | "natural" | "forced">((initial?.convection as "none" | "natural" | "forced") ?? "forced");
  const [radiation, setRadiation] = useState(Boolean((initialScenario?.options as { radiation?: boolean } | undefined)?.radiation));
  const [environmentProfile, setEnvironmentProfile] = useState<ThermalEnvironmentId>((initialScenario?.environment_profile as ThermalEnvironmentId | undefined) ?? "open_air");
  const [environmentAssumptions, setEnvironmentAssumptions] = useState<string[]>(() => Array.isArray(initialScenario?.environment_assumptions) ? initialScenario.environment_assumptions.map(String) : []);
  const [fans, setFans] = useState<ThermalFan[]>(() => normalizeThermalFans(initial?.fans, { x: Number(initial?.bounding_volume_mm?.x) || 160, y: Number(initial?.bounding_volume_mm?.y) || 100, z: Number(initial?.bounding_volume_mm?.z) || 60 }));
  const [heatsinks, setHeatsinks] = useState<ThermalHeatsink[]>(() => normalizeThermalHeatsinks(initial?.virtual_heatsinks));
  const [meshSize, setMeshSize] = useState(String(initial?.mesh?.cell_size_mm ?? 3));
  const [boundaryLayers, setBoundaryLayers] = useState(String(initial?.mesh?.boundary_layers ?? 3));
  const [maxCells, setMaxCells] = useState(String(initial?.mesh?.max_cells ?? 1000000));
  const [endTime, setEndTime] = useState(String(initial?.run?.end_time_s ?? 60));
  const [writeInterval, setWriteInterval] = useState(String(initial?.run?.write_interval_s ?? 1));
  const [maxIterations, setMaxIterations] = useState(String(initial?.run?.max_iterations ?? 2000));
  const [residualTarget, setResidualTarget] = useState(String(initial?.run?.residual_target ?? 0.000001));
  const [fieldResult, setFieldResult] = useState<unknown>(() => initial?.field_result ?? null);
  const [validation, setValidation] = useState<{ valid: boolean; solver_ready: boolean; issues: { severity: string; message: string }[]; capability?: { reason?: string } } | null>(null);
  const [preparedCase, setPreparedCase] = useState<{ status?: string; can_run?: boolean; case_dir?: string; message?: string; issues?: { severity: string; message: string }[] } | null>(null);
  const [runResult, setRunResult] = useState<{ status?: string; message?: string; result_contract?: string; result?: unknown } | null>(null);
  const [estimate, setEstimate] = useState<{ status: string; model_status: string; summary: { total_power_w: number; max_steady_temperature_c: number }; sources: { id: string; temperature_rise_c: number; steady_temperature_c: number; time_constant_s?: number }[]; issues: { severity: string; message: string }[] } | null>(null);
  type ComponentThermalResult = { contract: string; status: string; model_status: string; nodes: { id: string; component_ref: string; power_w: number; temperature_c: number; steady_temperature_c: number; heat_flow_top_w: number; heat_flow_bottom_w: number; peak_transient_temperature_c?: number; peak_transient_time_s?: number; time_to_90pct_steady_s?: number | null; final_to_steady_gap_c?: number }[]; surfaces?: (ThermalBoundary & { heat_flow_w: number })[]; transient: { time_s: number; temperatures_c: Record<string, number> }[]; summary: { total_power_w?: number; max_temperature_c?: number; steady_energy_balance_error_w?: number; peak_transient_temperature_c?: number }; issues: { severity: string; message: string }[] };
  const [nativeResult, setNativeResult] = useState<ComponentThermalResult | null>(() => (initialScenario?.component_result as ComponentThermalResult | undefined) ?? null);
  const [nativeResultInputKey, setNativeResultInputKey] = useState(String(initialScenario?.component_result_input_key ?? ""));
  const [nativeError, setNativeError] = useState("");
  const [busy, setBusy] = useState<"preflight" | "prepare" | "run" | "estimate" | "native" | null>(null);
  const advancedPhysics = medium !== "air" || enclosure !== "open" || radiation || fans.some(fan => fan.enabled) || heatsinks.some(heatsink => heatsink.enabled);
  const assemblyIssues = useMemo(() => thermalAssemblyIssues(thermalElements, thermalLinks), [thermalElements, thermalLinks]);
  const thermalScreening = useMemo(() => screenThermalElements(thermalElements, Number(ambient)), [ambient, thermalElements]);
  const boardFallback = { component_ref: "BOARD", power_w: Number(power), resistance_top_c_per_w: Number(boardTopRth), resistance_bottom_c_per_w: Number(boardBottomRth), thermal_capacitance_j_per_c: Number(thermalCapacitance) };
  const nativeInputs = nativeThermalInputs(thermalElements, thermalBoundaries, boardFallback);
  const activeBoundaries = thermalBoundaries.filter(boundary => boundary.enabled);
  const nativeInputKey = JSON.stringify({ mode, ambient: Number(ambient), endTime: Number(endTime), writeInterval: Number(writeInterval), components: nativeInputs.components, surfaces: activeBoundaries });
  const boardBoundaryElement: ThermalElement = { id: "thermal-board-fallback", reference: "BOARD", name: "Board fallback", kind: "board", material_id: "", surface_finish_id: "as-modeled", enabled: true, coordinate_frame: "board_local", position: [0, 0, 0], dimensions_mm: { x: Number(board?.width) || Number(volume.x) || 1, y: Number(board?.height) || Number(volume.y) || 1, z: board ? Math.max(board.stackup.reduce((sum, layer) => sum + (Number(layer.thickness) || 0), 0), 0.1) : 1.6 }, power_w: Number(power), emissivity: 0.8 };
  const boundaryEditorElements = thermalElements.some(element => element.reference === "BOARD") ? thermalElements : [boardBoundaryElement, ...thermalElements];
  const boardConductance = 1 / Number(boardTopRth) + 1 / Number(boardBottomRth);
  const boardEquivalentRth = Number.isFinite(boardConductance) && boardConductance > 0 ? 1 / boardConductance : 0;
  const scenario = useMemo(() => {
    const forcedAir = medium === "air" && convection === "forced";
    const totalFanFlow = fans.filter(fan => fan.enabled).reduce((sum, fan) => sum + Math.max(0, fan.flow_rate_m3_s), 0);
    return {
      contract: "spike/thermal/v1",
      solver: { engine: "spike.lumped_thermal_network", model_status: "approximate", case_status: preparedCase?.status ?? "unconfigured", validation_status: validation?.valid ? "passed" : validation ? "blocked" : "not_checked" },
      mode,
      application_environment: environment,
      environment_profile: environmentProfile,
      environment_assumptions: environmentAssumptions,
      medium,
      enclosure,
      convection: medium === "vacuum" ? "none" : convection,
      bounding_volume_mm: { x: Number(volume.x), y: Number(volume.y), z: Number(volume.z) },
      ambient_temperature_c: Number(ambient),
      board_fallback_power_w: Number(power),
      gravity: "-Z",
      heat_sources: [{
        id: "board-total",
        source_type: "board",
        power_w: nativeInputs.boardPowerUsed ? Number(power) : 0,
        theta_ja_c_per_w: boardEquivalentRth,
        theta_top_c_per_w: Number(boardTopRth),
        theta_bottom_c_per_w: Number(boardBottomRth),
        thermal_capacitance_j_per_c: Number(thermalCapacitance),
        region: "board",
        coordinate_frame: "board_local",
        position: [Number(board?.width) / 2 || Number(volume.x) / 2, Number(board?.height) / 2 || Number(volume.y) / 2, 0],
        dimensions_mm: { x: Number(board?.width) || 1, y: Number(board?.height) || 1, z: board ? Math.max(board.stackup.reduce((sum, layer) => sum + (Number(layer.thickness) || 0), 0), 0.1) : 1.6 },
      }, ...thermalElements.filter(element => element.enabled && element.power_w > 0).map(element => ({ id: `source-${element.id}`, element_id: element.id, reference: element.reference, name: element.name, source_type: element.kind, power_w: element.power_w, material_id: element.material_id, surface_finish_id: element.surface_finish_id, region: element.reference, coordinate_frame: element.coordinate_frame, position: [element.position[0], element.position[1], element.position[2] + element.dimensions_mm.z / 2], dimensions_mm: element.dimensions_mm }))],
      thermal_elements: thermalElements,
      thermal_links: thermalLinks,
      thermal_boundaries: thermalBoundaries,
      material_library: thermalMaterials,
      surface_finish_library: thermalSurfaceFinishes,
      thermal_screening: thermalScreening,
      assembly_issues: assemblyIssues,
      flow_channels: forcedAir && totalFanFlow > 0 ? [{ id: "main-channel", path: [[0, Number(volume.y) / 2, Number(volume.z) / 2], [Number(volume.x), Number(volume.y) / 2, Number(volume.z) / 2]], width_mm: Math.max(10, Number(volume.y) * 0.2), height_mm: Math.max(10, Number(volume.z) * 0.3), flow_rate_m3_s: totalFanFlow }] : [],
      fans,
      openings: enclosure === "vented_cabinet" ? [{ id: "cabinet-inlet", face: "-X", type: "velocity_inlet" }, { id: "cabinet-outlet", face: "+X", type: "pressure_outlet" }] : [],
      virtual_heatsinks: heatsinks,
      cabinet: enclosure === "vented_cabinet" ? { airflow_direction: [1, 0, 0], inlet: "-X", outlet: "+X" } : {},
      potting: medium === "potting" ? { material: "epoxy", conductivity_w_mk: 0.8, density_kg_m3: 1600, specific_heat_j_kgk: 1000 } : {},
      materials: { air: "standard-air", board: "FR4-copper" },
      // Retain exact bonds for qualified field plugins. The current OpenFOAM
      // air surrogate will reject this scenario rather than silently dropping
      // the PCB/contact physics requested by the user.
      component_bonds: componentBonds,
      mesh: { cell_size_mm: Number(meshSize), boundary_layers: Number(boundaryLayers), max_cells: Number(maxCells) },
      run: { end_time_s: Number(endTime), write_interval_s: Number(writeInterval), max_iterations: Number(maxIterations), residual_target: Number(residualTarget) },
      options: { radiation, turbulence: forcedAir ? "auto" : "laminar" },
      field_result: fieldResult ?? undefined,
      component_result: nativeResultInputKey === nativeInputKey ? nativeResult ?? undefined : undefined,
      component_result_input_key: nativeResultInputKey === nativeInputKey ? nativeInputKey : undefined,
    };
  }, [ambient, assemblyIssues, board, boardBottomRth, boardEquivalentRth, boardTopRth, boundaryLayers, componentBonds, convection, endTime, enclosure, environment, environmentAssumptions, environmentProfile, fans, fieldResult, heatsinks, maxCells, maxIterations, medium, meshSize, mode, nativeInputKey, nativeInputs.boardPowerUsed, nativeResult, nativeResultInputKey, power, preparedCase?.status, radiation, residualTarget, thermalBoundaries, thermalCapacitance, thermalElements, thermalLinks, thermalScreening, validation, volume.x, volume.y, volume.z, writeInterval]);
  useEffect(() => onPreview(scenario), [onPreview, scenario]);
  const preflightCase = async () => {
    if (activeBoundaries.length) { onStatus("Explicit object/surface boundaries are supported by the SPIKE object solver only; disable them before optional OpenFOAM preflight."); return null; }
    onScenario(scenario);
    setPreparedCase(null); setRunResult(null); setBusy("preflight");
    try {
      if (!design || !workerAvailable) throw new Error(!design ? "Import a design before thermal preflight" : "Thermal preflight requires the SPIKE desktop worker");
      const assemblyScope = await onRequireAdmission("thermal");
      const response = await runLocalWorker({ method: "validate_thermal", params: { design, scenario, engine_id: "external.openfoam", assembly_scope: assemblyScope } });
      const result = response.result as typeof validation | undefined;
      const next = result ?? { valid: false, solver_ready: false, issues: [{ severity: "error", message: response.error ?? "Thermal validation failed" }] };
      setValidation(next);
      onStatus(next.valid ? "Thermal preflight complete; review capability before preparing an OpenFOAM case" : response.error ?? "Thermal preflight found blocking setup issues");
      return next;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Thermal preflight failed";
      const next = { valid: false, solver_ready: false, issues: [{ severity: "error", message }] };
      setValidation(next);
      onStatus(message);
      return next;
    } finally {
      setBusy(null);
    }
  };
  const prepareCase = async () => {
    if (activeBoundaries.length) { onStatus("Disable explicit object/surface boundaries before preparing an OpenFOAM case; that adapter does not consume them."); return; }
    const preflight = validation?.valid ? validation : await preflightCase();
    if (!preflight?.valid) return;
    if (!design) return;
    setBusy("prepare");
    try {
      const assemblyScope = await onRequireAdmission("thermal");
      const response = await runLocalWorker({ method: "prepare_thermal_case", params: { design, scenario, engine_id: "external.openfoam", assembly_scope: assemblyScope } });
      const next = response.result as typeof preparedCase;
      setPreparedCase(next ?? { status: "blocked", can_run: false, message: response.error ?? "OpenFOAM case preparation failed" });
      onStatus(next?.can_run ? "OpenFOAM case prepared; execution is available" : next?.message ?? response.error ?? "OpenFOAM case preparation is blocked");
    } catch (error) {
      const message = error instanceof Error ? error.message : "OpenFOAM case preparation failed";
      setPreparedCase({ status: "blocked", can_run: false, message });
      onStatus(message);
    } finally {
      setBusy(null);
    }
  };
  const runCase = async () => {
    if (activeBoundaries.length) { onStatus("OpenFOAM cannot run this setup with explicit object/surface boundaries because they are not translated into that case."); return; }
    if (!preparedCase?.can_run || !preparedCase.case_dir) { onStatus("Prepare a runnable OpenFOAM case before execution"); return; }
    setBusy("run");
    try {
      const assemblyScope = await onRequireAdmission("thermal");
      const response = await runLocalWorker({ method: "run_thermal_case", params: { case_dir: preparedCase.case_dir, scenario, engine_id: "external.openfoam", allow_experimental: true, assembly_scope: assemblyScope } });
      const next = response.result as typeof runResult;
      setRunResult(next ?? { status: "failed", message: response.error ?? "OpenFOAM execution failed" });
      const preview = thermalFieldResultPreview(next?.result);
      if (preview) {
        setFieldResult(preview);
        onScenario({ ...scenario, field_result: preview });
      }
      onStatus(next?.status === "completed" ? "OpenFOAM execution completed; inspect imported result fields and validity metadata" : next?.message ?? response.error ?? "OpenFOAM execution did not complete");
    } catch (error) {
      const message = error instanceof Error ? error.message : "OpenFOAM execution failed";
      setRunResult({ status: "failed", message });
      onStatus(message);
    } finally {
      setBusy(null);
    }
  };
  const compactEstimate = async () => {
    if (activeBoundaries.length) { onStatus("The compact independent screen ignores surface boundaries. Run the SPIKE object solver instead or disable those boundaries."); return; }
    onScenario(scenario); setBusy("estimate");
    try {
      const assemblyScope = await onRequireAdmission("thermal");
      const response = await runLocalWorker({ method: "estimate_thermal", params: { design, scenario, assembly_scope: assemblyScope } });
      const next = response.result as typeof estimate | undefined;
      setEstimate(next ?? null);
      onStatus(next?.status === "completed" ? "Compact thermal screen completed; it is not a CFD result" : response.error ?? "Compact thermal screen is blocked");
    } catch (error) {
      onStatus(error instanceof Error ? error.message : "Compact thermal screen failed");
    } finally {
      setBusy(null);
    }
  };
  const runNativeThermal = async () => {
    setBusy("native");
    setNativeResult(null);
    setNativeError("");
    try {
      if (!workerAvailable) throw new Error("The SPIKE desktop worker is required for a thermal run.");
      const components = nativeInputs.components;
      const invalidCapacity = mode === "transient" ? components.find(component => !(Number(component.thermal_capacitance_j_per_c) > 0)) : undefined;
      if (invalidCapacity) throw new Error(`${invalidCapacity.component_ref}: enter positive heat capacity J/K for transient analysis.`);
      const invalidPath = components.find(component => [component.resistance_top_c_per_w, component.resistance_bottom_c_per_w].some(value => value !== undefined && !(Number(value) > 0)));
      if (invalidPath) throw new Error(`${invalidPath.component_ref}: entered top/bottom paths must be positive K/W. Leave unused paths blank.`);
      const assemblyScope = await onRequireAdmission("thermal");
      const response = await runLocalWorker({ method: "run_component_thermal", params: { scenario: { mode, ambient_temperature_c: Number(ambient), run: { end_time_s: Number(endTime), write_interval_s: Number(writeInterval) } }, components, surfaces: thermalBoundaries, assembly_scope: assemblyScope } });
      const next = response.result as ComponentThermalResult | undefined;
      if (!response.ok || !next) throw new Error(response.error ?? "SPIKE thermal worker returned no result.");
      setNativeResult(next);
      setNativeResultInputKey(nativeInputKey);
      onScenario({ ...scenario, component_result: next, component_result_input_key: nativeInputKey });
      onStatus(next.status === "completed" ? `SPIKE ${mode === "transient" ? "transient" : "steady-state"} thermal run completed; approximate object network result` : next.issues?.[0]?.message ?? "Thermal run was blocked.");
    } catch (error) { const message = error instanceof Error ? error.message : "SPIKE thermal run failed."; setNativeError(message); onStatus(message); }
    finally { setBusy(null); }
  };
  const cancelRun = async () => {
    const cancelled = await cancelLocalWorker();
    onStatus(cancelled ? "OpenFOAM cancellation requested" : "No cancellable OpenFOAM operation is active");
  };
  return <div className="modal-shade thermal-setup-shade"><div className="floating-panel thermal-wizard">
    <div className="floating-heading"><div><b>THERMAL SETUP</b><small>SPIKE steady-state and transient component solver</small></div><button onClick={onClose}><X size={15} /></button></div>
    <p className="wizard-intro">Run the local lumped object model for steady-state or transient part temperatures. The separate spatial board model below solves a steady rectangular board temperature grid and reports board-contact, case, and junction temperatures from explicit part heat paths. Both are approximate.</p>
    <div className="thermal-workflow"><div className="active"><b>1. Inputs</b><span>Part W, K/W and transient J/K</span></div><div className={nativeResult ? "active" : ""}><b>2. SPIKE run</b><span>{nativeResult?.status ?? "Not run"}</span></div><div className={nativeResult?.status === "completed" ? "active" : ""}><b>3. Review</b><span>{nativeResult?.model_status ?? "Approximate model"}</span></div></div>
    <WorkflowSchematic title="Thermal network schematic" diagram={thermalSchematic(scenario)} />
    <div className="wizard-section"><label>SIMULATION SPACE</label><div className="wizard-fields"><div><span>Width</span><input value={volume.x} onChange={e => setVolume({ ...volume, x: e.target.value })} /><small>mm</small></div><div><span>Depth</span><input value={volume.y} onChange={e => setVolume({ ...volume, y: e.target.value })} /><small>mm</small></div><div><span>Height</span><input value={volume.z} onChange={e => setVolume({ ...volume, z: e.target.value })} /><small>mm</small></div></div></div>
    <div className="wizard-section"><label>ENVIRONMENT</label><div className="wizard-fields"><div><span>Application</span><select value={environment} onChange={e => setEnvironment(e.target.value)}><option value="domestic">Domestic</option><option value="industrial">Industrial</option><option value="marine">Marine</option><option value="aerospace">Aerospace</option><option value="custom">Custom</option></select></div><div><span>Medium</span><select value={medium} onChange={e => { const value = e.target.value as typeof medium; setMedium(value); if (value === "vacuum") setConvection("none"); }}><option value="air">Air</option><option value="vacuum">Vacuum</option><option value="potting">Potted block</option></select></div><div><span>Enclosure</span><select value={enclosure} onChange={e => setEnclosure(e.target.value as typeof enclosure)}><option value="open">Open volume</option><option value="sealed">Sealed enclosure</option><option value="vented_cabinet">Directional cabinet</option></select></div><div><span>Analysis</span><select value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="steady_state">Steady state</option><option value="transient">Transient</option></select></div></div></div>
    <ThermalEnvironmentPanel boardWidthMm={Number(board?.width) || Number(volume.x)} boardHeightMm={Number(board?.height) || Number(volume.y)} ambientC={Number(ambient)} powerW={Number(power)} initialProfile={environmentProfile} initialAirflowM3s={fans.filter(fan => fan.enabled).reduce((sum, fan) => sum + fan.flow_rate_m3_s, 0)} onApply={value => {
      setEnvironmentProfile(value.profileId); setEnvironmentAssumptions(value.assumptions); setMedium("air"); setEnclosure(value.enclosure); setConvection(value.convection);
      setBoardTopRth(value.topResistanceKPerW.toPrecision(8)); setBoardBottomRth(value.bottomResistanceKPerW.toPrecision(8));
      setFans(current => current.length ? current.map((fan, index) => ({ ...fan, enabled: value.profileId === "forced_air" && index === 0, flow_rate_m3_s: index === 0 ? value.airflowM3s : fan.flow_rate_m3_s })) : value.profileId === "forced_air" ? normalizeThermalFans(undefined, { x: Number(volume.x), y: Number(volume.y), z: Number(volume.z) }).map(fan => ({ ...fan, flow_rate_m3_s: value.airflowM3s })) : []);
      onStatus(`${value.profileId.replace(/_/g, " ")} assumptions applied; run a thermal solver to replace the boundary screen with computed results`);
    }} />
    <div className="wizard-section"><label>BOARD HEAT FALLBACK</label><p className="thermal-table-note">These BOARD values are used when no powered or cooldown part rows are selected. Part values from the table take precedence, so board power is not added twice.</p><div className="wizard-row"><span>Board dissipation</span><input type="number" min="0" value={power} onChange={e => setPower(e.target.value)} /><small>W</small></div><div className="wizard-row"><span>Ambient temperature</span><input type="number" min="-273.15" value={ambient} onChange={e => setAmbient(e.target.value)} /><small>°C</small></div><div className="wizard-row"><span>Top path to ambient</span><input type="number" min="0" value={boardTopRth} onChange={e => setBoardTopRth(e.target.value)} /><small>K/W</small></div><div className="wizard-row"><span>Bottom path to ambient</span><input type="number" min="0" value={boardBottomRth} onChange={e => setBoardBottomRth(e.target.value)} /><small>K/W</small></div><div className="wizard-row"><span>Board heat capacity (transient)</span><input type="number" min="0" value={thermalCapacitance} onChange={e => setThermalCapacitance(e.target.value)} /><small>J/K</small></div></div>
    <ThermalInputImport board={board} elements={thermalElements} onElements={setThermalElements} />
    {mode === "transient" && <div className="wizard-section"><label>COMPONENT TRANSIENT CONTROLS</label><div className="wizard-fields"><div><span>Duration</span><input aria-label="Component transient duration" type="number" min="0.001" step="1" value={endTime} onChange={e => setEndTime(e.target.value)} /><small>s</small></div><div><span>Time step / sample interval</span><input aria-label="Component transient time step" type="number" min="0.001" step="0.1" value={writeInterval} onChange={e => setWriteInterval(e.target.value)} /><small>s</small></div></div><p className="thermal-table-note">The local RC solver uses this time step. Reduce it to check time convergence; duration divided by time step must not exceed 10,000, with at most 100,000 component samples.</p></div>}
    <ThermalAssemblyEditor board={board} ambientC={Number(ambient)} elements={thermalElements} links={thermalLinks} onElements={setThermalElements} onLinks={setThermalLinks} />
    <ThermalBoundaryEditor elements={boundaryEditorElements} boundaries={thermalBoundaries} onBoundaries={setThermalBoundaries} />
    <p className="thermal-table-note">The SPIKE object run uses selected object power, heat capacity, top/bottom paths and the explicit conduction, convection or radiation boundaries below. Assembly contacts, material geometry and fans do not automatically create a heat path.</p>
    <div className="wizard-section thermal-native-run"><label>SPIKE OBJECT THERMAL SOLVER</label><p>Top/bottom resistances and added surface paths are additive. Conduction needs a complete resistance to its target; convection needs an exposed area and heat-transfer coefficient; radiation needs an exposed area and emissivity. Transient runs need heat capacity for every included object. Geometry, materials, fans and contacts do not automatically create these paths.</p><div className="thermal-native-actions"><button className="run-btn" data-guide="thermal-run" disabled={busy !== null || !workerAvailable} onClick={() => void runNativeThermal()}><Play size={15} /> {busy === "native" ? "Running SPIKE thermal" : `Run ${mode === "transient" ? "transient" : "steady state"}`}</button><button className="secondary-btn" disabled={busy !== null} onClick={() => onScenario(scenario)}>Save setup</button></div>{!workerAvailable && <small>The desktop worker is unavailable. Reopen SPIKE to run the thermal model.</small>}</div>
    {nativeError && <div className="thermal-validation invalid" role="alert"><b>SPIKE thermal run blocked</b><span>{nativeError}</span></div>}
    {nativeResult && nativeResultInputKey !== nativeInputKey && <div className="thermal-validation invalid"><b>Inputs changed</b><span>Rerun SPIKE thermal to update the component temperatures.</span></div>}
    {nativeResult && nativeResultInputKey === nativeInputKey && <div className={`thermal-validation ${nativeResult.status === "completed" ? "valid" : "invalid"}`}><b>SPIKE {mode === "transient" ? "transient" : "steady-state"} · {nativeResult.status} · {nativeResult.model_status}</b>{nativeResult.status === "completed" && <><span>{nativeResult.nodes.length} nodes · {nativeResult.summary.total_power_w?.toFixed(3)} W · maximum {nativeResult.summary.max_temperature_c?.toFixed(2)} °C</span><div className="thermal-native-results"><DataTable label="Component thermal results"><thead><tr><th>Reference</th><th>Power W</th><th>Final °C</th><th>Steady °C</th><th>Top heat W*</th><th>Bottom heat W*</th></tr></thead><tbody>{nativeResult.nodes.map(node => <tr key={node.id}><td>{node.component_ref}</td><td>{node.power_w.toFixed(3)}</td><td>{node.temperature_c.toFixed(2)}</td><td>{node.steady_temperature_c.toFixed(2)}</td><td>{node.heat_flow_top_w.toFixed(3)}</td><td>{node.heat_flow_bottom_w.toFixed(3)}</td></tr>)}</tbody></DataTable></div><small>* Branch heat flows are steady-state values, including when the selected run is transient.</small>{nativeResult.transient.length > 0 && <details><summary>Transient samples ({nativeResult.transient.length})</summary><div className="thermal-native-results"><DataTable label="Thermal transient samples"><thead><tr><th>Time s</th>{nativeResult.nodes.map(node => <th key={node.id}>{node.component_ref} °C</th>)}</tr></thead><tbody>{(nativeResult.transient.length <= 100 ? nativeResult.transient : [...nativeResult.transient.slice(0, 50), ...nativeResult.transient.slice(-50)]).map(frame => <tr key={frame.time_s}><td>{frame.time_s.toFixed(3)}</td>{nativeResult.nodes.map(node => <td key={node.id}>{frame.temperatures_c[node.id]?.toFixed(2) ?? "—"}</td>)}</tr>)}</tbody></DataTable></div>{nativeResult.transient.length > 100 && <small>Showing the first and last 50 samples. Increase the saved interval to reduce output size.</small>}</details>}</>}{nativeResult.issues.map((issue, index) => <small key={index}>{issue.severity}: {issue.message}</small>)}</div>}
    {nativeResult?.status === "completed" && nativeResultInputKey === nativeInputKey && nativeResult.transient.length > 1 && <ThermalTransientOverlay board={board} nodes={nativeResult.nodes} frames={nativeResult.transient} />}
    {nativeResult?.status === "completed" && nativeResultInputKey === nativeInputKey && Boolean(nativeResult.surfaces?.length) && <div className="wizard-section"><label>SURFACE HEAT FLOWS · STEADY STATE</label><div className="thermal-native-results"><DataTable label="Surface heat flows"><thead><tr><th>Object</th><th>Surface</th><th>Mechanism</th><th>Target</th><th>Flow W</th></tr></thead><tbody>{nativeResult.surfaces!.map(surface => <tr key={surface.id}><td>{surface.object_ref}</td><td>{surface.surface}</td><td>{surface.kind}</td><td>{surface.kind === "conduction" ? surface.target_ref || "ambient" : "environment"}</td><td>{surface.heat_flow_w.toFixed(4)}</td></tr>)}</tbody></DataTable></div><small>Positive flow leaves the object. A negative value means heat enters it. Interobject conduction appears once here and with the opposite sign at the target.</small></div>}
    {assemblyIssues.length > 0 && <div className="thermal-validation invalid"><b>Thermal assembly needs attention</b>{assemblyIssues.slice(0, 8).map(issue => <small key={issue}>{issue}</small>)}</div>}
    {thermalScreening.some(item => item.status === "critical" || item.status === "warning") && <div className="thermal-validation invalid"><b>Potential thermal limit violations</b>{thermalScreening.filter(item => item.status === "critical" || item.status === "warning").map(item => <small key={item.element_id}>{item.reference}: {item.estimated_junction_c?.toFixed(1)} deg C estimated, {item.margin_c?.toFixed(1)} deg C margin ({item.status})</small>)}<small>This legacy screen uses only top/bottom resistance estimates and ignores added surface boundaries. Review the completed lumped result; a qualified field claim requires separate validation.</small></div>}
    <BoardThermalPanel board={board} design={design} sourceText={boardSource} ambientC={Number(ambient)} workerAvailable={workerAvailable} onRequireAdmission={() => onRequireAdmission("thermal")} savedRequest={initialScenario?.board_thermal_request as React.ComponentProps<typeof BoardThermalPanel>["savedRequest"]} savedResult={initialScenario?.board_thermal_result as React.ComponentProps<typeof BoardThermalPanel>["savedResult"]} onSave={(request, result) => onScenario({ ...scenario, board_thermal_request: request, board_thermal_result: result })} onStatus={onStatus} />
    <details className="thermal-optional-cfd"><summary>Optional OpenFOAM CFD and airflow workflow</summary>
    {activeBoundaries.length > 0 && <p className="capability-warning">Explicit object and surface boundaries are calculated by the SPIKE object solver above. This OpenFOAM adapter and the older compact screen do not translate them; disable the boundaries to use those separate workflows.</p>}
    <div className="wizard-section"><label>AIRFLOW AND RADIATION</label><div className="wizard-fields"><div><span>Convection</span><select value={medium === "vacuum" ? "none" : convection} disabled={medium === "vacuum"} onChange={e => setConvection(e.target.value as typeof convection)}><option value="none">None</option><option value="natural">Natural</option><option value="forced">Forced / fan</option></select></div><div><span>Radiation</span><button className={`wizard-choice ${radiation ? "selected" : ""}`} onClick={() => setRadiation(!radiation)}>{radiation ? "Enabled" : "Disabled"}</button></div></div></div>
    <ThermalHardwareEditor fans={fans} heatsinks={heatsinks} elements={thermalElements} onFans={setFans} onHeatsinks={setHeatsinks} />
    {advancedPhysics && <p className="capability-warning thermal-hardware-warning"><AlertTriangle size={14} /> Hardware geometry and operating inputs are stored and previewed. Multi-region CHT remains unavailable until its validated solver adapter is installed.</p>}
    <div className="wizard-section"><label>OPTIONAL OPENFOAM CASE CONTROLS</label><div className="wizard-fields thermal-case-grid"><div><span>Base cell size</span><input type="number" min="0.01" step="0.1" value={meshSize} onChange={e => setMeshSize(e.target.value)} /><small>mm</small></div><div><span>Boundary layers</span><input type="number" min="0" step="1" value={boundaryLayers} onChange={e => setBoundaryLayers(e.target.value)} /></div><div><span>Cell ceiling</span><input type="number" min="1" step="1000" value={maxCells} onChange={e => setMaxCells(e.target.value)} /></div><div><span>End time</span><input type="number" min="0.001" step="1" disabled={mode !== "transient"} value={endTime} onChange={e => setEndTime(e.target.value)} /><small>s</small></div><div><span>Write interval</span><input type="number" min="0.001" step="0.1" disabled={mode !== "transient"} value={writeInterval} onChange={e => setWriteInterval(e.target.value)} /><small>s</small></div><div><span>Iteration ceiling</span><input type="number" min="10" step="10" value={maxIterations} onChange={e => setMaxIterations(e.target.value)} /></div><div><span>Residual target</span><input type="number" min="0.000000000001" step="0.000001" value={residualTarget} onChange={e => setResidualTarget(e.target.value)} /></div></div></div>
    {medium === "vacuum" && <p className="capability-warning"><AlertTriangle size={14} /> Vacuum disables convection. Airflow CFD is not applicable; radiation and solid conduction require a solver-supported model.</p>}
    {validation && <div className={`thermal-validation ${validation.valid ? "valid" : "invalid"}`}><b>{validation.valid ? "Preflight passed" : "Preflight blocked"}</b><span>{validation.solver_ready ? "Worker reports the setup is solver-ready. This is not validation evidence." : validation.capability?.reason ?? "Optional OpenFOAM availability or case capability has not been confirmed."}</span>{validation.issues.map((issue, index) => <small key={index}>{issue.severity}: {issue.message}</small>)}</div>}
    {preparedCase && <div className={`thermal-validation ${preparedCase.can_run ? "valid" : "invalid"}`}><b>{preparedCase.can_run ? "OpenFOAM case prepared" : "OpenFOAM case not runnable"}</b><span>{preparedCase.case_dir ? `Case directory: ${preparedCase.case_dir}` : preparedCase.message ?? "The worker did not return a case directory."}</span>{preparedCase.issues?.map((issue, index) => <small key={index}>{issue.severity}: {issue.message}</small>)}</div>}
    {runResult && <div className={`thermal-validation ${runResult.status === "completed" ? "valid" : "invalid"}`}><b>{runResult.status === "completed" ? "OpenFOAM run completed" : "OpenFOAM run did not complete"}</b><span>{runResult.message ?? runResult.result_contract ?? "No result-conversion summary was returned."}</span><small>Only worker-imported result fields may be interpreted as OpenFOAM output. No result is marked validated here.</small></div>}
    {estimate && <div className={`thermal-validation ${estimate.status === "completed" ? "valid" : "invalid"}`}><b>{estimate.status === "completed" ? "Compact estimate complete" : "Compact estimate blocked"}</b><span>{estimate.summary.max_steady_temperature_c.toFixed(1)} deg C maximum · {estimate.summary.total_power_w.toFixed(2)} W</span>{estimate.sources.map(source => <small key={source.id}>{source.id}: +{source.temperature_rise_c.toFixed(1)} deg C, {source.steady_temperature_c.toFixed(1)} deg C steady{source.time_constant_s ? `, tau ${source.time_constant_s.toFixed(1)} s` : ""}</small>)}<small>Approximate independent RC sources only; CFD, board spreading, coupling, airflow, radiation, and enclosure fields are not solved.</small></div>}
    <div className="wizard-actions thermal-actions"><button className="secondary-btn" onClick={onClose}>Close</button><button className="secondary-btn" disabled={busy !== null} onClick={() => onScenario(scenario)}>Save setup</button><button className="secondary-btn" disabled={busy !== null || !workerAvailable || !design || activeBoundaries.length > 0} onClick={() => void compactEstimate()}>{busy === "estimate" ? "Screening" : "Screen"}</button><button className="secondary-btn" disabled={busy !== null || !workerAvailable || !design || activeBoundaries.length > 0} onClick={() => void preflightCase()}>{busy === "preflight" ? "Checking" : "Preflight"}</button><button className="secondary-btn" disabled={busy !== null || !workerAvailable || !design || activeBoundaries.length > 0} onClick={() => void prepareCase()}>{busy === "prepare" ? "Preparing" : "Prepare case"}</button>{busy === "run" && <button className="secondary-btn" onClick={() => void cancelRun()}><X size={15} /> Cancel</button>}<button className="run-btn" disabled={busy !== null || !preparedCase?.can_run || activeBoundaries.length > 0} onClick={() => void runCase()}><Play size={15} /> {busy === "run" ? "Running" : "Run OpenFOAM"}</button></div>
    </details>
  </div></div>;
}

function PiRunDialog({ board, importedDesign, selected, analysisMode, initialWorkflow, sharedStage, onSharedStage, setup, setSetup, topology, limits, solverId, formulation, solverCatalog, probes, resources, appSettings, onRequireAdmission, onOpenPowerPaths, onOpenSpice, onDiagnosticHelp, onClose, onRunState, onResult }: {
  board: ParsedBoard | null;
  importedDesign?: Record<string, any> | null;
  selected: BoardObject | null;
  analysisMode: string;
  initialWorkflow: "single" | "path" | "batch";
  sharedStage: "Mesh" | "Solve";
  onSharedStage: (stage: "Mesh" | "Solve") => void;
  setup: PiSetup;
  setSetup: React.Dispatch<React.SetStateAction<PiSetup>>;
  topology: TopologyModel;
  limits: { drop: string; density: string };
  solverId: string;
  formulation: string;
  solverCatalog: SolverCatalogEntry[];
  probes: BoardObject[];
  resources: ProcessResources;
  appSettings: AppSettings;
  onRequireAdmission: (workload: AssemblyWorkload) => Promise<AssemblyAnalysisScope | null>;
  onOpenPowerPaths: () => void;
  onOpenSpice: () => void;
  onDiagnosticHelp: (code: string) => void;
  onClose: () => void;
  onRunState: (running: boolean, progress?: NonNullable<OperationDisplay>) => void;
  onResult: (message: string, summary?: AnalysisSummary) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [workflow, setWorkflow] = useState<"single" | "path" | "batch">(initialWorkflow);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [batchFilter, setBatchFilter] = useState("");
  const [batchResults, setBatchResults] = useState<BatchResult[]>([]);
  const [padFilters, setPadFilters] = useState<Record<string, string>>({});
  const [panelDock, setPanelDock] = useState<PiPanelDock>(() => {
    const saved = localStorage.getItem("spike.panel.pi-analysis.dock");
    return saved === "left" || saved === "right" || saved === "bottom" || saved === "float" ? saved : "right";
  });
  const [panelFrame, setPanelFrame] = useState<PiPanelFrame>(() => {
    const fallback = {
      x: Math.max(8, window.innerWidth - 540),
      y: 112,
      width: Math.min(520, Math.max(360, window.innerWidth - 24)),
      height: Math.min(680, Math.max(300, window.innerHeight - 160)),
    };
    try {
      const saved = JSON.parse(localStorage.getItem("spike.panel.pi-analysis.frame") ?? "{}") as Partial<PiPanelFrame>;
      const maxWidth = Math.min(window.innerWidth - 16, 720);
      return {
        x: Number.isFinite(saved.x) ? Number(saved.x) : fallback.x,
        y: Number.isFinite(saved.y) ? Number(saved.y) : fallback.y,
        width: Math.max(360, Math.min(maxWidth, Number(saved.width) || fallback.width)),
        height: Math.max(260, Math.min(window.innerHeight - 32, Number(saved.height) || fallback.height)),
      };
    } catch {
      return fallback;
    }
  });
  const [panelMoving, setPanelMoving] = useState(false);
  const [panelDropTarget, setPanelDropTarget] = useState<Exclude<PiPanelDock, "float"> | null>(null);
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const suppressPanelTitleClick = useRef(false);
  const minimizedPanelId = "pi-analysis-setup";
  useEffect(() => () => removeMinimizedTool(minimizedPanelId), []);
  const minimizePanel = () => {
    if (minimizeTool({
      id: minimizedPanelId,
      label: "PI analysis setup",
      restore: () => setPanelCollapsed(false),
      ...(!busy ? { close: onClose } : {}),
    })) setPanelCollapsed(true);
  };
  const [pickTarget, setPickTarget] = useState<{ kind: "sources" | "loads" | "returnSources" | "returnLoads"; jobId?: string } | null>(null);
  const [preflight, setPreflight] = useState<{ status: string; can_solve: boolean; summary: Record<string, number>; issues: DiagnosticIssue[] } | null>(null);
  const [convergence, setConvergence] = useState<ConvergenceReport | null>(null);
  const previousConvergenceSetup = useRef(setup);
  const [operation, setOperation] = useState<OperationTiming | null>(null);
  const [operationClock, setOperationClock] = useState(Date.now());
  const [lastOperation, setLastOperation] = useState<{ kind: OperationKind; seconds: number; succeeded: boolean } | null>(null);
  const activeOperationStartedAt = useRef<number | null>(null);
  const mode = analysisMode === "AC Impedance Sweep" ? "ac" : analysisMode === "Transient PI" ? "transient" : "dc";
  const admissionWorkload: AssemblyWorkload = mode === "dc" ? "pi_dc" : "pi_ac";
  const availableNets = board ? [...new Set(Object.values(board.nets).filter(Boolean))].sort((a, b) => a.localeCompare(b)) : [];
  const compiledPiPaths = useMemo(() => compilePiPaths(topology), [topology]);
  const activePiPath = compiledPiPaths.find(path => path.id === setup.powerPathId);
  const sourceNetFor = (job?: BatchNetJob) => job?.net ?? (workflow === "path" ? activePiPath?.source_terminal.net : undefined) ?? setup.net;
  const loadNetFor = (job?: BatchNetJob) => job?.net ?? (workflow === "path" ? activePiPath?.load_terminal.net : undefined) ?? setup.net;
  const layers = board?.layers ?? ["F.Cu", "B.Cu"];
  const configuredMeshCells = Math.max(100, Number(setup.maxPreviewCells) || 10000);
  const resourcePlan: ResourceCapacityPlan = useMemo(() => planResourceCapacity({
    availableMemoryBytes: resources.totalMemoryBytes,
    userMemoryFraction: appSettings.solverMemoryFraction,
    userMemoryLimitBytes: appSettings.solverMemoryLimitGb * 1024 ** 3,
    boardCount: 1,
    copperLayers: Math.max(1, board?.layers.length ?? 1),
    components: board?.components.length ?? 0,
    tracks: board?.tracks.length ?? 0,
    vias: board?.vias.length ?? 0,
    pads: board?.pads.length ?? 0,
    zones: board?.zones.length ?? 0,
    requestedMeshCells: configuredMeshCells,
  }), [appSettings.solverMemoryFraction, appSettings.solverMemoryLimitGb, board, configuredMeshCells, resources.totalMemoryBytes]);
  const effectiveMeshMemoryBudgetBytes = resourcePlan.policy.effectiveMemoryBudgetBytes ?? 512 * 1024 ** 2;
  const operationElapsed = operation ? Math.max(0, (operationClock - operation.startedAt) / 1000) : 0;
  const startOperation = (kind: OperationKind, label: string, meshCells = configuredMeshCells, jobs = 1) => {
    const timing: OperationTiming = {
      kind,
      label,
      startedAt: Date.now(),
      estimateSeconds: estimateOperationSeconds(kind, meshCells, jobs),
      meshCells,
      jobs,
    };
    activeOperationStartedAt.current = timing.startedAt;
    setOperationClock(timing.startedAt);
    setOperation(timing);
    onRunState(true, { label, elapsedSeconds: 0, estimateSeconds: timing.estimateSeconds });
    return timing.startedAt;
  };
  const updateOperation = (label: string, meshCells?: number) => {
    setOperation(current => {
      if (!current) return current;
      const cells = meshCells ?? current.meshCells;
      return { ...current, label, meshCells: cells, estimateSeconds: estimateOperationSeconds(current.kind, cells, current.jobs) };
    });
  };
  const finishOperation = (startedAt: number, kind: OperationKind, meshCells = configuredMeshCells, jobs = 1, succeeded = true) => {
    const seconds = Math.max(0, (Date.now() - startedAt) / 1000);
    if (succeeded) recordOperationTiming(kind, seconds, meshCells, jobs);
    setLastOperation({ kind, seconds, succeeded });
    if (activeOperationStartedAt.current === startedAt) activeOperationStartedAt.current = null;
    setOperation(null);
    onRunState(false);
    return seconds;
  };
  useEffect(() => {
    if (!operation) return;
    const update = () => {
      // React may not have cleaned up this interval yet when finishOperation
      // publishes the terminal state. Ignore that queued tick so it cannot
      // change the parent back to Running after a result has been generated.
      if (activeOperationStartedAt.current !== operation.startedAt) return;
      const now = Date.now();
      setOperationClock(now);
      onRunState(true, {
        label: operation.label,
        elapsedSeconds: Math.max(0, (now - operation.startedAt) / 1000),
        estimateSeconds: operation.estimateSeconds,
      });
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [operation?.label, operation?.estimateSeconds, operation?.startedAt]);
  useEffect(() => {
    localStorage.setItem("spike.panel.pi-analysis.dock", panelDock);
    localStorage.setItem("spike.panel.pi-analysis.frame", JSON.stringify(panelFrame));
  }, [panelDock, panelFrame]);
  useEffect(() => {
    if (previousConvergenceSetup.current !== setup) {
      setConvergence(null);
      previousConvergenceSetup.current = setup;
    }
  }, [setup]);
  useEffect(() => {
    const clampFrame = () => setPanelFrame(current => ({
      ...current,
      x: Math.max(4, Math.min(current.x, Math.max(4, window.innerWidth - Math.min(current.width, window.innerWidth - 8) - 4))),
      y: Math.max(4, Math.min(current.y, Math.max(4, window.innerHeight - 44))),
      width: Math.min(current.width, Math.max(360, window.innerWidth - 8)),
      height: Math.min(current.height, Math.max(260, window.innerHeight - 8)),
    }));
    window.addEventListener("resize", clampFrame);
    return () => window.removeEventListener("resize", clampFrame);
  }, []);
  const beginPanelMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || event.target instanceof Element && event.target.closest("button, input, select, textarea")) return;
    const panel = panelRef.current;
    if (!panel) return;
    const rect = panel.getBoundingClientRect();
    const maximumSideWidth = Math.min(window.innerWidth - 16, 720);
    const dragWidth = panelDock === "bottom" ? Math.min(panelFrame.width, maximumSideWidth) : Math.min(rect.width, maximumSideWidth);
    const offsetX = Math.min(event.clientX - rect.left, Math.max(40, dragWidth - 40));
    const offsetY = event.clientY - rect.top;
    const startX = event.clientX;
    const startY = event.clientY;
    const pointerId = event.pointerId;
    let moving = false;
    let dropTarget: Exclude<PiPanelDock, "float"> | null = null;
    const onMove = (pointer: PointerEvent) => {
      if (pointer.pointerId !== pointerId) return;
      if (!moving) {
        if (Math.hypot(pointer.clientX - startX, pointer.clientY - startY) < 5) return;
        moving = true;
        suppressPanelTitleClick.current = true;
        setPanelDock("float");
        setPanelCollapsed(false);
        setPanelMoving(true);
        setPanelFrame({
          x: Math.max(4, Math.min(window.innerWidth - dragWidth - 4, pointer.clientX - offsetX)),
          y: rect.top,
          width: dragWidth,
          height: rect.height,
        });
      }
      dropTarget = pointer.clientY >= window.innerHeight - 86
        ? "bottom"
        : pointer.clientX <= 86
          ? "left"
          : pointer.clientX >= window.innerWidth - 86
            ? "right"
            : null;
      setPanelDropTarget(dropTarget);
      setPanelFrame(current => ({
        ...current,
        x: Math.max(4, Math.min(window.innerWidth - current.width - 4, pointer.clientX - offsetX)),
        y: Math.max(4, Math.min(window.innerHeight - 44, pointer.clientY - offsetY)),
      }));
    };
    const onUp = (pointer: PointerEvent) => {
      if (pointer.pointerId !== pointerId) return;
      if (moving) {
        setPanelDock(dropTarget ?? "float");
        setPanelDropTarget(null);
        setPanelMoving(false);
        window.setTimeout(() => { suppressPanelTitleClick.current = false; }, 0);
      }
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };
  const beginPanelResize = (event: ReactPointerEvent<HTMLDivElement>, edge: "left" | "right" | "top" | "corner") => {
    event.stopPropagation();
    event.preventDefault();
    const panel = panelRef.current;
    if (!panel) return;
    const handle = event.currentTarget;
    const pointerId = event.pointerId;
    handle.setPointerCapture(pointerId);
    handle.classList.add("is-resizing");
    const rect = panel.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    let stopped = false;
    const onMove = (pointer: PointerEvent) => {
      if (pointer.pointerId !== pointerId) return;
      const dx = pointer.clientX - startX;
      const dy = pointer.clientY - startY;
      setPanelFrame(current => {
        if (edge === "left") {
          const width = Math.max(360, Math.min(window.innerWidth - 16, rect.width - dx));
          return { ...current, width, x: rect.right - width };
        }
        if (edge === "right") return { ...current, width: Math.max(360, Math.min(window.innerWidth - 16, rect.width + dx)) };
        if (edge === "top") {
          const height = Math.max(260, Math.min(window.innerHeight - 32, rect.height - dy));
          return { ...current, height, y: rect.bottom - height };
        }
        return {
          ...current,
          width: Math.max(360, Math.min(window.innerWidth - rect.left - 4, rect.width + dx)),
          height: Math.max(260, Math.min(window.innerHeight - rect.top - 4, rect.height + dy)),
        };
      });
    };
    const onUp = () => {
      if (stopped) return;
      stopped = true;
      handle.classList.remove("is-resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      window.removeEventListener("blur", onUp);
      handle.removeEventListener("lostpointercapture", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    window.addEventListener("pointercancel", onUp, { once: true });
    window.addEventListener("blur", onUp, { once: true });
    handle.addEventListener("lostpointercapture", onUp, { once: true });
  };
  const recommendedTransientStep = () => {
    const stop = tryParseSpiceNumber(setup.transientStopS, 1e-3);
    const candidates = [stop / 1000];
    [...setup.sources, ...setup.loads].forEach(item => {
      if (item.profile === "step" || item.profile === "pulse") {
        [item.profileRiseS, item.profile === "pulse" ? item.profileFallS : item.profileRiseS].forEach(value => {
          const edge = tryParseSpiceNumber(value, 0);
          if (edge > 0) candidates.push(edge / 10);
        });
      }
      if (item.profile === "piecewise_linear") {
        try {
          const points = parsePwlPoints(item.profileData);
          for (let index = 1; index < points.length; index += 1) {
            const interval = points[index][0] - points[index - 1][0];
            if (interval > 0) candidates.push(interval / 10);
          }
        } catch { /* Preflight reports the invalid PWL definition. */ }
      }
    });
    return Math.max(numericMinimum(candidates.filter(value => Number.isFinite(value) && value > 0), stop * 1e-12), stop * 1e-12);
  };
  useEffect(() => () => previewViewportTarget(null), []);
  useEffect(() => {
    if (!availableNets.length || setup.batchJobs.length) return;
    const batchMode: BatchAnalysisMode = mode === "ac" ? "ac" : mode === "transient" ? "transient" : "dc";
    const jobs = availableNets.map(net => batchJob(net, net === setup.net ? batchMode : "skip"));
    setSetup(current => ({ ...current, batchJobs: jobs }));
    setSelectedBatchId(jobs.find(job => job.mode !== "skip")?.id ?? jobs[0]?.id ?? "");
  }, [availableNets.join("|")]);
  const updateBatchJob = (id: string, patch: Partial<BatchNetJob>) => {
    setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => job.id === id ? { ...job, ...patch } : job) }));
  };
  const updateTerminal = (kind: "sources" | "loads", id: string, patch: Partial<PiTerminal>, jobId?: string) => {
    if (!jobId) {
      setSetup(current => ({ ...current, [kind]: current[kind].map(item => item.id === id ? { ...item, ...patch } : item) }));
      return;
    }
    setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => job.id === jobId ? { ...job, [kind]: job[kind].map(item => item.id === id ? { ...item, ...patch } : item) } : job) }));
  };
  const addTerminal = (kind: "sources" | "loads", jobId?: string) => {
    if (!jobId) {
      setSetup(current => ({ ...current, [kind]: [...current[kind], terminal(kind === "sources" ? "source" : "load", current[kind].length)] }));
      return;
    }
    setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => job.id === jobId ? { ...job, [kind]: [...job[kind], terminal(kind === "sources" ? "source" : "load", job[kind].length)] } : job) }));
  };
  const removeTerminal = (kind: "sources" | "loads", id: string, jobId?: string) => {
    if (!jobId) {
      setSetup(current => ({ ...current, [kind]: current[kind].filter(item => item.id !== id) }));
      return;
    }
    setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => job.id === jobId ? { ...job, [kind]: job[kind].filter(item => item.id !== id) } : job) }));
  };
  const updateReturnTerminal = (kind: "sources" | "loads", id: string, patch: Partial<PiTerminal>) => {
    setSetup(current => ({
      ...current,
      returnPath: { ...current.returnPath, [kind]: current.returnPath[kind].map(item => item.id === id ? { ...item, ...patch } : item) },
    }));
  };
  const addReturnTerminal = (kind: "sources" | "loads") => {
    setSetup(current => {
      const items = current.returnPath[kind];
      const base = terminal(kind === "sources" ? "source" : "load", items.length);
      const next = { ...base, id: `return-${base.id}`, name: kind === "sources" ? `Source return ${items.length + 1}` : `Load return ${items.length + 1}`, value: kind === "sources" ? "0" : "1" };
      return { ...current, returnPath: { ...current.returnPath, [kind]: [...items, next] } };
    });
  };
  const removeReturnTerminal = (kind: "sources" | "loads", id: string) => {
    setSetup(current => ({ ...current, returnPath: { ...current.returnPath, [kind]: current.returnPath[kind].filter(item => item.id !== id) } }));
  };
  const expandSpan = (rawLayers: string[]) => {
    if (!board) return rawLayers;
    if (rawLayers.some(layer => layer === "*.Cu" || layer === "F&B.Cu")) return [...board.layers];
    const copper = rawLayers.filter(layer => board.layers.includes(layer));
    if (copper.length === 2) {
      const first = board.layers.indexOf(copper[0]);
      const last = board.layers.indexOf(copper[1]);
      if (first >= 0 && last >= 0) return board.layers.slice(Math.min(first, last), Math.max(first, last) + 1);
    }
    return copper;
  };
  const selectedLocation = () => {
    if (!board || !selected) return null;
    const pad = board.pads.find(item => item.id === selected.id);
    if (pad) return { point: selected.position ?? pad.at, layers: expandSpan(pad.layers), anchorId: pad.id, anchorType: "pad" };
    const via = board.vias.find(item => item.id === selected.id);
    if (via) return { point: via.at, layers: expandSpan(via.layers), anchorId: via.id, anchorType: "via" };
    const component = board.components.find(item => item.id === selected.id);
    if (component) {
      const componentLayers = [...new Set(board.pads.filter(item => item.ref === component.ref).flatMap(item => expandSpan(item.layers)))];
      return { point: component.at, layers: componentLayers, anchorId: component.id, anchorType: "component" };
    }
    const track = board.tracks.find(item => item.id === selected.id);
    if (track) return { point: selected.position ?? [(track.start[0] + track.end[0]) / 2, (track.start[1] + track.end[1]) / 2] as [number, number], layers: [track.layer], anchorId: track.id, anchorType: "track" };
    const zone = board.zones.find(item => item.id === selected.id);
    if (!zone?.points.length) return null;
    return {
      point: selected.position ?? [
        zone.points.reduce((sum, point) => sum + point[0], 0) / zone.points.length,
        zone.points.reduce((sum, point) => sum + point[1], 0) / zone.points.length,
      ] as [number, number],
      layers: [zone.layer],
      anchorId: zone.id,
      anchorType: "zone",
    };
  };
  const placeFromSelection = (kind: "sources" | "loads", jobId?: string) => {
    const location = selectedLocation();
    if (!location || !selected?.net) {
      onResult("Select an exact point on a pad, via, routed trace, or copper zone before placing a terminal.");
      return false;
    }
    const job = jobId ? setup.batchJobs.find(item => item.id === jobId) : undefined;
    const activeNet = kind === "sources" ? sourceNetFor(job) : loadNetFor(job);
    if (!activeNet) {
      onResult("Select the analysis net before placing source and sink terminals.");
      return false;
    }
    if (selected.net !== activeNet) {
      onResult(`Terminal rejected: ${selected.name} is on ${selected.net}; this analysis is locked to ${activeNet}.`);
      return false;
    }
    setSetup(current => {
      const currentJob = jobId ? current.batchJobs.find(item => item.id === jobId) : null;
      const terminals = currentJob ? currentJob[kind] : current[kind];
      const target = terminals.find(item => !item.x || !item.y);
      const patch = {
        x: location.point[0].toFixed(4),
        y: location.point[1].toFixed(4),
        layer: "auto",
        layers: location.layers,
        anchorId: location.anchorId,
        anchorType: location.anchorType,
        net: selected?.net ?? "",
      };
      const updated = target
        ? terminals.map(item => item.id === target.id ? { ...item, ...patch } : item)
        : [...terminals, { ...terminal(kind === "sources" ? "source" : "load", terminals.length), ...patch }];
      if (currentJob) {
        return {
          ...current,
          batchJobs: current.batchJobs.map(item => item.id === currentJob.id ? { ...item, [kind]: updated } : item),
        };
      }
      return {
        ...current,
        [kind]: updated,
      };
    });
    onResult(`${kind === "sources" ? "Source" : "Sink"} placed at ${location.point[0].toFixed(4)}, ${location.point[1].toFixed(4)} mm on ${activeNet}.`);
    return true;
  };
  const placeReturnFromSelection = (kind: "sources" | "loads") => {
    const location = selectedLocation();
    if (!location || !selected?.net) {
      onResult("Select an exact point on return-path copper before placing the terminal.");
      return false;
    }
    if (!setup.returnPath.net) {
      onResult("Select the return or reference net before placing return terminals.");
      return false;
    }
    if (selected.net !== setup.returnPath.net) {
      onResult(`Return terminal rejected: ${selected.name} is on ${selected.net}; the return path is locked to ${setup.returnPath.net}.`);
      return false;
    }
    setSetup(current => {
      const terminals = current.returnPath[kind];
      const target = terminals.find(item => !item.x || !item.y);
      const patch = {
        x: location.point[0].toFixed(4),
        y: location.point[1].toFixed(4),
        layer: "auto",
        layers: location.layers,
        anchorId: location.anchorId,
        anchorType: location.anchorType,
        net: selected?.net ?? current.returnPath.net,
      };
      const updated = target
        ? terminals.map(item => item.id === target.id ? { ...item, ...patch } : item)
        : [...terminals, { ...terminal(kind === "sources" ? "source" : "load", terminals.length), ...patch, id: `return-${kind}-${terminals.length + 1}` }];
      return {
        ...current,
        returnPath: {
          ...current.returnPath,
          [kind]: updated,
        },
      };
    });
    onResult(`${kind === "sources" ? "Source reference" : "Load return"} placed at ${location.point[0].toFixed(4)}, ${location.point[1].toFixed(4)} mm on ${setup.returnPath.net}.`);
    return true;
  };
  const padLabel = (pad: ParsedPad) => {
    const identity = `${pad.ref ?? "?"}.${pad.name || "?"}`;
    const span = expandSpan(pad.layers);
    return `${identity} | ${pad.at[0].toFixed(3)}, ${pad.at[1].toFixed(3)} mm | ${span.join(" / ") || pad.layer}`;
  };
  const padsOnNet = (net: string, filterKey: string) => {
    const query = (padFilters[filterKey] ?? "").trim().toLowerCase();
    return (board?.pads ?? [])
      .filter(pad => pad.net === net)
      .filter(pad => !query || padLabel(pad).toLowerCase().includes(query))
      .sort((left, right) => `${left.ref ?? ""}.${left.name}`.localeCompare(`${right.ref ?? ""}.${right.name}`, undefined, { numeric: true }));
  };
  const padPlacement = (pad: ParsedPad): Partial<PiTerminal> => ({
    x: pad.at[0].toFixed(4),
    y: pad.at[1].toFixed(4),
    layer: "auto",
    layers: expandSpan(pad.layers),
    anchorId: pad.id,
    anchorType: "pad",
    net: pad.net ?? "",
  });
  const selectTerminalPad = (kind: "sources" | "loads", terminalId: string, padId: string, jobId?: string) => {
    const pad = board?.pads.find(item => item.id === padId);
    if (!pad) return;
    updateTerminal(kind, terminalId, padPlacement(pad), jobId);
    onResult(`${kind === "sources" ? "Source" : "Sink"} placed on ${padLabel(pad)}`);
  };
  const selectReturnPad = (kind: "sources" | "loads", terminalId: string, padId: string) => {
    const pad = board?.pads.find(item => item.id === padId);
    if (!pad) return;
    updateReturnTerminal(kind, terminalId, padPlacement(pad));
    onResult(`Return terminal placed on ${padLabel(pad)}`);
  };
  const activatePowerPath = (pathId: string) => {
    const path = compiledPiPaths.find(item => item.id === pathId);
    if (!path) {
      setSetup(current => ({ ...current, powerPathId: "" }));
      return;
    }
    setWorkflow("path");
    const sourcePad = board?.pads.find(pad => pad.id === path.source_terminal.pad_id);
    const loadPad = board?.pads.find(pad => pad.id === path.load_terminal.pad_id);
    setSetup(current => ({
      ...current,
      powerPathId: path.id,
      net: path.source_terminal.net,
      sources: current.sources.map((item, index) => index === 0 && sourcePad ? { ...item, ...padPlacement(sourcePad), net: path.source_terminal.net } : { ...item, net: path.source_terminal.net }),
      loads: current.loads.map((item, index) => index === 0 && loadPad ? { ...item, ...padPlacement(loadPad), net: path.load_terminal.net } : { ...item, net: path.load_terminal.net }),
    }));
    window.dispatchEvent(new CustomEvent("spike-analysis-net-selected", { detail: { nets: path.segments.map(segment => segment.net), net: path.source_terminal.net } }));
    onResult(path.issues.length ? `Power path selected with ${path.issues.length} review issue(s)` : `${path.label} selected: ${path.segments.length} nets and ${path.transitions.length} series component(s)`);
  };
  useEffect(() => {
    if (!pickTarget || !selected) return;
    if (pickTarget.kind === "returnSources" || pickTarget.kind === "returnLoads") {
      placeReturnFromSelection(pickTarget.kind === "returnSources" ? "sources" : "loads");
    } else {
      placeFromSelection(pickTarget.kind, pickTarget.jobId);
    }
    setPickTarget(null);
  }, [selected?.id, selected?.position?.[0], selected?.position?.[1]]);
  const terminalPayload = (item: PiTerminal, kind: "source" | "load") => {
    const x = Number(item.x);
    const y = Number(item.y);
    const value = parseSpiceNumber(item.value, `${item.name} ${kind === "source" ? "voltage" : "current"}`);
    const contactResistance = parseSpiceNumber(item.contactResistance || 0, `${item.name} contact resistance`);
    const packageResistance = parseSpiceNumber(item.packageResistance || 0, `${item.name} package resistance`);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(value)) throw new Error(`${item.name} requires valid X, Y, and ${kind === "source" ? "voltage" : "current"}.`);
    if (!Number.isFinite(contactResistance) || contactResistance < 0 || !Number.isFinite(packageResistance) || packageResistance < 0) throw new Error(`${item.name} resistance values must be zero or positive.`);
    const profileNumbers = {
      initial_value: parseSpiceNumber(item.profileInitial || 0, `${item.name} initial value`),
      delay_s: parseSpiceNumber(item.profileDelayS || 0, `${item.name} delay`),
      rise_time_s: parseSpiceNumber(item.profileRiseS || 0, `${item.name} rise time`),
      pulse_width_s: parseSpiceNumber(item.profileWidthS || 0, `${item.name} on time`),
      fall_time_s: parseSpiceNumber(item.profileFallS || 0, `${item.name} fall time`),
      period_s: parseSpiceNumber(item.profilePeriodS || 0, `${item.name} period`),
    };
    if (item.profile !== "constant" && Object.values(profileNumbers).some(entry => !Number.isFinite(entry))) throw new Error(`${item.name} waveform controls must be numeric.`);
    if (item.profile !== "constant" && [profileNumbers.delay_s, profileNumbers.rise_time_s, profileNumbers.pulse_width_s, profileNumbers.fall_time_s, profileNumbers.period_s].some(entry => entry < 0)) throw new Error(`${item.name} waveform times cannot be negative.`);
    if (item.profile === "pulse" && (!(profileNumbers.period_s > 0) || profileNumbers.period_s < profileNumbers.rise_time_s + profileNumbers.pulse_width_s + profileNumbers.fall_time_s)) throw new Error(`${item.name} pulse period must contain its rise, high-time, and fall intervals.`);
    if (item.profile === "piecewise_linear" && !item.profileData.trim()) throw new Error(`${item.name} requires piecewise-linear time:value points.`);
    return {
      id: item.id,
      name: item.name,
      position_mm: [x, y],
      ...(item.layer && item.layer !== "auto" ? { layer: item.layer, layer_scope: "single" } : {
        layer_scope: "connected_conductor",
        layer_candidates: item.layers ?? [],
      }),
      net: item.net || undefined,
      geometry_anchor: item.anchorId ? { id: item.anchorId, type: item.anchorType || "geometry" } : undefined,
      [kind === "source" ? "voltage_v" : "current_a"]: value,
      contact_resistance_ohm: contactResistance,
      package_resistance_ohm: packageResistance,
      profile: { kind: item.profile, ...profileNumbers, points: item.profile === "piecewise_linear" ? parsePwlPoints(item.profileData) : [] },
    };
  };
  const buildRequest = (job?: BatchNetJob) => {
    const requestedMode = job?.mode === "ac" ? "ac" : job?.mode === "dc" ? "dc" : mode;
    const path = workflow === "path" && !job ? activePiPath : undefined;
    const net = sourceNetFor(job);
    const loadNet = loadNetFor(job);
    const sources = job?.sources ?? setup.sources;
    const loads = job?.loads ?? setup.loads;
    const returnPath = setup.returnPath ?? defaultReturnPath();
    const explicitReturn = ["dc", "transient"].includes(requestedMode) && returnPath.mode !== "implicit";
    const coupling = job?.coupling ?? defaultCouplingSetup();
    if (!board || !net) throw new Error("Select an imported power net before preparing the analysis.");
    if (workflow === "path" && !path) throw new Error("Select a reviewed series power path, or create one in the Power Tree before solving.");
    if (!sources.length || !loads.length) throw new Error(`${net} requires at least one source and one sink.`);
    if (explicitReturn && !returnPath.net) throw new Error("Select a return/ground net for explicit loop solving.");
    if (explicitReturn && (!returnPath.sources.length || returnPath.loads.length !== loads.length)) throw new Error("Explicit return solving requires a source return and one paired return terminal for every current sink.");
    if (!(Number(setup.viaPlatingMm) > 0)) throw new Error("Via plating thickness must be a positive value in millimetres.");
    if (topology.nodes.length && !topology.nodes.some(node => node.kind === "source")) throw new Error("The active power tree has no source. Assign a source before simulation.");
    if (topology.nodes.length && !topology.nodes.some(node => node.kind === "load")) throw new Error("The active power tree has no load. Assign at least one load before simulation.");
    const topologyNodeIds = new Set(topology.nodes.map(node => node.id));
    if (topology.edges.some(edge => !topologyNodeIds.has(edge.from) || !topologyNodeIds.has(edge.to))) throw new Error("The active power tree contains a connection to a missing element.");
    const design = importedDesign ?? {
      contract: "spike/v1",
      name: "desktop-import",
      source_format: "kicad",
      source_path: "desktop-import",
      layers: board.layerDefinitions.map(layer => ({
        id: layer.id,
        name: layer.name,
        type: layer.kind,
        user_name: layer.userName ?? "",
      })),
      nets: Object.entries(board.nets).map(([id, name]) => ({ id, name })),
      tracks: board.tracks.map(track => ({ id: track.id, start: track.start, end: track.end, width: track.width, layer: track.layer, net_name: track.net })),
      vias: board.vias.map(via => ({ id: via.id, at: via.at, size: via.size, drill: via.drill, layers: via.layers, net_name: via.net })),
      pads: board.pads.map(pad => ({ ...pad, net_name: pad.net })),
      zones: board.zones.map(zone => ({ ...zone, net_name: zone.net })),
      components: board.components,
      stackup: board.stackup,
      technology: board.technology ?? "rigid",
      regions: board.regions ?? [],
      bends: board.bendLines ?? [],
    };
    const pathHandoff = path ? compilePiSeriesSolveHandoff(path, board.pads) : undefined;
    const terminalWithPathAnchor = (item: PiTerminal, anchor: PiPathTerminalAnchor): PiTerminal => ({
      ...item,
      x: anchor.position_mm[0].toFixed(4),
      y: anchor.position_mm[1].toFixed(4),
      layer: "auto",
      layers: anchor.layers,
      anchorId: anchor.geometry_anchor.id,
      anchorType: anchor.geometry_anchor.type,
      net: anchor.net,
    });
    const solverProbePayloads = probes.map(probe => {
      const track = board.tracks.find(item => item.id === probe.id);
      const via = board.vias.find(item => item.id === probe.id);
      const pad = board.pads.find(item => item.id === probe.id);
      const component = board.components.find(item => item.id === probe.id);
      const position = probe.position ?? (track
        ? [(track.start[0] + track.end[0]) / 2, (track.start[1] + track.end[1]) / 2] as [number, number]
        : via?.at ?? pad?.at ?? component?.at);
      return { id: probe.id, name: probe.name, net: probe.net, layer: probe.layer, position_mm: position };
    }).filter(probe => Array.isArray(probe.position_mm));
    const loopEndpoint = (padId: string, expectedNet: string, label: string) => {
      const pad = board.pads.find(item => item.id === padId);
      if (!pad) throw new Error(`${label} requires an explicit pad selection.`);
      if (pad.net !== expectedNet) throw new Error(`${label} ${pad.ref ?? "?"}.${pad.name} is on ${pad.net ?? "no net"}, not ${expectedNet}.`);
      return {
        id: pad.id,
        position_mm: pad.at,
        net: expectedNet,
        layer_scope: "connected_conductor",
        layer_candidates: pad.layers,
        geometry_anchor: { id: pad.id, type: "pad" },
        pad: { reference: pad.ref, number: pad.name },
      };
    };
    const componentModelPayload = (node: TopologyModel["nodes"][number]) => {
      const primitive = node.circuitModel?.primitive;
      const pins = node.circuitModel?.pins ?? [];
      const boardComponent = board.components.find(component => component.ref === node.ref);
      const inputPins = pins.filter(pin => pin.role === "input" || pin.role === "passive").map(pin => pin.pad_id);
      const outputPins = pins.filter(pin => pin.role === "output" || pin.role === "passive").map(pin => pin.pad_id);
      const parseModelValue = (value: string | number | boolean | null | undefined, label: string) => {
        if (typeof value === "boolean") throw new Error(`${label} must be numeric.`);
        return value === undefined || value === null || value === "" ? 0 : parseSpiceNumber(value, label);
      };
      const modelValue = parseModelValue(node.circuitModel?.value ?? node.value, `${node.ref ?? node.label} model value`);
      const rdsOn = parseModelValue(node.modelParameters?.rds_on_ohm ?? node.modelParameters?.resistance_ohm, `${node.ref ?? node.label} linearized resistance`);
      const modelKind = primitive ? "linear_rlc" : "linearized_operating_point";
      return {
        id: node.id,
        reference: node.ref,
        model_kind: modelKind,
        topology: node.orientation === "shunt" ? "shunt" : "series",
        resistance_ohm: primitive === "resistor" ? modelValue : rdsOn,
        inductance_h: primitive === "inductor" ? modelValue : parseModelValue(node.modelParameters?.inductance_h, `${node.ref ?? node.label} package inductance`),
        capacitance_f: primitive === "capacitor" ? modelValue : parseModelValue(node.modelParameters?.capacitance_f, `${node.ref ?? node.label} package capacitance`),
        input_pins: inputPins,
        output_pins: outputPins,
        geometry_center_mm: boardComponent?.at ?? null,
        operating_point: node.modelParameters?.operating_point ?? null,
        model_link: node.modelLink,
        reviewed: primitive ? pins.length >= 2 && modelValue > 0 : Boolean(node.modelLink && inputPins.length && outputPins.length && rdsOn >= 0),
      };
    };
    const loopExtractions = requestedMode === "ac" ? setup.loopExtractions.map((loop, index) => {
      if (!loop.forwardNet || !loop.returnNet || loop.forwardNet === loop.returnNet) throw new Error(`${loop.name || `Loop ${index + 1}`} requires distinct forward and return nets.`);
      const componentModels = loop.pathGroupId
        ? topology.nodes.filter(node => node.pathGroupId === loop.pathGroupId && node.orientation !== "block" && !["rail", "return"].includes(node.kind)).map(componentModelPayload)
        : [];
      return {
        id: loop.id,
        name: loop.name,
        forward: {
          net: loop.forwardNet,
          source: loopEndpoint(loop.forwardStartPadId, loop.forwardNet, `${loop.name} forward source`),
          load: loopEndpoint(loop.forwardEndPadId, loop.forwardNet, `${loop.name} forward load`),
        },
        return: {
          net: loop.returnNet,
          load: loopEndpoint(loop.returnStartPadId, loop.returnNet, `${loop.name} load-side return`),
          source: loopEndpoint(loop.returnEndPadId, loop.returnNet, `${loop.name} source-side return`),
        },
        component_models: componentModels,
        topology_path_group_id: loop.pathGroupId || null,
      };
    }) : [];
    const loopNets = loopExtractions.flatMap(loop => [loop.forward.net, loop.return.net]);
    const extractionReturnNet = loopExtractions[0]?.return.net ?? "";
    const spec = {
      contract: "spike/v1",
      mode: requestedMode,
      solver_id: job?.solverId ?? solverId,
      formulation: job ? "auto" : formulation,
      required_capabilities: requestedMode === "ac"
        ? [
            "frequency_dependent_impedance",
            "partial_inductance",
            ...(setup.skinEffect ? ["skin_effect"] : []),
            ...(setup.proximityEffect ? ["proximity_effect"] : []),
            ...(setup.roughnessModel !== "none" ? ["surface_roughness"] : []),
            ...(coupling.enabled && coupling.electricField ? ["electric_field_coupling"] : []),
            ...(coupling.enabled && coupling.magneticField ? ["magnetic_field_coupling"] : []),
          ]
        : requestedMode === "transient"
          ? ["transient_waveforms", "geometry_transient", "partial_inductance", ...(setup.transientCapacitanceModel !== "none" ? ["distributed_capacitance"] : []), "voltage_drop", "current_density", "tracks", "through_vias", "pads", "copper_zones", "package_resistance", "contact_resistance", ...(explicitReturn ? ["explicit_return_path"] : []), ...(returnPath.mode === "isolated_secondary" ? ["isolated_power_domain"] : [])]
          : ["dc_resistance", "tracks", "through_vias", "pads", "copper_zones", "package_resistance", "contact_resistance", ...(explicitReturn ? ["explicit_return_path"] : []), ...(returnPath.mode === "isolated_secondary" ? ["isolated_power_domain"] : [])],
      net_names: [...new Set([...(pathHandoff?.net_names ?? [net]), ...(explicitReturn ? [returnPath.net] : []), ...loopNets])],
      sources: [
        ...sources.map((item, index) => {
          const terminal = pathHandoff && index === 0 ? terminalWithPathAnchor(item, pathHandoff.source_terminal) : item;
          return { ...terminalPayload(terminal, "source"), net: terminal.net || net, terminal_role: "source_positive", domain_id: returnPath.domainId || "main" };
        }),
        ...(explicitReturn ? returnPath.sources.map(item => ({ ...terminalPayload(item, "source"), net: returnPath.net, voltage_v: 0, terminal_role: "source_return", domain_id: returnPath.domainId || "main" })) : []),
      ],
      loads: [
        ...loads.map((item, index) => {
          const terminal = pathHandoff && index === 0 ? terminalWithPathAnchor(item, pathHandoff.load_terminal) : item;
          return { ...terminalPayload(terminal, "load"), net: terminal.net || loadNet, terminal_role: "load_positive", pair_id: `load-pair-${index + 1}`, domain_id: returnPath.domainId || "main" };
        }),
        ...(explicitReturn ? returnPath.loads.map((item, index) => ({ ...terminalPayload({ ...item, value: String(-Math.abs(Number(loads[index]?.value ?? item.value))) }, "load"), net: returnPath.net, terminal_role: "load_return", pair_id: `load-pair-${index + 1}`, domain_id: returnPath.domainId || "main" })) : []),
      ],
      return_path: {
        mode: explicitReturn ? returnPath.mode : extractionReturnNet ? "explicit" : "implicit",
        net: explicitReturn ? returnPath.net : extractionReturnNet,
        domain_id: returnPath.domainId || "main",
        galvanically_isolated: returnPath.mode === "isolated_secondary",
      },
      probes: solverProbePayloads,
      frequency_start_hz: Number(setup.frequencyStart),
      frequency_stop_hz: Number(setup.frequencyStop),
      frequency_points: Number(setup.frequencyPoints),
      ...(requestedMode === "transient" ? {
        transient: {
          stop_time_s: parseSpiceNumber(setup.transientStopS, "Transient stop time"),
          time_step_s: setup.transientTimeStepMode === "auto"
            ? recommendedTransientStep()
            : parseSpiceNumber(setup.transientTimeStepS, "Transient integration step"),
          time_step_mode: setup.transientTimeStepMode,
          output_decimation: Number(setup.transientOutputDecimation),
          output_decimation_mode: setup.transientOutputDecimationMode,
          playback_fps: Number(setup.transientPlaybackFps),
          initial_condition: setup.transientInitialCondition,
          integration: "backward_euler",
          max_internal_steps: 50000,
          max_output_frames: 1000,
          max_solver_time_s: parseSpiceNumber(setup.transientMaxSolverTimeS, "Transient maximum solver time"),
          memory_budget_mb: Number(setup.transientMemoryBudgetMb),
          capacitance_model: setup.transientCapacitanceModel,
          visual_sample_limit: Number(setup.transientVisualSampleLimit),
        },
      } : {}),
      mesh: {
        dimension: setup.meshDimension,
        target_size_mm: Number(setup.meshTargetMm),
        zone_cell_mm: Number(setup.zoneCellMm),
        max_preview_cells: Number(setup.maxPreviewCells),
        memory_budget_mb: effectiveMeshMemoryBudgetBytes / 1024 ** 2,
        solver_memory_limit_gb: appSettings.solverMemoryLimitGb,
        fixed_memory_estimate_bytes: resourcePlan.budgets.fixedBytes,
        estimated_resident_bytes_per_cell: resourcePlan.estimates.totalBytesPerMeshCell,
        via_model: setup.viaModel,
        via_plating_thickness_mm: Number(setup.viaPlatingMm),
      },
      limits: { max_voltage_drop_mv: Number(limits.drop), max_current_density_a_mm2: Number(limits.density) },
      options: {
        topology,
        pi_path: pathHandoff?.pi_path,
        via_model: setup.viaModel,
        loop_extractions: loopExtractions,
        pdn_candidate_ports: requestedMode === "ac"
          ? solverProbePayloads
              .filter(probe => probe.net === net)
              .slice(0, 64)
              .map(probe => ({
                id: probe.id,
                name: probe.name,
                net,
                position_mm: probe.position_mm,
                ...(probe.layer ? { layer: probe.layer, layer_scope: "single" } : { layer_scope: "connected_conductor" }),
                geometry_anchor: { id: probe.id, type: "probe" },
                endpoint_reviewed: true,
              }))
          : [],
        max_pdn_candidate_ports: 64,
        conductor_models: {
          skin_effect: setup.skinEffect,
          proximity_effect: setup.proximityEffect,
          surface_roughness_model: setup.roughnessModel,
          rms_roughness_um: Number(setup.roughnessUm),
          huray_nodule_radius_um: Number(setup.hurayNoduleRadiusUm),
          huray_surface_ratio: Number(setup.huraySurfaceRatio),
        },
        coupling: {
          enabled: requestedMode === "ac" && coupling.enabled,
          electric_field: coupling.electricField,
          magnetic_field: coupling.magneticField,
          search_scope: coupling.scope,
          search_radius_mm: Number(coupling.radiusMm),
          include_traces: coupling.includeTraces,
          include_planes: coupling.includePlanes,
          include_zones: coupling.includeZones,
          cross_layer: coupling.crossLayer,
          aggressor_selection: "geometry_proximity",
          victim_net: net,
        },
      },
    };
    if (requestedMode === "ac" && (!(spec.frequency_start_hz > 0) || !(spec.frequency_stop_hz > spec.frequency_start_hz) || !(spec.frequency_points >= 2))) {
      throw new Error("AC sweep requires positive start/stop frequencies and at least two points.");
    }
    if (requestedMode === "transient") {
      const stopTime = parseSpiceNumber(setup.transientStopS, "Transient stop time");
      const timeStep = setup.transientTimeStepMode === "auto"
        ? recommendedTransientStep()
        : parseSpiceNumber(setup.transientTimeStepS, "Transient integration step");
      const decimation = Number(setup.transientOutputDecimation);
      const playbackFps = Number(setup.transientPlaybackFps);
      const steps = Math.ceil(stopTime / timeStep);
      if (!(stopTime > 0) || !(timeStep > 0) || timeStep > stopTime) throw new Error("Transient stop time and integration step must be positive, with the step no larger than the run time.");
      if (!Number.isInteger(decimation) || decimation < 1) throw new Error("Transient output decimation must be a positive integer.");
      if (!Number.isFinite(playbackFps) || playbackFps < 1 || playbackFps > 30) throw new Error("Transient playback rate must be between 1 and 30 FPS.");
      if (steps > 50000) throw new Error("Transient setup exceeds 50,000 internal steps; increase the time step or shorten the run.");
      if (setup.transientOutputDecimationMode === "manual" && Math.ceil(steps / decimation) + 1 > 1000) throw new Error("Transient setup exceeds 1,000 saved frames; increase output decimation or enable automatic decimation.");
      if (!(parseSpiceNumber(setup.transientMaxSolverTimeS, "Transient maximum solver time") > 0)) throw new Error("Transient maximum solver time must be positive.");
      if (!(Number(setup.transientMemoryBudgetMb) >= 32)) throw new Error("Transient memory budget must be at least 32 MB.");
      if (!(Number(setup.transientVisualSampleLimit) >= 100)) throw new Error("Transient visual sample limit must be at least 100.");
    }
    if (!(Number(setup.meshTargetMm) > 0) || !(Number(setup.zoneCellMm) > 0) || !(Number(setup.maxPreviewCells) >= 100)) {
      throw new Error("Mesh sizes must be positive and the preview limit must be at least 100 cells.");
    }
    const capacityError = resourcePlan.reasons.find(reason => reason.severity === "error");
    if (capacityError) throw new Error(capacityError.message);
    if (requestedMode === "ac" && coupling.enabled && coupling.scope === "radius" && !(Number(coupling.radiusMm) > 0)) {
      throw new Error(`${net} requires a positive coupling search radius.`);
    }
    if (requestedMode === "ac" && ["hammerstad", "gradient"].includes(setup.roughnessModel) && !(Number(setup.roughnessUm) >= 0)) {
      throw new Error("The selected roughness model requires a non-negative RMS roughness.");
    }
    if (requestedMode === "ac" && setup.roughnessModel === "huray" && (!(Number(setup.hurayNoduleRadiusUm) > 0) || !(Number(setup.huraySurfaceRatio) > 0))) {
      throw new Error("The Huray model requires positive nodule radius and surface-area ratio values.");
    }
    return { contract: "spike/analysis-request/v1", design, spec };
  };
  const pathSegmentRequests = (request: PiPathAnalysisRequest) => (
    workflow === "path" && activePiPath && mode !== "dc"
      ? createPiPathSegmentExtractionRequests(request, activePiPath)
      : []
  );
  const preflightPathSegments = async (segments: ReturnType<typeof pathSegmentRequests>, pathRequest: PiPathAnalysisRequest, assemblyScope: AssemblyAnalysisScope | null) => {
    const preflights: Record<string, unknown>[] = [];
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      updateOperation(`Preflighting ${segment.net} (${index + 1}/${segments.length})`);
      const response = await runLocalWorker({ method: "preflight_analysis", params: { ...segment.request, assembly_scope: assemblyScope } });
      if (!response.ok || !response.result) throw new Error(response.error ?? `${segment.net} preflight returned no result.`);
      preflights.push(response.result);
    }
    updateOperation("Building the reviewed full-path mesh preview");
    const pathResponse = await runLocalWorker({ method: "preflight_analysis", params: { ...pathRequest, assembly_scope: assemblyScope } });
    if (!pathResponse.ok || !pathResponse.result) throw new Error(pathResponse.error ?? "Full-path preflight returned no result.");
    return combinePiPathPreflights(preflights, pathResponse.result);
  };
  const solvePathExtractions = async (segments: ReturnType<typeof pathSegmentRequests>, assemblyScope: AssemblyAnalysisScope | null) => {
    const results: Record<string, unknown>[] = [];
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      updateOperation(`Extracting ${segment.net} RLCG (${index + 1}/${segments.length})`);
      const response = await runLocalWorker({ method: "run_analysis", params: { ...segment.request, assembly_scope: assemblyScope } });
      if (!response.ok || !response.result) throw new Error(response.error ?? `${segment.net} PEEC extraction returned no result.`);
      if (String(response.result.status ?? "failed") !== "completed") {
        const issue = (response.result.issues as { message?: string }[] | undefined)?.find(item => item.message)?.message;
        throw new Error(issue ?? `${segment.net} PEEC extraction did not complete.`);
      }
      results.push(response.result);
    }
    if (!activePiPath) throw new Error("The reviewed series path is no longer available.");
    return combinePiPathSegmentExtractions(activePiPath, results);
  };
  const validateAndPreview = async () => {
    const startedAt = startOperation("preview", "Validating geometry and generating mesh");
    let meshCells = configuredMeshCells;
    try {
      setBusy(true);
      const assemblyScope = await onRequireAdmission(admissionWorkload);
      const request = buildRequest();
      const segments = pathSegmentRequests(request);
      const response = segments.length
        ? { ok: true, result: await preflightPathSegments(segments, request, assemblyScope) }
        : await runLocalWorker({ method: "preflight_analysis", params: { ...request, assembly_scope: assemblyScope } });
      if (!response.ok || !response.result) throw new Error("error" in response ? response.error ?? "Pre-solve validation returned no result." : "Pre-solve validation returned no result.");
      const result = response.result as unknown as {
        status: string;
        can_solve: boolean;
        summary: Record<string, number>;
        issues: DiagnosticIssue[];
        mesh: { cells: unknown[]; component_bridges?: unknown[]; dimension?: string; quality?: Record<string, number> };
      };
      meshCells = Number(result.summary.mesh_cell_count ?? meshCells);
      setPreflight(result);
      const elapsed = finishOperation(startedAt, "preview", meshCells);
      window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: {
        contract: "spike/v1",
        analysis_id: `mesh-preview-${Date.now()}`,
        status: "preview",
        mode,
        model_status: "approximate",
        summary: result.summary,
        fields: { visualization: {
          schema: "spike/result-visualization/v1",
          scalar_fields: {},
          vector_fields: {},
          mesh: result.mesh.cells,
          component_bridges: result.mesh.component_bridges ?? [],
        } },
        issues: result.issues,
        provenance: { generator: "spike/preflight/v1", solved: false, desktop_wall_time_s: Number(elapsed.toFixed(3)) },
      } }));
      onResult(result.can_solve
        ? `Pre-solve validation passed in ${formatRunDuration(elapsed)}; ${result.summary.mesh_cell_count ?? 0} ${result.mesh.dimension ?? "surface"} mesh cells previewed`
        : `Pre-solve validation blocked after ${formatRunDuration(elapsed)} by ${result.summary.errors ?? 0} error(s)`);
    } catch (error) {
      const elapsed = finishOperation(startedAt, "preview", meshCells, 1, false);
      onResult(`${error instanceof Error ? error.message : "Pre-solve validation failed."} (${formatRunDuration(elapsed)})`);
    } finally {
      setBusy(false);
    }
  };
  const runConvergence = async () => {
    const startedAt = startOperation("convergence", "Validating convergence study");
    let meshCells = configuredMeshCells;
    try {
      const baseRequest = buildRequest();
      setBusy(true);
      setConvergence(null);
      const assemblyScope = await onRequireAdmission(admissionWorkload);
      const request = { ...baseRequest, assembly_scope: assemblyScope };
      const segments = pathSegmentRequests(request);
      const validation = segments.length
        ? { ok: true, result: await preflightPathSegments(segments, request, assemblyScope) }
        : await runLocalWorker({ method: "preflight_analysis", params: request });
      if (!validation.ok || !validation.result?.can_solve) {
        const issue = (validation.result?.issues as { message?: string }[] | undefined)?.find(item => item.message)?.message;
        throw new Error(issue ?? ("error" in validation ? validation.error : undefined) ?? "Pre-solve validation blocked the convergence study.");
      }
      meshCells = Number((validation.result.summary as Record<string, unknown> | undefined)?.mesh_cell_count ?? meshCells);
      updateOperation("Running adaptive mesh convergence", meshCells);
      let report: ConvergenceReport;
      if (segments.length) {
        const reports: ConvergenceReport[] = [];
        for (let index = 0; index < segments.length; index += 1) {
          updateOperation(`Converging ${segments[index].net} (${index + 1}/${segments.length})`, meshCells);
          const response = await runLocalWorker({
            method: "mesh_convergence",
            params: { ...segments[index].request, assembly_scope: assemblyScope, options: { levels: [2, 1, 0.5, 0.25], minimum_levels: 3, stop_when_converged: true } },
          });
          if (!response.ok || !response.result) throw new Error(response.error ?? `${segments[index].net} returned no convergence report.`);
          reports.push(response.result as unknown as ConvergenceReport);
        }
        const passed = reports.every(item => item.can_sign_off);
        report = {
          status: passed ? "passed" : "failed_to_converge",
          can_sign_off: passed,
          levels: reports.flatMap((item, index) => item.levels.map(level => ({ ...level, status: `${segments[index].net}: ${level.status}` }))),
          comparisons: reports.flatMap((item, index) => item.comparisons.map(comparison => ({ ...comparison, metric: `${segments[index].net}: ${comparison.metric}` }))),
        };
      } else {
        const response = await runLocalWorker({
          method: "mesh_convergence",
          params: { ...request, options: { levels: [2, 1, 0.5, 0.25], minimum_levels: 3, stop_when_converged: true } },
        });
        if (!response.ok || !response.result) throw new Error(response.error ?? "The local worker returned no convergence report.");
        report = response.result as unknown as ConvergenceReport;
      }
      setConvergence(report);
      const elapsed = finishOperation(startedAt, "convergence", meshCells);
      if (report.result && typeof report.result === "object") {
        const timedResult = report.result as Record<string, unknown>;
        timedResult.provenance = { ...((timedResult.provenance as Record<string, unknown> | undefined) ?? {}), desktop_wall_time_s: Number(elapsed.toFixed(3)), operation: "mesh_convergence" };
      }
      const bundle = normalizeSolverResult(report.result);
      if (bundle) {
        window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: report.result }));
        onResult(
          `${report.can_sign_off ? "Mesh convergence passed" : "Mesh convergence failed"} in ${formatRunDuration(elapsed)}; fine-grid PI result loaded${report.can_sign_off ? "" : " for review"}`,
          {
            maxDropMv: Number(bundle.summary.max_voltage_drop_v ?? 0) * 1000,
            maxDensity: Number(bundle.summary.max_current_density_a_mm2 ?? 0),
            status: bundle.status,
            modelStatus: report.can_sign_off ? "Converged / approximate physics" : "Failed to converge",
          },
        );
      }
    } catch (error) {
      const elapsed = finishOperation(startedAt, "convergence", meshCells, 1, false);
      onResult(`${error instanceof Error ? error.message : "Mesh convergence failed."} (${formatRunDuration(elapsed)})`);
    } finally {
      setBusy(false);
    }
  };
  const exportRequest = () => {
    try {
      const activeJobs = setup.batchJobs.filter(job => job.mode !== "skip");
      const request = workflow === "batch"
        ? { contract: "spike/analysis-batch/v1", execution: "sequential", jobs: activeJobs.map(job => buildRequest(job)), created_at: new Date().toISOString() }
        : buildRequest();
      const url = URL.createObjectURL(new Blob([JSON.stringify(request, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = workflow === "batch" ? "spike-analysis-batch.json" : `spike-${mode}-analysis-request.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      onResult(workflow === "batch" ? `Batch exported with ${activeJobs.length} active net jobs` : `${mode.toUpperCase()} solver request exported with ${setup.sources.length} sources and ${setup.loads.length} sinks`);
    } catch (error) {
      onResult(error instanceof Error ? error.message : "Unable to generate analysis request");
    }
  };
  const resultFromResponse = (net: string, requestedMode: Exclude<BatchAnalysisMode, "skip">, response: Awaited<ReturnType<typeof runLocalWorker>>): BatchResult => {
    if (!response.ok || !response.result) {
      return { net, mode: requestedMode, status: "failed", modelStatus: "unsupported", detail: response.error ?? "The local worker returned no result." };
    }
    const status = String(response.result.status ?? "failed");
    const issue = analysisFailure(response.result.issues, "Analysis failed without an error diagnostic.");
    const summary = response.result.summary as { max_voltage_drop_v?: number; max_current_density_a_mm2?: number } | undefined;
    const bundle = normalizeSolverResult(response.result);
    const detail = status === "completed" && requestedMode === "dc"
      ? `${((summary?.max_voltage_drop_v ?? 0) * 1000).toFixed(2)} mV max drop`
      : status === "completed" && requestedMode === "transient"
        ? `${Number((response.result.summary as Record<string, unknown> | undefined)?.transient_frames ?? 0).toLocaleString()} saved frames`
        : issue ?? `${requestedMode.toUpperCase()} ${status}`;
    return { net, mode: requestedMode, status, modelStatus: String(response.result.model_status ?? "unsupported"), detail, bundle: bundle ?? undefined };
  };
  const inspectBatchResult = (result: BatchResult) => {
    if (!result.bundle) return;
    window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: result.bundle }));
    window.dispatchEvent(new CustomEvent("spike-analysis-net-selected", { detail: { net: result.net } }));
    onResult(`${result.net} ${result.mode.toUpperCase()} result loaded into the layout overlay`);
  };
  const runBatch = async () => {
    const activeJobs = setup.batchJobs.filter(job => job.mode !== "skip");
    if (!activeJobs.length) { onResult("Select DC, AC, or transient for at least one net before running the batch"); return; }
    const startedAt = startOperation("batch", `Preparing batch of ${activeJobs.length} nets`, configuredMeshCells, activeJobs.length);
    let timingFinished = false;
    setBusy(true);
    setBatchResults([]);
    const completed: BatchResult[] = [];
    try {
      const assemblyScope = await onRequireAdmission(activeJobs.some(job => job.mode === "ac" || job.mode === "transient") ? "pi_ac" : "pi_dc");
      for (const [jobIndex, job] of activeJobs.entries()) {
        try {
          updateOperation(`Batch ${jobIndex + 1}/${activeJobs.length}: ${job.mode.toUpperCase()} ${job.net}`);
          const jobStartedAt = Date.now();
          const request = { ...buildRequest(job), assembly_scope: assemblyScope };
          const transaction = await runLocalWorker({ method: "run_preflighted_analysis", params: request });
          if (!transaction.ok || !transaction.result || transaction.result.contract !== "spike/preflighted-analysis/v1") {
            throw new Error(transaction.error ?? "The worker returned no preflighted batch transaction.");
          }
          const preflight = transaction.result.preflight as Record<string, unknown> | undefined;
          if (!preflight?.can_solve) {
            const issue = analysisFailure(preflight?.issues, "Pre-solve validation blocked this job without an error diagnostic.");
            const jobElapsed = Math.max(0, (Date.now() - jobStartedAt) / 1000);
            completed.push({
              net: job.net,
              mode: job.mode as Exclude<BatchAnalysisMode, "skip">,
              status: "blocked",
              modelStatus: "unsupported",
              detail: `${issue ?? "Pre-solve validation blocked this job."} - ${formatRunDuration(jobElapsed)}`,
            });
            setBatchResults([...completed]);
            continue;
          }
          const response = {
            ok: Boolean(transaction.result.analysis_result),
            result: transaction.result.analysis_result as Record<string, unknown> | undefined,
          };
          const jobElapsed = Math.max(0, (Date.now() - jobStartedAt) / 1000);
          if (response.result) response.result.provenance = {
            ...((response.result.provenance as Record<string, unknown> | undefined) ?? {}),
            desktop_operation: `batch_${job.mode}`,
            desktop_wall_time_s: Number(jobElapsed.toFixed(3)),
          };
          const result = resultFromResponse(job.net, job.mode as Exclude<BatchAnalysisMode, "skip">, response);
          result.detail = `${result.detail} - ${formatRunDuration(jobElapsed)}`;
          completed.push(result);
          setBatchResults([...completed]);
        } catch (error) {
          completed.push({ net: job.net, mode: job.mode as Exclude<BatchAnalysisMode, "skip">, status: "failed", modelStatus: "unsupported", detail: error instanceof Error ? error.message : "Invalid analysis request" });
          setBatchResults([...completed]);
        }
      }
      const successful = completed.filter(result => result.status === "completed");
      const blocked = completed.filter(result => result.status === "blocked");
      if (successful[0]?.bundle) inspectBatchResult(successful[0]);
      window.dispatchEvent(new CustomEvent("spike-analysis-batch-complete", { detail: successful.map(result => result.bundle).filter(Boolean) }));
      const elapsed = finishOperation(startedAt, "batch", configuredMeshCells, activeJobs.length);
      timingFinished = true;
      onResult(`Batch finished in ${formatRunDuration(elapsed)}: ${successful.length} completed, ${blocked.length} blocked, ${completed.length - successful.length - blocked.length} failed`);
    } catch (error) {
      const elapsed = finishOperation(startedAt, "batch", configuredMeshCells, activeJobs.length, false);
      timingFinished = true;
      onResult(`${error instanceof Error ? error.message : "Batch analysis failed."} (${formatRunDuration(elapsed)})`);
    } finally {
      if (!timingFinished) finishOperation(startedAt, "batch", configuredMeshCells, activeJobs.length, false);
      setBusy(false);
    }
  };
  const run = async () => {
    const operationKind = mode as "dc" | "ac" | "transient";
    const startedAt = startOperation(operationKind, "Validating setup and solver mesh");
    let meshCells = configuredMeshCells;
    let timingFinished = false;
    let elapsed = 0;
    const completeTiming = (succeeded: boolean) => {
      if (!timingFinished) {
        elapsed = finishOperation(startedAt, operationKind, meshCells, 1, succeeded);
        timingFinished = true;
      }
      return elapsed;
    };
    setBusy(true);
    try {
      const assemblyScope = await onRequireAdmission(admissionWorkload);
      const request = { ...buildRequest(), assembly_scope: assemblyScope };
      const segments = pathSegmentRequests(request);
      let preflightedAnalysis: Record<string, unknown> | undefined;
      let validation: { ok: boolean; result?: Record<string, unknown>; error?: string };
      if (segments.length) {
        validation = { ok: true, result: await preflightPathSegments(segments, request, assemblyScope) };
      } else {
        const transaction = await runLocalWorker({ method: "run_preflighted_analysis", params: request });
        if (!transaction.ok || !transaction.result || transaction.result.contract !== "spike/preflighted-analysis/v1") {
          throw new Error(transaction.error ?? "The local worker returned no preflighted analysis transaction.");
        }
        validation = { ok: true, result: transaction.result.preflight as Record<string, unknown> };
        preflightedAnalysis = transaction.result.analysis_result as Record<string, unknown> | undefined;
      }
      if (validation.result) setPreflight(validation.result as unknown as NonNullable<typeof preflight>);
      const canSolve = Boolean(validation.result?.can_solve);
      if (!validation.ok || !canSolve) {
        throw new Error(analysisFailure(validation.result?.issues, validation.error ?? "Pre-solve validation blocked this analysis without an error diagnostic."));
      }
      meshCells = Number((validation.result?.summary as Record<string, unknown> | undefined)?.mesh_cell_count ?? meshCells);
      if (segments.length) {
        const combined = await solvePathExtractions(segments, assemblyScope);
        updateOperation(`Solving ${activePiPath?.label ?? "reviewed power path"} circuit`, meshCells);
        const response = await runLocalWorker({
          method: "run_pi_path_native_mna",
          params: {
            design: request.design,
            spec: request.spec,
            assembly_scope: assemblyScope,
            ...combined,
            resource_limits: { memory_limit_gb: appSettings.solverMemoryLimitGb },
          },
        });
        if (!response.ok || !response.result) throw new Error(response.error ?? "Path circuit solver returned no result.");
        if (String(response.result.status ?? "failed") !== "completed") {
          const compile = response.result.compile as { issues?: { message?: string }[] } | undefined;
          throw new Error(compile?.issues?.find(item => item.message)?.message ?? "Path circuit solve was blocked.");
        }
        const workerAnalysisResult = response.result.analysis_result as Record<string, unknown> | undefined;
        if (!workerAnalysisResult) throw new Error("Path circuit solver did not return an AnalysisResult contract.");
        const analysisResult = attachPiPathComponentBridges(workerAnalysisResult, validation.result);
        const duration = completeTiming(true);
        analysisResult.provenance = {
          ...((analysisResult.provenance as Record<string, unknown> | undefined) ?? {}),
          desktop_operation: operationKind,
          desktop_wall_time_s: Number(duration.toFixed(3)),
          segment_mesh_cell_count: meshCells,
        };
        window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: analysisResult }));
        onResult(`${mode === "ac" ? "AC" : "Transient"} series-path solve completed in ${formatRunDuration(duration)} across ${segments.length} reviewed copper segments. Spatial fields remain segment extraction results; no circuit field was inferred.`);
        onClose();
        return;
      }
      updateOperation(
        mode === "ac" ? "Solving PEEC impedance extraction" : mode === "transient" ? "Solving transient PEEC response" : "Solving DC current distribution",
        meshCells,
      );
      const response = { ok: Boolean(preflightedAnalysis), result: preflightedAnalysis };
      if (!response.ok || !response.result) throw new Error("The preflight passed but the solver returned no analysis result.");
      const resultSummary = response.result.summary as { max_voltage_drop_v?: number; max_current_density_a_mm2?: number } | undefined;
      const status = String(response.result.status ?? "failed");
      if (status !== "completed") throw new Error(analysisFailure(response.result.issues, "Analysis failed without an error diagnostic."));
      const duration = completeTiming(true);
      response.result.provenance = {
        ...((response.result.provenance as Record<string, unknown> | undefined) ?? {}),
        desktop_operation: operationKind,
        desktop_wall_time_s: Number(duration.toFixed(3)),
        desktop_estimated_time_s: Number(estimateOperationSeconds(operationKind, meshCells).toFixed(3)),
      };
      if (mode === "ac") {
        const peecSummary = response.result.summary as { partial_inductance_h?: number; resistance_start_ohm?: number; filament_count?: number };
        window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: response.result }));
        onResult(`PEEC RL complete in ${formatRunDuration(duration)}: ${((peecSummary.partial_inductance_h ?? 0) * 1e9).toFixed(3)} nH, ${((peecSummary.resistance_start_ohm ?? 0) * 1000).toFixed(3)} mOhm, ${peecSummary.filament_count ?? 0} filaments`);
        onClose();
        return;
      }
      if (mode === "transient") {
        const transientSummary = response.result.summary as { max_voltage_drop_v?: number; max_current_density_a_mm2?: number; peak_inductive_drop_v?: number; frame_count?: number };
        const summary: AnalysisSummary = {
          maxDropMv: Number(transientSummary.max_voltage_drop_v ?? 0) * 1000,
          maxDensity: Number(transientSummary.max_current_density_a_mm2 ?? 0),
          status,
          modelStatus: String(response.result.model_status ?? "approximate"),
        };
        window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: response.result }));
        onResult(`Transient RL complete in ${formatRunDuration(duration)}: ${summary.maxDropMv.toFixed(2)} mV peak drop, ${(Number(transientSummary.peak_inductive_drop_v ?? 0) * 1000).toFixed(2)} mV peak branch L di/dt, ${transientSummary.frame_count ?? 0} saved frames`, summary);
        onClose();
        return;
      }
      const summary: AnalysisSummary = {
        maxDropMv: (resultSummary?.max_voltage_drop_v ?? 0) * 1000,
        maxDensity: resultSummary?.max_current_density_a_mm2 ?? 0,
        status,
        modelStatus: String(response.result.model_status ?? "approximate"),
      };
      window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: response.result }));
      onResult(`DC complete in ${formatRunDuration(duration)}: ${summary.maxDropMv.toFixed(2)} mV maximum drop`, summary);
      onClose();
    } catch (error) {
      const duration = completeTiming(false);
      onResult(`${error instanceof Error ? error.message : "Analysis failed."} (${formatRunDuration(duration)})`);
    } finally {
      if (!timingFinished) completeTiming(false);
      setBusy(false);
    }
  };
  const terminalPadPicker = (item: PiTerminal, net: string, filterKey: string, onPad: (padId: string) => void) => {
    const allPads = (board?.pads ?? []).filter(pad => pad.net === net);
    const filteredPads = padsOnNet(net, filterKey);
    const currentPad = item.anchorType === "pad" ? allPads.find(pad => pad.id === item.anchorId) : undefined;
    const shownPads = currentPad && !filteredPads.some(pad => pad.id === currentPad.id) ? [currentPad, ...filteredPads] : filteredPads;
    const visiblePads = shownPads.slice(0, 80);
    return <div className="terminal-pad-picker" onMouseLeave={() => previewViewportTarget(null)}>
      <div className="terminal-pad-heading"><b>PADS ON {net || "UNASSIGNED NET"}</b><span>{filteredPads.length} of {allPads.length}</span></div>
      <input value={padFilters[filterKey] ?? ""} onChange={event => setPadFilters(current => ({ ...current, [filterKey]: event.target.value }))} placeholder="Filter reference, pad, layer, or coordinate" aria-label={`Filter pads for ${item.name}`} />
      <div className="terminal-pad-options" role="listbox" aria-label={`Pad location for ${item.name}`}>
        {!allPads.length && <span>No pads found on this net</span>}
        {visiblePads.map(pad => <button type="button" role="option" aria-selected={currentPad?.id === pad.id} className={currentPad?.id === pad.id ? "selected" : ""} key={pad.id} onMouseEnter={() => previewViewportTarget({ kind: "object", id: pad.id, type: "pad", net: pad.net, ref: pad.ref, layer: pad.layer, position: pad.at, label: padLabel(pad) })} onClick={() => { onPad(pad.id); previewViewportTarget(null); }}><b>{pad.ref ?? "?"}.{pad.name || "?"}</b><span>{pad.at[0].toFixed(3)}, {pad.at[1].toFixed(3)} mm</span><small>{expandSpan(pad.layers).join(" / ") || pad.layer}</small></button>)}
        {shownPads.length > visiblePads.length && <span>Refine the filter to show {shownPads.length - visiblePads.length} additional pads.</span>}
      </div>
    </div>;
  };
  const netBrowser = (value: string, choices: string[], label: string, onNet: (net: string) => void) => <details className="analysis-net-browser" onMouseLeave={() => previewViewportTarget(null)}>
    <summary aria-label={label}><Network size={14} /><span>{value || "Select a net"}</span><ChevronDown size={14} /></summary>
    <div className="analysis-net-options" role="listbox" aria-label={label}>{choices.map(net => <button type="button" role="option" aria-selected={net === value} className={net === value ? "selected" : ""} key={net} onMouseEnter={() => previewViewportTarget({ kind: "net", net, label: net })} onClick={event => { onNet(net); previewViewportTarget(null); const details = event.currentTarget.closest("details"); if (details) details.open = false; }}><Network size={12} /><span>{net}</span></button>)}</div>
  </details>;
  const terminalRows = (kind: "sources" | "loads", unit: string, job?: BatchNetJob) => <div className="terminal-list">
    <PiSiTerminalEditor key={`${job?.id ?? "single"}-${kind}`} rows={job?.[kind] ?? setup[kind]}
      label={`${kind === "sources" ? "Voltage sources" : "Current sinks"} · ${kind === "sources" ? sourceNetFor(job) : loadNetFor(job)}`}
      layers={layers} valueLabel={unit} transient={(job?.mode ?? mode) === "transient"}
      addLabel={kind === "sources" ? "Add source" : "Add sink"}
      pickActive={pickTarget?.kind === kind && pickTarget.jobId === job?.id}
      selectionAvailable={Boolean(selected)}
      onAdd={() => addTerminal(kind, job?.id)}
      onTogglePick={() => setPickTarget(current => current?.kind === kind && current.jobId === job?.id ? null : { kind, jobId: job?.id })}
      onUseSelection={() => placeFromSelection(kind, job?.id)}
      onChange={(id, patch) => updateTerminal(kind, id, {
        ...patch, ...("x" in patch || "y" in patch ? { anchorId: "", anchorType: "coordinate", net: kind === "sources" ? sourceNetFor(job) : loadNetFor(job) } : {}),
      }, job?.id)}
      onRemove={id => removeTerminal(kind, id, job?.id)}
      renderDetails={item => <>
        {(job?.mode ?? mode) === "transient" && <TransientWaveformEditor value={item} stopTimeS={setup.transientStopS} quantity={kind === "sources" ? "voltage" : "current"} onChange={patch => updateTerminal(kind, item.id, patch, job?.id)} />}
        {terminalPadPicker(item, kind === "sources" ? sourceNetFor(job) : loadNetFor(job), `${job?.id ?? "single"}-${kind}-${item.id}`, padId => selectTerminalPad(kind, item.id, padId, job?.id))}
        <div className="terminal-scope">{item.layer && item.layer !== "auto" ? `Restricted to ${item.layer}` : item.anchorId ? `Anchored to ${item.anchorType} ${item.anchorId} across ${item.layers?.length ? item.layers.join(", ") : "its connected copper layers"}` : "Coordinate resolves on the selected net's connected conductor"}</div>
      </>} />
  </div>;
  const returnTerminalRows = (kind: "sources" | "loads") => {
    const pickerKind = kind === "sources" ? "returnSources" : "returnLoads";
    return <div className="terminal-list">
      <PiSiTerminalEditor key={`return-${kind}`} rows={setup.returnPath[kind]}
        label={`${kind === "sources" ? "Return references" : "Paired returns"} · ${setup.returnPath.net}`}
        layers={layers} valueLabel={kind === "sources" ? "Reference (V)" : "Paired current"}
        addLabel={kind === "sources" ? "Add reference" : "Add paired return"}
        pickActive={pickTarget?.kind === pickerKind}
        activePickLabel="Click exact return point"
        selectionAvailable={Boolean(selected)}
        onAdd={() => addReturnTerminal(kind)}
        onTogglePick={() => setPickTarget(current => current?.kind === pickerKind ? null : { kind: pickerKind })}
        onUseSelection={() => placeReturnFromSelection(kind)}
        readOnlyValue={kind === "sources" ? () => "0 V reference" : (_item, index) => setup.loads[index]?.value ? `${setup.loads[index].value} A return` : "Assign matching sink"}
        onChange={(id, patch) => updateReturnTerminal(kind, id, {
          ...patch, ...("x" in patch || "y" in patch ? { anchorId: "", anchorType: "coordinate", net: setup.returnPath.net } : {}),
        })}
        onRemove={id => removeReturnTerminal(kind, id)}
        renderDetails={item => <>
          {terminalPadPicker(item, setup.returnPath.net, `return-${kind}-${item.id}`, padId => selectReturnPad(kind, item.id, padId))}
          <div className="terminal-scope">{item.anchorId ? `Anchored to ${item.anchorType} ${item.anchorId} across its connected copper layers` : `Coordinate resolves on ${setup.returnPath.net || "the selected return net"}`}</div>
        </>} />
    </div>;
  };
  const activeBatchJob = setup.batchJobs.find(job => job.id === selectedBatchId)
    ?? setup.batchJobs.find(job => job.mode !== "skip")
    ?? setup.batchJobs[0];
  const transientRecommendedStep = recommendedTransientStep();
  const transientStopTime = tryParseSpiceNumber(setup.transientStopS, 0);
  const transientEffectiveStep = setup.transientTimeStepMode === "auto" ? transientRecommendedStep : tryParseSpiceNumber(setup.transientTimeStepS, 0);
  const transientStepCount = Math.max(0, Math.ceil(transientStopTime / transientEffectiveStep) || 0);
  const meshTarget = Math.max(Number(setup.meshTargetMm) || 1, 0.001);
  const memoryBudgetBytes = Math.max(32, Number(setup.transientMemoryBudgetMb) || 2048) * 1024 ** 2;
  const transientBranchCapacity = Math.max(16, Math.floor(Math.sqrt(memoryBudgetBytes * 0.65 / 160)));
  const estimatedPhysicalBranches = Math.min(transientBranchCapacity, Math.max(16,
    (board?.tracks.reduce((sum, track) => sum + Math.max(1, Math.ceil(Math.hypot(track.end[0] - track.start[0], track.end[1] - track.start[1]) / meshTarget)), 0) ?? 0)
    + (board?.vias.length ?? 0)
    + (board?.pads.length ?? 0) * 2
    + (board?.zones.length ?? 0) * 6,
  ));
  const estimatedNodes = estimatedPhysicalBranches + 1;
  const estimatedMatrixOrder = estimatedPhysicalBranches + estimatedNodes;
  const estimatedDenseBytes = 8 * (10 * estimatedPhysicalBranches ** 2 + 3 * estimatedMatrixOrder ** 2 + estimatedNodes ** 2);
  const visualLimit = Math.max(100, Number(setup.transientVisualSampleLimit) || 12000);
  const outputNodes = Math.min(estimatedNodes, Math.max(50, Math.floor(visualLimit / 3)));
  const outputBranches = Math.min(estimatedPhysicalBranches, Math.max(50, visualLimit - outputNodes));
  const frameResidentBytes = (2 * outputNodes + 6 * outputBranches) * 32 + 2048;
  const staticLayoutBytes = (outputNodes + outputBranches) * 320;
  const requestedTransientDecimation = Math.max(1, Number(setup.transientOutputDecimation) || 1);
  const allowedMemoryFrames = Math.max(2, Math.floor((memoryBudgetBytes - estimatedDenseBytes - staticLayoutBytes) / Math.max(frameResidentBytes, 1)));
  const allowedTransientFrames = Math.max(2, Math.min(1000, allowedMemoryFrames));
  const transientEffectiveDecimation = setup.transientOutputDecimationMode === "auto"
    ? Math.max(requestedTransientDecimation, Math.ceil(transientStepCount / Math.max(allowedTransientFrames - 1, 1)))
    : requestedTransientDecimation;
  const transientFrameCount = transientStepCount ? Math.ceil(transientStepCount / transientEffectiveDecimation) + 1 : 0;
  const transientOutputBytes = staticLayoutBytes + transientFrameCount * frameResidentBytes;
  const transientPeakBytes = estimatedDenseBytes + transientOutputBytes;
  const memoryLabel = (value: number) => value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(2)} GB` : `${(value / 1024 ** 2).toFixed(1)} MB`;
  const applyTransientRunPreset = (preset: "fast" | "load" | "startup") => {
    const patch = preset === "fast"
      ? { transientStopS: "25us", transientTimeStepMode: "auto" as const, transientOutputDecimationMode: "auto" as const }
      : preset === "load"
        ? { transientStopS: "2ms", transientTimeStepMode: "auto" as const, transientOutputDecimationMode: "auto" as const }
        : { transientStopS: "20ms", transientTimeStepMode: "auto" as const, transientOutputDecimationMode: "auto" as const };
    setSetup(current => ({ ...current, ...patch }));
  };
  const transientRunControls = (mode === "transient" || (workflow === "batch" && activeBatchJob?.mode === "transient")) && <div className="wizard-section transient-controls transient-controls-primary"><div className="transient-section-heading"><label>TRANSIENT CONTROL</label><span>SPICE-compatible time values</span></div>
    <div className="transient-run-presets"><button type="button" onClick={() => applyTransientRunPreset("fast")}><Activity size={12} /> Fast event</button><button type="button" onClick={() => applyTransientRunPreset("load")}><Waves size={12} /> Load transient</button><button type="button" onClick={() => applyTransientRunPreset("startup")}><Play size={12} /> Startup</button></div>
    <div className="sweep-grid transient-run-grid">
      <label>Simulation stop<input value={setup.transientStopS} onChange={event => setSetup(current => ({ ...current, transientStopS: event.target.value }))} placeholder="1ms" /></label>
      <label>Time-step policy<select value={setup.transientTimeStepMode} onChange={event => setSetup(current => ({ ...current, transientTimeStepMode: event.target.value as PiSetup["transientTimeStepMode"] }))}><option value="auto">Auto from fastest edge</option><option value="manual">Manual</option></select></label>
      <label>Integration step<input value={setup.transientTimeStepMode === "auto" ? formatEngineering(transientRecommendedStep, "s") : setup.transientTimeStepS} disabled={setup.transientTimeStepMode === "auto"} onChange={event => setSetup(current => ({ ...current, transientTimeStepS: event.target.value }))} placeholder="100ns" /></label>
      <label>Saved-frame policy<select value={setup.transientOutputDecimationMode} onChange={event => setSetup(current => ({ ...current, transientOutputDecimationMode: event.target.value as PiSetup["transientOutputDecimationMode"] }))}><option value="auto">Auto memory bound</option><option value="manual">Manual</option></select></label>
      <label>Save every N steps<input value={setup.transientOutputDecimation} disabled={setup.transientOutputDecimationMode === "auto"} onChange={event => setSetup(current => ({ ...current, transientOutputDecimation: event.target.value }))} /></label>
      <label>Playback rate (FPS)<input value={setup.transientPlaybackFps} onChange={event => setSetup(current => ({ ...current, transientPlaybackFps: event.target.value }))} /></label>
      <label>Maximum solver time<input value={setup.transientMaxSolverTimeS} onChange={event => setSetup(current => ({ ...current, transientMaxSolverTimeS: event.target.value }))} placeholder="120s" /></label>
      <label>Memory budget (MB)<input value={setup.transientMemoryBudgetMb} onChange={event => setSetup(current => ({ ...current, transientMemoryBudgetMb: event.target.value }))} /></label>
      <label>Visual sample limit<input value={setup.transientVisualSampleLimit} onChange={event => setSetup(current => ({ ...current, transientVisualSampleLimit: event.target.value }))} /></label>
      <label>Distributed capacitance<select value={setup.transientCapacitanceModel} onChange={event => setSetup(current => ({ ...current, transientCapacitanceModel: event.target.value as PiSetup["transientCapacitanceModel"] }))}><option value="auto">Auto from stackup</option><option value="stackup_shunt">Stackup shunt approximation</option><option value="none">R/L only</option></select></label>
      <label>Initial state<select value={setup.transientInitialCondition} onChange={event => setSetup(current => ({ ...current, transientInitialCondition: event.target.value as PiSetup["transientInitialCondition"] }))}><option value="operating_point">Operating point at t=0</option><option value="zero">Zero branch current</option></select></label>
      <div className={`transient-budget ${transientPeakBytes > memoryBudgetBytes ? "over-budget" : ""}`}>
        <span>Internal steps</span><b>{transientStepCount.toLocaleString()}</b><span>Effective save interval</span><b>{transientEffectiveDecimation.toLocaleString()}</b><span>Saved frames</span><b>{transientFrameCount.toLocaleString()}</b><span>Estimated result storage</span><b>{memoryLabel(transientOutputBytes)}</b><span>Estimated worker peak</span><b>{memoryLabel(transientPeakBytes)}</b><span>Configured budget</span><b>{memoryLabel(memoryBudgetBytes)}</b>
      </div>
    </div>
    <small className="mesh-scope-note">Automatic integration resolves the fastest configured edge with ten samples. Output decimation changes stored playback resolution only; every internal step is still solved.</small>
  </div>;
  const updateCoupling = (job: BatchNetJob, patch: Partial<CouplingSetup>) => {
    updateBatchJob(job.id, { coupling: { ...job.coupling, ...patch } });
  };
  const activeRunJobs = workflow === "batch" ? Math.max(1, setup.batchJobs.filter(job => job.mode !== "skip").length) : 1;
  const plannedOperation = workflow === "batch" ? "batch" : mode as OperationKind;
  const plannedEstimate = estimateOperationSeconds(plannedOperation, configuredMeshCells, activeRunJobs);
  const maximumDockWidth = Math.min(window.innerWidth - 16, 720);
  const maximumDockHeight = Math.max(96, Math.min(520, Math.floor((window.innerHeight - 270) * 0.55)));
  const hostStyle: CSSProperties = panelDock === "float"
    ? {}
    : panelDock === "bottom"
      ? { height: panelCollapsed ? 40 : Math.min(panelFrame.height, maximumDockHeight) }
      : { width: panelCollapsed ? 34 : Math.min(panelFrame.width, maximumDockWidth) };
  const panelStyle: CSSProperties = panelDock === "float"
    ? { left: panelFrame.x, top: panelFrame.y, right: "auto", bottom: "auto", width: panelFrame.width, height: panelCollapsed ? 40 : panelFrame.height }
    : {};
  const resizeEdge = panelDock === "right" ? "left" : panelDock === "left" ? "right" : panelDock === "bottom" ? "top" : "corner";
  const dcValidityNotice = convergence?.can_sign_off
    ? {
      state: "passed",
      title: "Mesh convergence passed",
      detail: `${convergence.levels.length} refinement levels established numerical stability for this exact net, terminal, load, via-model, and mesh setup.`,
    }
    : convergence
      ? {
        state: "failed",
        title: "Mesh convergence failed",
        detail: "The conductor geometry is present, but one or more required voltage-drop, copper-loss, load-current, or robust current-density metrics changed beyond tolerance between the finest meshes. Review the comparison below before sign-off.",
      }
      : {
        state: "pending",
        title: "Mesh convergence not run",
        detail: "No geometry is reported missing by this notice. DC includes tracks, vias, pads, zones, and assigned contact/package resistance. Run Convergence to compare coarse-to-fine meshes; exploratory solves are allowed, but engineering sign-off remains approximate until the required metrics pass.",
      };
  if (panelCollapsed) return null;
  return <div className={`analysis-setup-dock-host dock-${panelDock}`} style={hostStyle}>
    {panelMoving && <><div className={`pi-dock-target left ${panelDropTarget === "left" ? "active" : ""}`} /><div className={`pi-dock-target right ${panelDropTarget === "right" ? "active" : ""}`} /><div className={`pi-dock-target bottom ${panelDropTarget === "bottom" ? "active" : ""}`} /></>}
    <div ref={panelRef} data-managed-dock="true" data-shared-stage={sharedStage.toLowerCase()} className={`floating-panel pi-run-dialog batch-capable dock-${panelDock} ${panelMoving ? "panel-moving" : ""}`} style={panelStyle}>
    <div className="floating-heading" onPointerDown={beginPanelMove} title="Drag to move and dock"><div className="pi-panel-title-toggle"><b>PI ANALYSIS SETUP</b>{pickTarget && <small>Pick a copper object in the 2D or 3D viewport</small>}</div><span className="panel-heading-actions"><button className={panelDock === "left" ? "active" : ""} onClick={() => setPanelDock("left")} title="Dock setup left"><PanelLeft size={15} /></button><button className={panelDock === "bottom" ? "active" : ""} onClick={() => setPanelDock("bottom")} title="Dock setup bottom"><PanelBottom size={15} /></button><button className={panelDock === "right" ? "active" : ""} onClick={() => setPanelDock("right")} title="Dock setup right"><PanelRight size={15} /></button><button className={panelDock === "float" ? "active" : ""} onClick={() => setPanelDock("float")} title="Float setup panel"><PinOff size={15} /></button><button onClick={minimizePanel} title="Minimize setup to the bottom tool shelf"><ChevronDown size={15} /></button><button disabled={busy} onClick={onClose} title={busy ? "Wait for the active operation to finish" : "Close setup"}><X size={15} /></button></span></div>
    <div className="pi-dialog-body">
      <div className="shared-stage-switch" role="tablist" aria-label="Shared simulation stage"><button role="tab" aria-selected={sharedStage === "Mesh"} className={sharedStage === "Mesh" ? "selected" : ""} onClick={() => onSharedStage("Mesh")}><Grid3X3 size={14} /> Mesh</button><button role="tab" aria-selected={sharedStage === "Solve"} className={sharedStage === "Solve" ? "selected" : ""} onClick={() => onSharedStage("Solve")}><Play size={14} /> Solve</button></div>
      <div className="analysis-workflow-switch" role="tablist" aria-label="Analysis workflow">
        <button className={workflow === "single" ? "selected" : ""} onClick={() => setWorkflow("single")} title="Solve one electrically continuous copper net">Direct net</button>
        <button className={workflow === "path" ? "selected" : ""} onClick={() => { setWorkflow("path"); if (!activePiPath && compiledPiPaths[0]) activatePowerPath(compiledPiPaths[0].id); }} title="Solve an ordered source-to-load chain across nets and reviewed series parts">Series path</button>
        <button className={workflow === "batch" ? "selected" : ""} onClick={() => setWorkflow("batch")} title="Run independent DC or AC jobs for multiple nets">Independent batch</button>
      </div>
      {(workflow === "single" || workflow === "path") && <>
      <div className="wizard-section pi-path-section"><label>ANALYSIS PATH</label>
        {workflow === "single" && <>
          <div className="pi-workflow-description"><Network size={15} /><span><b>Direct copper net</b><small>Source and sink must be on the same connected net. Series components are not crossed in this mode.</small></span></div>
          {netBrowser(setup.net, availableNets, "Power net", net => { setSetup(current => ({ ...current, net, powerPathId: "", sources: current.sources.map(item => ({ ...item, net })), loads: current.loads.map(item => ({ ...item, net })) })); window.dispatchEvent(new CustomEvent("spike-analysis-net-selected", { detail: { net } })); })}
        </>}
        {workflow === "path" && <>
          <select value={setup.powerPathId} onChange={event => activatePowerPath(event.target.value)} aria-label="Series power path">
            <option value="">Select a reviewed Power Tree path</option>
            {compiledPiPaths.map(path => <option key={path.id} value={path.id}>{path.label}{path.issues.length ? " - review required" : ""}</option>)}
          </select>
          {!compiledPiPaths.length && <div className="pi-path-empty"><AlertTriangle size={15} /><span><b>No series path is defined</b><small>Build or extract an ordered source-to-load path in the Power Tree, including each intervening part and net segment.</small></span></div>}
        </>}
        {workflow === "path" && activePiPath && <div className={`pi-path-chain ${activePiPath.issues.length ? "invalid" : "ready"}`}>
          <div className="pi-path-chain-heading"><b>{activePiPath.label}</b><span>{activePiPath.segments.length} nets / {activePiPath.transitions.length} interfaces</span></div>
          <div className="pi-path-chain-flow">{activePiPath.segments.map((segment, index) => <span key={segment.id}><strong>{segment.net}</strong>{activePiPath.transitions[index] && <><ArrowRight size={13} /><em>{activePiPath.transitions[index].component_ref}</em><ArrowRight size={13} /></>}</span>)}</div>
          {activePiPath.issues.map(issue => <small key={issue}><AlertTriangle size={12} /> {issue}</small>)}
        </div>}
        {workflow === "path" && <><div className="terminal-actions"><button className="secondary-btn" onClick={onOpenPowerPaths}><Network size={14} /> {compiledPiPaths.length ? "Edit power paths" : "Create power path"}</button><button className="secondary-btn" onClick={onOpenSpice}><Microchip size={14} /> Review component models</button></div><small className="mesh-scope-note">Each series part is an explicit circuit interface between adjacent copper meshes. Reviewed linear R/L/C interfaces run in cross-net DC; nonlinear and time-dependent devices use the SPICE co-simulation workflow.</small></>}
      </div>
      {transientRunControls}
      <div className="wizard-section solve-only"><label>VOLTAGE SOURCES</label>{terminalRows("sources", "Voltage (V)")}</div>
      <div className="wizard-section solve-only"><label>CURRENT SINKS</label>{terminalRows("loads", "Current (A)")}</div>
      {mode !== "ac" && <div className="wizard-section solve-only"><label>RETURN PATH / GROUND</label>
        <div className="model-options">
          <label>Loop model<select value={setup.returnPath.mode} onChange={event => setSetup(current => ({ ...current, returnPath: { ...current.returnPath, mode: event.target.value as ReturnPathMode } }))}><option value="implicit">Rail-only approximation</option><option value="explicit">Explicit board return / ground</option><option value="isolated_secondary">Isolated transformer secondary</option></select></label>
          {setup.returnPath.mode !== "implicit" && <><div className="model-field"><span>Return / ground net</span>{netBrowser(setup.returnPath.net, availableNets.filter(name => name !== setup.net), "Return or ground net", net => { setSetup(current => ({ ...current, returnPath: { ...current.returnPath, net } })); window.dispatchEvent(new CustomEvent("spike-analysis-net-selected", { detail: { net } })); })}</div><label>Power domain<input value={setup.returnPath.domainId} onChange={event => setSetup(current => ({ ...current, returnPath: { ...current.returnPath, domainId: event.target.value } }))} placeholder="main or isolated-secondary-1" /></label></>}
        </div>
        {setup.returnPath.mode !== "implicit" && <><div className="return-terminal-group"><div className="return-terminal-heading"><b>SOURCE RETURN / LOCAL REFERENCE</b><small>Anchor the source-side electrical reference on its connected copper.</small></div>{returnTerminalRows("sources")}</div><div className="return-terminal-group"><div className="return-terminal-heading"><b>LOAD RETURNS</b><small>Place one return terminal for each current sink. Currents are paired automatically.</small></div>{returnTerminalRows("loads")}</div></>}
        {setup.returnPath.mode === "isolated_secondary" && <div className="stack-warning"><ShieldAlert size={15} /> The secondary uses its own 0 V reference and is not connected to primary ground. This boundary model does not simulate transformer magnetics, leakage, saturation, loss, or interwinding capacitance.</div>}
      </div>}
      <div className="wizard-section"><label>MESH</label><div className="sweep-grid"><label>Representation<select value={setup.meshDimension} onChange={event => setSetup(current => ({ ...current, meshDimension: event.target.value as PiSetup["meshDimension"] }))}><option value="surface_2_5d">2.5D connected conductor</option><option value="volume_3d">3D conductor volume</option></select></label><label>Target size (mm)<input value={setup.meshTargetMm} onChange={event => setSetup(current => ({ ...current, meshTargetMm: event.target.value }))} /></label><label>Zone cell (mm)<input value={setup.zoneCellMm} onChange={event => setSetup(current => ({ ...current, zoneCellMm: event.target.value }))} /></label><label>Preview cell limit<input value={setup.maxPreviewCells} onChange={event => setSetup(current => ({ ...current, maxPreviewCells: event.target.value }))} /></label></div><div className={`preflight-summary ${resourcePlan.status === "inadmissible" ? "blocked" : "ready"}`}><div><b>{resourcePlan.status === "inadmissible" ? "RESOURCE LIMIT EXCEEDED" : "RESOURCE PLAN"}</b><span>{resourcePlan.budgets.recommendedMeshCells === null ? "Worker admission will apply a 512 MB fallback" : `${resourcePlan.budgets.recommendedMeshCells.toLocaleString()} recommended · ${resourcePlan.budgets.admissibleMeshCells?.toLocaleString()} hard estimate`}</span></div><small>{resourcePlan.reasons[resourcePlan.reasons.length - 1]?.message ?? resourcePlan.disclaimer}</small></div>{setup.meshDimension === "volume_3d" && <small className="mesh-scope-note">3D conductor volumes are generated for inspection and solver-plugin exchange. The current DC and PEEC engines solve the connected hybrid graph; dielectric and air-volume full-wave solving remains capability-gated.</small>}</div>
      <div className="wizard-section"><label>VIA MODEL</label><div className="sweep-grid"><label>Representation<select value={setup.viaModel} onChange={event => setSetup(current => ({ ...current, viaModel: event.target.value as PiSetup["viaModel"] }))}><option value="extracted">Extracted drill and span</option><option value="plated_cylinder">Plated-cylinder approximation</option></select></label><label>Plating thickness (mm)<input value={setup.viaPlatingMm} onChange={event => setSetup(current => ({ ...current, viaPlatingMm: event.target.value }))} /></label></div></div>
      {mode === "ac" && <><div className="wizard-section"><label>FREQUENCY SWEEP</label><div className="sweep-grid"><label>Start (Hz)<input value={setup.frequencyStart} onChange={event => setSetup(current => ({ ...current, frequencyStart: event.target.value }))} /></label><label>Stop (Hz)<input value={setup.frequencyStop} onChange={event => setSetup(current => ({ ...current, frequencyStop: event.target.value }))} /></label><label>Points<input value={setup.frequencyPoints} onChange={event => setSetup(current => ({ ...current, frequencyPoints: event.target.value }))} /></label></div></div><div className="wizard-section"><label>CONDUCTOR EFFECTS</label><div className="model-options"><label><input type="checkbox" checked={setup.skinEffect} onChange={event => setSetup(current => ({ ...current, skinEffect: event.target.checked }))} /> Skin effect</label><label><input type="checkbox" checked={setup.proximityEffect} onChange={event => setSetup(current => ({ ...current, proximityEffect: event.target.checked }))} /> Proximity effect</label><label>Surface roughness<select value={setup.roughnessModel} onChange={event => setSetup(current => ({ ...current, roughnessModel: event.target.value as PiSetup["roughnessModel"] }))}><option value="none">Disabled</option><option value="hammerstad">Hammerstad correction</option><option value="huray">Huray snowball</option><option value="gradient">Gradient model</option></select></label>{setup.roughnessModel === "huray" ? <><label>Nodule radius (µm)<input value={setup.hurayNoduleRadiusUm} onChange={event => setSetup(current => ({ ...current, hurayNoduleRadiusUm: event.target.value }))} /></label><label>Surface-area ratio<input value={setup.huraySurfaceRatio} onChange={event => setSetup(current => ({ ...current, huraySurfaceRatio: event.target.value }))} /></label></> : setup.roughnessModel !== "none" ? <label>RMS roughness (µm)<input value={setup.roughnessUm} onChange={event => setSetup(current => ({ ...current, roughnessUm: event.target.value }))} /></label> : null}</div></div></>}
      {mode === "dc"
        ? <div className={`stack-warning model-validity-notice ${dcValidityNotice.state}`}>{dcValidityNotice.state === "passed" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}<span><b>{dcValidityNotice.title}</b><small>{dcValidityNotice.detail}</small></span></div>
        : <div className="stack-warning model-validity-notice pending"><AlertTriangle size={15} /><span><b>{mode === "ac" ? "Quasi-static AC validity limits" : "Experimental transient validity limits"}</b><small>{mode === "ac" ? "Native PEEC RL extraction supports the connected hybrid trace, pad, zone, and via mesh. Capacitance, proximity effect, and roughness remain capability-gated." : "Experimental PEEC RLC transient solves geometry resistance and full partial-inductance coupling. Stackup capacitance is a single-reference quasi-static approximation; via capacitance, dielectric loss, radiation, nonlinear parts, and closed-loop controls remain capability-gated."}</small></span></div>}
      </>}
      {workflow === "batch" && <>
        <div className="wizard-section batch-section"><label>NET JOBS</label><div className="batch-toolbar"><input value={batchFilter} onChange={event => setBatchFilter(event.target.value)} placeholder="Filter nets" aria-label="Filter batch nets" /><span>{setup.batchJobs.filter(job => job.mode !== "skip").length} active of {setup.batchJobs.length}</span><button onClick={() => setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => ({ ...job, mode: "dc", solverId: "auto" })) }))}>All DC</button><button onClick={() => setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => ({ ...job, mode: "ac", solverId: "auto" })) }))}>All AC</button><button onClick={() => setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => ({ ...job, mode: "transient", solverId: "auto" })) }))}>All transient</button><button onClick={() => setSetup(current => ({ ...current, batchJobs: current.batchJobs.map(job => ({ ...job, mode: "skip", solverId: "auto" })) }))}>Clear</button></div><DataTable label="Batch net jobs" className="batch-jobs-table" searchable={false} onMouseLeave={() => previewViewportTarget(null)}><thead><tr><th>Net</th><th>Simulation</th><th>Solver engine</th></tr></thead><tbody>{setup.batchJobs.filter(job => job.net.toLowerCase().includes(batchFilter.toLowerCase())).map(job => <tr className={activeBatchJob?.id === job.id ? "selected" : ""} key={job.id} onMouseEnter={() => previewViewportTarget({ kind: "net", net: job.net, label: job.net })}><td><button onClick={() => setSelectedBatchId(job.id)}><Network size={13} /><span>{job.net}</span>{job.mode === "ac" && job.coupling.enabled && <Waves size={12} />}</button></td><td><select value={job.mode} onChange={event => { updateBatchJob(job.id, { mode: event.target.value as BatchAnalysisMode, solverId: "auto" }); setSelectedBatchId(job.id); }} aria-label={`${job.net} simulation type`}><option value="skip">Skip</option><option value="dc">DC</option><option value="ac">AC</option><option value="transient">Transient</option></select></td><td><select value={job.solverId} disabled={job.mode === "skip"} onChange={event => { updateBatchJob(job.id, { solverId: event.target.value }); setSelectedBatchId(job.id); }} aria-label={`${job.net} solver engine`}><option value="auto">Auto engine</option>{solverCatalog.filter(solver => solver.id === job.solverId || (job.mode !== "skip" && solver.analyses.includes(job.mode) && solver.runnable !== false && ["available", "experimental"].includes(solver.state))).map(solver => <option key={solver.id} value={solver.id} disabled={solver.runnable === false || !["available", "experimental"].includes(solver.state)}>{solver.name}{solver.state === "available" ? "" : ` - ${solver.state.replace(/_/g, " ")}`}</option>)}</select></td></tr>)}</tbody></DataTable></div>
        {activeBatchJob && activeBatchJob.mode !== "skip" && <div className="batch-job-editor">
          <div className="batch-job-heading"><div><b>{activeBatchJob.net}</b><span>{activeBatchJob.mode.toUpperCase()} job configuration</span></div><span className={`job-mode ${activeBatchJob.mode}`}>{activeBatchJob.mode}</span></div>
          <div className="wizard-section"><label>VOLTAGE SOURCES</label>{terminalRows("sources", "Voltage (V)", activeBatchJob)}</div>
          <div className="wizard-section"><label>CURRENT SINKS</label>{terminalRows("loads", "Current (A)", activeBatchJob)}</div>
          {activeBatchJob.mode === "ac" && <>
            <div className="wizard-section"><label>FREQUENCY SWEEP</label><div className="sweep-grid"><label>Start (Hz)<input value={setup.frequencyStart} onChange={event => setSetup(current => ({ ...current, frequencyStart: event.target.value }))} /></label><label>Stop (Hz)<input value={setup.frequencyStop} onChange={event => setSetup(current => ({ ...current, frequencyStop: event.target.value }))} /></label><label>Points<input value={setup.frequencyPoints} onChange={event => setSetup(current => ({ ...current, frequencyPoints: event.target.value }))} /></label></div></div>
            <div className="wizard-section"><label>NEIGHBOUR COUPLING</label><div className="coupling-header"><label><input type="checkbox" checked={activeBatchJob.coupling.enabled} onChange={event => updateCoupling(activeBatchJob, { enabled: event.target.checked })} /> Analyse interference from nearby conductors</label><span>{activeBatchJob.coupling.enabled ? "CAPABILITY REQUIRED" : "OFF"}</span></div>{activeBatchJob.coupling.enabled && <div className="coupling-grid"><label><input type="checkbox" checked={activeBatchJob.coupling.electricField} onChange={event => updateCoupling(activeBatchJob, { electricField: event.target.checked })} /> Electric-field coupling</label><label><input type="checkbox" checked={activeBatchJob.coupling.magneticField} onChange={event => updateCoupling(activeBatchJob, { magneticField: event.target.checked })} /> Magnetic-field coupling</label><label><input type="checkbox" checked={activeBatchJob.coupling.crossLayer} onChange={event => updateCoupling(activeBatchJob, { crossLayer: event.target.checked })} /> Include other layers</label><label>Neighbour scope<select value={activeBatchJob.coupling.scope} onChange={event => updateCoupling(activeBatchJob, { scope: event.target.value as CouplingScope })}><option value="adjacent">Geometrically adjacent</option><option value="radius">Search radius</option><option value="all_board">Entire board</option></select></label>{activeBatchJob.coupling.scope === "radius" && <label>Radius (mm)<input value={activeBatchJob.coupling.radiusMm} onChange={event => updateCoupling(activeBatchJob, { radiusMm: event.target.value })} /></label>}<label><input type="checkbox" checked={activeBatchJob.coupling.includeTraces} onChange={event => updateCoupling(activeBatchJob, { includeTraces: event.target.checked })} /> Traces</label><label><input type="checkbox" checked={activeBatchJob.coupling.includePlanes} onChange={event => updateCoupling(activeBatchJob, { includePlanes: event.target.checked })} /> Planes</label><label><input type="checkbox" checked={activeBatchJob.coupling.includeZones} onChange={event => updateCoupling(activeBatchJob, { includeZones: event.target.checked })} /> Zones</label></div>}</div>
          </>}
        </div>}
        {batchResults.length > 0 && <div className="wizard-section"><label>BATCH RESULTS</label><div className="batch-results">{batchResults.map(result => <button type="button" key={`${result.net}-${result.mode}`} className={result.status} disabled={!result.bundle} onClick={() => inspectBatchResult(result)} title={result.bundle ? `Load ${result.net} result into the board overlay` : result.detail}><b>{result.net}</b><span>{result.mode.toUpperCase()}</span><strong>{result.status}</strong><small>{result.detail}</small></button>)}</div></div>}
        <div className="stack-warning"><AlertTriangle size={15} /> Each active net selects its own DC, AC, or transient engine and is preflighted before solve. Automatic selection is evaluated per job. AC coupling jobs remain blocked unless the selected plugin declares the required electric or magnetic field capability.</div>
      </>}
      {preflight && <div className={`preflight-summary mesh-only ${preflight.can_solve ? "ready" : "blocked"}`}>
        <div><b>{preflight.can_solve ? "READY TO SOLVE" : "SOLVE BLOCKED"}</b><span>{preflight.summary.mesh_cell_count ?? 0} mesh cells · {preflight.summary.errors ?? 0} errors · {preflight.summary.warnings ?? 0} warnings</span></div>
        <div className="diagnostic-list">{preflight.issues.slice(0, 8).map((issue, index) => <DiagnosticItem key={`${issue.code ?? issue.message}-${index}`} issue={issue} onHelp={onDiagnosticHelp} />)}</div>
      </div>}
      {convergence && <div className={`preflight-summary mesh-only ${convergence.can_sign_off ? "ready" : "blocked"}`}>
        <div><b>{convergence.can_sign_off ? "MESH CONVERGED" : "FAILED TO CONVERGE"}</b><span>{convergence.levels.length} levels · {convergence.comparisons.filter(item => item.required !== false && item.status === "passed").length}/{convergence.comparisons.filter(item => item.required !== false).length} required metrics passed</span></div>
        {convergence.comparisons.map(item => <small key={item.metric} title={item.meaning} className={item.required === false ? "advisory" : item.status === "passed" ? "" : "error"}>{item.required === false ? "Advisory " : ""}{item.metric}: {item.pass_basis === "absolute" && item.absolute_delta !== null && item.absolute_delta !== undefined ? `${(item.absolute_delta * 1e6).toFixed(2)} µV absolute` : item.relative_delta === null ? "unavailable" : `${(item.relative_delta * 100).toFixed(3)}%`} / {item.pass_basis === "absolute" && item.absolute_tolerance ? `${(item.absolute_tolerance * 1e6).toFixed(2)} µV limit` : `${(item.tolerance * 100).toFixed(1)}%`}</small>)}
      </div>}
    </div>
    <div className={`operation-timing ${operation ? "running" : "estimate"}`} role="status" aria-live="polite"><Activity size={15} /><span><b>{operation?.label ?? "Estimated solve time"}</b><small>{operation ? `${operation.meshCells.toLocaleString()} mesh-cell basis${operation.jobs > 1 ? ` · ${operation.jobs} jobs` : ""}` : `${configuredMeshCells.toLocaleString()} configured preview cells${lastOperation ? ` · last ${lastOperation.kind} ${lastOperation.succeeded ? "completed" : "stopped"} in ${formatRunDuration(lastOperation.seconds)}` : ""}`}</small></span><strong>{formatRunDuration(operation ? operationElapsed : plannedEstimate)}</strong><em>{operation ? `estimate ~${formatRunDuration(operation.estimateSeconds)}` : "adaptive estimate"}</em></div>
    <div className={`wizard-actions pi-dialog-actions ${workflow}-actions`}><button className="secondary-btn" disabled={busy} onClick={exportRequest} title={`Export ${workflow === "batch" ? "batch" : "solver"} request`}><FileOutput size={14} /><span>Export {workflow === "batch" ? "batch" : "request"}</span></button>{workflow !== "batch" && <><button className="secondary-btn" disabled={busy || (workflow === "path" && !activePiPath)} onClick={() => void validateAndPreview()} title="Validate setup and preview the solver mesh"><Layers3 size={14} /><span>Preview mesh</span></button><button className="secondary-btn" disabled={busy || (workflow === "path" && !activePiPath)} onClick={() => void runConvergence()} title="Run the configured mesh convergence study"><Gauge size={14} /><span>Convergence</span></button></>}<button className={`run-btn ${busy ? "stop" : ""}`} disabled={!busy && workflow === "path" && !activePiPath} onClick={() => void (busy ? cancelLocalWorker() : workflow === "batch" ? runBatch() : run())}>{busy ? <X size={15} /> : <Play size={15} fill="currentColor" />}<span>{busy ? `Stop · ${formatRunDuration(operationElapsed)}` : workflow === "batch" ? "Run batch" : workflow === "path" ? "Run series path" : mode === "ac" ? "Run PEEC RL" : mode === "transient" ? "Run transient" : "Run DC"}</span></button></div>
    <div className={`pi-panel-resizer ${resizeEdge}`} role="separator" aria-label={`Resize ${panelDock} setup panel`} onPointerDown={event => beginPanelResize(event, resizeEdge)} />
  </div></div>;
}

type ExtensionPackagePreview = {
  contract: string;
  manifest: ExtensionCatalogEntry;
  package_sha256: string;
  file_count: number;
  installed: boolean;
  managed: boolean;
  can_install: boolean;
};

function ExtensionManager({ extensions, board, gerberSource, onOpenGerber, preferredId, preferredContributionId, defaultNet, uiVisible, onToggleUi, result, emergePreview, optycalSource, optycalPreview, onInvalidateOptycalPreview, onInvalidatePreview, harness, trustBusy, trustError, onTrust, onHarnessChange, onClose, onRefresh, onRun }: {
  extensions: ExtensionCatalogEntry[];
  board: ParsedBoard | null;
  gerberSource: EMergeGerberSource | null;
  onOpenGerber: (pythonExecutable: string) => void;
  preferredId: string;
  preferredContributionId: string;
  defaultNet: string;
  uiVisible: (extension: ExtensionCatalogEntry, part: "menuBar" | "titleBar") => boolean;
  onToggleUi: (extensionId: string, part: "menuBar" | "titleBar") => void;
  result: Record<string, unknown> | null;
  emergePreview: Record<string, unknown> | null;
  optycalSource: Record<string, unknown> | null;
  optycalPreview: Record<string, unknown> | null;
  onInvalidateOptycalPreview: () => void;
  onInvalidatePreview: () => void;
  harness: Record<string, any> | null;
  trustBusy: string | null;
  trustError: string;
  onTrust: (extensionId: string) => void;
  onHarnessChange: (value: Record<string, any>) => void;
  onClose: () => void;
  onRefresh: () => void;
  onRun: (extensionId: string, contributionId: string, parameters: Record<string, any>) => void | Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [managerPage, setManagerPage] = useState<"browse" | "manage">(preferredId ? "manage" : "browse");
  const [packagePath, setPackagePath] = useState("");
  const [packagePreview, setPackagePreview] = useState<ExtensionPackagePreview | null>(null);
  const [packageBusy, setPackageBusy] = useState(false);
  const [packageError, setPackageError] = useState("");
  const [packageNotice, setPackageNotice] = useState("");
  const [parameterText, setParameterText] = useState("{}");
  const [parameterError, setParameterError] = useState("");
  const [meshMode, setMeshMode] = useState("dc");
  const [meshNets, setMeshNets] = useState(defaultNet);
  const [meshTargetMm, setMeshTargetMm] = useState("1");
  const [meshDimension, setMeshDimension] = useState("surface_2_5d");
  const [emergeSetup, setEmergeSetup] = useState<EMergeSetup>(() => defaultEMergeSetup(defaultNet));
  const [openEMSSetup, setOpenEMSSetup] = useState(defaultOpenEMSSetup);
  const [emergePreviewStudy, setEmergePreviewStudy] = useState<"radiation" | "si">("radiation");
  const [optycalSetup, setOptycalSetup] = useState<OptycalSetup>(defaultOptycalSetup);
  const [savedOptycalSource, setSavedOptycalSource] = useState<Record<string, unknown> | null>(null);
  const [optycalBusy, setOptycalBusy] = useState(false);
  const activeOptycalSource = savedOptycalSource ?? optycalSource;
  const chooseOptycalStep = async () => {
    try { const file = await selectNativeImportFile("structure"); if (file) { setOptycalSetup(value => ({ ...value, step_path: file.path })); onInvalidateOptycalPreview(); } }
    catch (error) { setParameterError(String(error)); }
  };
  const chooseOptycalSource = async () => {
    try {
      const file = await openNativeTextFile("result"); if (!file) return;
      const parsed = JSON.parse(file.contents);
      if (!admitOptycalSource(parsed)) throw new Error("Select a completed EMerge result with complex radiation samples and excitation metadata.");
      setSavedOptycalSource(parsed); setOptycalSetup(value => ({ ...value, frequency_hz: "" })); onInvalidateOptycalPreview();
    } catch (error) { setParameterError(String(error)); }
  };
  const [selectedId, setSelectedId] = useState(preferredId || extensions[0]?.id || "");
  const [selectedContributionId, setSelectedContributionId] = useState(preferredContributionId);
  useEffect(() => { if (preferredId) { setSelectedId(preferredId); setManagerPage("manage"); } }, [preferredId]);
  useEffect(() => { if (preferredContributionId) setSelectedContributionId(preferredContributionId); }, [preferredContributionId]);
  useEffect(() => { setParameterText("{}"); setParameterError(""); onInvalidatePreview(); }, [selectedId]);
  const filtered = extensions.filter(extension => `${extension.name} ${extension.provider} ${extension.description}`.toLowerCase().includes(query.toLowerCase()));
  const selectedExtension = extensions.find(extension => extension.id === selectedId) ?? filtered[0];
  const contributions = selectedExtension
    ? Object.entries(selectedExtension.contributes).flatMap(([point, entries]) => entries.map(entry => ({ ...entry, point })))
    : [];
  const emergeNetOptions = [...new Set(Object.values(board?.nets ?? {}))].sort();
  const emergePadOptions = (board?.pads ?? []).map(pad => pad.id).filter(Boolean).sort();
  const resultView = result?.view as { type?: string; columns?: unknown[]; rows?: unknown[][] } | undefined;
  const inspectPackage = async (path: string) => {
    setPackagePath(path); setPackagePreview(null); setPackageError(""); setPackageNotice(""); setPackageBusy(true);
    try {
      const response = await runLocalWorker({ method: "inspect_extension_package", params: { path } });
      if (!response.ok || !response.result) throw new Error(response.error ?? "Could not inspect the extension package.");
      setPackagePreview(response.result as ExtensionPackagePreview);
    } catch (error) { setPackageError(error instanceof Error ? error.message : String(error)); }
    finally { setPackageBusy(false); }
  };
  const choosePackage = async () => {
    try {
      const file = await selectNativeImportFile("extension");
      if (file) await inspectPackage(file.path);
    } catch (error) { setPackageError(error instanceof Error ? error.message : String(error)); }
  };
  const installPackage = async () => {
    if (!packagePreview || !packagePath) return;
    setPackageBusy(true); setPackageError(""); setPackageNotice("");
    try {
      const response = await runLocalWorker({ method: "install_extension", params: { path: packagePath, replace: packagePreview.installed && packagePreview.managed } });
      if (!response.ok || !response.result) throw new Error(response.error ?? "Extension installation failed.");
      const id = String(response.result.extension_id ?? packagePreview.manifest.id);
      setPackageNotice(`${packagePreview.manifest.name} ${response.result.action === "updated" ? "updated" : "installed"}. Review its permissions, then trust it to run.`);
      setSelectedId(id); setManagerPage("manage"); setPackagePreview(null); onRefresh();
    } catch (error) { setPackageError(error instanceof Error ? error.message : String(error)); }
    finally { setPackageBusy(false); }
  };
  const removePackage = async (extension: ExtensionCatalogEntry) => {
    if (!extension.can_remove) return;
    setPackageBusy(true); setPackageError(""); setPackageNotice("");
    try {
      const response = await runLocalWorker({ method: "remove_extension", params: { extension_id: extension.id } });
      if (!response.ok) throw new Error(response.error ?? "Extension removal failed.");
      setSelectedId(""); setPackageNotice(`${extension.name} removed.`); onRefresh();
    } catch (error) { setPackageError(error instanceof Error ? error.message : String(error)); }
    finally { setPackageBusy(false); }
  };
  const run = async (id: string) => {
    if (!selectedExtension || optycalBusy) return;
    if (selectedExtension.id === "spike.emerge-suite" && id === "emerge-gerber-import" && onOpenGerber) { onOpenGerber(emergeSetup.python_executable); return; }
    setOptycalBusy(true);
    try {
      const parameters = JSON.parse(parameterText);
      if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) throw new Error("Options must be an object.");
      const contribution = contributions.find(item => item.id === id);
      if (selectedExtension.id === "spike.openems-suite" && id !== "openems-probe") {
        const domain = id.includes("pi") ? "pi" : id.includes("si") ? "si" : "em";
        Object.assign(parameters, openEMSParameters(openEMSSetup, domain, id === "openems-preview" ? "preflight" : id === "openems-mesh" ? "prepare" : "run"));
      }
      if (selectedExtension.id === "spike.emerge-suite" && ["emerge-radiation", "emerge-si", "emerge-preview", "emerge-mesh", "emerge-mesh-preview"].includes(id)) Object.assign(parameters, emergeParameters(emergeSetup, gerberSource ? "gerber" : "board"));
      if (selectedExtension.id === "spike.emerge-suite" && id === "emerge-preview") parameters.preview_radiation = emergePreviewStudy === "radiation";
      if (selectedExtension.id === "spike.emerge-suite" && id === "emerge-probe" && emergeSetup.python_executable.trim()) parameters.python_executable = emergeSetup.python_executable.trim();
      if (selectedExtension.id === "spike.optycal-suite" && ["optycal-preview", "optycal-radiation"].includes(id)) Object.assign(parameters, optycalParameters(optycalSetup, activeOptycalSource));
      if (selectedExtension.id === "spike.optycal-suite" && id === "optycal-probe" && optycalSetup.python_executable.trim()) parameters.python_executable = optycalSetup.python_executable.trim();
      if (contribution?.point === "analyses" && selectedExtension.permissions.includes("mesh.read") && parameters.mesh_spec === undefined) {
        const target = Number(meshTargetMm);
        if (!Number.isFinite(target) || target < 0.05) throw new Error("Mesh target size must be at least 0.05 mm.");
        parameters.mesh_spec = { mode: meshMode,
          net_names: meshNets.split(",").map(value => value.trim()).filter(Boolean),
          mesh: { target_size_mm: target, dimension: meshDimension } };
      }
      setParameterError(""); await onRun(selectedExtension.id, id, parameters);
    } catch (e) { setParameterError(String(e)); }
    finally { setOptycalBusy(false); }
  };
  return <div className="modal-shade"><div className="floating-panel extension-manager">
    <div className="floating-heading"><div><b>EXTENSION MANAGER</b><small>Applications, solvers, tools, importers, reports, and validators</small></div><button onClick={onClose}><X size={15} /></button></div>
    <div className="extension-toolbar"><button className={managerPage === "browse" ? "selected" : ""} onClick={() => setManagerPage("browse")}><PackageSearch size={13} /> Browse</button><button className={managerPage === "manage" ? "selected" : ""} onClick={() => setManagerPage("manage")}><Settings2 size={13} /> Manage</button><label><Search size={13} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search extensions" /></label><button onClick={onRefresh}><Activity size={13} /> Refresh</button></div>
    {managerPage === "browse" ? <div className="extension-browser">
      <section className="extension-browser-install"><h3>Install a local extension</h3><p>Choose a ZIP package or enter the path to an unpacked extension directory. SPIKE will inspect its manifest before installation.</p><div className="extension-browser-path"><input aria-label="Extension package path" value={packagePath} onChange={event => { setPackagePath(event.target.value); setPackagePreview(null); }} placeholder="Path to .zip, .spike-extension, or directory" /><button className="secondary-btn" onClick={() => void choosePackage()} disabled={packageBusy}><FolderOpen size={14} /> Choose package</button><button className="secondary-btn" onClick={() => void inspectPackage(packagePath)} disabled={packageBusy || !packagePath.trim()}><Search size={14} /> Inspect</button></div>
        {packagePreview && <div className="extension-package-preview"><div><PackageOpen size={20} /><span><b>{packagePreview.manifest.name}</b><small>{packagePreview.manifest.provider} · version {packagePreview.manifest.version} · {packagePreview.manifest.license}</small></span></div><p>{packagePreview.manifest.description}</p><small>{packagePreview.file_count} files · SHA-256 {packagePreview.package_sha256}</small><div className="extension-permissions"><label>REQUESTED PERMISSIONS</label><div>{packagePreview.manifest.permissions.length ? packagePreview.manifest.permissions.map(permission => <span key={permission}>{permission}</span>) : <span>None</span>}</div></div><button className="run-btn" disabled={packageBusy || !packagePreview.can_install} onClick={() => void installPackage()}><Plus size={14} /> {packagePreview.installed ? "Update extension" : "Install extension"}</button>{!packagePreview.can_install && <small>This extension ID is already in use by another installation and cannot be replaced here.</small>}</div>}
      </section><section className="extension-browser-discovered"><h3>Available in SPIKE</h3><p>Built-in and installed extensions are listed here. Select one to view its tools and permissions.</p>{filtered.map(extension => <button key={extension.id} onClick={() => { setSelectedId(extension.id); setManagerPage("manage"); }}><Puzzle size={15} /><span><b>{extension.name}</b><small>{extension.provider} · {extension.version} · {extension.install_state ?? (extension.bundled ? "bundled" : "installed")}</small></span><ArrowRight size={13} /></button>)}{!filtered.length && <div className="extension-empty">No extensions match this search.</div>}</section>
    </div> : <div className="extension-layout">
      <div className="extension-list">{filtered.map(extension => <button key={extension.id} data-guide={extension.id === "spike.emerge-suite" ? "emerge-extension" : undefined} className={selectedExtension?.id === extension.id ? "selected" : ""} onClick={() => setSelectedId(extension.id)}><Network size={16} /><span><b>{extension.name}</b><small>{extension.provider} · {extension.version}</small></span><i className={extension.trusted ? "trusted" : "untrusted"}>{extension.trusted ? "TRUSTED" : "BLOCKED"}</i></button>)}{!filtered.length && <div className="extension-empty">No installed extensions match this filter.</div>}</div>
      <div className="extension-detail">{selectedExtension ? <>
        <div className="extension-title"><div><b>{selectedExtension.name}</b><span>{selectedExtension.id}</span></div><span className={`extension-state ${selectedExtension.state}`}>{selectedExtension.state}</span></div>
        <div className="extension-ui-controls"><label><input type="checkbox" checked={uiVisible(selectedExtension, "menuBar")} onChange={() => onToggleUi(selectedExtension.id, "menuBar")} /> Extensions menu</label><label><input type="checkbox" checked={uiVisible(selectedExtension, "titleBar")} onChange={() => onToggleUi(selectedExtension.id, "titleBar")} /> Extensions toolbar</label></div>
        <div className="extension-manage-actions"><span>{selectedExtension.bundled ? "Built into SPIKE" : selectedExtension.managed ? "Installed by SPIKE" : "External extension path"}</span>{selectedExtension.can_remove && <button type="button" className="secondary-btn" disabled={packageBusy} onClick={() => void removePackage(selectedExtension)}><Trash2 size={13} /> Remove</button>}</div>
        <p>{selectedExtension.description}</p>
        <dl><dt>Provider</dt><dd>{selectedExtension.provider}</dd><dt>License</dt><dd>{selectedExtension.license}</dd><dt>Network</dt><dd>{selectedExtension.permissions.includes("network") ? "Requested" : "Not requested"}</dd><dt>Execution</dt><dd>Isolated local process</dd></dl>
        <div className="extension-permissions"><label>PERMISSIONS</label><div>{selectedExtension.permissions.length ? selectedExtension.permissions.map(permission => <span key={permission}>{permission}</span>) : <span>None</span>}</div></div>
        {selectedExtension.permissions.includes("mesh.read") && contributions.some(item => item.point === "analyses") && <div className="wizard-section"><label>BOARD MESH HANDOFF</label><small>SPIKE sends complete bounded topology plus materials, excitations and a separate display preview. A blank net list includes all nets.</small><div className="sweep-grid"><label>Analysis mode<select value={meshMode} onChange={event => setMeshMode(event.target.value)}><option value="dc">DC / PI</option><option value="ac">AC / RLCG</option><option value="si">SI</option><option value="thermal">Thermal</option></select></label><label>Nets (comma separated)<input value={meshNets} onChange={event => setMeshNets(event.target.value)} placeholder="All nets" /></label><label>Target size (mm)<input type="number" min="0.05" step="0.05" value={meshTargetMm} onChange={event => setMeshTargetMm(event.target.value)} /></label><label>Representation<select value={meshDimension} onChange={event => setMeshDimension(event.target.value)}><option value="surface_2_5d">2.5D surface</option><option value="volume_3d">3D conductor volume</option></select></label></div></div>}
        {selectedExtension.permissions.includes("harness.read") && <HarnessDocumentEditor value={harness} onChange={onHarnessChange} />}
        {selectedExtension.id === "spike.mcad" && <McadOptions text={parameterText} onChange={setParameterText} onError={setParameterError} />}
        {selectedExtension.id === "spike.emerge-suite" && <div data-guide="emerge-setup"><EMergeSetupForm gerberSource={gerberSource} onOpenGerber={onOpenGerber} value={emergeSetup} onChange={value => { setEmergeSetup(value); onInvalidatePreview(); }} netOptions={emergeNetOptions} padOptions={emergePadOptions} boardPads={board?.pads} copperLayerOrder={board?.stackup.filter(layer => layer.name.endsWith(".Cu")).map(layer => layer.name)} boardBounds={board?.bounds} /></div>}
        {selectedExtension.id === "spike.openems-suite" && <OpenEMSSetupForm value={openEMSSetup} onChange={setOpenEMSSetup} netOptions={emergeNetOptions} disabled={optycalBusy} />}
        {selectedExtension.id === "spike.optycal-suite" && <OptycalSetupForm value={optycalSetup} onChange={value => { setOptycalSetup(value); onInvalidateOptycalPreview(); }} sourceResult={activeOptycalSource} onSelectStep={chooseOptycalStep} onSelectSource={chooseOptycalSource} busy={optycalBusy} />}
        {(contributions.some(c => c.input_schema) || contributions.some(c => c.point === "analyses")) && <details><summary>Extension options</summary><p>JSON options sent to the selected extension. Leave as an empty object when no options are needed.</p><textarea aria-label="Extension options JSON" rows={4} value={parameterText} onChange={e => setParameterText(e.target.value)} /></details>}
        {parameterError && <p role="alert">{parameterError}</p>}
        <div className="extension-contributions"><label>CONTRIBUTIONS</label>{contributions.map(contribution => <div key={`${contribution.point}-${contribution.id}`} className={selectedContributionId === contribution.id ? "selected" : ""}><span><b>{contribution.name}</b><small>{contribution.point.replace("_", " ")} · {contribution.description ?? contribution.id}</small></span><button data-guide={contribution.id === "emerge-si" ? "emerge-run-si" : contribution.id === "emerge-radiation" ? "emerge-run-radiation" : undefined} disabled={optycalBusy || !selectedExtension.trusted || selectedExtension.state === "disabled" || !["applications", "commands", "reports", "validators", "importers", "exporters", "harness_engines", "schemas", "analyses", "panels"].includes(contribution.point)} onClick={() => { setSelectedContributionId(contribution.id); run(contribution.id); }}><Play size={12} /> Run</button></div>)}</div>
        {selectedExtension.id === "spike.emerge-suite" && <><label>Python preview study<select aria-label="EMerge Python preview study" value={emergePreviewStudy} onChange={event => { setEmergePreviewStudy(event.target.value as "radiation" | "si"); onInvalidatePreview(); }}><option value="radiation">Radiation</option><option value="si">SI / S-parameters</option></select></label><EMergeScriptPreview data={emergePreview} /><EMergeCapabilityInventory rows={emergePreview?.capabilities ?? (result?.data as Record<string, unknown> | undefined)?.feature_inventory} /></>}
        {selectedExtension.id === "spike.optycal-suite" && <OptycalScriptPreview data={optycalPreview} />}
        {result && <div className="extension-output" data-guide={selectedExtension.id === "spike.emerge-suite" ? "emerge-result" : undefined}><label>EXTENSION OUTPUT</label><div className="extension-output-title">{result.status !== "completed" ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}<b>{String(result.title ?? "Extension completed")}</b></div><EMergeResultPlot result={selectedExtension.id === "spike.emerge-suite" ? result : null} /><OptycalResultPlot result={selectedExtension.id === "spike.optycal-suite" ? result : null} />{resultView?.type === "property_table" && Array.isArray(resultView.rows) ? <DataTable label="Extension output"><thead><tr>{(resultView.columns ?? []).map((column, index) => <th key={index}>{String(column)}</th>)}</tr></thead><tbody>{resultView.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{String(cell)}</td>)}</tr>)}</tbody></DataTable> : ["spike/mcad-export/v1", "spike/artifact-export/v1"].includes((result.data as any)?.contract) ? <ExtensionArtifacts data={result.data as Record<string, any>} /> : ["spike.emerge-suite", "spike.optycal-suite"].includes(selectedExtension.id) && (result.data as any)?.analysis_result ? null : <pre>{JSON.stringify(result.data ?? result, null, 2)}</pre>}</div>}
        {!selectedExtension.trusted && <div className="stack-warning"><ShieldAlert size={15} /><span>Trusting this extension allows its local code to execute with the listed permissions for this session. Process separation is not a complete operating-system sandbox.</span><button type="button" disabled={trustBusy !== null || selectedExtension.state === "disabled"} onClick={() => onTrust(selectedExtension.id)}>{trustBusy === selectedExtension.id ? "Trusting…" : "Trust for session"}</button></div>}
        {trustError && <p role="alert">{trustError}</p>}
      </> : <div className="extension-empty">No extension selected. Use Browse to install a local package.</div>}</div>
    </div>}
    <div className="extension-footer"><span role={packageError ? "alert" : "status"}>{packageError || packageNotice || "Third-party code runs in a local process after you trust its permissions."}</span><button className="secondary-btn" onClick={onClose}>Close</button></div>
  </div></div>;
}

function ShortcutWindow({ shortcuts, onAssign, onReset, onClose }: { shortcuts: Record<ShortcutAction, string>; onAssign: (action: ShortcutAction, key: string) => void; onReset: () => void; onClose: () => void }) {
  const [capturing, setCapturing] = useState<ShortcutAction | null>(null);
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!capturing) {
      if (event.key === "Escape") onClose();
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (event.key === "Escape") {
      setCapturing(null);
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    onAssign(capturing, normalizedShortcutKey(event.key));
    setCapturing(null);
  };
  return <div className="modal-shade" onKeyDown={onKeyDown}><div className="floating-panel shortcut-modal">
    <div className="floating-heading"><b>KEYBOARD SHORTCUTS</b><button onClick={onClose}><X size={15} /></button></div>
    <div className="shortcut-list">
      {shortcutGroups.map(group => <section className="shortcut-group" key={group.label}><h3>{group.label}</h3>{group.actions.map(action => <div className="shortcut-row" key={action}><span>{shortcutLabels[action]}</span><button className={capturing === action ? "capturing" : ""} onClick={() => setCapturing(action)} autoFocus={capturing === action}>{capturing === action ? "Press key" : <kbd>{shortcuts[action]}</kbd>}</button></div>)}</section>)}
      <section className="shortcut-group shortcut-fixed"><h3>Editing and files</h3>{fixedShortcuts.map(item => <div className="shortcut-row" key={item.key}><span>{item.label}</span><kbd>{item.key}</kbd></div>)}</section>
    </div>
    <div className="shortcut-footer"><span>Assigning a used key swaps the conflicting binding.</span><button className="secondary-btn" onClick={onReset}>Reset defaults</button></div>
  </div></div>;
}

function SearchPanel({ query, board, onClose, onSelect }: { query: string; board: ParsedBoard | null; onClose: () => void; onSelect: (object: BoardObject) => void }) {
  useEffect(() => () => previewViewportTarget(null), []);
  const term = query.toLowerCase(); const results: BoardObject[] = [];
  board?.components.filter(item => item.ref.toLowerCase().includes(term)).slice(0, 12).forEach(item => results.push({ id: item.id, type: "component", name: item.ref, ref: item.ref, layer: item.layer, model: item.model }));
  board?.pads.filter(item => `${item.ref ?? ""}.${item.name} ${item.net ?? ""}`.toLowerCase().includes(term)).slice(0, 12).forEach(item => results.push({ id: item.id, type: "pad", name: `${item.ref ?? "?"}.${item.name}`, ref: item.ref, net: item.net, layer: item.layer, position: item.at }));
  board?.tracks.filter(item => item.id.toLowerCase().includes(term) || item.net?.toLowerCase().includes(term)).slice(0, 12).forEach(item => results.push({ id: item.id, type: "trace", name: item.id, net: item.net, layer: item.layer }));
  board?.vias.filter(item => item.id.toLowerCase().includes(term) || item.net?.toLowerCase().includes(term)).slice(0, 8).forEach(item => results.push({ id: item.id, type: "via", name: item.id, net: item.net, layer: "through" }));
  useEffect(() => {
    const rows = [...document.querySelectorAll<HTMLButtonElement>(".search-results .search-result")];
    const cleanups = rows.map((row, index) => {
      const item = results[index];
      if (!item) return () => undefined;
      const enter = () => previewViewportTarget({ kind: "object", id: item.id, type: item.type, net: item.net, ref: item.ref, layer: item.layer, position: item.position, label: item.name });
      const leave = () => previewViewportTarget(null);
      row.addEventListener("pointerenter", enter);
      row.addEventListener("pointerleave", leave);
      return () => { row.removeEventListener("pointerenter", enter); row.removeEventListener("pointerleave", leave); };
    });
    return () => { cleanups.forEach(cleanup => cleanup()); previewViewportTarget(null); };
  }, [board, query]);
  return <div className="floating-panel search-results"><div className="floating-heading"><b>SEARCH RESULTS</b><button onClick={onClose}><X size={15} /></button></div><p className="modal-note">{results.length} matching board objects for <b>{query}</b></p>{results.length ? results.slice(0, 18).map(item => <button className="search-result" key={item.id} onClick={() => { onSelect(item); onClose(); }}><Search size={13} /><span>{item.name}</span><small>{item.type}{item.net ? ` · ${item.net}` : ""}</small></button>) : <div className="empty-dock">No imported board objects match this search.</div>}</div>;
}
