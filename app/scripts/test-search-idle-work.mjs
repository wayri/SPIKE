// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import * as search from "../src/universalSearchModel.ts";

let scores=0,discoveries=0,suggestions=0;
const jsx=(type,props)=>({type,props:props??{}}), module={exports:{}};
const code=ts.transpileModule(readFileSync(new URL("../src/UniversalSearch.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function("require","module","exports",code)(id=>{
  if(id==="react")return {useState:initial=>[typeof initial==="function"?initial():initial,()=>{}],useRef:initial=>({current:initial}),useMemo:fn=>fn(),useEffect:()=>{}};
  if(id==="react/jsx-runtime")return {jsx,jsxs:jsx};
  if(id==="./icons")return {};
  if(id==="./focusCommands")return {searchableFocusCommands:()=>{discoveries++;return [];}};
  if(id==="./universalSearchModel")return {...search,scoreUniversalSearchItem:(...args)=>{scores++;return search.scoreUniversalSearchItem(...args);}};
  if(id==="./searchPreferences")return {emptySearchPreferences:()=>({pins:[]}),searchPreferenceRank:()=>0,recentSearchActionIds:()=>[],frequentSearchActionIds:()=>[]};
  return {};
},module,module.exports);
const items=Array.from({length:3000},(_,i)=>({id:`part-${i}`,label:`Inspect part U${i}`,category:"Board",run(){}}));
const props={items,onClose(){},suggestCommands:()=>{suggestions++;return [];}};
for(let i=0;i<10;i++)assert.equal(module.exports.default({...props,open:false}),null);
assert.deepEqual({scores,discoveries,suggestions},{scores:0,discoveries:0,suggestions:0},"closed search does no indexing, ranking or intent generation during parent updates");
assert.ok(module.exports.default({...props,open:true}));
assert.equal(scores,3000,"opening search still ranks the entire current inventory");
assert.equal(discoveries,1);
assert.ok(suggestions>0);
// Execute the actual App workspace-discovery expression with counted builders.
const app=ts.createSourceFile("App.tsx",readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8"),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let workspaceChildren;
const visit=node=>{
  if(ts.isObjectLiteralExpression(node)&&node.properties.some(prop=>ts.isPropertyAssignment(prop)&&prop.name.getText(app)==="id"&&prop.initializer.getText(app)==='"workspaces"')){
    workspaceChildren=node.properties.find(prop=>ts.isPropertyAssignment(prop)&&prop.name.getText(app)==="children").initializer;
  }
  ts.forEachChild(node,visit);
};visit(app);assert.ok(workspaceChildren);
const expression=ts.transpileModule(`const result = ${workspaceChildren.getText(app)};`,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
let builds=0;
const project=(active)=>new Function("commandDiscoveryActive","tabs","ribbonContentFor","focusCommandsFromElements","selectWorkspace",`${expression};return result;`)(active,Array.from({length:12},(_,i)=>({name:`Workspace ${i}`})),()=>{builds++;return null;},()=>[],()=>{});
assert.equal(project(false).length,12,"closed command discovery retains workspace names");
assert.equal(builds,0,"closed discovery does not construct twelve hidden ribbon inventories");
assert.equal(project(true).length,12);assert.equal(builds,12,"open discovery includes every current workspace");
console.log("Search idle-work check passed: 10 closed renders, 3,000 actions, zero rankings/discovery/suggestion calls; open search keeps all candidates.");
