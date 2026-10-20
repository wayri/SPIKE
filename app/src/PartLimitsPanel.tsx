// SPDX-License-Identifier: Apache-2.0
import { useMemo, useRef, useState } from "react";
import { Plus, Save, Trash2, Upload, Download, Pencil } from "./icons";
import { usePanelPresentation } from "./panelPresentation";
import { admitPartLimits, PART_LIMIT_UNITS, partLimitReportCsv, type PartLimitReport, type PartLimitRule } from "./partLimitsModel";
import "./buttonStandard.css";
import "./PartLimitsPanel.css";

export type PartLimitComponent = { occurrence_id: string; component_id: string; reference: string };
const emptyRule = (): PartLimitRule => ({ id: crypto.randomUUID(), occurrence_id: "", component_id: "", label: "Supply voltage", quantity: "voltage", unit: "V", lower: null, upper: null, reference: "0", value: null, rating_source: "", measurement_source: "", evidence_status: "unreviewed" });
export default function PartLimitsPanel({ components, rules, report, disabled, onChange }: {
  components: PartLimitComponent[]; rules: PartLimitRule[]; report?: PartLimitReport; disabled: boolean; onChange: (rules: PartLimitRule[]) => void;
}) {
  const { ownerDocument } = usePanelPresentation();
  const [draft, setDraft] = useState<PartLimitRule>(emptyRule), [error, setError] = useState(""), [filter, setFilter] = useState(""), [page, setPage] = useState(0);
  const input = useRef<HTMLInputElement>(null), editor = useRef<HTMLDetailsElement>(null);
  const names = useMemo(() => new Map(components.map(part => [JSON.stringify([part.occurrence_id, part.component_id]), part.reference || part.component_id])), [components]);
  const choices = components.filter(part => `${part.occurrence_id} ${part.reference}`.toLowerCase().includes(filter.toLowerCase()));
  const target = JSON.stringify([draft.occurrence_id, draft.component_id]);
  const exportFile = (name: string, data: unknown, csv = false) => {
    if (!ownerDocument) return;
    const url = URL.createObjectURL(new Blob([csv ? String(data) : JSON.stringify(data, null, 2)], { type: csv ? "text/csv;charset=utf-8" : "application/json" }));
    const link = ownerDocument.createElement("a"); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const numberField = (key: "lower" | "upper" | "reference" | "value", title: string) => <label>{title}<input aria-label={title} inputMode="decimal" value={draft[key] ?? ""} placeholder="Unknown / unset" onChange={e => setDraft({ ...draft, [key]: e.target.value.trim() || null, ...(key === "value" ? {evidence_status:"unreviewed" as const} : {}) })}/></label>;
  const reportRows = report?.rows.slice(page * 100, (page + 1) * 100) ?? [];
  return <section className="part-limits" aria-label="Part operating limits">
    <p>Declare limits for a specific board occurrence and part. Values are captured observations, not automatically inferred solver extrema. Record the rating’s operating conditions and the observation’s result ID, case and revision.</p>
    <div className="part-limit-actions">
      <button type="button" disabled={disabled} onClick={() => { setDraft(emptyRule()); setError(""); if(editor.current)editor.current.open=true; }}><Plus size={14}/> New rule</button>
      <button type="button" disabled={disabled} onClick={() => input.current?.click()}><Upload size={14}/> Import rules & observations</button>
      <button type="button" disabled={!rules.length} onClick={() => exportFile("part-limits.json", { contract: "spike/part-limits/v1", rules })}><Download size={14}/> Export rules</button>
      <button type="button" disabled={!report || disabled} onClick={() => report && exportFile("part-limit-report.csv", partLimitReportCsv(report), true)}><Download size={14}/> Report CSV</button>
      <button type="button" disabled={!report || disabled} onClick={() => report && exportFile("part-limit-report.json", report)}><Download size={14}/> Report JSON</button>
    </div>
    <input ref={input} hidden type="file" accept=".json" aria-label="Part limits JSON file" onChange={async event => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return; try {
      if (file.size > 8 * 1024 * 1024) throw new Error("Part limit import exceeds 8 MiB.");
      const envelope = JSON.parse(await file.text()); if (envelope.contract !== "spike/part-limits/v1") throw new Error("Expected spike/part-limits/v1.");
      const incoming = admitPartLimits(envelope.rules);
      if (incoming.some(rule => !names.has(JSON.stringify([rule.occurrence_id, rule.component_id])))) throw new Error("Imported targets do not match the current board occurrences and part IDs.");
      onChange(incoming); setError(""); setDraft(emptyRule());
    } catch (cause) { setError(`Import rejected; existing rules retained. ${cause instanceof Error ? cause.message : String(cause)}`); } }}/>
    {error && <p role="alert">{error}</p>}
    <details ref={editor} open={!report}><summary>Configure a part limit</summary><fieldset disabled={disabled}><legend>{rules.some(rule => rule.id === draft.id) ? "Edit operating-limit rule" : "Add operating-limit rule"}</legend>
      <div className="part-limit-grid">
        <label>Find part<input value={filter} placeholder="Board occurrence or reference" onChange={e => setFilter(e.target.value)}/></label>
        <label>Part<select aria-label="Limit target part" value={target} onChange={e => { const [occurrence_id, component_id] = JSON.parse(e.target.value); setDraft({ ...draft, occurrence_id, component_id }); }}>
          <option value={JSON.stringify(["", ""])}>Choose a part…</option>
          {draft.component_id && !choices.slice(0, 200).some(part => part.occurrence_id === draft.occurrence_id && part.component_id === draft.component_id) && <option value={target}>{draft.occurrence_id} / {names.get(target) ?? draft.component_id}</option>}
          {choices.slice(0, 200).map(part => <option key={JSON.stringify([part.occurrence_id, part.component_id])} value={JSON.stringify([part.occurrence_id, part.component_id])}>{part.occurrence_id} / {part.reference || part.component_id}</option>)}
        </select><small>{choices.length > 200 ? "First 200 matches; narrow the search." : `${choices.length} matching parts`}</small></label>
        <label>Check / pin / case label<input value={draft.label} onChange={e => setDraft({ ...draft, label: e.target.value })}/></label>
        <label>Quantity<select value={draft.quantity} onChange={e => { const quantity = e.target.value as PartLimitRule["quantity"]; setDraft({ ...draft, quantity, unit: PART_LIMIT_UNITS[quantity][0], lower: null, upper: null, reference: quantity === "temperature" ? null : "0", value: null, evidence_status: "unreviewed" }); }}>{Object.keys(PART_LIMIT_UNITS).map(key => <option key={key} value={key}>{key === "stress" ? "Mechanical stress" : key}</option>)}</select></label>
        <label>Unit (all rule values)<select value={draft.unit} onChange={e => setDraft({ ...draft, unit: e.target.value, lower: null, upper: null, reference: null, value: null, evidence_status: "unreviewed" })}>{PART_LIMIT_UNITS[draft.quantity].map(unit => <option key={unit} value={unit}>{unit === "degC" ? "°C" : unit}</option>)}</select></label>
        {numberField("lower", "Minimum allowed")}{numberField("upper", "Maximum allowed")}{numberField("reference", "Reference for percentage")}{numberField("value", "Observed value")}
        <label className="part-limit-wide">Rating source & operating conditions<textarea rows={2} value={draft.rating_source} placeholder="Datasheet revision, table, duty cycle, ambient, derating basis…" onChange={e => setDraft({ ...draft, rating_source: e.target.value })}/></label>
        <label className="part-limit-wide">Observation source / case / revision<textarea rows={2} value={draft.measurement_source} placeholder="Solver result or measurement ID; quantity location/pins; peak/RMS/time/corner…" onChange={e => setDraft({ ...draft, measurement_source: e.target.value, evidence_status: "unreviewed" })}/></label>
        <label><input type="checkbox" checked={draft.evidence_status === "reviewed"} onChange={e => setDraft({ ...draft, evidence_status: e.target.checked ? "reviewed" : "unreviewed" })}/> I reviewed this observation and its units</label>
      </div>
      <p>Stress is the percentage of the allowance used from the reference toward the bound. Headroom = 100 − stress; negative headroom means an exceedance. Temperature needs a reference such as ambient. Limits are inclusive. An unset reference leaves percentages unknown.</p>
      <button type="button" disabled={!draft.component_id || !draft.label.trim()} onClick={() => { try { const next = admitPartLimits([...rules.filter(rule => rule.id !== draft.id), draft]); onChange(next); setDraft(emptyRule()); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } }}><Save size={14}/> Save rule & invalidate report</button>
    </fieldset></details>
    <details open={rules.length > 0}><summary>{rules.length} configured rules · first 200 matching the part search shown</summary><ul className="part-limit-rule-list">{rules.filter(rule => `${rule.occurrence_id} ${names.get(JSON.stringify([rule.occurrence_id,rule.component_id]))} ${rule.label}`.toLowerCase().includes(filter.toLowerCase())).slice(0,200).map(rule => <li key={rule.id}><span>{rule.occurrence_id} / {names.get(JSON.stringify([rule.occurrence_id,rule.component_id])) ?? rule.component_id} · {rule.label}</span><button type="button" disabled={disabled} aria-label={`Edit ${rule.label}`} onClick={() => { setDraft({ ...rule }); setError(""); if(editor.current)editor.current.open=true; }}><Pencil size={14}/></button><button type="button" disabled={disabled} aria-label={`Remove ${rule.label}`} onClick={() => onChange(rules.filter(item => item.id !== rule.id))}><Trash2 size={14}/></button></li>)}</ul></details>
    {!report && <p role="status">Run review to evaluate the saved rules. Missing or unreviewed evidence stays unknown.</p>}
    {report && <><h3 data-status={report.overall_status}>Operating-limit report: {report.overall_status}</h3><p>{report.statement}</p><p>{report.covered_components} / {report.fitted_components} fitted parts have declared checks. {report.unchecked_components.length} parts have no rules. Only the declared quantities and cases are covered.</p>
      {report.part_summary && <details><summary>Worst declared allowance per part</summary><div className="engineering-table"><table><thead><tr><th>Part</th><th>Checks</th><th>Status</th><th>Stress %</th><th>Headroom %</th></tr></thead><tbody>{report.part_summary.slice(0,100).map(part=><tr key={JSON.stringify([part.occurrence_id,part.component_id])}><td>{part.occurrence_id} / {part.reference}</td><td>{part.declared_checks}</td><td>{part.status}</td><td>{part.stress_percent??"Unknown"}</td><td>{part.headroom_percent??"Unknown"}</td></tr>)}</tbody></table></div><small>First 100 parts; exports include every part. Percentages summarize declared allowances, not combined physical stress.</small></details>}
      <div className="engineering-table"><table><thead><tr>{["Part / check", "Value", "Allowed", "Stress %", "Headroom %", "Status", "Evidence"].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{reportRows.map(row => <tr key={row.id}><td>{row.occurrence_id} / {row.reference_designator}<br/>{row.label}</td><td>{row.value ?? "Unknown"} {row.unit === "degC" ? "°C" : row.unit}</td><td>{row.lower ?? "Unbounded"} … {row.upper ?? "Unbounded"} {row.unit === "degC" ? "°C" : row.unit}</td><td>{row.stress_percent ?? "Unknown"}</td><td>{row.headroom_percent ?? "Unknown"}</td><td><strong data-status={row.status}>{row.status}</strong>{row.status !== row.comparison_status && <small>Numeric check: {row.comparison_status}</small>}</td><td>{row.notes.join("; ") || "Reviewed supplied observation"}<details><summary>Sources & percentage basis</summary><p>{row.rating_source}</p><p>{row.measurement_source}</p><p>{row.percentage_note}; reference {row.reference ?? "unknown"} {row.unit}</p></details></td></tr>)}</tbody></table></div>
      <div className="part-limit-actions"><button type="button" disabled={!page} onClick={() => setPage(page - 1)}>Previous checks</button><span>Page {page + 1} / {Math.max(1, Math.ceil(report.rows.length / 100))}</span><button type="button" disabled={(page + 1) * 100 >= report.rows.length} onClick={() => setPage(page + 1)}>Next checks</button></div>
      {report.unchecked_components.length > 0 && <details><summary>Parts without checks</summary><p>{report.unchecked_components.slice(0, 100).map(part => `${part.occurrence_id}/${part.reference || part.component_id}`).join(", ")}{report.unchecked_components.length > 100 ? "… Full list is in the report export." : ""}</p></details>}
    </>}
  </section>;
}
