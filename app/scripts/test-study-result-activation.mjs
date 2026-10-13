// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
// Exercise the actual App activation handler with state boundaries replaced.
const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const start = source.indexOf("  const activateStudyCase = ");
const end = source.indexOf("  const addCaseToStudy = ", start);
assert.ok(start >= 0 && end > start);
const handler = source.slice(start, end);
const setters = [...new Set(handler.match(/\bset[A-Z]\w+/g))];
const bundle = { analysis_id: "saved-pi", mode: "pi", scalar_fields: { voltage_v: [1], voltage_drop_v: [] } };
function workspace(overrides = {}) {
  const state = {}, records = [], calls = [];
  const env = { boardFile: "fixture.kicad_pcb", activeDesignId: "fixture-design", universalRunning: false,
    recordChange: () => calls.push("change"), requestAnimationFrame: callback => callback(), commandCamera: command => calls.push(command),
    defaultResultVisualization: () => ({ mode: "geometry", visible: false }), normalizePiSetup: value => value,
    normalizeEmiSetup: value => value, normalizeEmiFieldResult: value => value, studyEMergeSetup: value => value,
    validateSiProtocolSuite: () => [], normalizeSolverResult: value => value === bundle ? bundle : null,
    isSupportedSavedResult: value => value === bundle, boundedResultRecords: value => value,
    resultRecord: value => ({ id: value.analysis_id, bundle: value }), emergeRadiationPatterns: () => [],
    openSiWorkbench: (...args) => calls.push(["si-viewer", ...args]), locateStudyResult: () => calls.push("locate"),
    availableEMQuantities: () => [], emViewportPayload: value => value,
    ...Object.fromEntries(setters.map(name => [name, value => { state[name] = typeof value === "function" ? value(name === "setResultRecords" ? records : {}) : value; }])), ...overrides };
  const compiled = ts.transpileModule(handler + "\nreturn activateStudyCase;", { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  return { state, calls, activate: new Function(...Object.keys(env), compiled)(...Object.values(env)) };
}
const item = { id: "case", name: "Saved case", type: "pi", mode: "DC IR Drop", settings: { boardFile: "fixture.kicad_pcb", designId: "fixture-design", piSetup: { net: "VCC" } }, scenario: {}, runs: [], datasetIds: [] };
{
 const w=workspace(); w.activate("study", {...item,resultSnapshot:bundle});
 assert.equal(w.state.setResultDisplay,"saved-pi"); assert.equal(w.state.setResultVisualization.mode,"voltage");
 assert.equal(w.state.setResultVisualizerOpen,true); assert.equal(w.state.setTab,"PI");
 assert.equal(w.state.setThermalPreview,null); assert.equal(w.state.setSelected,null); assert.equal(w.state.setIsolatedNet,null);
 assert.deepEqual(w.calls,["change","fit"]); assert.match(w.state.setStatus,/no solver was run/);
 assert.equal(w.state.setResultRecords[0].bundle,bundle);
}
{
 const w=workspace(); w.activate("study",{...item,type:"thermal",settings:{scenario:{ambient_c:25}},scenario:{name:"Hot case"},resultSnapshot:{board_thermal_result:{contract:"saved-test",temperature_c:42}}});
 assert.equal(w.state.setTab,"Thermal"); assert.equal(w.state.setThermalVisibility.field,true); assert.equal(w.state.setThermalVisibility.volume,false);
 assert.equal(w.state.setThermalScenario.ambient_c,25); assert.equal(w.state.setThermalScenario.name,"Hot case"); assert.equal(w.state.setThermalScenario.board_thermal_result.temperature_c,42);
 assert.equal(w.state.setThermalPreview,null); assert.ok(w.calls.includes("fit"));
}
{
 const w=workspace(); const result={contract:"spike/si-channel-result/v1",status:"completed"}; w.activate("study",{...item,type:"si",resultSnapshot:result});
 assert.equal(w.state.setSiChannelResult,result); assert.equal(w.state.setTab,"HF / SI"); assert.deepEqual(w.calls.find(Array.isArray),["si-viewer","geometry","channel",true]);
}
{
 const w=workspace(); w.activate("study",{...item,resultRef:"external.json"}); assert.ok(w.calls.includes("locate")); assert.equal(w.state.setResultDisplay,"none");
}
for(const candidate of [{...item,settings:{boardFile:"other.kicad_pcb"}},{...item,settings:{designId:"other"}},{...item,type:"unsupported"}]) {
 const w=workspace(); w.activate("study",candidate); assert.deepEqual(w.calls,[]); assert.equal(w.state.setSelected,undefined); assert.ok(w.state.setStatus);
}
{const w=workspace({universalRunning:true});w.activate("study",item);assert.deepEqual(w.calls,[]);assert.match(w.state.setStatus,/Stop/);}
console.log("Study result activation: domain viewers, retained overlays, fit/reset, missing-file recovery and incompatible/busy guards passed.");
