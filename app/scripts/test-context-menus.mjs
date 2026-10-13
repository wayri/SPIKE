// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

async function module(name) {
  const source = readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
}
const context = await module("contextScript"), trigger = await module("contextMenuTrigger"), table = await module("tableContext");
const dangerous = "RF α '); __import__('os').system('unwanted') #\\\n<script>";
const payload = Object.freeze({ id: dangerous, net: "RF/PORT1", board_instance_id: "board-2", value: 1.23456789012345, units: "V/m" });
const draft = context.contextScript({ kind: "selection", title: dangerous, payload }, "ticket-1");
assert.equal(draft.id, "ticket-1"); assert.ok(draft.name.endsWith(".py")); assert.equal(context.admitContextScript(draft)?.code, draft.code);
assert.equal(context.admitContextScript({ id: "a", name: "unsafe.txt", code: "" }), null);
assert.throws(() => context.contextScript({ kind: "selection", title: "large", payload: "a".repeat(context.MAX_CONTEXT_BYTES) }, "id"), /no samples were truncated/);
const python = process.platform === "win32" ? new URL("../../.venv/Scripts/python.exe", import.meta.url) : new URL("../../.venv/bin/python", import.meta.url);
const checked = spawnSync(fileURLToPath(python), ["-X", "utf8", "-c", "import sys,json,contextlib,io\nfrom types import SimpleNamespace\nsink=io.StringIO()\nwith contextlib.redirect_stdout(sink): exec(compile(sys.stdin.read(), '<context-draft>', 'exec'), {'spike':SimpleNamespace(design=None,results=None)})\nprint(sink.getvalue())"], { input: draft.code, encoding: "utf8" });
assert.equal(checked.status, 0, checked.stderr); assert.deepEqual(JSON.parse(checked.stdout), { kind: "selection", title: dangerous, payload });
const trace = Object.freeze({ type: "scatter", name: "S11", x: Object.freeze([1e9, 2e9]), y: Object.freeze([-10, null]) });
const snapshot = context.plotScriptContext([trace], { xaxis: { title: "Frequency [Hz]" }, yaxis: { title: "S11 [dB]" } }, "result-3");
const comparison = context.plotScriptContext([trace, {...trace, name:"same label"}], {}, "result-3", 1);
assert.deepEqual(comparison.traces.map(item => item.origin), ["source", "pasted view comparison"]);
assert.deepEqual(snapshot.traces[0].x, [1e9, 2e9]); assert.equal(snapshot.traces[0].y[1], null); assert.equal(snapshot.axes.xaxis.title, "Frequency [Hz]");
assert.deepEqual(context.plotScriptContext([{ type:"scatter", x:new Float64Array([0,1]),y:[NaN,Infinity] }], {}, "r").traces[0].y, [null,null]);
assert.throws(() => context.plotScriptContext([{ x: new Array(30001).fill(1) }], {}, "r"), /no samples were truncated/);
let opened = 0, prevented = 0, stopped = 0;
const handlers = trigger.contextMenuTrigger((x,y) => { opened++; assert.deepEqual([x,y], [20,40]); });
const event = { key:"F10", shiftKey:true, preventDefault(){prevented++;},stopPropagation(){stopped++;},currentTarget:{getBoundingClientRect(){return {left:20,bottom:40};}} };
handlers.onKeyDown(event); handlers.onKeyDown({...event,key:"Enter"}); handlers.onContextMenu({...event,clientX:20,clientY:40});
assert.deepEqual([opened,prevented,stopped],[2,2,2]);
globalThis.HTMLInputElement = class { constructor(value,type="text",checked=false){Object.assign(this,{value,type,checked});} };
const cell = (text,field=null) => ({textContent:text,querySelector(){return field;}});
const row = {cells:[cell("display rounded"),cell("old",new HTMLInputElement("1.23456789")),cell("",new HTMLInputElement("","checkbox",false))]};
const fakeTable = {querySelectorAll(selector){return selector === "thead th" ? [cell("Name"),cell("Field [mm]"),cell("Enabled")] : [row];}};
const rowData = table.displayedTableContext(fakeTable,row,"Geometry","row",2,500);
assert.deepEqual(rowData.rows,[["display rounded","1.23456789","false"]]); assert.equal(rowData.page,3); assert.equal(rowData.columns[1],"Field [mm]");
assert.throws(() => table.displayedTableContext({querySelectorAll(){return new Array(501).fill(row);}},null,"Large","page",0,501), /no rows were truncated/);
console.log("Context drafts preserve source values/units, reject oversized snapshots, safely encode user text, and support keyboard/table context actions.");
