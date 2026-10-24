// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import ts from "typescript";
import vm from "node:vm";
import {importTestTypescript} from "./import-test-typescript.mjs";
const {solverSuiteCatalog}=await importTestTypescript("solverSuiteCatalog");
const {PYTHON_TEMPLATES}=await importTestTypescript("pythonWorkspaceTemplates");
const templates=new Map(PYTHON_TEMPLATES.map(item=>[item.id,item]));
for(const capability of solverSuiteCatalog){if(capability.action==="python")assert.ok(templates.has(capability.templateId),`${capability.id}: missing precise template destination`);if(capability.sourceOnly)assert.equal(capability.action,undefined);}
const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const fragment=app.slice(app.indexOf("  const openSuiteWorkflow ="),app.indexOf("  const setInterfaceMode="));
assert.ok(fragment.length>500);
let events=[],draft,status="";const generation={current:1};
const scope={exports:{},solverSuiteCatalog,projectGeneration:generation,crypto:{randomUUID:()=>"test"},require:()=>({PYTHON_TEMPLATES}),setStatus:value=>status=value,setContextScriptDraft:value=>draft=value,setSolverSuiteOpen:value=>events.push(["manager",value]),setPythonOpen:value=>events.push(["python",value]),setPropulsionPodOpen:value=>events.push(["pod",value]),setTab:value=>events.push(["tab",value]),openSiWorkbench:view=>events.push(["si",view]),setPdnSuiteOpen:value=>events.push(["pdn",value]),setSparameterOpen:value=>events.push(["sparameter",value]),setSiProtocolSuitesOpen:value=>events.push(["eye",value]),openAnalysisSetup:value=>events.push(["analysis",value]),setExtensionSelectedId:value=>events.push(["extension",value]),openExtensionManager:async value=>events.push(["extension-manager",value]),setSpiceOpen:value=>events.push(["spice",value]),setNativeCfdOpen:value=>events.push(["cfd",value]),openExternalEngineCenter:async()=>events.push(["engines"]),setThermalOpen:value=>events.push(["thermal",value]),setEmiSection:value=>events.push(["em",value]),setRightOpen(){},setFocusTool(){}};
vm.runInNewContext(ts.transpileModule(fragment+"\nexports.open=openSuiteWorkflow;",{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scope);
for(const entry of solverSuiteCatalog.filter(item=>item.action)){
 events=[];draft=undefined;await scope.exports.open(entry.action,entry.extensionId,entry.id);
 if(entry.templateId){assert.equal(draft.code,templates.get(entry.templateId).code);assert.equal(draft.name,`${entry.templateId}.py`);assert.ok(events.some(item=>item[0]==="python"));}
 else if(entry.action==="propulsion-pod")assert.ok(events.some(item=>item[0]==="pod"));
 else if(entry.action==="si-multiport")assert.ok(events.some(item=>item[0]==="si"&&item[1]==="multiport"));
 else assert.ok(events.length>1,`${entry.id} opens an actual workflow`);
}
events=[];await scope.exports.open("python",undefined,"pi-board-volume-dc");assert.equal(events.length,0);assert.match(status,/no admitted setup route/);
const entry=solverSuiteCatalog.find(item=>item.templateId);scope.require=()=>({PYTHON_TEMPLATES:[]});events=[];await scope.exports.open(entry.action,undefined,entry.id);assert.equal(events.length,0);assert.match(status,/Missing setup template/);
let release;scope.require=()=>({PYTHON_TEMPLATES});events=[];const late=scope.exports.open(entry.action,undefined,entry.id);generation.current++;await late;assert.equal(events.length,0,"Late template load cannot open into a different project");
const panel=readFileSync(new URL("../src/SolverSuitePanel.tsx",import.meta.url),"utf8");assert.ok(panel.includes('initialView = "capabilities"'),"Solver search opens actual capability routes rather than dependency preview");
assert.ok(app.includes('const selectedExtension = selectedId ? extensions.find'));
console.log(`Solver navigation: ${solverSuiteCatalog.length} capability destinations, exact staged scripts, source-only/missing-template blocks and project-switch safety passed.`);
