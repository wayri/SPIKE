// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const require=createRequire(import.meta.url),root=resolve(import.meta.dirname,"../src"),cache=new Map();
function load(name){
 if(name.endsWith(".css"))return {};
 if(name==="./icons")return {CircuitBoard:()=>null,Plus:()=>null,Trash2:()=>null};
 if(!name.startsWith("./"))return require(name);
 if(cache.has(name))return cache.get(name);
 const file=resolve(root,name.slice(2)+(name.includes("Panel")?".tsx":".ts"));
 const code=ts.transpileModule(readFileSync(file,"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const module={exports:{}};new Function("require","module","exports",code)(load,module,module.exports);cache.set(name,module.exports);return module.exports;
}
const {suggestPiSetupIntents:suggest}=load("./piSearchIntent"),{default:Panel}=load("./PiSearchSetupPanel");
const part=ref=>({id:ref,ref,value:"fixture",at:[1,1],layer:"F.Cu"});
const pad=(ref,name,net)=>({id:ref+":"+name,ref,name,net,at:[1,1],layer:"F.Cu",layers:["F.Cu"]});
const board={components:[part("C10"),part("U21"),part("J1")],nets:{1:"netx",2:"GND"},pads:[pad("C10","1","netx"),pad("C10","2","GND"),pad("U21","1","netx"),pad("U21","2","netx"),pad("U21","3","GND"),pad("J1","1","netx")]};
function render(query,staleReason=""){return renderToStaticMarkup(React.createElement(Panel,{board,suggestion:suggest(query,board)[0],staleReason,onApply(){throw Error("SSR must not mutate workspace")},onClose(){},canRun:true}));}
let html=render("on board run PI on netx from C10 to U21");
for(const text of ["Missing:","Vsup","Isup","Isink allocation", "Choose return treatment","Unlimited ideal source","Run PI","Review in PI setup"])assert.ok(html.includes(text),text);
assert.ok(!html.includes("U21:3"),"Ground pin must not be offered as rail load");
html=render("run PI on netx from C10 to U21 Vsup=3.3V Isup=1A Isink=250mA");
assert.match(html,/value="3.3"/);assert.match(html,/value="0.25"/);assert.match(html,/0.125000/);assert.match(html,/disabled=""[^>]*>Run PI/);
html=render("run PI on netx from C10 to U21 and UNKNOWN");assert.ok(html.includes("PI sink 2 component"),"Unknown sink may not disappear from the setup");
html=render("run PI from C10 and J1 to U21");assert.ok(html.includes("Additional source 2"));
html=render("run PI on netx from C10 to U21","Board changed");assert.match(html,/role="alert">Board changed/);
console.log("PI setup review: missing electrical fields, source/sink identity, pin preview, multi-source and stale-board states passed.");
