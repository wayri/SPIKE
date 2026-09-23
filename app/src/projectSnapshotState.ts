/** Preserve future fields while replacing the fields the current UI edits. */
export function mergeProjectSnapshot(retained: unknown, updated: unknown): any {
  if (updated === undefined) return retained;
  if (Array.isArray(updated)) {
    const old = Array.isArray(retained) ? retained : [];
    const identity = (item: any) => item && typeof item === 'object' && !Array.isArray(item)
      ? item.id ?? item.design_id ?? item.analysis_id ?? item.ref : undefined;
    const indexed = new Map(old.map(item => [identity(item), item] as const).filter(([id]) => id !== undefined));
    return updated.map(item => identity(item) !== undefined ? mergeProjectSnapshot(indexed.get(identity(item)), item) : item);
  }
  if (!updated || typeof updated !== 'object') return updated;
  const previous = retained && typeof retained === 'object' && !Array.isArray(retained) ? retained as Record<string, unknown> : {};
  return Object.fromEntries([...new Set([...Object.keys(previous), ...Object.keys(updated)])]
    .map(key => [key, mergeProjectSnapshot(previous[key], (updated as Record<string, unknown>)[key])]));
}

export const RESULT_PACKAGE_CONTRACT = 'spike/result-package/v2';

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
    || projectSnapshot.emi?.field_result || projectSnapshot.emi?.screening || projectSnapshot.thermal?.scenario?.result;
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
