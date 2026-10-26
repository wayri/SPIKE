// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useState } from "react";
import { findWorkExamples, loadWorkExampleAsset, prepareWorkExampleAction, workExamples, workExampleStatuses, type WorkExample, type WorkExampleAction } from "./workExampleCatalog";
import { isDesktopShell, saveExtensionArtifact } from "./workerBridge";
import { downloadEMergeText } from "./emergeSampleExport";
import { workExamplePictures } from "./workExampleAssets";
import "./buttonStandard.css";
import "./WorkExamples.css";

export type WorkExamplesProps = {
  initialQuery?: string;
  /** The parent owns guarded project opening, inert draft staging and run authority. */
  onOpen?: (entryId: string, action: WorkExampleAction) => void | Promise<void>;
};
const statusLabel = (status: string) => status.replace(/-/g, " ");
const actionLabel = (row: WorkExample) => row.primaryAction === "emerge-library" ? "Open EMerge library"
  : row.primaryAction === "project" ? "Open saved project" : row.primaryAction === "ibis" ? "Stage IBIS example" : "Stage spatial SI example";
const previewLimit = 32 * 1024;

function ExampleCard({ row, onOpen }: { row: WorkExample; onOpen?: WorkExamplesProps["onOpen"] }) {
  const [selected, setSelected] = useState(row.assets[0]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState("");
  const id = useId();
  const act = async (task: () => Promise<string>) => {
    if (busy) return;
    setBusy(true); setMessage("");
    try { setMessage(await task()); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Example action failed. Try again."); }
    finally { setBusy(false); }
  };
  const save = () => act(async () => {
    const file = await loadWorkExampleAsset(row.id, selected);
    if (isDesktopShell()) {
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(file.text));
      const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
      const path = await saveExtensionArtifact({ file_name: file.name, media_type: "text/plain", encoding: "utf-8", data: file.text, sha256 });
      return path ? "File saved. Review its companion files and prerequisites before use." : "Save cancelled. Your workspace has not changed.";
    }
    downloadEMergeText(file.name, file.text);
    return "File downloaded. Review its companion files and prerequisites before use.";
  });
  const open = () => act(async () => {
    if (!onOpen) throw new Error("Workspace staging is unavailable here. Save the example files and follow the steps.");
    await onOpen(row.id, await prepareWorkExampleAction(row.id));
    return row.primaryAction === "emerge-library" ? "EMerge library opened." : "Workspace action requested. Complete any unsaved-changes prompt, then review the staged inputs. No solver has been started.";
  });
  return <article className="work-example-card" data-example-id={row.id}>
    <header><span className="work-example-category">{row.category}</span><span className="work-example-status" data-status={row.status}>{statusLabel(row.status)}</span></header>
    <h3>{row.title}</h3><p>{row.summary}</p>
    {row.preview && workExamplePictures[`../../${row.preview.asset}`] && <figure className="work-example-picture"><img loading="lazy" src={workExamplePictures[`../../${row.preview.asset}`]} alt={row.preview.alt} /><figcaption>{row.preview.caption}</figcaption></figure>}
    <dl><dt>Engine</dt><dd>{row.engine}</dd><dt>Requires</dt><dd>{row.dependencies}</dd></dl>
    <ol>{row.steps.map((step, index) => <li key={index}>{step}</li>)}</ol>
    <p className="work-example-limits"><strong>Limits:</strong> {row.limits}</p>
    <details><summary>Files, source command and license</summary>
      {row.command && <><p>Source command, run from the repository root after reviewing prerequisites:</p><pre>{row.command}</pre></>}
      <small>{row.license}</small><ul className="work-example-files">{row.assets.map(path => <li key={path}>{path}</li>)}</ul>
    </details>
    <div className="work-example-actions">
      {row.primaryAction !== "download" && <button type="button" className="spike-control--primary" disabled={busy || !onOpen} onClick={() => open()} title={onOpen ? actionLabel(row) : "Workspace action unavailable; files can still be saved"}>{actionLabel(row)}</button>}
      <label htmlFor={id}>Example file<select id={id} value={selected} disabled={busy} onChange={event => { setSelected(event.target.value); setPreview(""); setMessage(""); }}>{row.assets.map(path => <option key={path} value={path}>{path}</option>)}</select></label>
      <div className="work-example-file-actions"><button type="button" disabled={busy} onClick={() => save()}>{busy ? "Working..." : "Save selected file"}</button>
        <button type="button" disabled={busy} onClick={() => act(async () => { const text = (await loadWorkExampleAsset(row.id, selected)).text; setPreview(text.slice(0, previewLimit)); return text.length > previewLimit ? "Showing the first 32 KiB of text. Saving or opening retains the full file." : "Example text opened for inspection."; })}>Inspect text</button></div>
    </div>
    {preview && <details open className="work-example-preview"><summary>Selected file text</summary><pre tabIndex={0}>{preview}</pre></details>}
    {message && <p role="status" className="work-example-message">{message}</p>}
  </article>;
}

export default function WorkExamples({ onOpen, initialQuery = "" }: WorkExamplesProps) {
  const [query, setQuery] = useState(initialQuery);
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  useEffect(() => { setQuery(initialQuery); setCategory("all"); setStatus("all"); }, [initialQuery]);
  const rows = findWorkExamples(query, category, status);
  return <section className="work-examples" aria-label="Work examples">
    <header className="work-examples-heading"><div><span className="work-example-category">SPIKE example workbench</span><h2>Start with a concrete example</h2><p>Inspect an original input, review its assumptions, then choose an explicit next action.</p></div><span className="work-examples-count">{workExamples.length} curated cases</span></header>
    <p className="work-examples-boundary">Open saved project loads retained inputs and results after the unsaved-changes guard. No solver starts automatically. Runnable means a source workflow with the listed dependencies; this catalog does not check installed engines. Files are bundled for offline inspection and saving; Python scripts require the source checkout and original relative file layout.</p>
    <div className="work-examples-filters"><label>Find examples<input type="search" maxLength={256} value={query} onChange={event => setQuery(event.target.value)} placeholder="Crosstalk, decap, thermal, antenna..." /></label>
      <label>Work area<select value={category} onChange={event => setCategory(event.target.value)}><option value="all">All work areas</option>{[...new Set(workExamples.map(row => row.category))].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Readiness<select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All readiness states</option>{workExampleStatuses.map(value => <option key={value} value={value}>{statusLabel(value)}</option>)}</select></label>
      <button type="button" onClick={() => { setQuery(""); setCategory("all"); setStatus("all"); }} disabled={!query && category === "all" && status === "all"}>Clear filters</button>
    </div>
    <p role="status">{rows.length} matching examples. Setup only needs preparation; saved evidence preserves a past input/result; guides open an existing library. Model and protocol qualification remain separate.</p>
    <div className="work-example-grid">{rows.map(row => <ExampleCard key={row.id} row={row} onOpen={onOpen} />)}</div>
    {!rows.length && <div className="work-examples-empty"><h3>No matching examples</h3><p>Try a shorter search or clear the work-area and readiness filters.</p></div>}
  </section>;
}
