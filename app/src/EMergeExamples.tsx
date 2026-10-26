// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import SectionHelpButton from "./SectionHelpButton";
import { advancedEMergeStudies, findAdvancedEMergeStudies, loadAdvancedEMergeStudy, emergeExamples, findEMergeExamples } from "./emergeExampleCatalog";
import { isDesktopShell, saveNativeTextFile } from "./workerBridge";
import { downloadEMergeText } from "./emergeSampleExport";
import "./EMergeExamples.css";
const pictures: Record<string, string> = { patch: "patch_sphere.png", radome: "radome_analysis.png", "patch-fields": "patch_fields_nearfield.png", "esp32-surrogate": "esp32_surrogate_sphere.png" };
const capabilityLabel = (value: string) => value.replace(/_/g, " ").replace(/\be\b/g, "E").replace(/\bh\b/g, "H");
export default function EMergeExamples({ onOpen }: { onOpen: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const rows = findEMergeExamples(query, category);
  const studies = findAdvancedEMergeStudies(query, category);
  const saveStudy = async (id: string) => {
    if (busy) return;
    setBusy(id); setMessage("");
    try {
      const file = await loadAdvancedEMergeStudy(id);
      if (isDesktopShell()) { const path = await saveNativeTextFile(file.name, file.text, "result"); setMessage(path ? "Study wrapper saved. Open it in the separate SPIKE-Em gateway with its pinned resources and compatible runtime; review before execution." : "Study save cancelled."); }
      else { downloadEMergeText(file.name, file.text); setMessage("Study wrapper downloaded; its separate runtime and pinned source resources are required."); }
    } catch (error) { setMessage(error instanceof Error ? error.message : "Study export failed. Try again."); }
    finally { setBusy(""); }
  };
  return <section className="emerge-examples" aria-label="EMerge example projects">
    <header><div><h2>EMerge example projects</h2><p>1. Open a project. 2. Inspect fields and probe saved samples. 3. Review setup and runtime before an explicit new run.</p></div><SectionHelpButton topic="doc:docs/EMERGE_EXAMPLES.md" label="EMerge examples, fields and probing" /></header>
    <label>Find an EM example<input type="search" maxLength={256} value={query} onChange={event => setQuery(event.target.value)} placeholder="Antenna, near field, S21… * and ? supported" /></label>
    <nav aria-label="EM example library"><button type="button" aria-pressed={!advanced} onClick={() => { setAdvanced(false); setCategory("all"); }}>Board projects</button><button type="button" aria-pressed={advanced} onClick={() => { setAdvanced(true); setCategory("all"); }}>Advanced studies</button></nav>
    <nav aria-label="EM example categories">{["all", ...new Set((advanced ? advancedEMergeStudies : emergeExamples).map(row => row.category))].map(value => <button type="button" key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>{value === "all" ? "All examples" : value}</button>)}</nav>
    <p role="status">{advanced ? studies.length : rows.length} entries · Saved execution is separate from physical validation. Historical source-binding limits are retained in each project.</p>
    {!advanced && <div className="emerge-example-grid">{rows.map(row => <article key={row.id}><header><h3>{row.title}</h3><span>{row.status === "setup_only" ? "Setup only" : "Saved solver samples"}</span></header><p>{row.summary}</p>{pictures[row.id] && <figure><img src={`/help/emerge/${pictures[row.id]}`} loading="lazy" alt={`${row.title}: plot of retained solver samples`} /><figcaption>Retained solver plot; unvalidated physical model.</figcaption></figure>}<ul>{row.capabilities.map(capability => <li key={capability}>{capabilityLabel(capability)}</li>)}</ul><small>Model: {row.model_status}. Runtime is required only for a new solve.</small><button type="button" className="spike-control--primary" onClick={() => onOpen(row.id)}>Open {row.title}</button></article>)}</div>}
    {advanced && <><p>23 RF study wrappers use the separate SPIKE-Em gateway, compatible EMerge and pinned external resources. Saving never executes code or promotes a desktop adapter. Five thermal entries remain suspended.</p><div className="emerge-example-grid">{studies.map(row => <article key={row.id}><h3>{row.title}</h3><small>{row.category} · {row.status === "suspended" ? "Suspended" : "Separate gateway; runtime and resources required"}</small><p>{row.license}</p><button type="button" disabled={Boolean(busy) || row.status === "suspended"} onClick={() => void saveStudy(row.id)}>{busy === row.id ? "Saving…" : "Save study wrapper"}</button></article>)}</div><p role="status">{message}</p></>}
    {!(advanced ? studies.length : rows.length) && <p>Try a shorter search or choose All examples.</p>}
    <footer><strong>Advanced EM workflows</strong><p>Filters, waveguides, resonators, periodic cells, CAD, differential ports, optimization and scattering have separate study wrappers and runtime/adapter requirements. The guide maps their entry points and gaps. These projects do not establish calibrated gain, chamber physics or EMI compliance.</p><SectionHelpButton topic="doc:docs/EMERGE_EXAMPLES.md" anchor="advanced-study-map" label="Advanced EMerge study map" /></footer>
  </section>;
}
