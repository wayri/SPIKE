/// <reference types="vite/client" />
import { ArrowLeft, ArrowRight, BookOpen, Bookmark, Copy, Search, X } from "lucide-react";
import { Children, isValidElement, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { APP_VERSION } from "./appVersion";
import { helpTopics } from "./HelpTopics";
import HelpMarkdown, { CopyCode } from "./HelpMarkdown";
import { helpSlug, searchHelp, type HelpTopic } from "./helpModel";
import reference from "./helpReference.generated.json";
import controls from "./helpControls.generated.json";
import "./helpCenter.css";

const documents = import.meta.glob("../../docs/*.md", { eager: true, query: "?raw", import: "default" }) as Record<string, string>;
const rootDocuments = import.meta.glob(["../../TROUBLESHOOTING.md", "../../QUICK_REFERENCE.md", "../../DEVELOPMENT.md", "../../TESTING.md"], { eager: true, query: "?raw", import: "default" }) as Record<string, string>;
function plain(node: ReactNode): string {
  return Children.toArray(node).map(child => isValidElement<{ children?: ReactNode }>(child) ? plain(child.props.children) : typeof child === "string" || typeof child === "number" ? String(child) : "").join(" ");
}
const categoryFor = (path: string) => /WORKBENCH_HANDBOOK|USER_TASK|HELP_FAQ/.test(path) ? "Workflows & FAQ" : /CLI/.test(path) ? "CLI" : /ERROR|TROUBLESHOOT/.test(path) ? "Diagnostics" : "Reference library";
const controlGroups = Array.from(new Set(controls.map(control => control.file)));
const humanName = (file: string) => file.replace(/\.tsx$/, "").replace(/([a-z])([A-Z])/g, "$1 $2");
const errorTopic = (code: string) => `diagnostic:${code}`;
const categories = ["All", "Start here", "Workflows & FAQ", "Controls", "CLI", "Diagnostics", "Reference library", "Evidence", "Bookmarks"];
const screenshots = [
  { file: "marble-workspace-3d.png", title: "Marble workspace in 3D", caption: "SPIKE 0.2.12 local browser capture after source-importing the pinned Marble v1.4.4 board. The visible component bodies are procedural models; this capture did not use the native desktop worker.", source: "Local development browser, 2026-09-20; Marble source revision and hashes in THIRD_PARTY_NOTICES.md" },
  { file: "marble-layout-layers.png", title: "Marble layer inspection", caption: "SPIKE 0.2.12 local browser capture with All copper selected and the layer manager open. It documents the imported 2D board and controls, not an analysis result.", source: "Local development browser, 2026-09-20; Marble source revision and hashes in THIRD_PARTY_NOTICES.md" },
  { file: "marble-net-names.png", title: "Marble F.Cu net names", caption: "SPIKE 0.2.12 local browser capture of the F.Cu view at 4441% zoom. Fine-trace labels become visible with zoom; this is imported design metadata, not solved data.", source: "Local development browser, 2026-09-20; Marble source revision and hashes in THIRD_PARTY_NOTICES.md" },
  { file: "marble-report-preview.png", title: "Marble unsolved report preview", caption: "SPIKE 0.2.12 local browser capture of the Marble report preview. ANALYSIS NOT RUN is explicit, so this is a setup record and not numerical-result evidence.", source: "Local development browser, 2026-09-20; Marble source revision and hashes in THIRD_PARTY_NOTICES.md" },
  { file: "marble-v1.4.4-top.png", title: "Marble v1.4.4 reference board", caption: "Unchanged Berkeley Lab board-documentation render from the pinned v1.4.4 source. It identifies the documentation input; it is not a SPIKE screenshot or solver result.", source: "BerkeleyLab/Marble v1.4.4 docs/marble_top.png; provenance in THIRD_PARTY_NOTICES.md" },
  { file: "marble-v1.4.4-f-cu.svg", title: "Marble front-copper export", caption: "Actual F.Cu vector artwork exported by KiCad CLI 10 from the pinned Marble v1.4.4 source during visual-import verification. It is source geometry, not a SPIKE UI screenshot or solver field.", source: "artifacts/validation/marble-visual-2026-09-20/layout-response.json" },
  { file: "external-solver-center.png", title: "External engine readiness", caption: "Existing repository capture: openEMS is unavailable and gated. Detection, adapter availability, validation and workflow readiness are separate.", source: "docs/external-solver-center.png" },
  { file: "studio-batch-probes.png", title: "Recorded circuit signals", caption: "Existing SPIKES Studio workflow-regression-v3 capture: completed captured revision 5, differential voltage and an expression plotted in volts and watts. This is the separate native circuit studio, not the PCB workbench.", source: "artifacts/studio-evidence/workflow-regression-v3/01-batch-probes.png" },
  { file: "studio-vcd-timing.png", title: "HDL simulation and timing result", caption: "Existing SPIKES Studio reliability-smoke capture: simulation exit 0 and recorded clock/counter VCD transitions over 0–100 ns. This verifies the pictured testbench only.", source: "artifacts/studio-evidence/reliability-smoke/06-real-vcd-timing.png" },
];

function ControlReference({ file }: { file: string }) {
  const items = controls.filter(control => control.file === file);
  const [query, setQuery] = useState("");
  const visible = items.filter(item => `${item.label} ${item.section} ${item.description} ${item.options.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  return <><p>Controls in {humanName(file)}. Labels and tooltips come from the current interface. Repeated controls can have different contexts; values and availability depend on the active project. Read the workbench handbook for the sequence, prerequisites and outputs.</p><label className="help-local-search">Filter this reference<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Button, field, menu or option" /></label><p>{visible.length} of {items.length} control locations</p>{visible.map(item => <section className="help-control" key={item.id}><h3>{item.label}</h3><span className="help-tag">{item.kind === "Tool" ? "Ribbon button" : item.kind === "MenuItem" ? "Menu command" : item.kind}{item.section ? ` · ${item.section}` : ""}</span>{item.description && <p>{item.description}</p>}{item.dynamic && <p>The label is supplied by the active item or configuration. Use the surrounding workflow, selected object and visible tooltip to identify this instance.</p>}{item.inputType && <p>Input type: <code>{item.inputType}</code></p>}{item.options.length > 0 && <p>Choices: {item.options.join(" · ")}</p>}{(item.min || item.max || item.step) && <p>Declared range: {item.min || "no fixed minimum"} to {item.max || "no fixed maximum"}; step {item.step || "default"}.</p>}{item.disabled && <p>Conditionally available. Check the selected object, input validation, active operation and runtime readiness.</p>}<details><summary>Source reference</summary><p><code>app/src/{item.file}:{item.line}</code></p>{item.disabled && <p>Availability expression: <code>{item.disabled}</code></p>}</details></section>)}</>;
}
function readSaved(key: string): string[] { try { const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]"); return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []; } catch { return []; } }
function saveLocal(key: string, value: string[]) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Nonessential preferences. */ } }
function Checklist() {
  const labels = ["Import and inspect source quality", "Review endpoints, returns and units", "Select a supported solver and model", "Pass preflight and inspect mesh", "Run and inspect status/convergence", "Inspect fields, probes and limits", "Save project and export evidence"];
  const [checked, setChecked] = useState<string[]>(() => readSaved("spike.help.checklist"));
  return <section className="help-checklist"><h2>Analysis checklist</h2><p>Your local progress marker; checking a box does not run or validate an analysis.</p>{labels.map(label => <label key={label}><input type="checkbox" checked={checked.includes(label)} onChange={() => { const next = checked.includes(label) ? checked.filter(value => value !== label) : [...checked, label]; setChecked(next); saveLocal("spike.help.checklist", next); }} />{label}</label>)}<small>{checked.length} / {labels.length} marked complete</small></section>;
}
function makeTopics(): HelpTopic[] {
  return [
    { id: "home", title: "Welcome to SPIKE Help", category: "Start here", keywords: "guide getting started workflow handbook FAQ checklist", body: <><p className="help-lead">Find a workflow. Understand a control. Resolve a failure.</p><p>This offline guide combines illustrated walkthroughs, a workbench handbook, the source control inventory, both CLI parsers, and the canonical diagnostic catalog. Search article text, button labels, flags or complete codes.</p><div className="help-stats"><span><b>{controlGroups.length}</b> interface components</span><span><b>{controls.length}</b> control locations</span><span><b>{reference.commands.length}</b> command pages</span><span><b>{reference.errors.length}</b> diagnostics</span></div><p>Start with the <a href="#help/picture-guide" data-help-topic="picture-guide">picture walkthrough</a>, <a href="#help/feature-coverage" data-help-topic="feature-coverage">feature coverage map</a>, Workbench handbook or Quick start. Workflows & FAQ explains the sequence; Controls lists the interface reference; Reference library includes engineering and capability boundaries.</p><Checklist /><h2>Evidence and coverage</h2><p>Historical screenshots retain their original scope. The gallery distinguishes unsolved setup views from recorded circuit/HDL results. Current screenshots and solved examples for every PCB workbench are not yet available. Dynamic control labels are identified in the inventory; the catalog does not claim every runtime state has been exercised.</p></> },
    ...helpTopics().filter(topic => topic.id !== "error-codes").map(topic => ({ ...topic, category: topic.id === "feature-coverage" || topic.id === "recorded-pic-dc" ? "Evidence" : "Start here" })),
    ...Object.entries({ ...documents, ...rootDocuments }).map(([path, markdown]) => ({ id: `doc:${path.replace(/^\.\.\/\.\.\//, "")}`, source: path.replace(/^\.\.\/\.\.\//, ""), title: markdown.match(/^#\s+(.+)$/m)?.[1] ?? path.split("/").pop()!, keywords: path, markdown, category: categoryFor(path) })),
    ...controlGroups.map(file => ({ id: `controls:${file}`, title: `${humanName(file)} controls`, keywords: controls.filter(item => item.file === file).map(item => `${item.label} ${item.description} ${item.section} ${item.options.join(" ")}`).join(" "), category: "Controls", body: <ControlReference key={file} file={file} /> })),
    ...reference.commands.map(command => ({ id: `cli:${command.command}`, title: command.command, keywords: `${command.summary} ${command.usage}`, category: "CLI", body: <><p>{command.summary}</p><p>Generated from the actual command parser. Use <code>.\{command.command.split(" ")[0]}.cmd</code> in a Windows checkout in place of the executable name. This page does not execute commands.</p><CopyCode text={command.usage} /><h2>Interpreting completion</h2><p>{command.command.startsWith("spikes") ? "SPIKES: 0 = success; 2 = input error; 3 = solve failure." : "SPIKE: 0 = success; 1 = usage/input error; 2 = analysis failure; 3 = validation failure; 4 = warning gate. Check output status and command-specific gate policy as well."}</p></> })),
    ...reference.errors.map(entry => ({ id: errorTopic(entry.code), title: `${entry.code} · ${entry.title}`, keywords: `${entry.domain} ${entry.message} ${entry.action}`, category: "Diagnostics", body: <><span className="help-tag">{entry.domain} · classification {entry.classification}</span><h2>Meaning</h2><p>{entry.message}</p><h2>Resolution</h2><p>{entry.action}</p><div className="help-stats"><span>Recoverable <b>{entry.recoverable ? "Yes" : "No"}</b></span><span>Retryable <b>{entry.retryable ? "Yes, after the prescribed action" : "No"}</b></span></div><h2>Before escalation</h2><p>Preserve the complete code, operation ID, app/worker versions, safe detail, selected solver and request settings. The event message provides instance-specific context. Numerical validity and convergence are separate from diagnostic classification.</p><CopyCode text={entry.code} /></> })),
    { id: "evidence", title: "Screenshots and recorded results", category: "Evidence", keywords: "screenshots actual results studio HDL waveform report external engines", body: <><p>Original repository captures, shipped locally for offline viewing. Select a screenshot to enlarge. The Marble captures have the older HF/SI, EMI and Thermal ribbon. The current workspace puts Mesh and Solve directly after Home. Captions state what each image actually demonstrates.</p>{screenshots.map(item => <section key={item.file}><h2>{item.title}</h2><figure><button className="help-image-button" aria-label={`Enlarge ${item.title}`} onClick={event => { if (event.target === event.currentTarget) event.currentTarget.querySelector("img")?.click(); }}><img loading="lazy" src={`/help/${item.file}`} alt={item.title} /></button><figcaption>{item.caption}<br />Source: {item.source}</figcaption></figure></section>)}<h2>Still needed</h2><p>Current desktop screenshots with reproducible solved inputs/results for PI, SI, EMI, Thermal, assembly and each detailed editor. The unsolved report image is not evidence of a successful solve.</p></> },
  ];
}

export default function HelpCenter({ onClose, diagnosticCode, context }: { onClose: () => void; diagnosticCode?: string; context?: string }) {
  const topics = useMemo(makeTopics, []);
  const initial = diagnosticCode && topics.some(topic => topic.id === errorTopic(diagnosticCode)) ? errorTopic(diagnosticCode) : "home";
  const [history, setHistory] = useState([initial]), [position, setPosition] = useState(0);
  const [query, setQuery] = useState(diagnosticCode && initial === "home" ? diagnosticCode : ""), [category, setCategory] = useState("All");
  const [bookmarks, setBookmarks] = useState(() => readSaved("spike.help.bookmarks"));
  const [limit, setLimit] = useState(80), [notice, setNotice] = useState("");
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);
  const [toc, setToc] = useState<{ id: string; label: string }[]>([]);
  const modal = useRef<HTMLElement>(null), article = useRef<HTMLElement>(null), search = useRef<HTMLInputElement>(null), pendingAnchor = useRef("");
  const active = history[position], current = topics.find(topic => topic.id === active) ?? topics[0];
  const indexed = useMemo(() => topics.map(topic => ({ ...topic, text: `${topic.keywords} ${topic.markdown ?? plain(topic.body)}` })), [topics]);
  const filtered = useMemo(() => searchHelp(indexed.filter(topic => category === "All" || (category === "Bookmarks" ? bookmarks.includes(topic.id) : topic.category === category)), query), [indexed, category, bookmarks, query]);
  function scrollToAnchor(anchor: string) { const heading = Array.from(article.current?.querySelectorAll<HTMLElement>("[id]") ?? []).find(element => element.id === anchor); if (heading) heading.scrollIntoView({ block: "start" }); else article.current?.scrollTo({ top: 0 }); }
  function navigate(id: string, anchor = "") {
    if (!topics.some(topic => topic.id === id)) { setNotice("That help article is not included in this build."); return; }
    pendingAnchor.current = anchor; if (id === active) { scrollToAnchor(anchor); return; }
    setHistory(previous => [...previous.slice(0, position + 1), id]); setPosition(position + 1); setNotice("");
  }
  useEffect(() => {
    if (!diagnosticCode) return;
    const id = errorTopic(diagnosticCode);
    if (topics.some(topic => topic.id === id)) { setHistory([id]); setPosition(0); setQuery(""); }
    else { setQuery(diagnosticCode); setNotice(`No registered entry for ${diagnosticCode}. Preserve the exact event and verify app/worker versions.`); }
  }, [diagnosticCode, topics]);
  useEffect(() => { setLimit(80); }, [query, category]);
  useEffect(() => {
    const headings = Array.from(article.current?.querySelectorAll<HTMLElement>("h2, h3") ?? []);
    headings.forEach((heading, index) => { if (!heading.id) heading.id = `${helpSlug(heading.textContent ?? "section")}-${index}`; });
    setToc(headings.map(heading => ({ id: heading.id, label: heading.textContent ?? "" })));
    scrollToAnchor(pendingAnchor.current); pendingAnchor.current = "";
    article.current?.focus({ preventScroll: true });
  }, [active]);
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; search.current?.focus(); return () => previous?.focus(); }, []);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      event.stopImmediatePropagation(); // Modal shortcuts cannot edit the project behind help.
      if (event.key === "Escape") { event.preventDefault(); if (lightbox) setLightbox(null); else onClose(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") { event.preventDefault(); search.current?.focus(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") event.preventDefault();
      if (event.key === "Tab") {
        const scope = lightbox ? modal.current?.querySelector(".help-lightbox") : modal.current;
        const focusable = Array.from(scope?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href], summary, [tabindex="0"]') ?? []).filter(element => element.getClientRects().length > 0);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || !focusable.includes(document.activeElement as HTMLElement))) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !focusable.includes(document.activeElement as HTMLElement))) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener("keydown", key, true); return () => window.removeEventListener("keydown", key, true);
  }, [onClose, lightbox]);
  const hasTopic = (id: string) => topics.some(topic => topic.id === id);
  const setSearch = (value: string) => { if (value.startsWith("help:")) { const [id, anchor = ""] = value.slice(5).split("#"); if (hasTopic(id)) { navigate(id, anchor); setQuery(""); return; } } setQuery(value); };
  return <div className="modal-shade help-shade" role="dialog" aria-modal="true" aria-label="SPIKE help and user guide"><section ref={modal} className="help-center help-browser">
    <header><div><BookOpen size={22} /><span><b>SPIKE Help</b><small>Offline guide · v{APP_VERSION}{context ? ` · ${context} workspace` : ""}</small></span></div><div className="help-header-actions"><button onClick={() => navigate("doc:docs/WORKBENCH_HANDBOOK.md")}>Workbench handbook</button><button className="canvas-icon" aria-label="Close help" onClick={onClose}><X size={18} /></button></div></header>
    <div className="help-layout"><aside className="help-sidebar"><label className="help-search"><Search size={17} /><input ref={search} aria-label="Search all help" value={query} onChange={event => setSearch(event.target.value)} placeholder="Search topics, buttons, errors…" /></label><select aria-label="Help category" value={category} onChange={event => setCategory(event.target.value)}>{categories.map(name => <option key={name}>{name}</option>)}</select><div className="help-result-count" role="status">{filtered.length} articles{query ? ` matching “${query}”` : ""}</div><nav aria-label="Help articles">{filtered.slice(0, limit).map(topic => <button key={topic.id} aria-current={active === topic.id ? "page" : undefined} className={active === topic.id ? "active" : ""} onClick={() => navigate(topic.id)}><small>{topic.category}</small><span>{topic.title}</span>{query && <em>{topic.text.slice(Math.max(0, topic.text.toLowerCase().indexOf(query.toLowerCase()) - 35), Math.max(0, topic.text.toLowerCase().indexOf(query.toLowerCase()) - 35) + 145)}</em>}</button>)}{!filtered.length && <p className="help-empty">No matching articles. Try fewer words or select All. Unknown codes require their original diagnostic record.</p>}{filtered.length > limit && <button onClick={() => setLimit(limit + 80)}>Show more articles ({filtered.length - limit} remaining)</button>}</nav></aside>
    <div className="help-reading"><div className="help-toolbar"><button aria-label="Back in help" disabled={position === 0} onClick={() => setPosition(position - 1)}><ArrowLeft size={16} /></button><button aria-label="Forward in help" disabled={position === history.length - 1} onClick={() => setPosition(position + 1)}><ArrowRight size={16} /></button><button onClick={() => navigate("home")}>Home</button><span>{current.category}</span><button aria-label={bookmarks.includes(active) ? "Remove bookmark" : "Bookmark article"} aria-pressed={bookmarks.includes(active)} onClick={() => { const next = bookmarks.includes(active) ? bookmarks.filter(id => id !== active) : [...bookmarks, active]; setBookmarks(next); saveLocal("spike.help.bookmarks", next); }}><Bookmark size={16} fill={bookmarks.includes(active) ? "currentColor" : "none"} /></button><button onClick={() => void navigator.clipboard.writeText(`help:${active}`).then(() => setNotice("Help link copied. Paste it into help search to open this article."), () => setNotice(`Copy this help address: help:${active}`))}><Copy size={14} /> Link</button><button onClick={() => window.print()}>Print</button></div>
    {notice && <div className="help-notice" role="status">{notice}</div>}
    <article key={active} ref={article} tabIndex={-1} onClick={event => { const target = event.target; const link = target instanceof Element ? target.closest<HTMLAnchorElement>("a[data-help-topic]") : null; if (link?.dataset.helpTopic) { event.preventDefault(); navigate(link.dataset.helpTopic); return; } const image = target instanceof HTMLImageElement ? target : target instanceof Element ? target.closest("[data-help-image]")?.querySelector("img") : null; if (image instanceof HTMLImageElement) { event.preventDefault(); setLightbox({ src: image.src, alt: image.alt }); } }}><div className="help-eyebrow">SPIKE / {current.category}</div><h1>{current.title}</h1>{toc.length > 2 && <details className="help-toc"><summary>On this page · {toc.length} sections</summary>{toc.map(item => <button key={item.id} onClick={() => scrollToAnchor(item.id)}>{item.label}</button>)}</details>}{current.markdown ? <HelpMarkdown text={current.markdown} source={current.source ?? ""} navigate={navigate} hasTopic={hasTopic} /> : current.body}<div className="help-related"><h2>Continue learning</h2><button onClick={() => navigate("doc:docs/WORKBENCH_HANDBOOK.md")}>Workbench handbook</button><button onClick={() => navigate("doc:docs/HELP_FAQ.md")}>FAQ & recovery</button><button onClick={() => { setCategory("Controls"); setQuery(""); }}>Browse controls</button><button onClick={() => navigate("picture-guide")}>Picture walkthrough</button><button onClick={() => navigate("feature-coverage")}>Feature coverage & gaps</button><button onClick={() => navigate("evidence")}>Screenshots & results</button></div></article></div></div>
    <footer><span>Offline reference · Result validity and runtime diagnostics take precedence.</span><small>Ctrl+F search · Esc close</small></footer>
    {lightbox && <div className="help-lightbox" role="dialog" aria-label="Enlarged screenshot" aria-modal="true"><button autoFocus onClick={() => setLightbox(null)}><X size={18} /> Close image</button><img src={lightbox.src} alt={lightbox.alt} /><p>{lightbox.alt}</p></div>}
  </section></div>;
}
