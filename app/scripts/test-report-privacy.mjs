// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import ts from "typescript";
import {importTestTypescript} from "./import-test-typescript.mjs";
const privacy = await importTestTypescript("reportPrivacy");
const {createDiagnosticReport, reportWithNotes, formatDiagnosticReport, redactReportText} = privacy;
const error = new TypeError("SecretClient board failed for Alice alice@example.com C:\\Users\\Alice\\SecretClient.kicad_pcb token=privatekey");
error.code = "ENOENT";
error.stack = `${error.message}\n at SecretClient (file:///C:/Users/Alice/private/App.tsx?secret=TOKEN#fragment:42:9)\n at Alice (/home/alice/secret.ts:60:11)`;
const report = createDiagnosticReport(error, "\n at SecretClient\n at Alice");
assert.equal(report.error_class, "TypeError");
assert.equal(report.error_code, "ENOENT");
assert.deepEqual(report.frames, ["[source location removed]:42:9", "[source location removed]:60:11"]);
assert.equal(report.component_depth, 2);
const changed = new TypeError("other project"); changed.code="ENOENT"; changed.stack="other project\n at Bob (https://private.example/source.ts?key=OTHER#hash:42:9)\n at Bob (/Users/bob/private.ts:60:11)";
assert.equal(createDiagnosticReport(changed).report_id, report.report_id, "Grouping never hashes raw identity or project content");
changed.stack += "\n at source:61:11";
assert.notEqual(createDiagnosticReport(changed).report_id, report.report_id);
const attacks = [
  "C:\\Users\\Alice\\SecretClient\\board.kicad_pcb", "\\\\private-host\\Alice\\board.step", "/home/alice/secret/project", "/custom/Alice/secret", "/secret",
  "file:///Users/Alice/secret", "https://alice:password@private.example/project?token=privatekey#secret", "alice@example.com",
  "Bearer privatekey", "api_key=privatekey", "project='SecretClient'", 'board="SecretClient"', "username=Alice", "ghp_privatekey", "sk-privatekey", "eyJprivate.eyJsecret.signature", "SecretClient.kicad_pcb", "2026-10-18T12:34:56.000Z",
];
for (const attack of attacks) {
  const notes = redactReportText(attack);
  assert.doesNotMatch(notes, /Alice|alice|privatekey|private-host|SecretClient|private\.example|2026-10-18|eyJprivate|\/secret/, attack);
}
for (const format of ["json", "markdown"]) {
  const output = formatDiagnosticReport(reportWithNotes(report, attacks.join("\n")), format);
  assert.doesNotMatch(output, /Alice|alice|SecretClient|privatekey|private-host|private\.example|TOKEN|fragment|2026-10-18/);
  assert.match(output, /redaction_version/);
  assert.doesNotMatch(output, /generated_at|user_agent|location"/);
}
assert.equal(createDiagnosticReport(Object.assign(new Error("private"), {name:"Alice", code:"SECRET"})).error_class, "Error");
assert.equal(createDiagnosticReport(Object.assign(new Error("private"), {code:"SECRET"})).error_code, "");
assert.equal(redactReportText("a".repeat(15000)).length, 12000);

// Exercise actual component handlers with a minimal hook host. No browser, storage,
// clipboard or filesystem access is needed until an explicit export action.
let cursor=0; const state=[];
const react={useMemo:factory=>factory(), useState:initial=>{const index=cursor++;if(!(index in state))state[index]=initial;return [state[index],value=>{state[index]=value;}];},useRef:initial=>{const index=cursor++;if(!(index in state))state[index]={current:initial};return state[index];}};
let opened=0;
const nativeSaves=[];
let nativeSave=async()=>"C:\\Users\\Alice\\private-report.json";
const bridge={saveNativeTextFile:async(...args)=>{nativeSaves.push(args);return nativeSave();}};
const require=createRequire(import.meta.url), module={exports:{}};
const source=ts.transpileModule(readFileSync(new URL("../src/SupportReportPreview.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function("require","module","exports",source)(name=>name==="react"?react:name==="./reportPrivacy"?privacy:name==="./workerBridge"?bridge:name==="./bugReport"?{openBugReport:async()=>{opened++;}}:name.endsWith(".css")?{}:require(name),module,module.exports);
const render=()=>{cursor=0;return module.exports.default({error});};
const nodes=tree=>!tree||typeof tree!=="object"?[]:[tree,...[tree.props?.children].flat(Infinity).flatMap(nodes)];
const text=tree=>typeof tree==="string"?tree:!tree||typeof tree!=="object"?"":[tree.props?.children].flat(Infinity).map(text).join("");
const click=label=>nodes(render()).find(row=>row.type==="button"&&text(row)===label).props.onClick();
let tree=render(); assert.equal(opened,0); assert.match(text(tree),/Nothing is uploaded automatically/);
const noteInput=nodes(tree).find(row=>row.type==="textarea"&&!row.props.readOnly);
noteInput.props.onChange({target:{value:"alice@example.com"}});
assert.doesNotMatch(nodes(render()).find(row=>row.type==="textarea"&&row.props.readOnly).props.value,/alice/);
Object.defineProperty(globalThis,"navigator",{configurable:true,value:{clipboard:{writeText:async()=>{throw Error("private failure");}}}});
await click("Copy report"); assert.match(text(render()),/Copy failed/); assert.doesNotMatch(text(render()),/private failure/);
let copied=""; navigator.clipboard.writeText=async value=>{copied=value;};
await click("Copy report"); assert.match(text(render()),/Reviewed report copied/);assert.doesNotMatch(copied,/Alice|alice|SecretClient/);
await click("Save report");assert.match(text(render()),/Save failed/);
let downloadedBlob, downloadedName="", clicked=0, removed=0;
const originalCreate=URL.createObjectURL, originalRevoke=URL.revokeObjectURL;
URL.createObjectURL=blob=>{downloadedBlob=blob;return "blob:local-report";};
URL.revokeObjectURL=()=>{};
globalThis.document={body:{appendChild:()=>{}},createElement:()=>({set download(value){downloadedName=value;},click(){clicked++;},remove(){removed++;}})};
await click("Save report");assert.equal(clicked,1);assert.equal(removed,1);assert.match(downloadedName,/^SPIKE-[a-f0-9]{8}\.json$/);
assert.equal(await downloadedBlob.text(),nodes(render()).find(row=>row.type==="textarea"&&row.props.readOnly).props.value);
assert.match(text(render()),/download requested/);
delete globalThis.document;URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;

// Desktop export must use the host Save As boundary, never browser downloads.
globalThis.window={__TAURI_INTERNALS__:{}};
const nativeExpected=nodes(render()).find(row=>row.type==="textarea"&&row.props.readOnly).props.value;
await click("Save report");
assert.deepEqual(nativeSaves.at(-1),[downloadedName,nativeExpected,"support-report"]);
assert.match(text(render()),/Reviewed report saved/);assert.doesNotMatch(text(render()),/Alice|private-report/);
nodes(render()).find(row=>row.type==="select").props.onChange({target:{value:"markdown"}});
await click("Save report");
assert.match(nativeSaves.at(-1)[0],/^SPIKE-[a-f0-9]{8}\.md$/);
assert.equal(nativeSaves.at(-1)[1],nodes(render()).find(row=>row.type==="textarea"&&row.props.readOnly).props.value);
assert.match(nativeSaves.at(-1)[1],/^# SPIKE support report/);
nativeSave=async()=>null;await click("Save report");assert.match(text(render()),/save canceled/);assert.doesNotMatch(text(render()),/Save failed/);
nativeSave=async()=>{throw Error("C:\\Users\\Alice\\secret denied");};await click("Save report");assert.match(text(render()),/Save failed/);assert.doesNotMatch(text(render()),/Alice|secret denied/);
let releaseSave;
nativeSave=()=>new Promise(resolve=>{releaseSave=resolve;});
const saveAction=nodes(render()).find(row=>row.type==="button"&&text(row)==="Save report").props.onClick;
const pending=saveAction();await saveAction();await new Promise(resolve=>setImmediate(resolve));
assert.equal(nativeSaves.length,5,"A pending native save admits only one host request");
tree=render();assert.ok(nodes(tree).find(row=>row.type==="select").props.disabled);
assert.ok(nodes(tree).filter(row=>row.type==="button").every(row=>row.props.disabled));
assert.ok(nodes(tree).find(row=>row.type==="textarea"&&!row.props.readOnly).props.disabled);
assert.match(text(tree),/Saving report/);
releaseSave("C:\\Users\\Alice\\report.json");await pending;
assert.match(text(render()),/Reviewed report saved/);
assert.equal(nodes(render()).find(row=>row.type==="select").props.disabled,false);
assert.equal(clicked,1,"Native saves never request a browser download");
delete globalThis.window;
click("Clear notes");assert.equal(nodes(render()).find(row=>row.type==="textarea"&&!row.props.readOnly).props.value, "");
await click("Open issue form"); assert.equal(opened,1);
delete globalThis.navigator;
console.log("Support reports: privacy adversaries, stable public grouping, exact preview, explicit copy/save failures and issue handoff passed.");
