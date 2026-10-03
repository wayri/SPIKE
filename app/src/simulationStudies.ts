// SPDX-License-Identifier: Apache-2.0

/** A study groups independent, ordered simulation setups. It does not run a solver. */
export const STUDY_SCHEMA_VERSION = 1 as const;

export type StudyJson = null | boolean | number | string | StudyJson[] | { [key: string]: StudyJson };
export type StudyJsonObject = { [key: string]: StudyJson };
export type KnownSimulationType = "pi" | "si" | "em" | "thermal";

export const MAX_STUDY_DATASETS = 128;
export const MAX_STUDY_RUNS_PER_CASE = 100;
export const MAX_STUDY_RETAINED_BYTES = 96 * 1024 * 1024;
export const MAX_STUDY_DATASET_BYTES = 2 * 1024 * 1024;
export const MAX_STUDY_DOCUMENT_BYTES = 256 * 1024 * 1024;

export type StudyDataset = {
  id: string;
  name: string;
  kind: "json" | "csv";
  mediaType: string;
  provenance: string;
  units: StudyJsonObject;
  createdAt: string;
  resultDerived: boolean;
  payload?: StudyJson;
  rawText?: string;
  artifactRef?: string;
};

export type StudyRunFacts = {
  provider?: string;
  contract?: string;
  status?: string;
  modelStatus?: string;
  designId?: string;
  designDigestSha256?: string;
  units?: StudyJson;
};

export type StudyRun = {
  id: string;
  capturedAt: string;
  association: "workspace-capture";
  caseType: string;
  mode: string;
  scenario: StudyJsonObject;
  settings: StudyJsonObject;
  facts: StudyRunFacts;
  resultSnapshot?: StudyJson;
  resultRef?: string;
};

export type SimulationStudyCase = {
  id: string;
  type: string;
  mode: string;
  name: string;
  notes: string;
  scenario: StudyJsonObject;
  settings: StudyJsonObject;
  resultSnapshot?: StudyJson;
  resultRef?: string;
  runs: StudyRun[];
  datasetIds: string[];
};

export type SimulationStudy = {
  version: typeof STUDY_SCHEMA_VERSION;
  id: string;
  name: string;
  notes: string;
  tags: string[];
  archived: boolean;
  datasets: StudyDataset[];
  cases: SimulationStudyCase[];
};

const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const nonempty = (value: unknown, fallback: string): string =>
  typeof value === "string" && value.trim() ? value.trim() : fallback;
const notes = (value: unknown): string => typeof value === "string" ? value : "";
const newId = (): string => globalThis.crypto.randomUUID();
const isoDate = (value: unknown, fallback: string): string => {
  if (typeof value !== "string" || !value.trim() || !Number.isFinite(Date.parse(value))) return fallback;
  return new Date(value).toISOString();
};

/** Copy JSON data with finite numbers and safe keys; reject cycles and excessive nesting. */
function copyJson(value: unknown, seen = new WeakSet<object>(), depth = 0): StudyJson | undefined {
  if (depth > 32) return undefined;
  if (value === null || typeof value === "boolean" || typeof value === "string") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : undefined;
  if (typeof value !== "object") return undefined;
  if (seen.has(value)) return undefined;
  seen.add(value);
  let result: StudyJson | undefined;
  if (Array.isArray(value)) {
    const entries = value.map(entry => copyJson(entry, seen, depth + 1));
    result = entries.every(entry => entry !== undefined) ? entries as StudyJson[] : undefined;
  } else if (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null) {
    const record: StudyJsonObject = {};
    result = record;
    for (const [key, entry] of Object.entries(value)) {
      if (key === "__proto__" || key === "constructor" || key === "prototype") continue;
      const copied = copyJson(entry, seen, depth + 1);
      if (copied === undefined) { result = undefined; break; }
      record[key] = copied;
    }
  }
  seen.delete(value);
  return result;
}

export function copyStudyJson(value: unknown): StudyJson | undefined { return copyJson(value); }
export function studyJsonBytes(value: StudyJson): number { return new TextEncoder().encode(JSON.stringify(value)).length; }

const copyObject = (value: unknown): StudyJsonObject => {
  const copied = copyJson(value);
  return object(copied) ? copied as StudyJsonObject : {};
};

const stringList = (value: unknown, maximum: number, itemLength = 160): string[] => {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.flatMap(item => {
    if (typeof item !== "string") return [];
    const text = item.trim();
    if (!text || text.length > itemLength || seen.has(text)) return [];
    seen.add(text); return [text];
  }).slice(0, maximum);
};

function resultFacts(result: unknown): StudyRunFacts {
  if (!object(result)) return {};
  const nested = [result,
    object(result.analysis_result) ? result.analysis_result : null,
    object(result.extensionResult) && object(result.extensionResult.data) && object(result.extensionResult.data.analysis_result) ? result.extensionResult.data.analysis_result : null,
    ...["fieldResult", "result", "field_result", "board_thermal_result"].map(key => object(result[key]) ? result[key] : null),
  ].filter((value): value is Record<string, unknown> => object(value));
  const reported = nested.find(value => typeof value.contract === "string" || typeof value.status === "string" || object(value.provenance)) ?? result;
  const provenance = object(reported.provenance) ? reported.provenance : {};
  const facts: StudyRunFacts = {};
  if (typeof result.provider === "string") facts.provider = result.provider;
  if (typeof reported.contract === "string") facts.contract = reported.contract;
  if (typeof reported.status === "string") facts.status = reported.status;
  if (typeof reported.model_status === "string") facts.modelStatus = reported.model_status;
  if (typeof provenance.design_id === "string") facts.designId = provenance.design_id;
  if (typeof provenance.design_digest_sha256 === "string") facts.designDigestSha256 = provenance.design_digest_sha256;
  const units = copyJson(reported.units ?? provenance.units);
  if (units !== undefined) facts.units = units;
  return facts;
}

function retainedRunBytes(cases: readonly SimulationStudyCase[]): number {
  return cases.reduce((caseSum, item) => caseSum + item.runs.reduce((runSum, run) =>
    runSum + (run.resultSnapshot === undefined ? 0 : studyJsonBytes(run.resultSnapshot)), 0), 0);
}
function retainedDatasetBytes(datasets: readonly StudyDataset[]): number {
  return datasets.reduce((sum, item) => sum + (item.rawText ? new TextEncoder().encode(item.rawText).length : 0)
    + (item.payload === undefined ? 0 : studyJsonBytes(item.payload)), 0);
}

function normalizeRun(raw: unknown, usedIds: Set<string>): StudyRun | null {
  if (!object(raw)) return null;
  let id = nonempty(raw.id, newId());
  while (usedIds.has(id)) id = newId();
  usedIds.add(id);
  const capturedAt = isoDate(raw.capturedAt, new Date(0).toISOString());
  const value: StudyRun = {
    id, capturedAt, association: "workspace-capture",
    caseType: typeof raw.caseType === "string" ? raw.caseType : "",
    mode: typeof raw.mode === "string" ? raw.mode : "",
    scenario: copyObject(raw.scenario), settings: copyObject(raw.settings),
    facts: object(raw.facts) ? {
      ...(typeof raw.facts.contract === "string" ? { contract: raw.facts.contract } : {}),
      ...(typeof raw.facts.provider === "string" ? { provider: raw.facts.provider } : {}),
      ...(typeof raw.facts.status === "string" ? { status: raw.facts.status } : {}),
      ...(typeof raw.facts.modelStatus === "string" ? { modelStatus: raw.facts.modelStatus } : {}),
      ...(typeof raw.facts.designId === "string" ? { designId: raw.facts.designId } : {}),
      ...(typeof raw.facts.designDigestSha256 === "string" ? { designDigestSha256: raw.facts.designDigestSha256 } : {}),
      ...(copyJson(raw.facts.units) !== undefined ? { units: copyJson(raw.facts.units)! } : {}),
    } : resultFacts(raw.resultSnapshot),
  };
  const snapshot = copyJson(raw.resultSnapshot);
  if (snapshot !== undefined) value.resultSnapshot = snapshot;
  if (typeof raw.resultRef === "string" && raw.resultRef.trim()) value.resultRef = raw.resultRef.trim();
  return snapshot !== undefined || value.resultRef || (typeof raw.id === "string" && raw.id.trim()) ? value : null;
}

function normalizeDataset(raw: unknown, usedIds: Set<string>): StudyDataset | null {
  if (!object(raw) || !["json", "csv"].includes(String(raw.kind))) return null;
  let id = nonempty(raw.id, newId());
  while (usedIds.has(id)) id = newId();
  usedIds.add(id);
  const value: StudyDataset = {
    id, name: nonempty(raw.name, "Dataset"), kind: raw.kind as "json" | "csv",
    mediaType: typeof raw.mediaType === "string" ? raw.mediaType : raw.kind === "csv" ? "text/csv" : "application/json",
    provenance: typeof raw.provenance === "string" ? raw.provenance : "",
    units: copyObject(raw.units), createdAt: isoDate(raw.createdAt, new Date(0).toISOString()),
    resultDerived: raw.resultDerived === true,
  };
  const payload = copyJson(raw.payload);
  if (payload !== undefined) value.payload = payload;
  if (typeof raw.rawText === "string") value.rawText = raw.rawText;
  if (typeof raw.artifactRef === "string" && raw.artifactRef.trim()) value.artifactRef = raw.artifactRef.trim();
  const embeddedBytes = (value.rawText === undefined ? 0 : new TextEncoder().encode(value.rawText).length)
    + (value.payload === undefined ? 0 : studyJsonBytes(value.payload));
  if (embeddedBytes > MAX_STUDY_DATASET_BYTES) throw new Error("Study dataset exceeds the 2 MiB attachment limit.");
  if (value.kind === "csv" && value.rawText === undefined && !value.artifactRef && !(typeof raw.id === "string" && raw.id.trim())) return null;
  if (value.kind === "json" && value.payload === undefined && !value.artifactRef && !(typeof raw.id === "string" && raw.id.trim())) return null;
  return value;
}

function normalizeCase(raw: unknown, usedIds: Set<string>): SimulationStudyCase | null {
  if (!object(raw) || typeof raw.type !== "string" || !raw.type.trim()) return null;
  if (Array.isArray(raw.runs) && raw.runs.length > MAX_STUDY_RUNS_PER_CASE) throw new Error(`Simulation case exceeds ${MAX_STUDY_RUNS_PER_CASE} recorded snapshots.`);
  let id = nonempty(raw.id, newId());
  while (usedIds.has(id)) id = newId();
  usedIds.add(id);
  const usedRunIds = new Set<string>();
  const value: SimulationStudyCase = {
    id, type: raw.type.trim(), mode: typeof raw.mode === "string" ? raw.mode.trim() : "",
    name: nonempty(raw.name, raw.type.trim()), notes: notes(raw.notes),
    scenario: copyObject(raw.scenario), settings: copyObject(raw.settings),
    runs: (Array.isArray(raw.runs) ? raw.runs : [])
      .map(item => normalizeRun(item, usedRunIds)).filter((item): item is StudyRun => item !== null),
    datasetIds: stringList(raw.datasetIds, MAX_STUDY_DATASETS),
  };
  if (raw.resultSnapshot !== undefined) {
    const snapshot = copyJson(raw.resultSnapshot);
    if (snapshot !== undefined) value.resultSnapshot = snapshot;
  }
  if (typeof raw.resultRef === "string" && raw.resultRef.trim()) value.resultRef = raw.resultRef.trim();
  const retainedBytes = value.runs.reduce((sum, run) => sum + (run.resultSnapshot === undefined ? 0 : studyJsonBytes(run.resultSnapshot)), 0);
  if (retainedBytes > MAX_STUDY_RETAINED_BYTES) throw new Error("Recorded snapshots exceed the 96 MiB retained-data limit for this case.");
  return value;
}

/** Admit persisted data without trusting its shape. A future schema is rejected to avoid overwriting it. */
export function normalizeStudies(raw: unknown): SimulationStudy[] {
  const rows = Array.isArray(raw) ? raw : object(raw) && Array.isArray(raw.studies) ? raw.studies : [];
  if (object(raw) && raw.version !== undefined && raw.version !== STUDY_SCHEMA_VERSION) {
    throw new Error(`Unsupported simulation study schema version: ${String(raw.version)}`);
  }
  const usedIds = new Set<string>();
  return rows.flatMap((row: unknown) => {
    if (!object(row)) return [];
    if (row.version !== undefined && row.version !== STUDY_SCHEMA_VERSION) {
      throw new Error(`Unsupported simulation study schema version: ${String(row.version)}`);
    }
    let id = nonempty(row.id, newId());
    while (usedIds.has(id)) id = newId();
    usedIds.add(id);
    const cases = Array.isArray(row.cases) ? row.cases : [];
    if (Array.isArray(row.datasets) && row.datasets.length > MAX_STUDY_DATASETS) throw new Error(`Study exceeds ${MAX_STUDY_DATASETS} datasets.`);
    const usedDatasetIds = new Set<string>();
    const datasets = (Array.isArray(row.datasets) ? row.datasets : [])
      .map(item => normalizeDataset(item, usedDatasetIds)).filter((item): item is StudyDataset => item !== null);
    const datasetBytes = retainedDatasetBytes(datasets);
    if (datasetBytes > MAX_STUDY_RETAINED_BYTES) throw new Error("Study datasets exceed the 96 MiB retained-data limit.");
    const datasetIds = new Set(datasets.map(item => item.id));
    const normalizedCases = cases.map(item => normalizeCase(item, usedIds)).filter((item): item is SimulationStudyCase => item !== null)
      .map(item => ({ ...item, datasetIds: item.datasetIds.filter(id => datasetIds.has(id)) }));
    const runBytes = retainedRunBytes(normalizedCases);
    if (datasetBytes + runBytes > MAX_STUDY_RETAINED_BYTES) throw new Error("Study datasets and recorded snapshots exceed the 96 MiB retained-data limit.");
    const normalized: SimulationStudy = { version: STUDY_SCHEMA_VERSION, id, name: nonempty(row.name, "Untitled study"),
      notes: notes(row.notes), tags: stringList(row.tags, 32, 80), archived: row.archived === true,
      datasets, cases: normalizedCases };
    if (new TextEncoder().encode(JSON.stringify(normalized)).length > MAX_STUDY_DOCUMENT_BYTES) {
      throw new Error("Simulation study exceeds the 256 MiB document limit.");
    }
    return [normalized];
  });
}

export function createStudy(name = "Untitled study"): SimulationStudy {
  return { version: STUDY_SCHEMA_VERSION, id: newId(), name: nonempty(name, "Untitled study"), notes: "", tags: [], archived: false, datasets: [], cases: [] };
}

export function updateStudy(studies: SimulationStudy[], studyId: string, patch: Pick<Partial<SimulationStudy>, "name" | "notes" | "tags" | "archived" | "datasets">): SimulationStudy[] {
  return studies.map(study => {
    if (study.id !== studyId) return study;
    const updated = {
      ...study, name: patch.name === undefined ? study.name : nonempty(patch.name, study.name),
      notes: patch.notes === undefined ? study.notes : notes(patch.notes),
      tags: patch.tags === undefined ? study.tags : stringList(patch.tags, 32, 80),
      archived: patch.archived === undefined ? study.archived : patch.archived === true,
      datasets: patch.datasets ?? study.datasets,
    };
    return patch.datasets === undefined ? updated : normalizeStudies([updated])[0];
  });
}

export function removeStudy(studies: SimulationStudy[], studyId: string): SimulationStudy[] {
  return studies.filter(study => study.id !== studyId);
}

export function addStudyCase(
  study: SimulationStudy, type: string, name?: string, scenario?: StudyJsonObject,
  settings?: StudyJsonObject, mode = "",
): SimulationStudy {
  const usedIds = new Set([study.id, ...study.cases.map(item => item.id)]);
  const added = normalizeCase({ id: newId(), type, mode, name, scenario, settings }, usedIds);
  if (!added) throw new Error("Simulation type is required.");
  return { ...study, cases: [...study.cases, added] };
}

export function duplicateStudyCase(study: SimulationStudy, caseId: string): SimulationStudy {
  const index = study.cases.findIndex(item => item.id === caseId);
  if (index < 0) return study;
  const source = study.cases[index];
  const usedIds = new Set([study.id, ...study.cases.map(item => item.id)]);
  const copy = normalizeCase({ ...source, id: newId(), name: `${source.name} copy`,
    resultSnapshot: undefined, resultRef: undefined, runs: [] }, usedIds)!;
  const cases = [...study.cases];
  cases.splice(index + 1, 0, copy);
  return { ...study, cases };
}

export function updateStudyCase(study: SimulationStudy, caseId: string, patch: Partial<Omit<SimulationStudyCase, "id">>): SimulationStudy {
  const cases = study.cases.map(item => {
    if (item.id !== caseId) return item;
    const setupChanged = patch.type !== undefined || patch.mode !== undefined ||
      patch.scenario !== undefined || patch.settings !== undefined;
    const hasSnapshotPatch = Object.prototype.hasOwnProperty.call(patch, "resultSnapshot");
    const hasRefPatch = Object.prototype.hasOwnProperty.call(patch, "resultRef");
    const captureFacts = hasSnapshotPatch && patch.resultSnapshot !== undefined ? resultFacts(patch.resultSnapshot) : {};
    const captureSettings = patch.settings ?? item.settings;
    const capture = hasSnapshotPatch && patch.resultSnapshot !== undefined ? normalizeRun({
      id: newId(), capturedAt: new Date().toISOString(), scenario: patch.scenario ?? item.scenario,
      caseType: patch.type ?? item.type, mode: patch.mode ?? item.mode,
      settings: captureSettings, resultSnapshot: patch.resultSnapshot,
      resultRef: hasRefPatch ? patch.resultRef : undefined, facts: captureFacts,
    }, new Set([study.id, ...item.runs.map(run => run.id)])) : null;
    const updated = normalizeCase({ ...item, ...patch, id: item.id,
      resultSnapshot: hasSnapshotPatch ? patch.resultSnapshot : setupChanged ? undefined : item.resultSnapshot,
      resultRef: hasRefPatch ? patch.resultRef : setupChanged ? undefined : item.resultRef,
      runs: capture ? [...item.runs, capture] : patch.runs ?? item.runs,
    }, new Set([study.id]));
    return updated ?? item;
  });
  if (retainedDatasetBytes(study.datasets) + retainedRunBytes(cases) > MAX_STUDY_RETAINED_BYTES) {
    throw new Error("Study datasets and recorded snapshots exceed the 96 MiB retained-data limit.");
  }
  const updated = { ...study, cases };
  if (new TextEncoder().encode(JSON.stringify(updated)).length > MAX_STUDY_DOCUMENT_BYTES) {
    throw new Error("Simulation study exceeds the 256 MiB document limit.");
  }
  return updated;
}

export function removeStudyCase(study: SimulationStudy, caseId: string): SimulationStudy {
  return { ...study, cases: study.cases.filter(item => item.id !== caseId) };
}

/** Move a case to a zero-based destination, clamping out-of-range indices. */
export function moveStudyCase(study: SimulationStudy, caseId: string, destination: number): SimulationStudy {
  const index = study.cases.findIndex(item => item.id === caseId);
  if (index < 0 || !Number.isFinite(destination)) return study;
  const cases = [...study.cases];
  const [item] = cases.splice(index, 1);
  cases.splice(Math.max(0, Math.min(cases.length, Math.trunc(destination))), 0, item);
  return { ...study, cases };
}
