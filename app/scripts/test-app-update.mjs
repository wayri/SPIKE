// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import ts from "typescript";
import {importTestTypescript} from "./import-test-typescript.mjs";
const model=await importTestTypescript("appUpdateModel");
const {admittedAppUpdate,appUpdateBlockers,canInstallAppUpdate,updateDownloadPercent}=model;
assert.throws(()=>admittedAppUpdate({contract:"evil",status:"ready"}));
assert.throws(()=>admittedAppUpdate({contract:"spike/app-update/v1",status:"launch-any-file"}));
const ready=admittedAppUpdate({contract:"spike/app-update/v1",status:"ready",latest_version:"0.4.0",size:20,release_url:"https://evil.test/releases",unattended_supported:"true"});
assert.equal(ready.release_url,undefined);assert.equal(ready.unattended_supported,false);
assert.equal(updateDownloadPercent({...ready,status:"downloading",received_bytes:20}),99,"100% only after hash verification");
assert.equal(updateDownloadPercent({contract:ready.contract,status:"downloading"}),undefined);
const empty={hasProject:false,dirty:false,busy:false,editorsOpen:false};
assert.deepEqual(appUpdateBlockers(empty),[]);
for(const patch of [{hasProject:true},{dirty:true},{busy:true},{editorsOpen:true},{draftOwner:"workspace"},{detachedWindowsOpen:true}]){
 const blockers=appUpdateBlockers({...empty,...patch});assert(blockers.length>0);assert.equal(canInstallAppUpdate(ready,blockers,true,false),false);
}
assert.equal(canInstallAppUpdate(ready,[],false,false),false);
assert.equal(canInstallAppUpdate({...ready,status:"downloading"},[],true,false),false);
assert.equal(canInstallAppUpdate(ready,[],true,true),false);
assert.equal(canInstallAppUpdate(ready,[],true,false),true);
const states=[],refs=[],effects=[];let index=0;
const react={
 useState(initial){const i=index++;if(!(i in states))states[i]=typeof initial==="function"?initial():initial;return[states[i],next=>{states[i]=typeof next==="function"?next(states[i]):next;}];},
 useRef(initial){const i=index++;return refs[i]??={current:initial};},
 useEffect(effect,deps){const i=index++;if(!effects[i]||JSON.stringify(effects[i].deps)!==JSON.stringify(deps))effects[i]={effect,deps,pending:true};}
};
const jsx={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
const bridgeCalls=[];let resolveCheck,resolveDownload;
const bridge={
 isDesktopShell:()=>true,appUpdateStatus:async()=>model.idleAppUpdate,
 appUpdateCheck:()=>{bridgeCalls.push("check");return new Promise(resolve=>resolveCheck=resolve);},
 appUpdateDownload:()=>{bridgeCalls.push("download");return new Promise(resolve=>resolveDownload=resolve);},
 appUpdateCancel:async()=>undefined,
 appUpdateInstall:async()=>{bridgeCalls.push("install");return{contract:ready.contract,status:"installing"};}
};
globalThis.localStorage={getItem(){return null;},setItem(){}};
globalThis.document={activeElement:null};
globalThis.window={setInterval(){return 1;},clearInterval(){}};
const source=readFileSync(new URL("../src/AppUpdatePanel.tsx",import.meta.url),"utf8"),module={exports:{}};
new Function("require","module","exports",ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText)(
 name=>name==="react"?react:name==="react/jsx-runtime"?jsx:name==="./workerBridge"?bridge:name==="./appUpdateModel"?model:{},module,module.exports);
let props={visible:true,onHide(){},blockers:[],canCloseProject:true,canSaveProject:false,onSave:async()=>{},onCloseProject(){},onStatus(){}};
const render=()=>{index=0;return module.exports.default(props);};
const nodes=tree=>!tree||typeof tree!=="object"?[]:[tree,...[tree.props?.children].flat(Infinity).flatMap(nodes)];
const button=(tree,text)=>nodes(tree).find(node=>node.type==="button"&&[node.props.children].flat(Infinity).some(value=>value===text));
let tree=render();
button(tree,"Check GitHub").props.onClick();props.visible=false;assert.equal(render(),null);
resolveCheck({contract:ready.contract,status:"available",asset_name:"SPIKE_0.4.0_x64-setup.exe",latest_version:"0.4.0",size:20});await new Promise(resolve=>setImmediate(resolve));
props.visible=true;tree=render();assert(button(tree,"Download update"),"hidden panel retains completed check");
button(tree,"Download update").props.onClick();props.visible=false;assert.equal(render(),null);
resolveDownload(ready);await new Promise(resolve=>setImmediate(resolve));
props.visible=true;tree=render();assert.equal(button(tree,"Install update and close SPIKE").props.disabled,true,"installation needs acknowledgment after background download");
const consent=nodes(tree).filter(node=>node.type==="input"&&node.props.type==="checkbox").find(node=>node.props.checked===false&&!node.props.disabled);
consent.props.onChange({target:{checked:true}});tree=render();assert.equal(button(tree,"Install update and close SPIKE").props.disabled,false);
props.blockers=["New work opened"];tree=render();assert.equal(button(tree,"Install update and close SPIKE").props.disabled,true,"new work revokes readiness");
assert.deepEqual(bridgeCalls,["check","download"],"no hidden or automatic installation");
states[0]={...ready,status:"cancelled",asset_name:"SPIKE_0.4.0_x64-setup.exe"};tree=render();
assert(!button(tree,"Download update"),"cancelled downloads must be checked again before retry");
assert(button(tree,"Check GitHub"));
// A persisted unattended installer failure must reach activity before an automatic new check.
states.length=0;refs.length=0;effects.length=0;
const startupEvents=[];
globalThis.localStorage.getItem=()=>JSON.stringify({checkAtStartup:true});
bridge.appUpdateStatus=async()=>({contract:ready.contract,status:"failed",error:"Setup exited with code 7"});
bridge.appUpdateCheck=async()=>{startupEvents.push("check");return{contract:ready.contract,status:"current"};};
props={...props,visible:false,blockers:[],onStatus:message=>startupEvents.push(message)};
render();for(const effect of effects.filter(Boolean))effect.effect();
await new Promise(resolve=>setImmediate(resolve));
assert(startupEvents[0].includes("Setup exited with code 7"),"startup install failure must be reported before being replaced");
assert.equal(startupEvents.length,1,"a recovered failed update requires explicit retry, even with startup checks enabled");
console.log("App updater: integrity-state admission, work/draft guards, acknowledgment, background completion and no automatic install passed.");
