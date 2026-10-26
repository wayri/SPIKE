// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { RefreshCw, RotateCcw, Save } from "./icons";
import { runNativeProjectWorker } from "./workerBridge";
import type { ProjectBackupRecord } from "./projectBackupScheduler";
import SectionHelpButton from "./SectionHelpButton";
import "./projectBackups.css";
export default function ProjectBackupsPanel({ desktop, status, onBackup, onRestore }: {desktop:boolean;status:string;onBackup:()=>Promise<boolean>;onRestore:(id:string)=>void}) {
  const [records,setRecords]=useState<ProjectBackupRecord[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const alive=useRef(true),working=useRef(false);
  const refresh=async()=>{if(!desktop||working.current)return;working.current=true;setBusy(true);setError("");try{const response=await runNativeProjectWorker({method:"list_project_backups",params:{}});if(!response.ok)throw new Error(response.error??"Cannot list recovery backups.");if(alive.current)setRecords(Array.isArray(response.result?.backups)?response.result.backups as ProjectBackupRecord[]:[]);}catch(caught){if(alive.current)setError(caught instanceof Error?caught.message:String(caught));}finally{working.current=false;if(alive.current)setBusy(false);}};
  useEffect(()=>{alive.current=true;void refresh();return()=>{alive.current=false;};},[desktop]);
  return <section className="project-backups" aria-labelledby="project-backups-title"><header><h3 id="project-backups-title">Project recovery backups</h3><SectionHelpButton topic="doc:docs/PROJECT_BACKUPS.md" label="Project backups"/></header>
    <p>Automatic backups keep separate local recovery packages. Restore opens a copy; Save asks for a new project file.</p>
    <p role="status">{status}</p>{!desktop&&<p>Durable project backups require SPIKE desktop. Browser preview exports remain available through Save.</p>}
    <div className="project-backups-actions"><button type="button" disabled={!desktop||busy} onClick={()=>void (async()=>{if(await onBackup())await refresh();})()}><Save size={14}/>Back up now</button><button type="button" disabled={!desktop||busy} onClick={()=>void refresh()}><RefreshCw size={14}/>Refresh backups</button></div>
    {error&&<p role="alert">{error}</p>}
    <div className="project-backups-list">{records.map(record=><article key={record.id}><div><b title={record.project_name}>{record.project_name}</b><small><time dateTime={record.created_at}>{new Date(record.created_at).toLocaleString()}</time> · {(record.bytes/1048576).toFixed(1)} MiB</small></div><button type="button" disabled={busy} onClick={()=>onRestore(record.id)} aria-label={`Restore copy of ${record.project_name} from ${record.created_at}`}><RotateCcw size={14}/>Restore copy</button></article>)}</div>
    {desktop&&!busy&&!records.length&&<p>No recovery packages yet. Enable backups in Settings → Backups or use Back up now.</p>}
  </section>;
}
