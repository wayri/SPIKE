// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { Download, RefreshCw, ShieldCheck, Minus, X } from "./icons";
import { appUpdateCheck, appUpdateStatus, appUpdateDownload, appUpdateCancel, appUpdateInstall, isDesktopShell } from "./workerBridge";
import { admittedAppUpdate, idleAppUpdate, canInstallAppUpdate, updateDownloadPercent, updateBytes, type AppUpdateSnapshot } from "./appUpdateModel";
import "./buttonStandard.css";
import "./AppUpdatePanel.css";
type Preferences = { checkAtStartup: boolean; autoDownload: boolean };
function loadPreferences(): Preferences {
  try { const row=JSON.parse(localStorage.getItem("spike.appUpdate.preferences") || "{}"); return {checkAtStartup:row.checkAtStartup===true,autoDownload:row.autoDownload===true}; } catch { return {checkAtStartup:false,autoDownload:false}; }
}
/** Remains mounted when hidden: network work and update readiness belong to the main workspace. */
export default function AppUpdatePanel({ visible, onHide, blockers, canCloseProject, canSaveProject, onSave, onCloseProject, onStatus }: {
  visible: boolean; onHide: () => void; blockers: readonly string[]; canCloseProject: boolean; canSaveProject: boolean;
  onSave: () => Promise<unknown>; onCloseProject: () => void; onStatus: (message: string) => void;
}) {
  const [state,setState]=useState<AppUpdateSnapshot>(idleAppUpdate);
  const [pending,setPending]=useState(false),[acknowledged,setAcknowledged]=useState(false),[unattended,setUnattended]=useState(false);
  const [preferences,setPreferences]=useState(loadPreferences);
  const [cancelPending,setCancelPending]=useState(false);
  const mounted=useRef(true),busy=useRef(false),prefs=useRef(preferences),latest=useRef({blockers,onStatus});
  prefs.current=preferences;latest.current={blockers,onStatus};
  const desktop=isDesktopShell();
  const reportedPhase=useRef("");
  const panel=useRef<HTMLElement>(null);
  const publish=(value:unknown)=>{const next=admittedAppUpdate(value);if(mounted.current)setState(next);if(next.status==="ready"&&reportedPhase.current!=="ready")latest.current.onStatus(`SPIKE ${next.latest_version || "update"} downloaded and verified. Open SPIKE updates to install.`);if(next.status==="failed"&&reportedPhase.current!=="failed")latest.current.onStatus(`SPIKE update failed: ${next.error || next.message || "Check GitHub again."}`);reportedPhase.current=next.status;return next;};
  const fail=(error:unknown)=>{const message=error instanceof Error?error.message:String(error);if(mounted.current)setState(current=>({...current,status:"failed",error:message,message:undefined}));latest.current.onStatus(`SPIKE update: ${message}`);};
  const run=async(action:"check"|"download")=>{
    if(busy.current||!desktop)return;
    busy.current=true;setPending(true);setAcknowledged(false);
    setState(current=>({...current,status:action==="check"?"checking":"downloading",error:undefined,received_bytes:action==="download"?0:current.received_bytes}));
    try {
      const next=publish(await(action==="check"?appUpdateCheck():appUpdateDownload()));
      if(action==="check"&&next.status==="available"&&prefs.current.autoDownload){
        setState(current=>({...current,status:"downloading",received_bytes:0}));publish(await appUpdateDownload());
      }
    } catch(error){fail(error);} finally{busy.current=false;if(mounted.current)setPending(false);}
  };
  useEffect(()=>{
    mounted.current=true;
    if(desktop)void appUpdateStatus().then(value=>{publish(value);if(mounted.current&&prefs.current.checkAtStartup&&admittedAppUpdate(value).status!=="failed")void run("check");}).catch(fail);
    return()=>{mounted.current=false;};
  },[]);
  useEffect(()=>{try{localStorage.setItem("spike.appUpdate.preferences",JSON.stringify(preferences));}catch{/* Optional preference only. */}},[preferences]);
  useEffect(()=>{
    if(!desktop||!["checking","downloading","installing"].includes(state.status))return;
    let stopped=false,reading=false;
    const timer=window.setInterval(()=>{if(reading)return;reading=true;void appUpdateStatus().then(value=>{if(!stopped)publish(value);}).catch(error=>{if(!stopped)fail(error);}).finally(()=>{reading=false;});},1000);
    return()=>{stopped=true;window.clearInterval(timer);};
  },[desktop,state.status]);
  useEffect(()=>{setAcknowledged(false);},[blockers.join("|"),state.latest_version]);
  useEffect(()=>{
    if(!visible)return;
    const previous=document.activeElement;
    panel.current?.querySelector<HTMLElement>("button:not(:disabled)")?.focus();
    return()=>{if(previous instanceof HTMLElement&&previous.isConnected)previous.focus();};
  },[visible]);
  const cancel=async()=>{
    if(cancelPending)return;setCancelPending(true);
    try{await appUpdateCancel();publish(await appUpdateStatus());}catch(error){fail(error);}finally{if(mounted.current)setCancelPending(false);}
  };
  const install=async()=>{
    if(!canInstallAppUpdate(state,latest.current.blockers,acknowledged,pending))return;
    busy.current=true;setPending(true);setState(current=>({...current,status:"installing"}));
    try {
      // This uses current blockers at action time. Native code independently rechecks its operation state and verified cache.
      if(latest.current.blockers.length)throw new Error("Close active work before installing.");
      publish(await appUpdateInstall(true,unattended&&state.unattended_supported===true));
    }catch(error){fail(error);}finally{busy.current=false;if(mounted.current)setPending(false);}
  };
  if(!visible)return null;
  const percent=updateDownloadPercent(state),downloading=state.status==="downloading";
  return <div className="modal-shade app-update-shade" role="dialog" aria-modal="true" aria-labelledby="app-update-title" onKeyDown={event=>{
      event.stopPropagation();
      if(event.key==="Escape"){event.preventDefault();if(state.status!=="installing")onHide();}
      if(event.key==="Tab"){
        const entries=[...(panel.current?.querySelectorAll<HTMLElement>("button:not(:disabled),input:not(:disabled),summary,a[href]") ?? [])],first=entries[0],last=entries[entries.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    }}>
    <section className="app-update-panel" ref={panel}>
      <header><div><h2 id="app-update-title">SPIKE updates</h2><small>Official GitHub releases · wayri/spike</small></div><button type="button" className="spike-control--icon" aria-label="Minimize updates" disabled={state.status==="installing"} title="Hide this panel; downloads continue in the background" onClick={onHide}><Minus size={16}/></button></header>
      <main>
        <p>Check the latest stable release and download its installer without interrupting your work.</p>
        <div className="app-update-version"><span>Installed <b>{state.current_version || (desktop ? "Detecting…" : "Native app required")}</b></span>{state.latest_version&&<span>Latest <b>{state.latest_version}</b></span>}</div>
        {!desktop&&<p role="status">Application updates require the native SPIKE desktop application. This browser preview cannot install updates.</p>}
        <div className="app-update-actions"><button type="button" disabled={!desktop||pending||state.status==="installing"} onClick={()=>void run("check")}><RefreshCw size={15}/>{state.status==="checking"?"Checking…":"Check GitHub"}</button>
          {state.status==="available"&&state.asset_name&&<button type="button" className="spike-control--primary" disabled={!desktop||pending} onClick={()=>void run("download")}><Download size={15}/>Download update</button>}
          {downloading&&<button type="button" disabled={cancelPending} onClick={()=>void cancel()}><X size={15}/>{cancelPending?"Cancelling…":"Cancel download"}</button>}</div>
        {state.asset_name&&<p className="app-update-asset">{state.asset_name} · {updateBytes(state.size)}</p>}
        {downloading&&<div className="app-update-progress"><progress aria-label="Installer download" max={100} value={percent}/><span>{percent===undefined?"Downloading…":`${percent}%`} · {updateBytes(state.received_bytes)} received</span><small>You may hide this panel and keep working. Setup will not start automatically.</small></div>}
        {(state.message||state.error)&&<p className="app-update-message" role={state.error?"alert":"status"}>{state.error||state.message}</p>}
        {state.status==="current"&&<p role="status">This installation is up to date.</p>}
        {state.status==="ready"&&<>
          <div className="app-update-warning"><h3><ShieldCheck size={16}/>Before installing</h3><p>Save all work and close the project, simulations, editor windows and detached tools. SPIKE will close to release its files. Do not reopen it until setup has finished.</p><p>The update helper accesses only its update cache and SPIKE installation. Projects, board files and saved results are not cleanup targets. Setup files are deleted after setup finishes; interrupted update files are cleaned at the next startup.</p></div>
          {blockers.length>0&&<ul className="app-update-blockers">{blockers.map(message=><li key={message}>{message}</li>)}</ul>}
          <div className="app-update-actions"><button type="button" disabled={!canSaveProject||pending} onClick={()=>void onSave().catch(fail)}>Save project</button><button type="button" disabled={!canCloseProject||pending} onClick={onCloseProject}>Close project</button></div>
          {state.unattended_supported&&<label className="app-update-choice"><input type="checkbox" checked={unattended} onChange={event=>setUnattended(event.target.checked)}/>Run setup silently (Windows may still ask for permission)</label>}
          <label className="app-update-choice"><input type="checkbox" checked={acknowledged} disabled={blockers.length>0} onChange={event=>setAcknowledged(event.target.checked)}/>I have saved and closed my work. Close SPIKE and start the update.</label>
          <button type="button" className="spike-control--primary" disabled={!canInstallAppUpdate(state,blockers,acknowledged,pending)} onClick={()=>void install()}><Download size={15}/>Install update and close SPIKE</button>
        </>}
        {state.status==="installing"&&<p role="status">Preparing update handoff. SPIKE will close; setup starts after the application exits.</p>}
        <details><summary>Automatic download preferences</summary><label className="app-update-choice"><input type="checkbox" checked={preferences.checkAtStartup} onChange={event=>setPreferences(current=>({...current,checkAtStartup:event.target.checked}))}/>Check GitHub on startup</label><label className="app-update-choice"><input type="checkbox" checked={preferences.autoDownload} onChange={event=>setPreferences(current=>({...current,autoDownload:event.target.checked}))}/>Download new releases automatically after checking</label><small>These preferences never authorize installation or closing your work.</small></details>
      </main>
      <footer><span>Background downloads continue when this panel is hidden.</span><button type="button" disabled={state.status==="installing"} onClick={onHide}>Hide</button></footer>
    </section>
  </div>;
}
