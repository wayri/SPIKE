// SPDX-License-Identifier: Apache-2.0
import { useId, useState, type ReactNode } from "react";
import { ChevronDown, FolderOpen, PanelLeft, Search, type LucideIcon } from "./icons";
import ActionContextMenu, { type ContextAction } from "./ActionContextMenu";
import CommandStrip from "./CommandStrip";

export type WorkspaceShortcut = { name: string; icon: LucideIcon };
type Props = {
  projectName: string; fileActions: ContextAction[]; onFilesOpen: () => void;
  workspaces: readonly WorkspaceShortcut[]; activeWorkspace: string; onWorkspace: (name: string) => void;
  showWorkspaceBar: boolean; workspaceSwitcher: ReactNode; utilities: ReactNode;
  menuOpen: boolean; onMenu: () => void; searchOpen: boolean; onSearch: () => void;
};

/** File actions remain wired to the owner's unsaved-change and native-dialog flows. */
export default function WorkspaceHeader(props: Props) {
  const [fileAnchor, setFileAnchor] = useState<{x:number;y:number}|null>(null);
  const fileMenuId = useId();
  const openFiles = (button: HTMLButtonElement) => {
    props.onFilesOpen();
    const bounds = button.getBoundingClientRect();
    setFileAnchor({x:bounds.left,y:bounds.bottom+4});
  };
  return <header className={`topbar workspace-header ${props.showWorkspaceBar?"has-workspace-shortcuts":""}`}>
    <div className="workspace-header-main">
      <div className="workspace-header-brand">
        <button type="button" id="focus-menu-toggle" className="focus-menu-toggle spike-control--compact" aria-expanded={props.menuOpen} aria-controls="focus-command-panel" onClick={props.onMenu}><PanelLeft size={15}/> Menu</button>
        <div className="brand-mark"><b>SPIKE</b></div>
      </div>
      <button type="button" className="project-path workspace-project-trigger" aria-label={`Project files: ${props.projectName}`} title={`Open, save, import or export ${props.projectName}`} aria-haspopup="menu" aria-expanded={Boolean(fileAnchor)} aria-controls={fileAnchor?fileMenuId:undefined}
        onClick={event=>fileAnchor?setFileAnchor(null):openFiles(event.currentTarget)}
        onKeyDown={event=>{if(event.key==="ArrowDown"){event.preventDefault();openFiles(event.currentTarget);}}}>
        <FolderOpen size={16}/><b>{props.projectName}</b><ChevronDown size={13}/>
      </button>
      <button type="button" className={`universal-search-trigger workspace-header-search ${props.searchOpen?"active":""}`} aria-label="Open universal search" title="Search commands, workspaces, parts, nets and settings (Ctrl+K)" aria-keyshortcuts="Control+K Meta+K" aria-expanded={props.searchOpen} onClick={props.onSearch}>
        <Search size={19}/><span>Search commands, parts, nets…</span><kbd>Ctrl K</kbd>
      </button>
      <div className="workspace-header-utilities">{props.workspaceSwitcher}{props.utilities}</div>
    </div>
    {props.showWorkspaceBar&&<nav className="workspace-header-navigation" aria-label="Workspaces"><CommandStrip label="Workspace shortcuts" className="workspace-quick-switch">
      {props.workspaces.map(item=><button type="button" key={item.name} aria-pressed={props.activeWorkspace===item.name} onClick={()=>props.onWorkspace(item.name)} title={`${item.name} workspace`}><item.icon size={14}/><span>{item.name}</span></button>)}
    </CommandStrip></nav>}
    {fileAnchor&&<ActionContextMenu id={fileMenuId} {...fileAnchor} title="Project files" actions={props.fileActions} onClose={()=>setFileAnchor(null)}/>}
  </header>;
}
