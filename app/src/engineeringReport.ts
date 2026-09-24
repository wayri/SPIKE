import type { ParsedBoard } from "./boardParser";
import { APP_VERSION } from "./appVersion";
import { viaStressMapSvg } from "./viaStressMap";
import type { PdnReview, ScalarSample, SolverResultBundle } from "./analysisResults";
import { buildResultEngineeringAnalytics } from "./resultAnalytics";
import type { CopperFusingSettings, ResultEngineeringAnalytics } from "./resultAnalytics";
import { numericExtent, numericMaximum, numericMinimum } from "./numericRange";
import { reportFieldSamples, reportSparklineSvg } from "./engineeringReportPreviewData";
import { domainLabels, reportDomain, type ReportDomain } from "./engineeringReportDomain";
import { resultSolvedForPresentation } from "./resultAdmission";
import { sourceLoadReview } from "./sourceLoadReview";
import { sourceLoadReportHtml } from "./sourceLoadReport";
import { buildThermalReportSection } from "./thermalEngineeringReport";
import type { EmiFieldResult, EmiPreflight, EmiScreening, EmiSetup } from "./EmiWorkbench";

type ReportTerminal = {
  name: string;
  net: string;
  anchorType: string;
  anchorId: string;
  x: string;
  y: string;
  layer: string;
  layers: string[];
  value: string;
  profile?: string;
  profileData?: string;
  profileInitial?: string;
  profileDelayS?: string;
  profileRiseS?: string;
  profileWidthS?: string;
  profileFallS?: string;
  profilePeriodS?: string;
};

type ReportProbe = {
  id: string;
  name: string;
  type?: string;
  net?: string;
  layer?: string;
  position?: [number, number];
};

type ReportResultRecord = {
  id?: string;
  label: string;
  bundle: SolverResultBundle;
};

export type ReportInput = {
  projectName: string;
  boardFile: string;
  analysisMode: string;
  domain?: ReportDomain;
  board: ParsedBoard | null;
  result: SolverResultBundle | null;
  results?: ReportResultRecord[];
  setup: {
    net: string;
    sources: ReportTerminal[];
    loads: ReportTerminal[];
    returnPath: { mode: string; net: string };
    meshDimension: string;
    meshTargetMm: string;
    zoneCellMm: string;
    viaModel: string;
    viaPlatingMm: string;
    frequencyStart: string;
    frequencyStop: string;
    frequencyPoints: string;
    transientStopS?: string;
    transientTimeStepS?: string;
    transientOutputDecimation?: string;
    transientPlaybackFps?: string;
    transientInitialCondition?: string;
  };
  limits: { drop: string; density: string };
  probes: ReportProbe[];
  fusingSettings: CopperFusingSettings;
  modelAssignmentCount: number;
  pdnReview?: PdnReview | null;
  emi?: {
    setup: EmiSetup;
    preflight: EmiPreflight | null;
    screening: EmiScreening | null;
    fieldResult: EmiFieldResult | null;
  };
  si?: { channelResult: unknown; suite: unknown };
  thermal?: { scenario: unknown };
  projectPayload: unknown;
};

type FieldStat = {
  key: string;
  label: string;
  unit: string;
  count: number;
  minimum: number;
  mean: number;
  percentile95: number;
  maximum: number;
};

export type ReportAnalyticsRow = {
  scope: string;
  mode: string;
  status: string;
  modelStatus: string;
  sourceVoltageV: number | null;
  loadCurrentA: number | null;
  maxDropV: number | null;
  dropPercent: number | null;
  conductorLossW: number | null;
  sourcePowerW: number | null;
  deliveredPowerW: number | null;
  conductionEfficiencyPercent: number | null;
  effectiveResistanceOhm: number | null;
  peakCurrentDensityAMm2: number | null;
  solverTimeS: number | null;
  nodeCount: number | null;
};

export type ReportAnalytics = {
  rows: ReportAnalyticsRow[];
  totalConductorLossW: number | null;
  totalSourcePowerW: number | null;
  totalDeliveredPowerW: number | null;
  conductionEfficiencyPercent: number | null;
  totalLoadCurrentA: number | null;
  worstDropV: number | null;
  peakCurrentDensityAMm2: number | null;
  totalSolverTimeS: number | null;
  byNetW: Record<string, number>;
  byLayerW: Record<string, number>;
  byGeometryW: Record<string, number>;
};

const html = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]!);

const jsonForScript = (value: unknown) => JSON.stringify(value).replace(/</g, "\\u003c").replace(/-->/g, "--\\u003e");
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const finite = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};
const fmt = (value: unknown, digits = 5) => {
  const number = finite(value);
  if (number === null) return "-";
  if (number === 0) return "0";
  const magnitude = Math.abs(number);
  if (magnitude >= 10000 || magnitude < 0.001) return number.toExponential(Math.max(2, digits - 2));
  return number.toLocaleString("en-US", { maximumFractionDigits: digits });
};
const row = (...cells: unknown[]) => `<tr>${cells.map(cell => `<td>${html(cell)}</td>`).join("")}</tr>`;
const fnv1a = (value: unknown) => {
  const source = JSON.stringify(value ?? null);
  let hash = 0x811c9dc5;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `fnv1a32:${(hash >>> 0).toString(16).padStart(8, "0")}`;
};

const projectFingerprintInput = (value: unknown) => {
  const project = record(value);
  const design = record(project.design);
  return {
    contract: project.contract,
    format_version: project.format_version,
    project_id: project.project_id,
    design_id: design.design_id,
    board_file: design.board_file,
    manifest_digest: project.manifest_payload_sha256,
  };
};

const geometryFingerprintInput = (board: ParsedBoard | null) => board ? {
  bounds: board.bounds,
  layers: board.layers,
  stackup: board.stackup,
  counts: [board.tracks.length, board.vias.length, board.pads.length, board.zones.length, board.components.length],
  outlines: board.outlineLoops.map(loop => loop.length),
} : null;

const resultFingerprintInput = (result: SolverResultBundle | null) => result ? {
  contract: result.contract,
  analysis_id: result.analysis_id,
  mode: result.mode,
  model_status: result.model_status,
  summary: result.summary,
  field_counts: Object.fromEntries(Object.entries(result.scalar_fields).map(([key, values]) => [key, values.length])),
  vector_counts: Object.fromEntries(Object.entries(result.vector_fields).map(([key, values]) => [key, values.length])),
  mesh_count: result.mesh.length,
  frame_count: result.time_series.frames.length,
  provenance: result.provenance,
} : null;

const fieldDefinitions: Record<string, { label: string; unit: string }> = {
  voltage_v: { label: "Absolute voltage", unit: "V" },
  voltage_drop_v: { label: "Voltage drop", unit: "V" },
  current_a: { label: "Current", unit: "A" },
  operating_point_impedance_ohm: { label: "Operating-point V/I", unit: "ohm" },
  current_density_a_mm2: { label: "Current density", unit: "A/mm2" },
  power_loss_w: { label: "Copper power loss", unit: "W" },
  via_current_density_a_mm2: { label: "Via current density", unit: "A/mm2" },
};

// A report is an interactive *view* of a potentially very large result.  Keep
// this limit separate from solver data: exported evidence and solver summaries
// remain complete and authoritative.
const REPORT_TABLE_ROW_LIMIT = 500;

function reportNumber(summary: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = finite(summary[key]);
    if (value !== null) return value;
  }
  return null;
}

function boundedRows<T>(items: readonly T[], limit = REPORT_TABLE_ROW_LIMIT) {
  return { items: items.slice(0, limit), omitted: Math.max(0, items.length - limit) };
}

function percentile(sorted: number[], ratio: number) {
  if (!sorted.length) return 0;
  const position = (sorted.length - 1) * ratio;
  const lower = Math.floor(position);
  const fraction = position - lower;
  return sorted[lower + 1] === undefined ? sorted[lower] : sorted[lower] + fraction * (sorted[lower + 1] - sorted[lower]);
}

function fieldStats(result: SolverResultBundle | null): FieldStat[] {
  if (!result || !resultSolvedForPresentation(result)) return [];
  return Object.entries(result.scalar_fields).flatMap(([key, samples]) => {
    const values = samples.map(sample => sample.value).filter(Number.isFinite).sort((a, b) => a - b);
    if (!values.length) return [];
    const definition = fieldDefinitions[key] ?? { label: key.replace(/_/g, " "), unit: "" };
    return [{
      key,
      label: definition.label,
      unit: definition.unit,
      count: values.length,
      minimum: values[0],
      mean: values.reduce((sum, value) => sum + value, 0) / values.length,
      percentile95: percentile(values, 0.95),
      maximum: values[values.length - 1],
    }];
  });
}

function summaryMap(summary: Record<string, unknown>, key: string) {
  const value = record(summary[key]);
  return Object.fromEntries(Object.entries(value).flatMap(([name, raw]) => {
    const number = finite(raw);
    return number === null ? [] : [[name, number]];
  }));
}

function sumNullable(values: Array<number | null>) {
  const present = values.filter((value): value is number => value !== null);
  return present.length ? present.reduce((sum, value) => sum + value, 0) : null;
}

function maxNullable(values: Array<number | null>) {
  const present = values.filter((value): value is number => value !== null);
  return present.length ? numericMaximum(present) : null;
}

function mergeBreakdown(target: Record<string, number>, source: Record<string, number>) {
  Object.entries(source).forEach(([key, value]) => { target[key] = (target[key] ?? 0) + value; });
}

export function buildReportAnalytics(input: ReportInput): ReportAnalytics {
  const supplied = [...(input.results ?? [])];
  if (input.result && !supplied.some(item => item.bundle.analysis_id && item.bundle.analysis_id === input.result?.analysis_id)) {
    supplied.push({ label: input.setup.net || input.result.mode || "Active result", bundle: input.result });
  }
  const latestByScope = new Map<string, ReportResultRecord>();
  supplied.forEach(item => latestByScope.set(`${item.bundle.mode}|${item.label}`, item));
  const rows = [...latestByScope.values()].map(({ label, bundle }): ReportAnalyticsRow => {
    if (!resultSolvedForPresentation(bundle)) return {
      scope: label, mode: bundle.mode, status: bundle.status, modelStatus: bundle.model_status,
      sourceVoltageV: null, loadCurrentA: null, maxDropV: null, dropPercent: null,
      conductorLossW: null, sourcePowerW: null, deliveredPowerW: null,
      conductionEfficiencyPercent: null, effectiveResistanceOhm: null,
      peakCurrentDensityAMm2: null, solverTimeS: null, nodeCount: null,
    };
    const summary = bundle.summary;
    const sourceVoltageV = finite(summary.source_voltage_v);
    const loadCurrentA = finite(summary.total_load_current_a);
    const maxDropV = finite(summary.max_load_voltage_drop_v) ?? finite(summary.max_voltage_drop_v);
    const conductorLossW = bundle.mode === "transient"
      ? finite(summary.peak_copper_loss_w) ?? finite(summary.total_copper_loss_w)
      : finite(summary.total_copper_loss_w);
    const sourcePowerW = sourceVoltageV !== null && loadCurrentA !== null ? sourceVoltageV * loadCurrentA : null;
    const deliveredPowerW = sourcePowerW !== null && conductorLossW !== null ? Math.max(0, sourcePowerW - conductorLossW) : null;
    const conductionEfficiencyPercent = sourcePowerW !== null && sourcePowerW > 0 && deliveredPowerW !== null
      ? deliveredPowerW / sourcePowerW * 100
      : null;
    const effectiveResistanceOhm = finite(summary.effective_path_resistance_ohm)
      ?? (conductorLossW !== null && loadCurrentA !== null && Math.abs(loadCurrentA) > 0
        ? conductorLossW / (loadCurrentA * loadCurrentA)
        : null);
    return {
      scope: label,
      mode: bundle.mode,
      status: bundle.status,
      modelStatus: bundle.model_status,
      sourceVoltageV,
      loadCurrentA,
      maxDropV,
      dropPercent: maxDropV !== null && sourceVoltageV !== null && sourceVoltageV !== 0 ? maxDropV / Math.abs(sourceVoltageV) * 100 : null,
      conductorLossW,
      sourcePowerW,
      deliveredPowerW,
      conductionEfficiencyPercent,
      effectiveResistanceOhm,
      peakCurrentDensityAMm2: finite(summary.max_current_density_a_mm2),
      solverTimeS: finite(summary.total_solver_time_s),
      nodeCount: finite(summary.node_count) ?? (bundle.mesh.length ? bundle.mesh.length : null),
    };
  });
  const totalConductorLossW = sumNullable(rows.map(item => item.conductorLossW));
  const totalSourcePowerW = sumNullable(rows.map(item => item.sourcePowerW));
  const totalDeliveredPowerW = sumNullable(rows.map(item => item.deliveredPowerW));
  const byNetW: Record<string, number> = {};
  const byLayerW: Record<string, number> = {};
  const byGeometryW: Record<string, number> = {};
  [...latestByScope.values()].forEach(({ bundle }) => {
    if (!resultSolvedForPresentation(bundle)) return;
    mergeBreakdown(byNetW, summaryMap(bundle.summary, "net_power_loss_w"));
    mergeBreakdown(byLayerW, summaryMap(bundle.summary, "layer_power_loss_w"));
    mergeBreakdown(byGeometryW, summaryMap(bundle.summary, "geometry_power_loss_w"));
  });
  return {
    rows,
    totalConductorLossW,
    totalSourcePowerW,
    totalDeliveredPowerW,
    conductionEfficiencyPercent: totalSourcePowerW !== null && totalSourcePowerW > 0 && totalDeliveredPowerW !== null
      ? totalDeliveredPowerW / totalSourcePowerW * 100
      : null,
    totalLoadCurrentA: sumNullable(rows.map(item => item.loadCurrentA)),
    worstDropV: maxNullable(rows.map(item => item.maxDropV)),
    peakCurrentDensityAMm2: maxNullable(rows.map(item => item.peakCurrentDensityAMm2)),
    totalSolverTimeS: sumNullable(rows.map(item => item.solverTimeS)),
    byNetW,
    byLayerW,
    byGeometryW,
  };
}

function boundedDisplayRecords<T>(items: T[], limit: number): T[] {
  if (items.length <= limit) return items;
  const output: T[] = [];
  const step = items.length / limit;
  for (let index = 0; index < limit; index += 1) output.push(items[Math.floor(index * step)]);
  return output;
}

function summarizeFrameValues(values: readonly number[]) {
  let count = 0;
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  let sum = 0;
  for (const raw of values) {
    const value = Number(raw);
    if (!Number.isFinite(value)) continue;
    count += 1;
    sum += value;
    minimum = Math.min(minimum, value);
    maximum = Math.max(maximum, value);
  }
  return count ? { minimum, mean: sum / count, maximum } : null;
}

function reportGeometry(board: ParsedBoard | null, result: SolverResultBundle | null, results: ReportResultRecord[]) {
  if (!board) return null;
  const displayResult = resultSolvedForPresentation(result) ? result : null;
  const datasets = results.map((item, index) => ({
    id: `net-${index}`,
    label: item.label,
    fields: resultSolvedForPresentation(item.bundle) ? Object.fromEntries(Object.entries(item.bundle.scalar_fields).map(([key, samples]) => [key, reportFieldSamples(samples)])) : {},
    impedance: resultSolvedForPresentation(item.bundle) ? [
      ...item.bundle.parasitics.flatMap(parasitic => parasitic.impedance?.length ? [{ net: parasitic.net, points: parasitic.impedance }] : []),
      ...item.bundle.loop_parasitics.flatMap(loop => loop.impedance?.length ? [{ net: `Loop | ${loop.name}`, points: loop.impedance }] : []),
    ] : [],
  }));
  return {
    bounds: board.bounds,
    layers: board.layers,
    outlineLoops: board.outlineLoops,
    geometryCounts: {
      tracks: board.tracks.length,
      vias: board.vias.length,
      pads: board.pads.length,
      zones: board.zones.length,
      components: board.components.length,
    },
    tracks: boundedDisplayRecords(board.tracks, 4000).map(item => ({ s: item.start, e: item.end, w: item.width, l: item.layer, n: item.net })),
    vias: boundedDisplayRecords(board.vias, 2500).map(item => ({ p: item.at, d: item.size, drill: item.drill, ls: item.layers, n: item.net })),
    pads: boundedDisplayRecords(board.pads, 3500).map(item => ({ p: item.at, w: item.width, h: item.height, r: item.rotation, l: item.layer, ls: item.layers, n: item.net, ref: item.ref, name: item.name })),
    zones: boundedDisplayRecords(board.zones, 500).map(item => ({ p: item.points, l: item.layer, n: item.net })),
    components: boundedDisplayRecords(board.components, 1500).map(item => ({ p: item.at, w: item.width, h: item.height, r: item.rotation, l: item.layer, ref: item.ref, value: item.value })),
    fields: displayResult ? Object.fromEntries(Object.entries(displayResult.scalar_fields).map(([key, samples]) => [key, reportFieldSamples(samples)])) : {},
    timeSeries: displayResult?.time_series.frames.map(frame => {
      const compact = Object.entries(frame.scalar_values ?? {}).map(([key, values]) => [key, summarizeFrameValues(values)] as const);
      const explicit = Object.entries(frame.scalar_fields ?? {}).filter(([key]) => !(frame.scalar_values && key in frame.scalar_values)).map(([key, samples]) => [
        key,
        summarizeFrameValues((samples ?? []).map(sample => sample.value)),
      ] as const);
      return {
      time_s: frame.time_s,
      fields: Object.fromEntries([...compact, ...explicit]),
    };}) ?? [],
    impedance: [
      ...(displayResult?.parasitics.flatMap(item => item.impedance?.length ? [{ net: item.net, points: item.impedance }] : []) ?? []),
      ...(displayResult?.loop_parasitics.flatMap(item => item.impedance?.length ? [{ net: `Loop | ${item.name}`, points: item.impedance }] : []) ?? []),
    ],
    datasets,
  };
}

function summaryMetric(result: SolverResultBundle | null, stats: FieldStat[], key: string, fallbackField?: string) {
  const direct = finite(result?.summary[key]);
  if (direct !== null) return direct;
  return stats.find(item => item.key === fallbackField)?.maximum ?? null;
}

function statusClass(value: unknown) {
  const normalized = String(value ?? "").toLowerCase();
  if (/validated|completed|passed|ready/.test(normalized) && !/approx/.test(normalized)) return "pass";
  if (/fail|error|unsupported|blocked|not run/.test(normalized)) return "fail";
  return "warn";
}

function compactEvidence(input: ReportInput, generated: string, reportId: string, analytics: ReportAnalytics, engineeringLimits: ResultEngineeringAnalytics) {
  const project = record(input.projectPayload);
  const design = record(project.design);
  return {
    contract: "spike/engineering-report/v2",
    report_id: reportId,
    generated_at: generated,
    application_version: APP_VERSION,
    project_contract: project.contract ?? "spike/project/v1",
    project_saved_at: project.saved_at ?? null,
    project: project.project ?? { name: input.projectName },
    design: {
      source_file: design.source_file ?? input.boardFile,
      source_format: design.source_format ?? "unknown",
      source_fingerprint: fnv1a({ board_file: input.boardFile, source_length: typeof design.source_board === "string" ? design.source_board.length : 0 }),
      normalized_geometry_fingerprint: fnv1a(geometryFingerprintInput(input.board)),
    },
    analysis: {
      id: input.result?.analysis_id ?? null,
      contract: input.result?.contract ?? null,
      mode: input.result?.mode ?? input.analysisMode,
      status: input.result?.status ?? "not_run",
      model_status: input.result?.model_status ?? "unsupported",
      setup_fingerprint: fnv1a({ setup: input.setup, limits: input.limits, probes: input.probes }),
      result_fingerprint: input.result ? fnv1a(resultFingerprintInput(input.result)) : null,
      pdn_review: input.pdnReview ?? null,
      source_to_load: resultSolvedForPresentation(input.result) ? input.result?.source_to_load ?? null : null,
    },
    analytics,
    engineering_limits: engineeringLimits,
    solver_provenance: input.result?.provenance ?? { status: "No solver result" },
  };
}

const reportScript = String.raw`
(function(){
  'use strict';
  var runtimeIssues=[];
  var runtimeDiagnostic=document.getElementById('report-runtime-diagnostic');if(!runtimeDiagnostic&&document.body){runtimeDiagnostic=document.createElement('div');runtimeDiagnostic.id='report-runtime-diagnostic';runtimeDiagnostic.className='empty-result';runtimeDiagnostic.setAttribute('role','alert');runtimeDiagnostic.hidden=true;document.body.insertBefore(runtimeDiagnostic,document.body.firstChild);}
  function reportRuntimeIssue(surface,error){var detail=error&&error.message?error.message:String(error||'Unknown rendering failure');var message=surface+': '+detail;if(runtimeIssues.indexOf(message)>=0)return;runtimeIssues.push(message);var diagnostic=document.getElementById('report-runtime-diagnostic');if(diagnostic){diagnostic.hidden=false;diagnostic.textContent='Interactive report rendering diagnostic. '+runtimeIssues.join(' | ');}var target=surface==='Plotly field'?document.getElementById('plotly-field'):surface==='Result graph'?document.getElementById('result-chart'):null;if(target&&target.parentElement){target.parentElement.setAttribute('data-render-error','true');}if(window.console&&window.console.error)window.console.error('[SPIKE report] '+message,error);}
  function renderSafely(surface,render){try{return render();}catch(error){reportRuntimeIssue(surface,error);return null;}}
  window.addEventListener('error',function(event){reportRuntimeIssue('Report script',event.error||event.message);});
  window.addEventListener('unhandledrejection',function(event){reportRuntimeIssue('Report script',event.reason);});
  var dataNode=document.getElementById('report-data');
  var evidenceNode=document.getElementById('evidence-data');
  var data=renderSafely('Report data',function(){return JSON.parse(dataNode&&dataNode.textContent||'null');});
  var evidence=renderSafely('Report data',function(){return JSON.parse(evidenceNode&&evidenceNode.textContent||'{}');})||{};
  var canvas=document.getElementById('board-canvas');
  var context=canvas&&canvas.getContext?canvas.getContext('2d'):null;
  var graph=document.getElementById('result-chart');
  var graphContext=graph&&graph.getContext?graph.getContext('2d'):null;
  var view='2d', zoom=1, panX=0, panY=0, yaw=-0.65, pitch=0.72, dragging=false, lastX=0, lastY=0, fieldDisplay='raw', contourHoverPoints=[];
  var boardFrame=0;function scheduleBoardDraw(){if(boardFrame)return;boardFrame=window.requestAnimationFrame?window.requestAnimationFrame(function(){boardFrame=0;drawBoard();}):setTimeout(function(){boardFrame=0;drawBoard();},16);}
  var metricSelect=document.getElementById('viewport-metric');
  var graphSelect=document.getElementById('graph-series');
  var tooltip=document.getElementById('graph-tooltip');
  var colors=['#4a8df6','#3bc9db','#4dd4ac','#d8df58','#ffb84a','#ef6158'];
  try{
  var netTabs=Array.prototype.slice.call(document.querySelectorAll('[data-net-tab]'));
  var netPanels=Array.prototype.slice.call(document.querySelectorAll('[data-net-panel]'));
  function selectNet(net){netTabs.forEach(function(tab){var active=tab.getAttribute('data-net-tab')===net;tab.classList.toggle('active',active);tab.setAttribute('aria-selected',active?'true':'false');});netPanels.forEach(function(panel){panel.hidden=panel.getAttribute('data-net-panel')!==net;});var dataset=(data&&data.datasets||[]).find(function(item){return item.id===net;});if(dataset){data.fields=dataset.fields||{};data.impedance=dataset.impedance||[];renderSafely('Board canvas',drawBoard);renderSafely('Result graph',drawGraph);}}
  netTabs.forEach(function(tab){tab.addEventListener('click',function(){selectNet(tab.getAttribute('data-net-tab'));});});
  if(netTabs.length)selectNet(netTabs[0].getAttribute('data-net-tab'));
  function resize(target, ctx){if(!target||!ctx)throw new Error('Canvas context is unavailable.');var box=target.getBoundingClientRect();var dpr=Math.min(window.devicePixelRatio||1,2);target.width=Math.max(1,Math.round(box.width*dpr));target.height=Math.max(1,Math.round(box.height*dpr));ctx.setTransform(dpr,0,0,dpr,0,0);return {w:box.width,h:box.height};}
  function layerIndex(name){if(!data)return 0;var index=data.layers.indexOf(name);return index<0?0:index;}
  function layerZ(name){if(!data)return 0;var index=layerIndex(name);return (data.layers.length-1-index)*0.42;}
  // One coordinate policy for every report primitive and field: source board
  // coordinates retain their CAD top-left origin in 2D; 3D converts that same
  // point once to a right-handed world (+Y up).  Do not add per-layer flips.
  function project(point,z,size){var b=data.bounds,cx=(b.minX+b.maxX)/2,cy=(b.minY+b.maxY)/2;var dx=point[0]-cx,dy=point[1]-cy;var base=Math.min((size.w-52)/(b.maxX-b.minX||1),(size.h-52)/(b.maxY-b.minY||1))*zoom;if(view==='2d')return [size.w/2+panX+dx*base,size.h/2+panY+dy*base,0];var worldY=-dy,ca=Math.cos(yaw),sa=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);var rx=dx*ca-worldY*sa,ry=dx*sa+worldY*ca;return [size.w/2+panX+rx*base,size.h/2+panY-(ry*cp+z*sp)*base,(ry*sp-z*cp)];}
  function colorFor(value,min,max){var ratio=max===min?0.5:Math.max(0,Math.min(1,(value-min)/(max-min)));var position=ratio*(colors.length-1),left=Math.floor(position),right=Math.min(colors.length-1,left+1),mix=position-left;function rgb(hex){return [parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)];}var a=rgb(colors[left]),b=rgb(colors[right]);return 'rgb('+Math.round(a[0]+(b[0]-a[0])*mix)+','+Math.round(a[1]+(b[1]-a[1])*mix)+','+Math.round(a[2]+(b[2]-a[2])*mix)+')';}
  function drawContour(samples,metric,min,max,size){contourHoverPoints=[];var triangles=[],budget=12000;for(var sampleIndex=0;sampleIndex<samples.length&&triangles.length<budget;sampleIndex++){var sample=samples[sampleIndex],vertices=sample.vertices_mm||[];if(vertices.length<3)continue;var values=sample.vertex_values||[];for(var vertexIndex=1;vertexIndex<vertices.length-1&&triangles.length<budget;vertexIndex++){var source=[vertices[0],vertices[vertexIndex],vertices[vertexIndex+1]],cornerValues=[values[0],values[vertexIndex],values[vertexIndex+1]].map(function(value){return Number.isFinite(value)?value:sample.value;}),center=[(source[0][0]+source[1][0]+source[2][0])/3,(source[0][1]+source[1][1]+source[2][1])/3],centerValue=(cornerValues[0]+cornerValues[1]+cornerValues[2])/3,layer=sample.layer||'F.Cu',z=layerZ(layer)+.65,projected=source.map(function(vertex){return project([vertex[0],vertex[1]],z,size);}),projectedCenter=project(center,z,size);for(var corner=0;corner<3&&triangles.length<budget;corner++){var next=(corner+1)%3,value=(cornerValues[corner]+cornerValues[next]+centerValue)/3;triangles.push({points:[projected[corner],projected[next],projectedCenter],depth:(projected[corner][2]+projected[next][2]+projectedCenter[2])/3,color:colorFor(value,min,max),sample:sample});}}}triangles.sort(function(a,b){return b.depth-a.depth;}).forEach(function(triangle){context.beginPath();triangle.points.forEach(function(point,index){if(index===0)context.moveTo(point[0],point[1]);else context.lineTo(point[0],point[1]);});context.closePath();context.fillStyle=triangle.color;context.globalAlpha=.86;context.fill();context.globalAlpha=1;var cx=(triangle.points[0][0]+triangle.points[1][0]+triangle.points[2][0])/3,cy=(triangle.points[0][1]+triangle.points[1][1]+triangle.points[2][1])/3;contourHoverPoints.push({x:cx,y:cy,value:triangle.sample.value,xMm:triangle.sample.x_mm,yMm:triangle.sample.y_mm,layer:triangle.sample.layer,net:triangle.sample.net,sourceId:triangle.sample.source_id||triangle.sample.element_id||''});});if(!triangles.length){context.fillStyle='#a7bbc4';context.font='13px sans-serif';context.fillText('No explicit solver faces are available for this field.',24,42);}}
  function polygon(points,z,size,fill,stroke){if(!points||points.length<2)return;context.beginPath();points.forEach(function(point,index){var p=project(point,z,size);if(index===0)context.moveTo(p[0],p[1]);else context.lineTo(p[0],p[1]);});context.closePath();if(fill){context.fillStyle=fill;context.fill();}if(stroke){context.strokeStyle=stroke;context.lineWidth=1;context.stroke();}}
  function rectanglePoints(center,width,height,degrees){var radians=(degrees||0)*Math.PI/180,c=Math.cos(radians),s=Math.sin(radians);return [[-width/2,-height/2],[width/2,-height/2],[width/2,height/2],[-width/2,height/2]].map(function(offset){return [center[0]+offset[0]*c-offset[1]*s,center[1]+offset[0]*s+offset[1]*c];});}
  function drawBoard(){if(!canvas||!context){reportRuntimeIssue('Board canvas',new Error('2D canvas is unavailable in this report viewer.'));return;}var size=resize(canvas,context);context.clearRect(0,0,size.w,size.h);context.fillStyle='#101a20';context.fillRect(0,0,size.w,size.h);if(!data){context.fillStyle='#a7bbc4';context.font='14px sans-serif';context.fillText('No imported board geometry is available.',24,40);return;}
    var metric=metricSelect.value, samples=(data.fields&&data.fields[metric])||[];var range=samples.reduce(function(state,item){if(!Number.isFinite(item.value))return state;state.min=Math.min(state.min,item.value);state.max=Math.max(state.max,item.value);state.count++;return state;},{min:Infinity,max:-Infinity,count:0}),min=range.count?range.min:0,max=range.count?range.max:1;
    var copper='#c58a35',boardFill=view==='3d'?'rgba(43,98,74,.82)':'rgba(43,98,74,.62)';
    data.outlineLoops.forEach(function(loop){polygon(loop,0,size,boardFill,'#7f9da5');});
    data.zones.slice().sort(function(a,b){return layerIndex(b.l)-layerIndex(a.l);}).forEach(function(zone){polygon(zone.p,layerZ(zone.l),size,'rgba(183,126,47,.18)',null);});
    data.tracks.forEach(function(track){var a=project(track.s,layerZ(track.l),size),b=project(track.e,layerZ(track.l),size);context.beginPath();context.moveTo(a[0],a[1]);context.lineTo(b[0],b[1]);context.strokeStyle=copper;context.lineWidth=Math.max(1,track.w*Math.min(size.w/(data.bounds.maxX-data.bounds.minX||1),size.h/(data.bounds.maxY-data.bounds.minY||1))*zoom);context.lineCap='round';context.stroke();});
    data.pads.forEach(function(pad){polygon(rectanglePoints(pad.p,Math.max(.06,pad.w),Math.max(.06,pad.h),pad.r),layerZ(pad.l),size,'#d7a34b',null);});
    data.vias.forEach(function(via){var p=project(via.p,layerZ(via.ls&&via.ls[0]),size);var factor=Math.min(size.w/(data.bounds.maxX-data.bounds.minX||1),size.h/(data.bounds.maxY-data.bounds.minY||1))*zoom;context.beginPath();context.arc(p[0],p[1],Math.max(1.5,via.d*factor/2),0,Math.PI*2);context.fillStyle='#d7a34b';context.fill();context.beginPath();context.arc(p[0],p[1],Math.max(0.7,via.drill*factor/2),0,Math.PI*2);context.fillStyle='#101a20';context.fill();});
    data.components.forEach(function(component){polygon(rectanglePoints(component.p,Math.max(.08,component.w),Math.max(.08,component.h),component.r),view==='3d'?layerZ(component.l)+1.25:layerZ(component.l),size,null,'rgba(218,231,235,.55)');});
    contourHoverPoints=[];if(samples.length&&fieldDisplay!=='raw'){drawContour(samples,metric,min,max,size);}else if(samples.length){samples.forEach(function(sample){var p=project([sample.x_mm,sample.y_mm],sample.z_mm==null?layerZ(sample.layer):sample.z_mm,size),color=colorFor(sample.value,min,max),smooth=fieldDisplay==='smooth',radius=smooth?(view==='3d'?8:10):(view==='3d'?2.3:2.7);context.beginPath();context.arc(p[0],p[1],radius,0,Math.PI*2);if(smooth){var gradient=context.createRadialGradient(p[0],p[1],0,p[0],p[1],radius);gradient.addColorStop(0,color);gradient.addColorStop(.58,color);gradient.addColorStop(1,'rgba(0,0,0,0)');context.fillStyle=gradient;context.globalAlpha=.62;}else{context.fillStyle=color;context.globalAlpha=.9;}context.fill();context.globalAlpha=1;});}
    var bar=document.getElementById('viewport-colorbar');bar.hidden=!samples.length;document.getElementById('color-min').textContent=samples.length?min.toPrecision(4):'-';document.getElementById('color-max').textContent=samples.length?max.toPrecision(4):'-';document.getElementById('color-unit').textContent=metricSelect.options[metricSelect.selectedIndex].getAttribute('data-unit')||'';
  }
  function resetView(){zoom=1;panX=0;panY=0;yaw=-0.65;pitch=0.72;drawBoard();}
  document.querySelectorAll('[data-board-view]').forEach(function(button){button.addEventListener('click',function(){view=button.getAttribute('data-board-view');document.querySelectorAll('[data-board-view]').forEach(function(item){item.classList.toggle('active',item===button);});document.getElementById('interaction-hint').textContent=view==='3d'?'Left drag orbit | Middle/right drag pan | Wheel zoom':'Drag pan | Wheel zoom | Double-click fit';resetView();});});
  metricSelect.addEventListener('change',drawBoard);document.querySelectorAll('[data-field-display]').forEach(function(button){button.addEventListener('click',function(){fieldDisplay=button.getAttribute('data-field-display');if(fieldDisplay==='contour'&&view!=='3d'){view='3d';document.querySelectorAll('[data-board-view]').forEach(function(item){item.classList.toggle('active',item.getAttribute('data-board-view')==='3d');});}document.querySelectorAll('[data-field-display]').forEach(function(item){item.classList.toggle('active',item===button);});drawBoard();});});canvas.addEventListener('contextmenu',function(event){event.preventDefault();});canvas.addEventListener('pointerdown',function(event){dragging=true;lastX=event.clientX;lastY=event.clientY;canvas.setPointerCapture(event.pointerId);});canvas.addEventListener('pointerup',function(){dragging=false;});canvas.addEventListener('pointermove',function(event){var viewportTooltip=document.getElementById('viewport-tooltip');if(!dragging){if(fieldDisplay!=='raw'&&contourHoverPoints.length){var box=canvas.getBoundingClientRect(),x=event.clientX-box.left,y=event.clientY-box.top,nearest=contourHoverPoints.reduce(function(best,point){var distance=(point.x-x)*(point.x-x)+(point.y-y)*(point.y-y);return !best||distance<best.distance?{point:point,distance:distance}:best;},null);if(nearest&&nearest.distance<625){var option=metricSelect.options[metricSelect.selectedIndex],unit=option.getAttribute('data-unit')||'';viewportTooltip.hidden=false;viewportTooltip.style.left=Math.min(box.width-220,x+14)+'px';viewportTooltip.style.top=Math.max(8,y-62)+'px';viewportTooltip.textContent=Number(nearest.point.value).toPrecision(7)+' '+unit+' | '+nearest.point.xMm.toFixed(3)+', '+nearest.point.yMm.toFixed(3)+' mm | '+nearest.point.layer+' | returned solver sample';return;}}viewportTooltip.hidden=true;return;}viewportTooltip.hidden=true;var dx=event.clientX-lastX,dy=event.clientY-lastY;lastX=event.clientX;lastY=event.clientY;if(view==='3d'&&event.buttons===1&&!event.shiftKey){yaw+=dx*.009;pitch=Math.max(.12,Math.min(1.45,pitch+dy*.009));}else{panX+=dx;panY+=dy;}scheduleBoardDraw();});canvas.addEventListener('pointerleave',function(){document.getElementById('viewport-tooltip').hidden=true;});canvas.addEventListener('wheel',function(event){event.preventDefault();zoom=Math.max(.18,Math.min(12,zoom*Math.exp(-event.deltaY*.001)));scheduleBoardDraw();},{passive:false});canvas.addEventListener('dblclick',resetView);
  function graphSeries(){if(!data)return null;var key=graphSelect.value;if(key.indexOf('impedance:')===0){var net=key.slice(10),network=data.impedance.find(function(item){return item.net===net;});return network?{label:'Impedance | '+net,unit:'ohm',xLabel:'Frequency (Hz)',logX:true,points:network.points.map(function(point){return [point.frequency_hz,point.magnitude_ohm,point];})}:null;}if(key.indexOf('transient:')===0){var field=key.slice(10),option=graphSelect.options[graphSelect.selectedIndex],frames=(data.timeSeries||[]).filter(function(frame){return frame.fields&&frame.fields[field];});return frames.length?{label:option.textContent,unit:option.getAttribute('data-unit')||'',xLabel:'Time (s)',logX:false,points:frames.map(function(frame){return [frame.time_s,frame.fields[field].maximum,{time_s:frame.time_s}];})}:null;}var samples=(data.fields&&data.fields[key])||[];var option=graphSelect.options[graphSelect.selectedIndex];return samples.length?{label:option.textContent,unit:option.getAttribute('data-unit')||'',xLabel:'Spatial sample',logX:false,points:samples.map(function(sample,index){return [index+1,sample.value,sample];})}:null;}
  var graphPlot=null;
  function drawGraph(){if(!graph||!graphContext){reportRuntimeIssue('Result graph',new Error('2D canvas is unavailable in this report viewer.'));return;}var size=resize(graph,graphContext);graphContext.clearRect(0,0,size.w,size.h);graphContext.fillStyle='#fff';graphContext.fillRect(0,0,size.w,size.h);var series=graphSeries();if(!series||!series.points.length){graphContext.fillStyle='#657982';graphContext.font='13px sans-serif';graphContext.fillText('No graphable solver output is available.',24,42);graphPlot=null;return;}var points=series.points.filter(function(point){return Number.isFinite(point[0])&&Number.isFinite(point[1]);});var bounds=points.reduce(function(state,point){var x=series.logX?Math.log10(Math.max(point[0],1e-30)):point[0],y=point[1];state.minX=Math.min(state.minX,x);state.maxX=Math.max(state.maxX,x);state.minY=Math.min(state.minY,y);state.maxY=Math.max(state.maxY,y);return state;},{minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity}),minX=bounds.minX,maxX=bounds.maxX,minY=bounds.minY,maxY=bounds.maxY;if(maxY===minY){maxY+=1;minY-=1;}var left=62,right=18,top=24,bottom=44;function sx(value){var transformed=series.logX?Math.log10(Math.max(value,1e-30)):value;return left+(transformed-minX)/(maxX-minX||1)*(size.w-left-right);}function sy(value){return top+(maxY-value)/(maxY-minY)*(size.h-top-bottom);}graphContext.strokeStyle='#d9e1e4';graphContext.lineWidth=1;graphContext.font='10px sans-serif';graphContext.fillStyle='#61727a';for(var i=0;i<=5;i++){var y=top+i*(size.h-top-bottom)/5;graphContext.beginPath();graphContext.moveTo(left,y);graphContext.lineTo(size.w-right,y);graphContext.stroke();var label=maxY-(maxY-minY)*i/5;graphContext.fillText(label.toPrecision(4),4,y+3);}graphContext.strokeStyle='#237d94';graphContext.lineWidth=1.7;graphContext.beginPath();points.forEach(function(point,index){var x=sx(point[0]),y=sy(point[1]);if(index===0)graphContext.moveTo(x,y);else graphContext.lineTo(x,y);});graphContext.stroke();graphContext.fillStyle='#1c3d49';graphContext.font='600 11px sans-serif';graphContext.fillText(series.xLabel,left,size.h-12);graphContext.save();graphContext.translate(13,size.h/2);graphContext.rotate(-Math.PI/2);graphContext.fillText(series.unit,0,0);graphContext.restore();graphPlot={points:points,sx:sx,sy:sy,series:series};}
  graph.addEventListener('pointermove',function(event){if(!graphPlot)return;var box=graph.getBoundingClientRect(),x=event.clientX-box.left;var nearest=graphPlot.points.reduce(function(best,point){var distance=Math.abs(graphPlot.sx(point[0])-x);return !best||distance<best.distance?{point:point,distance:distance}:best;},null);if(!nearest)return;var point=nearest.point,meta=point[2]||{};tooltip.hidden=false;tooltip.style.left=Math.min(box.width-205,Math.max(8,graphPlot.sx(point[0])+10))+'px';tooltip.style.top=Math.max(8,graphPlot.sy(point[1])-55)+'px';tooltip.textContent='';var title=document.createElement('b'),value=document.createElement('span'),detail=document.createElement('small');title.textContent=graphPlot.series.label;value.textContent=Number(point[1]).toPrecision(7)+' '+graphPlot.series.unit;detail.textContent=graphPlot.series.logX?Number(point[0]).toPrecision(6)+' Hz':meta.time_s!=null?'t '+Number(meta.time_s).toPrecision(7)+' s':((meta.x_mm==null?'Sample '+point[0]:'x '+Number(meta.x_mm).toFixed(3)+' mm | y '+Number(meta.y_mm).toFixed(3)+' mm')+(meta.layer?' | '+meta.layer:''));tooltip.append(title,value,detail);});graph.addEventListener('pointerleave',function(){tooltip.hidden=true;});graphSelect.addEventListener('change',drawGraph);
  var printButton=document.getElementById('print-report'),evidenceButton=document.getElementById('download-evidence');if(printButton)printButton.addEventListener('click',function(){window.print();});if(evidenceButton)evidenceButton.addEventListener('click',function(){var blob=new Blob([JSON.stringify(evidence,null,2)],{type:'application/json'}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=evidence.report_id+'-evidence.json';link.click();setTimeout(function(){URL.revokeObjectURL(link.href);},1000);});
  var resizeFrame=0;window.addEventListener('resize',function(){if(resizeFrame)return;resizeFrame=window.requestAnimationFrame?window.requestAnimationFrame(function(){resizeFrame=0;renderSafely('Board canvas',drawBoard);renderSafely('Result graph',drawGraph);}):setTimeout(function(){resizeFrame=0;renderSafely('Board canvas',drawBoard);renderSafely('Result graph',drawGraph);},32);});renderSafely('Board canvas',drawBoard);renderSafely('Result graph',drawGraph);
  }catch(error){reportRuntimeIssue('Report initialization',error);}
})();`;

export function buildEngineeringReport(input: ReportInput) {
  const { board, setup } = input;
  const requestedResult = input.result, domain = input.domain ?? reportDomain(input.result, input.analysisMode);
  const result = requestedResult && reportDomain(requestedResult, requestedResult.mode) === domain
    ? requestedResult
    : input.results?.find(item => reportDomain(item.bundle, item.bundle.mode) === domain)?.bundle ?? null;
  const displayResult = resultSolvedForPresentation(result) ? result : null;
  const generated = new Date().toISOString();
  const reportId = `SPIKE-${result?.analysis_id || generated.replace(/[-:.TZ]/g, "").slice(0, 14)}`;
  const stats = fieldStats(result);
  const issues = result?.issues ?? [];
  const domainRecords = (input.results ?? []).filter(item => reportDomain(item.bundle, item.bundle.mode) === domain), domainInput: ReportInput = { ...input, result, results: domainRecords,
    pdnReview: displayResult ? input.pdnReview : null };
  const analytics = buildReportAnalytics(domainInput);
  const densityLimit = finite(input.limits.density);
  const engineeringBundles = [...new Map([
    ...domainRecords.map(item => [item.bundle.analysis_id || item.id || item.label, item.bundle] as const),
    ...(result ? [[result.analysis_id || "active", result] as const] : []),
  ]).values()].filter(bundle => reportDomain(bundle, bundle.mode) === domain && resultSolvedForPresentation(bundle));
  const engineeringResult = engineeringBundles.length <= 1 ? engineeringBundles[0] ?? null : {
    ...engineeringBundles[0],
    analysis_id: "report-aggregate",
    scalar_fields: {
      voltage_v: engineeringBundles.flatMap(bundle => bundle.scalar_fields.voltage_v),
      voltage_drop_v: engineeringBundles.flatMap(bundle => bundle.scalar_fields.voltage_drop_v),
      current_a: engineeringBundles.flatMap(bundle => bundle.scalar_fields.current_a),
      operating_point_impedance_ohm: engineeringBundles.flatMap(bundle => bundle.scalar_fields.operating_point_impedance_ohm),
      current_density_a_mm2: engineeringBundles.flatMap(bundle => bundle.scalar_fields.current_density_a_mm2),
      power_loss_w: engineeringBundles.flatMap(bundle => bundle.scalar_fields.power_loss_w),
      via_current_density_a_mm2: engineeringBundles.flatMap(bundle => bundle.scalar_fields.via_current_density_a_mm2),
    },
    probes: engineeringBundles.flatMap(bundle => bundle.probes),
  };
  const engineeringLimits = buildResultEngineeringAnalytics(engineeringResult, densityLimit !== null && densityLimit > 0 ? densityLimit : null, input.fusingSettings);
  const evidence = compactEvidence(domainInput, generated, reportId, analytics, engineeringLimits);
  const terminalReview = domain === "pi" ? sourceLoadReview(displayResult, input.setup.net || null, finite(input.limits.drop)) : null;
  const sourceLoadHtml = sourceLoadReportHtml(terminalReview, displayResult?.model_status, fmt, html);
  const netRecords: ReportResultRecord[] = domainRecords.length ? domainRecords : result ? [{ label: setup.net || result.analysis_id || "Analysis", bundle: result }] : [];
  const geometry = reportGeometry(board, result, netRecords);
  const solver = result?.provenance.solver ?? result?.provenance.solver_plugin ?? "Not run";
  const maxDrop = analytics.worstDropV ?? summaryMetric(displayResult, stats, "max_voltage_drop_v", "voltage_drop_v");
  const maxDensity = analytics.peakCurrentDensityAMm2 ?? summaryMetric(displayResult, stats, "max_current_density_a_mm2", "current_density_a_mm2");
  const transientMode = input.analysisMode === "Transient PI" || result?.mode === "transient";
  const totalLoss = analytics.totalConductorLossW ?? summaryMetric(displayResult, stats, transientMode ? "peak_copper_loss_w" : "total_copper_loss_w");
  const passivityCorrection = finite(result?.summary.inductance_passivity_correction_ratio);
  const scaledResidual = finite(result?.summary.max_scaled_linear_residual);
  const metricCards = (domain === "pi" ? [
    ["Worst maximum drop", maxDrop === null ? "-" : `${fmt(maxDrop * 1000)} mV`, maxDrop !== null && finite(input.limits.drop) !== null && maxDrop * 1000 > Number(input.limits.drop) ? "limit" : ""],
    ["Peak current density", maxDensity === null ? "-" : `${fmt(maxDensity)} A/mm2`, maxDensity !== null && finite(input.limits.density) !== null && maxDensity > Number(input.limits.density) ? "limit" : ""],
    [transientMode ? "Analyzed peak conductor loss" : "Analyzed conductor loss", totalLoss === null ? "-" : `${fmt(totalLoss)} W`, ""],
    ["Estimated source power", analytics.totalSourcePowerW === null ? "-" : `${fmt(analytics.totalSourcePowerW)} W`, ""],
    ["Estimated delivered power", analytics.totalDeliveredPowerW === null ? "-" : `${fmt(analytics.totalDeliveredPowerW)} W`, ""],
    ["Conduction efficiency", analytics.conductionEfficiencyPercent === null ? "-" : `${fmt(analytics.conductionEfficiencyPercent, 4)}%`, ""],
  ] : [
    ["Report discipline", domainLabels[domain], ""],
    ["Result status", result?.status ?? "Not run", statusClass(result?.status ?? "not run")],
    ["Model status", result?.model_status ?? "Not returned", statusClass(result?.model_status ?? "unsupported")],
    ["Solver", solver, ""],
    ["Analysis ID", result?.analysis_id ?? "Not assigned", ""],
    ["Returned fields", stats.length.toLocaleString("en-US"), ""],
  ]).map(([label, value, className]) => `<div class="metric ${className}"><span>${html(label)}</span><strong>${html(value)}</strong></div>`).join("");
  const failedNotice = result && !displayResult ? `<p class="empty-result">${html(result.status)} analysis: no solved values or plots are shown. ${html(String(result.provenance?.failure_stage ?? result.summary?.failure_stage ?? "Inspect solver issues and provenance below."))}</p>` : "";

  const analyticsTable = boundedRows(analytics.rows);
  const analyticsRows = analyticsTable.items.map(item => `<tr><td><b>${html(item.scope)}</b></td><td>${html(item.mode)}</td><td><span class="severity ${statusClass(`${item.status} ${item.modelStatus}`)}">${html(item.modelStatus)}</span></td><td>${fmt(item.sourceVoltageV, 6)}</td><td>${fmt(item.loadCurrentA, 6)}</td><td>${item.maxDropV === null ? "-" : fmt(item.maxDropV * 1000, 6)}</td><td>${fmt(item.dropPercent, 5)}</td><td>${fmt(item.conductorLossW, 7)}</td><td>${fmt(item.sourcePowerW, 7)}</td><td>${fmt(item.deliveredPowerW, 7)}</td><td>${fmt(item.conductionEfficiencyPercent, 5)}</td><td>${fmt(item.effectiveResistanceOhm, 8)}</td><td>${fmt(item.peakCurrentDensityAMm2, 6)}</td><td>${fmt(item.nodeCount, 0)}</td><td>${fmt(item.solverTimeS, 5)}</td></tr>`).join("") + (analyticsTable.omitted ? `<tr><td colspan="15">${analyticsTable.omitted.toLocaleString("en-US")} additional scope rows are preserved in evidence JSON but omitted from this responsive report table.</td></tr>` : "");
  const breakdownRows = (values: Record<string, number>) => {
    const bounded = boundedRows(Object.entries(values).sort((left, right) => right[1] - left[1]));
    return bounded.items
    .map(([name, value]) => `<tr><td>${html(name)}</td><td>${fmt(value, 8)}</td><td>${analytics.totalConductorLossW && analytics.totalConductorLossW > 0 ? `${fmt(value / analytics.totalConductorLossW * 100, 5)}%` : "-"}</td></tr>`)
    .join("") + (bounded.omitted ? `<tr><td colspan="3">${bounded.omitted.toLocaleString("en-US")} lower-ranked rows omitted from this report table; evidence JSON remains complete.</td></tr>` : "");
  };
  const netLossRows = breakdownRows(analytics.byNetW);
  const layerLossRows = breakdownRows(analytics.byLayerW);
  const geometryLossRows = breakdownRows(analytics.byGeometryW);
  const viaStressRows = engineeringLimits.stressedVias.slice(0, 30).map(via => `<tr><td><code>${html(via.elementId)}</code></td><td>${html(via.net)}</td><td>${html(via.layer)}</td><td>${fmt(via.currentDensityAMm2, 7)}</td><td>${via.designLimitUtilization === null ? "-" : `${fmt(via.designLimitUtilization * 100, 5)}%`}</td><td>${via.fusingUtilization === null ? "-" : `${fmt(via.fusingUtilization * 100, 5)}%`}</td><td><span class="severity ${via.status === "ok" ? "pass" : via.status === "fusing" ? "fail" : "warn"}">${html(via.status)}</span></td></tr>`).join("");
  const probeAnalytics = engineeringLimits.probeSummary;
  const fusingThreshold = engineeringLimits.fusing.currentDensityThresholdAMm2;
  const engineeringAnalyticsHtml = `<section id="engineering-analytics"><h2>Electrical Field, Probe, and Via Analytics</h2><table class="summary-table"><tr><th>Voltage field range</th><td>${(() => { const field = engineeringLimits.fields.find(item => item.key === "voltage_v"); return field ? `${fmt(field.minimum, 7)} to ${fmt(field.maximum, 7)} V` : "-"; })()}</td><th>Voltage-drop range</th><td>${(() => { const field = engineeringLimits.fields.find(item => item.key === "voltage_drop_v"); return field ? `${fmt(field.minimum * 1000, 7)} to ${fmt(field.maximum * 1000, 7)} mV` : "-"; })()}</td></tr><tr><th>Current-density range</th><td>${(() => { const field = engineeringLimits.fields.find(item => item.key === "current_density_a_mm2"); return field ? `${fmt(field.minimum, 7)} to ${fmt(field.maximum, 7)} A/mm2` : "-"; })()}</td><th>Via-density range</th><td>${(() => { const field = engineeringLimits.fields.find(item => item.key === "via_current_density_a_mm2"); return field ? `${fmt(field.minimum, 7)} to ${fmt(field.maximum, 7)} A/mm2` : "-"; })()}</td></tr><tr><th>Mapped probes</th><td>${probeAnalytics.mapped} / ${probeAnalytics.total}</td><th>Probe voltage range</th><td>${probeAnalytics.minimumVoltageV === null ? "-" : `${fmt(probeAnalytics.minimumVoltageV, 7)} to ${fmt(probeAnalytics.maximumVoltageV, 7)} V`}</td></tr><tr><th>Maximum probe drop</th><td>${probeAnalytics.maximumDropV === null ? "-" : `${fmt(probeAnalytics.maximumDropV * 1000, 7)} mV`}</td><th>Maximum probe density</th><td>${probeAnalytics.maximumCurrentDensityAMm2 === null ? "-" : `${fmt(probeAnalytics.maximumCurrentDensityAMm2, 7)} A/mm2`}</td></tr></table><h3>Copper fusing screen</h3><table class="summary-table"><tr><th>Model status</th><td><span class="severity warn">${html(engineeringLimits.fusing.modelStatus)}</span></td><th>Ambient / event duration</th><td>${fmt(engineeringLimits.fusing.ambientTemperatureC, 5)} C / ${fmt(engineeringLimits.fusing.faultDurationS, 7)} s</td></tr><tr><th>Calculated threshold</th><td>${fusingThreshold === null ? "Invalid input" : `${fmt(fusingThreshold, 7)} A/mm2`}</td><th>Maximum utilization</th><td>${engineeringLimits.fusing.maximumUtilization === null ? "-" : `${fmt(engineeringLimits.fusing.maximumUtilization * 100, 6)}%`}</td></tr></table><h3>Via electrical stress map</h3>${viaStressMapSvg(engineeringResult?.scalar_fields.via_current_density_a_mm2 ?? [])}<h3>Via stress ranking (top 30)</h3><table class="data-table"><thead><tr><th>Via</th><th>Net</th><th>Layer span</th><th>Density (A/mm2)</th><th>Design-limit use</th><th>Fusing use</th><th>Status</th></tr></thead><tbody>${viaStressRows || "<tr><td colspan='7'>The solver returned no via-current-density samples.</td></tr>"}</tbody></table><div class="analytics-note"><b>Fusing-screen validity</b><p>This short-duration adiabatic screen uses Onderdonk's copper equation with area in circular mils, the entered initial ambient, and event duration. It is not a continuous-current ampacity or PCB temperature-rise rating. It excludes PCB heat spreading, copper-thickness and via-plating tolerance, solder, neck-down geometry, convection, and enclosure conditions. Those effects require mesh-converged electro-thermal analysis. Equation reference: NASA NTRS, Evaluation of Magnet Configurations for Magnetohydrodynamic Aerocapture, Eq. 13, document 20240015387.</p></div></section>`;

  const pdnReview = displayResult && domainInput.pdnReview?.contract === "spike/pdn-review/v1" ? domainInput.pdnReview : null;
  const pdnCandidateRows = (pdnReview?.candidate_screening ?? []).map(candidate => {
    const issues = (candidate.issues ?? []).map(issue => `${issue.code}: ${issue.message}`).join("; ");
    return `<tr><td><b>${html(candidate.id)}</b></td><td><span class="severity ${statusClass(candidate.status)}">${html(candidate.status)}</span></td><td>${html(candidate.placement_method.replace(/_/g, " "))}</td><td><span class="severity ${statusClass(candidate.model_status)}">${html(candidate.model_status)}</span></td><td>${fmt(candidate.worst_impedance_ohm, 8)}</td><td>${fmt(candidate.worst_frequency_hz, 8)}</td><td>${fmt(candidate.worst_target_ratio, 7)}</td><td>${candidate.worst_impedance_improvement_percent == null ? "-" : `${fmt(candidate.worst_impedance_improvement_percent, 6)}%`}</td><td>${candidate.maximum_local_degradation_percent == null ? "-" : `${fmt(candidate.maximum_local_degradation_percent, 6)}%`}</td><td>${candidate.violation_count ?? "-"}</td><td><span class="severity ${candidate.passes_target ? "pass" : "fail"}">${candidate.passes_target ? "pass" : "fail"}</span></td><td>${html(issues || "-")}</td></tr>`;
  }).join("");
  const pdnPeakRows = [
    ...(pdnReview?.resonances ?? []).map(item => ({ type: "Resonance", ...item })),
    ...(pdnReview?.anti_resonances ?? []).map(item => ({ type: "Anti-resonance", ...item })),
  ].sort((left, right) => left.frequency_hz - right.frequency_hz)
    .map(item => `<tr><td>${html(item.type)}</td><td>${fmt(item.frequency_hz, 8)}</td><td>${fmt(item.magnitude_ohm, 8)}</td><td>${pdnReview ? fmt(item.magnitude_ohm / pdnReview.target_ohm, 7) : "-"}</td></tr>`)
    .join("");
  const pdnMethodRows = Object.entries(pdnReview?.candidate_method_counts ?? {})
    .map(([method, count]) => `<tr><td>${html(method.replace(/_/g, " "))}</td><td>${count}</td></tr>`)
    .join("");
  const pdnReviewHtml = pdnReview ? `<section id="pdn-review"><h2>PDN Target and Decoupling Review</h2><table class="summary-table"><tr><th>Power net</th><td><b>${html(pdnReview.net)}</b></td><th>Review status</th><td><span class="severity ${statusClass(pdnReview.status)}">${html(pdnReview.status)}</span></td></tr><tr><th>Target impedance</th><td>${fmt(pdnReview.target_ohm, 8)} ohm</td><th>Maximum impedance</th><td>${fmt(pdnReview.maximum_impedance_ohm, 8)} ohm</td></tr><tr><th>Violation samples</th><td>${pdnReview.violation_count}</td><th>Model status</th><td><span class="severity ${statusClass(pdnReview.model_status)}">${html(pdnReview.model_status)}</span></td></tr><tr><th>Best screened candidate</th><td>${html(pdnReview.best_candidate_id || "None")}</td><th>Candidate methods</th><td><table class="data-table"><tbody>${pdnMethodRows || "<tr><td>No candidates</td><td>0</td></tr>"}</tbody></table></td></tr></table><h3>Candidate screening</h3><table class="data-table"><thead><tr><th>Candidate</th><th>State</th><th>Placement model</th><th>Model status</th><th>Worst Z (ohm)</th><th>Worst frequency (Hz)</th><th>Z / target</th><th>Worst-Z improvement</th><th>Maximum local degradation</th><th>Violations</th><th>Target</th><th>Issues</th></tr></thead><tbody>${pdnCandidateRows || "<tr><td colspan='12'>No capacitor candidates were screened.</td></tr>"}</tbody></table><h3>Detected resonances</h3><table class="data-table"><thead><tr><th>Type</th><th>Frequency (Hz)</th><th>Magnitude (ohm)</th><th>Target ratio</th></tr></thead><tbody>${pdnPeakRows || "<tr><td colspan='4'>No resonance extrema were detected on the supplied sweep.</td></tr>"}</tbody></table><div class="analytics-note"><b>Placement-screen validity</b><p>Direct-port shunt and explicit series-connection-path candidates are circuit screening approximations. Geometry-aware location ranking is used only when reviewed, frequency-aligned two-port impedance data is supplied. Candidate ranking is not a global placement optimum and inherits the weakest model status of the source impedance and placement data. Rejected candidates remain visible with canonical error codes.</p></div></section>` : "";

  const emiSetup = input.emi?.setup;
  const emiPreflight = input.emi?.preflight;
  const emiScreening = input.emi?.screening;
  const emiStageRows = (emiPreflight?.stages ?? []).map(stage => `<tr><td><b>${html(stage.name)}</b></td><td><span class="severity ${statusClass(stage.state)}">${html(stage.state.replace(/_/g, " "))}</span></td><td>${html(stage.detail)}</td></tr>`).join("");
  const emiGeometryRows = (emiPreflight?.geometry_coverage ?? []).map(item => `<tr><td><b>${html(item.net)}</b></td><td>${item.tracks}</td><td>${item.vias}</td><td>${item.pads}</td><td>${item.zones}</td><td>${html(item.layers.join(" / ") || "-")}</td><td>${fmt(item.routed_length_mm, 7)}</td><td><span class="severity ${item.has_geometry ? "pass" : "fail"}">${item.has_geometry ? "mapped" : "missing"}</span></td></tr>`).join("");
  const emiRankingRows = (emiScreening?.screening?.recommended_nets ?? []).map((item, index) => `<tr><td>${index + 1}</td><td><b>${html(item.net)}</b></td><td>${fmt(item.score, 7)}</td><td>${html(item.reasons.join("; ") || "No ranking reasons were published")}</td><td>${item.geometry.tracks ?? 0} / ${item.geometry.vias ?? 0} / ${item.geometry.zones ?? 0}</td><td>${html(item.geometry.layers?.join(" / ") || "-")}</td></tr>`).join("");
  const emiIssueRows = (emiPreflight?.issues ?? []).map(issue => `<tr><td><span class="severity ${statusClass(issue.severity)}">${html(issue.severity)}</span></td><td><code>${html(issue.code)}</code></td><td>${html(issue.message)}</td><td>${html(issue.suggestion || "-")}</td></tr>`).join("");
  const emiReportHtml = emiSetup ? `<section id="emi-workflow"><h2>EMI Test Workflow</h2><table class="summary-table"><tr><th>Workflow status</th><td><span class="severity ${statusClass(emiPreflight?.status ?? "not run")}">${html(emiPreflight?.status?.replace(/_/g, " ") ?? "not run")}</span></td><th>Model status</th><td><span class="severity ${statusClass(emiScreening?.model_status ?? "unsupported")}">${html(emiScreening?.model_status ?? "not screened")}</span></td></tr><tr><th>Candidate nets</th><td>${html(emiSetup.selected_nets.join(" / ") || "none")}</td><th>Return nets</th><td>${html(emiSetup.return_nets.join(" / ") || "none")}</td></tr><tr><th>Requested analyses</th><td>${html(emiSetup.requested_analyses.join(" / ") || "none")}</td><th>Frequency range</th><td>${fmt(emiSetup.frequency.start_hz, 8)} to ${fmt(emiSetup.frequency.stop_hz, 8)} Hz | ${emiSetup.frequency.points} points</td></tr><tr><th>Environment</th><td>${html(emiSetup.environment.kind.replace(/_/g, " "))}</td><th>Excitation</th><td>${html(emiSetup.excitation.mode.replace(/_/g, " "))} | ${emiSetup.excitation.ports.length} explicit port(s)</td></tr><tr><th>Mesh / boundary</th><td>${fmt(emiSetup.mesh.resolution_mm, 6)} mm | ${emiSetup.mesh.padding_cells} cells</td><th>Maximum runtime</th><td>${fmt(emiSetup.max_solver_time_s, 7)} s</td></tr><tr><th>Readiness gates</th><td colspan="3">Screen ${emiPreflight?.can_screen ? "ready" : "blocked"} | Prepare ${emiPreflight?.can_prepare ? "ready" : "blocked"} | Run ${emiPreflight?.can_run ? "ready" : "blocked"}</td></tr></table><h3>Process readiness</h3><table class="data-table"><thead><tr><th>Stage</th><th>State</th><th>Detail</th></tr></thead><tbody>${emiStageRows || "<tr><td colspan='3'>Run EMI preflight to populate staged readiness.</td></tr>"}</tbody></table><h3>Selected-net geometry coverage</h3><table class="data-table"><thead><tr><th>Net</th><th>Tracks</th><th>Vias</th><th>Pads</th><th>Zones</th><th>Layers</th><th>Routed mm</th><th>Status</th></tr></thead><tbody>${emiGeometryRows || "<tr><td colspan='8'>No geometry coverage record is attached.</td></tr>"}</tbody></table><h3>Pre-pass risk ranking</h3><table class="data-table"><thead><tr><th>Rank</th><th>Net</th><th>Score</th><th>Traceable reasons</th><th>Track / via / zone</th><th>Layers</th></tr></thead><tbody>${emiRankingRows || "<tr><td colspan='6'>No EMI pre-pass screening result is attached.</td></tr>"}</tbody></table><h3>Setup and capability issues</h3><table class="data-table"><thead><tr><th>Severity</th><th>Code</th><th>Message</th><th>Suggested action</th></tr></thead><tbody>${emiIssueRows || "<tr><td colspan='4'>No EMI preflight issues were recorded.</td></tr>"}</tbody></table><div class="analytics-note"><b>EMI validity boundary</b><p>${html(emiScreening?.screening?.warning ?? "The EMI record contains setup and deterministic pre-pass screening only.")} This section does not calculate near fields, far fields, radiated or conducted emissions, antenna performance, or standards compliance. Those claims require a completed compatible field-solver result, calibrated fixtures, applicability limits, and trusted-tool or measured correlation.</p></div></section>` : "";
  const emiField = input.emi?.fieldResult?.far_field;
  const emiAngularSamples = emiField ? emiField.shape[1] * emiField.shape[2] : 0;
  const emiFieldRows = emiField?.frequencies_hz.map((frequencyHz, index) => {
    const maximumLinear = emiField.directivity.maximum_linear[index] ?? null;
    const maximumDbi = maximumLinear && maximumLinear > 0 ? 10 * Math.log10(maximumLinear) : null;
    const magnitudes = emiField.e_field_v_m.magnitude.slice(index * emiAngularSamples, (index + 1) * emiAngularSamples);
    const maximumField = numericMaximum(magnitudes);
    return `<tr><td>${fmt(frequencyHz, 10)}</td><td>${fmt(maximumLinear, 8)}</td><td>${fmt(maximumDbi, 7)}</td><td>${fmt(emiField.radiated_power.total_w[index], 9)}</td><td>${fmt(maximumField, 9)}</td><td>${emiAngularSamples}</td></tr>`;
  }).join("") ?? "";
  const emiPolarSvg = (() => {
    if (!emiField || !emiAngularSamples) return "";
    const phiIndex = emiField.phi_deg.reduce((best, value, index, values) => Math.abs(value) < Math.abs(values[best]) ? index : best, 0);
    const values = emiField.theta_deg.map((angle, thetaIndex) => ({ angle, value: emiField.directivity.linear[thetaIndex * emiField.shape[2] + phiIndex] ?? 0 }));
    const maximum = numericMaximum(values.map(item => item.value)) ?? 0;
    const maximumDb = maximum > 0 ? 10 * Math.log10(maximum) : 0;
    const points = values.map(item => {
      const sampleDb = item.value > 0 ? 10 * Math.log10(item.value) : maximumDb - 40;
      const radius = 12 + 78 * Math.max(0, Math.min(1, (sampleDb - (maximumDb - 40)) / 40));
      const angle = item.angle * Math.PI / 180;
      return `${110 + radius * Math.sin(angle)},${105 - radius * Math.cos(angle)}`;
    }).join(" ");
    return `<svg viewBox="0 0 220 210" role="img" aria-label="OpenEMS directivity cut at phi zero degrees" style="width:100%;max-width:360px;background:#10232b"><g fill="none" stroke="#43606b" stroke-width="1"><circle cx="110" cy="105" r="90"/><circle cx="110" cy="105" r="68"/><circle cx="110" cy="105" r="45"/><circle cx="110" cy="105" r="23"/><line x1="20" y1="105" x2="200" y2="105"/><line x1="110" y1="15" x2="110" y2="195"/></g><polyline points="${points}" fill="rgba(63,190,184,.2)" stroke="#40bfb8" stroke-width="2"/></svg>`;
  })();
  const emiFieldReportHtml = emiField ? `<section id="emi-far-field"><h2>Computed openEMS NF2FF Result</h2><table class="summary-table"><tr><th>Result status</th><td>${html(emiField.status)}</td><th>Validation status</th><td><span class="severity ${statusClass(emiField.validation_status)}">${html(emiField.validation_status.replace(/_/g, " "))}</span></td></tr><tr><th>Observation radius</th><td>${fmt(emiField.radius_m, 7)} m</td><th>Phase center</th><td>${emiField.center_mm.map(value => fmt(value, 7)).join(" / ")} mm</td></tr><tr><th>Angular grid</th><td>${emiField.shape[1]} theta x ${emiField.shape[2]} phi</td><th>Frequencies</th><td>${emiField.shape[0]}</td></tr></table><div style="display:grid;grid-template-columns:minmax(240px,.7fr) minmax(420px,1.3fr);gap:14px;align-items:start">${emiPolarSvg}<table class="data-table"><thead><tr><th>Frequency (Hz)</th><th>Peak D linear</th><th>Peak D (dBi)</th><th>Radiated W</th><th>Peak E (V/m)</th><th>Samples</th></tr></thead><tbody>${emiFieldRows}</tbody></table></div><div class="analytics-note"><b>Far-field validity boundary</b><p>Established: ${html(emiField.validation.established.join("; ") || "solver execution only")}. Required before this board result can be treated as validated: ${html(emiField.validation.required.join("; ") || "independent engineering review")}. A computed NF2FF result is not an EMC compliance certification.</p></div></section>` : "";

  const issueRows = issues.map(issue => `<tr><td><span class="severity ${statusClass(issue.severity)}">${html(issue.severity || "notice")}</span></td><td><code>${html(issue.code || "-")}</code></td><td>${html(issue.message || "-")}</td><td>${html(issue.status || "-")}</td></tr>`).join("");
  const probeRows = input.probes.map(probe => {
    const solved = result?.probes.find(item => item.id === probe.id || probe.id.endsWith(item.id));
    const position = solved?.position_mm ?? probe.position;
    return `<tr><td><b>${html(probe.name)}</b><small class="object-id">${html(probe.id)}</small></td><td>${html(probe.net || solved?.net || "-")}</td><td>${html(probe.layer || solved?.layer || "-")}</td><td>${position ? `${fmt(position[0], 4)}, ${fmt(position[1], 4)}` : "-"}</td><td><span class="severity ${statusClass(solved?.status ?? "not solved")}">${html(solved?.status ?? "not solved")}</span></td><td>${fmt(solved?.voltage_v, 7)}</td><td>${solved?.voltage_drop_v === undefined ? "-" : fmt(solved.voltage_drop_v * 1000, 6)}</td><td>${fmt(solved?.peak_adjacent_current_a, 6)}</td><td>${fmt(solved?.peak_adjacent_current_density_a_mm2, 6)}</td><td>${fmt(solved?.local_series_resistance_ohm, 6)}</td></tr>`;
  }).join("");
  const stackup = (board?.stackup ?? []).map(layer => row(layer.name, layer.type, layer.thickness === undefined ? "-" : `${fmt(layer.thickness, 5)} mm`, layer.material ?? "-", layer.epsilonR ?? "-", layer.lossTangent ?? "-")).join("");
  const anchorLabel = (item: ReportTerminal) => {
    const pad = board?.pads.find(candidate => candidate.id === item.anchorId);
    if (pad) return `${pad.ref ?? "?"}.${pad.name || "?"}`;
    const component = board?.components.find(candidate => candidate.id === item.anchorId);
    return component?.ref ?? (item.anchorId || "Coordinate");
  };
  const waveformLabel = (item: ReportTerminal) => item.profile === "step"
    ? `Step: ${item.profileInitial ?? 0} after ${item.profileDelayS ?? 0} s, rise ${item.profileRiseS ?? 0} s`
    : item.profile === "pulse"
      ? `Pulse: low ${item.profileInitial ?? 0}, delay ${item.profileDelayS ?? 0} s, rise/high/fall ${item.profileRiseS ?? 0}/${item.profileWidthS ?? 0}/${item.profileFallS ?? 0} s, period ${item.profilePeriodS ?? 0} s`
      : item.profile === "piecewise_linear" ? `PWL: ${item.profileData || "not defined"}` : "Constant";
  const terminals = [...setup.sources.map(item => ({ role: "Source", item })), ...setup.loads.map(item => ({ role: "Load", item }))].map(({ role, item }) => `<tr><td><span class="role ${role.toLowerCase()}">${role}</span></td><td><b>${html(item.name)}</b></td><td>${html(item.net || setup.net)}</td><td>${html(item.anchorType || "coordinate")}: <b>${html(anchorLabel(item))}</b><small class="object-id">${html(item.anchorId)}</small></td><td>${fmt(item.x, 4)}, ${fmt(item.y, 4)}</td><td>${html(item.layers.join(" / ") || item.layer || "Auto-connected")}</td><td>${html(item.value)} ${role === "Source" ? "V" : "A"}</td><td>${html(waveformLabel(item))}</td></tr>`).join("");
  const fieldRows = stats.map(item => `<tr><td><b>${html(item.label)}</b></td><td>${item.count.toLocaleString("en-US")}</td><td>${fmt(item.minimum, 7)}</td><td>${fmt(item.mean, 7)}</td><td>${fmt(item.percentile95, 7)}</td><td>${fmt(item.maximum, 7)}</td><td>${html(item.unit)}</td></tr>`).join("");
  const parasiticTable = boundedRows(result?.parasitics ?? []);
  const parasiticRows = parasiticTable.items.map(item => `<tr><td><b>${html(item.net)}</b></td><td>${html(item.model_status || "-")}</td><td>${fmt(item.resistance_ohm, 8)}</td><td>${fmt(item.inductance_h, 8)}</td><td>${item.capacitance_f == null ? "Unsupported" : fmt(item.capacitance_f, 8)}</td><td>${item.conductance_s == null ? "Unsupported" : fmt(item.conductance_s, 8)}</td><td>${html(item.parameter_availability?.capacitance ?? "-")}</td><td>${fmt(item.quality?.maximum_relative_residual, 8)}</td><td>${item.quality?.maximum_sampled_condition_number == null ? "Not sampled" : fmt(item.quality.maximum_sampled_condition_number, 8)}</td><td>${item.impedance?.length ?? 0}</td></tr>`).join("") + (parasiticTable.omitted ? `<tr><td colspan="10">${parasiticTable.omitted.toLocaleString("en-US")} additional extraction rows omitted from this report table.</td></tr>` : "");
  const loopParasiticRows = (result?.loop_parasitics ?? []).map(item => `<tr><td><b>${html(item.name)}</b><small class="object-id">${html(item.id)}</small></td><td>${html(item.forward_nets.join(" + ") || "-")}</td><td>${html(item.return_nets.join(" + ") || "-")}</td><td>${html(item.model_status || "-")}</td><td>${fmt(item.geometry_resistance_ohm, 8)}</td><td>${fmt(item.geometry_loop_inductance_h, 8)}</td><td>${fmt(item.component_resistance_ohm, 8)}</td><td>${fmt(item.component_inductance_h, 8)}</td><td>${item.component_series_capacitance_f == null ? "None" : fmt(item.component_series_capacitance_f, 8)}</td><td>${fmt(item.total_loop_inductance_h, 8)}</td><td>${item.estimated_net_capacitance_f == null ? "Not reported" : `${fmt(item.estimated_net_capacitance_f, 8)} (${html(item.capacitance_model_status)})`}</td><td>${item.impedance?.length ?? 0}</td></tr>`).join("");
  const stressRows = (result?.component_stress ?? []).map(item => row(item.reference, fmt(item.peak_voltage_v), fmt(item.peak_current_a), fmt(item.rms_current_a), fmt(item.peak_power_w), fmt(item.average_power_w), item.status)).join("");
  const graphOptions = [
    ...(result?.time_series.frames.length ? stats.map(item => `<option value="transient:${html(item.key)}" data-unit="${html(item.unit)}">Time history | Peak ${html(item.label)}</option>`) : []),
    ...stats.map(item => `<option value="${html(item.key)}" data-unit="${html(item.unit)}">${html(item.label)}</option>`),
    ...(result?.parasitics ?? []).filter(item => item.impedance?.length).map(item => `<option value="impedance:${html(item.net)}" data-unit="ohm">Impedance | ${html(item.net)}</option>`),
    ...(result?.loop_parasitics ?? []).filter(item => item.impedance?.length).map(item => `<option value="impedance:${html(`Loop | ${item.name}`)}" data-unit="ohm">Power-loop impedance | ${html(item.name)}</option>`),
  ].join("");
  const viewportOptions = `${stats.map(item => `<option value="${html(item.key)}" data-unit="${html(item.unit)}">${html(item.label)}</option>`).join("")}<option value="geometry" data-unit="">Geometry only</option>`;
  const provenanceRows = Object.entries(result?.provenance ?? {}).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).map(([key, value]) => row(key.replace(/_/g, " "), value)).join("");
  const thermalSection = buildThermalReportSection(input.thermal?.scenario);
  const thermalResult = thermalSection.result;
  const resultReady = Boolean(result) || (domain === "thermal" && thermalSection.ready);
  const displayedStatus = domain === "thermal" && Object.keys(thermalResult).length ? thermalResult.status : result?.status;
  const displayedModelStatus = domain === "thermal" && Object.keys(thermalResult).length ? thermalResult.model_status : result?.model_status;
  const transientDefinition = input.analysisMode === "Transient PI" || result?.mode === "transient"
    ? `<tr><th>Transient window</th><td>${html(`${setup.transientStopS ?? "-"} s stop | ${setup.transientTimeStepS ?? "-"} s integration step`)}</td><th>Saved output</th><td>${html(`Every ${setup.transientOutputDecimation ?? "-"} steps | ${setup.transientPlaybackFps ?? "-"} FPS | ${setup.transientInitialCondition ?? "-"} initial state`)}</td></tr>`
    : "";
  const transientQuality = transientMode
    ? `<tr><th>Inductance passivity correction</th><td>${passivityCorrection === null ? "-" : `${fmt(passivityCorrection * 100, 5)}%`}</td><th>Maximum scaled residual</th><td>${scaledResidual === null ? "-" : fmt(scaledResidual, 8)}</td></tr>`
    : "";
  const siChannelResult = record(input.si?.channelResult);
  const summary = domain === "thermal" ? thermalSection.summary : result?.summary ?? {};
  const thermalNumericalNote = domain === "thermal" ? thermalSection.numericalNote : "";
  const thermalReportHtml = domain === "thermal" ? thermalSection.sectionHtml : "";
  const siReportHtml = domain === "si" ? (() => {
    if (siChannelResult.contract === "spike/si-workflow-result/v1") {
      const time = record(siChannelResult.time_domain);
      const receivers = Array.isArray(time.receivers) ? time.receivers.map(record) : [];
      const checks = record(record(siChannelResult.network).checks);
      const limitations = Array.isArray(siChannelResult.limitations) ? siChannelResult.limitations : [];
      const warnings = Array.isArray(siChannelResult.warnings) ? siChannelResult.warnings : [];
      return `<section id="si-results"><h2>Loaded Signal-Integrity Study</h2><p>Experimental linear model. Production qualification: false. Compliance: not evaluated.</p><p>Time domain: ${html(String(time.status ?? "not returned"))}. ${html(String(time.reason ?? ""))} Passivity: ${html(String(record(checks.passivity).status ?? "not evaluated"))}. Reciprocity: ${html(String(record(checks.reciprocity).status ?? "not evaluated"))}.</p><table class="summary-table"><tr><th>Receiver port</th><th>Eye height (V)</th><th>High margin (V)</th><th>Low margin (V)</th></tr>${receivers.map(rx => `<tr><td>${html(String(Number(rx.port) + 1))}</td><td>${html(String(rx.eye_height_v))}</td><td>${html(String(rx.high_margin_v))}</td><td>${html(String(rx.low_margin_v))}</td></tr>`).join("")}</table><h3>Noise scope and results</h3><pre>${html(JSON.stringify(siChannelResult.noise, null, 2))}</pre><h3>Passive models and effective values</h3><pre>${html(JSON.stringify(siChannelResult.passives, null, 2))}</pre><h3>Assumptions and limits</h3><ul>${[...warnings, ...limitations].map(v => `<li>${html(String(v))}</li>`).join("")}</ul><p>Setup digest: ${html(String(siChannelResult.request_sha256 ?? ""))}. Full traces and Touchstone are retained with the study and can be exported from the source-to-receiver workbench.</p></section>`;
    }
    const extraction = record(siChannelResult.extraction);
    const eye = record(siChannelResult.eye);
    const pam4 = record(eye.pam4);
    const zOhm = reportNumber(extraction, "lossless_characteristic_impedance_ohm", "characteristic_impedance_ohm", "impedance_ohm");
    const insertionDb = reportNumber(summary, "insertion_loss_db", "sdd21_db", "s21_db");
    const returnDb = reportNumber(summary, "return_loss_db", "sdd11_db", "s11_db");
    const eyeMv = reportNumber(summary, "eye_height_mv", "minimum_eye_height_mv");
    const eyeNormalized = reportNumber(eye, "eye_height_normalized");
    const jitterPs = reportNumber(summary, "total_jitter_ps", "jitter_ps");
    const ber = reportNumber(summary, "ber", "ber_proxy") ?? reportNumber(pam4, "worst_ber_proxy");
    const compliance = String(siChannelResult.compliance_status ?? "not_evaluated");
    const qualification = String(siChannelResult.model_status ?? "not_qualified");
    return `<section id="si-results"><h2>Signal-Integrity Channel Result</h2><table class="summary-table"><tr><th>Characteristic impedance</th><td>${zOhm === null ? "Not returned" : `${fmt(zOhm, 7)} ohm`}</td><th>Insertion / return loss</th><td>${insertionDb === null ? "Not returned" : `${fmt(insertionDb, 6)} dB`} / ${returnDb === null ? "Not returned" : `${fmt(returnDb, 6)} dB`}</td></tr><tr><th>Eye height</th><td>${eyeMv !== null ? `${fmt(eyeMv, 6)} mV` : eyeNormalized !== null ? `${fmt(eyeNormalized, 6)} normalized` : "Not returned"}</td><th>Jitter / BER</th><td>${jitterPs === null ? "Not returned" : `${fmt(jitterPs, 6)} ps`} / ${ber === null ? "Not returned" : `${fmt(ber, 6)} proxy`}</td></tr><tr><th>Model / compliance</th><td colspan="3"><span class="severity ${statusClass(qualification)}">${html(qualification)}</span> ${html(compliance)}</td></tr></table><h3>Channel evidence</h3><p>Use the channel/eye/S-parameter/TDR graph selectors below for returned traces. Protocol compliance, IBIS-AMI behavior, rare-event BER, CDR and equalization remain unavailable unless explicitly supplied by a qualified adapter and marked in provenance.</p></section>`;
  })() : "";
  const piReportHtml = domain === "pi" ? `<section id="pi-results"><h2>Power-Integrity Result</h2><table class="summary-table"><tr><th>Worst rail drop</th><td>${maxDrop === null ? "Not returned" : `${fmt(maxDrop * 1000, 7)} mV`}</td><th>Peak current density</th><td>${maxDensity === null ? "Not returned" : `${fmt(maxDensity, 7)} A/mm2`}</td></tr><tr><th>Conductor loss</th><td>${totalLoss === null ? "Not returned" : `${fmt(totalLoss, 7)} W`}</td><th>PDN review</th><td>${pdnReview ? `${fmt(pdnReview.maximum_impedance_ohm, 8)} ohm maximum / ${pdnReview.violation_count} violation samples` : "Not attached"}</td></tr></table><div class="analytics-note"><b>PI scope</b><p>DC, AC/PDN, transient and circuit quantities retain their returned model status. The report does not convert approximate, partial, or unvalidated results into a signoff claim.</p></div></section>` : "";

  const netTabs = netRecords.length > 1
    ? `<div class="net-tabs" role="tablist" aria-label="Analyzed nets">${netRecords.map((item, index) => `<button type="button" role="tab" data-net-tab="net-${index}" aria-selected="${index === 0}">${html(item.label || `Net ${index + 1}`)}</button>`).join("")}</div>`
    : "";
  const netPanels = netRecords.map((item, index) => {
    const bundle = item.bundle;
    const bundleStats = fieldStats(bundle);
    const bundleSummary = resultSolvedForPresentation(bundle) ? bundle.summary ?? {} : {};
    const bundleNet = String(bundleSummary.net ?? bundleSummary.scope ?? item.label ?? setup.net ?? `Net ${index + 1}`);
    const bundleDrop = reportNumber(bundleSummary, "max_voltage_drop_v", "maximum_voltage_drop_v");
    const bundleDensity = reportNumber(bundleSummary, "max_current_density_a_mm2", "peak_current_density_a_mm2");
    const bundleLoss = reportNumber(bundleSummary, "total_copper_loss_w", "conductor_loss_w", "peak_copper_loss_w");
    const bundleRuntime = reportNumber(bundleSummary, "solver_time_s", "runtime_s");
    const previewRows = bundleStats.map(stat => `<tr><td>${html(stat.label)}</td><td>${stat.count.toLocaleString("en-US")}</td><td>${fmt(stat.minimum, 7)}</td><td>${fmt(stat.maximum, 7)}</td><td>${html(stat.unit)}</td></tr>`).join("");
    const previewPlots = Object.entries(bundle.scalar_fields).filter(([, samples]) => samples.length).slice(0, 3).map(([key, samples]) => {
      const definition = fieldDefinitions[key] ?? { label: key.replace(/_/g, " "), unit: "" };
      return reportSparklineSvg(samples, definition.label, definition.unit);
    }).join("");
    return `<article class="net-panel" role="tabpanel" data-net-panel="net-${index}"${index ? " hidden" : ""}><header><div><span>Analyzed net or scope</span><h3>${html(bundleNet)}</h3></div><div><span class="severity ${statusClass(`${bundle.status} ${bundle.model_status}`)}">${html(bundle.model_status)}</span><code>${html(bundle.analysis_id)}</code></div></header><div class="net-kpis"><div><span>Maximum drop</span><b>${bundleDrop === null ? "Not returned" : `${fmt(bundleDrop * 1000, 6)} mV`}</b></div><div><span>Peak density</span><b>${bundleDensity === null ? "Not returned" : `${fmt(bundleDensity, 6)} A/mm2`}</b></div><div><span>Conductor loss</span><b>${bundleLoss === null ? "Not returned" : `${fmt(bundleLoss, 7)} W`}</b></div><div><span>Runtime</span><b>${bundleRuntime === null ? "Not returned" : `${fmt(bundleRuntime, 6)} s`}</b></div></div><div class="net-plots">${previewPlots || "<div class='empty-result'>No returned scalar field is available for a static plot.</div>"}</div><table class="data-table"><thead><tr><th>Returned field</th><th>Samples</th><th>Minimum</th><th>Maximum</th><th>Unit</th></tr></thead><tbody>${previewRows || "<tr><td colspan='5'>This solver result contains no scalar preview fields.</td></tr>"}</tbody></table><details><summary>Solver provenance for ${html(bundleNet)}</summary><pre>${html(JSON.stringify(bundle.provenance, null, 2))}</pre></details></article>`;
  }).join("");
  const netReviewHtml = netRecords.length ? `<section id="net-review" class="page-break"><h2>${html(domainLabels[domain])} Results by Net</h2><p class="section-intro">Choose a net for screen review. Print and PDF output includes every net below in order, with its exact result identity, model status, returned values, and solver provenance.</p>${netTabs}<div class="net-panels">${netPanels}</div></section>` : "";
  const includeEmi = domain === "emi";

  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'"><title>${html(input.projectName)} | SPIKE Engineering Report</title><style>
  .analytics-breakdowns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.analytics-note{margin-top:14px;padding:12px 15px;border-left:4px solid var(--cyan);background:#edf6f8;color:#405860}.analytics-note b{display:block;margin-bottom:6px}.formula-list{margin:0;padding-left:20px}.formula-list li{margin:4px 0}@media(max-width:900px){.analytics-breakdowns{grid-template-columns:1fr}}
  section{content-visibility:auto;contain-intrinsic-size:1px 420px}
  :root{color-scheme:light;--ink:#17272f;--muted:#647982;--line:#cfd9dd;--soft:#eef3f4;--paper:#fff;--brand:#d99a32;--brand-dark:#80520c;--green:#18825c;--amber:#aa6a08;--red:#b53d3d;--cyan:#237d94}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#e9eef0;color:var(--ink);font:13px/1.45 Arial,sans-serif;letter-spacing:0}.report-header{background:#13252d;color:#fff;border-bottom:5px solid var(--brand)}.header-inner,.report-nav,.report-main,.footer-inner{width:min(1480px,calc(100% - 40px));margin:auto}.header-inner{min-height:118px;display:grid;grid-template-columns:1fr auto;align-items:center;gap:24px}.brand-line{display:flex;align-items:center;gap:14px}.brand-mark{width:44px;height:44px;display:grid;place-items:center;border:1px solid #52717c;color:#f3b548;font:bold 17px monospace}.eyebrow{color:#80a9b7;text-transform:uppercase;font-size:10px;font-weight:bold}.report-header h1{font-size:26px;margin:2px 0 0}.report-header p{margin:3px 0;color:#b9cbd1}.identity{text-align:right}.identity code{display:block;color:#f3b548;font-size:12px}.identity span{display:block;color:#9fb6be;font-size:11px;margin-top:4px}.header-actions{display:flex;justify-content:flex-end;gap:7px;margin-top:12px}button,select{font:inherit}.header-actions button,.view-toolbar button{border:1px solid #67808a;background:#1a323c;color:#e7f0f2;padding:7px 10px;cursor:pointer}.header-actions button:hover,.view-toolbar button:hover,.view-toolbar button.active{background:var(--brand);border-color:var(--brand);color:#172127}.report-nav{display:flex;gap:2px;overflow:auto}.report-nav a{color:#c9d8dc;text-decoration:none;padding:10px 12px;border-bottom:2px solid transparent;white-space:nowrap;font-size:11px;text-transform:uppercase;font-weight:bold}.report-nav a:hover{color:#fff;border-color:var(--brand)}.report-main{background:var(--paper);padding:26px 30px 54px;box-shadow:0 1px 8px #70808840}.status-banner{display:flex;align-items:center;justify-content:space-between;gap:20px;border-left:5px solid var(--brand);background:#fff6e5;padding:12px 15px;margin-bottom:22px}.status-banner.pass{border-color:var(--green);background:#eaf7f1}.status-banner.fail{border-color:var(--red);background:#fff0ef}.status-banner b{text-transform:uppercase}.status-banner span{color:#596c74}section{scroll-margin-top:12px;margin:0 0 34px}h2{font-size:18px;margin:0 0 14px;border-bottom:2px solid var(--brand);padding-bottom:7px}h3{font-size:13px;margin:20px 0 8px;text-transform:uppercase;color:#3b555f}.section-intro{color:var(--muted);max-width:880px}.summary-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);gap:22px}.metrics{display:grid;grid-template-columns:repeat(3,minmax(120px,1fr));border:1px solid var(--line)}.metric{min-height:82px;padding:14px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:#f8fafb}.metric:nth-child(3n){border-right:0}.metric:nth-last-child(-n+3){border-bottom:0}.metric span{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;font-weight:bold}.metric strong{display:block;font-size:19px;margin-top:8px}.metric.limit{background:#fff0ef}.metric.limit strong{color:var(--red)}.summary-table,.data-table{width:100%;border-collapse:collapse}.summary-table th,.summary-table td,.data-table th,.data-table td{border:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top}.summary-table th,.data-table th{background:#e8eef0;font-size:10px;text-transform:uppercase;color:#3b515a}.summary-table th{width:145px}.data-table tbody tr:nth-child(even){background:#f7f9fa}.data-table tbody tr:hover{background:#fff5e4}.severity,.role{display:inline-block;padding:2px 6px;border-left:3px solid var(--amber);background:#fff3dc;color:#704500;text-transform:uppercase;font:bold 9px Arial}.severity.pass{border-color:var(--green);background:#e5f5ee;color:#0e6949}.severity.fail{border-color:var(--red);background:#feeceb;color:#8c2929}.role.source{border-color:#368dcc;background:#eaf5fb;color:#176184}.role.load{border-color:#b86723;background:#fff0e2;color:#7d3e0b}.net-tabs{display:flex;gap:6px;overflow:auto;margin:14px 0 -1px}.net-tabs button{border:1px solid var(--line);border-bottom:3px solid transparent;background:#edf2f3;color:#344b54;padding:9px 15px;cursor:pointer;white-space:nowrap}.net-tabs button.active{background:#fff;border-bottom-color:var(--brand);font-weight:bold}.net-panel{border:1px solid var(--line);padding:16px;background:linear-gradient(135deg,#fff,#f7fafb)}.net-panel[hidden]{display:none}.net-panel>header{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;margin-bottom:12px}.net-panel>header span{font-size:10px;text-transform:uppercase;color:var(--muted)}.net-panel>header h3{margin:2px 0;color:var(--ink);font-size:18px}.net-panel>header code{display:block;margin-top:5px}.net-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}.net-kpis>div{padding:11px;background:#eaf1f3;border-top:3px solid var(--cyan)}.net-kpis span,.net-kpis b{display:block}.net-kpis span{font-size:9px;text-transform:uppercase;color:var(--muted)}.net-kpis b{margin-top:4px;font-size:15px}.object-id{display:block;max-width:230px;overflow:hidden;text-overflow:ellipsis;color:#82939a;font:9px monospace;margin-top:2px}code{font:11px ui-monospace,Consolas,monospace}.visual-shell{border:1px solid #334c56;background:#101a20}.view-toolbar{min-height:46px;display:flex;align-items:center;gap:6px;padding:7px 9px;border-bottom:1px solid #334c56;color:#c4d4d9}.view-toolbar select{height:31px;min-width:190px;background:#162932;color:#e5eff2;border:1px solid #48636d;padding:0 8px}.view-toolbar .spacer{flex:1}.view-toolbar small{color:#8fa7af}.canvas-wrap{position:relative;height:520px}.canvas-wrap canvas{display:block;width:100%;height:100%;touch-action:none}.colorbar{position:absolute;left:18px;bottom:16px;width:min(360px,55%);padding:8px;background:#0d171dd9;color:#dce7ea;border:1px solid #425c66}.color-gradient{height:8px;background:linear-gradient(90deg,#4a8df6,#3bc9db,#4dd4ac,#d8df58,#ffb84a,#ef6158)}.color-labels{display:flex;justify-content:space-between;font:9px monospace;margin-top:4px}.viewport-tooltip{position:absolute;z-index:4;width:210px;padding:8px;background:#0d1d24e8;color:#e7f0f2;border-left:3px solid var(--brand);font:10px/1.45 ui-monospace,Consolas,monospace;pointer-events:none}.plotly-shell{border:1px solid #334c56;background:#101a20}.plotly-field{height:540px}.graph-shell{position:relative;border:1px solid var(--line);padding:10px}.graph-tools{display:flex;align-items:center;gap:10px;margin-bottom:8px}.graph-tools select{height:32px;min-width:280px;border:1px solid #879ca4;background:#fff;padding:0 8px}.graph-wrap{height:340px;position:relative}.graph-wrap canvas{width:100%;height:100%;display:block}.graph-tooltip{position:absolute;z-index:2;width:195px;background:#10232bdc;color:#fff;padding:8px;border-left:3px solid var(--brand);pointer-events:none}.graph-tooltip b,.graph-tooltip span,.graph-tooltip small{display:block}.graph-tooltip span{color:#f1bd5e;margin:3px 0}.graph-tooltip small{color:#b9cbd1}.empty-result{padding:22px;border:1px dashed #9aabb2;background:#f5f7f8;color:#5f7179}.trace-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.trace-box{border:1px solid var(--line);padding:12px}.trace-box h3{margin-top:0}.trace-box dl{display:grid;grid-template-columns:155px 1fr;margin:0}.trace-box dt,.trace-box dd{padding:5px 0;border-bottom:1px solid #e3e9eb}.trace-box dt{color:var(--muted)}.trace-box dd{margin:0;font-family:ui-monospace,Consolas,monospace;overflow-wrap:anywhere}details{border:1px solid var(--line);margin-top:10px}summary{cursor:pointer;padding:9px 11px;background:#eef3f4;font-weight:bold}pre{max-height:360px;overflow:auto;margin:0;padding:12px;background:#17272f;color:#d9e7eb;font:10px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.report-footer{background:#13252d;color:#9eb3ba;border-top:3px solid var(--brand)}.footer-inner{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:20px}.footer-inner b{color:#e4eef1}.print-header{display:none}.nowrap{white-space:nowrap}@media(max-width:900px){.header-inner,.report-nav,.report-main,.footer-inner{width:100%}.header-inner{padding:18px;grid-template-columns:1fr}.identity{text-align:left}.header-actions{justify-content:flex-start}.report-main{padding:20px 14px}.summary-grid,.trace-grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.metric:nth-child(n){border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.net-kpis{grid-template-columns:repeat(2,1fr)}.canvas-wrap{height:430px}.plotly-field{height:440px}.view-toolbar{flex-wrap:wrap}.view-toolbar .spacer{display:none}.data-table{display:block;overflow:auto}}@page{size:A4 landscape;margin:15mm 10mm 18mm}@media print{body{background:#fff;font-size:9px}.report-header,.report-nav,.header-actions,.view-toolbar,.report-footer,.net-tabs{display:none}.print-header{display:flex;position:fixed;left:0;right:0;top:-11mm;justify-content:space-between;border-bottom:1px solid #5c7078;padding-bottom:2mm;font-size:8px}.report-main{width:100%;padding:0;box-shadow:none}.canvas-wrap{height:115mm}.plotly-field{height:115mm}.graph-wrap{height:82mm}.summary-grid{grid-template-columns:1.1fr .9fr}.metrics{grid-template-columns:repeat(3,1fr)}section{break-inside:avoid;margin-bottom:7mm}.net-panel,.net-panel[hidden]{display:block!important;break-before:page;break-inside:auto}.net-kpis{grid-template-columns:repeat(4,1fr)}.page-break{break-before:page}h2{font-size:13px;margin-bottom:3mm}.data-table th,.data-table td,.summary-table th,.summary-table td{padding:4px}.fixed-print-footer{display:flex!important;position:fixed;bottom:-13mm;left:0;right:0;border-top:1px solid #5c7078;justify-content:space-between;padding-top:2mm;font-size:8px;color:#52646b}.graph-tooltip,.viewport-tooltip{display:none}}
  </style><style>.net-plots{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}.net-plot{margin:0;padding:10px;border:1px solid var(--line);background:#fff}.net-plot figcaption{display:flex;justify-content:space-between;font-weight:bold}.net-plot figcaption span,.net-plot small{color:var(--muted);font-size:9px}.net-plot svg{display:block;width:100%;height:125px}@media(max-width:900px){.net-plots{grid-template-columns:1fr}}@media print{.net-plots{grid-template-columns:repeat(3,1fr)}.net-plot svg{height:32mm}}</style></head><body><div class="print-header"><b>SPIKE ${html(domainLabels[domain])} Report | ${html(input.projectName)}</b><span>${html(reportId)}</span></div><header class="report-header"><div class="header-inner"><div><div class="brand-line"><div class="brand-mark">SPI</div><div><div class="eyebrow">Multiphysics Electronics Workbench</div><h1>${html(domainLabels[domain])} Engineering Report</h1><p>${html(input.projectName)} | ${html(input.boardFile)}</p></div></div></div><div class="identity"><code>${html(reportId)}</code><span>Generated ${html(generated)}</span><span>SPIKE v${html(APP_VERSION)} | Offline self-contained report</span><div class="header-actions"><button id="download-evidence">Export evidence JSON</button><button id="print-report">Print / Save PDF</button></div></div></div><nav class="report-nav"><a href="#summary">Summary</a><a href="${domain === "emi" ? "#emi-workflow" : `#${domain}-results`}">${domain.toUpperCase()}</a>${netRecords.length ? `<a href="#net-review">Nets</a>` : ""}${domain === "pi" ? `<a href="#analytics">Analytics</a><a href="#engineering-analytics">Limits</a>${sourceLoadHtml ? `<a href="#source-load">Terminals</a>` : ""}${pdnReview ? `<a href="#pdn-review">PDN</a>` : ""}` : ""}${includeEmi && emiSetup ? `<a href="#emi-workflow">EMI</a>` : ""}<a href="#visualization">Visualization</a><a href="#graphs">Graphs</a>${domain === "pi" ? `<a href="#probes">Probes</a><a href="#definition">Setup</a>` : ""}<a href="#results">Results</a><a href="#validity">Warnings</a><a href="#traceability">Traceability</a></nav></header><main class="report-main">
  <div class="status-banner ${statusClass(`${displayedStatus ?? "not run"} ${displayedModelStatus ?? "unsupported"}`)}"><div><b>${html(displayedStatus ?? "Analysis not run")}</b><span> | ${html(displayedModelStatus ?? "No numerical model result is attached")}</span></div><span>${resultReady ? "Values below are reproduced from the attached solver result." : "This is a setup and design record. Run an analysis to populate numerical results and overlays."}</span></div>
  <section id="summary"><h2>Result Summary</h2><div class="summary-grid"><div class="metrics">${metricCards}${failedNotice}</div><table class="summary-table"><tr><th>Analysis</th><td>${html(result?.mode ?? input.analysisMode)}</td></tr><tr><th>Result status</th><td><span class="severity ${statusClass(result?.status ?? "not run")}">${html(result?.status ?? "not run")}</span></td></tr><tr><th>Model status</th><td><span class="severity ${statusClass(result?.model_status ?? "unsupported")}">${html(result?.model_status ?? "unsupported")}</span></td></tr><tr><th>Solver</th><td>${html(solver)}</td></tr><tr><th>Analysis ID</th><td><code>${html(result?.analysis_id || "Not assigned")}</code></td></tr><tr><th>Warnings / errors</th><td>${issues.filter(item => /warn/i.test(item.severity ?? "")).length} / ${issues.filter(item => /error|fail/i.test(item.severity ?? "")).length}</td></tr>${transientQuality}</table></div></section>
  ${thermalReportHtml}${siReportHtml}${piReportHtml}
  ${netReviewHtml}
  ${domain === "pi" ? `<section id="analytics"><h2>Power and System Analytics</h2><table class="summary-table"><tr><th>Analyzed scopes</th><td>${analytics.rows.length}</td><th>Combined load current</th><td>${analytics.totalLoadCurrentA === null ? "-" : `${fmt(analytics.totalLoadCurrentA, 7)} A`}</td></tr><tr><th>Analyzed conductor loss</th><td>${analytics.totalConductorLossW === null ? "-" : `${fmt(analytics.totalConductorLossW, 8)} W`}</td><th>Estimated delivered power</th><td>${analytics.totalDeliveredPowerW === null ? "-" : `${fmt(analytics.totalDeliveredPowerW, 8)} W`}</td></tr><tr><th>Worst voltage drop</th><td>${analytics.worstDropV === null ? "-" : `${fmt(analytics.worstDropV * 1000, 7)} mV`}</td><th>Peak current density</th><td>${analytics.peakCurrentDensityAMm2 === null ? "-" : `${fmt(analytics.peakCurrentDensityAMm2, 7)} A/mm2`}</td></tr><tr><th>Combined solver time</th><td>${analytics.totalSolverTimeS === null ? "-" : `${fmt(analytics.totalSolverTimeS, 6)} s`}</td><th>Conduction efficiency</th><td>${analytics.conductionEfficiencyPercent === null ? "-" : `${fmt(analytics.conductionEfficiencyPercent, 6)}%`}</td></tr></table><h3>Per analyzed net or scope</h3><table class="data-table"><thead><tr><th>Scope</th><th>Mode</th><th>Model</th><th>Source V</th><th>Load A</th><th>Drop mV</th><th>Drop %</th><th>Loss W</th><th>Source W</th><th>Delivered W</th><th>Efficiency %</th><th>Effective R</th><th>Peak J</th><th>Nodes</th><th>Runtime s</th></tr></thead><tbody>${analyticsRows || "<tr><td colspan='15'>No solved analysis is attached.</td></tr>"}</tbody></table><h3>Power-loss allocation</h3><div class="analytics-breakdowns"><div><b>By net</b><table class="data-table"><thead><tr><th>Net</th><th>Loss W</th><th>Share</th></tr></thead><tbody>${netLossRows || "<tr><td colspan='3'>Solver did not publish a per-net breakdown.</td></tr>"}</tbody></table></div><div><b>By layer</b><table class="data-table"><thead><tr><th>Layer</th><th>Loss W</th><th>Share</th></tr></thead><tbody>${layerLossRows || "<tr><td colspan='3'>Solver did not publish a per-layer breakdown.</td></tr>"}</tbody></table></div><div><b>By conductor element</b><table class="data-table"><thead><tr><th>Element</th><th>Loss W</th><th>Share</th></tr></thead><tbody>${geometryLossRows || "<tr><td colspan='3'>Solver did not publish an element breakdown.</td></tr>"}</tbody></table></div></div><div class="analytics-note"><b>Equations and scope</b><ul class="formula-list"><li>Conductor loss: P_loss = sum over solved branches of I_k^2 R_k.</li><li>Source power estimate: P_source = V_source x sum(I_load).</li><li>Delivered power estimate: P_delivered = P_source - P_loss.</li><li>Conduction efficiency: eta = 100 x P_delivered / P_source.</li><li>Effective resistance: R_effective = P_loss / I_load^2. Drop percentage = 100 x maximum drop / source voltage.</li></ul><p>Totals aggregate the latest result for each reported mode and scope. They include only analyzed conductor elements returned by the solver. Visualization samples may be decimated; totals come from solver-owned summaries.</p></div></section>${engineeringAnalyticsHtml}${sourceLoadHtml}${pdnReviewHtml}` : ""}
  ${includeEmi ? `${emiReportHtml}${emiFieldReportHtml}` : ""}
  <section id="visualization"><h2>Interactive Board and Result Visualization</h2><div class="visual-shell"><div class="view-toolbar"><button class="active" data-board-view="2d">2D layout</button><button data-board-view="3d">3D geometry</button><button class="active" data-field-display="raw">Raw samples</button><button data-field-display="smooth">Smooth field</button><button data-field-display="contour">3D contour</button><select id="viewport-metric" aria-label="Viewport result field">${viewportOptions}</select><div class="spacer"></div><small id="interaction-hint">Drag pan | Wheel zoom | Double-click fit</small></div><div class="canvas-wrap"><canvas id="board-canvas" aria-label="Interactive board result visualization"></canvas><div id="viewport-tooltip" class="viewport-tooltip" hidden></div><div class="colorbar" id="viewport-colorbar" hidden><div class="color-gradient"></div><div class="color-labels"><span id="color-min">-</span><b id="color-unit"></b><span id="color-max">-</span></div></div></div></div><p class="object-id">Report geometry and field samples are deterministically bounded for responsive display; numerical tables, summaries, and exported evidence remain authoritative. The optional 3D contour is a display-only interpolation grouped by solved net and copper layer.</p></section>
  <section id="graphs"><h2>Interactive Result Graphs</h2>${graphOptions ? `<div class="graph-shell"><div class="graph-tools"><label for="graph-series"><b>Series</b></label><select id="graph-series">${graphOptions}</select><span>Move over the graph for exact sample values.</span></div><div class="graph-wrap"><canvas id="result-chart"></canvas><div id="graph-tooltip" class="graph-tooltip" hidden></div></div></div>` : `<div class="empty-result">No scalar fields or impedance sweeps are available. Run a compatible solver to populate this section.</div><div hidden><select id="graph-series"></select><canvas id="result-chart"></canvas><div id="graph-tooltip"></div></div>`}</section>
  ${domain === "pi" ? `<section id="probes"><h2>Probe Table</h2><table class="data-table"><thead><tr><th>Probe</th><th>Net</th><th>Layer</th><th>Coordinate (mm)</th><th>Status</th><th>Voltage (V)</th><th>Drop (mV)</th><th>Current (A)</th><th>Density (A/mm2)</th><th>Local R (ohm)</th></tr></thead><tbody>${probeRows || "<tr><td colspan='10'>No probes are placed. Add probes in the viewport and rerun the analysis.</td></tr>"}</tbody></table></section><section id="definition"><h2>Power-Integrity Analysis Definition</h2><table class="summary-table"><tr><th>Design source</th><td>${html(input.boardFile)}</td><th>Power net</th><td>${html(setup.net || "-")}</td></tr><tr><th>Return path</th><td>${html(`${setup.returnPath.mode}: ${setup.returnPath.net || "not assigned"}`)}</td><th>Mesh</th><td>${html(`${setup.meshDimension}, target ${setup.meshTargetMm} mm, zone ${setup.zoneCellMm} mm`)}</td></tr><tr><th>Via model</th><td>${html(`${setup.viaModel}, plating ${setup.viaPlatingMm} mm`)}</td><th>Frequency sweep</th><td>${html(`${setup.frequencyStart} to ${setup.frequencyStop} Hz | ${setup.frequencyPoints} points`)}</td></tr>${transientDefinition}<tr><th>Limits</th><td colspan="3">${html(`${input.limits.drop} mV maximum drop | ${input.limits.density} A/mm2 maximum current density`)}</td></tr></table><h3>Sources and loads</h3><table class="data-table"><thead><tr><th>Role</th><th>Name</th><th>Net</th><th>Anchor</th><th>Coordinate (mm)</th><th>Connected layers</th><th>Value</th><th>Waveform</th></tr></thead><tbody>${terminals || "<tr><td colspan='8'>No terminals configured.</td></tr>"}</tbody></table></section>` : ""}
  <section><h2>Design and Stackup</h2><table class="summary-table"><tr><th>Board size</th><td>${html(board ? `${board.width.toFixed(3)} x ${board.height.toFixed(3)} mm` : "-")}</td><th>Copper layers</th><td>${board?.layers.length ?? 0}</td></tr><tr><th>Components / nets</th><td>${board?.components.length ?? 0} / ${board ? new Set(Object.values(board.nets)).size : 0}</td><th>3D assignments</th><td>${input.modelAssignmentCount}</td></tr><tr><th>Tracks / vias / pads / zones</th><td colspan="3">${board?.tracks.length ?? 0} / ${board?.vias.length ?? 0} / ${board?.pads.length ?? 0} / ${board?.zones.length ?? 0}</td></tr></table><table class="data-table"><thead><tr><th>Layer</th><th>Type</th><th>Thickness</th><th>Material</th><th>Er</th><th>Loss tangent</th></tr></thead><tbody>${stackup || "<tr><td colspan='6'>No stackup imported.</td></tr>"}</tbody></table></section>
  <section id="results" class="page-break"><h2>Numerical Results</h2>${domain === "thermal" ? thermalNumericalNote : resultReady ? `<table class="data-table"><thead><tr><th>Field</th><th>Samples</th><th>Minimum</th><th>Mean</th><th>95th percentile</th><th>Maximum</th><th>Unit</th></tr></thead><tbody>${fieldRows || "<tr><td colspan='7'>The solver returned no scalar fields.</td></tr>"}</tbody></table><h3>RLCG and impedance extraction</h3><table class="data-table"><thead><tr><th>Net</th><th>Model status</th><th>R (ohm)</th><th>L (H)</th><th>C (F)</th><th>G (S)</th><th>C fidelity</th><th>Residual</th><th>Condition</th><th>Z(f) points</th></tr></thead><tbody>${parasiticRows || "<tr><td colspan='10'>No parasitic result was produced.</td></tr>"}</tbody></table><h3>Power-loop parasitics</h3><table class="data-table"><thead><tr><th>Loop</th><th>Forward nets</th><th>Return nets</th><th>Model status</th><th>Geometry R (ohm)</th><th>Geometry loop L (H)</th><th>Component R (ohm)</th><th>Component L (H)</th><th>Component series C (F)</th><th>Total loop L (H)</th><th>Estimated net C (F)</th><th>Z(f) points</th></tr></thead><tbody>${loopParasiticRows || "<tr><td colspan='12'>No power-loop parasitic result was produced.</td></tr>"}</tbody></table><p class="object-id">Loop inductance retains solved forward/return coupling. Component R/L/C values are declared model contributions. The listed net capacitance is an estimate and not a validated multiconductor capacitance matrix.</p><h3>Component electrical stress</h3><table class="data-table"><thead><tr><th>Reference</th><th>Peak V</th><th>Peak A</th><th>RMS A</th><th>Peak W</th><th>Average W</th><th>Status</th></tr></thead><tbody>${stressRows || "<tr><td colspan='7'>No component stress bindings were supplied to the circuit solver.</td></tr>"}</tbody></table>` : `<div class="empty-result"><b>No numerical result is attached.</b><br>This report records the imported design and configured analysis only. Numerical fields, mesh results, parasitics, stress values, and probe measurements remain intentionally blank.</div>`}</section>
  <section id="validity"><h2>Warnings, Limits, and Validity</h2><p>Approximate, unsupported, failed-to-converge, and out-of-validity conditions remain visible and are never promoted to validated results.</p><table class="data-table"><thead><tr><th>Severity</th><th>Code</th><th>Message</th><th>Status</th></tr></thead><tbody>${issueRows || `<tr><td colspan="4">${resultReady ? "No result issues were recorded." : "No solver result is attached; numerical validity has not been established."}</td></tr>`}</tbody></table></section>
  <section id="traceability"><h2>Traceability and Reproducibility</h2><div class="trace-grid"><div class="trace-box"><h3>Result identity</h3><dl><dt>Report ID</dt><dd>${html(reportId)}</dd><dt>Result contract</dt><dd>${html(result?.contract ?? "Not available")}</dd><dt>Analysis ID</dt><dd>${html(result?.analysis_id ?? "Not available")}</dd><dt>Project fingerprint</dt><dd>${html(fnv1a(projectFingerprintInput(input.projectPayload)))}</dd><dt>Geometry fingerprint</dt><dd>${html(fnv1a(geometryFingerprintInput(board)))}</dd><dt>Result fingerprint</dt><dd>${html(result ? fnv1a(resultFingerprintInput(result)) : "Not available")}</dd></dl></div><div class="trace-box"><h3>Solver provenance</h3><table class="summary-table">${provenanceRows || "<tr><th>Status</th><td>No solver result</td></tr>"}</table></div></div><details><summary>Structured solver provenance</summary><pre>${html(JSON.stringify(result?.provenance ?? { status: "No solver result" }, null, 2))}</pre></details><details><summary>Compact reproducibility evidence</summary><pre>${html(JSON.stringify(evidence, null, 2))}</pre></details></section>
  </main><footer class="report-footer"><div class="footer-inner"><div><b>SPIKE Engineering Analysis Report</b><br>Numerical claims remain subject to the stated model status and validity limits.</div><div class="identity"><code>${html(reportId)}</code><span>${html(generated)}</span></div></div></footer><div class="fixed-print-footer" style="display:none"><span>SPIKE | ${html(input.projectName)}</span><span>${html(reportId)} | ${html(generated)}</span></div><script id="report-data" type="application/json">${jsonForScript(geometry)}</script><script id="evidence-data" type="application/json">${jsonForScript(evidence)}</script><script>${reportScript}</script></body></html>`;
}
