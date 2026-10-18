// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import ts from "typescript";
import {defaultShortcuts,eventShortcutKey} from "../src/shortcutCatalog.ts";
import {blocksViewportShortcut} from "../src/shortcutContext.ts";
import {importTestTypescript} from "./import-test-typescript.mjs";
const {viewportSmartContext}=await importTestTypescript("viewportSmartContext");
const text=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const source=ts.createSourceFile("App.tsx",text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let actionArrow,keyArrow;function walk(node){if(ts.isBinaryExpression(node)&&node.left.getText(source)==="viewportShortcutHandlerRef.current")actionArrow=node.right;if(ts.isVariableDeclaration(node)&&node.name.getText(source)==="onNavigationKey")keyArrow=node.initializer;ts.forEachChild(node,walk);}walk(source);assert(actionArrow&&keyArrow);
const calls=[];const board={nets:{"1":"VCC"},tracks:[{id:"trace",net:"VCC",start:[0,0],end:[3,4]}],pads:[],vias:[],components:[],zones:[],layers:["F.Cu","B.Cu"]};
const state={displayedResult:null,analysisResult:{time_series:{frames:[{time_s:0},{time_s:1},{time_s:2}]},provenance:{},scalar_fields:Object.fromEntries(["voltage_v","voltage_drop_v","current_a","current_density_a_mm2","power_loss_w","via_current_density_a_mm2","operating_point_impedance_ohm"].map(key=>[key,[]])),vector_fields:{electric_field:[],magnetic_field:[]},mesh:[]},selected:{id:"trace",type:"trace",name:"VCC",net:"VCC",layer:"F.Cu"},boardData:board,boardFile:"board",tab:"PI",analysisMode:"DC IR Drop",solverId:"auto",activeDesignId:"design",assemblyIr:null,viewMode:"3D",simulationDomain:"pi",resultVisualization:{animationFrame:0,animationPlaying:false,visible:true},activeWorkerOperation:null,shortcuts:{...defaultShortcuts},shortcutsOpen:false,modal:false,viewportShortcutHandlerRef:{current:null},viewportSmartContext,eventShortcutKey,blocksViewportShortcut,Math,String,Boolean,document:{querySelector:()=>state.modal?{}:null,querySelectorAll:()=>state.modal?[{closest:()=>null,getClientRects:()=>[{}],getAttribute:()=>"true"}]:[]},setResultVisualization:next=>{calls.push(["setResultVisualization"]);state.resultVisualization=typeof next==="function"?next(state.resultVisualization):next;},setShowModels:next=>{calls.push(["setShowModels"]);state.showModels=typeof next==="function"?next(state.showModels):next;},showModels:true};
const scope=new Proxy(state,{has:()=>true,get:(target,key)=>key===Symbol.unscopables?undefined:key in target?target[key]:key in globalThis?globalThis[key]:(...args)=>calls.push([key,...args])});
function compile(arrow){const code=ts.transpileModule(`const execute=${arrow.getText(source)};`,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None}}).outputText;return new Function("scope",`with(scope){${code};return execute;}`)(scope);}
state.viewportShortcutHandlerRef.current=compile(actionArrow);const dispatch=compile(keyArrow);
function key(key,patch={}){let prevented=false;dispatch({key,ctrlKey:false,metaKey:false,shiftKey:false,altKey:false,defaultPrevented:false,isComposing:false,repeat:false,target:null,preventDefault(){prevented=true;},...patch});return prevented;}
assert(key("z"));assert(calls.some(call=>call[0]==="commandCamera"&&call[1]==="view-top"));calls.length=0;
assert(key("Z",{shiftKey:true}));assert(calls.some(call=>call[1]==="view-bottom"));calls.length=0;
assert(key("F1"));assert(calls.some(call=>call[1]==="zoom-in-cursor"));calls.length=0;
assert(key(" ",{ctrlKey:true}));assert.equal(state.resultVisualization.animationPlaying,true);
state.resultVisualization.animationFrame=0;key("ArrowLeft",{ctrlKey:true});assert.equal(state.resultVisualization.animationFrame,0);
state.resultVisualization.animationFrame=2;key("ArrowRight",{ctrlKey:true});assert.equal(state.resultVisualization.animationFrame,2);
state.modal=true;calls.length=0;assert(!key("z"));assert.equal(calls.length,0);state.modal=false;
assert(!key("z",{target:{closest:selector=>selector.includes("input")?{}:null}}));assert.equal(calls.length,0);
assert(!key("z",{isComposing:true}));assert.equal(calls.length,0);
key("m",{repeat:true});assert.equal(calls.length,0,"held toggle keys cannot flicker models");
key("ArrowLeft",{repeat:true});assert(calls.some(call=>call[1]==="pan-left"));calls.length=0;
state.boardData=null;key("P",{ctrlKey:true,shiftKey:true});assert(calls.some(call=>call[0]==="setStatus"&&/Load/.test(call[1])));assert(!calls.some(call=>call[0]==="openAnalysisSetup"));
state.boardData=board;state.selected={...state.selected,net:"new-live-net"};board.nets["2"]="new-live-net";key("P",{ctrlKey:true,shiftKey:true});assert(calls.some(call=>call[0]==="selectNetForAnalysis"&&call[1]==="new-live-net"),"dispatch reads current workspace state rather than old effect closures");
console.log("Actual viewport shortcut handler: modifiers, camera commands, current state, frame bounds, repeat protection and editor/modal ownership passed.");
