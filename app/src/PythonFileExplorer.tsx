// SPDX-License-Identifier: Apache-2.0
import { ChevronDown, ChevronRight, FileCode2, Folder, FolderOpen, GitBranch, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { runLocalWorker } from "./workerBridge";
import { pythonAbsolutePath, pythonFileName, pythonPathKey, type PythonDocument, type PythonTreeEntry, type PythonTreeListing } from "./pythonWorkspaceModel";

type Worktree = { path: string; branch?: string; detached?: boolean; locked?: boolean; prunable?: boolean };
export default function PythonFileExplorer({ root, roots = [], documents, activePath, activeId, desktop, onRoot, onActivate, onOpenFolder, onOpenFile }: {
  root?: string; roots?: string[]; documents: PythonDocument[]; activePath?: string; activeId?: string; desktop: boolean;
  onActivate: (id: string) => void;
  onRoot: (root: string) => void; onOpenFolder: () => void; onOpenFile: (path: string, root: string) => void;
}) {
  const [directories, setDirectories] = useState<Record<string, PythonTreeListing>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [worktrees, setWorktrees] = useState<Worktree[]>([]);
  const [gitMessage, setGitMessage] = useState("");
  const [gitLoading, setGitLoading] = useState(false);
  const tree = useRef<HTMLDivElement>(null);
  const generation = useRef(0);
  const discoverWorktrees = async () => {
    const expected = generation.current;
    setGitLoading(true); setGitMessage("");
    try {
      const response = await runLocalWorker({ method: "python_workspace_files", params: { action: "worktrees", root } });
      if (generation.current !== expected) return;
      if (!response.ok) throw new Error(response.error ?? "Could not inspect worktrees.");
      const result = response.result;
      const entries = Array.isArray(result?.worktrees) ? result.worktrees.filter((item: Worktree) => item && typeof item.path === "string") as Worktree[] : [];
      setWorktrees(entries); setGitMessage(typeof result?.message === "string" ? result.message : entries.length ? "Switching folders keeps open tabs and their save paths." : "No worktrees found.");
    } catch (caught) { if (generation.current === expected) setGitMessage(caught instanceof Error ? caught.message : String(caught)); }
    finally { if (generation.current === expected) setGitLoading(false); }
  };
  const load = async (path?: string, expected = generation.current) => {
    const key = path ?? ".";
    setLoading(current => new Set(current).add(key));
    try {
      const response = await runLocalWorker({ method: "python_workspace_files", params: { action: "list", root, path } });
      if (expected !== generation.current) return;
      if (!response.ok) throw new Error(response.error ?? "Could not list the folder.");
      const listing = response.result as unknown as PythonTreeListing;
      if (!listing || !Array.isArray(listing.entries)) throw new Error("The worker returned an invalid folder listing.");
      setDirectories(current => ({ ...current, [listing.path]: listing }));
      setExpanded(current => new Set(current).add(listing.path));
      setError("");
      if (!root) onRoot(listing.root);
    } catch (caught) { if (expected === generation.current) setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { if (expected === generation.current) setLoading(current => { const next = new Set(current); next.delete(key); return next; }); }
  };
  useEffect(() => {
    const current = ++generation.current;
    setDirectories({}); setExpanded(new Set()); setLoading(new Set()); setError(""); setWorktrees([]); setGitMessage(""); setGitLoading(false);
    if (desktop) void load(undefined, current);
    return () => { generation.current++; };
  }, [root, desktop]);
  const toggle = (entry: PythonTreeEntry) => {
    if (expanded.has(entry.path)) setExpanded(current => { const next = new Set(current); next.delete(entry.path); return next; });
    else {
      setExpanded(current => new Set(current).add(entry.path));
      if (!directories[entry.path]) void load(entry.path);
    }
  };
  const query = filter.trim().toLowerCase();
  let rendered = 0;
  const rows = (path: string, depth = 0): React.ReactNode => {
    const listing = directories[path];
    if (!listing || depth > 20) return null;
    return <>{listing.entries.filter(entry => !query || entry.kind === "directory" || entry.name.toLowerCase().includes(query)).map(entry => {
      if (++rendered > 1000) return null;
      const directory = entry.kind === "directory", open = expanded.has(entry.path);
      return <div key={entry.path}><button type="button" className={`python-tree-row ${activePath && pythonPathKey(activePath) === pythonPathKey(pythonAbsolutePath(listing.root, entry.path)) ? "active" : ""}`} style={{ paddingLeft: 8 + depth * 13 }} title={pythonAbsolutePath(listing.root, entry.path)} onClick={() => directory ? toggle(entry) : onOpenFile(entry.path, root ?? listing.root)} disabled={loading.has(entry.path)} aria-expanded={directory ? open : undefined}>
        {directory ? open ? <ChevronDown size={12} /> : <ChevronRight size={12} /> : <span className="python-tree-spacer" />}{directory ? <Folder size={14} /> : <FileCode2 size={14} />}<span>{entry.name}</span>{loading.has(entry.path) && <small>…</small>}
      </button>{directory && open && rows(entry.path, depth + 1)}</div>;
    })}{listing.truncated && <p className="python-pane-note">Folder listing truncated. Open a smaller folder.</p>}</>;
  };
  return <div className="python-explorer">
    <div className="python-pane-heading"><b>FILES</b><button type="button" onClick={onOpenFolder} disabled={!desktop} title="Open scripts folder" aria-label="Open scripts folder"><FolderOpen size={14} /></button><button type="button" onClick={() => { const current = ++generation.current; setDirectories({}); setExpanded(new Set()); setLoading(new Set()); setGitLoading(false); void load(undefined, current); }} disabled={!desktop || loading.size > 0} title="Refresh files" aria-label="Refresh files"><RefreshCw size={13} /></button></div>
    <div className="python-explorer-root" title={root}>{root ? pythonFileName(root) : desktop ? "Loading workspace…" : "Open files"}</div>
    {desktop && roots.length > 1 && <label className="python-backup-select">Workspace<select aria-label="Workspace folder" value={root} onChange={event => onRoot(event.target.value)}>{Array.from(new Set([...(root ? [root] : []), ...roots])).map(path => <option key={path} value={path}>{path}</option>)}</select></label>}
    <details className="python-open-files" open><summary>OPEN EDITORS · {documents.length}</summary>{documents.map(document => <button type="button" key={document.id} aria-label={`${document.name} · ${document.code !== document.savedCode ? "Unsaved" : document.path ? "Saved" : "Draft"}`} aria-current={document.id === activeId ? "page" : undefined} className={`python-tree-row ${document.id === activeId || document.path && activePath === document.path ? "active" : ""}`} title={document.path ?? document.name} onClick={() => onActivate(document.id)}><FileCode2 size={12} /><span>{document.name}</span><small className={`python-save-state ${document.code !== document.savedCode ? "dirty" : ""}`}>{document.code !== document.savedCode ? "Unsaved" : document.path ? "Saved" : "Draft"}</small></button>)}</details>
    <input aria-label="Filter loaded files" placeholder="Filter loaded files…" value={filter} onChange={event => setFilter(event.target.value)} />
    {error && <p role="alert" className="python-pane-error">{error}</p>}
    <div ref={tree} className="python-file-tree" aria-label="Python workspace file tree" onKeyDown={event => { if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return; const buttons = Array.from(tree.current?.querySelectorAll<HTMLButtonElement>("button") ?? []); const index = buttons.indexOf(event.target as HTMLButtonElement); if (index < 0) return; event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))); buttons[next]?.focus(); }}>{desktop && root ? rows(".") : <p className="python-pane-note">Open a folder in the desktop app to browse its files.</p>}</div>
    {desktop && <details className="python-worktree-section"><summary><GitBranch size={12} /> GIT WORKTREES</summary><button type="button" onClick={() => void discoverWorktrees()} disabled={gitLoading}>{gitLoading ? "Inspecting…" : "Find worktrees"}</button>{worktrees.map(item => <button type="button" className="python-worktree-row" key={item.path} title={item.path} aria-pressed={!!root && pythonPathKey(root) === pythonPathKey(item.path)} onClick={() => onRoot(item.path)}><span>{pythonFileName(item.path)}</span><small>{item.branch?.replace(/^refs\/heads\//, "") ?? (item.detached ? "Detached HEAD" : "No branch")}{item.locked ? " · locked" : ""}{item.prunable ? " · prunable" : ""}</small></button>)}{gitMessage && <p className="python-pane-note" role="status">{gitMessage}</p>}</details>}
    <p className="python-pane-note">Folders load on expansion. Generated and dependency folders are omitted. Scripts save to their own files.</p>
  </div>;
}
