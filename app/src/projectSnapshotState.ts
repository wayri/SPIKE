const authoritativeStudyOmission = (path: readonly string[], key: string): boolean => {
  const owner = path[path.length - 1];
  return (owner === 'cases' || owner === 'runs') && (key === 'resultSnapshot' || key === 'resultRef')
    || owner === 'datasets' && (key === 'payload' || key === 'rawText' || key === 'artifactRef');
};

/** Preserve future fields while replacing the fields the current UI edits. */
export function mergeProjectSnapshot(retained: unknown, updated: unknown, path: readonly string[] = []): any {
  if (updated === undefined) return retained;
  if (Array.isArray(updated)) {
    const old = Array.isArray(retained) ? retained : [];
    const identity = (item: any) => item && typeof item === 'object' && !Array.isArray(item)
      ? item.id ?? item.design_id ?? item.analysis_id ?? item.ref : undefined;
    const indexed = new Map(old.map(item => [identity(item), item] as const).filter(([id]) => id !== undefined));
    return updated.map(item => identity(item) !== undefined ? mergeProjectSnapshot(indexed.get(identity(item)), item, path) : item);
  }
  if (!updated || typeof updated !== 'object') return updated;
  const previous = retained && typeof retained === 'object' && !Array.isArray(retained) ? retained as Record<string, unknown> : {};
  const current = updated as Record<string, unknown>;
  return Object.fromEntries([...new Set([...Object.keys(previous), ...Object.keys(current)])]
    .filter(key => !(path.includes('studies') && authoritativeStudyOmission(path, key)
      && !Object.prototype.hasOwnProperty.call(current, key)))
    .map(key => [key, mergeProjectSnapshot(previous[key], current[key], [...path, key])]));
}

export const RESULT_PACKAGE_CONTRACT = 'spike/result-package/v2';

/** Produce a design/setup copy while leaving the live project and its results intact. */
export function withoutSavedResults(snapshot: Record<string, any>): Record<string, any> {
  const copy = structuredClone(snapshot);
  if (Array.isArray(copy.studies)) for (const study of copy.studies) {
    if (Array.isArray(study?.datasets)) for (const dataset of study.datasets) {
      if (!dataset || typeof dataset !== 'object' || dataset.resultDerived !== true) continue;
      delete dataset.payload;
      delete dataset.rawText;
      delete dataset.artifactRef;
    }
    if (!Array.isArray(study?.cases)) continue;
    for (const simulationCase of study.cases) {
      if (!simulationCase || typeof simulationCase !== 'object') continue;
      delete simulationCase.resultSnapshot;
      delete simulationCase.resultRef;
      if (simulationCase.settings && typeof simulationCase.settings === 'object') delete simulationCase.settings.optycalSource;
      if (Array.isArray(simulationCase.runs)) for (const run of simulationCase.runs) {
        if (!run || typeof run !== 'object') continue;
        delete run.resultSnapshot;
        delete run.resultRef;
        if (run.settings && typeof run.settings === 'object') delete run.settings.optycalSource;
      }
    }
  }
  if (copy.analysis) {
    copy.analysis.latest_result = null;
    copy.analysis.active_result = null;
    copy.analysis.result_history = [];
    copy.analysis.pdn_review = null;
    if (copy.analysis.si) copy.analysis.si.latest_channel_result = null;
  }
  if (copy.emi) {
    copy.emi.preflight = null;
    copy.emi.screening = null;
    copy.emi.field_result = null;
  }
  if (copy.thermal?.scenario) {
    copy.thermal.scenario.result = null;
    copy.thermal.scenario.field_result = null;
  }
  copy.results = {};
  const coupledStudies = copy.assembly_ir?.extensions?.["spike.multiboard-studies"];
  if (coupledStudies && typeof coupledStudies === "object") for (const study of Object.values(coupledStudies)) {
    if (study && typeof study === "object") delete (study as Record<string, unknown>).result;
  }
  return copy;
}

export function isSupportedSavedResult(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const raw = value as Record<string, any>;
  const scalars = raw.scalar_fields;
  return Boolean(scalars && raw.vector_fields && Array.isArray(scalars.voltage_v)
    && Array.isArray(scalars.voltage_drop_v) && Array.isArray(scalars.current_density_a_mm2))
    || Boolean(raw.fields && typeof raw.fields === 'object' && !Array.isArray(raw.fields));
}

/** Keep unreadable engine results opaque; supported row deletion remains an edit. */
export function retainOpaqueResultState(retained: Record<string, any> | undefined, edited: Record<string, any>,
  isSupported: (value: unknown) => boolean, options: { clearAll?: boolean; clearLatest?: boolean } = {}): Record<string, any> {
  if (options.clearAll) return { ...edited, latest_result: null, result_history: [] };
  const rows = Array.isArray(edited.result_history) ? edited.result_history : [];
  const ids = new Set(rows.map((row: any) => String(row.id)));
  const opaque = (Array.isArray(retained?.result_history) ? retained.result_history : [])
    .filter((row: any) => row?.bundle != null && !isSupported(row.bundle) && !ids.has(String(row.id)));
  const oldLatest = retained?.latest_result;
  const opaqueLatest = oldLatest != null && !isSupported(oldLatest);
  const latest = options.clearLatest ? null : edited.latest_result ?? (opaqueLatest ? oldLatest : null);
  // Running a supported engine must not overwrite an older opaque active result.
  if (opaqueLatest && latest != null && latest !== oldLatest && !options.clearLatest) {
    const id = String(oldLatest.analysis_id ?? 'retained-opaque-result');
    if (!ids.has(id) && !opaque.some((row: any) => String(row.id) === id || row.bundle === oldLatest)) {
      opaque.push({ id, label: 'Result from another engine', bundle: oldLatest });
    }
  }
  return { ...edited, latest_result: latest, result_history: [...opaque, ...rows] };
}

export function createResultPackage(projectSnapshot: Record<string, any>, visuals?: unknown): Record<string, unknown> {
  const analysis = projectSnapshot.analysis ?? {};
  const hasResults = analysis.latest_result || analysis.result_history?.length || analysis.si?.latest_channel_result
    || projectSnapshot.emi?.field_result || projectSnapshot.emi?.screening || projectSnapshot.thermal?.scenario?.result
    || projectSnapshot.thermal?.scenario?.field_result
    || (Array.isArray(projectSnapshot.studies) && projectSnapshot.studies.some((study: any) =>
      Array.isArray(study?.cases) && study.cases.some((item: any) => item?.resultSnapshot != null
        || Array.isArray(item?.runs) && item.runs.some((run: any) => run?.resultSnapshot != null))
      || Array.isArray(study?.datasets) && study.datasets.some((dataset: any) => dataset?.resultDerived === true
        && (dataset.payload !== undefined || dataset.rawText !== undefined))));
  if (!hasResults) throw new Error('Run a simulation or load results before saving a result package.');
  return { contract: RESULT_PACKAGE_CONTRACT, generated_at: new Date().toISOString(), project_snapshot: projectSnapshot, visuals };
}

export function readResultPackage(text: string): { snapshot: Record<string, any> | null; results: Record<string, any>; visuals?: unknown } {
  const raw = JSON.parse(text);
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('Result file must contain a JSON object.');
  if (raw.contract === RESULT_PACKAGE_CONTRACT) {
    if (!raw.project_snapshot?.design || !raw.project_snapshot?.analysis) throw new Error('Result package is missing its design or analysis context.');
    return { snapshot: raw.project_snapshot, results: raw.project_snapshot.analysis, visuals: raw.visuals };
  }
  if (raw.contract === 'spike/result-package/v1') {
    return { snapshot: null, results: { ...raw.analysis, latest_result: raw.active_result,
      result_history: Array.isArray(raw.results) ? raw.results : [], saved_project: raw.project,
      probes: raw.probes, selection: raw.selection, emi: raw.emi } };
  }
  if (raw.analysis_id && (raw.scalar_fields || raw.outputs)) return { snapshot: null, results: { latest_result: raw, result_history: [] } };
  throw new Error('The selected file is not a SPIKE result package or simulation result.');
}
