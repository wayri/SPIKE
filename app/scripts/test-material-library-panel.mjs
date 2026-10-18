// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const states=[], effects=[];
let index=0, pending=[], requests=[], reject=false, updated=0;
const react={
  useState(initial){const i=index++;if(!(i in states))states[i]=initial;return[states[i],value=>{states[i]=typeof value==="function"?value(states[i]):value;}];},
  useMemo(fn){index++;return fn();},
  useEffect(fn,deps){const i=index++;if(!effects[i]||!deps.every((value,n)=>Object.is(value,effects[i][n])))pending.push(()=>{effects[i]=deps;fn();});},
};
const jsx={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
const catalog=[{id:"generic-copper",name:"Copper",revision:"1",family:"metal",properties:{}}];
const module={exports:{}};
const compiled=ts.transpileModule(readFileSync(new URL("../src/MaterialLibraryPanel.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function("require","module","exports",compiled)(name=>{
  if(name==="react")return react;
  if(name==="react/jsx-runtime")return jsx;
  if(name==="./icons")return{Layers:()=>null,Search:()=>null,Save:()=>null,RefreshCw:()=>null};
  if(name.endsWith(".css"))return{};
  if(name==="./workerBridge")return{runNativeProjectWorker:async request=>{requests.push(request);return request.method==="list_material_catalog"?{ok:true,result:{materials:catalog}}:reject?{ok:false,error:"Reopen changed project"}:{ok:true,result:{}};}};
  throw Error(name);
},module,module.exports);
const props={projectPath:"assembly.spike",manifestDigest:"a".repeat(64),desktopShell:true,
  assembly:{parts:[],boards:[{id:"board-a",name:"Board",design_id:"design-a",extensions:{}}]},
  designs:{designs:[{design_id:"design-a",layers:[{id:"canonical-layer",name:"Heater foil"}]}]},
  onUpdated:async()=>updated++,onStatus:()=>{},
};
const render=()=>{index=0;pending=[];const tree=module.exports.default(props);pending.forEach(fn=>fn());return tree;};
const find=(tree,test)=>{if(!tree||typeof tree!=="object")return null;if(Array.isArray(tree)){for(const item of tree){const found=find(item,test);if(found)return found;}return null;}return test(tree)?tree:find(tree.props?.children,test);};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
let tree=render();await flush();tree=render();tree=render();
assert.equal(requests.filter(r=>r.method==="assign_material_to_project").length,0,"catalog browsing never writes");
const region=find(tree,node=>node.props?.["aria-label"]==="Material board region");
assert.ok(region,"board region selection uses retained canonical layers");
region.props.onChange({target:{value:"canonical-layer"}});tree=render();
let save=find(tree,node=>node.type==="button"&&node.props.className==="spike-control--primary");
assert.equal(save.props.disabled,false);
await save.props.onClick();await flush();tree=render();
const assigned=requests.find(r=>r.method==="assign_material_to_project").params;
assert.equal(assigned.target_kind,"board_layer");assert.equal(assigned.layer_id,"canonical-layer");
assert.equal(assigned.target_id,"board-a");assert.equal(assigned.expected_manifest_payload_sha256,props.manifestDigest);
assert.equal(updated,1);
reject=true;save=find(tree,node=>node.type==="button"&&node.props.className==="spike-control--primary");
save.props.onClick();await flush();tree=render();
assert.match(find(tree,node=>node.props?.role==="alert").props.children,/Reopen changed project/);
assert.equal(updated,1,"a rejected mutation never refreshes as success");
console.log("Material browser: inert discovery, exact board-layer assignment, manifest binding and recovery passed.");
