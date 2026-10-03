// SPDX-License-Identifier: Apache-2.0
import {
  copyStudyJson, MAX_STUDY_DATASETS, MAX_STUDY_DATASET_BYTES, MAX_STUDY_RETAINED_BYTES,
  MAX_STUDY_DOCUMENT_BYTES, MAX_STUDY_RUNS_PER_CASE, normalizeStudies, studyJsonBytes, type SimulationStudy, type SimulationStudyCase,
  type StudyDataset, type StudyJson, type StudyJsonObject, type StudyRun,
} from "./simulationStudies";
export { MAX_STUDY_DOCUMENT_BYTES } from "./simulationStudies";

export const MAX_STUDY_ATTACHMENT_BYTES = MAX_STUDY_DATASET_BYTES;
export const MAX_STUDY_CAPTURE_BYTES = MAX_STUDY_RETAINED_BYTES;
const MAX_CSV_ROWS = 100_000;
const MAX_CSV_COLUMNS = 256;

const byteLength = (value: string): number => new TextEncoder().encode(value).length;
const uuid = (): string => globalThis.crypto.randomUUID();
const safeName = (value: string): string => value.trim() || "Dataset";
const record = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);

function reportedDatasetUnits(value: unknown): StudyJsonObject {
  if (!record(value)) return {};
  const provenance = record(value.provenance) ? value.provenance : {};
  const reported = value.units ?? provenance.units;
  let units: StudyJsonObject = {};
  const copied = copyStudyJson(reported);
  if (record(copied)) units = copied as StudyJsonObject;
  else if (Array.isArray(copied)) units = { reported: copied };
  if (typeof value.x_unit === "string") units.x_unit = value.x_unit;
  if (typeof value.y_unit === "string") units.y_unit = value.y_unit;
  return units;
}

export function preflightStudyDocument(study: SimulationStudy): { ok: true; bytes: number } | { ok: false; error: string } {
  const bytes = byteLength(JSON.stringify(study));
  return bytes > MAX_STUDY_DOCUMENT_BYTES
    ? { ok: false, error: "Simulation study exceeds the 256 MiB document limit." }
    : { ok: true, bytes };
}

/** Admit imported studies, then replace every identity while preserving internal dataset links. */
export function cloneImportedStudies(studies: readonly SimulationStudy[]): SimulationStudy[] {
  return normalizeStudies(studies).map(study => {
    const datasetIds = new Map(study.datasets.map(dataset => [dataset.id, uuid()]));
    return {
      ...study,
      id: uuid(),
      datasets: study.datasets.map(dataset => ({ ...dataset, id: datasetIds.get(dataset.id)! })),
      cases: study.cases.map(item => ({
        ...item,
        id: uuid(),
        datasetIds: item.datasetIds.flatMap(id => datasetIds.has(id) ? [datasetIds.get(id)!] : []),
        runs: item.runs.map(run => ({ ...run, id: uuid() })),
      })),
    };
  });
}

export type PrepareStudyDatasetOptions = {
  name: string;
  format: "json" | "csv";
  provenance: string;
  units?: StudyJsonObject;
  resultDerived?: boolean;
  createdAt?: string;
};

export type CsvPreview = { columns: string[]; rows: string[][] };

/** Parse ordinary RFC-4180-style quoted rows for preview; the original CSV remains authoritative. */
export function parseStudyCsv(text: string): CsvPreview {
  const records: string[][] = [];
  let row: string[] = [], field = "", quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') { field += '"'; index += 1; }
      else if (character === '"') quoted = false;
      else field += character;
    } else if (character === '"' && field.length === 0) quoted = true;
    else if (character === ",") { row.push(field); field = ""; }
    else if (character === "\n" || character === "\r") {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(field); records.push(row); row = []; field = "";
      if (records.length > MAX_CSV_ROWS + 1) throw new Error(`CSV dataset exceeds ${MAX_CSV_ROWS.toLocaleString()} data rows.`);
    } else field += character;
  }
  if (quoted) throw new Error("CSV dataset has an unterminated quoted field.");
  if (field.length || row.length) { row.push(field); records.push(row); }
  if (!records.length || !records[0].some(cell => cell.trim())) throw new Error("CSV dataset must contain a header row.");
  const columns = records[0];
  if (columns.length > MAX_CSV_COLUMNS) throw new Error(`CSV dataset exceeds ${MAX_CSV_COLUMNS} columns.`);
  if (records.some(record => record.length !== columns.length)) throw new Error("CSV rows must have the same number of columns as the header.");
  return { columns, rows: records.slice(1, 101) };
}

export function prepareStudyDataset(text: string, options: PrepareStudyDatasetOptions): StudyDataset {
  const bytes = byteLength(text);
  if (bytes > MAX_STUDY_ATTACHMENT_BYTES) throw new Error("Study dataset exceeds the 2 MiB attachment limit.");
  const createdAt = options.createdAt && Number.isFinite(Date.parse(options.createdAt))
    ? new Date(options.createdAt).toISOString() : new Date().toISOString();
  const base = {
    id: uuid(), name: safeName(options.name), provenance: options.provenance,
    createdAt, resultDerived: options.resultDerived === true,
  };
  if (options.format === "csv") {
    parseStudyCsv(text);
    return { ...base, kind: "csv", mediaType: "text/csv", rawText: text,
      units: (copyStudyJson(options.units ?? {}) ?? {}) as StudyJsonObject };
  }
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch { throw new Error("Study JSON dataset is not valid JSON."); }
  const payload = copyStudyJson(parsed);
  if (payload === undefined) throw new Error("Study JSON dataset contains unsupported, cyclic, or non-finite data.");
  const units = options.units === undefined ? reportedDatasetUnits(payload) : (copyStudyJson(options.units) ?? {}) as StudyJsonObject;
  return { ...base, kind: "json", mediaType: "application/json", payload, units };
}

export function exportStudyDataset(dataset: StudyDataset): { fileName: string; contents: string; mediaType: string } {
  const fileBase = dataset.name.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "dataset";
  if (dataset.kind === "csv") {
    if (dataset.rawText === undefined) throw new Error("CSV dataset has no embedded source text to export.");
    return { fileName: `${fileBase}.csv`, contents: dataset.rawText, mediaType: "text/csv" };
  }
  if (dataset.payload === undefined) throw new Error("JSON dataset has no embedded payload to export.");
  return { fileName: `${fileBase}.json`, contents: JSON.stringify(dataset.payload, null, 2), mediaType: "application/json" };
}

export function preflightStudyRunCapture(result: unknown, currentStudy?: SimulationStudy, currentCase?: SimulationStudyCase): { ok: true; bytes: number } | { ok: false; error: string } {
  const copied = copyStudyJson(result);
  if (copied === undefined) return { ok: false, error: "Result contains unsupported, cyclic, or non-finite data." };
  const bytes = studyJsonBytes(copied);
  if (currentCase && currentCase.runs.length >= MAX_STUDY_RUNS_PER_CASE) return { ok: false, error: `This case already has ${MAX_STUDY_RUNS_PER_CASE} recorded snapshots. Delete or export one before recording another.` };
  const retainedBytes = (currentCase?.runs ?? []).reduce((sum, run) => sum + (run.resultSnapshot === undefined ? 0 : studyJsonBytes(run.resultSnapshot)), 0);
  if (bytes > MAX_STUDY_CAPTURE_BYTES || retainedBytes + bytes > MAX_STUDY_CAPTURE_BYTES) return { ok: false, error: "Recorded snapshots would exceed the 96 MiB retained-data limit for this case. Delete or export a snapshot first." };
  const studyBytes = (currentStudy?.cases ?? []).reduce((caseSum, item) => caseSum + item.runs.reduce((runSum, run) =>
    runSum + (run.resultSnapshot === undefined ? 0 : studyJsonBytes(run.resultSnapshot)), 0), 0);
  const datasetBytes = (currentStudy?.datasets ?? []).reduce((sum, dataset) => sum
    + (dataset.rawText === undefined ? 0 : byteLength(dataset.rawText))
    + (dataset.payload === undefined ? 0 : studyJsonBytes(dataset.payload)), 0);
  if (studyBytes + datasetBytes + bytes > MAX_STUDY_CAPTURE_BYTES) return { ok: false, error: "Study datasets and recorded snapshots would exceed the 96 MiB retained-data limit. Delete or export retained data first." };
  if (currentStudy && currentCase) {
    const currentDocument = preflightStudyDocument(currentStudy);
    if (!currentDocument.ok) return currentDocument;
    const oldCurrentBytes = currentCase.resultSnapshot === undefined ? 0 : studyJsonBytes(currentCase.resultSnapshot);
    const capturedMetadataBytes = byteLength(JSON.stringify({ id: "00000000-0000-4000-8000-000000000000", capturedAt: new Date(0).toISOString(),
      association: "workspace-capture", caseType: currentCase.type, mode: currentCase.mode,
      scenario: currentCase.scenario, settings: currentCase.settings, facts: {} }));
    const projectedBytes = currentDocument.bytes - oldCurrentBytes + bytes * 2 + capturedMetadataBytes;
    if (projectedBytes > MAX_STUDY_DOCUMENT_BYTES) return { ok: false, error: "Recording this snapshot would exceed the 256 MiB study document limit." };
  }
  return { ok: true, bytes };
}

export function preflightStudyDatasetUpdate(datasets: readonly StudyDataset[], currentStudy?: SimulationStudy): { ok: true; bytes: number } | { ok: false; error: string } {
  if (datasets.length > MAX_STUDY_DATASETS) return { ok: false, error: `A study can retain at most ${MAX_STUDY_DATASETS} datasets.` };
  let bytes = 0;
  for (const dataset of datasets) {
    const itemBytes = (dataset.rawText === undefined ? 0 : byteLength(dataset.rawText))
      + (dataset.payload === undefined ? 0 : studyJsonBytes(dataset.payload));
    if (itemBytes > MAX_STUDY_ATTACHMENT_BYTES) return { ok: false, error: `${dataset.name} exceeds the 2 MiB attachment limit.` };
    bytes += itemBytes;
  }
  const runBytes = (currentStudy?.cases ?? []).reduce((caseSum, item) => caseSum + item.runs.reduce((runSum, run) =>
    runSum + (run.resultSnapshot === undefined ? 0 : studyJsonBytes(run.resultSnapshot)), 0), 0);
  if (bytes + runBytes > MAX_STUDY_RETAINED_BYTES) return { ok: false, error: "Study datasets and recorded snapshots would exceed the 96 MiB retained-data limit. Delete or export retained data first." };
  if (currentStudy) {
    const document = preflightStudyDocument({ ...currentStudy, datasets: [...datasets] });
    if (!document.ok) return document;
  }
  return { ok: true, bytes };
}

const canonical = (value: StudyJson | undefined): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
};
const hasUnitMetadata = (value: StudyJson | undefined): boolean => value !== undefined
  && (typeof value !== "object" || value === null || (Array.isArray(value) ? value.length > 0 : Object.keys(value).length > 0));

export type StudyComparisonCompatibility = { compatible: boolean; reasons: string[] };

/** Check identity and unit compatibility only; numerical comparison belongs to domain adapters. */
export function comparisonCompatibility(runs: readonly StudyRun[]): StudyComparisonCompatibility {
  if (runs.length < 2) return { compatible: false, reasons: ["Select at least two recorded runs."] };
  const reasons = new Set<string>(), first = runs[0].facts;
  if (!first.contract || runs.some(run => !run.facts.contract)) reasons.add("Compatibility not established: a result contract is not reported.");
  if (!hasUnitMetadata(first.units) || runs.some(run => !hasUnitMetadata(run.facts.units))) reasons.add("Compatibility not established: result units are not reported.");
  if (!runs[0].caseType || runs.some(run => !run.caseType)) reasons.add("Compatibility not established: simulation case type is not reported.");
  for (const run of runs.slice(1)) {
    const facts = run.facts;
    if ((first.contract ?? "") !== (facts.contract ?? "")) reasons.add("Result contracts differ.");
    if (runs[0].caseType !== run.caseType || runs[0].mode !== run.mode) reasons.add("Simulation case types or modes differ.");
    const designBound = Boolean(first.designId || first.designDigestSha256 || facts.designId || facts.designDigestSha256);
    if (designBound && (!first.designId || !first.designDigestSha256 || !facts.designId || !facts.designDigestSha256)) reasons.add("Compatibility not established: a source design binding is incomplete.");
    else if (designBound && (first.designId !== facts.designId || first.designDigestSha256 !== facts.designDigestSha256)) reasons.add("Source design bindings differ.");
    if (canonical(first.units) !== canonical(facts.units)) reasons.add("Result units differ.");
  }
  return { compatible: reasons.size === 0, reasons: [...reasons] };
}

export function studyMatchesQuery(study: SimulationStudy, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return true;
  return [study.name, study.notes, ...study.tags,
    ...study.cases.flatMap(item => [item.name, item.notes, item.type, item.mode]),
    ...study.datasets.flatMap(item => [item.name, item.provenance, item.kind]),
  ].some(value => value.toLocaleLowerCase().includes(needle));
}
