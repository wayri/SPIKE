// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { importTestTypescript } from './import-test-typescript.mjs';

const { appendHistorySnapshot, sharedHistoryDomains } = await importTestTypescript('projectHistory');
const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const sourceFile = ts.createSourceFile('App.tsx', appSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function initializer(name) {
  let found;
  const visit = node => { if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === name && node.initializer) found = node.initializer; if (!found) ts.forEachChild(node, visit); };
  visit(sourceFile); assert.ok(found, `App must declare ${name}`);
  const javascript = ts.transpileModule(`return (${found.getText(sourceFile)});`, { compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  return context => Function('context', `with (context) { ${javascript} }`)(context);
}

const designs = { contract:'spike/assembly-designs/v1', active_design_id:'design-0', future_owner_field:{retained:true}, designs:Array.from({length:20},(_,d)=>({contract:'spike/design-ir/v2',design_id:`design-${d}`,tracks:Array.from({length:1000},(_,row)=>({id:`${d}:${row}`,width_mm:.2,future:{exact:row}}))})) };
const packageShapes = {contract:'spike/assembly-package-shapes/v1',shapes:[{shape_id:'shape',future:{retained:true}}]};
const modelIndex = {contract:'spike/model-index/v1',models:[{id:'model',extensions:{future:42}}]};
const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
const initialAssembly={contract:'spike/assembly-ir/v1',assembly_id:'assembly',frame:{frame_id:'assembly',parent_frame_id:'',transform:identity},boards:Array.from({length:20},(_,i)=>({id:`board-${i}`,frame:{frame_id:`board-${i}-frame`,parent_frame_id:'assembly',transform:[...identity]}})),parts:[],future:{retained:true}};
const state={assemblyIr:initialAssembly,assemblyDesigns:designs,assemblyPackageShapes:packageShapes,modelIndex,assemblyEmWorkspace:null,engineeringReviewWorkspace:null,parallelWorkspace:{},emiChamberOpen:false,studies:[],probes:[],probeFormulaRows:[],probeReferenceIds:{},boardFile:'assembly.spike-design.json',frequency:'1e9',solverId:'auto',formulation:'auto',solverSelections:{},piSetup:{},piTopology:{},siTopology:{},selectedSiSuite:null,siChannelResult:null,spiceWorkspace:{},emiSetup:{},emiPreflight:null,emiScreening:null,emiFieldResult:null,thermalScenario:null,componentBonds:[],visibleLayers:{},assemblyLayerFocus:{},assemblyLayerVisibility:{},assemblyLayerOpacity:{},assemblyBoardVisibility:{},assemblyExplodedDistanceMm:0,layerOpacity:{},layerSeparation:0,showVias:true,showNetNames:true,showAxes:true,selected:null,selectionFilter:'all',isolatedNet:null,modelAssignments:{},assemblyModelAssignments:{},showModels:true,showSmdModels:true,showThtModels:true,navigationInertia:false,viewMode:'3D',resultVisualization:{},analysisResult:null,pdnReview:null,pdnReviewSourceId:null,boardData:null,boardSource:'',historyRef:{current:[]},redoRef:{current:[]},dirty:false,status:'',workspaceState:()=>({future_workspace:true}),restoreWorkspaceState:value=>{state.workspace=value;},defaultResultVisualization:()=>({}),emptyTopology:domain=>({domain}),normalizeStudies:value=>value,normalizePiSetup:value=>value,normalizeParallelWorkspace:value=>value,restoreEngineeringReviewWorkspace:value=>value,normalizeSpiceWorkspace:value=>value,normalizeEmiSetup:value=>value,normalizeEmiFieldResult:value=>value,markProjectDirty:()=>{state.dirty=true;}};
for(const name of ['Studies','Probes','ProbeFormulaRows','SavedProbeReferenceIds','EmiChamberOpen','BoardFile','Frequency','SolverId','Formulation','VisibleLayers','AssemblyLayerFocus','AssemblyLayerVisibility','AssemblyLayerOpacity','AssemblyBoardVisibility','AssemblyExplodedDistanceMm','SolverSelections','PiSetup','PiTopology','SiTopology','SelectedSiSuite','SiChannelResult','ParallelWorkspace','EngineeringReviewWorkspace','AssemblyEmWorkspace','AssemblyEmActiveScope','SpiceWorkspace','EmiSetup','EmiPreflight','EmiScreening','EmiFieldResult','ThermalScenario','ComponentBonds','AssemblyIr','AssemblyDesigns','AssemblyPackageShapes','ModelIndex','BondValidation','LayerOpacity','LayerSeparation','ShowVias','ShowNetNames','ShowAxes','NavigationInertia','Selected','SelectionFilter','IsolatedNet','ModelAssignments','AssemblyModelAssignments','ShowModels','ShowSmdModels','ShowThtModels','ViewMode','ResultVisualization','AnalysisResult','PdnReview','PdnReviewSourceId','Status']){const key=name==='SavedProbeReferenceIds'?'probeReferenceIds':name[0].toLowerCase()+name.slice(1);state[`set${name}`]=value=>{state[key]=typeof value==='function'?value(state[key]):value;};}
Object.assign(state,{structuredClone:globalThis.structuredClone,sharedHistoryDomains,appendHistorySnapshot});
state.boardImport={prepareComponents:async()=>{}};
const context=new Proxy(state,{has:()=>true,get:(target,key)=>key===Symbol.unscopables?undefined:key in target?target[key]:undefined});
const snapshot=initializer('snapshot')(context),restoreSnapshot=initializer('restoreSnapshot')(context);
Object.assign(state,{snapshot,restoreSnapshot});
const undo=initializer('undo')(context),redo=initializer('redo')(context);
assert.equal(typeof restoreSnapshot,'function');
for(let edit=0;edit<60;edit+=1){state.historyRef.current=appendHistorySnapshot(state.historyRef.current,snapshot());state.assemblyBoardVisibility={...state.assemblyBoardVisibility,[`board-${edit%20}`]:edit%2===0};}
assert.equal(state.historyRef.current.length,50);
for(const entry of state.historyRef.current){assert.equal(entry.assemblyDesigns,designs);assert.equal(entry.assemblyPackageShapes,packageShapes);assert.equal(entry.modelIndex,modelIndex);assert.equal(entry.assemblyIr,initialAssembly);}
assert.notEqual(state.historyRef.current[0].assemblyBoardVisibility,state.historyRef.current[1].assemblyBoardVisibility);
const retainedJsonBytes=Buffer.byteLength(JSON.stringify({designs,packageShapes,modelIndex}));
assert.equal(new Set(state.historyRef.current.flatMap(entry=>[entry.assemblyDesigns,entry.assemblyPackageShapes,entry.modelIndex])).size,3);
assert.ok(retainedJsonBytes>500000);
state.historyRef.current=[];state.redoRef.current=[];state.assemblyBoardVisibility={};state.historyRef.current=appendHistorySnapshot(state.historyRef.current,snapshot());
state.assemblyIr={...state.assemblyIr,boards:state.assemblyIr.boards.map((board,index)=>index===0?{...board,frame:{...board.frame,transform:[1,0,0,99,0,1,0,0,0,0,1,0,0,0,0,1]}}:board)};state.assemblyBoardVisibility={'board-0':false};const placedAssembly=state.assemblyIr;
assert.notEqual(placedAssembly,initialAssembly);assert.equal(placedAssembly.boards[1],initialAssembly.boards[1]);
undo();assert.equal(state.assemblyIr,initialAssembly);assert.deepEqual(state.assemblyBoardVisibility,{});assert.equal(state.redoRef.current[0].assemblyIr,placedAssembly);
redo();assert.equal(state.assemblyIr,placedAssembly);assert.deepEqual(state.assemblyBoardVisibility,{'board-0':false});assert.deepEqual(state.assemblyDesigns.future_owner_field,{retained:true});
assert.equal(sharedHistoryDomains({assemblyDesigns:designs}).assemblyDesigns,designs);
console.log(`Project history executed App snapshot/undo/redo with 50 states sharing ${retainedJsonBytes} retained JSON bytes`);
