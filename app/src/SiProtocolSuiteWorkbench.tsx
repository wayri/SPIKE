import { useMemo, useRef, useState } from "react";
import { AlertTriangle, BookOpenCheck, Boxes, CheckCircle2, Code2, Download, FileJson, Network, Play, Plus, Save, Settings2, ShieldAlert, Upload, X } from "lucide-react";
import {
  builtinSiProtocolSuites, createCustomSiProtocolSuite, protocolSuiteExtensionBundle,
  SiAnalysisId, SiProtocolSuite, validateSiProtocolSuite,
} from "./siProtocolSuites";

type Props = {
  extensionSuites?: SiProtocolSuite[];
  onClose: () => void;
  onStatus: (message: string) => void;
  onOpenTopology: () => void;
  onOpenNetwork: (suite: SiProtocolSuite) => void;
  onOpenExtensions: () => void;
};

const STORAGE_KEY = "spike.si.custom-protocol-suites.v1";
const ANALYSES: { id: SiAnalysisId; label: string }[] = [
  { id: "topology", label: "Topology" }, { id: "impedance", label: "Impedance" },
  { id: "rlgc", label: "RLGC" }, { id: "s_parameters", label: "S-parameters" },
  { id: "tdr_tdt", label: "TDR / TDT" }, { id: "insertion_return_loss", label: "Insertion / return loss" },
  { id: "next_fext", label: "NEXT / FEXT" }, { id: "mode_conversion", label: "Mode conversion" },
  { id: "skew_delay", label: "Skew / delay" }, { id: "eye", label: "Eye" },
  { id: "jitter", label: "Jitter" }, { id: "pam4", label: "PAM4" },
  { id: "power_aware", label: "Power-aware SI" }, { id: "compliance_review", label: "Compliance evidence review" },
];

function loadCustomSuites(): SiProtocolSuite[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as unknown[];
    return parsed.filter(item => validateSiProtocolSuite(item).length === 0) as SiProtocolSuite[];
  } catch { return []; }
}

function download(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function contributionSuites(values: SiProtocolSuite[] | undefined): SiProtocolSuite[] {
  return (values ?? []).filter(value => validateSiProtocolSuite(value).length === 0);
}

export default function SiProtocolSuiteWorkbench({ extensionSuites, onClose, onStatus, onOpenTopology, onOpenNetwork, onOpenExtensions }: Props) {
  const importRef = useRef<HTMLInputElement>(null);
  const [customSuites, setCustomSuites] = useState<SiProtocolSuite[]>(loadCustomSuites);
  const [selectedId, setSelectedId] = useState("spike.si.ddr");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"suite" | "builder">("suite");
  const [builderMode, setBuilderMode] = useState<"gui" | "code">("gui");
  const [draft, setDraft] = useState<SiProtocolSuite>(createCustomSiProtocolSuite);
  const [code, setCode] = useState(() => JSON.stringify(createCustomSiProtocolSuite(), null, 2));
  const [codeErrors, setCodeErrors] = useState<string[]>([]);
  const suites = useMemo(() => {
    const byId = new Map<string, SiProtocolSuite>();
    [...builtinSiProtocolSuites, ...contributionSuites(extensionSuites), ...customSuites].forEach(item => byId.set(item.id, item));
    return [...byId.values()];
  }, [customSuites, extensionSuites]);
  const filtered = suites.filter(item => `${item.name} ${item.family} ${item.description}`.toLowerCase().includes(query.toLowerCase()));
  const selected = suites.find(item => item.id === selectedId) ?? filtered[0] ?? suites[0];
  const draftErrors = validateSiProtocolSuite(draft);

  const updateDraft = (next: SiProtocolSuite) => {
    setDraft(next);
    setCode(JSON.stringify(next, null, 2));
    setCodeErrors(validateSiProtocolSuite(next));
  };
  const applyCode = () => {
    try {
      const parsed = JSON.parse(code) as SiProtocolSuite;
      const errors = validateSiProtocolSuite(parsed);
      setCodeErrors(errors);
      if (!errors.length) setDraft(parsed);
    } catch (error) { setCodeErrors([error instanceof Error ? error.message : String(error)]); }
  };
  const saveDraft = () => {
    const errors = validateSiProtocolSuite(draft);
    if (errors.length) { setCodeErrors(errors); onStatus(`Protocol suite has ${errors.length} validation error(s)`); return; }
    const safe = { ...draft, custom: true, qualification: draft.qualification === "validated" ? "setup_only" as const : draft.qualification };
    const next = [...customSuites.filter(item => item.id !== safe.id), safe];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setCustomSuites(next);
    setSelectedId(safe.id);
    setView("suite");
    onStatus(`${safe.name} saved as a declarative SI suite; no solver or compliance capability was inferred`);
  };
  const importSuite = async (file?: File) => {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as SiProtocolSuite;
      const errors = validateSiProtocolSuite(parsed);
      if (errors.length) throw new Error(errors.join(" "));
      updateDraft({ ...parsed, custom: true, qualification: parsed.qualification === "validated" ? "setup_only" : parsed.qualification });
      setView("builder");
      setBuilderMode("gui");
      onStatus(`${file.name} loaded into the protocol suite builder`);
    } catch (error) { onStatus(`Protocol suite import rejected: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const runAnalysis = (analysisId: SiAnalysisId) => {
    if (!selected) return;
    if (analysisId === "topology") { onOpenTopology(); return; }
    if ([
      "impedance", "rlgc", "s_parameters", "tdr_tdt", "insertion_return_loss",
      "next_fext", "mode_conversion", "skew_delay", "eye", "jitter",
    ].includes(analysisId)) { onOpenNetwork(selected); return; }
    onStatus(`${selected.name}: ${ANALYSES.find(item => item.id === analysisId)?.label ?? analysisId} setup is retained, but execution remains blocked until its declared solver/model/validation capabilities pass`);
  };

  return <div className="modal-backdrop"><section className="modal si-suite-workbench" role="dialog" aria-modal="true" aria-label="SI protocol suites">
    <header><div><span className="eyebrow">SIGNAL INTEGRITY</span><h2>Protocol suites</h2></div><div className="si-suite-header-actions"><button className={view === "suite" ? "selected" : ""} onClick={() => setView("suite")}><Network size={14} /> Suites</button><button className={view === "builder" ? "selected" : ""} onClick={() => setView("builder")}><Plus size={14} /> Extension builder</button><button className="icon-btn" onClick={onClose} title="Close"><X size={17} /></button></div></header>
    {view === "suite" ? <div className="si-suite-layout">
      <aside className="si-suite-catalog">
        <label><Settings2 size={13} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Filter protocol suites" /></label>
        <div>{filtered.map(item => <button key={item.id} className={selected?.id === item.id ? "selected" : ""} onClick={() => setSelectedId(item.id)}><span><b>{item.name}</b><small>{item.family} · {item.revision}</small></span><em>{item.custom ? "CUSTOM" : "BUILT-IN"}</em></button>)}</div>
      </aside>
      {selected && <main className="si-suite-detail">
        <div className="si-suite-title"><div><span className="eyebrow">{selected.family} WORKSPACE</span><h3>{selected.name}</h3><p>{selected.description}</p></div><span className="si-suite-qualification">{selected.qualification.replace(/_/g, " ")}</span></div>
        <div className="si-suite-gate"><ShieldAlert size={17} /><span><b>Configuration is available; protocol compliance is not claimed.</b> Built-in profiles contain workflow structure, not licensed normative limits. Solver results remain gated by their result-level blocked uses, source/receiver/package models, validation evidence, and user-supplied licensed limits.</span></div>
        <div className="si-suite-summary"><div><span>SIGNALING</span><b>{selected.signaling.replace(/_/g, " ")}</b></div><div><span>ENCODING</span><b>{selected.encoding}</b></div><div><span>ANALYSES</span><b>{selected.analyses.length}</b></div><div><span>LIMIT RULES</span><b>{selected.rules.length || "user supplied"}</b></div></div>
        <div className="si-suite-columns"><section><h4>Channel topology</h4>{selected.topology.map(item => <div className="si-suite-line" key={item}><Network size={13} /> {item}</div>)}<button className="secondary-btn" onClick={onOpenTopology}>Open Channel Tree</button></section><section><h4>Required inputs</h4>{selected.requiredInputs.map(item => <div className="si-suite-line warning" key={item}><AlertTriangle size={13} /> {item}</div>)}<small>Missing models or unreviewed limits block the affected analysis stage.</small></section></div>
        <section className="si-suite-analyses"><h4>Dedicated analysis plan</h4><div>{selected.analyses.map(analysis => <button key={analysis.id} onClick={() => runAnalysis(analysis.id)}><span>{analysis.status === "available_input_review" ? <CheckCircle2 size={15} /> : <ShieldAlert size={15} />}<b>{analysis.name}</b></span><small>{analysis.requiredCapabilities.join(" · ") || "no additional capability"}</small><em>{analysis.status === "available_input_review" ? "CONFIGURE" : "GATED"}</em></button>)}</div></section>
        <footer className="si-suite-footer"><span><BookOpenCheck size={14} /> {selected.provenance.title} · {selected.provenance.access.replace(/_/g, " ")}</span><button className="secondary-btn" onClick={onOpenExtensions}><Boxes size={14} /> Extension manager</button><button className="primary-btn" onClick={() => runAnalysis("topology")}><Play size={14} /> Configure suite</button></footer>
      </main>}
    </div> : <div className="si-builder">
      <div className="si-builder-toolbar"><button className={builderMode === "gui" ? "selected" : ""} onClick={() => setBuilderMode("gui")}><Settings2 size={14} /> GUI</button><button className={builderMode === "code" ? "selected" : ""} onClick={() => setBuilderMode("code")}><Code2 size={14} /> JSON code</button><button onClick={() => importRef.current?.click()}><Upload size={14} /> Import</button><input ref={importRef} className="hidden-input" type="file" accept=".json,.spike-protocol.json" onChange={event => void importSuite(event.target.files?.[0])} /><button onClick={() => download(`${draft.id}.spike-protocol.json`, draft)}><Download size={14} /> Suite</button><button onClick={() => download(`${draft.id}.spike-extension-source.json`, protocolSuiteExtensionBundle(draft))}><FileJson size={14} /> Extension source</button></div>
      <div className="si-builder-gate"><ShieldAlert size={16} /><span>The GUI and JSON modes generate the same declarative contract. Optional extension code is exported dormant: it cannot run until digest-bound publisher trust, exact permissions, and an OS sandbox are implemented and approved.</span></div>
      {builderMode === "gui" ? <div className="si-builder-form">
        <section><h3>Identity</h3><div className="si-builder-grid"><label>ID<input value={draft.id} onChange={event => updateDraft({ ...draft, id: event.target.value.toLowerCase() })} /></label><label>Name<input value={draft.name} onChange={event => updateDraft({ ...draft, name: event.target.value })} /></label><label>Family<select value={draft.family} onChange={event => updateDraft({ ...draft, family: event.target.value as SiProtocolSuite["family"] })}>{["DDR", "GDDR", "SERDES", "LVDS", "PCI", "PCIE", "PXI", "DISPLAYPORT", "HDMI", "USB", "ETHERNET", "MIPI", "SATA", "CXL", "JESD204", "HBM", "CUSTOM"].map(item => <option key={item}>{item}</option>)}</select></label><label>Revision<input value={draft.revision} onChange={event => updateDraft({ ...draft, revision: event.target.value })} /></label><label>Signaling<select value={draft.signaling} onChange={event => updateDraft({ ...draft, signaling: event.target.value as SiProtocolSuite["signaling"] })}><option value="single_ended">Single ended</option><option value="differential">Differential</option><option value="parallel_bus">Parallel bus</option><option value="mixed">Mixed</option></select></label><label>Encoding<select value={draft.encoding} onChange={event => updateDraft({ ...draft, encoding: event.target.value as SiProtocolSuite["encoding"] })}><option>NRZ</option><option>PAM4</option><option>mixed</option><option value="user_defined">User defined</option></select></label></div><label>Description<textarea value={draft.description} onChange={event => updateDraft({ ...draft, description: event.target.value })} /></label></section>
        <section><h3>Topology and inputs</h3><div className="si-builder-grid"><label>Topology stages<textarea value={draft.topology.join("\n")} onChange={event => updateDraft({ ...draft, topology: event.target.value.split("\n").map(item => item.trim()).filter(Boolean) })} /></label><label>Required inputs<textarea value={draft.requiredInputs.join("\n")} onChange={event => updateDraft({ ...draft, requiredInputs: event.target.value.split("\n").map(item => item.trim()).filter(Boolean) })} /></label></div></section>
        <section><h3>Analysis modules</h3><div className="si-builder-checks">{ANALYSES.map(item => <label key={item.id}><input type="checkbox" checked={draft.analyses.some(analysis => analysis.id === item.id)} onChange={event => updateDraft({ ...draft, analyses: event.target.checked ? [...draft.analyses, { id: item.id, name: item.label, requiredCapabilities: item.id === "topology" ? ["design_ir", "ports"] : [`validated_${item.id}`], status: item.id === "topology" ? "available_input_review" : "solver_gated" }] : draft.analyses.filter(analysis => analysis.id !== item.id) })} /> {item.label}</label>)}</div></section>
        <section><h3>Limit provenance</h3><div className="si-builder-grid"><label>Source title<input value={draft.provenance.title} onChange={event => updateDraft({ ...draft, provenance: { ...draft.provenance, title: event.target.value } })} /></label><label>Source locator<input value={draft.provenance.locator} onChange={event => updateDraft({ ...draft, provenance: { ...draft.provenance, locator: event.target.value } })} /></label></div><small>Normative masks and thresholds must be entered by an authorized user and retain clause/source provenance. The builder does not copy restricted standards text.</small></section>
      </div> : <div className="si-builder-code"><textarea spellCheck={false} value={code} onChange={event => setCode(event.target.value)} /><button className="secondary-btn" onClick={applyCode}><Code2 size={14} /> Validate and apply JSON</button></div>}
      <div className={`si-builder-validation ${draftErrors.length || codeErrors.length ? "invalid" : "valid"}`}>{(builderMode === "code" ? codeErrors : draftErrors).length ? (builderMode === "code" ? codeErrors : draftErrors).map(error => <span key={error}><AlertTriangle size={13} /> {error}</span>) : <span><CheckCircle2 size={13} /> Valid declarative suite contract</span>}</div>
      <footer><span>Custom definitions default to setup-only and cannot self-assert validation.</span><button className="primary-btn" disabled={Boolean(draftErrors.length)} onClick={saveDraft}><Save size={14} /> Save custom suite</button></footer>
    </div>}
  </section></div>;
}
