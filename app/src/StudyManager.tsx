// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { Archive, ArchiveRestore, ArrowDown, ArrowUp, Copy, Database, Download, FileJson, FolderPlus, Play, Plus, Save, Search, Trash2, Upload, X } from "lucide-react";
import { MAX_STUDY_DATASETS, normalizeStudies, type SimulationStudy, type SimulationStudyCase, type StudyDataset, type StudyRun } from "./simulationStudies";
import { comparisonCompatibility, exportStudyDataset, MAX_STUDY_DOCUMENT_BYTES, prepareStudyDataset, preflightStudyDatasetUpdate, preflightStudyDocument, studyMatchesQuery } from "./studyWorkspaceModel";
import { isDesktopShell, saveNativeTextFile } from "./workerBridge";
import "./studyManager.css";

export type StudyCaseType = { value: string; label: string; disabled?: boolean; description?: string };
const DEFAULT_TYPES: StudyCaseType[] = [
  { value: "pi", label: "Power integrity" }, { value: "si", label: "Signal integrity" },
  { value: "thermal", label: "Thermal" }, { value: "em", label: "Electromagnetics" },
];

type Props = {
  studies: SimulationStudy[]; currentType: string; activeCaseId: string | null;
  onCreateStudy: () => string;
  onUpdateStudy: (studyId: string, patch: Partial<SimulationStudy>) => void;
  onRemoveStudy: (studyId: string) => void;
  onAddCase: (studyId: string, type: string) => void;
  onUpdateCase: (studyId: string, caseId: string, patch: Partial<SimulationStudyCase>) => void;
  onDuplicateCase: (studyId: string, caseId: string) => void;
  onRemoveCase: (studyId: string, caseId: string) => void;
  onMoveCase: (studyId: string, caseId: string, destination: number) => void;
  onActivateCase: (studyId: string, studyCase: SimulationStudyCase) => void;
  onSaveCaseSetup: (studyId: string, studyCase: SimulationStudyCase) => void;
  onCaptureCaseResult: (studyId: string, studyCase: SimulationStudyCase) => void;
  onClose: () => void; caseTypes?: StudyCaseType[];
  onOpenResult?: (run: StudyRun, studyCase: SimulationStudyCase) => void;
  onImportStudies?: (studies: SimulationStudy[]) => void;
};
type Tab = "setup" | "runs" | "datasets" | "compare";
type DeleteTarget = { kind: "study" | "case" | "run" | "dataset"; id: string };

const cleanName = (text: string, fallback: string) => text.trim().replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "") || fallback;
const pretty = (value: unknown) => JSON.stringify(value, null, 2);
const dateText = (value: string) => { const date = new Date(value); return Number.isFinite(date.valueOf()) ? date.toLocaleString() : "Unknown time"; };
const valueText = (value: unknown) => value === null ? "null" : ["string", "number", "boolean"].includes(typeof value) ? String(value) : Array.isArray(value) ? `${value.length} items` : value && typeof value === "object" ? `${Object.keys(value).length} fields` : "Not recorded";

async function exportText(name: string, contents: string, mediaType: string) {
  if (isDesktopShell()) {
    const path = await saveNativeTextFile(name, contents, "result");
    return path ? `Exported to ${path}` : "Export canceled.";
  }
  const url = URL.createObjectURL(new Blob([contents], { type: mediaType }));
  const link = document.createElement("a"); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return `Download requested for ${name}.`;
}

function Facts({ run }: { run: StudyRun }) {
  const facts = { ...run.facts, units: run.facts.units ?? "Not recorded" };
  return <dl className="study-facts">{Object.entries(facts).map(([key, value]) => <div key={key}><dt>{key.replace(/([A-Z])/g, " $1")}</dt><dd>{valueText(value)}</dd></div>)}</dl>;
}

export default function StudyManager(props: Props) {
  const types = props.caseTypes?.length ? props.caseTypes : DEFAULT_TYPES;
  const defaultType = types.some(type => type.value === props.currentType && !type.disabled) ? props.currentType : types.find(type => !type.disabled)?.value ?? "";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(props.activeCaseId);
  const [newType, setNewType] = useState(defaultType);
  const [tab, setTab] = useState<Tab>("setup");
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [tagDraft, setTagDraft] = useState("");
  const [pendingDelete, setPendingDelete] = useState<DeleteTarget | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [datasetRole, setDatasetRole] = useState<"source" | "result">("source");
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [studyNameDraft, setStudyNameDraft] = useState("");
  const [caseNameDraft, setCaseNameDraft] = useState("");
  const [modeDraft, setModeDraft] = useState("");
  const importRef = useRef<HTMLInputElement>(null);
  const datasetRef = useRef<HTMLInputElement>(null);

  const visible = useMemo(() => {
    return props.studies.filter(study => (showArchived || !study.archived) && studyMatchesQuery(study, query));
  }, [props.studies, query, showArchived]);
  const study = visible.find(item => item.id === selectedId) ?? visible[0] ?? null;
  const selectedCase = study?.cases.find(item => item.id === caseId) ?? study?.cases.find(item => item.id === props.activeCaseId) ?? study?.cases[0] ?? null;
  const inspectedRun = selectedCase?.runs.find(run => run.id === runId) ?? (selectedCase?.runs.length ? selectedCase.runs[selectedCase.runs.length - 1] : null);
  const compared = selectedCase?.runs.filter(run => compareIds.includes(run.id)) ?? [];

  useEffect(() => { if (study && selectedId !== study.id) setSelectedId(study.id); }, [study?.id]);
  useEffect(() => { if (selectedCase && caseId !== selectedCase.id) setCaseId(selectedCase.id); }, [selectedCase?.id, study?.id]);
  useEffect(() => { setStudyNameDraft(study?.name ?? ""); }, [study?.id, study?.name]);
  useEffect(() => { setCaseNameDraft(selectedCase?.name ?? ""); }, [selectedCase?.id, selectedCase?.name]);
  useEffect(() => { setModeDraft(selectedCase?.mode ?? ""); }, [selectedCase?.id, selectedCase?.mode]);
  useEffect(() => {
    setCompareIds(ids => ids.filter(id => selectedCase?.runs.some(run => run.id === id)));
    setRunId(id => id && selectedCase?.runs.some(run => run.id === id) ? id : null);
  }, [selectedCase?.id, selectedCase?.runs]);

  const addTags = () => {
    if (!study) return;
    const additions = tagDraft.split(",").map(tag => tag.trim()).filter(Boolean);
    props.onUpdateStudy(study.id, { tags: [...new Set([...study.tags, ...additions])] }); setTagDraft("");
  };
  const importFile = async (file?: File) => {
    if (!file) return;
    if (file.size > MAX_STUDY_DOCUMENT_BYTES) { setMessage("Import rejected: study JSON exceeds 256 MiB."); return; }
    try {
      const imported = normalizeStudies(JSON.parse(await file.text()));
      if (!imported.length) throw new Error("No valid studies were found.");
      if (!props.onImportStudies) throw new Error("Study import is unavailable in this workspace.");
      props.onImportStudies(imported); setSelectedId(null);
      setMessage(`Imported ${imported.length} stud${imported.length === 1 ? "y" : "ies"}.`);
    } catch (error) { setMessage(error instanceof Error ? `Import rejected: ${error.message}` : "Import rejected."); }
    if (importRef.current) importRef.current.value = "";
  };
  const attachDataset = async (file?: File) => {
    if (!study || !file) return;
    if (file.size > 2 * 1024 * 1024) { setMessage("Dataset rejected: file exceeds 2 MiB."); return; }
    if (study.datasets.length >= MAX_STUDY_DATASETS) { setMessage(`Dataset rejected: limit is ${MAX_STUDY_DATASETS} per study.`); return; }
    try {
      const text = await file.text();
      const csv = file.name.toLowerCase().endsWith(".csv") || file.type === "text/csv";
      const dataset = prepareStudyDataset(text, { name: file.name, format: csv ? "csv" : "json", provenance: datasetRole === "result" ? "User-attached result-derived file" : "User-attached source file", resultDerived: datasetRole === "result" });
      const datasets = [...study.datasets, dataset];
      const admission = preflightStudyDatasetUpdate(datasets, study);
      if (!admission.ok) throw new Error(admission.error);
      props.onUpdateStudy(study.id, { datasets });
      if (selectedCase) props.onUpdateCase(study.id, selectedCase.id, { datasetIds: [...new Set([...selectedCase.datasetIds, dataset.id])] });
      setMessage(`Attached ${file.name}. Units remain unassigned unless the dataset supplies them.`);
    } catch (error) { setMessage(error instanceof Error ? `Dataset rejected: ${error.message}` : "Dataset rejected."); }
    if (datasetRef.current) datasetRef.current.value = "";
  };
  const exportStudy = async () => {
    if (!study) return;
    try {
      const contents = JSON.stringify({ version: study.version, studies: [study] });
      const admission = preflightStudyDocument(study);
      if (!admission.ok || new TextEncoder().encode(contents).length > MAX_STUDY_DOCUMENT_BYTES) throw new Error(admission.ok ? "Study export exceeds the 256 MiB study document limit." : admission.error);
      setMessage(await exportText(`${cleanName(study.name, "study")}.spike-study.json`, contents, "application/json"));
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Export failed."); }
  };
  const exportDataset = async (dataset: StudyDataset) => {
    try { const exported = exportStudyDataset(dataset); setMessage(await exportText(exported.fileName, exported.contents, exported.mediaType)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Export failed."); }
  };
  const confirmDelete = () => {
    if (!study || !pendingDelete) return;
    if (pendingDelete.kind === "study") { props.onRemoveStudy(study.id); setSelectedId(null); }
    else if (pendingDelete.kind === "case") props.onRemoveCase(study.id, pendingDelete.id);
    else if (pendingDelete.kind === "dataset") props.onUpdateStudy(study.id, { datasets: study.datasets.filter(dataset => dataset.id !== pendingDelete.id) });
    else if (selectedCase) props.onUpdateCase(study.id, selectedCase.id, { runs: selectedCase.runs.filter(run => run.id !== pendingDelete.id) });
    setPendingDelete(null);
  };
  const selectedType = types.find(type => type.value === newType);
  const compatibility = comparisonCompatibility(compared);

  return <div className="modal-shade study-manager-shade" role="dialog" aria-modal="true" aria-label="Simulation studies" onKeyDown={event => { if (event.key === "Escape" && pendingDelete) { event.stopPropagation(); setPendingDelete(null); } }}>
    <section className="study-manager">
      <header className="study-manager-header"><div><b>Simulation studies</b><small>Saved setups, recorded results, and supplied data. This manager does not start a solver.</small></div><div className="study-header-actions"><button onClick={() => importRef.current?.click()}><Upload size={15}/> Import</button><button disabled={!study} onClick={() => void exportStudy()}><Download size={15}/> Export</button><button className="canvas-icon" aria-label="Close studies" onClick={props.onClose}><X size={17}/></button></div></header>
      <input ref={importRef} className="study-file-input" type="file" accept="application/json,.json" aria-label="Import study JSON" onChange={event => void importFile(event.target.files?.[0])}/>
      <input ref={datasetRef} className="study-file-input" type="file" accept="application/json,text/csv,.json,.csv" aria-label="Attach dataset file" onChange={event => void attachDataset(event.target.files?.[0])}/>
      {message && <div className="study-message" role="status"><span>{message}</span><button aria-label="Dismiss status" onClick={() => setMessage("")}><X size={14}/></button></div>}
      <div className="study-manager-body">
        <aside className="study-navigator" aria-label="Study navigator">
          <button className="primary-btn" onClick={() => setSelectedId(props.onCreateStudy())}><FolderPlus size={15}/> New study</button>
          <label className="study-search"><Search size={14}/><span className="sr-only">Search studies</span><input aria-label="Search studies" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search studies, tags, cases"/></label>
          <label className="study-check"><input type="checkbox" checked={showArchived} onChange={event => setShowArchived(event.target.checked)}/> Show archived</label>
          <div className="study-nav-results">{visible.map(item => <button key={item.id} className={item.id === study?.id ? "selected" : ""} onClick={() => { setSelectedId(item.id); setCaseId(null); }}><span><b title={item.name}>{item.name}</b>{item.archived && <Archive size={13}/>}</span><small>{item.cases.length} cases · {item.datasets.length} datasets</small><span className="study-tag-row">{item.tags.slice(0, 3).map(tag => <em key={tag}>{tag}</em>)}</span></button>)}{!visible.length && <p className="study-muted">No studies match this view.</p>}</div>
        </aside>
        <main className="study-case-pane">{!study ? <div className="study-empty"><h3>No studies yet</h3><p>Create a study or import bounded SPIKE study JSON.</p></div> : <>
          <div className="study-heading"><label>Study name<input aria-label="Study name" value={studyNameDraft} onChange={event => setStudyNameDraft(event.target.value)} onBlur={() => props.onUpdateStudy(study.id, { name: studyNameDraft })} onKeyDown={event => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { setStudyNameDraft(study.name); event.currentTarget.blur(); } }}/></label><button className="study-details-toggle" onClick={() => setInspectorOpen(open => !open)}>{selectedCase ? "Case details" : "Study datasets"}</button><button onClick={() => props.onUpdateStudy(study.id, { archived: !study.archived })}>{study.archived ? <ArchiveRestore size={15}/> : <Archive size={15}/>} {study.archived ? "Restore" : "Archive"}</button><button className="danger-btn" onClick={() => setPendingDelete({ kind: "study", id: study.id })}><Trash2 size={15}/> Delete</button></div>
          <label className="study-note">Purpose and notes<textarea aria-label="Study notes" value={study.notes} onChange={event => props.onUpdateStudy(study.id, { notes: event.target.value })} rows={2}/></label>
          <div className="study-tags"><span>Tags</span>{study.tags.map(tag => <button key={tag} title={`Remove tag ${tag}`} onClick={() => props.onUpdateStudy(study.id, { tags: study.tags.filter(item => item !== tag) })}>{tag}<X size={12}/></button>)}<label><span className="sr-only">Add tags</span><input aria-label="Add tags" value={tagDraft} onChange={event => setTagDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); addTags(); } }} placeholder="Add tag"/></label><button disabled={!tagDraft.trim()} onClick={addTags}>Add</button></div>
          <div className="study-add-case"><label>Add case<select aria-label="New case type" value={newType} onChange={event => setNewType(event.target.value)}>{types.map(type => <option key={type.value} value={type.value} disabled={type.disabled}>{type.label}{type.disabled ? " (unavailable)" : ""}</option>)}</select></label><button className="primary-btn" disabled={!newType || selectedType?.disabled} title={selectedType?.disabled ? selectedType.description ?? "Unavailable in this workspace" : undefined} onClick={() => props.onAddCase(study.id, newType)}><Plus size={15}/> Add</button></div>
          <div className="study-case-table" role="table" aria-label="Study cases"><div className="study-case-table-head" role="row"><span>#</span><span>Case</span><span>Domain / mode</span><span>Source status</span><span>Evidence</span><span>Order</span></div>{study.cases.map((item, index) => {
            const active = item.id === props.activeCaseId;
            return <div key={item.id} role="row" tabIndex={0} aria-selected={item.id === selectedCase?.id} className={`study-case-row ${item.id === selectedCase?.id ? "selected" : ""} ${active ? "active" : ""}`} onClick={() => setCaseId(item.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setCaseId(item.id); } }}><span>{index + 1}</span><span><b title={item.name}>{item.name}</b>{active && <em>Active setup</em>}</span><span><b>{types.find(type => type.value === item.type)?.label ?? item.type}</b><small title={item.mode}>{item.mode || "Mode not recorded"}</small></span><span>{active ? "Loaded in workspace" : "Saved setup"}</span><span>{item.runs.length} runs · {item.datasetIds.length} data</span><span className="study-order"><button aria-label={`Move ${item.name} up`} disabled={index === 0} onClick={event => { event.stopPropagation(); props.onMoveCase(study.id, item.id, index - 1); }}><ArrowUp size={13}/></button><button aria-label={`Move ${item.name} down`} disabled={index === study.cases.length - 1} onClick={event => { event.stopPropagation(); props.onMoveCase(study.id, item.id, index + 1); }}><ArrowDown size={13}/></button></span></div>;
          })}{!study.cases.length && <p className="study-muted">Add a case to retain a setup for this study.</p>}</div>
        </>}</main>
        <aside className={`study-inspector ${inspectorOpen ? "open" : ""}`} aria-label="Case details">{study && selectedCase ? <>
          <div className="study-inspector-title"><div><small>{types.find(type => type.value === selectedCase.type)?.label ?? selectedCase.type}</small><h3 title={selectedCase.name}>{selectedCase.name}</h3></div><span><button className="study-inspector-close canvas-icon" aria-label="Hide case details" onClick={() => setInspectorOpen(false)}><X size={15}/></button><button className="danger-btn canvas-icon" aria-label={`Delete ${selectedCase.name}`} onClick={() => setPendingDelete({ kind: "case", id: selectedCase.id })}><Trash2 size={15}/></button></span></div>
          <div className="study-tabs" role="tablist">{(["setup", "runs", "datasets", "compare"] as Tab[]).map(name => <button key={name} role="tab" aria-selected={tab === name} onClick={() => setTab(name)}>{name === "runs" ? "Recorded runs" : name[0].toUpperCase() + name.slice(1)}</button>)}</div>
          <div className="study-tab-content">{tab === "setup" && <>
            <label>Case name<input aria-label="Selected case name" value={caseNameDraft} onChange={event => setCaseNameDraft(event.target.value)} onBlur={() => props.onUpdateCase(study.id, selectedCase.id, { name: caseNameDraft })} onKeyDown={event => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { setCaseNameDraft(selectedCase.name); event.currentTarget.blur(); } }}/></label>
            <label>Mode<input aria-label="Selected case mode" value={modeDraft} onChange={event => setModeDraft(event.target.value)} onBlur={() => props.onUpdateCase(study.id, selectedCase.id, { mode: modeDraft })} onKeyDown={event => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { setModeDraft(selectedCase.mode); event.currentTarget.blur(); } }}/></label>
            <label>Scenario label<input aria-label="Selected case scenario" value={String(selectedCase.scenario.label ?? "")} onChange={event => props.onUpdateCase(study.id, selectedCase.id, { scenario: { ...selectedCase.scenario, label: event.target.value } })}/></label>
            <label>Notes<textarea aria-label="Selected case notes" rows={3} value={selectedCase.notes} onChange={event => props.onUpdateCase(study.id, selectedCase.id, { notes: event.target.value })}/></label>
            <div className="study-action-stack"><button onClick={() => props.onActivateCase(study.id, selectedCase)}><Play size={14}/> Activate saved setup</button><button disabled={selectedCase.id !== props.activeCaseId} onClick={() => props.onSaveCaseSetup(study.id, selectedCase)}><Save size={14}/> Save current setup</button><button disabled={selectedCase.id !== props.activeCaseId} title={selectedCase.id !== props.activeCaseId ? "Activate this case before recording the current workspace result." : "Save a workspace-captured snapshot; this does not rerun the solver."} onClick={() => props.onCaptureCaseResult(study.id, selectedCase)}><Save size={14}/> Record snapshot</button><button onClick={() => props.onDuplicateCase(study.id, selectedCase.id)}><Copy size={14}/> Duplicate case</button></div>
            <details><summary>Saved setup JSON</summary><pre>{pretty({ scenario: selectedCase.scenario, settings: selectedCase.settings })}</pre></details>
          </>}
          {tab === "runs" && <>{!selectedCase.runs.length ? <p className="study-muted">No recorded snapshots. Recording freezes the current workspace result, setup, and reported status. Capture time is not a solver execution timestamp.</p> : <div className="study-run-layout"><div className="study-run-list">{[...selectedCase.runs].reverse().map(run => <button key={run.id} className={run.id === inspectedRun?.id ? "selected" : ""} onClick={() => setRunId(run.id)}><span>{dateText(run.capturedAt)}{run.facts.status ? ` · ${run.facts.status}` : ""}</span><small>{run.facts.modelStatus ? `Model: ${run.facts.modelStatus}` : "Model status not reported"}</small></button>)}</div>{inspectedRun && <div className="study-run-detail"><h4>Workspace captured {dateText(inspectedRun.capturedAt)}</h4><Facts run={inspectedRun}/><div className="study-inline-actions">{props.onOpenResult && <button disabled={inspectedRun.resultSnapshot == null} title={inspectedRun.resultSnapshot == null ? "This capture has no embedded result payload." : undefined} onClick={() => props.onOpenResult?.(inspectedRun, selectedCase)}>Load capture in workspace</button>}<button onClick={() => void exportText(`${cleanName(selectedCase.name, "case")}-${cleanName(inspectedRun.id, "run")}.json`, pretty(inspectedRun), "application/json").then(setMessage)}><Download size={13}/> Export</button><button className="danger-btn" onClick={() => setPendingDelete({ kind: "run", id: inspectedRun.id })}><Trash2 size={13}/> Delete</button></div><details><summary>Raw recorded JSON</summary><pre>{pretty(inspectedRun)}</pre></details></div>}</div>}</>}
          {tab === "datasets" && <><label>Attachment role<select aria-label="Dataset attachment role" value={datasetRole} onChange={event => setDatasetRole(event.target.value as "source" | "result")}><option value="source">Source / reference data</option><option value="result">Result-derived data</option></select></label><button className="primary-btn" onClick={() => datasetRef.current?.click()}><Database size={14}/> Attach JSON or CSV</button><p className="study-muted">Choose the role explicitly. Result-derived payloads may be stripped from result-free project copies. Maximum 2 MiB.</p><div className="study-dataset-list">{study.datasets.map(dataset => <article key={dataset.id}><FileJson size={18}/><div><b title={dataset.name}>{dataset.name}</b><small>{dataset.kind.toUpperCase()} · {dataset.resultDerived ? "Result-derived" : "Source"} · {dataset.provenance || "No provenance supplied"}</small></div><button aria-label={`Export ${dataset.name}`} onClick={() => void exportDataset(dataset)}><Download size={13}/></button><button aria-label={`${selectedCase.datasetIds.includes(dataset.id) ? "Unlink" : "Link"} ${dataset.name}`} onClick={() => props.onUpdateCase(study.id, selectedCase.id, { datasetIds: selectedCase.datasetIds.includes(dataset.id) ? selectedCase.datasetIds.filter(id => id !== dataset.id) : [...selectedCase.datasetIds, dataset.id] })}>{selectedCase.datasetIds.includes(dataset.id) ? <X size={13}/> : <Plus size={13}/>}</button><button aria-label={`Remove ${dataset.name}`} onClick={() => setPendingDelete({ kind: "dataset", id: dataset.id })}><Trash2 size={13}/></button></article>)}{!study.datasets.length && <p className="study-muted">No datasets are attached to this study.</p>}</div></>}
          {tab === "compare" && <><p className="study-muted">Select two or more recorded snapshots. Values retain their reported units and model status.</p><div className="study-compare-picker">{selectedCase.runs.map(run => <label key={run.id}><input type="checkbox" checked={compareIds.includes(run.id)} onChange={event => setCompareIds(ids => event.target.checked ? [...ids, run.id] : ids.filter(id => id !== run.id))}/><span>{dateText(run.capturedAt)}{run.facts.status ? ` · ${run.facts.status}` : ""}</span></label>)}</div>{compared.length >= 2 && compatibility.compatible ? <div className="study-compare-table"><table><thead><tr><th>Fact</th>{compared.map(run => <th key={run.id}>{dateText(run.capturedAt)}</th>)}</tr></thead><tbody>{["status", "modelStatus", "contract", "designId", "units"].map(key => <tr key={key}><th>{key}</th>{compared.map(run => <td key={run.id}>{key === "units" ? <pre>{pretty(run.facts.units ?? "Not recorded")}</pre> : String(run.facts[key as keyof typeof run.facts] ?? "Not recorded")}</td>)}</tr>)}</tbody></table></div> : <p className="study-muted">{compared.length < 2 ? "Select at least two runs to compare." : `Comparison unavailable: ${compatibility.reasons.join(" ")}`}</p>}</>}
          </div>
        </> : study ? <div className="study-tab-content"><div className="study-inspector-title"><h3>Study datasets</h3><button className="study-inspector-close canvas-icon" aria-label="Hide study datasets" onClick={() => setInspectorOpen(false)}><X size={15}/></button></div><p className="study-muted">This study has no cases. Attach source or result-derived data at study scope; it can be linked when a case is added.</p><label>Attachment role<select aria-label="Dataset attachment role" value={datasetRole} onChange={event => setDatasetRole(event.target.value as "source" | "result")}><option value="source">Source / reference data</option><option value="result">Result-derived data</option></select></label><button className="primary-btn" onClick={() => datasetRef.current?.click()}><Database size={14}/> Attach JSON or CSV</button><div className="study-dataset-list">{study.datasets.map(dataset => <article key={dataset.id}><FileJson size={18}/><div><b title={dataset.name}>{dataset.name}</b><small>{dataset.resultDerived ? "Result-derived" : "Source"} · {dataset.provenance}</small></div><button aria-label={`Export ${dataset.name}`} onClick={() => void exportDataset(dataset)}><Download size={13}/></button><button aria-label={`Remove ${dataset.name}`} onClick={() => setPendingDelete({ kind: "dataset", id: dataset.id })}><Trash2 size={13}/></button></article>)}{!study.datasets.length && <p className="study-muted">No study datasets are attached.</p>}</div></div> : <p className="study-muted">Select a study to inspect its cases and evidence.</p>}</aside>
      </div>
      {pendingDelete && <div className="study-delete-confirm" role="alertdialog" aria-modal="true" aria-label={`Confirm ${pendingDelete.kind} deletion`}><div><b>Delete this {pendingDelete.kind}?</b><p>{pendingDelete.kind === "study" ? "This removes only the selected study and the evidence stored inside it." : pendingDelete.kind === "case" ? "Other cases in this study remain unchanged." : pendingDelete.kind === "dataset" ? "This removes the attachment and its links from all cases in this study." : "This removes only the selected recorded run."}</p><span><button onClick={() => setPendingDelete(null)}>Cancel</button><button className="danger-btn" onClick={confirmDelete}>Delete {pendingDelete.kind}</button></span></div></div>}
    </section>
  </div>;
}
