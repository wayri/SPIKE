// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import type { ParsedBoard } from "./boardParser";
import { thermalFieldColor } from "./thermalResultFields";
import { boardThermalCuts } from "./boardThermalViewport";
import { numericExtent } from "./numericRange";
import { runLocalWorker } from "./workerBridge";
import type { AssemblyAnalysisScope } from "./assemblyAdmission";

type ContactMode = "pads" | "square";
type ComponentInput = { component_ref: string; power_w: number; r_junction_case_k_w: number; r_case_board_k_w: number; contact_mode?: ContactMode; contact_size_mm?: number };
type VirtualHeatsink = { id: string; face: "top" | "bottom"; x_mm: number; y_mm: number; width_mm: number; height_mm: number; interface_resistance_k_w: number; sink_to_ambient_k_w: number };
type TransientInput = { end_time_s: number; time_step_s: number; output_stride: number; copper_volumetric_heat_capacity_j_m3k: number; dielectric_volumetric_heat_capacity_j_m3k: number };
type BoardModel = "plate" | "layered";
type BoardInput = { model?: BoardModel; conductivity_w_mk?: number; thickness_mm: number; convection_top_w_m2k: number; convection_bottom_w_m2k: number; grid_step_mm: number; dielectric_conductivity_w_mk?: number; copper_conductivity_w_mk?: number; via_plating_thickness_mm?: number; include_copper?: boolean; include_vias?: boolean; include_tracks?: boolean; include_pads?: boolean; include_zones?: boolean; fuzzy_sigma_mm?: number };
type BoardSettings = Required<BoardInput>;
export type BoardThermalRequest = { ambient_temperature_c: number; board: BoardInput; components: ComponentInput[]; virtual_heatsinks?: VirtualHeatsink[]; transient?: TransientInput };
type Request = BoardThermalRequest;
type BoardResult = {
  contract: string; status: "completed" | "blocked"; model_status: string;
  grid?: { origin_mm: [number, number]; spacing_mm: [number, number]; shape: [number, number]; temperatures_c: number[]; order?: string };
  layer_grids?: Array<{ name: string; thickness_mm: number; temperatures_c: number[]; copper_coverage: number[] }>;
  components?: Array<ComponentInput & { position_mm?: [number, number]; board_temperature_c: number; case_temperature_c: number; junction_temperature_c: number; pad_count?: number; pad_contacts?: Array<{ pad_name: string; position_mm: [number, number]; area_mm2: number; board_temperature_c: number; heat_w: number }> }>;
  virtual_heatsinks?: Array<VirtualHeatsink & { temperature_c: number; board_contact_temperature_c: number; heat_flow_w: number }>;
  transient?: Array<{ time_s: number; layer_temperatures_c: number[][]; maximum_board_temperature_c: number; storage_rate_w: number; energy_balance_error_w: number }>;
  summary?: { minimum_board_temperature_c?: number; maximum_board_temperature_c?: number; maximum_junction_temperature_c?: number; total_power_w?: number; outward_heat_w?: number; heatsink_outward_heat_w?: number; energy_balance_error_w?: number; linear_relative_residual?: number; transient_peak_board_temperature_c?: number; transient_final_stored_energy_j?: number; max_transient_energy_balance_error_w?: number };
  issues?: Array<{ severity?: string; message?: string }>;
  message?: string;
};
type Row = Omit<ComponentInput, "contact_size_mm" | "contact_mode"> & { selected: boolean; contact_mode: ContactMode; contact_size_mm: number };
type Props = { board: ParsedBoard | null; design: Record<string, unknown> | null; sourceText?: string | null; ambientC: number; workerAvailable: boolean; savedRequest?: Request; savedResult?: BoardResult; onRequireAdmission: () => Promise<AssemblyAnalysisScope | null>; onSave: (request: Request, result: BoardResult | null) => void; onStatus: (message: string) => void };
function TemperatureCut({ label, points, unit }: { label: string; points: [number, number][]; unit: string }) {
  if (!points.length) return null;
  const first = points[0][0];
  const last = points[points.length - 1][0];
  const { minimum: low, maximum: high } = numericExtent(points.map(point => point[1]));
  const xspan = Math.max(last - first, 1e-9);
  const yspan = Math.max(high - low, 1e-9);
  return <figure className="board-thermal-cut"><svg role="img" aria-label={`${label} temperature profile`} viewBox="0 0 260 130" preserveAspectRatio="none">
    <path d="M 32 10 V 104 H 250" fill="none" stroke="#8fa9b5" strokeWidth="1" />
    <polyline points={points.map(([distance, temperature]) => `${32 + 215 * (distance - first) / xspan},${102 - 86 * (temperature - low) / yspan}`).join(" ")} fill="none" stroke="#ff9a6b" strokeWidth="2" />
    <text x="2" y="18">{high.toFixed(1)}°C</text><text x="2" y="104">{low.toFixed(1)}°C</text>
    <text x="32" y="122">{first.toFixed(1)} {unit}</text><text x="200" y="122">{last.toFixed(1)} {unit}</text>
  </svg><figcaption>{label}</figcaption></figure>;
}
const blankSettings: BoardSettings = { model: "plate", conductivity_w_mk: NaN, thickness_mm: NaN, convection_top_w_m2k: NaN, convection_bottom_w_m2k: NaN, grid_step_mm: NaN, dielectric_conductivity_w_mk: NaN, copper_conductivity_w_mk: NaN, via_plating_thickness_mm: NaN, include_copper: true, include_vias: true, include_tracks: true, include_pads: true, include_zones: true, fuzzy_sigma_mm: 0 };
const finite = (value: unknown) => typeof value === "number" && Number.isFinite(value);
function requestKey(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) => {
    if (Array.isArray(item) && item.every(part => part && typeof part === "object" && typeof part.component_ref === "string"))
      return [...item].sort((left, right) => left.component_ref.localeCompare(right.component_ref));
    return item && typeof item === "object" && !Array.isArray(item)
      ? Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right))) : item;
  });
}
const formatted = (value: unknown, digits = 2) => finite(value) ? (value as number).toFixed(digits) : "—";
function padInventory(board: ParsedBoard | null, design: Record<string, unknown> | null): { counts: Map<string, number>; minimumSizes: Map<string, number> } {
  const designPads = design?.pads;
  const pads: unknown[] = Array.isArray(designPads) ? designPads : board?.pads ?? [];
  const counts = new Map<string, number>();
  const minimumSizes = new Map<string, number>();
  for (const candidate of pads) {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) continue;
    const pad = candidate as Record<string, unknown>;
    const ref = pad.component_ref ?? pad.component ?? pad.component_id ?? pad.ref;
    const size = Array.isArray(pad.size_mm) ? pad.size_mm : Array.isArray(pad.size) ? pad.size : [pad.width, pad.height];
    const layers = Array.isArray(pad.layers) ? pad.layers : [pad.layer];
    const drill = pad.drill_size_mm ?? pad.drill;
    const drillWidth = Array.isArray(drill) ? drill[0] : drill;
    const drillHeight = Array.isArray(drill) ? drill[1] : drill;
    const landArea = Number(size[0]) * Number(size[1]) - Math.PI * Number(finite(drillWidth) ? drillWidth : 0) * Number(finite(drillHeight) ? drillHeight : 0) / 4;
    if (typeof ref !== "string" || !ref || String(pad.type ?? "").toLowerCase() === "np_thru_hole" || pad.plated === false
      || !finite(size[0]) || !finite(size[1]) || size[0] <= 0 || size[1] <= 0 || landArea <= 0
      || !layers.some(layer => typeof layer === "string" && (layer === "*.Cu" || layer.endsWith(".Cu")))) continue;
    counts.set(ref, (counts.get(ref) ?? 0) + 1);
    minimumSizes.set(ref, Math.min(minimumSizes.get(ref) ?? Infinity, Number(size[0]), Number(size[1])));
  }
  return { counts, minimumSizes };
}
function physicalStackup(board: ParsedBoard | null) {
  const layers = (board?.stackup ?? []).filter(layer => /copper|dielectric|core|prepreg/i.test(layer.type));
  const copper = layers.filter(layer => /copper/i.test(layer.type)).length;
  const dielectric = layers.length - copper;
  const complete = copper > 0 && dielectric > 0 && layers.every(layer => finite(layer.thickness) && (layer.thickness ?? 0) > 0);
  return { layers, complete, thicknessMm: complete ? layers.reduce((sum, layer) => sum + (layer.thickness ?? 0), 0) : NaN };
}
export function validBoardThermalResult(raw: unknown, request: Request): raw is BoardResult {
  if (!raw || typeof raw !== "object") return false;
  const result = raw as BoardResult;
  if (result.contract !== "spike/board-thermal-result/v1" || !["completed", "blocked"].includes(result.status) || typeof result.model_status !== "string") return false;
  if (result.status === "blocked") return Array.isArray(result.issues) && result.issues.every(issue => typeof issue?.message === "string");
  const grid = result.grid;
  if (!grid || grid.order !== "x-fast" || !Array.isArray(grid.shape) || !Array.isArray(grid.origin_mm) || !Array.isArray(grid.spacing_mm) || !Array.isArray(grid.temperatures_c)) return false;
  const [nx, ny] = grid.shape;
  if (!Number.isInteger(nx) || !Number.isInteger(ny) || nx < 1 || ny < 1 || nx * ny > 8192 || grid.origin_mm.length !== 2 || grid.spacing_mm.length !== 2 || grid.temperatures_c.length !== nx * ny || !grid.temperatures_c.every(finite) || !grid.origin_mm.every(finite) || !grid.spacing_mm.every(value => finite(value) && value > 0)) return false;
  if (request.board.model === "layered" && (!Array.isArray(result.layer_grids) || !result.layer_grids.length || !result.layer_grids.every(layer => typeof layer.name === "string" && finite(layer.thickness_mm) && layer.thickness_mm > 0 && Array.isArray(layer.temperatures_c) && layer.temperatures_c.length === nx * ny && layer.temperatures_c.every(finite) && Array.isArray(layer.copper_coverage) && layer.copper_coverage.length === nx * ny && layer.copper_coverage.every(value => finite(value) && value >= 0 && value <= 1)))) return false;
  const expected = new Set(request.components.map(part => part.component_ref));
  if (!Array.isArray(result.components) || result.components.length !== expected.size || !result.components.every(part => {
    const selected = request.components.find(item => item.component_ref === part.component_ref);
    const validPads = selected?.contact_mode !== "pads" || (part.contact_mode === "pads" && Number.isInteger(part.pad_count) && (part.pad_count ?? 0) > 0 && Array.isArray(part.pad_contacts) && part.pad_contacts.length === part.pad_count && part.pad_contacts.every(pad => typeof pad.pad_name === "string" && Array.isArray(pad.position_mm) && pad.position_mm.length === 2 && pad.position_mm.every(finite) && [pad.area_mm2, pad.board_temperature_c, pad.heat_w].every(finite) && pad.area_mm2 > 0));
    return expected.delete(part.component_ref) && [part.power_w, part.board_temperature_c, part.case_temperature_c, part.junction_temperature_c].every(finite) && Array.isArray(part.position_mm) && part.position_mm.length === 2 && part.position_mm.every(finite) && validPads;
  })) return false;
  const summary = result.summary;
  if (request.virtual_heatsinks?.length && (!Array.isArray(result.virtual_heatsinks) || result.virtual_heatsinks.length !== request.virtual_heatsinks.length || !result.virtual_heatsinks.every(sink => [sink.temperature_c, sink.board_contact_temperature_c, sink.heat_flow_w].every(finite)))) return false;
  if (request.transient && (!Array.isArray(result.transient) || result.transient.length < 2 || !result.transient.every(frame => finite(frame.time_s) && finite(frame.maximum_board_temperature_c) && finite(frame.storage_rate_w) && finite(frame.energy_balance_error_w) && Array.isArray(frame.layer_temperatures_c) && frame.layer_temperatures_c.length === result.layer_grids?.length && frame.layer_temperatures_c.every(values => Array.isArray(values) && values.length === nx * ny && values.every(finite))) || !finite(summary?.transient_peak_board_temperature_c) || !finite(summary?.max_transient_energy_balance_error_w))) return false;
  return Boolean(summary && [summary.minimum_board_temperature_c, summary.maximum_board_temperature_c, summary.maximum_junction_temperature_c, summary.total_power_w, summary.energy_balance_error_w, summary.linear_relative_residual].every(finite));
}

export default function BoardThermalPanel({ board, design, sourceText, ambientC, workerAvailable, savedRequest, savedResult, onRequireAdmission, onSave, onStatus }: Props) {
  const { counts, minimumSizes } = padInventory(board, design);
  const stack = physicalStackup(board);
  const [settings, setSettings] = useState<BoardSettings>(() => ({ ...blankSettings, model: stack.complete ? "layered" : "plate", ...savedRequest?.board }));
  const [rows, setRows] = useState<Row[]>(() => (board?.components ?? []).map(part => {
    const saved = savedRequest?.components.find(row => row.component_ref === part.ref);
    return { component_ref: part.ref, selected: Boolean(saved), power_w: saved?.power_w ?? NaN, r_junction_case_k_w: saved?.r_junction_case_k_w ?? NaN, r_case_board_k_w: saved?.r_case_board_k_w ?? NaN, contact_mode: saved ? saved.contact_mode ?? "square" : counts.has(part.ref) ? "pads" : "square", contact_size_mm: saved?.contact_size_mm ?? NaN };
  }));
  const [virtualHeatsinks, setVirtualHeatsinks] = useState<VirtualHeatsink[]>(() => savedRequest?.virtual_heatsinks ?? []);
  const [transientEnabled, setTransientEnabled] = useState(Boolean(savedRequest?.transient));
  const [transientSettings, setTransientSettings] = useState<TransientInput>(() => savedRequest?.transient ?? { end_time_s: 60, time_step_s: 10, output_stride: 1, copper_volumetric_heat_capacity_j_m3k: 3.45e6, dielectric_volumetric_heat_capacity_j_m3k: 1.4e6 });
  const [result, setResult] = useState<BoardResult | null>(savedRequest && validBoardThermalResult(savedResult, savedRequest) ? savedResult : null);
  const [resultKey, setResultKey] = useState(requestKey(savedRequest ?? null));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [layerIndex, setLayerIndex] = useState(-1);
  const [showCopperCoverage, setShowCopperCoverage] = useState(false);
  const [smoothDisplay, setSmoothDisplay] = useState(true);
  const [frameIndex, setFrameIndex] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const gridX = board && finite(settings.grid_step_mm) && settings.grid_step_mm > 0 ? Math.ceil((board.bounds.maxX - board.bounds.minX) / settings.grid_step_mm) : 0;
  const gridY = board && finite(settings.grid_step_mm) && settings.grid_step_mm > 0 ? Math.ceil((board.bounds.maxY - board.bounds.minY) / settings.grid_step_mm) : 0;
  const cellsPerLayer = gridX * gridY;
  const unresolvedPads = rows.filter(row => row.selected && row.contact_mode === "pads" && (minimumSizes.get(row.component_ref) ?? Infinity) < settings.grid_step_mm).map(row => row.component_ref);
  const commonBoard = { thickness_mm: settings.thickness_mm, convection_top_w_m2k: settings.convection_top_w_m2k, convection_bottom_w_m2k: settings.convection_bottom_w_m2k, grid_step_mm: settings.grid_step_mm };
  const requestBoard: BoardInput = settings.model === "layered"
    ? { ...commonBoard, model: "layered", dielectric_conductivity_w_mk: settings.dielectric_conductivity_w_mk, copper_conductivity_w_mk: settings.copper_conductivity_w_mk, ...(settings.include_vias ? { via_plating_thickness_mm: settings.via_plating_thickness_mm } : {}), include_copper: settings.include_copper, include_vias: settings.include_vias, include_tracks: settings.include_tracks, include_pads: settings.include_pads, include_zones: settings.include_zones, fuzzy_sigma_mm: settings.fuzzy_sigma_mm }
    : { ...commonBoard, model: "plate", conductivity_w_mk: settings.conductivity_w_mk };
  const request: Request = { ambient_temperature_c: ambientC, board: requestBoard, components: rows.filter(row => row.selected).map(({ component_ref, power_w, r_junction_case_k_w, r_case_board_k_w, contact_mode, contact_size_mm }) => ({ component_ref, power_w, r_junction_case_k_w, r_case_board_k_w, contact_mode, ...(contact_mode === "square" ? { contact_size_mm } : {}) })), ...(virtualHeatsinks.length ? { virtual_heatsinks: virtualHeatsinks } : {}), ...(transientEnabled ? { transient: transientSettings } : {}) };
  const inputKey = requestKey(request);
  const changeSetting = (key: "conductivity_w_mk" | "thickness_mm" | "convection_top_w_m2k" | "convection_bottom_w_m2k" | "grid_step_mm" | "dielectric_conductivity_w_mk" | "copper_conductivity_w_mk" | "via_plating_thickness_mm" | "fuzzy_sigma_mm", value: string) => setSettings(current => ({ ...current, [key]: value === "" ? NaN : Number(value) }));
  const changeRow = (ref: string, patch: Partial<Row>) => setRows(current => current.map(row => row.component_ref === ref ? { ...row, ...patch } : row));
  const changeHeatsink = (id: string, patch: Partial<VirtualHeatsink>) => setVirtualHeatsinks(current => current.map(sink => sink.id === id ? { ...sink, ...patch } : sink));
  const inputError = () => {
    if (!request.components.length || !request.components.some(row => row.power_w > 0)) return "Select at least one board part with positive power.";
    if (settings.model === "layered" && !stack.complete) return "Layered mode needs an imported physical stackup with positive thickness for every copper and dielectric layer. Choose plate mode or import a complete stackup.";
    if (virtualHeatsinks.length && settings.model !== "layered") return "Virtual board heatsinks need the layered model and an imported physical stackup.";
    if (transientEnabled && settings.model !== "layered") return "Spatial board transient needs the layered model and an imported physical stackup.";
    if (transientEnabled) { const { end_time_s, time_step_s, output_stride, copper_volumetric_heat_capacity_j_m3k, dielectric_volumetric_heat_capacity_j_m3k } = transientSettings; const steps = end_time_s / time_step_s; if (![end_time_s, time_step_s, copper_volumetric_heat_capacity_j_m3k, dielectric_volumetric_heat_capacity_j_m3k].every(value => finite(value) && value > 0) || !Number.isInteger(output_stride) || output_stride < 1 || !Number.isInteger(steps) || steps < 1 || steps > 240 || 1 + Math.ceil(steps / output_stride) > 24 || cellsPerLayer * stack.layers.length * (1 + Math.ceil(steps / output_stride)) > 500000) return "Transient board run needs positive time and heat capacities, an integer number of 1–240 steps, and at most 24 frames / 500,000 saved temperature values. Increase output stride or grid step."; }
    if (virtualHeatsinks.length > 16 || virtualHeatsinks.some(sink => ![sink.x_mm, sink.y_mm, sink.width_mm, sink.height_mm, sink.interface_resistance_k_w, sink.sink_to_ambient_k_w].every(finite) || sink.width_mm <= 0 || sink.height_mm <= 0 || sink.interface_resistance_k_w < 0 || sink.sink_to_ambient_k_w <= 0 || !board || sink.x_mm - sink.width_mm / 2 < board.bounds.minX || sink.x_mm + sink.width_mm / 2 > board.bounds.maxX || sink.y_mm - sink.height_mm / 2 < board.bounds.minY || sink.y_mm + sink.height_mm / 2 > board.bounds.maxY)) return "Each virtual heatsink needs a footprint inside the board, nonnegative interface K/W, and positive sink-to-ambient K/W (16 maximum).";
    if (cellsPerLayer > 8192) return `Grid estimate is ${cellsPerLayer} cells per layer, above the 8,192-cell limit. Increase grid step.`;
    const withoutPads = request.components.find(row => row.contact_mode === "pads" && !counts.has(row.component_ref));
    if (withoutPads) return `${withoutPads.component_ref} has no eligible imported copper pads. Choose square contact or import pads for this part.`;
    if (settings.model === "layered" && finite(settings.thickness_mm) && Math.abs(settings.thickness_mm - stack.thicknessMm) > 0.05 * stack.thicknessMm) return `Board thickness must agree with imported physical stackup thickness ${formatted(stack.thicknessMm, 3)} mm within 5%.`;
    if (settings.model === "layered" && (![settings.dielectric_conductivity_w_mk, settings.copper_conductivity_w_mk].every(value => finite(value) && value > 0) || settings.include_vias && (!finite(settings.via_plating_thickness_mm) || settings.via_plating_thickness_mm <= 0) || !finite(settings.fuzzy_sigma_mm) || settings.fuzzy_sigma_mm < 0)) return "For layered board mode, enter positive dielectric and copper conductivity, positive via plating thickness when vias are included, and nonnegative spread sigma.";
    if (settings.model === "plate" && (!finite(settings.conductivity_w_mk) || settings.conductivity_w_mk <= 0)) return "Enter positive effective board conductivity for plate mode.";
    if (![settings.thickness_mm, settings.grid_step_mm].every(value => finite(value) && value > 0) || ![settings.convection_top_w_m2k, settings.convection_bottom_w_m2k].every(value => finite(value) && value >= 0) || settings.convection_top_w_m2k + settings.convection_bottom_w_m2k <= 0 || !finite(ambientC) || ambientC < -273.15 || request.components.some(row => !finite(row.power_w) || row.power_w < 0 || !finite(row.r_junction_case_k_w) || row.r_junction_case_k_w <= 0 || !finite(row.r_case_board_k_w) || row.r_case_board_k_w <= 0 || row.contact_mode === "square" && (!finite(row.contact_size_mm) || Number(row.contact_size_mm) <= 0))) return "Enter positive thickness, grid step, resistances, and square contact size where selected; nonnegative power and convection with at least one positive convection value; and valid ambient temperature.";
    return "";
  };
  const run = async () => {
    setError("");
    if (!design || !board) { setError("Import a PCB design before running the board model."); return; }
    const invalid = inputError(); if (invalid) { setError(invalid); return; }
    setBusy(true);
    try {
      const assemblyScope = await onRequireAdmission();
      const bounds = board.bounds;
      const thermalDesign = { ...design, metadata: { ...((design.metadata && typeof design.metadata === "object" && !Array.isArray(design.metadata)) ? design.metadata as Record<string, unknown> : {}), board_bounds_mm: [bounds.minX, bounds.minY, bounds.maxX, bounds.maxY] } };
      const response = await runLocalWorker({ method: "run_board_thermal", params: { design: thermalDesign, request, assembly_scope: assemblyScope,
        ...(settings.model === "layered" && sourceText ? { source_kicad_pcb: sourceText } : {}) } });
      const next = response.result as BoardResult | undefined;
      if (!response.ok || !validBoardThermalResult(next, request)) throw new Error(response.error ?? "The board thermal worker returned an invalid result.");
      setResult(next); setResultKey(inputKey); setPlaying(false); setFrameIndex(next.transient?.length ? next.transient.length - 1 : -1); onSave(request, next);
      onStatus(next.status === "completed" ? `Approximate ${settings.model === "layered" ? "layered" : "2D plate"} board thermal run completed` : next.issues?.[0]?.message ?? next.message ?? "Board thermal run was blocked");
    } catch (cause) { const message = cause instanceof Error ? cause.message : "Board thermal run failed"; setError(message); onStatus(message); }
    finally { setBusy(false); }
  };
  const grid = result?.status === "completed" && resultKey === inputKey ? result.grid : undefined;
  const [nx, ny] = grid?.shape ?? [0, 0];
  const layerGrids = result?.status === "completed" && resultKey === inputKey && Array.isArray(result.layer_grids) ? result.layer_grids : [];
  const transientFrames = result?.status === "completed" && resultKey === inputKey && Array.isArray(result.transient) ? result.transient : [];
  const activeFrame = frameIndex >= 0 ? transientFrames[frameIndex] : undefined;
  useEffect(() => {
    if (!playing || transientFrames.length < 2) return;
    const timer = window.setInterval(() => setFrameIndex(index => index < 0 || index >= transientFrames.length - 1 ? 0 : index + 1), 600);
    return () => window.clearInterval(timer);
  }, [playing, result, resultKey, inputKey, transientFrames.length]);
  const selectedLayer = layerIndex >= 0 ? layerGrids[layerIndex] : undefined;
  const values = activeFrame?.layer_temperatures_c[layerIndex >= 0 ? layerIndex : 0] ?? selectedLayer?.temperatures_c ?? grid?.temperatures_c ?? [];
  const coverage = selectedLayer?.copper_coverage;
  const plotReady = Boolean(grid && grid.order === "x-fast" && Number.isInteger(nx) && Number.isInteger(ny) && nx > 0 && ny > 0 && nx * ny <= 8192 && values.length === nx * ny && values.every(finite));
  const coverageReady = Boolean(showCopperCoverage && selectedLayer && Array.isArray(coverage) && coverage.length === nx * ny && coverage.every(value => finite(value) && value >= 0 && value <= 1));
  const extent = plotReady ? numericExtent(values) : { minimum: 0, maximum: 0 };
  const minimum = transientFrames.length ? Math.min(ambientC, result?.summary?.minimum_board_temperature_c ?? extent.minimum) : extent.minimum;
  const maximum = transientFrames.length ? Math.max(result?.summary?.maximum_board_temperature_c ?? extent.maximum, result?.summary?.transient_peak_board_temperature_c ?? extent.maximum) : extent.maximum;
  return <div className="wizard-section board-thermal-section" data-guide="thermal-board-setup">
    <label>{settings.model === "layered" ? "LAYERED BOARD THERMAL" : "2D BOARD THERMAL"} · APPROXIMATE</label>
    <p className="thermal-table-note">Enter measured or justified board and component properties. Imported copper pads locate pad contacts; conductivity, convection, thermal resistance, and package heat flow are not inferred. Plate mode is a uniform 2D sheet. Layered mode is an approximate 3D stack discretization with optional imported copper/vias and Gaussian spread. Neither resolves package blocks, a tetrahedral mesh, airflow, or CFD.</p>
    <div className="board-thermal-settings"><label>Board model<span><select aria-label="Board thermal model" value={settings.model} onChange={event => setSettings(current => ({ ...current, model: event.target.value as BoardModel }))}><option value="plate">Uniform 2D plate</option><option value="layered" disabled={!stack.complete}>Layered 3D stack (approximate)</option></select></span></label></div>
    {!stack.complete && <p className="thermal-table-note">Layered mode is unavailable: import an ordered physical stackup with positive thickness for each copper and dielectric layer.</p>}
    <div className="board-thermal-settings">{([
      ["thickness_mm", "Board thickness", "mm"], ["convection_top_w_m2k", "Top convection", "W/(m²·K)"], ["convection_bottom_w_m2k", "Bottom convection", "W/(m²·K)"], ["grid_step_mm", "Grid step", "mm"],
    ] as const).map(([key, label, unit]) => <label key={key}>{label}<span><input type="number" min={key.startsWith("convection_") ? "0" : "0.001"} step="any" value={Number.isNaN(settings[key]) ? "" : settings[key]} onChange={event => changeSetting(key, event.target.value)} /> {unit}</span></label>)}</div>
    {settings.model === "plate" ? <div className="board-thermal-settings"><label>Effective board conductivity<span><input aria-label="Board conductivity" type="number" min="0.001" step="any" value={Number.isNaN(settings.conductivity_w_mk) ? "" : settings.conductivity_w_mk} onChange={event => changeSetting("conductivity_w_mk", event.target.value)} /> W/(m·K)</span></label></div> : <>
      <p className="thermal-table-note">Layer thicknesses come from the imported stackup; entered board thickness must agree with that stack. Feature switches control sampled copper occupancy and spreading. Pad contact mode still uses imported pads for case-to-board injection when copper layer spreading is off. Spread sigma of 0 leaves sampled copper coverage unsmoothed; a positive value blurs each layer's coverage.</p>
      <div className="board-thermal-settings">{([
        ["dielectric_conductivity_w_mk", "Dielectric conductivity", "W/(m·K)"], ["copper_conductivity_w_mk", "Copper conductivity", "W/(m·K)"], ["fuzzy_sigma_mm", "Copper blur sigma", "mm"],
      ] as const).map(([key, label, unit]) => <label key={key}>{label}<span><input aria-label={label} type="number" min={key === "fuzzy_sigma_mm" ? "0" : "0.001"} step="any" value={Number.isNaN(settings[key]) ? "" : settings[key]} onChange={event => changeSetting(key, event.target.value)} /> {unit}</span></label>)}
      {settings.include_vias && <label>Via plating thickness<span><input aria-label="Via plating thickness" type="number" min="0.001" step="any" value={Number.isNaN(settings.via_plating_thickness_mm) ? "" : settings.via_plating_thickness_mm} onChange={event => changeSetting("via_plating_thickness_mm", event.target.value)} /> mm</span></label>}</div>
      <div className="board-thermal-settings">{([
        ["include_copper", "Copper layers"], ["include_vias", "Vias"], ["include_tracks", "Tracks"], ["include_pads", "Pads"], ["include_zones", "Zones"],
      ] as const).map(([key, label]) => <label key={key}><span><input aria-label={`Include ${label}`} type="checkbox" checked={settings[key]} onChange={event => setSettings(current => ({ ...current, [key]: event.target.checked }))} /> {label}</span></label>)}</div>
    </>}
    {board && <p className="thermal-table-note">Grid estimate: {gridX > 0 && gridY > 0 ? `${gridX} × ${gridY} = ${cellsPerLayer} cells per layer` : "enter a positive grid step"}{settings.model === "layered" ? ` · ${stack.layers.length} depth layers · imported physical thickness ${formatted(stack.thicknessMm, 3)} mm` : ""}.{cellsPerLayer > 8192 ? " Exceeds the 8,192-cell limit; increase grid step." : ""}</p>}
    {settings.model === "layered" && <div className="wizard-section"><div className="thermal-section-heading"><label>VIRTUAL BOARD HEATSINKS</label><span>{virtualHeatsinks.length}</span><button type="button" disabled={!board || virtualHeatsinks.length >= 16} onClick={() => { if (!board) return; const width = board.bounds.maxX - board.bounds.minX; const height = board.bounds.maxY - board.bounds.minY; setVirtualHeatsinks(current => [...current, { id: `HS${Date.now()}`, face: "top", x_mm: (board.bounds.minX + board.bounds.maxX) / 2, y_mm: (board.bounds.minY + board.bounds.maxY) / 2, width_mm: Math.min(20, width / 4), height_mm: Math.min(20, height / 4), interface_resistance_k_w: 1, sink_to_ambient_k_w: 10 }]); }}>Add virtual heatsink</button></div>
      <p className="thermal-table-note">A rectangular contact on the top or bottom face feeds an isothermal mathematical sink. Interface K/W and sink-to-ambient K/W are explicit assumptions; fins, airflow, and 3D heatsink geometry are not solved. Existing assembly/CFD heatsink shapes do not automatically affect this board run.</p>
      {virtualHeatsinks.length > 0 && <div className="thermal-table-scroll"><table className="thermal-input-table thermal-spreadsheet"><thead><tr><th>ID</th><th>Face</th><th>Center X mm</th><th>Center Y mm</th><th>Width mm</th><th>Height mm</th><th>Interface K/W</th><th>Sink–ambient K/W</th><th /></tr></thead><tbody>{virtualHeatsinks.map(sink => <tr key={sink.id}><td>{sink.id}</td><td><select aria-label={`${sink.id} face`} value={sink.face} onChange={event => changeHeatsink(sink.id, { face: event.target.value as VirtualHeatsink["face"] })}><option value="top">Top</option><option value="bottom">Bottom</option></select></td>{(["x_mm", "y_mm", "width_mm", "height_mm", "interface_resistance_k_w", "sink_to_ambient_k_w"] as const).map(key => <td key={key}><input aria-label={`${sink.id} ${key}`} type="number" step="any" value={Number.isNaN(sink[key]) ? "" : sink[key]} onChange={event => changeHeatsink(sink.id, { [key]: event.target.value === "" ? NaN : Number(event.target.value) })} /></td>)}<td><button type="button" onClick={() => setVirtualHeatsinks(current => current.filter(item => item.id !== sink.id))}>Remove</button></td></tr>)}</tbody></table></div>}</div>}
    {settings.model === "layered" && <div className="wizard-section"><label><input aria-label="Solve transient board field" type="checkbox" checked={transientEnabled} onChange={event => setTransientEnabled(event.target.checked)} /> SOLVE TRANSIENT BOARD FIELD</label><p className="thermal-table-note">Constant assigned power starts at ambient. Enter reviewed volumetric heat capacities; the displayed animation uses saved backward-Euler board cells, not interpolated steady maps. Part case/junction values in the table remain steady-state estimates.</p>{transientEnabled && <div className="board-thermal-settings">{([
      ["end_time_s", "End time", "s"], ["time_step_s", "Time step", "s"], ["output_stride", "Save every N steps", "steps"], ["copper_volumetric_heat_capacity_j_m3k", "Copper volumetric capacity", "J/(m³·K)"], ["dielectric_volumetric_heat_capacity_j_m3k", "Dielectric volumetric capacity", "J/(m³·K)"],
    ] as const).map(([key, label, unit]) => <label key={key}>{label}<span><input aria-label={label} type="number" min={key === "output_stride" ? "1" : "0.000001"} step={key === "output_stride" ? "1" : "any"} value={Number.isNaN(transientSettings[key]) ? "" : transientSettings[key]} onChange={event => setTransientSettings(current => ({ ...current, [key]: event.target.value === "" ? NaN : Number(event.target.value) }))} /> {unit}</span></label>)}</div>}</div>}
    {unresolvedPads.length > 0 && <p className="thermal-table-note" role="status">Pad contact resolution warning: {unresolvedPads.join(", ")} has a pad narrower than the grid step. BGA/QFN contacts may be underresolved; use a finer step and compare results.</p>}
    <p className="thermal-table-note">Ambient: {formatted(ambientC)} °C. Select board references, enter power and thermal resistances, then choose imported pad contacts or an explicit square fallback.</p>
    <div className="thermal-native-results board-thermal-parts"><table><thead><tr><th>Use</th><th>Reference</th><th>Power W</th><th>Junction–case K/W</th><th>Case–board K/W</th><th>Board contact</th><th>Imported pads</th><th>Square width mm</th></tr></thead><tbody>{rows.map(row => <tr key={row.component_ref}><td><input aria-label={`Use ${row.component_ref}`} type="checkbox" checked={row.selected} onChange={event => changeRow(row.component_ref, { selected: event.target.checked })} /></td><td>{row.component_ref}</td>{(["power_w", "r_junction_case_k_w", "r_case_board_k_w"] as const).map(key => <td key={key}><input aria-label={`${row.component_ref} ${key}`} type="number" min="0" step="any" value={Number.isNaN(row[key]) ? "" : row[key]} onChange={event => changeRow(row.component_ref, { [key]: event.target.value === "" ? NaN : Number(event.target.value) })} /></td>)}<td><select aria-label={`${row.component_ref} contact mode`} value={row.contact_mode} onChange={event => changeRow(row.component_ref, { contact_mode: event.target.value as ContactMode })}><option value="pads">Imported pads</option><option value="square">Square fallback</option></select></td><td>{counts.get(row.component_ref) ?? 0}</td><td><input aria-label={`${row.component_ref} contact_size_mm`} type="number" min="0" step="any" disabled={row.contact_mode === "pads"} value={Number.isNaN(row.contact_size_mm) ? "" : row.contact_size_mm} onChange={event => changeRow(row.component_ref, { contact_size_mm: event.target.value === "" ? NaN : Number(event.target.value) })} /></td></tr>)}</tbody></table></div>
    {!board && <p className="thermal-table-note">Import a board to choose component references.</p>}
    <div className="thermal-native-actions"><button className="run-btn" disabled={busy || !workerAvailable || !board || !design} onClick={() => void run()}>{busy ? "Running board model" : "Run board thermal"}</button><button className="secondary-btn" disabled={busy} onClick={() => { const invalid = inputError(); if (invalid) setError(invalid); else { setError(""); onSave(request, null); } }}>Save board inputs</button></div>
    {!workerAvailable && <p className="thermal-table-note">The desktop worker is unavailable.</p>}
    {error && <div className="thermal-validation invalid" role="alert">{error}</div>}
    {result && resultKey !== inputKey && <div className="thermal-validation invalid">Board inputs changed. Rerun to update the map and part temperatures.</div>}
    {result && resultKey === inputKey && <div className={`thermal-validation ${result.status === "completed" ? "valid" : "invalid"}`}><b>Board run · {result.status} · {result.model_status}</b>{result.issues?.map((issue, index) => <small key={index}>{issue.severity}: {issue.message}</small>)}{result.message && <small>{result.message}</small>}</div>}
    {result?.status === "completed" && resultKey === inputKey && <><p className="thermal-table-note">{formatted(result.summary?.total_power_w, 3)} W total · board {formatted(result.summary?.minimum_board_temperature_c)}–{formatted(result.summary?.maximum_board_temperature_c)} °C · maximum junction {formatted(result.summary?.maximum_junction_temperature_c)} °C</p>
      {transientFrames.length > 1 && <div className="wizard-section"><label>TRANSIENT BOARD ANIMATION · {activeFrame ? `${formatted(activeFrame.time_s, 1)} s` : "steady state"}</label><div className="thermal-native-actions"><button type="button" onClick={() => { if (!playing && frameIndex < 0) setFrameIndex(0); setPlaying(value => !value); }}>{playing ? "Pause" : "Play"}</button><button type="button" onClick={() => { setPlaying(false); setFrameIndex(-1); }}>Show steady</button><input aria-label="Transient board time frame" type="range" min="0" max={transientFrames.length - 1} value={Math.max(0, frameIndex)} onChange={event => { setPlaying(false); setFrameIndex(Number(event.target.value)); }} /></div><p className="thermal-table-note">Frame {Math.max(0, frameIndex) + 1}/{transientFrames.length} · peak board cell {formatted(activeFrame?.maximum_board_temperature_c ?? result.summary?.maximum_board_temperature_c)} °C · transient peak {formatted(result.summary?.transient_peak_board_temperature_c)} °C · final stored heat {formatted(result.summary?.transient_final_stored_energy_j, 3)} J · maximum step heat-balance error {formatted(result.summary?.max_transient_energy_balance_error_w, 8)} W. Colors share one scale across frames.</p><svg role="img" aria-label="Maximum board temperature versus transient time" viewBox="0 0 360 100" preserveAspectRatio="none"><path d="M 20 5 V 85 H 355" fill="none" stroke="currentColor" strokeWidth="1" /><polyline fill="none" stroke="#2683ca" strokeWidth="2" points={transientFrames.map(frame => `${20 + 330 * (frame.time_s / transientFrames[transientFrames.length - 1].time_s)},${85 - 75 * ((frame.maximum_board_temperature_c - ambientC) / Math.max(1e-9, (result.summary?.transient_peak_board_temperature_c ?? ambientC) - ambientC))}`).join(" ")} /><text x="20" y="98">0 s</text><text x="305" y="98">{formatted(transientFrames[transientFrames.length - 1].time_s, 1)} s</text></svg></div>}
      <label className="thermal-table-note"><input aria-label="Smooth thermal display" type="checkbox" checked={smoothDisplay} onChange={event => setSmoothDisplay(event.target.checked)} /> Smooth displayed temperature colors (solver cells unchanged)</label>
      {layerGrids.length > 0 && <div className="board-thermal-settings"><label>Temperature layer<span><select aria-label="Temperature layer" value={selectedLayer ? layerIndex : -1} onChange={event => setLayerIndex(Number(event.target.value))}><option value={-1}>Top surface</option>{layerGrids.map((layer, index) => <option key={`${layer.name}:${index}`} value={index}>{layer.name} · {formatted(layer.thickness_mm, 3)} mm</option>)}</select></span></label>{selectedLayer && <label><span><input aria-label="Show copper coverage" type="checkbox" checked={showCopperCoverage} onChange={event => setShowCopperCoverage(event.target.checked)} /> Show copper coverage</span></label>}</div>}
      {plotReady && grid ? <figure className="board-thermal-figure"><svg role="img" aria-label={`${selectedLayer?.name ?? "Board"} temperature grid, ${nx} by ${ny} cells, ${formatted(minimum)} to ${formatted(maximum)} degrees Celsius`} viewBox={`-45 -24 ${nx + 62} ${ny + 55}`} preserveAspectRatio="xMidYMid meet"><defs><filter id="board-thermal-display-smooth" x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB"><feGaussianBlur stdDeviation="0.55" /></filter></defs><g filter={smoothDisplay ? "url(#board-thermal-display-smooth)" : undefined}>{values.map((value, index) => { const [r, g, b] = thermalFieldColor(value, minimum, maximum); return <rect key={index} x={index % nx} y={Math.floor(index / nx)} width="1" height="1" fill={`rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`}><title>{`x ${formatted(grid.origin_mm[0] + (index % nx) * grid.spacing_mm[0])} mm, y ${formatted(grid.origin_mm[1] + Math.floor(index / nx) * grid.spacing_mm[1])} mm: ${formatted(value)} °C`}</title></rect>; })}</g>{coverageReady && coverage?.map((value, index) => value > 0 ? <rect key={`copper:${index}`} x={index % nx} y={Math.floor(index / nx)} width="1" height="1" fill="#fff" opacity={0.55 * value}><title>{`Copper coverage ${formatted(value * 100, 1)}%`}</title></rect> : null)}{result.components?.map(part => part.position_mm && finite(part.position_mm[0]) && finite(part.position_mm[1]) ? <g key={part.component_ref} transform={`translate(${(part.position_mm[0] - grid.origin_mm[0]) / grid.spacing_mm[0]} ${(part.position_mm[1] - grid.origin_mm[1]) / grid.spacing_mm[1]})`}><circle r="1.8" fill="none" stroke="#fff" strokeWidth="0.45" /><text x="2.5" y="-1">{part.component_ref}</text></g> : null)}<text x="0" y="-5">X → {formatted(grid.origin_mm[0])} to {formatted(grid.origin_mm[0] + nx * grid.spacing_mm[0])} mm</text><text x="-42" y="0">Y ↓</text><text x="0" y={ny + 12}>{formatted(grid.origin_mm[1])} to {formatted(grid.origin_mm[1] + ny * grid.spacing_mm[1])} mm</text></svg><figcaption>Imported board bounds as a rectangle, source XY with +X right and +Y down. Circles mark component centers. Displayed colors are smoothed when selected; hover reports original solved cell values. Blue {formatted(minimum)} °C → red {formatted(maximum)} °C.{coverageReady ? " White overlay indicates copper coverage (opacity 0–100%)." : ""}</figcaption></figure> : <p className="thermal-table-note">Grid is unavailable or exceeds the 8,192 cell display limit.</p>}
      {grid && result.components?.filter(part => part.position_mm).map(part => {
        const cuts = boardThermalCuts(grid, part.position_mm!, layerGrids);
        return <div className="board-thermal-part-profiles" key={`cuts:${part.component_ref}`}>
          <strong>{part.component_ref} solved board temperature cuts · x/y source coordinates</strong>
          <div className="board-thermal-cut-row">
            <TemperatureCut label="Horizontal X" points={cuts.horizontal} unit="mm" />
            <TemperatureCut label="Vertical Y" points={cuts.vertical} unit="mm" />
            <TemperatureCut label="Through stack Z" points={cuts.throughStack} unit="mm" />
          </div>
          <small>Sampled at the cell containing {part.component_ref}. Z is layer-center depth from the top face. These temperature cuts do not establish a directional thermal resistance without local heat flow.</small>
        </div>;
      })}
      <div className="thermal-native-results"><table><thead><tr><th>Reference</th><th>Contact</th><th>Power W</th><th>Board °C</th><th>Case °C</th><th>Junction °C</th></tr></thead><tbody>{result.components?.map(part => <tr key={part.component_ref}><td>{part.component_ref}</td><td>{part.contact_mode === "pads" ? `${part.pad_count} pads` : "Square"}</td><td>{formatted(part.power_w, 3)}</td><td>{formatted(part.board_temperature_c)}</td><td>{formatted(part.case_temperature_c)}</td><td>{formatted(part.junction_temperature_c)}</td></tr>)}</tbody></table></div>
      {result.virtual_heatsinks?.length ? <div className="thermal-native-results"><b>Virtual heatsink heat paths · {formatted(result.summary?.heatsink_outward_heat_w, 3)} W to ambient</b><table><thead><tr><th>ID</th><th>Face</th><th>Board contact °C</th><th>Sink °C</th><th>Heat to ambient W</th></tr></thead><tbody>{result.virtual_heatsinks.map(sink => <tr key={sink.id}><td>{sink.id}</td><td>{sink.face}</td><td>{formatted(sink.board_contact_temperature_c)}</td><td>{formatted(sink.temperature_c)}</td><td>{formatted(sink.heat_flow_w, 4)}</td></tr>)}</tbody></table></div> : null}
      {result.components?.filter(part => part.contact_mode === "pads" && part.pad_contacts?.length).map(part => <details key={part.component_ref}><summary>{part.component_ref} pad heat paths ({part.pad_count})</summary><div className="thermal-native-results"><table><thead><tr><th>Pad</th><th>Area mm²</th><th>Board °C</th><th>Heat W</th></tr></thead><tbody>{part.pad_contacts?.map((pad, index) => <tr key={`${pad.pad_name}:${index}`}><td>{pad.pad_name}</td><td>{formatted(pad.area_mm2, 3)}</td><td>{formatted(pad.board_temperature_c)}</td><td>{formatted(pad.heat_w, 4)}</td></tr>)}</tbody></table></div></details>)}
    </>}
  </div>;
}
