// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { FilePlus2, Search } from "./icons";
import { PYTHON_TEMPLATES, type PythonTemplate } from "./pythonWorkspaceTemplates";

export default function PythonTemplateLibrary({ onCreate }: { onCreate: (template: PythonTemplate) => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const categoryCounts = new Map<string, number>();
  for (const template of PYTHON_TEMPLATES) categoryCounts.set(template.category, (categoryCounts.get(template.category) ?? 0) + 1);
  const categories = ["All", ...Array.from(categoryCounts.keys())];
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const visible = PYTHON_TEMPLATES.filter(template => {
    if (category !== "All" && template.category !== category) return false;
    const searchable = [template.id, template.title, template.description, template.category, ...template.requirements].join(" ").toLowerCase();
    return terms.every(term => searchable.includes(term));
  });
  return <div className="python-template-library">
    <div className="python-pane-heading"><b>TEMPLATES</b><small>{PYTHON_TEMPLATES.length}</small></div>
    <label className="python-template-search"><Search size={13} /><input aria-label="Search Python templates" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find an analysis…" /></label>
    <select aria-label="Python template category" value={category} onChange={event => setCategory(event.target.value)}>{categories.map(item => <option key={item} value={item}>{item} ({item === "All" ? PYTHON_TEMPLATES.length : categoryCounts.get(item)})</option>)}</select>
    <div className="python-template-summary" role="status"><span>{visible.length} matching template{visible.length === 1 ? "" : "s"}</span>{(query || category !== "All") && <button type="button" onClick={() => { setQuery(""); setCategory("All"); }}>Clear filters</button>}</div>
    <div className="python-template-cards">{visible.map(template => <article key={template.id}><small>{template.category}</small><h3>{template.title}</h3><p>{template.description}</p>{template.requirements.length > 0 && <p className="python-template-requirements">Needs: {template.requirements.join(" · ")}</p>}<button type="button" onClick={() => onCreate(template)}><FilePlus2 size={13} /> Open template</button></article>)}{!visible.length && <p className="python-pane-note">No templates match this search.</p>}</div>
    <p className="python-pane-note">Templates open in a new tab. Review their inputs before running.</p>
  </div>;
}
