// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { FilePlus2, Search } from "lucide-react";
import { PYTHON_TEMPLATES, type PythonTemplate } from "./pythonWorkspaceTemplates";

export default function PythonTemplateLibrary({ onCreate }: { onCreate: (template: PythonTemplate) => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const categories = ["All", ...Array.from(new Set(PYTHON_TEMPLATES.map(template => template.category)))];
  const visible = PYTHON_TEMPLATES.filter(template => (category === "All" || template.category === category) && `${template.title} ${template.description} ${template.category}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="python-template-library">
    <div className="python-pane-heading"><b>TEMPLATES</b><small>{PYTHON_TEMPLATES.length}</small></div>
    <label className="python-template-search"><Search size={13} /><input aria-label="Search Python templates" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find an analysis…" /></label>
    <select aria-label="Python template category" value={category} onChange={event => setCategory(event.target.value)}>{categories.map(item => <option key={item}>{item}</option>)}</select>
    <div className="python-template-cards">{visible.map(template => <article key={template.id}><small>{template.category}</small><h3>{template.title}</h3><p>{template.description}</p>{template.requirements.length > 0 && <p className="python-template-requirements">Needs: {template.requirements.join(" · ")}</p>}<button type="button" onClick={() => onCreate(template)}><FilePlus2 size={13} /> Open template</button></article>)}{!visible.length && <p className="python-pane-note">No templates match this search.</p>}</div>
    <p className="python-pane-note">Templates open in a new tab. Review their inputs before running.</p>
  </div>;
}
