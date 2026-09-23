import { FileArchive, FilePlus2, FolderOpen, History, Save, SaveAll, X } from "lucide-react";

export type RecentProject = { name: string; path: string | null; openedAt: string };

export default function ProjectManager({ projectName, projectPath, boardFile, counts, recent, onNew, onOpen, onSave, onSaveAs, onClose }: {
  projectName: string; projectPath: string | null; boardFile: string;
  counts: { layers: number; nets: number; components: number; results: number };
  recent: RecentProject[]; onNew: () => void; onOpen: () => void; onSave: () => void; onSaveAs: () => void; onClose: () => void;
}) {
  return <div className="modal-shade" role="dialog" aria-modal="true" aria-label="Project manager"><section className="project-manager-modal">
    <header><div><FileArchive size={18} /><span><b>Project manager</b><small>SPIKE project package and recent work</small></span></div><button className="canvas-icon" onClick={onClose}><X size={16} /></button></header>
    <div className="project-manager-current"><div><span>Current project</span><b>{projectName}</b><small>{projectPath ?? "Not saved to a native path"}</small></div><div><span>Embedded design</span><b>{boardFile}</b><small>{counts.layers} layers · {counts.nets} nets · {counts.components} components · {counts.results} results</small></div></div>
    <div className="project-manager-actions"><button onClick={onNew}><FilePlus2 size={17} /><span>New project</span></button><button onClick={onOpen}><FolderOpen size={17} /><span>Open</span></button><button onClick={onSave}><Save size={17} /><span>Save</span></button><button onClick={onSaveAs}><SaveAll size={17} /><span>Save as</span></button></div>
    <section className="recent-projects"><h3><History size={14} /> Recent projects</h3>{recent.length ? recent.map(item => <button key={`${item.path}:${item.openedAt}`} onClick={onOpen}><FileArchive size={14} /><span><b>{item.name}</b><small>{item.path ?? "Browser project"}</small></span><time>{new Date(item.openedAt).toLocaleString()}</time></button>) : <p>No projects have been opened or saved in this profile.</p>}</section>
    <footer><span>Format: spike-project-package/v2</span><button className="secondary-btn" onClick={onClose}>Close</button></footer>
  </section></div>;
}
