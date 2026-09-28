// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { ArrowDown, ArrowUp, Copy, FolderPlus, Play, Plus, Save, Trash2, X } from "lucide-react";
import type { SimulationStudy, SimulationStudyCase } from "./simulationStudies";
import "./studyManager.css";

const caseTypes = [
  { value: "pi", label: "Power integrity" },
  { value: "si", label: "Signal integrity" },
  { value: "thermal", label: "Thermal" },
  { value: "em", label: "Electromagnetics" },
];

type Props = {
  studies: SimulationStudy[];
  currentType: string;
  activeCaseId: string | null;
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
  onClose: () => void;
};

export default function StudyManager(props: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newType, setNewType] = useState(props.currentType);
  const study = props.studies.find(item => item.id === selectedId) ?? props.studies[0] ?? null;

  return <div className="modal-shade study-manager-shade" role="dialog" aria-modal="true" aria-label="Simulation studies">
    <section className="study-manager">
      <header><div><b>Simulation studies</b><small>Group PI, SI, thermal, and EM cases in one project. Repeat a type for different conditions.</small></div><button className="canvas-icon" aria-label="Close studies" onClick={props.onClose}><X size={17} /></button></header>
      <div className="study-manager-body">
        <aside className="study-list"><button className="primary-btn" onClick={() => setSelectedId(props.onCreateStudy())}><FolderPlus size={15} /> New study</button>
          {props.studies.map(item => <button key={item.id} className={item.id === study?.id ? "selected" : ""} onClick={() => setSelectedId(item.id)}><b>{item.name}</b><small>{item.cases.length} case{item.cases.length === 1 ? "" : "s"}</small></button>)}
        </aside>
        <main>{!study ? <div className="study-empty"><h3>No studies yet</h3><p>Create a study, then add cases from any analysis domain.</p></div> : <>
          <div className="study-heading"><label>Study name<input aria-label="Study name" value={study.name} onChange={event => props.onUpdateStudy(study.id, { name: event.target.value })} /></label><button className="danger-btn" title="Delete study" onClick={() => props.onRemoveStudy(study.id)}><Trash2 size={15} /> Delete study</button></div>
          <label className="study-note">Purpose and notes<textarea aria-label="Study notes" value={study.notes} onChange={event => props.onUpdateStudy(study.id, { notes: event.target.value })} rows={2} /></label>
          <div className="study-add-case"><label>Add simulation<select aria-label="New case type" value={newType} onChange={event => setNewType(event.target.value)}>{caseTypes.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label><button className="primary-btn" onClick={() => props.onAddCase(study.id, newType)}><Plus size={15} /> Add case</button></div>
          <p className="study-guidance">Activate a case to load its saved setup into the matching workspace. Run it with that workspace’s controls, then capture its result here. Save setup after changing inputs.</p>
          <div className="study-cases">{study.cases.map((item, index) => <article key={item.id} className={item.id === props.activeCaseId ? "active" : ""}>
            <div className="study-case-top"><span className="study-index">{index + 1}</span><strong>{caseTypes.find(type => type.value === item.type)?.label ?? item.type}</strong><span>{item.mode}</span><small>{item.resultSnapshot ? "Result saved" : "No case result"}</small><div className="study-order"><button title="Move up" aria-label={`Move ${item.name} up`} disabled={index === 0} onClick={() => props.onMoveCase(study.id, item.id, index - 1)}><ArrowUp size={14} /></button><button title="Move down" aria-label={`Move ${item.name} down`} disabled={index === study.cases.length - 1} onClick={() => props.onMoveCase(study.id, item.id, index + 1)}><ArrowDown size={14} /></button></div></div>
            <div className="study-case-fields"><label>Case name<input aria-label={`Case name ${index + 1}`} value={item.name} onChange={event => props.onUpdateCase(study.id, item.id, { name: event.target.value })} /></label><label>Conditions / scenario<input aria-label={`Conditions ${index + 1}`} value={String(item.scenario?.label ?? "")} placeholder="e.g. closed enclosure, 25 °C" onChange={event => props.onUpdateCase(study.id, item.id, { scenario: { ...item.scenario, label: event.target.value } })} /></label></div>
            <label className="study-case-notes">Notes<input aria-label={`Case notes ${index + 1}`} value={item.notes} onChange={event => props.onUpdateCase(study.id, item.id, { notes: event.target.value })} /></label>
            <div className="study-case-actions"><button onClick={() => props.onActivateCase(study.id, item)}><Play size={14} /> Activate</button><button onClick={() => props.onSaveCaseSetup(study.id, item)}><Save size={14} /> Save current setup</button><button onClick={() => props.onCaptureCaseResult(study.id, item)}><Save size={14} /> Capture result</button><button title="Duplicate case" onClick={() => props.onDuplicateCase(study.id, item.id)}><Copy size={14} /> Duplicate</button><button className="danger-btn" title="Delete case" onClick={() => props.onRemoveCase(study.id, item.id)}><Trash2 size={14} /></button></div>
          </article>)}{!study.cases.length && <p className="study-empty">Add a simulation case to this study.</p>}</div>
        </>}</main>
      </div>
    </section>
  </div>;
}
