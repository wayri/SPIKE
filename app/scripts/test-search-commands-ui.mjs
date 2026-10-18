// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import * as model from "../src/universalSearchModel.ts";
import * as searchPreferences from "../src/searchPreferences.ts";
import { suggestSearchCommands } from "../src/searchSentences.ts";
const states = [], refs = [], effects = [];
let index = 0, pending = [], executed = [], closed = 0, blocked = false;
const same = (a,b) => a && b && a.length === b.length && a.every((x,i) => Object.is(x,b[i]));
const react = {
 useState(initial) { const i=index++; if (!(i in states)) states[i]=typeof initial==="function"?initial():initial; return [states[i],value => {states[i]=typeof value==="function"?value(states[i]):value;}]; },
 useRef(initial) { const i=index++; return refs[i]??={current:initial}; },
 useMemo(fn) { index++; return fn(); },
 useEffect(fn,deps) { const i=index++; if (!same(effects[i]?.deps,deps)) pending.push(()=>{effects[i]?.cleanup?.();effects[i]={deps,cleanup:fn()};}); },
};
const jsx = { Fragment: Symbol("Fragment"), jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}) };
const compiled=ts.transpileModule(readFileSync(new URL("../src/UniversalSearch.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const module={exports:{}};
new Function("require","module","exports",compiled)(name=>name==="react"?react:name==="react/jsx-runtime"?jsx:name.endsWith(".css")?{}:name==="./icons"?{ArrowRight:()=>null,Search:()=>null,X:()=>null,SlidersHorizontal:()=>null,MousePointer2:()=>null}:name==="./liveControlSearch"?{liveControlSearch:()=>[]}:name==="./universalSearchModel"?model:name==="./searchPreferences"?searchPreferences:name==="./focusCommands"?{searchableFocusCommands:commands=>commands.flatMap(command=>command.run?[{...command,id:`command:${command.id}`,category:"Command",keywords:"",disabled:Boolean(command.disabled)}]:[])}:(()=>{throw new Error(name);})(),module,module.exports);
const targets=[{id:"canonical-A1",name:"netK-A1",kind:"net"},{id:"canonical-A10",name:"netK-A10",kind:"net"}];
const props={open:true,items:[{id:"settings",label:"Application settings",category:"Settings",run:()=>executed.push("settings")}],commands:[{id:"shortcut",label:"Export report",shortcut:"Ctrl+E",run:()=>executed.push("report")}],onClose:()=>closed++,suggestCommands:query=>suggestSearchCommands(query,targets).map(row=>({...row,category:"Command",disabled:blocked,run:()=>executed.push(row.target)}))};
const render=()=>{index=0;pending=[];const tree=module.exports.default(props);pending.forEach(fn=>fn());return tree;};
const find=(tree,predicate)=>{if(!tree||typeof tree!=="object")return null;if(Array.isArray(tree)){for(const child of tree){const hit=find(child,predicate);if(hit)return hit;}return null;}if(predicate(tree))return tree;return find(tree.props?.children,predicate);};
const findAll=(tree,predicate,found=[])=>{if(!tree||typeof tree!=="object")return found;if(Array.isArray(tree)){tree.forEach(child=>findAll(child,predicate,found));return found;}if(predicate(tree))found.push(tree);findAll(tree.props?.children,predicate,found);return found;};
const text=tree=>tree==null?"":typeof tree==="string"?tree:Array.isArray(tree)?tree.map(text).join(" "):text(tree.props?.children);
const input=tree=>find(tree,node=>node.type==="input");
const key=(tree,value)=>input(tree).props.onKeyDown({key:value,preventDefault(){}});
const originalAnimation=globalThis.requestAnimationFrame;
const originalStorage=globalThis.localStorage;
const saved=new Map();
globalThis.localStorage={getItem:key=>saved.get(key)??null,setItem:(key,value)=>saved.set(key,value)};
globalThis.requestAnimationFrame=fn=>{fn();return 0;};
try {
 let tree=render();tree=render();
 assert.ok(find(tree,node=>node.props?.["aria-label"]==="Pin Application settings"),"empty search retains the ordinary action inventory");
 input(tree).props.onChange({target:{value:"run PI on net netK-A"}});tree=render();
 assert.equal(executed.length,0,"Typing never launches a simulation");
 key(tree,"Tab");tree=render();
 assert.equal(input(tree).props.value,'Run PI on net "netK-A1"');
 assert.equal(executed.length,0,"Completion never launches a simulation");
 key(tree,"Enter");assert.deepEqual(executed,["canonical-A1"]);assert.equal(closed,1);
 input(tree).props.onChange({target:{value:"run PI on net netK-A"}});tree=render();key(tree,"ArrowDown");tree=render();key(tree,"Enter");assert.equal(executed.at(-1),"canonical-A10");
 blocked=true;tree=render();key(tree,"Enter");assert.equal(executed.length,2,"Disabled command cannot execute with Enter");
 input(tree).props.onChange({target:{value:"run PI on net nonexistent"}});tree=render();key(tree,"Enter");assert.equal(executed.length,2,"Missing target cannot reuse stale active result");
 blocked=false;input(tree).props.onChange({target:{value:"please open settings"}});tree=render();key(tree,"Enter");assert.equal(executed.at(-1),"settings");
 input(tree).props.onChange({target:{value:"export report"}});tree=render();key(tree,"Enter");assert.equal(executed.at(-1),"report","live command inventory participates in universal search");
 key(tree,"Escape");assert.equal(closed,5);
 let finishPending;
 props.items.push({id:"pending",label:"Pending fixture",category:"Test",run:()=>{executed.push("pending");return new Promise(resolve=>{finishPending=resolve;});}});
 input(tree).props.onChange({target:{value:"Pending fixture"}});tree=render();key(tree,"Enter");key(tree,"Enter");
 assert.equal(executed.filter(value=>value==="pending").length,1,"repeated Enter cannot launch the same asynchronous action twice");
 tree=render();assert.equal(find(tree,node=>node.props?.role==="option").props.disabled,true,"an in-flight result is visibly disabled");
 finishPending();await new Promise(resolve=>setImmediate(resolve));tree=render();
 props.items.push({id:"failing",label:"Failure fixture",category:"Test",run:()=>Promise.reject(new Error("Control changed; refresh search"))});
 input(tree).props.onChange({target:{value:"Failure fixture"}});tree=render();key(tree,"Enter");
 await new Promise(resolve=>setImmediate(resolve));tree=render();
 assert.equal(closed,6,"A failed action keeps search open for recovery");
 assert.match(find(tree,node=>node.props?.role==="alert").props.children,/Control changed/);
 const pin=find(tree,node=>node.props?.["aria-label"]==="Pin Failure fixture");
 pin.props.onClick();tree=render();
 assert.equal(find(tree,node=>node.props?.["aria-label"]==="Unpin Failure fixture").props["aria-pressed"],true,"pinning remains available without executing the action");
 input(tree).props.onChange({target:{value:""}});tree=render();
 assert.match(text(findAll(tree,node=>node.props?.role==="option")[0]),/Failure fixture/,"a pin stays discoverable at the start of empty search");
 const summary=find(tree,node=>node.props?.["aria-label"]==="Recent and most used search actions");
 assert.ok(summary,"empty search exposes compact learned-action shortcuts");
 assert.ok(findAll(summary,node=>node.type==="button"&&node.props?.title).length<=5,"only five learned shortcuts are visible at once");
 find(summary,node=>node.type==="button"&&text(node)==="Most used").props.onClick();tree=render();
 assert.ok(findAll(find(tree,node=>node.props?.["aria-label"]==="Recent and most used search actions"),node=>node.type==="button"&&node.props?.title).length<=5,"Most used mode also remains capped at five shortcuts");
 assert.ok(saved.has(searchPreferences.SEARCH_PREFERENCES_KEY),"preferences persist only local action IDs and bounded usage metadata");
 assert.doesNotMatch(saved.get(searchPreferences.SEARCH_PREFERENCES_KEY),/please open|Failure fixture|run PI/,"stored preferences never contain query or label text");
 console.log("Search keyboard completion, explicit execution, disabled and stale-result checks passed.");
} finally {globalThis.requestAnimationFrame=originalAnimation;globalThis.localStorage=originalStorage;effects.forEach(effect=>effect?.cleanup?.());}

const invalid=searchPreferences.parseSearchPreferences('{"version":1,"pins":[7],"usage":{"x":{"count":-1,"lastUsed":"today"}}}');
assert.deepEqual(invalid,{version:1,pins:[],usage:{}},"malformed preference rows are discarded");
let learned=searchPreferences.emptySearchPreferences();
learned=searchPreferences.recordSearchAction(learned,"settings",1000,null);
learned=searchPreferences.recordSearchAction(learned,"settings",2000,null);
learned=searchPreferences.recordSearchAction(learned,"report",3000,null);
learned=searchPreferences.toggleSearchPin(learned,"report",null);
assert.deepEqual(searchPreferences.recentSearchActionIds(learned),["report","settings"]);
assert.deepEqual(searchPreferences.frequentSearchActionIds(learned),["settings","report"]);
assert.ok(searchPreferences.searchPreferenceRank(learned,"report",3000)>searchPreferences.searchPreferenceRank(learned,"settings",3000),"pinning preserves discoverability ahead of learned frequency");
