export type ResultViewMode =
  | "geometry"
  | "voltage"
  | "voltage_drop"
  | "current"
  | "current_density"
  | "power_loss"
  | "via_stress"
  | "impedance"
  | "mesh"
  | "electric_field"
  | "magnetic_field";

export type ViaModel = "extracted" | "plated_cylinder" | "lumped_rlc" | "ignore";

export type ScalarSample = {
  x_mm: number;
  y_mm: number;
  z_mm?: number;
  layer?: string;
  net?: string;
  element_id?: string;
  source_id?: string;
  width_mm?: number;
  kind?: string;
  source_kind?: string;
  vertices_mm?: [number, number, number][];
  value: number;
};

export type SampleLayout = Omit<ScalarSample, "value">;

export type VectorSample = ScalarSample & {
  vector: [number, number, number];
  magnitude: number;
};

export type MeshCell = {
  id: string;
  vertices_mm: [number, number, number][];
  kind?: "surface" | "volume" | string;
  topology?: string;
  source_kind?: string;
  source_id?: string;
  layer?: string;
  net?: string;
};

/**
 * An electrical branch between two extracted terminals. It is intentionally a
 * line-only result primitive: it communicates a circuit equivalent without
 * claiming a package volume, material distribution, or current-density field.
 */
export type ComponentBridge = {
  id: string;
  topology: "line2" | string;
  representation: "electrical_equivalent_line";
  vertices_mm: [[number, number, number], [number, number, number]];
  component_ref?: string;
  component_id?: string;
  from_net?: string;
  to_net?: string;
  from_layer?: string;
  to_layer?: string;
  resistance_ohm?: number;
  current_a?: number;
  voltage_drop_v?: number;
  power_loss_w?: number;
  model_ref?: string;
  geometry_model?: string;
  current_density_supported: false;
};

export type ImpedancePoint = {
  frequency_hz: number;
  resistance_ohm?: number;
  reactance_ohm?: number;
  magnitude_ohm: number;
  phase_deg: number;
};

export type ParasiticResult = {
  contract?: string;
  model_status?: string;
  net: string;
  resistance_ohm?: number;
  capacitance_f?: number | null;
  inductance_h?: number;
  conductance_s?: number | null;
  parameter_availability?: Record<string, string>;
  network_uses?: string[];
  blocked_uses?: string[];
  quality?: {
    maximum_relative_residual?: number;
    maximum_sampled_condition_number?: number | null;
    least_squares_fallback_count?: number;
    inductance_passivity?: {
      negative_eigenmode_count?: number;
      frobenius_correction_ratio?: number;
    };
    capacitance?: {
      model?: string;
      status?: string;
      reference_mode?: string;
      reference_net?: string;
      branch_coverage?: number;
      loss_tangent_branch_coverage?: number;
      skipped_via_branch_count?: number;
    };
  };
  impedance?: ImpedancePoint[];
  source_node?: number;
  sink_node?: number;
};

export type PdnMultiportCandidate = {
  id: string;
  location: {
    position_mm: [number, number];
    layer?: string;
    requested_layer?: string;
    resolved_layer?: string;
    connected_layers?: string[];
    mesh_node?: number;
  };
  source_result_id: string;
  endpoint_reviewed: boolean;
  reciprocal: boolean;
  model_status: string;
  local_impedance: ImpedancePoint[];
  transfer_impedance: ImpedancePoint[];
  reverse_transfer_impedance: ImpedancePoint[];
};

export type PdnMultiportResult = {
  contract: "spike/pdn-multiport/v1" | string;
  model_status: string;
  net: string;
  source_result_id: string;
  reference: { kind: string; mesh_node?: number };
  ports: { id: string; role: "observation" | "candidate" | string; node?: number; endpoint_reviewed?: boolean }[];
  observation_impedance: ImpedancePoint[];
  candidates: PdnMultiportCandidate[];
  z_parameters: {
    frequency_hz: number;
    resistance_ohm: number[][];
    reactance_ohm: number[][];
  }[];
  quality?: {
    maximum_reciprocity_error?: number;
    minimum_passivity_eigenvalue_ohm?: number;
    maximum_relative_residual?: number;
    maximum_sampled_condition_number?: number | null;
  };
  validity?: { scope?: string; limits?: string[] };
};

export type PdnCandidateRequest = {
  id: string;
  capacitance_f: number;
  esr_ohm: number;
  esl_h: number;
  count: number;
  mounting_resistance_ohm: number;
  mounting_inductance_h: number;
  location?: PdnMultiportCandidate["location"];
  source_result_id?: string;
  endpoint_reviewed?: boolean;
  reciprocal?: boolean;
  model_status?: string;
  local_impedance?: ImpedancePoint[];
  transfer_impedance?: ImpedancePoint[];
  reverse_transfer_impedance?: ImpedancePoint[];
};

export type CouplingRisk = {
  victim_net: string;
  aggressor_net: string;
  status: "pass" | "warning" | "fail" | "unsupported";
  peak_coupled_voltage_v?: number;
  next_db?: number;
  fext_db?: number;
  detail?: string;
};

export type PdnReview = {
  contract: string;
  status: "pass" | "violated";
  model_status: string;
  net: string;
  target_ohm: number;
  maximum_impedance_ohm: number;
  violation_count: number;
  resonances: { frequency_hz: number; magnitude_ohm: number }[];
  anti_resonances: { frequency_hz: number; magnitude_ohm: number }[];
  candidate_screening: {
    id: string;
    status: "evaluated" | "rejected";
    placement_method: "direct_port_shunt" | "series_connection_path" | "multiport_impedance_loading" | "invalid";
    model_status: string;
    worst_impedance_ohm?: number;
    worst_frequency_hz?: number;
    worst_target_ratio?: number;
    worst_impedance_improvement_percent?: number;
    maximum_local_degradation_percent?: number;
    violation_count?: number;
    passes_target: boolean;
    issues?: { code: string; severity: string; message: string }[];
  }[];
  candidate_method_counts?: Record<string, number>;
  best_candidate_id?: string | null;
};

export type ResultFrame = {
  time_s: number;
  scalar_fields?: Partial<SolverResultBundle["scalar_fields"]>;
  vector_fields?: Partial<SolverResultBundle["vector_fields"]>;
  scalar_values?: Record<string, number[]>;
  vector_values?: Record<string, number[]>;
  mesh?: MeshCell[];
};

export type ComponentStress = {
  component_id: string;
  reference: string;
  peak_voltage_v: number;
  peak_current_a: number;
  rms_current_a: number;
  peak_power_w: number;
  average_power_w: number;
  ratings: Record<string, number>;
  utilization: Record<string, number | null>;
  status: string;
};

export type SolverResultBundle = {
  contract: string;
  analysis_id: string;
  status: string;
  mode: string;
  model_status: string;
  summary: Record<string, unknown>;
  scalar_fields: {
    voltage_v: ScalarSample[];
    voltage_drop_v: ScalarSample[];
    current_a: ScalarSample[];
    operating_point_impedance_ohm: ScalarSample[];
    current_density_a_mm2: ScalarSample[];
    power_loss_w: ScalarSample[];
    via_current_density_a_mm2: ScalarSample[];
  };
  vector_fields: {
    current_density: VectorSample[];
    electric_field: VectorSample[];
    magnetic_field: VectorSample[];
  };
  mesh: MeshCell[];
  component_bridges: ComponentBridge[];
  parasitics: ParasiticResult[];
  pdn_multiports: PdnMultiportResult[];
  loop_parasitics: Array<{
    contract: "spike/loop-parasitics/v1";
    id: string;
    name: string;
    model_status: string;
    forward_nets: string[];
    return_nets: string[];
    geometry_resistance_ohm: number;
    geometry_loop_inductance_h: number;
    component_resistance_ohm: number;
    component_inductance_h: number;
    component_series_capacitance_f: number | null;
    total_loop_inductance_h: number;
    estimated_net_capacitance_f: number | null;
    capacitance_model_status: string;
    impedance: ImpedancePoint[];
    conductors: Record<string, unknown>[];
    component_models: Record<string, unknown>[];
    quality: Record<string, unknown>;
    validity: Record<string, unknown>;
  }>;
  coupling_risks: CouplingRisk[];
  time_series: {
    contract?: string;
    times_s: number[];
    frames: ResultFrame[];
    layouts?: Record<string, SampleLayout[]>;
    field_layouts?: Record<string, string>;
    vector_layouts?: Record<string, string>;
    vector_directions?: Record<string, [number, number, number][]>;
  };
  component_stress: ComponentStress[];
  probes: {
    id: string;
    name?: string;
    net?: string;
    layer?: string;
    status?: string;
    position_mm?: [number, number];
    voltage_v?: number;
    voltage_drop_v?: number;
    peak_adjacent_current_density_a_mm2?: number;
    peak_adjacent_current_a?: number;
    adjacent_power_loss_w?: number;
    local_series_resistance_ohm?: number;
    message?: string;
  }[];
  issues: { code?: string; severity?: string; message?: string; status?: string }[];
  provenance: Record<string, unknown>;
};

export type ResultVisualization = {
  visible: boolean;
  mode: ResultViewMode;
  analysisOnly: boolean;
  boardOpacity: number;
  showVectors: boolean;
  vectorScale: number;
  viaModel: ViaModel;
  translucentScene: boolean;
  sceneMode: "opaque" | "translucent" | "analysis_only" | "results_only";
  showComponentModels: boolean;
  plotStyle: "flat" | "height" | "contour";
  fieldStyle: "cells" | "smooth";
  waveHeightScale: number;
  fusingAmbientC: number;
  fusingDurationS: number;
  animationPlaying: boolean;
  animationFrame: number;
  animationFps: number;
  impedanceFrequencyHz: number | null;
  visibleResultLayers: string[];
};

export const defaultResultVisualization = (): ResultVisualization => ({
  visible: true,
  mode: "geometry",
  analysisOnly: false,
  boardOpacity: 0.18,
  showVectors: false,
  vectorScale: 1,
  viaModel: "extracted",
  translucentScene: false,
  sceneMode: "opaque",
  showComponentModels: true,
  plotStyle: "flat",
  fieldStyle: "cells",
  waveHeightScale: 1,
  fusingAmbientC: 25,
  fusingDurationS: 1,
  animationPlaying: false,
  animationFrame: 0,
  animationFps: 12,
  impedanceFrequencyHz: null,
  visibleResultLayers: [],
});

const finite = (value: unknown, fallback = 0) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
};

const scalar = (item: Record<string, unknown>, key: string): ScalarSample => ({
  x_mm: finite(item.x_mm),
  y_mm: finite(item.y_mm),
  z_mm: item.z_mm === undefined ? undefined : finite(item.z_mm),
  layer: typeof item.layer === "string" ? item.layer : undefined,
  net: typeof item.net === "string" ? item.net : typeof item.net_name === "string" ? item.net_name : undefined,
  element_id: typeof item.element_id === "string" ? item.element_id : typeof item.id === "string" ? item.id : undefined,
  source_id: typeof item.source_id === "string" ? item.source_id : undefined,
  width_mm: item.width_mm === undefined ? undefined : finite(item.width_mm),
  kind: typeof item.kind === "string" ? item.kind : undefined,
  source_kind: typeof item.source_kind === "string" ? item.source_kind : undefined,
  vertices_mm: Array.isArray(item.vertices_mm)
    ? item.vertices_mm
      .filter(vertex => Array.isArray(vertex) && vertex.length >= 3)
      .map(vertex => [finite(vertex[0]), finite(vertex[1]), finite(vertex[2])] as [number, number, number])
    : undefined,
  value: finite(item[key] ?? item.value),
});

const vectors = (value: unknown, valueKey: string): VectorSample[] =>
  Array.isArray(value) ? value.map(raw => {
    const item = raw as Record<string, unknown>;
    const rawVector = Array.isArray(item.vector) ? item.vector : [item.x, item.y, item.z];
    const vector: [number, number, number] = [finite(rawVector[0]), finite(rawVector[1]), finite(rawVector[2])];
    const magnitude = finite(item.magnitude, Math.hypot(...vector));
    return { ...scalar(item, valueKey), vector, magnitude };
  }) : [];

const bridgePoint = (value: unknown): [number, number, number] | null =>
  Array.isArray(value) && value.length >= 3
    && value.slice(0, 3).every(item => Number.isFinite(Number(item)))
    ? [finite(value[0]), finite(value[1]), finite(value[2])]
    : null;

const componentBridges = (value: unknown): ComponentBridge[] => !Array.isArray(value) ? [] : value.flatMap(raw => {
  if (!raw || typeof raw !== "object") return [];
  const item = raw as Record<string, unknown>;
  const vertices = Array.isArray(item.vertices_mm)
    ? item.vertices_mm.map(bridgePoint).filter((point): point is [number, number, number] => point !== null)
    : [];
  const startMm = Array.isArray(item.start_mm) ? item.start_mm : [];
  const endMm = Array.isArray(item.end_mm) ? item.end_mm : [];
  const start = vertices[0] ?? bridgePoint([startMm[0], startMm[1], item.start_z_mm]);
  const end = vertices[1] ?? bridgePoint([endMm[0], endMm[1], item.end_z_mm]);
  if (!start || !end) return [];
  return [{
    id: typeof item.id === "string" ? item.id : `component-bridge-${start.join("-")}-${end.join("-")}`,
    topology: typeof item.topology === "string" ? item.topology : "line2",
    representation: "electrical_equivalent_line",
    vertices_mm: [start, end],
    component_ref: typeof item.component_ref === "string" ? item.component_ref : undefined,
    component_id: typeof item.component_id === "string" ? item.component_id : undefined,
    from_net: typeof item.from_net === "string" ? item.from_net : undefined,
    to_net: typeof item.to_net === "string" ? item.to_net : undefined,
    from_layer: typeof item.from_layer === "string" ? item.from_layer : undefined,
    to_layer: typeof item.to_layer === "string" ? item.to_layer : undefined,
    resistance_ohm: item.resistance_ohm === undefined ? undefined : finite(item.resistance_ohm),
    current_a: item.current_a === undefined ? undefined : finite(item.current_a),
    voltage_drop_v: item.voltage_drop_v === undefined ? undefined : finite(item.voltage_drop_v),
    power_loss_w: item.power_loss_w === undefined ? undefined : finite(item.power_loss_w),
    model_ref: typeof item.model_ref === "string" ? item.model_ref : undefined,
    geometry_model: typeof item.geometry_model === "string" ? item.geometry_model : undefined,
    // A line equivalent cannot truthfully carry a spatial current density.
    current_density_supported: false,
  }];
});

export function normalizeSolverResult(raw: unknown): SolverResultBundle | null {
  if (!raw || typeof raw !== "object") return null;
  const result = raw as Record<string, unknown>;
  const directScalars = result.scalar_fields as SolverResultBundle["scalar_fields"] | undefined;
  const directVectors = result.vector_fields as SolverResultBundle["vector_fields"] | undefined;
  if (directScalars && directVectors
    && Array.isArray(directScalars.voltage_v)
    && Array.isArray(directScalars.voltage_drop_v)
    && Array.isArray(directScalars.current_density_a_mm2)) {
    const directSeries = result.time_series && typeof result.time_series === "object"
      ? result.time_series as SolverResultBundle["time_series"]
      : { times_s: [], frames: [] };
    const directNetworks = result.networks && typeof result.networks === "object"
      ? result.networks as Record<string, unknown>
      : {};
    const directParasitics = Array.isArray(result.parasitics)
      ? result.parasitics as ParasiticResult[]
      : Array.isArray(directNetworks.parasitics)
        ? directNetworks.parasitics as ParasiticResult[]
        : [];
    return {
      ...(result as unknown as SolverResultBundle),
      scalar_fields: {
        ...directScalars,
        current_a: Array.isArray(directScalars.current_a) ? directScalars.current_a : [],
        operating_point_impedance_ohm: Array.isArray(directScalars.operating_point_impedance_ohm) ? directScalars.operating_point_impedance_ohm : [],
        power_loss_w: Array.isArray(directScalars.power_loss_w) ? directScalars.power_loss_w : [],
        via_current_density_a_mm2: Array.isArray(directScalars.via_current_density_a_mm2) ? directScalars.via_current_density_a_mm2 : [],
      },
      component_bridges: componentBridges(result.component_bridges),
      time_series: {
        contract: directSeries.contract,
        times_s: Array.isArray(directSeries.times_s) ? directSeries.times_s.map(value => finite(value)) : [],
        frames: Array.isArray(directSeries.frames) ? directSeries.frames : [],
        layouts: directSeries.layouts,
        field_layouts: directSeries.field_layouts,
        vector_layouts: directSeries.vector_layouts,
        vector_directions: directSeries.vector_directions,
      },
      component_stress: Array.isArray(result.component_stress) ? result.component_stress as ComponentStress[] : [],
      parasitics: directParasitics,
      pdn_multiports: Array.isArray(result.pdn_multiports)
        ? result.pdn_multiports as PdnMultiportResult[]
        : Array.isArray(directNetworks.pdn_multiports)
          ? directNetworks.pdn_multiports as PdnMultiportResult[]
          : [],
      loop_parasitics: Array.isArray(result.loop_parasitics)
        ? result.loop_parasitics as SolverResultBundle["loop_parasitics"]
        : Array.isArray(directNetworks.loop_parasitics)
          ? directNetworks.loop_parasitics as SolverResultBundle["loop_parasitics"]
          : [],
      coupling_risks: Array.isArray(result.coupling_risks)
        ? result.coupling_risks as CouplingRisk[]
        : Array.isArray(directNetworks.coupling_risks)
          ? directNetworks.coupling_risks as CouplingRisk[]
          : [],
    };
  }
  const fields = (result.fields && typeof result.fields === "object" ? result.fields : {}) as Record<string, unknown>;
  const nodeVoltages = Array.isArray(fields.node_voltages) ? fields.node_voltages as Record<string, unknown>[] : [];
  const edgeResults = Array.isArray(fields.edge_results) ? fields.edge_results as Record<string, unknown>[] : [];
  const visualization = (fields.visualization && typeof fields.visualization === "object" ? fields.visualization : {}) as Record<string, unknown>;
  const scalarFields = (visualization.scalar_fields && typeof visualization.scalar_fields === "object" ? visualization.scalar_fields : {}) as Record<string, unknown>;
  const vectorFields = (visualization.vector_fields && typeof visualization.vector_fields === "object" ? visualization.vector_fields : {}) as Record<string, unknown>;
  const rawSeries = (result.time_series && typeof result.time_series === "object"
    ? result.time_series
    : visualization.time_series && typeof visualization.time_series === "object" ? visualization.time_series : {}) as Record<string, unknown>;
  const rawFrames = Array.isArray(rawSeries.frames) ? rawSeries.frames as Record<string, unknown>[] : [];
  const voltageSamples = nodeVoltages.map(item => scalar(item, "voltage_v"));
  const sourceVoltage = finite((result.summary as Record<string, unknown> | undefined)?.source_voltage_v, numericMaximum(voltageSamples.map(item => item.value), 0));
  const edgeScalars = (key: string) => edgeResults.map(item => scalar(item, key));
  const readScalars = (key: string) => Array.isArray(scalarFields[key])
    ? (scalarFields[key] as Record<string, unknown>[]).map(item => scalar(item, "value"))
    : [];
  return {
    contract: String(result.contract ?? "spike/v1"),
    analysis_id: String(result.analysis_id ?? ""),
    status: String(result.status ?? "failed"),
    mode: String(result.mode ?? "unknown"),
    model_status: String(result.model_status ?? "unsupported"),
    summary: (result.summary as Record<string, unknown>) ?? {},
    scalar_fields: {
      voltage_v: readScalars("voltage_v").length ? readScalars("voltage_v") : voltageSamples,
      voltage_drop_v: readScalars("voltage_drop_v").length
        ? readScalars("voltage_drop_v")
        : voltageSamples.map(item => ({ ...item, value: Math.max(0, sourceVoltage - item.value) })),
      current_a: readScalars("current_a").length
        ? readScalars("current_a")
        : readScalars("current_magnitude_a").length
          ? readScalars("current_magnitude_a")
          : edgeScalars("current_a"),
      operating_point_impedance_ohm: readScalars("operating_point_impedance_ohm"),
      current_density_a_mm2: readScalars("current_density_a_mm2").length
        ? readScalars("current_density_a_mm2")
        : edgeScalars("current_density_a_mm2"),
      power_loss_w: readScalars("power_loss_w").length
        ? readScalars("power_loss_w")
        : edgeScalars("power_loss_w"),
      via_current_density_a_mm2: readScalars("via_current_density_a_mm2"),
    },
    vector_fields: {
      current_density: vectors(vectorFields.current_density, "magnitude"),
      electric_field: vectors(vectorFields.electric_field, "magnitude"),
      magnetic_field: vectors(vectorFields.magnetic_field, "magnitude"),
    },
    mesh: Array.isArray(visualization.mesh) ? visualization.mesh as MeshCell[] : [],
    component_bridges: componentBridges(visualization.component_bridges),
    parasitics: Array.isArray(result.networks)
      ? result.networks as ParasiticResult[]
      : Array.isArray((result.networks as Record<string, unknown> | undefined)?.parasitics)
        ? (result.networks as Record<string, unknown>).parasitics as ParasiticResult[]
        : [],
    pdn_multiports: Array.isArray((result.networks as Record<string, unknown> | undefined)?.pdn_multiports)
      ? (result.networks as Record<string, unknown>).pdn_multiports as PdnMultiportResult[]
      : Array.isArray(result.pdn_multiports)
        ? result.pdn_multiports as PdnMultiportResult[]
        : [],
    loop_parasitics: Array.isArray((result.networks as Record<string, unknown> | undefined)?.loop_parasitics)
      ? (result.networks as Record<string, unknown>).loop_parasitics as SolverResultBundle["loop_parasitics"]
      : [],
    coupling_risks: Array.isArray((result.networks as Record<string, unknown> | undefined)?.coupling_risks)
      ? (result.networks as Record<string, unknown>).coupling_risks as CouplingRisk[]
      : [],
    time_series: {
      contract: typeof rawSeries.contract === "string" ? rawSeries.contract : undefined,
      times_s: Array.isArray(rawSeries.times_s) ? rawSeries.times_s.map(value => finite(value)) : rawFrames.map(frame => finite(frame.time_s)),
      frames: rawFrames.map(frame => ({
        time_s: finite(frame.time_s),
        scalar_fields: frame.scalar_fields as ResultFrame["scalar_fields"],
        vector_fields: frame.vector_fields as ResultFrame["vector_fields"],
        scalar_values: frame.scalar_values && typeof frame.scalar_values === "object" ? frame.scalar_values as ResultFrame["scalar_values"] : undefined,
        vector_values: frame.vector_values && typeof frame.vector_values === "object" ? frame.vector_values as ResultFrame["vector_values"] : undefined,
        mesh: Array.isArray(frame.mesh) ? frame.mesh as MeshCell[] : undefined,
      })),
      layouts: rawSeries.layouts && typeof rawSeries.layouts === "object" ? rawSeries.layouts as Record<string, SampleLayout[]> : undefined,
      field_layouts: rawSeries.field_layouts && typeof rawSeries.field_layouts === "object" ? rawSeries.field_layouts as Record<string, string> : undefined,
      vector_layouts: rawSeries.vector_layouts && typeof rawSeries.vector_layouts === "object" ? rawSeries.vector_layouts as Record<string, string> : undefined,
      vector_directions: rawSeries.vector_directions && typeof rawSeries.vector_directions === "object" ? rawSeries.vector_directions as Record<string, [number, number, number][]> : undefined,
    },
    component_stress: Array.isArray((result.networks as Record<string, unknown> | undefined)?.component_stress)
      ? (result.networks as Record<string, unknown>).component_stress as ComponentStress[]
      : [],
    probes: Array.isArray(result.probes) ? result.probes as SolverResultBundle["probes"] : [],
    issues: Array.isArray(result.issues) ? result.issues as SolverResultBundle["issues"] : [],
    provenance: (result.provenance as Record<string, unknown>) ?? {},
  };
}

export type FrameFieldSelection = {
  scalarFields?: readonly string[];
  vectorFields?: readonly string[];
};

// Count newly allocated sample objects, including each vector's direction array.
// Retain at most one oversized active frame so repeated paints still reuse it.
const MAX_CACHED_FRAME_SAMPLE_UNITS = 250_000;
const materializedFrameCache = new WeakMap<SolverResultBundle, Map<string, { result: SolverResultBundle; cost: number }>>();

export function resultAtFrame(
  result: SolverResultBundle | null,
  frameIndex: number,
  selection?: FrameFieldSelection,
): SolverResultBundle | null {
  if (!result?.time_series.frames.length) return result;
  const boundedFrame = Math.max(0, Math.min(frameIndex, result.time_series.frames.length - 1));
  const scalarSelection = selection?.scalarFields ? new Set(selection.scalarFields) : null;
  const vectorSelection = selection?.vectorFields ? new Set(selection.vectorFields) : null;
  const cacheKey = `${boundedFrame}|${selection?.scalarFields?.join(",") ?? "*"}|${selection?.vectorFields?.join(",") ?? "*"}`;
  const existingCache = materializedFrameCache.get(result);
  const cached = existingCache?.get(cacheKey);
  if (cached) {
    existingCache!.delete(cacheKey);
    existingCache!.set(cacheKey, cached);
    return cached.result;
  }
  const frame = result.time_series.frames[boundedFrame];
  const layouts = result.time_series.layouts ?? {};
  const fieldLayouts = result.time_series.field_layouts ?? {};
  const compactScalars = Object.fromEntries(Object.entries(frame.scalar_values ?? {}).filter(([field]) => (!scalarSelection || scalarSelection.has(field)) && !Object.prototype.hasOwnProperty.call(frame.scalar_fields ?? {}, field)).map(([field, values]) => {
    const layout = layouts[fieldLayouts[field] ?? field] ?? [];
    const samples = new Array<ScalarSample>(Math.min(layout.length, values.length));
    for (let index = 0; index < samples.length; index++) samples[index] = { ...layout[index], value: finite(values[index]) };
    return [field, samples];
  })) as Partial<SolverResultBundle["scalar_fields"]>;
  const vectorLayouts = result.time_series.vector_layouts ?? {};
  const compactVectors = Object.fromEntries(Object.entries(frame.vector_values ?? {}).filter(([field]) => (!vectorSelection || vectorSelection.has(field)) && !Object.prototype.hasOwnProperty.call(frame.vector_fields ?? {}, field)).map(([field, values]) => {
    const layout = layouts[vectorLayouts[field] ?? field] ?? [];
    const directions = result.time_series.vector_directions?.[field] ?? [];
    return [field, Array.from({ length: Math.min(layout.length, values.length) }, (_, index) => {
      const signed = finite(values[index]);
      const direction = directions[index] ?? [0, 0, 0];
      return {
        ...layout[index],
        value: Math.abs(signed),
        magnitude: Math.abs(signed),
        vector: [direction[0] * signed, direction[1] * signed, direction[2] * signed] as [number, number, number],
      };
    })];
  })) as Partial<SolverResultBundle["vector_fields"]>;
  const explicitScalars = scalarSelection
    ? Object.fromEntries(Object.entries(frame.scalar_fields ?? {}).filter(([field]) => scalarSelection.has(field)))
    : frame.scalar_fields ?? {};
  const explicitVectors = vectorSelection
    ? Object.fromEntries(Object.entries(frame.vector_fields ?? {}).filter(([field]) => vectorSelection.has(field)))
    : frame.vector_fields ?? {};
  const materialized: SolverResultBundle = {
    ...result,
    scalar_fields: { ...result.scalar_fields, ...compactScalars, ...explicitScalars },
    vector_fields: { ...result.vector_fields, ...compactVectors, ...explicitVectors },
    mesh: frame.mesh ?? result.mesh,
    summary: { ...result.summary, active_time_s: frame.time_s, active_frame: boundedFrame },
  };
  let cache = materializedFrameCache.get(result);
  if (!cache) {
    cache = new Map();
    materializedFrameCache.set(result, cache);
  }
  const cost = Object.values(compactScalars).reduce((sum, values) => sum + values.length, 0)
    + Object.values(compactVectors).reduce((sum, values) => sum + values.length * 2, 0);
  cache.set(cacheKey, { result: materialized, cost });
  let retainedCost = [...cache.values()].reduce((sum, entry) => sum + entry.cost, 0);
  while (cache.size > 1 && (cache.size > 4 || retainedCost > MAX_CACHED_FRAME_SAMPLE_UNITS)) {
    const oldest = cache.keys().next().value!;
    retainedCost -= cache.get(oldest)!.cost;
    cache.delete(oldest);
  }
  return materialized;
}

export const resultModeAvailable = (result: SolverResultBundle | null, mode: ResultViewMode) => {
  if (mode === "geometry") return true;
  if (!result) return false;
  if (mode === "mesh") return result.mesh.length > 0;
  if (mode === "voltage") return result.scalar_fields.voltage_v.length > 0;
  if (mode === "voltage_drop") return result.scalar_fields.voltage_drop_v.length > 0;
  if (mode === "current") return result.scalar_fields.current_a.length > 0;
  if (mode === "current_density") return result.scalar_fields.current_density_a_mm2.length > 0;
  if (mode === "power_loss") return result.scalar_fields.power_loss_w.length > 0;
  if (mode === "via_stress") return result.scalar_fields.via_current_density_a_mm2.length > 0;
  if (mode === "impedance") return result.scalar_fields.operating_point_impedance_ohm.length > 0
    || result.parasitics.some(item => Boolean(item.impedance?.length))
    || result.loop_parasitics.some(item => Boolean(item.impedance?.length));
  if (mode === "electric_field") return result.vector_fields.electric_field.length > 0;
  return result.vector_fields.magnetic_field.length > 0;
};
import { numericMaximum } from "./numericRange";
