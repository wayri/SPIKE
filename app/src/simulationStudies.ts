// SPDX-License-Identifier: Apache-2.0

/** A study groups independent, ordered simulation setups. It does not run a solver. */
export const STUDY_SCHEMA_VERSION = 1 as const;

export type StudyJson = null | boolean | number | string | StudyJson[] | { [key: string]: StudyJson };
export type StudyJsonObject = { [key: string]: StudyJson };
export type KnownSimulationType = "pi" | "si" | "em" | "thermal";

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
};

export type SimulationStudy = {
  version: typeof STUDY_SCHEMA_VERSION;
  id: string;
  name: string;
  notes: string;
  cases: SimulationStudyCase[];
};

const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const nonempty = (value: unknown, fallback: string): string =>
  typeof value === "string" && value.trim() ? value.trim() : fallback;
const notes = (value: unknown): string => typeof value === "string" ? value : "";
const newId = (): string => globalThis.crypto.randomUUID();

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

const copyObject = (value: unknown): StudyJsonObject => {
  const copied = copyJson(value);
  return object(copied) ? copied as StudyJsonObject : {};
};

function normalizeCase(raw: unknown, usedIds: Set<string>): SimulationStudyCase | null {
  if (!object(raw) || typeof raw.type !== "string" || !raw.type.trim()) return null;
  let id = nonempty(raw.id, newId());
  while (usedIds.has(id)) id = newId();
  usedIds.add(id);
  const value: SimulationStudyCase = {
    id, type: raw.type.trim(), mode: typeof raw.mode === "string" ? raw.mode.trim() : "",
    name: nonempty(raw.name, raw.type.trim()), notes: notes(raw.notes),
    scenario: copyObject(raw.scenario), settings: copyObject(raw.settings),
  };
  if (raw.resultSnapshot !== undefined) {
    const snapshot = copyJson(raw.resultSnapshot);
    if (snapshot !== undefined) value.resultSnapshot = snapshot;
  }
  if (typeof raw.resultRef === "string" && raw.resultRef.trim()) value.resultRef = raw.resultRef.trim();
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
    return [{ version: STUDY_SCHEMA_VERSION, id, name: nonempty(row.name, "Untitled study"),
      notes: notes(row.notes), cases: cases.map(item => normalizeCase(item, usedIds)).filter((item): item is SimulationStudyCase => item !== null) }];
  });
}

export function createStudy(name = "Untitled study"): SimulationStudy {
  return { version: STUDY_SCHEMA_VERSION, id: newId(), name: nonempty(name, "Untitled study"), notes: "", cases: [] };
}

export function updateStudy(studies: SimulationStudy[], studyId: string, patch: Pick<Partial<SimulationStudy>, "name" | "notes">): SimulationStudy[] {
  return studies.map(study => study.id === studyId ? {
    ...study, name: patch.name === undefined ? study.name : nonempty(patch.name, study.name),
    notes: patch.notes === undefined ? study.notes : notes(patch.notes),
  } : study);
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
    resultSnapshot: undefined, resultRef: undefined }, usedIds)!;
  const cases = [...study.cases];
  cases.splice(index + 1, 0, copy);
  return { ...study, cases };
}

export function updateStudyCase(study: SimulationStudy, caseId: string, patch: Partial<Omit<SimulationStudyCase, "id">>): SimulationStudy {
  return { ...study, cases: study.cases.map(item => {
    if (item.id !== caseId) return item;
    const setupChanged = patch.type !== undefined || patch.mode !== undefined ||
      patch.scenario !== undefined || patch.settings !== undefined;
    const hasSnapshotPatch = Object.prototype.hasOwnProperty.call(patch, "resultSnapshot");
    const hasRefPatch = Object.prototype.hasOwnProperty.call(patch, "resultRef");
    const updated = normalizeCase({ ...item, ...patch, id: item.id,
      resultSnapshot: hasSnapshotPatch ? patch.resultSnapshot : setupChanged ? undefined : item.resultSnapshot,
      resultRef: hasRefPatch ? patch.resultRef : setupChanged ? undefined : item.resultRef,
    }, new Set([study.id]));
    return updated ?? item;
  }) };
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
