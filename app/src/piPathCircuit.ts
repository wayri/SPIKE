import type { CompiledPiPath } from "./piPath";

type JsonRecord = Record<string, unknown>;

export type PiPathAnalysisRequest = {
  contract: string;
  design: JsonRecord;
  spec: JsonRecord;
};

export type PiPathSegmentExtraction = {
  segmentId: string;
  net: string;
  fromPadId: string;
  toPadId: string;
  request: PiPathAnalysisRequest;
};

export type PiPathExtractionBundle = {
  extraction_result: JsonRecord;
  segment_mappings: Array<{
    segment_id: string;
    network_index: number;
    from_pad_id: string;
    to_pad_id: string;
    endpoint_reviewed: true;
  }>;
};

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function expectedPads(path: CompiledPiPath, index: number): [string, string] {
  const from = index === 0 ? path.source_terminal.pad_id : path.transitions[index - 1]?.output_pad_id;
  const to = index === path.segments.length - 1 ? path.load_terminal.pad_id : path.transitions[index]?.input_pad_id;
  if (!from || !to) throw new Error(`Path segment ${path.segments[index]?.net ?? index + 1} has incomplete reviewed pad endpoints.`);
  return [from, to];
}

function endpointTerminal(source: JsonRecord, net: string, pad: JsonRecord, role: "source" | "load"): JsonRecord {
  const padId = String(pad.id ?? "");
  if (!padId || pad.net_name !== net) throw new Error(`Reviewed ${role} pad ${padId || "is missing"} does not belong to ${net}.`);
  return {
    ...source,
    id: `${role}-${padId}`,
    name: `${role === "source" ? "Segment source" : "Segment load"} ${padId}`,
    net,
    position_mm: pad.at,
    layer_scope: "connected_conductor",
    layer_candidates: array(pad.layers),
    geometry_anchor: { id: padId, type: "pad" },
    terminal_role: role === "source" ? "source_positive" : "load_positive",
    ...(role === "source" ? { voltage_v: 1, ac_magnitude_v: 1 } : { current_a: 1, ac_magnitude_a: 1 }),
  };
}

/** Build one exact pad-to-pad PEEC request for every ordered copper segment. */
export function createPiPathSegmentExtractionRequests(
  baseRequest: PiPathAnalysisRequest,
  path: CompiledPiPath,
): PiPathSegmentExtraction[] {
  if (!path.segments.length || path.transitions.length !== path.segments.length - 1) {
    throw new Error("A reviewed series path must contain every copper segment and transition before extraction.");
  }
  const baseSpec = record(baseRequest.spec);
  const baseOptions = record(baseSpec.options);
  const baseSources = array(baseSpec.sources).map(record);
  const baseLoads = array(baseSpec.loads).map(record);
  const sourceTemplate = baseSources.find(item => item.terminal_role === "source_positive") ?? baseSources[0] ?? {};
  const loadTemplate = baseLoads.find(item => item.terminal_role === "load_positive") ?? baseLoads[0] ?? {};
  const pads = array(record(baseRequest.design).pads).map(record);
  const padById = new Map(pads.map(pad => [String(pad.id ?? ""), pad]));

  return path.segments.map((segment, index) => {
    const [fromPadId, toPadId] = expectedPads(path, index);
    const options: JsonRecord = {
      ...baseOptions,
      loop_extractions: [],
      pdn_candidate_ports: [],
      coupling: { ...record(baseOptions.coupling), enabled: false },
      path_segment_extraction: {
        contract: "spike/pi-path-segment-extraction/v1",
        path_id: path.id,
        segment_id: segment.id,
        from_pad_id: fromPadId,
        to_pad_id: toPadId,
        endpoint_reviewed: true,
      },
    };
    delete options.pi_path;
    const fromPad = padById.get(fromPadId);
    const toPad = padById.get(toPadId);
    if (!fromPad || !toPad) throw new Error(`${segment.net} segment endpoints do not resolve to imported board pads.`);
    const spec: JsonRecord = {
      ...baseSpec,
      mode: "ac",
      solver_id: "spike.peec_2_5d",
      formulation: "peec_2_5d",
      required_capabilities: ["frequency_dependent_impedance", "partial_inductance"],
      net_names: [segment.net],
      sources: [endpointTerminal(sourceTemplate, segment.net, fromPad, "source")],
      loads: [endpointTerminal(loadTemplate, segment.net, toPad, "load")],
      return_path: { ...record(baseSpec.return_path), mode: "implicit" },
      probes: [],
      options,
    };
    return {
      segmentId: segment.id,
      net: segment.net,
      fromPadId,
      toPadId,
      request: { ...baseRequest, spec },
    };
  });
}

function analysisResult(value: unknown): JsonRecord {
  const candidate = record(value);
  return record(candidate.analysis_result ?? candidate.result ?? candidate);
}

/** Combine reviewed segment PEEC outputs without inferring or reusing a network. */
export function combinePiPathSegmentExtractions(
  path: CompiledPiPath,
  extractions: readonly unknown[],
): PiPathExtractionBundle {
  if (extractions.length !== path.segments.length) {
    throw new Error(`Expected ${path.segments.length} segment extraction results, received ${extractions.length}.`);
  }
  const parasitics: JsonRecord[] = [];
  const mappings: PiPathExtractionBundle["segment_mappings"] = [];
  const statuses = new Set<string>();
  const analysisIds: string[] = [];

  path.segments.forEach((segment, index) => {
    const result = analysisResult(extractions[index]);
    const networks = record(result.networks);
    const matches = array(networks.parasitics)
      .map(record)
      .filter(network => network.contract === "spike/rlgc-network/v1" && network.net === segment.net);
    if (matches.length !== 1) {
      throw new Error(`${segment.net} produced ${matches.length} matching reviewed RLCG networks; exactly one is required.`);
    }
    const [fromPadId, toPadId] = expectedPads(path, index);
    const networkIndex = parasitics.length;
    parasitics.push(matches[0]);
    mappings.push({
      segment_id: segment.id,
      network_index: networkIndex,
      from_pad_id: fromPadId,
      to_pad_id: toPadId,
      endpoint_reviewed: true,
    });
    if (typeof result.model_status === "string") statuses.add(result.model_status);
    if (typeof result.analysis_id === "string") analysisIds.push(result.analysis_id);
  });

  return {
    extraction_result: {
      contract: "spike/pi-path-segment-extraction-result/v1",
      analysis_id: `pi-path-extraction:${path.id}`,
      model_status: statuses.size === 1 ? [...statuses][0] : "experimental",
      networks: { parasitics },
      provenance: {
        path_id: path.id,
        segment_analysis_ids: analysisIds,
        endpoint_reviewed: true,
        topology_inference: false,
      },
    },
    segment_mappings: mappings,
  };
}

/** Merge segment readiness with the worker's canonical full-path preview. */
export function combinePiPathPreflights(preflights: readonly unknown[], pathPreflight?: unknown): JsonRecord {
  const results = preflights.map(record);
  const aggregate = record(pathPreflight);
  const aggregateMesh = record(aggregate.mesh);
  const segmentCells = results.flatMap(item => array(record(item.mesh).cells));
  const cells = array(aggregateMesh.cells).length ? array(aggregateMesh.cells) : segmentCells;
  const componentBridges = array(aggregateMesh.component_bridges);
  const issueKeys = new Set<string>();
  const issues = [...results.flatMap(item => array(item.issues)), ...array(aggregate.issues)].filter(item => {
    const issue = record(item);
    const key = `${String(issue.code ?? "")}|${String(issue.severity ?? "")}|${String(issue.message ?? "")}`;
    if (issueKeys.has(key)) return false;
    issueKeys.add(key);
    return true;
  });
  const errors = issues.filter(item => record(item).severity === "error").length;
  const segmentReady = results.length > 0 && results.every(item => item.can_solve === true);
  const aggregateReady = pathPreflight === undefined || aggregate.can_solve === true;
  return {
    contract: "spike/pi-path-preflight/v1",
    status: errors ? "blocked" : "ready",
    can_solve: segmentReady && aggregateReady && errors === 0,
    summary: {
      ...record(aggregate.summary),
      mesh_cell_count: cells.length,
      segment_count: results.length,
      component_bridge_count: componentBridges.length,
      errors,
      warnings: issues.filter(item => record(item).severity === "warning").length,
    },
    issues,
    mesh: {
      ...aggregateMesh,
      cells,
      component_bridges: componentBridges,
      dimension: String(aggregateMesh.dimension ?? "multi-segment"),
      quality: record(aggregateMesh.quality),
    },
  };
}

/** Preserve reviewed path-interface geometry in a circuit result without fabricating spatial fields. */
export function attachPiPathComponentBridges(result: JsonRecord, preflight: unknown): JsonRecord {
  const bridges = array(record(record(preflight).mesh).component_bridges);
  if (!bridges.length) return result;
  const fields = record(result.fields);
  const visualization = record(fields.visualization);
  const provenance = record(result.provenance);
  return {
    ...result,
    fields: {
      ...fields,
      visualization: {
        ...visualization,
        component_bridges: bridges,
      },
    },
    provenance: {
      ...provenance,
      component_bridge_contract: "spike/pi-path-interface-elements/v1",
      reviewed_component_bridge_count: bridges.length,
      component_bridge_spatial_field_inferred: false,
    },
  };
}
