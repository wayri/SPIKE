// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";
const geometry = readFileSync(new URL("../src/SParameterWorkbench.tsx", import.meta.url), "utf8");
const workflow = readFileSync(new URL("../src/SiWorkflowWorkbench.tsx", import.meta.url), "utf8");
const { siWorkflowPortIssues } = await importTestTypescript("siWorkflowAssignments");
const parse = geometry.slice(geometry.indexOf("const parseEyeMask ="), geometry.indexOf("const engineering ="));
const builder = geometry.slice(geometry.indexOf("  const prepareGeometryChannel ="), geometry.indexOf("  const runGeometryChannel ="));
const adapter = geometry.slice(geometry.indexOf("  const requestGeometryRun ="), geometry.indexOf('  return <div className="modal-backdrop"', geometry.indexOf("  const requestGeometryRun =")));
const defaults = { activeDesign: { design_id: "board-A" }, signalNet: "sig", referenceNet: "gnd", referenceLayer: "bottom", frequencyStartHz: "0", frequencyStopHz: "4e9", frequencyPoints: "1025", bitRateHz: "1e9", referenceImpedanceOhm: "50", victimNet: "", differentialMateNet: "", signaling: "single_ended", initialFocus: "channel", separationToleranceMm: "0.15", skewToleranceMm: "2", modulation: "NRZ", txFfeTaps: "1", rxDfeTaps: "0", ctleZeroHz: "0", ctlePoleHz: "0", voltageNoise: "0.01", loadedCrosstalk: false, crosstalkSourceV: "1", crosstalkTerminations: ["50","50","50","50"], eyeMaskJson: "", eyeMaskProfileId: "", eyeVoltageScale: "", eyeVoltageOffset: "", suite: null, desktop: true, siBusy: false };
function compile(source) { return ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText; }
function geometryFixture(overrides = {}) {
 const input = { ...defaults, ...overrides }, actions = [];
 const source = `function fixture(input, actions) { const {${Object.keys(defaults).join(",")}} = input; const record = value => value && typeof value === "object" && !Array.isArray(value) ? value : {}; ${parse} ${builder}
 const designRevision=JSON.stringify(activeDesign); const useGuidedRunAdapter=adapter=>adapter;
 const setSiError=()=>{}; const setWorkflowView=v=>actions.push(["view",v]), setSetupStep=v=>actions.push(["step",v]);
 const runGeometryChannel=async()=>actions.push(["worker"]); ${adapter} return {adapter:requestGeometryRun,prepare:prepareGeometryChannel}; }`;
 return { ...new Function(compile(source) + ";return fixture;")()(input, actions), actions };
}
const signal = new AbortController().signal;
let fixture = geometryFixture();
assert.equal((await fixture.adapter.check()).requirements.length, 0);
assert.equal(fixture.actions.length, 0, "readiness must never execute worker");
assert.equal(fixture.prepare().request.frequencies_hz.length, 1025);
for (const [override, route, pattern] of [
 [{activeDesign:null},"domain",/retained design/],
 [{signalNet:""},"ports",/signal net/],
 [{referenceNet:"sig"},"ports",/distinct/],
 [{signaling:"differential"},"ports",/P\/N mate/],
 [{frequencyStartHz:"1"},"conditions",/0 Hz/],
 [{frequencyPoints:"2"},"conditions",/3 through/],
 [{bitRateHz:"NaN"},"conditions",/positive and finite/],
 [{eyeMaskJson:"{"},"conditions",/JSON|property|position/],
 [{modulation:"PAM4",txFfeTaps:"invalid"},"conditions",/FFE/],
 [{victimNet:"victim",loadedCrosstalk:true,crosstalkTerminations:["0","50","50","50"]},"conditions",/termination/],
 [{eyeMaskProfileId:"profile"},"conditions",/scale and offset/],
]) {
 fixture=geometryFixture(override); const check=await fixture.adapter.check();
 assert.equal(check.requirements.length,1); assert.equal(check.requirements[0].route,route); assert.match(check.requirements[0].detail,pattern);
 fixture.adapter.fix(check.requirements[0]); assert.deepEqual(fixture.actions,[["view",false],["step",route]]);
 assert.throws(fixture.prepare,pattern,"actual Run and guide use the same request validation");
}
const semanticDesign = { design_id: "board-A", tracks: [{ id: "t", start: [0,0], end: [1,0] }] };
const stableRevision = geometryFixture({activeDesign:semanticDesign}).adapter.context.revision;
assert.equal(geometryFixture({activeDesign:structuredClone(semanticDesign)}).adapter.context.revision, stableRevision, "equal reconstructed source snapshots must not notify a new readiness revision");
assert.notEqual(geometryFixture({activeDesign:{...semanticDesign,tracks:[{...semanticDesign.tracks[0],end:[2,0]}]}}).adapter.context.revision, stableRevision, "routing edits invalidate readiness even with unchanged design ID");
assert.match(geometry,/useMemo\(\(\) => JSON\.stringify\(activeDesign\), \[activeDesign\]\)/);
assert.match(workflow,/useMemo\(\(\) => JSON\.stringify\(design\), \[design\]\)/);
fixture=geometryFixture(); await fixture.adapter.run({},signal); assert.deepEqual(fixture.actions,[["worker"]]);
const cancelled=new AbortController();cancelled.abort(); await fixture.adapter.run({},cancelled.signal);assert.equal(fixture.actions.length,1);
const loadedAdapter=workflow.slice(workflow.indexOf("  const requestWorkflowRun ="),workflow.indexOf("  const stop ="));
const loadedSource=`function fixture(setup,siWorkflowPortIssues,actions){const design={design_id:"a"},desktop=true,busy=false,designRevision=JSON.stringify(design); const useGuidedRunAdapter=a=>a,onReveal=()=>actions.push("reveal"),setError=()=>{},setStep=s=>actions.push(s),run=async()=>actions.push("worker");${loadedAdapter}return requestWorkflowRun;}`;
const loadedFactory=new Function(compile(loadedSource)+";return fixture;")();
const setup={channel:{kind:"rlgc",conductors:1},sources:[{port:0},{port:0}],receivers:[]};
assert(siWorkflowPortIssues(setup).length>0);
const actions=[];const loaded=loadedFactory(setup,siWorkflowPortIssues,actions);const check=await loaded.check();
assert(check.requirements.length>0);assert(check.requirements.every(row=>row.route==="endpoints"));assert.deepEqual(actions,[]);
loaded.fix(check.requirements[0]);assert.deepEqual(actions,["reveal","endpoints"]);
assert.match(geometry,/onClick=\{requestGeometryRun\}/);assert.match(workflow,/onClick=\{requestWorkflowRun\}/);
console.log("SI guided-run adapters: shared validation, repair routing, non-executing checks and cancellation passed");
