// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {createRequire} from "node:module";
import {fileURLToPath} from "node:url";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import ts from "typescript";
const require=createRequire(import.meta.url);
function load(name,mocks={}) {
 const source=readFileSync(new URL(`../src/${name}`,import.meta.url),"utf8");
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const module={exports:{}};new Function("require","module","exports",code)(key=>key in mocks?mocks[key]:key.endsWith(".css")?{}:require(key),module,module.exports);return module.exports;
}
const model=load("kicadSchematicModel.ts");
const icons=new Proxy({},{get:()=>()=>null});
const Viewer=load("KicadSchematicViewer.tsx",{"./kicadSchematicModel":model,"./icons":icons}).default;
const python=fileURLToPath(new URL("../../.venv/Scripts/python.exe",import.meta.url));
const result=spawnSync(python,["-c",`import json,tempfile
from pathlib import Path
from tests.python.test_connectivity_view_importer import XML
from python.spike_core.service import handle
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)/'board.xml';p.write_text(XML,encoding='utf-8')
 print(json.dumps(handle({'method':'import_connectivity_view','params':{'path':str(p)}})))`],{cwd:fileURLToPath(new URL("../../",import.meta.url)),encoding:"utf8"});
assert.equal(result.status,0,result.stderr);const response=JSON.parse(result.stdout);assert.equal(response.ok,true);
const document=model.normalizeSchematicDocument(response.result);
const html=renderToStaticMarkup(React.createElement(Viewer,{snapshot:{document,linked:false,boardName:"",selected:{reference:"R1"},busy:false,status:""},act(){},nativeWindow:true}));
assert.match(html,/Generated connectivity diagram/);assert.match(html,/KiCad netlist/);assert.match(html,/ODB\+\+ archive/);assert.match(html,/ODB\+\+ folder/);
assert.match(html,/data:image\/svg\+xml/);assert.match(html,/aria-label="Select R1 10k"/);assert.match(html,/schematic-pick highlighted/);assert.doesNotMatch(html,/>Close<\/button>/);
assert.equal(model.boardNetForSchematic(document.nets[0],{pads:[{ref:"R1",name:"1",net:"board-VCC"},{ref:"C1",name:"1",net:"board-VCC"}]}),"board-VCC");
console.log("Real worker output passes frontend admission, renders a labelled selectable diagram, and maps explicit pins.");
