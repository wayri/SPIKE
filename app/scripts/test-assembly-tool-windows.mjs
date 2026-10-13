// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import React from 'react';
import { createRequire } from 'node:module';
import { importTestTypescript } from './import-test-typescript.mjs';
const model = await importTestTypescript('assemblyToolWindowModel');
const source = readFileSync(new URL('../src/assemblyToolWindows.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const module = { exports: {} };
const groups = new Map(); let dropSnapshots = false;
class Channel {
 constructor(name) { this.name = name; this.listeners = []; this.closed = false; const list = groups.get(name) ?? []; list.push(this); groups.set(name, list); }
 addEventListener(_, listener) { this.listeners.push(listener); }
 postMessage(data) { if (dropSnapshots && data.event === 'spike-assembly-tool-snapshot') return; for (const peer of groups.get(this.name) ?? []) if (peer !== this && !peer.closed) queueMicrotask(() => peer.listeners.forEach(fn => fn({ data }))); }
 close() { this.closed = true; }
}
globalThis.BroadcastChannel = Channel;
const popups = [];
globalThis.window = { location: { href: 'http://localhost/index.html', search: '' }, open(url) { const child = { url, closed: false, focusCount: 0, close() { this.closed = true; }, focus() { this.focusCount++; } }; popups.push(child); return child; } };
const nativeWindows = new Map(), nativeCalls = [];
class NativeWindow {
 constructor(label, options) { this.label = label; this.options = options; this.handlers = new Map(); nativeWindows.set(label, this); }
 static async getByLabel(label) { return nativeWindows.get(label) ?? null; }
 async once(event, callback) { this.handlers.set(event, callback); return () => this.handlers.delete(event); }
 async unminimize() { nativeCalls.push('restore'); }
 async show() { nativeCalls.push('show'); }
 async setFocus() { nativeCalls.push('focus'); }
 async destroy() { nativeWindows.delete(this.label); this.handlers.get('tauri://destroyed')?.(); }
}
const nativeEvents = { listen: async () => () => {}, emitTo: async () => {} };
new Function('require', 'module', 'exports', js)(name => name === './assemblyToolWindowModel' ? model : name === './detachedToolWindows' ? { awaitNativeWindowCreated: async () => {} } : name === '@tauri-apps/api/event' ? nativeEvents : name === '@tauri-apps/api/webviewWindow' ? { WebviewWindow: NativeWindow } : (() => { throw new Error(name); })(), module, module.exports);
const api = module.exports;
const snapshot = { revision: 'first', assembly: null, designs: null };
const actions = []; let hang = false;
assert.equal(await api.focusAssemblyToolWindow('placement'),false);
await api.openAssemblyToolWindow('placement', snapshot, action => { actions.push(action); return hang ? new Promise(() => {}) : 42; });
assert.equal(await api.focusAssemblyToolWindow('placement'),true);
assert.equal(popups[0].focusCount,1,'reopening brings the existing tool forward');
const originalUrl=popups[0].url;
await api.openAssemblyToolWindow('placement', snapshot, action => { actions.push(action); return hang ? new Promise(() => {}) : 42; });
assert.equal(popups.length,1);assert.equal(popups[0].url,originalUrl,'reuse preserves the session token and child drafts');
window.location.search = new URL(popups[0].url, window.location.href).search;
const received = [];
const child = await api.connectAssemblyToolChild('placement', value => received.push(value));
await new Promise(resolve => setImmediate(resolve));
assert.equal(received.at(-1).revision, 'first', 'child ready receives current workspace snapshot');
assert.equal(await child.act({ type: 'move-mode', mode: 'rotate' }), 42);
assert.equal(actions.length, 1);
dropSnapshots = true;
await api.updateAssemblyToolWindow('placement', { ...snapshot, revision: 'second' });
await assert.rejects(child.act({ type: 'placement', boardId: 'A', transform: [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1] }), /Assembly changed/);
assert.equal(actions.length, 1, 'stale window cannot mutate a newer assembly');
dropSnapshots = false;
await api.updateAssemblyToolWindow('placement', { ...snapshot, revision: 'second' });
await new Promise(resolve => setImmediate(resolve));
assert.equal(await child.act({ type: 'explode', value: 12 }), 42);
assert.equal(actions.at(-1).value, 12);
const forged = new Channel(groups.keys().next().value);
forged.postMessage({ event: 'spike-assembly-tool-action', envelope: { kind: 'placement', token: 'wrong', action: { type: 'explode', value: 999 } } });
await new Promise(resolve => setImmediate(resolve));
assert.equal(actions.length, 2, 'token mismatch is rejected');
forged.close();
assert.equal(model.validAssemblyToolAction({ type: 'placement', transform: [NaN] }), false);
assert.equal(model.validAssemblyToolAction({ type: 'snap-gap', value: Infinity }), false);
assert.equal(model.validAssemblyToolAction({ type: 'unknown' }), false);
assert.equal(model.validAssemblyToolAction({ type: 'collaboration', mode: 'freecad' }), true);
assert.equal(model.validAssemblyToolAction({ type: 'collaboration', mode: 'attachments' }), true);
assert.equal(model.validAssemblyToolAction({ type: 'collaboration', mode: 'invented-plm' }), false,'collaboration routes stay bounded to owned SPIKE surfaces');
assert.equal(model.validAssemblyToolAction({ type: 'snap-target', boardId: 'A', value: 'A::hole::P1' }), true);
assert.equal(model.validAssemblyToolAction({ type: 'layer-focus', boardId: 'A', value: 'F.Cu' }), true);
assert.equal(model.validAssemblyToolAction({ type: 'layer-focus', boardId: 'A', value: '' }), false);
assert.equal(model.validAssemblyToolAction({ type: 'layer-focus', value: 'F.Cu' }), false);
assert.equal(model.validAssemblyToolViewportData({revision:'view-1',boards:{design:{tracks:[]}},assemblyModels:[]}),true);
assert.equal(model.validAssemblyToolViewportData({revision:'view-1',boards:Array.from({length:31},()=>({}))}),false);
assert.equal(model.validAssemblyToolAction({type:'layer-state',boardId:'B',layerVisibility:{'F.Cu':false},layerOpacity:{'F.Cu':.5}}),true);
assert.equal(model.validAssemblyToolAction({type:'layer-state',boardId:'B',layerVisibility:{'F.Cu':'false'}}),false);
assert.equal(model.validAssemblyToolAction({type:'layer-state',boardId:'B',layerVisibility:{'F.Cu':true},layerOpacity:{'F.Cu':NaN}}),false);
assert.equal(model.validAssemblyToolAction({type:'layer-state',boardId:'B',layerVisibility:{'F.Cu':true},layerOpacity:{'F.Cu':2}}),false);
assert.equal(model.validAssemblyToolAction({ type: 'update-assembly', assembly: { contract: 'wrong', boards: [], parts: [] } }), false);
hang = true;
const pending = child.act({ type: 'save' });
await new Promise(resolve => setImmediate(resolve));
child.stop();
await assert.rejects(pending, /closed/);
await api.closeAssemblyToolWindow('placement');
assert.equal(popups[0].closed, true);
assert.equal(api.assemblyToolKindFromLocation('?spikeAssemblyTool=workspace'), 'workspace');
assert.equal(api.assemblyToolKindFromLocation('?spikeAssemblyTool=arbitrary'), null);
await api.openAssemblyToolWindow('workspace',snapshot,()=>{});
popups.at(-1).closed=true;
await api.openAssemblyToolWindow('workspace',snapshot,()=>{});
assert.equal(popups.length,3,'a manually closed browser popup can be reopened');
const viewportSnapshot={...snapshot,viewportRevision:'view-1'};
const viewportData={revision:'view-1',boards:{design:{tracks:[]}},assemblyModels:[]};
await api.updateAssemblyToolWindow('workspace',viewportSnapshot,viewportData);
window.location.search=new URL(popups.at(-1).url,window.location.href).search;
const workspaceBridgeChild=await api.connectAssemblyToolChild('workspace',()=>{});
await new Promise(resolve=>setImmediate(resolve));
assert.deepEqual(await workspaceBridgeChild.requestViewport('view-1'),viewportData,'child fetches retained CPU renderer inputs only through its token-bound session');
await assert.rejects(workspaceBridgeChild.requestViewport('stale-view'),/changed/,'stale viewport revisions cannot retrieve current renderer inputs');
workspaceBridgeChild.stop();
await api.closeAssemblyToolWindow('workspace');
const openPopup=window.open;window.open=()=>null;
await assert.rejects(api.openAssemblyToolWindow('workspace',snapshot,()=>{}),/Allow local SPIKE popup/);
window.open=openPopup;
window.__TAURI_INTERNALS__={};
await api.openAssemblyToolWindow('workspace',snapshot,()=>{});
const nativeWorkspace=nativeWindows.get(model.assemblyToolLabels.workspace);
assert.equal(nativeWorkspace.options.title,'SPIKE | Multi-board workspace');
assert.equal(nativeWorkspace.options.decorations,true);assert.equal(nativeWorkspace.options.resizable,true);
assert.equal(nativeWorkspace.options.skipTaskbar,false,'native assembly tools retain independent Windows taskbar entries');
await api.openAssemblyToolWindow('managers',snapshot,()=>{});
const nativeManager=nativeWindows.get(model.assemblyToolLabels.managers);
assert.equal(nativeManager.options.width,600);
assert.equal(nativeManager.options.minWidth,600);
assert.equal(nativeManager.options.maxWidth,600,'manager width cannot change while boards/tabs switch');
assert.equal(nativeManager.options.maximizable,false);
assert.equal(nativeManager.options.resizable,true,'height remains adjustable');
await api.closeAssemblyToolWindow('managers');
const toolWindowSource=readFileSync(new URL('../src/assemblyToolWindows.ts',import.meta.url),'utf8');
assert.match(toolWindowSource,/kind === "placement" \? 860 : 600/,'board managers open at a compact native width while placement retains its wider surface');
const toolWindowCss=readFileSync(new URL('../src/assemblyToolWindows.css',import.meta.url),'utf8');
assert.match(toolWindowCss,/\.assembly-tool-managers\{padding:0;overflow:hidden;gap:0\}/,'manager root delegates scrolling to its active content');
assert.match(toolWindowCss,/\.assembly-tool-native\.assembly-tool-managers \.assembly-manager-shade\{flex-direction:column\}/,'native manager shade lets its child shrink on the vertical axis');
assert.match(toolWindowCss,/\.assembly-tool-native\.assembly-tool-managers \.assembly-board-managers\{height:auto;max-height:100%\}/,'native manager height is bounded by the root allocation rather than its modal default');
assert.match(toolWindowCss,/\.assembly-tool-native\.assembly-tool-managers \.layer-manager \.floating-heading\{display:none\}/,'native managers omit duplicate content headings beneath the OS title');
assert.match(toolWindowCss,/\.assembly-tool-native\.assembly-tool-managers \.assembly-board-managers\{grid-template-rows:auto auto minmax\(0,1fr\)\}/,'native manager tabs, board picker and content consume exactly three outer grid tracks');
assert.match(toolWindowCss,/:has\(\.assembly-connector-links\)\{grid-template-rows:auto minmax\(0,1fr\)\}/,'connector links consume the available native manager height without an empty picker track');
assert.match(toolWindowCss,/\.layer-manager\.embedded\{grid-template-rows:auto auto minmax\(0,1fr\)!important\}/,'hidden embedded layer heading leaves search, actions and one scrolling list track');
const managerPreview=readFileSync(new URL('./assembly-manager-preview.tsx',import.meta.url),'utf8');
assert.match(managerPreview,/assembly-tool-root assembly-tool-managers assembly-tool-native/,'preview exercises the native manager CSS boundary');
assert.match(managerPreview,/style=\{\{ width: 600, height: 720 \}\}/,'preview uses the compact native manager dimensions');
assert.match(managerPreview,/buttonStandard\.css/,'interactive manager preview imports shared control standards');
assert.equal(await api.focusAssemblyToolWindow('workspace'),true);
assert.deepEqual(nativeCalls,['restore','show','focus'],'a minimized native workspace is restored before focusing');
assert.ok(JSON.parse(readFileSync(new URL('../src-tauri/capabilities/main-window.json',import.meta.url),'utf8')).permissions.includes('core:window:allow-unminimize'));
assert.ok(JSON.parse(readFileSync(new URL('../src-tauri/capabilities/main-window.json',import.meta.url),'utf8')).permissions.includes('core:window:allow-get-all-windows'), 'WebviewWindow.getByLabel requires native window inventory permission');
await api.closeAssemblyToolWindow('workspace');delete window.__TAURI_INTERNALS__;

// Execute the actual parent entry points against window/state spies.
const appSource=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
assert.doesNotMatch(appSource,/<AssemblyWorkspace\b|<AssemblyBoardManagers\b/,'setup and scoped managers render only in their separate tool roots');
const appAst=ts.createSourceFile('App.tsx',appSource,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const helperNames=new Set(['openAssemblyWorkspace','openAssemblyPlacement','openBoardManager']),helpers=[];
function findHelpers(node){if(ts.isVariableDeclaration(node)&&helperNames.has(node.name.getText(appAst)))helpers.push(node.getText(appAst));ts.forEachChild(node,findHelpers);}
findHelpers(appAst);assert.equal(helpers.length,3);
let stateFlags={},focusedTools=[];
const assemblyState={assemblyIr:{boards:[{id:'A'},{id:'B'}]},assemblyDesigns:{}};
const entriesJs=ts.transpileModule(helpers.map(code=>'const '+code+';').join('\n'),{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
const entries=new Function('assemblyIr','assemblyDesigns','setAssemblyWorkspaceOpen','setAssemblyHandlingExpanded','setLayersOpen','setNetManagerOpen','setAssemblyLinksOpen','focusAssemblyTool',entriesJs+'return {openAssemblyWorkspace,openAssemblyPlacement,openBoardManager};')(
 assemblyState.assemblyIr,assemblyState.assemblyDesigns,
 value=>stateFlags.workspace=value,value=>stateFlags.placement=value,value=>stateFlags.layers=value,value=>stateFlags.nets=value,value=>stateFlags.links=value,kind=>focusedTools.push(kind));
entries.openAssemblyWorkspace();entries.openAssemblyWorkspace();entries.openAssemblyPlacement();entries.openBoardManager('links');entries.openBoardManager('layers');
assert.deepEqual(stateFlags,{workspace:true,placement:true,layers:true,nets:false,links:false},'switching managers retains one selected tab without closing the workspace');
assert.deepEqual(focusedTools,['workspace','workspace','placement','managers','managers']);

// Cancelling a browser close must not tell the main window that the tool closed.
const nativeRequire=createRequire(import.meta.url),effects=[],listeners=new Map(),childActions=[];let stateIndex=0;
window.addEventListener=(name,callback)=>listeners.set(name,callback);window.removeEventListener=name=>listeners.delete(name);
globalThis.document={documentElement:{dataset:{}}};
const rootReact={...React,useState(initial){return[stateIndex++===0?{...snapshot,visuals:{},diagnostics:{},overlayMessages:[]}:initial,()=>{}];},useRef:initial=>({current:initial}),useEffect:effect=>effects.push(effect)};
const rootSource=readFileSync(new URL('../src/AssemblyToolWindowRoot.tsx',import.meta.url),'utf8');
assert.match(rootSource, /nativeWindow=\{nativeWindow\}/, 'native assembly roots identify OS-decorated presentation');
assert.match(rootSource, /\{!nativeWindow && <header className="assembly-tool-heading">[\s\S]*?Close tool<\/button><\/header>\}/, 'native placement and manager windows rely on the OS title and close control');
const workspaceSource=readFileSync(new URL('../src/AssemblyWorkspace.tsx',import.meta.url),'utf8');
const managerSource=readFileSync(new URL('../src/AssemblyBoardManagers.tsx',import.meta.url),'utf8');
assert.match(workspaceSource, /!props\.nativeWindow && <button[^>]*aria-label="Close multi-board workspace"/, 'native assembly workspaces suppress the duplicate window close button');
assert.match(managerSource, /!nativeWindow && <button[^>]*aria-label="Close assembly board managers"/, 'native assembly managers suppress the duplicate window close button');
const rootJs=ts.transpileModule(rootSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const rootModule={exports:{}};
new Function('require','module','exports',rootJs)(name=>name==='react'?rootReact:name.endsWith('.css')?{}:name==='./assemblyToolWindows'?{connectAssemblyToolChild:async()=>({act:async action=>{childActions.push(action);},stop(){}}),onAssemblyToolCloseRequest:async()=>{throw Error('browser uses beforeunload');}}:name==='./appSettings'?{loadAppSettings:()=>({theme:'dark'}),APP_SETTINGS_STORAGE_KEY:'settings'}:name.startsWith('./Assembly')?{default:()=>null}:nativeRequire(name),rootModule,rootModule.exports);
const childRoot=rootModule.exports.default({kind:'workspace'});
const cleanups=effects.map(effect=>effect());await new Promise(resolve=>setImmediate(resolve));
function descendants(element){return React.isValidElement(element)?[element,...React.Children.toArray(element.props.children).flatMap(descendants)]:[];}
const workspaceChild=descendants(childRoot).find(element=>element.props.onDirtyChange);
workspaceChild.props.onOpenCollaboration('freecad');await new Promise(resolve=>setImmediate(resolve));
assert.ok(childActions.some(action=>action.type==='collaboration'&&action.mode==='freecad'),'workspace routes collaboration launch through the bounded child action channel');
workspaceChild.props.onDirtyChange(true);await new Promise(resolve=>setImmediate(resolve));
let closePrevented=false;const closeEvent={preventDefault(){closePrevented=true;},returnValue:null};
listeners.get('beforeunload')(closeEvent);
assert.equal(closePrevented,true);assert.equal(closeEvent.returnValue,'');
assert.ok(!childActions.some(action=>action.type==='closed'),'a cancelled close keeps the main session and draft alive');
listeners.get('pagehide')();await new Promise(resolve=>setImmediate(resolve));
assert.equal(childActions.at(-1).type,'closed','actual page exit notifies the parent');
cleanups.forEach(cleanup=>cleanup?.());
console.log('Assembly tool sessions, readiness, RPC, stale revisions, malformed actions, teardown and route checks passed');
