// SPDX-License-Identifier: Apache-2.0
/** Fixed desktop analysis workflow. Worker contracts remain the numerical authority. */
export type McpLoadedContext = {
  design: Record<string, unknown> | null; canonicalDesign?: unknown; assembly?: unknown; assemblyDesigns?: unknown;
  assemblyScope?: unknown; sourceKiCadPcb?: string; boardBoundsMm?: number[]; boardFile?: string; activeDesignId?: string | null; extensions?: unknown[]; results?: unknown[];
};
type Response = { ok: boolean; result?: Record<string, unknown>; error?: string };
type Options = {
  callWorker: (request: { method: string; params: Record<string, unknown> }) => Promise<Response>;
  getContext: () => McpLoadedContext;
  admitScope?: (kind: string, parameters: Record<string, unknown>) => Promise<unknown>;
  publishResult?: (result: Record<string, unknown>, meta: { kind: string; caseId: string; jobId: string; scope: string; parameters: Record<string, unknown> }) => void | Promise<void>;
};
type Prepared = { id: string; kind: string; scope: string; parameters: Record<string, unknown>; binding: string; revision: number; preflightJobId?: string; runJobId?: string; preflight?: { revision: number; binding: string; ready: boolean; result: Record<string, unknown>; parameters: Record<string, unknown> } };
type Job = { id: string; caseId: string; phase: "preflight" | "solve"; status: string; result?: Record<string, unknown>; error?: string };
const rec = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const FLOWS: Record<string, { method: string; key: string; schema?: string; description: string }> = {
  studio_feedback: { method: "run_studio_board_cosimulation", key: "request", schema: "studio-board-feedback-request-v1.schema.json", description: "Explicit board-bound RLC/ideal-source electrical, lumped thermal and uniform conductor feedback. No inferred semiconductor losses or spatial FEM fields." },
  pi: { method: "run_preflighted_analysis", key: "spec", schema: "analysis-spec-v1.schema.json", description: "Loaded-board PI with worker solver admission and explicit sources, loads and return path." },
  si: { method: "run_si_uniform_channel", key: "request", schema: "si-uniform-channel-request-v1.schema.json", description: "Loaded uniform/piecewise geometry SI, explicit aggressor/victim and crosstalk port map for NEXT/FEXT; unsupported geometry stays blocked." },
  si_workflow: { method: "run_si_workflow", key: "request", schema: "si-workflow-request-v1.schema.json", description: "Explicit channel/source/receiver workflow with supported network analysis and optional time-domain eyes. User models are not inferred from board geometry." },
  ac_pi: { method: "analyze_ac_power_integrity", key: "request", schema: "ac-pi-request-v1.schema.json", description: "Experimental explicit uniform passive RLGC line, skin and imposed-field proximity losses, Ferranti voltage rise and resonances. No geometry extraction or inferred nearby fields." },
  thermal: { method: "estimate_thermal", key: "scenario", description: "Compact thermal estimate. Supply scenario.mode, ambient_temperature_c and heat_sources with power_w/theta_ja_c_per_w (thermal_capacitance_j_per_c for transient), or explicit thermal_elements/thermal_links. Worker validates the scenario; no CFD claim." },
  board_thermal: { method: "run_board_thermal", key: "request", schema: "board-thermal-request-v1.schema.json", description: "Board thermal solve from explicit board material, heat and boundary parameters." },
  em: { method: "emi_screen", key: "setup", schema: "emi-setup-v1.schema.json", description: "Electrical EMI risk screening; radiation and field solving require a supported extension." },
  extension: { method: "invoke_extension", key: "parameters", description: "A trusted installed analysis contribution, using its published input schema and safe preparation path. No trust, scripts or arbitrary worker dispatch." },
  multiboard_pi: { method: "run_multiboard_circuit", key: "request", schema: "multiboard-circuit-request-v1.schema.json", description: "Explicit reduced circuit model and link/contact values bound to the loaded assembly." },
  multiboard_si: { method: "run_multiboard_circuit", key: "request", schema: "multiboard-circuit-request-v1.schema.json", description: "Reduced assembly AC circuit model; this is not coupled full-wave board extraction." },
  multiboard_thermal: { method: "run_multiboard_thermal", key: "request", schema: "multiboard-thermal-request-v1.schema.json", description: "Assembly-bound explicit reduced heat-flow/contact network." },
  multiboard_em: { method: "run_multiboard_em", key: "request", schema: "multiboard-em-request-v1.schema.json", description: "Assembly-bound explicit mutual-inductance loop model, not full-wave assembly radiation." },
};
function safeObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Parameters must be an object.");
  const text = JSON.stringify(value);
  if (text.length > 1024 * 1024) throw new Error("Parameters exceed the 1 MiB limit.");
  const inspect = (item: unknown, depth: number) => {
    if (depth > 20) throw new Error("Parameters are too deeply nested.");
    if (typeof item === "number" && !Number.isFinite(item)) throw new Error("Parameters must contain finite numbers.");
    if (item && typeof item === "object") for (const [key, child] of Object.entries(item)) { if (["__proto__", "constructor", "prototype"].includes(key)) throw new Error("Unsafe parameter key."); inspect(child, depth + 1); }
  };
  inspect(value, 0);
  return JSON.parse(text) as Record<string, unknown>;
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(",")}}`;
  return JSON.stringify(value) ?? "null";
}
async function sha(value: unknown) { return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(typeof value === "string" ? value : canonical(value)))), byte => byte.toString(16).padStart(2, "0")).join(""); }
async function binding(context: McpLoadedContext) { return sha({ design: context.design, canonicalDesign: context.canonicalDesign, assembly: context.assembly, assemblyDesigns: context.assemblyDesigns, assemblyScope: context.assemblyScope, sourceKiCadPcb: context.sourceKiCadPcb, activeDesignId: context.activeDesignId }); }
function nets(context: McpLoadedContext): string[] {
  const values: string[] = [];
  for (const design of [rec(context.design), rec(context.canonicalDesign)]) {
    const declared = Array.isArray(design.nets) ? design.nets : Object.values(rec(design.nets));
    values.push(...declared.map(value => typeof value === "string" ? value : String(rec(value).name ?? rec(value).net_name ?? "")));
    for (const key of ["tracks", "pads", "zones"]) if (Array.isArray(design[key])) for (const item of design[key] as unknown[]) { const row = rec(item); const name = row.net_name ?? row.net; if (typeof name === "string") values.push(name); }
  }
  return [...new Set(values.filter(Boolean))].sort();
}
function physicalAssembly(value: unknown) { const assembly = rec(value), extensions = { ...rec(assembly.extensions) }; delete extensions["spike.multiboard-studies"]; return { ...assembly, extensions }; }
function checkedParameters(kind: string, value: unknown) { const parameters = safeObject(value), allowed = kind === "extension" ? ["extension_id", "contribution_id", "parameters"] : [FLOWS[kind].key]; if (Object.keys(parameters).some(key => !allowed.includes(key))) throw new Error("Unknown analysis parameter; consult analysis_describe and the published schema."); return parameters; }
function missingInputs(item: Prepared, context: McpLoadedContext): string[] {
  const flow = FLOWS[item.kind], input = rec(item.parameters[flow.key]), missing: string[] = [];
  if (!Object.keys(input).length) missing.push(flow.key);
  if (item.kind === "pi") for (const key of ["solver_id", "mode", "net_names", "sources", "loads", "return_path"]) if (input[key] === undefined) missing.push(`spec.${key}`);
  if (item.kind === "si") {
    for (const key of ["contract", "signal_net", "reference_net", "reference_layer", "frequencies_hz", "reference_impedance_ohm"]) if (input[key] === undefined) missing.push(`request.${key}`);
    if (input.crosstalk_model && !input.victim_net) missing.push("request.victim_net");
    const known = nets(context);
    for (const key of ["signal_net", "victim_net", "reference_net"]) if (typeof input[key] === "string" && !known.includes(input[key] as string)) missing.push(`request.${key}: net is not present in the loaded board`);
    if (!context.canonicalDesign) missing.push("loaded canonical SpiDeR v2");
  }
  if (item.kind === "ac_pi") {
    for (const key of ["contract", "frequencies_hz", "length_m", "R_ohm_per_m", "L_h_per_m", "G_s_per_m", "C_f_per_m", "source_impedance_ohm", "load_impedance_ohm"]) if (input[key] === undefined) missing.push(`request.${key}`);
  }
  if (item.kind === "si_workflow") {
    for (const key of ["contract", "channel", "sources", "receivers", "run_time_domain"]) if (input[key] === undefined) missing.push(`request.${key}`);
    if (input.run_time_domain === true) for (const key of ["bit_rate_hz", "bit_count"]) if (input[key] === undefined) missing.push(`request.${key}`);
    for (const [role, required] of [["sources", ["port", "resistance_ohm", "low_v", "high_v", "rise_time_s", "fall_time_s"]], ["receivers", ["port", "resistance_ohm", "capacitance_f"]]] as const) {
      const endpoints = input[role];
      if (Array.isArray(endpoints)) endpoints.forEach((endpoint, index) => { if (!rec(endpoint).ibis) for (const key of required) if (rec(endpoint)[key] === undefined) missing.push(`request.${role}.${index}.${key}`); });
    }
    if (rec(input.channel).kind === "geometry" && !context.canonicalDesign) missing.push("loaded canonical SpiDeR v2");
  }
  if (item.kind === "studio_feedback") {
    for (const key of ["contract", "netlist", "board_revision", "mode", "bindings", "thermal", "controls"]) if (input[key] === undefined) missing.push(`request.${key}`);
  }
  if (item.kind === "thermal") {
    for (const key of ["mode", "ambient_temperature_c"]) if (input[key] === undefined) missing.push(`scenario.${key}`);
    const sources = Array.isArray(input.heat_sources) && input.heat_sources.length ? input.heat_sources : Array.isArray(input.thermal_elements) ? input.thermal_elements : [];
    if (!sources.length) missing.push("scenario.heat_sources or scenario.thermal_elements");
    sources.forEach((source, index) => {
      if (rec(source).power_w === undefined) missing.push(`scenario.heat_sources/thermal_elements.${index}.power_w`);
      if (Array.isArray(input.heat_sources) && input.heat_sources.length) {
        if (rec(source).theta_ja_c_per_w === undefined) missing.push(`scenario.heat_sources.${index}.theta_ja_c_per_w`);
        if (input.mode === "transient" && rec(source).thermal_capacitance_j_per_c === undefined) missing.push(`scenario.heat_sources.${index}.thermal_capacitance_j_per_c`);
      }
    });
  }
  if (item.kind === "board_thermal") {
    for (const key of ["board", "components", "ambient_temperature_c"]) if (input[key] === undefined) missing.push(`request.${key}`);
    const board = rec(input.board);
    for (const key of ["model", "thickness_mm", "grid_step_mm", "convection_top_w_m2k", "convection_bottom_w_m2k", ...(board.model === "layered" ? ["dielectric_conductivity_w_mk", "copper_conductivity_w_mk", "include_copper", "include_vias", "include_tracks", "include_pads", "include_zones", "fuzzy_sigma_mm", ...(board.include_vias === true ? ["via_plating_thickness_mm"] : [])] : ["conductivity_w_mk"])]) if (board[key] === undefined) missing.push(`request.board.${key}`);
    if (!Array.isArray(input.components) || !input.components.length) missing.push("request.components (nonempty)");
    if (Array.isArray(input.components)) input.components.forEach((value, index) => {
      const component = rec(value);
      for (const key of ["component_ref", "power_w", "r_junction_case_k_w", "r_case_board_k_w", "contact_mode", ...(component.contact_mode === "square" ? ["contact_size_mm"] : [])]) if (component[key] === undefined) missing.push(`request.components.${index}.${key}`);
    });
    if (input.transient !== undefined) for (const key of ["end_time_s", "time_step_s", "output_stride", "copper_volumetric_heat_capacity_j_m3k", "dielectric_volumetric_heat_capacity_j_m3k"]) if (rec(input.transient)[key] === undefined) missing.push(`request.transient.${key}`);
  }
  if (item.kind === "em") for (const key of ["contract", "selected_nets", "return_nets", "requested_analyses", "frequency", "environment", "mesh", "max_solver_time_s", "excitation", "net_metrics"]) if (input[key] === undefined) missing.push(`setup.${key}`);
  if (item.scope === "reduced_assembly") {
    if (!context.assembly) missing.push("loaded AssemblyIR");
    if (canonical(physicalAssembly(input.assembly)) !== canonical(physicalAssembly(context.assembly))) missing.push("request.assembly must match the loaded assembly physics");
    const required = item.kind === "multiboard_em" ? ["contract", "loops", "mutual_inductances", "frequency_hz", "connector_models"] : item.kind === "multiboard_thermal" ? ["contract", "mode", "ambient_temperature_c", "board_models", "contact_models"] : ["contract", "domain", "board_models", "link_models", "ground", "analysis"];
    for (const key of required) if (input[key] === undefined) missing.push(`request.${key}`);
    if (["multiboard_pi", "multiboard_si"].includes(item.kind) && input.domain !== item.kind.replace("multiboard_", "")) missing.push("request.domain must match the prepared analysis kind");
    const scan = (value: unknown, path: string) => { if (value === null) missing.push(path); else if (value && typeof value === "object") Object.entries(value).forEach(([key, child]) => scan(child, `${path}.${key}`)); };
    for (const [key, value] of Object.entries(input)) if (key !== "assembly") scan(value, `request.${key}`);
  }
  return missing;
}

export function createMcpAnalysisConversation(options: Options) {
  const cases = new Map<string, Prepared>(), jobs = new Map<string, Job>();
  // Include broker-owned mutable state in assistant review bindings. React's
  // project revision alone cannot observe external MCP patches or job admission.
  const revisionIdentity = crypto.randomUUID();
  let stateRevision = 0;
  const changed = () => { stateRevision += 1; };
  const worker = async (method: string, params: Record<string, unknown>) => { const reply = await options.callWorker({ method, params }); if (!reply.ok || !reply.result) throw new Error(reply.error ?? `${method} returned no result.`); return reply.result; };
  const lookup = (id: unknown) => { const item = typeof id === "string" ? cases.get(id) : undefined; if (!item) throw new Error("Prepared case was not found."); return item; };
  const fresh = async (item: Prepared) => { const context = options.getContext(); if (item.binding !== await binding(context)) throw new Error("Loaded design or assembly changed; prepare a new case."); return context; };
  const summary = (job: Job) => {
    const result = rec(rec(job.result?.data).analysis_result ?? job.result?.analysis_result ?? job.result), evidence = rec(result.evidence);
    return { jobId: job.id, caseId: job.caseId, phase: job.phase, status: job.status, error: job.error, evidenceAvailable: Boolean(job.result), result: job.result ? { status: result.status, ready: result.ready, missing: result.missing, model_status: result.model_status, summary: result.summary, issues: result.issues ?? evidence.issues, provenance: result.provenance, numerical_admission: result.numerical_admission ?? evidence.numerical_admission } : undefined };
  };
  const spawn = (item: Prepared, phase: Job["phase"], execute: () => Promise<Record<string, unknown>>) => {
    if ([...jobs.values()].some(job => job.status === "running")) throw new Error("An MCP analysis job is already running; poll its status before starting another.");
    if (jobs.size >= 32) { const oldest = [...jobs.values()].find(job => job.status !== "running"); if (oldest) jobs.delete(oldest.id); }
    const job: Job = { id: crypto.randomUUID(), caseId: item.id, phase, status: "running" }; jobs.set(job.id, job);
    if (phase === "preflight") item.preflightJobId = job.id; else item.runJobId = job.id;
    changed();
    void execute().then(async result => { job.result = result; const payload = rec(rec(result.data).analysis_result ?? result.analysis_result ?? result);
      const partial = phase === "solve" && payload.status === "partial";
      const screening = phase === "solve" && item.kind === "em" && payload.status === "completed_screening_only";
      const blocked = phase === "solve" && !partial && !screening && !["completed", "completed_with_warnings", "solved"].includes(String(payload.status));
      if (phase === "solve" && !blocked) await options.publishResult?.(result, { kind: item.kind, caseId: item.id, jobId: job.id, scope: item.scope, parameters: item.preflight?.parameters ?? item.parameters });
      job.status = blocked ? "blocked" : partial ? "partial" : screening ? "completed_screening_only" : "completed";
      changed();
    }).catch(error => { job.status = "failed"; job.error = error instanceof Error ? error.message : String(error); changed(); });
    return summary(job);
  };
  const extension = (item: Prepared, context: McpLoadedContext) => {
    const entry = (context.extensions ?? []).map(rec).find(row => row.id === item.parameters.extension_id);
    if (!entry || entry.trusted !== true || entry.state === "disabled") throw new Error("Select a trusted, enabled installed extension. MCP cannot grant trust.");
    const contributions = entry.contributions ?? entry.contributes;
    const groups = rec(contributions);
    const analyses = Array.isArray(contributions) ? contributions : Array.isArray(groups.analyses) ? groups.analyses : [];
    const contribution = analyses.map(rec).find(row => row.id === item.parameters.contribution_id && (!row.kind || row.kind === "analysis"));
    if (!contribution) throw new Error("Only an advertised analysis contribution can run through MCP.");
    const schema = rec(contribution.input_schema);
    const parameters = rec(item.parameters.parameters);
    for (const key of Array.isArray(schema.required) ? schema.required : []) if (typeof key === "string" && parameters[key] === undefined) throw new Error(`Missing extension parameter: ${key}`);
    return { entry, contribution, parameters };
  };
  const extensionContext = (entry: Record<string, unknown>, context: McpLoadedContext, parameters: Record<string, unknown>) => {
    const permissions = Array.isArray(entry.permissions) ? entry.permissions : [];
    return { parameters, ...(permissions.includes("design.read") ? { design: context.design } : {}),
      ...(permissions.includes("results.read") ? { results: { contract: "spike/results-context/v1", complete: true, result: context.results?.[context.results.length - 1] ?? null } } : {}) };
  };
  const preflight = async (item: Prepared) => {
    item.preflight = undefined;
    changed();
    const revision = item.revision, context = await fresh(item), missing = missingInputs(item, context);
    if (missing.length) return { status: "needs_input", ready: false, missing, caseId: item.id, numerical_admission: "not_run" };
    if (context.assembly && item.scope === "active_board") { if (!context.assemblyScope) throw new Error("An explicit active-board assembly scope is required."); await worker("validate_assembly_analysis_scope", { design: context.design, assembly_scope: context.assemblyScope }); }
    await options.admitScope?.(item.kind, item.parameters);
    let result: Record<string, unknown>, parameters = { ...item.parameters }, ready = true;
    const scope = context.assemblyScope ? { assembly_scope: context.assemblyScope } : {};
    if (item.kind === "pi") { result = await worker("preflight_analysis", { design: context.design, spec: parameters.spec, ...scope }); ready = result.can_solve === true; }
    else if (item.kind === "studio_feedback") { result = await worker("validate_studio_board_cosimulation", { design: context.design, request: parameters.request, ...scope }); ready = result.status === "accepted"; }
    else if (item.kind === "thermal") { result = await worker("validate_thermal", { scenario: parameters.scenario, ...scope }); ready = result.valid === true; }
    else if (item.kind === "em") { result = await worker("emi_preflight", { design: context.design, setup: parameters.setup, ...scope }); ready = result.can_screen === true; }
    else if (item.kind === "extension") {
      const admitted = extension(item, context), id = String(admitted.entry.id), contribution = String(parameters.contribution_id);
      const previewId = id === "spike.emerge-suite" ? "emerge-preview" : id === "spike.optycal-suite" ? "optycal-preview" : admitted.contribution.preflight_contribution_id;
      if (typeof previewId !== "string") throw new Error("This extension has no safe advertised preparation path; use its GUI controls.");
      result = await worker("invoke_extension", { extension_id: id, contribution_id: previewId, context: extensionContext(admitted.entry, context, { ...admitted.parameters, ...(id === "spike.emerge-suite" ? { preview_radiation: contribution === "emerge-radiation" } : {}) }) });
      const data = rec(result.data);
      if (typeof data.script !== "string" || typeof data.script_sha256 !== "string" || await sha(data.script) !== data.script_sha256) throw new Error("The prepared extension script digest is missing or does not match.");
      parameters = { ...parameters, parameters: { ...admitted.parameters, expected_generated_script_sha256: data.script_sha256, ...(data.structure_source_sha256 ? { expected_structure_source_sha256: data.structure_source_sha256 } : {}) } };
      result = { status: "prepared", generated_script_sha256: data.script_sha256, case_sha256: data.case_sha256, structure_source_sha256: data.structure_source_sha256, setup: data.setup ?? data.case, model_status: "unvalidated", numerical_admission: "adapter_prepared_not_solved" };
    } else result = { status: "structural_ready", model_status: "unvalidated", numerical_admission: "worker_validates_at_execution", description: "Required inputs and loaded identity checked; this path has no separate numerical preflight. Runtime may still reject geometry, passivity, resources or unsupported physics." };
    await fresh(item);
    if (item.revision !== revision) throw new Error("Case changed during preflight; preflight its new revision.");
    item.preflight = { revision, binding: item.binding, ready, result, parameters };
    changed();
    return { status: ready ? "ready_for_execution" : "blocked", ready, caseId: item.id, revision, evidence: result };
  };
  const run = async (item: Prepared) => {
    const context = await fresh(item), admitted = item.preflight;
    if (!admitted?.ready || admitted.revision !== item.revision || admitted.binding !== item.binding) throw new Error("Complete a passing preflight for this exact case revision before running.");
    const parameters = admitted.parameters, flow = FLOWS[item.kind], scope = context.assemblyScope ? { assembly_scope: context.assemblyScope } : {};
    let params: Record<string, unknown>;
    if (item.kind === "extension") { const admittedExtension = extension(item, context); params = { extension_id: parameters.extension_id, contribution_id: parameters.contribution_id, context: extensionContext(admittedExtension.entry, context, rec(parameters.parameters)) }; }
    else if (item.scope === "reduced_assembly") params = { request: parameters.request };
    else params = { [flow.key]: parameters[flow.key], ...(item.kind === "si" || item.kind === "si_workflow" ? { design: context.canonicalDesign } : { design: context.design }), ...scope };
    if (item.kind === "board_thermal") {
      if (context.boardBoundsMm) params.design = { ...rec(params.design), metadata: { ...rec(rec(params.design).metadata), board_bounds_mm: context.boardBoundsMm } };
      if (rec(rec(parameters.request).board).model === "layered" && context.sourceKiCadPcb) params.source_kicad_pcb = context.sourceKiCadPcb;
    }
    const result = await worker(flow.method, params);
    await fresh(item);
    return result;
  };
  return { getRevision: () => `${revisionIdentity}:${stateRevision}`, reviewCase: (caseId: string) => { const item = lookup(caseId); return safeObject({ caseId: item.id, kind: item.kind, scope: item.scope, revision: item.revision, loadedDesignBinding: item.binding, parameters: item.preflight?.parameters ?? item.parameters, preflight: item.preflight?.result ?? null }); }, async handle(command: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const context = options.getContext();
    if (command === "studio_board_context") {
      if (!context.design || Object.keys(args).length) throw new Error("Load a board and use no caller-supplied context overrides.");
      const loadedDesignBinding = await binding(context), result = await worker("prepare_studio_board_context", { design: context.design });
      if (loadedDesignBinding !== await binding(options.getContext())) throw new Error("The loaded board changed during Studio context inspection.");
      return { ...result, loadedDesignBinding, activeDesignId: context.activeDesignId };
    }
    if (["spider_context", "spider_query", "spider_compare"].includes(command)) {
      if (!context.design) throw new Error("Load a board before inspecting its SpiDeR document.");
      const allowed = command === "spider_compare" ? ["before", "query"] : command === "spider_query" ? ["query"] : [];
      if (Object.keys(args).some(key => !allowed.includes(key))) throw new Error("Unknown SpiDeR bridge argument.");
      const query = safeObject(args.query ?? {}), allowedQuery = command === "spider_compare" ? ["entity_types", "offset", "limit"] : ["entity_types", "ids", "source_ids", "name_contains", "offset", "limit", "expected_revision"];
      if (Object.keys(query).some(key => !allowedQuery.includes(key))) throw new Error("Unknown SpiDeR query field.");
      const loadedDesignBinding = await binding(context), document = context.canonicalDesign ?? context.design;
      const result = command === "spider_context"
        ? await worker("validate_spider", { document, max_issues: 50 })
        : command === "spider_query"
        ? await worker("query_spider", { document, ...query })
        : await worker("compare_spider", { before: safeObject(args.before), after: document, ...query });
      if (loadedDesignBinding !== await binding(options.getContext())) throw new Error("The loaded design changed during SpiDeR inspection; query its new revision.");
      return { ...result, loadedDesignBinding, activeDesignId: context.activeDesignId, readOnly: true };
    }
    if (command === "analysis_context") {
      const query = rec(args.query), offset = Number(query.pad_offset ?? 0), limit = Number(query.pad_limit ?? 500);
      if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 1000 || query.net_names !== undefined && (!Array.isArray(query.net_names) || query.net_names.length > 128 || !query.net_names.every(value => typeof value === "string" && value.length <= 512))) throw new Error("Pad query requires pad_offset ≥0, pad_limit 1..1000 and at most 128 net_names strings.");
      const filter = Array.isArray(query.net_names) ? new Set(query.net_names as string[]) : null;
      const pads = (Array.isArray(rec(context.design).pads) ? rec(context.design).pads as unknown[] : []).filter(item => !filter || filter.has(String(rec(item).net_name ?? rec(item).net ?? "")));
      return { boardLoaded: Boolean(context.design), boardFile: context.boardFile, activeDesignId: context.activeDesignId, loadedDesignBinding: await binding(context), nets: nets(context), layers: rec(context.design).stackup,
      padOffset: offset, padCount: pads.length, padsTruncated: offset + limit < pads.length,
      pads: pads.slice(offset, offset + limit).map(item => { const pad = rec(item); return { id: pad.id, reference: pad.reference ?? pad.ref ?? pad.component_ref, net: pad.net_name ?? pad.net, layer: pad.layer, at: pad.at }; }),
      assembly: context.assembly ? { id: rec(context.assembly).assembly_id, boards: rec(context.assembly).boards, harnesses: rec(context.assembly).harnesses, thermal_contacts: rec(context.assembly).thermal_contacts } : null,
      extensions: context.extensions ?? [], resultCount: context.results?.length ?? 0,
      results: (context.results ?? []).map((value, index) => { const payload = rec(rec(rec(value).data).analysis_result ?? rec(value).analysis_result ?? value); return { index, resultId: payload.analysis_id, analysis_id: payload.analysis_id, status: payload.status, mode: payload.mode, model_status: payload.model_status, provenance: payload.provenance, datasets: Object.keys(rec(payload.em_fields ?? payload.fields)) }; }),
      capability_limits: ["Loaded board only unless reduced_assembly is explicit.", "No full assembly coupled FEM claim.", "Missing electrical/thermal/excitation parameters must be supplied."] };
    }
    if (command === "analysis_describe") { if (args.kind !== undefined && !Object.prototype.hasOwnProperty.call(FLOWS, String(args.kind))) throw new Error("Unknown analysis kind."); return { analyses: args.kind ? { [String(args.kind)]: FLOWS[String(args.kind)] } : FLOWS, extensions: context.extensions ?? [], sequence: ["analysis_context", "analysis_describe", "spike_contract_schema / spike_validate_contract", "analysis_prepare", "analysis_patch as needed", "analysis_preflight then poll analysis_job", "analysis_run then poll analysis_job", "analysis_evidence"], scopes: ["active_board", "reduced_assembly"], defaults_are_not_measured_inputs: true }; }
    if (command === "analysis_prepare") {
      const kind = String(args.kind), scope = String(args.scope);
      if (!Object.prototype.hasOwnProperty.call(FLOWS, kind) || !["active_board", "reduced_assembly"].includes(scope) || kind.startsWith("multiboard_") !== (scope === "reduced_assembly")) throw new Error("Choose a supported kind and explicit matching scope.");
      if (!context.design) throw new Error("Load a board in SPIKE before preparing a loaded-design analysis.");
      if (cases.size >= 32) throw new Error("Prepared case limit reached; restart SPIKE to reset it.");
      const parameters = checkedParameters(kind, args.parameters ?? {}), item: Prepared = { id: crypto.randomUUID(), kind, scope, parameters, binding: await binding(context), revision: 1 }; cases.set(item.id, item);
      changed();
      if (scope === "reduced_assembly" && !parameters.request) { const draft = await worker("prepare_multiboard_study", { request: { assembly: context.assembly, domain: kind.replace("multiboard_", "").replace("em", "emi") } }); item.parameters.request = draft.request; changed(); }
      return { caseId: item.id, kind, scope, revision: item.revision, loadedDesignBinding: item.binding, parameters: item.parameters, missing: missingInputs(item, context), solved: false };
    }
    if (command === "analysis_patch") { const item = lookup(args.caseId); await fresh(item); if ([...jobs.values()].some(job => job.caseId === item.id && job.status === "running")) throw new Error("Wait for the active job before changing its case."); item.parameters = { ...item.parameters, ...checkedParameters(item.kind, args.patch) }; item.revision++; item.preflight = undefined; item.preflightJobId = undefined; item.runJobId = undefined; changed(); return { caseId: item.id, revision: item.revision, parameters: item.parameters, missing: missingInputs(item, context), solved: false }; }
    if (command === "analysis_preflight") { const item = lookup(args.caseId); await fresh(item); if (item.preflightJobId && jobs.has(item.preflightJobId)) return summary(jobs.get(item.preflightJobId)!); return spawn(item, "preflight", () => preflight(item)); }
    if (command === "analysis_run") { const item = lookup(args.caseId); await fresh(item); if (item.runJobId && jobs.has(item.runJobId)) return summary(jobs.get(item.runJobId)!); if (!item.preflight?.ready) throw new Error("Poll the passing preflight job before running."); return spawn(item, "solve", () => run(item)); }
    if (command === "analysis_job" || command === "analysis_evidence") {
      const job = typeof args.jobId === "string" ? jobs.get(args.jobId) : undefined; if (!job) throw new Error("Analysis job was not found.");
      if (command === "analysis_job") return summary(job);
      if (!job.result) throw new Error("Job has no returned evidence yet; poll its status.");
      const query = rec(args.query), path = String(query.path ?? ""), offset = Number(query.offset ?? 0), limit = Number(query.limit ?? 50);
      if (!/^[a-zA-Z0-9_.]*$/.test(path) || path.split(".").some(part => ["__proto__", "constructor", "prototype"].includes(part)) || !Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 200) throw new Error("Use a safe evidence path, nonnegative offset and limit 1..200.");
      let value: unknown = job.result; for (const part of path ? path.split(".") : []) value = rec(value)[part] ?? (Array.isArray(value) && /^\d+$/.test(part) ? value[Number(part)] : undefined);
      if (value === undefined) throw new Error("Requested evidence path was not returned by the solver.");
      if (Array.isArray(value)) { const slice = value.slice(offset, offset + limit); if (JSON.stringify(slice).length > 65536) return { ...summary(job), path, offset, total: value.length, message: "Requested page exceeds 64 KiB; reduce limit or choose a narrower indexed path." }; return { ...summary(job), path, offset, total: value.length, value: slice, actual_returned_evidence: true }; }
      if (JSON.stringify(value).length > 65536) return { ...summary(job), path, keys: Object.keys(rec(value)), message: "Choose a narrower path; evidence is not fabricated or silently truncated." };
      return { ...summary(job), path, value, actual_returned_evidence: true };
    }
    throw new Error("Unsupported desktop analysis command.");
  } };
}
