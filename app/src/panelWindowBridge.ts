// SPDX-License-Identifier: Apache-2.0
/** Presentation-only native boundary; does not dispatch worker/solver operations. */
export async function setPanelUiScale(scale:number):Promise<void> {
  if(!Number.isFinite(scale)||scale<.65||scale>1.5)throw new Error("UI scale must be between 65% and 150%.");
  if(typeof window!=="undefined" && "__TAURI_INTERNALS__" in window){
    const {invoke}=await import("@tauri-apps/api/core");await invoke("set_panel_ui_scale",{scale});
  } else if(typeof document!=="undefined")document.documentElement.style.zoom=String(scale);
}

/** Capture native identity while the linked document is live, before unload. */
export function prepareLinkedPanelClose(child:Window):()=>Promise<void> {
  let label=(child as Window & {__SPIKE_PANEL_WINDOW_LABEL__?:unknown}).__SPIKE_PANEL_WINDOW_LABEL__;
  const native=typeof window!=="undefined" && "__TAURI_INTERNALS__" in window;
  return async()=>{
    if(native){
      if(typeof label!=="string")try{label=(child as Window & {__SPIKE_PANEL_WINDOW_LABEL__?:unknown}).__SPIKE_PANEL_WINDOW_LABEL__;}catch{/* Initial identity remains available after unload. */}
      if(typeof label!=="string" || !/^spike-panel-popup-[1-9][0-9]*$/.test(label))throw new Error("Floating window identity unavailable; close its native title bar and retry.");
      const {WebviewWindow}=await import("@tauri-apps/api/webviewWindow");
      const view=await WebviewWindow.getByLabel(label);if(view)await view.destroy();
    }else if(!child.closed)child.close();
  };
}
/** Qualification queries presentation hosts only; no files or solver operations. */
export async function countLinkedPanelWindows():Promise<number> {
  const {getAllWebviewWindows}=await import("@tauri-apps/api/webviewWindow");
  return (await getAllWebviewWindows()).filter(view=>/^spike-panel-popup-[1-9][0-9]*$/.test(view.label)).length;
}
