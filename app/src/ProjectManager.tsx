// SPDX-License-Identifier: Apache-2.0
import { FileArchive, FilePlus2, FolderOpen, History, ListTree, Save, SaveAll, Upload, X } from "./icons";
import "./projectManager.css";

export type RecentProject = { name: string; path: string | null; openedAt: string };

type ProjectManagerProps = {
  projectName: string;
  projectPath: string | null;
  boardFile: string;
  counts: { layers: number; nets: number; components: number; results: number };
  recent: RecentProject[];
  onNew: () => void;
  onOpen: () => void;
  onImport: () => void;
  onSave: () => void;
  onSaveAs: () => void;
  onSaveWithoutResults: () => void;
  onSaveResultsFile: () => void;
  onStudies: () => void;
  onClose: () => void;
};

type ProjectAction = {
  label: string;
  detail: string;
  icon: typeof FileArchive;
  run: () => void;
  primary?: boolean;
};

function ActionGroup({ label, actions }: { label: string; actions: ProjectAction[] }) {
  return <section className="project-action-group" aria-label={label}>
    <h3>{label}</h3>
    <div className="project-action-list">
      {actions.map(action => <button key={action.label} type="button" className={action.primary ? "spike-control--primary" : undefined} onClick={action.run} title={action.detail}>
        <action.icon size={16} aria-hidden="true" />
        <span><b>{action.label}</b><small>{action.detail}</small></span>
      </button>)}
    </div>
  </section>;
}

export default function ProjectManager(props: ProjectManagerProps) {
  const openActions: ProjectAction[] = [
    { label: "New project", detail: "Start an empty workspace", icon: FilePlus2, run: props.onNew },
    { label: "Open", detail: "Open a board or SPIKE project", icon: FolderOpen, run: props.onOpen },
    { label: "Import CAD", detail: "Import a supported design source", icon: Upload, run: props.onImport },
    { label: "Studies", detail: "Browse simulation studies", icon: ListTree, run: props.onStudies },
  ];
  const saveActions: ProjectAction[] = [
    { label: "Save", detail: "Save project with retained results", icon: Save, run: props.onSave, primary: true },
    { label: "Save as", detail: "Save a new project package", icon: SaveAll, run: props.onSaveAs },
    { label: "Project only", detail: "Save without retained results", icon: Save, run: props.onSaveWithoutResults },
    { label: "Results file", detail: "Export the current results", icon: SaveAll, run: props.onSaveResultsFile },
  ];

  return <div className="modal-shade project-manager-shade" role="presentation">
    <section className="project-manager-modal" role="dialog" aria-modal="true" aria-labelledby="project-manager-title">
      <header className="project-manager-header">
        <div><FileArchive size={18} aria-hidden="true" /><span><b id="project-manager-title">Project manager</b><small>Project package, design summary, and recent work</small></span></div>
        <button type="button" className="canvas-icon spike-control--icon" onClick={props.onClose} aria-label="Close Project manager" title="Close Project manager"><X size={16} /></button>
      </header>

      <div className="project-manager-scroll">
        <section className="project-manager-current" aria-label="Current project summary">
          <div><span>Current project</span><b title={props.projectName}>{props.projectName}</b><small title={props.projectPath ?? undefined}>{props.projectPath ?? "Not saved to a native path"}</small></div>
          <div><span>Embedded design</span><b title={props.boardFile}>{props.boardFile}</b><small>{props.counts.layers} layers · {props.counts.nets} nets · {props.counts.components} components · {props.counts.results} results</small></div>
        </section>

        <div className="project-manager-actions">
          <ActionGroup label="Open and create" actions={openActions} />
          <ActionGroup label="Save and export" actions={saveActions} />
        </div>

        <section className="recent-projects" aria-labelledby="recent-projects-title">
          <h3 id="recent-projects-title"><History size={14} aria-hidden="true" /> Recent projects</h3>
          {props.recent.length ? <div className="recent-project-list">{props.recent.map(item => <button type="button" key={`${item.path}:${item.openedAt}`} onClick={props.onOpen} title={item.path ?? item.name}>
            <FileArchive size={14} aria-hidden="true" /><span><b>{item.name}</b><small>{item.path ?? "Browser project"}</small></span><time dateTime={item.openedAt}>{new Date(item.openedAt).toLocaleString()}</time>
          </button>)}</div> : <p>No projects have been opened or saved in this profile.</p>}
        </section>
      </div>

      <footer><span>Desktop format: spike-project-package/v3</span><button type="button" className="secondary-btn spike-control--compact" onClick={props.onClose}>Close</button></footer>
    </section>
  </div>;
}
