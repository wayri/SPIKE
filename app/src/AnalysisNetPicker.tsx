// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import { ChevronDown, Network, Search } from "./icons";
import { optionMatchesQuery } from "./optionSearch";

/** Net identities remain exact; wildcard queries filter, never expand a selection. */
export default function AnalysisNetPicker({ value, choices, label, onNet, onPreview }: {
  value: string; choices: readonly string[]; label: string;
  onNet: (net: string) => void; onPreview: (net: string | null) => void;
}) {
  const [query, setQuery] = useState("");
  const details = useRef<HTMLDetailsElement>(null);
  const filtered = choices.filter(net => optionMatchesQuery(net, query));
  const close = () => { if (details.current) { details.current.open = false; details.current.querySelector("summary")?.focus(); } onPreview(null); };
  return <details ref={details} className="analysis-net-browser" onMouseLeave={() => onPreview(null)} onKeyDown={event => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
    if (event.key === "ArrowDown" && event.target instanceof HTMLInputElement) { event.preventDefault(); details.current?.querySelector<HTMLButtonElement>('[role="option"]')?.focus(); }
  }}>
    <summary aria-label={label}><Network size={14}/><span>{value || "Select a net"}</span><ChevronDown size={14}/></summary>
    <label className="analysis-net-search"><Search size={14}/><input type="search" aria-label={`Search ${label}`} maxLength={128} value={query} placeholder="Search nets · * or ?" onChange={event => setQuery(event.target.value)}/></label>
    <small role="status">{filtered.length} of {choices.length} nets{filtered.length > 200 ? " · Refine search to see more" : ""}</small>
    <div className="analysis-net-options" role="listbox" aria-label={label}>{filtered.slice(0, 200).map(net => <button type="button" role="option" aria-selected={net === value} className={net === value ? "selected" : ""} key={net}
      onMouseEnter={() => onPreview(net)} onKeyDown={event => {
        if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        event.preventDefault(); const rows = [...(details.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') ?? [])], index = rows.indexOf(event.currentTarget);
        rows[event.key === "Home" ? 0 : event.key === "End" ? rows.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + rows.length) % rows.length]?.focus();
      }} onClick={() => { if (choices.includes(net)) { onNet(net); close(); } }}><Network size={12}/><span>{net}</span></button>)}</div>
    {!filtered.length && <p role="status">No matching nets.</p>}
  </details>;
}
